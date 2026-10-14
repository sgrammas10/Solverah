"""Pulse cadence + anti-nag state (BUILD_PLAN B-2).

No table of its own. `profiles.extra["pulse_settings"]` is the storage -- D-7
(BUILD_PLAN, 2026-09-10, cross-cutting rule) is why: a new user-data table has
to join the `GET /me/export` and account-deletion seam D-7b owns this wave, and
the profile document already does. `profile_repository.load_document`/
`update_document` thread this key through both for free; nothing here has to.
This module itself reads and writes the one key through
`profile_repository.read_extra_key`/`update_extra_key` -- one SELECT to read,
three statements to write, the same compare-and-swap on `profiles.version` as a
whole-document save -- because nothing here needs the rest of the document.

Shape (every key optional -- a user who has never touched Pulse has none of
them, and `read_settings` fills every default; rows written before the
2026-09-14 G21 ruling have the first four keys only, so `auto_slowed` must
default like the rest rather than be assumed present)::

    {
      "cadence": "weekly" | "biweekly" | "monthly" | "off",
      "last_prompted_at": "<iso8601>" | None,
      "awaiting_response": bool,
      "consecutive_unanswered": int,
      "auto_slowed": bool,
    }

All four cadences are user-settable (G21, 2026-09-14): `monthly` is a real
menu option now, *and* still where the anti-nag auto-drop lands a quiet user
(PRODUCT_DECISIONS.md §"Pulse"). Those two are not the same state, which is
what `auto_slowed` records: True only when the engine moved this user to
`monthly` on its own, so the "we've slowed these down" note is shown to the
user it is true of and never to the user who chose monthly themselves.

**Who writes which field.** `set_cadence` (an explicit user choice) is the only
writer of `cadence` for user-chosen values, always clears the anti-nag
counters, and always clears `auto_slowed` -- an explicit choice is never held
against a prior silence (PRODUCT_DECISIONS.md §2: "silence is data, never a
guilt trip", which cuts both ways), and choosing a cadence ends the auto state
even when the cadence chosen is the same `monthly` the drop had landed on.
`mark_answered` (a completed check-in) is the only writer of
`awaiting_response`'s False transition. `record_prompt` (the cadence engine,
about to send a prompt) is the only writer of `last_prompted_at`,
`awaiting_response`'s True transition, `consecutive_unanswered`, and
`auto_slowed`'s True transition, and is the one place `cadence` moves to
`monthly` without the user asking. No two callers ever race to set the same
field for a reason other than `profile_repository`'s own optimistic-concurrency
retry, which already handles that.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, Optional, Sequence

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
    "read_settings_for_users",
    "record_prompt",
    "set_cadence",
]

SETTINGS_KEY = "pulse_settings"

#: PRODUCT_DECISIONS.md §2 / BUILD_PLAN B-2: "weekly default".
DEFAULT_CADENCE = "weekly"

#: The four cadences a user can choose directly. `monthly` joined them in the
#: G21 ruling (2026-09-14); it remains the anti-nag drop's landing spot too,
#: and `auto_slowed` is what tells the two apart.
USER_SETTABLE_CADENCES = ("weekly", "biweekly", "monthly", "off")

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
    "auto_slowed": False,
}


def _with_defaults(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    return {**_DEFAULTS, **raw}


def read_settings(user_id: int) -> Dict[str, Any]:
    """This user's Pulse cadence/anti-nag state, defaults filled in.

    A user who has never touched Pulse settings has no `pulse_settings` key at
    all in their profile document, which is not a special case here: it reads
    the same as an explicit `{"cadence": "weekly", ...}` would. One SELECT of
    the key (`profile_repository.read_extra_key`), which is exactly what the
    whole document's `.get(SETTINGS_KEY)` would give.
    """
    from solverah.repositories import profile_repository

    return _with_defaults(profile_repository.read_extra_key(user_id, SETTINGS_KEY))


def read_settings_for_users(user_ids: Sequence[int]) -> Dict[int, Dict[str, Any]]:
    """`read_settings` for many users in one SELECT: every id in *user_ids* maps
    to its settings, defaults filled in -- a user with no profile row or no key
    reads as the defaults, exactly as `read_settings` would give. Sends nothing
    for an empty *user_ids*.
    """
    from solverah.repositories import profile_repository

    stored = profile_repository.read_extra_key_for_users(user_ids, SETTINGS_KEY)
    return {user_id: _with_defaults(stored.get(user_id)) for user_id in user_ids}


def is_due(
    settings: Dict[str, Any],
    *,
    now: datetime.datetime,
    last_checkin_at: Optional[datetime.datetime] = None,
) -> bool:
    """Whether *settings* (as `read_settings` returns it) is due a prompt at *now*.

    `off` is never due. Otherwise the clock starts at the LATER of
    `last_prompted_at` and *last_checkin_at* -- the user's most recent completed
    check-in -- and a prompt is due once the cadence's interval has elapsed
    since then:

    - A user never prompted is due one interval after their last check-in
      rather than immediately (2026-09-11 ruling: checking in once is the
      opt-in, and the clock starts at that check-in, so a fresh first check-in
      buys a full quiet interval before the first prompt instead of everyone
      who ever checked in getting emailed the moment a cron first runs).
    - A user who checked in on their own after the last prompt is not due
      again until one interval after THAT check-in (2026-10-02 fix F4): before
      this the clock ran from the prompt alone, so a voluntary check-in three
      days ago still earned a "time to check in" email.

    THE INTERVAL IS COUNTED IN CALENDAR DAYS (UTC), NOT SECONDS (fix F5).
    The cron runs daily at a fixed time, so a prompt sent at one run is
    exactly seven days old at the run a week later -- give or take the few
    milliseconds between the two runs' clocks. A strict `now - last >= 7 days`
    lost that coin flip whenever the later run was a hair early, and the
    "weekly" prompt went out on day 8 instead. Comparing dates makes day 7 due
    whatever the time of day either side fell on.

    *last_checkin_at* is the caller's job to supply --
    `pulse_cadence_service.send_due_prompts`, the only caller, already excludes
    every zero-check-in user before reaching this function. A never-prompted user
    asked about here with no *last_checkin_at* is never due, defensively.
    """
    cadence = settings["cadence"]
    if cadence == "off":
        return False
    last_prompted_at = settings["last_prompted_at"]
    anchors = [
        anchor
        for anchor in (
            datetime.datetime.fromisoformat(last_prompted_at) if last_prompted_at else None,
            last_checkin_at,
        )
        if anchor is not None
    ]
    if not anchors:
        return False
    last = max(anchors)
    elapsed_days = (_utc_date(now) - _utc_date(last)).days
    return elapsed_days >= CADENCE_INTERVALS[cadence].days


def _utc_date(moment: datetime.datetime) -> datetime.date:
    """The UTC calendar date of *moment*; a naive value is taken as UTC already
    (every timestamp this module sees is timezone-aware, from a
    `timezone=True` column or an `isoformat()` of one -- this is the defensive
    reading, not a conversion)."""
    if moment.tzinfo is not None:
        moment = moment.astimezone(datetime.timezone.utc)
    return moment.date()


def set_cadence(user_id: int, cadence: str) -> Dict[str, Any]:
    """An explicit user choice. Returns the new `pulse_settings`.

    Always resets `awaiting_response` and `consecutive_unanswered`: picking a
    cadence is itself a re-engagement signal, so nothing about a prior silence
    carries into what happens next. Always clears `auto_slowed` for the same
    reason -- once the user has stated a cadence, the slowdown the engine chose
    for them is no longer the explanation for the one they are on, including
    when they pick the very `monthly` the drop had landed them on.
    `last_prompted_at` is left alone -- it states a fact (when this user was
    last emailed) that switching cadence does not change, and clearing it would
    make the very next cadence run treat them as never-prompted and email them
    again immediately.

    Raises:
        ValueError: *cadence* is not one of `USER_SETTABLE_CADENCES`.
    """
    if cadence not in USER_SETTABLE_CADENCES:
        raise ValueError(
            "cadence must be one of %r, got %r" % (USER_SETTABLE_CADENCES, cadence)
        )

    from solverah.repositories import profile_repository

    def _mutate(stored: Any) -> Dict[str, Any]:
        return {
            **_with_defaults(stored),
            "cadence": cadence,
            "awaiting_response": False,
            "consecutive_unanswered": 0,
            "auto_slowed": False,
        }

    return profile_repository.update_extra_key(user_id, SETTINGS_KEY, _mutate)


def _answered(stored: Any) -> Dict[str, Any]:
    """`mark_answered`'s write: the stored settings, defaults filled in, with
    `awaiting_response` off. Pure -- `update_extra_key` re-runs it on every
    lost compare-and-swap."""
    settings = _with_defaults(stored)
    settings["awaiting_response"] = False
    return settings


def mark_answered(user_id: int) -> None:
    """Flip `awaiting_response` off after a completed check-in.

    A no-op -- one SELECT of the key, no write at all -- when nothing was
    outstanding, which is the common case: most check-ins are voluntary, not a
    reply to a specific prompt email. Does not touch `consecutive_unanswered`;
    the cadence engine is the only reader of that field, and it re-derives
    "was the last prompt answered" from `awaiting_response` at its own next
    due-check rather than this call trying to guess what that will need.
    """
    if not read_settings(user_id)["awaiting_response"]:
        return

    from solverah.repositories import profile_repository

    profile_repository.update_extra_key(user_id, SETTINGS_KEY, _answered)


def record_prompt(
    user_id: int,
    *,
    cadence: str,
    consecutive_unanswered: int,
    prompted_at: datetime.datetime,
    auto_slowed: bool = False,
) -> None:
    """The cadence engine's write: a prompt is about to be sent.

    Called from the same transaction as the outbox row it accompanies (see
    `pulse_cadence_service.send_due_prompts`), before either is committed --
    so a crash before commit means neither happened, and the next run
    reprocesses this user exactly as if nothing had been attempted.

    *auto_slowed* is written on every prompt, not only on a drop: the engine
    passes True when this call is the drop and otherwise passes the value it
    already read back through, so an auto-dropped user stays flagged across
    later prompts and a user who chose `monthly` themselves stays unflagged.
    """
    from solverah.repositories import profile_repository

    def _mutate(stored: Any) -> Dict[str, Any]:
        settings = _with_defaults(stored)
        settings.update(
            cadence=cadence,
            last_prompted_at=prompted_at.isoformat(),
            awaiting_response=True,
            consecutive_unanswered=consecutive_unanswered,
            auto_slowed=auto_slowed,
        )
        return settings

    profile_repository.update_extra_key(user_id, SETTINGS_KEY, _mutate)
