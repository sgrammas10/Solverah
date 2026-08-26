"""Schemas for the account-rights endpoints (GDPR/CCPA export and deletion).

The shapes below are the ones ``solverah/api/v1/account.py`` already returns.
Nothing here changes them -- see the package docstring for why Phase 1a's
schemas are descriptive rather than enforced.
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

    ``profile`` is the raw ``users.profile_data`` blob, so it is typed as an open
    object: its key set is genuinely per-user until Phase 2 decomposes it.
    """

    exported_at: str = Field(description="ISO 8601 timestamp of this export.")
    account: ExportedAccount
    profile: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw profile_data blob. Open-ended until Phase 2 (P0-1).",
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
    """Explicit confirmation, so a stray click cannot destroy an account."""

    confirm: str = Field(description='Must be the literal string "DELETE".')


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
