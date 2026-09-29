"""
scorer_pipeline.py -- S1-1, S1-2, S1-5 from SPRINT_SCORER_PIPELINE_01.md.

  S1-1: extended response schema (adds evidence_quotes) + ScorerResult/DimensionScore
        types + packet_version extraction.
  S1-2: score_packet(packet, rubric, model_cfg) -> ScorerResult -- a clean interface
        with no file-writing side effects, unlike scorer_variance_test_v2.py's
        run_once() which tangles scoring with CSV/raw-JSON output.
  S1-5: citation verifier -- matches each evidence_quote against the packet's
        addressable excerpts to determine source_tag and whether it actually appears
        verbatim, normalizing whitespace/dashes/smart-quotes (the exact bug 08-15b
        found by hand on P-02/P-05).

DESIGN DECISION, recorded because it changes the schema from what a literal reading of
the sprint doc implies: evidence_quotes are QUOTE TEXT ONLY. The model is NOT asked to
self-report source_tags. Source classification is computed DOWNSTREAM by matching each
quote to its originating excerpt in the packet, whose source class is already
deterministic (company / noncompany / disputed / researcher -- the exact taxonomy
build_rater_page.py already uses and the rater pages already ship with). Asking the
model to self-classify would duplicate a classification this project has already built
and validated once, on infrastructure raters are actively using, with no way to force
the two to agree -- the same "one claim in two costumes" problem the anonymization
ruleset's R8 rule exists to catch, now on the scoring side instead of the collection
side. The excerpt-parsing and classify_source logic below is PORTED from
Solverah_IP/ground_truth/rater_app/build_rater_page.py (not imported), matching this
project's existing convention of independently-runnable scripts (see
reidentification_attack.py's load_packet_section1) and deliberately avoiding any import
into or modification of live rater infrastructure while raters may be mid-round.

    pip install openai python-dotenv pandas
"""

from __future__ import annotations

import html as htmllib
import json
import os
import re as _re
import sys
import time
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from openai import (
    APIConnectionError, APIStatusError, APITimeoutError, BadRequestError,
    OpenAI, RateLimitError,
)

# ---------------------------------------------------------------------------
# PATHS -- same resolution as scorer_variance_test_v2.py / reidentification_attack.py.
# Solverah_IP has moved before (sibling of the Solverah repo under Desktop/, then
# in-repo at Solverah/Solverah_IP) and may move again, so instead of hard-coding a
# depth, search upward from this file for the first ancestor holding a Solverah_IP/
# whose anchors.json is real. SOLVERAH_IP_DIR always wins outright when set, honored
# verbatim with no existence check.
# ---------------------------------------------------------------------------
def _find_ip_dir(start: Path) -> Path | None:
    for ancestor in start.parents:
        candidate = ancestor / "Solverah_IP"
        if (candidate / "ground_truth" / "rater_app" / "anchors.json").exists():
            return candidate
    return None


_HERE = Path(__file__).resolve()
_FALLBACK_IP_DIR = _HERE.parent.parent / "Solverah_IP"
if "SOLVERAH_IP_DIR" in os.environ:
    REPO_IP = Path(os.environ["SOLVERAH_IP_DIR"])
else:
    REPO_IP = _find_ip_dir(_HERE) or _FALLBACK_IP_DIR
ANCHORS_PATH = REPO_IP / "ground_truth" / "rater_app" / "anchors.json"

VALID_PACKETS = ["P-01", "P-02", "P-03", "P-04", "P-05", "P-06"]
DIMENSIONS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]
SCORE_BAND_VALUES = [0.1, 0.3, 0.5, 0.7, 0.9]
CONFIDENCE_BAND_VALUES = [0.1, 0.3, 0.6, 0.9]

MODEL = "gpt-5.5-2026-04-23"
REASONING_EFFORT = "medium"
TEMPERATURE = 1.0
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 2.0


def packet_path_for(packet_id: str) -> Path:
    if packet_id not in VALID_PACKETS:
        raise ValueError(f"packet must be one of {VALID_PACKETS}, got {packet_id!r}")
    return REPO_IP / "ground_truth" / "anonymization" / f"{packet_id}_packet_ANON.txt"


