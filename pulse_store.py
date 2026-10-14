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
call `pulse_checkin_history`/`pulse_events_in_range` for export -- see those modules for
the wiring; nothing about D-7 lives in this file.

D-7b (2026-09-11 ruling): the two tables split on deletion. `pulse_checkins` holds no
free text -- `item_scores` and `experienced` are plain 1..5 integers -- so it rides the
tombstone de-identified, the same as `environment_reports`; `account_repository`
touches it nowhere in the deletion path at all. `pulse_events.note` IS free text, and
free text is never retained de-identified, so `account_repository.delete_personal_rows`
destroys every row for the deleting user.
"""

from __future__ import annotations

import datetime
from typing import Any, Optional, Sequence

import sqlalchemy as sa

from work_pulse.pulse_items import dimensions_for_checkin, is_valid_score
from model import PULSE_EVENT_NOTE_MAX_LENGTH, PULSE_EVENT_TYPES

__all__ = [
    "CHECKIN_SEQUENCE_LOCK",
    "claim_checkin_sequence",
    "write_pulse_checkin",
    "write_pulse_checkin_row",
    "write_pulse_event",
    "write_pulse_event_row",
    "latest_pulse_checkin",
    "pulse_checkin_history",
    "pulse_checkin_count",
    "pulse_events_in_range",
]

#: `pg_advisory_xact_lock`'s first key for `claim_checkin_sequence`: an arbitrary
#: constant ("PULS" in ASCII) that only has to stay stable and differ from any
#: other advisory-lock user's. The second key is the user id.
CHECKIN_SEQUENCE_LOCK = 0x50554C53


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


def _active_company_link_id(db, user_id: int) -> Optional[int]:
    """The id of the user's ACTIVE `UserCompanyLink`, or None when they have none.

    "Active" (six-trait build, C8, 2026-10-13; `model.PulseCheckin.company_link_id`'s
    docstring): `started_on <= today` and (`ended_on` is None or `ended_on >= today`).
    Read through `company_evidence_store.company_links_for_user`, a cross-lane read --
    this module never writes to `user_company_link`. That store function already
    orders newest-`started_on`-first, so the first row meeting both conditions is the
    one to attach. A user cannot hold two open links at all as of the orchestrator's
    2026-10-13 one-current-job ruling: `create_company_link` closes any prior open link
    before inserting a new one, and `ix_ucl_one_open_per_user` (a partial unique index
    on `user_id` where `ended_on IS NULL`) enforces it in the DB -- this still takes
    "first match" rather than assume it.
    """
    import company_evidence_store

    today = datetime.date.today()
    for link in company_evidence_store.company_links_for_user(db, user_id):
        if link.started_on <= today and (link.ended_on is None or link.ended_on >= today):
            return link.id
    return None


def _add_checkin(db, user_id: int, *, sequence, item_scores, experienced, version):
    """Validate and flush one check-in; returns the ORM row."""
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
        company_link_id=_active_company_link_id(db, user_id),
    )
    db.session.add(row)
    # Populates row.id for a caller that needs it before commit -- and, through the
    # INSERT's RETURNING, the server-default taken_at.
    db.session.flush()
    return row


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
    key set. Returns the new `pulse_checkins.id`; `write_pulse_checkin_row` returns
    the whole row.
    """
    return _add_checkin(
        db, user_id, sequence=sequence, item_scores=item_scores,
        experienced=experienced, version=version,
    ).id


def write_pulse_checkin_row(
    db,
    user_id: int,
    *,
    sequence: int,
    item_scores: dict[str, int],
    experienced: int,
    version: str,
) -> dict[str, Any]:
    """`write_pulse_checkin`, returning the new row as `pulse_checkin_history`
    serializes it rather than only its id.

    Serialized here, while the flushed row is still in hand, and that is the point:
    the INSERT's RETURNING has already brought back the server-default `taken_at`.
    Past this call the session holds the row only weakly, and after the caller's
    commit it is expired too -- either way, reading it again is a SELECT.
    """
    return _serialize_checkin(
        _add_checkin(
            db, user_id, sequence=sequence, item_scores=item_scores,
            experienced=experienced, version=version,
        )
    )


