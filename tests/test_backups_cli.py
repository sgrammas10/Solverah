"""`flask backups run` -- the scheduled database backup (docs/RUNBOOK_SCENARIO_A_CRON.md).

Production's backup posture was 7-day Render PITR plus one manually rehearsed
dump: nothing scheduled, nothing stored outside Render (PROD_READINESS_2026-09
§6).  This command is the scheduled half, and what it does is destructive at one
end (it deletes old artifacts) and load-bearing at the other (what it stores is
what a restore uses), so the split here is deliberate:

* **The dump, the verification and the pruning run for real** against the
  compose Postgres 18 the rest of the suite uses.  A backup path proven only
  against fakes is a backup path proven against nothing.
* **The object store is the one mocked boundary**, per CLAUDE.md -- it is an
  external service, and the alternative is a test suite that writes to (and
  prunes!) a real bucket.  ``LocalDirectoryBackupStore`` stands in for the
  storage *round trip*, and a stub boto3 client covers the S3 calls themselves.

The prune *policy* is not tested here; it is pure and lives in
tests/test_backup_retention.py, exhaustively.  What this file adds is that the
command feeds that policy an honest listing and carries out exactly what it
returns.

**Why some of this can skip.** ``pg_dump`` refuses a server newer than itself,
and the ubuntu runner's stock PostgreSQL client is several majors behind the
pg18 service container -- so the backend job installs postgresql-client-18
before pytest and these run there like anywhere else.  That install step is
allowed to fail (a third-party apt archive is not something a merge should
depend on), and when it does the dump-taking tests skip with a reason naming the
version they needed rather than failing.  **If backup behaviour ever looks
unverified, read the skip lines first.**  Everything not needing a client -- the
refusals, the credential separation, the exit contract -- runs regardless.
Production never has the problem: that cron runs on
infra/docker/Dockerfile.backup, which pins postgresql-client-18.
"""

import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from solverah.infra import backup_storage
from solverah.services import backups

#: The client major `pg_dump` must be at least.  Compose, CI's service
#: container and Render's managed instance are all Postgres 18 and that is
#: load-bearing (uuidv7()); a client older than the server refuses to run at all.
REQUIRED_PG_CLIENT_MAJOR = 18


