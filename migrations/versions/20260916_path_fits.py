"""add path_fits -- stored Tier-2 deep fits per (user, occupation) (BUILD_PLAN F-5)

Storage for `backend/services/path_deep_fit.deep_fit`. See `model.py`'s "Path
Intelligence Tier 2" section for the full design rationale (why the row is mutable
rather than append-only, why the payload is one JSONB column rather than decomposed,
why there are two staleness mechanisms and a TTL on top of them). Summarized:

- one row per (user, occupation), enforced by `uq_path_fits_user_occupation`, which
  is also the key every read and every upsert goes through -- there is no second
  access pattern, so it is the only index this table needs;
- `payload` is `DeepFit.to_dict()` stored whole;
- `profile_fingerprint` is a digest of the scorer inputs, so a row that outlived a
  profile change is detectable even if a write site forgot to call `invalidate`.

WHY THE UNIQUE CONSTRAINT IS PLAIN, NOT `NULLS NOT DISTINCT`
-----------------------------------------------------------
Both key columns are NOT NULL, so the 20260906_scorer_run question does not arise
here: there are no NULLs for Postgres to treat as distinct, and a plain UNIQUE is
the whole guarantee rather than most of it.

REVERSIBILITY
-------------
Unconditionally reversible. The table is derived data with no other reader, and
every row it holds is recomputable from the profile plus four cached O*NET calls,
so `downgrade` drops it outright rather than checking for anything first -- unlike
20260906_scorer_run's downgrade, which refuses when the rows it would delete are
not reconstructible.

Revision ID: 20260916_path_fits
Revises: 20260914_experiments
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260916_path_fits"
down_revision = "20260914_experiments"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "path_fits",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        # No foreign key on this one: occupations live in the corpus artifact
        # (a .npy in S3), not in this database.
        sa.Column("onet_code", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("profile_fingerprint", sa.Text(), nullable=False),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_pathfit_user"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "onet_code", name="uq_path_fits_user_occupation"
        ),
    )


def downgrade():
    op.drop_table("path_fits")
