"""Cloudflare R2 (S3-compatible) object storage.

Resumes are the only thing in the bucket.  They never transit Flask: the browser
gets a presigned PUT, uploads directly, and the API is told the key afterwards.
That two-step is deliberate and is called out in docs/ARCHITECTURE.md Appendix B
as behaviour not to refactor away.
"""

from __future__ import annotations

import os

import boto3

__all__ = ["ALLOWED_MIME", "MAX_BYTES", "get_s3_client"]

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


def get_s3_client():
    """Return a boto3 S3 client configured for Cloudflare R2.

    R2 is S3-compatible, so the same boto3 API works with a custom endpoint URL.
    Credentials and endpoint are sourced from environment variables:
        S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_REGION.
    """
    # Cloudflare R2 is S3-compatible; endpoint_url overrides the default AWS endpoint
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("S3_REGION", "auto"),
    )
