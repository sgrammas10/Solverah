"""Profile, resume, and dashboard endpoints.

Rules are prefix-free and mounted at ``/api/v1`` with an ``/api`` alias, so the
paths are exactly the ones that existed before: ``/profile``,
``/profile/career-status``, ``/profile/skills/proficiency``,
``/profile/resume-url``, ``/profile/resume/presign``,
``/profile/resume/finalize``, ``/dashboard-data``.

Part 5.2 renames these to ``/me/...`` and splits the ``GET|POST /profile``
god-endpoint into separate identity, profile, experience, education, and skills
resources.  That is Phase 1b: it changes response shapes, and 13 frontend files
read the ``profile_data`` blob shape directly.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from solverah.infra.storage import ALLOWED_MIME, MAX_BYTES
from solverah.openapi import document
from solverah.repositories import user_repository
from solverah.schemas import LegacyError
from solverah.schemas.profile import (
    CareerStatusRequest,
    CareerStatusResponse,
    DashboardResponse,
    ProfileReadResponse,
    ProfileSaveRequest,
    ProfileSaveResponse,
    ResumeFinalizeRequest,
    ResumeFinalizeResponse,
    ResumePresignRequest,
    ResumePresignResponse,
    ResumeUrlResponse,
    SkillProficiencyRequest,
    SkillProficiencyResponse,
)
from solverah.services import profile_service
from validators import clean_profile_data

from .auth import _wp_v2_completed

__all__ = ["profiles_bp"]

profiles_bp = Blueprint("profiles", __name__)

_AUTHENTICATED = ["accessTokenCookie"]
_AUTHENTICATED_WRITE = ["accessTokenCookie", "csrfHeader"]


def _current_user():
    """The account behind the JWT, or None.

    The identity claim is the user's email -- every ``create_access_token`` call
    issues ``identity=user.email``.
    """
    return user_repository.find_by_email(get_jwt_identity())


def _respond(result: profile_service.ProfileResult):
    return jsonify(result.body), result.status


def _validate_upload(data) -> tuple:
    """Shared MIME/size gate for the presign and finalize steps.

    Returns ``(mime, size, error_response)``; the error is None when valid.
    The two steps return different messages for the same size failure --
    "File too large (max 10MB)" on presign, "Invalid file size" on finalize --
    and that difference is preserved rather than harmonised, because the
    frontend surfaces both strings directly.
    """
    mime = (data.get("mime") or "").strip()
    size = int(data.get("size") or 0)
    if mime not in ALLOWED_MIME:
        return mime, size, (jsonify({"error": "Unsupported file type"}), 400)
    return mime, size, None


@document(
    "Read or update the authenticated user's profile",
    tags=["profile"],
    request=ProfileSaveRequest,
    request_required=False,
    responses={200: ProfileReadResponse, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
)
@profiles_bp.route("/profile", methods=["GET", "POST"])
@jwt_required()
def profile():
    """GET|POST /profile - Read or update the authenticated user's profile.

    GET returns the full profile including profileData and the current CSRF
    token, and writes a `read` audit log entry (P0-3).

    POST merges incoming profileData keys into the existing profile (unknown
    keys are stripped by clean_profile_data). Quiz results are merged at the
    sub-key level so existing quiz entries are preserved. Diffs against the
    stored parser snapshot to record ResumeParseCorrection rows for any
    experience/education/skills the user edits after a resume upload.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    if request.method == "GET":
        return _respond(
            profile_service.read_profile(
                user,
                csrf_token=get_jwt().get("csrf"),
                wp_v2_completed=_wp_v2_completed,
            )
        )

    data = request.get_json()
    return _respond(
        profile_service.save_profile(
            user,
            raw_profile_data=data.get("profileData", {}),
            clean_profile_data=clean_profile_data,
        )
    )


