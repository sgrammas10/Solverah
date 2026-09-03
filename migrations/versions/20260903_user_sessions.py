"""S3: the refresh-token table.

One table, additive.  No existing column changes type, name or meaning, no data
is moved, and no existing row is touched -- so ``downgrade`` is a drop, as it
was for the outbox and scoring-job migrations this follows.

Part 4.2 declared ``user_sessions`` and nothing built it, which is
``docs/audits/SECURITY_AUDIT_2026-09.md`` finding 1.1 (HIGH): logout cleared a
cookie and revoked nothing, so a captured access token stayed valid for the rest
of its hour.  This is the table that makes revocation possible.

**Four shapes differ from the SQL in ARCHITECTURE.md Part 4.2, and each is a
decision rather than a drift.**

``revoked_at`` becomes ``retired_at`` + ``retired_reason``.  A token dies four
ways -- rotated, logged out, detected as reused, expired -- and a single
timestamp cannot tell an incident review which happened.  The reason is a fixed
vocabulary held by ``ck_user_sessions_retired_reason``, not free text: a typo'd
reason is a row that answers nothing and a query that silently misses it.
``ck_user_sessions_retirement_complete`` refuses a time without a reason or a
reason without a time, because a death with no cause is an audit row that cannot
do its job.

``family_id``, ``parent_id`` and ``successor_id`` are new.  Rotation on use and
reuse detection are the whole point of A7 and neither is expressible without
them: the family is what a leak revokes, and the parent/successor links are the
chain an audit reads.  ``family_id`` defaults to ``uuidv7()`` so a new sign-in
opens a family without the application having to mint one, and rotation carries
the value forward explicitly.

``user_agent`` and ``ip`` are **not** built, though Part 4.2 draws them.  They
are per-request identifying data and the feature that would read them -- a
device list, "sign out everywhere else" -- does not exist.  The same audit that
raised 1.1 raised #18 and #7 against exactly this shape: identifying columns
retained past any reader.  They arrive with the screen that shows them.

``public_id`` is not built either.  Part 4.1's rule exists so an integer id does
not have to leave the database, and no id from this table leaves it at all: the
client's handle on a session is the token, which is a secret, and the family id
travels only inside a signed JWT claim.  A second surrogate key with no reader
is a column to maintain and a uniqueness index to pay for.

**The two self-referencing foreign keys are ``ON DELETE SET NULL``**, not
CASCADE.  A cascade would make deleting one retired row take its whole chain
with it, so the retention pass -- which deletes by age, oldest first -- would
silently remove live sessions along with their expired ancestors.  SET NULL
loses a link and keeps every row that is still somebody's session.

**Two partial indexes rather than one.**  The retention pass reads two disjoint
halves: live rows by ``expires_at``, dead rows by ``retired_at``.  A single
index over either column alone would make each scan the other's rows, and in
steady state the dead half is almost all of them.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260903_user_sessions"
down_revision = "20260901_scoring_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column(
            "family_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        # Hex SHA-256 of the opaque token; see domain/auth.hash_refresh_token
        # for why the digest is SHA-256 and not bcrypt. The raw value is never
        # written here or anywhere else.
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("parent_id", sa.BigInteger()),
        sa.Column("successor_id", sa.BigInteger()),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("retired_reason", sa.Text()),
        sa.PrimaryKeyConstraint("id", name="pk_user_sessions"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_sessions_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["user_sessions.id"],
            name="fk_user_sessions_parent",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["successor_id"],
            ["user_sessions.id"],
            name="fk_user_sessions_successor",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "(retired_at IS NULL AND retired_reason IS NULL) OR "
            "(retired_at IS NOT NULL AND retired_reason IS NOT NULL)",
            name="ck_user_sessions_retirement_complete",
        ),
        sa.CheckConstraint(
            "retired_reason IS NULL OR retired_reason IN "
            "('rotated', 'logged_out', 'reused', 'expired')",
            name="ck_user_sessions_retired_reason",
        ),
    )
    # Unique because it is the lookup key: a presented token hashes to exactly
    # one row or to none, and the index is what makes that one equality probe
    # rather than a scan of every session in the table.
    op.create_index(
        "uq_user_sessions_token_hash", "user_sessions", ["token_hash"], unique=True
    )
    # Reuse detection revokes on the family, so this index is on the path of the
    # security event itself.
    op.create_index("ix_user_sessions_family", "user_sessions", ["family_id"])
    op.create_index(
        "ix_user_sessions_user_issued",
        "user_sessions",
        ["user_id", sa.text("issued_at DESC")],
    )
    op.create_index(
        "ix_user_sessions_live",
        "user_sessions",
        ["expires_at"],
        postgresql_where=sa.text("retired_at IS NULL"),
    )
    op.create_index(
        "ix_user_sessions_retired",
        "user_sessions",
        ["retired_at"],
        postgresql_where=sa.text("retired_at IS NOT NULL"),
    )


def downgrade():
    # The indexes and both check constraints go with the table. Nothing else
    # references it -- no other table carries a `session_id` -- so there is
    # nothing to detach first, and no shared function to leave behind (this
    # table has no `updated_at` and therefore no trigger).
    #
    # What a downgrade costs, stated because it is not nothing: every live
    # refresh session is destroyed, so every signed-in user is asked to log in
    # again once their access token expires. Nothing is lost but the sessions
    # themselves.
    op.drop_table("user_sessions")
