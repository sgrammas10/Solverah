"""The Pulse prompt cadence engine (BUILD_PLAN B-2): who is due, the anti-nag
auto-drop, and the outbox email that invites them back.

Run as ``flask pulse send-prompts`` (`solverah/cli.py`) -- the Scenario A cron
pattern (see that module's header for why this is a Flask CLI entry point a
Render Cron Job service calls, and not a Celery beat schedule: production has
no broker and no worker). No table of its own: due-ness reads and writes
`pulse_settings.py`'s state on the profile document, and D-7 (BUILD_PLAN,
2026-09-10) is why -- a new user-data table has to join the account
export/delete seam D-7b owns this wave, and the profile document already does.

**Idempotency, the same shape as every other outbox caller.** The business
write -- this user's `pulse_settings` marked as freshly prompted -- and the
obligation to send -- the outbox row -- are written in the same transaction and
committed together, *before* `outbox.publish_soon` is even called. A crash
before that commit means neither happened, and the next run reprocesses the
user exactly as if nothing had been attempted: `is_due` still says yes, because
nothing moved `last_prompted_at`. A crash after the commit but before the
publish call just delays the send to the outbox sweep, the same "at-least-once"
guarantee `solverah/services/outbox.py`'s own docstring accepts for every other
caller.

**The due-selection scan.** `send_due_prompts` walks every confirmed-email user
once. There is no ``pulse_settings`` column to filter on in SQL -- it is a key
inside `profiles.extra`, a JSONB remainder column -- so this is a Python-side
scan rather than a query predicate. Deliberately: the product is pre-launch,
the user table is small, and adding a JSONB path index for one weekly cron job
would be optimizing a problem this codebase does not have yet.
"""

from __future__ import annotations

import datetime
from typing import Dict, Optional

from model import User, db
from solverah.services import outbox, pulse_settings

__all__ = ["TARGET_ROUTE", "send_due_prompts"]

#: The frontend route B-3 mounts the check-in flow on. Named here so the deep
#: link and B-3's route table cannot silently drift apart -- see BUILD_PLAN
#: B-2's report for the naming rationale (mirrors `/situation-report`,
#: `/manager-profile`'s bare-noun pattern).
TARGET_ROUTE = "/pulse"


def _deep_link(base_url: str) -> str:
    return base_url.rstrip("/") + TARGET_ROUTE


def send_due_prompts(
    *, base_url: str, now: Optional[datetime.datetime] = None
) -> Dict[str, int]:
    """Prompt every confirmed-email user whose cadence says they are due.

    Unconfirmed addresses are skipped outright -- Pulse prompts are a retention
    nudge, not a transactional email, and sending non-essential mail to an
    address nobody has proven ownership of is not a call this pass should make
    silently. Flagged in BUILD_PLAN B-2's report for Sebastian's review.

    A user with zero completed check-ins is excluded too, regardless of cadence
    or confirmation status (2026-09-11 ruling): checking in once is the opt-in,
    users are recruited in-product, and Pulse never sends a first, unsolicited
    invitation by email. For an eligible user never yet prompted, the due
    baseline is their most recent check-in's `taken_at`, not cron-discovery
    time -- see `pulse_settings.is_due`'s docstring.

    Returns:
        Counts keyed by outcome, for the cron's JSON log line.
    """
    import pulse_store

    now = now if now is not None else datetime.datetime.now(datetime.timezone.utc)

    checked = 0
    sent = 0
    dropped_to_monthly = 0

    # `.all()`, not `.yield_per()`: a server-side cursor does not survive the
    # per-user `db.session.commit()` below (`psycopg2.ProgrammingError: named
    # cursor isn't valid anymore`) -- the commit ends the transaction the
    # cursor was streaming rows under. Loading the whole list up front is the
    # same pre-launch-scale call the module docstring already makes for doing
    # this scan in Python instead of a JSONB query in the first place.
    for user in User.query.filter(User.email_confirmed).all():
        checked += 1
        latest_checkin = pulse_store.latest_pulse_checkin(user.id)
        if latest_checkin is None:
            continue

        settings = pulse_settings.read_settings(user.id)
        last_checkin_at = datetime.datetime.fromisoformat(latest_checkin["taken_at"])
        if not pulse_settings.is_due(settings, now=now, last_checkin_at=last_checkin_at):
            continue

        consecutive_unanswered = settings["consecutive_unanswered"]
        if settings["awaiting_response"]:
            consecutive_unanswered += 1
        else:
            consecutive_unanswered = 0

        slowdown_notice = False
        new_cadence = settings["cadence"]
        if consecutive_unanswered >= pulse_settings.CONSECUTIVE_UNANSWERED_DROP_THRESHOLD:
            new_cadence = pulse_settings.DROPPED_CADENCE
            consecutive_unanswered = 0
            slowdown_notice = True
            dropped_to_monthly += 1

        pulse_settings.record_prompt(
            user.id,
            cadence=new_cadence,
            consecutive_unanswered=consecutive_unanswered,
            prompted_at=now,
        )
        entry_id = outbox.enqueue(
            outbox.TOPIC_EMAIL_PULSE_PROMPT,
            {
                "to": user.email,
                "deep_link": _deep_link(base_url),
                "slowdown_notice": slowdown_notice,
            },
        )
        db.session.commit()
        outbox.publish_soon(entry_id)
        sent += 1

    return {"checked": checked, "sent": sent, "dropped_to_monthly": dropped_to_monthly}
