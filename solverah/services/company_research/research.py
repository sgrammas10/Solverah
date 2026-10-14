"""Step 1 of the pipeline: a company name -> verified evidence items.

One research turn on Anthropic (``solverah.infra.llm.research.run_research_call``),
parsed, then filtered by two gates before anything is written:

1. **Excerpt verification** (review F1). An item is kept only when ALL of these hold:

   (a) the citations used come from the item's OWN source -- a
       ``web_search_result_location`` citation matches by URL, a ``char_location``
       citation matches by the URL the infra resolved from its ``document_index``
       (title match only as the fallback for an unresolved one), and the
       ``ResearchSource`` with that URL must have been fetched;
   (b) those citations cover at least ``VERIFY_MIN_COVERAGE`` of the excerpt's words
       (``textcheck.verify_excerpt``);
   (c) the item's URL was fetched or cited, not merely listed in search results;
   (d) every quotation mark in the excerpt appears in the matching cited text.

   Items that fail are DROPPED and counted by reason. This is the production stand-in
   for v4.11's "confirm every excerpt on a rendered copy of the page": the model cannot
   invent a quotation the API did not see it quote, and cannot wrap a real fragment in
   an invented sentence. Which citation kind verified each kept item is recorded.
2. **The paraphrase gate** (``textcheck.paraphrase_gate``, review F13): no quotation
   marks, no over-long shared run, no phrase-level copying, checked against the excerpt
   and every other citation from the same URL. Rejection, not regeneration: a second
   call for a handful of paraphrases is cost and surface the first live runs do not
   need; if the drop rate is high the fix is the prompt.

Dates (review F8): a ``careers_page`` item dated on its retrieval day is access-dated
(no publication date is claimed); a ``job_posting`` item whose URL was FETCHED was
verified open and is dated at retrieval, as a pasted posting is.

Speakers (review F4): an ``employee_review`` whose speaker marks it as the employer's
reply is re-tagged ``careers_page`` (the system prompt's own rule) so the stored
source type is honest; the speaker is stored with the item.

The run card (review F2): ``ResearchOutcome.diagnostics`` is an INTERNAL record of
what happened -- counts, citation kinds, yield per source type against v4.11's
minimums, the raw text and the citations. It holds verbatim third-party text, so it is
written to ``company_research_run.diagnostics_internal`` and never serialized.
``ResearchOutcome.unverified_run`` says when the service must FAIL the run
(``research_unverified``): candidates but nothing kept, or no citations at all.

Contract: company name and public URLs only. ``run_research`` takes a name and a
domain and nothing else; no user content can reach this module.

Cost is recorded on failure too: every error raised out of ``run_research`` is a
``ResearchCallError`` (or subclass) carrying ``.usage``, including this module's own
``ResearchParseError`` for a turn that completed but produced no parseable record
(which also carries the run card, so the raw text of an unparseable turn is kept).
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from company_evidence_store import EvidenceItemInput
from solverah.infra.llm.research import (
    ResearchCallError,
    ResearchResult,
    ResearchUsage,
    estimate_research_cost_usd,
    run_research_call,
)
from solverah.services.company_research import textcheck
from solverah.services.company_research.constants import (
    JOB_POSTING_MIN_DISTINCT_POSTINGS,
    RESEARCH_MAX_FETCHES,
    RESEARCH_MAX_SEARCHES,
    RESEARCH_MAX_TOKENS,
    SOURCE_YIELD_TARGETS,
)
from solverah.services.company_research.prompts import (
    RESEARCH_PROMPT_VERSION,
    RESEARCH_SYSTEM,
    SOURCE_TYPE_GUIDE,
    build_research_prompt,
)

__all__ = [
    "ResearchOutcome",
    "ResearchParseError",
    "build_run_card",
    "normalize_domain",
    "parse_record",
    "run_research",
]

logger = logging.getLogger("solverah.company_research.research")

_RESEARCH_SOURCE_TYPES = tuple(key for key, _ in SOURCE_TYPE_GUIDE)
_SCOPES = ("company", "division", "location", "role")

#: A speaker that says the item is the employer's reply on a review site. Stricter than
#: constants.EMPLOYER_SPEAKER_PATTERN (which the aggregation uses to mark any company
#: voice): this one re-TAGS the item, so it must not catch a job title.
_EMPLOYER_REPLY_RE = re.compile(
    r"^\s*employer\b|employer(?:'s)?\s+(?:response|reply)|"
    r"(?:response|reply)\s+from\s+(?:the\s+)?(?:employer|company|management)",
    re.IGNORECASE,
)


class ResearchParseError(ResearchCallError):
    """The turn finished but its text held no parseable record. Carries the usage
    billed, like every other research failure, and the run card (raw text and
    citations) so the engineer can see what came back."""

    def __init__(self, message: str, usage: ResearchUsage, diagnostics: Optional[dict] = None):
        super().__init__(message, usage)
        self.diagnostics = diagnostics


@dataclass(frozen=True)
class ResearchOutcome:
    """What one research turn produced, after the gates."""

    items: tuple
    """``EvidenceItemInput`` rows ready for ``company_evidence_store.write_items``."""
    domain: Optional[str]
    headcount: Optional[int]
    headcount_as_of: Optional[datetime.date]
    headcount_source: Optional[str]
    scope_declaration: Optional[str]
    usage: ResearchUsage
    cost_usd: Optional[float]
    model: str
    served_model: str
    fell_back: bool
    candidates: int
    """Items the model proposed, before the gates."""
    dropped_unverified: int
    dropped_paraphrase: int
    dropped_invalid: int
    """Items with a bad vocabulary word, no URL, or an empty excerpt."""
    citations: int
    """Citations the API attached to the turn's text, of any kind."""
    diagnostics: dict
    """The INTERNAL run card. Holds verbatim text; see the module docstring."""
    prompt_version: str = RESEARCH_PROMPT_VERSION
    item_meta: tuple = field(default_factory=tuple)
    """Per kept item: ``verified_by``, ``coverage``, ``access_dated``, ``verified_open``."""

    @property
    def unverified_run(self) -> bool:
        """The run must FAIL as ``research_unverified``: the model proposed items and
        none survived verification, or the turn carried no citation at all (the API
        never saw it quote anything -- usually a prompt-shape problem)."""
        return (self.candidates > 0 and not self.items) or self.citations == 0


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_DECODER = json.JSONDecoder()


