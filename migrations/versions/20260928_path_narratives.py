"""add path_narratives -- the narrator's sentences, stored by input fingerprint (BUILD_PLAN W-16)

One row per (user, occupation, fingerprint): the `why_text` and tags the path
narrator wrote for one card, filed under a digest of exactly what the prompt fed
the model about that card and that person. See `model.py`'s "Path Intelligence:
the narrator's sentences, stored" section for the full design rationale (why a
table, why the fingerprint rather than an invalidation list is the correctness,
why a new fingerprint is a new row rather than an overwrite).

WHY THE UNIQUE KEY IS THREE COLUMNS AND PLAIN, NOT `NULLS NOT DISTINCT`
----------------------------------------------------------------------
`(user_id, onet_code, fingerprint)` is the identity of one sentence: the same
card for the same person under the same narrator inputs. It is also the upsert
target two concurrent narrations of one user converge on. All three columns are
NOT NULL, so 20260906_scorer_run's question does not arise -- the same answer
20260916_path_fits and 20260921_path_wants give.

WHY `ON DELETE CASCADE` WHEN ACCOUNT DELETION DELETES EXPLICITLY
----------------------------------------------------------------
Account deletion tombstones the user row, so the cascade never fires on that
path and `account_repository.delete_personal_rows` removes these rows by hand,
like `path_fits`. The cascade is for a HARD delete of a user row (a support
purge, a test teardown), where a narrative outliving its person would be the
exact retention D-7b forbids.

REVERSIBILITY
-------------
Unconditionally reversible, on 20260916_path_fits' terms: every row is derived
data, recomputable by the narrator from the profile, so `downgrade` drops the
table outright. What a rollback costs is one narrator run per user's next load.

Revision ID: 20260928_path_narratives
Revises: 20260921_path_wants
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260928_path_narratives"
down_revision = "20260921_path_wants"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "path_narratives",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        # No foreign key on this one: occupations live in the corpus artifact
        # (a .npy in S3), not in this database.
        sa.Column("onet_code", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("why_text", sa.Text(), nullable=False),
        sa.Column(
            "profile_dimensions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_pathnarrative_user", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "onet_code",
            "fingerprint",
            name="uq_path_narratives_user_code_fp",
        ),
    )


def downgrade():
    op.drop_table("path_narratives")
