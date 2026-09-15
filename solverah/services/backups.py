"""Take a database backup, prove it is readable, store it, prune what expired.

Production's backup posture before this module was 7-day Render PITR plus one
manual `pg_dump` rehearsed on 2026-08-27 (PROD_READINESS_2026-09.md §6): nothing
scheduled, and nothing stored anywhere Render's account compromise would not
also reach.  This is the scheduled half -- `flask backups run`, daily -- and the
order of its four steps is the design:

    dump  ->  verify  ->  upload  ->  prune

**Verify before upload, always.** ``pg_restore --list`` reads the archive's
table of contents, which is the cheapest thing that distinguishes "a 40MB file"
from "a restorable backup": a dump truncated by a disk that filled, or by a
connection dropped mid-stream, is a plausible-looking file that fails at the
only moment anyone will ever try it.  Verifying *before* the upload also means a
bad artifact never reaches the bucket to be counted among the copies that make
older ones expendable.

**Prune last, and only on the strength of this pass.** The retention decision
lives in ``solverah.domain.backup_retention`` as a pure function with no way to
reach a bucket; this module's job is to hand it an honest listing and to carry
out exactly what it returns.

**What the caller does with failures.** Everything here raises
:class:`BackupError` on a failed step, and ``flask backups run`` lets that
propagate to a non-zero exit -- unlike the outbox sweep, a failed dump or upload
IS a failed pass, and cron alerting must fire.  A prune *refusal* is not a
failure and does not raise: it is the safety rails doing their job, reported in
the JSON line and exiting 0 (see the domain module).

``pg_dump`` runs against a live database and takes no lock that blocks writers
-- it holds ACCESS SHARE, which conflicts only with ACCESS EXCLUSIVE (DDL).  The
flags here are the ones the rehearsed manual path already used (`make
db-snapshot`) and nothing more; there is no lock-timeout tuning to add and
adding some would be the way to turn a harmless job into a harmful one.
"""

from __future__ import annotations

import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from solverah.domain.backup_retention import (
    DEFAULT_MIN_RETAINED,
    DEFAULT_RETENTION_DAYS,
    plan_prune,
)

__all__ = [
    "BACKUP_PREFIX",
    "BackupError",
    "DUMP_TIMEOUT_SECONDS",
    "artifact_key",
    "dump_database",
    "libpq_url",
    "run_backup",
    "verify_dump",
]

#: Key prefix every artifact is written under.  One prefix, one cadence: when a
#: second cadence is ever added (the runbook's WAL/incremental tripwire), it gets
#: its own prefix and its own policy rather than sharing this one's.
BACKUP_PREFIX = "daily/"

#: Ceiling on a single ``pg_dump``/``pg_restore`` invocation.  The measured prod
#: dump was 16.5 seconds at 68KB and 15 seconds to restore 424MB, so 30 minutes
#: is not a tuning knob -- it is the difference between a cron pass that fails
#: and one that runs until the platform kills it with no JSON line and no Sentry
#: event.
DUMP_TIMEOUT_SECONDS = 1800

_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"


class BackupError(RuntimeError):
    """A step of the backup pass failed.  The pass exits non-zero."""


def utcnow() -> datetime:
    """Timezone-aware now.  One definition, so tests can substitute one clock."""
    return datetime.now(timezone.utc)


def artifact_key(moment: datetime, prefix: str = BACKUP_PREFIX) -> str:
    """The object key for a dump taken at *moment*.

    Sorts lexicographically in time order, which makes a bucket listing readable
    by a human in an incident without any tooling.
    """
    return "%ssolverah-%s.dump" % (prefix, moment.astimezone(timezone.utc).strftime(_TIMESTAMP_FORMAT))


