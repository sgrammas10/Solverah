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
    create_access_token,
    get_csrf_token,
    get_jwt_identity,
    jwt_required,
    set_access_cookies,
)

from solverah.extensions import bcrypt, limiter
from solverah.openapi import document
from solverah.repositories import user_repository
from solverah.schemas import LegacyError, OkResponse
from solverah.schemas.intake import (
    EarlyAccessRequest,
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
from solverah.services import intake_service
from validators import validate_password

__all__ = ["intake_bp"]

intake_bp = Blueprint("intake", __name__)

_AUTHENTICATED_WRITE = ["accessTokenCookie", "csrfHeader"]


def _respond(result: intake_service.IntakeResult):
    """Turn an :class:`IntakeResult` into a Flask response, minting a JWT if asked."""
    if not result.issue_token:
        return jsonify(result.body), result.status

    access_token = create_access_token(identity=result.user.email)
    body = dict(result.body)
    body["csrfToken"] = get_csrf_token(access_token)
    response = jsonify(body)
    set_access_cookies(response, access_token)
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


@document(
    "Register interest from the landing-page modal",
    tags=["intake"],
    request=EarlyAccessRequest,
    responses={200: OkResponse, 400: LegacyError, 500: LegacyError},
    security=[],
)
@intake_bp.route("/early-access-request", methods=["POST"])
def early_access_request():
    """POST /early-access-request - Early-access interest form (no resume).

    Accepts a lightweight JSON body from the landing-page modal and forwards the
    details to info@solverah.com via Resend. Does not persist to the database.
    """
    return _respond(
        intake_service.early_access_request(
            request.get_json(silent=True) or {}, current_app.logger
        )
    )


@document(
    "Presign an upload URL for an anonymous resume submission",
    tags=["intake"],
    request=IntakePresignRequest,
    responses={200: IntakePresignResponse, 400: LegacyError},
    security=[],
)
@intake_bp.route("/intake/presign", methods=["POST"])
@limiter.limit("10 per minute")
def presign():
    """POST /intake/presign - Generate a presigned S3 PUT URL for resume upload.

    Step 1 of 2 in the intake flow. The client sends the file's MIME type and
    size; the server validates both, generates a UUID-based object key, and
    returns a short-lived presigned PUT URL for direct browser-to-R2 upload.
    """
    data, error = _require_json()
    if error:
        return error

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
)
@intake_bp.route("/intake/finalize", methods=["POST"])
@limiter.limit("20 per minute")
def finalize():
    """POST /intake/finalize - Commit an intake submission after resume upload.

    Step 2 of 2. The client provides personal details and the object key from
    the presign step. The server validates all fields, verifies the uploaded
    object exists in R2 and matches the declared size and type, inserts the row,
    and sends an internal notification email.
    """
    data, error = _require_json()
    if error:
        return error

    return _respond(intake_service.finalize(data, current_app.logger))


@document(
    "Register a new account from an intake submission",
    tags=["intake"],
    request=IntakeCreateAccountRequest,
    responses={201: IntakeCreateAccountResponse, 400: LegacyError, 404: LegacyError},
    security=[],
)
@intake_bp.route("/intake/create-account", methods=["POST"])
@limiter.limit("5 per minute")
def intake_create_account():
    """POST /intake/create-account - Register a new account from an intake submission.

    Looks up the intake record by submission_id, validates the chosen password,
    creates a User row with email_confirmed=False, and sends a verification
    email. The intake record's status is updated to "account_created".
    """
    data, error = _require_json()
    if error:
        return error

    return _respond(
        intake_service.create_account(
            data,
            hash_password=bcrypt.generate_password_hash,
            validate_password=validate_password,
        )
    )


@document(
    "Sign in and attach an intake submission to an existing account",
    tags=["intake"],
    request=IntakeSignInRequest,
    responses={
        200: IntakeSignInResponse,
        400: LegacyError,
        401: LegacyError,
        403: LegacyError,
        404: LegacyError,
        423: LegacyError,
    },
    security=[],
)
@intake_bp.route("/intake/sign-in", methods=["POST"])
@limiter.limit("5 per minute")
def intake_sign_in():
    """POST /intake/sign-in - Sign in and attach an intake submission to an account.

    Used when the user already has an account and returns through the intake
    flow. After successful authentication, the intake's parsed profile data is
    merged (intake values win on conflict) into the user's existing profile.
    The intake status is updated to "account_linked".
    """
    data, error = _require_json()
    if error:
        return error

    return _respond(
        intake_service.sign_in(data, check_password=bcrypt.check_password_hash)
    )


@document(
    "Persist an anonymous quiz session onto the authenticated account",
    tags=["intake"],
    request=IntakeSaveToAccountRequest,
    responses={200: IntakeSaveToAccountResponse, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
)
@intake_bp.route("/intake/save-to-account", methods=["POST"])
@limiter.limit("10 per minute")
@jwt_required()
def intake_save_to_account():
    """POST /intake/save-to-account - Persist anonymous WPLL session data to the account.

    Called by the frontend immediately after login when sessionStorage contains
    intake data from the /start flow. Creates the user_intake row on first call;
    upserts on subsequent calls (preserves wpl_* fields if already set).
    """
    user = user_repository.find_by_email(get_jwt_identity())
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(
        intake_service.save_to_account(user, request.get_json(silent=True) or {})
    )


@document(
    "Submit the intake form as an already-authenticated user",
    tags=["intake"],
    request=IntakeLinkAccountRequest,
    responses={200: OkResponse, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
)
@intake_bp.route("/intake/link-account", methods=["POST"])
@limiter.limit("5 per minute")
@jwt_required()
def intake_link_account():
    """POST /intake/link-account - Submit the intake form for an authenticated user.

    Records the submission against the JWT identity, verifies the upload, then
    merges the parsed resume into the user's profile.
    """
    from flask import abort

    current_email = get_jwt_identity()
    user = user_repository.find_by_email(current_email)
    if user is None:
        # first_or_404() in the original; the 404 handler turns it into a
        # problem document, so the shape the client sees is unchanged.
        abort(404)

    data, error = _require_json()
    if error:
        return error

    return _respond(intake_service.link_account(user, current_email, data))