def _extract_json_object(text: str) -> Optional[dict]:
    """The LAST JSON object in *text* that carries an ``items`` list, wherever it sits
    (inside a code fence, after narration, before a trailing remark). Scans each '{'
    from the end and decodes one object from it, so earlier braces in prose cannot
    hide the record and trailing text cannot break it."""
    if not text:
        return None
    start = len(text)
    while True:
        start = text.rfind("{", 0, start)
        if start == -1:
            return None
        try:
            parsed, _end = _DECODER.raw_decode(text, start)
        except ValueError:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("items"), list):
            return parsed


def parse_record(text: str) -> dict:
    """The record object out of the model's text, or ``ValueError``."""
    parsed = _extract_json_object(text)
    if parsed is None:
        raise ValueError("no JSON record with an 'items' list in the research text")
    return parsed


def _parse_date(value: Any) -> Optional[datetime.date]:
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", value)
    if m is None:
        # "accessed 2026-10-13" and similar labelled forms
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
        if m is None:
            return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _parse_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 1 else None
    if isinstance(value, float) and value.is_integer():
        return int(value) if value >= 1 else None
    if isinstance(value, str):
        digits = re.sub(r"[^\d]", "", value)
        if digits:
            n = int(digits)
            return n if n >= 1 else None
    return None


def normalize_domain(value: Any) -> Optional[str]:
    """'https://www.Acme.com/careers' -> 'acme.com'; None for anything that is not a
    hostname."""
    if not value or not isinstance(value, str):
        return None
    v = value.strip().lower()
    v = re.sub(r"^[a-z]+://", "", v)
    v = v.split("/", 1)[0].split("?", 1)[0]
    if v.startswith("www."):
        v = v[4:]
    if not v or "." not in v or " " in v:
        return None
    return v


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "y", "1")
    return bool(value)


