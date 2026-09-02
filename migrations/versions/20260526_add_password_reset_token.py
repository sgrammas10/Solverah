"""Add password reset token columns to user table.

Revision ID: 20260526_password_reset_token
Revises: 20260414_work_env_to_text
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa

# Renamed from "20260526_add_password_reset_token" (33 chars): over the VARCHAR(32) limit of
# alembic_version.version_num. See tests/test_migrations_chain.py.
revision = "20260526_password_reset_token"
down_revision = "20260414_work_env_to_text"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user", sa.Column("reset_token", sa.String(length=64), nullable=True))
    op.add_column("user", sa.Column("reset_sent_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("user", "reset_sent_at")
    op.drop_column("user", "reset_token")
