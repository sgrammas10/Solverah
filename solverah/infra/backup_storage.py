"""Where database backups are stored -- the object store the application cannot touch.

Separate from ``solverah/infra/storage.py`` and deliberately so.  That module
reads ``S3_*`` and holds resumes; this one reads ``BACKUP_S3_*`` and holds the
database.  The two never share a client, a bucket, or a credential, because the
threat the backup bucket exists for is the application's own key being stolen:
a backup an attacker with the app's credentials can delete is not a backup, it
is a copy.  ``solverah/config.py`` refuses at boot if the two collide, and
nothing here falls back to the app's values when the backup group is absent.

Two stores implement one small interface:

* :class:`S3BackupStore` -- production, and the only one a cron in production
  can select.
* :class:`LocalDirectoryBackupStore` -- a directory on disk, reachable only via
  the explicit ``flask backups run --local-dir`` flag and refused when
  ``APP_ENV`` is production.  It exists so a rehearsal exercises the *real* dump,
  the *real* verification and the *real* prune decisions with only the network
  removed, and so the test suite can do the same without a bucket.  It is not a
  fallback: nothing selects it implicitly, because a backup silently landing on
  a cron box's ephemeral disk is worse than a backup that failed loudly.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Protocol

from solverah.domain.backup_retention import Artifact

__all__ = [
    "BackupStorageError",
    "BackupStore",
    "LocalDirectoryBackupStore",
    "S3BackupStore",
    "local_backup_store",
    "s3_backup_store",
]


class BackupStorageError(RuntimeError):
    """Raised when the backup destination cannot be built or used."""


class BackupStore(Protocol):
    """List, upload, delete.  Nothing else -- the store is not asked to think.

    Every retention decision is made by
    ``solverah.domain.backup_retention.plan_prune`` on the result of
    :meth:`list_artifacts`; a store that filtered or sorted would be a second,
    invisible policy.
    """

    def list_artifacts(self, prefix: str) -> List[Artifact]:
        ...

    def put(self, key: str, source: Path) -> None:
        ...

    def delete(self, key: str) -> None:
        ...

    def describe(self) -> str:
        """A log-safe one-line description of where this store writes."""
        ...


class S3BackupStore:
    """The production store: an S3-compatible bucket reached with backup credentials.

    Takes an already-built client rather than building one, which is what lets
    the test suite exercise this class against a stub.  The client is the single
    place in the backup path that talks to an external service, and per
    CLAUDE.md it is therefore the single place a test may mock.
    """

    def __init__(self, client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def list_artifacts(self, prefix: str) -> List[Artifact]:
        """Every object under *prefix*, paginated.

        Pagination is not premature: a page is 1000 keys and the pass deletes
        based on what this returns, so an unpaginated listing would silently
        stop seeing the oldest artifacts -- exactly the ones prune acts on --
        the day the bucket crossed that line.
        """
        artifacts: List[Artifact] = []
        token = None
        while True:
            kwargs = {"Bucket": self._bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            response = self._client.list_objects_v2(**kwargs)
            for obj in response.get("Contents", []) or []:
                artifacts.append(
                    Artifact(
                        key=obj["Key"],
                        size_bytes=int(obj["Size"]),
                        modified_at=_as_utc(obj["LastModified"]),
                    )
                )
            if not response.get("IsTruncated"):
                return artifacts
            token = response.get("NextContinuationToken")
            if not token:
                return artifacts

    def put(self, key: str, source: Path) -> None:
        self._client.upload_file(str(source), self._bucket, key)

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def describe(self) -> str:
        return "s3://%s" % self._bucket


class LocalDirectoryBackupStore:
    """A directory on disk, for rehearsals and tests.  Never selected implicitly.

    Mirrors the S3 store closely enough that a rehearsal proves the prune
    decisions: same keys, same listing shape, same deletes.  What it does not
    prove is the upload -- which is the point of it being explicit.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def list_artifacts(self, prefix: str) -> List[Artifact]:
        base = self._root
        artifacts: List[Artifact] = []
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            key = path.relative_to(base).as_posix()
            if not key.startswith(prefix):
                continue
            stat = path.stat()
            artifacts.append(
                Artifact(
                    key=key,
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                )
            )
        return artifacts

    def put(self, key: str, source: Path) -> None:
        destination = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    def delete(self, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)

    def describe(self) -> str:
        return "file://%s" % self._root.as_posix()

    def _resolve(self, key: str) -> Path:
        """Map *key* to a path, refusing anything that escapes the root.

        Keys are generated by this codebase, so traversal is not a live threat;
        the check is here because the alternative -- a delete loop that trusts
        an arbitrary string to stay inside a directory -- is one refactor away
        from being one.
        """
        candidate = (self._root / key).resolve()
        root = self._root.resolve()
        if root != candidate and root not in candidate.parents:
            raise BackupStorageError("backup key escapes the store root: %r" % key)
        return candidate


def s3_backup_store(settings) -> S3BackupStore:
    """Build the production store from validated ``BACKUP_S3_*`` settings.

    Args:
        settings: A :class:`solverah.config.Settings`.

    Raises:
        BackupStorageError: If the backup credential group is not configured.
            Refusing is the whole design: the app's ``S3_*`` values are never
            consulted, so an unconfigured cron fails its pass loudly rather than
            writing the database into the resume bucket.
    """
    if not settings.has_backup_storage():
        raise BackupStorageError(
            "BACKUP_S3_* is not configured, so there is nowhere to upload a backup. "
            "Set BACKUP_S3_ENDPOINT_URL, BACKUP_S3_BUCKET_NAME, BACKUP_S3_ACCESS_KEY_ID "
            "and BACKUP_S3_SECRET_ACCESS_KEY. These are deliberately separate "
            "credentials from the application's S3_*, and there is no fallback to them."
        )

    import boto3  # local: the factory imports this module's package at boot

    from solverah.infra.storage import BACKUP_READ_TIMEOUT_SECONDS, boto_config

    client = boto3.client(
        "s3",
        endpoint_url=settings.backup_s3_endpoint_url,
        aws_access_key_id=settings.backup_s3_access_key_id,
        aws_secret_access_key=settings.backup_s3_secret_access_key,
        region_name=settings.backup_s3_region,
        # Bounded so a wedged provider cannot hang the backup cron forever; the
        # longer read timeout is because upload_file streams a whole dump.
        config=boto_config(read_timeout=BACKUP_READ_TIMEOUT_SECONDS),
    )
    return S3BackupStore(client, settings.backup_s3_bucket_name)


def _as_utc(value: datetime) -> datetime:
    """Normalise an object store's timestamp to aware UTC.

    boto3 returns aware datetimes; a stub or a future SDK might not, and
    ``Artifact`` rejects naive ones rather than comparing them by accident of
    the local timezone.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def local_backup_store(path: str) -> LocalDirectoryBackupStore:
    """Build a rehearsal store at *path* (``~`` and env vars expanded)."""
    return LocalDirectoryBackupStore(Path(os.path.expandvars(os.path.expanduser(path))))
