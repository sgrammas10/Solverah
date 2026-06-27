"""LLM narrative layer for career path suggestions.

Takes the top scored candidates from the path-scoring algorithm and calls
OpenAI to select the best 2–3, writing a plain-language explanation for
each.  No scoring logic lives here — all numeric work is done upstream in
path_scoring.py.

Environment variables
---------------------
OPENAI_API_KEY        Required.  Standard OpenAI credential.
OPENAI_NARRATIVE_MODEL  Optional.  Defaults to "gpt-4o-mini".
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Literal

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment,misc]

from backend.services.path_scoring import ScoredPath

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class UserContext:
    archetype: str                                              # WorkPulse archetype label
    management_preferences: dict                               # Full ManagerMatch result dict
    career_status: Literal["employed", "between_jobs", "first_job"]
    top_skills: list[str]                                      # Highest-expertise skill names
    move_intent: str | None = None
    seniority_intent: str | None = None
    priority: str | None = None


@dataclass
class PathSuggestion:
    onet_code: str
    title: str
    why_text: str               # 1–2 sentence plain-language explanation
    profile_dimensions: list[str] = field(default_factory=list)  # 2–3 short tag strings


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class NarrativeGenerationError(Exception):
    """Raised when the LLM returns a malformed response on both attempts."""


# ---------------------------------------------------------------------------
# OpenAI client  (same pattern as app.py _get_openai_client)
# ---------------------------------------------------------------------------


def _get_openai_client():
    if OpenAI is None:
        raise RuntimeError("openai package is not installed")
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key, timeout=60.0, max_retries=2)


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


_MOVE_INTENT_LABELS: dict[str, str] = {
    "stay_in_field": "Stay in my field",
    "adjacent": "Something adjacent",
    "fresh_start": "Fresh direction",
}
_SENIORITY_INTENT_LABELS: dict[str, str] = {
    "move_up": "Looking to move up",
    "stay_lateral": "Similar level",
    "open": "Open to either",
}
_PRIORITY_LABELS: dict[str, str] = {
    "pay_title": "Pay & title",
    "interesting_work": "Interesting work",
    "work_life_balance": "Work-life balance",
    "learning_growth": "Learning & growth",
}


def _format_management_prefs(prefs: dict) -> str:
    if not prefs:
        return "Not provided."
    parts: list[str] = []
    archetype = prefs.get("archetype", "")
    if archetype:
        parts.append(f"Manager archetype: {archetype}")
    for dim, score in (prefs.get("dimension_scores") or {}).items():
        label = dim.replace("_", " ").title()
        parts.append(f"  {label}: {float(score):.2f}")
    return "\n".join(parts) if parts else "Not provided."


def _build_prompt(
    candidates: list[ScoredPath],
    ctx: UserContext,
) -> list[dict]:
    """Return the OpenAI messages list for the narrative prompt."""
    candidates_json = json.dumps(
        [
            {
                "onet_code": c.onet_code,
                "title": c.title,
                "match_score": c.score,
                "overlapping_skills": c.overlapping_skills,
            }
            for c in candidates
        ],
        indent=2,
    )

    system = (
        "You are a career advisor helping users identify realistic next-step career paths.\n\n"
        "CRITICAL RULES — follow exactly:\n"
        "1. Write a narrative for EVERY candidate in the list — do not skip any.\n"
        "2. Preserve the exact order of the candidates as given.\n"
        "3. why_text: 1–2 sentences, plain language, specific to this user, encouraging.\n"
        "4. profile_dimensions: a list of exactly 2 or 3 short tags (5–8 words each) "
        "that reference the user's actual skills, archetype, or preferences. "
        "Examples: 'Builds on your Python skills', 'Fits your autonomy preference', "
        "'Matches your Deep Diver archetype'.\n\n"
        "Return ONLY a JSON object with this exact schema — no markdown, no prose:\n"
        "{\n"
        '  "suggestions": [\n'
        "    {\n"
        '      "onet_code": "<code from the candidate list>",\n'
        '      "title": "<occupation title>",\n'
        '      "why_text": "<1–2 sentence explanation>",\n'
        '      "profile_dimensions": ["<tag1>", "<tag2>"]\n'
        "    }\n"
        "  ]\n"
        "}"
    )

    top_skills_str = (
        ", ".join(ctx.top_skills) if ctx.top_skills else "none listed"
    )
    management_str = _format_management_prefs(ctx.management_preferences)

    prefs_section = ""
    if any([ctx.move_intent, ctx.seniority_intent, ctx.priority]):
        move_label = _MOVE_INTENT_LABELS.get(ctx.move_intent or "", "Not specified")
        seniority_label = _SENIORITY_INTENT_LABELS.get(ctx.seniority_intent or "", "Not specified")
        priority_label = _PRIORITY_LABELS.get(ctx.priority or "", "Not specified")
        prefs_section = (
            "Preferences\n"
            "===========\n"
            f"Move direction:    {move_label}\n"
            f"Seniority intent:  {seniority_label}\n"
            f"What matters most: {priority_label}\n\n"
        )

    user_msg = (
        "User Profile\n"
        "============\n"
        f"Career status:        {ctx.career_status}\n"
        f"WorkPulse archetype:  {ctx.archetype}\n"
        f"Top skills:           {top_skills_str}\n"
        f"Management preferences:\n{management_str}\n\n"
        f"{prefs_section}"
        "Candidate Career Paths (sorted by match_score, highest first)\n"
        "==============================================================\n"
        f"{candidates_json}\n\n"
        "Write a why_text and profile_dimensions for every candidate above, "
        "in the same order, and return the JSON object."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]


# ---------------------------------------------------------------------------
# Response validation
# ---------------------------------------------------------------------------


def _validate_response(data: dict, valid_codes: set[str]) -> list[PathSuggestion]:
    """Parse and validate the LLM JSON dict into PathSuggestion objects.

    Raises:
        ValueError: With a description of the first constraint violated.
    """
    suggestions_raw = data.get("suggestions")
    if not isinstance(suggestions_raw, list):
        raise ValueError(
            f"'suggestions' must be a list, got {type(suggestions_raw).__name__}"
        )
    if len(suggestions_raw) == 0:
        raise ValueError("'suggestions' list is empty")

    results: list[PathSuggestion] = []
    for i, item in enumerate(suggestions_raw):
        if not isinstance(item, dict):
            raise ValueError(f"suggestions[{i}] is not a dict")

        for required_key in ("onet_code", "title", "why_text", "profile_dimensions"):
            if required_key not in item:
                raise ValueError(
                    f"suggestions[{i}] is missing required key '{required_key}'"
                )

        code: str = item["onet_code"]
        if code not in valid_codes:
            raise ValueError(
                f"suggestions[{i}].onet_code '{code}' is not in the input candidate list"
            )

        dims = item["profile_dimensions"]
        if not isinstance(dims, list) or len(dims) < 2:
            raise ValueError(
                f"suggestions[{i}].profile_dimensions must be a list of at least 2 strings, "
                f"got {dims!r}"
            )

        results.append(
            PathSuggestion(
                onet_code=code,
                title=str(item["title"]),
                why_text=str(item["why_text"]),
                profile_dimensions=[str(d) for d in dims],
            )
        )

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_narratives(
    candidates: list[ScoredPath],
    user_context: UserContext,
) -> list[PathSuggestion]:
    """Generate plain-language career path suggestions from scored candidates.

    Calls OpenAI to write a narrative for every scored candidate.  Order is
    preserved from the input (highest score first).  If the response is
    malformed, one retry is attempted before raising NarrativeGenerationError.

    Args:
        candidates:   Scored candidates from path_scoring.score_paths (up to 10).
        user_context: User's archetype, preferences, and top skills.

    Returns:
        PathSuggestion objects for every input candidate, in score order.

    Raises:
        NarrativeGenerationError: Input is empty, or LLM response is
                                   malformed on both attempts.
        RuntimeError:              OPENAI_API_KEY missing or openai not installed.
    """
    if not candidates:
        raise NarrativeGenerationError(
            "Cannot generate narratives: candidate list is empty"
        )

    valid_codes: set[str] = {c.onet_code for c in candidates}
    client = _get_openai_client()
    model = os.environ.get("OPENAI_NARRATIVE_MODEL", "gpt-4o-mini")
    messages = _build_prompt(candidates, user_context)

    last_error: Exception | None = None
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            return _validate_response(data, valid_codes)
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc

    raise NarrativeGenerationError(
        f"LLM returned a malformed narrative response on both attempts. "
        f"Last error: {last_error}"
    )
