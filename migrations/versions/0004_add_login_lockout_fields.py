"""Add login lockout fields to user

Revision ID: 0004_add_login_lockout_fields
Revises: 0003_audit_log_event_metadata
Create Date: 2026-01-29

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0004_add_login_lockout_fields"
down_revision = "0003_audit_log_event_metadata"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user",
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "user",
        sa.Column("locked_until", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_column("user", "locked_until")
    op.drop_column("user", "failed_login_attempts")