def _clean_str(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


# ---------------------------------------------------------------------------
# The gates
# ---------------------------------------------------------------------------

def _citations_for(url: str, source, result: ResearchResult) -> list:
    """The citations from the item's own source (rule (a)): search citations by URL,
    fetch citations by URL too, with a title match as the fallback.

    Since 2026-10-13 the infra resolves a ``char_location`` citation's ``url`` through
    its ``document_index`` against the fetched documents (llm-features fix in
    ``solverah.infra.llm.research``), so a page listed by a search under one title and
    fetched under another is matched by its URL and no longer drops as
    ``no_citation_from_source``. The title match stays ONLY for a citation whose URL the
    infra could not resolve (``url`` is None): there it is the pre-fix rule, unchanged.
    A citation that resolved to a DIFFERENT URL never falls back to the title -- a
    title is not evidence that two pages are one page.
    """
    matching = []
    for cite in result.citations:
        if not cite.cited_text:
            continue
        if cite.kind == "web_search_result_location":
            if cite.url == url:
                matching.append(cite)
        elif cite.kind == "char_location":
            if source is None or not source.fetched:
                continue
            if cite.url is not None:
                if cite.url == url:
                    matching.append(cite)
            elif cite.title and cite.title == source.title:
                matching.append(cite)
    return matching


def _build_items(record: dict, result: ResearchResult, retrieved_at: datetime.datetime):
    sources_by_url = {s.url: s for s in result.sources if s.url}
    retrieved_day = retrieved_at.date()

    kept: list = []
    meta: list = []
    reasons: dict = {}
    retagged = 0

    def drop(reason: str) -> None:
        reasons[reason] = reasons.get(reason, 0) + 1

    for raw in record.get("items") or []:
        if not isinstance(raw, dict):
            drop("invalid")
            continue
        source_type = str(raw.get("source_type") or "").strip()
        scope = str(raw.get("scope") or "").strip()
        excerpt = raw.get("excerpt")
        paraphrase = raw.get("paraphrase")
        url = raw.get("url")
        if (
            source_type not in _RESEARCH_SOURCE_TYPES
            or scope not in _SCOPES
            or not isinstance(excerpt, str) or not excerpt.strip()
            or not isinstance(url, str) or not url.strip()
        ):
            drop("invalid")
            continue
        url = url.strip()

        # (c) the URL was fetched or cited, not merely listed.
        source = sources_by_url.get(url)
        if source is None:
            drop("url_not_seen")
            continue
        if not (source.fetched or source.cited):
            drop("url_only_listed")
            continue
        # (a) citations from this source only; (b) + (d) in verify_excerpt.
        matching = _citations_for(url, source, result)
        if not matching:
            drop("no_citation_from_source")
            continue
        cited_texts = [c.cited_text for c in matching]
        verification = textcheck.verify_excerpt(excerpt, cited_texts)
        if not verification.verified:
            drop(verification.reason)
            continue

        gate = (
            textcheck.paraphrase_gate(excerpt, paraphrase, cited_texts)
            if isinstance(paraphrase, str) else "empty"
        )
        if gate is not None:
            drop("paraphrase_" + gate)
            continue

        scope_label = _clean_str(raw.get("scope_label"))
        if scope == "company":
            scope_label = None
        speaker = _clean_str(raw.get("speaker"))
        if source_type == "employee_review" and speaker and _EMPLOYER_REPLY_RE.search(speaker):
            source_type = "careers_page"
            retagged += 1

        model_date = _parse_date(raw.get("date"))
        access_dated = _truthy(raw.get("date_is_access_date")) or (
            source_type == "careers_page" and model_date == retrieved_day
        )
        verified_open = source_type == "job_posting" and source.fetched
        if verified_open:
            published_at: Optional[datetime.date] = retrieved_day
        else:
            published_at = None if access_dated else model_date

        kinds = {c.kind for c in matching}
        verified_by = "both" if len(kinds) > 1 else next(iter(kinds))

        kept.append(EvidenceItemInput(
            scope, source_type, excerpt.strip(), paraphrase.strip(),
            scope_label, url, published_at, retrieved_at, speaker,
        ))
        meta.append({
            "url": url,
            "source_type": source_type,
            "scope": scope,
            "verified_by": verified_by,
            "coverage": round(verification.coverage, 3),
            "published_at": published_at.isoformat() if published_at else None,
            "access_dated": access_dated,
            "verified_open": verified_open,
        })

    return kept, meta, reasons, retagged


_INVALID = ("invalid",)
_UNVERIFIED = ("url_not_seen", "url_only_listed", "no_citation_from_source",
               "too_short", "coverage", "quote_marks", "no_citation")


def _yield(kept: list) -> dict:
    """Kept items per source type against Collector v4.11's minimums."""
    out: dict = {}
    for source_type, (minimum, maximum) in SOURCE_YIELD_TARGETS.items():
        mine = [i for i in kept if i.source_type == source_type]
        entry = {"kept": len(mine), "minimum": minimum, "maximum": maximum,
                 "met": len(mine) >= minimum}
        if source_type == "job_posting":
            distinct = len({i.source_url for i in mine if i.source_url})
            entry["distinct_postings"] = distinct
            entry["min_distinct_postings"] = JOB_POSTING_MIN_DISTINCT_POSTINGS
            entry["met"] = entry["met"] and distinct >= JOB_POSTING_MIN_DISTINCT_POSTINGS
        out[source_type] = entry
    return out


#: The domains neither server tool may use, comma-separated, read at call time. Empty
#: means no filter. The attorney decides the real list (review-site collection awaits
#: that review, 2026-10-13); this is the plumbing, and the list used is on the run card.
BLOCKED_DOMAINS_VAR = "SOLVERAH_RESEARCH_BLOCKED_DOMAINS"


def blocked_domains() -> list[str]:
    """``SOLVERAH_RESEARCH_BLOCKED_DOMAINS`` as a de-duplicated list of bare
    hostnames (lower-cased, whitespace and an ``https://`` prefix tolerated)."""
    raw = os.environ.get(BLOCKED_DOMAINS_VAR) or ""
    seen: dict = {}
    for part in raw.split(","):
        host = part.strip().lower()
        host = re.sub(r"^[a-z]+://", "", host).strip("/").strip()
        if host:
            seen.setdefault(host, None)
    return list(seen)


def build_run_card(result: ResearchResult, *, record: Optional[dict] = None,
                   kept: Optional[list] = None, meta: Optional[list] = None,
                   reasons: Optional[dict] = None, retagged: int = 0,
                   blocked_domains: Optional[list] = None) -> dict:
    """The INTERNAL run card. With only *result* it describes an unparseable turn."""
    reasons = reasons or {}
    kept = kept or []
    by_kind: dict = {}
    for cite in result.citations:
        by_kind[cite.kind or "unknown"] = by_kind.get(cite.kind or "unknown", 0) + 1
    candidates = len(record.get("items") or []) if record else 0
    totals = result.usage.totals
    card: dict = {
        "prompt_version": RESEARCH_PROMPT_VERSION,
        "blocked_domains": list(blocked_domains or []),
        "parsed": record is not None,
        "candidates": candidates,
        "kept": len(kept),
        "dropped": {
            "invalid": sum(reasons.get(r, 0) for r in _INVALID),
            "unverified": sum(reasons.get(r, 0) for r in _UNVERIFIED),
            "paraphrase": sum(v for r, v in reasons.items() if r.startswith("paraphrase_")),
            "by_reason": dict(sorted(reasons.items())),
        },
        "retagged_employer_replies": retagged,
        "citations": {"total": len(result.citations), "by_kind": by_kind},
        "requested_model": result.model,
        "served_model": result.served_model,
        "fell_back": result.fell_back,
        "stop_reason": result.stop_reason,
        "continuations": result.continuations,
        "usage": {
            "api_requests": result.usage.api_requests,
            "web_search_requests": result.usage.web_search_requests,
            "web_fetch_requests": result.usage.web_fetch_requests,
            "input_tokens": totals.input_tokens,
            "output_tokens": totals.output_tokens,
            "cache_creation_input_tokens": totals.cache_creation_input_tokens,
            "cache_read_input_tokens": totals.cache_read_input_tokens,
        },
        "scope_declaration": _clean_str(record.get("scope_declaration")) if record else None,
        "yield": _yield(kept),
        "sources": [
            {"url": s.url, "title": s.title, "fetched": s.fetched, "cited": s.cited,
             "page_age": s.page_age, "retrieved_at": s.retrieved_at}
            for s in result.sources
        ],
        "items": list(meta or []),
        # Verbatim third-party text from here down: the reason the card is internal.
        "raw_text": result.text,
        "raw_citations": [
            {"kind": c.kind, "url": c.url, "title": c.title, "cited_text": c.cited_text}
            for c in result.citations
        ],
    }
    return card


# ---------------------------------------------------------------------------
# The call
# ---------------------------------------------------------------------------

def run_research(
    company_name: str,
    *,
    domain: Optional[str] = None,
    client: Any = None,
    model: Optional[str] = None,
    now: Optional[datetime.datetime] = None,
) -> ResearchOutcome:
    """One research turn for *company_name*, parsed and gated.

    Raises ``LLMProviderUnavailable`` before any spend (no key), and a
    ``ResearchCallError`` subclass -- each carrying ``.usage`` -- for a turn that
    spent money and did not produce a record.
    """
    prompt = build_research_prompt(company_name, domain)
    blocked = blocked_domains()
    result = run_research_call(
        prompt,
        system=RESEARCH_SYSTEM,
        model=model,
        max_tokens=RESEARCH_MAX_TOKENS,
        max_searches=RESEARCH_MAX_SEARCHES,
        max_fetches=RESEARCH_MAX_FETCHES,
        blocked_domains=blocked,
        client=client,
    )
    try:
        record = parse_record(result.final_text)
    except ValueError:
        try:
            record = parse_record(result.text)
        except ValueError as exc:
            raise ResearchParseError(
                "research record unparseable: %s" % exc, result.usage,
                diagnostics=build_run_card(result, blocked_domains=blocked),
            ) from exc

    retrieved_at = now or datetime.datetime.now(datetime.timezone.utc)
    items, meta, reasons, retagged = _build_items(record, result, retrieved_at)
    card = build_run_card(result, record=record, kept=items, meta=meta,
                          reasons=reasons, retagged=retagged, blocked_domains=blocked)

    company = record.get("company") if isinstance(record.get("company"), dict) else {}
    headcount = _parse_int(company.get("headcount"))

    outcome = ResearchOutcome(
        items=tuple(items),
        domain=normalize_domain(company.get("official_domain")),
        headcount=headcount,
        headcount_as_of=_parse_date(company.get("headcount_as_of")) if headcount else None,
        headcount_source=_clean_str(company.get("headcount_source")) if headcount else None,
        scope_declaration=card["scope_declaration"],
        usage=result.usage,
        cost_usd=estimate_research_cost_usd(result.usage),
        model=result.model,
        served_model=result.served_model,
        fell_back=result.fell_back,
        candidates=card["candidates"],
        dropped_unverified=card["dropped"]["unverified"],
        dropped_paraphrase=card["dropped"]["paraphrase"],
        dropped_invalid=card["dropped"]["invalid"],
        citations=len(result.citations),
        diagnostics=card,
        item_meta=tuple(meta),
    )
    logger.info(
        "company_research_parsed",
        extra={
            "event": "company_research_parsed",
            "candidates": outcome.candidates,
            "kept": len(outcome.items),
            "dropped_unverified": outcome.dropped_unverified,
            "dropped_paraphrase": outcome.dropped_paraphrase,
            "dropped_invalid": outcome.dropped_invalid,
            "citations": outcome.citations,
            "cost_usd": outcome.cost_usd,
            "served_model": outcome.served_model,
        },
    )
    return outcome
