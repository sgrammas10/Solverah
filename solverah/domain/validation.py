"""Field-level validation predicates.

Lifted unchanged from ``app.py``, where they sat above the routes that used
them.  Pure and side-effect free, so they are equally usable from a handler, a
service, and the pydantic validators Phase 1b attaches to the request models.

These are deliberately permissive.  ``_is_valid_email`` in particular is a
``local@domain.tld`` shape check, not an RFC 5322 parser and not a proof the
address exists -- that is what the confirmation code is for.  A stricter regex
here would reject valid addresses and buy nothing, because delivery is the only
real test.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

__all__ = [
    "EMAIL_PATTERN",
    "LINKEDIN_ALLOWED_HOSTS",
    "PHONE_PATTERN",
    "is_valid_email",
    "is_valid_https_url",
    "is_valid_linkedin_url",
    "is_valid_phone",
    "normalize_whitespace",
]

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_PATTERN = re.compile(r"^[0-9+().\-\s]{7,25}$")

#: Only these two hosts are accepted for a LinkedIn URL.  An allowlist rather
#: than a substring check, because "linkedin.com.evil.test" contains the string
#: and is not LinkedIn.
LINKEDIN_ALLOWED_HOSTS = {
    "linkedin.com",
    "www.linkedin.com",
}


def normalize_whitespace(value: str) -> str:
    """Collapse runs of whitespace in *value* to a single space and strip ends."""
    return " ".join(value.split())


def is_valid_email(email: str) -> bool:
    """Return True if *email* matches a basic ``local@domain.tld`` pattern."""
    return bool(EMAIL_PATTERN.match(email))


def is_valid_phone(phone: str) -> bool:
    """Return True if *phone* contains 7-25 digit/punctuation characters."""
    return bool(PHONE_PATTERN.match(phone))


def is_valid_https_url(value: str) -> bool:
    """Return True if *value* is an HTTPS URL with a non-empty host."""
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def is_valid_linkedin_url(value: str) -> bool:
    """Return True if *value* is an HTTPS LinkedIn URL (linkedin.com or www.linkedin.com)."""
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.netloc in LINKEDIN_ALLOWED_HOSTS