def libpq_url(database_url: str) -> str:
    """Return *database_url* in the form libpq accepts.

    SQLAlchemy URLs may carry a driver (``postgresql+psycopg2://``) that
    ``pg_dump`` does not understand, and the application's own ``DATABASE_URL``
    is the one this cron is given -- the same variable, no new configuration.

    Raises:
        BackupError: If the URL is not Postgres at all.  The suite runs on
            Postgres and so does production, so this is nearly unreachable --
            but "nearly" is doing the work: a SQLite URL reaching ``pg_dump``
            produces a connection error about a host named after a file, which
            is a bad way to learn that the cron is pointed at nothing.
    """
    url = (database_url or "").strip()
    if not url:
        raise BackupError("DATABASE_URL is empty; there is nothing to back up.")

    scheme, separator, rest = url.partition("://")
    if not separator:
        raise BackupError("DATABASE_URL is not a URL: %r" % _redact(url))

    base = scheme.split("+", 1)[0].lower()
    if base not in {"postgresql", "postgres"}:
        raise BackupError(
            "backups require a PostgreSQL DATABASE_URL; got scheme %r. "
            "pg_dump cannot back up anything else." % scheme
        )
    return "postgresql://%s" % rest


def dump_database(
    database_url: str,
    destination: Path,
    *,
    timeout_seconds: int = DUMP_TIMEOUT_SECONDS,
) -> int:
    """Write a custom-format dump of *database_url* to *destination*.

    ``-Fc`` (custom) rather than plain SQL: it is compressed, it is what
    ``pg_restore`` needs for selective restores, and it is the format the
    rehearsed rollback path (docs/RUNBOOK_DATABASE_ROLLBACK.md, Path A) already
    uses -- a backup in a format nobody has restored from is a backup nobody has
    tested.  ``--no-owner --no-acl`` because a restore lands on an instance whose
    role names are Render's, not this database's.

    The connection string is passed as an argument, so it is visible in the
    process list of whatever host runs this -- as it already is in `make
    db-snapshot`. That host is a single-tenant cron container that runs this one
    command and exits, and the alternatives (splitting the URL into PG* vars, a
    PGPASSFILE) buy nothing there while adding parsing that can get the target
    database wrong. Anything on its way back out to a log is redacted.

    Returns:
        Size of the written artifact in bytes.

    Raises:
        BackupError: If ``pg_dump`` is missing, fails, times out, or produces
            nothing.
    """
    command = [
        "pg_dump",
        "--dbname=%s" % libpq_url(database_url),
        "-Fc",
        "--no-owner",
        "--no-acl",
        "-f",
        str(destination),
    ]
    _run(command, timeout_seconds=timeout_seconds, what="pg_dump")

    if not destination.exists() or destination.stat().st_size == 0:
        raise BackupError("pg_dump exited 0 but wrote no data to %s" % destination)
    return destination.stat().st_size


def verify_dump(path: Path, *, timeout_seconds: int = DUMP_TIMEOUT_SECONDS) -> int:
    """Prove *path* is a readable archive; return the number of TOC entries.

    This is the check that separates a file from a backup.  It is not a restore
    -- only a restore proves a restore -- but it reads the whole archive header
    and catalogue, so truncation, corruption of the leading blocks, and "the
    disk filled at 90%" all fail here rather than during an incident.

    Raises:
        BackupError: If the archive cannot be listed or lists nothing.
    """
    completed = _run(
        ["pg_restore", "--list", str(path)],
        timeout_seconds=timeout_seconds,
        what="pg_restore --list",
    )
    entries = [
        line
        for line in completed.stdout.splitlines()
        if line.strip() and not line.lstrip().startswith(";")
    ]
    if not entries:
        raise BackupError(
            "pg_restore --list read %s but found no entries: the archive is empty "
            "or unreadable, and it will not be uploaded." % path.name
        )
    return len(entries)


