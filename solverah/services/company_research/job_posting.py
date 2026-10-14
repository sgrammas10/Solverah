"""A user's pasted job posting -> role-scope evidence items, through the SCORER client.

The posting is user content. It never goes to the research client (Anthropic, whose
contract is company name and public URLs only); extraction runs on the OpenAI scorer
client, an existing vendor, under structured outputs. ``tests/test_company_research_pipeline.py``
proves it: the research fake records zero requests across a posting job, and an AST
check pins that this module imports nothing from ``solverah.infra.llm.research``.

Every excerpt the model returns is verified by CONTAINMENT in the pasted text (the
whole source is in hand, so this verifier is exact where the research one is
citation-based), then the paraphrase gate runs against the excerpt AND the whole
posting (a paraphrase that copies a different sentence of the posting is still the
employer's words on a page). Items that fail either are dropped and counted. The items are written under the posting (``source_type user_pasted_posting``,
scope ``role``), scored by the same per-item scorer, and aggregated into records
private to the posting (``job_posting_id`` set).
"""

from __future__ import annotations

import datetime
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

from causal_graph.scorer_pipeline import REASONING_EFFORT, TEMPERATURE, call_with_retry
from company_evidence_store import EvidenceItemInput
from solverah.infra import llm
from solverah.services.company_research import textcheck
from solverah.services.company_research.prompts import (
    POSTING_EXTRACT_PROMPT_VERSION,
    build_posting_extraction_prompt,
)

__all__ = ["EXTRACTION_SCHEMA", "PostingExtraction", "extract_posting_items"]

logger = logging.getLogger("solverah.company_research.posting")

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "maxItems": 10,
            "items": {
                "type": "object",
                "properties": {
                    "excerpt": {"type": "string"},
                    "paraphrase": {"type": "string"},
                },
                "required": ["excerpt", "paraphrase"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["items"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class PostingExtraction:
    items: tuple
    candidates: int
    dropped_unverified: int
    dropped_paraphrase: int
    prompt_tokens: int
    completion_tokens: int
    model: str
    prompt_version: str = POSTING_EXTRACT_PROMPT_VERSION


def extract_posting_items(
    posting_text: str,
    *,
    title: Optional[str] = None,
    client: Any = None,
    model: Optional[str] = None,
    today: Optional[datetime.date] = None,
) -> PostingExtraction:
    """Cut *posting_text* into verified, paraphrased role-scope items.

    Every item is dated *today* (the paste date): a posting the user is weighing is
    current by construction, and the aggregation's recency window reads
    ``published_at``, so an undated paste would be `unknown` on every trait however
    much it said.
    """
    if not posting_text or not posting_text.strip():
        raise ValueError("a job posting needs its text")
    model = model or llm.default_scorer_model()
    if client is None:
        client = llm.get_scorer_client()
    today = today or datetime.date.today()

    messages = [{"role": "user", "content": build_posting_extraction_prompt(posting_text, title)}]
    response, _honored = call_with_retry(
        client, messages, model, TEMPERATURE, REASONING_EFFORT, schema=EXTRACTION_SCHEMA
    )
    usage = getattr(response, "usage", None)
    parsed = json.loads(response.choices[0].message.content)
    raw_items = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(raw_items, list):
        raise ValueError("posting extraction answer has no items list")

    kept: list = []
    unverified = bad_paraphrase = 0
    for raw in raw_items:
        excerpt = raw.get("excerpt") if isinstance(raw, dict) else None
        paraphrase = raw.get("paraphrase") if isinstance(raw, dict) else None
        if not isinstance(excerpt, str) or not textcheck.text_contains(posting_text, excerpt):
            unverified += 1
            continue
        if not isinstance(paraphrase, str) or not textcheck.paraphrase_passes_gate(
            excerpt, paraphrase, (posting_text,)
        ):
            bad_paraphrase += 1
            continue
        kept.append(EvidenceItemInput(
            "role", "user_pasted_posting", excerpt.strip(), paraphrase.strip(),
            (title.strip() or None) if title else None, None, today,
        ))

    logger.info(
        "posting_items_extracted",
        extra={
            "event": "posting_items_extracted",
            "candidates": len(raw_items),
            "kept": len(kept),
            "dropped_unverified": unverified,
            "dropped_paraphrase": bad_paraphrase,
        },
    )
    return PostingExtraction(
        items=tuple(kept),
        candidates=len(raw_items),
        dropped_unverified=unverified,
        dropped_paraphrase=bad_paraphrase,
        prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        model=model,
    )
