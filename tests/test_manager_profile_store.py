"""Tests for manager_profile_store.py + the manager_profiles table (BUILD_PLAN C-3).

Storage's own contract, independent of the scoring layer: a caller hands
write_manager_profile raw answers (opaque JSONB, authored-identity by convention) and a
complete dimension_scores dict plus scoring_key/version, and storage persists it,
unmodified, append-only. Mirrors tests/test_environment_report_store.py.
"""

import pytest
from sqlalchemy.exc import IntegrityError

DIMENSION_SCORES = {
    "autonomy": 0.525,
    "feedback_style": 0.525,
    "relationship": 0.80,
    "growth_focus": 0.25,
}

ANSWERS = [{"question_id": "mp-q%d" % i, "choice": "a"} for i in range(1, 17)]


def _write(db, user_id=1, **overrides):
    from manager_profile_store import write_manager_profile

    kwargs = dict(
        answers=ANSWERS,
        dimension_scores=DIMENSION_SCORES,
        scoring_key="mp-v1",
        version="v1",
    )
    kwargs.update(overrides)
    return write_manager_profile(db, user_id, **kwargs)


# ---------------------------------------------------------------------------
# Happy path + append-only semantics
# ---------------------------------------------------------------------------


def test_write_then_read_round_trips(client, seed_user):
    from app import app
    from manager_profile_store import latest_manager_profile
    from model import db

    seed_user(1)
    with app.app_context():
        row_id = _write(db, user_id=1)
        db.session.commit()

        result = latest_manager_profile(1)
        assert result["id"] == row_id
        assert result["user_id"] == 1
        assert result["answers"] == ANSWERS
        assert result["dimension_scores"] == DIMENSION_SCORES
        assert result["scoring_key"] == "mp-v1"
        assert result["version"] == "v1"
        assert result["created_at"] is not None


def test_second_submission_is_a_second_row_not_an_update(client, seed_user):
    """The append-only precedent (D-16): a retake never overwrites the first sitting."""
    from app import app
    from manager_profile_store import latest_manager_profile
    from model import ManagerProfile, db

    seed_user(1)
    with app.app_context():
        first_id = _write(db, user_id=1, scoring_key="mp-v0")
        db.session.commit()

        second_scores = {k: 0.9 for k in DIMENSION_SCORES}
        second_id = _write(db, user_id=1, dimension_scores=second_scores)
        db.session.commit()

        assert first_id != second_id
        assert ManagerProfile.query.filter_by(user_id=1).count() == 2

        first_row = db.session.get(ManagerProfile, first_id)
        assert first_row.scoring_key == "mp-v0"  # untouched by the second write

        latest = latest_manager_profile(1)
        assert latest["id"] == second_id
        assert latest["dimension_scores"] == second_scores


def test_latest_manager_profile_is_none_when_user_has_no_sittings(client, seed_user):
    from app import app
    from manager_profile_store import latest_manager_profile

    seed_user(1)
    with app.app_context():
        assert latest_manager_profile(1) is None


def test_reads_are_scoped_per_user(client, seed_user):
    from app import app
    from manager_profile_store import latest_manager_profile
    from model import db

    seed_user(1, 2)
    with app.app_context():
        _write(db, user_id=1)
        db.session.commit()

        assert latest_manager_profile(2) is None


# ---------------------------------------------------------------------------
# Model-level constraints
# ---------------------------------------------------------------------------


def test_manager_profile_requires_a_real_user(client):
    """fk_managerprofile_user: an orphan user_id is rejected."""
    from app import app
    from model import ManagerProfile, db

    with app.app_context():
        db.session.add(
            ManagerProfile(
                user_id=999999,
                answers=ANSWERS,
                dimension_scores=DIMENSION_SCORES,
                scoring_key="mp-v1",
                version="v1",
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()


@pytest.mark.parametrize("missing_column", ["scoring_key", "version"])
def test_required_text_columns_reject_null(client, seed_user, missing_column):
    """`scoring_key` and `version` are Text NOT NULL: a Python `None` becomes a SQL NULL
    and the constraint fires. `answers`/`dimension_scores` are JSONB, where a Python
    `None` serializes to the JSON `null` literal rather than a SQL NULL -- the same
    behaviour `EnvironmentReport.raw_answers` has, and why that table's own tests do not
    assert null-rejection on its JSONB column either."""
    from app import app
    from model import ManagerProfile, db

    seed_user(1)
    with app.app_context():
        kwargs = dict(
            user_id=1,
            answers=ANSWERS,
            dimension_scores=DIMENSION_SCORES,
            scoring_key="mp-v1",
            version="v1",
        )
        kwargs[missing_column] = None
        db.session.add(ManagerProfile(**kwargs))
        with pytest.raises(IntegrityError):
            db.session.commit()
