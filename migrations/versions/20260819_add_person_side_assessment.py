"""add person-side assessment tables

Adds the minimum subset of causal_graph/v1_model/schema.sql needed to persist a completed
person-side assessment: raw responses (append-only) and derived dimension scores.

Deliberately NOT included: schema.sql's `person`, `dimension`, `company`,
`company_dimension_score`, `confounder`, `recommendation`, `model_run`, `weight_posterior`
and the outcome tables. schema.sql's `company` collides with the application's existing
`company` table and reconciling them is separate work (S-07). `person` is replaced by a
direct reference to `user.id` -- see the model docstrings for why.

Revision ID: 20260819_person_assessment
Revises: 20260603_wpl_result
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa

revision = "20260819_person_assessment"
down_revision = "20260603_wpl_result"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assessment_response",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=False),
        sa.Column("choice", sa.String(length=8), nullable=False),
        sa.Column("form_version", sa.String(length=64), nullable=False),
        sa.Column(
            "answered_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "submission_id", "item_id", name="uq_response_submission_item"
        ),
    )
    op.create_index(
        "ix_assessment_response_user_id", "assessment_response", ["user_id"]
    )
    op.create_index(
        "ix_assessment_response_submission_id", "assessment_response", ["submission_id"]
    )

    op.create_table(
        "person_dimension_score",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("dimension_key", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("scoring_key_version", sa.String(length=64), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column(
            "scored_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "dimension_key",
            "scoring_key_version",
            name="uq_pscore_person_dim_keyversion",
        ),
        sa.CheckConstraint("score >= 0 AND score <= 1", name="ck_pscore_score_range"),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_pscore_confidence_range",
        ),
    )
    op.create_index(
        "ix_person_dimension_score_user_id", "person_dimension_score", ["user_id"]
    )


def downgrade():
    op.drop_index("ix_person_dimension_score_user_id", "person_dimension_score")
    op.drop_table("person_dimension_score")
    op.drop_index("ix_assessment_response_submission_id", "assessment_response")
    op.drop_index("ix_assessment_response_user_id", "assessment_response")
    op.drop_table("assessment_response")
