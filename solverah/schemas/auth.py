"""Schemas for registration, login, email confirmation, and password reset.

Field names are the wire names, including the camelCase ``csrfToken`` and
``profileData`` the frontend already reads.  Renaming them is a client-visible
change and belongs to Phase 1b, not to the schema layer.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import ConfigDict, Field

from . import SolverahModel

__all__ = [
    "ConfirmEmailRequest",
    "LoginRequest",
    "LoginResponse",
    "LogoutResponse",
    "MessageResponse",
    "PasswordResetRequest",
    "PasswordResetVerifyRequest",
    "PasswordResetVerifyResponse",
    "RegisterRequest",
    "RegisterResponse",
    "ResendConfirmationRequest",
    "SendEmailFailureResponse",
    "SessionFlags",
    "SessionResponse",
    "SessionUser",
    "SummaryUser",
]


class MessageResponse(SolverahModel):
    """A bare acknowledgement: ``{"message": "..."}``."""

    message: str


class LogoutResponse(MessageResponse):
    """Always ``{"message": "logout successful"}``.

    The cookie is cleared with ``Set-Cookie`` on this response.  Note that the
    JWT itself remains valid until it expires -- clearing the cookie ends the
    browser session but cannot revoke the token, which is exactly what Part 5.3's
    database-backed refresh tokens are for.
    """


class SummaryUser(SolverahModel):
    """The identity fields returned where no profile payload is wanted."""

    id: int
    email: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None


class SessionUser(SummaryUser):
    """The user object returned on a successful login.

    ``profileData`` is the entire ``users.profile_data`` blob.  Shipping the
    whole user document on every session restore is the god-endpoint problem
    Part 5.2 splits apart; it is documented here rather than quietly trimmed,
    because trimming it would break the frontend that reads it.
    """

    model_config = ConfigDict(extra="allow")

    profileData: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw profile_data blob. Open-ended until Phase 2 (P0-1).",
    )
    wpl_completed: bool = Field(description="Legacy Work Pulse instrument completed.")
    wpll_completed: bool = Field(description="Work Pulse Lite-Lite completed.")
    wp_v2_completed: bool = Field(
        description="Current 24-item Work Pulse assessment completed."
    )


class RegisterRequest(SolverahModel):
    """Body of ``POST /register``.

    ``terms_accepted`` must be boolean ``true`` -- the handler compares with
    ``is True``, so a truthy string is rejected. That is deliberate: consent
    evidence should not be satisfiable by accident (GAP-01/GAP-05).
    """

    model_config = ConfigDict(extra="allow")

    email: str
    password: str
    name: Optional[str] = None
    terms_accepted: bool = Field(
        description="Must be literal true. Recorded in profile_data as evidence of assent."
    )
    terms_version: Optional[str] = Field(
        default=None, description='Version assented to; stored as "unversioned" when absent.'
    )


class RegisterResponse(SolverahModel):
    message: str
    user: SummaryUser


class LoginRequest(SolverahModel):
    email: str
    password: str


class LoginResponse(SolverahModel):
    """Successful login. The JWT arrives as an HttpOnly cookie, not in the body.

    ``csrfToken`` is the double-submit half of the scheme: the client stores it
    in memory and echoes it as ``X-CSRF-TOKEN`` on every state-changing request.
    Appendix B calls this scheme correct and preserved verbatim.
    """

    message: str
    csrfToken: str = Field(description="Echo as X-CSRF-TOKEN on POST/PUT/PATCH/DELETE.")
    user: SessionUser


class ConfirmEmailRequest(SolverahModel):
    email: str
    code: str = Field(description="6-digit OTP from the registration email.")


class ResendConfirmationRequest(SolverahModel):
    email: str


class SendEmailFailureResponse(SolverahModel):
    """The 500 body when Resend rejects a send.

    Carries ``detail`` on the resend path only, which is where the original
    handler included it.
    """

    error: str
    detail: Optional[str] = None


class PasswordResetRequest(SolverahModel):
    email: str


class PasswordResetVerifyRequest(SolverahModel):
    email: str
    code: str = Field(description="6-digit OTP from the reset email.")


class PasswordResetVerifyResponse(SolverahModel):
    """Passwordless sign-in result.

    Same envelope as :class:`LoginResponse` but with the summary user: this path
    does not return ``profileData`` or the assessment-completion flags, and the
    difference is preserved rather than harmonised.
    """

    message: str
    csrfToken: str = Field(description="Echo as X-CSRF-TOKEN on POST/PUT/PATCH/DELETE.")
    user: SummaryUser


# ---------------------------------------------------------------------------
# Phase 1b -- GET /auth/session
# ---------------------------------------------------------------------------

class SessionFlags(SolverahModel):
    """Per-user booleans the shell needs before it can decide what to render.

    They live in their own object rather than at the top level so a flag can be
    added without the client having to distinguish "new flag" from "new identity
    field", and so the whole set can be cached under one key.
    """

    email_confirmed: bool = Field(description="Account has verified its address.")
    wpl_completed: bool = Field(description="Legacy Work Pulse instrument completed.")
    wpll_completed: bool = Field(description="Work Pulse Lite-Lite completed.")
    wp_v2_completed: bool = Field(
        description="Current 24-item person-side assessment completed."
    )


class SessionResponse(SolverahModel):
    """``GET /auth/session`` -- the cheap session probe, and the fix for P0-3.

    The endpoint it replaces on the app-boot path is ``GET /profile``, which
    returned the entire user document *and* wrote an ``AuditLog`` row on every
    read.  Session restore fires on every page load, so the highest-volume table
    in the system was written synchronously on the hottest endpoint and a
    request that ought to be servable from a read replica took a write lock.

    This returns identity, the CSRF token, and the flags -- no ``profileData``,
    no audit row, no commit.  A client that wants the profile asks
    ``GET /me/profile`` for it, which is the whole point of the split.
    """

    user: SummaryUser
    csrf_token: Optional[str] = Field(
        default=None,
        description="Echo as X-CSRF-TOKEN on POST/PUT/PATCH/DELETE.",
    )
    flags: SessionFlags
