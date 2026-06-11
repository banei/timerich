from decimal import Decimal

from sqlalchemy.orm import Session

from app.auth import hash_password
from app.database import SessionLocal
from app.models import AssetCategory, Fund, User, UserConfig
from app.services.bucket_config import bucket_config_to_json, default_buckets
from app.services.growth_limits import (
    NASDAQ100_FUND_META,
    RETIRED_NDX_CODES,
    SP500_BACKUP_META,
)

CATEGORIES = [
    (1, "NASDAQ", "纳指100"),
    (2, "SP500", "标普500"),
    (3, "DIVIDEND", "红利低波"),
    (4, "BOND", "债券"),
]

# (code, name, category_id, fund_type, priority, annual_fee, purchase_fee)
FUNDS = [
    # 纳指100 — 与 growth_limits.NASDAQ100_FUND_META 对齐
    ("270042", "广发纳斯达克100ETF联接(QDII)A", 1, "otc_link", 5, "0.009500", "0.001200"),
    ("000834", "大成纳斯达克100ETF联接(QDII)A", 1, "otc_link", 5, "0.010000", "0.001200"),
    ("040046", "华安纳斯达克100ETF联接(QDII)A", 1, "otc_link", 4, "0.010000", "0.001200"),
    ("019547", "招商纳斯达克100ETF发起式联接(QDII)A", 1, "otc_link", 4, "0.007500", "0.001200"),
    ("019524", "华泰柏瑞纳斯达克100ETF发起式联接(QDII)A", 1, "otc_link", 4, "0.008000", "0.001200"),
    ("019441", "万家纳斯达克100指数发起式(QDII)A", 1, "otc_link", 3, "0.008000", "0.001200"),
    ("539001", "建信纳斯达克100指数(QDII)A", 1, "otc_link", 3, "0.008000", "0.001200"),
    ("018966", "汇添富纳斯达克100ETF发起式联接(QDII)A", 1, "otc_link", 3, "0.008000", "0.001200"),
    ("019172", "摩根纳斯达克100指数(QDII)A", 1, "otc_link", 3, "0.008000", "0.001200"),
    ("019736", "宝盈纳斯达克100指数发起(QDII)A", 1, "otc_link", 3, "0.008000", "0.001200"),
    ("016452", "南方纳斯达克100指数发起(QDII)A", 1, "otc_link", 3, "0.008000", "0.001200"),
    ("017436", "华宝纳斯达克精选股票发起(QDII)A", 1, "otc_link", 2, "0.008000", "0.001200"),
    ("161130", "易方达纳斯达克100ETF联接(QDII-LOF)A", 1, "otc_link", 5, "0.008500", "0.001200"),
    ("018043", "天弘纳斯达克100指数发起(QDII)A", 1, "otc_link", 5, "0.007500", "0.001200"),
    ("160213", "国泰纳斯达克100指数", 1, "otc_link", 4, "0.010000", "0.001200"),
    ("015299", "华夏纳斯达克100ETF发起式联接(QDII)A", 1, "otc_link", 3, "0.008500", "0.001200"),
    ("016532", "嘉实纳斯达克100ETF发起联接(QDII)A", 1, "otc_link", 3, "0.007500", "0.001200"),
    # 标普500备胎
    ("050025", "博时标普500ETF联接A", 2, "otc_link", 5, "0.008000", "0.001000"),
    ("118002", "易方达标普500人民币A", 2, "otc_link", 5, "0.008000", "0.001000"),
    ("096001", "大成标普500等权重A", 2, "otc_link", 4, "0.009000", "0.001000"),
    # 红利 / 债券
    ("007466", "华泰柏瑞红利低波联接A", 3, "otc_link", 5, "0.006000", "0.000800"),
    ("563020", "易方达红利低波ETF", 3, "etf", 5, "0.002000", "0.000000"),
    ("512890", "华泰柏瑞红利低波ETF", 3, "etf", 4, "0.006000", "0.000000"),
    ("511010", "国债ETF", 4, "bond_etf", 5, "0.001500", "0.000000"),
    ("110007", "易方达稳健收益", 4, "otc_link", 4, "0.008000", "0.000800"),
]


def seed_fund_pool(db: Session) -> None:
    for cid, code, name in CATEGORIES:
        if db.query(AssetCategory).filter(AssetCategory.code == code).first() is None:
            db.add(AssetCategory(id=cid, code=code, name=name))
    db.commit()

    for code, name, cat_id, ftype, priority, annual, purchase in FUNDS:
        row = db.query(Fund).filter(Fund.code == code).first()
        if row is None:
            db.add(
                Fund(
                    code=code,
                    name=name,
                    category_id=cat_id,
                    fund_type=ftype,
                    priority=priority,
                    annual_fee_rate=Decimal(annual),
                    purchase_fee_rate=Decimal(purchase),
                    is_active=True,
                )
            )
        else:
            row.name = name
            row.category_id = cat_id
            row.fund_type = ftype
            row.priority = priority
            row.is_active = True

    for code in RETIRED_NDX_CODES:
        row = db.query(Fund).filter(Fund.code == code).first()
        if row:
            row.is_active = False

    # 同步 growth_limits 元数据中的名称
    for code, meta in {**NASDAQ100_FUND_META, **SP500_BACKUP_META}.items():
        row = db.query(Fund).filter(Fund.code == code).first()
        if row and row.name != meta["name"]:
            row.name = meta["name"]

    db.commit()


def seed_admin(db: Session) -> None:
    admin = db.query(User).filter(User.username == "admin").first()
    if admin is None:
        admin = User(
            username="admin",
            password_hash=hash_password("112233"),
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.flush()
        db.add(
            UserConfig(
                user_id=admin.id,
                risk_profile="balanced",
                target_nasdaq_pct=Decimal("0.35"),
                target_dividend_pct=Decimal("0.40"),
                target_bond_pct=Decimal("0.25"),
                bucket_config=bucket_config_to_json(default_buckets()),
                monthly_budget=Decimal("5000"),
            )
        )
        db.commit()
        print("Created admin user")


def main() -> None:
    db = SessionLocal()
    try:
        seed_fund_pool(db)
        seed_admin(db)
        print("Seed completed")
    finally:
        db.close()


if __name__ == "__main__":
    main()