def run_backup(
    store,
    database_url: str,
    *,
    work_dir: Path,
    now: Optional[datetime] = None,
    prefix: str = BACKUP_PREFIX,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    min_retained: int = DEFAULT_MIN_RETAINED,
    timeout_seconds: int = DUMP_TIMEOUT_SECONDS,
) -> dict:
    """Run one complete pass and return the summary the CLI prints.

    Args:
        store: A :class:`solverah.infra.backup_storage.BackupStore`.
        database_url: The database to dump -- the same ``DATABASE_URL`` the
            other two crons get.
        work_dir: Directory the dump is written to before upload.  The caller
            owns its lifetime (the CLI uses a temporary directory), so the
            artifact never outlives the pass on the cron box's disk.
        now: Injectable clock, for tests.

    Returns:
        A JSON-serialisable dict: what was dumped, how long it took, what the
        store holds afterwards, and what prune did or refused to do.

    Raises:
        BackupError: If the dump, verification, upload, or a delete fails.  Each
            is a failed pass and must exit non-zero.
    """
    moment = now or utcnow()
    started = time.monotonic()

    key = artifact_key(moment, prefix)
    local_path = Path(work_dir) / Path(key).name

    dump_started = time.monotonic()
    dump_bytes = dump_database(database_url, local_path, timeout_seconds=timeout_seconds)
    dump_seconds = time.monotonic() - dump_started

    # Verification failure is raised, not returned: it must both fail the pass
    # and stop the upload, and the prune below never runs.
    verified_entries = verify_dump(local_path, timeout_seconds=timeout_seconds)

    try:
        store.put(key, local_path)
    except Exception as exc:  # noqa: BLE001 - every store failure is a failed pass
        raise BackupError("uploading %s to %s failed: %s" % (key, store.describe(), exc)) from exc

    artifacts = store.list_artifacts(prefix)
    plan = plan_prune(
        artifacts,
        now=moment,
        uploaded_key=key,
        verified=True,
        retention_days=retention_days,
        min_retained=min_retained,
    )

    for doomed in plan.delete:
        try:
            store.delete(doomed)
        except Exception as exc:  # noqa: BLE001 - a half-applied prune must be visible
            raise BackupError("deleting expired backup %s failed: %s" % (doomed, exc)) from exc

    return {
        "event": "backups_run",
        "destination": store.describe(),
        "key": key,
        "dump_bytes": dump_bytes,
        "dump_seconds": round(dump_seconds, 3),
        "duration_seconds": round(time.monotonic() - started, 3),
        "archive_entries": verified_entries,
        "verified": True,
        "retention_days": retention_days,
        "min_retained": min_retained,
        "pruned": len(plan.delete),
        "pruned_keys": list(plan.delete),
        "prune_refused": plan.refusal,
        "retained_files": plan.retained_files,
        "retained_bytes": plan.retained_bytes,
    }


def _run(command, *, timeout_seconds: int, what: str) -> subprocess.CompletedProcess:
    """Run *command*, turning every failure mode into a :class:`BackupError`.

    stderr is carried into the message rather than logged separately: the whole
    diagnosis of a failed dump is in ``pg_dump``'s own last line, and a cron
    failure that says only "exit 1" costs somebody the incident.
    """
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise BackupError(
            "%s is not installed on this host. The backup cron runs on the "
            "infra/docker/Dockerfile.backup image precisely because Render's native "
            "Python runtime guarantees no PostgreSQL client. (%s)" % (command[0], exc)
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise BackupError("%s exceeded %ds and was killed" % (what, timeout_seconds)) from exc

    if completed.returncode != 0:
        raise BackupError(
            "%s failed (exit %d): %s"
            % (what, completed.returncode, _redact(completed.stderr.strip()) or "no stderr")
        )
    return completed


def _redact(text: str) -> str:
    """Strip credentials out of anything on its way into a message or a log.

    ``pg_dump``'s errors quote the connection string it was given, and that
    string carries the database password.  A cron failure is exactly the text
    that ends up in a log aggregator, a Sentry event, and a pasted chat message.
    """
    return re.sub(r"://[^/@\s]*@", "://***@", text or "")
