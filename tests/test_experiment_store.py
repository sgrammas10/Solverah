"""Tests for experiment_store.py + the experiments table (BUILD_PLAN B-5).

Same structure as `tests/test_environment_report_store.py`/`test_pulse_store.py`:
storage on its own contract, no service-layer cell validation (that lives in
`solverah/services/experiment_service.py`).
"""
from __future__ import annotations

import datetime

import pytest
from sqlalchemy.exc import IntegrityError

UTC = datetime.timezone.utc


def _start(db, user_id=1, **overrides):
    from experiment_store import start_experiment

    kwargs = dict(dimension="autonomy", direction="under")
    kwargs.update(overrides)
    return start_experiment(db, user_id, **kwargs)


# ---------------------------------------------------------------------------
# start_experiment / active_experiment
# ---------------------------------------------------------------------------


def test_start_then_read_round_trips(client, seed_user):
    from app import app
    from model import db

    seed_user(1)
    with app.app_context():
        row = _start(db, user_id=1, dimension="pace", direction="over")
        db.session.commit()

        assert row["user_id"] == 1
        assert row["dimension"] == "pace"
        assert row["direction"] == "over"
        assert row["register"] == "change_in_place"
        assert row["status"] == "active"
        assert row["abandoned_at"] is None
        assert row["started_at"] is not None
        assert row["ends_at"] is not None


def test_ends_at_is_started_at_plus_the_window(client, seed_user):
    from app import app
    from experiment_store import EXPERIMENT_WINDOW
    from model import db

    seed_user(1)
    with app.app_context():
        row = _start(db, user_id=1)
        db.session.commit()

        started = datetime.datetime.fromisoformat(row["started_at"])
        ends = datetime.datetime.fromisoformat(row["ends_at"])
        assert ends - started == EXPERIMENT_WINDOW


def test_active_experiment_is_none_until_one_is_started(client, seed_user):
    from app import app
    from experiment_store import active_experiment
    from model import db

    seed_user(1)
    with app.app_context():
        assert active_experiment(1) is None
        _start(db, user_id=1)
        db.session.commit()
        assert active_experiment(1)["dimension"] == "autonomy"


# ---------------------------------------------------------------------------
# The one-active-per-user constraint, at the database
# ---------------------------------------------------------------------------


def test_the_database_refuses_a_second_active_experiment_for_one_user(client, seed_user):
    """The partial unique index (`uq_experiments_one_active_per_user`) is the
    backstop a race between two service-layer checks would otherwise slip
    through -- proven here by going around the service layer entirely."""
    from app import app
    from model import Experiment, db

    seed_user(1)
    with app.app_context():
        db.session.add(Experiment(user_id=1, dimension="autonomy", direction="under",
                                   register="change_in_place",
                                   ends_at=datetime.datetime.now(UTC)))
        db.session.commit()

        db.session.add(Experiment(user_id=1, dimension="pace", direction="over",
                                   register="change_in_place",
                                   ends_at=datetime.datetime.now(UTC)))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_two_abandoned_experiments_for_one_user_do_not_collide(client, seed_user):
    """The index is partial (`WHERE status = 'active'`) -- a user's history of
    abandoned attempts is unconstrained by it."""
    from app import app
    from experiment_store import abandon_experiment
    from model import db

    seed_user(1)
    with app.app_context():
        first = _start(db, user_id=1, dimension="autonomy", direction="under")
        db.session.commit()
        abandon_experiment(db, 1, first["id"])
        db.session.commit()

        second = _start(db, user_id=1, dimension="pace", direction="over")
        db.session.commit()
        abandon_experiment(db, 1, second["id"])
        db.session.commit()  # no IntegrityError


# ---------------------------------------------------------------------------
# abandon_experiment: idempotency + cross-user isolation
# ---------------------------------------------------------------------------


def test_abandon_sets_status_and_abandoned_at(client, seed_user):
    from app import app
    from experiment_store import abandon_experiment
    from model import db

    seed_user(1)
    with app.app_context():
        row = _start(db, user_id=1)
        db.session.commit()

        abandoned = abandon_experiment(db, 1, row["id"])
        db.session.commit()

        assert abandoned["status"] == "abandoned"
        assert abandoned["abandoned_at"] is not None


