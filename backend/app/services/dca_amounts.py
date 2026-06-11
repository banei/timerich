"""定投金额解析：上次实际提交金额 vs 基金池配置。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import BucketFundConfig, InvestmentRecord


def amount_from_last_record(row: InvestmentRecord) -> float:
    """最近一次定投记录对应的默认定投金额。"""
    if row.status == "failed":
        return 0.0
    if row.status in ("confirmed", "partial") and row.confirmed_amount is not None:
        return float(row.confirmed_amount)
    return float(row.submitted_amount)


def get_last_investment_by_fund(db: Session, user_id: int) -> dict[str, dict[str, Any]]:
    """每只基金最近一次定投记录（金额 + 时间）。"""
    rows = (
        db.query(InvestmentRecord)
        .filter(InvestmentRecord.user_id == user_id)
        .order_by(InvestmentRecord.date.desc(), InvestmentRecord.id.desc())
        .all()
    )
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.fund_code in out:
            continue
        amt = amount_from_last_record(row)
        if amt <= 0 and row.status != "failed":
            continue
        out[row.fund_code] = {"amount": amt, "at": row.created_at, "status": row.status}
    return out


def sync_pool_defaults_from_records(db: Session, user_id: int) -> list[dict[str, Any]]:
    """将基金池内每只基金最近一次定投结果写入 daily_limit（失败 → 0 并暂停）。"""
    rows = (
        db.query(InvestmentRecord)
        .filter(InvestmentRecord.user_id == user_id)
        .order_by(InvestmentRecord.date.desc(), InvestmentRecord.id.desc())
        .all()
    )
    last_by_code: dict[str, InvestmentRecord] = {}
    for row in rows:
        if row.fund_code not in last_by_code:
            last_by_code[row.fund_code] = row

    pool = (
        db.query(BucketFundConfig)
        .filter(BucketFundConfig.user_id == user_id)
        .order_by(BucketFundConfig.sort_order, BucketFundConfig.id)
        .all()
    )
    updates: list[dict[str, Any]] = []
    for item in pool:
        last = last_by_code.get(item.fund_code)
        if last is None:
            continue
        amt = amount_from_last_record(last)
        old = float(item.daily_limit)
        item.daily_limit = Decimal(str(amt))
        if amt <= 0:
            item.status = "paused"
        elif item.status == "paused":
            item.status = "active"
        updates.append(
            {
                "fund_code": item.fund_code,
                "fund_name": item.fund_name,
                "old_amount": old,
                "new_amount": amt,
                "last_status": last.status,
            }
        )
    if updates:
        db.commit()
    return updates


def resolve_dca_amount(
    fund_code: str,
    pool_amount: float,
    pool_updated_at: datetime | None,
    last_by_fund: dict[str, dict[str, Any]],
    *,
    growth_plan_amount: float | None = None,
) -> float:
    """
    定投默认金额：
    1. 基金池在最后一次提交之后有修改 → 用池配置
    2. 否则有历史提交 → 用上次金额
    3. 否则月度计划分配
    4. 否则池配置
    """
    pool_amount = float(pool_amount or 0)
    last = last_by_fund.get(fund_code)
    if last and pool_updated_at is not None and pool_updated_at > last["at"]:
        return pool_amount
    if last:
        return float(last["amount"])
    if growth_plan_amount is not None and growth_plan_amount > 0:
        return float(growth_plan_amount)
    return pool_amount
