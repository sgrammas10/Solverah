"""Phase 3b: the scoring-job table.

One table, additive.  No existing column changes type, name or meaning, no data
is moved, and no existing endpoint's response shape depends on it -- so
``downgrade`` is a drop, as it was for the outbox migration this follows.

**Why one table for two job types.**  ``job_type`` discriminates
``assessment_scoring`` from ``path_suggestions``.  Both are "a user's input, a
provider call, a result", and they share a state machine, a claim, a reaper, a
lost-enqueue sweep and a purge.  Splitting them would buy two copies of those
five things -- which must not drift from each other -- to separate two column
sets that differ by one nullable ``kind``.  A12 is untouched by this: it governs
the *response* model per discriminator, and the poll endpoints publish and
validate one model per instrument regardless of where the row lives.

**Why ``resume_parse_jobs`` was not merged into it.**  That table carries
``object_key``, ``mime``, ``size_bytes`` and ``resume_name`` -- four columns with
no meaning for a scoring job -- and it already exists with a migration behind it.
Rewriting a shipped table to save a state machine that is copied once is a
migration risk taken for tidiness.

**Three check constraints, and each one closes a hole the application could
otherwise open.**  ``ck_scoring_jobs_kind_matches_type`` keeps ``kind`` on the
job type that has one, so a path-suggestion row cannot carry
``kind = 'work_pulse'`` and be served by the assessment poll under that
instrument's response model.  ``ck_scoring_jobs_owner_required`` grants
ownerless rows to exactly one instrument by name -- ``wpll``, the anonymous
pre-launch teaser -- so no other job type can acquire a row that no user owns
and therefore no user can be denied.  ``ck_scoring_jobs_status`` fixes the
vocabulary the reaper keys off; a typo'd status would make a job invisible to it
and poll forever.

**Two partial indexes, not one over ``created_at``.**  The pending sweep reads
``WHERE status IN ('queued','running')`` and the purge reads ``WHERE status IN
('succeeded','failed')``.  Those select disjoint halves of the table, so a
single index over ``created_at`` would make each scan the other's rows -- and in
steady state the terminal half is almost all of them.

``user_id`` cascades from ``users``: a deleted account's scoring jobs hold its
answers and its result blobs, and nothing should outlive the account.  The
``wpll`` rows have no account to cascade from, which is what
``solverah.scoring.purge_jobs`` exists for.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260901_scoring_jobs"
down_revision = "20260827_phase3_outbox"
branch_labels = None
depends_on = None

#: Same function every other table's `updated_at` trigger calls, restated as
#: CREATE OR REPLACE for the reason the outbox migration gives: depending on a
#: function an earlier migration happened to leave behind breaks the moment that
#: migration is squashed or its downgrade is run.
_SET_UPDATED_AT = """
CREATE OR REPLACE FUNCTION solverah_set_updated_at() RETURNS trigger AS $BODY$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$BODY$ LANGUAGE plpgsql;
"""


def upgrade():
    op.create_table(
        "scoring_jobs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuidv7()"),
        ),
        # Nullable, for `wpll` alone -- see ck_scoring_jobs_owner_required.
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text()),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text()),
        sa.Column(
            "attempts", sa.SmallInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_scoring_jobs"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_scoring_jobs_user",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_scoring_jobs_status",
        ),
        sa.CheckConstraint(
            "job_type IN ('assessment_scoring', 'path_suggestions')",
            name="ck_scoring_jobs_type",
        ),
        sa.CheckConstraint(
            "(job_type = 'assessment_scoring' AND kind IS NOT NULL) OR "
            "(job_type = 'path_suggestions' AND kind IS NULL)",
            name="ck_scoring_jobs_kind_matches_type",
        ),
        sa.CheckConstraint(
            "user_id IS NOT NULL OR "
            "(job_type = 'assessment_scoring' AND kind = 'wpll')",
            name="ck_scoring_jobs_owner_required",
        ),
    )
    op.create_index(
        "uq_scoring_jobs_public_id", "scoring_jobs", ["public_id"], unique=True
    )
    op.create_index(
        "ix_scoring_jobs_user",
        "scoring_jobs",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_scoring_jobs_pending",
        "scoring_jobs",
        ["created_at"],
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_index(
        "ix_scoring_jobs_terminal",
        "scoring_jobs",
        ["created_at"],
        postgresql_where=sa.text("status IN ('succeeded', 'failed')"),
    )

    op.execute(_SET_UPDATED_AT)
    op.execute("DROP TRIGGER IF EXISTS trg_scoring_jobs_updated_at ON scoring_jobs")
    op.execute(
        "CREATE TRIGGER trg_scoring_jobs_updated_at "
        "BEFORE UPDATE ON scoring_jobs "
        "FOR EACH ROW EXECUTE FUNCTION solverah_set_updated_at()"
    )


def downgrade():
    # The trigger and the indexes go with the table; the shared
    # `solverah_set_updated_at` function does not, because six other tables
    # still fire it.
    op.execute("DROP TRIGGER IF EXISTS trg_scoring_jobs_updated_at ON scoring_jobs")
    op.drop_table("scoring_jobs")
