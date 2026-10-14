"""Tests for pulse_store.py + the pulse_checkins / pulse_events tables (BUILD_PLAN B-1).

B-2 (the API + cadence engine) does not exist yet, so these tests exercise storage on
its own contract: a caller hands write_pulse_checkin the sequence it served and the
answers it got back, and storage validates the shape against
`work_pulse.pulse_items` before persisting it, append-only. Same structure as
`tests/test_environment_report_store.py`.
"""

import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from work_pulse.pulse_items import dimensions_for_checkin

UTC = datetime.timezone.utc


def _item_scores_for(user_id, sequence, value=3):
    return {dim: value for dim in dimensions_for_checkin(user_id, sequence)}


def _write_checkin(db, user_id=1, sequence=0, **overrides):
    from pulse_store import write_pulse_checkin

    kwargs = dict(
        item_scores=_item_scores_for(user_id, sequence),
        experienced=4,
        version="pulse-v1-test",
    )
    kwargs.update(overrides)
    return write_pulse_checkin(db, user_id, sequence=sequence, **kwargs)


def _write_event(db, user_id=1, **overrides):
    from pulse_store import write_pulse_event

    kwargs = dict(event_type="new_manager", note=None)
    kwargs.update(overrides)
    return write_pulse_event(db, user_id, **kwargs)


# ---------------------------------------------------------------------------
# write_pulse_checkin: happy path + append-only semantics
# ---------------------------------------------------------------------------


def test_write_checkin_then_read_round_trips(client, seed_user):
    from app import app
    from pulse_store import latest_pulse_checkin
    from model import db

    seed_user(1)
    with app.app_context():
        scores = _item_scores_for(1, 0, value=2)
        checkin_id = _write_checkin(db, user_id=1, sequence=0, item_scores=scores, experienced=5)
        db.session.commit()

        result = latest_pulse_checkin(1)
        assert result["id"] == checkin_id
        assert result["user_id"] == 1
        assert result["sequence"] == 0
        assert result["item_scores"] == scores
        assert result["experienced"] == 5
        assert result["version"] == "pulse-v1-test"
        assert result["taken_at"] is not None


def test_second_checkin_is_a_second_row_not_an_update(client, seed_user):
    from app import app
    from pulse_store import pulse_checkin_count, pulse_checkin_history
    from model import PulseCheckin, db

    seed_user(1)
    with app.app_context():
        first_id = _write_checkin(db, user_id=1, sequence=0)
        db.session.commit()
        second_id = _write_checkin(db, user_id=1, sequence=1)
        db.session.commit()

        assert first_id != second_id
        assert PulseCheckin.query.filter_by(user_id=1).count() == 2
        assert pulse_checkin_count(1) == 2

        history = pulse_checkin_history(1)
        assert [h["id"] for h in history] == [second_id, first_id]  # newest first


def test_latest_pulse_checkin_is_none_when_user_has_no_checkins(client, seed_user):
    from app import app
    from pulse_store import latest_pulse_checkin

    seed_user(1)
    with app.app_context():
        assert latest_pulse_checkin(1) is None


def test_pulse_checkin_history_is_empty_list_not_none(client, seed_user):
    from app import app
    from pulse_store import pulse_checkin_history

    seed_user(1)
    with app.app_context():
        assert pulse_checkin_history(1) == []


def test_pulse_checkin_count_is_zero_for_a_new_user(client, seed_user):
    from app import app
    from pulse_store import pulse_checkin_count

    seed_user(1)
    with app.app_context():
        assert pulse_checkin_count(1) == 0


def test_history_and_count_are_scoped_per_user(client, seed_user):
    from app import app
    from model import db
    from pulse_store import pulse_checkin_count, pulse_checkin_history

    seed_user(1, 2)
    with app.app_context():
        _write_checkin(db, user_id=1, sequence=0)
        db.session.commit()

        assert pulse_checkin_count(2) == 0
        assert pulse_checkin_history(2) == []
        assert pulse_checkin_count(1) == 1


def test_sequence_advances_by_completed_checkins_not_by_elapsed_time(client, seed_user):
    """`work_pulse.pulse_items.dimensions_for_checkin`'s docstring: `sequence` counts
    completed check-ins, never a calendar gap. A checkin dated years in the past still
    counts as exactly one completed check-in -- `pulse_checkin_count` has no notion of
    "stale" or "how long ago", only "how many rows"."""
    from app import app
    from model import PulseCheckin, db
    from pulse_store import pulse_checkin_count

    seed_user(1)
    with app.app_context():
        _write_checkin(db, user_id=1, sequence=0)
        db.session.commit()

        old_row = PulseCheckin.query.filter_by(user_id=1).one()
        old_row.taken_at = datetime.datetime(2020, 1, 1, tzinfo=UTC)
        db.session.commit()

        # A long-elapsed gap changes nothing about what sequence comes next.
        assert pulse_checkin_count(1) == 1


