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
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Literal

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment,misc]

from backend.services.path_scoring import ScoredPath

logger = logging.getLogger(__name__)

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
    """Return the OpenAI messages list for the narrative prompt.

    **No score goes into this prompt (W-13, ruling flag 12).**  The candidate
    JSON used to carry ``match_score`` and the heading used to say "sorted by
    match_score, highest first", and a model handed a number writes about the
    number: the third browser test found "...making it a strong fit for your
    background." on a Database Administrators card.  The order is still the
    order -- the list arrives ranked and rule 2 pins it -- so nothing the
    narrator needs was removed with the field.  The deterministic
    :func:`_scrub_grades` below is the other half: the prompt is the request and
    the scrub is the guarantee.
    """
    candidates_json = json.dumps(
        [
            {
                "onet_code": c.onet_code,
                "title": c.title,
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
        "3. why_text: 1–2 sentences, plain language, specific to this user, "
        "concrete: what the work involves and which of their skills it uses.\n"
        "4. profile_dimensions: a list of exactly 2 or 3 short tags (5–8 words each) "
        "that reference the user's actual skills, archetype, or preferences. "
        "Examples: 'Builds on your Python skills', 'Fits your autonomy preference', "
        "'Matches your Deep Diver archetype'.\n"
        "5. Describe what the work involves and which of the user's skills it "
        "uses. NEVER rate, rank or grade the fit. Banned outright, in why_text "
        "and in the tags: 'strong/great/perfect/excellent/good fit', 'ideal "
        "match', 'highly suitable', 'top choice', any percentage, and any "
        "score, rating or ranking of any kind.\n\n"
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
        "Candidate Career Paths (already in the order they will be shown)\n"
        "================================================================\n"
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
    if len(suggestions_raw) != len(valid_codes):
        raise ValueError(
            f"expected {len(valid_codes)} suggestions, got {len(suggestions_raw)}"
        )

    results: list[PathSuggestion] = []
    seen_codes: set[str] = set()
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
        if code in seen_codes:
            raise ValueError(
                f"suggestions[{i}].onet_code '{code}' appears more than once"
            )
        seen_codes.add(code)

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
# The grade scrub (W-13, ruling flag 12)
# ---------------------------------------------------------------------------
#
# "No percentage, no score, and no grade word standing in for one reaches the
# screen."  The prompt above asks for that; this is what makes it true.  A
# prompt is a request to a probabilistic system, and the third browser test
# caught the request being ignored -- a Database Administrators card reading
# "...making it a strong fit for your background." -- so the rule is enforced
# after the fact by something deterministic as well as asked for before it.
#
# Deliberately a scrub and not a rejection: a narrative that grades in its last
# clause is still a good description of the work in its first, and throwing the
# whole page away (or retrying, at 10 s a batch) to remove six words would cost
# far more than it saves.  What is dropped is the smallest thing that carries
# the grade -- a trailing clause, a leading clause, or the sentence.


#: Phrases that grade the fit rather than describe the work.
#:
#: **One list, and Julie may extend it.**  Adding a phrase here tightens the
#: scrub; the system prompt's rule 5 names the same families in prose, so the
#: two are meant to be read together.  Matched case-insensitively against whole
#: words.
#:
#: What is deliberately NOT here: the bare words "match", "fit" and "suits".
#: "Matches your Deep Diver archetype" is a statement about which archetype the
#: user has, not a grade, and it is one of the tag examples rule 4 gives -- a
#: list that caught it would empty the tags of every card.
_GRADE_PHRASES: tuple[str, ...] = (
    # "a strong fit", "an excellent match", "the perfect choice"
    r"(?:strong|great|good|excellent|perfect|ideal|solid|natural|exceptional"
    r"|outstanding|close|obvious|poor|weak)\s+(?:fit|match|choice|option|candidate)",
    r"(?:fit|match)\s+scores?",
    r"(?:highly|well|perfectly|especially|uniquely)\s+(?:suitable|suited|aligned|matched)",
    r"top\s+(?:choice|pick|match|candidate|result)",
    r"best\s+(?:fit|match|choice|option)",
    r"(?:strongly|highly)\s+recommend(?:ed)?",
    r"rank(?:s|ed|ing)?\s+(?:first|second|third|top|highest|number\s+\w+)",
    r"scores?\s+(?:highly|well|high)",
    # Any number expressed as a share, and the bare symbol with it: a "%"
    # anywhere in a narrative is a score by another name.
    r"%",
    r"\d+\s*(?:out\s+of|/)\s*\d+",
    r"(?:match|fit|compatibility|alignment)\s+(?:score|rating|percentage)",
    # W-15, from the fourth user test. The verb the other way round from "well
    # aligned": "...aligning well with your technical skills."
    r"align(?:s|ed|ing)?\s+(?:well|closely|perfectly|strongly)",
    # Praise for the MOVE rather than the fit: "It's a great opportunity...",
    # "It's an excellent way to grow...". The old rule 3 asked for
    # "encouraging" prose, which invited exactly this.
    r"(?:great|excellent|fantastic|ideal|perfect|wonderful|amazing)\s+"
    r"(?:opportunity|way|step|move|path|chance|option)",
    r"(?:well|perfectly|ideally)\s+(?:positioned|placed|equipped)",
)

_GRADE_RE = re.compile(
    "|".join(r"(?:\b%s)" % phrase if phrase[0].isalpha() else r"(?:%s)" % phrase
             for phrase in _GRADE_PHRASES),
    re.IGNORECASE,
)

#: Where a graded tail can be cut off without mangling the sentence.
_CLAUSE_SEPARATORS: tuple[str, ...] = (", ", " and ", " which ", " making ", " so ")

#: Where a graded head can be cut off the front ("Strong match: uses your...").
_HEAD_SEPARATORS: tuple[str, ...] = (": ", " -- ", " — ")

#: Sentence boundary: a terminator FOLLOWED BY SPACE.  Not a bare ``[.!?]``,
#: which splits "0.82" into "0" and "82 ..." and leaves the half without the
#: word "score" in it looking innocent.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _grades(fragment: str) -> bool:
    """Does *fragment* rate, rank or grade anything?"""
    return bool(_GRADE_RE.search(fragment))


def _scrub_sentence(sentence: str) -> str:
    """One sentence with its grading removed, or "" if that is all it was."""
    stripped = sentence.strip()
    if not stripped:
        return ""
    body = stripped.rstrip(".!?")
    # Whatever punctuation was there and nothing more: a `profile_dimensions`
    # tag is a fragment with no full stop, and inventing one would edit every
    # clean tag on the page.
    terminator = stripped[len(body):]
    if not body:
        return ""

    # A graded lead-in, cut at its own punctuation: "Strong match: uses your
    # Python." -> "Uses your Python."
    for separator in _HEAD_SEPARATORS:
        head, found, tail = body.partition(separator)
        if found and tail.strip() and _grades(head) and not _grades(tail):
            body = tail.strip()
            body = body[0].upper() + body[1:]
            break

    # A graded tail, cut at the LAST clause boundary that still removes it --
    # the smallest cut that does the job.  "…data available and secure, making
    # it a strong fit for your background." has two eligible boundaries, and
    # the earlier one would throw away "and secure" for nothing.  The head must
    # come out clean either way, or there is nothing to keep and the
    # whole-sentence test below takes it.
    cut: int | None = None
    for separator in _CLAUSE_SEPARATORS:
        start = 0
        while True:
            index = body.find(separator, start)
            if index == -1:
                break
            head, tail = body[:index], body[index + len(separator):]
            if head.strip() and tail.strip() and not _grades(head) and _grades(tail):
                cut = index if cut is None else max(cut, index)
            start = index + 1
    if cut is not None:
        body = body[:cut].rstrip().rstrip(",")

    if _grades(body):
        return ""
    return body + terminator


def _scrub_grades(text: str) -> str:
    """*text* with every grading clause and grading sentence removed.

    Returns "" when the whole of it was a grade ("A great fit.", "95% overlap
    with your skills") -- the caller decides what to put there instead, because
    a ``why_text`` needs a replacement sentence and a tag needs only to be
    dropped.
    """
    if not text or not text.strip():
        return ""
    kept = [
        cleaned
        for cleaned in (_scrub_sentence(part) for part in _SENTENCE_SPLIT_RE.split(text))
        if cleaned
    ]
    return " ".join(kept).strip()


def _fallback_sentence(overlapping_skills: list[str]) -> str:
    """The sentence a card gets when the scrub left nothing.

    The SAME sentence ``intelligence_service._describe`` writes for a card the
    re-rank surfaced with no narrative -- imported rather than copied, so a
    user cannot meet two different house voices depending on which code path
    wrote their card.

    Imported inside the function on purpose. ``backend.services`` is the lower
    layer and ``solverah.services`` the upper one; a module-scope import here
    would invert that and pull Flask, the ORM and the repositories into a module
    whose own tests need none of them.  By the time this runs the caller is
    ``intelligence_service`` itself, so the module is already imported.
    """
    from solverah.services.intelligence_service import _overlap_sentence

    return _overlap_sentence(list(overlapping_skills))


def _scrub_suggestions(
    suggestions: list[PathSuggestion],
    candidates: list[ScoredPath],
) -> list[PathSuggestion]:
    """Apply :func:`_scrub_grades` to every narrative, logging once per batch."""
    skills_by_code = {c.onet_code: list(c.overlapping_skills) for c in candidates}
    scrubbed_codes: list[str] = []

    for suggestion in suggestions:
        fired = False

        why_text = _scrub_grades(suggestion.why_text)
        if why_text != suggestion.why_text:
            fired = True
        if not why_text:
            why_text = _fallback_sentence(skills_by_code.get(suggestion.onet_code, []))
        suggestion.why_text = why_text

        tags = [_scrub_grades(tag) for tag in suggestion.profile_dimensions]
        kept = [tag for tag in tags if tag]
        if kept != suggestion.profile_dimensions:
            fired = True
        suggestion.profile_dimensions = kept

        if fired:
            scrubbed_codes.append(suggestion.onet_code)

    if scrubbed_codes:
        # One line per batch, carrying the codes: a prompt regression shows up
        # as this line appearing on most cards instead of none, which is
        # visible in a log search in a way a silently-edited sentence is not.
        logger.warning(
            "path_narrative_grade_scrubbed",
            extra={
                "event": "path_narrative_grade_scrubbed",
                "codes": scrubbed_codes,
                "batch_size": len(suggestions),
            },
        )
    return suggestions


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
            # Validated first, then scrubbed: the validator's job is "did the
            # model answer the question asked", and a grade is a well-formed
            # answer that breaks a different rule (W-13, ruling flag 12).
            return _scrub_suggestions(_validate_response(data, valid_codes), candidates)
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc

    raise NarrativeGenerationError(
        f"LLM returned a malformed narrative response on both attempts. "
        f"Last error: {last_error}"
    )


#: How many candidates go in one narrator completion.
#:
#: Ten, because ten is what the page is and what the prompt was written and
#: measured against -- not a tuning knob.  W-12 measured one call of twenty at
#: 17.7-18.9 s against 10.3-11.1 s for ten, so a bigger batch buys nothing: the
#: cost is close to linear in cards and the fixed overhead is about a second.
_BATCH_SIZE: int = 10


def generate_narratives_batched(
    candidates: list[ScoredPath],
    user_context: UserContext,
) -> list[PathSuggestion]:
    """:func:`generate_narratives` over ten-card batches, in parallel, best-effort.

    W-12.  The scoring job narrates twenty candidates -- the ten it shows and ten
    held in reserve for the cards a tap promotes -- and this is how it affords
    them.

    **Threads, because the narrator is I/O-bound.**  Measured against the real
    API on three F-2 profiles: ten cards 10.35 / 11.09 / 10.35 s, two batches of
    ten on a pool 11.87 / 9.37 / 9.96 s.  Mean difference **-0.20 s** -- inside
    this narrator's own run-to-run spread.  Twenty cards in one completion costs
    17.72 / 18.58 / 18.87 s, so the parallelism is the whole saving.  Tokens go
    up honestly: ~1,520 more per job, one extra completion.

    **Best-effort per batch, and that asymmetry is deliberate.**  A batch that
    cannot be narrated contributes nothing and is logged; the others still land.
    This is the only sane rule once a job narrates cards the user is not going to
    see: failing the whole job -- and with it the ten-card shortlist, which is
    the product -- because prose for a hypothetical eleventh card came back
    malformed would trade the thing that matters for the thing that does not.
    The caller decides whether an empty result is fatal;
    :func:`intelligence_service.path_suggestions` treats the FIRST batch's
    absence as fatal, because that one is the page.

    Order is preserved across batches, so the caller can still slice the page off
    the front.  An empty *candidates* list returns empty rather than raising,
    unlike :func:`generate_narratives`: "narrate nothing" is a coherent request
    here, where the batches are derived rather than chosen.
    """
    if not candidates:
        return []

    batches = [
        candidates[start:start + _BATCH_SIZE]
        for start in range(0, len(candidates), _BATCH_SIZE)
    ]
    if len(batches) == 1:
        # One batch: no pool, no thread, and the same call the job made before
        # W-12 -- so a ten-card job is unchanged rather than merely equivalent.
        return generate_narratives(batches[0], user_context)

    with ThreadPoolExecutor(max_workers=len(batches)) as pool:
        futures = [
            pool.submit(generate_narratives, batch, user_context)
            for batch in batches
        ]
        results = []
        for index, future in enumerate(futures):
            try:
                results.append(future.result())
            except Exception:  # noqa: BLE001 -- logged, and the batch is dropped
                logger.warning(
                    "path_narrative_batch_failed",
                    extra={
                        "event": "path_narrative_batch_failed",
                        "batch": index,
                        "batch_size": len(batches[index]),
                    },
                    exc_info=True,
                )
                results.append([])

    return [suggestion for batch in results for suggestion in batch]
