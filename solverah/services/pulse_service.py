"""Pulse API operations (BUILD_PLAN B-2): checkins, history, next-checkin,
events, and cadence settings.

This is only what an authenticated user's own requests can do. The engine that
decides who gets PROMPTED is `pulse_cadence_service.py`, run from
`flask pulse send-prompts` -- a different module because a Flask CLI process and
a `/api/v1/me/...` request are different callers with different lifecycles, even
though both end up calling `pulse_settings.py`.

Raises `solverah.errors` types for every failure, per
`solverah/services/__init__.py`'s convention ("It raises solverah.errors types,
or returns a result the API layer serialises"). BUILD_PLAN B-2's brief calls for
mapping the store's refusals to `application/problem+json` explicitly, which is
why this module raises `ValidationError` rather than returning the `{"error":
...}` shape the sibling Situation Report routes in this same blueprint still
use -- those predate `solverah.errors` and have not been migrated; this is new
code with no such history to match.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, Optional

from model import User, db
from solverah.errors import ValidationError
from solverah.services import pulse_settings

__all__ = [
    "get_history",
    "get_next_checkin",
    "get_settings",
    "submit_checkin",
    "submit_event",
    "update_settings",
]

#: `GET /me/pulse/history`'s `limit`, when given. Unbounded (`None`) by default,
#: same reasoning as `pulse_store.pulse_checkin_history`'s own default: a
#: history read is a different question from "what applies right now", and a
#: Pulse account accumulates at most one row a week, so there is no cost to
#: leaving it unbounded. `solverah.pagination.resolve_limit` is not reused here
#: because its default is never "unbounded" -- it always returns an int.
_MIN_HISTORY_LIMIT = 1
_MAX_HISTORY_LIMIT = 100


def _require_dict(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValidationError(detail="body must be an object")
    return payload


def _parse_datetime(raw: Optional[str], *, field_name: str) -> Optional[datetime.datetime]:
    if raw is None or raw == "":
        return None
    try:
        parsed = datetime.datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError(
            detail="%s must be an ISO-8601 datetime" % field_name,
            errors=[{"field": field_name, "code": "invalid_datetime"}],
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def _parse_history_limit(raw: Optional[str]) -> Optional[int]:
    if raw is None or raw == "":
        return None
    try:
        limit = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            detail="limit must be an integer",
            errors=[{"field": "limit", "code": "int_parsing"}],
        ) from exc
    return max(_MIN_HISTORY_LIMIT, min(_MAX_HISTORY_LIMIT, limit))


def submit_checkin(user: User, payload: Any) -> Dict[str, Any]:
    """Record one check-in for this user's next round-robin sequence.

    The sequence and the dimensions it must answer are both server-derived
    (`pulse_store.pulse_checkin_count`, `work_pulse.pulse_items.dimensions_for_checkin`)
    -- the request names only the answers, never the sequence or the item set.
    """
    import pulse_store
    from work_pulse.pulse_items import FORM_VERSION

    payload = _require_dict(payload)
    item_scores = payload.get("item_scores")
    if not isinstance(item_scores, dict):
        raise ValidationError(
            detail="item_scores must be an object",
            errors=[{"field": "item_scores", "code": "invalid_type"}],
        )
    experienced = payload.get("experienced")

    sequence = pulse_store.pulse_checkin_count(user.id)
    try:
        checkin_id = pulse_store.write_pulse_checkin(
            db,
            user.id,
            sequence=sequence,
            item_scores=item_scores,
            experienced=experienced,
            version=FORM_VERSION,
        )
    except ValueError as exc:
        raise ValidationError(
            detail=str(exc), errors=[{"field": "item_scores", "code": "invalid_checkin"}]
        ) from exc

    pulse_settings.mark_answered(user.id)
    db.session.commit()

    from model import PulseCheckin

    row = db.session.get(PulseCheckin, checkin_id)
    return {
        "id": checkin_id,
        "sequence": sequence,
        "taken_at": row.taken_at.isoformat() if row is not None and row.taken_at else None,
        "item_scores": dict(item_scores),
        "experienced": experienced,
        "version": FORM_VERSION,
    }


def get_next_checkin(user: User) -> Dict[str, Any]:
    """The items this user's next check-in will serve -- the same instrument
    `submit_checkin` will validate the answer against."""
    import pulse_store
    from work_pulse.pulse_items import render_checkin

    sequence = pulse_store.pulse_checkin_count(user.id)
    return render_checkin(user.id, sequence)


#: `pulse_store`'s serializers include `user_id` -- it is the store's own
#: contract, shared with the account-export reader. The wire response strips
#: it: the caller is always reading their own history (the route resolves
#: `user` from the JWT, never a path parameter), so echoing their id back adds
#: nothing `PulseCheckinResponse`/`PulseEventResponse` do not already omit.
def _drop_user_id(record: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in record.items() if key != "user_id"}


def get_history(
    user: User,
    *,
    since_raw: Optional[str],
    until_raw: Optional[str],
    limit_raw: Optional[str],
) -> Dict[str, Any]:
    """Check-ins and events, newest first, optionally windowed."""
    import pulse_store

    since = _parse_datetime(since_raw, field_name="since")
    until = _parse_datetime(until_raw, field_name="until")
    limit = _parse_history_limit(limit_raw)

    checkins = pulse_store.pulse_checkin_history(user.id, since=since, until=until, limit=limit)
    events = pulse_store.pulse_events_in_range(user.id, since=since, until=until)
    return {
        "checkins": [_drop_user_id(row) for row in checkins],
        "events": [_drop_user_id(row) for row in events],
    }


def submit_event(user: User, payload: Any) -> Dict[str, Any]:
    """Log one dated annotation on this user's Pulse timeline."""
    import pulse_store

    payload = _require_dict(payload)
    event_type = payload.get("event_type")
    note = payload.get("note")

    try:
        event_id = pulse_store.write_pulse_event(db, user.id, event_type=event_type, note=note)
    except ValueError as exc:
        raise ValidationError(
            detail=str(exc), errors=[{"field": "event_type", "code": "invalid_event"}]
        ) from exc
    db.session.commit()

    from model import PulseEvent

    row = db.session.get(PulseEvent, event_id)
    return {
        "id": event_id,
        "at": row.at.isoformat() if row is not None and row.at else None,
        "event_type": event_type,
        "note": note,
    }


#: `GET` and `PATCH /me/pulse/settings` return the *same* keys, deliberately:
#: the client writes the PATCH echo straight into the cache slot the GET fills
#: (`usePulse.ts`'s `useUpdatePulseSettings`), so a PATCH that answered with a
#: narrower body would blank `auto_slowed` on screen until the next refetch.
def _settings_response(settings: Dict[str, Any]) -> Dict[str, Any]:
    return {"cadence": settings["cadence"], "auto_slowed": settings["auto_slowed"]}


def get_settings(user: User) -> Dict[str, Any]:
    return _settings_response(pulse_settings.read_settings(user.id))


def update_settings(user: User, payload: Any) -> Dict[str, Any]:
    """weekly / biweekly / monthly / off, always one call -- and always a clean
    slate for the anti-nag state (`pulse_settings.set_cadence`'s docstring),
    `auto_slowed` included."""
    payload = _require_dict(payload)
    cadence = payload.get("cadence")
    try:
        updated = pulse_settings.set_cadence(user.id, cadence)
    except ValueError as exc:
        raise ValidationError(
            detail=str(exc), errors=[{"field": "cadence", "code": "invalid_cadence"}]
        ) from exc
    db.session.commit()
    return _settings_response(updated)
