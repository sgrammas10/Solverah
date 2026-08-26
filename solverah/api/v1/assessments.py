"""The five assessment instruments.

Paths unchanged: ``/work-pulse/lite-lite/result``, ``/work-pulse/submit``,
``/work-pulse/results``, ``/focus-type/submit``, ``/manager-match/submit``,
``/manager-match/results``, ``/assessment/form``, ``/assessment/submit``.

The two person-side culture routes at the bottom are thin on purpose.  Every
correctness requirement -- the server-authoritative shuffle (D-04), the
cross-dimension interleave, the opaque item tokens, the per-dimension arity check
(D-02) -- lives in ``assessment_form.py`` and ``present_items.py``.  A route that
reimplements any of it, or reaches past ``assessment_form`` into
``present_items`` / ``score_person_side`` directly, is a bug.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from solverah.extensions import limiter
from solverah.openapi import document
from solverah.repositories import user_repository
from solverah.schemas import LegacyError
from solverah.schemas.assessments import (
    AssessmentFormResponse,
    AssessmentSubmitRequest,
    AssessmentSubmitResponse,
    FocusTypeResult,
    FocusTypeSubmitRequest,
    ManagerMatchResult,
    ManagerMatchSubmitRequest,
    WorkPulseResult,
    WorkPulseSubmitRequest,
    WpllResultResponse,
    WpllSubmitRequest,
)
from solverah.services import assessment_service

__all__ = ["assessments_bp"]

assessments_bp = Blueprint("assessments", __name__)

_AUTHENTICATED = ["accessTokenCookie"]
_AUTHENTICATED_WRITE = ["accessTokenCookie", "csrfHeader"]


def _respond(result: assessment_service.AssessmentResult):
    return jsonify(result.body), result.status


def _current_user():
    return user_repository.find_by_email(get_jwt_identity())


@document(
    "Generate the anonymous Work Pulse Lite-Lite teaser insight",
    tags=["assessments"],
    request=WpllSubmitRequest,
    responses={200: WpllResultResponse, 400: LegacyError},
    security=[],
)
@assessments_bp.route("/work-pulse/lite-lite/result", methods=["POST"])
def work_pulse_lite_lite_result():
    """POST /work-pulse/lite-lite/result - LLM-powered insight for the WPLL teaser.

    Anonymous endpoint - no auth required. Calls OpenAI to generate a
    personalised 2-3 sentence insight from the 5 WPLL answers, then returns it
    alongside the fixed set of locked section titles shown on the result screen.
    Falls back silently to the rules-based engine if the LLM call fails or
    returns a malformed response.
    """
    data = request.get_json(silent=True) or {}
    return _respond(assessment_service.wpll_insight(data.get("answers", [])))


@document(
    "Generate and persist a Work Pulse narrative",
    tags=["assessments"],
    request=WorkPulseSubmitRequest,
    responses={200: WorkPulseResult, 400: LegacyError, 404: LegacyError, 500: LegacyError},
    security=_AUTHENTICATED_WRITE,
)
@assessments_bp.route("/work-pulse/submit", methods=["POST"])
@limiter.limit("5 per minute")
@jwt_required()
def work_pulse_submit():
    """POST /work-pulse/submit - Generate and persist a Work Pulse narrative.

    Validates the 12 WP answers, calls OpenAI with a structured prompt that
    optionally incorporates earlier WPLL signals from the user's intake row,
    then persists the answers and narrative to user_intake.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    return _respond(
        assessment_service.submit_work_pulse(user, data.get("answers"), current_app.logger)
    )


