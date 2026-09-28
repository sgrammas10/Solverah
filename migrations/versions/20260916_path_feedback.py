"""add path_feedback -- inline card judgements for the `adjacent` path (BUILD_PLAN F-6)

One row per (user, occupation) judgement. `backend/services/path_scoring` rebuilds
the retrieval query from these rows on every request rather than storing the
rotated query itself -- see `model.py`'s "Path Intelligence: inline card feedback"
section for the four reasons that is the design and not an optimisation left
undone.

WHY THERE IS NO `verdict` ENUM TYPE
-----------------------------------
`verdict` is `text` with the vocabulary enforced in
`solverah/repositories/path_feedback_repository.VERDICTS` and again in the API
schema. A Postgres enum would make adding a fourth verdict a migration, and the
verdict set is a product question that is still moving (F-7 shares this machinery
with a different seed). `experiments.status` made the same call for the same
reason. No CHECK constraint either, for the same reason and one more: a CHECK
would turn a client sending an unknown verdict into an `IntegrityError` at commit
time instead of the `400 invalid_verdict` the route answers before it writes.

WHY THE UNIQUE CONSTRAINT IS PLAIN, NOT `NULLS NOT DISTINCT`
-----------------------------------------------------------
Both key columns are NOT NULL, so 20260906_scorer_run's question does not arise:
there are no NULLs for Postgres to treat as distinct. Same answer, same reason, as
20260916_path_fits directly below this one in the chain.

REVERSIBILITY
-------------
Unconditionally reversible, but NOT for `path_fits`' reason. A deep fit is
recomputable from the profile; a judgement is not recomputable from anything --
it is something a person said. `downgrade` still drops the table outright,
because the alternative (refusing, the way 20260906_scorer_run's downgrade does)
would mean a rollback of this deploy could not proceed at all, and the data a
rollback would destroy is a handful of taps a user can redo in seconds. That is a
deliberate trade and not an oversight: if this table ever grows something a user
could not trivially re-enter, revisit the downgrade before adding the column.

Revision ID: 20260916_path_fb
Revises: 20260916_path_fits
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa

revision = "20260916_path_fb"
down_revision = "20260916_path_fits"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "path_feedback",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        # No foreign key on this one: occupations live in the corpus artifact
        # (a .npy in S3), not in this database.
        sa.Column("onet_code", sa.Text(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_pathfeedback_user"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "onet_code", name="uq_path_feedback_user_occupation"
        ),
    )


def downgrade():
    op.drop_table("path_feedback")
