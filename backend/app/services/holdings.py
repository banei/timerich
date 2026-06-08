from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Fund, Holding, Transaction


def recalculate_holdings(db: Session, user_id: int) -> None:
    txns = (
        db.query(Transaction)
        .filter(Transaction.user_id == user_id)
        .order_by(Transaction.date, Transaction.id)
        .all()
    )
    aggregates: dict[int, dict[str, Decimal]] = {}

    for txn in txns:
        agg = aggregates.setdefault(
            txn.fund_id,
            {"shares": Decimal(0), "invested": Decimal(0), "value": Decimal(0)},
        )
        if txn.txn_type in {"buy", "rebalance_buy", "dividend"}:
            agg["shares"] += txn.shares
            agg["invested"] += txn.amount
        elif txn.txn_type in {"sell", "rebalance_sell"}:
            agg["shares"] -= txn.shares
            agg["invested"] -= txn.amount
        agg["value"] = agg["shares"] * txn.nav

    existing = {
        h.fund_id: h
        for h in db.query(Holding).filter(Holding.user_id == user_id).all()
    }

    seen: set[int] = set()
    for fund_id, agg in aggregates.items():
        holding = existing.get(fund_id)
        if holding is None:
            holding = Holding(user_id=user_id, fund_id=fund_id)
            db.add(holding)
        holding.total_shares = agg["shares"]
        holding.total_invested = agg["invested"]
        holding.current_value = agg["value"]
        seen.add(fund_id)

    for fund_id, holding in existing.items():
        if fund_id not in seen:
            db.delete(holding)

    db.commit()


def holdings_with_funds(db: Session, user_id: int) -> list[dict]:
    rows = (
        db.query(Holding, Fund)
        .join(Fund, Fund.id == Holding.fund_id)
        .filter(Holding.user_id == user_id)
        .all()
    )
    return [
        {
            "fund_id": h.fund_id,
            "fund_code": f.code,
            "fund_name": f.name,
            "total_shares": h.total_shares,
            "total_invested": h.total_invested,
            "current_value": h.current_value,
        }
        for h, f in rows
    ]


def category_totals(db: Session, user_id: int) -> dict[str, Decimal]:
    from app.models import AssetCategory

    rows = (
        db.query(AssetCategory.code, Holding.current_value)
        .join(Fund, Fund.category_id == AssetCategory.id)
        .join(Holding, Holding.fund_id == Fund.id)
        .filter(Holding.user_id == user_id)
        .all()
    )
    totals: dict[str, Decimal] = {"NASDAQ": Decimal(0), "DIVIDEND": Decimal(0), "BOND": Decimal(0), "SP500": Decimal(0)}
    for code, value in rows:
        if code in totals:
            totals[code] += value
        elif code == "SP500":
            totals["SP500"] += value
    return totals
