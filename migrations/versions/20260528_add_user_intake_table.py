"""add user_intake table

Revision ID: 20260528_user_intake
Revises: 20260526_add_password_reset_token
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa

revision = "20260528_user_intake"
down_revision = "20260526_add_password_reset_token"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_intake",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("selected_statement_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("wpll_answers", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("wpll_insight_text", sa.Text(), nullable=True),
        sa.Column("wpll_completed_at", sa.DateTime(), nullable=True),
        sa.Column("wpl_answers", sa.JSON(), nullable=True),
        sa.Column("wpl_narrative", sa.Text(), nullable=True),
        sa.Column("wpl_completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_intake_user_id"),
    )


def downgrade():
    op.drop_table("user_intake")
