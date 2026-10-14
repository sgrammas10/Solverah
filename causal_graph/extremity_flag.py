"""
extremity_flag.py -- floor-bias workaround for the LLM extractor.

WHY THIS EXISTS
---------------
Measured 2026-09-01 across 72 independent scoring instances (two separate runs,
model gpt-5.5-2026-04-23): the extractor NEVER assigns the 0.1 band, on any
dimension, while human raters used 0.1 at least five times on the same six
packets. An explicit prompt instruction telling the model to use extreme bands on
unanimous evidence produced zero movement on all three test cases. The bias is
structural, not a prompting gap -- see LLM_VS_HUMAN_COMPARISON_2026-09-01.md
addenda 4 and 5.

Consequence: any downstream rule of the form "score <= 0.2 -> flag this company"
can never fire. That blocks the quarantine-gate idea outright. This module
supplies the missing bottom-end signal WITHOUT trusting the model's score field.

WHAT DOESN'T WORK (documented so it isn't re-attempted)
-------------------------------------------------------
1. source_tag counts. `classify_source` returns company / noncompany / disputed /
   researcher -- AUTHORSHIP, not valence. It cannot tell you whether cited evidence
   is negative, so it cannot detect "unanimous negative evidence" on its own.

2. A SYMMETRIC citation-consistency flag ("all cited quotes match the extreme band
   but the score sits inside that pole"). This looks right and fails validation.
   Counterexample from real data, P-03/autonomy: the model cited three quotes that
   all match the 0.9 band description ("Own your impact on day one", "thrive in
   autonomous, high-expectation environments", "work independently and take full
   ownership ... without ... hand-holding") and scored 0.7. Identical citation
   shape to the true floor cases -- but here the human raters' median was also 0.7,
   so the model was right and the flag would be a false positive. Citing vivid
   extreme quotes and then scoring moderately is ordinary, defensible behavior.
   A symmetric consistency check cannot separate that from real floor-avoidance.

WHAT THIS MODULE DOES INSTEAD
-----------------------------
It exploits the one asymmetry that IS established: the model's output distribution
is truncated at the bottom and not at the top. It emits 0.9 freely; it never emits
0.1. So the flag is deliberately ONE-SIDED. It fires only on the floor, and only
because bottom-end truncation is a measured property of this model -- not because
the logic is sound in both directions. If a future model is shown to use 0.1
normally, this module should be retired, not made symmetric.

The bottom-end signal comes from a differently-shaped question. Rather than asking
the model to RATE a company (the task shape that triggers the reluctance), it asks
a binary, per-quote, company-agnostic membership question: "does this text fragment
describe <band 0.1 description>? yes/no". The hypothesis is that reluctance attaches
to rendering a harsh verdict on an identifiable employer, not to classifying an
isolated fragment against a description.

    *** THAT HYPOTHESIS IS UNTESTED. *** Run validate_probe_escapes_reluctance()
    before trusting any output of this module. If the probe returns "no" on quotes
    that plainly match the 0.1 description, the reluctance transfers, this approach
    is dead too, and the finding should be recorded rather than worked around.

USAGE
    from extremity_flag import flag_result, ForcedChoiceBandProbe
    probe = ForcedChoiceBandProbe(client, anchors, allow_off_axis=True)   # <- the tested default
    flags = flag_result(result, packet_text, probe=probe)

RECOMMENDED PROBE (settled 2026-09-01 by probe_boundary_test.py, 46 real quotes,
three designs A/B/C'd against one pre-registered label set):

                          A floor    B boundary   C off-axis   D opposite
  LLMBandProbe (binary)   12/13 92%   6/10  60%   12/12 100%   11/11 100%
  ForcedChoice            10/13 77%   8/10  80%    9/12  75%   11/11 100%
  ForcedChoice + escape    9/13 69%   8/10  80%   12/12 100%   11/11 100%   <- USE THIS

Binary over-matches at the 0.1/0.3 boundary (it is asked about one description in
isolation, so any resemblance earns a yes). Plain forced choice fixes that but
cannot say "none of these", so it maps negative-sounding OFF-AXIS quotes onto the
low band -- the dangerous failure, since it can manufacture unanimity out of
irrelevant evidence. Forced choice plus the off-axis opt-out keeps both fixes.

Its lower A score is the tolerable direction (the flag under-fires, a human simply
gets no suggestion) and on review 3 of its 4 A misses were bad hand labels, not
probe errors: the probe separates 0.1 from 0.3 more reliably than the labeller did.

Measured effect on the two cells that fired in the 2026-09-01 sweep: P-06/autonomy
(the one CONFIRMED true positive) still fires -- all three quotes match; the
unadjudicated P-06/feedback fire disappears, because "mid-year touch points and
formal end-of-year discussions" correctly lands on 0.3 rather than 0.1. Precision
up, the solid hit retained.

NOT re-measured: the overall fire rate under this probe. The sweep's 12% was
measured with the binary probe. Re-run run_flag_sweep.py to get the real number.

No file I/O, no side effects, no imports into live rater or API infrastructure --
same convention as scorer_pipeline.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol, Sequence

FLOOR_BAND = 0.1
CEILING_BAND = 0.9

# Minimum number of extreme-matching verified quotes before a flag is even
# considered. One quote is an anecdote, not unanimity.
MIN_EXTREME_QUOTES = 2


@dataclass
class QuoteProbe:
    """One cited quote, and whether it matches the floor band's description."""
    quote: str
    dimension: str
    matches_floor_band: Optional[bool]   # None = probe could not decide / not run
    verified: bool                       # did it verify against the packet text
    source_tag: Optional[str] = None


