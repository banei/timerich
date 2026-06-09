"""日定投记忆与批量确认单测。"""

from datetime import date

from app.services.daily_dca import (
    build_dca_batch,
    cancel_daily_dca,
    confirm_daily_dca,
    empty_memory,
    stop_daily_dca_memory,
)
from app.services.daily_planner import build_daily_execution
from app.services.execution_planner import plan_growth_bucket


def test_plan_growth_with_memory_codes():
    plan = plan_growth_bucket(
        350,
        {"270042": "广发纳指100", "000834": "大成纳指100"},
        {"270042": 300, "000834": 300},
        preferred_fund_codes=["270042", "000834"],
    )
    codes = [f.fund_code for f in plan.funds]
    assert codes == ["270042", "000834"]
    assert sum(f.planned_amount for f in plan.funds) == 350


def test_build_dca_batch_defaults_from_memory():
    memory = {
        "active": True,
        "fund_codes": ["270042", "000834"],
        "last_action_date": "2026-06-08",
    }
    proposed = [
        {"fund_code": "270042", "fund_name": "A", "planned_amount": 10},
        {"fund_code": "000834", "fund_name": "B", "planned_amount": 70},
    ]
    batch = build_dca_batch(
        proposed_funds=proposed,
        memory=memory,
        today_record=None,
        action_date="2026-06-09",
        fund_catalog={},
    )
    assert batch["status"] == "pending"
    assert all(i["selected"] for i in batch["items"])
    assert batch["total_selected"] == 80


def test_confirm_and_cancel_memory_flow():
    class Row:
        execution_detail = None

    row = Row()
    confirm_daily_dca(
        row,
        action_date="2026-06-09",
        funds=[
            {"fund_code": "270042", "planned_amount": 10, "selected": True},
            {"fund_code": "000834", "planned_amount": 70, "selected": True},
        ],
        fund_catalog={"270042": "A", "000834": "B"},
    )
    assert row.execution_detail["daily_dca_memory"]["active"] is True
    assert row.execution_detail["daily_dca_memory"]["fund_codes"] == ["270042", "000834"]

    cancel_daily_dca(row, action_date="2026-06-10", stop_memory=True, proposed_funds=[])
    assert row.execution_detail["daily_dca_days"]["2026-06-10"]["status"] == "cancelled"
    assert row.execution_detail["daily_dca_memory"]["active"] is False

    row2 = Row()
    stop_daily_dca_memory(row2)
    assert row2.execution_detail["daily_dca_memory"] == empty_memory()


def test_daily_execution_applies_memory():
    memory = {"active": True, "fund_codes": ["270042"], "funds": []}
    ctx = build_daily_execution(
        as_of=date(2026, 6, 9),
        month="2026-06",
        bucket_amounts={"growth": 2000},
        invested_by_bucket={"growth": 0},
        today_invested_by_bucket={"growth": 0},
        fund_catalog={"161130": "易方达", "270042": "广发"},
        purchase_limits={"161130": 10, "270042": 300},
        labels={"growth": "成长档"},
        colors={"growth": "#3ABFF8"},
        dca_memory=memory,
    )
    assert ctx.growth.funds
    assert ctx.growth.funds[0]["fund_code"] == "270042"
    assert ctx.dca_batch["memory_active"] is True
    assert ctx.dca_batch["status"] == "pending"
