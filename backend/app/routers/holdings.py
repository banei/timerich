from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import AssetCategory, Fund, FundQuote, MonthlyCoefficient, MonthlyExecution, PEHistory, Transaction, User, UserConfig
from app.schemas.common import (
    ApiResponse,
    CustomGrowthFundAdd,
    CustomGrowthFundsUpdate,
    DailyDcaCancel,
    DailyDcaConfirm,
    ExecutionAmountOverrides,
    ExecutionStepUpdate,
    GrowthPurchaseLimitsUpdate,
    TransactionCreate,
    TransactionOut,
)
from app.services.daily_dca import (
    MEMORY_KEY,
    cancel_daily_dca,
    confirm_daily_dca,
    copy_memory_to_execution_detail,
    get_daily_dca_memory,
    stop_daily_dca_memory,
)
from app.services.allocation import calculate_monthly_amounts
from app.services.coefficients import calculate_dividend_coefficient, calculate_nasdaq_coefficient
from app.services.bucket_config import parse_bucket_config
from app.services.daily_planner import build_daily_execution
from app.services.execution_calendar import build_action_steps, date_info, first_trading_day, last_trading_day
from app.services.execution_planner import BOND_FUNDS, DIVIDEND_FUNDS, build_execution_plan
from app.services.fund_fees import apply_fees_to_plan_dict, fee_catalog_from_funds
from app.services.fund_nav import enrich_daily_dca_batch, enrich_funds_for_confirm
from app.services.growth_limits import (
    CUSTOM_GROWTH_FUNDS_KEY,
    all_growth_fund_codes,
    all_growth_fund_codes_with_custom,
    merge_custom_limits,
    merge_purchase_limits,
    normalize_fund_code,
    parse_custom_growth_funds,
)
from app.services.fund_purchase import fetch_em_purchase_for_codes
from app.services.holdings import holdings_with_funds, recalculate_holdings
from app.services.market_data import MarketDataService
from app.services.percentile import calculate_percentile

router = APIRouter(tags=["holdings"])