def load_anchors(path: Path | str | None = None) -> dict:
    """The frozen anchors.json by default; any other anchors file by path (e.g. v3.1)."""
    p = Path(path) if path is not None else ANCHORS_PATH
    if not p.exists():
        raise FileNotFoundError(f"anchors file not found at {p}.")
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Insufficient evidence (Julie's ruling 4, anchors v3.1+). The model may abstain on a
# dimension -- score AND confidence null -- instead of being forced onto a band, so its
# output can be compared with human raters' on the same terms. Switched on by the RUBRIC:
# an anchors file without an `insufficient_evidence` block (the frozen v1, and v3) gets
# exactly the pre-2026-09-29 schema, prompt and instruction, pinned byte for byte by
# fixtures/scorer_v1_golden.json.
# ---------------------------------------------------------------------------
INSUFFICIENT_MARKER = "INSUFFICIENT EVIDENCE --"


def permits_insufficient_evidence(anchors: dict) -> bool:
    return "insufficient_evidence" in anchors


def build_rubric_text(anchors: dict) -> str:
    allow = permits_insufficient_evidence(anchors)
    # "frozen for round 1" was always a claim about v1; a rubric that offers the skip is
    # by construction not the round-1 instrument, so it does not repeat the claim.
    status = "" if allow else " · frozen for round 1"
    lines = ["SOLVERAH", "Company Culture Rating Rubric",
              f"Ground-truth scoring instrument · {anchors['rubric_version']}{status}", ""]
    lines.append(
        "Score each of the six dimensions independently, using ONLY the evidence packet "
        "provided. For each dimension, pick exactly one band value from "
        f"{anchors['band_values']} for the score, and exactly one band value from "
        "the confidence bands below for the confidence. Do not interpolate between bands. "
        "Also quote 1-3 short verbatim phrases from the packet that most directly support "
        "your score -- copy them exactly as they appear, do not paraphrase."
    )
    lines.append("")
    if allow:
        ie = anchors["insufficient_evidence"]
        lines.append(
            f"{INSUFFICIENT_MARKER} {ie['label']}: {ie['text']} To record it, set BOTH score "
            "and confidence to null for that dimension. Quotes are optional when you do; if "
            "you give any, they should show why the packet cannot support a score. Use this "
            "only when the packet genuinely cannot characterise the company on that "
            "dimension -- never as a way to avoid an extreme band."
        )
        lines.append("")
    lines.append("Five gates -- read before scoring:")
    for i, gate in enumerate(anchors["gates"], 1):
        lines.append(f"{i}. {gate}")
    lines.append("")
    lines.append("Confidence bands (about the EVIDENCE, not about you):")
    for band in anchors["confidence_bands"]:
        lines.append(f"  {band['value']} ({band['label']}): {band['text']}")
    lines.append("")
    lines.append("The six dimensions:")
    for dim in anchors["dimensions"]:
        lines.append("")
        lines.append(f"## {dim['name']} ({dim['key']})   {dim['low_pole']} (0.1)  →  {dim['high_pole']} (0.9)")
        lines.append(f"Measures: {dim['measures']}")
        lines.append(f"Where to look: {dim['where_to_look']}")
        lines.append(f"Keep distinct: {dim['keep_distinct']}")
        lines.append("Score bands:")
        for band in dim["bands"]:
            lines.append(f"  {band['value']} ({band['reads_as']}): {band['text']}")
    return "\n".join(lines)


_START_MARKER = "########## SECTION 1"
_END_MARKER = "########## END OF PACKET ##########"
_PACKET_VERSION_RE = _re.compile(r"build\s+(v[\d.]+)")


def load_packet_section1(packet_path: Path) -> str:
    if not packet_path.exists():
        raise FileNotFoundError(f"Packet not found at {packet_path}.")
    raw = packet_path.read_text(encoding="utf-8")
    start, end = raw.find(_START_MARKER), raw.find(_END_MARKER)
    if start == -1 or end == -1:
        raise ValueError(
            "Could not find SECTION 1 / END OF PACKET markers -- refusing to guess."
        )
    return raw[start:end + len(_END_MARKER)].strip()


def packet_version_for(packet_path: Path) -> str:
    """Parsed from the packet header's 'scrubbed from : P-0N_packet.txt (build vX.Y, ...)'
    line -- the collector-prompt version is already recorded there for every packet
    (verified: all six currently say 'build v4.6'). Using this instead of inventing a
    new versioning scheme keeps packet_version tied to the thing that actually changes
    packet content, per the same reasoning schema.sql already applies to model_run."""
    raw = packet_path.read_text(encoding="utf-8")
    header = raw[:raw.find(_START_MARKER)] if _START_MARKER in raw else raw[:500]
    m = _PACKET_VERSION_RE.search(header)
    if not m:
        raise ValueError(
            f"Could not find a 'build vX.Y' version marker in {packet_path}'s header. "
            f"Refusing to guess a packet_version."
        )
    return m.group(1)


# ---------------------------------------------------------------------------
# Excerpt parsing + source classification -- PORTED from build_rater_page.py
# (see module docstring for why this is a port, not an import). Kept structurally
# identical to the original so the two stay comparable; if build_rater_page.py's
# classify_source ever changes, this needs a matching update -- flagged here so a
# future reader knows the two must move together even though they're not one function.
# ---------------------------------------------------------------------------
_SECTION_RE = _re.compile(r"^\s*---\s*([A-F])\.\s")
_EXCERPT_RE = _re.compile(r"^\s*[•·]\s")
_COMPANY_RUN_PUBLICATION_RE = _re.compile(
    r"(company|employer)[^\]]{0,40}?(blog|newsroom|magazine|microsite|publication)"
    r"|(blog|newsroom|magazine|microsite|publication)[^\]]{0,20}?(company|employer)")
_EXEC_BYLINE = ("chief executive", "ceo,", "founder", "(executive)")


def classify_source(attribution: str, byline: Optional[str] = None) -> str:
    """company | noncompany | disputed | researcher | unknown. Ported verbatim (logic-
    for-logic) from build_rater_page.py's function of the same name -- see that file's
    docstring for the full reasoning behind each branch."""
    a = attribution.lower()
    if "researcher observation" in a or "absence recorded" in a:
        return "researcher"
    if "employee review" in a:
        return "noncompany"
    if ("independent," in a or "trade press" in a or "business press" in a
            or "not company-authored" in a):
        return "noncompany"
    bracket = _re.match(r"\s*—\s*\[([^\]]*)\]", attribution)
    pub_field = bracket.group(1).lower() if bracket else a
    if _COMPANY_RUN_PUBLICATION_RE.search(pub_field):
        b = (byline if byline is not None else attribution).lower()
        return "company" if any(e in b for e in _EXEC_BYLINE) else "disputed"
    if ("company-authored" in a or "employer-authored" in a or "employer," in a
            or "regulatory filing" in a or "10-k" in a or "company website" in a
            or "company careers" in a or "company code" in a or "job posting" in a
            or "company values" in a or "attributed on the page" in a):
        return "company"
    return "unknown"


@dataclass
class Excerpt:
    eid: str
    section: str
    text: str          # verbatim quote body, NOT html-escaped
    source_tag: str     # company | noncompany | disputed | researcher | unknown


def parse_excerpts(packet_text: str) -> list[Excerpt]:
    """Same block-iteration approach as build_rater_page.py's build_packet_markup,
    returning structured Excerpt records instead of HTML. Ignores prose/section-header
    blocks; only bullet blocks carrying a quoted body count as excerpts (a bullet
    without a quote is prose, e.g. P-05's Section C exemption note)."""
    excerpts: list[Excerpt] = []
    section, idx = "?", 0
    section_note, group_preamble = "", ""

    lines = packet_text.split("\n")
    blocks: list = []
    cur: list[str] = []
    for line in lines:
        if line.strip():
            cur.append(line)
        else:
            if cur:
                blocks.append(cur)
                cur = []
            blocks.append(None)
    if cur:
        blocks.append(cur)

    for blk in blocks:
        if blk is None:
            continue
        joined = "\n".join(blk)
        m = _SECTION_RE.match(blk[0])
        if m:
            section, idx = m.group(1), 0
            section_note, group_preamble = "", ""
            continue
        if _EXCERPT_RE.match(blk[0]) and '"' in joined:
            idx += 1
            eid = f"{section}{idx}"
            bm = _re.search(r"—\s*\[", joined)
            if bm:
                attribution = joined[bm.start():]
                src = classify_source(attribution)
            else:
                src = classify_source(group_preamble + " || " + section_note, byline=group_preamble)
            excerpts.append(Excerpt(eid=eid, section=section, text=joined, source_tag=src))
            continue
        group_preamble = " ".join(x.strip() for x in blk)
        if not section_note:
            section_note = group_preamble
    return excerpts


# ---------------------------------------------------------------------------
# S1-1: ScorerResult / DimensionScore types + extended response schema
# ---------------------------------------------------------------------------
@dataclass
class DimensionScore:
    dimension: str
    score: Optional[float]        # None = insufficient evidence (anchors v3.1+ only)
    confidence: Optional[float]   # None exactly when score is None
    evidence_quotes: list[str]

    @property
    def insufficient_evidence(self) -> bool:
        return self.score is None


@dataclass
class ScorerResult:
    packet_id: str
    model: str
    rubric_version: str
    packet_version: str
    temperature_honored: bool
    reasoning_effort: str
    timestamp: str
    dimensions: list[DimensionScore] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "packet_id": self.packet_id, "model": self.model,
            "rubric_version": self.rubric_version, "packet_version": self.packet_version,
            "temperature_honored": self.temperature_honored,
            "reasoning_effort": self.reasoning_effort, "timestamp": self.timestamp,
            "dimensions": [
                {"dimension": d.dimension, "score": d.score, "confidence": d.confidence,
                 "evidence_quotes": d.evidence_quotes,
                 # present only on an abstention, so a scored row is shaped as before
                 **({"insufficient_evidence": True} if d.insufficient_evidence else {})}
                for d in self.dimensions
            ],
        }


