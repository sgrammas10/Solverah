"""Schemas for the profile, resume, and dashboard endpoints.

``GET|POST /profile`` is the god-endpoint Part 5.2 breaks apart: one route that
reads or writes the entire user document, returns the whole profile document
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
    "IdentityResponse",
    "IdentityUpdateRequest",
    "ProfileDocument",
    "ProfilePatchRequest",
    "ResumeCompleteRequest",
    "ResumeCompleteResponse",
    "ResumeDownloadResponse",
    "ResumeParseJobAccepted",
    "ResumeParseJobStatus",
    "ResumeTicketRequest",
    "ResumeTicketResponse",
    "SkillsPutRequest",
    "SkillsResponse",
    "CareerStatusResponse",
    "DashboardResponse",
    "SkillRating",
]


class CareerStatusRequest(SolverahModel):
    status: str = Field(description='One of "employed", "between_jobs", "first_job".')


class CareerStatusResponse(SolverahModel):
    career_status: str


class SkillRating(SolverahModel):
    name: str
    proficiency: str = Field(
        description='One of "beginner", "intermediate", "advanced".'
    )


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


# ===========================================================================
# Phase 1b -- the /me/* resources
# ===========================================================================
#
# Part 5.2 splits ``GET|POST /profile`` into an identity resource and a profile
# resource.  The shapes below are what that split produces.
#
# A note on P0-1, recorded here because this is where the split lands.  The
# blob is still the storage -- Phase 2 decomposes it, not this phase -- so
# ``PATCH /me/profile`` remains a read-modify-write of a whole JSON column with
# no version column to check.  Splitting the endpoint makes that *temporarily
# worse* in one specific way: a client that used to send one ``POST /profile``
# now sends ``PATCH /me`` and ``PATCH /me/profile``, so a failure between them
# leaves identity and profile out of step, and two concurrent editors have two
# windows to lose an update in rather than one.  That is accepted, not
# overlooked.  ``ProfileDocument`` carries the envelope the fix needs: Phase 2
# adds ``version`` to it and ``If-Match`` to the request, and neither is a
# client-visible break because the envelope already exists.


class IdentityResponse(SolverahModel):
    """``GET /me`` -- who the caller is, and nothing else.

    Four columns off ``users``. No ``profileData``: shipping the whole user
    document to render a nav bar is the god-endpoint problem, and the client
    that wants the profile asks for the profile.
    """

    id: int
    email: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    email_confirmed: bool = Field(description="Address has been verified.")


class IdentityUpdateRequest(SolverahModel):
    """``PATCH /me``.

    ``name`` is the only writable identity field, and the omissions are
    deliberate rather than pending. Changing ``email`` has to re-run
    verification or it is an account-takeover primitive; ``role`` is a privilege
    boundary and is not something an account may grant itself.
    """

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=255, description="Display name.")


class ProfileDocument(SolverahModel):
    """``GET|PATCH /me/profile`` -- the profile half, in an envelope.

    The envelope is the point. Returning the document bare would leave nowhere
    to put a ``version`` and no way to add one later without colliding with a
    profile key of the same name.

    P0-1 is fixed as of Phase 2a and ``version`` is *not* here yet, which is
    deliberate: the fix is server-side compare-and-swap on ``profiles.version``,
    and it needs no cooperation from the client. Exposing the version becomes
    worth doing when a client wants to say "write this only if you still have
    what I read" -- an If-Match, not a field.
    """

    profile: Dict[str, Any] = Field(
        default_factory=dict,
        description="The profile document. Assembled from the profile tables since Phase 2a; open-ended because the unpromoted keys genuinely vary per user.",
    )


class ProfilePatchRequest(SolverahModel):
    """``PATCH /me/profile``.

    Merged over the stored document rather than replacing it, and filtered by
    ``validators.clean_profile_data`` first -- an unrecognised key is dropped,
    not rejected, which is why the inner object stays open.
    """

    model_config = ConfigDict(extra="ignore")

    profile: Dict[str, Any] = Field(
        description="Partial profile. Merged over the stored document; unknown keys are stripped."
    )


class SkillsResponse(SolverahModel):
    """``GET|PUT /me/skills`` -- self-rated proficiencies.

    ``skills_proficiency_confirmed`` is what stops the rating modal
    re-prompting; it is part of the resource because the client needs it to
    decide whether to ask.
    """

    skills_proficiency_confirmed: bool
    skill_levels: Dict[str, str] = Field(
        default_factory=dict, description="skill name -> proficiency level."
    )


class SkillsPutRequest(SolverahModel):
    """``PUT /me/skills`` -- the full set of ratings.

    PUT, not PATCH: the handler writes the ratings it is given over the stored
    map wholesale, so the verb matches what the write actually does.
    """

    model_config = ConfigDict(extra="ignore")

    skills: List[SkillRating]


class ResumeTicketRequest(SolverahModel):
    """``POST /me/resumes`` -- ask for somewhere to upload to."""

    model_config = ConfigDict(extra="ignore")

    mime: str = Field(description="Must be PDF, DOC, or DOCX.")
    size: int = Field(description="Exact byte count; bound into the signature.")


class ResumeTicketResponse(SolverahModel):
    """An upload ticket. The browser PUTs the file to ``upload_url`` itself.

    ``resume_id`` replaces the raw ``object_key`` the superseded endpoint handed
    back, and that is a security improvement rather than cosmetics. Finalize
    used to accept a caller-supplied key and check it began with
    ``profile/{your-id}/``; now the server rebuilds the key from the JWT
    identity and this id, so there is no key for a caller to name at all.
    """

    resume_id: str = Field(description="Opaque id. Pass to /me/resumes/{id}/complete.")
    upload_url: str = Field(description="Presigned PUT URL, valid for 10 minutes.")
    max_bytes: int


class ResumeCompleteRequest(SolverahModel):
    """``POST /me/resumes/{resume_id}/complete`` -- the file is uploaded; parse it."""

    model_config = ConfigDict(extra="ignore")

    mime: str
    size: int
    name: Optional[str] = Field(default=None, description="Original filename, for display.")


class ResumeCompleteResponse(ProfileDocument):
    """The profile after the parsed resume was merged into it.

    Parsing still runs inline, which is P0-6. Part 5.2 has this returning 202
    with a job handle; it does not do that yet, and returning a 202 for work
    that finished synchronously would be a lie the client would have to poll
    against. It becomes a 202 when Phase 3's queue exists.
    """


class ResumeDownloadResponse(SolverahModel):
    url: str = Field(description="Presigned GET URL, valid for 10 minutes.")


class ResumeParseJobAccepted(SolverahModel):
    """``202`` from ``POST /me/resumes/{resume_id}/parse-jobs``.

    Part 5.2's ``202 + job handle``, added in Phase 3 alongside the synchronous
    ``/complete`` rather than replacing it: a client cannot move from awaiting a
    200 to polling a job in the same deploy that first gives it something to
    poll. ``/complete`` keeps working until the frontend has moved.
    """

    job_id: str = Field(
        description="Poll GET /me/resume-parse-jobs/{job_id} until status is terminal."
    )
    status: str = Field(description='Always "queued" here; the job has not started.')
    status_url: str = Field(description="Where to poll. Relative to the API root.")


class ResumeParseJobStatus(SolverahModel):
    """``GET /me/resume-parse-jobs/{job_id}``.

    ``status`` is one of ``queued``, ``running``, ``succeeded``, ``failed``; the
    last two are terminal and a client should stop polling on either.

    ``profile`` is present only on ``succeeded``, and carries what ``/complete``
    would have returned -- so the two paths hand back the same document and the
    client's merge logic does not fork. ``error`` is present only on ``failed``
    and is a fixed message: parse failures come from pdfminer, python-docx and
    botocore, whose text carries bucket names and object keys.
    """

    model_config = ConfigDict(extra="allow")

    job_id: str
    status: str
    error: Optional[str] = None
    profile: Optional[Dict[str, Any]] = None
