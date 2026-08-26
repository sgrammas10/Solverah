"""Schemas for the profile, resume, and dashboard endpoints.

``GET|POST /profile`` is the god-endpoint Part 5.2 breaks apart: one route that
reads or writes the entire user document, returns the whole ``profile_data``
blob on every session restore, and writes an audit row on the read.  The models
below describe it exactly as it is, because Phase 1a does not change it.

What the models *do* buy right now is a written-down boundary.  When Phase 2
decomposes ``profile_data`` into columns, these are the shapes that must keep
holding -- the storage change is not allowed to reach the client, and a schema
that fails to validate a real response is how that gets caught.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from . import SolverahModel

__all__ = [
    "CareerStatusRequest",
    "CareerStatusResponse",
    "DashboardResponse",
    "ProfileReadResponse",
    "ProfileSaveRequest",
    "ProfileSaveResponse",
    "ResumeFinalizeRequest",
    "ResumeFinalizeResponse",
    "ResumePresignRequest",
    "ResumePresignResponse",
    "ResumeUrlResponse",
    "SkillProficiencyRequest",
    "SkillProficiencyResponse",
    "SkillRating",
]


class ProfileReadResponse(SolverahModel):
    """``GET /profile`` -- the entire user document.

    Note ``csrfToken``: the read doubles as the client's way of recovering a
    CSRF token after a page reload, since the token is held in memory and the
    JWT cookie is HttpOnly. That is the reason this endpoint is on the app-boot
    path at all, and Part 5.2's ``GET /auth/session`` is what replaces it.
    """

    model_config = ConfigDict(extra="allow")

    id: int
    email: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    profileData: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw profile_data blob. Open-ended until Phase 2 (P0-1).",
    )
    csrfToken: Optional[str] = Field(
        default=None, description="Echo as X-CSRF-TOKEN on state-changing methods."
    )
    wpl_completed: bool
    wpll_completed: bool
    wp_v2_completed: bool


class ProfileSaveRequest(SolverahModel):
    """``POST /profile``.

    Keys inside ``profileData`` are filtered server-side by
    ``validators.clean_profile_data`` -- an unknown key is dropped, not
    rejected, so the model is open here to match.
    """

    model_config = ConfigDict(extra="allow")

    profileData: Dict[str, Any] = Field(
        default_factory=dict,
        description="Partial profile. Merged over the stored blob; unknown keys are stripped.",
    )


class ProfileSaveResponse(SolverahModel):
    message: str
    profileData: Dict[str, Any] = Field(default_factory=dict)


class CareerStatusRequest(SolverahModel):
    status: str = Field(description='One of "employed", "between_jobs", "first_job".')


class CareerStatusResponse(SolverahModel):
    career_status: str


class SkillRating(SolverahModel):
    name: str
    proficiency: str = Field(
        description='One of "beginner", "intermediate", "advanced".'
    )


class SkillProficiencyRequest(SolverahModel):
    skills: List[SkillRating]


class SkillProficiencyResponse(SolverahModel):
    """Confirming proficiencies also stops the rating modal re-prompting."""

    skills_proficiency_confirmed: bool
    skill_levels: Dict[str, str] = Field(
        default_factory=dict, description="skill name -> proficiency level."
    )


class ResumeUrlResponse(SolverahModel):
    url: str = Field(description="Presigned GET URL, valid for 10 minutes.")


class ResumePresignRequest(SolverahModel):
    mime: str = Field(description="Must be PDF, DOC, or DOCX.")
    size: int = Field(description="Exact byte count; bound into the signature.")


class ResumePresignResponse(SolverahModel):
    """Step 1 of the two-step upload. The browser PUTs to ``upload_url``.

    ``size`` from the request is signed into the URL as ``ContentLength``, so a
    client that declares 1 KB and uploads a gigabyte is rejected by R2 rather
    than trusted by us.
    """

    object_key: str = Field(description="Pass back to /profile/resume/finalize.")
    upload_url: str = Field(description="Presigned PUT URL, valid for 10 minutes.")
    max_bytes: int


class ResumeFinalizeRequest(SolverahModel):
    object_key: str = Field(
        description="Key from the presign step. Must be under profile/{your-user-id}/."
    )
    mime: str
    size: int
    name: Optional[str] = Field(default=None, description="Original filename, for display.")


class ResumeFinalizeResponse(SolverahModel):
    """Step 2. Parsing runs inline, which is P0-6.

    Part 5.2 turns this into a 202 with a job handle once Phase 3's queue
    exists; the response shape below is the synchronous one it replaces.
    """

    message: str
    profileData: Dict[str, Any] = Field(default_factory=dict)


class DashboardActivity(SolverahModel):
    model_config = ConfigDict(extra="allow")

    type: Optional[str] = None
    text: Optional[str] = None
    time: Optional[str] = None
    icon: Optional[str] = None


class DashboardRecommendation(SolverahModel):
    model_config = ConfigDict(extra="allow")

    title: Optional[str] = None
    description: Optional[str] = None
    action: Optional[str] = None
    priority: Optional[str] = None
    href: Optional[str] = None


class DashboardResponse(SolverahModel):
    """Job-seeker dashboard summary.

    ``recentActivity`` and ``recommendations`` are static placeholders in the
    current implementation; the three counts are live.
    """

    profileCompletion: str = Field(description='Percentage with a literal "%", e.g. "71%".')
    jobMatches: int
    applications: int
    recentActivity: List[DashboardActivity] = Field(default_factory=list)
    recommendations: List[DashboardRecommendation] = Field(default_factory=list)
    hasIntakeSubmission: bool
