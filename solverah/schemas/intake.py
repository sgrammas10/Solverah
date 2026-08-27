"""Schemas for the public intake funnel and its account-attachment endpoints.

Field naming is inconsistent across this group and is preserved that way:
``/early-access-request`` takes camelCase (``firstName``), everything else takes
snake_case (``first_name``).  The frontend sends both today.  Part 5.2's rewrite
is where that gets settled.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import ConfigDict, Field, RootModel

from . import OkResponse, SolverahModel
from .auth import SummaryUser
from .intelligence import QuizInsightsGuestResponse

__all__ = [
    "CLAIM_LIMITS",
    "CLAIM_REQUIRES_AUTH",
    "CLAIM_REQUESTS",
    "STRICTEST_CLAIM_LIMIT",
    "EarlyAccessRequest",
    "IntakeClaimEnvelope",
    "IntakeClaimLinkRequest",
    "IntakeClaimRegisterRequest",
    "IntakeClaimRequest",
    "IntakeClaimResponse",
    "IntakeClaimSessionRequest",
    "IntakeClaimSignInRequest",
    "QuizPreviewInsightsResponse",
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


# ===========================================================================
# Phase 1b -- POST /intake/claims
# ===========================================================================
#
# Part 5.2 collapses four account-attachment endpoints into one ``claim`` with
# a ``mode`` discriminator.  The four were ``/intake/create-account``,
# ``/intake/sign-in``, ``/intake/link-account``, and ``/intake/save-to-account``,
# and they are all answers to the same question: *this browser is holding
# something anonymous -- attach it to an account.*  What differed was which
# account and where the anonymous thing came from.
#
# One thing the doc's framing understates and the code makes plain: the four
# are less symmetric than "four copies of one branch" suggests.  ``link`` files
# a *new* submission for someone already signed in rather than claiming an
# existing one, and ``session`` has no submission at all -- it adopts an
# anonymous Work Pulse Lite-Lite session held in ``sessionStorage``.  That is
# why the route is ``POST /intake/claims`` and not Part 5.2's
# ``/intake/submissions/{id}/claim``: two of the four modes have no submission
# id to put in the path, and inventing one would mean either a fabricated id or
# two endpoints again.
#
# The models below are a discriminated union on ``mode``, so a client gets a
# real 422 naming the field it got wrong rather than a generic one.


class IntakeClaimEnvelope(SolverahModel):
    """The discriminator, and the fallback when it is missing or unrecognised.

    Validating an unknown mode against this produces
    ``{"field": "mode", "code": "literal_error"}``, which tells a client what is
    wrong and what the alternatives are. Validating it against one of the four
    concrete models would report every field of an arbitrarily chosen mode as
    missing, which tells them nothing.
    """

    model_config = ConfigDict(extra="ignore")

    mode: Literal["register", "sign_in", "link", "session"] = Field(
        description=(
            '"register" creates an account from a submission; "sign_in" attaches '
            'one to an existing account; "link" files a submission as an already '
            'signed-in user; "session" adopts an anonymous quiz session.'
        )
    )


class IntakeClaimRegisterRequest(IntakeClaimEnvelope):
    """``mode: "register"`` -- create a new account from a finished submission.

    The account's email comes from the submission, never from this body: the
    submitter proved control of it by receiving nothing, but they did type it
    into a form that is already recorded, and letting the claim body override it
    would turn a guessed submission id into an account under any address.
    """

    mode: Literal["register"] = "register"
    submission_id: str
    password: str
    role: Optional[str] = Field(
        default="job-seeker", description='Only "job-seeker" is accepted.'
    )


class IntakeClaimSignInRequest(IntakeClaimEnvelope):
    """``mode: "sign_in"`` -- attach a submission to an existing account.

    The email must match the one on the submission, so a submission cannot be
    attached to an unrelated account by guessing its id.
    """

    mode: Literal["sign_in"] = "sign_in"
    submission_id: str
    email: str
    password: str


class IntakeClaimLinkRequest(IntakeClaimEnvelope, IntakeFinalizeRequest):
    """``mode: "link"`` -- file a submission while already signed in.

    Same body as a submission minus the email, which comes from the JWT.
    Recording the body's email instead would let a signed-in user file a
    submission under someone else's address.
    """

    model_config = ConfigDict(extra="allow")

    mode: Literal["link"] = "link"
    email: Optional[str] = Field(
        default=None,
        description="Ignored. The submission is recorded against the JWT identity.",
    )
    info_opt_in: Optional[bool] = None


class IntakeClaimSessionRequest(IntakeClaimEnvelope):
    """``mode: "session"`` -- adopt an anonymous Work Pulse Lite-Lite session.

    The one mode with no submission behind it. Called right after login when
    ``sessionStorage`` still holds answers from the ``/start`` flow.
    """

    mode: Literal["session"] = "session"
    selected_statement_ids: List[Any] = Field(default_factory=list)
    wpll_answers: List[WpllAnswer] = Field(
        default_factory=list, description="At most 5 items."
    )
    wpll_insight_text: Optional[str] = None


class IntakeClaimRequest(RootModel):
    """Documentation-only union of the four claim bodies.

    Do not validate against this; the route enforces :data:`CLAIM_REQUESTS` per
    mode. Unlike the assessment union, this one *is* discriminated on a property
    of the payload, so a generated client can narrow it.
    """

    root: Union[
        IntakeClaimRegisterRequest,
        IntakeClaimSignInRequest,
        IntakeClaimLinkRequest,
        IntakeClaimSessionRequest,
    ] = Field(discriminator="mode")


class IntakeClaimResponse(RootModel):
    """Documentation-only union of the four claim results.

    ``register`` answers 201 and the rest answer 200, and the bodies differ:
    two carry a session (a JWT cookie plus a CSRF token), one carries the
    quiz-completion flag, one is a bare acknowledgement. Unifying the request
    did not unify these, for the same reason it did not unify the five
    assessment results.
    """

    root: Union[
        IntakeCreateAccountResponse,
        IntakeSignInResponse,
        IntakeSaveToAccountResponse,
        OkResponse,
    ]


#: ``mode`` -> the body that mode accepts. This is what is enforced.
CLAIM_REQUESTS: Dict[str, type] = {
    "register": IntakeClaimRegisterRequest,
    "sign_in": IntakeClaimSignInRequest,
    "link": IntakeClaimLinkRequest,
    "session": IntakeClaimSessionRequest,
}

#: ``mode`` -> whether a JWT is required. ``register`` and ``sign_in`` are how
#: an anonymous visitor gets one, so requiring it there would be circular.
CLAIM_REQUIRES_AUTH: Dict[str, bool] = {
    "register": False,
    "sign_in": False,
    "link": True,
    "session": True,
}

#: ``mode`` -> rate limit, preserved exactly from the four separate handlers.
#: Collapsing the routes merges their buckets unless something is done about it,
#: and these were not all the same number to begin with.
CLAIM_LIMITS: Dict[str, str] = {
    "register": "5 per minute",
    "sign_in": "5 per minute",
    "link": "5 per minute",
    "session": "10 per minute",
}

#: What an unrecognised mode gets: the strictest of the four. A client that
#: cannot name a valid mode should not be able to probe faster than one that can.
STRICTEST_CLAIM_LIMIT = "5 per minute"


class QuizPreviewInsightsResponse(QuizInsightsGuestResponse):
    """``POST /intake/quiz-preview/insights`` -- unauthenticated preview insights.

    Same body as the authenticated endpoint, minus persistence: nothing is
    written to any profile, because there is no account yet.
    """
