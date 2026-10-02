"""Prompt construction and response normalisation for AI quiz insights.

The model is asked for strict JSON with one insight per quiz in input order,
each carrying the quiz's ``key`` verbatim.  It does not always comply, which is
what :func:`coerce_insight_payload` is for: it forces the response back onto the
canonical shape rather than letting a malformed field reach the client or the
``profile_data`` blob.

Both functions are pure -- no network, no database, no app context.
"""

from __future__ import annotations

import json

__all__ = ["build_quiz_insight_prompt", "coerce_insight_payload"]


def build_quiz_insight_prompt(quiz_group: str, quizzes: list[dict]) -> list[dict]:
    """Construct the system + user messages for the quiz-insight OpenAI call.

    The prompt instructs the model to:
      - Return strictly valid JSON (no markdown or extra text).
      - Produce exactly one insight per quiz in input order.
      - Use each quiz's ``key`` field verbatim in its response.

    Args:
        quiz_group: Logical group label (e.g. ``"careerQuizzes"``).
        quizzes:    List of normalized quiz dicts, each with ``key``, ``title``,
                    and ``items`` (list of ``{question, selected}``).

    Returns:
        A two-element list of OpenAI chat message dicts:
        ``[{"role": "system", ...}, {"role": "user", ...}]``.
    """
    quiz_keys = [q.get("key", f"quiz_{i}") for i, q in enumerate(quizzes)]
    system = (
        "You are an expert career insights engine designed to analyze structured quiz responses "
        "and extract meaningful career-related patterns.\n\n"

        "PRIMARY OBJECTIVE:\n"
        "Generate one distinct, personalized insight for EACH quiz provided. "
        "Each insight must be specific to that quiz's answers — do not merge or combine quizzes.\n\n"

        "STRICT RULES:\n"
        "- Output VALID JSON only. Do not include markdown, commentary, or extra text.\n"
        "- The 'insights' array MUST contain exactly one entry per quiz, in the same order as the input.\n"
        "- Each insight's 'key' MUST exactly match the corresponding quiz's 'key' field.\n"
        "- Do NOT invent traits, preferences, or experiences not supported by the input.\n"
        "- Do NOT provide medical, psychological, or legal advice.\n"
        "- Avoid generic career advice that could apply to anyone.\n"
        "- Maintain a professional, supportive, and non-judgmental tone.\n"
        "- Be concise but information-dense.\n"

        "INSIGHT QUALITY GUIDELINES:\n"
        "- Each insight should reveal something specific to that quiz's answers.\n"
        "- Prefer specificity over broad statements.\n"
        "- Recommendations must be practical and immediately actionable.\n"
        f"- You will receive {len(quizzes)} quiz(zes). Return exactly {len(quizzes)} insight(s).\n"
        f"- Expected keys in order: {quiz_keys}\n"
    )
    user_payload = {
        "quiz_group": quiz_group,
        "quizzes": quizzes,
        "output_rules": {
            "tone": "clear, supportive, non-judgmental",
            "length": "short but meaningful",
            "key_takeaways_count": "3-5",
            "next_steps_count": "2-4",
            "insights_count": len(quizzes),
        },
        "output_format": {
            "overallInsight": {
                "summary": "string — synthesis across ALL quizzes combined",
                "keyTakeaways": ["string — cross-quiz pattern or theme"],
                "nextSteps": ["string — actionable step informed by all quizzes"],
            },
            "insights": [
                {
                    "key": "must match the quiz key exactly",
                    "title": "string — name of this specific quiz",
                    "summary": "string — insight specific to this quiz only",
                    "keyTakeaways": ["string"],
                    "combinedMeaning": "string",
                    "nextSteps": ["string"],
                },
                {
                    "key": "next quiz key",
                    "title": "string",
                    "summary": "string",
                    "keyTakeaways": ["string"],
                    "combinedMeaning": "string",
                    "nextSteps": ["string"],
                },
            ],
        },
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload)},
    ]


def _as_text(value: object) -> str | None:
    """A string field as a non-empty string or ``None``.

    A list (the model sometimes answers a prose field with bullets) is joined
    rather than dropped; anything else that is not text is ``None``.
    """
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        joined = " ".join(item.strip() for item in value if isinstance(item, str) and item.strip())
        return joined or None
    return None


def _as_text_list(value: object) -> list[str]:
    """A list field as a list of non-empty strings -- always a list.

    The page calls ``.map`` on ``keyTakeaways`` and ``nextSteps``, so a bare
    string, a number, or a dict from a non-compliant model response would
    throw in the browser (2026-10-02 audit #14). A single string becomes a
    one-item list; non-string items and blanks are dropped.
    """
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


def coerce_insight_payload(payload: dict, quiz_group: str, fallback_quizzes: list[dict]) -> dict:
    """Normalise the raw JSON returned by the OpenAI insight call.

    The model occasionally returns a single insight dict instead of a list, or
    omits the ``key`` field.  This function defensively coerces the payload to a
    canonical structure so the rest of the endpoint doesn't need to handle every
    malformed variant.

    Args:
        payload:          Parsed JSON dict from the OpenAI response.
        quiz_group:       Used to generate a fallback key if none is present.
        fallback_quizzes: The original quiz list — used to recover ``key`` values
                          when the model forgets to echo them back.

    Returns:
        Dict with ``{"overallInsight": ..., "insights": [...]}``, or ``{}`` if
        the payload cannot be salvaged.
    """
    if not isinstance(payload, dict):
        return {}
    insights = payload.get("insights")
    raw_overall = payload.get("overallInsight")
    overall_insight = None
    if isinstance(raw_overall, dict):
        overall_insight = {
            "summary": _as_text(raw_overall.get("summary")),
            "keyTakeaways": _as_text_list(raw_overall.get("keyTakeaways")),
            "nextSteps": _as_text_list(raw_overall.get("nextSteps")),
        }
        if not any(overall_insight.values()):
            overall_insight = None

    if isinstance(insights, dict):
        insights = [insights]

    if not isinstance(insights, list):
        return {}

    normalized = []
    for idx, item in enumerate(insights):
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if not key and fallback_quizzes and idx < len(fallback_quizzes):
            key = fallback_quizzes[idx].get("key")
        normalized.append(
            {
                "key": key or f"{quiz_group}-{idx+1}",
                "title": _as_text(item.get("title")),
                "summary": _as_text(item.get("summary")),
                "keyTakeaways": _as_text_list(item.get("keyTakeaways")),
                "combinedMeaning": _as_text(item.get("combinedMeaning")),
                "nextSteps": _as_text_list(item.get("nextSteps")),
            }
        )

    if not normalized:
        return {}

    return {"overallInsight": overall_insight, "insights": normalized}