# ---------------------------------------------------------------------------
# write_pulse_checkin: validation
# ---------------------------------------------------------------------------


def test_write_rejects_item_scores_for_the_wrong_sequence(client, seed_user):
    from app import app
    from model import db

    seed_user(1)
    with app.app_context():
        wrong_scores = _item_scores_for(1, sequence=1)  # built for sequence 1
        with pytest.raises(ValueError, match="missing|extra"):
            _write_checkin(db, user_id=1, sequence=0, item_scores=wrong_scores)


def test_write_rejects_a_partial_item_scores_set(client, seed_user):
    from app import app
    from model import db

    seed_user(1)
    with app.app_context():
        full = _item_scores_for(1, sequence=0)
        partial = dict(list(full.items())[:-1])
        with pytest.raises(ValueError, match="missing"):
            _write_checkin(db, user_id=1, sequence=0, item_scores=partial)


def test_write_rejects_an_extra_dimension_not_served_this_sequence(client, seed_user):
    from app import app
    from model import db
    from work_pulse.pulse_items import DIMENSIONS

    seed_user(1)
    with app.app_context():
        served = dimensions_for_checkin(1, sequence=0)
        unserved = [d for d in DIMENSIONS if d not in served][0]
        extra = dict(_item_scores_for(1, sequence=0), **{unserved: 3})
        with pytest.raises(ValueError, match="extra"):
            _write_checkin(db, user_id=1, sequence=0, item_scores=extra)


@pytest.mark.parametrize("bad_value", [0, 6, -1, 3.5, "3"])
def test_write_rejects_an_out_of_range_item_score(client, seed_user, bad_value):
    from app import app
    from model import db

    seed_user(1)
    with app.app_context():
        scores = _item_scores_for(1, sequence=0)
        dim = next(iter(scores))
        scores[dim] = bad_value
        with pytest.raises(ValueError, match="valid 1..5 score"):
            _write_checkin(db, user_id=1, sequence=0, item_scores=scores)


@pytest.mark.parametrize("bad_value", [0, 6, -1])
def test_write_rejects_an_out_of_range_experienced_score(client, seed_user, bad_value):
    from app import app
    from model import db

    seed_user(1)
    with app.app_context():
        with pytest.raises(ValueError, match="experienced"):
            _write_checkin(db, user_id=1, sequence=0, experienced=bad_value)


def test_write_rejects_a_negative_sequence(client, seed_user):
    from app import app
    from model import db
    from pulse_store import write_pulse_checkin

    seed_user(1)
    with app.app_context():
        with pytest.raises(ValueError, match="sequence"):
            write_pulse_checkin(
                db, 1, sequence=-1, item_scores={}, experienced=3, version="v1"
            )


# ---------------------------------------------------------------------------
# write_pulse_event: happy path + validation
# ---------------------------------------------------------------------------


def test_write_event_then_read_round_trips(client, seed_user):
    from app import app
    from pulse_store import pulse_events_in_range
    from model import db

    seed_user(1)
    with app.app_context():
        event_id = _write_event(db, user_id=1, event_type="reorg", note="new team structure")
        db.session.commit()

        events = pulse_events_in_range(1)
        assert len(events) == 1
        assert events[0]["id"] == event_id
        assert events[0]["event_type"] == "reorg"
        assert events[0]["note"] == "new team structure"
        assert events[0]["at"] is not None


def test_write_event_accepts_none_note(client, seed_user):
    from app import app
    from pulse_store import pulse_events_in_range
    from model import db

    seed_user(1)
    with app.app_context():
        _write_event(db, user_id=1, event_type="role_change", note=None)
        db.session.commit()

        assert pulse_events_in_range(1)[0]["note"] is None


def test_write_event_rejects_an_unknown_type(client, seed_user):
    from app import app
    from model import db

    seed_user(1)
    with app.app_context():
        with pytest.raises(ValueError, match="event_type"):
            _write_event(db, user_id=1, event_type="promotion")


def test_write_event_rejects_a_note_over_the_length_cap(client, seed_user):
    from app import app
    from model import db
    from model import PULSE_EVENT_NOTE_MAX_LENGTH

    seed_user(1)
    with app.app_context():
        with pytest.raises(ValueError, match="cap"):
            _write_event(db, user_id=1, note="x" * (PULSE_EVENT_NOTE_MAX_LENGTH + 1))


