"""scorer_run + dimension_score_citation; version company scores by the rubric (S1-6)

Builds causal_graph/v1_model/scorer_run_ddl_PROPOSED.sql, which specified these tables and
was never applied. Until now every company score the LLM extractor produced lived in loose
JSON on disk and nothing in the app wrote `company_dimension_score` at all -- so no match
surface could be built on it, and no stored score could be traced back to the rubric wording
that produced it. That traceability is the point: with it, a change of anchor wording is a
re-run against stored rows rather than a rebuild.

WHY scorer_run IS NOT model_run
-------------------------------
schema.sql's `model_run` versions the PyMC FIT (model_version, dimension_set_version,
priors_version). The scorer's version axis moves when a vendor ships a model update; the
Bayesian model's moves when priors or dimensions change. Fusing them would make neither
independently queryable. The PROPOSED DDL makes this call explicitly and it is preserved
here deliberately -- these stay two tables.

THE UNIQUENESS KEY (the PROPOSED DDL does not cover this)
---------------------------------------------------------
`uq_cscore_company_dim_source_asof` was (company_id, dimension_key, source, as_of), so
scoring one company twice on one day under two different rubrics failed outright -- which
is precisely the comparison these tables exist to make possible. scorer_run_id joins the key.

It is added as UNIQUE **NULLS NOT DISTINCT**. Adding a nullable column to a plain UNIQUE
constraint would silently WEAKEN the guarantee for the rows that have no scorer run:
Postgres treats NULLs as distinct, so two human 'researched' rows for the same
company/dimension/day would both insert where today the second is refused. NULLS NOT
DISTINCT gives both halves at once -- LLM rows from different runs coexist, and
NULL-scorer_run rows keep exactly the behaviour they have today. Both halves are tested in
tests/test_company_side_tables.py.

That needs Postgres 15+; this repo runs 18 (CI pinned, uuidv7 is native). If the server is
older this migration REFUSES rather than falling back to a plain UNIQUE, per D-07: a
weakening raises, it does not degrade quietly into a "safe" default.

REVERSIBILITY
-------------
The downgrade is honest but conditional, and it says so at runtime. Dropping scorer_run_id
means the old four-column key must hold again, and rows written under two scorer runs for
one (company, dimension, source, as_of) violate it by construction -- that being the whole
reason the column was added. The downgrade therefore checks first and refuses with the
offending cells named, rather than half-dropping the schema and leaving a table that cannot
take its own constraint back.

Revision ID: 20260906_scorer_run
Revises: 20260903_user_sessions
Create Date: 2026-09-06
"""
import sys

from alembic import op
import sqlalchemy as sa

revision = "20260906_scorer_run"
down_revision = "20260903_user_sessions"
branch_labels = None
depends_on = None

#: The four-column key as it stood before this revision, and the five-column key that
#: replaces it. Named once so upgrade and downgrade cannot drift apart.
OLD_KEY = ("company_id", "dimension_key", "source", "as_of")
NEW_KEY = OLD_KEY + ("scorer_run_id",)
KEY_NAME = "uq_cscore_company_dim_source_asof"


def _require_nulls_not_distinct() -> None:
    """Refuse to run where the five-column key cannot be expressed without weakening.

    D-07: a constraint that cannot be enforced as designed raises. The alternative -- a
    plain UNIQUE over the same five columns -- looks identical in a schema dump and
    silently stops de-duplicating the human 'researched' rows, which is the failure this
    whole migration is written to avoid.
    """
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError(
            "This revision needs UNIQUE NULLS NOT DISTINCT, which %s does not have. "
            "Refusing: a plain UNIQUE over the same five columns would silently allow "
            "duplicate 'researched' rows that are refused today (D-07)."
            % bind.dialect.name
        )
    version = bind.dialect.server_version_info or ()
    if version < (15,):
        raise RuntimeError(
            "UNIQUE NULLS NOT DISTINCT requires PostgreSQL 15+; this server reports %r. "
            "Refusing rather than falling back to a plain UNIQUE, which would silently "
            "weaken the existing de-duplication guarantee for 'researched' and "
            "'declared' rows (D-07)." % (version,)
        )


