"""add pulse_checkins + pulse_events (BUILD_PLAN B-1)

Storage for the Pulse check-in instrument. See `model.py`'s "The Pulse" section for
the full design rationale (round-robin `item_scores` rather than all five dimensions
every row, `sequence` persisted rather than re-derived, D-7 export/delete inclusion
landing in this same chunk rather than being left for the D-7 catch-up chunk).
Summarized:

- `pulse_checkins` is one row per completed check-in, never updated. `item_scores` is
  JSONB holding exactly the `pulse_items.ITEMS_PER_CHECKIN` dimensions that check-in's
  round-robin sequence served -- not a fixed key set, so no CHECK can enforce its shape
  beyond "valid JSON"; `pulse_store.write_pulse_checkin` is where that validation lives.
- `pulse_events` is one row per logged event (manager change, reorg, remote change,
  role change, or an unlisted "other"), with an optional length-capped note.

Both append-only (D-16 tradition, matching `environment_reports`).

Revision ID: 20260911_pulse_checkins
Revises: 20260910_situation_report_pins
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260911_pulse_checkins"
down_revision = "20260910_situation_report_pins"
branch_labels = None
depends_on = None

PULSE_EVENT_TYPES = ("new_manager", "reorg", "remote_change", "role_change", "other")
PULSE_EVENT_NOTE_MAX_LENGTH = 280


def upgrade():
    op.create_table(
        "pulse_checkins",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "taken_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("item_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("experienced", sa.SmallInteger(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_pulsecheckin_user"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("sequence >= 0", name="ck_pulsecheckin_sequence_nonneg"),
        sa.CheckConstraint(
            "experienced >= 1 AND experienced <= 5",
            name="ck_pulsecheckin_experienced_range",
        ),
    )
    op.create_index(
        "ix_pulse_checkins_user_taken",
        "pulse_checkins",
        ["user_id", sa.text("taken_at DESC")],
    )

    op.create_table(
        "pulse_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_pulseevent_user"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "event_type IN %s" % (PULSE_EVENT_TYPES,), name="ck_pulseevent_type_vocab"
        ),
        sa.CheckConstraint(
            "note IS NULL OR char_length(note) <= %d" % PULSE_EVENT_NOTE_MAX_LENGTH,
            name="ck_pulseevent_note_length",
        ),
    )
    op.create_index(
        "ix_pulse_events_user_at",
        "pulse_events",
        ["user_id", sa.text("at DESC")],
    )


def downgrade():
    op.drop_index("ix_pulse_events_user_at", "pulse_events")
    op.drop_table("pulse_events")

    op.drop_index("ix_pulse_checkins_user_taken", "pulse_checkins")
    op.drop_table("pulse_checkins")