def _pg_client_major():
    """Major version of the `pg_dump` on PATH, or None if there is not one."""
    if not shutil.which("pg_dump"):
        return None
    try:
        out = subprocess.run(
            ["pg_dump", "--version"], capture_output=True, text=True, timeout=30
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    found = re.search(r"(\d+)", out)
    return int(found.group(1)) if found else None


_CLIENT_MAJOR = _pg_client_major()

needs_pg_client = pytest.mark.skipif(
    _CLIENT_MAJOR is None or _CLIENT_MAJOR < REQUIRED_PG_CLIENT_MAJOR,
    reason=(
        "needs pg_dump >= %d (found %s). pg_dump refuses a newer server, and this "
        "suite's database is Postgres 18. The production cron runs on "
        "infra/docker/Dockerfile.backup, which pins postgresql-client-18."
        % (REQUIRED_PG_CLIENT_MAJOR, _CLIENT_MAJOR or "no pg_dump on PATH")
    ),
)


@pytest.fixture()
def ctx(client):
    """An application context with the schema built -- so the dump has content."""
    from app import app

    with app.app_context():
        yield app
        from model import db

        db.session.rollback()


@pytest.fixture()
def store_dir(tmp_path):
    return tmp_path / "backups"


def _invoke(app, *args):
    """Run a CLI command; return (exit_code, parsed-JSON-or-None, raw result)."""
    result = app.test_cli_runner().invoke(args=list(args))
    payload = None
    for line in reversed(result.output.strip().splitlines()):
        try:
            payload = json.loads(line)
            break
        except ValueError:
            continue
    return result.exit_code, payload, result


def _text(result) -> str:
    """Everything the command said, on either stream.

    Click 8.2 stopped merging stderr into ``output``, and a ClickException --
    which is how this command reports a refusal -- writes to stderr. Reading
    only ``output`` would make those assertions pass by looking at nothing.
    """
    parts = [result.output or ""]
    try:
        parts.append(result.stderr or "")
    except (ValueError, AttributeError):  # older click, or nothing captured
        pass
    if result.exception is not None:
        parts.append(str(result.exception))
    return "\n".join(parts)


def _seed_artifact(store_dir: Path, name: str, *, age_days: float, size: int = 2048):
    """Write a stand-in artifact with an old mtime, as the store would see it."""
    path = store_dir / "daily" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    old = time.time() - age_days * 86400
    os.utime(path, (old, old))
    return path


def _stored(store_dir: Path):
    daily = store_dir / "daily"
    return sorted(p.name for p in daily.glob("*")) if daily.exists() else []


# ── The command exists where the cron will look for it ──────────────────────


def test_the_command_is_registered_on_the_app_the_factory_builds(ctx):
    """A cron box has the repo and env vars and nothing else; the command has to
    be reachable through create_app() exactly like the other two."""
    exit_code, _, result = _invoke(ctx, "backups", "run", "--help")

    assert exit_code == 0
    assert "--local-dir" in result.output
    assert "--retention-days" in result.output


# ── The happy path, for real ────────────────────────────────────────────────


@needs_pg_client
def test_a_pass_dumps_verifies_uploads_and_reports_the_numbers(ctx, store_dir):
    exit_code, payload, result = _invoke(
        ctx, "backups", "run", "--local-dir", str(store_dir)
    )

    assert exit_code == 0, result.output
    assert payload["event"] == "backups_run"
    assert payload["verified"] is True
    assert payload["dump_bytes"] > 0
    assert payload["archive_entries"] > 0
    assert payload["duration_seconds"] >= payload["dump_seconds"] > 0
    assert payload["retained_files"] == 1
    assert payload["retained_bytes"] == payload["dump_bytes"]
    assert payload["pruned"] == 0

    stored = _stored(store_dir)
    assert len(stored) == 1
    assert stored[0] == Path(payload["key"]).name
    assert (store_dir / payload["key"]).stat().st_size == payload["dump_bytes"]


@needs_pg_client
def test_what_lands_in_the_store_is_a_readable_archive_of_this_database(
    ctx, store_dir
):
    """The artifact, not just the temporary file, must be the restorable thing.

    Verification happens before upload; this checks the upload did not mangle
    what was verified, by listing the *stored* archive and finding a table this
    schema actually has.
    """
    exit_code, payload, result = _invoke(
        ctx, "backups", "run", "--local-dir", str(store_dir)
    )
    assert exit_code == 0, result.output

    listing = subprocess.run(
        ["pg_restore", "--list", str(store_dir / payload["key"])],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert listing.returncode == 0
    assert "TABLE public users" in listing.stdout


@needs_pg_client
def test_a_second_pass_reports_what_the_store_actually_holds(ctx, store_dir):
    """Keys are timestamped to the second, so two passes inside one second write
    the same key and the second overwrites the first. That is acceptable -- a
    manual re-run replacing its own artifact loses nothing -- but only because
    the reported counts describe the store rather than the passes."""
    _invoke(ctx, "backups", "run", "--local-dir", str(store_dir))
    exit_code, payload, _ = _invoke(ctx, "backups", "run", "--local-dir", str(store_dir))

    assert exit_code == 0
    assert payload["retained_files"] == len(_stored(store_dir))
    assert payload["retained_bytes"] == sum(
        p.stat().st_size for p in (store_dir / "daily").glob("*")
    )


# ── Pruning, against a real store ───────────────────────────────────────────


@needs_pg_client
def test_expired_artifacts_are_deleted_and_everything_else_is_kept(ctx, store_dir):
    store_dir.mkdir(parents=True, exist_ok=True)
    fresh = [
        _seed_artifact(store_dir, "solverah-fresh-%02d.dump" % day, age_days=day)
        for day in range(1, 12)
    ]
    expired = [
        _seed_artifact(store_dir, "solverah-old-%02d.dump" % day, age_days=day)
        for day in (31, 45, 400)
    ]

    exit_code, payload, result = _invoke(
        ctx, "backups", "run", "--local-dir", str(store_dir)
    )

    assert exit_code == 0, result.output
    assert payload["pruned"] == 3
    assert sorted(Path(k).name for k in payload["pruned_keys"]) == sorted(
        p.name for p in expired
    )
    assert payload["prune_refused"] is None

    survivors = _stored(store_dir)
    for path in expired:
        assert path.name not in survivors, "an expired artifact survived the prune"
    for path in fresh:
        assert path.name in survivors, "prune deleted an in-window artifact"
    assert payload["retained_files"] == len(survivors)


@needs_pg_client
def test_a_thin_store_prunes_nothing_and_still_exits_zero(ctx, store_dir):
    """The first weeks in production: expired artifacts exist, the floor says no.

    Exit 0 matters as much as the refusal -- a cron that alerted every night for
    a week would train whoever is on call to ignore it.
    """
    store_dir.mkdir(parents=True, exist_ok=True)
    ancient = _seed_artifact(store_dir, "solverah-ancient.dump", age_days=99)

    exit_code, payload, result = _invoke(
        ctx, "backups", "run", "--local-dir", str(store_dir)
    )

    assert exit_code == 0, result.output
    assert payload["pruned"] == 0
    assert "below the floor" in payload["prune_refused"]
    assert ancient.name in _stored(store_dir), "prune deleted below the floor"


@needs_pg_client
def test_prune_never_takes_the_newest_artifact_when_the_cron_has_been_broken(
    ctx, store_dir
):
    """Nothing uploaded for months, so every stored artifact is expired -- and
    the one this pass just wrote is the only thing standing between the product
    and no backup at all."""
    store_dir.mkdir(parents=True, exist_ok=True)
    for day in range(40, 52):
        _seed_artifact(store_dir, "solverah-stale-%02d.dump" % day, age_days=day)

    exit_code, payload, result = _invoke(
        ctx,
        "backups",
        "run",
        "--local-dir",
        str(store_dir),
        # The floor would refuse this outright; lowering it is what puts the
        # newest-artifact rule under test rather than the rail in front of it.
        "--min-retained",
        "1",
    )

    assert exit_code == 0, result.output
    assert Path(payload["key"]).name in _stored(store_dir)
    assert payload["key"] not in payload["pruned_keys"]
    assert payload["retained_files"] == 1


# ── The exit contract: a failed pass pages ──────────────────────────────────


def test_a_failed_dump_fails_the_pass(ctx, store_dir, monkeypatch):
    """Unlike the outbox sweep, there is no 'individual row failed' here."""
    monkeypatch.setattr(
        backups,
        "dump_database",
        lambda *_a, **_k: (_ for _ in ()).throw(backups.BackupError("pg_dump died")),
    )

    exit_code, _, _ = _invoke(ctx, "backups", "run", "--local-dir", str(store_dir))

    assert exit_code != 0
    assert _stored(store_dir) == []


def test_a_dump_that_does_not_verify_is_never_uploaded(ctx, store_dir, monkeypatch):
    """The ordering that makes the whole thing safe: a bad artifact must not
    reach the store, where it would be counted among the copies that make older
    ones expendable."""
    monkeypatch.setattr(
        backups,
        "verify_dump",
        lambda *_a, **_k: (_ for _ in ()).throw(backups.BackupError("truncated archive")),
    )
    store_dir.mkdir(parents=True, exist_ok=True)
    _seed_artifact(store_dir, "solverah-ancient.dump", age_days=99)

    exit_code, _, _ = _invoke(ctx, "backups", "run", "--local-dir", str(store_dir))

    assert exit_code != 0
    assert _stored(store_dir) == ["solverah-ancient.dump"], (
        "an unverified dump reached the store, or a failed pass still pruned"
    )


@needs_pg_client
def test_a_failed_upload_fails_the_pass_and_prunes_nothing(ctx, store_dir, monkeypatch):
    def _explode(self, key, source):
        raise OSError("bucket unreachable")

    monkeypatch.setattr(backup_storage.LocalDirectoryBackupStore, "put", _explode)
    store_dir.mkdir(parents=True, exist_ok=True)
    _seed_artifact(store_dir, "solverah-ancient.dump", age_days=99)

    exit_code, _, _ = _invoke(ctx, "backups", "run", "--local-dir", str(store_dir))

    assert exit_code != 0
    assert _stored(store_dir) == ["solverah-ancient.dump"]


def test_a_missing_backup_destination_fails_the_pass(ctx):
    """No BACKUP_S3_* in this suite's environment (CI sets five variables), so
    the S3 path is the unconfigured one -- and it must fail, not quietly no-op.
    A daily job reporting success while storing nothing is how a backup gap
    survives all the way to the restore."""
    exit_code, _, result = _invoke(ctx, "backups", "run")
    said = _text(result)

    assert exit_code != 0
    assert "BACKUP_S3_" in said
    assert "no fallback" in said


def test_the_rehearsal_store_is_refused_in_production(ctx, store_dir, monkeypatch):
    """A backup on a cron container's ephemeral disk is not a backup."""
    from solverah.config import Settings

    production = Settings.from_env(
        {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql://u:p@localhost:5432/solverah",
            "JWT_SECRET_KEY": "x" * 40,
            "JWT_COOKIE_SECURE": "true",
            "JWT_COOKIE_SAMESITE": "None",
        }
    )
    monkeypatch.setitem(ctx.extensions, "solverah_settings", production)

    exit_code, _, result = _invoke(ctx, "backups", "run", "--local-dir", str(store_dir))

    assert exit_code != 0
    assert "--local-dir" in _text(result)
    assert _stored(store_dir) == []


# ── Dump and verify, at their own boundaries ────────────────────────────────


@needs_pg_client
def test_a_truncated_archive_fails_verification(tmp_path):
    """The failure the verification step exists for: a file that looks like a
    backup and is not one. A dump cut short by a full disk gets this far."""
    path = tmp_path / "truncated.dump"
    path.write_bytes(b"PGDMP" + b"\x00" * 64)

    with pytest.raises(backups.BackupError):
        backups.verify_dump(path)


@needs_pg_client
def test_a_dump_of_a_database_that_is_not_there_fails_with_pg_dumps_own_reason(
    ctx, tmp_path
):
    """A cron failure whose message is only "exit 1" costs somebody the incident,
    so pg_dump's own last line has to survive into the exception."""
    from app import app

    url = app.extensions["solverah_settings"].database_url
    missing = url.rsplit("/", 1)[0] + "/no_such_database_here"

    with pytest.raises(backups.BackupError) as exc:
        backups.dump_database(missing, tmp_path / "never-written.dump", timeout_seconds=60)

    assert "no_such_database_here" in str(exc.value)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            'connection to "postgresql://solverah:hunter2@db:5432/app" failed',
            'connection to "postgresql://***@db:5432/app" failed',
        ),
        ("nothing to redact here", "nothing to redact here"),
        ("", ""),
    ],
)
def test_credentials_are_stripped_from_anything_on_its_way_into_a_log(raw, expected):
    """pg_dump can quote the connection string it was given, password included,
    and a failed pass's message is exactly the text that reaches a log
    aggregator, a Sentry event, and a pasted chat message."""
    assert backups._redact(raw) == expected


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgresql://u:p@h:5432/db", "postgresql://u:p@h:5432/db"),
        ("postgresql+psycopg2://u:p@h:5432/db", "postgresql://u:p@h:5432/db"),
        ("postgres://u:p@h:5432/db", "postgresql://u:p@h:5432/db"),
    ],
)
def test_sqlalchemy_urls_are_translated_for_libpq(given, expected):
    """DATABASE_URL is the same variable the other two crons get -- no new
    configuration -- so it may carry a driver pg_dump has never heard of."""
    assert backups.libpq_url(given) == expected


