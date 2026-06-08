from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import MonthlyCoefficient, PEHistory, User, UserConfig
from app.schemas.common import ApiResponse
from app.services.advice import (
    build_allocation_advice,
    build_dividend_advice,
    build_nasdaq_advice,
    build_overall_advice,
    build_spillover_advice,
)
from app.services.allocation import calculate_monthly_amounts
from app.services.coefficients import calculate_dividend_coefficient, calculate_nasdaq_coefficient
from app.services.holdings import category_totals, holdings_with_funds
from app.services.market_data import MarketDataService
from app.services.percentile import calculate_percentile

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _load_signal_inputs(db: Session) -> dict:
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

    return {
        "ndx": ndx,
        "h30269": h30269,
        "pe_percentile": pe_percentile,
        "nasdaq_coef": nasdaq_coef,
        "nasdaq_label": nasdaq_label,
        "div_yield": div_yield,
        "div_coef": div_coef,
        "div_label": div_label,
    }


@router.get("/summary", response_model=ApiResponse)
def summary(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    config = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    holdings = holdings_with_funds(db, user.id)
    totals = category_totals(db, user.id)
    total_value = sum((h["current_value"] for h in holdings), Decimal(0))
    total_invested = sum((h["total_invested"] for h in holdings), Decimal(0))
    profit = total_value - total_invested
    profit_rate = float(profit / total_invested) if total_invested > 0 else 0.0

    family_pct = None
    if config and config.family_total_assets and config.family_total_assets > 0:
        family_pct = float(total_value / config.family_total_assets)

    return ApiResponse(
        data={
            "total_value": str(total_value),
            "total_invested": str(total_invested),
            "profit": str(profit),
            "profit_rate": profit_rate,
            "family_pct": family_pct,
            "family_limit": str(config.max_total_pct_of_family) if config else None,
            "category_totals": {k: str(v) for k, v in totals.items()},
        }
    )


@router.get("/signals", response_model=ApiResponse)
def signals(db: Annotated[Session, Depends(get_db)]):
    s = _load_signal_inputs(db)
    ndx = s["ndx"]
    nasdaq_advice = build_nasdaq_advice(s["pe_percentile"], s["nasdaq_coef"], s["nasdaq_label"])
    dividend_advice = build_dividend_advice(s["div_yield"], s["div_coef"], s["div_label"])

    return ApiResponse(
        data={
            "nasdaq": {
                "pe_percentile": s["pe_percentile"],
                "coefficient": s["nasdaq_coef"],
                "label": s["nasdaq_label"],
                "pe_ttm": str(ndx.pe_ttm) if ndx and ndx.pe_ttm else None,
                "advice": nasdaq_advice,
            },
            "dividend": {
                "dividend_yield": s["div_yield"],
                "coefficient": s["div_coef"],
                "label": s["div_label"],
                "advice": dividend_advice,
            },
        }
    )


@router.get("/advice", response_model=ApiResponse)
def advice(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    config = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    s = _load_signal_inputs(db)

    nasdaq_advice = build_nasdaq_advice(s["pe_percentile"], s["nasdaq_coef"], s["nasdaq_label"])
    dividend_advice = build_dividend_advice(s["div_yield"], s["div_coef"], s["div_label"])

    amounts = {"nasdaq": 0.0, "dividend": 0.0, "bond": 0.0}
    if config:
        month = date.today().strftime("%Y-%m")
        coef = db.query(MonthlyCoefficient).filter(
            MonthlyCoefficient.user_id == user.id, MonthlyCoefficient.month == month
        ).first()
        nasdaq_c = float(coef.nasdaq_coefficient) if coef else s["nasdaq_coef"]
        div_c = float(coef.dividend_coefficient) if coef else s["div_coef"]
        amounts = calculate_monthly_amounts(
            float(config.monthly_budget),
            {
                "nasdaq": float(config.target_nasdaq_pct),
                "dividend": float(config.target_dividend_pct),
                "bond": float(config.target_bond_pct),
            },
            {"nasdaq": nasdaq_c, "dividend": div_c},
        )

    spillover_advice = build_spillover_advice(s["nasdaq_coef"], s["div_coef"], amounts)

    deviations: dict[str, float] = {}
    threshold_passive = 0.05
    threshold_active = 0.10
    if config:
        threshold_passive = float(config.rebalance_threshold_passive)
        threshold_active = float(config.rebalance_threshold_active)
        totals = category_totals(db, user.id)
        total = sum(totals.values(), Decimal(0))
        if total > 0:
            nasdaq_val = totals.get("NASDAQ", Decimal(0)) + totals.get("SP500", Decimal(0))
            current = {
                "nasdaq": float(nasdaq_val / total),
                "dividend": float(totals.get("DIVIDEND", Decimal(0)) / total),
                "bond": float(totals.get("BOND", Decimal(0)) / total),
            }
            target = {
                "nasdaq": float(config.target_nasdaq_pct),
                "dividend": float(config.target_dividend_pct),
                "bond": float(config.target_bond_pct),
            }
            deviations = {k: current[k] - target[k] for k in target}

    allocation_advice = build_allocation_advice(deviations, threshold_passive, threshold_active)
    overall = build_overall_advice(nasdaq_advice, dividend_advice, spillover_advice, allocation_advice)

    return ApiResponse(
        data={
            "overall": overall,
            "nasdaq": nasdaq_advice,
            "dividend": dividend_advice,
            "spillover": spillover_advice,
            "allocation": allocation_advice,
            "amounts": amounts,
        }
    )


@router.get("/allocation", response_model=ApiResponse)
def allocation(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    config = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    totals = category_totals(db, user.id)
    total = sum(totals.values(), Decimal(0))
    if total <= 0 or config is None:
        return ApiResponse(data={"current": {}, "target": {}, "deviations": {}})

    nasdaq_val = totals.get("NASDAQ", Decimal(0)) + totals.get("SP500", Decimal(0))
    current = {
        "nasdaq": float(nasdaq_val / total),
        "dividend": float(totals.get("DIVIDEND", Decimal(0)) / total),
        "bond": float(totals.get("BOND", Decimal(0)) / total),
    }
    target = {
        "nasdaq": float(config.target_nasdaq_pct),
        "dividend": float(config.target_dividend_pct),
        "bond": float(config.target_bond_pct),
    }
    deviations = {k: current[k] - target[k] for k in target}
    alloc_advice = build_allocation_advice(
        deviations,
        float(config.rebalance_threshold_passive),
        float(config.rebalance_threshold_active),
    )
    return ApiResponse(
        data={
            "current": current,
            "target": target,
            "deviations": deviations,
            "total": str(total),
            "advice": alloc_advice,
        }
    )


@router.post("/refresh", response_model=ApiResponse)
def refresh(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    force = user.role == "admin"
    svc = MarketDataService(db)
    results = svc.daily_refresh(force=force)
    return ApiResponse(data=results, meta={"forced": force})


@router.get("/execution-preview", response_model=ApiResponse)
def execution_preview(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    config = db.query(UserConfig).filter(UserConfig.user_id == user.id).first()
    month = date.today().strftime("%Y-%m")
    coef = db.query(MonthlyCoefficient).filter(
        MonthlyCoefficient.user_id == user.id, MonthlyCoefficient.month == month
    ).first()

    s = _load_signal_inputs(db)
    nasdaq_c = float(coef.nasdaq_coefficient) if coef else s["nasdaq_coef"]
    div_c = float(coef.dividend_coefficient) if coef else s["div_coef"]

    if config is None:
        return ApiResponse(data={})

    amounts = calculate_monthly_amounts(
        float(config.monthly_budget),
        {
            "nasdaq": float(config.target_nasdaq_pct),
            "dividend": float(config.target_dividend_pct),
            "bond": float(config.target_bond_pct),
        },
        {"nasdaq": nasdaq_c, "dividend": div_c},
    )
    return ApiResponse(
        data={
            "month": month,
            "coefficients": {"nasdaq": nasdaq_c, "dividend": div_c},
            "amounts": amounts,
            "budget": str(config.monthly_budget),
        }
    )
