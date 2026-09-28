"""add path_wants -- what should change about the user's own job (BUILD_PLAN W-4)

One row per answer the user has given on the "what should change" panel. See
`model.py`'s "Path Intelligence: what should change about the user's OWN job"
section for the full design rationale (why "fine" is the absence of a row, why
the rows are keyed to the anchor occupation and go inert rather than being
deleted on a job change, why `item_key` is a digest of the O*NET statement
rather than its position or its label).

WHY THE UNIQUE KEY IS FOUR COLUMNS AND PLAIN, NOT `NULLS NOT DISTINCT`
----------------------------------------------------------------------
`(user_id, anchor_onet_code, kind, item_key)` is the identity of one question
asked of one person about one job: `kind` is in the key because a task digest and
an axis name are drawn from different vocabularies and a collision between them
would be a silent overwrite, not a conflict anyone could see. All four are NOT
NULL, so 20260906_scorer_run's question does not arise -- there are no NULLs for
Postgres to treat as distinct, the same answer 20260916_path_fits and
20260916_path_feedback give.

WHY THERE IS NO `kind` OR `verdict` ENUM TYPE, AND NO CHECK
------------------------------------------------------------
20260916_path_feedback's two reasons, unchanged. The vocabulary is enforced in
`solverah/repositories/path_wants_repository` and again at the API boundary; a
Postgres enum would make a fifth condition axis a migration, and a CHECK would
turn a bad verdict into an `IntegrityError` at commit instead of the typed `422`
the route answers before it writes anything.

REVERSIBILITY
-------------
Unconditionally reversible, and on 20260916_path_feedback's terms rather than
20260916_path_fits'. These rows are not recomputable from anything -- they are
things a person said -- but a rollback of this deploy must be able to proceed,
and what it destroys is a panel the user can answer again in under a minute.
That is a deliberate trade: if this table ever grows something a user could not
re-enter (a free-text "why", say), revisit the downgrade before adding the
column.

Revision ID: 20260921_path_wants
Revises: 20260916_path_fb
Create Date: 2026-09-21
"""
from alembic import op
import sqlalchemy as sa

revision = "20260921_path_wants"
down_revision = "20260916_path_fb"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "path_wants",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        # No foreign key on this one: occupations live in the corpus artifact
        # (a .npy in S3), not in this database.
        sa.Column("anchor_onet_code", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("item_key", sa.Text(), nullable=False),
        sa.Column("item_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_pathwants_user"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "anchor_onet_code",
            "kind",
            "item_key",
            name="uq_path_wants_user_anchor_item",
        ),
    )


def downgrade():
    op.drop_table("path_wants")
