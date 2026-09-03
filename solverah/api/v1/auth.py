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

import re
from urllib.parse import urlsplit

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    get_csrf_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
    unset_jwt_cookies,
    verify_jwt_in_request,
)

from security import REFRESH_PER_IP_LIMIT
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
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    ResendConfirmationRequest,
    SessionResponse,
)
from solverah.services import auth_service, refresh_tokens
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
_SCOPE_REFRESH = "auth:refresh"


def _session_user():
    """The account behind the JWT, or None.

    The identity claim is the user's email -- every ``create_access_token`` call
    issues ``identity=user.email``.
    """
    return user_repository.find_by_email(get_jwt_identity())


def _respond(result: auth_service.AuthResult):
    """Turn an :class:`AuthResult` into a Flask response.

    When the service reports a session was established, mint the tokens here
    rather than in the service: ``create_access_token`` needs the app's JWT
    configuration and the cookies need a response, and keeping both at the HTTP
    boundary is what allows the service to run in a worker.

    Two tokens now leave here, not one, and the order matters.  The refresh
    session is opened *first* because its family id goes into the access token's
    ``sid`` claim -- that claim is how ``POST /auth/logout`` knows which family
    to revoke when the refresh cookie itself is not sent to it (it is
    path-scoped to ``/auth/refresh``).
    """
    if not result.issue_token:
        return jsonify(result.body), result.status

    response, _ = start_session(result.user, result.body)
    return response, result.status


def start_session(user, body: dict):
    """Open a refresh session for *user* and answer with both cookies set.

    Shared with ``solverah/api/v1/intake.py``, which establishes a session on
    its own claim/sign-in paths.  It is one function rather than two similar
    ones on purpose: a sign-in path that minted an access token and forgot the
    refresh token would hand the user a session that dies in fifteen minutes
    with nothing to renew it, and that failure is invisible until the sixteenth
    minute.

    Args:
        user: The account the session belongs to.
        body: The response body the caller has already assembled.  The CSRF
            token is added to it here, under the ``csrfToken`` key the frontend
            has always read.

    Returns:
        ``(response, session)`` -- the Flask response with both cookies
        attached, and the :class:`refresh_tokens.IssuedSession` behind it.
    """
    session = refresh_tokens.issue(user)
    access_token = create_access_token(
        identity=user.email, additional_claims={"sid": session.family_id}
    )
    payload = dict(body)
    payload["csrfToken"] = get_csrf_token(access_token)
    response = jsonify(payload)
    set_access_cookies(response, access_token)
    set_refresh_cookie(response, session.token)
    return response, session


def set_refresh_cookie(response, raw_token: str) -> None:
    """Attach the opaque refresh token to *response*.

    Not ``flask_jwt_extended.set_refresh_cookies``, and the reason is the whole
    point of the design: that helper decodes the value it is given to read a
    ``csrf`` claim out of it, which works only for a JWT.  This token is opaque
    by decision (A7) -- a JWT refresh token is self-validating and therefore
    unrevocable, which is the defect being fixed -- so it has no claims to
    decode.

    Every attribute is read from the same JWT config keys the helper reads, so
    ``unset_jwt_cookies`` on logout clears exactly this cookie: same name, same
    path, same domain, same SameSite.  A clear that differs by one character
    leaves the credential in the jar.

    ``max_age`` is set explicitly rather than left to ``JWT_SESSION_COOKIE``.
    The access cookie is a session cookie and stays one; a thirty-day refresh
    token in a cookie that dies with the browser window would be a thirty-day
    row nobody can ever present.
    """
    config = current_app.config
    response.set_cookie(
        config.get("JWT_REFRESH_COOKIE_NAME", "refresh_token_cookie"),
        value=raw_token,
        max_age=int(refresh_tokens.REFRESH_TOKEN_DAYS * 24 * 60 * 60),
        secure=config.get("JWT_COOKIE_SECURE", False),
        httponly=True,
        domain=config.get("JWT_COOKIE_DOMAIN"),
        path=config.get("JWT_REFRESH_COOKIE_PATH", "/"),
        samesite=config.get("JWT_COOKIE_SAMESITE"),
    )


def _origin_allowed(origin: str) -> bool:
    """Whether *origin* is one this deployment serves.

    Reads the allowlist the factory resolved (``solverah_cors_rules``) so this
    check and the CORS configuration cannot disagree about which origins are
    ours.  Exact entries are compared as strings and patterns with ``re.match``
    -- the same call flask-cors makes, and the reason the two kinds are kept
    apart: reading ``https://solverah.com`` as a regex would also match
    ``https://solverahXcom``, a domain somebody else can register.
    """
    exact, patterns = current_app.extensions.get("solverah_cors_rules", ([], []))
    if origin in exact:
        return True
    return any(re.match(pattern, origin) for pattern in patterns)


