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

import collections
import json
import logging
import os
import re
import threading
from concurrent.futures import FIRST_COMPLETED, Future, wait
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

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
    #: W-16. True when the grade scrub left nothing of the model's sentence and
    #: ``why_text`` is the house fallback instead. Such a card may be SHOWN, but
    #: it must never be STORED as a narrative: a stored row is served as prose on
    #: every later load, and a fallback sentence is not prose.
    is_fallback: bool = False


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


#: The system message. A module constant rather than a string built inside
#: :func:`_build_prompt` so that :func:`narrative_fingerprint` can hash the very
#: same text: an edit to the rules changes what the model is asked, so it must
#: change every stored narrative's key too (W-16).
_SYSTEM_PROMPT: str = (
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


def _candidate_entry(candidate: ScoredPath) -> dict:
    """What the prompt says about one card -- and nothing else does (W-13, W-16)."""
    return {
        "onet_code": candidate.onet_code,
        "title": candidate.title,
        "overlapping_skills": candidate.overlapping_skills,
    }


def _profile_block(ctx: UserContext) -> str:
    """The "User Profile" and "Preferences" sections of the user message.

    Everything the prompt says about the PERSON, rendered exactly as the model
    reads it. Split out of :func:`_build_prompt` for W-16, so the prompt and the
    stored-narrative key are built from one function and cannot drift apart.
    """
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

    return (
        "User Profile\n"
        "============\n"
        f"Career status:        {ctx.career_status}\n"
        f"WorkPulse archetype:  {ctx.archetype}\n"
        f"Top skills:           {top_skills_str}\n"
        f"Management preferences:\n{management_str}\n\n"
        f"{prefs_section}"
    )


def narrative_fingerprint(candidate: ScoredPath, ctx: UserContext) -> str:
    """The key a stored narrative for *candidate* is filed under (W-16).

    A digest of exactly what :func:`_build_prompt` feeds the model about this
    one card and this one person, built from the SAME helpers the prompt uses:

    * the system message (:data:`_SYSTEM_PROMPT`) -- a rule edit re-keys all;
    * :func:`_profile_block` -- career status, WorkPulse archetype, top skills
      (in prompt order, which is profile order: the model reads them in that
      order), the manager-match archetype and dimension scores as rendered to
      two decimals, and the move/seniority/priority labels;
    * :func:`_candidate_entry` -- onet_code, title and overlapping skills.

    NOT in it, deliberately: the path-wants answers and the feedback taps. They
    reorder the list but are never shown to the narrator, so a narrative written
    before a wants save is still the narrative the narrator would write after
    it -- which is the whole point of storing them. Nor the OTHER cards in the
    same batch: they are in the prompt, but a per-card key cannot depend on the
    batch a card happened to share, and rule 1 asks for each card on its own.
    ``tests/test_path_narrative.py`` pins both halves.
    """
    import hashlib

    canonical = json.dumps(
        {
            "system": _SYSTEM_PROMPT,
            "profile": _profile_block(ctx),
            "candidate": _candidate_entry(candidate),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
        [_candidate_entry(c) for c in candidates],
        indent=2,
    )

    user_msg = (
        f"{_profile_block(ctx)}"
        "Candidate Career Paths (already in the order they will be shown)\n"
        "================================================================\n"
        f"{candidates_json}\n\n"
        "Write a why_text and profile_dimensions for every candidate above, "
        "in the same order, and return the JSON object."
    )

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
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
            # W-16: shown, never stored -- see `PathSuggestion.is_fallback`.
            suggestion.is_fallback = True
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
#: **Five (W-16), down from ten.**  The cost of one completion is close to linear
#: in cards (W-12: twenty in one call 17.7-18.9 s, ten 10.3-11.1 s), so with the
#: batches on threads the job waits for the slowest BATCH, and halving the batch
#: roughly halves the wait.  Measured on twenty real scored cards per profile,
#: three profiles x three runs, interleaved, real API (W-16 note):
#:
#:     2 x 10   mean 8.22 s  (6.60 - 13.23)   3,295 - 3,959 tokens
#:     4 x  5   mean 4.36 s  (4.09 -  4.75)   4,223 - 4,849 tokens
#:
#: The price is the prompt header repeated twice more: about +910 tokens a job
#: (mean 3,546 -> 4,457, +26 %), ~840 of them prompt tokens, which gpt-4o-mini bills at a quarter
#: of the completion rate.  Below five the fixed ~1 s per call starts to
#: dominate (one card is 1.4 s, five 3.1-3.7 s) and the header repeats again.
_BATCH_SIZE: int = 5

#: W-17. How many cards at the top of the page are narrated one card per call,
#: ahead of everything else.
#:
#: Three because ``PathSuggestionList`` shows three before "Show more": these are
#: the only sentences a user is looking at in the first seconds. One card is a
#: ~1.4 s completion (W-12), against 3.1-3.7 s for five, so three parallel
#: one-card calls put the visible sentences on screen in about the time of one.
_HEAD_SIZE: int = 3

#: W-17. Narrator calls in flight at once, across the whole process.
#:
#: W-16 capped it indirectly: four narrations (``NARRATION_WORKERS``) x four
#: batches each (a per-narration pool) = sixteen sockets. It is now one shared
#: pool, so the bound is on what actually costs something -- open provider calls
#: -- and not on the number of users waiting.
#:
#: Thirty-two, measured (W-17 note): ten users loading at once on the capped
#: 8-thread server, real OpenAI, "first three sentences present" p50 / p95:
#:
#:     W-16 (4 narrations x 4 batches)      8.35 / 12.58 s   (rerun 9.49 / 14.37)
#:     16 threads, no tail limit            3.98 /  5.60 s
#:     24 threads, tail limit 12            3.27 /  4.39 s
#:     32 threads, tail limit 16            2.69 /  3.94 s   (rerun 2.60 / 3.81)
#:
#: I/O-bound threads that hold no database connection; the provider calls
#: themselves are the cost, and the tail limit keeps the bulk of them at W-16's
#: sixteen.
_CALL_WORKERS: int = 32

#: W-17. The most TAIL calls in flight at once -- the rest of the pool is kept
#: for heads.
#:
#: A priority queue alone is not enough, and the first measurement said so: the
#: pool does not pre-empt, so when ten users arrive within a second the first few
#: users' tails take every thread (3.5 s each) and the later users' heads, first
#: in the queue, still wait for them. Capping the tail keeps
#: ``_CALL_WORKERS - _TAIL_LIMIT`` threads that only a head can take, so a head
#: waits at most for other heads (~1.4 s each), never for somebody's tail.
#: Sixteen is W-16's whole ceiling, so bulk narration is no more parallel than it
#: was; only the visible three got extra room.
_TAIL_LIMIT: int = 16

#: W-17. Queue priorities on the shared pool: every user's visible three go
#: ahead of anybody's tail.
_HEAD_PRIORITY: int = 0
_TAIL_PRIORITY: int = 1


class _PriorityPool:
    """A fixed set of daemon threads draining per-priority queues (W-17).

    ``concurrent.futures.ThreadPoolExecutor`` is FIFO, and FIFO is the fairness
    bug: user B's first three would queue behind user A's seventeen-card tail.
    Here a free thread takes the lowest priority number that has work waiting
    AND is under its limit (*limits*, ``{priority: max in flight}``; absent means
    no limit beyond the pool itself). Equal priorities run in submission order.

    Started lazily on the first submit, so importing this module (a CLI, a
    migration) starts no threads. Daemon threads, because nothing here must
    outlive the process: a narration cut off by a shutdown is covered by
    ``intelligence_service.NARRATION_DEADLINE`` like any other dead worker.
    """

    def __init__(self, workers: int, name: str, limits: Optional[dict[int, int]] = None) -> None:
        self._workers = workers
        self._name = name
        self._limits = dict(limits or {})
        self._queues: dict[int, collections.deque] = {}
        self._running: collections.Counter = collections.Counter()
        self._cond = threading.Condition()
        self._threads: list[threading.Thread] = []

    def submit(self, priority: int, fn: Callable[..., Any], *args: Any) -> Future:
        future: Future = Future()
        with self._cond:
            if not self._threads:
                self._start_locked()
            self._queues.setdefault(priority, collections.deque()).append((future, fn, args))
            self._cond.notify()
        return future

    def _start_locked(self) -> None:
        for index in range(self._workers):
            thread = threading.Thread(
                target=self._work, name="%s-%d" % (self._name, index), daemon=True
            )
            thread.start()
            self._threads.append(thread)

    def _take_locked(self) -> Optional[tuple]:
        for priority in sorted(self._queues):
            waiting = self._queues[priority]
            limit = self._limits.get(priority)
            if waiting and (limit is None or self._running[priority] < limit):
                self._running[priority] += 1
                return (priority,) + waiting.popleft()
        return None

    def _work(self) -> None:
        while True:
            with self._cond:
                item = self._take_locked()
                while item is None:
                    self._cond.wait()
                    item = self._take_locked()
            priority, future, fn, args = item
            try:
                if future.set_running_or_notify_cancel():
                    try:
                        future.set_result(fn(*args))
                    except BaseException as exc:  # noqa: BLE001 -- handed to the waiter
                        future.set_exception(exc)
            finally:
                with self._cond:
                    self._running[priority] -= 1
                    # A capped priority may be runnable again: wake every
                    # waiter, not one, or the one woken may find only work it
                    # is still not allowed to take while another could.
                    self._cond.notify_all()


_call_pool = _PriorityPool(
    _CALL_WORKERS, "path-narrator", limits={_TAIL_PRIORITY: _TAIL_LIMIT}
)


def _narrate(batch: list[ScoredPath], user_context: UserContext) -> list[PathSuggestion]:
    """One completion. Looked up at call time, so a test double of
    :func:`generate_narratives` is what the pool runs."""
    return generate_narratives(batch, user_context)


def narrate_page_first(
    head: list[ScoredPath],
    tail: list[ScoredPath],
    user_context: UserContext,
    on_landed: Optional[Callable[[list[PathSuggestion]], None]] = None,
) -> list[PathSuggestion]:
    """Narrate *head* one card per call, then *tail* in batches of five (W-17).

    W-16 narrated all twenty cards as four batches of five, so the three cards a
    user can see waited for the batch they happened to share: ~3.5-4.5 s. Now:

    * each *head* card (the caller passes the page's first three that have no
      stored sentence) is its own completion at head priority -- three calls in
      parallel, ~1.4 s;
    * *tail* goes out in :data:`_BATCH_SIZE` batches at tail priority, in order,
      so the rest of the page is written before the reserve.

    All on the process-wide :data:`_call_pool`, where every user's head goes
    ahead of anybody's tail (see :data:`_HEAD_PRIORITY`).

    *on_landed* is called with each completion's suggestions **as it lands, on
    the calling thread** -- the caller's thread has the app context and the
    database session, the pool's threads have neither and never need them. It
    is how the page gets its first three sentences before the tail is done. An
    exception from it is logged and does not stop the other completions.

    **Best-effort per call**, as W-12's batching was: a call that fails (after
    :func:`generate_narratives`' own retry) contributes nothing and is logged;
    the caller's fallback covers its cards. Returns every suggestion that was
    written, in *head* + *tail* order. Nothing to narrate returns [] without
    touching the pool.
    """
    calls: list[tuple[int, list[ScoredPath]]] = [
        (_HEAD_PRIORITY, [card]) for card in head
    ] + [
        (_TAIL_PRIORITY, tail[start:start + _BATCH_SIZE])
        for start in range(0, len(tail), _BATCH_SIZE)
    ]
    if not calls:
        return []

    futures = {
        _call_pool.submit(priority, _narrate, batch, user_context): index
        for index, (priority, batch) in enumerate(calls)
    }
    written: dict[int, list[PathSuggestion]] = {}
    outstanding = set(futures)
    while outstanding:
        done, outstanding = wait(outstanding, return_when=FIRST_COMPLETED)
        for future in done:
            index = futures[future]
            try:
                suggestions = future.result()
            except Exception:  # noqa: BLE001 -- logged, and the call is dropped
                logger.warning(
                    "path_narrative_batch_failed",
                    extra={
                        "event": "path_narrative_batch_failed",
                        "batch": index,
                        "batch_size": len(calls[index][1]),
                        "head": calls[index][0] == _HEAD_PRIORITY,
                    },
                    exc_info=True,
                )
                continue
            written[index] = suggestions
            if on_landed is not None:
                try:
                    on_landed(suggestions)
                except Exception:  # noqa: BLE001 -- the other calls still land
                    logger.exception("path_narrative_landing_failed")

    return [suggestion for index in sorted(written) for suggestion in written[index]]