def test_events_are_append_only(client, seed_user):
    from app import app
    from model import PulseEvent, db

    seed_user(1)
    with app.app_context():
        _write_event(db, user_id=1, event_type="new_manager")
        db.session.commit()
        _write_event(db, user_id=1, event_type="remote_change")
        db.session.commit()

        assert PulseEvent.query.filter_by(user_id=1).count() == 2


def test_pulse_events_in_range_is_empty_list_not_none(client, seed_user):
    from app import app
    from pulse_store import pulse_events_in_range

    seed_user(1)
    with app.app_context():
        assert pulse_events_in_range(1) == []


def test_pulse_events_in_range_windows_by_date(client, seed_user):
    from app import app
    from model import PulseEvent, db
    from pulse_store import pulse_events_in_range

    seed_user(1)
    with app.app_context():
        old_id = _write_event(db, user_id=1, event_type="new_manager")
        db.session.commit()
        PulseEvent.query.filter_by(id=old_id).one().at = datetime.datetime(2020, 1, 1, tzinfo=UTC)
        db.session.commit()

        recent_id = _write_event(db, user_id=1, event_type="reorg")
        db.session.commit()

        windowed = pulse_events_in_range(
            1, since=datetime.datetime(2025, 1, 1, tzinfo=UTC)
        )
        assert [e["id"] for e in windowed] == [recent_id]

        unbounded = pulse_events_in_range(1)
        assert {e["id"] for e in unbounded} == {old_id, recent_id}


def test_events_are_scoped_per_user(client, seed_user):
    from app import app
    from model import db
    from pulse_store import pulse_events_in_range

    seed_user(1, 2)
    with app.app_context():
        _write_event(db, user_id=1, event_type="new_manager")
        db.session.commit()

        assert pulse_events_in_range(2) == []
        assert len(pulse_events_in_range(1)) == 1


# ---------------------------------------------------------------------------
# Model-level constraints (CHECK constraints hold even if a caller bypasses
# pulse_store and writes the ORM rows directly)
# ---------------------------------------------------------------------------


