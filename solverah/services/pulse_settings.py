"""Pulse cadence + anti-nag state (BUILD_PLAN B-2).

No table of its own. `profiles.extra["pulse_settings"]`, via
`profile_repository.update_document`, is the storage -- D-7 (BUILD_PLAN,
2026-09-10, cross-cutting rule) is why: a new user-data table has to join the
`GET /me/export` and account-deletion seam D-7b owns this wave, and the profile
document already does. `profile_repository.load_document`/`update_document`
thread this key through both for free; nothing here has to.

Shape (every key optional -- a user who has never touched Pulse has none of
them, and `read_settings` fills every default)::

    {
      "cadence": "weekly" | "biweekly" | "monthly" | "off",
      "last_prompted_at": "<iso8601>" | None,
      "awaiting_response": bool,
      "consecutive_unanswered": int,
    }

`monthly` is reachable only through the anti-nag auto-drop
(`pulse_cadence_service.send_due_prompts`) -- a user can set themselves to
`weekly`, `biweekly`, or `off` and never directly to `monthly`.

**Who writes which field.** `set_cadence` (an explicit user choice) is the only
writer of `cadence` for the three user-settable values, and always clears the
anti-nag counters -- an explicit choice is never held against a prior silence
(PRODUCT_DECISIONS.md §2: "silence is data, never a guilt trip", which cuts
both ways). `mark_answered` (a completed check-in) is the only writer of
`awaiting_response`'s False transition. `record_prompt` (the cadence engine,
about to send a prompt) is the only writer of `last_prompted_at`,
`awaiting_response`'s True transition, `consecutive_unanswered`, and the one
place `cadence` moves to `monthly`. No two callers ever race to set the same
field for a reason other than `profile_repository`'s own optimistic-concurrency
retry, which already handles that.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, Optional

__all__ = [
    "CADENCE_INTERVALS",
    "CONSECUTIVE_UNANSWERED_DROP_THRESHOLD",
    "DEFAULT_CADENCE",
    "DROPPED_CADENCE",
    "SETTINGS_KEY",
    "USER_SETTABLE_CADENCES",
    "is_due",
    "mark_answered",
    "read_settings",
    "record_prompt",
    "set_cadence",
]

SETTINGS_KEY = "pulse_settings"

#: PRODUCT_DECISIONS.md §2 / BUILD_PLAN B-2: "weekly default".
DEFAULT_CADENCE = "weekly"

#: The three cadences a user can choose directly. `monthly` is deliberately
#: absent -- it is where the anti-nag drop lands a user, not a menu option.
USER_SETTABLE_CADENCES = ("weekly", "biweekly", "off")

CADENCE_INTERVALS: Dict[str, datetime.timedelta] = {
    "weekly": datetime.timedelta(days=7),
    "biweekly": datetime.timedelta(days=14),
    "monthly": datetime.timedelta(days=30),
}

#: BUILD_PLAN B-2: "3 consecutive unanswered -> auto-drop to monthly".
CONSECUTIVE_UNANSWERED_DROP_THRESHOLD = 3
DROPPED_CADENCE = "monthly"

_DEFAULTS: Dict[str, Any] = {
    "cadence": DEFAULT_CADENCE,
    "last_prompted_at": None,
    "awaiting_response": False,
    "consecutive_unanswered": 0,
}


def _with_defaults(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    return {**_DEFAULTS, **raw}


def read_settings(user_id: int) -> Dict[str, Any]:
    """This user's Pulse cadence/anti-nag state, defaults filled in.

    A user who has never touched Pulse settings has no `pulse_settings` key at
    all in their profile document, which is not a special case here: it reads
    the same as an explicit `{"cadence": "weekly", ...}` would.
    """
    from solverah.repositories import profile_repository

    document = profile_repository.load_document(user_id)
    return _with_defaults(document.get(SETTINGS_KEY))


def is_due(
    settings: Dict[str, Any],
    *,
    now: datetime.datetime,
    last_checkin_at: Optional[datetime.datetime] = None,
) -> bool:
    """Whether *settings* (as `read_settings` returns it) is due a prompt at *now*.

    `off` is never due. A user never prompted (`last_prompted_at` is None) is due
    `CADENCE_INTERVALS[cadence]` after *last_checkin_at* -- their most recent
    completed check-in -- rather than immediately (2026-09-11 ruling: checking in
    once is the opt-in, and the clock starts at that check-in, so a fresh first
    check-in buys a full quiet interval before the first prompt instead of
    everyone who ever checked in getting emailed the moment a cron first runs).

    *last_checkin_at* is the caller's job to supply for a never-prompted user --
    `pulse_cadence_service.send_due_prompts`, the only caller, already excludes
    every zero-check-in user before reaching this function. A never-prompted user
    asked about here with no *last_checkin_at* is never due, defensively.
    """
    cadence = settings["cadence"]
    if cadence == "off":
        return False
    last_prompted_at = settings["last_prompted_at"]
    if last_prompted_at is None:
        if last_checkin_at is None:
            return False
        last = last_checkin_at
    else:
        last = datetime.datetime.fromisoformat(last_prompted_at)
    return now - last >= CADENCE_INTERVALS[cadence]


def set_cadence(user_id: int, cadence: str) -> Dict[str, Any]:
    """An explicit user choice. Returns the new `pulse_settings`.

    Always resets `awaiting_response` and `consecutive_unanswered`: picking a
    cadence is itself a re-engagement signal, so nothing about a prior silence
    carries into what happens next. `last_prompted_at` is left alone -- it
    states a fact (when this user was last emailed) that switching cadence does
    not change, and clearing it would make the very next cadence run treat them
    as never-prompted and email them again immediately.

    Raises:
        ValueError: *cadence* is not one of `USER_SETTABLE_CADENCES`.
    """
    if cadence not in USER_SETTABLE_CADENCES:
        raise ValueError(
            "cadence must be one of %r, got %r" % (USER_SETTABLE_CADENCES, cadence)
        )

    from solverah.repositories import profile_repository

    def _mutate(document: Dict[str, Any]) -> Dict[str, Any]:
        current = _with_defaults(document.get(SETTINGS_KEY))
        updated = {
            **current,
            "cadence": cadence,
            "awaiting_response": False,
            "consecutive_unanswered": 0,
        }
        return {**document, SETTINGS_KEY: updated}

    new_document = profile_repository.update_document(user_id, _mutate)
    return new_document[SETTINGS_KEY]


def mark_answered(user_id: int) -> None:
    """Flip `awaiting_response` off after a completed check-in.

    A no-op -- no read past the first, no write at all -- when nothing was
    outstanding, which is the common case: most check-ins are voluntary, not a
    reply to a specific prompt email. Does not touch `consecutive_unanswered`;
    the cadence engine is the only reader of that field, and it re-derives
    "was the last prompt answered" from `awaiting_response` at its own next
    due-check rather than this call trying to guess what that will need.
    """
    current = read_settings(user_id)
    if not current["awaiting_response"]:
        return

    from solverah.repositories import profile_repository

    def _mutate(document: Dict[str, Any]) -> Dict[str, Any]:
        settings = _with_defaults(document.get(SETTINGS_KEY))
        settings["awaiting_response"] = False
        return {**document, SETTINGS_KEY: settings}

    profile_repository.update_document(user_id, _mutate)


def record_prompt(
    user_id: int,
    *,
    cadence: str,
    consecutive_unanswered: int,
    prompted_at: datetime.datetime,
) -> None:
    """The cadence engine's write: a prompt is about to be sent.

    Called from the same transaction as the outbox row it accompanies (see
    `pulse_cadence_service.send_due_prompts`), before either is committed --
    so a crash before commit means neither happened, and the next run
    reprocesses this user exactly as if nothing had been attempted.
    """
    from solverah.repositories import profile_repository

    def _mutate(document: Dict[str, Any]) -> Dict[str, Any]:
        settings = _with_defaults(document.get(SETTINGS_KEY))
        settings.update(
            cadence=cadence,
            last_prompted_at=prompted_at.isoformat(),
            awaiting_response=True,
            consecutive_unanswered=consecutive_unanswered,
        )
        return {**document, SETTINGS_KEY: settings}

    profile_repository.update_document(user_id, _mutate)
