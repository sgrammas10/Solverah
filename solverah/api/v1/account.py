"""Account deletion and data export -- GDPR/CCPA-style user rights endpoints.

Served at ``/api/v1/account/{export,delete}`` and, for the length of the
frontend cutover, at ``/api/account/{export,delete}``.  Neither path, request
body, nor response shape changed in Phase 1.

The D-16 reconciliation these implement, the tombstone strategy, and the reason
object storage is cleared before the database are all documented in
``solverah/services/account_service.py``.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required, unset_jwt_cookies

from solverah.openapi import document
from solverah.repositories import user_repository
from solverah.schemas import LegacyError
from solverah.schemas.account import (
    AccountDeleteRequest,
    AccountDeleteResponse,
    AccountExportResponse,
)
from solverah.services import account_service

__all__ = ["account_bp"]

# The blueprint name is preserved from when this module lived at the repo root:
# it is the first half of the endpoint name ("account_lifecycle.export_account_data"),
# which Flask-Limiter uses as its storage key and the audit log records.
account_bp = Blueprint("account_lifecycle", __name__)


def _current_user():
    """The account behind the JWT.

    The identity claim is the user's EMAIL -- every ``create_access_token`` call
    issues ``identity=user.email``. Parsing it as an id raised ValueError on
    every authenticated call into this module.
    """
    return user_repository.find_by_email(get_jwt_identity())


@document(
    "Export every identified data class held for the authenticated user",
    tags=["account"],
    responses={200: AccountExportResponse, 404: LegacyError},
    security=["accessTokenCookie"],
)
@account_bp.route("/account/export", methods=["GET"])
@jwt_required()
def export_account_data():
    """GET /account/export - one JSON document of everything we hold."""
    user = _current_user()
    if user is None:
        return jsonify({"error": "User not found"}), 404

    result = account_service.export_account_data(user)
    return jsonify(result.body), result.status


@document(
    "Erase personal data, retaining de-identified assessment rows",
    tags=["account"],
    request=AccountDeleteRequest,
    responses={200: AccountDeleteResponse, 400: LegacyError, 404: LegacyError},
    security=["accessTokenCookie", "csrfHeader"],
)
@account_bp.route("/account/delete", methods=["POST"])
@jwt_required()
def delete_account():
    """POST /account/delete - erase personal data; keep de-identified research rows.

    Body (JSON): {"confirm": "DELETE"} - explicit confirmation string so a
    stray click or replayed request cannot destroy an account.
    """
    data = request.get_json(silent=True) or {}

    # Confirmation is checked before the user lookup so an unconfirmed request
    # gets the same 400 whether or not the JWT still maps to an account.
    if data.get("confirm") != account_service.DELETE_CONFIRMATION:
        result = account_service.delete_account(None, data.get("confirm"))
        return jsonify(result.body), result.status

    user = _current_user()
    if user is None:
        return jsonify({"error": "User not found"}), 404

    result = account_service.delete_account(user, data.get("confirm"))
    response = jsonify(result.body)
    if result.clear_session:
        unset_jwt_cookies(response)
    return response, result.status
