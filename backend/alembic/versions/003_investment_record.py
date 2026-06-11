"""investment_record and bucket_fund_config

Revision ID: 003
Revises: 002
"""

import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

DT = sa.DateTime(timezone=False)


def upgrade() -> None:
    op.create_table(
        "bucket_fund_config",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("bucket_code", sa.String(32), nullable=False),
        sa.Column("fund_code", sa.String(16), nullable=False),
        sa.Column("fund_name", sa.String(128), nullable=False),
        sa.Column("daily_limit", sa.DECIMAL(18, 2), nullable=False),
        sa.Column("frequency", sa.String(32), nullable=False),
        sa.Column("buy_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", DT, nullable=False),
        sa.Column("updated_at", DT, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "bucket_code", "fund_code", name="uq_bucket_fund_user"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_bucket_fund_user", "bucket_fund_config", ["user_id"])

    op.create_table(
        "investment_record",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("fund_code", sa.String(16), nullable=False),
        sa.Column("fund_name", sa.String(128), nullable=False),
        sa.Column("bucket_code", sa.String(32), nullable=False),
        sa.Column("record_type", sa.String(16), nullable=False),
        sa.Column("planned_amount", sa.DECIMAL(18, 4), nullable=False),
        sa.Column("submitted_amount", sa.DECIMAL(18, 4), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("confirmed_amount", sa.DECIMAL(18, 4), nullable=True),
        sa.Column("confirmed_shares", sa.DECIMAL(18, 6), nullable=True),
        sa.Column("confirmed_nav", sa.DECIMAL(18, 4), nullable=True),
        sa.Column("confirmed_date", sa.Date(), nullable=True),
        sa.Column("frequency", sa.String(32), nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", DT, nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_invest_record_user_date", "investment_record", ["user_id", "date"])
    op.create_index("ix_invest_record_status", "investment_record", ["user_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_invest_record_status", table_name="investment_record")
    op.drop_index("ix_invest_record_user_date", table_name="investment_record")
    op.drop_table("investment_record")
    op.drop_index("ix_bucket_fund_user", table_name="bucket_fund_config")
    op.drop_table("bucket_fund_config")
