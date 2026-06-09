"""基金申购费用估算（基于基金池费率，外扣式）。"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.models import Fund


def _money(value: float | Decimal) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calc_purchase_fee(amount: float, purchase_fee_rate: float) -> float:
    """外扣式申购费：申购金额 × 费率 / (1 + 费率)。"""
    if amount <= 0 or purchase_fee_rate <= 0:
        return 0.0
    fee = amount * purchase_fee_rate / (1 + purchase_fee_rate)
    return _money(fee)


def fee_catalog_from_funds(funds: list[Fund]) -> dict[str, dict[str, float]]:
    catalog: dict[str, dict[str, float]] = {}
    for fund in funds:
        catalog[fund.code] = {
            "purchase_fee_rate": float(fund.purchase_fee_rate),
            "annual_fee_rate": float(fund.annual_fee_rate),
            "redemption_fee_2y": float(fund.redemption_fee_2y or 0),
        }
    return catalog


def enrich_fund_allocation(alloc: dict[str, Any], catalog: dict[str, dict[str, float]]) -> dict[str, Any]:
    meta = catalog.get(alloc.get("fund_code", ""), {})
    rate = float(meta.get("purchase_fee_rate", 0) or 0)
    amount = float(alloc.get("planned_amount", 0) or 0)
    fee = calc_purchase_fee(amount, rate)
    net = _money(amount - fee)
    result = dict(alloc)
    result["purchase_fee_rate"] = rate
    result["annual_fee_rate"] = float(meta.get("annual_fee_rate", 0) or 0)
    result["purchase_fee_amount"] = fee
    result["net_invested_amount"] = net
    return result


def summarize_fund_fees(funds: list[dict[str, Any]]) -> dict[str, float]:
    total_planned = _money(sum(float(f.get("planned_amount", 0) or 0) for f in funds))
    total_fee = _money(sum(float(f.get("purchase_fee_amount", 0) or 0) for f in funds))
    total_net = _money(sum(float(f.get("net_invested_amount", 0) or 0) for f in funds))
    return {
        "total_planned": total_planned,
        "total_purchase_fee": total_fee,
        "total_net_invested": total_net,
    }


def enrich_bucket_funds(
    funds: list[dict[str, Any]],
    catalog: dict[str, dict[str, float]],
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    enriched = [enrich_fund_allocation(f, catalog) for f in funds]
    summary = summarize_fund_fees(enriched)
    return enriched, summary


def apply_fees_to_plan_dict(plan_dict: dict[str, Any], catalog: dict[str, dict[str, float]]) -> dict[str, Any]:
    """为执行计划各基金分配附加申购费，并汇总费用。"""
    for bucket in plan_dict.get("bucket_executions", []):
        funds, summary = enrich_bucket_funds(bucket.get("funds", []), catalog)
        bucket["funds"] = funds
        if funds:
            bucket["fee_summary"] = summary

    daily = plan_dict.get("daily")
    if daily and isinstance(daily, dict):
        growth = daily.get("growth")
        if growth and isinstance(growth, dict):
            funds, summary = enrich_bucket_funds(growth.get("funds", []), catalog)
            growth["funds"] = funds
            if funds:
                growth["fee_summary"] = summary

    month_funds: list[dict[str, Any]] = []
    for bucket in plan_dict.get("bucket_executions", []):
        month_funds.extend(bucket.get("funds", []))
    if month_funds:
        plan_dict["fee_summary"] = summarize_fund_fees(month_funds)

    if daily and daily.get("growth", {}).get("fee_summary"):
        plan_dict["daily_fee_summary"] = daily["growth"]["fee_summary"]

    return plan_dict