_DIMENSION_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "enum": SCORE_BAND_VALUES},
        "confidence": {"type": "number", "enum": CONFIDENCE_BAND_VALUES},
        "evidence_quotes": {
            "type": "array", "minItems": 1, "maxItems": 3,
            "items": {"type": "string"},
            "description": "1-3 short verbatim phrases copied exactly from the packet "
                            "that most directly support this score. Copy exactly; do "
                            "not paraphrase, summarize, or combine multiple sentences.",
        },
    },
    "required": ["score", "confidence", "evidence_quotes"],
    "additionalProperties": False,
}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {dim: _DIMENSION_SCHEMA for dim in DIMENSIONS},
    "required": DIMENSIONS,
    "additionalProperties": False,
}

# The abstaining variant. Strict mode needs every property in `required`, so score and
# confidence stay required and become nullable (an anyOf with null -- the union form
# OpenAI documents for strict mode; NOT yet sent to the live API as of 2026-09-29, so the
# first live call is also its acceptance test); evidence_quotes may be empty. "Null score
# means null confidence" is not expressible in strict JSON schema, so score_packet enforces
# it on the parsed response.
_DIMENSION_SCHEMA_INSUFFICIENT = {
    "type": "object",
    "properties": {
        "score": {"anyOf": [{"type": "number", "enum": SCORE_BAND_VALUES}, {"type": "null"}]},
        "confidence": {"anyOf": [{"type": "number", "enum": CONFIDENCE_BAND_VALUES},
                                 {"type": "null"}]},
        "evidence_quotes": {
            "type": "array", "minItems": 0, "maxItems": 3,
            "items": {"type": "string"},
            "description": "1-3 short verbatim phrases copied exactly from the packet that "
                            "most directly support this score. Copy exactly; do not "
                            "paraphrase, summarize, or combine multiple sentences. May be "
                            "empty only when score is null (insufficient evidence).",
        },
    },
    "required": ["score", "confidence", "evidence_quotes"],
    "additionalProperties": False,
}

