"""pulse_store.py -- persistence for the Pulse check-in instrument (BUILD_PLAN B-1).

No Flask, no cadence logic, no email. A caller (B-2, not built yet) hands
`write_pulse_checkin` the round-robin sequence it served and the answers it got back;
this module validates the shape against `work_pulse.pulse_items` and persists it,
unmodified. Deliberately shaped like `environment_report_store.py`: write paths do not
commit (the caller owns the transaction), and reads return plain dicts rather than ORM
rows, so a consumer cannot navigate back into the session through the return value.

APPEND-ONLY (D-16 tradition), same reasoning as `environment_reports`: every call to
`write_pulse_checkin` / `write_pulse_event` inserts a new row, never updates one.
History is the point -- it is what B-3's trend view and E-4's training data both read.

D-7 (BUILD_PLAN, 2026-09-10 cross-cutting rule): `pulse_checkins` and `pulse_events`
join `/me/export` and the account-deletion flow the same commit that creates them.
`solverah/services/account_service.py` and `solverah/repositories/account_repository.py`
call `pulse_checkin_history`/`pulse_events_in_range` and delete both tables' rows
directly -- see those modules for the wiring; nothing about D-7 lives in this file.
"""

from __future__ import annotations

from typing import Any, Optional

from work_pulse.pulse_items import dimensions_for_checkin, is_valid_score
from model import PULSE_EVENT_NOTE_MAX_LENGTH, PULSE_EVENT_TYPES

__all__ = [
    "write_pulse_checkin",
    "write_pulse_event",
    "latest_pulse_checkin",
    "pulse_checkin_history",
    "pulse_checkin_count",
    "pulse_events_in_range",
]


def _require_served_item_scores(
    user_id: int, sequence: int, item_scores: dict[str, int]
) -> None:
    """Refuse an `item_scores` dict that doesn't match what this exact
    (user, sequence) pair was served.

    Mirrors `environment_report_store._require_all_dimensions`'s reasoning: a caller
    that submitted the wrong dimensions -- a stale form, a sequence off by one --
    should fail loudly here rather than write a row `pulse_checkin_history` would
    later read back as if it were a real answer to a different question.
    """
    expected = set(dimensions_for_checkin(user_id, sequence))
    got = set(item_scores)
    if got != expected:
        missing = expected - got
        extra = got - expected
        raise ValueError(
            "item_scores for user %r sequence %r must cover exactly %r. "
            "missing=%r extra=%r" % (user_id, sequence, sorted(expected), sorted(missing), sorted(extra))
        )
    for dim, score in item_scores.items():
        if not is_valid_score(score):
            raise ValueError(
                "item_scores[%r] = %r is not a valid 1..5 score" % (dim, score)
            )


def write_pulse_checkin(
    db,
    user_id: int,
    *,
    sequence: int,
    item_scores: dict[str, int],
    experienced: int,
    version: str,
) -> int:
    """Write one check-in. Does NOT commit -- the caller owns the transaction
    boundary, same as `assessment_store.persist_submission` and
    `write_environment_report`.

    `item_scores` must name exactly the `ITEMS_PER_CHECKIN` dimensions
    `work_pulse.pulse_items.dimensions_for_checkin(user_id, sequence)` selected --
    enforced here, not left to `pulse_checkins`' JSONB column, which cannot check a
    key set. Returns the new `pulse_checkins.id`.
    """
    from model import PulseCheckin

    _require_served_item_scores(user_id, sequence, item_scores)
    if not is_valid_score(experienced):
        raise ValueError("experienced = %r is not a valid 1..5 score" % (experienced,))

    row = PulseCheckin(
        user_id=user_id,
        sequence=sequence,
        item_scores=dict(item_scores),
        experienced=experienced,
        version=version,
    )
    db.session.add(row)
    db.session.flush()  # populates row.id for a caller that needs it before commit
    return row.id


