from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    DECIMAL,
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")  # admin | user
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(3), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(3), default=utcnow, onupdate=utcnow)

    config: Mapped["UserConfig | None"] = relationship(back_populates="user", uselist=False)


class UserConfig(Base):
    __tablename__ = "user_config"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), unique=True)
    risk_profile: Mapped[str] = mapped_column(String(16), default="balanced")
    target_nasdaq_pct: Mapped[Decimal] = mapped_column(DECIMAL(8, 6), default=Decimal("0.35"))
    target_dividend_pct: Mapped[Decimal] = mapped_column(DECIMAL(8, 6), default=Decimal("0.40"))
    target_bond_pct: Mapped[Decimal] = mapped_column(DECIMAL(8, 6), default=Decimal("0.25"))
    monthly_budget: Mapped[Decimal] = mapped_column(DECIMAL(18, 4), default=Decimal("5000"))
    rebalance_threshold_passive: Mapped[Decimal] = mapped_column(DECIMAL(8, 6), default=Decimal("0.05"))
    rebalance_threshold_active: Mapped[Decimal] = mapped_column(DECIMAL(8, 6), default=Decimal("0.10"))
    max_total_pct_of_family: Mapped[Decimal] = mapped_column(DECIMAL(8, 6), default=Decimal("0.30"))
    family_total_assets: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 4), nullable=True)
    bucket_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(3), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(3), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship(back_populates="config")


class AssetCategory(Base):
    __tablename__ = "asset_category"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Fund(Base):
    __tablename__ = "fund"
    __table_args__ = (
        Index("ix_fund_category", "category_id"),
        Index("ix_fund_active", "is_active"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    category_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("asset_category.id"))
    fund_type: Mapped[str] = mapped_column(String(16))
    market: Mapped[str | None] = mapped_column(String(4), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    annual_fee_rate: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))
    purchase_fee_rate: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))
    redemption_fee_2y: Mapped[Decimal] = mapped_column(DECIMAL(8, 6), default=Decimal(0))
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(3), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(3), default=utcnow, onupdate=utcnow)


class FundQuote(Base):
    __tablename__ = "fund_quote"
    __table_args__ = (
        Index("ix_fund_quote_unique", "fund_id", "date", unique=True),
        Index("ix_fund_quote_date", "date"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fund_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fund.id"))
    date: Mapped[date] = mapped_column(Date)
    nav: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 4), nullable=True)
    iopv: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 4), nullable=True)
    premium_rate: Mapped[Decimal | None] = mapped_column(DECIMAL(8, 6), nullable=True)
    purchase_limit: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 2), nullable=True)
    source: Mapped[str] = mapped_column(String(32))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(3), default=utcnow)


class IndexQuote(Base):
    __tablename__ = "index_quote"
    __table_args__ = (
        Index("ix_index_quote_unique", "symbol", "date", unique=True),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32))
    date: Mapped[date] = mapped_column(Date)
    close: Mapped[Decimal] = mapped_column(DECIMAL(18, 4))
    pe_ttm: Mapped[Decimal | None] = mapped_column(DECIMAL(10, 4), nullable=True)
    dividend_yield: Mapped[Decimal | None] = mapped_column(DECIMAL(8, 6), nullable=True)
    source: Mapped[str] = mapped_column(String(32))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(3), default=utcnow)


class PEHistory(Base):
    __tablename__ = "pe_history"
    __table_args__ = (
        Index("ix_pe_history_date", "date", unique=True),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date)
    pe_ttm: Mapped[Decimal] = mapped_column(DECIMAL(10, 4))
    rolling_10y_percentile: Mapped[Decimal | None] = mapped_column(DECIMAL(8, 6), nullable=True)


