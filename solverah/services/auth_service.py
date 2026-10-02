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
Resolved here in Phase 3, and worth stating because it changes two error paths:

* Email is no longer sent inline.  Every send in this module writes an ``outbox``
  row **inside the transaction that makes the change the email is about**, and a
  worker delivers it.  ``resend_confirmation`` and ``request_password_reset``
  used to answer 500 when Resend was unreachable -- having already rotated the
  token, so the user was told it failed while the code in the database had
  changed underneath them.  Both now answer 200: the row is durable, the send is
  owed, and a retry will make it.  See ``solverah/services/outbox.py``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import sqlalchemy as sa

from model import User, db
from solverah.domain import auth as domain
from solverah.repositories import (
    assessment_repository,
    profile_repository,
    user_repository,
)
from solverah.services import outbox

__all__ = [
    "AuthResult",
    "CONFIRM_CODE_EXPIRED",
    "CONFIRM_INVALID_CODE",
    "MAX_LOGIN_ATTEMPTS",
    "LOGIN_LOCKOUT_MINUTES",
    "RESET_INVALID_OR_EXPIRED",
    "clear_failed_logins",
    "confirm_email",
    "login",
    "record_failed_login",
    "register",
    "request_password_reset",
    "resend_confirmation",
    "verify_password_reset",
]

