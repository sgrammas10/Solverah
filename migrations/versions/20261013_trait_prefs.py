"""person_trait_preference -- per-trait tolerance + must-have (six-trait match model)

PRODUCT_DECISIONS.md §2, "The six-trait match model" (Sebastian, 2026-10-13). Per
trait, the user states how much LESS (`under_steps`) and how much MORE (`over_steps`)
of the trait than their core preference a job may provide without cost, in
person-lattice steps of 0.25 (0, 1 or 2), plus a must-have flag (at most two per
sitting -- enforced by the service, since a CHECK cannot see sibling rows).

Append-only: a sitting is six rows sharing `sitting_id`, the latest sitting (highest
`id`) is current, earlier ones are kept. No row at all = UNANSWERED = today's
behaviour downstream.

Person-side and D-01-gated like the two core tables: read and written only through
`assessment_store`, and the `user_id` FK carries no `ondelete` for the same reason as
theirs (account deletion tombstones the user row).

The dimension vocabulary is spelled out here rather than imported: a migration must
keep meaning what it meant at its revision.

REVERSIBILITY
-------------
`downgrade` drops the table and with it every stated tolerance. Nothing else reads
it, so the pre-feature schema is fully restored; the answers themselves are lost.

Revision ID: 20261013_trait_prefs
Revises: 20261002_experiment_completed
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261013_trait_prefs"
down_revision = "20261002_experiment_completed"
branch_labels = None
depends_on = None

TABLE = "person_trait_preference"
DIMENSIONS = ("autonomy", "pace", "collaboration", "feedback", "innovation", "decision")


def upgrade():
    op.create_table(
        TABLE,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("sitting_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dimension_key", sa.String(length=32), nullable=False),
        sa.Column("under_steps", sa.SmallInteger(), nullable=False),
        sa.Column("over_steps", sa.SmallInteger(), nullable=False),
        sa.Column("must_have", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("form_version", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sitting_id", "dimension_key", name="uq_ptpref_sitting_dim"),
        sa.CheckConstraint(
            "dimension_key IN %s" % (DIMENSIONS,), name="ck_ptpref_dimension_vocab"
        ),
        sa.CheckConstraint(
            "under_steps >= 0 AND under_steps <= 2", name="ck_ptpref_under_steps_range"
        ),
        sa.CheckConstraint(
            "over_steps >= 0 AND over_steps <= 2", name="ck_ptpref_over_steps_range"
        ),
    )
    op.create_index(
        "ix_ptpref_user_latest", TABLE, ["user_id", sa.text("id DESC")], unique=False
    )


def downgrade():
    op.drop_index("ix_ptpref_user_latest", table_name=TABLE)
    op.drop_table(TABLE)
