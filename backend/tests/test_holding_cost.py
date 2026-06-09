"""持仓成本：移动加权均价 + FIFO 超一年份额。"""

from datetime import date
from decimal import Decimal

from app.services.holding_cost import (
    TxnLot,
    build_holding_cost_snapshot,
    moving_weighted_avg_cost,
    shares_held_over_one_year,
)


def _lot(d: str, shares: str, nav: str, amount: str, txn_type: str = "buy") -> TxnLot:
    return TxnLot(
        date=date.fromisoformat(d),
        shares=Decimal(shares),
        nav=Decimal(nav),
        amount=Decimal(amount),
        txn_type=txn_type,
    )


def test_moving_weighted_avg_cost_two_buys():
    """两次买入后均价 = 总成本 / 总份额。"""
    txns = [
        _lot("2024-01-10", "100", "1.00", "100"),
        _lot("2024-06-10", "100", "2.00", "200"),
    ]
    shares, avg, total = moving_weighted_avg_cost(txns)
    assert shares == Decimal("200")
    assert total == Decimal("300")
    assert avg == Decimal("1.5")


def test_moving_weighted_avg_unchanged_on_sell():
    """卖出不改变剩余份额均价。"""
    txns = [
        _lot("2024-01-10", "100", "1.00", "100"),
        _lot("2024-06-10", "100", "2.00", "200"),
        _lot("2025-01-10", "50", "2.50", "125", "sell"),
    ]
    shares, avg, total = moving_weighted_avg_cost(txns)
    assert shares == Decimal("150")
    assert avg == Decimal("1.5")
    assert total == Decimal("225")


def test_fifo_shares_over_one_year():
    txns = [
        _lot("2023-01-01", "100", "1.0", "100"),
        _lot("2025-06-01", "50", "1.2", "60"),
        _lot("2025-06-02", "30", "1.2", "36", "sell"),
    ]
    over = shares_held_over_one_year(txns, as_of=date(2025, 6, 9))
    # 卖出 30 按 FIFO 先扣 2023 批次 → 剩 70 超一年 + 50 不足一年
    assert over == Decimal("70")


def test_holding_snapshot():
    txns = [
        _lot("2023-01-01", "100", "1.0", "100"),
        _lot("2025-06-01", "50", "1.2", "60"),
    ]
    snap = build_holding_cost_snapshot(txns, as_of=date(2025, 6, 9))
    assert snap.total_shares == Decimal("150")
    assert snap.shares_over_one_year == Decimal("100")
    assert snap.shares_under_one_year == Decimal("50")
