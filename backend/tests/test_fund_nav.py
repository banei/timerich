"""净值份额估算单测。"""

from unittest.mock import patch

from app.services.fund_fees import fee_catalog_from_funds
from app.services.fund_nav import calc_estimated_shares, enrich_fund_with_shares, enrich_daily_dca_batch


class _FakeFund:
    def __init__(self, code: str, rate: float = 0.0015):
        self.code = code
        self.purchase_fee_rate = rate
        self.annual_fee_rate = 0.006
        self.redemption_fee_2y = 0


def test_calc_estimated_shares():
    # 净投入 99.85 / 净值 1.2345
    shares = calc_estimated_shares(99.85, 1.2345)
    assert shares is not None
    assert shares > 80


def test_enrich_fund_with_shares():
    catalog = fee_catalog_from_funds([_FakeFund("270042")])
    row = enrich_fund_with_shares(
        {"fund_code": "270042", "fund_name": "测试", "planned_amount": 100},
        fee_catalog=catalog,
        nav_info={"nav": 2.5, "nav_date": "2026-06-06", "source": "db", "stale": False},
    )
    assert row["net_invested_amount"] < 100
    assert row["estimated_shares"] == calc_estimated_shares(row["net_invested_amount"], 2.5)
    assert row["nav"] == 2.5


def test_enrich_daily_dca_batch_structure():
    plan = {
        "daily": {
            "growth": {
                "funds": [
                    {
                        "fund_code": "270042",
                        "fund_name": "广发",
                        "planned_amount": 100,
                    }
                ]
            },
            "dca_batch": {
                "status": "pending",
                "items": [
                    {
                        "fund_code": "270042",
                        "fund_name": "广发",
                        "planned_amount": 100,
                        "selected": True,
                    }
                ],
            },
        }
    }

    nav_stub = {
        "270042": {"nav": 2.0, "nav_date": "2026-06-06", "source": "test", "stale": False},
    }
    with patch("app.services.fund_nav.resolve_nav_map", return_value=nav_stub):
        out = enrich_daily_dca_batch(
            None,
            plan,
            [_FakeFund("270042")],
            live=False,
        )
    item = out["daily"]["dca_batch"]["items"][0]
    assert item["estimated_shares"] is not None
    assert item["nav"] == 2.0
