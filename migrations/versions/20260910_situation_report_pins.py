"""add situation_report_pins (BUILD_PLAN A-5, ⚑5)

Storage for the Situation Report's D-15 pin override. See `model.py`'s
`SituationReportPin` docstring for the full design rationale: the DEFAULT pin (the
first completed `core` sitting) needs no row at all -- it is computed live from the
append-only submission and raw-answer tables behind `assessment_store`, which never
change which sitting was first. This table holds only the explicit override
`POST /me/situation-report/recalibrate` writes, one row per user (mutable, unlike
`environment_reports`/`manager_profiles`), and the ordering log lives in the
existing `audit_log` table rather than a second one here.

Revision ID: 20260910_situation_report_pins
Revises: 20260910_manager_profiles
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa

revision = "20260910_situation_report_pins"
down_revision = "20260910_manager_profiles"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "situation_report_pins",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column(
            "pinned_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_situationreportpin_user"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_situation_report_pins_user"),
    )


def downgrade():
    op.drop_table("situation_report_pins")