def _add_event(db, user_id: int, *, event_type, note):
    """Validate and flush one event; returns the ORM row."""
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
    return row


def write_pulse_event(
    db,
    user_id: int,
    *,
    event_type: str,
    note: Optional[str] = None,
) -> int:
    """Write one event. Does NOT commit -- same transaction convention as
    `write_pulse_checkin`. Returns the new `pulse_events.id`;
    `write_pulse_event_row` returns the whole row.

    Validated here as well as by the table's own CHECK constraints
    (`model.PulseEvent`), so a caller gets a clear `ValueError` instead of an opaque
    `IntegrityError` for the common mistakes -- an unlisted `event_type`, a `note`
    over `PULSE_EVENT_NOTE_MAX_LENGTH`.
    """
    return _add_event(db, user_id, event_type=event_type, note=note).id


def write_pulse_event_row(
    db,
    user_id: int,
    *,
    event_type: str,
    note: Optional[str] = None,
) -> dict[str, Any]:
    """`write_pulse_event`, returning the new row as `pulse_events_in_range`
    serializes it, server-default `at` included, for the reason
    `write_pulse_checkin_row` gives."""
    return _serialize_event(_add_event(db, user_id, event_type=event_type, note=note))


def _serialize_checkin(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "taken_at": row.taken_at.isoformat() if row.taken_at else None,
        "sequence": row.sequence,
        "item_scores": dict(row.item_scores),
        "experienced": row.experienced,
        "version": row.version,
        "company_link_id": row.company_link_id,
    }


def _serialize_event(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "at": row.at.isoformat() if row.at else None,
        "event_type": row.event_type,
        "note": row.note,
    }


def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def _unchanged(value):
    return value


#: The keys of each serializer above, and how a projected read formats the ones
#: that are not passed through as stored -- the serializers' own formatting, so a
#: projected read and a whole-row read agree on every key they share.
_CHECKIN_KEYS = (
    "id", "user_id", "taken_at", "sequence", "item_scores", "experienced", "version",
    "company_link_id",
)
_CHECKIN_FORMATS = {"taken_at": _iso, "item_scores": dict}
_EVENT_KEYS = ("id", "user_id", "at", "event_type", "note")
_EVENT_FORMATS = {"at": _iso}


def _selected(model, columns: Sequence[str], keys: Sequence[str]) -> list:
    """The mapped columns for *columns*, which must name one or more of *keys*."""
    columns = tuple(columns)
    if not columns or any(name not in keys for name in columns):
        raise ValueError("columns must name one or more of %r, got %r" % (keys, columns))
    return [getattr(model, name) for name in columns]


def _project(row, columns: Sequence[str], formats: dict) -> dict[str, Any]:
    return {name: formats.get(name, _unchanged)(value) for name, value in zip(columns, row)}


def _int4(value: int) -> int:
    """*value* folded into Postgres `integer` range (two's complement), for the
    two-key advisory lock. An id past 2**31 shares a key with the id 2**32 away:
    harmless -- those two users merely queue behind each other."""
    return (value + 2**31) % 2**32 - 2**31


def claim_checkin_sequence(db, user_id: int) -> int:
    """The `sequence` the check-in this transaction is about to write must use.

    `pulse_checkin_count` alone is count-then-insert: two submits for one user
    that both count before either commits take the same sequence, and nothing
    refuses the duplicate -- there is no unique `(user_id, sequence)`, and adding
    one could fail its migration on a duplicate already stored. This takes a
    transaction-scoped advisory lock on `(CHECKIN_SEQUENCE_LOCK, user_id)` first,
    so a second submit for the same user waits at the lock until the first
    commits or rolls back, and only then counts, the first one's row included.
    Other users never wait.

    Two statements, in this order, and not one: under READ COMMITTED a statement
    reads the snapshot taken when it started, so a count inside the very
    statement that waited for the lock would still miss the row the lock holder
    had just committed.

    The lock is held until the caller's commit or rollback -- the caller owns
    the transaction boundary, as with every write here.
    """
    db.session.execute(
        sa.select(
            sa.func.pg_advisory_xact_lock(
                sa.cast(CHECKIN_SEQUENCE_LOCK, sa.Integer), sa.cast(_int4(user_id), sa.Integer)
            )
        )
    )
    return pulse_checkin_count(user_id)


