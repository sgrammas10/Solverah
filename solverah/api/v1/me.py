"""``/api/v1/me`` -- everything about the authenticated principal.

Part 5.2's "Me" block, and the endpoint redesign's centrepiece: the
``GET|POST /profile`` god-endpoint is split here into an identity resource, a
profile resource, a skills resource, and a resume resource, and the two
account-rights endpoints move onto ``GET /me/export`` and ``DELETE /me``.

Why the split is worth doing
----------------------------
``GET /profile`` returned the whole user document -- identity, the entire
``profile_data`` blob, and three completion flags -- and wrote an ``AuditLog``
row on the way out.  It sat on the app-boot path, so every page load shipped a
document the shell does not render and took a write lock to do it.  ``POST
/profile`` rewrote the same column whatever field had actually changed, so
editing a phone number was a read-modify-write of everything.

After the split the boot path is ``GET /auth/session`` (identity, CSRF token,
flags -- no blob, no write), the profile is fetched when a screen needs it, and
a skills edit writes through a resource that says "skills".

What the split does *not* do
----------------------------
It does not touch ``profile_data``.  The blob is still the storage; Phase 2
decomposes it.  Part 5.2 lists ``/me/experiences`` and ``/me/educations``, and
they are deliberately absent from this module: they replace
``profileData.experience[]`` and ``profileData.education[]`` *inside the blob*,
so building them now would mean CRUD endpoints performing read-modify-write on
sub-arrays of a JSON column -- which is starting the decomposition, with the
lost-update window of P0-1 widened once per list item, and none of the row-level
storage that makes the decomposition safe.  They land in Phase 2 with the tables
they need.

There is a cost to the split, recorded in ``solverah/schemas/profile.py`` where
the shapes are: a client that sent one ``POST /profile`` now sends two requests,
so P0-1's lost-update window is temporarily two windows instead of one.  That is
accepted.  ``ProfileDocument``'s envelope is what Phase 2 hangs ``version`` off
to close it.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required, unset_jwt_cookies

from solverah.extensions import limiter
from solverah.infra.storage import ALLOWED_MIME, MAX_BYTES
from solverah.openapi import document
from solverah.repositories import user_repository
from solverah.schemas import LegacyError
from solverah.schemas.account import AccountDeleteRequest, AccountDeleteResponse, AccountExportResponse
from solverah.schemas.profile import (
    CareerStatusRequest,
    CareerStatusResponse,
    DashboardResponse,
    IdentityResponse,
    IdentityUpdateRequest,
    ProfileDocument,
    ProfilePatchRequest,
    ResumeCompleteRequest,
    ResumeCompleteResponse,
    ResumeDownloadResponse,
    ResumeParseJobAccepted,
    ResumeParseJobStatus,
    ResumeTicketRequest,
    ResumeTicketResponse,
    SkillsPutRequest,
    SkillsResponse,
)
from solverah.services import account_service, profile_service, resume_jobs
from validators import clean_profile_data

__all__ = ["me_bp"]

me_bp = Blueprint("me", __name__)

_AUTHENTICATED = ["accessTokenCookie"]
_AUTHENTICATED_WRITE = ["accessTokenCookie", "csrfHeader"]

#: Rate limit for polling a resume-parse job -- the same shape as the 3b poll
#: endpoints' `POLL_LIMIT` (`solverah/api/v1/assessments.py`,
#: `solverah/api/v1/intelligence.py`).
#:
#: This route (3a) carried the identical exposure those two were built with a
#: limit to avoid: left on the `50 per hour` global default, a client polling
#: every two seconds exhausts it inside a single parse, and shares that budget
#: with every other default-limited route the same browser is using. A9's
#: per-instrument budgets do not reach a poll either way -- it is a single
#: indexed-row read with no provider call, so it spends nothing. A19 recorded
#: the exposure and deferred the fix rather than make it in passing; this is
#: that fix.
#:
#: The day cap is restated rather than dropped, same reason as the 3b routes:
#: `@limiter.limit` defaults to `override_defaults=True`, so naming only a
#: per-minute allowance would silently remove the global `200 per day` while
#: reading as a tightening.
POLL_LIMIT = "60 per minute;2000 per day"


def _current_user():
    """The account behind the JWT, or None.

    The identity claim is the user's email -- every ``create_access_token`` call
    issues ``identity=user.email``.
    """
    return user_repository.find_by_email(get_jwt_identity())


def _respond(result: profile_service.ProfileResult):
    return jsonify(result.body), result.status


def _body() -> dict:
    """The validated JSON body.

    Every route in this module is ``enforce=True``, so
    ``solverah.validation`` has already checked this payload against the
    declared model before the handler runs. Reading it with ``silent=True`` here
    is about a body that is absent rather than wrong -- which for a model with
    no required fields is legitimate and validates as ``{}``.
    """
    return request.get_json(silent=True) or {}


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

@document(
    "Read the authenticated user's identity",
    tags=["me"],
    responses={200: IdentityResponse, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
)
@me_bp.route("/me", methods=["GET"])
@jwt_required()
def get_me():
    """GET /me - identity only: id, email, name, role, confirmation state.

    No profileData and no audit row. The client that needs the profile asks
    GET /me/profile for it; that is what splitting the god-endpoint bought.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return _respond(profile_service.read_identity(user))