@pytest.mark.parametrize("given", ["sqlite:///test.db", "mysql://u:p@h/db", "", "nonsense"])
def test_a_non_postgres_database_url_is_refused_before_pg_dump_sees_it(given):
    """Otherwise the error is pg_dump failing to resolve a host named after a
    file, which is a bad way to learn the cron is pointed at nothing."""
    with pytest.raises(backups.BackupError):
        backups.libpq_url(given)


def test_the_artifact_key_sorts_in_time_order():
    """A bucket listing should be readable by a human mid-incident."""
    earlier = backups.artifact_key(datetime(2026, 9, 3, 3, 30, tzinfo=timezone.utc))
    later = backups.artifact_key(datetime(2026, 9, 4, 3, 30, tzinfo=timezone.utc))

    assert earlier < later
    assert earlier.startswith("daily/")
    assert earlier.endswith(".dump")


# ── The S3 store: the one place a mock is correct ───────────────────────────


class _StubS3Client:
    """Records calls the way boto3's S3 client is called; returns its shapes.

    Not a MagicMock: the point is to assert on the *bucket* and *keys* each call
    carries, and a stub that spells out the response shape also documents what
    S3BackupStore depends on.
    """

    def __init__(self, pages):
        self._pages = pages
        self.uploaded = []
        self.deleted = []
        self.listed = []

    def list_objects_v2(self, **kwargs):
        self.listed.append(kwargs)
        index = 0 if "ContinuationToken" not in kwargs else int(kwargs["ContinuationToken"])
        return self._pages[index]

    def upload_file(self, source, bucket, key):
        self.uploaded.append((source, bucket, key))

    def delete_object(self, Bucket, Key):  # noqa: N803 - boto3's own casing
        self.deleted.append((Bucket, Key))


