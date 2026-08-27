"""Pure authentication rules: code lifetimes, lockout arithmetic, blank profiles.

Extracted from the seven handlers in ``app.py`` that each re-derived them
inline.  ``confirm_email`` and ``verify_password_reset`` carried two copies of
the same nine-line expiry check, differing only in which pair of columns they
read -- a shape that guarantees the two drift.

Nothing here touches the database, the request, or the clock by default: ``now``
is an argument with a sensible default, so an expiry boundary can be tested at
the boundary rather than by sleeping.
"""

from __future__ import annotations

import datetime
import os
import random
import secrets
from typing import Any, Dict, Optional

__all__ = [
    "DEFAULT_VERIFY_CODE_EXP_MINUTES",
    "code_expiry_minutes",
    "default_profile",
    "generate_verification_code",
    "is_code_expired",
    "lockout_until",
    "utcnow",
]

#: How long a 6-digit email/reset code stays valid.  Overridable with
#: VERIFY_CODE_EXP_MINUTES, read per call because the handlers it replaces did.
DEFAULT_VERIFY_CODE_EXP_MINUTES = 15


def utcnow() -> datetime.datetime:
    """Timezone-aware current time.

    A helper rather than a bare call so every comparison in this module is
    against an aware datetime.  The naive/aware mix is what made the original
    expiry checks need the ``.replace(tzinfo=utc)`` dance below.
    """
    return datetime.datetime.now(datetime.timezone.utc)


def code_expiry_minutes(env: Optional[Dict[str, str]] = None) -> int:
    """Minutes a verification code remains valid."""
    source = os.environ if env is None else env
    return int(source.get("VERIFY_CODE_EXP_MINUTES", str(DEFAULT_VERIFY_CODE_EXP_MINUTES)))


def generate_verification_code() -> str:
    """Return a 6-digit numeric code.

    ``random`` rather than ``secrets`` is what the handlers used, and changing it
    is a security improvement that does not belong in a batch whose contract is
    "behaviour is unchanged" -- a code generator swap wants its own change and
    its own test, not to ride along inside a 38-route move.  Tracked, not fixed
    here: ``random`` is a Mersenne Twister, so observing enough codes recovers
    the state and predicts the next one.
    """
    return str(random.randint(100000, 999999))


def is_code_expired(
    sent_at: Optional[datetime.datetime],
    *,
    minutes: Optional[int] = None,
    now: Optional[datetime.datetime] = None,
) -> bool:
    """Whether a code issued at *sent_at* has expired.

    Args:
        sent_at: When the code was sent.  A naive value is read as UTC, which is
            what the database stores; ``None`` counts as expired, since a code
            with no issue time cannot be shown to be current.
        minutes: Lifetime override; defaults to :func:`code_expiry_minutes`.
        now: Comparison instant; defaults to :func:`utcnow`.

    Returns:
        True if the code is expired or unusable.
    """
    if sent_at is None:
        return True
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=datetime.timezone.utc)
    window = datetime.timedelta(
        minutes=code_expiry_minutes() if minutes is None else minutes
    )
    return sent_at + window < (now or utcnow())


def lockout_until(
    minutes: int, now: Optional[datetime.datetime] = None
) -> datetime.datetime:
    """When a lockout starting now should end."""
    return (now or utcnow()) + datetime.timedelta(minutes=minutes)


def unusable_password_hash() -> str:
    """A password value that no bcrypt comparison can ever match.

    Used when tombstoning an account.  bcrypt verification of a non-bcrypt
    string fails structurally, so this is not a weak password -- it is not a
    password at all.
    """
    return "!deleted!%s" % secrets.token_hex(16)


def default_profile(email: str = "", name: str = "") -> Dict[str, Any]:
    """Return a blank ``profile_data`` dict pre-populated with identity fields.

    Used when registering a new user or creating an account from an intake
    submission.

    Args:
        email: User's email address -- pre-fills the ``email`` field.
        name:  Full name (``"First Last"``); split into firstName/lastName.

    Returns:
        Profile dict ready to be stored in ``User.profile_data``.
    """
    first = name.split(" ")[0] if name else ""
    last = " ".join(name.split(" ")[1:]) if name else ""

    # Default job-seeker profile
    profile = {
        "firstName": first,
        "lastName": last,
        "email": email,
        "phone": "",
        "location": "",
        "primaryLocation": "",
        "secondaryLocations": [],
        "linkedinUrl": "",
        "summary": "",
        "experience": [],
        "education": [],
        "certifications": [],
        "skills": [],
        "skill_levels": {},
        "performanceReviews": [],
        "psychometricResults": {
            "leadership": {"score": None, "percentile": None, "completed": False},
            "problemSolving": {"score": None, "percentile": None, "completed": False},
            "communication": {"score": None, "percentile": None, "completed": False},
            "creativity": {"score": None, "percentile": None, "completed": False},
            "teamwork": {"score": None, "percentile": None, "completed": False},
        },
    }

    return profile