def test_abandon_is_idempotent_and_keeps_the_original_timestamp(client, seed_user):
    from app import app
    from experiment_store import abandon_experiment
    from model import db

    seed_user(1)
    with app.app_context():
        row = _start(db, user_id=1)
        db.session.commit()

        first = abandon_experiment(db, 1, row["id"])
        db.session.commit()
        second = abandon_experiment(db, 1, row["id"])
        db.session.commit()

        assert second["status"] == "abandoned"
        assert second["abandoned_at"] == first["abandoned_at"]


def test_abandon_returns_none_for_someone_elses_experiment(client, seed_user):
    from app import app
    from experiment_store import abandon_experiment
    from model import db

    seed_user(1, 2)
    with app.app_context():
        row = _start(db, user_id=1)
        db.session.commit()

        assert abandon_experiment(db, 2, row["id"]) is None


def test_abandon_returns_none_for_a_nonexistent_id(client, seed_user):
    from app import app
    from experiment_store import abandon_experiment
    from model import db

    seed_user(1)
    with app.app_context():
        assert abandon_experiment(db, 1, 999999) is None


# ---------------------------------------------------------------------------
# experiment_for_user / experiments_for_user
# ---------------------------------------------------------------------------


def test_experiment_for_user_is_none_across_users(client, seed_user):
    from app import app
    from experiment_store import experiment_for_user
    from model import db

    seed_user(1, 2)
    with app.app_context():
        row = _start(db, user_id=1)
        db.session.commit()

        assert experiment_for_user(1, row["id"]) is not None
        assert experiment_for_user(2, row["id"]) is None


def test_experiments_for_user_lists_newest_first(client, seed_user):
    from app import app
    from experiment_store import abandon_experiment, experiments_for_user
    from model import db

    seed_user(1)
    with app.app_context():
        first = _start(db, user_id=1, dimension="autonomy", direction="under")
        db.session.commit()
        abandon_experiment(db, 1, first["id"])
        db.session.commit()

        second = _start(db, user_id=1, dimension="pace", direction="over")
        db.session.commit()

        history = experiments_for_user(1)
        assert [row["id"] for row in history] == [second["id"], first["id"]]


# ---------------------------------------------------------------------------
# checkin_experienced_values: the before/after windows
# ---------------------------------------------------------------------------


def _write_checkin_at(db, user_id, taken_at, experienced, sequence):
    from model import PulseCheckin
    from work_pulse.pulse_items import dimensions_for_checkin

    row = PulseCheckin(
        user_id=user_id,
        sequence=sequence,
        item_scores={dim: 3 for dim in dimensions_for_checkin(user_id, sequence)},
        experienced=experienced,
        version="pulse-v1-test",
        taken_at=taken_at,
    )
    db.session.add(row)
    db.session.flush()
    return row


def test_checkin_experienced_values_splits_on_started_at(client, seed_user):
    from app import app
    from experiment_store import checkin_experienced_values
    from model import db

    seed_user(1)
    started_at = datetime.datetime(2026, 9, 1, tzinfo=UTC)
    ends_at = started_at + datetime.timedelta(days=14)

    with app.app_context():
        # Two check-ins strictly before started_at.
        _write_checkin_at(db, 1, started_at - datetime.timedelta(days=10), 2, 0)
        _write_checkin_at(db, 1, started_at - datetime.timedelta(days=1), 3, 1)
        # One check-in exactly ON started_at -- belongs to "after", not "before".
        _write_checkin_at(db, 1, started_at, 4, 2)
        # One check-in inside the window, one after ends_at (excluded entirely).
        _write_checkin_at(db, 1, started_at + datetime.timedelta(days=7), 5, 3)
        _write_checkin_at(db, 1, ends_at + datetime.timedelta(days=1), 1, 4)
        db.session.commit()

        before, after = checkin_experienced_values(1, started_at=started_at, ends_at=ends_at)
        assert sorted(before) == [2, 3]
        assert sorted(after) == [4, 5]


def test_checkin_experienced_values_empty_when_no_checkins_exist(client, seed_user):
    from app import app
    from experiment_store import checkin_experienced_values
    from model import db

    seed_user(1)
    started_at = datetime.datetime(2026, 9, 1, tzinfo=UTC)
    ends_at = started_at + datetime.timedelta(days=14)

    with app.app_context():
        before, after = checkin_experienced_values(1, started_at=started_at, ends_at=ends_at)
        assert before == []
        assert after == []
