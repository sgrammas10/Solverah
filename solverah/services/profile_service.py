"""Profile read/write, career status, skill proficiency, resume, and dashboard.

The behaviour of every function below is unchanged from the handlers in
``app.py`` it replaces.  What changed is that the merge semantics
(:mod:`solverah.domain.profile`) are now pure and testable, the queries live in
:mod:`solverah.repositories.profile_repository`, and object storage sits behind
:mod:`solverah.services.resume_service`.

Two defects are carried forward deliberately, both recorded in
docs/ARCHITECTURE.md:

* :func:`read_profile` writes an ``AuditLog`` row and commits **on every read**
  (P0-3).  Session restore fires it on every page load, so the highest-volume
  table in the system is written synchronously on the hottest endpoint, and a
  request that ought to be servable from a read replica takes a write lock.
* :func:`save_profile` is a read-modify-write of a whole JSON column (P0-1).
  Two concurrent writers both read, both merge, and the second commit discards
  the first with no error. There is no version column to check.

Neither is fixed here, because fixing either changes observable behaviour and
this batch's contract is that it does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from model import User, db
from solverah.domain import profile as domain
from solverah.repositories import profile_repository
from solverah.services import audit, path_cache, resume_service

__all__ = [
    "ProfileResult",
    "dashboard_data",
    "read_profile",
    "resume_download_url",
    "save_profile",
    "set_career_status",
    "set_skill_proficiency",
    "start_resume_upload",
    "finish_resume_upload",
]


@dataclass
class ProfileResult:
    """A service outcome the API layer turns into a response."""

    status: int
    body: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status < 400


def _error(status: int, message: str) -> ProfileResult:
    return ProfileResult(status=status, body={"error": message})


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------

def read_profile(user: User, csrf_token: Optional[str], wp_v2_completed) -> ProfileResult:
    """Return the full profile document and record the read.

    The audit write on a GET is P0-3 and is preserved -- see the module
    docstring. It is also why this function commits.
    """
    audit.log_audit_event(
        action="read",
        actor_user_id=user.id,
        resource="profile",
        metadata={"target_user_id": user.id},
    )
    db.session.commit()
    return ProfileResult(
        status=200,
        body={
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "profileData": user.profile_data or {},
            "csrfToken": csrf_token,
            "wpl_completed": bool(user.intake and user.intake.wpl_completed_at),
            "wpll_completed": bool(user.intake and user.intake.wpll_completed_at),
            "wp_v2_completed": wp_v2_completed(user.id),
        },
    )


def save_profile(user: User, raw_profile_data: Any, clean_profile_data) -> ProfileResult:
    """Merge incoming profile keys, record parser corrections, and commit.

    Args:
        raw_profile_data: The client's ``profileData`` object, unfiltered.
        clean_profile_data: Server-side key allowlist from ``validators.py``.
            Passed in so this module does not import a root-level module that
            has nothing to do with the service layer.
    """
    profile_data = clean_profile_data(raw_profile_data)
    existing = user.profile_data or {}

    merged = domain.merge_profile(existing, profile_data)

    # Any field the user changed from what the parser produced is recorded in
    # resume_parse_correction for training-data analysis.
    resume_key, corrections = domain.resume_field_corrections(existing, profile_data)
    if resume_key and corrections:
        profile_repository.record_resume_corrections(user.id, resume_key, corrections)

    profile_repository.save_profile_data(user, merged)
    audit.log_audit_event(
        action="update",
        actor_user_id=user.id,
        resource="profile",
        metadata={
            "updated_fields": sorted(profile_data.keys()),
            "target_user_id": user.id,
        },
    )
    db.session.commit()

    if profile_data.keys() & domain.PATH_INPUT_KEYS:
        path_cache.invalidate(user.id)

    return ProfileResult(
        status=200,
        body={
            "message": "Profile updated successfully",
            "profileData": user.profile_data,
        },
    )


def set_career_status(user: User, status: Any) -> ProfileResult:
    """Set ``career_status`` without a full profile save."""
    if status not in domain.CAREER_STATUSES:
        return _error(400, "invalid_status")

    profile_data = dict(user.profile_data or {})
    profile_data["career_status"] = status
    profile_repository.save_profile_data(user, profile_data)
    db.session.commit()

    return ProfileResult(status=200, body={"career_status": status})


def set_skill_proficiency(user: User, skills: Any) -> ProfileResult:
    """Bulk-write self-rated proficiencies into ``skill_levels``."""
    problem = domain.validate_skill_ratings(skills)
    if problem:
        return _error(400, problem)

    profile_data, skill_levels = domain.apply_skill_levels(user.profile_data, skills)
    profile_repository.save_profile_data(user, profile_data)
    db.session.commit()
    path_cache.invalidate(user.id)

    return ProfileResult(
        status=200,
        body={"skills_proficiency_confirmed": True, "skill_levels": skill_levels},
    )


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------

def resume_download_url(user: User) -> ProfileResult:
    """Presign a short-lived GET URL for the user's stored resume."""
    resume_key = (user.profile_data or {}).get("resumeKey")
    if not resume_key:
        return _error(404, "No resume on file")

    try:
        url = resume_service.download_url(resume_key)
    except Exception:  # noqa: BLE001 -- storage detail must not reach the client
        return _error(500, "Unable to generate resume URL")

    return ProfileResult(status=200, body={"url": url})


