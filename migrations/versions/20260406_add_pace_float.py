"""Add pace_float column to company table and backfill from pace string.

Revision ID: 20260406_add_pace_float
Revises: 20260330_add_company
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa

revision = "20260406_add_pace_float"
down_revision = "20260330_add_company"
branch_labels = None
depends_on = None

_PACE_MAP = {
    "slow": 0.0,
    "moderate": 0.33,
    "fast": 0.66,
    "very-fast": 1.0,
}


def upgrade():
    op.add_column("company", sa.Column("pace_float", sa.Float(), nullable=True))

    company = sa.table("company", sa.column("pace", sa.String), sa.column("pace_float", sa.Float))
    conn = op.get_bind()
    for label, value in _PACE_MAP.items():
        conn.execute(
            company.update()
            .where(company.c.pace == label)
            .values(pace_float=value)
        )


def downgrade():
    op.drop_column("company", "pace_float")
