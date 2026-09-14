"""AI-generated career insights from quiz answers.

Two endpoints share almost everything: an authenticated one that persists into
the profile's ``quizInsights``, and an anonymous preview limited to one call per
IP per day.  The differences are two: whether the result is stored, and the name
of one response key -- authenticated returns ``overallInsight``, the guest
preview returns ``overallSummary``.  Both are read by the frontend, so both are
preserved.

Normalisation happens before the model is called (:func:`normalize_quizzes`) and
again after (``insight_prompts.coerce_insight_payload``).  Neither is optional:
the first stops empty or malformed quizzes from being paid for, and the second
stops a non-compliant model response from reaching the client or the blob.
"""

from __future__ import annotations

import datetime
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from model import User, db
from solverah.infra import llm
from solverah.repositories import profile_repository
from solverah.services import insight_prompts

__all__ = [
    "CAREER_QUIZ_GROUP",
    "InsightResult",
    "generate_for_guest",
    "generate_for_user",
    "normalize_quizzes",
]

#: The one group stored per-quiz rather than as a single document.
CAREER_QUIZ_GROUP = "careerQuizzes"


@dataclass
class InsightResult:
    """A service outcome the API layer turns into a response."""

    status: int
    body: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status < 400


def _error(status: int, message: str) -> InsightResult:
    return InsightResult(status=status, body={"error": message})


def normalize_quizzes(quizzes: Any) -> List[Dict[str, Any]]:
    """Drop anything unusable and trim what is left.

    A quiz survives only with a key, a title, and at least one item that has
    both a question and a selected answer. Everything else is discarded rather
    than sent -- a half-empty quiz costs a token spend and produces an insight
    about nothing.
    """
    normalized = []
    for quiz in quizzes or []:
        if not isinstance(quiz, dict):
            continue
        key = (quiz.get("key") or "").strip()
        title = (quiz.get("title") or "").strip()
        items = quiz.get("items") or []
        if not key or not title or not isinstance(items, list) or not items:
            continue
        normalized_items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            question = (item.get("question") or "").strip()
            selected = (item.get("selected") or "").strip()
            if question and selected:
                normalized_items.append({"question": question, "selected": selected})
        if normalized_items:
            normalized.append({"key": key, "title": title, "items": normalized_items})
    return normalized


def _generate(quiz_group: str, quizzes: List[Dict[str, Any]], logger) -> Tuple[Any, Any, str]:
    """Call the model and normalise its response.

    Returns:
        ``(payload, error_result, model)``. Exactly one of payload/error is set.
    """
    model = os.environ.get("OPENAI_QUIZ_MODEL", "gpt-4o-mini")
    try:
        client = llm.get_openai_client()
        response = client.chat.completions.create(
            model=model,
            messages=insight_prompts.build_quiz_insight_prompt(quiz_group, quizzes),
            response_format={"type": "json_object"},
        )
        insight_payload = json.loads(response.choices[0].message.content or "{}")
    except Exception as exc:  # noqa: BLE001 -- surfaced to the caller
        logger.exception("Quiz insight generation failed")
        # The exception type and message are included deliberately: this is an
        # operator-facing failure on a feature that is easy to misconfigure
        # (missing key, wrong model name), and the class name is the fastest
        # route to the cause. It leaks no user data and no stack frames.
        return None, _error(
            500, "Unable to generate insight: %s: %s" % (type(exc).__name__, exc)
        ), model

    normalized = insight_prompts.coerce_insight_payload(insight_payload, quiz_group, quizzes)
    return normalized, None, model


def _validate_request(quiz_group: str, quizzes: Any):
    """Shared front-door validation. Returns ``(normalized, error_result)``."""
    if not quiz_group or not isinstance(quizzes, list) or not quizzes:
        return None, _error(400, "quizGroup and quizzes are required")

    normalized = normalize_quizzes(quizzes)
    if not normalized:
        return None, _error(400, "No valid quiz answers provided")
    return normalized, None


