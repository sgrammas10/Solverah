"""The transactional outbox: what goes in it, and how it gets out.

Part 4.7, Phase 3 item 2.  Every outbound email in the application now travels
through here.

**The problem it solves.**  Registration created the account, committed it, and
then called Resend inline.  Three different callers each invented their own
answer to "what if that call fails": ``register`` swallowed it and returned 201
with no code ever sent, ``resend_confirmation`` and ``request_password_reset``
returned 500 after having already rotated the token, and ``early_access_request``
returned 500 having persisted nothing at all, losing the lead outright.  All
three are the same bug -- a side effect that is neither inside the transaction
nor retried -- and all three are fixed by moving the *intent* into the
transaction and the *delivery* out of the request.

**The invariant, stated precisely, because it is what the tests assert:**

1. The row is written with ``db.session.add`` and never committed by this
   module.  It lands in the caller's transaction, so the business write and the
   obligation to send commit together or not at all.
2. A publish that fails leaves ``published_at`` NULL and increments ``attempts``.
   The row is still there; :func:`drain` will find it.  Nothing is lost.
3. A publish against a row that is already published sends nothing and reports
   ``already_published``.  Retries are therefore safe -- which matters, because
   ``task_acks_late`` means a worker killed mid-task gets the message again.

Point 3 is enforced with a row lock (``SELECT ... FOR UPDATE``) held across the
provider call, so two workers handed the same id cannot both send.  Holding a
lock across a network call is normally a thing to avoid; here it is one row in a
queue table, :func:`drain` uses ``SKIP LOCKED`` so nothing waits behind it, and
the alternative is a double-send.  What it does not defend against is the send
succeeding and the process dying before the UPDATE commits: that is at-least-once,
which is the strongest guarantee available against a remote provider that has no
idempotency key.

**Publishing runs on its own connection, not on ``db.session``.**  Under eager
execution the "worker" is the request thread, and ``db.session`` is scoped to it
-- committing that session inside a task would commit whatever the request had
pending as well.  ``db.engine.begin()`` makes the task's transaction genuinely
its own in both modes, which is what lets the same code be evidence in tests and
correct in production.

**Handlers resolve the send function off the module at call time.**  Every email
test in the suite does ``monkeypatch.setattr("solverah.infra.email.send_...")``;
binding the function at import would step around all of them and start sending
real mail from the test suite the first time someone set ``RESEND_API_KEY``.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Callable, Dict, List, Optional

import sqlalchemy as sa

from model import Outbox, db
from solverah.infra import email as email_infra

__all__ = [
    "ALREADY_PUBLISHED",
    "FAILED",
    "MAX_ATTEMPTS",
    "MISSING",
    "PUBLISHED",
    "RETRY_MIN_AGE",
    "TOPICS",
    "TOPIC_EMAIL_EARLY_ACCESS",
    "TOPIC_EMAIL_INTAKE_NOTIFICATION",
    "TOPIC_EMAIL_PASSWORD_RESET",
    "TOPIC_EMAIL_PULSE_PROMPT",
    "TOPIC_EMAIL_VERIFICATION",
    "depth",
    "drain",
    "enqueue",
    "publish",
    "publish_soon",
    "purge_published",
    "unpublished_count",
]

logger = logging.getLogger("solverah.outbox")

# -- Topics -----------------------------------------------------------------
#
# Dotted, `domain.event` shaped, and treated as data on the wire: a row written
# by one deploy is published by the next, so renaming a topic is a migration and
# not a rename.  Adding one means adding a handler below; an unknown topic is a
# failure rather than a silent drop, and `drain` parks it after MAX_ATTEMPTS.

TOPIC_EMAIL_VERIFICATION = "email.verification"
TOPIC_EMAIL_PASSWORD_RESET = "email.password_reset"
TOPIC_EMAIL_EARLY_ACCESS = "email.early_access"
TOPIC_EMAIL_INTAKE_NOTIFICATION = "email.intake_notification"
TOPIC_EMAIL_PULSE_PROMPT = "email.pulse_prompt"

# -- Publish outcomes -------------------------------------------------------
#
# Returned rather than raised.  A publish failure is an ordinary state of this
# system, not an exception: the row stays for the sweep and the caller -- a
# Celery task -- has nothing useful to do with a traceback.

PUBLISHED = "published"
ALREADY_PUBLISHED = "already_published"
FAILED = "failed"
MISSING = "missing"

#: How many times a row is retried before :func:`drain` stops picking it up.
#:
#: The row is not deleted and not marked published -- it parks, visibly, with
#: ``attempts = MAX_ATTEMPTS`` and ``published_at IS NULL``.  A payload that can
#: never be delivered (an address the provider rejects, a topic this deploy does
#: not know) would otherwise be retried by every sweep forever, and the sweep
#: would spend its budget on it instead of on the rows behind it.
MAX_ATTEMPTS = 8

#: Backoff: the age a row must reach before try ``n + 1`` is allowed.
#:
#: Indexed by ``attempts`` -- the number of tries already made -- and measured
#: from ``created_at``, so no schema change is needed: ``attempts`` only ever
#: goes up, which makes age-at-attempt a monotonic stand-in for
#: time-since-last-attempt.
#:
#: The schedule assumes the sweep runs on a coarse cadence (production is a
#: cron every ~5 minutes; see docs/RUNBOOK_SCENARIO_A_CRON.md) rather than the
#: 30-second beat loop the original flat design was written for.  Under that
#: beat loop, 8 flat attempts spanned ~4 minutes and a Resend outage longer
#: than that parked every row it touched.  With the entries below and a 5-minute
#: cadence, the tries land at roughly 0 (inline), 5m, 15m, 45m, 2h, 4h, 8h and
#: 16h of row age -- so only an outage longer than ~16 hours can park a row,
#: and a healthy provider still gets the user their code on the next sweep.
#:
#: The first two entries are zero on purpose: a row that has never been tried
#: (a lost ``publish_soon``) and a row whose single inline attempt just failed
#: are both worth retrying at the very next sweep.
#:
#: One degenerate case, accepted: eligibility is age-based, so if the sweep
#: itself was down for hours, a backlogged row old enough to clear every
#: threshold can burn its remaining attempts across consecutive sweeps.  That
#: still gives it ~30 minutes of retries after the sweep recovers, which is the
#: old design's whole budget.
RETRY_MIN_AGE = (
    datetime.timedelta(0),           # try 1: never attempted
    datetime.timedelta(0),           # try 2: first (inline) attempt failed
    datetime.timedelta(minutes=15),  # try 3
    datetime.timedelta(minutes=45),  # try 4
    datetime.timedelta(hours=2),     # try 5
    datetime.timedelta(hours=4),     # try 6
    datetime.timedelta(hours=8),     # try 7
    datetime.timedelta(hours=16),    # try 8: parks if this one fails
)

assert len(RETRY_MIN_AGE) == MAX_ATTEMPTS


def _send_verification(payload: Dict[str, Any]) -> None:
    email_infra.send_confirmation_email(payload["to"], payload["code"])


def _send_password_reset(payload: Dict[str, Any]) -> None:
    email_infra.send_password_reset_email(payload["to"], payload["code"])


def _send_early_access(payload: Dict[str, Any]) -> None:
    email_infra.send_early_access_modal_notification(**payload)


def _send_intake_notification(payload: Dict[str, Any]) -> None:
    email_infra.send_intake_notification(**payload)


def _send_pulse_prompt(payload: Dict[str, Any]) -> None:
    email_infra.send_pulse_prompt_email(
        payload["to"], payload["deep_link"], slowdown_notice=payload.get("slowdown_notice", False)
    )


#: Topic -> the side effect publishing it performs.
TOPICS: Dict[str, Callable[[Dict[str, Any]], None]] = {
    TOPIC_EMAIL_VERIFICATION: _send_verification,
    TOPIC_EMAIL_PASSWORD_RESET: _send_password_reset,
    TOPIC_EMAIL_EARLY_ACCESS: _send_early_access,
    TOPIC_EMAIL_INTAKE_NOTIFICATION: _send_intake_notification,
    TOPIC_EMAIL_PULSE_PROMPT: _send_pulse_prompt,
}

_table = Outbox.__table__


# ---------------------------------------------------------------------------
# Write side -- runs in the caller's transaction
# ---------------------------------------------------------------------------

def enqueue(topic: str, payload: Dict[str, Any]) -> int:
    """Add an outbox row to the current transaction and return its id.

    Does **not** commit, and that is the whole design: the caller's
    ``db.session.commit()`` is what makes both the business write and this row
    durable together.

    Flushes, because the caller needs the id to hand to :func:`publish_soon`
    after the commit.  Reading ``entry.id`` after the commit instead would issue
    a refresh SELECT against an expired instance for no benefit.

    Args:
        topic: One of the ``TOPIC_*`` constants.  Rejected here if unknown, so a
            typo fails at the write rather than silently parking a row that no
            publisher can ever handle.
        payload: JSON-serialisable arguments for the topic's handler.

    Returns:
        The new row's ``id``.
    """
    if topic not in TOPICS:
        raise ValueError("unknown outbox topic %r" % topic)

    entry = Outbox(topic=topic, payload=payload)
    db.session.add(entry)
    db.session.flush()
    return entry.id


def publish_soon(entry_id: int) -> None:
    """Ask a worker to publish *entry_id*. Call this **after** the commit.

    Called before the commit, the worker can win the race and find no row.  The
    row would still be published by the next sweep, so the failure is a delay
    rather than a loss -- but it is a delay on the path a user is waiting on,
    which is the one that matters.

    Never raises.  If the broker is unreachable the row simply waits for
    :func:`drain`; see ``solverah.infra.queue.enqueue``.
    """
    from solverah.infra.queue import enqueue as enqueue_task
    from solverah.tasks.outbox_tasks import publish_entry

    enqueue_task(publish_entry, entry_id)


# ---------------------------------------------------------------------------
# Publish side -- runs in a worker, on its own transaction
# ---------------------------------------------------------------------------

def publish(entry_id: int) -> str:
    """Deliver one outbox row. Returns one of the outcome constants.

    Requires a Flask application context (for ``db.engine``); the task wrapper
    supplies one.
    """
    with db.engine.begin() as connection:
        row = connection.execute(
            sa.select(_table.c.topic, _table.c.payload, _table.c.published_at)
            .where(_table.c.id == entry_id)
            .with_for_update()
        ).first()

        if row is None:
            # Not an error worth alarming on: the row can legitimately be gone if
            # `purge_published` ran between the enqueue and the worker picking it
            # up, which only happens for a row that was already delivered.
            logger.info(
                "outbox_missing", extra={"event": "outbox_missing", "outbox_id": entry_id}
            )
            return MISSING

        if row.published_at is not None:
            return ALREADY_PUBLISHED

        handler = TOPICS.get(row.topic)
        try:
            if handler is None:
                raise ValueError("no handler for topic %r" % row.topic)
            handler(row.payload or {})
        except Exception as exc:  # noqa: BLE001 -- the row is the retry record
            connection.execute(
                sa.update(_table)
                .where(_table.c.id == entry_id)
                .values(attempts=_table.c.attempts + 1)
            )
            logger.error(
                "outbox_publish_failed",
                extra={
                    "event": "outbox_publish_failed",
                    "outbox_id": entry_id,
                    "topic": row.topic,
                    "error": str(exc),
                },
            )
            return FAILED

        connection.execute(
            sa.update(_table)
            .where(_table.c.id == entry_id)
            .values(published_at=sa.func.now(), attempts=_table.c.attempts + 1)
        )
        logger.info(
            "outbox_published",
            extra={
                "event": "outbox_published",
                "outbox_id": entry_id,
                "topic": row.topic,
            },
        )
        return PUBLISHED


def drain(limit: int = 100) -> Dict[str, int]:
    """Publish everything still owed, oldest first. The safety net.

    This is what makes :func:`publish_soon` allowed to fail quietly.  It covers
    the broker being down when the row was written, the worker dying between
    delivery and completion, and a provider outage that has since ended.

    ``SKIP LOCKED`` rather than plain ``FOR UPDATE``: several sweeps may overlap,
    and a row another worker is mid-send on should be left to it rather than
    waited on.  The ids are collected in one short transaction and published one
    per transaction after it, so the selecting transaction is not held open
    across N provider calls.  Two overlapping sweeps that both collect the same
    id are still safe: :func:`publish` locks the row across the provider call,
    so the loser waits and then reads ``published_at`` -- one send, never two.

    A row is only selected once it is old enough for its next try -- see
    :data:`RETRY_MIN_AGE`.  A row still inside its backoff window is left where
    it is and counted by nothing here; it stays visible in :func:`depth` as
    ``pending``.

    Returns:
        Counts keyed by outcome, plus ``selected``.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    # attempts -> the latest created_at that makes the row old enough to retry.
    eligible_cutoff = sa.case(
        {tries: now - min_age for tries, min_age in enumerate(RETRY_MIN_AGE)},
        value=_table.c.attempts,
        else_=now - RETRY_MIN_AGE[-1],
    )
    with db.engine.begin() as connection:
        ids: List[int] = [
            row.id
            for row in connection.execute(
                sa.select(_table.c.id)
                .where(
                    _table.c.published_at.is_(None),
                    _table.c.attempts < MAX_ATTEMPTS,
                    _table.c.created_at <= eligible_cutoff,
                )
                .order_by(_table.c.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ]

    counts: Dict[str, int] = {"selected": len(ids)}
    for entry_id in ids:
        outcome = publish(entry_id)
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


def purge_published(older_than_hours: int = 24) -> int:
    """Delete rows delivered more than *older_than_hours* ago.

    The table holds addresses and one-time codes, so keeping delivered rows is a
    PII decision rather than a disk one -- and 24 hours is well past every OTP's
    15-minute expiry.  Unpublished rows are never touched, including parked ones:
    a row that could not be delivered is a thing somebody has to look at.
    """
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        hours=older_than_hours
    )
    with db.engine.begin() as connection:
        result = connection.execute(
            sa.delete(_table).where(
                _table.c.published_at.is_not(None), _table.c.published_at < cutoff
            )
        )
    return result.rowcount or 0


def unpublished_count(include_parked: bool = True) -> int:
    """How many rows are still owed. For tests; the readiness probe reads :func:`depth`."""
    clauses: List[Any] = [_table.c.published_at.is_(None)]
    if not include_parked:
        clauses.append(_table.c.attempts < MAX_ATTEMPTS)
    with db.engine.connect() as connection:
        return int(
            connection.execute(
                sa.select(sa.func.count()).select_from(_table).where(*clauses)
            ).scalar_one()
        )


def depth() -> Dict[str, int]:
    """Unpublished rows split into the two states an operator acts on differently.

    ``pending`` rows are waiting on a publisher and will clear on their own once
    one runs; ``parked`` rows exhausted :data:`MAX_ATTEMPTS` (under eager
    execution that is a single failed inline send) and clear only by hand.

    Reported in the ``/readyz`` payload as information, never as readiness: a
    deep outbox means email is behind, not that the process cannot serve
    traffic, and failing readiness on it would pull the whole service out of
    rotation over a non-fatal condition.

    One statement: both counts come from one pass over the unpublished rows,
    the ``pending`` half as a ``FILTER``.  Two separate counts cost the probe a
    second round trip and could disagree -- a row published between them made
    ``parked`` negative.
    """
    with db.engine.connect() as connection:
        row = connection.execute(
            sa.select(
                sa.func.count().label("total"),
                sa.func.count()
                .filter(_table.c.attempts < MAX_ATTEMPTS)
                .label("pending"),
            ).where(_table.c.published_at.is_(None))
        ).one()
    return {"pending": int(row.pending), "parked": int(row.total) - int(row.pending)}


def entry_state(entry_id: int) -> Optional[Dict[str, Any]]:
    """The row's publish state, or None. Used by tests to assert the invariant."""
    with db.engine.connect() as connection:
        row = connection.execute(
            sa.select(
                _table.c.topic,
                _table.c.payload,
                _table.c.published_at,
                _table.c.attempts,
            ).where(_table.c.id == entry_id)
        ).first()
    if row is None:
        return None
    return {
        "topic": row.topic,
        "payload": row.payload,
        "published_at": row.published_at,
        "attempts": row.attempts,
    }