MAX_LOGIN_ATTEMPTS = int(os.environ.get("MAX_LOGIN_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "15"))

#: The ``error`` strings a bad one-time code answers with.  They ARE the
#: machine-readable codes: the SPA keys its user-facing copy on these exact
#: values (``src/features/auth/otpErrorCopy.ts``, G8), the contract baseline
#: records ``{"error": "invalid code"}`` byte-for-byte, and the legacy
#: ``{"error": ...}`` body has no other field to carry a code in.  Named so a
#: reword here is a deliberate wire change rather than a copy edit that
#: silently drops every verify screen back to raw server text.
CONFIRM_INVALID_CODE = "invalid code"
CONFIRM_CODE_EXPIRED = "code expired"
RESET_INVALID_OR_EXPIRED = "invalid_or_expired_code"


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


def _account(user: User) -> Dict[str, Any]:
    """The four identity fields an auth response carries, read off *user* now.

    Callers read these before they commit, not after. A commit expires every
    loaded attribute, so the same four reads afterwards are a SELECT of a row
    the transaction already holds.
    """
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}


_users = User.__table__


def _write_login_counter(user_id: int, **values: Any) -> None:
    """Write the lockout columns in one UPDATE, then commit.

    In SQL rather than through the ORM instance, so the new values are computed
    from the row as the database holds it when the UPDATE runs. Two counter
    writes that overlap therefore both land: the second waits on the first's
    row lock, then computes from its committed count. Counted in Python, both
    read the same count and ``version``; ``users`` carries ``version_id_col``,
    so the second write matched no row and raised ``StaleDataError`` -- a 500,
    and a lost count.

    The UPDATE moves ``version`` but does not check it, and not checking is
    what lets two counter writes serialise instead of failing. What moving it
    keeps is the ORM side of the contract: a session that loaded this row
    before the UPDATE still gets ``StaleDataError`` from its own flush rather
    than overwriting these values. The ``User`` instance in the caller's session
    is stale until the commit below expires it, and nothing reads it in between.
    """
    db.session.execute(
        sa.update(_users)
        .where(_users.c.id == user_id)
        .values(version=_users.c.version + 1, **values)
    )
    db.session.commit()


def record_failed_login(user: User) -> None:
    """Count one wrong password against *user*. Commits.

    The lockout rule for every password sign-in -- :func:`login` and
    ``intake_service.sign_in`` -- lives here once, so the two share one counter
    and one threshold. The intake path used to keep its own copy, counted in
    Python, with the lost update :func:`_write_login_counter` describes. The
    failure that reaches :data:`MAX_LOGIN_ATTEMPTS` sets ``locked_until`` and
    restarts the count; every SET expression reads the pre-update row.
    """
    reached = _users.c.failed_login_count + 1 >= MAX_LOGIN_ATTEMPTS
    _write_login_counter(
        user.id,
        failed_login_count=sa.case((reached, 0), else_=_users.c.failed_login_count + 1),
        locked_until=sa.case(
            (reached, domain.lockout_until(LOGIN_LOCKOUT_MINUTES)),
            else_=_users.c.locked_until,
        ),
    )


def clear_failed_logins(user: User) -> None:
    """After a correct password, zero the count and lift any lock. Commits if it writes.

    Both password paths call this *before* their email-confirmation gate, so
    confirming an address never leaves a stale counter behind. A row with
    nothing to clear is not written: a commit with nothing in it still costs a
    round trip and expires ``user``, and the next read reloads the row. When it
    does write, ``user`` comes back expired, so callers read what they need off
    it first.
    """
    if user.failed_login_count or user.locked_until is not None:
        _write_login_counter(user.id, failed_login_count=0, locked_until=None)


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
        password_hash=hashed_pw,
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
    # The verification email joins the same transaction as the account it
    # verifies. Before this it was a separate call after the commit, so a Resend
    # outage produced an account nobody could confirm and a 201 that said
    # everything was fine -- the failure recorded only as a log line and an audit
    # row. Now the send is a committed obligation and the worker retries it.
    entry_id = outbox.enqueue(
        outbox.TOPIC_EMAIL_VERIFICATION, {"to": new_user.email, "code": code}
    )
    account = _account(new_user)
    db.session.commit()
    outbox.publish_soon(entry_id)

    return AuthResult(
        status=201,
        body={"message": "registered", "user": account},
        user=new_user,
    )


# ``send_registration_code`` lived here and is gone. It existed to make the
# post-commit Resend call best-effort -- catch, log, write an `email_send_failed`
# audit row, commit again -- and every line of that was compensating for the send
# being outside the transaction. It is inside it now, so there is nothing left to
# compensate for and no second commit to make.


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

    The counter is :func:`record_failed_login` and :func:`clear_failed_logins`,
    shared with the intake sign-in. A successful login with nothing to reset
    writes and commits nothing: the session row ``refresh_tokens.issue``
    inserts next is then the request's only commit.
    """
    email = (email or "").strip().lower()
    password = password or ""

    user = user_repository.find_by_email(email)
    if user and user.locked_until and user.locked_until > domain.utcnow():
        return _error(423, "Account locked. Try again later.")

    if user is None:
        # Burn the same bcrypt work a real account would, then fall through to
        # the identical 401 below.  Without this the `not user` short-circuit
        # answers tens of milliseconds sooner than a wrong password does, and
        # the 2026-09 audit probed exactly that: same status, same body, two
        # populations separable by the clock.  Enumerating a mailing list off a
        # timing difference is slower than off a status code, not harder.
        #
        # The result is deliberately discarded -- `TIMING_EQUALISER_HASH` has no
        # matching plaintext, so it can only ever be False, and branching on it
        # would put the branch back.
        check_password(domain.TIMING_EQUALISER_HASH, password)

    if not user or not check_password(user.password_hash, password):
        if user:
            record_failed_login(user)
        return _error(401, "Invalid credentials")

    # Read before clear_failed_logins can commit and expire the row.
    user_id = user.id
    account = _account(user)
    email_confirmed = getattr(user, "email_confirmed", False)
    clear_failed_logins(user)

    # Require email confirmation
    if not email_confirmed:
        return _error(
            403,
            "Email not confirmed. Please check your inbox or use the resend option.",
        )

    finished = assessment_repository.completed_kinds(user_id)
    return AuthResult(
        status=200,
        body={
            "message": "login successful",
            "user": {
                **account,
                "profileData": profile_repository.load_document(user_id),
                "wpl_completed": "work_pulse" in finished,
                "wpll_completed": "wpll" in finished,
                "wp_v2_completed": wp_v2_completed(user_id),
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
        return _error(400, CONFIRM_INVALID_CODE)

    # Check expiry (15 minutes for 6-digit codes)
    if domain.is_code_expired(user.confirmation_sent_at):
        return _error(400, CONFIRM_CODE_EXPIRED)

    if user.confirmation_token != code:
        return _error(400, CONFIRM_INVALID_CODE)

    user.email_confirmed = True
    # Phase 2c's `users.status`. Nothing reads it yet, and it is maintained here
    # rather than left at its 'pending' default because a status column that is
    # always 'pending' is not a column, it is a lie with a name.
    user.status = "active"
    user.confirmation_token = None
    user.confirmation_sent_at = None
    db.session.commit()

    return AuthResult(status=200, body={"message": "email confirmed"}, user=user)


#: The only body ``resend_confirmation`` ever returns once the address parses,
#: and the only one ``request_password_reset`` ever returns.  Named so the three
#: outcomes each function has -- sent, already-confirmed, no such account --
#: cannot drift apart by someone editing one return and not the others.
RESEND_UNIFORM_BODY = {"message": "confirmation_sent"}
RESET_UNIFORM_BODY = {"message": "reset_sent"}


def resend_confirmation(*, email: str, is_valid_email) -> AuthResult:
    """Issue a fresh OTP for an unconfirmed account, disclosing nothing.

    Answers ``200 confirmation_sent`` for all three outcomes -- code sent,
    address already confirmed, no such account -- because the three are
    indistinguishable to anyone who is not reading that inbox, and that is the
    point.  Until S1 they were ``200`` / ``400 "Email already confirmed"`` /
    ``404 "Account not found"``, which the 2026-09 audit probed live: replay a
    mailing list here and the status codes sort it into registered, registered-
    and-verified, and unknown.

    The malformed-address ``400`` stays, and is not a leak: it depends only on
    the *string*, never on whether it names an account, so it answers the same
    for both populations.

    No work is done for an unknown address -- no row, no outbox entry, no email
    -- so an attacker cannot use this to make the system send mail to a third
    party either.
    """
    email = (email or "").strip().lower()
    if not email or not is_valid_email(email):
        return _error(400, "Valid email is required")

    user = user_repository.find_by_email(email)
    if not user or getattr(user, "email_confirmed", False):
        # Nothing to do, and nothing to say about which of the two it was.
        return AuthResult(status=200, body=dict(RESEND_UNIFORM_BODY), user=user)

    code = domain.generate_verification_code()
    user.confirmation_token = code
    user.confirmation_sent_at = domain.utcnow()
    # Rotating the token and owing the email are now one commit. They were two
    # statements with a network call between them: the token in the database was
    # already the new one when the send failed, so the 500 this used to return
    # told the user nothing had happened while the code they had been sent
    # earlier had just been invalidated.
    entry_id = outbox.enqueue(
        outbox.TOPIC_EMAIL_VERIFICATION, {"to": user.email, "code": code}
    )
    db.session.commit()
    outbox.publish_soon(entry_id)

    return AuthResult(status=200, body=dict(RESEND_UNIFORM_BODY), user=user)


# ---------------------------------------------------------------------------
# Password reset (passwordless sign-in by OTP)
# ---------------------------------------------------------------------------

def request_password_reset(*, email: str) -> AuthResult:
    """Send a 6-digit sign-in OTP, disclosing nothing about who has an account.

    Answers ``200 reset_sent`` whether or not the address names a confirmed
    account.  The 404 that stood here until S1 -- "No account found with that
    email address." -- was the cleanest enumeration oracle in the application,
    and the 2026-09 audit probed it live: POST a mailing list, keep the 200s,
    and the result is a verified list of this product's users.  Its own
    docstring had been carrying the fix as a deferred to-do since Phase 1b.

    ``verify_password_reset`` was already written to hold up its half of this:
    every one of its failure modes answers the same ``invalid_or_expired_code``,
    so the code someone types after this 200 cannot re-open the question.

    The UI stays coherent because it never distinguished the two either -- it
    navigates to the code-entry screen on 200 and shows the server's wording on
    an error, so an unknown address now reaches a screen that says a code was
    sent and never receives one, which is the standard shape of this flow.
    """
    email = (email or "").strip().lower()

    user = user_repository.find_by_email(email)
    if not user or not getattr(user, "email_confirmed", False):
        # No row to write, no email to owe, nothing to disclose.  An unconfirmed
        # account lands here too: this endpoint mints a *session*, so handing
        # one to an address nobody has proved they control would make email
        # confirmation optional.
        return AuthResult(status=200, body=dict(RESET_UNIFORM_BODY), user=user)

    code = domain.generate_verification_code()
    user.reset_token = code
    user.reset_sent_at = domain.utcnow()
    entry_id = outbox.enqueue(
        outbox.TOPIC_EMAIL_PASSWORD_RESET, {"to": user.email, "code": code}
    )
    db.session.commit()
    outbox.publish_soon(entry_id)

    return AuthResult(status=200, body=dict(RESET_UNIFORM_BODY), user=user)


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
        return _error(400, RESET_INVALID_OR_EXPIRED)

    if domain.is_code_expired(user.reset_sent_at):
        return _error(400, RESET_INVALID_OR_EXPIRED)

    if user.reset_token != code:
        return _error(400, RESET_INVALID_OR_EXPIRED)

    user.reset_token = None
    user.reset_sent_at = None
    account = _account(user)
    db.session.commit()

    return AuthResult(
        status=200,
        body={"message": "login successful", "user": account},
        user=user,
        issue_token=True,
    )
