"""Registration, login, email confirmation, and password-reset logic.

Extracted verbatim in behaviour from the seven handlers in ``app.py``.  Every
status code, every error string, and every response key is preserved -- the
blueprint in ``solverah/api/v1/auth.py`` is a translation of these results into
HTTP and nothing more.

The results are returned as small dataclasses rather than ``(dict, status)``
tuples so the API layer, not the service, decides the wire format.  That is what
lets Phase 1b change the response shape (Part 5.2's ``/auth/session``, refresh
tokens, Problem Details bodies) without touching the rules below.

Known issues carried forward, not fixed here:

* Failed-login counting is per-account only.  Part 5.3 wants 5 per 15 minutes
  per IP *and* per email; the per-IP half is currently the blanket
  ``@limiter.limit("5 per minute")`` on the route, which is per-worker until
  Redis is wired up (P0-5).
* :func:`login` returns the entire profile document, so session restore
  ships the whole user document.  That is the god-endpoint problem Part 5.2
  splits into ``GET /auth/session`` plus ``GET /me/profile``.
* Email is sent inline, so a Resend outage holds a worker (P0-6).  Phase 3 moves
  it to the ``email`` queue behind a transactional outbox.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from model import User, db
from solverah.domain import auth as domain
from solverah.infra import email as email_infra
from solverah.repositories import profile_repository, user_repository
from solverah.services import audit

__all__ = [
    "AuthResult",
    "MAX_LOGIN_ATTEMPTS",
    "LOGIN_LOCKOUT_MINUTES",
    "confirm_email",
    "login",
    "register",
    "request_password_reset",
    "resend_confirmation",
    "verify_password_reset",
]

MAX_LOGIN_ATTEMPTS = int(os.environ.get("MAX_LOGIN_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "15"))


@dataclass
class AuthResult:
    """Outcome of a service call, in the terms the API layer needs.

    Attributes:
        status: HTTP status the API layer should return.
        body: Response body, already in its final shape.
        user: The account involved, when the caller needs to mint a token for it.
        issue_token: Whether the API layer should set a JWT cookie.
    """

    status: int
    body: Dict[str, Any] = field(default_factory=dict)
    user: Optional[User] = None
    issue_token: bool = False

    @property
    def ok(self) -> bool:
        return self.status < 400


def _error(status: int, message: str, **extra: Any) -> AuthResult:
    return AuthResult(status=status, body=dict({"error": message}, **extra))


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(
    *,
    email: str,
    password: str,
    name: Optional[str],
    terms_accepted: Any,
    terms_version: Optional[str],
    hash_password,
    validate_password,
) -> AuthResult:
    """Create an account and send its verification code.

    Args:
        hash_password: ``bcrypt.generate_password_hash``-shaped callable.  Passed
            in rather than imported so this module does not depend on a Flask
            extension, which is what lets it be called from a worker.
        validate_password: Returns ``(is_valid, message)``.
    """
    email = (email or "").strip().lower()
    password = password or ""
    role = "job-seeker"

    # Terms/privacy acceptance + 16+ eligibility attestation are required at
    # registration (GAP-01/GAP-05, 2026-08-20). The acceptance record -- version
    # + timestamp -- is stored in the profile document below as evidence of assent.
    if terms_accepted is not True:
        return _error(400, "You must accept the Terms of Service and Privacy Policy")

    is_valid, validation_message = validate_password(password)
    if not is_valid:
        return _error(400, validation_message)

    # Check user existence off of email
    if user_repository.email_exists(email):
        return _error(400, "User already exists")

    hashed_pw = hash_password(password).decode("utf-8")
    profile_data = domain.default_profile(email=email, name=name)
    profile_data["legal_acceptance"] = {
        "terms_version": terms_version or "unversioned",
        "accepted_at": domain.utcnow().isoformat(),
        "age_16_plus_attested": True,
    }

    # Create user with 6-digit verification code
    code = domain.generate_verification_code()
    new_user = User(
        email=email,
        password=hashed_pw,
        name=name,
        role=role,
        email_confirmed=False,
        confirmation_token=code,
        confirmation_sent_at=domain.utcnow(),
    )
    user_repository.add(new_user)
    # The profile is rows in six tables now, and rows need the user's id. The
    # flush gets one without committing, so the user and their profile still
    # land in one transaction -- a user row with no profile would be an account
    # that cannot be read.
    db.session.flush()
    profile_repository.update_document(new_user.id, lambda _existing: profile_data)
    db.session.commit()

    return AuthResult(
        status=201,
        body={
            "message": "registered",
            "user": {
                "id": new_user.id,
                "email": new_user.email,
                "name": new_user.name,
                "role": new_user.role,
            },
        },
        user=new_user,
    )


def send_registration_code(user: User, code: str, logger) -> None:
    """Best-effort delivery of the registration code.

    Deliberately swallows the failure: the account exists, and refusing to
    return 201 because a third party is down would leave the caller unable to
    tell whether to retry the registration.  The failure is recorded as an audit
    event so it is countable, and the user can recover with
    ``POST /resend-confirmation``.
    """
    try:
        email_infra.send_confirmation_email(user.email, code)
    except Exception as exc:  # noqa: BLE001 -- see docstring
        # id, not email: keep PII out of logs
        logger.error("register email send failed for user %s: %s", user.id, exc)
        audit.log_audit_event(
            action="email_send_failed",
            actor_user_id=user.id,
            resource="email",
            metadata={"error": str(exc)},
        )
        db.session.commit()


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def login(*, email: str, password: str, check_password, wp_v2_completed) -> AuthResult:
    """Authenticate, enforcing lockout and the email-confirmation gate.

    The order of checks is load-bearing and preserved from the original: the
    lockout is tested before the password, so a locked account cannot be used as
    a password oracle; and the confirmation gate is tested *after* the failed-
    attempt counter is reset, so confirming an email does not leave a stale
    counter behind.
    """
    email = (email or "").strip().lower()
    password = password or ""

    user = user_repository.find_by_email(email)
    if user and user.locked_until and user.locked_until > domain.utcnow():
        return _error(423, "Account locked. Try again later.")

    if not user or not check_password(user.password, password):
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
                user.locked_until = domain.lockout_until(LOGIN_LOCKOUT_MINUTES)
                user.failed_login_attempts = 0
            db.session.commit()
        return _error(401, "Invalid credentials")

    # Reset failed attempts and clear lockout
    user.failed_login_attempts = 0
    user.locked_until = None
    db.session.commit()

    # Require email confirmation
    if not getattr(user, "email_confirmed", False):
        return _error(
            403,
            "Email not confirmed. Please check your inbox or use the resend option.",
        )

    return AuthResult(
        status=200,
        body={
            "message": "login successful",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "profileData": profile_repository.load_document(user.id),
                "wpl_completed": bool(user.intake and user.intake.wpl_completed_at),
                "wpll_completed": bool(user.intake and user.intake.wpll_completed_at),
                "wp_v2_completed": wp_v2_completed(user.id),
            },
        },
        user=user,
        issue_token=True,
    )


# ---------------------------------------------------------------------------
# Email confirmation
# ---------------------------------------------------------------------------

def confirm_email(*, email: str, code: str) -> AuthResult:
    """Verify the 6-digit OTP sent at registration and mark the email confirmed."""
    email = (email or "").strip().lower()
    code = (code or "").strip()
    if not email or not code:
        return _error(400, "email and code are required")

    user = user_repository.find_by_email(email)
    if not user or not user.confirmation_token:
        return _error(400, "invalid code")

    # Check expiry (15 minutes for 6-digit codes)
    if domain.is_code_expired(user.confirmation_sent_at):
        return _error(400, "code expired")

    if user.confirmation_token != code:
        return _error(400, "invalid code")

    user.email_confirmed = True
    user.confirmation_token = None
    user.confirmation_sent_at = None
    db.session.commit()

    return AuthResult(status=200, body={"message": "email confirmed"}, user=user)


def resend_confirmation(*, email: str, is_valid_email, logger) -> AuthResult:
    """Issue a fresh OTP for an unconfirmed account."""
    email = (email or "").strip().lower()
    if not email or not is_valid_email(email):
        return _error(400, "Valid email is required")

    user = user_repository.find_by_email(email)
    if not user:
        return _error(404, "Account not found")

    if getattr(user, "email_confirmed", False):
        return _error(400, "Email already confirmed")

    code = domain.generate_verification_code()
    user.confirmation_token = code
    user.confirmation_sent_at = domain.utcnow()
    db.session.commit()

    try:
        email_infra.send_confirmation_email(user.email, code)
    except Exception as exc:  # noqa: BLE001 -- reported to the caller below
        audit.log_audit_event(
            action="email_send_failed",
            actor_user_id=user.id,
            resource="email",
            metadata={"error": str(exc)},
        )
        # id, not email: keep PII out of logs
        logger.error("resend_confirmation email failed for user %s: %s", user.id, exc)
        return _error(500, "Failed to send email", detail=str(exc))

    return AuthResult(status=200, body={"message": "confirmation_sent"}, user=user)


# ---------------------------------------------------------------------------
# Password reset (passwordless sign-in by OTP)
# ---------------------------------------------------------------------------

def request_password_reset(*, email: str, logger) -> AuthResult:
    """Send a 6-digit OTP for passwordless login.

    Answers 404 for an unknown or unconfirmed address, which discloses account
    existence.  Preserved as-is: Part 5.3 changes this to a uniform 200 with a
    per-email rate limit, and that is a client-visible behaviour change, so it
    belongs with the rest of 1b rather than here.
    """
    email = (email or "").strip().lower()

    user = user_repository.find_by_email(email)
    if not user or not getattr(user, "email_confirmed", False):
        return _error(404, "No account found with that email address.")

    code = domain.generate_verification_code()
    user.reset_token = code
    user.reset_sent_at = domain.utcnow()
    db.session.commit()

    try:
        email_infra.send_password_reset_email(user.email, code)
    except Exception as exc:  # noqa: BLE001 -- reported to the caller below
        audit.log_audit_event(
            action="email_send_failed",
            actor_user_id=user.id,
            resource="email",
            metadata={"error": str(exc)},
        )
        # id, not email: keep PII out of logs
        logger.error("request_password_reset email failed for user %s: %s", user.id, exc)
        return _error(500, "Failed to send email. Please try again.")

    return AuthResult(status=200, body={"message": "reset_sent"}, user=user)


def verify_password_reset(*, email: str, code: str) -> AuthResult:
    """Validate the OTP and hand back a session.

    Every failure answers with the same ``invalid_or_expired_code`` string --
    deliberately, so the response cannot be used to tell "no such account" from
    "wrong code" from "too late".
    """
    email = (email or "").strip().lower()
    code = (code or "").strip()

    if not email or not code:
        return _error(400, "email and code are required")

    user = user_repository.find_by_email(email)
    if not user or not user.reset_token:
        return _error(400, "invalid_or_expired_code")

    if domain.is_code_expired(user.reset_sent_at):
        return _error(400, "invalid_or_expired_code")

    if user.reset_token != code:
        return _error(400, "invalid_or_expired_code")

    user.reset_token = None
    user.reset_sent_at = None
    db.session.commit()

    return AuthResult(
        status=200,
        body={
            "message": "login successful",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
            },
        },
        user=user,
        issue_token=True,
    )