@document(
    "Update the authenticated user's identity",
    tags=["me"],
    request=IdentityUpdateRequest,
    responses={200: IdentityResponse, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
)
@me_bp.route("/me", methods=["PATCH"])
@jwt_required()
def patch_me():
    """PATCH /me - change the display name.

    Name is the only writable identity field. Email is not, because changing it
    without re-verification is an account-takeover primitive; role is not,
    because an account granting itself a role is a privilege escalation.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return _respond(profile_service.update_identity(user, _body().get("name")))


@document(
    "Erase personal data, retaining de-identified assessment rows",
    tags=["me"],
    request=AccountDeleteRequest,
    responses={200: AccountDeleteResponse, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
)
@me_bp.route("/me", methods=["DELETE"])
@jwt_required()
def delete_me():
    """DELETE /me - erase personal data; keep de-identified research rows.

    Body (JSON): {"confirm": "DELETE"} - an explicit confirmation string, so a
    stray click or a replayed request cannot destroy an account.

    A body on DELETE is unusual and is the right place for this. It is not a
    secret, so a query parameter would work, but a confirmation that travels in
    the URL ends up in access logs, proxy caches, and browser history -- and an
    intermediary that strips the body fails this closed, with a 400, rather than
    open.
    """
    data = _body()

    # Confirmation is checked before the user lookup so an unconfirmed request
    # gets the same 400 whether or not the JWT still maps to an account.
    if data.get("confirm") != account_service.DELETE_CONFIRMATION:
        result = account_service.delete_account(None, data.get("confirm"))
        return jsonify(result.body), result.status

    user = _current_user()
    if user is None:
        return jsonify({"error": "User not found"}), 404

    result = account_service.delete_account(user, data.get("confirm"))
    response = jsonify(result.body)
    if result.clear_session:
        unset_jwt_cookies(response)
    return response, result.status


@document(
    "Export every identified data class held for the authenticated user",
    tags=["me"],
    responses={200: AccountExportResponse, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
)
@me_bp.route("/me/export", methods=["GET"])
@jwt_required()
def export_me():
    """GET /me/export - one JSON document of everything we hold."""
    user = _current_user()
    if user is None:
        return jsonify({"error": "User not found"}), 404

    result = account_service.export_account_data(user)
    return jsonify(result.body), result.status


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@document(
    "Read the authenticated user's profile document",
    tags=["me"],
    responses={200: ProfileDocument, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
)
@me_bp.route("/me/profile", methods=["GET"])
@jwt_required()
def get_my_profile():
    """GET /me/profile - the profile blob, in an envelope.

    Records a `read` audit event. Unlike the endpoint this replaces, that write
    is no longer on the session-restore path, which is what made it P0-3.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return _respond(profile_service.read_profile_document(user))


@document(
    "Merge a partial profile over the stored document",
    tags=["me"],
    request=ProfilePatchRequest,
    responses={200: ProfileDocument, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
)
@me_bp.route("/me/profile", methods=["PATCH"])
@jwt_required()
def patch_my_profile():
    """PATCH /me/profile - merge incoming keys into the stored profile.

    Unknown keys are stripped by clean_profile_data rather than rejected. Quiz
    results merge at the sub-key level so existing entries survive. Edits are
    diffed against the stored parser snapshot to record ResumeParseCorrection
    rows for anything the user changed after a resume upload.

    Still a read-modify-write of a whole JSON column (P0-1), and still without a
    version to check. Phase 2 is what fixes that; the envelope this returns is
    where the version will go.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(
        profile_service.patch_profile(user, _body().get("profile", {}), clean_profile_data)
    )


@document(
    "Set the user's career status",
    tags=["me"],
    request=CareerStatusRequest,
    responses={200: CareerStatusResponse, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
)
@me_bp.route("/me/career-status", methods=["PATCH"])
@jwt_required()
def patch_my_career_status():
    """PATCH /me/career-status - set career_status directly.

    A targeted request rather than a full profile save, so the onboarding modal
    can record a status without the user filling in experience entries.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "not_found"}), 404
    return _respond(profile_service.set_career_status(user, _body().get("status")))


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

