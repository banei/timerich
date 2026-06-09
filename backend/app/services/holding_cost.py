"""持仓成本：移动加权均价 + FIFO 份额批次（税务提示）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable, Sequence


BUY_TYPES = frozenset({"buy", "rebalance_buy", "dividend"})
SELL_TYPES = frozenset({"sell", "rebalance_sell"})
ONE_YEAR_DAYS = 365


@dataclass(frozen=True)
class TxnLot:
    date: date
    shares: Decimal
    nav: Decimal
    amount: Decimal
    txn_type: str


@dataclass
class FifoLot:
    date: date
    shares: Decimal
    cost_per_share: Decimal


@dataclass
class HoldingCostSnapshot:
    total_shares: Decimal
    avg_cost: Decimal
    total_cost: Decimal
    shares_over_one_year: Decimal
    shares_under_one_year: Decimal


def _d(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value))


def moving_weighted_avg_cost(
    transactions: Sequence[TxnLot],
) -> tuple[Decimal, Decimal, Decimal]:
    """
    移动加权平均成本（与天天基金/支付宝一致）。

    买入：新均价 = (原份额×原均价 + 买入金额) / (原份额 + 新份额)
    卖出：均价不变，仅减少份额与总成本
    分红再投资：视同买入
    """
    shares = Decimal(0)
    total_cost = Decimal(0)

    for txn in sorted(transactions, key=lambda t: (t.date, id(t))):
        if txn.shares <= 0:
            continue
        if txn.txn_type in BUY_TYPES:
            total_cost += txn.amount
            shares += txn.shares
        elif txn.txn_type in SELL_TYPES:
            if shares <= 0:
                continue
            sell_shares = min(txn.shares, shares)
            cost_per_share = total_cost / shares if shares > 0 else Decimal(0)
            total_cost -= cost_per_share * sell_shares
            shares -= sell_shares

    if shares <= 0:
        return Decimal(0), Decimal(0), Decimal(0)

    avg_cost = total_cost / shares
    return shares, avg_cost, total_cost


def fifo_remaining_lots(
    transactions: Sequence[TxnLot],
    as_of: date | None = None,
) -> list[FifoLot]:
    """按 FIFO 模拟卖出后的剩余份额批次。"""
    lots: list[FifoLot] = []

    for txn in sorted(transactions, key=lambda t: (t.date, id(t))):
        if txn.shares <= 0:
            continue
        if txn.txn_type in BUY_TYPES:
            cost_per_share = txn.amount / txn.shares if txn.shares > 0 else Decimal(0)
            lots.append(FifoLot(date=txn.date, shares=txn.shares, cost_per_share=cost_per_share))
        elif txn.txn_type in SELL_TYPES:
            remaining = txn.shares
            while remaining > 0 and lots:
                head = lots[0]
                take = min(remaining, head.shares)
                head.shares -= take
                remaining -= take
                if head.shares <= 0:
                    lots.pop(0)

    if as_of is not None:
        lots = [lot for lot in lots if lot.shares > 0]

    return [lot for lot in lots if lot.shares > 0]


def shares_held_over_one_year(
    transactions: Sequence[TxnLot],
    as_of: date | None = None,
) -> Decimal:
    """
    持有超 1 年的份额（FIFO 卖出后统计）。

    用于提示卖出时优先卖长期份额（红利税 0% vs 10%）。
    """
    ref = as_of or date.today()
    lots = fifo_remaining_lots(transactions, as_of=ref)
    over = Decimal(0)
    for lot in lots:
        if (ref - lot.date).days >= ONE_YEAR_DAYS:
            over += lot.shares
    return over


def build_holding_cost_snapshot(
    transactions: Sequence[TxnLot],
    as_of: date | None = None,
) -> HoldingCostSnapshot:
    ref = as_of or date.today()
    shares, avg_cost, total_cost = moving_weighted_avg_cost(transactions)
    over = shares_held_over_one_year(transactions, as_of=ref)
    under = max(shares - over, Decimal(0))
    return HoldingCostSnapshot(
        total_shares=shares,
        avg_cost=avg_cost,
        total_cost=total_cost,
        shares_over_one_year=over,
        shares_under_one_year=under,
    )


def txn_lots_from_rows(rows: Iterable) -> list[TxnLot]:
    return [
        TxnLot(
            date=row.date if isinstance(row.date, date) else date.fromisoformat(str(row.date)),
            shares=_d(row.shares),
            nav=_d(row.nav),
            amount=_d(row.amount),
            txn_type=row.txn_type,
        )
        for row in rows
    ]