@dataclass
class ExtremityFlag:
    packet_id: str
    dimension: str
    score: Optional[float]       # None = the model recorded insufficient evidence
    n_verified: int
    n_matching_floor: int
    n_not_matching: int
    flag: Optional[str]          # "FLOOR_SUSPECT" or None
    severity: Optional[str]      # "mild" | "severe"
    rationale: str
    probes: list[QuoteProbe] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "packet_id": self.packet_id, "dimension": self.dimension,
            "score": self.score, "n_verified": self.n_verified,
            "n_matching_floor": self.n_matching_floor,
            "n_not_matching": self.n_not_matching,
            "flag": self.flag, "severity": self.severity,
            "rationale": self.rationale,
            "probes": [{"quote": p.quote, "matches_floor_band": p.matches_floor_band,
                        "verified": p.verified, "source_tag": p.source_tag}
                       for p in self.probes],
        }


class BandProbe(Protocol):
    """Decides, per quote, whether it describes the dimension's 0.1 band."""

    def probe(self, quotes: Sequence[str], dimension: str) -> list[Optional[bool]]:
        ...


class ManualBandProbe:
    """Hand-supplied labels. For testing the flag logic without API calls."""

    def __init__(self, labels: dict[tuple[str, str], Optional[bool]]):
        # keyed by (dimension, quote)
        self._labels = labels

    def probe(self, quotes: Sequence[str], dimension: str) -> list[Optional[bool]]:
        return [self._labels.get((dimension, q)) for q in quotes]


