"""Schemas for the account-rights endpoints (GDPR/CCPA export and deletion).

The shapes below are served by ``GET /api/v1/me/export`` and ``DELETE /api/v1/me``
in ``solverah/api/v1/me.py``.  Phase 1b folded the account-lifecycle routes into
the ``/me`` resource -- exporting and erasing an account are things done to the
authenticated principal, and Part 5.2 puts them where everything else about it
already lives.  Neither body changed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from . import SolverahModel

__all__ = [
    "AccountDeleteRequest",
    "AccountDeleteResponse",
    "AccountExportResponse",
    "ExportedAccount",
    "ExportedIntakeSubmission",
    "ExportedJobRecommendation",
    "ExportedLegacyQuiz",
]


class ExportedAccount(SolverahModel):
    """Identity fields of the exporting user."""

    id: int
    email: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    email_confirmed: Optional[bool] = None


class ExportedIntakeSubmission(SolverahModel):
    """One pre-launch intake submission matched to the account's email."""

    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    state: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    resume_filename: Optional[str] = Field(
        default=None,
        description=(
            "Basename of the stored object, not the R2 key. The key is an "
            "internal locator and exporting it would hand out a storage path."
        ),
    )
    status: Optional[str] = None
    created_at: Optional[str] = Field(default=None, description="ISO 8601 timestamp.")


class ExportedLegacyQuiz(SolverahModel):
    """The pre-assessment-table quiz payloads held on ``UserIntake``."""

    model_config = ConfigDict(extra="allow")

    wpll_answers: Optional[Any] = None
    wpll_insight_text: Optional[str] = None
    wpl_answers: Optional[Any] = None
    wpl_narrative: Optional[str] = None
    wpl_result: Optional[Any] = None


class ExportedJobRecommendation(SolverahModel):
    job_id: Optional[str] = None
    score: Optional[float] = None
    created_at: Optional[str] = Field(default=None, description="ISO 8601 timestamp.")


class AccountExportResponse(SolverahModel):
    """Every identified data class held for the authenticated user.

    ``profile`` is the profile document -- ``profiles`` and its child tables
    since Phase 2a, the ``users.profile_data`` blob before it, and byte-identical
    either way. It stays typed as an open object because the keys that have not
    been promoted to columns yet still vary per user.
    """

    exported_at: str = Field(description="ISO 8601 timestamp of this export.")
    account: ExportedAccount
    profile: Dict[str, Any] = Field(
        default_factory=dict,
        description="The profile document. Assembled from the profile tables since Phase 2a; open-ended because the unpromoted keys genuinely vary per user.",
    )
    intake_submissions: List[ExportedIntakeSubmission] = Field(default_factory=list)
    legacy_quiz: Optional[ExportedLegacyQuiz] = None
    assessment_answers: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "The subject's own answers. Keyed by intent rather than after the "
            "table they come from, so an internal schema name does not become "
            "part of a public contract."
        ),
    )
    dimension_scores: List[Dict[str, Any]] = Field(default_factory=list)
    job_recommendations: List[ExportedJobRecommendation] = Field(default_factory=list)


class AccountDeleteRequest(SolverahModel):
    """Explicit confirmation, so a stray click cannot destroy an account.

    ``confirm`` is declared **optional** even though the request is refused
    without it, and that is deliberate rather than an oversight.

    Making it required would let the enforced schema reject an absent value with
    422 while the handler rejects a wrong value with 400 -- two refusal paths to
    the same decision, on the one operation in the API that cannot be undone.
    A safety interlock on an irreversible action wants exactly one path, owned by
    the code that performs the action, so that it cannot be relaxed by a change
    to a schema. Leaving it optional here means every non-``"DELETE"`` value --
    absent, empty, misspelled, wrong type -- takes the same branch and gets the
    same actionable message.

    The field is still documented, so a generated client still knows to send it.
    """

    model_config = ConfigDict(extra="ignore")

    confirm: Optional[str] = Field(
        default=None, description='Must be the literal string "DELETE".'
    )


class AccountDeleteResponse(SolverahModel):
    """Result of a tombstone deletion.

    ``r2_delete_failures`` is deliberately part of the success body rather than
    being swallowed: reporting "deleted" while a resume object is still live in
    object storage would be a false claim (D-07).
    """

    message: str
    r2_delete_failures: List[str] = Field(
        default_factory=list,
        description="Object keys that could not be removed from R2. Empty is the happy path.",
    )