def _reject_cross_site():
    """CSRF control for ``POST /auth/refresh``.  Returns a response, or None.

    **Why this endpoint cannot use the double-submit token every other
    state-changing route uses.**  That scheme works because the client holds the
    CSRF token in memory, handed to it in the body of the response that signed
    it in.  ``POST /auth/refresh`` is reached at exactly the moment the client
    holds nothing: a returning visitor's first request after fifteen minutes
    away is a page load, the session probe 401s, and the tab has no token
    because it has not been signed in yet *in this page's lifetime*.  The cookie
    flask-jwt-extended writes for that purpose is unreadable here, because the
    SPA is served from ``solverah.com`` and the API from ``api.solverah.com`` --
    which is also why the token is echoed in the login body in the first place.
    A double-submit requirement on this route would mean every visitor who
    closed the tab is signed out, which is the feature this round exists to
    build, inverted.

    **What is checked instead**, and it is a CSRF control rather than a
    substitute for one:

    * ``Origin`` (falling back to ``Referer``) must be an origin this deployment
      serves.  A browser sets these itself and a page cannot forge them, so a
      form or ``fetch`` on ``evil.com`` announces ``evil.com`` and is refused.
      This is the standard defence for a cookie-authenticated endpoint that
      cannot carry a token, and against an attacker who can *write* a cookie it
      is stronger than double-submit, which such an attacker satisfies by
      writing both halves.
    * The request must be ``application/json``.  A cross-site HTML form can only
      send three content types and this is not one of them, so the check closes
      the case where a browser sends no ``Origin`` at all.

    Neither check is load-bearing alone and together they leave nothing that a
    cross-site page can send.  Both are recorded in the S3 round report as the
    one place the mechanism -- not the requirement -- departs from the other
    routes.
    """
    if request.mimetype != "application/json":
        return jsonify({"error": "unsupported_media_type"}), 415

    origin = request.headers.get("Origin")
    if origin is None:
        referer = request.headers.get("Referer")
        if referer:
            parts = urlsplit(referer)
            origin = "%s://%s" % (parts.scheme, parts.netloc) if parts.scheme else None

    # No Origin and no Referer is a non-browser caller -- curl, a test client, a
    # health check. CSRF is an attack a browser is tricked into making, so there
    # is nothing here to defend against; the credential still has to be valid.
    if origin is None:
        return None

    if not _origin_allowed(origin):
        return jsonify({"error": "cross_site_request_refused"}), 403
    return None


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


def _revocable_family():
    """The session family this request may end, or None.

    Read from the ``sid`` claim on the access token rather than from the refresh
    cookie, because the refresh cookie is path-scoped to ``/auth/refresh`` and
    the browser therefore does not send it here.  In practice the access token
    is always fresh at this point: the client refreshes before retrying any
    401, so by the time a logout is sent it is carrying a fifteen-minute token
    minted seconds ago.

    Verification failures are swallowed on purpose, and each swallowed case is
    the right answer rather than a shrug:

    * **No token, or an expired one.**  There is no session to revoke and the
      cookies still need clearing.  Logout has always answered 200 for a caller
      with no session and continues to.
    * **A token with no ``sid``.**  Issued before this round shipped, so it has
      no refresh family behind it -- nothing to revoke.  This is what keeps
      mid-session users from meeting an error on the first logout after deploy.
    * **A missing or wrong CSRF header.**  This is the one worth stating
      plainly.  A cross-site page can still force a logout -- audit finding #25,
      LOW, and unchanged here -- but because that request cannot satisfy the
      CSRF check it lands in this branch, so it clears cookies in the victim's
      browser and revokes nothing server-side.  Forged logout stays the nuisance
      it was; it does not become a way to end somebody's session for real.
    """
    try:
        verify_jwt_in_request(optional=True)
    except Exception:  # noqa: BLE001 -- every failure means "no family", see above
        return None
    return (get_jwt() or {}).get("sid")


