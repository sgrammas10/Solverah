"""Rename audit log metadata attribute

Revision ID: 0003_audit_log_event_metadata
Revises: 0002_audit_logs
Create Date: 2026-01-12

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "0003_audit_log_event_metadata"
down_revision = "0002_audit_logs"
branch_labels = None
depends_on = None


def upgrade():
    # No database change needed; aligns ORM attribute name.
    pass


def downgrade():
    pass