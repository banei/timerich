from app.services.fund_fees import calc_purchase_fee, enrich_fund_allocation, summarize_fund_fees


def test_purchase_fee_front_load():
    # 100 元、费率 0.12% → 约 0.12 元
    fee = calc_purchase_fee(100, 0.0012)
    assert fee == 0.12


def test_zero_fee_for_etf():
    fee = calc_purchase_fee(5000, 0)
    assert fee == 0.0


def test_enrich_allocation():
    row = enrich_fund_allocation(
        {"fund_code": "161130", "planned_amount": 100},
        {"161130": {"purchase_fee_rate": 0.0012, "annual_fee_rate": 0.0085, "redemption_fee_2y": 0}},
    )
    assert row["purchase_fee_amount"] == 0.12
    assert row["net_invested_amount"] == 99.88
    assert row["purchase_fee_rate"] == 0.0012


def test_summarize():
    funds = [
        {"planned_amount": 100, "purchase_fee_amount": 0.12, "net_invested_amount": 99.88},
        {"planned_amount": 50, "purchase_fee_amount": 0.06, "net_invested_amount": 49.94},
    ]
    s = summarize_fund_fees(funds)
    assert s["total_planned"] == 150.0
    assert s["total_purchase_fee"] == 0.18
