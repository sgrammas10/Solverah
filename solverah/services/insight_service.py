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


#: Generic text for a failed generation. The provider's own error stays in the log.
_GENERATION_FAILED_MESSAGE = "We couldn't generate your insight right now. Please try again in a moment."

#: Total answered items across every quiz in one request. The schema caps each
#: quiz (40 items) and the quiz count (8); this caps the product. The six real
#: quizzes together come to 78.
MAX_TOTAL_ITEMS = 120


def _error(status: int, message: str, code: Optional[str] = None) -> InsightResult:
    body: Dict[str, Any] = {"error": message}
    if code:
        body["code"] = code
    return InsightResult(status=status, body=body)


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
            max_completion_tokens=llm.QUIZ_INSIGHT_MAX_COMPLETION_TOKENS,
        )
        insight_payload = json.loads(response.choices[0].message.content or "{}")
    except Exception as exc:  # noqa: BLE001 -- logged, then answered generically
        # The exception type and message go to the log, not the response
        # (2026-10-02 audit #4). The body used to carry them -- "the fastest
        # route to the cause" for an operator -- but the modal rendered that
        # body to users, provider error text and all. The log line has the
        # traceback, and `code` tells a client which failure this was.
        logger.exception(
            "Quiz insight generation failed (model=%s): %s: %s", model, type(exc).__name__, exc
        )
        return None, _error(500, _GENERATION_FAILED_MESSAGE, "insight_generation_failed"), model

    normalized = insight_prompts.coerce_insight_payload(insight_payload, quiz_group, quizzes)
    return normalized, None, model


def _validate_request(quiz_group: str, quizzes: Any):
    """Shared front-door validation. Returns ``(normalized, error_result)``."""
    if not quiz_group or not isinstance(quizzes, list) or not quizzes:
        return None, _error(400, "quizGroup and quizzes are required")

    normalized = normalize_quizzes(quizzes)
    if not normalized:
        return None, _error(400, "No valid quiz answers provided")
    if sum(len(quiz["items"]) for quiz in normalized) > MAX_TOTAL_ITEMS:
        return None, _error(400, "Too many quiz answers in one request")
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
        return _error(500, _GENERATION_FAILED_MESSAGE, "insight_malformed")

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

    No transaction is open during that call. The route's user lookup began one,
    and it is ended before the provider is asked rather than left idling through
    the round trip; the id is taken first because the commit expires the row.
    """
    quiz_group = (data.get("quizGroup") or "").strip()
    normalized, error = _validate_request(quiz_group, data.get("quizzes") or [])
    if error:
        return error

    user_id = user.id if user is not None else None
    db.session.commit()

    payload, error, model = _generate(quiz_group, normalized, logger)
    if error:
        return error

    insights = payload.get("insights") if isinstance(payload, dict) else None
    overall_insight = payload.get("overallInsight") if isinstance(payload, dict) else None

    if not isinstance(insights, list):
        return _error(500, _GENERATION_FAILED_MESSAGE, "insight_malformed")

    if user_id is None:
        return _error(404, "User not found")

    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    posted_keys = [quiz["key"] for quiz in normalized]
    # What the response reports as the group's synthesis: for careerQuizzes,
    # the one actually stored, which a partial post leaves unchanged.
    reported_overall: Dict[str, Any] = {"value": overall_insight}

    def store(stored: Any) -> Dict[str, Any]:
        # `quizInsights` is one profile key, written as one: the rest of the
        # document is neither read nor rewritten to replace it.
        quiz_insights = dict(stored) if isinstance(stored, dict) else {}

        if quiz_group == CAREER_QUIZ_GROUP:
            group = _career_group_store(
                quiz_insights.get(CAREER_QUIZ_GROUP),
                insights,
                overall_insight,
                timestamp,
                model,
                posted_keys,
            )
            quiz_insights[CAREER_QUIZ_GROUP] = group
            reported_overall["value"] = group.get("_overallInsight")
            # Before 2026-10-02 the guest replay stored two of these quizzes as
            # flat groups of their own (G16). Once the quiz has an entry in the
            # career group, the flat copy is a stale duplicate that the agent
            # context would read twice; drop it -- but only once the nested entry
            # exists. A model response can omit a posted quiz, and deleting the
            # flat copy then would lose that insight outright.
            for key in posted_keys:
                if key != CAREER_QUIZ_GROUP and key in group and key in quiz_insights:
                    del quiz_insights[key]
        else:
            quiz_insights[quiz_group] = _single_group_store(
                insights, overall_insight, timestamp, model
            )
        return quiz_insights

    profile_repository.update_extra_key(user_id, "quizInsights", store)
    db.session.commit()

    return InsightResult(
        status=200,
        body={
            "quizGroup": quiz_group,
            "overallInsight": reported_overall["value"],
            "insights": insights,
        },
    )


def _stored_quiz_keys(group: Dict[str, Any]) -> set:
    """The quiz entries in a stored career group: not metadata, dict-valued."""
    return {
        key for key, value in group.items()
        if not key.startswith("_") and isinstance(value, dict)
    }


def _career_group_store(
    existing, insights, overall_insight, timestamp, model, posted_keys=()
) -> Dict[str, Any]:
    """The careerQuizzes group stores one entry per quiz, keyed by quiz key.

    Merged over what is already there rather than replacing it, so generating
    insights for one quiz does not erase the others. The underscore-prefixed
    keys are group-level metadata and cannot collide with a quiz key.

    ``_overallInsight`` is the page's "Across all your quizzes" card, so it is
    replaced only by a synthesis that saw every quiz the group already holds
    (2026-10-02 audit #6). A post of one quiz into a group holding three used
    to overwrite it with a one-quiz synthesis under that heading. A partial
    post now updates its own entries and leaves the synthesis as it was; the
    SPA posts every saved quiz together, so the synthesis stays current.
    ``_overallKeys`` records which quizzes the stored synthesis covers.
    """
    store = dict(existing) if isinstance(existing, dict) else {}

    covers_all = _stored_quiz_keys(store) <= set(posted_keys)
    if overall_insight and isinstance(overall_insight, dict) and covers_all:
        store["_overallInsight"] = overall_insight
        store["_overallKeys"] = sorted(set(posted_keys))
    store["_generatedAt"] = timestamp
    store["_model"] = model

    for insight in insights:
        if not isinstance(insight, dict):
            continue
        key = insight.get("key")
        if not key:
            continue
        # Only quizzes that were actually posted. A key the model invented
        # would sit in the group as a "stored quiz" no later post ever covers,
        # so `covers_all` would stay False and the combined card never update.
        if posted_keys and key not in posted_keys:
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