def write_pulse_event(
    db,
    user_id: int,
    *,
    event_type: str,
    note: Optional[str] = None,
) -> int:
    """Write one event. Does NOT commit -- same transaction convention as
    `write_pulse_checkin`. Returns the new `pulse_events.id`.

    Validated here as well as by the table's own CHECK constraints
    (`model.PulseEvent`), so a caller gets a clear `ValueError` instead of an opaque
    `IntegrityError` for the common mistakes -- an unlisted `event_type`, a `note`
    over `PULSE_EVENT_NOTE_MAX_LENGTH`.
    """
    from model import PulseEvent

    if event_type not in PULSE_EVENT_TYPES:
        raise ValueError(
            "event_type %r is not one of %r" % (event_type, PULSE_EVENT_TYPES)
        )
    if note is not None and len(note) > PULSE_EVENT_NOTE_MAX_LENGTH:
        raise ValueError(
            "note is %d characters, over the %d-character cap"
            % (len(note), PULSE_EVENT_NOTE_MAX_LENGTH)
        )

    row = PulseEvent(user_id=user_id, event_type=event_type, note=note)
    db.session.add(row)
    db.session.flush()
    return row.id


def _serialize_checkin(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "taken_at": row.taken_at.isoformat() if row.taken_at else None,
        "sequence": row.sequence,
        "item_scores": dict(row.item_scores),
        "experienced": row.experienced,
        "version": row.version,
    }


def _serialize_event(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "at": row.at.isoformat() if row.at else None,
        "event_type": row.event_type,
        "note": row.note,
    }


def latest_pulse_checkin(user_id: int) -> Optional[dict[str, Any]]:
    """This user's most recent check-in, or None if they have never completed one.

    Ordered by `taken_at` (with `id` as the tiebreak), matching
    `ix_pulse_checkins_user_taken`'s column order so this is an index-only scan
    rather than a sort -- `environment_report_store.latest_environment_report`'s
    precedent.
    """
    from model import PulseCheckin

    row = (
        PulseCheckin.query.filter_by(user_id=user_id)
        .order_by(PulseCheckin.taken_at.desc(), PulseCheckin.id.desc())
        .first()
    )
    return _serialize_checkin(row) if row is not None else None


def pulse_checkin_count(user_id: int) -> int:
    """How many check-ins this user has completed.

    THE sanctioned way a caller (B-2) turns "how many has this user done" into the
    `sequence` to serve next: the next check-in is always `pulse_checkin_count(user_id)`,
    because `dimensions_for_checkin`'s `sequence` counts completed check-ins, zero-based
    (`work_pulse.pulse_items.dimensions_for_checkin`'s docstring).
    """
    from model import PulseCheckin

    return PulseCheckin.query.filter_by(user_id=user_id).count()


def pulse_checkin_history(
    user_id: int,
    *,
    since=None,
    until=None,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """This user's check-ins, newest first, optionally windowed by `taken_at`.

    `since`/`until` are inclusive bounds (datetimes) for B-3's trend view, which needs
    "the last N weeks" rather than every check-in a long-tenured user has ever done.
    `limit` is opt-in and unbounded by default -- same reasoning as
    `environment_report_store.environment_report_history`'s `limit`: a history read is
    a different question from "what applies right now", and truncating it silently
    would read an account's real, short history as if it were missing data.
    """
    from model import PulseCheckin

    query = PulseCheckin.query.filter_by(user_id=user_id)
    if since is not None:
        query = query.filter(PulseCheckin.taken_at >= since)
    if until is not None:
        query = query.filter(PulseCheckin.taken_at <= until)
    query = query.order_by(PulseCheckin.taken_at.desc(), PulseCheckin.id.desc())
    if limit is not None:
        query = query.limit(limit)

    return [_serialize_checkin(row) for row in query.all()]


def pulse_events_in_range(
    user_id: int,
    *,
    since=None,
    until=None,
) -> list[dict[str, Any]]:
    """This user's logged events, newest first, optionally windowed by `at`.

    Unbounded by default, same reasoning as `pulse_checkin_history`. B-4's wiring reads
    this to decide when an environment-report resubmission should be prompted, and
    account export (D-7) reads it with no bounds to return every event a user has ever
    logged.
    """
    from model import PulseEvent

    query = PulseEvent.query.filter_by(user_id=user_id)
    if since is not None:
        query = query.filter(PulseEvent.at >= since)
    if until is not None:
        query = query.filter(PulseEvent.at <= until)
    query = query.order_by(PulseEvent.at.desc(), PulseEvent.id.desc())

    return [_serialize_event(row) for row in query.all()]
