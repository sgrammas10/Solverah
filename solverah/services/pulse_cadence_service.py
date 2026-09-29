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

**The due-selection scan.** `send_due_prompts` reads its candidates -- every
confirmed-email user with at least one check-in, and that check-in's time -- in
one query, and their settings in one more. There is no ``pulse_settings`` column
to filter on in SQL -- it is a key inside `profiles.extra`, a JSONB remainder
column -- so due-ness itself is still decided in Python over that batch rather
than as a query predicate. Deliberately: the product is pre-launch, the user
table is small, and adding a JSONB path index for one weekly cron job would be
optimizing a problem this codebase does not have yet. The batch only rules
users out; a user it rules in is re-read just before the write, so each prompt
is still decided on reads taken moments before it is recorded, as it was before
there was a batch (see the loop). The cost of that rule is one run of delay for a
user who becomes due mid-run -- a cadence change to a shorter interval, say,
landing after the batch was read: the batch already ruled them out, so this run
skips them and the next run prompts them.
"""

from __future__ import annotations

import datetime
from typing import Dict, List, Optional, Tuple

import sqlalchemy as sa

from model import PulseCheckin, User, db
from solverah.services import outbox, pulse_settings

__all__ = ["TARGET_ROUTE", "send_due_prompts"]

#: The frontend route B-3 mounts the check-in flow on. Named here so the deep
#: link and B-3's route table cannot silently drift apart -- see BUILD_PLAN
#: B-2's report for the naming rationale (mirrors `/situation-report`,
#: `/manager-profile`'s bare-noun pattern).
TARGET_ROUTE = "/pulse"


def _deep_link(base_url: str) -> str:
    return base_url.rstrip("/") + TARGET_ROUTE


def _confirmed_user_count() -> int:
    """How many confirmed-email users there are -- the run's ``checked`` count,
    which has always counted every one of them, check-in or not."""
    return db.session.execute(
        sa.select(sa.func.count()).select_from(User).where(User.email_confirmed)
    ).scalar_one()


def _candidates(user_id: Optional[int] = None) -> List[Tuple[int, str, datetime.datetime]]:
    """``(user_id, email, latest taken_at)`` for every confirmed-email user with
    at least one check-in -- or for *user_id* alone -- one row per user, in one
    query.

    Plain tuples, not ``User`` rows, and that is load-bearing: the loop commits
    once per prompted user, a commit expires every ORM row in the session, and
    an expired row read on the next iteration is a SELECT per user. ``DISTINCT
    ON`` keeps each user's newest check-in -- the same row, by the same order,
    as `pulse_store.latest_pulse_checkin`. `ix_pulse_checkins_user_taken`
    (user_id, taken_at DESC) matches that order's first two keys only; the
    ``id DESC`` tie-break is not in the index.
    """
    statement = (
        sa.select(PulseCheckin.user_id, User.email, PulseCheckin.taken_at)
        .join(User, User.id == PulseCheckin.user_id)
        .where(User.email_confirmed)
    )
    if user_id is not None:
        statement = statement.where(PulseCheckin.user_id == user_id)
    rows = db.session.execute(
        statement.distinct(PulseCheckin.user_id).order_by(
            PulseCheckin.user_id, PulseCheckin.taken_at.desc(), PulseCheckin.id.desc()
        )
    )
    return [(row_user_id, email, taken_at) for row_user_id, email, taken_at in rows]


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

    Statements, whatever the number of users: one count (``checked`` has always
    counted every confirmed-email user), one read of the candidates, one of
    their settings. A prompted user then costs a constant few more -- the
    re-read below, the settings write, the outbox row -- and its own commit.

    Returns:
        Counts keyed by outcome, for the cron's JSON log line.
    """
    now = now if now is not None else datetime.datetime.now(datetime.timezone.utc)

    checked = _confirmed_user_count()
    sent = 0
    dropped_to_monthly = 0

    # Whole lists, not a streamed cursor: a server-side cursor does not survive
    # the per-user `db.session.commit()` below (`psycopg2.ProgrammingError:
    # named cursor isn't valid anymore`) -- the commit ends the transaction the
    # cursor was streaming rows under. Loading the candidates up front is the
    # same pre-launch-scale call the module docstring already makes for doing
    # this scan in Python instead of a JSONB query in the first place.
    candidates = _candidates()
    batch = pulse_settings.read_settings_for_users([user_id for user_id, _, _ in candidates])

    for user_id, _email, last_checkin_at in candidates:
        if not pulse_settings.is_due(batch[user_id], now=now, last_checkin_at=last_checkin_at):
            continue

        # The batch was read before any of this run's commits, so it only rules
        # users out. A user it rules in is read again here -- the latest check-in
        # and the settings, the two reads the loop used to make for every user --
        # so a cadence change, a check-in, or an account deletion (which drops
        # the confirmation) that landed while earlier users were being prompted
        # decides this prompt, and `record_prompt` never writes the batch's
        # older settings back over it.
        current = _candidates(user_id)
        if not current:
            continue
        _, email, last_checkin_at = current[0]
        settings = pulse_settings.read_settings(user_id)
        if not pulse_settings.is_due(settings, now=now, last_checkin_at=last_checkin_at):
            continue

        consecutive_unanswered = settings["consecutive_unanswered"]
        if settings["awaiting_response"]:
            consecutive_unanswered += 1
        else:
            consecutive_unanswered = 0

        slowdown_notice = False
        new_cadence = settings["cadence"]
        auto_slowed = settings["auto_slowed"]
        if consecutive_unanswered >= pulse_settings.CONSECUTIVE_UNANSWERED_DROP_THRESHOLD:
            # The counter resets either way -- three unanswered prompts have
            # been accounted for, whatever they led to. The *drop* only fires
            # for a user not already on the dropped cadence: there is nowhere
            # slower to go, and telling someone already at monthly that we have
            # "slowed these down" a second and third time is the nag the rule
            # exists to prevent (G21, 2026-09-14). `dropped_to_monthly` counts
            # real drops for the same reason -- a no-op write is not one.
            consecutive_unanswered = 0
            if new_cadence != pulse_settings.DROPPED_CADENCE:
                new_cadence = pulse_settings.DROPPED_CADENCE
                slowdown_notice = True
                auto_slowed = True
                dropped_to_monthly += 1

        pulse_settings.record_prompt(
            user_id,
            cadence=new_cadence,
            consecutive_unanswered=consecutive_unanswered,
            prompted_at=now,
            auto_slowed=auto_slowed,
        )
        entry_id = outbox.enqueue(
            outbox.TOPIC_EMAIL_PULSE_PROMPT,
            {
                "to": email,
                "deep_link": _deep_link(base_url),
                "slowdown_notice": slowdown_notice,
            },
        )
        # One commit per prompted user, on purpose: the settings write and its
        # outbox row land together or not at all (the module docstring's
        # idempotency). It expires nothing the loop reads next -- `candidates`
        # holds tuples, not ORM rows.
        db.session.commit()
        outbox.publish_soon(entry_id)
        sent += 1

    return {"checked": checked, "sent": sent, "dropped_to_monthly": dropped_to_monthly}
