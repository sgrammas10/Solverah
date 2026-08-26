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
    CultureMatchesQuery,
    CultureMatchesResponse,
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
)
@companies_bp.route("/companies/<int:company_id>", methods=["GET"])
@jwt_required()
def company_detail(company_id: int):
    """GET /companies/<company_id> - Return a company's full profile."""
    return _respond(matching_service.company_detail(company_id))


@document(
    "Rank companies by culture fit for the authenticated user",
    tags=["companies"],
    query=CultureMatchesQuery,
    responses={200: CultureMatchesResponse, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED,
)
@companies_bp.route("/company-lens/matches", methods=["GET"])
@jwt_required()
def company_lens_matches():
    """GET /company-lens/matches - Score all companies against culture preferences.

    Returns the best and worst fits. A user who completed Work Pulse before
    culture_preferences was persisted gets it backfilled here, which is why a
    GET can write.
    """
    user = user_repository.find_by_email(get_jwt_identity())
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(
        matching_service.culture_matches(
            user,
            raw_limit=request.args.get("limit", matching_service.DEFAULT_LIMIT),
            logger=current_app.logger,
        )
    )
