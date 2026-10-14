"""company evidence pipeline: research runs, evidence items, item scores, trait records,
job postings, company headcount (six-trait build, C3)

PRODUCT_DECISIONS.md §2 "The six-trait match model" (2026-10-13): each company trait is
a RECORD, not a number. This revision is the storage for the production pipeline that
produces those records -- research run -> evidence items -> per-item, per-dimension
scores with an explicit abstain -> aggregated trait records -- plus the user's own pasted
job posting as a role-scope source, and the company's raw headcount from which the
`stage_size` confounder is derived. The research/scoring code (C5) and the match service
(C6) write and read these tables through `company_evidence_store.py` only. See the
"Company evidence pipeline" section of model.py for the design notes behind each table.

The existing S1-6 company score + dimension_score_citation path is untouched and NOT
repurposed: it stays the research/ground-truth path. `evidence_item_score` points at the
same `scorer_run` so a rubric change is a re-run on both. (The S1-6 score table is not
named here on purpose: tests/test_company_confidence_unused.py reads prose, and this
revision's `confidence` column is the trait record's, not the score row's.)

`company_evidence_item.excerpt_internal` is the third-party text the scorer scored. It is
INTERNAL ONLY and never reaches a route or page (GAP-14,
Solverah_IP/compliance/AI_GOVERNANCE_AND_CLAIMS.md). `paraphrase` is what users may see.
tests/test_company_evidence_internal.py enforces the reachability rule.

WHY NO `NULLS NOT DISTINCT` KEY
-------------------------------
20260906_scorer_run's question is asked and answered rather than skipped: the only unique
keys here -- `uq_iscore_item_dim_run` (item, dimension, scorer run) and
`uq_ctrait_evidence_record_score` -- are over NOT NULL columns, so no NULL is ever
compared. `company_trait_record` deliberately has NO unique key: it keeps history and the
latest `computed_at` per (company, dimension, scope, scope_label, job_posting_id) wins on
read, served by `ix_ctrait_latest`.

PRIVATE vs SHARED RECORDS
-------------------------
A trait record aggregated from a user's pasted posting carries that `job_posting_id` (role
scope only, by CHECK). It is private to the posting's owner: the shared company read
returns only `job_posting_id IS NULL` rows, and account deletion destroys the posting, its
items, their scores, and these records with their link rows, so nothing derived from a
deleted user's paste survives (orchestrator review, 2026-10-13).

TABLE ORDER
-----------
`job_posting_submission` is created before `company_evidence_item` so the item's FK to
it exists at creation time; `company_research_run` likewise. Dropped in reverse.

REVERSIBILITY
-------------
Unconditionally reversible. Five of the six tables hold research output that the
pipeline recomputes from its inputs (a company name and the web), so a rollback destroys
nothing that cannot be rebuilt by re-running research. The exception is
`job_posting_submission`: those are users' own pastes, on 20260921_path_wants' terms --
a rollback of this deploy must be able to proceed, and what it destroys is a paste the
user can repeat. The three `company` columns are dropped with their CHECK; the derived
`stage_size` rows in `company_confounder_value` are ordinary confounder rows under the
existing table and are left in place, exactly as a hand-entered confounder would be.

Revision ID: 20261013_company_evidence
Revises: 20261013_trait_prefs
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261013_company_evidence"
down_revision = "20261013_trait_prefs"
branch_labels = None
depends_on = None


def upgrade():
    # -- company: raw headcount, from which the stage_size confounder is cut ----------
    op.add_column("company", sa.Column("headcount", sa.Integer(), nullable=True))
    op.add_column("company", sa.Column("headcount_as_of", sa.Date(), nullable=True))
    op.add_column("company", sa.Column("headcount_source", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_company_headcount_positive", "company", "headcount IS NULL OR headcount >= 1"
    )

    # -- one row per research run per company; the on-demand cache reads status here --
    op.create_table(
        "company_research_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        # The exact pinned snapshot string, never an alias (as scorer_run.model).
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        # INTERNAL ONLY -- the pipeline's run card: counts, the raw research text and
        # the citations' verbatim text. Never serialized (C5b, review F2).
        sa.Column(
            "diagnostics_internal", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "trigger IN ('on_demand', 'batch')", name="ck_cresearch_trigger_vocab"
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')",
            name="ck_cresearch_status_vocab",
        ),
        sa.CheckConstraint(
            "status = 'failed' OR error IS NULL", name="ck_cresearch_error_only_on_failed"
        ),
        sa.CheckConstraint(
            "(status IN ('done', 'failed')) = (finished_at IS NOT NULL)",
            name="ck_cresearch_finished_iff_terminal",
        ),
        sa.CheckConstraint(
            "status = 'queued' OR started_at IS NOT NULL",
            name="ck_cresearch_started_unless_queued",
        ),
        sa.CheckConstraint("cost_usd IS NULL OR cost_usd >= 0", name="ck_cresearch_cost_nonneg"),
    )
    op.create_index(
        "ix_cresearch_company_created", "company_research_run", ["company_id", "created_at"]
    )

    # -- the user's own pasted posting (user-keyed; export/delete is auth-accounts') -----
    op.create_table(
        "job_posting_submission",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("posting_text", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('pending', 'scored', 'failed')", name="ck_jobposting_status_vocab"
        ),
        sa.CheckConstraint("length(posting_text) > 0", name="ck_jobposting_text_nonempty"),
    )
    op.create_index("ix_jobposting_user", "job_posting_submission", ["user_id"])

    # -- evidence items: exactly one parent, a scope, an internal excerpt + a paraphrase --
    op.create_table(
        "company_evidence_item",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("research_run_id", sa.BigInteger(), nullable=True),
        sa.Column("job_posting_id", sa.BigInteger(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("scope_label", sa.Text(), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column(
            "retrieved_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        # Who is speaking ('employee review, Cashier', 'employer response'): rubric
        # gate 2's input, and how an employer's reply is told from a review (C5b, F4).
        sa.Column("speaker", sa.Text(), nullable=True),
        # INTERNAL ONLY -- never serialized. See the module docstring.
        sa.Column("excerpt_internal", sa.Text(), nullable=False),
        sa.Column("paraphrase", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.ForeignKeyConstraint(["research_run_id"], ["company_research_run.id"]),
        sa.ForeignKeyConstraint(["job_posting_id"], ["job_posting_submission.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(research_run_id IS NOT NULL AND job_posting_id IS NULL) "
            "OR (research_run_id IS NULL AND job_posting_id IS NOT NULL)",
            name="ck_cevidence_one_parent",
        ),
        sa.CheckConstraint(
            "scope IN ('company', 'division', 'location', 'role')",
            name="ck_cevidence_scope_vocab",
        ),
        sa.CheckConstraint(
            "source_type IN ('careers_page', 'employee_review', 'job_posting', "
            "'first_person', 'news', 'disclosure', 'user_pasted_posting')",
            name="ck_cevidence_source_vocab",
        ),
        sa.CheckConstraint(
            "(job_posting_id IS NOT NULL) = (source_type = 'user_pasted_posting')",
            name="ck_cevidence_posting_source",
        ),
        sa.CheckConstraint(
            "job_posting_id IS NULL OR scope = 'role'", name="ck_cevidence_posting_is_role"
        ),
        sa.CheckConstraint(
            "scope <> 'company' OR scope_label IS NULL",
            name="ck_cevidence_company_scope_unlabelled",
        ),
        sa.CheckConstraint("length(paraphrase) > 0", name="ck_cevidence_paraphrase_nonempty"),
    )
    op.create_index("ix_cevidence_company", "company_evidence_item", ["company_id"])
    op.create_index("ix_cevidence_run", "company_evidence_item", ["research_run_id"])
    op.create_index("ix_cevidence_posting", "company_evidence_item", ["job_posting_id"])

    # -- per-item, per-dimension scores, with the explicit abstain ---------------------
    op.create_table(
        "evidence_item_score",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("evidence_item_id", sa.BigInteger(), nullable=False),
        sa.Column("dimension_key", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("abstained", sa.Boolean(), nullable=False),
        # The scorer's own confidence band (rubric gate 5): stored, never weighted by
        # (C5b, F4). Not the S1-6 score table's column of the same name.
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("scorer_run_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["evidence_item_id"], ["company_evidence_item.id"]),
        sa.ForeignKeyConstraint(["scorer_run_id"], ["scorer_run.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evidence_item_id", "dimension_key", "scorer_run_id",
            name="uq_iscore_item_dim_run",
        ),
        sa.CheckConstraint(
            "(abstained AND score IS NULL) OR (NOT abstained AND score IS NOT NULL)",
            name="ck_iscore_abstained_iff_null",
        ),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 1)", name="ck_iscore_score_range"
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_iscore_confidence_range",
        ),
    )
    op.create_index("ix_iscore_run", "evidence_item_score", ["scorer_run_id"])

    # -- the trait record: known / mixed / unknown, history kept -------------------------
    # A record with a job_posting_id is PRIVATE to that posting's owner (role scope only)
    # and dies with the posting; NULL is the shared, research-derived read.
    op.create_table(
        "company_trait_record",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("job_posting_id", sa.BigInteger(), nullable=True),
        sa.Column("dimension_key", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("scope_label", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("estimate", sa.Float(), nullable=True),
        sa.Column("low_end", sa.Float(), nullable=True),
        sa.Column("high_end", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "evidence_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "abstain_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("first_dated", sa.Date(), nullable=True),
        sa.Column("last_dated", sa.Date(), nullable=True),
        sa.Column("split_explained_by", sa.Text(), nullable=True),
        sa.Column("aggregation_version", sa.Text(), nullable=False),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.ForeignKeyConstraint(["job_posting_id"], ["job_posting_submission.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "scope IN ('company', 'division', 'location', 'role')",
            name="ck_ctrait_scope_vocab",
        ),
        sa.CheckConstraint(
            "status IN ('known', 'mixed', 'unknown')", name="ck_ctrait_status_vocab"
        ),
        sa.CheckConstraint(
            "scope <> 'company' OR scope_label IS NULL",
            name="ck_ctrait_company_scope_unlabelled",
        ),
        sa.CheckConstraint(
            "(status = 'known') = (estimate IS NOT NULL)", name="ck_ctrait_known_iff_estimate"
        ),
        sa.CheckConstraint(
            "(status = 'mixed') = (low_end IS NOT NULL AND high_end IS NOT NULL)",
            name="ck_ctrait_mixed_iff_ends",
        ),
        sa.CheckConstraint(
            "(low_end IS NULL) = (high_end IS NULL)", name="ck_ctrait_ends_together"
        ),
        sa.CheckConstraint(
            "low_end IS NULL OR high_end IS NULL OR low_end <= high_end",
            name="ck_ctrait_ends_ordered",
        ),
        sa.CheckConstraint(
            "estimate IS NULL OR (estimate >= 0 AND estimate <= 1)",
            name="ck_ctrait_estimate_range",
        ),
        sa.CheckConstraint(
            "low_end IS NULL OR (low_end >= 0 AND low_end <= 1)", name="ck_ctrait_low_range"
        ),
        sa.CheckConstraint(
            "high_end IS NULL OR (high_end >= 0 AND high_end <= 1)",
            name="ck_ctrait_high_range",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_ctrait_confidence_range",
        ),
        sa.CheckConstraint(
            "split_explained_by IS NULL OR split_explained_by IN ('scope', 'time')",
            name="ck_ctrait_split_vocab",
        ),
        # A mixed record says what explains its split; a KNOWN record may carry 'time'
        # as the "changed recently" note when the recent side of a time-explained split
        # decided it (C5b, provisional Julie ask 4). Never on unknown.
        sa.CheckConstraint(
            "split_explained_by IS NULL OR status <> 'unknown'",
            name="ck_ctrait_split_not_unknown",
        ),
        sa.CheckConstraint(
            "evidence_count >= 0 AND abstain_count >= 0", name="ck_ctrait_counts_nonneg"
        ),
        sa.CheckConstraint(
            "(first_dated IS NULL) = (last_dated IS NULL)", name="ck_ctrait_dates_together"
        ),
        sa.CheckConstraint(
            "first_dated IS NULL OR last_dated IS NULL OR first_dated <= last_dated",
            name="ck_ctrait_dates_ordered",
        ),
        sa.CheckConstraint(
            "job_posting_id IS NULL OR scope = 'role'", name="ck_ctrait_posting_is_role"
        ),
    )
    op.create_index(
        "ix_ctrait_latest", "company_trait_record",
        ["company_id", "dimension_key", "scope", "scope_label", "job_posting_id",
         sa.text("computed_at DESC"), sa.text("id DESC")],
    )
    op.create_index("ix_ctrait_posting", "company_trait_record", ["job_posting_id"])

    # -- which item scores each record was computed from -------------------------------
    op.create_table(
        "company_trait_record_evidence",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("trait_record_id", sa.BigInteger(), nullable=False),
        sa.Column("evidence_item_score_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["trait_record_id"], ["company_trait_record.id"]),
        sa.ForeignKeyConstraint(["evidence_item_score_id"], ["evidence_item_score.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "trait_record_id", "evidence_item_score_id",
            name="uq_ctrait_evidence_record_score",
        ),
    )
    op.create_index(
        "ix_ctrait_evidence_score", "company_trait_record_evidence", ["evidence_item_score_id"]
    )


def downgrade():
    op.drop_index("ix_ctrait_evidence_score", "company_trait_record_evidence")
    op.drop_table("company_trait_record_evidence")
    op.drop_index("ix_ctrait_posting", "company_trait_record")
    op.drop_index("ix_ctrait_latest", "company_trait_record")
    op.drop_table("company_trait_record")
    op.drop_index("ix_iscore_run", "evidence_item_score")
    op.drop_table("evidence_item_score")
    op.drop_index("ix_cevidence_posting", "company_evidence_item")
    op.drop_index("ix_cevidence_run", "company_evidence_item")
    op.drop_index("ix_cevidence_company", "company_evidence_item")
    op.drop_table("company_evidence_item")
    op.drop_index("ix_jobposting_user", "job_posting_submission")
    op.drop_table("job_posting_submission")
    op.drop_index("ix_cresearch_company_created", "company_research_run")
    op.drop_table("company_research_run")
    op.drop_constraint("ck_company_headcount_positive", "company", type_="check")
    op.drop_column("company", "headcount_source")
    op.drop_column("company", "headcount_as_of")
    op.drop_column("company", "headcount")