@document(
    "Read self-rated skill proficiencies",
    tags=["me"],
    responses={200: SkillsResponse, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
)
@me_bp.route("/me/skills", methods=["GET"])
@jwt_required()
def get_my_skills():
    """GET /me/skills - proficiency ratings and whether they are confirmed.

    New in Phase 1b. The superseded endpoint was write-only, so the client had
    to read the whole profile document to find out what it had already saved.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return _respond(profile_service.read_skills(user))


@document(
    "Replace self-rated skill proficiencies",
    tags=["me"],
    request=SkillsPutRequest,
    responses={200: SkillsResponse, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
)
@me_bp.route("/me/skills", methods=["PUT"])
@jwt_required()
def put_my_skills():
    """PUT /me/skills - write the full set of proficiency ratings.

    PUT rather than the PATCH this replaces, because the write is a wholesale
    replacement of the ratings map, not a merge into it. Also sets
    skills_proficiency_confirmed so the rating modal stops re-prompting.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return _respond(profile_service.set_skill_proficiency(user, _body().get("skills")))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@document(
    "Summary statistics for the job-seeker dashboard",
    tags=["me"],
    responses={200: DashboardResponse, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
)
@me_bp.route("/me/dashboard", methods=["GET"])
@jwt_required()
def get_my_dashboard():
    """GET /me/dashboard - profile completion, match count, application count.

    recentActivity and recommendations are static placeholders until those
    features exist; the three counts are live.
    """
    email = get_jwt_identity()
    user = user_repository.find_by_email(email)
    if user is None:
        return jsonify({"error": "User not found"}), 404
    return _respond(profile_service.dashboard_data(user, email))


# ---------------------------------------------------------------------------
# Resumes
# ---------------------------------------------------------------------------

def _validate_upload(data) -> tuple:
    """Shared MIME/size gate for the ticket and complete steps.

    Returns ``(mime, size, error_response)``; the error is None when valid.
    Unlike the pair this replaces, both steps answer an oversized file with the
    same message. The two used to differ -- "File too large (max 10MB)" on
    presign, "Invalid file size" on finalize -- for no reason beyond how they
    were written, and 1b is where that is allowed to be settled.
    """
    mime = (data.get("mime") or "").strip()
    size = int(data.get("size") or 0)
    if mime not in ALLOWED_MIME:
        return mime, size, (jsonify({"error": "Unsupported file type"}), 400)
    if size <= 0 or size > MAX_BYTES:
        return mime, size, (jsonify({"error": "File too large (max 10MB)"}), 400)
    return mime, size, None


@document(
    "Request an upload ticket for a new resume",
    tags=["me"],
    request=ResumeTicketRequest,
    responses={200: ResumeTicketResponse, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
)
@me_bp.route("/me/resumes", methods=["POST"])
@jwt_required()
def post_my_resume_ticket():
    """POST /me/resumes - presign a PUT URL for a resume upload. Step 1 of 2.

    Returns a resume_id rather than the raw object key the superseded endpoint
    handed back. The key is derived server-side from the JWT identity, so a
    caller has no key to name and the finalize step has no prefix check to get
    wrong.
    """
    data = _body()
    mime, size, error = _validate_upload(data)
    if error:
        return error

    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(profile_service.resume_upload_ticket(user, mime, size, MAX_BYTES))


@document(
    "Parse an uploaded resume into the profile",
    tags=["me"],
    request=ResumeCompleteRequest,
    responses={200: ResumeCompleteResponse, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
)
@me_bp.route("/me/resumes/<resume_id>/complete", methods=["POST"])
@jwt_required()
def post_my_resume_complete(resume_id: str):
    """POST /me/resumes/{resume_id}/complete - parse the upload. Step 2 of 2.

    Downloads the object, runs the rule-based parser, and merges the parsed
    experience, education, and skills into the profile. Stores a
    _parsedResumeSnapshot so later edits can be diffed against what the parser
    produced (see ResumeParseCorrection).

    Parsing runs inline, which is P0-6. Part 5.2 has this returning 202 with a
    job handle; it will, when Phase 3's queue exists. Returning one now for work
    that finished synchronously would give the client something to poll that is
    already done.
    """
    data = _body()
    mime, size, error = _validate_upload(data)
    if error:
        return error

    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(
        profile_service.complete_resume_upload(
            user,
            resume_id=resume_id,
            mime=mime,
            size=size,
            name=(data.get("name") or "").strip(),
        )
    )


@document(
    "Presign a download URL for a stored resume",
    tags=["me"],
    responses={200: ResumeDownloadResponse, 404: LegacyError, 500: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
)
@me_bp.route("/me/resumes/<resume_id>/download-url", methods=["GET"])
@jwt_required()
def get_my_resume_download_url(resume_id: str):
    """GET /me/resumes/{resume_id}/download-url - short-lived presigned GET URL.

    `current` is a valid resume_id and means "the resume on my profile". The
    blob holds exactly one resumeKey, so until Phase 2 gives resumes their own
    rows that is the only one a client can name without having just uploaded it.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return _respond(profile_service.resume_download_url_by_id(user, resume_id))


# ---------------------------------------------------------------------------
# Resume parsing as a job (Phase 3)
# ---------------------------------------------------------------------------
#
# Part 5.2's `202 + job handle` for the one endpoint in this module that does
# genuinely slow work: `/complete` downloads the object from R2, writes it to a
# temp file, and runs pdfminer or python-docx over it, all inside the request.
#
# Added alongside `/complete` rather than replacing it. The old path is
# unchanged and still works, because a client cannot switch from awaiting a 200
# to polling a job in the same deploy that first gives it a job to poll. When
# the frontend has moved, `/complete` becomes a deletion and this becomes the
# only way in.


@document(
    "Queue a resume parse and return a job handle",
    tags=["me"],
    request=ResumeCompleteRequest,
    responses={202: ResumeParseJobAccepted, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "Asynchronous counterpart to `POST /me/resumes/{resume_id}/complete`. "
        "Identical request body; answers `202` with a job handle instead of "
        "blocking for the parse. Poll `GET /me/resume-parse-jobs/{job_id}` until "
        "`status` is `succeeded` or `failed`.\n\n"
        "The synchronous endpoint is unchanged and remains available."
    ),
)
@me_bp.route("/me/resumes/<resume_id>/parse-jobs", methods=["POST"])
@jwt_required()
def post_my_resume_parse_job(resume_id: str):
    """POST /me/resumes/{resume_id}/parse-jobs - queue the parse, return 202."""
    data = _body()
    mime, size, error = _validate_upload(data)
    if error:
        return error

    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    object_key = profile_service.resolve_resume_key(user, resume_id, mime=mime)
    if not object_key:
        return jsonify({"error": "Resume not found"}), 404

    job = resume_jobs.create(
        user,
        object_key=object_key,
        mime=mime,
        size=size,
        name=(data.get("name") or "").strip(),
    )
    job_id = job.public_id.hex
    return (
        jsonify(
            {
                "job_id": job_id,
                "status": job.status,
                "status_url": "/me/resume-parse-jobs/%s" % job_id,
            }
        ),
        202,
    )


@document(
    "Report the state of a queued resume parse",
    tags=["me"],
    responses={200: ResumeParseJobStatus, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
)
@me_bp.route("/me/resume-parse-jobs/<job_id>", methods=["GET"])
@limiter.limit(POLL_LIMIT)
@jwt_required()
def get_my_resume_parse_job(job_id: str):
    """GET /me/resume-parse-jobs/{job_id} - poll a queued parse.

    404 covers three cases deliberately: no such job, a malformed handle, and a
    job belonging to somebody else. Distinguishing them would confirm that a
    handle exists, which is the only thing protecting one.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    job = resume_jobs.find_for_user(user.id, job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404

    return jsonify(resume_jobs.status_for(job)), 200
