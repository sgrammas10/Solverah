"""Phase 3: the transactional outbox and the resume parse-job table.

Two tables, both additive.  No existing column changes type, name or meaning, no
data is moved, and no endpoint's response shape depends on either -- so this
migration is reversible by dropping what it created, which is why ``downgrade``
here is three lines where Phase 2's were three hundred.

**`outbox` is Part 4.7's table, column for column.**  It is what makes "the email
send failed so the request 500'd" go away: the row is inserted into the
transaction that performs the business write, so an account and the verification
email it is owed become one commit, and a worker delivers afterwards.

It is deliberately **not partitioned**, unlike the three tables the previous
migration rebuilt.  Those are append-only histories where the retention mechanism
is dropping a month.  This is a queue: rows are written, published within seconds,
and swept once delivered, so its steady-state size is the backlog rather than the
history.  Partitioning it would also force `created_at` into the primary key --
Postgres requires the partition key to be part of every unique constraint -- and
the publisher's `WHERE id = :id ... FOR UPDATE` would become a scan across every
partition to find one row.

**The index is partial, and that is the whole performance story.**  The drain
query is `WHERE published_at IS NULL ORDER BY created_at`.  With
`ix_outbox_unpublished` covering only unpublished rows, its cost tracks the
backlog -- normally zero to a handful of rows -- rather than everything the table
has ever held.  A published row leaves the index entirely.

**`resume_parse_jobs` is not in Part 4.**  It is the durable half of Phase 3's
`202 + job handle` for resume parsing, and it is a table rather than Celery's
result backend for two reasons.  The result backend is Redis, so
`GET /me/resume-parse-jobs/{id}` would answer 404 for every job in flight the
moment Redis restarted -- for work that had actually succeeded.  And a result
backend is a transport detail with a TTL, not a record of what a user asked the
product to do; the object key, the attempt count and the failure reason are all
things support needs after that TTL would have expired.

`status` is constrained rather than left as free text.  Four states, two of them
terminal, and the sweep that fails stalled jobs keys off exactly this vocabulary
-- a typo'd status would make a job invisible to it and poll forever.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260827_phase3_outbox"
down_revision = "20260827_partition"
branch_labels = None
depends_on = None

#: Same function the Phase 2a migration installs, restated as CREATE OR REPLACE.
#:
#: Restated rather than assumed present: `resume_parse_jobs` needs the trigger,
#: and a migration that depends on a function some *earlier* migration happened
#: to leave behind breaks the moment that earlier one is squashed or its
#: downgrade is run. CREATE OR REPLACE with an identical body is idempotent and
#: costs nothing.
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
        "outbox",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column(
            "attempts", sa.SmallInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.PrimaryKeyConstraint("id", name="pk_outbox"),
    )
    op.create_index(
        "ix_outbox_unpublished",
        "outbox",
        ["created_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )

    op.create_table(
        "resume_parse_jobs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("resume_name", sa.Text()),
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
        sa.PrimaryKeyConstraint("id", name="pk_resume_parse_jobs"),
        # ON DELETE CASCADE: a deleted account's parse jobs carry its object keys
        # and are of no use to anyone. `retention_cleanup.py` sweeps the objects
        # themselves; this stops the rows outliving the account that owned them.
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_resume_parse_jobs_user",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_resume_parse_jobs_status",
        ),
    )
    op.create_index(
        "uq_resume_parse_jobs_public_id", "resume_parse_jobs", ["public_id"], unique=True
    )
    op.create_index(
        "ix_resume_parse_jobs_user",
        "resume_parse_jobs",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_resume_parse_jobs_pending",
        "resume_parse_jobs",
        ["created_at"],
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    op.execute(_SET_UPDATED_AT)
    op.execute(
        "DROP TRIGGER IF EXISTS trg_resume_parse_jobs_updated_at ON resume_parse_jobs"
    )
    op.execute(
        "CREATE TRIGGER trg_resume_parse_jobs_updated_at "
        "BEFORE UPDATE ON resume_parse_jobs "
        "FOR EACH ROW EXECUTE FUNCTION solverah_set_updated_at()"
    )


def downgrade():
    # The trigger and its indexes go with the tables; the shared
    # `solverah_set_updated_at` function does not, because five other tables
    # still fire it.
    op.execute(
        "DROP TRIGGER IF EXISTS trg_resume_parse_jobs_updated_at ON resume_parse_jobs"
    )
    op.drop_table("resume_parse_jobs")
    op.drop_table("outbox")