def upgrade():
    _require_nulls_not_distinct()

    # -- the scorer's own version axis ------------------------------------------------
    op.create_table(
        "scorer_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        # The exact pinned snapshot string, e.g. 'gpt-5.5-2026-04-23'. NEVER an alias:
        # an alias silently re-points when the vendor ships an update, which is the one
        # thing this column exists to make visible.
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("temperature", sa.Numeric(), nullable=True),
        # FALSE if the API rejected or ignored the requested temperature. Near-zero
        # variance from an ignored temperature is not the same finding as near-zero
        # variance from a better model (SPRINT_SCORER_PIPELINE_01.md).
        sa.Column("temperature_honored", sa.Boolean(), nullable=False),
        sa.Column("reasoning_effort", sa.Text(), nullable=True),
        # anchors.json's rubric_version, e.g. 'v1-frozen-2026-08-15'.
        sa.Column("rubric_version", sa.Text(), nullable=False),
        # Collector-prompt build version parsed from the packet header, e.g. 'v4.6'.
        sa.Column("packet_version", sa.Text(), nullable=False),
        sa.Column(
            "run_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # -- trace every scraped score back to the run that produced it --------------------
    # Nullable: 'researched' (human ground truth) and 'declared' (from the company) rows
    # have no scorer run, and never will.
    op.add_column(
        "company_dimension_score",
        sa.Column("scorer_run_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_cscore_scorer_run", "company_dimension_score", "scorer_run",
        ["scorer_run_id"], ["id"],
    )
    op.create_index(
        "ix_company_dimension_score_scorer_run_id",
        "company_dimension_score", ["scorer_run_id"],
    )

    # -- the key change: two rubrics on one company on one day must coexist ------------
    op.drop_constraint(KEY_NAME, "company_dimension_score", type_="unique")
    op.create_unique_constraint(
        KEY_NAME, "company_dimension_score", list(NEW_KEY),
        postgresql_nulls_not_distinct=True,
    )

    # -- one row per evidence quote per score ------------------------------------------
    # `matched` / `matched_excerpt_id` / `source_tag` are the citation verifier's output
    # (S1-5), not the model's self-report -- source is computed downstream from the
    # packet's addressable excerpts rather than trusted from the model.
    #
    # An UNMATCHED quote is STORED, never discarded. A quote that fails to verify is
    # exactly the failure this table exists to make visible; dropping it would leave the
    # score looking better evidenced than it is.
    op.create_table(
        "dimension_score_citation",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        # Integer, not BIGINT as the PROPOSED DDL wrote it: schema.sql declared
        # company_dimension_score.id BIGSERIAL but the applied app table (20260819) made
        # it INTEGER. Matching the column actually referenced beats matching the proposal.
        sa.Column("company_dimension_score_id", sa.Integer(), nullable=False),
        sa.Column("quote_text", sa.Text(), nullable=False),
        sa.Column("matched", sa.Boolean(), nullable=False),
        sa.Column("matched_excerpt_id", sa.Text(), nullable=True),
        sa.Column("source_tag", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_dimension_score_id"], ["company_dimension_score.id"],
            name="fk_citation_score",
        ),
        sa.PrimaryKeyConstraint("id"),
        # An unverified quote has no known provenance to report, so both provenance
        # columns must be empty exactly when `matched` is false. Without this the table
        # could carry a source_tag for a quote that was never found in the packet.
        sa.CheckConstraint(
            "(matched AND matched_excerpt_id IS NOT NULL AND source_tag IS NOT NULL) "
            "OR (NOT matched AND matched_excerpt_id IS NULL AND source_tag IS NULL)",
            name="ck_citation_provenance_iff_matched",
        ),
    )
    op.create_index(
        "ix_citation_score", "dimension_score_citation", ["company_dimension_score_id"]
    )


def downgrade():
    # FIRST, before dropping anything: can the four-column key come back at all? Postgres
    # would roll the whole downgrade back anyway on transactional DDL, but ordering the
    # check first is what makes that a guarantee of this migration rather than a property
    # of the database it happens to run on.
    bind = op.get_bind()
    clashes = bind.execute(
        sa.text(
            "SELECT company_id, dimension_key, source, as_of, count(*) AS n "
            "FROM company_dimension_score "
            "GROUP BY company_id, dimension_key, source, as_of HAVING count(*) > 1"
        )
    ).fetchall()
    if clashes:
        message = (
            "Cannot downgrade: %d (company, dimension, source, as_of) cell(s) hold more "
            "than one score, which is only possible because scorer_run_id distinguishes "
            "them. Restoring the four-column key would have to delete real scores, and "
            "this migration will not choose which. Delete the superseded scorer_run's "
            "rows deliberately, then re-run. Offending cells: %r"
            % (len(clashes), [tuple(r) for r in clashes[:10]])
        )
        # Written to stderr as well as raised. `flask db downgrade` routes an exception
        # from a migration through a logger this app's structured-logging config
        # suppresses, so the CLI otherwise exits 1 with NO explanation at all -- measured
        # 2026-09-06. A refusal nobody can read is an unexplained failure.
        sys.stderr.write("\n" + message + "\n\n")
        sys.stderr.flush()
        raise RuntimeError(message)

    op.drop_index("ix_citation_score", "dimension_score_citation")
    op.drop_table("dimension_score_citation")

    op.drop_constraint(KEY_NAME, "company_dimension_score", type_="unique")
    op.create_unique_constraint(KEY_NAME, "company_dimension_score", list(OLD_KEY))

    op.drop_index("ix_company_dimension_score_scorer_run_id", "company_dimension_score")
    op.drop_constraint("fk_cscore_scorer_run", "company_dimension_score", type_="foreignkey")
    op.drop_column("company_dimension_score", "scorer_run_id")
    op.drop_table("scorer_run")