def _page(keys, *, truncated=False, token=None):
    return {
        "Contents": [
            {
                "Key": key,
                "Size": 100,
                "LastModified": datetime(2026, 9, 1, tzinfo=timezone.utc),
            }
            for key in keys
        ],
        "IsTruncated": truncated,
        "NextContinuationToken": token,
    }


def test_the_s3_store_uploads_lists_and_deletes_against_the_backup_bucket(tmp_path):
    client = _StubS3Client([_page(["daily/a.dump", "daily/b.dump"])])
    store = backup_storage.S3BackupStore(client, "solverah-backups")
    source = tmp_path / "x.dump"
    source.write_bytes(b"dump")

    store.put("daily/x.dump", source)
    artifacts = store.list_artifacts("daily/")
    store.delete("daily/a.dump")

    assert client.uploaded == [(str(source), "solverah-backups", "daily/x.dump")]
    assert client.listed[0] == {"Bucket": "solverah-backups", "Prefix": "daily/"}
    assert [a.key for a in artifacts] == ["daily/a.dump", "daily/b.dump"]
    assert client.deleted == [("solverah-backups", "daily/a.dump")]


def test_the_s3_listing_follows_pagination():
    """A page is 1000 keys. Stopping at the first one would hide the oldest
    artifacts -- which are exactly the ones prune acts on -- from the day the
    bucket crossed that line, silently."""
    client = _StubS3Client(
        [
            _page(["daily/1.dump"], truncated=True, token="1"),
            _page(["daily/2.dump"]),
        ]
    )
    store = backup_storage.S3BackupStore(client, "solverah-backups")

    artifacts = store.list_artifacts("daily/")

    assert [a.key for a in artifacts] == ["daily/1.dump", "daily/2.dump"]
    assert len(client.listed) == 2


