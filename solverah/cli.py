"""Operational CLI commands -- the cron half of Scenario A.

Production (PROD_READINESS_2026-09_ANSWERS.md) is one Render web service and a
Postgres database: no Redis, no Celery worker, no beat.  Everything in
``BEAT_SCHEDULE`` is therefore dead in production, and two of those jobs are
load-bearing: the outbox sweep is what turns "the inline send failed once" into
"sent a few minutes later" instead of "never sent", and the retention purge is
what stops delivered outbox rows -- addresses and one-time codes -- accumulating
forever.

These commands are those two jobs as Flask CLI entry points, so a separate
Render **Cron Job** service can run them with nothing but the repo and the
dashboard env vars:

    flask outbox sweep       # suggested: every 5 minutes
    flask retention run      # suggested: daily

Both boot through ``create_app()`` (the Flask CLI imports ``app.py``), so fatal
config validation and Sentry apply exactly as they do to the web service --
a crash in a cron pass is captured, not just a line in a 14-day log tail.
The cron service shares nothing with the web process but the database, and the
database is all these commands touch; concurrency against inline publishes and
against an overlapping cron run is handled by the row locking inside
``outbox.publish``/``outbox.drain`` (``FOR UPDATE`` / ``SKIP LOCKED``).

**Exit codes are for cron alerting, and they distinguish two failures.**  A pass
that ran to completion exits 0 even if every row it retried failed -- a flaky
provider is the outbox's normal weather, the rows are still there, and the next
sweep retries them.  A non-zero exit means the pass *itself* crashed (config,
database, a bug) and the sweeper needs a human.

Service imports happen inside the command bodies: this module is imported by the
factory, which must stay importable without pulling in ``model`` and the email
infrastructure.
"""

from __future__ import annotations

import json

import click
from flask.cli import AppGroup

__all__ = ["outbox_cli", "register_cli", "retention_cli"]

outbox_cli = AppGroup("outbox", help="Transactional-outbox operations (cron entry points).")
retention_cli = AppGroup("retention", help="Data-retention purges (cron entry points).")

#: Retention window for *delivered* outbox rows, in hours.
#:
#: Conservative on the destructive side: with the suggested daily cadence, a
#: delivered row (address + already-used one-time code) lives three to four
#: days -- far past every OTP's 15-minute expiry, long enough to answer "did my
#: verification email actually send on Friday?" on Monday, and short enough to
#: bound the PII hole the purge exists to close.  The beat task used 24h on an
#: hourly schedule; a daily cron gets a wider window so one missed run never
#: triples the backlog's age relative to its window.
OUTBOX_RETENTION_HOURS = 72


@outbox_cli.command("sweep")
@click.option(
    "--limit",
    default=500,
    show_default=True,
    help="Maximum rows attempted in this pass; anything beyond waits for the next run.",
)
def outbox_sweep(limit: int) -> None:
    """Retry unpublished outbox rows, respecting attempts and backoff.

    Selects rows that are unpublished, under MAX_ATTEMPTS, and old enough for
    their next try (outbox.RETRY_MIN_AGE), and publishes each one.  Rows whose
    send fails stay for the next sweep; that is a 0 exit.  Non-zero means the
    pass itself crashed.
    """
    from solverah.services import outbox

    counts = outbox.drain(limit=limit)
    depth = outbox.depth()
    click.echo(json.dumps({"event": "outbox_sweep", **counts, "outbox": depth}))


@retention_cli.command("run")
@click.option(
    "--outbox-hours",
    default=OUTBOX_RETENTION_HOURS,
    show_default=True,
    help="Delete outbox rows DELIVERED more than this many hours ago.",
)
@click.option(
    "--scoring-days",
    default=7,  # scoring_jobs.PURGE_DAYS; literal so the cron contract is visible here
    show_default=True,
    help="Delete terminal scoring_jobs rows older than this many days.",
)
@click.option(
    "--resume-days",
    default=30,  # resume_jobs.PURGE_DAYS; ditto
    show_default=True,
    help="Delete terminal resume_parse_jobs rows older than this many days.",
)
def retention_run(outbox_hours: int, scoring_days: int, resume_days: int) -> None:
    """Purge rows whose retention window has passed.  Deletes are narrow by design:

    * outbox: only rows that are BOTH delivered (published_at set) AND older
      than the window.  Pending and parked rows are never touched -- they are
      email still owed.
    * scoring_jobs / resume_parse_jobs: only terminal (succeeded/failed) rows
      past their window.  Queued/running rows belong to the reapers, not here.

    No foreign key references any of the three tables, so nothing cascades.
    Prints what it deleted; exits non-zero only if the pass itself crashed.
    """
    from solverah.services import outbox, resume_jobs, scoring_jobs

    summary = {
        "event": "retention_run",
        "outbox_deleted": outbox.purge_published(older_than_hours=outbox_hours),
        "outbox_window_hours": outbox_hours,
        "scoring_jobs_deleted": scoring_jobs.purge_terminal(older_than_days=scoring_days),
        "scoring_window_days": scoring_days,
        "resume_jobs_deleted": resume_jobs.purge_terminal(older_than_days=resume_days),
        "resume_window_days": resume_days,
    }
    click.echo(json.dumps(summary))


def register_cli(app) -> None:
    """Attach the operational command groups to *app*'s CLI."""
    app.cli.add_command(outbox_cli)
    app.cli.add_command(retention_cli)
