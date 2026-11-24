"""Schemas for the public intake funnel and its account-attachment endpoints.

Every body here is snake_case (``first_name``). The one camelCase body,
``/intake/early-access``'s, went with that route on 2026-11-23 (G31).
"""

from __future__ import annotations

from typing import Dict, Literal, Optional, Union

from pydantic import ConfigDict, Field, RootModel

from . import OkResponse, SolverahModel
from .auth import SummaryUser
from .intelligence import QuizInsightsGuestResponse

__all__ = [
    "CLAIM_LIMITS",
    "CLAIM_REQUIRES_AUTH",
    "CLAIM_REQUESTS",
    "STRICTEST_CLAIM_LIMIT",
    "IntakeClaimEnvelope",
    "IntakeClaimLinkRequest",
    "IntakeClaimRegisterRequest",
    "IntakeClaimRequest",
    "IntakeClaimResponse",
    "IntakeClaimSignInRequest",
    "QuizPreviewInsightsResponse",
    "IntakeCreateAccountRequest",
    "IntakeCreateAccountResponse",
    "IntakeFinalizeRequest",
    "IntakeLinkAccountRequest",
    "IntakePresignRequest",
    "IntakePresignResponse",
    "IntakeSignInRequest",
    "IntakeSignInResponse",
    "OkResponse",
]


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
# One thing the doc's framing understates and the code makes plain: the modes
# are less symmetric than "copies of one branch" suggests.  ``link`` files a
# *new* submission for someone already signed in rather than claiming an
# existing one.  That is why the route is ``POST /intake/claims`` and not
# Part 5.2's ``/intake/submissions/{id}/claim``: ``link`` has no submission id
# to put in the path, and inventing one would mean either a fabricated id or
# two endpoints again.
#
# There were four modes until 2026-11-23.  The fourth, ``session``, adopted an
# anonymous Work Pulse Lite-Lite session from ``sessionStorage`` after login;
# its only caller was the ``/start`` replay in ``Login.tsx``, deleted with
# ``/start`` (G24), and the mode went with it (ruling C).  A body naming it now
# gets the same ``literal_error`` on ``mode`` as any other unknown mode.
#
# The models below are a discriminated union on ``mode``, so a client gets a
# real 422 naming the field it got wrong rather than a generic one.


class IntakeClaimEnvelope(SolverahModel):
    """The discriminator, and the fallback when it is missing or unrecognised.

    Validating an unknown mode against this produces
    ``{"field": "mode", "code": "literal_error"}``, which tells a client what is
    wrong and what the alternatives are. Validating it against one of the
    concrete models would report every field of an arbitrarily chosen mode as
    missing, which tells them nothing.
    """

    model_config = ConfigDict(extra="ignore")

    mode: Literal["register", "sign_in", "link"] = Field(
        description=(
            '"register" creates an account from a submission; "sign_in" attaches '
            'one to an existing account; "link" files a submission as an already '
            'signed-in user.'
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


class IntakeClaimRequest(RootModel):
    """Documentation-only union of the three claim bodies.

    Do not validate against this; the route enforces :data:`CLAIM_REQUESTS` per
    mode. Unlike the assessment union, this one *is* discriminated on a property
    of the payload, so a generated client can narrow it.
    """

    root: Union[
        IntakeClaimRegisterRequest,
        IntakeClaimSignInRequest,
        IntakeClaimLinkRequest,
    ] = Field(discriminator="mode")


class IntakeClaimResponse(RootModel):
    """Documentation-only union of the three claim results.

    ``register`` answers 201 and the rest answer 200, and the bodies differ:
    ``register`` and ``sign_in`` carry a session (a JWT cookie plus a CSRF
    token), ``link`` is a bare acknowledgement. Unifying the request did not
    unify these, for the same reason it did not unify the five assessment
    results.
    """

    root: Union[
        IntakeCreateAccountResponse,
        IntakeSignInResponse,
        OkResponse,
    ]


#: ``mode`` -> the body that mode accepts. This is what is enforced.
CLAIM_REQUESTS: Dict[str, type] = {
    "register": IntakeClaimRegisterRequest,
    "sign_in": IntakeClaimSignInRequest,
    "link": IntakeClaimLinkRequest,
}

#: ``mode`` -> whether a JWT is required. ``register`` and ``sign_in`` are how
#: an anonymous visitor gets one, so requiring it there would be circular.
CLAIM_REQUIRES_AUTH: Dict[str, bool] = {
    "register": False,
    "sign_in": False,
    "link": True,
}

#: ``mode`` -> rate limit, preserved exactly from the separate handlers.
#: Collapsing the routes merges their buckets unless something is done about it.
#: The three are one number since ``session`` (10 per minute) was removed.
CLAIM_LIMITS: Dict[str, str] = {
    "register": "5 per minute",
    "sign_in": "5 per minute",
    "link": "5 per minute",
}

#: What an unrecognised mode gets: the strictest of the three. A client that
#: cannot name a valid mode should not be able to probe faster than one that can.
STRICTEST_CLAIM_LIMIT = "5 per minute"


class QuizPreviewInsightsResponse(QuizInsightsGuestResponse):
    """``POST /intake/quiz-preview/insights`` -- unauthenticated preview insights.

    Same body as the authenticated endpoint, minus persistence: nothing is
    written to any profile, because there is no account yet.
    """