RESPONSE_SCHEMA_INSUFFICIENT = {
    "type": "object",
    "properties": {dim: _DIMENSION_SCHEMA_INSUFFICIENT for dim in DIMENSIONS},
    "required": DIMENSIONS,
    "additionalProperties": False,
}


def response_schema(allow_insufficient_evidence: bool = False) -> dict:
    return RESPONSE_SCHEMA_INSUFFICIENT if allow_insufficient_evidence else RESPONSE_SCHEMA


# ---------------------------------------------------------------------------
# S1-2: score_packet() -- clean interface, no file-writing side effects.
# ---------------------------------------------------------------------------
def call_with_retry(client: OpenAI, messages: list[dict], model: str,
                     temperature: Optional[float], reasoning_effort: str,
                     schema: Optional[dict] = None):
    kwargs = dict(model=model, messages=messages, response_format={
        "type": "json_schema",
        "json_schema": {"name": "dimension_scores_v2", "strict": True,
                        "schema": RESPONSE_SCHEMA if schema is None else schema},
    })
    active_kwargs = dict(kwargs, temperature=temperature, reasoning_effort=reasoning_effort)
    temperature_honored = True
    last_exc: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return client.chat.completions.create(**active_kwargs), temperature_honored
        except BadRequestError as exc:
            msg = str(exc).lower()
            if "temperature" in msg and "temperature" in active_kwargs:
                active_kwargs = {k: v for k, v in active_kwargs.items() if k != "temperature"}
                temperature_honored = False
                continue
            if "reasoning_effort" in msg and "reasoning_effort" in active_kwargs:
                active_kwargs = {k: v for k, v in active_kwargs.items() if k != "reasoning_effort"}
                continue
            raise
        except (RateLimitError, APIConnectionError, APITimeoutError, APIStatusError) as exc:
            last_exc = exc
            retryable = isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError)) or (
                isinstance(exc, APIStatusError) and exc.status_code in (429, 500, 502, 503, 504))
            if not retryable or attempt == MAX_RETRIES:
                raise
            time.sleep(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 1))
    raise last_exc  # pragma: no cover


