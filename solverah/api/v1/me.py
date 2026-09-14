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
from solverah.schemas import PROBLEM_RESPONSE_MODEL, LegacyError
from solverah.schemas.account import AccountDeleteRequest, AccountDeleteResponse, AccountExportResponse
from solverah.schemas.manager_playbook import ManagerPlaybookResponse
from solverah.schemas.experiments import (
    ExperimentAbandonResponse,
    ExperimentListResponse,
    ExperimentStartRequest,
    ExperimentStartResponse,
)
from solverah.schemas.pulse import (
    PulseCadenceResponse,
    PulseCadenceUpdateRequest,
    PulseCheckinRequest,
    PulseCheckinResponse,
    PulseEventRequest,
    PulseEventResponse,
    PulseHistoryQuery,
    PulseHistoryResponse,
    PulseNextCheckinResponse,
)
from solverah.schemas.profile import (
    CareerStatusRequest,
    CareerStatusResponse,
    DashboardResponse,
    IdentityResponse,
    IdentityUpdateRequest,
    ProfileDocument,
    ProfilePatchRequest,
    ResumeCompleteRequest,
    ResumeDownloadResponse,
    ResumeParseJobAccepted,
    ResumeParseJobStatus,
    ResumeTicketRequest,
    ResumeTicketResponse,
    SkillsPutRequest,
    SkillsResponse,
)
from solverah.schemas.situation_report import (
    EnvironmentReportSubmitRequest,
    EnvironmentReportSubmitResponse,
    SituationReportRecalibrateResponse,
    SituationReportResponse,
)
from solverah.services import (
    account_service,
    experiment_service,
    manager_playbook_service,
    profile_service,
    pulse_service,
    resume_jobs,
    situation_report_service,
)
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
# Manager Decoder (BUILD_PLAN C-3)
# ---------------------------------------------------------------------------

@document(
    "Read the Manager Decoder playbook for this user's latest manager profile",
    tags=["me"],
    responses={200: ManagerPlaybookResponse, 404: LegacyError, 409: PROBLEM_RESPONSE_MODEL},
    security=_AUTHENTICATED,
    enforce=True,
    description=(
        "Diffs this user's ManagerMatch needs against their latest manager-profile "
        "sitting (`POST /assessments/manager-profile`) and returns the assembled "
        "playbook. Two states answer `409`, distinguishably: no ManagerMatch sitting "
        "yet (`errors[0].code == \"no_manager_match\"`), and a ManagerMatch sitting but "
        "no manager profile yet (`\"no_manager_profile\"`) -- a client routes the user "
        "at whichever instrument is missing rather than showing a generic error."
    ),
)
@me_bp.route("/me/manager-playbook", methods=["GET"])
@jwt_required()
def get_my_manager_playbook():
    """GET /me/manager-playbook - the Decoder's playbook for this user's latest sitting."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    result = manager_playbook_service.get_manager_playbook(user)
    return jsonify(result.body), result.status


# ---------------------------------------------------------------------------
# Situation Report (BUILD_PLAN A-5)
# ---------------------------------------------------------------------------
#
# Matches the sibling assessment routes' submission budget
# (`solverah/api/v1/assessments.py`'s `DEFAULT_SUBMISSION_LIMIT`) -- both writes here
# score deterministically and instantly, like `focus_type` and the Manager Decoder's
# storage, so there is no provider-spend reason for a different number.
SITUATION_REPORT_SUBMIT_LIMIT = "5 per minute"


@document(
    "Submit the environment-side instrument for the Situation Report",
    tags=["me"],
    request=EnvironmentReportSubmitRequest,
    responses={
        200: EnvironmentReportSubmitResponse,
        400: LegacyError,
        404: LegacyError,
        409: PROBLEM_RESPONSE_MODEL,
    },
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "Scores the twelve environment items instantly (rules-scored, no Celery) and "
        "stores an append-only `environment_reports` row (D-16 tradition: a "
        "resubmission is a new row, never an update). `career_status` is snapshotted "
        "from the caller's profile at submit time, not taken from the request body. "
        "`first_job` has no role to describe and is refused with a distinguishable "
        "`409` (`errors[0].code == \"first_job_no_role\"`) the UI turns into the skip "
        "path (PRODUCT_DECISIONS.md §2, 2026-09-10)."
    ),
)
@me_bp.route("/me/environment-report", methods=["POST"])
@limiter.limit(SITUATION_REPORT_SUBMIT_LIMIT)
@jwt_required()
def post_my_environment_report():
    """POST /me/environment-report - score and store one environment-report sitting."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    result = situation_report_service.submit_environment_report(user, _body())
    return jsonify(result.body), result.status


