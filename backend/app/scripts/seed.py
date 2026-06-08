from decimal import Decimal

from sqlalchemy.orm import Session

from app.auth import hash_password
from app.database import SessionLocal
from app.models import AssetCategory, Fund, User, UserConfig

CATEGORIES = [
    (1, "NASDAQ", "纳指100"),
    (2, "SP500", "标普500"),
    (3, "DIVIDEND", "红利低波"),
    (4, "BOND", "债券"),
]

FUNDS = [
    ("161130", "易方达纳斯达克100联接A", 1, "otc_link", 5, "0.008500", "0.001200"),
    ("018043", "天弘纳斯达克100A", 1, "otc_link", 5, "0.007500", "0.001200"),
    ("270042", "广发纳指100联接A", 1, "otc_link", 4, "0.009500", "0.001200"),
    ("000834", "大成纳斯达克100联接A", 1, "otc_link", 4, "0.010000", "0.001200"),
    ("160213", "国泰纳斯达克100联接A", 1, "otc_link", 4, "0.010000", "0.001200"),
    ("018959", "华夏纳斯达克100联接A", 1, "otc_link", 3, "0.008500", "0.001200"),
    ("040046", "华安纳斯达克100联接A", 1, "otc_link", 3, "0.010000", "0.001200"),
    ("019547", "嘉实纳斯达克100联接A", 1, "otc_link", 3, "0.007500", "0.001200"),
    ("017437", "摩根纳斯达克100A", 1, "otc_link", 2, "0.008000", "0.001200"),
    ("019870", "招商纳斯达克100联接A", 1, "otc_link", 2, "0.007500", "0.001200"),
    ("050025", "博时标普500ETF联接A", 2, "otc_link", 5, "0.008000", "0.001000"),
    ("118002", "易方达标普500人民币A", 2, "otc_link", 5, "0.008000", "0.001000"),
    ("096001", "大成标普500等权重A", 2, "otc_link", 4, "0.009000", "0.001000"),
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
        if db.query(Fund).filter(Fund.code == code).first() is None:
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
