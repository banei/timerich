"""基金净值查询与申购份额估算（外扣费后净投入 ÷ 净值）。"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from app.models import Fund, FundQuote
from app.services.fund_fees import enrich_fund_allocation, fee_catalog_from_funds


def _money4(value: float | Decimal) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def calc_estimated_shares(net_invested: float, nav: float) -> float | None:
    """场外基金份额：净确认金额 / 单位净值，保留四位小数。"""
    if net_invested <= 0 or nav <= 0:
        return None
    return _money4(net_invested / nav)


def _latest_quote_row(db: Session, fund_id: int) -> FundQuote | None:
    return (
        db.query(FundQuote)
        .filter(FundQuote.fund_id == fund_id)
        .order_by(FundQuote.date.desc())
        .first()
    )


def fetch_live_nav(fund_code: str) -> dict[str, Any] | None:
    try:
        import akshare as ak

        df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
        if df is None or df.empty:
            return None
        last = df.iloc[-1]
        nav = float(last["净值"])
        nav_date = str(last["净值日期"])[:10]
        if nav <= 0:
            return None
        return {
            "nav": _money4(nav),
            "nav_date": nav_date,
            "source": "akshare",
            "stale": False,
        }
    except Exception as exc:
        logger.warning("基金 {} 实时净值查询失败: {}", fund_code, exc)
        return None


def resolve_nav_map(
    db: Session,
    fund_codes: list[str],
    *,
    live: bool = False,
    stale_after_days: int = 5,
) -> dict[str, dict[str, Any]]:
    """按基金代码解析最新净值；live=True 时对缺失或过期项尝试 akshare。"""
    if not fund_codes:
        return {}

    funds = db.query(Fund).filter(Fund.code.in_(fund_codes)).all()
    by_code = {f.code: f for f in funds}
    today = date.today()
    stale_cutoff = today - timedelta(days=stale_after_days)
    result: dict[str, dict[str, Any]] = {}

    for code in fund_codes:
        fund = by_code.get(code)
        db_info: dict[str, Any] | None = None
        if fund:
            row = _latest_quote_row(db, fund.id)
            if row and row.nav and float(row.nav) > 0:
                nav_date = row.date
                db_info = {
                    "nav": _money4(float(row.nav)),
                    "nav_date": nav_date.isoformat(),
                    "source": row.source or "db",
                    "stale": nav_date < stale_cutoff,
                }

        need_live = live or db_info is None or db_info.get("stale")
        if need_live:
            live_info = fetch_live_nav(code)
            if live_info:
                if fund:
                    from app.services.market_data import MarketDataService

                    MarketDataService(db).upsert_fund_quote(
                        fund.id,
                        date.fromisoformat(live_info["nav_date"]),
                        Decimal(str(live_info["nav"])),
                        live_info["source"],
                    )
                result[code] = live_info
                continue

        if db_info:
            result[code] = db_info
        else:
            result[code] = {
                "nav": None,
                "nav_date": None,
                "source": "unknown",
                "stale": True,
            }

    return result


def enrich_fund_with_shares(
    fund: dict[str, Any],
    *,
    fee_catalog: dict[str, dict[str, float]],
    nav_info: dict[str, Any] | None,
) -> dict[str, Any]:
    enriched = enrich_fund_allocation(fund, fee_catalog)
    info = nav_info or {}
    nav = info.get("nav")
    net = float(enriched.get("net_invested_amount") or 0)
    shares = calc_estimated_shares(net, float(nav)) if nav else None
    enriched.update(
        {
            "nav": nav,
            "nav_date": info.get("nav_date"),
            "nav_source": info.get("source"),
            "nav_stale": bool(info.get("stale")),
            "estimated_shares": shares,
        }
    )
    return enriched


def summarize_share_estimates(funds: list[dict[str, Any]]) -> dict[str, Any]:
    selected = [f for f in funds if f.get("selected", True)]
    with_nav = [f for f in selected if f.get("estimated_shares") is not None]
    return {
        "total_estimated_shares": _money4(sum(float(f["estimated_shares"]) for f in with_nav))
        if with_nav
        else None,
        "funds_with_nav": len(with_nav),
        "funds_missing_nav": len(selected) - len(with_nav),
    }


def enrich_daily_dca_batch(
    db: Session,
    plan_dict: dict[str, Any],
    funds: list[Fund],
    *,
    live: bool = False,
) -> dict[str, Any]:
    """为 daily.dca_batch 各条目附加净值与预估份额。"""
    daily = plan_dict.get("daily")
    if not daily or not isinstance(daily, dict):
        return plan_dict

    batch = daily.get("dca_batch")
    if not batch or not isinstance(batch, dict):
        return plan_dict

    items = batch.get("items") or []
    if not items:
        return plan_dict

    growth_by_code = {
        str(f.get("fund_code")): f for f in (daily.get("growth") or {}).get("funds") or []
    }
    fee_catalog = fee_catalog_from_funds(funds)
    codes = [str(i.get("fund_code")) for i in items if i.get("fund_code")]
    nav_map = resolve_nav_map(db, codes, live=live)

    batch_status = batch.get("status")
    enriched_items: list[dict[str, Any]] = []
    for item in items:
        code = str(item.get("fund_code", ""))
        if (
            not live
            and batch_status == "confirmed"
            and item.get("estimated_shares") is not None
            and item.get("nav") is not None
        ):
            enriched_items.append(dict(item))
            continue

        base = dict(growth_by_code.get(code) or item)
        base["planned_amount"] = item.get("planned_amount", base.get("planned_amount"))
        base["selected"] = item.get("selected", base.get("selected", True))
        base["fund_name"] = item.get("fund_name") or base.get("fund_name")
        merged = enrich_fund_with_shares(base, fee_catalog=fee_catalog, nav_info=nav_map.get(code))
        merged["selected"] = base["selected"]
        enriched_items.append(merged)

    batch["items"] = enriched_items
    batch["share_summary"] = summarize_share_estimates(enriched_items)
    daily["dca_batch"] = batch
    plan_dict["daily"] = daily
    return plan_dict


def enrich_funds_for_confirm(
    db: Session,
    funds: list[dict[str, Any]],
    active_funds: list[Fund],
    *,
    live: bool = True,
) -> list[dict[str, Any]]:
    """确认购买前服务端计算份额并写入记录。"""
    selected = [f for f in funds if f.get("selected", True)]
    codes = [str(f["fund_code"]) for f in selected]
    fee_catalog = fee_catalog_from_funds(active_funds)
    nav_map = resolve_nav_map(db, codes, live=live)
    enriched: list[dict[str, Any]] = []
    for f in selected:
        code = str(f["fund_code"])
        merged = enrich_fund_with_shares(f, fee_catalog=fee_catalog, nav_info=nav_map.get(code))
        merged["selected"] = True
        enriched.append(merged)
    return enriched
