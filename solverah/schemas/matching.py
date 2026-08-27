"""Schemas for company lookup and culture matching."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from . import SolverahModel

__all__ = [
    "CompanyDetailResponse",
    "CompanyListEntry",
    "CompanyListQuery",
    "CompanyListResponse",
    "CultureMatchEntry",
    "MatchesQuery",
    "MatchesResponse",
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


# ===========================================================================
# Phase 1b -- cursor-paginated lists
# ===========================================================================
#
# Part 5.1: ``?cursor=&limit=`` in, ``{ "data": [...], "next_cursor": "..." }``
# out, and never an offset.  Decision A5 gives the reason and it is a
# correctness one before it is a performance one: with ``OFFSET``, a row
# inserted or deleted between two requests shifts every subsequent page, so a
# client walking a list under concurrent writes silently skips and repeats
# entries.  See ``solverah/pagination.py`` for how the keyset is built.


class CompanyListQuery(SolverahModel):
    """Query parameters for ``GET /companies``."""

    model_config = ConfigDict(extra="ignore")

    cursor: Optional[str] = Field(
        default=None,
        description="Opaque token from a previous next_cursor. Pass back unmodified.",
    )
    limit: Optional[int] = Field(default=None, description="Rows per page. Clamped to 1-100.")
    q: Optional[str] = Field(default=None, description="Case-insensitive substring of the name.")
    industry: Optional[str] = Field(
        default=None, description="Exact industry match, case-insensitive."
    )


class CompanyListEntry(SolverahModel):
    """One company in the list.

    Deliberately not the full profile: the list ships the fields a card renders
    and ``GET /companies/{id}`` ships the rest. The endpoint this pattern
    replaces had no list at all, so every screen that wanted several companies
    fetched the whole research document for each.
    """

    id: int
    name: Optional[str] = None
    slug: Optional[str] = None
    industry: Optional[str] = None


class CompanyListResponse(SolverahModel):
    """A page of companies. ``next_cursor`` is null on the last page."""

    data: List[CompanyListEntry] = Field(default_factory=list)
    next_cursor: Optional[str] = Field(
        default=None,
        description="Pass as ?cursor= for the next page. Null means this was the last.",
    )


class MatchesQuery(SolverahModel):
    """Query parameters for ``GET /me/matches``."""

    model_config = ConfigDict(extra="ignore")

    cursor: Optional[str] = Field(default=None, description="Opaque token from next_cursor.")
    limit: Optional[int] = Field(default=None, description="Rows per page. Clamped to 1-100.")
    lens: Optional[str] = Field(
        default=None, description='Scoring lens. Only "culture" exists today.'
    )
    order: Optional[str] = Field(
        default=None,
        description=(
            '"best" (default) ranks strongest fit first; "worst" ranks weakest first. '
            "The endpoint this replaces returned both halves in one body, which is "
            "why the parameter exists rather than the client paging to the end."
        ),
    )


class MatchesResponse(SolverahModel):
    """A page of scored companies.

    ``total_companies_scored`` is carried alongside the page because it is what
    the UI puts in "N companies scored", and a client cannot derive it from a
    page. It is also the honest measure of P0-2: it counts the rows this request
    pulled into Python and scored, every time, with no index and no cache.
    """

    data: List[CultureMatchEntry] = Field(default_factory=list)
    next_cursor: Optional[str] = Field(default=None)
    total_companies_scored: int
    lens: str = Field(description='Which scoring lens produced these. Always "culture" today.')
    order: str = Field(description='"best" or "worst".')