@document(
    "Retrieve the stored Work Pulse result",
    tags=["assessments"],
    responses={200: WorkPulseResult, 404: LegacyError, 422: LegacyError},
    security=_AUTHENTICATED,
)
@assessments_bp.route("/work-pulse/results", methods=["GET"])
@jwt_required()
def work_pulse_results_get():
    """GET /work-pulse/results - Retrieve persisted Work Pulse results.

    Returns the stored narrative, emerging signals, and archetype from the
    user's most recent Work Pulse submission. Used by the results page to
    rehydrate state in fresh browser sessions where sessionStorage has been
    cleared.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(assessment_service.get_work_pulse_result(user))


@document(
    "Score and persist a FocusType result",
    tags=["assessments"],
    request=FocusTypeSubmitRequest,
    responses={200: FocusTypeResult, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
)
@assessments_bp.route("/focus-type/submit", methods=["POST"])
@limiter.limit("5 per minute")
@jwt_required()
def focus_type_submit():
    """POST /focus-type/submit - Score and persist a FocusType result.

    Accepts the 5 scene payloads, runs deterministic scoring, and persists the
    archetype result to user.profile_data["focus_type_result"].
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(
        assessment_service.submit_focus_type(user, request.get_json(silent=True) or {})
    )


@document(
    "Score and persist a ManagerMatch result",
    tags=["assessments"],
    request=ManagerMatchSubmitRequest,
    responses={200: ManagerMatchResult, 400: LegacyError, 404: LegacyError, 500: LegacyError},
    security=_AUTHENTICATED_WRITE,
)
@assessments_bp.route("/manager-match/submit", methods=["POST"])
@limiter.limit("5 per minute")
@jwt_required()
def manager_match_submit():
    """POST /manager-match/submit - Score and persist a ManagerMatch result.

    Validates 15 forced-choice answers, runs deterministic scoring, calls OpenAI
    to generate a personalised narrative, then persists the full result to
    user.profile_data["manager_match_result"].
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    return _respond(
        assessment_service.submit_manager_match(
            user, data.get("answers"), current_app.logger
        )
    )


@document(
    "Retrieve the stored ManagerMatch result",
    tags=["assessments"],
    responses={200: ManagerMatchResult, 404: LegacyError},
    security=_AUTHENTICATED,
)
@assessments_bp.route("/manager-match/results", methods=["GET"])
@jwt_required()
def manager_match_results_get():
    """GET /manager-match/results - Retrieve the persisted ManagerMatch result."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(assessment_service.get_manager_match_result(user))


# ---------------------------------------------------------------------------
# Person-side culture assessment (S-01)
# ---------------------------------------------------------------------------

@document(
    "Fetch the person-side assessment items, ordered for this respondent",
    tags=["assessments"],
    responses={200: AssessmentFormResponse, 404: LegacyError, 500: LegacyError},
    security=_AUTHENTICATED,
)
@assessments_bp.route("/assessment/form", methods=["GET"])
@jwt_required()
def assessment_form_get():
    """GET /assessment/form - the person-side items, ordered for this respondent.

    The payload carries `blocks`, not `dimensions`. The client renders it
    verbatim: it must not sort, group, re-shuffle, or reorder options. Ordering
    is server-authoritative because two independent PRNGs in two languages
    diverging is silent, and a divergence corrupts a resumed session's ordering
    rather than raising.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(assessment_service.person_side_form(user, current_app.logger))


@document(
    "Score and persist a completed person-side assessment",
    tags=["assessments"],
    request=AssessmentSubmitRequest,
    responses={200: AssessmentSubmitResponse, 400: LegacyError, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
)
@assessments_bp.route("/assessment/submit", methods=["POST"])
@limiter.limit("5 per minute")
@jwt_required()
def assessment_submit():
    """POST /assessment/submit - score and persist a completed assessment.

    The six dimension scores are NOT returned. The documented threat to this
    instrument is aspirational answering by a user self-profiling for matching,
    and handing back the six numbers gives a retaking respondent a gradient to
    optimise against -- it teaches the item-to-dimension mapping that the
    shuffle and the interleave exist to hide. Whatever the user is eventually
    shown about their own profile should be designed against that pressure, not
    fall out of the submit response by default.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    return _respond(assessment_service.submit_person_side(user, data.get("responses")))
