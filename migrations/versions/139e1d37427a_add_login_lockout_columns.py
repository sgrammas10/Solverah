"""Add login lockout columns to user

Revision ID: 139e1d37427a
Revises: 0003_audit_log_event_metadata
Create Date: 2026-01-26
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "139e1d37427a"
down_revision = "0003_audit_log_event_metadata"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "user",
        sa.Column(
            "failed_login_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "user",
        sa.Column("locked_until", sa.DateTime(), nullable=True),
    )
    # Drop default so future inserts rely on ORM default.
    op.alter_column("user", "failed_login_attempts", server_default=None)


def downgrade():
    op.drop_column("user", "locked_until")
    op.drop_column("user", "failed_login_attempts")
