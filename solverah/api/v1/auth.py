"""Authentication endpoints -- ``/api/v1/auth/*``.

Part 5.2's auth block.  Phase 1a moved these handlers out of ``app.py`` at their
original paths; Phase 1b renamed them onto ``/auth/...`` and deleted both the
old rules and the unversioned aliases that had kept the deployed frontend
working through the cutover.

The handlers do four things and nothing else: read the request, call a service,
translate the result into a response, and attach the JWT cookie when the service
says a session was established.  All seven rules -- lockout counting, the
confirmation gate, code expiry, the uniform reset error string -- live in
``solverah/services/auth_service.py``, so they are testable without a request
context and callable from a worker.

Two conventions here are load-bearing rather than stylistic.

**Rate limits go below the route decorator.**  ``Blueprint.route`` registers the
function object it is handed and returns it unchanged, so a limiter written
*above* it wraps something Flask never calls.  Every ``@limiter.limit`` in the
pre-Phase-1 ``app.py`` was written that way and enforced nothing at all -- the
5/minute on login, the 3/minute on password reset, all of it inert.
``tests/test_rate_limits.py`` is the regression cover.

**Limits are ``shared_limit`` with an explicit scope, not ``limit``.**  During
the cutover that was what let a superseded path and its replacement count into
one bucket; both paths are gone now, and the scope stays for a different reason.
Flask-Limiter composes its storage key from the scope when one is given and from
the *endpoint name* when one is not, so dropping it would rename every live
bucket at deploy time and hand every caller a fresh allowance mid-release.  The
scope names the operation, which is the thing that has not changed.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    get_csrf_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
    unset_jwt_cookies,
)

from solverah.domain.validation import is_valid_email
from solverah.extensions import bcrypt, limiter
from solverah.openapi import document
from solverah.repositories import assessment_repository, user_repository
from solverah.schemas import LegacyError
from solverah.schemas.auth import (
    ConfirmEmailRequest,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    MessageResponse,
    PasswordResetRequest,
    PasswordResetVerifyRequest,
    PasswordResetVerifyResponse,
    RegisterRequest,
    RegisterResponse,
    ResendConfirmationRequest,
    SessionResponse,
)
from solverah.services import auth_service
from validators import validate_password

__all__ = ["auth_bp"]

auth_bp = Blueprint("auth", __name__)

_AUTHENTICATED = ["accessTokenCookie"]

#: Rate-limit buckets, named per operation. See the module docstring for why
#: these are explicit scopes on ``shared_limit`` rather than bare ``limit``.
_SCOPE_LOGIN = "auth:login"
_SCOPE_REGISTER = "auth:register"
_SCOPE_CONFIRM = "auth:confirm-email"
_SCOPE_RESEND = "auth:resend-confirmation"
_SCOPE_FORGOT = "auth:password-forgot"
_SCOPE_RESET = "auth:password-reset"


def _session_user():
    """The account behind the JWT, or None.

    The identity claim is the user's email -- every ``create_access_token`` call
    issues ``identity=user.email``.
    """
    return user_repository.find_by_email(get_jwt_identity())


def _respond(result: auth_service.AuthResult):
    """Turn an :class:`AuthResult` into a Flask response.

    When the service reports a session was established, mint the access token
    here rather than in the service: ``create_access_token`` needs the app's JWT
    configuration, and keeping it at the HTTP boundary is what allows the service
    to run in a worker.
    """
    if not result.issue_token:
        return jsonify(result.body), result.status

    access_token = create_access_token(identity=result.user.email)
    body = dict(result.body)
    body["csrfToken"] = get_csrf_token(access_token)
    response = jsonify(body)
    set_access_cookies(response, access_token)
    return response, result.status


def _wp_v2_completed(user_id: int) -> bool:
    """Whether this user has completed the CURRENT Work Pulse instrument.

    The 24-item person-side assessment, read through assessment_store -- the only
    sanctioned read path (D-01 / tests/test_employer_visibility.py).

    Never allowed to break login: this flag gates a banner, and a wrong False
    re-shows a prompt to someone who already finished -- visible and recoverable
    -- while an exception here would be an authentication outage. The error is
    logged, not swallowed.
    """
    from assessment_store import has_completed_assessment

    try:
        return has_completed_assessment(user_id)
    except Exception as exc:  # noqa: BLE001 -- deliberate boundary, see docstring
        current_app.logger.error("wp_v2_completed check failed for user %s: %s", user_id, exc)
        return False


# ---------------------------------------------------------------------------
# Registration and sign-in
# ---------------------------------------------------------------------------

@document(
    "Create an account and send its verification code",
    tags=["auth"],
    request=RegisterRequest,
    responses={201: RegisterResponse, 400: LegacyError},
    security=[],
    enforce=True,
)
@auth_bp.route("/auth/register", methods=["POST"])
@limiter.shared_limit("5 per minute", scope=_SCOPE_REGISTER)
def register():
    """POST /auth/register - Create a new user account.

    Creates the user with ``email_confirmed=False`` and sends a 6-digit OTP. The
    user must confirm their email before they can log in. Profile data is
    pre-seeded with a blank default profile appropriate for the given role.

    The OTP is written to the outbox inside the same transaction as the account
    (Phase 3), so there is no longer a second call here to make it best-effort:
    a created account and an owed verification email are one commit.
    """
    data = request.get_json(silent=True) or {}
    result = auth_service.register(
        email=data.get("email") or "",
        password=data.get("password") or "",
        name=data.get("name"),
        terms_accepted=data.get("terms_accepted"),
        terms_version=data.get("terms_version"),
        hash_password=bcrypt.generate_password_hash,
        validate_password=validate_password,
    )
    return _respond(result)


@document(
    "Authenticate a user and issue a JWT cookie",
    tags=["auth"],
    request=LoginRequest,
    responses={200: LoginResponse, 401: LegacyError, 403: LegacyError, 423: LegacyError},
    security=[],
    enforce=True,
)
@auth_bp.route("/auth/login", methods=["POST"])
@limiter.shared_limit("5 per minute", scope=_SCOPE_LOGIN)
def login():
    """POST /auth/login - Authenticate a user and issue a JWT cookie.

    Validates credentials, enforces account lockout after MAX_LOGIN_ATTEMPTS
    consecutive failures, and requires email confirmation before granting
    access. On success, sets an HttpOnly JWT cookie and returns the CSRF token
    in the response body (so the frontend can attach it as X-CSRF-TOKEN on
    mutating requests).
    """
    data = request.get_json(silent=True) or {}
    return _respond(
        auth_service.login(
            email=data.get("email") or "",
            password=data.get("password") or "",
            check_password=bcrypt.check_password_hash,
            wp_v2_completed=_wp_v2_completed,
        )
    )


@document(
    "Clear the JWT cookie",
    tags=["auth"],
    responses={200: LogoutResponse},
    security=[],
    enforce=True,
)
@auth_bp.route("/auth/logout", methods=["POST"])
def logout():
    """POST /auth/logout - Clear the JWT cookie server-side.

    Flask-JWT-Extended's unset_jwt_cookies removes the access-token cookie from
    the response, effectively ending the session. The JWT itself stays valid
    until it expires -- clearing the cookie ends the browser session but cannot
    revoke the token, which is what Part 5.3's database-backed refresh tokens
    are for.
    """
    resp = jsonify({"message": "logout successful"})
    unset_jwt_cookies(resp)
    return resp


@document(
    "Probe the current session without loading the user document",
    tags=["auth"],
    responses={200: SessionResponse, 401: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
)
@auth_bp.route("/auth/session", methods=["GET"])
@jwt_required()
def session():
    """GET /auth/session - identity, CSRF token, and flags. Writes nothing.

    This is the fix for P0-3. The frontend restored its session by calling
    GET /profile, which returned the entire profile_data blob and committed an
    AuditLog row on the way out -- a write on the hottest read in the system, on
    every page load, for data the app shell does not render.

    This answers the same question with four identity fields, the CSRF token,
    and four booleans, and it does not write. A client that needs the profile
    asks GET /me/profile, which is what splitting the god-endpoint bought.
    """
    user = _session_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    finished = assessment_repository.completed_kinds(user.id)
    return jsonify(
        {
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
            },
            "csrf_token": get_jwt().get("csrf"),
            "flags": {
                "email_confirmed": bool(getattr(user, "email_confirmed", False)),
                "wpl_completed": "work_pulse" in finished,
                "wpll_completed": "wpll" in finished,
                "wp_v2_completed": _wp_v2_completed(user.id),
            },
        }
    )


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------

@document(
    "Verify the 6-digit code sent at registration",
    tags=["auth"],
    request=ConfirmEmailRequest,
    responses={200: MessageResponse, 400: LegacyError},
    security=[],
    enforce=True,
)
@auth_bp.route("/auth/email/verify", methods=["POST"])
@limiter.shared_limit("5 per minute", scope=_SCOPE_CONFIRM)
def verify_email():
    """POST /auth/email/verify - Verify the 6-digit OTP sent at registration.

    Checks that the code matches, has not expired (default 15 min window), and
    clears the token fields on success so the code cannot be reused.
    """
    data = request.get_json() or {}
    return _respond(
        auth_service.confirm_email(
            email=data.get("email") or "",
            code=data.get("code") or "",
        )
    )


@document(
    "Issue a fresh verification code for an unconfirmed account",
    tags=["auth"],
    request=ResendConfirmationRequest,
    # No 500 branch any more: Phase 3 made the send an outbox row committed with
    # the token rotation, so an unreachable provider is a delayed email rather
    # than a failed request. `SendEmailFailureResponse` went with it.
    #
    # No 404 branch either, as of S1: an unknown address and an already-confirmed
    # one both answer 200 now, because a status code that separates them is a
    # user-enumeration oracle. The remaining 400 is malformed-email only, which
    # depends on the string and not on who owns it.
    responses={
        200: MessageResponse,
        400: LegacyError,
    },
    security=[],
    enforce=True,
    description=(
        "Answers `200` whether or not the address names an unconfirmed "
        "account. The three outcomes -- code sent, already confirmed, no such "
        "account -- are deliberately indistinguishable to the caller (S1); "
        "only the addressee learns which happened. A `400` here means the "
        "address itself did not parse."
    ),
)
@auth_bp.route("/auth/email/verify/resend", methods=["POST"])
@limiter.shared_limit("5 per minute", scope=_SCOPE_RESEND)
def resend_verification():
    """POST /auth/email/verify/resend - Issue a fresh OTP for unconfirmed accounts.

    Regenerates and re-sends the 6-digit verification code. Rate-limited to 5
    per minute to prevent abuse.
    """
    data = request.get_json() or {}
    return _respond(
        auth_service.resend_confirmation(
            email=data.get("email") or "",
            is_valid_email=is_valid_email,
        )
    )


# ---------------------------------------------------------------------------
# Passwordless sign-in
# ---------------------------------------------------------------------------

@document(
    "Send a sign-in code to a confirmed account",
    tags=["auth"],
    request=PasswordResetRequest,
    # 200 is the only answer as of S1. The 404 that used to mean "no account
    # found with that email address" was a user-enumeration oracle: POST a
    # mailing list, keep the 200s, get a verified user list.
    responses={200: MessageResponse},
    security=[],
    enforce=True,
    description=(
        "Answers `200 reset_sent` whether or not the address names a "
        "confirmed account, so the response cannot be used to test whether "
        "someone has an account here (S1). A code is sent only when one does. "
        "`POST /auth/password/reset` holds up the other half: all of its "
        "failures answer the same `invalid_or_expired_code`."
    ),
)
@auth_bp.route("/auth/password/forgot", methods=["POST"])
@limiter.shared_limit("3 per minute", scope=_SCOPE_FORGOT)
def forgot_password():
    """POST /auth/password/forgot - Send a 6-digit OTP for passwordless login."""
    return _respond(
        auth_service.request_password_reset(
            email=(request.get_json(silent=True) or {}).get("email") or "",
        )
    )


@document(
    "Exchange a sign-in code for a session",
    tags=["auth"],
    request=PasswordResetVerifyRequest,
    responses={200: PasswordResetVerifyResponse, 400: LegacyError},
    security=[],
    enforce=True,
)
@auth_bp.route("/auth/password/reset", methods=["POST"])
@limiter.shared_limit("5 per minute", scope=_SCOPE_RESET)
def reset_password():
    """POST /auth/password/reset - Validate OTP and issue a JWT.

    Validates the 6-digit OTP, clears it on success, and issues a JWT cookie
    plus CSRF token so the user is fully logged in without a password.
    """
    data = request.get_json(silent=True) or {}
    return _respond(
        auth_service.verify_password_reset(
            email=data.get("email") or "",
            code=data.get("code") or "",
        )
    )
