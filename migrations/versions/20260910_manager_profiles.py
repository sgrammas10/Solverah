"""add manager_profiles (BUILD_PLAN C-3)

Storage for the Manager Decoder's observed-manager instrument. See `model.py`'s
`ManagerProfile` docstring for the full design rationale (⚑4's shared store, authored-identity
answers, `scoring_key` as a required column rather than a JSONB field). Summarized: one
table, append-only (D-16 tradition, matching `environment_reports`), consumed by the
Decoder's playbook now and the Situation Report's manager section later.

Revision ID: 20260910_manager_profiles
Revises: 20260910_environment_reports
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260910_manager_profiles"
down_revision = "20260910_environment_reports"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "manager_profiles",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dimension_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scoring_key", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_managerprofile_user"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_manager_profiles_user_created",
        "manager_profiles",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade():
    op.drop_index("ix_manager_profiles_user_created", "manager_profiles")
    op.drop_table("manager_profiles")