@document(
    "Set the user's career status",
    tags=["profile"],
    request=CareerStatusRequest,
    responses={200: CareerStatusResponse, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
)
@profiles_bp.route("/profile/career-status", methods=["PATCH"])
@jwt_required()
def set_career_status():
    """PATCH /profile/career-status - Directly set the user's career_status.

    Lets the frontend set career status with a single targeted request rather
    than a full profile save. Used by the career-status onboarding modal so the
    user can pick a status without filling in experience entries.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "not_found"}), 404

    data = request.get_json() or {}
    return _respond(profile_service.set_career_status(user, data.get("status")))


@document(
    "Bulk-update self-rated skill proficiencies",
    tags=["profile"],
    request=SkillProficiencyRequest,
    responses={200: SkillProficiencyResponse, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
)
@profiles_bp.route("/profile/skills/proficiency", methods=["PATCH"])
@jwt_required()
def set_skills_proficiency():
    """PATCH /profile/skills/proficiency - Bulk-update skill proficiency ratings.

    Accepts a list of { name, proficiency } objects and writes them into the
    skill_levels dict in profile_data. Also sets skills_proficiency_confirmed
    so the proficiency modal is not re-shown on the next Path Intelligence
    visit.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "not_found"}), 404

    data = request.get_json() or {}
    return _respond(profile_service.set_skill_proficiency(user, data.get("skills")))


@document(
    "Presign a download URL for the stored resume",
    tags=["profile"],
    responses={200: ResumeUrlResponse, 404: LegacyError, 500: LegacyError},
    security=_AUTHENTICATED,
)
@profiles_bp.route("/profile/resume-url", methods=["GET"])
@jwt_required()
def get_profile_resume_url():
    """GET /profile/resume-url - Get a presigned download URL for the user's resume.

    Generates a short-lived (10-minute) presigned GET URL for the resume stored
    at the resumeKey in the user's profile, so the browser can download or
    display the file without exposing permanent storage credentials.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(profile_service.resume_download_url(user))


@document(
    "Presign an upload URL for a new resume",
    tags=["profile"],
    request=ResumePresignRequest,
    responses={200: ResumePresignResponse, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
)
@profiles_bp.route("/profile/resume/presign", methods=["POST"])
@jwt_required()
def profile_resume_presign():
    """POST /profile/resume/presign - Presign a PUT URL for authenticated resume upload.

    Scopes the S3 object key to profile/{user_id}/{uuid}/resume.{ext} so that
    one user cannot overwrite another's file. Step 1 of 2.
    """
    data = request.get_json(silent=True) or {}
    mime, size, error = _validate_upload(data)
    if error:
        return error
    if size <= 0 or size > MAX_BYTES:
        return jsonify({"error": "File too large (max 10MB)"}), 400

    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(profile_service.start_resume_upload(user, mime, size, MAX_BYTES))


@document(
    "Parse an uploaded resume into the profile",
    tags=["profile"],
    request=ResumeFinalizeRequest,
    responses={200: ResumeFinalizeResponse, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
)
@profiles_bp.route("/profile/resume/finalize", methods=["POST"])
@jwt_required()
def profile_resume_finalize():
    """POST /profile/resume/finalize - Parse the uploaded resume and update profile.

    Verifies the object key belongs to the requesting user, downloads the
    resume from R2, runs the rule-based parser, and merges the parsed fields
    (experience, education, skills) into the user's profile. Also stores a
    _parsedResumeSnapshot so subsequent edits can be diffed against the
    parser's original output (see ResumeParseCorrection).
    """
    data = request.get_json(silent=True) or {}
    mime, size, error = _validate_upload(data)
    if error:
        return error
    if size <= 0 or size > MAX_BYTES:
        return jsonify({"error": "Invalid file size"}), 400

    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(
        profile_service.finish_resume_upload(
            user,
            object_key=(data.get("object_key") or "").strip(),
            mime=mime,
            size=size,
            name=(data.get("name") or "").strip(),
        )
    )


@document(
    "Summary statistics for the job-seeker dashboard",
    tags=["profile"],
    responses={200: DashboardResponse},
    security=_AUTHENTICATED,
)
@profiles_bp.route("/dashboard-data", methods=["GET"])
@jwt_required()
def get_dashboard_data():
    """GET /dashboard-data - Return summary stats for the job-seeker dashboard.

    Computes profile completion percentage, job-match count, and application
    count from live data. Also returns static placeholder recommendations and
    recent activity until those features are fully wired up.
    """
    from flask import abort

    email = get_jwt_identity()
    user = user_repository.find_by_email(email)
    if user is None:
        # first_or_404() in the original; the 404 handler turns it into a
        # problem document, so the shape the client sees is unchanged.
        abort(404)

    return _respond(profile_service.dashboard_data(user, email))
