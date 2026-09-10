"""add environment_reports + environment_dimension_score (BUILD_PLAN A-2)

Storage for the Situation Report's environment-side instrument. See `model.py`'s
"Environment side" section for the full design rationale (long-format scores mirroring
the person-side dimension-score table, append-only unlike it, JSONB raw answers decoupled
from A-1's item keys, no D-15 pin here). Summarized:

- `environment_reports` is one row per submission, never updated. `raw_answers` is
  opaque JSONB (item id -> choice) precisely because A-1 -- the instrument that will
  define those item ids -- had not landed when this migration was written; nothing here
  depends on its shape.
- `environment_dimension_score` is long-format (one row per report per dimension),
  matching the person-side dimension-score table's shape so
  `causal_graph/v1_model/assemble_training_data.py` (E-4) can eventually read both sides
  of a training pair through the same kind of query. Dimension keys are plain strings
  validated in code (`model.ENV_DIMENSIONS`), not a DB registry or CHECK vocabulary --
  the same convention the person-side and `company_dimension_score` tables already use.

Revision ID: 20260910_environment_reports
Revises: 20260906_scorer_run
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260910_environment_reports"
down_revision = "20260906_scorer_run"
branch_labels = None
depends_on = None

CAREER_STATUSES = ("employed", "between_jobs", "first_job")


def upgrade():
    op.create_table(
        "environment_reports",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "submitted_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("raw_answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("stage_size", sa.SmallInteger(), nullable=False),
        sa.Column("comp", sa.SmallInteger(), nullable=True),
        sa.Column("experienced_outcome", sa.SmallInteger(), nullable=False),
        sa.Column("career_status", sa.Text(), nullable=False),
        sa.Column("employer_name_normalized", sa.Text(), nullable=True),
        sa.Column("version", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_envreport_user"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "stage_size >= 1 AND stage_size <= 5", name="ck_envreport_stage_size_range"
        ),
        sa.CheckConstraint(
            "comp IS NULL OR (comp >= 1 AND comp <= 5)", name="ck_envreport_comp_range"
        ),
        sa.CheckConstraint(
            "experienced_outcome >= 1 AND experienced_outcome <= 5",
            name="ck_envreport_experienced_outcome_range",
        ),
        sa.CheckConstraint(
            "career_status IN %s" % (CAREER_STATUSES,),
            name="ck_envreport_career_status_vocab",
        ),
    )
    op.create_index(
        "ix_environment_reports_user_submitted",
        "environment_reports",
        ["user_id", sa.text("submitted_at DESC")],
    )

    op.create_table(
        "environment_dimension_score",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("environment_report_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("dimension_key", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column(
            "scored_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["environment_report_id"], ["environment_reports.id"],
            name="fk_edscore_report",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_edscore_user"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "environment_report_id", "dimension_key", name="uq_edscore_report_dim"
        ),
        sa.CheckConstraint("score >= 0 AND score <= 1", name="ck_edscore_score_range"),
    )
    op.create_index(
        "ix_environment_dimension_score_environment_report_id",
        "environment_dimension_score", ["environment_report_id"],
    )
    op.create_index(
        "ix_environment_dimension_score_user_id",
        "environment_dimension_score", ["user_id"],
    )


def downgrade():
    op.drop_index(
        "ix_environment_dimension_score_user_id", "environment_dimension_score"
    )
    op.drop_index(
        "ix_environment_dimension_score_environment_report_id",
        "environment_dimension_score",
    )
    op.drop_table("environment_dimension_score")

    op.drop_index("ix_environment_reports_user_submitted", "environment_reports")
    op.drop_table("environment_reports")
