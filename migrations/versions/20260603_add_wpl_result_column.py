"""add wpl_result column to user_intake

Revision ID: 20260603_wpl_result
Revises: 20260528_user_intake
Create Date: 2026-06-03
"""
from alembic import op
import sqlalchemy as sa

revision = "20260603_wpl_result"
down_revision = "20260528_user_intake"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user_intake",
        sa.Column("wpl_result", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("user_intake", "wpl_result")
