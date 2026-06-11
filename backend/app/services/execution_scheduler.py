"""今日定投任务调度：按频率与基金池生成待执行列表。"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import BucketFundConfig, InvestmentRecord
from app.services.execution_calendar import (
    date_info,
    is_trading_day,
    last_trading_day,
    next_trading_day_on_or_after,
    weekday_zh,
)
from app.services.dca_amounts import get_last_investment_by_fund, resolve_dca_amount
from app.services.fund_pool import seed_default_fund_pool
from app.services.growth_limits import merge_purchase_limits, resolve_daily_limit

WEEKDAY_MAP = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}


def get_effective_monthly_day(year: int, month: int, day_num: int) -> date:
    last = calendar.monthrange(year, month)[1]
    d = date(year, month, min(day_num, last))
    return next_trading_day_on_or_after(d)


def should_buy_today(frequency: str, today: date) -> bool:
    if frequency == "manual":
        return False
    if frequency == "daily":
        return True
    if frequency.startswith("weekly_"):
        key = frequency.split("_", 1)[1].upper()
        return today.weekday() == WEEKDAY_MAP.get(key, -1)
    if frequency.startswith("monthly_"):
        try:
            day_num = int(frequency.split("_", 1)[1])
        except (IndexError, ValueError):
            return False
        return get_effective_monthly_day(today.year, today.month, day_num) == today
    return False


def already_submitted_today(db: Session, user_id: int, fund_code: str, today: date) -> bool:
    return get_record_for_date(db, user_id, fund_code, today) is not None


def get_record_for_date(
    db: Session, user_id: int, fund_code: str, on_date: date
) -> InvestmentRecord | None:
    return (
        db.query(InvestmentRecord)
        .filter(
            InvestmentRecord.user_id == user_id,
            InvestmentRecord.fund_code == fund_code,
            InvestmentRecord.date == on_date,
        )
        .first()
    )


def _task_default_selected(frequency: str, today: date, *, existing: InvestmentRecord | None) -> bool:
    """非每日频率仅在计划日默认勾选；手动频率不自动勾选。"""
    if existing is not None:
        return False
    if frequency == "daily":
        return True
    if frequency == "manual":
        return False
    return should_buy_today(frequency, today)


def _make_pool_task(
    item: BucketFundConfig,
    *,
    today: date,
    amt: float,
    purchase_limits: dict,
    existing: InvestmentRecord | None = None,
) -> TodayFundTask:
    plat_limit, _ = resolve_daily_limit(item.fund_code, purchase_limits)
    purchase_limit = float(plat_limit) if plat_limit is not None else None
    display_amt = float(existing.submitted_amount) if existing else amt
    label = _limit_label(purchase_limit, item.status, display_amt)
    if existing is not None:
        label = f"已录入·{existing.status}"
    return TodayFundTask(
        fund_code=item.fund_code,
        fund_name=item.fund_name,
        bucket_code=item.bucket_code,
        record_type="probe" if item.buy_type == "probe" else "scheduled",
        planned_amount=display_amt,
        daily_limit=display_amt,
        limit_label=label,
        selected=_task_default_selected(item.frequency, today, existing=existing),
        frequency=item.frequency,
        pool_id=item.id,
        purchase_limit=purchase_limit,
        already_submitted=existing is not None,
        record_status=existing.status if existing else None,
    )


def next_buy_hint(frequency: str, today: date) -> str:
    if frequency == "daily":
        nxt = today + timedelta(days=1)
        while not is_trading_day(nxt):
            nxt += timedelta(days=1)
        return date_info(nxt)["date_label"]
    if frequency.startswith("weekly_"):
        key = frequency.split("_", 1)[1].upper()
        target = WEEKDAY_MAP.get(key, 0)
        d = today + timedelta(days=1)
        for _ in range(14):
            if d.weekday() == target and is_trading_day(d):
                return date_info(d)["date_label"]
            d += timedelta(days=1)
    if frequency.startswith("monthly_"):
        try:
            day_num = int(frequency.split("_", 1)[1])
        except (IndexError, ValueError):
            return "—"
        y, m = today.year, today.month
        if today >= get_effective_monthly_day(y, m, day_num):
            m = m + 1 if m < 12 else 1
            y = y if m > 1 else y + 1
        eff = get_effective_monthly_day(y, m, day_num)
        return date_info(eff)["date_label"]
    return "手动触发"


@dataclass
class TodayFundTask:
    fund_code: str
    fund_name: str
    bucket_code: str
    record_type: str
    planned_amount: float
    daily_limit: float | None
    limit_label: str
    selected: bool = True
    frequency: str = "daily"
    pool_id: int | None = None
    purchase_limit: float | None = None
    already_submitted: bool = False
    record_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "fund_code": self.fund_code,
            "fund_name": self.fund_name,
            "bucket_code": self.bucket_code,
            "record_type": self.record_type,
            "planned_amount": self.planned_amount,
            "daily_limit": self.daily_limit,
            "limit_label": self.limit_label,
            "selected": self.selected,
            "frequency": self.frequency,
            "pool_id": self.pool_id,
            "purchase_limit": self.purchase_limit,
            "already_submitted": self.already_submitted,
            "record_status": self.record_status,
        }


def _limit_label(purchase_limit: float | None, status: str, dca_amount: float) -> str:
    if status == "paused" or dca_amount <= 0:
        return "暂停"
    if purchase_limit is None:
        return "正常"
    if purchase_limit <= 0:
        return "平台暂停"
    return f"限购¥{purchase_limit:.0f}" if purchase_limit < 1000 else "正常"


def build_today_tasks_from_pool(
    db: Session,
    user_id: int,
    today: date,
    *,
    growth_fund_amounts: list[dict] | None = None,
    backfill: bool = False,
    last_by_fund: dict[str, dict] | None = None,
) -> tuple[list[TodayFundTask], list[dict]]:
    """返回 (今日任务, 跳过的桶提示)。backfill=True 时包含已录入项并可在无计划任务时展示全池。"""
    seed_default_fund_pool(db, user_id)
    pool = (
        db.query(BucketFundConfig)
        .filter(BucketFundConfig.user_id == user_id, BucketFundConfig.status == "active")
        .order_by(BucketFundConfig.sort_order)
        .all()
    )
    purchase_limits = merge_purchase_limits()
    last_map = last_by_fund or {}

    tasks: list[TodayFundTask] = []
    skipped_buckets: list[dict] = []

    growth_scheduled: dict[str, float] = {}
    if growth_fund_amounts:
        for f in growth_fund_amounts:
            growth_scheduled[str(f["fund_code"])] = float(f.get("planned_amount", 0))

    growth_codes_in_plan = set(growth_scheduled.keys())

    for item in pool:
        if item.bucket_code != "growth":
            continue
        if not should_buy_today(item.frequency, today) and not (backfill and item.frequency == "manual"):
            continue
        existing = get_record_for_date(db, user_id, item.fund_code, today)
        if existing is not None and not backfill:
            continue
        plan_amt = growth_scheduled.get(item.fund_code) if item.fund_code in growth_codes_in_plan else None
        amt = resolve_dca_amount(
            item.fund_code,
            float(item.daily_limit),
            item.updated_at,
            last_map,
            growth_plan_amount=plan_amt if item.buy_type == "scheduled" else None,
        )

        if amt <= 0 and existing is None:
            continue

        tasks.append(_make_pool_task(item, today=today, amt=amt, purchase_limits=purchase_limits, existing=existing))

    # 计划里有、池里没有配置的正式基金也纳入
    for code, plan_amt in growth_scheduled.items():
        existing = get_record_for_date(db, user_id, code, today)
        if existing is not None and not backfill:
            continue
        pool_item = next((p for p in pool if p.fund_code == code), None)
        pool_amt = float(pool_item.daily_limit) if pool_item else 0.0
        pool_updated = pool_item.updated_at if pool_item else None
        amt = resolve_dca_amount(code, pool_amt, pool_updated, last_map, growth_plan_amount=plan_amt)
        if amt <= 0 and existing is None:
            continue
        if any(t.fund_code == code for t in tasks):
            continue
        name = code
        for f in growth_fund_amounts or []:
            if f["fund_code"] == code:
                name = f.get("fund_name", code)
                break
        freq = pool_item.frequency if pool_item else "daily"
        tasks.append(
            TodayFundTask(
                fund_code=code,
                fund_name=name,
                bucket_code="growth",
                record_type="scheduled",
                planned_amount=float(existing.submitted_amount) if existing else amt,
                daily_limit=None,
                limit_label="已录入" if existing else "正常",
                selected=_task_default_selected(freq, today, existing=existing),
                frequency=freq,
                already_submitted=existing is not None,
                record_status=existing.status if existing else None,
            )
        )

    # 补录：无频率命中时展示全部可买基金供手动勾选
    if backfill and not any(not t.already_submitted for t in tasks):
        seen = {t.fund_code for t in tasks}
        for item in pool:
            if item.fund_code in seen or item.status != "active":
                continue
            amt = resolve_dca_amount(
                item.fund_code,
                float(item.daily_limit),
                item.updated_at,
                last_map,
            )
            if amt <= 0:
                continue
            existing = get_record_for_date(db, user_id, item.fund_code, today)
            tasks.append(_make_pool_task(item, today=today, amt=amt, purchase_limits=purchase_limits, existing=existing))
            seen.add(item.fund_code)

    # 非 growth 桶：仅提示下次
    bucket_names = {
        "dividend": "红利桶",
        "gold": "黄金桶",
        "bond_long": "长债桶",
        "bond_short": "短债桶",
    }
    for bucket, label in bucket_names.items():
        items = [i for i in pool if i.bucket_code == bucket and i.status == "active"]
        if not items:
            continue
        due = any(should_buy_today(i.frequency, today) for i in items)
        if due:
            for item in items:
                if not should_buy_today(item.frequency, today):
                    continue
                existing = get_record_for_date(db, user_id, item.fund_code, today)
                if existing is not None and not backfill:
                    continue
                amt = resolve_dca_amount(
                    item.fund_code,
                    float(item.daily_limit),
                    item.updated_at,
                    last_map,
                )
                if amt <= 0 and existing is None:
                    continue
                tasks.append(_make_pool_task(item, today=today, amt=amt, purchase_limits=purchase_limits, existing=existing))
        else:
            freq = items[0].frequency
            skipped_buckets.append(
                {
                    "bucket_code": bucket,
                    "bucket_name": label,
                    "message": f"今日无需买入（下次: {next_buy_hint(freq, today)}）",
                }
            )

    return tasks, skipped_buckets


def compute_next_event(today: date, tasks: list[TodayFundTask], skipped: list[dict]) -> dict | None:
    if tasks:
        return None
    if skipped:
        first = skipped[0]
        hint = first["message"].replace("今日无需买入（下次: ", "").replace("）", "")
        return {"date_label": hint, "bucket_name": first["bucket_name"], "days_until": 1}
    nxt = today + timedelta(days=1)
    while not is_trading_day(nxt):
        nxt += timedelta(days=1)
    return {
        "date_label": date_info(nxt)["date_label"],
        "bucket_name": "成长桶",
        "days_until": max(1, (nxt - today).days),
    }
