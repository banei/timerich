"""growth_limits 纳指候选名单单测。"""

from app.services.growth_limits import (
    NASDAQ100_FUND_META,
    RETIRED_NDX_CODES,
    all_growth_fund_codes,
    effective_growth_ladder,
    growth_fund_roster,
    merge_custom_limits,
    merge_purchase_limits,
    parse_custom_growth_funds,
)
from app.services.execution_planner import plan_growth_bucket


def test_ladder_includes_new_buyable_funds():
    codes = all_growth_fund_codes()
    assert "270042" in codes
    assert "019524" in codes
    assert "016452" in codes
    assert "018959" not in codes
    assert "019870" not in codes


def test_retired_codes_not_in_meta():
    for code in RETIRED_NDX_CODES:
        assert code not in NASDAQ100_FUND_META


def test_roster_marks_paused_defaults():
    limits = merge_purchase_limits()
    roster = growth_fund_roster(limits)
    by_code = {r["fund_code"]: r for r in roster}
    assert by_code["161130"]["buyable"] is False
    assert by_code["270042"]["buyable"] is True


def test_custom_fund_in_ladder_and_roster():
    custom = [{"fund_code": "123456", "fund_name": "测试联接A", "daily_limit": 50.0, "tier": 2}]
    limits = merge_custom_limits(merge_purchase_limits(), custom)
    ladder = effective_growth_ladder(custom)
    assert "123456" in ladder[1]
    roster = growth_fund_roster(limits, custom_funds=custom)
    row = next(r for r in roster if r["fund_code"] == "123456")
    assert row["is_custom"] is True
    assert row["fund_name"] == "测试联接A"
    assert row["daily_limit"] == 50.0


def test_custom_fund_participates_in_daily_plan():
    custom = [{"fund_code": "123456", "fund_name": "测试联接A", "daily_limit": 100.0, "tier": 1}]
    limits = merge_custom_limits(merge_purchase_limits(), custom)
    ladder = effective_growth_ladder(custom)
    plan = plan_growth_bucket(
        150.0,
        {"123456": "测试联接A"},
        limits,
        growth_ladder=ladder,
    )
    codes = [f.fund_code for f in plan.funds]
    assert "123456" in codes


def test_parse_custom_funds_skips_invalid():
    detail = {
        "custom_growth_funds": [
            {"fund_code": "270042", "fund_name": "已有", "daily_limit": 10, "tier": 1},
            {"fund_code": "bad", "fund_name": "无效"},
        ]
    }
    parsed = parse_custom_growth_funds(detail)
    assert len(parsed) == 1
    assert parsed[0]["fund_code"] == "270042"
