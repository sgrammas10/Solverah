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
    flask corpus build         # suggested: quarterly (BUILD_PLAN F-1)
    flask corpus zones         # 11 requests; refreshes the Job Zone sidecar
    flask corpus clusters      # no network; refreshes the fresh_start seed
    flask corpus experience    # ~2,800 requests, resumable; the wants layer's
                               # working-conditions sidecar (BUILD_PLAN W-3)
    flask corpus tasks         # no O*NET; the wants panel's eight tasks per job
                               # with plain-words labels (BUILD_PLAN W-3)
    flask corpus summaries     # no network; one O*NET sentence per card (W-18)

``pulse send-prompts`` is the newest of the four cron jobs and not load-bearing
the way the first two are -- nothing breaks if a run is skipped, a due user is
simply prompted on the next one -- but it shares the same idempotency shape (see
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

``corpus build`` is the odd one out of the five and says so up front: it touches
no database and no email, and it is the only command here that spends money at a
provider.  It lives in this module for the reason
``docs/PATH_INTELLIGENCE_REDESIGN.md`` §2.1 gives -- O*NET content changes
quarterly, so refreshing the occupation corpus should be a scheduled job rather
than something somebody remembers to run on a laptop.  It draws the pass/fail
line where ``backups run`` does, not where ``outbox sweep`` does: a partial
corpus would be loaded and trusted for a quarter, so a build that cannot fetch
its catalog refuses to write anything and exits non-zero.

Service imports happen inside the command bodies: this module is imported by the
factory, which must stay importable without pulling in ``model`` and the email
infrastructure.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import click
from flask.cli import AppGroup

__all__ = [
    "backups_cli",
    "corpus_cli",
    "outbox_cli",
    "pulse_cli",
    "register_cli",
    "retention_cli",
]

outbox_cli = AppGroup("outbox", help="Transactional-outbox operations (cron entry points).")
retention_cli = AppGroup("retention", help="Data-retention purges (cron entry points).")
backups_cli = AppGroup("backups", help="Database backups (cron entry point).")
pulse_cli = AppGroup("pulse", help="Pulse check-in cadence (cron entry point).")
corpus_cli = AppGroup("corpus", help="O*NET occupation vector corpus (BUILD_PLAN F-1).")

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


@corpus_cli.command("build")
@click.option(
    "--out-dir",
    default=None,
    help="Directory for the .npy, sidecar and checkpoint "
    "(default: $SOLVERAH_CORPUS_DIR). Keep it OUTSIDE the repo.",
)
@click.option("--version", default=None, help="Filename version stamp (default: UTC date).")
@click.option(
    "--limit",
    default=None,
    type=int,
    help="Only build the first N occupations by code -- for smoke runs.",
)
@click.option(
    "--rate",
    default=None,
    type=float,
    show_default="4.0/s",
    help="Aggregate O*NET requests per second. O*NET's documented threshold is 5.",
)
@click.option(
    "--workers",
    default=4,
    show_default=True,
    type=int,
    help="Concurrent fetchers. Hides latency; --rate still bounds the request rate.",
)
@click.option(
    "--resume/--no-resume",
    default=True,
    show_default=True,
    help="Reuse role documents already in the checkpoint file.",
)
@click.option("--checkpoint", default=None, help="Override the checkpoint file path.")
def corpus_build(
    out_dir: str | None,
    version: str | None,
    limit: int | None,
    rate: float | None,
    workers: int,
    resume: bool,
    checkpoint: str | None,
) -> None:
    """Build the precomputed O*NET occupation vector corpus.

    Enumerates the whole O*NET catalog (~1,016 occupations), fetches each one's
    description, tasks and hot technologies, composes a role document, embeds it
    with text-embedding-3-small and writes a float32 matrix plus a JSON sidecar
    mapping row index to O*NET code.

    ~3,070 O*NET requests and ~13 minutes at the default rate; the O*NET Terms
    of Service put the threshold at 5 requests/second and 50,000/day.  The run
    is resumable -- fetched documents are checkpointed as they arrive, so a
    re-run after a trip costs only what it had not already fetched.

    Writes local files only.  Uploading the artifact is F-3's, and deliberately
    not wired here: Sebastian reviews a corpus before it goes anywhere.

    Exit codes follow this module's convention.  Unlike `outbox sweep`, a
    partial pass is NOT a success: an artifact with a hole in it would be
    loaded and trusted for a quarter, so the builder refuses to write one and
    exits non-zero.
    """
    from backend.services import occupation_corpus
    from backend.services.onet_client import OnetClient
    from solverah.infra.llm import get_openai_client

    resolved_out_dir = out_dir or os.environ.get("SOLVERAH_CORPUS_DIR")
    if not resolved_out_dir:
        raise click.ClickException(
            "No output directory. Pass --out-dir or set SOLVERAH_CORPUS_DIR. "
            "There is deliberately no default: the artifact is ~6 MB of binary "
            "and must not land in the repo tree."
        )

    try:
        onet_client = OnetClient()
        openai_client = get_openai_client()
    except (RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        build = occupation_corpus.build_corpus(
            out_dir=resolved_out_dir,
            onet_client=onet_client,
            openai_client=openai_client,
            version=version,
            limit=limit,
            requests_per_second=(
                rate if rate is not None else occupation_corpus.DEFAULT_REQUESTS_PER_SECOND
            ),
            workers=workers,
            resume=resume,
            checkpoint_path=checkpoint,
            on_progress=lambda message: click.echo(message, err=True),
        )
    except occupation_corpus.CorpusBuildError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(json.dumps(build.summary()))
    # Returned as well as echoed so `corpus refresh` can chain the zone,
    # cluster and publish steps onto the artifact this run actually produced,
    # rather than re-deriving the filename from a date and hoping they agree.
    # Click ignores a command's return value; `ctx.invoke` passes it through.
    return build


@corpus_cli.command("zones")
@click.option(
    "--corpus",
    default=None,
    help="The .npy artifact, or a directory holding one "
    "(default: $SOLVERAH_CORPUS_PATH, then $SOLVERAH_CORPUS_DIR).",
)
@click.option(
    "--rate",
    default=None,
    type=float,
    show_default="4.0/s",
    help="Aggregate O*NET requests per second. O*NET's documented threshold is 5.",
)
def corpus_zones(corpus: str | None, rate: float | None) -> None:
    """Write the Job Zone sidecar beside an existing corpus artifact.

    Job Zone is the education/training a career demands, and BUILD_PLAN F-3
    applies it as a hard feasibility filter at retrieval.  It is not in the
    corpus artifact: `/online/occupations` pages the whole catalog and carries
    a zone on most records, so this is **11 O*NET requests**, against 1,016 for
    `get_job_zone` per occupation.

    Coverage is not total -- measured 2026-09-16, 923 of 1,016 rows carry one.
    The 93 without are the "..., All Other" residuals, which retrieval filters
    out anyway, plus 18 real occupations, 17 of them the military group.  A
    row with no zone is excluded whenever a ceiling is asked for; see
    `occupation_retrieval.zone_within_ceiling`.

    Writes `<artifact>.zones.json` and touches neither the .npy nor its
    sidecar -- see `occupation_retrieval.write_zone_sidecar` for why that
    separation is deliberate rather than incidental.

    Cheap enough to re-run on its own cadence; it does not need a corpus
    rebuild and a corpus rebuild does not need it.
    """
    from backend.services import occupation_corpus, occupation_retrieval
    from backend.services.onet_client import OnetAPIError, OnetClient, OnetRateLimitError

    resolved = (
        corpus
        or os.environ.get("SOLVERAH_CORPUS_PATH")
        or os.environ.get("SOLVERAH_CORPUS_DIR")
    )
    if not resolved:
        raise click.ClickException(
            "No corpus artifact. Pass --corpus or set SOLVERAH_CORPUS_PATH."
        )

    try:
        matrix_path = occupation_retrieval.resolve_matrix_path(resolved)
    except occupation_retrieval.CorpusUnavailable as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        onet_client = OnetClient()
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    limiter = occupation_corpus.RateLimiter(
        rate if rate is not None else occupation_corpus.DEFAULT_REQUESTS_PER_SECOND
    )
    try:
        zones = occupation_retrieval.fetch_job_zones(
            onet_client,
            limiter=limiter,
            on_progress=lambda message: click.echo(message, err=True),
        )
    except (OnetAPIError, OnetRateLimitError) as exc:
        raise click.ClickException(f"O*NET request failed: {exc}") from exc

    if not zones:
        raise click.ClickException(
            "O*NET returned no job zones; refusing to write an empty sidecar."
        )

    path = occupation_retrieval.write_zone_sidecar(matrix_path, zones)
    click.echo(
        json.dumps(
            {
                "event": "corpus_zones",
                "matrix_path": str(matrix_path),
                "zones_path": str(path),
                "occupations": len(zones),
                "onet_requests": limiter.count,
            }
        )
    )


@corpus_cli.command("clusters")
@click.option(
    "--corpus",
    default=None,
    help="The .npy artifact, or a directory holding one "
    "(default: $SOLVERAH_CORPUS_PATH, then $SOLVERAH_CORPUS_DIR).",
)
@click.option(
    "--k",
    default=None,
    type=int,
    show_default="occupation_clusters.CLUSTER_COUNT",
    help="How many regions to cut the corpus into.",
)
@click.option(
    "--show/--no-show",
    default=True,
    help="Print the three titles nearest each centroid.",
)
def corpus_clusters(corpus: str | None, k: int | None, show: bool) -> None:
    """Write the k-means cluster sidecar beside an existing corpus artifact.

    BUILD_PLAN F-7: `fresh_start` has no occupation anchor to retrieve around,
    so its first page is one occupation per region of the corpus.  This is that
    partition, precomputed.

    **Makes no network calls and spends nothing.**  It reads the artifact,
    fits k-means over the retrievable rows and writes
    `<artifact>.clusters.json`; the O*NET catalog and the embedding model are
    not involved, which is why it is safe to re-run at will.  Re-run it after
    every `corpus build` -- the sidecar names occupations by code, and a build
    that adds one leaves this file stale, which
    `occupation_clusters.get_assignment` detects and works around at the cost of
    a ~0.7 s fit in every worker.

    `--show` prints the three titles nearest each centroid, because a seed is
    only as meaningful as the partition under it and a k-means over documents
    can cluster on length or boilerplate instead of on occupational domain.
    Look at the output before trusting it.
    """
    from backend.services import occupation_clusters, occupation_retrieval

    resolved = (
        corpus
        or os.environ.get("SOLVERAH_CORPUS_PATH")
        or os.environ.get("SOLVERAH_CORPUS_DIR")
    )
    if not resolved:
        raise click.ClickException(
            "No corpus artifact. Pass --corpus or set SOLVERAH_CORPUS_PATH."
        )

    try:
        matrix_path = occupation_retrieval.resolve_matrix_path(resolved)
        loaded = occupation_retrieval.load_corpus(matrix_path)
    except occupation_retrieval.CorpusUnavailable as exc:
        raise click.ClickException(str(exc)) from exc

    assignment = occupation_clusters.compute_assignment(
        loaded, k=k or occupation_clusters.CLUSTER_COUNT
    )
    path = occupation_clusters.write_cluster_sidecar(matrix_path, assignment)

    if show:
        for row in occupation_clusters.summarise(loaded, assignment):
            click.echo(
                "  cluster %-2s n=%-4s %s"
                % (row["cluster"], row["size"], "; ".join(row["titles"])),
                err=True,
            )

    click.echo(
        json.dumps(
            {
                "event": "corpus_clusters",
                "matrix_path": str(matrix_path),
                "clusters_path": str(path),
                "k": assignment.k,
                "occupations": assignment.count,
            }
        )
    )



@corpus_cli.command("experience")
@click.option(
    "--corpus",
    default=None,
    help="The .npy artifact, or a directory holding one "
    "(default: $SOLVERAH_CORPUS_PATH, then $SOLVERAH_CORPUS_DIR).",
)
@click.option(
    "--from-raw",
    default=None,
    type=click.Path(exists=True, dir_okay=False),
    help="Build from an already-fetched JSONL of O*NET reports instead of "
    "calling O*NET.  One {code, title, reports} record per line.",
)
@click.option(
    "--checkpoint",
    default=None,
    type=click.Path(),
    help="Where the fetch appends each occupation's reports as it goes "
    "(default: <artifact>.experience.raw.jsonl).  Re-running resumes from it.",
)
@click.option(
    "--rate",
    default=None,
    type=float,
    show_default="4.0/s",
    help="Aggregate O*NET requests per second. O*NET's documented threshold is 5.",
)
def corpus_experience(
    corpus: str | None,
    from_raw: str | None,
    checkpoint: str | None,
    rate: float | None,
) -> None:
    """Write the working-conditions sidecar beside an existing corpus artifact.

    BUILD_PLAN W-3: a user can say what should change about their day -- more
    people, less public, more desk -- and this is what the scorer measures a
    candidate occupation against.  The axes are small bundles of O*NET
    work-context elements stored as percentile ranks across the corpus; see
    `backend.services.occupation_conditions` for why bundles and why
    percentiles.

    **Three O*NET requests per occupation, so ~2,800 for the catalog** -- an
    order of magnitude more than `corpus zones` and the reason this one
    checkpoints: every occupation is appended to the raw JSONL as it completes
    and a re-run skips what is already there, so a run that dies at request
    2,000 costs the remaining 800 and not all 2,800.

    `--from-raw` skips the network entirely and builds from a JSONL somebody
    already fetched, which is how the first build was made (the W-3 prototype's
    939-occupation pull, 0 API errors).  Prefer it: this data changes when O*NET
    re-rates an occupation, which is quarterly at most.

    Writes `<artifact>.experience.json` and touches neither the .npy nor any
    other sidecar.
    """
    from backend.services import occupation_conditions, occupation_retrieval

    resolved = (
        corpus
        or os.environ.get("SOLVERAH_CORPUS_PATH")
        or os.environ.get("SOLVERAH_CORPUS_DIR")
    )
    if not resolved:
        raise click.ClickException(
            "No corpus artifact. Pass --corpus or set SOLVERAH_CORPUS_PATH."
        )

    try:
        matrix_path = occupation_retrieval.resolve_matrix_path(resolved)
        loaded = occupation_retrieval.load_corpus(matrix_path)
    except occupation_retrieval.CorpusUnavailable as exc:
        raise click.ClickException(str(exc)) from exc

    onet_requests = 0
    if from_raw:
        rows: list = list(occupation_conditions.iter_raw_rows(from_raw))
        source = Path(from_raw).name
    else:
        raw_path = Path(checkpoint) if checkpoint else matrix_path.with_name(
            matrix_path.stem + ".experience.raw.jsonl"
        )
        rows, onet_requests = _fetch_experience_reports(loaded, raw_path, rate)
        source = raw_path.name

    table = occupation_conditions.build_table(rows, source=source)
    if not table.count:
        raise click.ClickException(
            "no occupation carried a work-context rating; refusing to write an "
            "empty sidecar."
        )

    path = occupation_conditions.write_conditions_sidecar(matrix_path, table)
    click.echo(
        json.dumps(
            {
                "event": "corpus_experience",
                "matrix_path": str(matrix_path),
                "experience_path": str(path),
                "occupations": table.count,
                "coverage": {
                    axis: table.coverage(axis)
                    for axis in occupation_conditions.AXIS_NAMES
                },
                "onet_requests": onet_requests,
            }
        )
    )


def _fetch_experience_reports(
    loaded, raw_path: Path, rate: float | None
) -> tuple[list, int]:
    """Fetch every occupation's reports, appending to *raw_path* as it goes.

    Split out of the command body so the command stays the shape its siblings
    have -- resolve, call a service, write, echo JSON -- with the resumability
    bookkeeping (what is already on disk, what to append) in one place.
    """
    from backend.services import occupation_conditions, occupation_corpus
    from backend.services.onet_client import OnetAPIError, OnetClient, OnetRateLimitError
    from backend.services.occupation_retrieval import is_all_other_title

    try:
        onet_client = OnetClient()
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    done: list[str] = []
    rows: list = []
    if raw_path.exists():
        rows = list(occupation_conditions.iter_raw_rows(raw_path))
        done = [str(row.get("code")) for row in rows]
        click.echo(f"resuming: {len(done)} occupations already fetched", err=True)

    # "..., All Other" rows are skipped: retrieval never returns one, so three
    # requests each would buy nothing but rate limit.
    wanted = [
        (code, title)
        for code, title in zip(loaded.codes, loaded.titles)
        if not is_all_other_title(title)
    ]
    limiter = occupation_corpus.RateLimiter(
        rate if rate is not None else occupation_corpus.DEFAULT_REQUESTS_PER_SECOND
    )

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("a", encoding="utf-8") as handle:

        def _append(record: dict) -> None:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
            handle.flush()

        try:
            fetched = occupation_conditions.fetch_condition_reports(
                onet_client,
                wanted,
                limiter=limiter,
                already_done=done,
                on_record=_append,
                on_progress=lambda message: click.echo(message, err=True),
            )
        except OnetRateLimitError as exc:
            raise click.ClickException(
                f"O*NET rate limit hit: {exc}.  {raw_path} holds what was "
                "fetched; re-run to resume."
            ) from exc
        except OnetAPIError as exc:
            raise click.ClickException(f"O*NET request failed: {exc}") from exc

    return rows + fetched, limiter.count


@corpus_cli.command("fit")
@click.option(
    "--corpus",
    default=None,
    help="The .npy artifact, or a directory holding one "
    "(default: $SOLVERAH_CORPUS_PATH, then $SOLVERAH_CORPUS_DIR).",
)
@click.option(
    "--limit",
    default=None,
    type=int,
    help="Only the first N retrievable occupations. For a dry sample before "
    "spending the ~3,800 requests a full run costs.",
)
@click.option(
    "--checkpoint",
    default=None,
    type=click.Path(),
    help="Where each occupation's four answers are appended as they arrive "
    "(default: a scratch file under the system temp directory). "
    "Re-running resumes from it and does not re-fetch finished occupations.",
)
@click.option(
    "--rate",
    default=None,
    type=float,
    show_default="4.0/s",
    help="Aggregate O*NET requests per second. O*NET's documented threshold is 5.",
)
def corpus_fit(
    corpus: str | None,
    limit: int | None,
    checkpoint: str | None,
    rate: float | None,
) -> None:
    """Write the deep-fit sidecar beside an existing corpus artifact.

    BUILD_PLAN W-9.  Opening a card runs `path_deep_fit.deep_fit`, whose first
    act is four live O*NET calls for the clicked occupation -- measured at
    2,384 ms cold and 844 ms with the client's own 24h cache warm.  Everything
    those calls return is static per occupation, so this fetches all of it once
    and writes it beside the artifact; after that a click costs zero O*NET
    requests.  See `backend.services.occupation_fit` for what is stored and why
    it is stored unfiltered.

    **Four O*NET requests per occupation, so ~3,800 for the catalog** (~16
    minutes at the default 4/s, under O*NET's documented threshold of 5).  That
    is why this checkpoints: every occupation is appended to the JSONL as it
    completes and a re-run skips what is already there, so a run that dies at
    request 3,000 costs the remaining 800 and not all 3,800.

    "..., All Other" rows are skipped -- retrieval never returns one and
    `deep_fit` refuses a click on one, so four requests each would buy nothing
    but rate limit.

    Writes `<artifact>.fit.json` and touches neither the .npy nor any other
    sidecar.
    """
    import tempfile

    from backend.services import occupation_fit, occupation_retrieval

    resolved = (
        corpus
        or os.environ.get("SOLVERAH_CORPUS_PATH")
        or os.environ.get("SOLVERAH_CORPUS_DIR")
    )
    if not resolved:
        raise click.ClickException(
            "No corpus artifact. Pass --corpus or set SOLVERAH_CORPUS_PATH."
        )

    try:
        matrix_path = occupation_retrieval.resolve_matrix_path(resolved)
        loaded = occupation_retrieval.load_corpus(matrix_path)
    except occupation_retrieval.CorpusUnavailable as exc:
        raise click.ClickException(str(exc)) from exc

    # Beside the artifact would put a half-finished fetch log inside a published
    # artifact set that `corpus publish` enumerates -- the judgement
    # `_checkpointed_labeller` already makes for `corpus tasks`.
    raw_path = (
        Path(checkpoint)
        if checkpoint
        else Path(tempfile.gettempdir()) / "solverah" / f"{matrix_path.stem}.fit.raw.jsonl"
    )
    rows, onet_requests = _fetch_occupation_fits(loaded, raw_path, rate, limit)

    table = occupation_fit.build_table(rows, source=raw_path.name)
    if not table.count:
        raise click.ClickException(
            "no occupation carried a single O*NET answer; refusing to write an "
            "empty sidecar."
        )

    path = occupation_fit.write_fit_sidecar(matrix_path, table)
    click.echo(
        json.dumps(
            {
                "event": "corpus_fit",
                "matrix_path": str(matrix_path),
                "fit_path": str(path),
                "checkpoint": str(raw_path),
                "occupations": table.count,
                "complete": table.complete_count,
                "partial": table.count - table.complete_count,
                "onet_requests": onet_requests,
                "bytes": path.stat().st_size,
            }
        )
    )


def _fetch_occupation_fits(
    loaded, raw_path: Path, rate: float | None, limit: int | None
) -> tuple[list, int]:
    """Fetch every occupation's four answers, appending to *raw_path* as it goes.

    Split out of the command body for the reason `_fetch_experience_reports` is:
    the command keeps the shape its siblings have -- resolve, call a service,
    write, echo JSON -- and the resumability bookkeeping lives in one place.

    Checkpoint rows for codes that are NOT in this run's wanted set are dropped
    rather than carried into the table.  That is what makes `--limit` a sample
    of the catalog rather than "the sample plus whatever an earlier full run
    left in the file", and it also stops a rebuilt corpus's retired codes
    surviving in the sidecar.
    """
    from backend.services import occupation_corpus, occupation_fit
    from backend.services.onet_client import OnetClient, OnetRateLimitError
    from backend.services.occupation_retrieval import is_all_other_title

    try:
        onet_client = OnetClient()
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    wanted = [
        (code, title)
        for code, title in zip(loaded.codes, loaded.titles)
        if not is_all_other_title(title)
    ]
    if limit is not None:
        wanted = wanted[:limit]
    wanted_codes = {code for code, _ in wanted}

    rows: list = []
    if raw_path.exists():
        rows = [
            row
            for row in occupation_fit.iter_raw_rows(raw_path)
            if str(row.get("code")) in wanted_codes
        ]
        click.echo(f"resuming: {len(rows)} occupations already fetched", err=True)
    done = {str(row.get("code")) for row in rows}

    limiter = occupation_corpus.RateLimiter(
        rate if rate is not None else occupation_corpus.DEFAULT_REQUESTS_PER_SECOND
    )

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    fetched: list = []
    with raw_path.open("a", encoding="utf-8") as handle:
        try:
            for index, (code, title) in enumerate(wanted, start=1):
                if code in done:
                    continue
                record = occupation_fit.record_payload(
                    code,
                    title,
                    occupation_fit.fetch_occupation_fit(
                        onet_client, code, limiter=limiter
                    ),
                )
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")
                handle.flush()
                fetched.append(record)
                if index % 25 == 0:
                    click.echo(
                        f"  {index}/{len(wanted)} occupations, "
                        f"{limiter.count} requests",
                        err=True,
                    )
        except OnetRateLimitError as exc:
            raise click.ClickException(
                f"O*NET rate limit hit: {exc}.  {raw_path} holds what was "
                "fetched; re-run to resume."
            ) from exc

    return rows + fetched, limiter.count


@corpus_cli.command("tasks")
@click.option(
    "--corpus",
    default=None,
    help="The .npy artifact, or a directory holding one "
    "(default: $SOLVERAH_CORPUS_PATH, then $SOLVERAH_CORPUS_DIR).",
)
@click.option(
    "--documents",
    default=None,
    type=click.Path(exists=True, dir_okay=False),
    help="The corpus documents JSONL (default: <artifact>.documents.jsonl).",
)
@click.option(
    "--labels/--no-labels",
    default=True,
    show_default=True,
    help="Write plain-words display labels with one offline LLM pass. "
    "--no-labels writes each O*NET statement as its own label and costs nothing.",
)
@click.option(
    "--limit",
    default=None,
    type=int,
    help="Only the first N occupations. For pricing a full run from a sample.",
)
@click.option(
    "--checkpoint",
    default=None,
    type=click.Path(),
    help="Where each occupation's labels are appended as they are written "
    "(default: a scratch file under the system temp directory). "
    "Re-running resumes from it and does not re-pay for finished occupations.",
)
def corpus_tasks(
    corpus: str | None,
    documents: str | None,
    labels: bool,
    limit: int | None,
    checkpoint: str | None,
) -> None:
    """Write the panel-tasks sidecar beside an existing corpus artifact.

    BUILD_PLAN W-3: W-4's panel shows the user their own job's tasks and asks
    *more / less* about each.  O*NET gives an occupation 5 to 41 statements, so
    this picks up to eight **chosen for spread** -- eight paraphrases of the same
    duty collect one bit of information eight times -- and writes a plain-words
    display label beside each.  See `backend.services.occupation_tasks` for why
    spread and why the original statement is kept byte-exact.

    **No O*NET requests at all**: the task lists are already in the corpus
    documents file `corpus build` wrote.  The two costs are embeddings for the
    selection (~$0.01 for the catalog) and, with `--labels`, one `gpt-4o-mini`
    completion per occupation.

    **Price it before you pay it.**  `--limit 25 --labels` labels 25
    occupations, measures their real token usage and projects the full run in
    the `cost` block it echoes.  The labels are checkpointed per occupation, so
    the sample is not wasted: the full run resumes over it.

    Writes `<artifact>.tasks.json` and touches neither the .npy nor any other
    sidecar.
    """
    from backend.services import occupation_retrieval, occupation_tasks

    resolved = (
        corpus
        or os.environ.get("SOLVERAH_CORPUS_PATH")
        or os.environ.get("SOLVERAH_CORPUS_DIR")
    )
    if not resolved:
        raise click.ClickException(
            "No corpus artifact. Pass --corpus or set SOLVERAH_CORPUS_PATH."
        )

    try:
        matrix_path = occupation_retrieval.resolve_matrix_path(resolved)
    except occupation_retrieval.CorpusUnavailable as exc:
        raise click.ClickException(str(exc)) from exc

    docs_path = (
        Path(documents)
        if documents
        else occupation_tasks.documents_path_for(matrix_path)
    )
    if not docs_path.is_file():
        raise click.ClickException(
            f"no corpus documents at {docs_path}. Pass --documents, or re-run "
            "`flask corpus build` (it writes the JSONL beside the artifact)."
        )

    rows = list(occupation_tasks.iter_documents(docs_path))
    retrievable = sum(
        1
        for row in rows
        if not occupation_retrieval.is_all_other_title(str(row.get("title") or ""))
    )
    if limit is not None:
        rows = rows[:limit]

    # One client, two jobs: the embeddings that choose the eight, and (with
    # --labels) the completions that describe them.  Required either way --
    # selection without an embedder would be "O*NET's first eight", which is
    # the crowded list this command exists to avoid.
    from solverah.infra.llm import get_openai_client

    try:
        openai_client = get_openai_client()
    except RuntimeError as exc:
        raise click.ClickException(
            f"{exc}. Selection needs the embeddings API even with --no-labels."
        ) from exc

    usage: dict[str, int] = {}
    labels_for = None
    close_checkpoint = lambda: None  # noqa: E731 -- a no-op, not a branch
    if labels:
        labels_for, close_checkpoint = _checkpointed_labeller(
            occupation_tasks, openai_client, matrix_path, checkpoint, usage
        )

    try:
        table = occupation_tasks.build_table(
            rows,
            openai_client,
            source=docs_path.name,
            with_labels=labels,
            labels_for=labels_for,
            usage=usage,
            on_progress=lambda message: click.echo(message, err=True),
        )
    finally:
        close_checkpoint()

    if not table.count:
        raise click.ClickException(
            "no retrievable occupation carried a task list; refusing to write "
            "an empty sidecar."
        )

    path = occupation_tasks.write_tasks_sidecar(matrix_path, table)
    click.echo(
        json.dumps(
            {
                "event": "corpus_tasks",
                "matrix_path": str(matrix_path),
                "tasks_path": str(path),
                "documents": str(docs_path),
                "occupations": table.count,
                "tasks_chosen": table.task_count,
                "labelled": labels,
                "label_fallbacks": table.label_fallbacks,
                "cost": occupation_tasks.project_label_cost(
                    usage, table.count, retrievable
                )
                if labels
                else None,
            }
        )
    )


@corpus_cli.command("summaries")
@click.option(
    "--corpus",
    default=None,
    help="The .npy artifact, or a directory holding one "
    "(default: $SOLVERAH_CORPUS_PATH, then $SOLVERAH_CORPUS_DIR).",
)
@click.option(
    "--documents",
    default=None,
    type=click.Path(exists=True, dir_okay=False),
    help="The corpus documents JSONL (default: <artifact>.documents.jsonl).",
)
@click.option(
    "--show",
    default=0,
    show_default=True,
    type=int,
    help="Print the N longest summaries (stderr), to read the cuts.",
)
def corpus_summaries(corpus: str | None, documents: str | None, show: int) -> None:
    """Write the one-sentence card summaries beside an existing corpus artifact.

    BUILD_PLAN W-18: each Path Intelligence card shows O*NET's own description
    of the occupation, first sentence only, under its title the moment the card
    appears -- before the narrator's personal sentence lands.

    **Makes no network calls and spends nothing.**  It reads the corpus
    documents file `corpus build` wrote beside the artifact and writes
    `<artifact>.summaries.json`; see `backend.services.occupation_summaries` for
    how a long sentence is cut.  `corpus refresh` runs it before publishing, so
    the summaries rebuild themselves with the corpus.
    """
    from backend.services import occupation_retrieval, occupation_summaries, occupation_tasks

    resolved = (
        corpus
        or os.environ.get("SOLVERAH_CORPUS_PATH")
        or os.environ.get("SOLVERAH_CORPUS_DIR")
    )
    if not resolved:
        raise click.ClickException(
            "No corpus artifact. Pass --corpus or set SOLVERAH_CORPUS_PATH."
        )

    try:
        matrix_path = occupation_retrieval.resolve_matrix_path(resolved)
    except occupation_retrieval.CorpusUnavailable as exc:
        raise click.ClickException(str(exc)) from exc

    docs_path = (
        Path(documents)
        if documents
        else occupation_tasks.documents_path_for(matrix_path)
    )
    if not docs_path.is_file():
        raise click.ClickException(
            f"no corpus documents at {docs_path}. Pass --documents, or re-run "
            "`flask corpus build` (it writes the JSONL beside the artifact)."
        )

    table = occupation_summaries.build_table(
        occupation_tasks.iter_documents(docs_path), source=docs_path.name
    )
    if not table.count:
        raise click.ClickException(
            "no retrievable occupation carried a description; refusing to write "
            "an empty sidecar."
        )
    path = occupation_summaries.write_summaries_sidecar(matrix_path, table)

    lengths = sorted(len(text) for text in table.summaries.values())
    if show > 0:
        longest = sorted(table.summaries.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        for code, text in longest[:show]:
            # ASCII-only: this console is cp1252 and O*NET prose is not.
            line = "  %s [%d] %s" % (code, len(text), text)
            click.echo(line.encode("ascii", "replace").decode("ascii"), err=True)

    click.echo(
        json.dumps(
            {
                "event": "corpus_summaries",
                "matrix_path": str(matrix_path),
                "summaries_path": str(path),
                "documents": str(docs_path),
                "occupations": table.count,
                "bytes": path.stat().st_size,
                "chars_p50": lengths[len(lengths) // 2],
                "chars_max": lengths[-1],
            }
        )
    )


def _checkpointed_labeller(occupation_tasks, openai_client, matrix_path, checkpoint, usage):
    """A `labels_for` that reads a checkpoint first and appends what it buys.

    Split out of the command body for the reason `_fetch_experience_reports` is:
    the command keeps the shape its siblings have -- resolve, call a service,
    write, echo JSON -- and the resumability bookkeeping lives in one place.

    The checkpoint defaults **outside the corpus directory**, unlike
    `corpus experience`'s raw file.  That directory is a published artifact set
    that a dev server and `corpus publish` both enumerate; a half-finished label
    log is scratch, and scratch does not belong in it.
    """
    import tempfile

    path = (
        Path(checkpoint)
        if checkpoint
        else Path(tempfile.gettempdir()) / "solverah" / f"{matrix_path.stem}.tasks.labels.jsonl"
    )
    done: dict[str, tuple[list[str], int]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            done[str(record["code"])] = (
                [str(text) for text in record["labels"]],
                int(record.get("fallbacks") or 0),
            )
        click.echo(f"resuming: {len(done)} occupations already labelled", err=True)

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a", encoding="utf-8")

    def labels_for(code: str, title: str, statements):
        # A checkpointed row is only reusable if it still lines up with the
        # statements being asked about: a rebuilt corpus can change which eight
        # were chosen, and reusing labels by position would silently put one
        # task's words beside another's text.
        cached = done.get(code)
        if cached is not None and len(cached[0]) == len(statements):
            return list(cached[0]), cached[1]
        result = occupation_tasks.label_occupation(
            openai_client, title, statements, usage=usage
        )
        handle.write(
            json.dumps(
                {"code": code, "labels": result[0], "fallbacks": result[1]},
                ensure_ascii=False,
            )
            + "\n"
        )
        handle.flush()
        return result

    return labels_for, handle.close


@corpus_cli.command("publish")
@click.option(
    "--corpus",
    default=None,
    help="The .npy artifact, or a directory holding one "
    "(default: $SOLVERAH_CORPUS_PATH, then $SOLVERAH_CORPUS_DIR).",
)
@click.option(
    "--prefix",
    default=None,
    help="Key prefix in the app bucket (default: $SOLVERAH_CORPUS_S3_PREFIX, "
    "then the directory part of $SOLVERAH_CORPUS_S3_KEY).",
)
@click.option(
    "--bucket",
    default=None,
    help="Override the app bucket (default: $S3_BUCKET_NAME). Never the backup bucket.",
)
@click.option(
    "--dry-run/--no-dry-run",
    default=False,
    show_default=True,
    help="Resolve and report without making ANY network call.",
)
def corpus_publish(
    corpus: str | None, prefix: str | None, bucket: str | None, dry_run: bool
) -> None:
    """Upload a built corpus artifact set to the app bucket.

    Four required objects -- the `.npy`, its sidecar, the zone sidecar and the
    cluster sidecar -- under `<prefix>/<filename>`, which is where
    `occupation_retrieval._fetch_from_s3` looks. All four are required; a
    partial upload would leave `zone_max` raising on every `adjacent` and
    `fresh_start` request, or every worker paying a k-means fit.

    **Plus W-3's two, when they are beside the artifact**: `*.experience.json`
    and `*.tasks.json` (`occupation_corpus.OPTIONAL_PUBLISHED_SUFFIXES`). They
    are carried rather than required because neither `corpus build` nor
    `corpus refresh` produces them, so demanding them would make the quarterly
    cadence unable to publish at all -- but a corpus published without them
    silently strips the wants layer of its data, which is what the corpus
    deploy dependency in `docs/RUNBOOK_DEPLOY_MAIN_MERGE.md` exists to catch.
    W-9's `*.fit.json` and W-18's `*.summaries.json` ride the same optional
    tier; `corpus refresh` does build the summaries (no network), so a refresh
    always carries that one. Count the objects in the echoed summary.

    **Versioned by filename and never overwriting.** A key that already exists
    with different bytes is a refusal: workers cache the artifact and never
    re-fetch it, so changing one in place splits the fleet across two corpora.
    Re-publishing identical bytes is a no-op, which is what makes a refresh that
    died halfway resumable.

    Publishing does NOT put the new corpus into service. The last step is
    setting `SOLVERAH_CORPUS_S3_KEY` to the key this command echoes, which is a
    deliberate separate act -- and the rollback.

    `--dry-run` makes no network call of any kind, not even a `head_object`.
    """
    from backend.services import occupation_corpus, occupation_retrieval

    resolved = (
        corpus
        or os.environ.get("SOLVERAH_CORPUS_PATH")
        or os.environ.get("SOLVERAH_CORPUS_DIR")
    )
    if not resolved:
        raise click.ClickException(
            "No corpus artifact. Pass --corpus or set SOLVERAH_CORPUS_PATH."
        )

    try:
        matrix_path = occupation_retrieval.resolve_matrix_path(resolved)
    except occupation_retrieval.CorpusUnavailable as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        published = occupation_corpus.publish_corpus(
            matrix_path,
            bucket=bucket or os.environ.get("S3_BUCKET_NAME", ""),
            key_prefix=prefix or occupation_corpus.default_key_prefix(),
            dry_run=dry_run,
            on_progress=lambda message: click.echo(message, err=True),
        )
    except occupation_corpus.CorpusBuildError as exc:
        raise click.ClickException(str(exc)) from exc
    except KeyError as exc:
        # `get_s3_client` reads S3_ENDPOINT_URL / S3_ACCESS_KEY_ID /
        # S3_SECRET_ACCESS_KEY straight out of os.environ. A missing one is an
        # operator error, and a bare KeyError traceback does not say which.
        raise click.ClickException(
            f"S3 is not configured: {exc} is unset. "
            "The app bucket's credentials are S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, "
            "S3_SECRET_ACCESS_KEY and S3_BUCKET_NAME."
        ) from exc

    click.echo(json.dumps(published.summary()))


@corpus_cli.command("refresh")
@click.option(
    "--out-dir",
    default=None,
    help="Directory for the new artifact (default: $SOLVERAH_CORPUS_DIR). "
    "Keep it OUTSIDE the repo.",
)
@click.option("--version", default=None, help="Filename version stamp (default: UTC date).")
@click.option(
    "--prefix",
    default=None,
    help="Key prefix in the app bucket (default: $SOLVERAH_CORPUS_S3_PREFIX, "
    "then the directory part of $SOLVERAH_CORPUS_S3_KEY).",
)
@click.option(
    "--rate",
    default=None,
    type=float,
    show_default="4.0/s",
    help="Aggregate O*NET requests per second. O*NET's documented threshold is 5.",
)
@click.option(
    "--workers",
    default=4,
    show_default=True,
    type=int,
    help="Concurrent fetchers. Hides latency; --rate still bounds the request rate.",
)
@click.option(
    "--resume/--no-resume",
    default=True,
    show_default=True,
    help="Reuse role documents already in the checkpoint file.",
)
@click.option(
    "--dry-run/--no-dry-run",
    default=False,
    show_default=True,
    help="Report the plan and make NO network call -- no O*NET, no OpenAI, no S3.",
)
@click.pass_context
def corpus_refresh(
    ctx: click.Context,
    out_dir: str | None,
    version: str | None,
    prefix: str | None,
    rate: float | None,
    workers: int,
    resume: bool,
    dry_run: bool,
) -> None:
    """The quarterly cadence: build, zones, clusters, summaries, publish.

    O*NET's content changes quarterly and an artifact nobody refreshes is a
    slowly rotting one, so this is the whole cycle as one command -- and as one
    Render cron entry (`render.yaml`, `docs/RUNBOOK_SCENARIO_A_CRON.md`).

    **It is the other four commands, invoked**, not a reimplementation of them.
    `ctx.invoke` means a change to `corpus build` cannot drift from what a
    refresh does, which a copied body would have allowed within one round.

    Cost: ~3,070 O*NET requests at the shared 4/s ceiling (~13 minutes), 11 more
    for the zones, ~$0.01 of embeddings, and no network at all for the clusters
    or the card summaries (W-18) -- the summaries are cut from the documents
    file the build just wrote, so they rebuild themselves with the corpus.
    Resumable by construction rather than by bookkeeping -- the build reuses its
    checkpoint, the zones and clusters are idempotent rewrites, and the publish
    skips objects already in the bucket byte-for-byte. A re-run after a trip
    costs only what had not already been done.

    **Refreshing does not deploy.** The new artifact goes up under a new
    date-stamped key and the one in service is untouched until somebody sets
    `SOLVERAH_CORPUS_S3_KEY` to the key this echoes. That is deliberate: it is
    the review gate, and the rollback.

    `--dry-run` makes NO network call of any kind and reports what the run would
    cost and where it would publish.
    """
    from backend.services import occupation_corpus, occupation_retrieval

    resolved_out_dir = out_dir or os.environ.get("SOLVERAH_CORPUS_DIR")
    if not resolved_out_dir:
        raise click.ClickException(
            "No output directory. Pass --out-dir or set SOLVERAH_CORPUS_DIR."
        )
    resolved_prefix = prefix or occupation_corpus.default_key_prefix()

    if dry_run:
        stamp = version or occupation_corpus.default_version()
        matrix_name = f"onet_corpus_{stamp}.npy"
        existing = (
            os.environ.get("SOLVERAH_CORPUS_PATH")
            or os.environ.get("SOLVERAH_CORPUS_DIR")
            or ""
        )
        plan = {
            "event": "corpus_refresh",
            "dry_run": True,
            "steps": ["build", "zones", "clusters", "summaries", "publish"],
            "out_dir": str(Path(resolved_out_dir)),
            "version": stamp,
            "matrix_filename": matrix_name,
            "bucket": os.environ.get("S3_BUCKET_NAME", "") or None,
            "key_prefix": resolved_prefix or None,
            # The five this refresh will BUILD: the four required ones and
            # W-18's summaries.  W-3's two sidecars and W-9's are published
            # when they exist beside the artifact, but a refresh builds a new
            # artifact and does not build them for it, so a plan that listed
            # them would be promising something this command does not do.
            # See `corpus_publish`'s docstring and the runbook.
            "would_publish": (
                [f"{resolved_prefix}/onet_corpus_{stamp}{suffix}"
                 for suffix in (*occupation_corpus.PUBLISHED_SUFFIXES, ".summaries.json")]
                if resolved_prefix
                else []
            ),
            "corpus_s3_key_after": (
                f"{resolved_prefix}/{matrix_name}" if resolved_prefix else None
            ),
            "onet_requests_estimate": 3_073 + 11,
            "rate_limit_per_second": (
                rate if rate is not None else occupation_corpus.DEFAULT_REQUESTS_PER_SECOND
            ),
            "in_service_now": existing or None,
        }
        problems = []
        if not plan["bucket"]:
            problems.append("S3_BUCKET_NAME is unset")
        if not resolved_prefix:
            problems.append(
                "no key prefix: set SOLVERAH_CORPUS_S3_PREFIX or SOLVERAH_CORPUS_S3_KEY"
            )
        for name in ("S3_ENDPOINT_URL", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
            if not os.environ.get(name):
                problems.append(f"{name} is unset")
        for name in ("ONET_API_KEY", "OPENAI_API_KEY"):
            if not os.environ.get(name):
                problems.append(f"{name} is unset")
        plan["problems"] = problems
        click.echo(json.dumps(plan))
        if problems:
            raise click.ClickException(
                "the refresh would fail: " + "; ".join(problems)
            )
        return

    build = ctx.invoke(
        corpus_build,
        out_dir=resolved_out_dir,
        version=version,
        limit=None,
        rate=rate,
        workers=workers,
        resume=resume,
        checkpoint=None,
    )
    matrix = str(build.matrix_path) if build is not None else resolved_out_dir
    ctx.invoke(corpus_zones, corpus=matrix, rate=rate)
    ctx.invoke(corpus_clusters, corpus=matrix, k=None, show=False)
    ctx.invoke(corpus_summaries, corpus=matrix, documents=None, show=0)
    ctx.invoke(
        corpus_publish, corpus=matrix, prefix=prefix, bucket=None, dry_run=False
    )


def register_cli(app) -> None:
    """Attach the operational command groups to *app*'s CLI."""
    app.cli.add_command(outbox_cli)
    app.cli.add_command(retention_cli)
    app.cli.add_command(backups_cli)
    app.cli.add_command(pulse_cli)
    app.cli.add_command(corpus_cli)
