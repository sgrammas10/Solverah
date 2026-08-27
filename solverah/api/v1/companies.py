"""Company lookup and culture matching.

Paths unchanged: ``/companies/<int:company_id>`` and ``/company-lens/matches``.

Both are Phase 2 targets and both are moved here as-is.  ``/company-lens/matches``
is P0-2 -- an O(all-companies) in-process scan per request, with a write
committed on the read path -- and the reasons for not fixing it in this batch are
in ``solverah/services/matching_service.py``.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from solverah.openapi import document
from solverah.repositories import user_repository
from solverah.schemas import LegacyError
from solverah.schemas.matching import (
    CompanyDetailResponse,
    CompanyListQuery,
    CompanyListResponse,
    MatchesQuery,
    MatchesResponse,
)
from solverah.services import matching_service

__all__ = ["companies_bp"]

companies_bp = Blueprint("companies", __name__)

_AUTHENTICATED = ["accessTokenCookie"]


def _respond(result: matching_service.MatchingResult):
    return jsonify(result.body), result.status


@document(
    "Fetch a company's full research profile",
    tags=["companies"],
    responses={200: CompanyDetailResponse, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
)
@companies_bp.route("/companies/<int:company_id>", methods=["GET"])
@jwt_required()
def company_detail(company_id: int):
    """GET /companies/<company_id> - Return a company's full profile."""
    return _respond(matching_service.company_detail(company_id))


@document(
    "List companies, filtered and paginated",
    tags=["companies"],
    query=CompanyListQuery,
    responses={200: CompanyListResponse, 422: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
)
@companies_bp.route("/companies", methods=["GET"])
@jwt_required()
def company_list():
    """GET /companies - one page of companies.

    New in Phase 1b: there was no list endpoint, so a screen wanting several
    companies fetched the full research document for each one by id.

    Paginated with an opaque keyset cursor, never an offset (A5). Pass
    next_cursor back as ?cursor= and stop when it comes back null. A cursor the
    server did not mint is a 422, not a silent page one -- answering a garbled
    cursor with the first page is how a paging loop becomes an infinite one.
    """
    return _respond(
        matching_service.list_companies(
            cursor=request.args.get("cursor"),
            limit=request.args.get("limit"),
            q=request.args.get("q"),
            industry=request.args.get("industry"),
        )
    )


@document(
    "Rank companies by fit for the authenticated user",
    tags=["companies"],
    query=MatchesQuery,
    responses={200: MatchesResponse, 400: LegacyError, 404: LegacyError, 422: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
    description=(
        "Replaces `GET /company-lens/matches`, which returned two fixed-size "
        "slices -- `best_fits` and `worst_fits` -- in one body, with nothing "
        "reachable beyond them. `?order=worst` carries the second slice over: "
        "the two halves are now two directions through one paginated list.\n\n"
        "Still an O(all-companies) in-process scan that can commit a backfill "
        "on the read path (P0-2). The cursor is what lets Phase 2 fix that "
        "behind an unchanged contract; it is not itself the fix."
    ),
)
@companies_bp.route("/me/matches", methods=["GET"])
@jwt_required()
def my_matches():
    """GET /me/matches - companies ranked by culture fit, one page at a time.

    A user who completed Work Pulse before culture_preferences was persisted
    gets it backfilled here, which is why a GET can write.
    """
    user = user_repository.find_by_email(get_jwt_identity())
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(
        matching_service.matches(
            user,
            cursor=request.args.get("cursor"),
            limit=request.args.get("limit"),
            lens=request.args.get("lens"),
            order=request.args.get("order"),
            logger=current_app.logger,
        )
    )