@document(
    "Read the Situation Report",
    tags=["me"],
    responses={200: SituationReportResponse, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
    description=(
        "Three states, distinguished by `state`: `needs_core` (no completed `core` "
        "sitting yet -- an already-submitted environment report is echoed as bare "
        "dimension scores, with no gap to compute), `needs_environment_report` (core "
        "done, no environment report yet), and `complete` (the full gap report, "
        "needs-forward sliced when the pinned career_status is past-tense). D-15 "
        "(structural, every state): no person-side score, no numeric gap, no "
        "per-dimension magnitude, ever. Person-side reads go through the pinned "
        "snapshot (⚑5) -- a core retake with no explicit "
        "`POST /me/situation-report/recalibrate` leaves this response byte-identical. "
        "`manager` is always present: `{'has_profile': bool}`, a link-or-prompt to the "
        "Manager Decoder. `complete` additionally carries `events_since_report` "
        "(BUILD_PLAN B-4): Pulse life/work events logged after the environment "
        "report's `submitted_at`, each `{'type', 'date'}` and never a `note` -- "
        "what the frontend's resubmission banner reads."
    ),
)
@me_bp.route("/me/situation-report", methods=["GET"])
@jwt_required()
def get_my_situation_report():
    """GET /me/situation-report - the Situation Report, in whichever state applies."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    result = situation_report_service.get_situation_report(user)
    return jsonify(result.body), result.status


@document(
    "Re-pin the Situation Report to the latest completed core sitting",
    tags=["me"],
    responses={
        200: SituationReportRecalibrateResponse,
        404: LegacyError,
        409: PROBLEM_RESPONSE_MODEL,
    },
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "⚑5: the explicit, logged re-pin action. Idempotent when already pinned to "
        "the latest completed core sitting -- `recalibrated` is `false` and nothing "
        "is written or logged. Refuses `409` "
        "(`errors[0].code == \"no_core_sitting\"`) before any core sitting exists."
    ),
)
@me_bp.route("/me/situation-report/recalibrate", methods=["POST"])
@limiter.limit(SITUATION_REPORT_SUBMIT_LIMIT)
@jwt_required()
def post_my_situation_report_recalibrate():
    """POST /me/situation-report/recalibrate - re-pin to the latest core sitting."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    result = situation_report_service.recalibrate(user)
    return jsonify(result.body), result.status


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
# Part 5.2's `202 + job handle` for the one flow in this module that does
# genuinely slow work: the parse downloads the object from R2, writes it to a
# temp file, and runs pdfminer or python-docx over it. 3a added this alongside
# the synchronous `POST /me/resumes/{resume_id}/complete`; 3c deleted that
# route once the frontend had moved (afcec62), so this is the only way in.


@document(
    "Queue a resume parse and return a job handle",
    tags=["me"],
    request=ResumeCompleteRequest,
    responses={202: ResumeParseJobAccepted, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "Step 2 of 2 of a resume upload, and the only step 2 since Phase 3c "
        "deleted the synchronous `POST /me/resumes/{resume_id}/complete`. "
        "Answers `202` with a job handle instead of blocking for the parse. "
        "Poll `GET /me/resume-parse-jobs/{job_id}` until `status` is "
        "`succeeded` or `failed`."
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


# ---------------------------------------------------------------------------
# Pulse (BUILD_PLAN B-2)
# ---------------------------------------------------------------------------
#
# What a user's own requests can do. The cron half that decides WHO gets
# prompted (`flask pulse send-prompts`, `solverah/cli.py`) is a separate module,
# `solverah.services.pulse_cadence_service` -- a Flask CLI process and a request
# here are different callers with different lifecycles.
#
# Cadence/anti-nag state has no table of its own: it rides on the profile
# document (`solverah.services.pulse_settings`) rather than adding one, per
# BUILD_PLAN's D-7 cross-cutting rule -- a new user-data table would have to
# join the `GET /me/export` / account-deletion seam D-7b owns this wave.
#
# Matches the Situation Report submission routes' budget: both write instantly
# and deterministically, with no provider spend to bound.
PULSE_SUBMIT_LIMIT = "5 per minute"


@document(
    "Submit a Pulse check-in",
    tags=["me"],
    request=PulseCheckinRequest,
    responses={200: PulseCheckinResponse, 404: LegacyError, 422: PROBLEM_RESPONSE_MODEL},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "The server derives both the sequence (`pulse_checkin_count`) and the three "
        "dimensions it must answer (`dimensions_for_checkin`) -- the client never "
        "chooses either. Posting a different dimension set, or a score outside 1..5, "
        "is refused `422` in problem+json rather than accepted or 500ing."
    ),
)
@me_bp.route("/me/pulse/checkins", methods=["POST"])
@limiter.limit(PULSE_SUBMIT_LIMIT)
@jwt_required()
def post_my_pulse_checkin():
    """POST /me/pulse/checkins - record one check-in for this user's next sequence."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(pulse_service.submit_checkin(user, _body())), 200


@document(
    "Read Pulse check-in and event history",
    tags=["me"],
    query=PulseHistoryQuery,
    responses={200: PulseHistoryResponse, 404: LegacyError, 422: PROBLEM_RESPONSE_MODEL},
    security=_AUTHENTICATED,
    enforce=True,
    description=(
        "Newest first, optionally windowed by `since`/`until` (ISO-8601, inclusive). "
        "`limit` bounds check-ins (1..100, clamped) and is unbounded when absent; "
        "events are never limited -- B-4 reads every one to decide when a Situation "
        "Report resubmission prompt applies."
    ),
)
@me_bp.route("/me/pulse/history", methods=["GET"])
@jwt_required()
def get_my_pulse_history():
    """GET /me/pulse/history - check-ins and events, newest first."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    result = pulse_service.get_history(
        user,
        since_raw=request.args.get("since"),
        until_raw=request.args.get("until"),
        limit_raw=request.args.get("limit"),
    )
    return jsonify(result), 200


@document(
    "Read the items this user's next Pulse check-in will serve",
    tags=["me"],
    responses={200: PulseNextCheckinResponse, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
    description=(
        "`work_pulse.pulse_items.render_checkin`'s shape verbatim: server-derived and "
        "FORM_VERSION-stamped, so a client always knows which three dimensions (plus "
        "the outcome item) to render next without computing the round-robin itself -- "
        "and it is the same instrument `POST /me/pulse/checkins` validates the answer "
        "against."
    ),
)
@me_bp.route("/me/pulse/next-checkin", methods=["GET"])
@jwt_required()
def get_my_pulse_next_checkin():
    """GET /me/pulse/next-checkin - the three dimensions + outcome item to render next."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(pulse_service.get_next_checkin(user)), 200


@document(
    "Log a Pulse life/work event",
    tags=["me"],
    request=PulseEventRequest,
    responses={200: PulseEventResponse, 404: LegacyError, 422: PROBLEM_RESPONSE_MODEL},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "One of new_manager / reorg / remote_change / role_change / other, with an "
        "optional 280-character note. B-4 reads these to prompt an environment-report "
        "resubmission; B-3's trend view plots them on the check-in axis. Nothing here "
        "scores anything."
    ),
)
@me_bp.route("/me/pulse/events", methods=["POST"])
@limiter.limit(PULSE_SUBMIT_LIMIT)
@jwt_required()
def post_my_pulse_event():
    """POST /me/pulse/events - log one dated annotation."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(pulse_service.submit_event(user, _body())), 200


@document(
    "Read the Pulse check-in cadence",
    tags=["me"],
    responses={200: PulseCadenceResponse, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
)
@me_bp.route("/me/pulse/settings", methods=["GET"])
@jwt_required()
def get_my_pulse_settings():
    """GET /me/pulse/settings - the current cadence."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(pulse_service.get_settings(user)), 200


@document(
    "Set the Pulse check-in cadence",
    tags=["me"],
    request=PulseCadenceUpdateRequest,
    responses={200: PulseCadenceResponse, 404: LegacyError, 422: PROBLEM_RESPONSE_MODEL},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "weekly (default), biweekly, or off -- off is always this one call. Also "
        "clears the anti-nag state: an explicit choice is never held against a prior "
        "silence (PRODUCT_DECISIONS.md §2)."
    ),
)
@me_bp.route("/me/pulse/settings", methods=["PATCH"])
@limiter.limit(PULSE_SUBMIT_LIMIT)
@jwt_required()
def patch_my_pulse_settings():
    """PATCH /me/pulse/settings - change the cadence."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(pulse_service.update_settings(user, _body())), 200


# ---------------------------------------------------------------------------
# Condition experiments (BUILD_PLAN B-5)
# ---------------------------------------------------------------------------
#
# Generated from A-6's `change_in_place` guidance cells: a user runs a named
# two-week change against one of the twelve the gap engine can diagnose, and
# the readout reads Pulse `experienced` check-ins from before and after.
# Matches the Situation Report / Pulse submission routes' budget: every write
# here scores nothing and calls no provider.
EXPERIMENT_SUBMIT_LIMIT = "5 per minute"


@document(
    "Start a condition experiment",
    tags=["me"],
    request=ExperimentStartRequest,
    responses={
        201: ExperimentStartResponse,
        404: LegacyError,
        409: PROBLEM_RESPONSE_MODEL,
        422: PROBLEM_RESPONSE_MODEL,
    },
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "`dimension`/`direction` must name one of the twelve real `change_in_place` "
        "cells (`errors[0].code == \"not_a_change_in_place_cell\"` otherwise, 422). "
        "Refuses `409` (`errors[0].code == \"experiment_already_active\"`) if this "
        "user already has one running -- a two-week change is confounded by a second "
        "concurrent one, so at most one may run at a time."
    ),
)
@me_bp.route("/me/experiments", methods=["POST"])
@limiter.limit(EXPERIMENT_SUBMIT_LIMIT)
@jwt_required()
def post_my_experiment():
    """POST /me/experiments - start a two-week condition experiment."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(experiment_service.start_experiment(user, _body())), 201


@document(
    "List this user's condition experiments",
    tags=["me"],
    responses={200: ExperimentListResponse, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
    description=(
        "Newest first. Each entry carries the derived `phase` ('running' / 'ended' / "
        "'abandoned'), the before/after `readout` (a verdict word plus the two "
        "check-in counts, never a delta), and the cell's own `experiment_name`."
    ),
)
@me_bp.route("/me/experiments", methods=["GET"])
@jwt_required()
def get_my_experiments():
    """GET /me/experiments - every experiment this user has started, newest first."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(experiment_service.list_experiments(user)), 200


@document(
    "Abandon a condition experiment",
    tags=["me"],
    responses={200: ExperimentAbandonResponse, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "Idempotent: abandoning an already-abandoned experiment is a 200 with the "
        "row unchanged, not an error. 404 if the id does not exist or belongs to "
        "someone else -- the two are deliberately indistinguishable."
    ),
)
@me_bp.route("/me/experiments/<int:experiment_id>/abandon", methods=["POST"])
@limiter.limit(EXPERIMENT_SUBMIT_LIMIT)
@jwt_required()
def post_my_experiment_abandon(experiment_id: int):
    """POST /me/experiments/{id}/abandon - stop a running experiment."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(experiment_service.abandon_experiment(user, experiment_id)), 200
