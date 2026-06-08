"""init

Revision ID: 001
Revises:
Create Date: 2026-06-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

DT = mysql.DATETIME(fsp=3)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), nullable=False),
        sa.Column("locked_until", DT, nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "asset_category",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )

    op.create_table(
        "user_config",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("risk_profile", sa.String(16), nullable=False),
        sa.Column("target_nasdaq_pct", sa.DECIMAL(8, 6), nullable=False),
        sa.Column("target_dividend_pct", sa.DECIMAL(8, 6), nullable=False),
        sa.Column("target_bond_pct", sa.DECIMAL(8, 6), nullable=False),
        sa.Column("monthly_budget", sa.DECIMAL(18, 4), nullable=False),
        sa.Column("rebalance_threshold_passive", sa.DECIMAL(8, 6), nullable=False),
        sa.Column("rebalance_threshold_active", sa.DECIMAL(8, 6), nullable=False),
        sa.Column("max_total_pct_of_family", sa.DECIMAL(8, 6), nullable=False),
        sa.Column("family_total_assets", sa.DECIMAL(18, 4), nullable=True),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )

    op.create_table(
        "fund",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("fund_type", sa.String(16), nullable=False),
        sa.Column("market", sa.String(4), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("annual_fee_rate", sa.DECIMAL(8, 6), nullable=False),
        sa.Column("purchase_fee_rate", sa.DECIMAL(8, 6), nullable=False),
        sa.Column("redemption_fee_2y", sa.DECIMAL(8, 6), nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["asset_category.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )

    op.create_table(
        "index_quote",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("close", sa.DECIMAL(18, 4), nullable=False),
        sa.Column("pe_ttm", sa.DECIMAL(10, 4), nullable=True),
        sa.Column("dividend_yield", sa.DECIMAL(8, 6), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("fetched_at", DT, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_index_quote_unique", "index_quote", ["symbol", "date"], unique=True)

    op.create_table(
        "fund_quote",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("fund_id", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("nav", sa.DECIMAL(18, 4), nullable=True),
        sa.Column("iopv", sa.DECIMAL(18, 4), nullable=True),
        sa.Column("premium_rate", sa.DECIMAL(8, 6), nullable=True),
        sa.Column("purchase_limit", sa.DECIMAL(18, 2), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("fetched_at", DT, nullable=False),
        sa.ForeignKeyConstraint(["fund_id"], ["fund.id"]),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_fund_quote_unique", "fund_quote", ["fund_id", "date"], unique=True)

    op.create_table(
        "pe_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("pe_ttm", sa.DECIMAL(10, 4), nullable=False),
        sa.Column("rolling_10y_percentile", sa.DECIMAL(8, 6), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_pe_history_date", "pe_history", ["date"], unique=True)

    op.create_table(
        "transaction",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("fund_id", sa.BigInteger(), nullable=False),
        sa.Column("txn_type", sa.String(32), nullable=False),
        sa.Column("amount", sa.DECIMAL(18, 4), nullable=False),
        sa.Column("nav", sa.DECIMAL(18, 4), nullable=False),
        sa.Column("shares", sa.DECIMAL(18, 6), nullable=False),
        sa.Column("coefficient", sa.DECIMAL(8, 6), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.ForeignKeyConstraint(["fund_id"], ["fund.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )

    op.create_table(
        "holding",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("fund_id", sa.BigInteger(), nullable=False),
        sa.Column("total_shares", sa.DECIMAL(18, 6), nullable=False),
        sa.Column("total_invested", sa.DECIMAL(18, 4), nullable=False),
        sa.Column("current_value", sa.DECIMAL(18, 4), nullable=False),
        sa.Column("last_updated", DT, nullable=False),
        sa.ForeignKeyConstraint(["fund_id"], ["fund.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "fund_id", name="uq_holding_user_fund"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )

    op.create_table(
        "monthly_coefficient",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("nasdaq_pe_percentile", sa.DECIMAL(8, 6), nullable=False),
        sa.Column("nasdaq_coefficient", sa.DECIMAL(8, 6), nullable=False),
        sa.Column("dividend_yield", sa.DECIMAL(8, 6), nullable=False),
        sa.Column("dividend_coefficient", sa.DECIMAL(8, 6), nullable=False),
        sa.Column("calculated_at", DT, nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_monthly_coef_user_month", "monthly_coefficient", ["user_id", "month"], unique=True)

    op.create_table(
        "monthly_execution",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("step_check_signals", sa.Boolean(), nullable=False),
        sa.Column("step_calc_amounts", sa.Boolean(), nullable=False),
        sa.Column("step_execute_nasdaq", sa.Boolean(), nullable=False),
        sa.Column("step_check_premium", sa.Boolean(), nullable=False),
        sa.Column("step_execute_dividend", sa.Boolean(), nullable=False),
        sa.Column("step_execute_bond", sa.Boolean(), nullable=False),
        sa.Column("step_record", sa.Boolean(), nullable=False),
        sa.Column("planned_nasdaq_amount", sa.DECIMAL(18, 4), nullable=False),
        sa.Column("planned_dividend_amount", sa.DECIMAL(18, 4), nullable=False),
        sa.Column("planned_bond_amount", sa.DECIMAL(18, 4), nullable=False),
        sa.Column("actual_nasdaq_amount", sa.DECIMAL(18, 4), nullable=True),
        sa.Column("actual_dividend_amount", sa.DECIMAL(18, 4), nullable=True),
        sa.Column("actual_bond_amount", sa.DECIMAL(18, 4), nullable=True),
        sa.Column("execution_detail", sa.JSON(), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("completed_at", DT, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_monthly_exec_user_month", "monthly_execution", ["user_id", "month"], unique=True)

    op.create_table(
        "rebalance_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("before_nasdaq_pct", sa.DECIMAL(8, 6), nullable=False),
        sa.Column("before_dividend_pct", sa.DECIMAL(8, 6), nullable=False),
        sa.Column("before_bond_pct", sa.DECIMAL(8, 6), nullable=False),
        sa.Column("after_nasdaq_pct", sa.DECIMAL(8, 6), nullable=True),
        sa.Column("after_dividend_pct", sa.DECIMAL(8, 6), nullable=True),
        sa.Column("after_bond_pct", sa.DECIMAL(8, 6), nullable=True),
        sa.Column("action_taken", sa.String(32), nullable=False),
        sa.Column("orders_json", sa.JSON(), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )

    op.create_table(
        "data_fetch_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("data_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source", sa.String(32), nullable=True),
        sa.Column("message", sa.String(500), nullable=True),
        sa.Column("fetched_at", DT, nullable=False),
        sa.Column("next_fetch_after", DT, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_fetch_log_key", "data_fetch_log", ["data_key"])

    op.create_table(
        "backfill_status",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("progress_pct", sa.Integer(), nullable=False),
        sa.Column("message", sa.String(500), nullable=True),
        sa.Column("updated_at", DT, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_key"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )


def downgrade() -> None:
    for table in [
        "backfill_status",
        "data_fetch_log",
        "rebalance_log",
        "monthly_execution",
        "monthly_coefficient",
        "holding",
        "transaction",
        "pe_history",
        "fund_quote",
        "index_quote",
        "fund",
        "user_config",
        "asset_category",
        "users",
    ]:
        op.drop_table(table)
