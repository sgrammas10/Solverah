"""Validation rules for the public intake form.

The two intake write endpoints -- ``/intake/finalize`` (anonymous) and
``/intake/link-account`` (authenticated) -- carried near-identical 40-line
validation blocks that differed in three error strings and one extra field.
That is the shape that guarantees drift: a rule tightened on one path and not
the other is invisible until someone finds the looser one.

They share :func:`validate_submission` here.  The differences are parameters,
and the ones that survive are named so they cannot be introduced by accident:

* ``name_too_long_message`` -- finalize says "First or last name is too long",
  link-account says "Name is too long".  Both strings are rendered directly by
  the frontend, so they are preserved rather than harmonised.
* ``require_email`` -- only the anonymous path collects an email; the
  authenticated path takes it from the JWT.

Every check, and the order they run in, is preserved: the order determines which
message a request with several problems gets back.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional, Tuple

from .validation import (
    is_valid_email,
    is_valid_https_url,
    is_valid_linkedin_url,
    is_valid_phone,
    normalize_whitespace,
)

__all__ = [
    "MAX_EMAIL_LENGTH",
    "is_valid_email",
    "MAX_NAME_LENGTH",
    "MAX_STATE_LENGTH",
    "MAX_URL_LENGTH",
    "IntakeFields",
    "is_valid_uuid",
    "parse_submission",
    "validate_submission",
]

MAX_EMAIL_LENGTH = 254
MAX_NAME_LENGTH = 120
MAX_STATE_LENGTH = 50
MAX_PHONE_LENGTH = 50
MAX_URL_LENGTH = 400


def is_valid_uuid(value: str) -> bool:
    """Whether *value* parses as a UUID.

    The submission id is client-supplied and becomes part of the object key and
    the primary key, so it is checked before either is built.
    """
    try:
        uuid.UUID(value)
    except Exception:  # noqa: BLE001 -- any parse failure is the same answer
        return False
    return True


class IntakeFields(dict):
    """Normalised intake fields, addressable as attributes or keys."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:  # pragma: no cover - attribute typo guard
            raise AttributeError(name) from exc


def parse_submission(data: Dict[str, Any]) -> IntakeFields:
    """Normalise a raw intake body: trim, collapse whitespace, lower the email.

    Separated from validation so the normalised values are what gets validated
    *and* what gets stored -- the original code normalised and validated in one
    pass, which made it possible for a check to run against a different string
    than the one written to the database.
    """
    return IntakeFields(
        submission_id=(data.get("submission_id") or "").strip(),
        first_name=normalize_whitespace((data.get("first_name") or "").strip()),
        last_name=normalize_whitespace((data.get("last_name") or "").strip()),
        email=(data.get("email") or "").strip().lower(),
        state=normalize_whitespace((data.get("state") or "").strip()),
        phone=normalize_whitespace((data.get("phone") or "").strip()),
        linkedin_url=(data.get("linkedin_url") or "").strip(),
        portfolio_url=(data.get("portfolio_url") or "").strip(),
        privacy_consent=data.get("privacy_consent") is True,
        info_opt_in=data.get("info_opt_in") is True,
        object_key=(data.get("object_key") or "").strip(),
        mime=(data.get("mime") or "").strip(),
        size=int(data.get("size") or 0),
    )


def validate_submission(
    fields: IntakeFields,
    *,
    allowed_mime,
    max_bytes: int,
    require_email: bool,
    name_too_long_message: str,
) -> Optional[str]:
    """Validate a normalised intake submission.

    Returns:
        None when valid, otherwise the exact error message the endpoint should
        return with a 400.

    The order below is the order the original handlers used and is load-bearing:
    a request that is wrong in several ways must keep getting the same message
    it got before, because the frontend maps some of them to specific fields.
    """
    if not is_valid_uuid(fields.submission_id):
        return "Invalid submission_id"

    # The object key must live under this submission's prefix. Without the
    # check a client could name any key in the bucket and have it attached to
    # their own submission.
    if not fields.object_key.startswith("intake/%s/" % fields.submission_id):
        return "Invalid object_key"
    if fields.mime not in allowed_mime:
        return "Unsupported file type"
    if fields.size <= 0 or fields.size > max_bytes:
        return "Invalid file size"

    if require_email:
        if (
            not fields.email
            or len(fields.email) > MAX_EMAIL_LENGTH
            or not is_valid_email(fields.email)
        ):
            return "Valid email is required"

    if not fields.state or len(fields.state) > MAX_STATE_LENGTH:
        return "State is required"

    if not fields.privacy_consent:
        return "Privacy consent is required"

    if not fields.first_name or not fields.last_name:
        return "First and last name are required"

    if len(fields.first_name) > MAX_NAME_LENGTH or len(fields.last_name) > MAX_NAME_LENGTH:
        return name_too_long_message

    if fields.phone and not is_valid_phone(fields.phone):
        return "Invalid phone format"

    if fields.linkedin_url and not is_valid_linkedin_url(fields.linkedin_url):
        return "LinkedIn URL must be https://linkedin.com"

    if fields.portfolio_url and not is_valid_https_url(fields.portfolio_url):
        return "Portfolio URL must be https://"

    if (
        len(fields.phone) > MAX_PHONE_LENGTH
        or len(fields.linkedin_url) > MAX_URL_LENGTH
        or len(fields.portfolio_url) > MAX_URL_LENGTH
    ):
        return "One or more fields are too long"

    return None
