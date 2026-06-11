"""基金池配置：频率、限购、正式/试探。"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import BucketFundConfig, Fund
from app.services.dca_amounts import get_last_investment_by_fund, resolve_dca_amount
from app.services.growth_limits import (
    GROWTH_FUND_LADDER,
    NASDAQ100_FUND_META,
    merge_purchase_limits,
    resolve_daily_limit,
)


PROBE_DEFAULT_CODES = ("161130", "018043", "160213")


def lookup_fund_by_code(db: Session, code: str) -> dict:
    """根据基金代码查名称与平台日限购（天天基金）。"""
    code = str(code).strip()
    fund = db.query(Fund).filter(Fund.code == code).first()
    name = fund.name if fund else code
    purchase_limit: float | None = None
    try:
        from app.services.fund_purchase import fetch_em_purchase_for_codes

        infos = fetch_em_purchase_for_codes([code])
        if infos:
            info = infos[0]
            if info.fund_name:
                name = info.fund_name
            if info.daily_limit is not None:
                purchase_limit = float(info.daily_limit)
            if info.status == "paused":
                purchase_limit = 0.0
    except Exception:
        pass
    if purchase_limit is None:
        plat, _ = resolve_daily_limit(code, merge_purchase_limits())
        if plat is not None:
            purchase_limit = float(plat)
    return {
        "fund_code": code,
        "fund_name": name,
        "purchase_limit": purchase_limit,
    }


def _default_limit(code: str) -> Decimal:
    meta = NASDAQ100_FUND_META.get(code, {})
    val = meta.get("default_limit", 300.0)
    return Decimal(str(val))


def seed_default_fund_pool(db: Session, user_id: int) -> list[BucketFundConfig]:
    existing = db.query(BucketFundConfig).filter(BucketFundConfig.user_id == user_id).count()
    if existing > 0:
        return list_fund_pool(db, user_id)

    rows: list[BucketFundConfig] = []
    order = 0
    for tier_idx, tier in enumerate(GROWTH_FUND_LADDER[:3], start=1):
        for code in tier:
            meta = NASDAQ100_FUND_META.get(code, {})
            limit, _ = resolve_daily_limit(code, merge_purchase_limits())
            buy_type = "probe" if code in PROBE_DEFAULT_CODES else "scheduled"
            status = "paused" if limit <= 0 and buy_type == "scheduled" else "active"
            if buy_type == "probe" and limit <= 0:
                limit = Decimal("10")
            rows.append(
                BucketFundConfig(
                    user_id=user_id,
                    bucket_code="growth",
                    fund_code=code,
                    fund_name=meta.get("name", code),
                    daily_limit=Decimal(str(limit)) if limit else Decimal("10"),
                    frequency="daily" if tier_idx <= 2 else "weekly_WED",
                    buy_type=buy_type,
                    status=status,
                    sort_order=order,
                )
            )
            order += 1
    db.add_all(rows)
    db.commit()
    return rows


def list_fund_pool(db: Session, user_id: int, *, bucket_code: str | None = None) -> list[BucketFundConfig]:
    q = db.query(BucketFundConfig).filter(BucketFundConfig.user_id == user_id)
    if bucket_code:
        q = q.filter(BucketFundConfig.bucket_code == bucket_code)
    return q.order_by(BucketFundConfig.bucket_code, BucketFundConfig.sort_order, BucketFundConfig.id).all()


def fund_pool_to_dict(
    rows: list[BucketFundConfig],
    *,
    last_by_fund: dict[str, dict] | None = None,
) -> list[dict]:
    last_map = last_by_fund or {}
    out: list[dict] = []
    for r in rows:
        effective = resolve_dca_amount(
            r.fund_code,
            float(r.daily_limit),
            r.updated_at,
            last_map,
        )
        out.append(
            {
                "id": r.id,
                "bucket_code": r.bucket_code,
                "fund_code": r.fund_code,
                "fund_name": r.fund_name,
                "daily_limit": effective,
                "frequency": r.frequency,
                "buy_type": r.buy_type,
                "status": r.status,
                "sort_order": r.sort_order,
            }
        )
    return out


def upsert_fund_pool_item(db: Session, user_id: int, data: dict) -> BucketFundConfig:
    code = str(data["fund_code"]).strip()
    bucket = str(data["bucket_code"]).strip()
    row = (
        db.query(BucketFundConfig)
        .filter(
            BucketFundConfig.user_id == user_id,
            BucketFundConfig.bucket_code == bucket,
            BucketFundConfig.fund_code == code,
        )
        .first()
    )
    fund = db.query(Fund).filter(Fund.code == code).first()
    name = (data.get("fund_name") or "").strip()
    if not name:
        name = fund.name if fund else code
    if (not name or name == code) and len(code) == 6:
        looked = lookup_fund_by_code(db, code)
        name = looked["fund_name"] or name
    if row is None:
        row = BucketFundConfig(
            user_id=user_id,
            bucket_code=bucket,
            fund_code=code,
            fund_name=name,
        )
        db.add(row)
    row.fund_name = name
    amount = Decimal(str(data.get("daily_limit", row.daily_limit or 10)))
    row.daily_limit = amount
    row.frequency = str(data.get("frequency", row.frequency or "daily"))
    row.buy_type = str(data.get("buy_type", row.buy_type or "scheduled"))
    if amount <= 0:
        row.status = "paused"
    elif data.get("status") == "paused":
        row.status = "paused"
    else:
        row.status = "active"
    if "sort_order" in data:
        row.sort_order = int(data["sort_order"])
    db.commit()
    db.refresh(row)
    return row


def delete_fund_pool_item(db: Session, user_id: int, item_id: int) -> bool:
    row = (
        db.query(BucketFundConfig)
        .filter(BucketFundConfig.user_id == user_id, BucketFundConfig.id == item_id)
        .first()
    )
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
