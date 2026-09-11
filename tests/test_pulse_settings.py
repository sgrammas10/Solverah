"""Tests for pulse_settings.py -- cadence/anti-nag state on the profile document
(BUILD_PLAN B-2).

No table of its own (D-7's cross-cutting rule -- see the module docstring), so
these tests go through `profile_repository` the same way `test_profile_decomposition.py`
proves `extra` round-trips: write with the module's own functions, read back with
`read_settings`, and separately assert `profiles.version` to prove the no-op fast
path in `mark_answered` really is a no-op and not just a no-visible-change write.
"""

import datetime

import pytest

UTC = datetime.timezone.utc


def _profile_version(user_id):
    from model import Profile

    row = Profile.query.filter_by(user_id=user_id).first()
    return row.version if row is not None else None


# ---------------------------------------------------------------------------
# read_settings: defaults
# ---------------------------------------------------------------------------


def test_read_settings_defaults_for_a_user_who_never_touched_pulse(client, seed_user):
    from app import app
    from solverah.services import pulse_settings

    seed_user(1)
    with app.app_context():
        settings = pulse_settings.read_settings(1)

    assert settings == {
        "cadence": "weekly",
        "last_prompted_at": None,
        "awaiting_response": False,
        "consecutive_unanswered": 0,
    }


# ---------------------------------------------------------------------------
# set_cadence
# ---------------------------------------------------------------------------


def test_set_cadence_persists_and_rejects_unknown_values(client, seed_user):
    from app import app
    from model import db
    from solverah.services import pulse_settings

    seed_user(1)
    with app.app_context():
        updated = pulse_settings.set_cadence(1, "biweekly")
        db.session.commit()
        assert updated["cadence"] == "biweekly"
        assert pulse_settings.read_settings(1)["cadence"] == "biweekly"

        with pytest.raises(ValueError):
            pulse_settings.set_cadence(1, "monthly")
        with pytest.raises(ValueError):
            pulse_settings.set_cadence(1, "daily")


def test_set_cadence_clears_anti_nag_state_but_leaves_last_prompted_at(client, seed_user):
    """An explicit choice is a clean slate for the counters, per the module's
    docstring -- but `last_prompted_at` states a fact that switching cadence
    does not change, so clearing it too would make the next cadence run treat
    this user as never-prompted and email them again immediately."""
    from app import app
    from model import db
    from solverah.services import pulse_settings

    seed_user(1)
    with app.app_context():
        prompted_at = datetime.datetime(2026, 1, 1, tzinfo=UTC)
        pulse_settings.record_prompt(
            1, cadence="weekly", consecutive_unanswered=2, prompted_at=prompted_at
        )
        db.session.commit()

        updated = pulse_settings.set_cadence(1, "biweekly")
        db.session.commit()

    assert updated["awaiting_response"] is False
    assert updated["consecutive_unanswered"] == 0
    assert updated["cadence"] == "biweekly"
    assert updated["last_prompted_at"] == prompted_at.isoformat()


# ---------------------------------------------------------------------------
# mark_answered
# ---------------------------------------------------------------------------


def test_mark_answered_is_a_true_no_op_when_nothing_is_outstanding(client, seed_user):
    from app import app
    from solverah.services import pulse_settings

    seed_user(1)
    with app.app_context():
        version_before = _profile_version(1)  # None: no profiles row yet
        pulse_settings.mark_answered(1)
        version_after = _profile_version(1)

    assert version_before is None
    assert version_after is None, "mark_answered wrote a profiles row it had no reason to"


def test_mark_answered_flips_awaiting_response_off(client, seed_user):
    from app import app
    from model import db
    from solverah.services import pulse_settings

    seed_user(1)
    with app.app_context():
        pulse_settings.record_prompt(
            1, cadence="weekly", consecutive_unanswered=1, prompted_at=datetime.datetime.now(UTC)
        )
        db.session.commit()
        assert pulse_settings.read_settings(1)["awaiting_response"] is True

        pulse_settings.mark_answered(1)
        db.session.commit()

        settings = pulse_settings.read_settings(1)

    assert settings["awaiting_response"] is False
    # consecutive_unanswered is untouched here -- only the cadence engine's
    # record_prompt is meant to move it, per the module docstring.
    assert settings["consecutive_unanswered"] == 1


# ---------------------------------------------------------------------------
# record_prompt
# ---------------------------------------------------------------------------


def test_record_prompt_sets_every_field(client, seed_user):
    from app import app
    from model import db
    from solverah.services import pulse_settings

    seed_user(1)
    now = datetime.datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    with app.app_context():
        pulse_settings.record_prompt(1, cadence="monthly", consecutive_unanswered=0, prompted_at=now)
        db.session.commit()
        settings = pulse_settings.read_settings(1)

    assert settings == {
        "cadence": "monthly",
        "last_prompted_at": now.isoformat(),
        "awaiting_response": True,
        "consecutive_unanswered": 0,
    }


# ---------------------------------------------------------------------------
# is_due
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cadence,days_since_prompt,expected",
    [
        ("weekly", None, True),      # never prompted -> due immediately
        ("weekly", 3, False),
        ("weekly", 8, True),
        ("biweekly", 10, False),
        ("biweekly", 15, True),
        ("monthly", 20, False),
        ("monthly", 31, True),
        ("off", None, False),        # off is never due, even unprompted
        ("off", 100, False),
    ],
)
def test_is_due(cadence, days_since_prompt, expected):
    from solverah.services import pulse_settings

    now = datetime.datetime(2026, 6, 1, tzinfo=UTC)
    last_prompted_at = (
        None if days_since_prompt is None else (now - datetime.timedelta(days=days_since_prompt)).isoformat()
    )
    settings = {
        "cadence": cadence,
        "last_prompted_at": last_prompted_at,
        "awaiting_response": False,
        "consecutive_unanswered": 0,
    }

    assert pulse_settings.is_due(settings, now=now) is expected
