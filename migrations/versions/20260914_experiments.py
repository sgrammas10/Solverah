"""add experiments (BUILD_PLAN B-5)

Condition experiments: a user runs a named two-week change against one of
`work_pulse.situation_content.GUIDANCE_CELLS`'s twelve `change_in_place` cells, and
the readout reads back Pulse `experienced` check-ins from before and after. See
`model.py`'s "Condition experiments" section for the full design rationale (one
active experiment per user enforced by a partial unique index, `ends_at` stored
rather than computed, no free text anywhere on the row).

Revision ID: 20260914_experiments
Revises: 20260911_pulse_checkins
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa

revision = "20260914_experiments"
down_revision = "20260911_pulse_checkins"
branch_labels = None
depends_on = None

EXPERIMENT_DIMENSIONS = ("autonomy", "pace", "collaboration", "feedback", "innovation", "decision")
EXPERIMENT_DIRECTIONS = ("under", "over")
EXPERIMENT_STATUSES = ("active", "abandoned")


def upgrade():
    op.create_table(
        "experiments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("dimension", sa.Text(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("register", sa.Text(), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("abandoned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_experiment_user"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "dimension IN %s" % (EXPERIMENT_DIMENSIONS,), name="ck_experiment_dimension_vocab"
        ),
        sa.CheckConstraint(
            "direction IN %s" % (EXPERIMENT_DIRECTIONS,), name="ck_experiment_direction_vocab"
        ),
        # A single-element SQL tuple, not `IN %s` over a one-item Python tuple --
        # `str(("change_in_place",))` carries a trailing comma that is invalid
        # `IN (...)` syntax in Postgres.
        sa.CheckConstraint("register = 'change_in_place'", name="ck_experiment_register_vocab"),
        sa.CheckConstraint(
            "status IN %s" % (EXPERIMENT_STATUSES,), name="ck_experiment_status_vocab"
        ),
        sa.CheckConstraint(
            "(status = 'abandoned') = (abandoned_at IS NOT NULL)",
            name="ck_experiment_abandoned_at_matches_status",
        ),
    )
    op.create_index(
        "ix_experiments_user_created",
        "experiments",
        ["user_id", sa.text("created_at DESC")],
    )
    # The methodological rule (docs/BUILD_PLAN.md §4.5): a two-week change is
    # confounded by a second concurrent one, so at most one experiment may be
    # active per user. Partial so a user with several abandoned experiments in
    # their history is unconstrained by them.
    op.create_index(
        "uq_experiments_one_active_per_user",
        "experiments",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade():
    op.drop_index("uq_experiments_one_active_per_user", "experiments")
    op.drop_index("ix_experiments_user_created", "experiments")
    op.drop_table("experiments")
