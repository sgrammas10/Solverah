"""Operational CLI commands -- the cron half of Scenario A.

Production (PROD_READINESS_2026-09_ANSWERS.md) is one Render web service and a
Postgres database: no Redis, no Celery worker, no beat.  Everything in
``BEAT_SCHEDULE`` is therefore dead in production, and two of those jobs are
load-bearing: the outbox sweep is what turns "the inline send failed once" into
"sent a few minutes later" instead of "never sent", and the retention purge is
what stops delivered outbox rows -- addresses and one-time codes -- and dead
refresh-session rows accumulating forever.

These commands are those two jobs as Flask CLI entry points, so a separate
Render **Cron Job** service can run them with nothing but the repo and the
dashboard env vars:

    flask outbox sweep         # suggested: every 5 minutes
    flask retention run        # suggested: daily
    flask backups run          # suggested: daily, 03:30 UTC
    flask pulse send-prompts   # suggested: daily (BUILD_PLAN B-2)

``pulse send-prompts`` is the newest of the four and not load-bearing the way
the first two are -- nothing breaks if a run is skipped, a due user is simply
prompted on the next one -- but it shares the same idempotency shape (see
``solverah.services.pulse_cadence_service``) and the same reason for being a
cron entry point rather than a beat task.

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

``backups run`` draws that line in the same place and lands on the other side of
it: there is no "individual row" in a backup pass, so a failed dump, a dump that
will not verify, or a failed upload IS the pass failing and must page.  What
does *not* page is a prune refusal -- the retention rails declining to delete are
the system working, reported in the JSON line at exit 0.

Unlike the other two, ``backups run`` shells out to ``pg_dump``, so it runs on
the ``infra/docker/Dockerfile.backup`` image rather than Render's native Python
runtime, which guarantees no PostgreSQL client of any version.

Service imports happen inside the command bodies: this module is imported by the
factory, which must stay importable without pulling in ``model`` and the email
infrastructure.
"""

from __future__ import annotations

import json
import os

import click
from flask.cli import AppGroup

__all__ = ["backups_cli", "outbox_cli", "pulse_cli", "register_cli", "retention_cli"]

outbox_cli = AppGroup("outbox", help="Transactional-outbox operations (cron entry points).")
retention_cli = AppGroup("retention", help="Data-retention purges (cron entry points).")
backups_cli = AppGroup("backups", help="Database backups (cron entry point).")
pulse_cli = AppGroup("pulse", help="Pulse check-in cadence (cron entry point).")

#: The frontend origin the Pulse deep link is built against, when neither the
#: env var nor `--base-url` supplies one. Same value as `factory.py`'s
#: `PRODUCTION_CORS_ORIGINS`' apex entry -- there is no existing "the frontend's
#: base URL" setting to reuse (every email before this one sent an OTP code, not
#: a link), so this mirrors `solverah/infra/email.py`'s own style of a plain
#: `os.environ.get` rather than growing `solverah.config.Settings` for one value.
DEFAULT_APP_BASE_URL = "https://solverah.com"

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
@click.option(
    "--session-days",
    default=30,  # refresh_tokens.PURGE_DAYS; ditto
    show_default=True,
    help="Delete dead user_sessions rows older than this many days.",
)
def retention_run(
    outbox_hours: int, scoring_days: int, resume_days: int, session_days: int
) -> None:
    """Purge rows whose retention window has passed.  Deletes are narrow by design:

    * outbox: only rows that are BOTH delivered (published_at set) AND older
      than the window.  Pending and parked rows are never touched -- they are
      email still owed.
    * scoring_jobs / resume_parse_jobs: only terminal (succeeded/failed) rows
      past their window.  Queued/running rows belong to the reapers, not here.
    * user_sessions: only rows that are BOTH dead -- retired, or past
      ``expires_at`` -- AND older than the window.  A live session is somebody
      signed in right now, and deleting one signs them out with no event
      anywhere saying why.

    The sessions pass has two steps and the order is the point.  ``expire_stale``
    stamps ``retired_reason = 'expired'`` on rows whose ``expires_at`` has passed
    without anyone ever coming back for them -- which is most of them, since a
    token is only ever examined when it is presented -- so the audit trail says
    how each row died rather than leaving the majority blank.  The delete then
    applies one window to one column.  It stamps ``retired_at`` with the
    ``expires_at`` that already passed, never with the clock, so a row whose
    window is long gone is stamped and removed in the same pass instead of
    being granted a fresh thirty days for having been noticed.

    ``user_sessions`` has two self-referencing foreign keys (parent/successor),
    both ``ON DELETE SET NULL``, so deleting an old row breaks a link and takes
    nothing with it.  No other table references any of the four.

    Prints what it deleted; exits non-zero only if the pass itself crashed.
    """
    from solverah.services import outbox, refresh_tokens, resume_jobs, scoring_jobs

    summary = {
        "event": "retention_run",
        "outbox_deleted": outbox.purge_published(older_than_hours=outbox_hours),
        "outbox_window_hours": outbox_hours,
        "scoring_jobs_deleted": scoring_jobs.purge_terminal(older_than_days=scoring_days),
        "scoring_window_days": scoring_days,
        "resume_jobs_deleted": resume_jobs.purge_terminal(older_than_days=resume_days),
        "resume_window_days": resume_days,
        "sessions_expired": refresh_tokens.expire_stale(),
        "sessions_deleted": refresh_tokens.purge_terminal(older_than_days=session_days),
        "session_window_days": session_days,
    }
    click.echo(json.dumps(summary))