def score_packet(
    client: OpenAI,
    packet_text: str,
    rubric_text: str,
    *,
    packet_id: str,
    rubric_version: str,
    packet_version: str,
    model: str = MODEL,
    temperature: float = TEMPERATURE,
    reasoning_effort: str = REASONING_EFFORT,
    allow_insufficient_evidence: bool = False,
) -> ScorerResult:
    """S1-2's interface: score_packet(packet, rubric, model_cfg) -> ScorerResult.
    No file I/O -- the caller decides what to persist and how. This is the piece
    scorer_variance_test_v2.py's run_once() doesn't have: that function scores AND
    writes its own raw JSON AND appends to a specific CSV shape, so it can't be reused
    anywhere the output needs a different destination (e.g. serving, or this sprint's
    own S1-4/S1-7 scripts) without copy-pasting the whole function.

    `allow_insufficient_evidence` must be `permits_insufficient_evidence(anchors)` for the
    anchors `rubric_text` was built from. A mismatch -- a prompt offering the skip with a
    schema that forbids it, or the reverse -- is refused BEFORE any API call is paid for."""
    if (INSUFFICIENT_MARKER in rubric_text) != allow_insufficient_evidence:
        raise ValueError(
            "rubric_text and allow_insufficient_evidence disagree: pass "
            "allow_insufficient_evidence=permits_insufficient_evidence(anchors) for the "
            "anchors the rubric text was built from."
        )
    instruction = (
        "Score the evidence packet against the rubric on these six dimensions: "
        + ", ".join(DIMENSIONS) + ". For each dimension, choose a score from exactly "
        f"these band values: {SCORE_BAND_VALUES}, a confidence from exactly these band "
        f"values: {CONFIDENCE_BAND_VALUES}, and 1-3 short verbatim quotes from the "
        "packet supporting the score. Base your scoring only on the rubric and packet "
        "text provided. Do not use any outside knowledge, web search, or tools, even "
        "if you recognise the company from the evidence."
    )
    if allow_insufficient_evidence:
        instruction += (
            " If the packet genuinely cannot characterise the company on a dimension, you "
            "may instead record insufficient evidence for it: score null and confidence null."
        )
    messages = [{"role": "user", "content": f"RUBRIC:\n{rubric_text}\n\nEVIDENCE PACKET:\n{packet_text}\n\n{instruction}"}]
    response, temperature_honored = call_with_retry(
        client, messages, model, temperature, reasoning_effort,
        schema=response_schema(allow_insufficient_evidence))
    parsed = json.loads(response.choices[0].message.content)

    return ScorerResult(
        packet_id=packet_id, model=model, rubric_version=rubric_version,
        packet_version=packet_version, temperature_honored=temperature_honored,
        reasoning_effort=reasoning_effort, timestamp=datetime.now(timezone.utc).isoformat(),
        dimensions=[_dimension_from(dim, parsed[dim], allow_insufficient_evidence)
                    for dim in DIMENSIONS],
    )


