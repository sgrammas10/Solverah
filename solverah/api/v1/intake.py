"""Public intake endpoints and the four ways to attach a submission to an account.

Paths are unchanged: ``/early-access-request``, ``/intake/presign``,
``/intake/finalize``, ``/intake/create-account``, ``/intake/sign-in``,
``/intake/save-to-account``, ``/intake/link-account`` -- now served under
``/api/v1`` with an ``/api`` alias.

The first four are unauthenticated and are the most exposed surface in the
application, which is why they carry the tightest rate limits.  Those limits
were inert before Phase 1 (see ``security._skip_when_testing`` for the decorator
ordering bug) and now enforce.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    get_jwt_identity,
    jwt_required,
    verify_jwt_in_request,
)

from security import (
    GUEST_INSIGHTS_GLOBAL_LIMIT,
    GUEST_INSIGHTS_PER_IP_LIMIT,
    global_rate_limit_key,
)
from solverah.api.v1.auth import start_session
from solverah.extensions import bcrypt, limiter
from solverah.openapi import document
from solverah.repositories import user_repository
from solverah.schemas import LegacyError, OkResponse
from solverah.schemas.intelligence import QuizInsightsRequest
from solverah.schemas.intake import (
    CLAIM_LIMITS,
    CLAIM_REQUESTS,
    CLAIM_REQUIRES_AUTH,
    STRICTEST_CLAIM_LIMIT,
    EarlyAccessRequest,
    IntakeClaimEnvelope,
    IntakeClaimRequest,
    IntakeClaimResponse,
    QuizPreviewInsightsResponse,
    IntakeCreateAccountRequest,
    IntakeCreateAccountResponse,
    IntakeFinalizeRequest,
    IntakeLinkAccountRequest,
    IntakePresignRequest,
    IntakePresignResponse,
    IntakeSaveToAccountRequest,
    IntakeSaveToAccountResponse,
    IntakeSignInRequest,
    IntakeSignInResponse,
)
from solverah.services import insight_service, intake_service
from validators import validate_password

__all__ = ["intake_bp"]

intake_bp = Blueprint("intake", __name__)

_AUTHENTICATED_WRITE = ["accessTokenCookie", "csrfHeader"]

#: Rate-limit buckets, shared between each superseded handler and its
#: replacement for the length of the cutover. ``shared_limit`` rather than
#: ``limit(scope=...)``: the latter keys as ``"{endpoint}:{scope}"``, which
#: sub-divides one endpoint's bucket instead of joining two.
_SCOPE_PRESIGN = "intake:resume-ticket"
_SCOPE_FINALIZE = "intake:submission"
_SCOPE_GUEST_INSIGHTS = "intake:quiz-preview-insights"
_SCOPE_GUEST_INSIGHTS_GLOBAL = "intake:quiz-preview-insights:global"

#: Namespace for a claim's bucket, completed with the ``mode``. See
#: ``_claim_scope`` for why the mode has to be in the key.
CLAIM_SCOPE_PREFIX = "intake:claim:"


def _respond(result: intake_service.IntakeResult):
    """Turn an :class:`IntakeResult` into a Flask response, opening a session if asked.

    Delegates to ``auth.start_session`` rather than minting the access token
    here, which it did until S3.  This is a third sign-in path -- ``POST
    /intake/claims`` in ``signin`` mode -- and a sign-in path that mints an
    access token without a refresh token hands the user a session that dies
    fifteen minutes later with nothing to renew it.  One function means the
    third path cannot quietly diverge from the two in ``auth.py``;
    ``tests/test_refresh_tokens.py`` asserts every ``issue_token`` path sets the
    refresh cookie, so a fourth one cannot be added without noticing either.
    """
    if not result.issue_token:
        return jsonify(result.body), result.status

    response, _ = start_session(result.user, result.body)
    return response, result.status


def _require_json():
    """Return the body, or an error response when it is empty.

    Four of these handlers reject an empty body with a specific message before
    doing anything else, and the frontend renders it. Preserved exactly.
    """
    data = request.get_json(silent=True) or {}
    if not data:
        return None, (jsonify({"error": "JSON body required"}), 400)
    return data, None


def _claim_mode() -> str:
    """The ``mode`` on the current claim body, or "" when there is none.

    Read from the parsed JSON, which Flask caches on the request, so the two
    rate-limit callables and the handler all see one parse.
    """
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        mode = payload.get("mode")
        if isinstance(mode, str):
            return mode
    return ""


def _claim_scope(_endpoint: str) -> str:
    """Rate-limit bucket for one claim, keyed by mode.

    The same decision the collapsed assessment route forces, for the same
    reason. Four handlers were four buckets; one handler is one bucket unless
    the mode is put in the key. Without this, a visitor who tried to sign in and
    then registered would be spending one allowance across two operations -- and
    an attacker probing ``sign_in`` would consume the budget of the endpoint
    that creates accounts.

    ``shared_limit`` rather than ``limit(scope=...)``: the latter builds its key
    as ``"{endpoint}:{scope}"``, which sub-divides this endpoint's bucket but
    would not join it to the superseded handler's for the length of the cutover.
    """
    return "%s%s" % (CLAIM_SCOPE_PREFIX, _claim_mode() or "unknown")


def _claim_limit() -> str:
    """The limit for the mode being claimed.

    Per-mode because the four were not all the same number: three ran at 5 per
    minute and ``save-to-account`` at 10. An unrecognised mode gets the
    strictest of them -- a client that cannot name a valid mode should not be
    able to probe faster than one that can.
    """
    return CLAIM_LIMITS.get(_claim_mode(), STRICTEST_CLAIM_LIMIT)


@document(
    "Register interest from the landing-page modal",
    tags=["intake"],
    request=EarlyAccessRequest,
    responses={200: OkResponse, 400: LegacyError},
    security=[],
    enforce=True,
)
@intake_bp.route("/intake/early-access", methods=["POST"])
def intake_early_access():
    """POST /intake/early-access - early-access interest form (no resume).

    Writes the lead to the transactional outbox and returns 200; a worker
    delivers it to info@solverah.com. This answered 500 on a mail failure until
    Phase 3, because the lead existed only as an email and a swallowed error lost
    it. The row is durable before this returns, so there is nothing left to lose
    and nothing left to report.
    """
    return _respond(
        intake_service.early_access_request(request.get_json(silent=True) or {})
    )


@document(
    "Request an upload ticket for an anonymous resume submission",
    tags=["intake"],
    request=IntakePresignRequest,
    responses={200: IntakePresignResponse, 400: LegacyError},
    security=[],
    enforce=True,
    description=(
        "Part 5.2 places this at `/intake/submissions/{id}/resume-ticket`, and "
        "it is here instead because the id does not exist yet when this is "
        "called. The ticket is what mints it: the flow is ticket -> browser "
        "uploads to R2 -> `POST /intake/submissions` commits the row, and no "
        "row exists until the last step. A path that takes the id would need "
        "either a draft row inserted before any validation ran, or a "
        "client-generated id -- and the id is the *only* thing protecting an "
        "anonymous submission, so it has to come from a server-side CSPRNG."
    ),
)
@intake_bp.route("/intake/resume-tickets", methods=["POST"])
@limiter.shared_limit("10 per minute", scope=_SCOPE_PRESIGN)
def intake_resume_ticket():
    """POST /intake/resume-tickets - presign a PUT URL and mint a submission id.

    Step 1 of 2. The client sends the file's MIME type and size; the server
    validates both, generates a UUID-based object key, and returns a short-lived
    presigned PUT URL for a direct browser-to-R2 upload.
    """
    data = request.get_json(silent=True) or {}
    return _respond(
        intake_service.presign(
            mime=(data.get("mime") or "").strip(),
            size=int(data.get("size") or 0),
        )
    )


@document(
    "Commit an intake submission after the resume upload",
    tags=["intake"],
    request=IntakeFinalizeRequest,
    responses={200: OkResponse, 400: LegacyError},
    security=[],
    enforce=True,
)
@intake_bp.route("/intake/submissions", methods=["POST"])
@limiter.shared_limit("20 per minute", scope=_SCOPE_FINALIZE)
def intake_create_submission():
    """POST /intake/submissions - commit a submission after the resume upload.

    Step 2 of 2. Validates every field, HEADs the uploaded object to confirm it
    exists and matches the declared size and type, inserts the row, and sends an
    internal notification.

    The HEAD is not decoration. The ticket signs a ContentLength, so R2 rejects a
    body of a different size -- but nothing stops a client skipping the upload
    entirely and calling this anyway. The check is what makes the row mean "a
    resume of this size and type exists at this key".
    """
    return _respond(intake_service.finalize(request.get_json(silent=True) or {}))


@document(
    "Attach an anonymous submission or quiz session to an account",
    tags=["intake"],
    request=IntakeClaimRequest,
    request_for=lambda _view_args, payload: CLAIM_REQUESTS.get(
        (payload or {}).get("mode") if isinstance(payload, dict) else None,
        IntakeClaimEnvelope,
    ),
    responses={
        200: IntakeClaimResponse,
        201: IntakeClaimResponse,
        400: LegacyError,
        401: LegacyError,
        403: LegacyError,
        404: LegacyError,
        423: LegacyError,
    },
    security=[],
    enforce=True,
    description=(
        "Replaces `/intake/create-account`, `/intake/sign-in`, "
        "`/intake/link-account`, and `/intake/save-to-account`. All four answer "
        "the same question -- *this browser holds something anonymous, attach "
        "it to an account* -- and differ in which account and where the "
        "anonymous thing came from. `mode` is the discriminator and selects the "
        "request body, the response body, whether a JWT is required, and which "
        "rate-limit bucket the call lands in.\n\n"
        "`register` and `sign_in` are public: they are how a visitor *gets* a "
        "session, so requiring one would be circular. `link` and `session` "
        "require a JWT and the CSRF header with it.\n\n"
        "This is `/intake/claims`, not Part 5.2's "
        "`/intake/submissions/{id}/claim`, because two of the four modes have "
        "no submission id -- `link` files a new submission rather than claiming "
        "an existing one, and `session` adopts a quiz session that was never a "
        "submission at all."
    ),
)
@intake_bp.route("/intake/claims", methods=["POST"])
@limiter.shared_limit(_claim_limit, scope=_claim_scope)
def intake_claim():
    """POST /intake/claims - attach anonymous intake data to an account.

    The mode is validated before this runs (`enforce=True` against the
    per-mode model), so by here it is one of the four and its required fields
    are present.
    """
    data = request.get_json(silent=True) or {}
    mode = data.get("mode")

    if CLAIM_REQUIRES_AUTH.get(mode):
        # Not @jwt_required(): two of the four modes are deliberately public.
        # verify_jwt_in_request() is the same function the decorator calls, so
        # the cookie lookup, the signature check, and -- on a POST -- the CSRF
        # check are identical.
        verify_jwt_in_request()

    if mode == "register":
        return _respond(
            intake_service.create_account(
                data,
                hash_password=bcrypt.generate_password_hash,
                validate_password=validate_password,
            )
        )

    if mode == "sign_in":
        return _respond(
            intake_service.sign_in(data, check_password=bcrypt.check_password_hash)
        )

    current_email = get_jwt_identity()
    user = user_repository.find_by_email(current_email)
    if user is None:
        return jsonify({"error": "User not found"}), 404

    if mode == "link":
        return _respond(intake_service.link_account(user, current_email, data))

    return _respond(intake_service.save_to_account(user, data))


@document(
    "Generate AI career insights for an unauthenticated preview",
    tags=["intake"],
    request=QuizInsightsRequest,
    responses={200: QuizPreviewInsightsResponse, 400: LegacyError, 500: LegacyError},
    security=[],
    enforce=True,
    description=(
        "The unauthenticated half of the quiz-insights pair. Nothing is "
        "persisted, because there is no account yet.\n\n"
        "Rate-limited per IP *and* under a global daily ceiling. The endpoint "
        "this replaces carried `1 per day` keyed on the IP alone, which behind "
        "corporate NAT or mobile CGNAT meant one preview per office per day and "
        "read to the user as a broken quiz rather than as a limit. See "
        "`solverah/api/v1/intelligence.py` for the full reasoning."
    ),
)
@intake_bp.route("/intake/quiz-preview/insights", methods=["POST"])
@limiter.shared_limit(GUEST_INSIGHTS_GLOBAL_LIMIT, scope=_SCOPE_GUEST_INSIGHTS_GLOBAL,
                      key_func=global_rate_limit_key)
@limiter.shared_limit(GUEST_INSIGHTS_PER_IP_LIMIT, scope=_SCOPE_GUEST_INSIGHTS)
def intake_quiz_preview_insights():
    """POST /intake/quiz-preview/insights - AI insights for an anonymous preview.

    Same generation path as the authenticated endpoint; the result is returned
    and not stored.

    Answers directly rather than through this module's `_respond`: that
    helper is typed for `intake_service.IntakeResult` and reads
    `result.issue_token` to decide whether to open a session.
    `insight_service.generate_for_guest` returns a plain `InsightResult`
    (status/body only, no session to open, matching
    `intelligence.py`'s own `_respond` for the authenticated sibling route)
    -- routing it through the session-aware helper raised an `AttributeError`
    on every call (D-5, docs/BUILD_PLAN.md).
    """
    result = insight_service.generate_for_guest(
        request.get_json(silent=True) or {}, current_app.logger
    )
    return jsonify(result.body), result.status
