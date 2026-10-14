"""Tests for `20261002_experiment_completed` -- the migration behind the
'completed' experiment status -- run against the real test database.

The schema the fixtures build (`db.create_all()`) is already the post-upgrade
one, so `upgrade` is proven by `flask db upgrade` on a lane database (see the
2026-10-02 fix-wave report) and what this file pins is the DOWNGRADE GUARD,
which no other test covers. schema-steward's review (2026-10-02) found the
first guard only caught "completed beside active" and let "two completed rows,
no active row" -- the shape of every user who has run two experiments -- reach
the relabel UPDATE, which then died on `uq_experiments_one_active_per_user`
with a bare IntegrityError instead of the explained refusal.

The migration module is loaded by path and its `op` bound to the test session's
connection through alembic's own `Operations`, so `downgrade()` runs its real
SQL. Postgres DDL is transactional, so the happy-path test rolls the whole
thing back and the fixture's schema is untouched for the next test.
"""
from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations" / "versions" / "20261002_experiment_completed.py"
)
UTC = datetime.timezone.utc


def _load_migration(connection):
    spec = importlib.util.spec_from_file_location("_h_experiment_completed", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    context = MigrationContext.configure(connection)
    module.op = Operations(context)
    return module


def _row(db, user_id, *, status, ended_days_ago=20, dimension="autonomy"):
    from model import Experiment

    ends_at = datetime.datetime.now(UTC) - datetime.timedelta(days=ended_days_ago)
    row = Experiment(
        user_id=user_id, dimension=dimension, direction="under", register="change_in_place",
        started_at=ends_at - datetime.timedelta(days=14), ends_at=ends_at, status=status,
        abandoned_at=ends_at if status == "abandoned" else None,
    )
    db.session.add(row)
    db.session.flush()
    return row.id


def _statuses(db, user_id):
    from model import Experiment

    return sorted(
        status for (status,) in db.session.query(Experiment.status).filter_by(user_id=user_id)
    )


def test_downgrade_refuses_two_completed_rows_for_one_user(client, seed_user):
    """The gap schema-steward found: no active row at all, just two finished
    experiments -- relabelling both 'active' would collide on the index."""
    from app import app
    from model import db

    seed_user(1)
    with app.app_context():
        _row(db, 1, status="completed", ended_days_ago=40)
        _row(db, 1, status="completed", ended_days_ago=20, dimension="pace")
        module = _load_migration(db.session.connection())

        with pytest.raises(RuntimeError, match="more than one active-or-completed"):
            module.downgrade()

        # Nothing relabelled, nothing dropped: the refusal came before any write.
        assert _statuses(db, 1) == ["completed", "completed"]
        db.session.rollback()


def test_downgrade_refuses_a_completed_row_beside_an_active_one(client, seed_user):
    from app import app
    from model import db

    seed_user(1)
    with app.app_context():
        _row(db, 1, status="completed", ended_days_ago=20)
        _row(db, 1, status="active", ended_days_ago=-10, dimension="pace")
        module = _load_migration(db.session.connection())

        with pytest.raises(RuntimeError, match="1 user\\(s\\)"):
            module.downgrade()
        db.session.rollback()


def test_downgrade_relabels_one_completed_row_per_user_and_narrows_the_check(client, seed_user):
    """The shape the old schema CAN hold: at most one active-or-completed row
    per user. Abandoned rows never count against the limit."""
    from app import app
    from model import db

    seed_user(1, 2, 3)
    with app.app_context():
        _row(db, 1, status="completed")
        _row(db, 1, status="abandoned", dimension="pace")
        _row(db, 2, status="active", ended_days_ago=-10)
        _row(db, 3, status="abandoned")
        _row(db, 3, status="abandoned", dimension="pace")
        module = _load_migration(db.session.connection())

        module.downgrade()

        assert _statuses(db, 1) == ["abandoned", "active"]
        assert _statuses(db, 2) == ["active"]
        assert _statuses(db, 3) == ["abandoned", "abandoned"]
        check = db.session.execute(
            sa.text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_experiment_status_vocab'"
            )
        ).scalar()
        assert "completed" not in check
        # Transactional DDL: roll it all back so the fixture's schema survives.
        db.session.rollback()


def test_upgrade_backfills_only_ended_active_rows(client, seed_user):
    """Run against the already-upgraded schema (the CHECK drop/recreate is a
    no-op round trip there); what this pins is the backfill predicate."""
    from app import app
    from model import db

    seed_user(1, 2, 3)
    with app.app_context():
        _row(db, 1, status="active", ended_days_ago=1)     # ended -> completed
        _row(db, 2, status="active", ended_days_ago=-10)   # running -> untouched
        _row(db, 3, status="abandoned", ended_days_ago=1)  # untouched
        module = _load_migration(db.session.connection())

        module.upgrade()

        assert _statuses(db, 1) == ["completed"]
        assert _statuses(db, 2) == ["active"]
        assert _statuses(db, 3) == ["abandoned"]
        db.session.rollback()
