"""Schemas for the public intake funnel and its account-attachment endpoints.

Field naming is inconsistent across this group and is preserved that way:
``/early-access-request`` takes camelCase (``firstName``), everything else takes
snake_case (``first_name``).  The frontend sends both today.  Part 5.2's rewrite
is where that gets settled.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from . import OkResponse, SolverahModel
from .auth import SummaryUser

__all__ = [
    "EarlyAccessRequest",
    "IntakeCreateAccountRequest",
    "IntakeCreateAccountResponse",
    "IntakeFinalizeRequest",
    "IntakeLinkAccountRequest",
    "IntakePresignRequest",
    "IntakePresignResponse",
    "IntakeSaveToAccountRequest",
    "IntakeSaveToAccountResponse",
    "IntakeSignInRequest",
    "IntakeSignInResponse",
    "OkResponse",
    "WpllAnswer",
]


class EarlyAccessRequest(SolverahModel):
    """Landing-page interest form.

    Not persisted -- the submission exists only as an email to
    info@solverah.com. A delivery failure loses the lead, which is why this is
    the one intake endpoint that returns 500 rather than swallowing the error.
    """

    model_config = ConfigDict(extra="allow")

    firstName: str
    lastName: str
    email: str
    phone: Optional[str] = None
    preferredContact: Optional[str] = None
    careerJourney: Optional[str] = None


class IntakePresignRequest(SolverahModel):
    mime: str = Field(description="Must be PDF, DOC, or DOCX.")
    size: int = Field(description="Exact byte count; bound into the signature.")


class IntakePresignResponse(SolverahModel):
    """Step 1 of 2. The browser PUTs the file to ``upload_url``.

    ``submission_id`` is a v4 UUID and is the only thing protecting an anonymous
    submission -- there is no account to authorise against, so the object key is
    deliberately unguessable.
    """

    submission_id: str
    object_key: str
    upload_url: str = Field(description="Presigned PUT URL, valid for 10 minutes.")
    max_bytes: int


class IntakeFinalizeRequest(SolverahModel):
    """Step 2 of 2. The server HEADs the object before recording the row.

    Without that check a client could skip the upload entirely and still create
    a submission pointing at a key that holds nothing.
    """

    model_config = ConfigDict(extra="allow")

    submission_id: str
    object_key: str = Field(description="Must be under intake/{submission_id}/.")
    mime: str
    size: int
    first_name: str
    last_name: str
    email: str
    state: str
    privacy_consent: bool = Field(description="Must be literal true.")
    phone: Optional[str] = None
    linkedin_url: Optional[str] = Field(
        default=None, description="Must be an https://linkedin.com URL if present."
    )
    portfolio_url: Optional[str] = Field(
        default=None, description="Must be https:// if present."
    )


class IntakeCreateAccountRequest(SolverahModel):
    """Register a new account from a finished submission."""

    submission_id: str
    password: str
    role: Optional[str] = Field(
        default="job-seeker", description='Only "job-seeker" is accepted.'
    )


class IntakeCreateAccountResponse(SolverahModel):
    message: str
    user: SummaryUser


class IntakeSignInRequest(SolverahModel):
    """Attach a submission to an existing account by signing in.

    The email must match the one on the submission, so a submission cannot be
    attached to an unrelated account by guessing its id.
    """

    submission_id: str
    email: str
    password: str


class IntakeSignInResponse(SolverahModel):
    """Same envelope as a login: JWT in an HttpOnly cookie, CSRF token in the body."""

    message: str
    csrfToken: str = Field(description="Echo as X-CSRF-TOKEN on POST/PUT/PATCH/DELETE.")
    user: SummaryUser


class IntakeLinkAccountRequest(IntakeFinalizeRequest):
    """Submit the intake form while already signed in.

    Same body as finalize minus the email, which comes from the JWT -- recording
    the body's email instead would let a signed-in user file a submission under
    someone else's address.
    """

    model_config = ConfigDict(extra="allow")

    email: Optional[str] = Field(
        default=None,
        description="Ignored. The submission is recorded against the JWT identity.",
    )
    info_opt_in: Optional[bool] = None


class WpllAnswer(SolverahModel):
    model_config = ConfigDict(extra="allow")

    question_id: Optional[str] = None
    option_id: Optional[str] = None


class IntakeSaveToAccountRequest(SolverahModel):
    """Persist an anonymous Work Pulse Lite-Lite session onto the account.

    Called right after login when sessionStorage still holds data from the
    ``/start`` flow.
    """

    selected_statement_ids: List[Any] = Field(default_factory=list)
    wpll_answers: List[WpllAnswer] = Field(
        default_factory=list, description="At most 5 items."
    )
    wpll_insight_text: Optional[str] = None


class IntakeSaveToAccountResponse(SolverahModel):
    message: str
    wpll_completed: bool
