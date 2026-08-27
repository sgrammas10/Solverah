"""add company-side, match/funnel, and model-run tables (S-07)

Completes the migration of causal_graph/v1_model/schema.sql into the app database.
Decided with Sebastian 2026-08-19:

- schema.sql's `company` is reconciled INTO the app's existing `company` table: one new
  nullable-unique `domain` column, nothing else. No parallel company table.
- No `dimension`/`confounder` registry tables -- keys are plain strings validated in code,
  matching the person-side convention already in production.
- schema.sql's Postgres enums (score_source, rec_channel, funnel_action) become
  String + CHECK constraints so the SQLite test database enforces the same vocabulary.
- schema.sql's `recommendation` is created as `match_recommendation` because the app
  already has `job_recommendation` for a different concept.

Empty tables are free; capture (funnel, outcomes) starts the day the product is
publicized instead of after a second migration.

Revision ID: 20260819_company_model
Revises: 20260819_person_assessment
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa

revision = "20260819_company_model"
down_revision = "20260819_person_assessment"
branch_labels = None
depends_on = None


def upgrade():
    # -- company: the one reconciliation change --------------------------------------
    op.add_column("company", sa.Column("domain", sa.String(length=255), nullable=True))
    op.create_unique_constraint("uq_company_domain", "company", ["domain"])

    # -- company side -----------------------------------------------------------------
    op.create_table(
        "company_dimension_score",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("dimension_key", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "is_ground_truth", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "dimension_key", "source", "as_of",
            name="uq_cscore_company_dim_source_asof",
        ),
        sa.CheckConstraint("score >= 0 AND score <= 1", name="ck_cscore_score_range"),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_cscore_confidence_range"
        ),
        sa.CheckConstraint(
            "source IN ('scraped', 'researched', 'declared')",
            name="ck_cscore_source_vocab",
        ),
    )
    op.create_index(
        "ix_company_dimension_score_company_id", "company_dimension_score", ["company_id"]
    )

    op.create_table(
        "company_confounder_value",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("confounder_key", sa.String(length=32), nullable=False),
        sa.Column("value_num", sa.Float(), nullable=True),
        sa.Column("value_cat", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "confounder_key", "source", "as_of",
            name="uq_conf_company_key_source_asof",
        ),
        sa.CheckConstraint(
            "value_num IS NOT NULL OR value_cat IS NOT NULL", name="ck_conf_value_present"
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_conf_confidence_range",
        ),
        sa.CheckConstraint(
            "source IN ('scraped', 'researched', 'declared')",
            name="ck_conf_source_vocab",
        ),
    )
    op.create_index(
        "ix_company_confounder_value_company_id", "company_confounder_value", ["company_id"]
    )

    # -- model runs (created before match_recommendation so its FK can exist at
    #    creation time -- no deferred-FK dance as in schema.sql) ----------------------
    op.create_table(
        "model_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("dimension_set_version", sa.String(length=64), nullable=False),
        sa.Column("priors_version", sa.String(length=64), nullable=False),
        sa.Column("n_rows", sa.Integer(), nullable=True),
        sa.Column(
            "trained_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "weight_posterior",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_run_id", sa.Integer(), nullable=False),
        sa.Column("weight_name", sa.String(length=64), nullable=False),
        sa.Column("mean", sa.Float(), nullable=False),
        sa.Column("sd", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["model_run_id"], ["model_run.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_run_id", "weight_name", name="uq_weight_run_name"),
    )
    op.create_index(
        "ix_weight_posterior_model_run_id", "weight_posterior", ["model_run_id"]
    )

    # -- match + funnel ----------------------------------------------------------------
    op.create_table(
        "match_recommendation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("model_run_id", sa.Integer(), nullable=True),
        sa.Column("p_fit", sa.Float(), nullable=True),
        sa.Column("p_fit_low", sa.Float(), nullable=True),
        sa.Column("p_fit_high", sa.Float(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column(
            "is_exploration", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "channel", sa.String(length=16), server_default="onsite", nullable=False
        ),
        sa.Column(
            "shown_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.ForeignKeyConstraint(["model_run_id"], ["model_run.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "p_fit IS NULL OR (p_fit >= 0 AND p_fit <= 1)", name="ck_mrec_pfit_range"
        ),
        sa.CheckConstraint(
            "p_fit_low IS NULL OR (p_fit_low >= 0 AND p_fit_low <= 1)",
            name="ck_mrec_pfit_low_range",
        ),
        sa.CheckConstraint(
            "p_fit_high IS NULL OR (p_fit_high >= 0 AND p_fit_high <= 1)",
            name="ck_mrec_pfit_high_range",
        ),
        sa.CheckConstraint(
            "channel IN ('onsite', 'email')", name="ck_mrec_channel_vocab"
        ),
    )
    op.create_index("ix_match_recommendation_user_id", "match_recommendation", ["user_id"])
    op.create_index(
        "ix_match_recommendation_company_id", "match_recommendation", ["company_id"]
    )

    op.create_table(
        "rec_action",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recommendation_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column(
            "acted_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["recommendation_id"], ["match_recommendation.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "action IN ('viewed', 'saved', 'passed', 'applied', 'interviewed', "
            "'offered', 'hired', 'accepted', 'declined')",
            name="ck_raction_action_vocab",
        ),
    )
    op.create_index("ix_rec_action_recommendation_id", "rec_action", ["recommendation_id"])

    # -- outcomes (separate tables on purpose: appeal is fast and biased, experienced
    #    is slow and true -- schema.sql design principle 4) ----------------------------
    op.create_table(
        "outcome_appeal",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recommendation_id", sa.Integer(), nullable=False),
        sa.Column("fit_yes", sa.Boolean(), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column(
            "responded_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["recommendation_id"], ["match_recommendation.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recommendation_id", name="uq_oappeal_recommendation"),
        sa.CheckConstraint(
            "channel IN ('onsite', 'email')", name="ck_oappeal_channel_vocab"
        ),
    )

    op.create_table(
        "outcome_experienced",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("recommendation_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.Date(), nullable=True),
        sa.Column(
            "checkin_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("working_scale", sa.SmallInteger(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.ForeignKeyConstraint(["recommendation_id"], ["match_recommendation.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "working_scale >= 1 AND working_scale <= 5", name="ck_oexp_working_scale_range"
        ),
    )
    op.create_index("ix_outcome_experienced_user_id", "outcome_experienced", ["user_id"])


def downgrade():
    op.drop_index("ix_outcome_experienced_user_id", "outcome_experienced")
    op.drop_table("outcome_experienced")
    op.drop_table("outcome_appeal")
    op.drop_index("ix_rec_action_recommendation_id", "rec_action")
    op.drop_table("rec_action")
    op.drop_index("ix_match_recommendation_company_id", "match_recommendation")
    op.drop_index("ix_match_recommendation_user_id", "match_recommendation")
    op.drop_table("match_recommendation")
    op.drop_index("ix_weight_posterior_model_run_id", "weight_posterior")
    op.drop_table("weight_posterior")
    op.drop_table("model_run")
    op.drop_index("ix_company_confounder_value_company_id", "company_confounder_value")
    op.drop_table("company_confounder_value")
    op.drop_index("ix_company_dimension_score_company_id", "company_dimension_score")
    op.drop_table("company_dimension_score")
    op.drop_constraint("uq_company_domain", "company", type_="unique")
    op.drop_column("company", "domain")
