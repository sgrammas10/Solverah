"""Add password reset token columns to user table.

Revision ID: 20260526_add_password_reset_token
Revises: 20260414_work_environment_to_text
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa

revision = "20260526_add_password_reset_token"
down_revision = "20260414_work_environment_to_text"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user", sa.Column("reset_token", sa.String(length=64), nullable=True))
    op.add_column("user", sa.Column("reset_sent_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("user", "reset_sent_at")
    op.drop_column("user", "reset_token")
