"""DB ledger indexes: seven added where readers scanned, seven dropped that served nothing

Indexes only. No table, column, constraint or row changes, so every statement
here is catalogue work plus one index build, and the whole migration runs in
alembic's one transaction. Plain CREATE INDEX rather than CONCURRENTLY for that
reason: CONCURRENTLY cannot run inside a transaction, and every table touched is
small in production (the largest, `user_sessions`, is one row per sign-in and
rotation inside its retention window), so the brief write lock is the cheaper
trade than a migration that can half-apply.

LOCK TIMEOUT FIRST. Both directions start with `SET LOCAL lock_timeout = '10s'`.
DROP INDEX takes ACCESS EXCLUSIVE on its table, `users` included. Without a
timeout it can queue behind a live request's ACCESS SHARE, and every later read
of that table then queues behind the DROP: an app-wide stall during the deploy.
With it, the migration fails fast, the transaction rolls back whole, and the
deploy stops with the old code still serving. Re-running it later is safe.
The slug check (below) runs straight after, before any CREATE, so an abort there
leaves nothing to undo either.

ADDED -- each one serves a query the DB ledger found scanning
-------------------------------------------------------------
* `ix_job_recommendation_user_id` -- the dashboard count, the export list and
  the account-deletion DELETE all filter `job_recommendation` on `user_id`; the
  table had only its primary key.
* `ix_intake_submissions_email_lower` on `lower(email)` -- the one expression
  every intake email lookup now compares through (`IntakeSubmission.email_key`):
  the account export and deletion, the dashboard's intake banner, and the
  retention sweep. The column is VARCHAR as submitted, not CITEXT.
* `ix_intake_submissions_created_at` -- retention's `created_at < cutoff`.
* `ix_user_sessions_parent`, `ix_user_sessions_successor` -- the two
  self-referencing foreign keys are `ON DELETE SET NULL`, so each row the
  retention purge deletes makes Postgres look for rows pointing at it. Plain and
  NON-UNIQUE by design: `refresh_tokens.rotate` inserts the successor before it
  claims the parent, and that order is deadlock-free only while no unique index
  covers these columns.
* `ix_outbox_published` -- `purge_published`'s `published_at IS NOT NULL AND
  published_at < cutoff`, partial on its first predicate; `ix_outbox_unpublished`
  already covers the other half.
* `ix_resume_parse_jobs_terminal` -- `purge_terminal`, the exact shape of
  `ix_scoring_jobs_terminal`.

DROPPED -- each one duplicated an index that stays, or served nothing
---------------------------------------------------------------------
* `ix_resume_parse_correction_user_id`, `ix_company_dimension_score_company_id`,
  `ix_company_confounder_value_company_id`, `ix_weight_posterior_model_run_id`,
  `ix_environment_dimension_score_environment_report_id` -- single-column
  indexes on the leading column of a unique constraint on the same table, which
  already serves every lookup (and every foreign-key check) on that column.
* `ix_company_slug` -- a plain index beside the unique constraint
  `company_slug_key` on the same column. The upgrade checks that the constraint
  is there before it drops the index: a database built by `db.create_all()`
  rather than this chain has `ix_company_slug` as the ONLY unique index on the
  slug, and dropping it there would silently lose the uniqueness.
* `ix_users_confirmation_token` -- no query filters on the token. Every reader
  looks the user up by email and compares the token in Python.

The two person-side assessment tables carry the same leading-column redundancy
and are deliberately left alone: naming them here would put this file outside
the D-01 allowlist, for about 24 index writes saved per sitting.

REVERSIBILITY
-------------
Unconditionally reversible: `downgrade` drops the seven added indexes and
recreates the seven dropped ones exactly as their original migrations built
them. No data is involved in either direction.

Revision ID: 20260928_ledger_indexes
Revises: 20260928_path_narratives
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa

revision = "20260928_ledger_indexes"
down_revision = "20260928_path_narratives"
branch_labels = None
depends_on = None


#: (name, table, columns, where) for every index this revision adds.
_ADDED = (
    ("ix_job_recommendation_user_id", "job_recommendation", ["user_id"], None),
    (
        "ix_intake_submissions_email_lower",
        "intake_submissions",
        [sa.text("lower(email)")],
        None,
    ),
    ("ix_intake_submissions_created_at", "intake_submissions", ["created_at"], None),
    ("ix_user_sessions_parent", "user_sessions", ["parent_id"], None),
    ("ix_user_sessions_successor", "user_sessions", ["successor_id"], None),
    ("ix_outbox_published", "outbox", ["published_at"], "published_at IS NOT NULL"),
    (
        "ix_resume_parse_jobs_terminal",
        "resume_parse_jobs",
        ["created_at"],
        "status IN ('succeeded', 'failed')",
    ),
)

#: (name, table, columns) for every index this revision drops. All seven were
#: plain, non-unique, whole-table indexes, which is how `downgrade` rebuilds them.
_DROPPED = (
    ("ix_resume_parse_correction_user_id", "resume_parse_correction", ["user_id"]),
    ("ix_company_slug", "company", ["slug"]),
    ("ix_company_dimension_score_company_id", "company_dimension_score", ["company_id"]),
    (
        "ix_company_confounder_value_company_id",
        "company_confounder_value",
        ["company_id"],
    ),
    ("ix_weight_posterior_model_run_id", "weight_posterior", ["model_run_id"]),
    (
        "ix_environment_dimension_score_environment_report_id",
        "environment_dimension_score",
        ["environment_report_id"],
    ),
    ("ix_users_confirmation_token", "users", ["confirmation_token"]),
)


def _require_slug_constraint():
    """Refuse to drop `ix_company_slug` unless `company_slug_key` keeps the slug unique."""
    present = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM pg_constraint "
            "WHERE conname = 'company_slug_key' AND contype = 'u' "
            "AND conrelid = CAST('company' AS regclass)"
        )
    ).scalar()
    if not present:
        raise RuntimeError(
            "company_slug_key is missing, so ix_company_slug may be the only unique "
            "index on company.slug; not dropping it. Inspect the company table's "
            "indexes before re-running this migration."
        )


#: First statement of each direction; see "LOCK TIMEOUT FIRST" above.
_LOCK_TIMEOUT = "SET LOCAL lock_timeout = '10s'"


def upgrade():
    op.execute(_LOCK_TIMEOUT)
    _require_slug_constraint()

    for name, table, columns, where in _ADDED:
        op.create_index(
            name,
            table,
            columns,
            postgresql_where=sa.text(where) if where else None,
        )

    for name, table, _columns in _DROPPED:
        op.drop_index(name, table_name=table)


def downgrade():
    op.execute(_LOCK_TIMEOUT)

    for name, table, columns in _DROPPED:
        op.create_index(name, table, columns)

    for name, table, _columns, _where in _ADDED:
        op.drop_index(name, table_name=table)