class LLMBandProbe:
    """Binary per-quote membership probe, batched one call per (packet, dimension).

    Deliberate framing choices, each one aimed at NOT reproducing the scoring task
    that triggers the floor reluctance:
      * no company is named or implied; quotes arrive as isolated fragments
      * no score, band value or rating is requested -- only yes/no membership
      * the 0.1 band's own description from the frozen anchors is the yardstick,
        so this introduces no new taxonomy to keep in sync
      * quotes are presented in a shuffled, unnumbered-by-origin list so the model
        cannot infer it is being asked to condemn one employer
    """

    def __init__(self, client, anchors: dict, model: str = "gpt-5.5-2026-04-23",
                 reasoning_effort: str = "medium",
                 call_fn: Optional[Callable] = None):
        self._client = client
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._call_fn = call_fn
        self._floor_text = {}
        for d in anchors["dimensions"]:
            floor = next(b for b in d["bands"] if b["value"] == FLOOR_BAND)
            self._floor_text[d["key"]] = {
                "pole": d["low_pole"],
                "text": floor["text"],
                "measures": d["measures"],
            }

    def probe(self, quotes: Sequence[str], dimension: str) -> list[Optional[bool]]:
        if not quotes:
            return []
        spec = self._floor_text[dimension]
        schema = {
            "type": "object",
            "properties": {
                "answers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer"},
                            "matches": {"type": "boolean"},
                        },
                        "required": ["index", "matches"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["answers"],
            "additionalProperties": False,
        }
        listing = "\n".join(f"{i}. \"{q}\"" for i, q in enumerate(quotes))
        prompt = (
            "You are classifying isolated text fragments against a single written "
            "description. This is a text-matching task, not an evaluation of any "
            "organization, and no organization is identified.\n\n"
            f"DESCRIPTION (category \"{spec['pole']}\"):\n{spec['text']}\n\n"
            f"For context, the underlying property being described is: {spec['measures']}\n\n"
            "For each fragment below, answer whether the fragment describes a situation "
            "matching the DESCRIPTION above. Answer only true or false for each. Judge "
            "the fragment on its own words; do not speculate about surrounding context.\n\n"
            f"FRAGMENTS:\n{listing}"
        )
        messages = [{"role": "user", "content": prompt}]

        if self._call_fn is not None:
            response = self._call_fn(messages, schema)
        else:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                reasoning_effort=self._reasoning_effort,
                response_format={"type": "json_schema", "json_schema": {
                    "name": "band_membership", "strict": True, "schema": schema}},
            )
        parsed = json.loads(response.choices[0].message.content)
        out: list[Optional[bool]] = [None] * len(quotes)
        for a in parsed["answers"]:
            i = a["index"]
            if 0 <= i < len(quotes):
                out[i] = bool(a["matches"])
        return out



class ForcedChoiceBandProbe:
    """Alternative to LLMBandProbe: 5-way forced choice instead of binary membership.

    WHY THIS EXISTS (probe_boundary_test.py, 2026-09-01)
    ----------------------------------------------------
    LLMBandProbe asks "does this fragment match <the 0.1 description>? yes/no".
    That framing has a measured false-positive path: a quote containing BOTH poles
    can score a "yes" because part of it resembles the single description shown,
    with nothing forcing a comparison against the alternatives. The proof case is
    decision / "combines systematic pricing infrastructure with trader judgment" --
    explicitly both poles, matched True against the 0.1 band.

    This probe shows all five band descriptions and asks which one the fragment best
    matches, returning True only when the answer is the floor band. A both-poles
    sentence should land on the mixed band and therefore return False.

    Same isolation properties as LLMBandProbe: no company named, no score requested,
    fragments presented as an unordered list, descriptions taken verbatim from the
    frozen anchors.
    """

    def __init__(self, client, anchors: dict, model: str = "gpt-5.5-2026-04-23",
                 reasoning_effort: str = "medium",
                 call_fn: Optional[Callable] = None,
                 allow_off_axis: bool = False):
        """allow_off_axis=True adds an explicit 'this fragment is not about this
        property at all' escape hatch. Measured 2026-09-01: without it, off-axis
        rejection drops from 12/12 (binary probe) to 9/12, because a forced choice
        among five bands cannot express 'none of these' and maps negative-sounding
        irrelevant quotes onto the low band. That is the dangerous failure for the
        flag -- it can manufacture unanimity out of unrelated evidence."""
        self._client = client
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._call_fn = call_fn
        self._allow_off_axis = allow_off_axis
        self._dims = {}
        for d in anchors["dimensions"]:
            self._dims[d["key"]] = {
                "measures": d["measures"],
                "bands": [(b["value"], b["reads_as"], b["text"]) for b in d["bands"]],
            }

    def probe(self, quotes: Sequence[str], dimension: str) -> list[Optional[bool]]:
        if not quotes:
            return []
        spec = self._dims[dimension]
        band_values = [b[0] for b in spec["bands"]]
        schema = {
            "type": "object",
            "properties": {
                "answers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer"},
                            **({"describes_this_property": {"type": "boolean"}}
                               if self._allow_off_axis else {}),
                            "best_match": {"type": "number", "enum": band_values},
                        },
                        "required": (["index", "describes_this_property", "best_match"]
                                     if self._allow_off_axis else ["index", "best_match"]),
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["answers"],
            "additionalProperties": False,
        }
        desc = "\n".join(f"  {v} ({reads_as}): {text}"
                         for v, reads_as, text in spec["bands"])
        listing = "\n".join(f"{i}. \"{q}\"" for i, q in enumerate(quotes))
        prompt = (
            "You are matching isolated text fragments to whichever of several written "
            "descriptions fits best. This is a text-matching task, not an evaluation of "
            "any organization, and no organization is identified.\n\n"
            f"The underlying property being described is: {spec['measures']}\n\n"
            f"DESCRIPTIONS:\n{desc}\n\n"
            + ("For each fragment, FIRST decide whether it describes the property above "
               "at all. Many fragments describe some entirely different property; for "
               "those set describes_this_property to false. Only if it does describe "
               "this property, choose the ONE description it best matches. "
               if self._allow_off_axis else
               "For each fragment below, choose the ONE description it best matches. ")
            + "If a fragment describes both extremes at once, or sits between them, choose "
            "the middle description -- do not choose an extreme because part of the "
            "fragment resembles it. Judge each fragment on its own words.\n\n"
            f"FRAGMENTS:\n{listing}"
        )
        messages = [{"role": "user", "content": prompt}]

        if self._call_fn is not None:
            response = self._call_fn(messages, schema)
        else:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                reasoning_effort=self._reasoning_effort,
                response_format={"type": "json_schema", "json_schema": {
                    "name": "band_choice", "strict": True, "schema": schema}},
            )
        parsed = json.loads(response.choices[0].message.content)
        out: list[Optional[bool]] = [None] * len(quotes)
        for a in parsed["answers"]:
            i = a["index"]
            if 0 <= i < len(quotes):
                if self._allow_off_axis and not a.get("describes_this_property", True):
                    out[i] = False
                else:
                    out[i] = (float(a["best_match"]) == FLOOR_BAND)
        return out


