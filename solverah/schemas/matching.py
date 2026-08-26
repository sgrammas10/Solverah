"""Schemas for company lookup and culture matching."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from . import SolverahModel

__all__ = [
    "CompanyDetailResponse",
    "CultureMatchEntry",
    "CultureMatchesQuery",
    "CultureMatchesResponse",
]


class CompanyDetailResponse(SolverahModel):
    """One company's full stored research profile.

    ``id`` is the integer primary key and appears in the URL, so this endpoint
    enumerates: an authenticated caller can walk the ids and read the whole
    network. Part 4.2 replaces it with a UUID ``public_id``.

    ``profile`` is the serialised ``CompanyProfile`` from
    :mod:`packages.ml.culture` -- open here because its optional sections vary
    by how much research a company has had.
    """

    id: int
    name: Optional[str] = None
    slug: Optional[str] = None
    profile: Optional[Dict[str, Any]] = Field(
        default=None, description="Serialised CompanyProfile."
    )


class CultureMatchesQuery(SolverahModel):
    """Query parameters for the culture-match list.

    No cursor: this endpoint returns two fixed-size slices rather than a page,
    and Part 5.2 is where it becomes a properly paginated ``/me/matches``.
    """

    limit: int = Field(
        default=5,
        description="Companies per list. Clamped to 1-50; a non-integer is a 400.",
    )


class CultureMatchEntry(SolverahModel):
    """One scored company.

    ``top_matching_dimensions`` and ``top_mismatching_dimensions`` are the two
    highest- and two lowest-scoring dimensions, and ``fit_summary`` is the
    sentence built from them.
    """

    model_config = ConfigDict(extra="allow")

    id: int
    name: Optional[str] = None
    slug: Optional[str] = None
    industry: Optional[str] = None
    fit_score: Optional[float] = None
    top_matching_dimensions: List[str] = Field(default_factory=list)
    top_mismatching_dimensions: List[str] = Field(default_factory=list)
    fit_summary: Optional[str] = None


class CultureMatchesResponse(SolverahModel):
    """Best and worst culture fits for the authenticated user.

    When at most ``2 * limit`` companies score, the two lists partition the
    whole set at its midpoint rather than each taking a slice off the end -- so
    a company never appears in both.
    """

    best_fits: List[CultureMatchEntry] = Field(default_factory=list)
    worst_fits: List[CultureMatchEntry] = Field(
        default_factory=list, description="Ordered worst fit first."
    )
    total_companies_scored: int
    limit: int