def start_resume_upload(user: User, mime: str, size: int, max_bytes: int) -> ProfileResult:
    """Step 1 of 2: hand back a presigned PUT URL scoped to this user."""
    object_key = resume_service.object_key_for_user(user.id, mime)
    url = resume_service.presign_upload(object_key, mime, size)
    return ProfileResult(
        status=200,
        body={
            "object_key": object_key,
            "upload_url": url,
            "max_bytes": max_bytes,
        },
    )


def finish_resume_upload(
    user: User, object_key: str, mime: str, size: int, name: str
) -> ProfileResult:
    """Step 2 of 2: parse the uploaded resume and merge it into the profile.

    The ``profile/{user.id}/`` prefix check is the authorisation boundary for
    this endpoint. Without it a caller could name any key in the bucket and have
    its contents parsed into their own profile -- including another user's
    resume.
    """
    if not object_key.startswith("profile/%s/" % user.id):
        return _error(400, "Invalid object_key")

    profile_updates = resume_service.build_profile_from_resume_key(
        resume_key=object_key,
        resume_mime=mime,
        resume_size_bytes=size,
        resume_name=name or None,
    )

    existing = user.profile_data or {}
    merged = {**existing, **profile_updates}
    merged["_parsedResumeSnapshot"] = resume_service.snapshot_of(object_key, profile_updates)

    profile_repository.save_profile_data(user, merged)
    db.session.commit()

    return ProfileResult(
        status=200,
        body={"message": "Resume processed", "profileData": user.profile_data},
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

#: Static until the underlying features exist.  Kept as data rather than being
#: built inline so the day they become dynamic is a change to one name.
_PLACEHOLDER_ACTIVITY: List[Dict[str, Any]] = [
    {
        "type": "assessment",
        "text": "Complete your leadership assessment",
        "time": "1 day ago",
        "icon": "Brain",
    }
]

_PLACEHOLDER_RECOMMENDATIONS: List[Dict[str, Any]] = [
    {
        "title": "Complete Psychometric Assessment",
        "description": "Boost visibility",
        "action": "Take Assessment",
        "priority": "high",
        "href": "/job-seeker/profile#assessments",
    },
    {
        "title": "Add Recent Experience",
        "description": "Update your experience section",
        "action": "Update Profile",
        "priority": "medium",
        "href": "/job-seeker/profile#experience",
    },
]


def dashboard_data(user: User, email: str) -> ProfileResult:
    """Summary stats for the job-seeker dashboard.

    ``recentActivity`` and ``recommendations`` are static placeholders; the
    counts are live. Preserved as-is so the dashboard renders identically.
    """
    profile = user.profile_data or {}

    applications = (
        len(profile.get("applications", [])) if "applications" in profile else 0
    )

    return ProfileResult(
        status=200,
        body={
            "profileCompletion": "%d%%" % domain.profile_completion_percent(profile),
            "jobMatches": profile_repository.count_job_recommendations(user.id),
            "applications": applications,
            "recentActivity": list(_PLACEHOLDER_ACTIVITY),
            "recommendations": [dict(item) for item in _PLACEHOLDER_RECOMMENDATIONS],
            "hasIntakeSubmission": profile_repository.has_intake_submission(email),
        },
    )