def flag_dimension(
    *,
    packet_id: str,
    dimension: str,
    score: Optional[float],
    quotes: Sequence[str],
    verified_map: dict[str, bool],
    probe: BandProbe,
    source_map: Optional[dict[str, Optional[str]]] = None,
) -> ExtremityFlag:
    """Flag one (packet, dimension) cell.

    Only VERIFIED quotes count. An unverified quote means the model garbled or
    invented it; a flag grounded on unverifiable text would be worse than no flag,
    which is the same reasoning noncompany_support() already applies upstream.
    """
    source_map = source_map or {}
    if score is None:
        # The model recorded insufficient evidence (anchors v3.1+). There is no score to sit
        # above the floor, so there is nothing to flag -- and no probe call is spent finding
        # that out.
        return ExtremityFlag(
            packet_id=packet_id, dimension=dimension, score=None,
            n_verified=0, n_matching_floor=0, n_not_matching=0, flag=None, severity=None,
            rationale="Insufficient evidence recorded; no score, so no floor to correct.",
            probes=[],
        )
    verified_quotes = [q for q in quotes if verified_map.get(q)]
    results = probe.probe(verified_quotes, dimension) if verified_quotes else []

    probes = [
        QuoteProbe(quote=q, dimension=dimension, matches_floor_band=m,
                   verified=True, source_tag=source_map.get(q))
        for q, m in zip(verified_quotes, results)
    ]
    # unverified quotes are recorded but never counted
    probes += [QuoteProbe(quote=q, dimension=dimension, matches_floor_band=None,
                          verified=False, source_tag=source_map.get(q))
               for q in quotes if not verified_map.get(q)]

    n_verified = len(verified_quotes)
    n_matching = sum(1 for m in results if m is True)
    n_not = sum(1 for m in results if m is False)

    flag = None
    severity = None

    if score <= FLOOR_BAND:
        rationale = (f"Score already at or below the floor band ({score}); nothing to "
                     f"correct. Flag exists only for scores the model placed above a "
                     f"floor its own evidence supports.")
    elif n_verified == 0:
        rationale = "No verified citations; cannot ground a flag on unverifiable text."
    elif n_matching < MIN_EXTREME_QUOTES:
        rationale = (f"Only {n_matching} verified citation(s) match the {FLOOR_BAND} band "
                     f"description (minimum {MIN_EXTREME_QUOTES}). Not unanimous enough.")
    elif n_not > 0:
        rationale = (f"{n_matching} citation(s) match the {FLOOR_BAND} band but {n_not} "
                     f"do not -- genuinely mixed evidence, which is what the middle bands "
                     f"are for. No flag.")
    else:
        flag = "FLOOR_SUSPECT"
        severity = "severe" if (score - FLOOR_BAND) >= 0.4 else "mild"
        rationale = (
            f"All {n_matching} verified citations match the {FLOOR_BAND} band description "
            f"for '{dimension}', with zero non-matching citations, yet the assigned score "
            f"is {score}. The model's own cited evidence supports the floor band it "
            f"structurally declines to use."
        )

    return ExtremityFlag(
        packet_id=packet_id, dimension=dimension, score=score,
        n_verified=n_verified, n_matching_floor=n_matching, n_not_matching=n_not,
        flag=flag, severity=severity, rationale=rationale, probes=probes,
    )