def _dimension_from(dim: str, row: dict, allow_insufficient_evidence: bool) -> DimensionScore:
    score = row["score"]
    if score is None:
        if not allow_insufficient_evidence:
            raise ValueError(f"{dim}: null score from a call whose rubric offers no skip")
        # Null score means null confidence. Strict schema cannot tie the two together, so a
        # confidence the model attached to an abstention is dropped here rather than kept
        # as a number that describes no score.
        return DimensionScore(dimension=dim, score=None, confidence=None,
                              evidence_quotes=list(row["evidence_quotes"]))
    if row["confidence"] is None:
        # The reverse is not recoverable: a score with no confidence is not a row this
        # project stores. Fail loudly rather than invent one. (A score with zero quotes IS
        # kept -- the citation verifier reports it as unsupported, which is the honest record.)
        raise ValueError(f"{dim}: score {score} returned with a null confidence")
    return DimensionScore(dimension=dim, score=float(score),
                          confidence=float(row["confidence"]),
                          evidence_quotes=list(row["evidence_quotes"]))


# ---------------------------------------------------------------------------
# S1-5: citation verifier.
# ---------------------------------------------------------------------------
# The em-dash/smart-quote normalization this project already found the hard way
# (08-15b, P-02/P-05: a wholesale retype silently turned ASCII hyphens into em dashes
# inside quote bodies, and three quotes failed a naive string-match audit purely on
# punctuation until dash normalization was added). Whitespace collapse is the third
# normalization scorer_variance_test_v2.py-style prompts already need, since a model
# may reproduce a multi-line quote with different line wrapping.
_DASH_CHARS = "‒–—―‑"
_QUOTE_CHARS = "‘’“”"


def _normalize(text: str) -> str:
    out = text
    for d in _DASH_CHARS:
        out = out.replace(d, "-")
    out = out.replace("‘", "'").replace("’", "'")
    out = out.replace("“", '"').replace("”", '"')
    out = _re.sub(r"\s+", " ", out).strip()
    return out


@dataclass
class CitationCheck:
    packet_id: str
    dimension: str
    quote: str
    matched: bool
    matched_eid: Optional[str]
    source_tag: Optional[str]


def verify_quote(quote: str, excerpts: list[Excerpt]) -> tuple[bool, Optional[str], Optional[str]]:
    """Normalized substring match against every excerpt's verbatim text. Returns
    (matched, excerpt_id, source_tag). Checks ALL excerpts and requires the match to be
    unambiguous-enough (first match wins, but multiple matches are still 'matched' --
    a quote appearing in two excerpts is the R8 double-counting case, not a verification
    failure) rather than stopping at the first excerpt tried."""
    norm_quote = _normalize(quote)
    if len(norm_quote) < 10:
        return False, None, None  # too short to be meaningful evidence, same floor as MIN_CITE in the rater app
    for ex in excerpts:
        if norm_quote in _normalize(ex.text):
            return True, ex.eid, ex.source_tag
    return False, None, None


def verify_result(result: ScorerResult, packet_text: str) -> list[CitationCheck]:
    excerpts = parse_excerpts(packet_text)
    rows = []
    for dim in result.dimensions:
        for quote in dim.evidence_quotes:
            matched, eid, src = verify_quote(quote, excerpts)
            rows.append(CitationCheck(
                packet_id=result.packet_id, dimension=dim.dimension, quote=quote,
                matched=matched, matched_eid=eid, source_tag=src,
            ))
    return rows


def noncompany_support(result: ScorerResult, packet_text: str) -> dict:
    """Per dimension: whether at least one MATCHED, VERIFIED quote is non-company-
    authored. Deliberately requires matched=True -- an unverified quote (the model
    invented it, or garbled it past recognition) cannot count as evidence of anything,
    which is the whole point of building the verifier before trusting the flag."""
    checks = verify_result(result, packet_text)
    out = {}
    for dim in DIMENSIONS:
        dim_checks = [c for c in checks if c.dimension == dim and c.matched]
        out[dim] = any(c.source_tag == "noncompany" for c in dim_checks)
    return out