def test_the_store_is_built_from_backup_credentials_and_never_the_apps(monkeypatch):
    """The audit posture in one assertion: a stolen application key must not
    reach the backups, which is only true if these are different credentials."""
    import boto3

    from solverah.config import Settings

    captured = {}
    monkeypatch.setattr(boto3, "client", lambda service, **kw: captured.update(kw) or object())

    settings = Settings.from_env(
        {
            "APP_ENV": "development",
            "DATABASE_URL": "postgresql://u:p@localhost:5432/solverah",
            "JWT_SECRET_KEY": "x" * 40,
            "S3_ENDPOINT_URL": "https://app.r2.example",
            "S3_BUCKET_NAME": "solverah-resumes",
            "S3_ACCESS_KEY_ID": "app-key-id",
            "S3_SECRET_ACCESS_KEY": "app-secret",
            "BACKUP_S3_ENDPOINT_URL": "https://backups.r2.example",
            "BACKUP_S3_BUCKET_NAME": "solverah-backups",
            "BACKUP_S3_ACCESS_KEY_ID": "backup-key-id",
            "BACKUP_S3_SECRET_ACCESS_KEY": "backup-secret",
        }
    )

    backup_storage.s3_backup_store(settings)

    assert captured["endpoint_url"] == "https://backups.r2.example"
    assert captured["aws_access_key_id"] == "backup-key-id"
    assert captured["aws_secret_access_key"] == "backup-secret"
    assert "app-key-id" not in captured.values()
    assert "app-secret" not in captured.values()