@document(
    "End the session: revoke its refresh family and clear the cookies",
    tags=["auth"],
    responses={200: LogoutResponse},
    security=[],
    enforce=True,
    description=(
        "Revokes the refresh-token family behind the session server-side and "
        "clears both cookies. Answers `200` whether or not there was a session "
        "to end. The access token already issued is not revoked and remains "
        "valid for the rest of its fifteen minutes -- see the handler's "
        "docstring for why that residue is bounded and deliberate."
    ),
)
@auth_bp.route("/auth/logout", methods=["POST"])
def logout():
    """POST /auth/logout - End the session server-side and clear the cookies.

    **This is audit finding 1.1.**  Until S3 this handler called
    ``unset_jwt_cookies`` and nothing else, and its own docstring said what that
    cost: "the JWT itself stays valid until it expires -- clearing the cookie
    ends the browser session but cannot revoke the token".  An attacker holding
    a captured cookie kept full access for up to an hour after the victim logged
    out, and nothing short of rotating ``JWT_SECRET_KEY`` across the fleet
    stopped them.

    Now the refresh family dies here.  Every descendant of that sign-in is
    retired as ``logged_out``, so the attacker's copy of the refresh token buys
    nothing: presenting it answers 401, and because the reason is not
    ``rotated`` it is never inside the rotation grace window however soon it is
    presented.

    **The residue, stated rather than glossed.**  An access token already minted
    is a signed JWT and stays valid until its ``exp``.  Fifteen minutes, down
    from sixty, and that is the trade this design makes deliberately: a denylist
    checked on every request would close the last fifteen minutes at the cost of
    a lookup on the hottest path in the application, and A7 chose one lookup per
    *refresh* over one per request. What used to be an hour of full access after
    logout is now a quarter of an hour, and nothing survives past it.
    """
    family_id = _revocable_family()
    if family_id:
        refresh_tokens.revoke_family(
            family_id, reason=refresh_tokens.REASON_LOGGED_OUT
        )
    resp = jsonify({"message": "logout successful"})
    unset_jwt_cookies(resp)
    return resp


@document(
    "Exchange the refresh cookie for a new access token",
    tags=["auth"],
    responses={200: RefreshResponse, 401: LegacyError, 403: LegacyError, 415: LegacyError},
    security=[],
    enforce=True,
    description=(
        "Rotates the refresh token: the presented one is retired and a new one "
        "replaces it in the cookie. Presenting a token that was already retired "
        "-- outside the short concurrency grace window -- is treated as "
        "evidence the token leaked and revokes every token in that sign-in's "
        "family. Every failure answers the same `401 invalid_refresh_token`, so "
        "the response cannot be used to tell a stale token from a stolen one "
        "from one that never existed."
    ),
)
@auth_bp.route("/auth/refresh", methods=["POST"])
@limiter.shared_limit(REFRESH_PER_IP_LIMIT, scope=_SCOPE_REFRESH)
def refresh():
    """POST /auth/refresh - Rotate the refresh token, mint a new access token.

    The one door onto ``user_sessions``.  The decision -- rotate, grace, reuse,
    expired, unknown -- belongs to ``solverah.services.refresh_tokens``; this
    handler reads the cookie, checks the request is not cross-site, and turns
    the outcome into cookies and a status code.

    Two of the five outcomes succeed, and only one of them sets a refresh
    cookie:

    * ``rotated`` -- the ordinary path.  New access token, new refresh cookie.
    * ``grace`` -- a second request presenting a token the first one just
      rotated (two tabs, or two parallel queries in one tab).  A new access
      token and **no** ``Set-Cookie``: the successor the first request minted is
      already in the browser's jar, because cookies are per-browser and not
      per-tab, so re-setting anything here would be writing over a live token
      with nothing.

    A failure clears both cookies.  Leaving a dead refresh cookie in the jar
    means the client presents it again on the next 401, which re-revokes an
    already-dead family on every page load -- noise in the audit trail that
    reads exactly like an attack.
    """
    refused = _reject_cross_site()
    if refused is not None:
        return refused

    cookie_name = current_app.config.get("JWT_REFRESH_COOKIE_NAME", "refresh_token_cookie")
    outcome = refresh_tokens.rotate(request.cookies.get(cookie_name) or "")

    if not outcome.ok:
        response = jsonify({"error": "invalid_refresh_token"})
        unset_jwt_cookies(response)
        return response, 401

    access_token = create_access_token(
        identity=outcome.user.email, additional_claims={"sid": outcome.family_id}
    )
    response = jsonify(
        {"message": "refreshed", "csrfToken": get_csrf_token(access_token)}
    )
    set_access_cookies(response, access_token)
    if outcome.token is not None:
        set_refresh_cookie(response, outcome.token)
    return response


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
