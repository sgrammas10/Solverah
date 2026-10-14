"""Step 2 of the pipeline: evidence items -> per-item, per-dimension scores.

The scorer is the validated one: ``gpt-5.5-2026-04-23`` under structured outputs, on
anchors v3.1 with the ``insufficient_evidence`` abstain. The rubric text is
``causal_graph.scorer_pipeline.build_rubric_text(anchors)`` -- IMPORTED, not lifted, so
the words the model reads here are byte-identical to the words the ground-truth
harness validated. Because that function lives in another lane, its output is PINNED:
``prompts.RUBRIC_TEXT_SHA256`` is tied to ``SCORING_PROMPT_VERSION`` and
``tests/test_company_research_pipeline.py`` recomputes it, so an edit to the harness
fails a test here instead of silently changing production scoring (review F14).
``call_with_retry`` is imported for the same reason: it is what knows that a snapshot
may refuse ``temperature`` and records ``temperature_honored`` truthfully.

The anchors are a FROZEN COPY shipped inside this package (``anchors_v3_1.json``),
pinned by hash against the ``Solverah_IP`` original in the same test, so production
no longer reads the research corpus at runtime (review F14).

What differs from the harness, and why (also in ``prompts.build_scoring_instruction``):

* The scoring unit is one evidence item, not a packet. Items are batched
  (``SCORING_BATCH_SIZE`` per call) to share the rubric text, but the response schema
  has ONE OBJECT PER ITEM, each the harness's own abstaining dimension schema, so an
  item is scored independently in the schema and never pooled with its neighbours.
* No ``evidence_quotes`` per dimension: the item is the quote. The schema is the
  harness's ``_DIMENSION_SCHEMA_INSUFFICIENT`` minus that field.
* ``confidence`` is requested AND STORED on each score row (rubric gate 5) but never
  read by the aggregation: no weighting in v1 (constants.py, Julie ask 2).
* The item block carries the SPEAKER (rubric gate 2) alongside source type, scope and
  date.
* The company is SCRUBBED from the scorer's input (review F9): its name, its domain and
  the domain's bare label become ``SCRUB_REPLACEMENT`` in the item block only. The
  stored excerpt is untouched; the harness scrubbed its packets for the same reason
  (reputation is not evidence).
* ``packet_version`` on the ``scorer_run`` row is the research or posting prompt
  version that produced the items -- the CompanyLens analogue of a packet's collector
  build.

This module reads ``excerpt_internal``: it is the scorer, and the guard test grants
this package. Nothing it returns carries the text.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from sqlalchemy.orm import undefer

from causal_graph.scorer_pipeline import (
    CONFIDENCE_BAND_VALUES,
    DIMENSIONS,
    REASONING_EFFORT,
    REPO_IP,
    SCORE_BAND_VALUES,
    TEMPERATURE,
    build_rubric_text,
    call_with_retry,
    load_anchors,
    permits_insufficient_evidence,
)
from company_evidence_store import ItemScoreInput, write_item_scores
from solverah.infra import llm
from solverah.services.company_research.constants import (
    SCORING_BATCH_SIZE,
    SCRUB_MIN_LABEL_CHARS,
    SCRUB_REPLACEMENT,
)
from solverah.services.company_research.prompts import (
    SCORING_PROMPT_VERSION,
    build_scoring_instruction,
)

__all__ = [
    "ANCHORS_PATH",
    "ANCHORS_SOURCE_PATH",
    "ScoringOutcome",
    "anchors",
    "batch_schema",
    "company_scrubber",
    "rubric_text",
    "score_items",
]

logger = logging.getLogger("solverah.company_research.score")

#: The frozen copy of anchors v3.1 this package scores on. Byte-identical to
#: ANCHORS_SOURCE_PATH (pinned by hash in the tests); research-ground-truth owns the
#: source, and a new anchors version arrives here as a new copy plus a version bump.
ANCHORS_PATH: Path = Path(__file__).with_name("anchors_v3_1.json")
#: The research corpus original the copy is pinned against.
ANCHORS_SOURCE_PATH: Path = REPO_IP / "ground_truth" / "rater_app" / "anchors_v3_1_PROPOSED.json"


@lru_cache(maxsize=1)
def anchors() -> dict:
    data = load_anchors(ANCHORS_PATH)
    if not permits_insufficient_evidence(data):
        raise RuntimeError(
            "%s offers no insufficient_evidence block; the per-item scorer needs the "
            "abstain (anchors v3.1+)" % ANCHORS_PATH
        )
    return data


@lru_cache(maxsize=1)
def rubric_text() -> str:
    return build_rubric_text(anchors())


_DIMENSION_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"anyOf": [{"type": "number", "enum": SCORE_BAND_VALUES}, {"type": "null"}]},
        "confidence": {"anyOf": [{"type": "number", "enum": CONFIDENCE_BAND_VALUES},
                                 {"type": "null"}]},
    },
    "required": ["score", "confidence"],
    "additionalProperties": False,
}

_ITEM_SCHEMA = {
    "type": "object",
    "properties": {dim: _DIMENSION_SCHEMA for dim in DIMENSIONS},
    "required": list(DIMENSIONS),
    "additionalProperties": False,
}


def item_key(item_id: int) -> str:
    return "item_%d" % item_id


def batch_schema(item_ids: Sequence[int]) -> dict:
    """One required object per item, each the six-dimension abstaining schema."""
    keys = [item_key(i) for i in item_ids]
    return {
        "type": "object",
        "properties": {key: _ITEM_SCHEMA for key in keys},
        "required": keys,
        "additionalProperties": False,
    }


@dataclass(frozen=True)
class ScoringOutcome:
    scorer_run_id: int
    items: int
    scored: int
    """Non-abstaining (item, dimension) rows written."""
    abstained: int
    calls: int
    prompt_tokens: int
    completion_tokens: int
    temperature_honored: bool
    model: str


# ---------------------------------------------------------------------------
# The scrub (F9)
# ---------------------------------------------------------------------------

def company_scrubber(name: Optional[str], domain: Optional[str]) -> Callable[[str], str]:
    """A function replacing the company's name, its domain and the domain's bare label
    (``acme`` from ``acme.example``) with SCRUB_REPLACEMENT, case-insensitively, at word
    boundaries. A label shorter than SCRUB_MIN_LABEL_CHARS is not scrubbed on its own.
    Possessives follow naturally ("Acme's" -> "the company's")."""
    terms: list[str] = []
    if name and name.strip():
        terms.append(name.strip())
    if domain and domain.strip():
        d = domain.strip().lower()
        terms.append(d)
        label = d.split(".", 1)[0]
        if len(label) >= SCRUB_MIN_LABEL_CHARS:
            terms.append(label)
    if not terms:
        return lambda text: text
    # Longest first so "Acme Corp" is replaced before "acme" would split it.
    terms.sort(key=len, reverse=True)
    pattern = re.compile(
        r"(?<![A-Za-z0-9])(?:%s)(?![A-Za-z0-9])" % "|".join(re.escape(t) for t in terms),
        re.IGNORECASE,
    )
    return lambda text: pattern.sub(SCRUB_REPLACEMENT, text or "")


def _item_block(item, scrub: Callable[[str], str]) -> str:
    date = item.published_at.isoformat() if item.published_at else "undated"
    label = " (%s)" % scrub(item.scope_label) if item.scope_label else ""
    speaker = scrub(item.speaker) if item.speaker else "not recorded"
    return (
        f"[{item_key(item.id)}] source type: {item.source_type} | scope: {item.scope}{label} "
        f"| speaker: {speaker} | date: {date}\n\"{scrub(item.excerpt_internal)}\""
    )


def _parse_batch(parsed: dict, items) -> list:
    rows = []
    for item in items:
        answer = parsed.get(item_key(item.id))
        if not isinstance(answer, dict):
            raise ValueError("scorer answer is missing %s" % item_key(item.id))
        for dim in DIMENSIONS:
            cell = answer.get(dim)
            if not isinstance(cell, dict):
                raise ValueError("scorer answer for %s lacks %s" % (item_key(item.id), dim))
            score = cell.get("score")
            if score is None:
                rows.append(ItemScoreInput(item.id, dim, None, True))
                continue
            if float(score) not in SCORE_BAND_VALUES:
                raise ValueError("%s/%s: %r is not a band value" % (item_key(item.id), dim, score))
            confidence = cell.get("confidence")
            if confidence is not None:
                if float(confidence) not in CONFIDENCE_BAND_VALUES:
                    raise ValueError(
                        "%s/%s: %r is not a confidence band" % (item_key(item.id), dim, confidence)
                    )
                confidence = float(confidence)
            rows.append(ItemScoreInput(item.id, dim, float(score), False, confidence))
    return rows


def score_items(
    db,
    item_ids: Sequence[int],
    *,
    packet_version: str,
    client: Any = None,
    model: Optional[str] = None,
    notes: Optional[str] = None,
) -> ScoringOutcome:
    """Score every item in *item_ids* on all six dimensions and write the rows under
    one new ``scorer_run``. Returns what was written and what it cost in tokens.

    *packet_version* names the prompt that produced the items (research or posting
    extraction). Raises ``LLMProviderUnavailable`` before any call when no key is set.
    """
    from model import Company, CompanyEvidenceItem, ScorerRun

    ids = [int(i) for i in item_ids]
    model = model or llm.default_scorer_model()
    if client is None:
        client = llm.get_scorer_client()

    items = []
    if ids:
        by_id = {
            row.id: row
            for row in db.session.query(CompanyEvidenceItem)
            .options(undefer(CompanyEvidenceItem.excerpt_internal))
            .filter(CompanyEvidenceItem.id.in_(ids))
            .all()
        }
        missing = [i for i in ids if i not in by_id]
        if missing:
            raise ValueError("evidence items do not exist: %r" % (missing,))
        items = [by_id[i] for i in ids]

    scrubbers: dict = {}
    for item in items:
        if item.company_id not in scrubbers:
            company = db.session.get(Company, item.company_id)
            scrubbers[item.company_id] = company_scrubber(
                company.name if company else None, company.domain if company else None
            )

    rubric = rubric_text()
    all_rows: list = []
    honored = True
    calls = prompt_tokens = completion_tokens = 0

    for start in range(0, len(items), SCORING_BATCH_SIZE):
        batch = items[start:start + SCORING_BATCH_SIZE]
        keys = [item_key(i.id) for i in batch]
        body = "\n\n".join(_item_block(i, scrubbers[i.company_id]) for i in batch)
        instruction = build_scoring_instruction(
            keys, DIMENSIONS, SCORE_BAND_VALUES, CONFIDENCE_BAND_VALUES,
            scrub_replacement=SCRUB_REPLACEMENT,
        )
        messages = [{"role": "user", "content":
                     f"RUBRIC:\n{rubric}\n\nEVIDENCE ITEMS:\n{body}\n\n{instruction}"}]
        response, this_honored = call_with_retry(
            client, messages, model, TEMPERATURE, REASONING_EFFORT,
            schema=batch_schema([i.id for i in batch]),
        )
        honored = honored and this_honored
        calls += 1
        usage = getattr(response, "usage", None)
        prompt_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
        parsed = json.loads(response.choices[0].message.content)
        all_rows.extend(_parse_batch(parsed, batch))

    run = ScorerRun(
        model=model,
        temperature=TEMPERATURE if honored else None,
        temperature_honored=honored,
        reasoning_effort=REASONING_EFFORT,
        rubric_version=anchors()["rubric_version"],
        packet_version=packet_version,
        notes=json.dumps({
            "pipeline": "companylens",
            "scoring_prompt_version": SCORING_PROMPT_VERSION,
            "items": len(items),
            "calls": calls,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            **({"note": notes} if notes else {}),
        }),
    )
    db.session.add(run)
    db.session.commit()

    written = write_item_scores(db, all_rows, scorer_run_id=run.id) if all_rows else 0
    abstained = sum(1 for r in all_rows if r.abstained)
    logger.info(
        "company_items_scored",
        extra={
            "event": "company_items_scored",
            "scorer_run_id": run.id,
            "items": len(items),
            "rows": written,
            "abstained": abstained,
            "calls": calls,
            "temperature_honored": honored,
        },
    )
    return ScoringOutcome(
        scorer_run_id=run.id,
        items=len(items),
        scored=written - abstained,
        abstained=abstained,
        calls=calls,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        temperature_honored=honored,
        model=model,
    )
