"""日定投计划：将月预算按剩余交易日均摊，并结合限购生成当日可执行清单。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.services.execution_calendar import (
    date_info,
    is_trading_day,
    last_trading_day,
    month_weekdays,
    next_trading_day_on_or_after,
)
from app.services.daily_dca import build_dca_batch, get_today_dca_record, memory_fund_codes
from app.services.execution_planner import BOND_FUNDS, DIVIDEND_FUNDS, plan_growth_bucket, _money
from app.services.growth_limits import (
    effective_growth_ladder,
    growth_fund_roster,
    growth_limit_snapshot,
    merge_custom_limits,
    parse_custom_growth_funds,
)


def trading_days_in_month(year: int, month: int) -> int:
    return len(month_weekdays(year, month))


def trading_days_remaining(as_of: date) -> int:
    return sum(1 for d in month_weekdays(as_of.year, as_of.month) if d >= as_of)


def trading_days_elapsed(as_of: date) -> int:
    return sum(1 for d in month_weekdays(as_of.year, as_of.month) if d < as_of)


def even_daily_amount(monthly_remaining: float, days_remaining: int) -> float:
    if days_remaining <= 0 or monthly_remaining <= 0:
        return 0.0
    return _money(monthly_remaining / days_remaining)


@dataclass
class DailyBucketPlan:
    bucket: str
    name: str
    color: str
    mode: str
    monthly_planned: float
    monthly_invested: float
    monthly_remaining: float
    days_remaining: int
    today_target: float
    today_invested: float
    funds: list[dict[str, Any]] = field(default_factory=list)
    execution_notes: list[str] = field(default_factory=list)
    fee_summary: dict[str, float] | None = None
    action_date: str | None = None
    weekday: str | None = None
    date_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "name": self.name,
            "color": self.color,
            "mode": self.mode,
            "monthly_planned": self.monthly_planned,
            "monthly_invested": self.monthly_invested,
            "monthly_remaining": self.monthly_remaining,
            "days_remaining": self.days_remaining,
            "today_target": self.today_target,
            "today_invested": self.today_invested,
            "funds": self.funds,
            "execution_notes": self.execution_notes,
            "fee_summary": self.fee_summary,
            "action_date": self.action_date,
            "weekday": self.weekday,
            "date_label": self.date_label,
        }


@dataclass
class DailyExecutionContext:
    date: str
    month: str
    is_trading_day: bool
    trading_days_in_month: int
    trading_days_remaining: int
    trading_days_elapsed: int
    growth: DailyBucketPlan
    other_buckets: list[DailyBucketPlan] = field(default_factory=list)
    schedule: list[dict[str, Any]] = field(default_factory=list)
    growth_limits: list[dict[str, Any]] = field(default_factory=list)
    ndx_roster: list[dict[str, Any]] = field(default_factory=list)
    custom_growth_funds: list[dict[str, Any]] = field(default_factory=list)
    dca_batch: dict[str, Any] = field(default_factory=dict)
    date_label: str = ""
    weekday: str = ""
    next_trading_date: str | None = None
    next_trading_date_label: str | None = None
    month_end_date: str | None = None
    month_end_date_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "date_label": self.date_label,
            "weekday": self.weekday,
            "month": self.month,
            "is_trading_day": self.is_trading_day,
            "next_trading_date": self.next_trading_date,
            "next_trading_date_label": self.next_trading_date_label,
            "month_end_date": self.month_end_date,
            "month_end_date_label": self.month_end_date_label,
            "trading_days_in_month": self.trading_days_in_month,
            "trading_days_remaining": self.trading_days_remaining,
            "trading_days_elapsed": self.trading_days_elapsed,
            "growth": self.growth.to_dict(),
            "other_buckets": [b.to_dict() for b in self.other_buckets],
            "schedule": self.schedule,
            "growth_limits": self.growth_limits,
            "ndx_roster": self.ndx_roster,
            "custom_growth_funds": self.custom_growth_funds,
            "dca_batch": self.dca_batch,
        }


def _build_growth_schedule(as_of: date, monthly_remaining: float) -> list[dict[str, Any]]:
    schedule: list[dict[str, Any]] = []
    remaining = monthly_remaining
    for d in month_weekdays(as_of.year, as_of.month):
        if d < as_of:
            continue
        days_left = trading_days_remaining(d)
        target = even_daily_amount(remaining, days_left)
        info = date_info(d)
        schedule.append(
            {
                "date": info["date"],
                "weekday": info["weekday"],
                "date_label": info["date_label"],
                "target_amount": target,
                "is_today": d == as_of,
            }
        )
    return schedule


def build_daily_execution(
    *,
    as_of: date,
    month: str,
    bucket_amounts: dict[str, float],
    invested_by_bucket: dict[str, float],
    today_invested_by_bucket: dict[str, float],
    fund_catalog: dict[str, str] | None,
    purchase_limits: dict[str, float] | None,
    labels: dict[str, str],
    colors: dict[str, str],
    merged_purchase_limits: dict[str, float] | None = None,
    dca_memory: dict[str, Any] | None = None,
    execution_detail: dict[str, Any] | None = None,
) -> DailyExecutionContext:
    year, mon = map(int, month.split("-"))
    days_in_month = trading_days_in_month(year, mon)
    days_rem = trading_days_remaining(as_of)
    days_elapsed = trading_days_elapsed(as_of)
    trading_today = is_trading_day(as_of)
    today_info = date_info(as_of)
    next_td = next_trading_day_on_or_after(as_of)
    next_info = date_info(next_td)
    month_end = last_trading_day(year, mon)
    month_end_info = date_info(month_end)

    growth_planned = bucket_amounts.get("growth", 0.0)
    growth_invested = invested_by_bucket.get("growth", 0.0)
    growth_remaining = max(_money(growth_planned - growth_invested), 0.0)
    today_growth_target = even_daily_amount(growth_remaining, days_rem) if trading_today else 0.0

    growth_notes: list[str] = []
    if not trading_today:
        growth_notes.append(
            f"今日非交易日，请于 {next_info['date_label']} 继续按剩余额度均摊"
        )
    elif growth_remaining <= 0:
        growth_notes.append("本月成长档计划额度已投满")
    else:
        growth_notes.append(
            f"月剩余 ¥{growth_remaining:,.0f} ÷ {days_rem} 个交易日 ≈ 今日目标 ¥{today_growth_target:,.0f}"
        )

    memory = dca_memory or {}
    detail = execution_detail or {}
    custom_funds = parse_custom_growth_funds(detail)
    growth_ladder = effective_growth_ladder(custom_funds)
    effective_limits = merge_custom_limits(
        merged_purchase_limits or purchase_limits or {},
        custom_funds,
    )

    preferred_codes: list[str] | None = None
    if memory.get("active"):
        codes = memory_fund_codes(memory)
        if codes:
            preferred_codes = codes

    growth_funds: list[dict[str, Any]] = []
    if today_growth_target > 0:
        bucket_plan = plan_growth_bucket(
            today_growth_target,
            fund_catalog,
            effective_limits,
            name=labels.get("growth"),
            color=colors.get("growth"),
            preferred_fund_codes=preferred_codes,
            growth_ladder=growth_ladder,
        )
        growth_funds = [f.to_dict() for f in bucket_plan.funds]
        if len(growth_funds) > 1:
            growth_notes.insert(
                0,
                f"今日目标需 {len(growth_funds)} 只纳指联接凑额度（按阶梯日限购依次买满）",
            )
        growth_notes.extend(bucket_plan.execution_notes)

    growth_action = next_info if not trading_today else today_info
    growth_plan = DailyBucketPlan(
        bucket="growth",
        name=labels.get("growth", "成长档"),
        color=colors.get("growth", "#3ABFF8"),
        mode="daily",
        monthly_planned=growth_planned,
        monthly_invested=growth_invested,
        monthly_remaining=growth_remaining,
        days_remaining=days_rem,
        today_target=today_growth_target,
        today_invested=today_invested_by_bucket.get("growth", 0.0),
        funds=growth_funds,
        execution_notes=growth_notes,
        action_date=growth_action["date"],
        weekday=growth_action["weekday"],
        date_label=growth_action["date_label"],
    )

    other_codes = {
        "dividend": list(DIVIDEND_FUNDS.values()),
        "gold": ["518880"],
        "bond_long": [BOND_FUNDS["long"]],
        "bond_short": [BOND_FUNDS["short"]],
    }
    other_buckets: list[DailyBucketPlan] = []
    for code in ("dividend", "gold", "bond_long", "bond_short"):
        planned = bucket_amounts.get(code, 0.0)
        invested = invested_by_bucket.get(code, 0.0)
        remaining = max(_money(planned - invested), 0.0)
        notes: list[str] = []
        if planned > 0 and remaining > 0:
            notes.append(f"建议操作日：{month_end_info['date_label']}（月末最后交易日）")
        elif planned > 0 and remaining <= 0:
            notes.append("本月该桶计划额度已投满")
        other_buckets.append(
            DailyBucketPlan(
                bucket=code,
                name=labels.get(code, code),
                color=colors.get(code, "#7C8DB0"),
                mode="monthly",
                monthly_planned=planned,
                monthly_invested=invested,
                monthly_remaining=remaining,
                days_remaining=days_rem,
                today_target=0.0,
                today_invested=today_invested_by_bucket.get(code, 0.0),
                funds=[],
                execution_notes=notes,
                action_date=month_end_info["date"],
                weekday=month_end_info["weekday"],
                date_label=month_end_info["date_label"],
            )
        )

    schedule = _build_growth_schedule(as_of, growth_remaining)
    limit_rows = growth_limit_snapshot(effective_limits, fund_catalog, custom_funds=custom_funds)
    roster = growth_fund_roster(effective_limits, fund_catalog, custom_funds=custom_funds)

    action_date = growth_action["date"]
    today_record = get_today_dca_record(execution_detail, action_date)
    dca_batch = build_dca_batch(
        proposed_funds=growth_funds,
        memory=memory,
        today_record=today_record,
        action_date=action_date,
        fund_catalog=fund_catalog,
    )

    return DailyExecutionContext(
        date=as_of.isoformat(),
        date_label=today_info["date_label"],
        weekday=today_info["weekday"],
        month=month,
        is_trading_day=trading_today,
        next_trading_date=None if trading_today else next_info["date"],
        next_trading_date_label=None if trading_today else next_info["date_label"],
        month_end_date=month_end_info["date"],
        month_end_date_label=month_end_info["date_label"],
        trading_days_in_month=days_in_month,
        trading_days_remaining=days_rem,
        trading_days_elapsed=days_elapsed,
        growth=growth_plan,
        other_buckets=other_buckets,
        schedule=schedule,
        growth_limits=limit_rows,
        ndx_roster=roster,
        custom_growth_funds=custom_funds,
        dca_batch=dca_batch,
    )