def latest_pulse_checkin(user_id: int) -> Optional[dict[str, Any]]:
    """This user's most recent check-in, or None if they have never completed one.

    Ordered by `taken_at` (with `id` as the tiebreak), matching
    `ix_pulse_checkins_user_taken`'s column order, so the index hands back the
    newest row first rather than the rows being sorted -- not an index-only scan,
    since the whole row is read from the table --
    `environment_report_store.latest_environment_report`'s precedent.
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
    (`work_pulse.pulse_items.dimensions_for_checkin`'s docstring). A caller about to
    WRITE that check-in counts through `claim_checkin_sequence` instead, which holds
    the count still until its transaction ends.
    """
    from model import PulseCheckin

    return PulseCheckin.query.filter_by(user_id=user_id).count()


def pulse_checkin_history(
    user_id: int,
    *,
    since=None,
    until=None,
    limit: Optional[int] = None,
    columns: Optional[Sequence[str]] = None,
) -> list[dict[str, Any]]:
    """This user's check-ins, newest first, optionally windowed by `taken_at`.

    `since`/`until` are inclusive bounds (datetimes) for B-3's trend view, which needs
    "the last N weeks" rather than every check-in a long-tenured user has ever done.
    `limit` is opt-in and unbounded by default -- same reasoning as
    `environment_report_store.environment_report_history`'s `limit`: a history read is
    a different question from "what applies right now", and truncating it silently
    would read an account's real, short history as if it were missing data.

    `columns` narrows the read to some of the whole row's keys (`ValueError` for a
    name the row does not have): only those columns are selected, and each comes
    back formatted as the whole row formats it. The condition-experiment readout
    reads one range this way -- `taken_at` and `experienced`, never `item_scores`.
    """
    from model import PulseCheckin, db

    conditions = [PulseCheckin.user_id == user_id]
    if since is not None:
        conditions.append(PulseCheckin.taken_at >= since)
    if until is not None:
        conditions.append(PulseCheckin.taken_at <= until)
    order = (PulseCheckin.taken_at.desc(), PulseCheckin.id.desc())

    if columns is None:
        query = PulseCheckin.query.filter(*conditions).order_by(*order)
        if limit is not None:
            query = query.limit(limit)
        return [_serialize_checkin(row) for row in query.all()]

    statement = (
        sa.select(*_selected(PulseCheckin, columns, _CHECKIN_KEYS))
        .where(*conditions)
        .order_by(*order)
    )
    if limit is not None:
        statement = statement.limit(limit)
    return [_project(row, columns, _CHECKIN_FORMATS) for row in db.session.execute(statement)]


def pulse_events_in_range(
    user_id: int,
    *,
    since=None,
    until=None,
    after=None,
    columns: Optional[Sequence[str]] = None,
) -> list[dict[str, Any]]:
    """This user's logged events, newest first, optionally windowed by `at`.

    Unbounded by default, same reasoning as `pulse_checkin_history`. B-4's wiring reads
    this to decide when an environment-report resubmission should be prompted, and
    account export (D-7) reads it with no bounds to return every event a user has ever
    logged.

    `since`/`until` are inclusive; `after` is an exclusive lower bound (`at > after`)
    for "strictly since" -- the Situation Report's events since its environment
    report -- so that boundary is drawn in SQL rather than by re-filtering an
    inclusive read. `columns` narrows the read as `pulse_checkin_history`'s does;
    that same caller never selects `note`, free text it must not ship.
    """
    from model import PulseEvent, db

    conditions = [PulseEvent.user_id == user_id]
    if since is not None:
        conditions.append(PulseEvent.at >= since)
    if after is not None:
        conditions.append(PulseEvent.at > after)
    if until is not None:
        conditions.append(PulseEvent.at <= until)
    order = (PulseEvent.at.desc(), PulseEvent.id.desc())

    if columns is None:
        query = PulseEvent.query.filter(*conditions).order_by(*order)
        return [_serialize_event(row) for row in query.all()]

    statement = (
        sa.select(*_selected(PulseEvent, columns, _EVENT_KEYS)).where(*conditions).order_by(*order)
    )
    return [_project(row, columns, _EVENT_FORMATS) for row in db.session.execute(statement)]