@router.get("/holdings", response_model=ApiResponse)
def get_holdings(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return ApiResponse(data=holdings_with_funds(db, user.id))


@router.get("/transactions", response_model=ApiResponse[list[TransactionOut]])
def list_transactions(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    rows = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(200)
        .all()
    )
    return ApiResponse(data=[TransactionOut.model_validate(r) for r in rows])


@router.post("/transactions", response_model=ApiResponse[TransactionOut])
def create_transaction(
    body: TransactionCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    fund = db.get(Fund, body.fund_id)
    if fund is None:
        raise HTTPException(status_code=404, detail="基金不存在")

    shares = body.shares
    if shares is None and body.nav > 0:
        shares = body.amount / body.nav

    txn = Transaction(
        user_id=user.id,
        date=date.fromisoformat(body.date),
        fund_id=body.fund_id,
        txn_type=body.txn_type,
        amount=body.amount,
        nav=body.nav,
        shares=shares or Decimal(0),
        coefficient=body.coefficient,
        notes=body.notes,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    recalculate_holdings(db, user.id)
    return ApiResponse(data=TransactionOut.model_validate(txn))


@router.delete("/transactions/{txn_id}", response_model=ApiResponse)
def delete_transaction(
    txn_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    txn = db.get(Transaction, txn_id)
    if txn is None or txn.user_id != user.id:
        raise HTTPException(status_code=404, detail="交易不存在")
    db.delete(txn)
    db.commit()
    recalculate_holdings(db, user.id)
    return ApiResponse(data={"deleted": txn_id})


execution_router = APIRouter(prefix="/execution", tags=["execution"])

STEP_MAP = {
    "check_signals": "step_check_signals",
    "calc_amounts": "step_calc_amounts",
    "execute_nasdaq": "step_execute_nasdaq",
    "check_premium": "step_check_premium",
    "execute_dividend": "step_execute_dividend",
    "execute_bond": "step_execute_bond",
    "record": "step_record",
}


def _load_execution_signals(db: Session, user_id: int) -> dict:
    svc = MarketDataService(db)
    ndx = svc.get_latest_index("NDX")
    h30269 = svc.get_latest_index("H30269")

    pe_percentile = 0.5
    if ndx and ndx.pe_ttm:
        history = [float(r.pe_ttm) for r in db.query(PEHistory).all()]
        if history:
            pe_percentile = calculate_percentile(float(ndx.pe_ttm), history)

    nasdaq_coef, nasdaq_label = calculate_nasdaq_coefficient(pe_percentile)
    div_yield = float(h30269.dividend_yield) if h30269 and h30269.dividend_yield else 0.047
    div_coef, div_label = calculate_dividend_coefficient(div_yield)

    month = date.today().strftime("%Y-%m")
    coef_row = (
        db.query(MonthlyCoefficient)
        .filter(MonthlyCoefficient.user_id == user_id, MonthlyCoefficient.month == month)
        .first()
    )
    if coef_row:
        nasdaq_coef = float(coef_row.nasdaq_coefficient)
        div_coef = float(coef_row.dividend_coefficient)

    return {
        "pe_percentile": pe_percentile,
        "nasdaq_coef": nasdaq_coef,
        "nasdaq_label": nasdaq_label,
        "div_yield": div_yield,
        "div_coef": div_coef,
        "div_label": div_label,
    }


def _month_date_range(month: str) -> tuple[date, date]:
    year, mon = map(int, month.split("-"))
    start = date(year, mon, 1)
    if mon == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, mon + 1, 1)
    return start, end


def _invested_for_funds(
    db: Session,
    user_id: int,
    fund_codes: list[str],
    start: date,
    end: date,
) -> float:
    if not fund_codes:
        return 0.0
    funds = db.query(Fund).filter(Fund.code.in_(fund_codes)).all()
    fund_ids = [f.id for f in funds]
    if not fund_ids:
        return 0.0
    total = (
        db.query(func.sum(Transaction.amount))
        .filter(
            Transaction.user_id == user_id,
            Transaction.fund_id.in_(fund_ids),
            Transaction.txn_type == "buy",
            Transaction.date >= start,
            Transaction.date < end,
        )
        .scalar()
    )
    return float(total or 0)


def _invested_by_bucket(
    db: Session,
    user_id: int,
    month: str,
    *,
    extra_growth_codes: list[str] | None = None,
) -> dict[str, float]:
    start, end = _month_date_range(month)
    growth_codes = all_growth_fund_codes_with_custom(
        [{"fund_code": c} for c in (extra_growth_codes or [])]
    )
    return {
        "growth": _invested_for_funds(db, user_id, growth_codes, start, end),
        "dividend": _invested_for_funds(db, user_id, list(DIVIDEND_FUNDS.values()), start, end),
        "gold": _invested_for_funds(db, user_id, ["518880"], start, end),
        "bond_long": _invested_for_funds(db, user_id, [BOND_FUNDS["long"]], start, end),
        "bond_short": _invested_for_funds(db, user_id, [BOND_FUNDS["short"]], start, end),
    }


def _today_invested_by_bucket(
    db: Session,
    user_id: int,
    as_of: date,
    *,
    extra_growth_codes: list[str] | None = None,
) -> dict[str, float]:
    start = as_of
    end = as_of + timedelta(days=1)
    growth_codes = all_growth_fund_codes_with_custom(
        [{"fund_code": c} for c in (extra_growth_codes or [])]
    )
    return {
        "growth": _invested_for_funds(db, user_id, growth_codes, start, end),
        "dividend": _invested_for_funds(db, user_id, list(DIVIDEND_FUNDS.values()), start, end),
        "gold": _invested_for_funds(db, user_id, ["518880"], start, end),
        "bond_long": _invested_for_funds(db, user_id, [BOND_FUNDS["long"]], start, end),
        "bond_short": _invested_for_funds(db, user_id, [BOND_FUNDS["short"]], start, end),
    }


def _growth_limit_overrides(row: MonthlyExecution) -> dict[str, float]:
    if not row.execution_detail or not isinstance(row.execution_detail, dict):
        return {}
    raw = row.execution_detail.get("growth_purchase_limits")
    if not isinstance(raw, dict):
        return {}
    return {str(k): float(v) for k, v in raw.items()}


def _custom_growth_funds(row: MonthlyExecution) -> list[dict]:
    if not row.execution_detail or not isinstance(row.execution_detail, dict):
        return []
    return parse_custom_growth_funds(row.execution_detail)


def _ensure_growth_fund(db: Session, code: str, name: str) -> Fund:
    row = db.query(Fund).filter(Fund.code == code).first()
    if row:
        if name and name != code and row.name in {code, ""}:
            row.name = name
        if not row.is_active:
            row.is_active = True
        return row
    cat = db.query(AssetCategory).filter(AssetCategory.code == "NASDAQ").first()
    cat_id = cat.id if cat else 1
    row = Fund(
        code=code,
        name=name or code,
        category_id=cat_id,
        fund_type="otc_link",
        priority=3,
        annual_fee_rate=Decimal("0.010000"),
        purchase_fee_rate=Decimal("0.001200"),
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _normalize_custom_fund_item(body: CustomGrowthFundAdd, fund_catalog: dict[str, str]) -> dict:
    code = normalize_fund_code(body.fund_code)
    name = (body.fund_name or "").strip() or fund_catalog.get(code) or code
    daily_limit = float(body.daily_limit) if body.daily_limit is not None else 300.0
    return {
        "fund_code": code,
        "fund_name": name,
        "daily_limit": daily_limit,
        "tier": int(body.tier),
    }


def _lookup_fund_meta(code: str) -> tuple[str, float | None]:
    """尝试从东方财富拉取名称与日限购，失败则返回占位。"""
    try:
        infos = fetch_em_purchase_for_codes([code])
        if infos:
            info = infos[0]
            limit = info.daily_limit if info.daily_limit is not None else 300.0
            if info.status == "paused":
                limit = 0.0
            return info.fund_name or code, limit
    except Exception:
        pass
    return code, None


def _load_purchase_limits(db: Session, fund_codes: list[str]) -> dict[str, float]:
    funds = db.query(Fund).filter(Fund.code.in_(fund_codes)).all()
    limits: dict[str, float] = {}
    for fund in funds:
        quote = (
            db.query(FundQuote)
            .filter(FundQuote.fund_id == fund.id)
            .order_by(FundQuote.date.desc())
            .first()
        )
        if quote and quote.purchase_limit is not None:
            limits[fund.code] = float(quote.purchase_limit)
    return limits


def _get_or_create_execution(db: Session, user: User) -> MonthlyExecution:
    month = date.today().strftime("%Y-%m")
    row = (
        db.query(MonthlyExecution)
        .filter(MonthlyExecution.user_id == user.id, MonthlyExecution.month == month)
        .first()
    )
    if row:
        return row

    config = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    amounts = {"nasdaq": 0, "dividend": 0, "bond": 0}
    if config:
        amounts = calculate_monthly_amounts(
            float(config.monthly_budget),
            {
                "nasdaq": float(config.target_nasdaq_pct),
                "dividend": float(config.target_dividend_pct),
                "bond": float(config.target_bond_pct),
            },
            {"nasdaq": 1.0, "dividend": 1.0},
        )

    y, m = map(int, month.split("-"))
    prev_month = f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"

    prev_row = (
        db.query(MonthlyExecution)
        .filter(MonthlyExecution.user_id == user.id, MonthlyExecution.month == prev_month)
        .first()
    )
    execution_detail = None
    if prev_row and prev_row.execution_detail and isinstance(prev_row.execution_detail, dict):
        prev_mem = prev_row.execution_detail.get(MEMORY_KEY)
        if isinstance(prev_mem, dict):
            execution_detail = copy_memory_to_execution_detail(None, prev_mem)
        prev_custom = prev_row.execution_detail.get(CUSTOM_GROWTH_FUNDS_KEY)
        if isinstance(prev_custom, list) and prev_custom:
            execution_detail = dict(execution_detail or {})
            execution_detail[CUSTOM_GROWTH_FUNDS_KEY] = prev_custom

    row = MonthlyExecution(
        user_id=user.id,
        month=month,
        planned_nasdaq_amount=Decimal(str(amounts["nasdaq"])),
        planned_dividend_amount=Decimal(str(amounts["dividend"])),
        planned_bond_amount=Decimal(str(amounts["bond"])),
        execution_detail=execution_detail,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@execution_router.get("/plan", response_model=ApiResponse)
def execution_plan(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    live_nav: bool = Query(False, description="为日定投批量确认实时拉取缺失/过期净值"),
):
    config = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    if config is None:
        return ApiResponse(data={})

    row = _get_or_create_execution(db, user)
    signals = _load_execution_signals(db, user.id)
    funds = db.query(Fund).filter(Fund.is_active.is_(True)).all()
    fund_catalog = {f.code: f.name for f in funds}

    overrides: dict[str, float] | None = None
    if row.execution_detail and isinstance(row.execution_detail, dict):
        raw = row.execution_detail.get("amount_overrides")
        if isinstance(raw, dict):
            overrides = {k: float(v) for k, v in raw.items()}

    buckets = parse_bucket_config(
        config.bucket_config,
        target_nasdaq=float(config.target_nasdaq_pct),
        target_dividend=float(config.target_dividend_pct),
        target_bond=float(config.target_bond_pct),
    )
    custom_funds = _custom_growth_funds(row)
    db_limits = _load_purchase_limits(db, all_growth_fund_codes_with_custom(custom_funds))
    limit_overrides = _growth_limit_overrides(row)
    purchase_limits = merge_purchase_limits(db_limits=db_limits, user_overrides=limit_overrides)
    purchase_limits = merge_custom_limits(purchase_limits, custom_funds)
    labels = {b.code: b.name for b in buckets}
    colors = {b.code: b.color for b in buckets}

    plan = build_execution_plan(
        month=row.month,
        budget=float(config.monthly_budget),
        buckets=buckets,
        pe_percentile=signals["pe_percentile"],
        nasdaq_coef=signals["nasdaq_coef"],
        nasdaq_label=signals["nasdaq_label"],
        dividend_yield=signals["div_yield"],
        dividend_coef=signals["div_coef"],
        dividend_label=signals["div_label"],
        fund_catalog=fund_catalog,
        purchase_limits=purchase_limits,
        amount_overrides=overrides,
    )
    plan_dict = plan.to_dict()
    final_by_bucket = {d["bucket"]: d["final_amount"] for d in plan_dict["derivations"]}
    as_of = date.today()
    custom_codes = [f["fund_code"] for f in custom_funds]
    invested = _invested_by_bucket(db, user.id, row.month, extra_growth_codes=custom_codes)
    today_invested = _today_invested_by_bucket(db, user.id, as_of, extra_growth_codes=custom_codes)
    dca_memory = get_daily_dca_memory(db, user.id, row.month)
    execution_detail = row.execution_detail if isinstance(row.execution_detail, dict) else {}
    daily = build_daily_execution(
        as_of=as_of,
        month=row.month,
        bucket_amounts=final_by_bucket,
        invested_by_bucket=invested,
        today_invested_by_bucket=today_invested,
        fund_catalog=fund_catalog,
        purchase_limits=purchase_limits,
        labels=labels,
        colors=colors,
        merged_purchase_limits=purchase_limits,
        dca_memory=dca_memory,
        execution_detail=execution_detail,
    )
    daily_dict = daily.to_dict()
    plan_dict["daily"] = daily_dict
    plan_dict["action_steps"] = build_action_steps(row.month, as_of)

    year, mon = map(int, row.month.split("-"))
    month_start_info = date_info(first_trading_day(year, mon))
    month_end_info = date_info(last_trading_day(year, mon))
    plan_dict["month_start"] = month_start_info
    plan_dict["month_end"] = month_end_info

    growth_action = daily_dict.get("growth") or {}
    for bucket in plan_dict.get("bucket_executions", []):
        if bucket.get("bucket") == "growth":
            bucket["action_date"] = growth_action.get("action_date")
            bucket["weekday"] = growth_action.get("weekday")
            bucket["date_label"] = growth_action.get("date_label")
        else:
            bucket["action_date"] = month_end_info["date"]
            bucket["weekday"] = month_end_info["weekday"]
            bucket["date_label"] = month_end_info["date_label"]

    fee_catalog = fee_catalog_from_funds(funds)
    plan_dict = apply_fees_to_plan_dict(plan_dict, fee_catalog)
    plan_dict = enrich_daily_dca_batch(db, plan_dict, funds, live=live_nav)

    return ApiResponse(data=plan_dict)


@execution_router.put("/{month}/growth-limits", response_model=ApiResponse)
def update_growth_limits(
    month: str,
    body: GrowthPurchaseLimitsUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    row = (
        db.query(MonthlyExecution)
        .filter(MonthlyExecution.user_id == user.id, MonthlyExecution.month == month)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="月度执行单不存在")

    detail = dict(row.execution_detail or {})
    existing = detail.get("growth_purchase_limits")
    merged_limits = dict(existing) if isinstance(existing, dict) else {}
    for code, value in body.limits.items():
        merged_limits[code] = str(value)
    detail["growth_purchase_limits"] = merged_limits
    row.execution_detail = detail
    db.commit()
    return ApiResponse(data={"month": month, "growth_purchase_limits": merged_limits})


@execution_router.post("/{month}/custom-growth-funds", response_model=ApiResponse)
def add_custom_growth_fund(
    month: str,
    body: CustomGrowthFundAdd,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    row = _execution_row_or_404(db, user.id, month)
    funds = db.query(Fund).filter(Fund.is_active.is_(True)).all()
    fund_catalog = {f.code: f.name for f in funds}

    try:
        code = normalize_fund_code(body.fund_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = _custom_growth_funds(row)
    if any(item["fund_code"] == code for item in existing):
        raise HTTPException(status_code=400, detail="该基金已在自定义列表中")
    if code in all_growth_fund_codes():
        raise HTTPException(status_code=400, detail="该基金已在内置纳指名单中，请直接在「日限购设置」调整")

    name = (body.fund_name or "").strip() or fund_catalog.get(code)
    daily_limit = float(body.daily_limit) if body.daily_limit is not None else None
    if not name or name == code:
        fetched_name, fetched_limit = _lookup_fund_meta(code)
        name = name or fetched_name
        if daily_limit is None and fetched_limit is not None:
            daily_limit = fetched_limit
    if daily_limit is None:
        daily_limit = 300.0

    item = {
        "fund_code": code,
        "fund_name": name or code,
        "daily_limit": daily_limit,
        "tier": int(body.tier),
    }
    _ensure_growth_fund(db, code, item["fund_name"])

    detail = dict(row.execution_detail or {})
    custom_list = list(existing)
    custom_list.append(item)
    detail[CUSTOM_GROWTH_FUNDS_KEY] = custom_list
    row.execution_detail = detail
    db.commit()
    return ApiResponse(data={"month": month, "custom_growth_funds": custom_list})


@execution_router.put("/{month}/custom-growth-funds", response_model=ApiResponse)
def replace_custom_growth_funds(
    month: str,
    body: CustomGrowthFundsUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    row = _execution_row_or_404(db, user.id, month)
    funds = db.query(Fund).filter(Fund.is_active.is_(True)).all()
    fund_catalog = {f.code: f.name for f in funds}

    custom_list: list[dict] = []
    seen: set[str] = set()
    for entry in body.funds:
        try:
            item = _normalize_custom_fund_item(entry, fund_catalog)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if item["fund_code"] in seen:
            continue
        seen.add(item["fund_code"])
        _ensure_growth_fund(db, item["fund_code"], item["fund_name"])
        custom_list.append(item)

    detail = dict(row.execution_detail or {})
    detail[CUSTOM_GROWTH_FUNDS_KEY] = custom_list
    row.execution_detail = detail
    db.commit()
    return ApiResponse(data={"month": month, "custom_growth_funds": custom_list})


@execution_router.delete("/{month}/custom-growth-funds/{fund_code}", response_model=ApiResponse)
def remove_custom_growth_fund(
    month: str,
    fund_code: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    row = _execution_row_or_404(db, user.id, month)
    try:
        code = normalize_fund_code(fund_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = _custom_growth_funds(row)
    custom_list = [item for item in existing if item["fund_code"] != code]
    if len(custom_list) == len(existing):
        raise HTTPException(status_code=404, detail="自定义基金不存在")

    detail = dict(row.execution_detail or {})
    detail[CUSTOM_GROWTH_FUNDS_KEY] = custom_list
    row.execution_detail = detail
    db.commit()
    return ApiResponse(data={"month": month, "custom_growth_funds": custom_list})


def _execution_row_or_404(db: Session, user_id: int, month: str) -> MonthlyExecution:
    row = (
        db.query(MonthlyExecution)
        .filter(MonthlyExecution.user_id == user_id, MonthlyExecution.month == month)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="月度执行单不存在")
    return row


@execution_router.put("/{month}/daily-dca/confirm", response_model=ApiResponse)
def confirm_daily_dca_batch(
    month: str,
    body: DailyDcaConfirm,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    row = _execution_row_or_404(db, user.id, month)
    funds = db.query(Fund).filter(Fund.is_active.is_(True)).all()
    fund_catalog = {f.code: f.name for f in funds}
    payload = [
        {
            "fund_code": item.fund_code,
            "fund_name": item.fund_name,
            "planned_amount": float(item.planned_amount),
            "selected": item.selected,
        }
        for item in body.funds
    ]
    active_funds = db.query(Fund).filter(Fund.is_active.is_(True)).all()
    payload = enrich_funds_for_confirm(db, payload, active_funds, live=True)
    try:
        result = confirm_daily_dca(
            row,
            action_date=body.action_date,
            funds=payload,
            fund_catalog=fund_catalog,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row.step_execute_nasdaq = True
    db.commit()
    return ApiResponse(data=result)


@execution_router.put("/{month}/daily-dca/cancel", response_model=ApiResponse)
def cancel_daily_dca_batch(
    month: str,
    body: DailyDcaCancel,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    row = _execution_row_or_404(db, user.id, month)
    funds = db.query(Fund).filter(Fund.is_active.is_(True)).all()
    fund_catalog = {f.code: f.name for f in funds}
    proposed = [
        {
            "fund_code": item.fund_code,
            "fund_name": item.fund_name,
            "planned_amount": float(item.planned_amount),
            "selected": item.selected,
        }
        for item in body.funds
    ]
    result = cancel_daily_dca(
        row,
        action_date=body.action_date,
        stop_memory=body.stop_memory,
        proposed_funds=proposed,
        fund_catalog=fund_catalog,
    )
    db.commit()
    return ApiResponse(data=result)


@execution_router.put("/{month}/daily-dca/stop", response_model=ApiResponse)
def stop_daily_dca(
    month: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    row = _execution_row_or_404(db, user.id, month)
    memory = stop_daily_dca_memory(row)
    db.commit()
    return ApiResponse(data={"memory": memory})


@execution_router.get("/current-month", response_model=ApiResponse)
def current_month(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    row = _get_or_create_execution(db, user)
    steps = {
        "check_signals": row.step_check_signals,
        "calc_amounts": row.step_calc_amounts,
        "execute_nasdaq": row.step_execute_nasdaq,
        "check_premium": row.step_check_premium,
        "execute_dividend": row.step_execute_dividend,
        "execute_bond": row.step_execute_bond,
        "record": row.step_record,
    }
    done = sum(1 for v in steps.values() if v)
    return ApiResponse(
        data={
            "month": row.month,
            "steps": steps,
            "progress": f"{done}/7",
            "planned": {
                "nasdaq": str(row.planned_nasdaq_amount),
                "dividend": str(row.planned_dividend_amount),
                "bond": str(row.planned_bond_amount),
            },
        }
    )


@execution_router.put("/{month}/amounts", response_model=ApiResponse)
def update_execution_amounts(
    month: str,
    body: ExecutionAmountOverrides,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    row = (
        db.query(MonthlyExecution)
        .filter(MonthlyExecution.user_id == user.id, MonthlyExecution.month == month)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="月度执行单不存在")

    detail = dict(row.execution_detail or {})
    detail["amount_overrides"] = {k: str(v) for k, v in body.amounts.items()}
    row.execution_detail = detail

    if "growth" in body.amounts:
        row.planned_nasdaq_amount = body.amounts["growth"]
    if "dividend" in body.amounts:
        row.planned_dividend_amount = body.amounts["dividend"]
    bond_total = body.amounts.get("bond_long", Decimal(0)) + body.amounts.get("bond_short", Decimal(0))
    if bond_total > 0:
        row.planned_bond_amount = bond_total

    db.commit()
    return ApiResponse(data={"month": month, "amount_overrides": detail["amount_overrides"]})


@execution_router.put("/{month}/step/{step_name}", response_model=ApiResponse)
def update_step(
    month: str,
    step_name: str,
    body: ExecutionStepUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    field = STEP_MAP.get(step_name)
    if field is None:
        raise HTTPException(status_code=400, detail="未知步骤")
    row = (
        db.query(MonthlyExecution)
        .filter(MonthlyExecution.user_id == user.id, MonthlyExecution.month == month)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="月度执行单不存在")
    setattr(row, field, body.completed)
    db.commit()
    return ApiResponse(data={"step": step_name, "completed": body.completed})


@execution_router.post("/{month}/complete", response_model=ApiResponse)
def complete_month(
    month: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    from datetime import datetime

    row = (
        db.query(MonthlyExecution)
        .filter(MonthlyExecution.user_id == user.id, MonthlyExecution.month == month)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="月度执行单不存在")
    row.completed_at = datetime.utcnow()
    db.commit()
    return ApiResponse(data={"completed_at": row.completed_at.isoformat()})