def flag_result(result, packet_text: str, probe: BandProbe,
                verify_result_fn: Callable, dimensions: Optional[Sequence[str]] = None
                ) -> list[ExtremityFlag]:
    """Flag every dimension of a ScorerResult.

    `verify_result_fn` is scorer_pipeline.verify_result, injected rather than
    imported so this module has no import-time dependency on the scorer and can be
    unit-tested standalone.
    """
    checks = verify_result_fn(result, packet_text)
    out = []
    for dim in result.dimensions:
        if dimensions and dim.dimension not in dimensions:
            continue
        dim_checks = [c for c in checks if c.dimension == dim.dimension]
        verified_map = {c.quote: c.matched for c in dim_checks}
        source_map = {c.quote: c.source_tag for c in dim_checks}
        out.append(flag_dimension(
            packet_id=result.packet_id, dimension=dim.dimension, score=dim.score,
            quotes=list(dim.evidence_quotes), verified_map=verified_map,
            probe=probe, source_map=source_map,
        ))
    return out


def validate_probe_escapes_reluctance(probe: BandProbe) -> dict:
    """THE GATING TEST. Run this before trusting anything above.

    Feeds the probe verified quotes from P-06/autonomy, which match the autonomy
    0.1 band description almost verbatim (that band's own text says "reviews cite
    micromanagement or rigid procedure"), alongside clear non-matches as controls.
    If the probe will not say True on the obvious matches, the floor reluctance has
    transferred to the probe task and this whole approach is dead.

    Returns a dict with pass/fail and the raw answers. A FAIL is a real finding and
    should be recorded, not worked around by loosening the test.
    """
    should_match = [
        "Typically works under close supervision.",
        "Follow a range of mandatory procedures",
        "they believe in top down micromanagement.",
    ]
    should_not_match = [
        "You act on instinct and initiative, not instruction.",
        "No politics, no process tax, no committees.",
    ]
    quotes = should_match + should_not_match
    answers = probe.probe(quotes, "autonomy")

    got_pos = answers[:len(should_match)]
    got_neg = answers[len(should_match):]
    passed = all(a is True for a in got_pos) and all(a is False for a in got_neg)
    return {
        "passed": passed,
        "expected_true": dict(zip(should_match, got_pos)),
        "expected_false": dict(zip(should_not_match, got_neg)),
        "interpretation": (
            "PASS: the probe classifies harsh evidence as matching the floor band, so "
            "the reluctance does not transfer to this task shape and the flag is usable."
            if passed else
            "FAIL: the probe would not confirm obvious floor-band matches (or confirmed "
            "obvious non-matches). Either the reluctance transfers to the probe task, or "
            "the probe framing is wrong. Do NOT use the flag until this is resolved; "
            "record the failure -- it is a real result about the model, not a bug to "
            "tune away."
        ),
    }
