"""Cloudflare R2 (S3-compatible) object storage.

Resumes are the only thing in the bucket.  They never transit Flask: the browser
gets a presigned PUT, uploads directly, and the API is told the key afterwards.
That two-step is deliberate and is called out in docs/ARCHITECTURE.md Appendix B
as behaviour not to refactor away.
"""

from __future__ import annotations

import os

import boto3
from botocore.config import Config as _BotoConfig

__all__ = [
    "ALLOWED_MIME",
    "BACKUP_READ_TIMEOUT_SECONDS",
    "CONNECT_TIMEOUT_SECONDS",
    "MAX_ATTEMPTS",
    "MAX_BYTES",
    "READ_TIMEOUT_SECONDS",
    "TOTAL_MAX_ATTEMPTS",
    "boto_config",
    "get_s3_client",
]

#: Resume content types the presign endpoints will sign for.  Anything else is
#: rejected before a URL is issued, so the bucket cannot be used as general
#: file hosting.
ALLOWED_MIME = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

#: Upper bound bound into the presigned URL's ``ContentLength``, so the limit is
#: enforced by R2 rather than by a number the client sends us.
MAX_BYTES = 10 * 1024 * 1024  # 10MB


# ── Client timeouts ────────────────────────────────────────────────────────
#
# These are the ONLY bound on how long an R2 call can hold a worker thread.
# Gunicorn's 30s timeout does not help here: under gthread it reaps a wedged
# *process*, not a thread blocked in a socket read (measured -- see
# docs/ARCHITECTURE.md and the gunicorn.conf.py history).  Prod is 3 workers x
# 8 threads = 24 threads total, so a provider that accepts connections and then
# stops answering exhausts the pool if each call can hang unbounded.
#
# The math, per S3 call, worst case.  Note that botocore's ``max_attempts``
# counts retries *beyond* the initial request, so N there means N + 1 total
# attempts -- read the normalized ``total_max_attempts`` for the true number:
#
#   before  botocore defaults: connect 60s + read 60s, retry mode "legacy",
#           total_max_attempts 5  ->  5 x (60 + 60) = 600s of thread hold
#   after   connect 3s + read 10s, retry mode "standard", max_attempts 2 and
#           so total_max_attempts 3  ->  3 x (3 + 10) = 39s, plus standard
#           mode's backoff sleeps between attempts
#
# 39s is not under the 30s in gunicorn.conf.py, and deliberately is not chased
# down to fit: that 30s reaps a wedged *process*, not a thread parked in a
# socket read, so there is no threshold here to duck under.  The number that
# matters is 600s -> ~40s, a 15x reduction in how much of a 24-thread pool one
# unresponsive provider can hold, with the failure arriving as an ordinary
# storage error on the paths below rather than as an unbounded wait.
#
# Deliberately module constants and not config/env values: they are a property
# of "R2 from a Render web service", not something an operator should be
# tuning per environment.
#
# Retries are safe because every S3 operation in this codebase is idempotent.
# Verified per call site:
#   generate_presigned_url  -- local signing, no network call at all
#     (solverah/services/intake_service.py, solverah/services/resume_service.py)
#   head_object             -- read-only (solverah/services/intake_service.py)
#   get_object              -- read-only (solverah/services/resume_service.py,
#                              solverah/services/agent_service.py)
#   list_objects_v2         -- read-only (retention_cleanup.py)
#   delete_object           -- idempotent by S3 contract; deleting an already
#                              deleted key succeeds (solverah/services/
#                              account_service.py, retention_cleanup.py)
# There is no put_object, no multipart upload, and no copy: browsers PUT
# directly to R2 with a presigned URL, so no write ever leaves this process.

#: Seconds to wait for the TCP/TLS connection to R2.
CONNECT_TIMEOUT_SECONDS = 3

#: Seconds to wait for each read from an established connection.
READ_TIMEOUT_SECONDS = 10

#: Retries *after* the initial request, under botocore's "standard" retry mode
#: -- so 2 here is 3 attempts in total.  "standard" (not the "legacy" default)
#: retries a narrower, documented set of errors and applies its own retry
#: quota, so a broadly failing provider stops being retried instead of every
#: call paying the full budget.
MAX_ATTEMPTS = 2

#: What ``MAX_ATTEMPTS`` becomes once botocore normalizes it.  Named because
#: the client reports this key, not ``max_attempts``.
TOTAL_MAX_ATTEMPTS = MAX_ATTEMPTS + 1


#: Read timeout for the *backup* client, which is not on a request thread and
#: whose ``upload_file`` streams a whole database dump.  10s there would abort
#: healthy backups on any slow ACK, so this keeps botocore's own default; the
#: property being preserved is "bounded", not "short".  Connect timeout and
#: retry mode are shared, because neither depends on payload size.
BACKUP_READ_TIMEOUT_SECONDS = 60


def boto_config(read_timeout: int = READ_TIMEOUT_SECONDS) -> _BotoConfig:
    """Return the botocore ``Config`` every S3 client in this app is built with.

    Exposed separately from :func:`get_s3_client` so the backup client and any
    script building its own client share the same bounds, and so tests can
    assert on it.

    Args:
        read_timeout: Override for callers whose payloads are not a request-
            path resume.  Pass ``BACKUP_READ_TIMEOUT_SECONDS`` for those; the
            default is the request-path value.
    """
    return _BotoConfig(
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        read_timeout=read_timeout,
        retries={"max_attempts": MAX_ATTEMPTS, "mode": "standard"},
    )


def get_s3_client():
    """Return a boto3 S3 client configured for Cloudflare R2.

    R2 is S3-compatible, so the same boto3 API works with a custom endpoint URL.
    Credentials and endpoint are sourced from environment variables:
        S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_REGION.

    The client carries :func:`boto_config`; see the timeout constants above for
    why an unbounded client is not an option on a threaded worker.
    """
    # Cloudflare R2 is S3-compatible; endpoint_url overrides the default AWS endpoint
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("S3_REGION", "auto"),
        config=boto_config(),
    )
