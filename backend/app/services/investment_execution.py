"""定投执行 v2：今日任务、提交、确认、历史。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import AssetCategory, BucketFundConfig, Fund, InvestmentRecord, MonthlyExecution, PEHistory, Transaction, User, UserConfig
from app.services.bucket_config import parse_bucket_config
from app.services.coefficients import calculate_dividend_coefficient, calculate_nasdaq_coefficient
from app.services.dca_amounts import get_last_investment_by_fund
from app.services.daily_planner import build_daily_execution
from app.services.execution_scheduler import (
    build_today_tasks_from_pool,
    compute_next_event,
)
from app.services.execution_calendar import date_info, is_trading_day
from app.services.execution_planner import build_execution_plan
from app.services.fund_fees import enrich_bucket_funds, fee_catalog_from_funds
from app.services.growth_limits import merge_custom_limits, merge_purchase_limits, parse_custom_growth_funds
from app.services.holdings import recalculate_holdings
from app.services.percentile import calculate_percentile


def _load_signals(db: Session, user_id: int) -> dict[str, Any]:
    pe_rows = db.query(PEHistory).order_by(PEHistory.date.desc()).limit(500).all()
    pe_vals = [float(r.pe_ttm) for r in pe_rows if r.pe_ttm]
    pe_pct = calculate_percentile(pe_vals[-1], pe_vals) if pe_vals else 0.5
    nasdaq_coef, nasdaq_label = calculate_nasdaq_coefficient(pe_pct)
    div_yield = 0.045
    div_coef, div_label = calculate_dividend_coefficient(div_yield)
    return {
        "pe_percentile": pe_pct,
        "nasdaq_coef": nasdaq_coef,
        "nasdaq_label": nasdaq_label,
        "div_yield": div_yield,
        "div_coef": div_coef,
        "div_label": div_label,
    }


def _execution_context(db: Session, user: User, as_of: date) -> dict[str, Any]:
    config = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    if config is None:
        return {}
    row = (
        db.query(MonthlyExecution)
        .filter(MonthlyExecution.user_id == user.id, MonthlyExecution.month == as_of.strftime("%Y-%m"))
        .first()
    )
    funds = db.query(Fund).filter(Fund.is_active.is_(True)).all()
    fund_catalog = {f.code: f.name for f in funds}
    custom_funds = parse_custom_growth_funds(row.execution_detail if row and row.execution_detail else {})
    purchase_limits = merge_custom_limits(
        merge_purchase_limits(),
        custom_funds,
    )
    buckets = parse_bucket_config(
        config.bucket_config,
        target_nasdaq=float(config.target_nasdaq_pct),
        target_dividend=float(config.target_dividend_pct),
        target_bond=float(config.target_bond_pct),
    )
    signals = _load_signals(db, user.id)
    labels = {b.code: b.name for b in buckets}
    colors = {b.code: b.color for b in buckets}
    plan = build_execution_plan(
        month=as_of.strftime("%Y-%m"),
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
    )
    plan_dict = plan.to_dict()
    final_by_bucket = {d["bucket"]: d["final_amount"] for d in plan_dict["derivations"]}
    daily = build_daily_execution(
        as_of=as_of,
        month=as_of.strftime("%Y-%m"),
        bucket_amounts=final_by_bucket,
        invested_by_bucket={k: 0.0 for k in final_by_bucket},
        today_invested_by_bucket={k: 0.0 for k in final_by_bucket},
        fund_catalog=fund_catalog,
        purchase_limits=purchase_limits,
        labels=labels,
        colors=colors,
        merged_purchase_limits=purchase_limits,
        execution_detail=row.execution_detail if row and isinstance(row.execution_detail, dict) else {},
    )
    return {
        "daily": daily.to_dict(),
        "labels": labels,
        "fund_catalog": fund_catalog,
    }


def record_to_dict(r: InvestmentRecord) -> dict[str, Any]:
    return {
        "id": r.id,
        "date": r.date.isoformat(),
        "fund_code": r.fund_code,
        "fund_name": r.fund_name,
        "bucket_code": r.bucket_code,
        "record_type": r.record_type,
        "planned_amount": float(r.planned_amount),
        "submitted_amount": float(r.submitted_amount),
        "status": r.status,
        "confirmed_amount": float(r.confirmed_amount) if r.confirmed_amount is not None else None,
        "confirmed_shares": float(r.confirmed_shares) if r.confirmed_shares is not None else None,
        "confirmed_nav": float(r.confirmed_nav) if r.confirmed_nav is not None else None,
        "confirmed_date": r.confirmed_date.isoformat() if r.confirmed_date else None,
        "frequency": r.frequency,
        "notes": r.notes,
    }


def get_today_view(db: Session, user: User, as_of: date | None = None) -> dict[str, Any]:
    target = as_of or date.today()
    real_today = date.today()
    is_today = target == real_today
    is_backfill = target < real_today
    info = date_info(target)
    ctx = _execution_context(db, user, target)
    growth_funds = (ctx.get("daily") or {}).get("growth", {}).get("funds", [])

    if not is_trading_day(target) and is_today:
        nxt = compute_next_event(target, [], [])
        return {
            "date": info["date"],
            "date_label": info["date_label"],
            "weekday": info["weekday"],
            "is_trading_day": False,
            "is_today": True,
            "is_backfill": False,
            "has_tasks": False,
            "bucket_groups": [],
            "skipped_buckets": [],
            "total_amount": 0.0,
            "fee_summary": None,
            "next_event": nxt,
        }

    tasks, skipped = build_today_tasks_from_pool(
        db,
        user.id,
        target,
        growth_fund_amounts=growth_funds,
        backfill=is_backfill or not is_today,
        last_by_fund=get_last_investment_by_fund(db, user.id),
    )
    labels = ctx.get("labels", {})

    pending_tasks = [t for t in tasks if not t.already_submitted]

    scheduled = [t for t in pending_tasks if t.record_type == "scheduled"]
    probe = [t for t in pending_tasks if t.record_type == "probe"]
    submitted_scheduled = [t for t in tasks if t.already_submitted and t.record_type == "scheduled"]
    submitted_probe = [t for t in tasks if t.already_submitted and t.record_type == "probe"]

    bucket_groups: list[dict] = []
    if scheduled:
        by_bucket: dict[str, list] = {}
        for t in scheduled:
            by_bucket.setdefault(t.bucket_code, []).append(t.to_dict())
        for code, items in by_bucket.items():
            bucket_groups.append(
                {
                    "bucket_code": code,
                    "bucket_name": labels.get(code, code),
                    "record_type": "scheduled",
                    "funds": items,
                    "total_amount": sum(i["planned_amount"] for i in items),
                }
            )
    if probe:
        bucket_groups.append(
            {
                "bucket_code": "growth",
                "bucket_name": "试探性买入",
                "record_type": "probe",
                "funds": [t.to_dict() for t in probe],
                "total_amount": sum(t.planned_amount for t in probe),
                "hint": "非正式定投，仅测试额度是否放开",
            }
        )

    submitted_all = submitted_scheduled + submitted_probe
    if submitted_all and (is_backfill or not is_today):
        bucket_groups.append(
            {
                "bucket_code": "submitted",
                "bucket_name": "该日已录入",
                "record_type": "submitted",
                "funds": [t.to_dict() for t in submitted_all],
                "total_amount": sum(t.planned_amount for t in submitted_all),
                "hint": "以下基金在该日已有记录，无需重复提交",
            }
        )

    fee_tasks = pending_tasks
    all_fund_dicts = [t.to_dict() for t in fee_tasks]
    funds_for_fee = [
        {
            "fund_code": f["fund_code"],
            "fund_name": f["fund_name"],
            "planned_amount": f["planned_amount"],
        }
        for f in all_fund_dicts
    ]
    fee_catalog = fee_catalog_from_funds(db.query(Fund).filter(Fund.is_active.is_(True)).all())
    _, fee_summary = enrich_bucket_funds(funds_for_fee, fee_catalog) if funds_for_fee else ([], None)

    total = sum(t.planned_amount for t in pending_tasks)
    return {
        "date": info["date"],
        "date_label": info["date_label"],
        "weekday": info["weekday"],
        "is_trading_day": is_trading_day(target),
        "is_today": is_today,
        "is_backfill": is_backfill,
        "has_tasks": len(pending_tasks) > 0,
        "bucket_groups": bucket_groups,
        "skipped_buckets": skipped if is_today else [],
        "total_amount": total,
        "fee_summary": fee_summary,
        "next_event": compute_next_event(target, pending_tasks, skipped) if is_today and not pending_tasks else None,
    }


def submit_today(
    db: Session,
    user: User,
    *,
    tasks: list[dict],
    skip_codes: list[str] | None = None,
    as_of: date | None = None,
) -> list[InvestmentRecord]:
    today = as_of or date.today()
    skip = set(skip_codes or [])
    created: list[InvestmentRecord] = []
    for item in tasks:
        code = str(item["fund_code"])
        if code in skip:
            continue
        amount = Decimal(str(item.get("amount", item.get("planned_amount", 0))))
        if amount <= 0:
            continue
        if (
            db.query(InvestmentRecord)
            .filter(
                InvestmentRecord.user_id == user.id,
                InvestmentRecord.fund_code == code,
                InvestmentRecord.date == today,
            )
            .first()
        ):
            continue
        row = InvestmentRecord(
            user_id=user.id,
            date=today,
            fund_code=code,
            fund_name=str(item.get("fund_name", code)),
            bucket_code=str(item.get("bucket_code", "growth")),
            record_type=str(item.get("record_type", "scheduled")),
            planned_amount=amount,
            submitted_amount=amount,
            status="pending",
            frequency=str(item.get("frequency", "daily")),
        )
        db.add(row)
        created.append(row)
        pool_row = (
            db.query(BucketFundConfig)
            .filter(BucketFundConfig.user_id == user.id, BucketFundConfig.fund_code == code)
            .first()
        )
        if pool_row is not None:
            pool_row.daily_limit = amount
    db.commit()
    for r in created:
        db.refresh(r)
    return created


def list_pending(db: Session, user_id: int, limit: int = 50) -> list[dict]:
    """仅返回 status=pending 的记录（已确认/失败等见本月记录）。"""
    rows = (
        db.query(InvestmentRecord)
        .filter(InvestmentRecord.user_id == user_id, InvestmentRecord.status == "pending")
        .order_by(InvestmentRecord.date.desc(), InvestmentRecord.id.desc())
        .limit(limit)
        .all()
    )
    return [record_to_dict(r) for r in rows]


def confirm_record(
    db: Session,
    user: User,
    record_id: int,
    *,
    status: str,
    confirmed_amount: float | None = None,
    confirmed_shares: float | None = None,
    confirmed_nav: float | None = None,
    confirmed_date: str | None = None,
) -> InvestmentRecord:
    row = (
        db.query(InvestmentRecord)
        .filter(InvestmentRecord.user_id == user.id, InvestmentRecord.id == record_id)
        .first()
    )
    if row is None:
        raise ValueError("记录不存在")
    row.status = status
    if confirmed_amount is not None:
        row.confirmed_amount = Decimal(str(confirmed_amount))
    if confirmed_shares is not None:
        row.confirmed_shares = Decimal(str(confirmed_shares))
    if confirmed_nav is not None:
        row.confirmed_nav = Decimal(str(confirmed_nav))
    if confirmed_date:
        row.confirmed_date = date.fromisoformat(confirmed_date)

    if status in ("confirmed", "partial") and row.confirmed_amount and row.confirmed_nav:
        fund = db.query(Fund).filter(Fund.code == row.fund_code).first()
        if fund is None:
            cat = db.query(AssetCategory).filter(AssetCategory.code == "NASDAQ").first()
            fund = Fund(
                code=row.fund_code,
                name=row.fund_name,
                category_id=cat.id if cat else 1,
                fund_type="otc_link",
                priority=3,
                annual_fee_rate=Decimal("0.01"),
                purchase_fee_rate=Decimal("0.0012"),
                is_active=True,
            )
            db.add(fund)
            db.flush()
        shares = row.confirmed_shares
        if shares is None and row.confirmed_nav > 0:
            shares = row.confirmed_amount / row.confirmed_nav
        txn_date = row.confirmed_date or row.date
        db.add(
            Transaction(
                user_id=user.id,
                date=txn_date,
                fund_id=fund.id,
                txn_type="buy",
                amount=row.confirmed_amount,
                nav=row.confirmed_nav,
                shares=shares or Decimal(0),
                notes=f"定投确认 #{row.id}",
            )
        )
    db.commit()
    db.refresh(row)
    recalculate_holdings(db, user.id)
    return row


def month_history(
    db: Session,
    user_id: int,
    month: str,
    *,
    status: str = "all",
) -> dict[str, Any]:
    q = db.query(InvestmentRecord).filter(
        InvestmentRecord.user_id == user_id,
        InvestmentRecord.date >= date.fromisoformat(f"{month}-01"),
    )
    y, m = map(int, month.split("-"))
    if m == 12:
        end = date(y + 1, 1, 1)
    else:
        end = date(y, m + 1, 1)
    q = q.filter(InvestmentRecord.date < end)
    if status != "all":
        q = q.filter(InvestmentRecord.status == status)
    rows = q.order_by(InvestmentRecord.date.desc(), InvestmentRecord.id.desc()).all()

    total_submitted = sum(float(r.submitted_amount) for r in rows)
    total_confirmed = sum(float(r.confirmed_amount or 0) for r in rows if r.status in ("confirmed", "partial"))
    total_failed = sum(float(r.submitted_amount) for r in rows if r.status == "failed")

    # 按日聚合展示
    by_day: dict[str, list[InvestmentRecord]] = {}
    for r in rows:
        by_day.setdefault(r.date.isoformat(), []).append(r)

    day_rows: list[dict] = []
    for day_key in sorted(by_day.keys(), reverse=True):
        day_items = by_day[day_key]
        codes = sorted({i.fund_code for i in day_items})
        label = f"{len(codes)}只" if len(codes) > 1 else day_items[0].fund_name
        if len(codes) == 1:
            label = f"{codes[0]}{day_items[0].fund_name[:6]}"
        statuses = {i.status for i in day_items}
        if "pending" in statuses:
            result = "pending"
        elif statuses == {"failed"}:
            result = "failed"
        elif "partial" in statuses:
            result = "partial"
        else:
            result = "confirmed"
        day_rows.append(
            {
                "date": day_key,
                "label": label,
                "record_type": day_items[0].record_type,
                "fund_count": len(day_items),
                "amount": sum(float(i.submitted_amount) for i in day_items),
                "status": result,
                "records": [record_to_dict(i) for i in day_items],
            }
        )

    return {
        "month": month,
        "summary": {
            "total_submitted": total_submitted,
            "total_confirmed": total_confirmed,
            "total_failed": total_failed,
        },
        "days": day_rows,
    }