class Transaction(Base):
    __tablename__ = "transaction"
    __table_args__ = (
        Index("ix_txn_user", "user_id"),
        Index("ix_txn_date", "date"),
        Index("ix_txn_fund", "fund_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    date: Mapped[date] = mapped_column(Date)
    fund_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fund.id"))
    txn_type: Mapped[str] = mapped_column(String(32))
    amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 4))
    nav: Mapped[Decimal] = mapped_column(DECIMAL(18, 4))
    shares: Mapped[Decimal] = mapped_column(DECIMAL(18, 6))
    coefficient: Mapped[Decimal | None] = mapped_column(DECIMAL(8, 6), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(3), default=utcnow)


class Holding(Base):
    __tablename__ = "holding"
    __table_args__ = (
        UniqueConstraint("user_id", "fund_id", name="uq_holding_user_fund"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    fund_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("fund.id"))
    total_shares: Mapped[Decimal] = mapped_column(DECIMAL(18, 6), default=Decimal(0))
    total_invested: Mapped[Decimal] = mapped_column(DECIMAL(18, 4), default=Decimal(0))
    current_value: Mapped[Decimal] = mapped_column(DECIMAL(18, 4), default=Decimal(0))
    last_updated: Mapped[datetime] = mapped_column(DateTime(3), default=utcnow, onupdate=utcnow)


class MonthlyCoefficient(Base):
    __tablename__ = "monthly_coefficient"
    __table_args__ = (
        Index("ix_monthly_coef_user_month", "user_id", "month", unique=True),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    month: Mapped[str] = mapped_column(String(7))
    nasdaq_pe_percentile: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))
    nasdaq_coefficient: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))
    dividend_yield: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))
    dividend_coefficient: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(3), default=utcnow)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class MonthlyExecution(Base):
    __tablename__ = "monthly_execution"
    __table_args__ = (
        Index("ix_monthly_exec_user_month", "user_id", "month", unique=True),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    month: Mapped[str] = mapped_column(String(7))
    step_check_signals: Mapped[bool] = mapped_column(Boolean, default=False)
    step_calc_amounts: Mapped[bool] = mapped_column(Boolean, default=False)
    step_execute_nasdaq: Mapped[bool] = mapped_column(Boolean, default=False)
    step_check_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    step_execute_dividend: Mapped[bool] = mapped_column(Boolean, default=False)
    step_execute_bond: Mapped[bool] = mapped_column(Boolean, default=False)
    step_record: Mapped[bool] = mapped_column(Boolean, default=False)
    planned_nasdaq_amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 4), default=Decimal(0))
    planned_dividend_amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 4), default=Decimal(0))
    planned_bond_amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 4), default=Decimal(0))
    actual_nasdaq_amount: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 4), nullable=True)
    actual_dividend_amount: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 4), nullable=True)
    actual_bond_amount: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 4), nullable=True)
    execution_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(3), nullable=True)


class RebalanceLog(Base):
    __tablename__ = "rebalance_log"
    __table_args__ = (
        Index("ix_rebalance_user_date", "user_id", "date"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    date: Mapped[date] = mapped_column(Date)
    type: Mapped[str] = mapped_column(String(32))
    before_nasdaq_pct: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))
    before_dividend_pct: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))
    before_bond_pct: Mapped[Decimal] = mapped_column(DECIMAL(8, 6))
    after_nasdaq_pct: Mapped[Decimal | None] = mapped_column(DECIMAL(8, 6), nullable=True)
    after_dividend_pct: Mapped[Decimal | None] = mapped_column(DECIMAL(8, 6), nullable=True)
    after_bond_pct: Mapped[Decimal | None] = mapped_column(DECIMAL(8, 6), nullable=True)
    action_taken: Mapped[str] = mapped_column(String(32))
    orders_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(3), default=utcnow)


class DataFetchLog(Base):
    __tablename__ = "data_fetch_log"
    __table_args__ = (
        Index("ix_fetch_log_key", "data_key"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    data_key: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16))  # success | failed | skipped
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(3), default=utcnow)
    next_fetch_after: Mapped[datetime | None] = mapped_column(DateTime(3), nullable=True)


class BackfillStatus(Base):
    __tablename__ = "backfill_status"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_key: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(3), default=utcnow, onupdate=utcnow)
