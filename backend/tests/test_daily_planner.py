"""日定投计划单测。"""

from datetime import date

from app.services.daily_planner import (
    build_daily_execution,
    even_daily_amount,
    trading_days_in_month,
    trading_days_remaining,
)


def test_even_daily_split_mid_month():
    # 2026-06 有 22 个工作日；6月9日剩余约 17 天
    as_of = date(2026, 6, 9)
    days_rem = trading_days_remaining(as_of)
    daily = even_daily_amount(1700, days_rem)
    assert daily > 0
    assert daily * days_rem == 1700.0


def test_growth_daily_plan_with_limits():
    as_of = date(2026, 6, 9)
    ctx = build_daily_execution(
        as_of=as_of,
        month="2026-06",
        bucket_amounts={"growth": 2000, "dividend": 0, "gold": 0, "bond_long": 0, "bond_short": 0},
        invested_by_bucket={"growth": 0},
        today_invested_by_bucket={"growth": 0},
        fund_catalog={"270042": "广发纳指100联接A", "000834": "大成纳指100联接A"},
        purchase_limits={"270042": 300},
        labels={"growth": "成长档"},
        colors={"growth": "#3ABFF8"},
    )
    g = ctx.growth
    assert g.mode == "daily"
    assert g.monthly_planned == 2000
    assert g.today_target > 0
    assert len(g.funds) >= 1
    assert g.funds[0]["fund_code"] == "270042"
    assert g.funds[0]["planned_amount"] <= 300
    assert len(ctx.schedule) == trading_days_remaining(as_of)


def test_month_complete_no_today_target():
    as_of = date(2026, 6, 9)
    ctx = build_daily_execution(
        as_of=as_of,
        month="2026-06",
        bucket_amounts={"growth": 1000},
        invested_by_bucket={"growth": 1000},
        today_invested_by_bucket={"growth": 0},
        fund_catalog={},
        purchase_limits={},
        labels={"growth": "成长档"},
        colors={"growth": "#3ABFF8"},
    )
    assert ctx.growth.monthly_remaining == 0
    assert ctx.growth.today_target == 0
    assert ctx.growth.funds == []