def test_checkin_sequence_negative_is_rejected(client, seed_user):
    from app import app
    from model import PulseCheckin, db

    seed_user(1)
    with app.app_context():
        db.session.add(
            PulseCheckin(
                user_id=1, sequence=-1, item_scores={}, experienced=3, version="v1"
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()


@pytest.mark.parametrize("bad_experienced", [0, 6])
def test_checkin_experienced_out_of_range_is_rejected(client, seed_user, bad_experienced):
    from app import app
    from model import PulseCheckin, db

    seed_user(1)
    with app.app_context():
        db.session.add(
            PulseCheckin(
                user_id=1, sequence=0, item_scores={}, experienced=bad_experienced,
                version="v1",
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_checkin_requires_a_real_user(client):
    from app import app
    from model import PulseCheckin, db

    with app.app_context():
        db.session.add(
            PulseCheckin(
                user_id=999999, sequence=0, item_scores={}, experienced=3, version="v1"
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_event_type_outside_vocabulary_is_rejected_at_the_model_level(client, seed_user):
    from app import app
    from model import PulseEvent, db

    seed_user(1)
    with app.app_context():
        db.session.add(PulseEvent(user_id=1, event_type="promotion"))
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_a_valid_row_of_every_event_type_is_accepted(client, seed_user):
    """Sibling VALID-row test (S-40 lesson): proves the vocabulary CHECK isn't
    rejecting every insert, only the ones outside it."""
    from app import app
    from model import PULSE_EVENT_TYPES, PulseEvent, db

    seed_user(1)
    with app.app_context():
        for event_type in PULSE_EVENT_TYPES:
            db.session.add(PulseEvent(user_id=1, event_type=event_type))
        db.session.commit()
        assert PulseEvent.query.filter_by(user_id=1).count() == len(PULSE_EVENT_TYPES)


def test_event_note_over_length_cap_is_rejected_at_the_model_level(client, seed_user):
    from app import app
    from model import PULSE_EVENT_NOTE_MAX_LENGTH, PulseEvent, db

    seed_user(1)
    with app.app_context():
        db.session.add(
            PulseEvent(
                user_id=1,
                event_type="other",
                note="x" * (PULSE_EVENT_NOTE_MAX_LENGTH + 1),
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_event_note_at_the_length_cap_is_accepted(client, seed_user):
    """Sibling VALID-row test for the boundary itself."""
    from app import app
    from model import PULSE_EVENT_NOTE_MAX_LENGTH, PulseEvent, db

    seed_user(1)
    with app.app_context():
        db.session.add(
            PulseEvent(
                user_id=1, event_type="other", note="x" * PULSE_EVENT_NOTE_MAX_LENGTH
            )
        )
        db.session.commit()
        assert len(PulseEvent.query.filter_by(user_id=1).one().note) == PULSE_EVENT_NOTE_MAX_LENGTH


def test_event_requires_a_real_user(client):
    from app import app
    from model import PulseEvent, db

    with app.app_context():
        db.session.add(PulseEvent(user_id=999999, event_type="other"))
        with pytest.raises(IntegrityError):
            db.session.commit()


# ---------------------------------------------------------------------------
# company_link_id (six-trait build, C8): attach the user's ACTIVE
# `UserCompanyLink` at write time; detach cleanly (SET NULL) when it is deleted.
# ---------------------------------------------------------------------------


def _mk_company(db, name="Acme", slug="acme"):
    from model import Company

    company = Company(name=name, slug=slug, profile_json={})
    db.session.add(company)
    db.session.commit()
    return company


def _mk_link(db, user_id, company_id, *, started_on, ended_on=None):
    from model import UserCompanyLink

    link = UserCompanyLink(
        user_id=user_id, company_id=company_id, started_on=started_on, ended_on=ended_on
    )
    db.session.add(link)
    db.session.commit()
    return link


def test_checkin_with_no_link_gets_null_company_link_id(client, seed_user):
    from app import app
    from pulse_store import latest_pulse_checkin
    from model import db

    seed_user(1)
    with app.app_context():
        _write_checkin(db, user_id=1, sequence=0)
        db.session.commit()

        result = latest_pulse_checkin(1)
        assert result["company_link_id"] is None


def test_checkin_attaches_the_active_link(client, seed_user):
    from app import app
    from pulse_store import latest_pulse_checkin
    from model import db

    seed_user(1)
    with app.app_context():
        company = _mk_company(db)
        today = datetime.date.today()
        link = _mk_link(db, 1, company.id, started_on=today - datetime.timedelta(days=30))

        _write_checkin(db, user_id=1, sequence=0)
        db.session.commit()

        result = latest_pulse_checkin(1)
        assert result["company_link_id"] == link.id


def test_checkin_does_not_attach_an_ended_link(client, seed_user):
    from app import app
    from pulse_store import latest_pulse_checkin
    from model import db

    seed_user(1)
    with app.app_context():
        company = _mk_company(db)
        today = datetime.date.today()
        _mk_link(
            db, 1, company.id,
            started_on=today - datetime.timedelta(days=60),
            ended_on=today - datetime.timedelta(days=1),
        )

        _write_checkin(db, user_id=1, sequence=0)
        db.session.commit()

        result = latest_pulse_checkin(1)
        assert result["company_link_id"] is None


def test_checkin_does_not_attach_a_future_dated_link(client, seed_user):
    from app import app
    from pulse_store import latest_pulse_checkin
    from model import db

    seed_user(1)
    with app.app_context():
        company = _mk_company(db)
        today = datetime.date.today()
        _mk_link(db, 1, company.id, started_on=today + datetime.timedelta(days=5))

        _write_checkin(db, user_id=1, sequence=0)
        db.session.commit()

        result = latest_pulse_checkin(1)
        assert result["company_link_id"] is None


def test_deleting_the_link_nulls_the_checkin_but_keeps_it(client, seed_user):
    from app import app
    from pulse_store import latest_pulse_checkin
    import company_evidence_store
    from model import db

    seed_user(1)
    with app.app_context():
        company = _mk_company(db)
        today = datetime.date.today()
        link = _mk_link(db, 1, company.id, started_on=today - datetime.timedelta(days=10))

        checkin_id = _write_checkin(db, user_id=1, sequence=0)
        db.session.commit()

        before = latest_pulse_checkin(1)
        assert before["company_link_id"] == link.id

        assert company_evidence_store.delete_company_link(db, 1, link.id) is True

        after = latest_pulse_checkin(1)
        assert after["id"] == checkin_id
        assert after["company_link_id"] is None


def test_checkin_stops_attaching_a_link_once_the_user_ends_it(client, seed_user):
    import company_evidence_store
    from app import app
    from pulse_store import latest_pulse_checkin
    from model import db

    seed_user(1)
    with app.app_context():
        company = _mk_company(db)
        today = datetime.date.today()
        link = _mk_link(db, 1, company.id, started_on=today - datetime.timedelta(days=60))

        _write_checkin(db, user_id=1, sequence=0)
        db.session.commit()
        assert latest_pulse_checkin(1)["company_link_id"] == link.id

        company_evidence_store.end_company_link(
            db, 1, link.id, ended_on=today - datetime.timedelta(days=1))

        _write_checkin(db, user_id=1, sequence=1)
        db.session.commit()
        assert latest_pulse_checkin(1)["company_link_id"] is None
