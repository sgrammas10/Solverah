"""Authentication endpoints.

Served at ``/api/v1/<rule>`` and, for the length of the frontend cutover, at
``/api/<rule>`` -- see ``solverah/factory.py:register_legacy_aliases``.  Paths,
bodies, and status codes are unchanged from the handlers these replace.

The handlers here do four things and nothing else: read the request, call a
service, translate the result into a response, and attach the JWT cookie when
the service says a session was established.  All seven rules -- lockout counting,
the confirmation gate, code expiry, the uniform reset error string -- live in
``solverah/services/auth_service.py``, so they are testable without a request
context and callable from a worker.

Rate limits are attached below the route decorator so the limit applies to the
function Flask registered.  Because ``register_legacy_aliases`` binds the legacy
path to the *same endpoint*, both paths share one bucket: ``POST /api/login`` and
``POST /api/v1/login`` cannot be alternated to get twice the allowance.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    get_csrf_token,
    set_access_cookies,
    unset_jwt_cookies,
)

from solverah.extensions import bcrypt, limiter
from solverah.openapi import document
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
    SendEmailFailureResponse,
)
from solverah.domain.validation import is_valid_email
from solverah.services import auth_service
from validators import validate_password

__all__ = ["auth_bp"]

auth_bp = Blueprint("auth", __name__)


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


@document(
    "Create an account and send its verification code",
    tags=["auth"],
    request=RegisterRequest,
    responses={201: RegisterResponse, 400: LegacyError},
    security=[],
)
@auth_bp.route("/register", methods=["POST"])
@limiter.limit("5 per minute")
def register():
    """POST /register - Create a new user account.

    Creates the user with ``email_confirmed=False`` and sends a 6-digit OTP. The
    user must confirm their email before they can log in. Profile data is
    pre-seeded with a blank default profile appropriate for the given role.
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
    if result.ok and result.user is not None:
        # Best-effort; a mail failure must not turn a created account into an error.
        auth_service.send_registration_code(
            result.user, result.user.confirmation_token, current_app.logger
        )
    return _respond(result)


@document(
    "Authenticate a user and issue a JWT cookie",
    tags=["auth"],
    request=LoginRequest,
    responses={200: LoginResponse, 401: LegacyError, 403: LegacyError, 423: LegacyError},
    security=[],
)
@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    """POST /login - Authenticate a user and issue a JWT cookie.

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
)
@auth_bp.route("/logout", methods=["POST"])
def logout():
    """POST /logout - Clear the JWT cookie server-side.

    Flask-JWT-Extended's unset_jwt_cookies removes the access-token cookie from
    the response, effectively ending the session.
    """
    resp = jsonify({"message": "logout successful"})
    unset_jwt_cookies(resp)
    return resp


@document(
    "Verify the 6-digit code sent at registration",
    tags=["auth"],
    request=ConfirmEmailRequest,
    responses={200: MessageResponse, 400: LegacyError},
    security=[],
)
@auth_bp.route("/confirm-email", methods=["POST"])
@limiter.limit("5 per minute")
def confirm_email():
    """POST /confirm-email - Verify the 6-digit OTP sent at registration.

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
    responses={
        200: MessageResponse,
        400: LegacyError,
        404: LegacyError,
        500: SendEmailFailureResponse,
    },
    security=[],
)
@auth_bp.route("/resend-confirmation", methods=["POST"])
@limiter.limit("5 per minute")
def resend_confirmation():
    """POST /resend-confirmation - Issue a fresh OTP for unconfirmed accounts.

    Regenerates and re-sends the 6-digit verification code. Rate-limited to 5
    per minute to prevent abuse.
    """
    data = request.get_json() or {}
    return _respond(
        auth_service.resend_confirmation(
            email=data.get("email") or "",
            is_valid_email=is_valid_email,
            logger=current_app.logger,
        )
    )


@document(
    "Send a sign-in code to a confirmed account",
    tags=["auth"],
    request=PasswordResetRequest,
    responses={200: MessageResponse, 404: LegacyError, 500: LegacyError},
    security=[],
)
@auth_bp.route("/request-password-reset", methods=["POST"])
@limiter.limit("3 per minute")
def request_password_reset():
    """POST /request-password-reset - Send a 6-digit OTP for passwordless login."""
    return _respond(
        auth_service.request_password_reset(
            email=(request.get_json(silent=True) or {}).get("email") or "",
            logger=current_app.logger,
        )
    )


@document(
    "Exchange a sign-in code for a session",
    tags=["auth"],
    request=PasswordResetVerifyRequest,
    responses={200: PasswordResetVerifyResponse, 400: LegacyError},
    security=[],
)
@auth_bp.route("/verify-password-reset", methods=["POST"])
@limiter.limit("5 per minute")
def verify_password_reset():
    """POST /verify-password-reset - Validate OTP and issue a JWT.

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
