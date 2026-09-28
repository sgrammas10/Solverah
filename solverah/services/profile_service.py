"""Profile read/write, career status, skill proficiency, resume, and dashboard.

The behaviour of every function below is unchanged from the handlers in
``app.py`` it replaces.  What changed is that the merge semantics
(:mod:`solverah.domain.profile`) are now pure and testable, the queries live in
:mod:`solverah.repositories.profile_repository`, and object storage sits behind
:mod:`solverah.services.resume_service`.

Two defects were carried forward here and both are now gone.

* :func:`read_profile_document` wrote an ``AuditLog`` row and committed **on every
  read** (P0-3).  **Fixed in Phase 3.**  The event is still recorded -- this is a
  deliberate read of a personal-data document and the trail is worth its cost --
  but it is handed to a worker, so the read itself issues no INSERT, takes no
  write lock, and commits nothing.  ``solverah/services/audit.py`` explains which
  of the two recording paths a caller belongs on.
* :func:`save_profile` was a read-modify-write of a whole JSON column (P0-1).
  Two concurrent writers both read, both merged, and the second commit discarded
  the first with no error.  **Fixed in Phase 2a.**  Every write below now hands a
  pure merge function to
  :func:`solverah.repositories.profile_repository.update_document`, which applies
  it under a compare-and-swap on ``profiles.version`` and re-applies it against a
  fresh read when another writer got there first.

The shapes returned below are unchanged, deliberately and to the byte.  What was
``user.profile_data`` is now assembled from six tables and no caller -- the SPA
included -- can tell.  ``tests/test_profile_decomposition.py`` is what keeps that
true, and ``tests/test_profile_concurrency.py`` is what proves the fix above is
a fix rather than a rearrangement.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from model import User, db
from solverah.domain import profile as domain
from solverah.infra import cache
from solverah.repositories import (
    assessment_repository,
    dashboard_repository,
    path_fit_repository,
    profile_repository,
)
from solverah.services import audit, dashboard_feed, path_cache, resume_service

__all__ = [
    "CURRENT_RESUME",
    "ProfileResult",
    "dashboard_data",
    "patch_profile",
    "read_identity",
    "read_profile_document",
    "read_skills",
    "resolve_resume_key",
    "resume_download_url_by_id",
    "resume_upload_ticket",
    "update_identity",
    "read_profile",
    "save_profile",
    "set_career_status",
    "set_skill_proficiency",
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

    The god-endpoint body: identity, the whole profile document, a CSRF token and
    four completion flags in one response. No route reaches it -- Part 5.2 split
    it into ``GET /me``, ``GET /me/profile`` and ``GET /auth/session``, and
    Phase 1b moved the last caller off it -- and it is kept only because deleting
    it is a separate decision from this phase's.

    Its audit write moved off the request path with the routed one, because a
    dead function that commits on a read is a live one waiting for somebody to
    wire it up again.
    """
    audit.record_read_event(
        action="read",
        actor_user_id=user.id,
        resource="profile",
        metadata={"target_user_id": user.id},
    )
    finished = assessment_repository.completed_kinds(user.id)
    return ProfileResult(
        status=200,
        body={
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "profileData": profile_repository.load_document(user.id),
            "csrfToken": csrf_token,
            "wpl_completed": "work_pulse" in finished,
            "wpll_completed": "wpll" in finished,
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

    # Filled in by the merge below. The merge runs once per attempt -- again on
    # every lost compare-and-swap -- so the corrections are *collected* there and
    # written here, after exactly one attempt has succeeded. Writing them inside
    # would write them once per attempt.
    pending: Dict[str, Any] = {"resume_key": None, "corrections": []}

    def merge(existing: Dict[str, Any]) -> Dict[str, Any]:
        # Any field the user changed from what the parser produced is recorded
        # in resume_parse_correction for training-data analysis. Diffed against
        # the *freshly read* `existing`, which is what makes it right on a retry
        # and would not have been had it closed over a document read earlier.
        resume_key, corrections = domain.resume_field_corrections(existing, profile_data)
        pending["resume_key"] = resume_key
        pending["corrections"] = corrections
        return domain.merge_profile(existing, profile_data)

    document = profile_repository.update_document(user.id, merge)

    if pending["resume_key"] and pending["corrections"]:
        profile_repository.record_resume_corrections(
            user.id, pending["resume_key"], pending["corrections"]
        )

    audit.log_audit_event(
        action="update",
        actor_user_id=user.id,
        resource="profile",
        metadata={
            "updated_fields": sorted(profile_data.keys()),
            "target_user_id": user.id,
        },
    )
    # Evaluated before the commit because the F-5 invalidation has to ride the
    # same transaction; the Tier-1 cache is in-process and cannot.
    path_inputs_changed = bool(profile_data.keys() & domain.PATH_INPUT_KEYS)
    if path_inputs_changed:
        path_fit_repository.invalidate(user.id)

    db.session.commit()

    if path_inputs_changed:
        path_cache.invalidate(user.id)

    return ProfileResult(
        status=200,
        body={
            "message": "Profile updated successfully",
            "profileData": document,
        },
    )


def set_career_status(user: User, status: Any) -> ProfileResult:
    """Set ``career_status`` without a full profile save.

    ``career_status`` is a path-scoring INPUT, not a label: it decides the
    ``seniority``/``priority`` weight row (``path_scoring._WEIGHT_SPLITS``),
    whether a title is read off the experience list at all
    (``intelligence_service.build_user_profile`` skips it for ``first_job``),
    and the Job Zone floor. So changing it changes every suggestion -- and
    until F-8 box 6 this was the one profile write that invalidated neither
    cache, which meant a user who corrected "employed" to "between_jobs" kept
    being served the answers to the question they had just changed.

    A pre-existing bug, and one the F-5 enumeration missed because it was
    looking for sites that already called ``path_cache.invalidate``. Tier 2
    self-corrected through its profile fingerprint, so only Tier 1 actually
    served stale results; both are dropped here anyway, because "one of the two
    happens to be self-healing" is not a rule anybody can keep in their head.
    """
    if status not in domain.CAREER_STATUSES:
        return _error(400, "invalid_status")

    profile_repository.update_document(
        user.id, lambda existing: {**existing, "career_status": status}
    )
    path_fit_repository.invalidate(user.id)  # in-transaction, with the commit below
    db.session.commit()
    path_cache.invalidate(user.id)  # after the commit: it caches what is now true

    return ProfileResult(status=200, body={"career_status": status})


def set_skill_proficiency(user: User, skills: Any) -> ProfileResult:
    """Bulk-write self-rated proficiencies into ``skill_levels``."""
    problem = domain.validate_skill_ratings(skills)
    if problem:
        return _error(400, problem)

    written: Dict[str, str] = {}

    def apply(existing: Dict[str, Any]) -> Dict[str, Any]:
        updated, skill_levels = domain.apply_skill_levels(existing, skills)
        # Rewritten once per attempt; what survives is what the attempt that
        # actually committed produced.
        written.clear()
        written.update(skill_levels)
        return updated

    profile_repository.update_document(user.id, apply)
    path_fit_repository.invalidate(user.id)  # F-5, with the Tier-1 cache below
    db.session.commit()
    path_cache.invalidate(user.id)

    return ProfileResult(
        status=200,
        body={"skills_proficiency_confirmed": True, "skill_levels": dict(written)},
    )


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------


# The synchronous parse -- `finish_resume_upload` and its wrapper
# `complete_resume_upload`, the pair behind `POST /me/resumes/{id}/complete` --
# was deleted in Phase 3c. The parse runs in `resume_jobs.run`, which performs
# the same merge through `profile_repository.update_document`.


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

dashboard_feed.install_invalidation()


def _has_work_pulse(user_id: int) -> bool:
    """The current Work Pulse instrument is on record -- the banner's own rule."""
    from assessment_store import has_completed_assessment

    return has_completed_assessment(user_id)


def dashboard_data(user: User, email: str) -> ProfileResult:
    """Summary stats for the job-seeker dashboard. Cached in Redis (Phase 3).

    ``recentActivity`` is the user's real events, newest first, and
    ``recommendations`` their next unfinished steps; both are built by
    :mod:`solverah.services.dashboard_feed`. The counts are live.

    Reads on a miss: the assembled profile document, a recommendation count, an
    intake-submission existence check, one ``UNION ALL`` for the newest event of
    each activity source (``dashboard_repository.latest_activity``), and the
    current-Work-Pulse existence check. No per-source or per-row queries. The
    cached payload is per user, so the key carries the user id and nothing else.

    **What invalidates it, and the one thing that does not.** Every change to the
    profile document drops the key, from
    :func:`solverah.repositories.profile_repository.update_document`, which is
    the single write path Phase 2a left. Every insert or update of an activity
    row (assessment sitting, environment report, manager profile, pulse
    check-in, resume) drops it through ``dashboard_feed``'s ``after_flush`` hook.
    ``jobMatches`` has no live writer today. ``hasIntakeSubmission`` does: an
    anonymous intake finalized under this address while the user is already
    signed in elsewhere would flip it, and that write has no user id to key off.
    It -- and a pulse check-in going stale with the passage of time -- are what
    the TTL rather than an invalidation bounds, which is what the TTL is for.
    """
    key = cache.dashboard_key(user.id)
    cached = cache.get_json(key)
    if cached is not None:
        return ProfileResult(status=200, body=cached)

    profile = profile_repository.load_document(user.id)

    applications = (
        len(profile.get("applications", [])) if "applications" in profile else 0
    )
    activity_rows = dashboard_repository.latest_activity(user.id)
    now = datetime.datetime.now(datetime.timezone.utc)

    body = {
        "profileCompletion": "%d%%" % domain.profile_completion_percent(profile),
        "jobMatches": profile_repository.count_job_recommendations(user.id),
        "applications": applications,
        "recentActivity": dashboard_feed.build_activity(activity_rows, profile),
        "recommendations": dashboard_feed.build_recommendations(
            profile, activity_rows, has_work_pulse=_has_work_pulse(user.id), now=now
        ),
        "hasIntakeSubmission": profile_repository.has_intake_submission(email),
    }
    cache.set_json(key, body)
    return ProfileResult(status=200, body=body)


# ---------------------------------------------------------------------------
# Phase 1b -- the /me/* split
# ---------------------------------------------------------------------------
#
# ``read_profile`` above answers "who are you AND what is your profile" in one
# call, which is what made it the app-boot endpoint and what made P0-3 expensive.
# The functions below answer the two halves separately.
#
# The audit write stays on the profile half and is gone from the identity half,
# and that is the actual fix rather than a cosmetic one. Reading a personal-data
# document is an event worth recording; reading a name to render a nav bar is
# not, and it was the second one firing on every page load that put a write on
# the hottest read in the system. Session restore now goes to
# ``GET /auth/session``, which touches neither.

def read_identity(user: User) -> ProfileResult:
    """Identity fields only. No blob, no audit row, no commit."""
    return ProfileResult(
        status=200,
        body={
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "email_confirmed": bool(getattr(user, "email_confirmed", False)),
        },
    )


def update_identity(user: User, name: Any) -> ProfileResult:
    """Write the one identity field an account may change about itself.

    Email is absent because changing it without re-verification is an
    account-takeover primitive, and role because an account granting itself a
    role is a privilege escalation. Neither is an oversight to be filled in
    later by whoever needs it next.
    """
    cleaned = (name or "").strip()
    if not cleaned:
        return _error(400, "name is required")

    user.name = cleaned
    audit.log_audit_event(
        action="update",
        actor_user_id=user.id,
        resource="identity",
        metadata={"updated_fields": ["name"], "target_user_id": user.id},
    )
    db.session.commit()
    return read_identity(user)


def read_profile_document(user: User) -> ProfileResult:
    """The profile blob in its envelope, and record that it was read.

    Still records an audit event, unlike the identity read: this is a deliberate
    read of a personal-data document and the trail is worth its cost. What
    changed in Phase 3 is *where the row is written*. It used to be appended to
    this request's session and committed here, which is P0-3 -- a write lock and
    a commit on a request that should be servable from a replica. It is now
    handed to a worker, and this function commits nothing at all.

    The event is recorded either way. ``tests/test_me_api.py`` asserts the row
    still appears after this read, and ``tests/test_read_path_writes.py`` asserts
    that the request itself did not write it.
    """
    audit.record_read_event(
        action="read",
        actor_user_id=user.id,
        resource="profile",
        metadata={"target_user_id": user.id},
    )
    return ProfileResult(
        status=200, body={"profile": profile_repository.load_document(user.id)}
    )


def patch_profile(user: User, profile: Any, clean_profile_data) -> ProfileResult:
    """Merge a partial profile over the stored document.

    Identical merge semantics to :func:`save_profile`, including the parser-
    correction diffing -- only the envelope differs. Read that function's
    docstring for the P0-1 caveat, which this shares in full: it is a
    read-modify-write of a whole JSON column and the second of two concurrent
    commits discards the first without an error.
    """
    result = save_profile(user, profile, clean_profile_data)
    if not result.ok:
        return result
    return ProfileResult(status=200, body={"profile": result.body["profileData"]})


def read_skills(user: User) -> ProfileResult:
    """Self-rated proficiencies, and whether the user has confirmed them."""
    profile = profile_repository.load_document(user.id)
    return ProfileResult(
        status=200,
        body={
            "skills_proficiency_confirmed": bool(
                profile.get("skills_proficiency_confirmed")
            ),
            "skill_levels": profile.get("skill_levels") or {},
        },
    )


# ---------------------------------------------------------------------------
# Resumes, addressed by id rather than by object key
# ---------------------------------------------------------------------------
#
# The superseded pair took a caller-supplied ``object_key`` and defended itself
# with a ``profile/{your-id}/`` prefix check. That check was correct and load-
# bearing -- without it a caller could name any key in the bucket and have its
# contents parsed into their own profile, another user's resume included.
#
# Addressing by id removes the need for the check rather than repeating it. The
# server rebuilds the key from the JWT identity and the id, so a caller has no
# key to name and no prefix to get wrong. This is the one place in Phase 1b
# where the redesign closes something rather than moving it.

#: Path segment meaning "whatever resume is on my profile". Phase 2a gave
#: resumes their own table, but one row per user: `resumes` replaces the current
#: row rather than accumulating history, because `retention_cleanup` sweeps
#: object keys no row references and keeping superseded uploads would stop them
#: being reclaimed. An id here addresses one of several the release history
#: arrives.
CURRENT_RESUME = "current"


def _resume_id_of(resume_key: str) -> Optional[str]:
    """The id segment of ``profile/{user_id}/{id}/resume.{ext}``, or None."""
    parts = (resume_key or "").split("/")
    if len(parts) >= 4 and parts[0] == "profile":
        return parts[2]
    return None


def resume_upload_ticket(user: User, mime: str, size: int, max_bytes: int) -> ProfileResult:
    """Step 1 of 2: an upload ticket scoped to this user by construction."""
    object_key = resume_service.object_key_for_user(user.id, mime)
    resume_id = _resume_id_of(object_key)
    url = resume_service.presign_upload(object_key, mime, size)
    return ProfileResult(
        status=200,
        body={"resume_id": resume_id, "upload_url": url, "max_bytes": max_bytes},
    )


def resolve_resume_key(user: User, resume_id: str, mime: Optional[str] = None) -> Optional[str]:
    """The storage key for *resume_id*, or None when it names nothing.

    ``current`` resolves to whatever is on the profile. Any other value is
    rebuilt from the caller's own id, so it can only ever address the caller's
    own prefix -- an id belonging to another user produces a key under *this*
    user's prefix, which does not exist, rather than reaching theirs.
    """
    resume = profile_repository.current_resume(user.id)
    stored = resume.object_key if resume is not None else None
    if resume_id == CURRENT_RESUME:
        return stored or None

    if not resume_id or "/" in resume_id:
        return None

    if mime is None:
        # A read: only the stored resume can be addressed, because the
        # extension is part of the key and is not knowable from the id alone.
        if stored and _resume_id_of(stored) == resume_id:
            return stored
        return None

    ext = resume_service.MIME_EXTENSIONS.get(mime, "bin")
    return "profile/%s/%s/resume.%s" % (user.id, resume_id, ext)


def resume_download_url_by_id(user: User, resume_id: str) -> ProfileResult:
    """Presign a short-lived GET URL for one of the caller's resumes."""
    object_key = resolve_resume_key(user, resume_id)
    if not object_key:
        return _error(404, "No resume on file")

    try:
        url = resume_service.download_url(object_key)
    except Exception:  # noqa: BLE001 -- storage detail must not reach the client
        return _error(500, "Unable to generate resume URL")

    return ProfileResult(status=200, body={"url": url})