@backups_cli.command("run")
@click.option(
    "--retention-days",
    default=None,
    type=click.IntRange(min=1),
    help="Delete artifacts older than this many days (default: 30).",
)
@click.option(
    "--min-retained",
    default=None,
    type=click.IntRange(min=1),
    help="Refuse to prune at all if fewer than this many artifacts would remain "
    "(default: 7).",
)
@click.option(
    "--prefix",
    default=None,
    help="Key prefix to write under and prune within (default: daily/).",
)
@click.option(
    "--local-dir",
    default=None,
    type=click.Path(file_okay=False),
    help="REHEARSAL ONLY: store artifacts in this directory instead of the backup "
    "bucket. Refused when APP_ENV is production.",
)
@click.option(
    "--timeout-seconds",
    default=None,
    type=click.IntRange(min=1),
    help="Ceiling on the pg_dump and pg_restore invocations (default: 1800).",
)
def backups_run(
    retention_days: int,
    min_retained: int,
    prefix: str,
    local_dir: str,
    timeout_seconds: int,
) -> None:
    """Dump the database, verify it, upload it, and prune what has expired.

    One pass, in that order, and the order is the safety property: nothing is
    uploaded that ``pg_restore --list`` could not read, and nothing is deleted
    until a verified artifact is in the store beside it.

    Exits non-zero if the dump, the verification, the upload, or a delete fails
    -- all four are the pass failing, and cron alerting keys on that.  A prune
    the retention rails refuse (too few artifacts, a listing that does not
    contain what was just uploaded) exits 0 with ``prune_refused`` explaining
    itself: a bucket in its first week prunes nothing, every day, correctly.
    """
    import tempfile

    from flask import current_app

    from solverah.infra import backup_storage
    from solverah.services import backups

    settings = current_app.extensions["solverah_settings"]

    if local_dir:
        # The rehearsal store writes to whatever disk the process is on, which
        # on a Render cron is ephemeral and gone when the job exits. Producing a
        # green JSON line and no backup is the exact failure this whole command
        # exists to end, so production cannot reach it by flag or by accident.
        if settings.is_production:
            raise click.ClickException(
                "--local-dir is a rehearsal aid and is refused when APP_ENV is "
                "production: a backup on a cron container's ephemeral disk is not "
                "a backup. Configure BACKUP_S3_* and run without the flag."
            )
        store = backup_storage.local_backup_store(local_dir)
    else:
        try:
            store = backup_storage.s3_backup_store(settings)
        except backup_storage.BackupStorageError as exc:
            # A destination-less pass is a failed pass, not a quiet no-op: a
            # daily job reporting success while storing nothing is how a backup
            # gap survives to the restore.
            raise click.ClickException(str(exc)) from exc

    # Every option defaults to None and unset ones are dropped, so the policy's
    # own constants stay the single definition of the defaults -- click cannot
    # show them with `show_default` here because importing the service at module
    # scope is what this module's header rules out.
    kwargs = {
        "prefix": prefix,
        "retention_days": retention_days,
        "min_retained": min_retained,
        "timeout_seconds": timeout_seconds,
    }
    with tempfile.TemporaryDirectory(prefix="solverah-backup-") as work_dir:
        summary = backups.run_backup(
            store,
            settings.database_url,
            work_dir=work_dir,
            **{k: v for k, v in kwargs.items() if v is not None},
        )

    click.echo(json.dumps(summary))


@pulse_cli.command("send-prompts")
@click.option(
    "--base-url",
    default=None,
    help="Frontend origin for the deep link (default: $APP_BASE_URL or %r)."
    % DEFAULT_APP_BASE_URL,
)
def pulse_send_prompts(base_url: str) -> None:
    """Email every confirmed-email user whose Pulse cadence says they are due.

    Idempotent, same contract as `outbox sweep`: a re-run within the same
    cadence window emails nobody twice, because due-ness is `last_prompted_at`
    plus the cadence interval, and that timestamp is only ever set once a
    prompt's outbox row and it commit together (`pulse_cadence_service`'s
    docstring). Exits non-zero only if the pass itself crashed; an individual
    send failing is the outbox's normal weather and is retried by the next
    `outbox sweep`, not by this command.
    """
    from solverah.services import pulse_cadence_service

    resolved_base_url = base_url or os.environ.get("APP_BASE_URL", DEFAULT_APP_BASE_URL)
    summary = pulse_cadence_service.send_due_prompts(base_url=resolved_base_url)
    click.echo(json.dumps({"event": "pulse_send_prompts", **summary}))


def register_cli(app) -> None:
    """Attach the operational command groups to *app*'s CLI."""
    app.cli.add_command(outbox_cli)
    app.cli.add_command(retention_cli)
    app.cli.add_command(backups_cli)
    app.cli.add_command(pulse_cli)
