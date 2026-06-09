"""add bucket_config to user_config

Revision ID: 002
Revises: 001
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def _legacy_buckets(nasdaq: float, dividend: float, bond: float) -> dict:
    bond_long = bond * 0.7
    bond_short = bond * 0.3
    defaults = [
        ("growth", "成长", nasdaq, "#3ABFF8"),
        ("dividend", "红利", dividend, "#F87272"),
        ("gold", "黄金", 0.0, "#FBBD23"),
        ("bond_long", "长债", bond_long, "#B083F0"),
        ("bond_short", "短债", bond_short, "#67E8F9"),
    ]
    return {
        "buckets": [
            {"code": c, "name": n, "target_pct": p, "color": col}
            for c, n, p, col in defaults
        ]
    }


def upgrade() -> None:
    op.add_column(
        "user_config",
        sa.Column("bucket_config", sa.JSON(), nullable=True),
    )
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, target_nasdaq_pct, target_dividend_pct, target_bond_pct FROM user_config"
        )
    ).fetchall()
    for row in rows:
        cfg = _legacy_buckets(
            float(row.target_nasdaq_pct),
            float(row.target_dividend_pct),
            float(row.target_bond_pct),
        )
        conn.execute(
            sa.text("UPDATE user_config SET bucket_config = :cfg WHERE id = :id"),
            {"cfg": json.dumps(cfg), "id": row.id},
        )


def downgrade() -> None:
    op.drop_column("user_config", "bucket_config")
