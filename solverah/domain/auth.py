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
import secrets
from typing import Any, Dict, Optional

__all__ = [
    "DEFAULT_VERIFY_CODE_EXP_MINUTES",
    "TIMING_EQUALISER_HASH",
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

#: A real bcrypt digest, verified against on the "no such account" login branch
#: so that branch costs what a real one costs.
#:
#: The 2026-09 audit probed a timing oracle: ``login`` short-circuits on
#: ``if not user or not check_password(...)``, so an unknown address answered
#: 401 without bcrypt ever running, while a known address answered the same 401
#: several tens of milliseconds later.  The bodies matched; the clock did not.
#:
#: The fix is to spend the work rather than to hide it.  Hashing a *dummy*
#: rather than the submitted password matters: verification cost in bcrypt is
#: set by the digest's own cost parameter, not by the candidate, so this is a
#: constant amount of work regardless of what an attacker sends.
#:
#: ``$2b$12$`` matches flask-bcrypt's default ``BCRYPT_LOG_ROUNDS`` of 12, which
#: is what every stored ``password_hash`` in this application carries -- nothing
#: sets the config key.  If that default is ever overridden, re-mint this at the
#: new cost, or the branches diverge again in the other direction.
#:
#: It is not a secret and it is not a password: the plaintext behind it was 32
#: bytes from ``secrets.token_bytes`` and was never recorded.  No candidate can
#: match it, so a caller cannot use it to authenticate as anyone.
TIMING_EQUALISER_HASH = "$2b$12$EQUirQt4sCsr7BnlsiS44./t8QypkRLv7Ymy4cpqKD9cwU.GoXhFG"


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
    """Return a 6-digit numeric code from the system CSPRNG.

    This code is a bearer credential.  ``/auth/password/reset`` exchanges it for
    a full session cookie without ever consulting ``password_hash``, so
    predicting one is equivalent to knowing the password.

    Until S1 it came from ``random.randint``, and the docstring that stood here
    said why that was tolerated (it was what the pre-Phase-1 handlers used, and
    the batch that moved them promised "behaviour is unchanged").  The 2026-09
    audit priced it: ``random`` is a Mersenne Twister, its state is recoverable
    from ~624 consecutive outputs, and the attack needs no access to the
    victim's inbox -- harvest codes by self-registering, reconstruct the state,
    call ``/auth/password/forgot`` for the victim, predict the code.

    ``secrets.randbelow`` draws from the OS entropy source, whose output is not
    a function of previously observed output.  The arithmetic keeps the format
    the wire and the UI already depend on: ``randbelow(900000)`` yields
    ``0..899999``, and ``+ 100000`` shifts that onto ``100000..999999`` -- every
    6-digit value, none shorter, uniformly.  ``str`` of that never needs
    zero-padding, which is why the code is safe to compare as text.

    The module-level guard in ``tests/test_otp_entropy.py`` keeps ``random``
    from coming back here or anywhere else under ``solverah/``.
    """
    return str(secrets.randbelow(900000) + 100000)


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