def generate_for_guest(data: Dict[str, Any], logger) -> InsightResult:
    """Anonymous preview. Nothing is persisted."""
    quiz_group = (data.get("quizGroup") or "").strip()
    normalized, error = _validate_request(quiz_group, data.get("quizzes") or [])
    if error:
        return error

    payload, error, _model = _generate(quiz_group, normalized, logger)
    if error:
        return error

    insights = payload.get("insights") if isinstance(payload, dict) else None
    # `coerce_insight_payload` names this field `overallInsight` on both
    # paths -- there is no `overallSummary` key on `payload` for this to have
    # ever read, so it was always None. The guest response deliberately
    # flattens the dict to just its `summary` text (D-5, docs/BUILD_PLAN.md):
    # `GuestQuizInsights.tsx` types `overallSummary` as a plain string and
    # renders it directly, unlike the authenticated page, which renders
    # `overallInsight`'s keyTakeaways/nextSteps as a full dict too.
    overall_insight = payload.get("overallInsight") if isinstance(payload, dict) else None
    overall_summary = overall_insight.get("summary") if isinstance(overall_insight, dict) else None

    if not isinstance(insights, list):
        return _error(500, "Malformed insight response")

    return InsightResult(
        status=200,
        body={
            "quizGroup": quiz_group,
            "overallSummary": overall_summary,
            "insights": insights,
        },
    )


def generate_for_user(user: Optional[User], data: Dict[str, Any], logger) -> InsightResult:
    """Authenticated generation, persisted into the profile's ``quizInsights``.

    Note the ordering: the model is called *before* the user is looked up, which
    is how the original ran. It means a request from a JWT whose user has since
    been deleted still pays for a completion before returning 404. Preserved,
    because reordering changes which error a caller sees.
    """
    quiz_group = (data.get("quizGroup") or "").strip()
    normalized, error = _validate_request(quiz_group, data.get("quizzes") or [])
    if error:
        return error

    payload, error, model = _generate(quiz_group, normalized, logger)
    if error:
        return error

    insights = payload.get("insights") if isinstance(payload, dict) else None
    overall_insight = payload.get("overallInsight") if isinstance(payload, dict) else None

    if not isinstance(insights, list):
        return _error(500, "Malformed insight response")

    if not user:
        return _error(404, "User not found")

    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def store(existing: Dict[str, Any]) -> Dict[str, Any]:
        quiz_insights = existing.get("quizInsights")
        quiz_insights = dict(quiz_insights) if isinstance(quiz_insights, dict) else {}

        if quiz_group == CAREER_QUIZ_GROUP:
            quiz_insights[CAREER_QUIZ_GROUP] = _career_group_store(
                quiz_insights.get(CAREER_QUIZ_GROUP),
                insights,
                overall_insight,
                timestamp,
                model,
            )
        else:
            quiz_insights[quiz_group] = _single_group_store(
                insights, overall_insight, timestamp, model
            )
        return {**existing, "quizInsights": quiz_insights}

    profile_repository.update_document(user.id, store)
    db.session.commit()

    return InsightResult(
        status=200,
        body={
            "quizGroup": quiz_group,
            "overallInsight": overall_insight,
            "insights": insights,
        },
    )


def _career_group_store(existing, insights, overall_insight, timestamp, model) -> Dict[str, Any]:
    """The careerQuizzes group stores one entry per quiz, keyed by quiz key.

    Merged over what is already there rather than replacing it, so generating
    insights for one quiz does not erase the others. The underscore-prefixed
    keys are group-level metadata and cannot collide with a quiz key.
    """
    store = dict(existing) if isinstance(existing, dict) else {}

    if overall_insight and isinstance(overall_insight, dict):
        store["_overallInsight"] = overall_insight
    store["_generatedAt"] = timestamp
    store["_model"] = model

    for insight in insights:
        if not isinstance(insight, dict):
            continue
        key = insight.get("key")
        if not key:
            continue
        store[key] = {
            "title": insight.get("title"),
            "summary": insight.get("summary"),
            "keyTakeaways": insight.get("keyTakeaways"),
            "combinedMeaning": insight.get("combinedMeaning"),
            "nextSteps": insight.get("nextSteps"),
            "generatedAt": timestamp,
            "model": model,
        }
    return store


def _single_group_store(insights, overall_insight, timestamp, model) -> Dict[str, Any]:
    """Every other group stores one flat document built from the first insight."""
    first = insights[0] if insights else {}
    return {
        "title": first.get("title"),
        "summary": first.get("summary"),
        "keyTakeaways": first.get("keyTakeaways"),
        "combinedMeaning": first.get("combinedMeaning"),
        "nextSteps": first.get("nextSteps"),
        "overallInsight": overall_insight,
        "generatedAt": timestamp,
        "model": model,
    }
