from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Fund, FundQuote, Holding, Transaction
from app.services.holding_cost import build_holding_cost_snapshot, txn_lots_from_rows


def recalculate_holdings(db: Session, user_id: int) -> None:
    txns = (
        db.query(Transaction)
        .filter(Transaction.user_id == user_id)
        .order_by(Transaction.date, Transaction.id)
        .all()
    )
    by_fund: dict[int, list] = {}
    for txn in txns:
        by_fund.setdefault(txn.fund_id, []).append(txn)

    aggregates: dict[int, dict[str, Decimal]] = {}
    for fund_id, fund_txns in by_fund.items():
        snap = build_holding_cost_snapshot(txn_lots_from_rows(fund_txns))
        last_nav = fund_txns[-1].nav if fund_txns else Decimal(0)
        aggregates[fund_id] = {
            "shares": snap.total_shares,
            "invested": snap.total_cost,
            "value": snap.total_shares * last_nav,
        }

    existing = {
        h.fund_id: h
        for h in db.query(Holding).filter(Holding.user_id == user_id).all()
    }

    seen: set[int] = set()
    for fund_id, agg in aggregates.items():
        if agg["shares"] <= 0:
            continue
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


def _latest_nav(db: Session, fund_id: int) -> Decimal | None:
    row = (
        db.query(FundQuote)
        .filter(FundQuote.fund_id == fund_id)
        .order_by(FundQuote.date.desc())
        .first()
    )
    return row.nav if row and row.nav else None


def holdings_with_funds(db: Session, user_id: int) -> list[dict]:
    rows = (
        db.query(Holding, Fund)
        .join(Fund, Fund.id == Holding.fund_id)
        .filter(Holding.user_id == user_id)
        .all()
    )
    result: list[dict] = []
    for h, f in rows:
        fund_txns = (
            db.query(Transaction)
            .filter(Transaction.user_id == user_id, Transaction.fund_id == h.fund_id)
            .order_by(Transaction.date, Transaction.id)
            .all()
        )
        snap = build_holding_cost_snapshot(txn_lots_from_rows(fund_txns))
        current_nav = _latest_nav(db, h.fund_id) or (
            h.current_value / h.total_shares if h.total_shares > 0 else Decimal(0)
        )
        profit = h.current_value - snap.total_cost
        profit_pct = float(profit / snap.total_cost) if snap.total_cost > 0 else 0.0
        first_buy = fund_txns[0].date if fund_txns else date.today()
        holding_days = (date.today() - first_buy).days

        result.append(
            {
                "fund_id": h.fund_id,
                "fund_code": f.code,
                "fund_name": f.name,
                "total_shares": h.total_shares,
                "total_invested": snap.total_cost,
                "avg_cost": snap.avg_cost,
                "current_nav": current_nav,
                "current_value": h.current_value,
                "profit": profit,
                "profit_pct": profit_pct,
                "holding_days": holding_days,
                "shares_over_one_year": snap.shares_over_one_year,
                "shares_under_one_year": snap.shares_under_one_year,
            }
        )
    return result


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