def test_an_unconfigured_backup_group_refuses_rather_than_falling_back(monkeypatch):
    """There is no fallback to S3_*, and building a client at all would be one."""
    import boto3

    from solverah.config import Settings

    monkeypatch.setattr(
        boto3, "client", lambda *a, **k: pytest.fail("built an S3 client with no backup config")
    )
    settings = Settings.from_env(
        {
            "APP_ENV": "development",
            "DATABASE_URL": "postgresql://u:p@localhost:5432/solverah",
            "JWT_SECRET_KEY": "x" * 40,
            "S3_ENDPOINT_URL": "https://app.r2.example",
            "S3_BUCKET_NAME": "solverah-resumes",
            "S3_ACCESS_KEY_ID": "app-key-id",
            "S3_SECRET_ACCESS_KEY": "app-secret",
        }
    )

    with pytest.raises(backup_storage.BackupStorageError, match="BACKUP_S3_"):
        backup_storage.s3_backup_store(settings)


def test_the_local_store_round_trips_keys_the_way_the_s3_store_does(tmp_path):
    """The rehearsal store is only useful if its listing matches the real one's
    shape -- prefixed keys, sizes, aware timestamps."""
    store = backup_storage.LocalDirectoryBackupStore(tmp_path)
    source = tmp_path / "src.dump"
    source.write_bytes(b"abcd")

    store.put("daily/one.dump", source)
    store.put("other/two.dump", source)
    artifacts = store.list_artifacts("daily/")

    assert [a.key for a in artifacts] == ["daily/one.dump"]
    assert artifacts[0].size_bytes == 4
    assert artifacts[0].modified_at.tzinfo is not None

    store.delete("daily/one.dump")
    assert store.list_artifacts("daily/") == []


def test_the_local_store_refuses_a_key_that_escapes_its_root(tmp_path):
    store = backup_storage.LocalDirectoryBackupStore(tmp_path / "root")

    with pytest.raises(backup_storage.BackupStorageError):
        store.delete("../../etc/passwd")


# ── The service, wired to a store, without a database ───────────────────────


def test_run_backup_hands_the_policy_the_stores_own_listing(tmp_path, monkeypatch):
    """The command must not filter, sort, or second-guess what the store reports
    -- a second, invisible policy is how the tested one stops being the one that
    runs."""
    seen = {}

    def _spy(artifacts, **kwargs):
        seen["artifacts"] = list(artifacts)
        seen["kwargs"] = kwargs
        from solverah.domain.backup_retention import plan_prune as real

        return real(artifacts, **kwargs)

    monkeypatch.setattr(backups, "plan_prune", _spy)
    monkeypatch.setattr(backups, "dump_database", lambda url, dest, **_k: dest.write_bytes(b"d") or 1)
    monkeypatch.setattr(backups, "verify_dump", lambda *_a, **_k: 42)

    store = backup_storage.LocalDirectoryBackupStore(tmp_path / "store")
    for name in ("daily/older.dump", "daily/oldest.dump"):
        (tmp_path / "seed.dump").write_bytes(b"seed")
        store.put(name, tmp_path / "seed.dump")

    summary = backups.run_backup(store, "postgresql://u:p@h/db", work_dir=tmp_path)

    assert {a.key for a in seen["artifacts"]} == {
        "daily/older.dump",
        "daily/oldest.dump",
        summary["key"],
    }
    assert seen["kwargs"]["uploaded_key"] == summary["key"]
    assert seen["kwargs"]["verified"] is True
    assert summary["archive_entries"] == 42
