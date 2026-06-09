"""execution_planner 推导逻辑单测。"""

from app.services.bucket_config import buckets_from_legacy, default_buckets, targets_map
from app.services.execution_planner import (
    build_execution_plan,
    derive_bucket_amounts,
    plan_dividend_bucket,
    plan_growth_bucket,
)
from app.services.growth_limits import merge_purchase_limits


def test_default_five_buckets_sum_to_one():
    buckets = default_buckets()
    assert abs(sum(b.target_pct for b in buckets) - 1.0) < 1e-9


def test_monthly_allocation_with_spillover_to_dividend():
    """纳指系数 0.5 时，溢出进红利桶（手册案例）。"""
    targets = targets_map(buckets_from_legacy(0.35, 0.40, 0.25))
    coeffs = {"growth": 0.5, "dividend": 1.0, "gold": 1.0, "bond_long": 1.0, "bond_short": 1.0}
    lines = derive_bucket_amounts(5000, targets, coeffs)
    by_bucket = {line.bucket: line for line in lines}

    assert by_bucket["growth"].final_amount == 875.0
    assert by_bucket["dividend"].final_amount == 2875.0
    assert by_bucket["bond_long"].final_amount == 875.0
    assert by_bucket["bond_short"].final_amount == 375.0
    assert sum(line.final_amount for line in lines) == 5000.0


def test_spillover_to_bond_when_dividend_slow():
    targets = targets_map(buckets_from_legacy(0.35, 0.40, 0.25))
    coeffs = {"growth": 0.5, "dividend": 0.7, "gold": 1.0, "bond_long": 1.0, "bond_short": 1.0}
    lines = derive_bucket_amounts(5000, targets, coeffs)
    by_bucket = {line.bucket: line for line in lines}

    assert by_bucket["growth"].final_amount == 875.0
    assert by_bucket["dividend"].final_amount == 1400.0
    assert by_bucket["bond_long"].final_amount > 875.0
    assert sum(line.final_amount for line in lines) == 5000.0


def test_custom_bucket_names_in_derivation():
    buckets = buckets_from_legacy(0.35, 0.40, 0.25)
    buckets[0] = buckets[0].__class__(
        code="growth", name="纳指成长", target_pct=buckets[0].target_pct, color=buckets[0].color
    )
    targets = targets_map(buckets)
    labels = {b.code: b.name for b in buckets}
    lines = derive_bucket_amounts(5000, targets, {"growth": 1.0, "dividend": 1.0, "gold": 1.0}, labels)
    assert lines[0].label == "纳指成长"


def test_growth_yifangda_10_spills_to_next_fund():
    plan = plan_growth_bucket(
        100,
        fund_catalog={"161130": "易方达纳指100联接A", "018043": "天弘纳斯达克100A"},
        purchase_limits={"161130": 10, "018043": 300},
    )
    assert len(plan.funds) == 2
    assert plan.funds[0].fund_code == "161130"
    assert plan.funds[0].planned_amount == 10
    assert plan.funds[1].fund_code == "018043"
    assert plan.funds[1].planned_amount == 90
    assert sum(f.planned_amount for f in plan.funds) == 100


def test_growth_yifangda_paused_skips_to_next():
    plan = plan_growth_bucket(
        50,
        fund_catalog={"161130": "易方达纳指100联接A", "018043": "天弘纳斯达克100A"},
        purchase_limits={"161130": 0, "018043": 300},
    )
    assert len(plan.funds) == 1
    assert plan.funds[0].fund_code == "018043"
    assert plan.funds[0].planned_amount == 50


def test_growth_default_limit_161130_is_10():
    limits = merge_purchase_limits()
    plan = plan_growth_bucket(
        80,
        fund_catalog={"161130": "易方达纳指100联接A", "018043": "天弘纳斯达克100A"},
        purchase_limits=limits,
    )
    assert plan.funds[0].planned_amount == 10
    assert sum(f.planned_amount for f in plan.funds) == 80


def test_growth_ladder_respects_purchase_limit():
    plan = plan_growth_bucket(
        2000,
        fund_catalog={"161130": "易方达纳指100联接A", "018043": "天弘纳斯达克100A"},
        purchase_limits={"161130": 300},
    )
    codes = [f.fund_code for f in plan.funds]
    assert codes[0] == "161130"
    assert plan.funds[0].planned_amount == 300
    assert "018043" in codes
    assert sum(f.planned_amount for f in plan.funds) == 2000


def test_dividend_split_above_10k():
    plan = plan_dividend_bucket(12000)
    assert len(plan.funds) == 2
    assert plan.funds[0].planned_amount == 6000
    assert plan.funds[1].planned_amount == 6000


def test_dividend_all_otc_below_10k():
    plan = plan_dividend_bucket(5000)
    assert len(plan.funds) == 1
    assert plan.funds[0].fund_code == "007466"


def test_build_execution_plan_with_custom_names():
    buckets = default_buckets()
    buckets = [
        buckets[0].__class__(code="growth", name="我的成长桶", target_pct=0.35, color="#3ABFF8"),
        *buckets[1:],
    ]
    plan = build_execution_plan(
        month="2026-06",
        budget=5000,
        buckets=buckets,
        pe_percentile=0.94,
        nasdaq_coef=0.5,
        nasdaq_label="高估",
        dividend_yield=0.047,
        dividend_coef=1.0,
        dividend_label="正常",
        fund_catalog={"161130": "易方达纳指100联接A"},
    )
    data = plan.to_dict()
    assert data["signals"][0]["name"] == "我的成长桶"
    assert data["derivations"][0]["label"] == "我的成长桶"
    assert data["bucket_executions"][0]["name"] == "我的成长桶"
    assert data["derivations"][1]["final_amount"] == 2875.0
    assert data["total_planned"] == 5000.0
    recon = data["budget_reconciliation"]
    assert recon["aligned"] is True
    assert recon["delta"] == 0.0
    assert recon["after_signals_total"] == 5000.0


def test_budget_reconciliation_with_override():
    buckets = default_buckets()
    plan = build_execution_plan(
        month="2026-06",
        budget=5000,
        buckets=buckets,
        pe_percentile=0.5,
        nasdaq_coef=1.0,
        nasdaq_label="正常",
        dividend_yield=0.047,
        dividend_coef=1.0,
        dividend_label="正常",
        amount_overrides={"growth": 2000},
    )
    recon = plan.budget_reconciliation
    assert recon is not None
    assert recon.aligned is False
    assert recon.has_manual_overrides is True
    assert recon.delta > 0
