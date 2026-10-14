"""The six-trait match service: a person against researched companies, through the
causal model, with the must-have / unknown / mixed gate layer on top.

Six-trait build, C6 (2026-10-13). Spec: docs/PRODUCT_DECISIONS.md §2, "The six-trait
match model"; plan: docs/superpowers/plans/2026-10-13-companylens-six-trait.md (C6 and
the orchestrator ruling). What the routes in `solverah/api/v1/companies.py` call.

WHAT A READ IS
--------------
For one user and one company, six trait reads. Each read is built from the company's
SHARED trait record on that trait (`company_evidence_store.trait_records`, company scope,
research-derived) and the user's core score on it (through `assessment_store`, the D-01
doorway), plus the user's stated tolerance and must-have flag:

* known   -> scored normally. The read reports the DIRECTION ("more" / "less" of the
             trait than you prefer, from the sign of person - estimate), whether the gap
             is inside the user's flat zone, and `must_have`. A must-have broken on a
             known trait (outside the zone) FLAGS the company and sorts it LAST; it is
             never hidden.
* mixed   -> NEVER averaged. The record's `low_end` and `high_end` are each read as if
             they were the company, separately. If the worse of the two breaks a
             must-have that is a RISK flag, not a disqualification. The user sees both
             sides' paraphrased evidence and the scope/time explanation when there is one.
             For RANKING the worse end counts (conservative) -- see `_worst_case_z`.
* unknown -> excluded from the model through `env_missing`: no gap, no penalty, flagged.
             On a must-have it becomes an Investigate step with interview questions
             (`company_match_content`).

Coverage is always reported as counts (known, mixed, unknown, of 6). Fewer than 3 known
traits is `not_enough_evidence`: no ranking position, listed after the ranked companies,
with what is missing.

THE ZONE
--------
A user who answered the tolerance step gets `trait_preferences.flat_zones(prefs)`. A user
who has NOT answered gets `{d: (0.15, 0.15)}` for all six -- the hinge at the floor -- and
never None (orchestrator ruling 2026-10-13: "unanswered = today's behaviour" is the
Situation Report's rule, the only surface with a "today"; CompanyLens is new and serves
the hinge). Gap convention here is match_core's: gap = person - env; gap > 0 means the
company offers LESS than the user prefers and reads the UNDER zone.

RANKING, AND WHAT NEVER REACHES THE WIRE
----------------------------------------
Companies are ordered by the model's linear predictor z (`match_core.point_z`), the
weights coming from the SAME source rule as `situation_report_service._dimension_weights`
(`SOLVERAH_MODEL_WEIGHTS_SOURCE`: unset or "priors" reads priors.yaml and needs no
`model_run` row -- production never seeds one; "run" reads the latest model_run through
`match_scoring.load_run_weights`, no fallback). z, any probability, any estimate, any
confidence number and the person's scores stay in this module. The response carries
labels, counts, dates and flags only -- tests/test_company_lens_api.py walks every
response for a float, a percentage or a key that looks like a score.

Ranking order: ranked companies first, those with a must-have break last among them,
then by z descending, then id; `not_enough_evidence` companies after all ranked ones,
by name. The order IS the output; `rank` is a 1-based position among ranked companies.

MIXED TRAITS IN THE RANKING (`_worst_case_z`)
---------------------------------------------
z is additive over dimensions (one `mag` and one `dir` term per dimension, see
match_core.outcome_logit), so the worst case over k mixed traits does not need 2^k
evaluations: evaluate once with every mixed trait at its `low_end` (the base), then once
per mixed trait with that trait at `high_end` and the others still at low_end; the
worst-case z is base + sum over mixed traits of min(0, z_high - z_base). Documented
here because it is the one place a reviewer would reach for an average.

NEXT STEP (v1 rule)
-------------------
One of Julie's categories per company (`company_match_content.NEXT_STEPS`):
`investigate` if any must-have is unknown, or mixed with a risk flag, or has a posting
disagreement; else `explore` if `not_enough_evidence`; else `decide`. `prepare`, `act`
and `dont_act_yet` are in the vocabulary for the Situation Report side of the loop and
are not produced here.

POSTING READ
------------
With `posting_id`, the posting's private role-scope records (`posting_trait_records`,
owner checked HERE before the store is asked) sit beside the company records. A
DISAGREEMENT is when both are known and either they fall on different sides of 0.5 or
their estimates differ by `POSTING_DISAGREEMENT_GAP` (0.3) or more. Posting records never
enter the ranking: they are one user's private read.
"""

from __future__ import annotations

import functools
import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

import company_evidence_store as store
from model import User, db
from solverah import pagination
from solverah.domain import trait_preferences
from solverah.domain.trait_preferences import TRAIT_KEYS
from solverah.repositories import company_repository
from solverah.services import company_match_content as content
from solverah.services.matching_service import MatchingResult

__all__ = [
    "FLAG_INVESTIGATE",
    "FLAG_MUST_HAVE_BREAK",
    "FLAG_RISK",
    "FLOOR_ZONE",
    "MIN_KNOWN_FOR_READ",
    "POSTING_DISAGREEMENT_GAP",
    "STATE_CORE_REQUIRED",
    "STATE_NOT_ENOUGH_EVIDENCE",
    "STATE_NOT_RESEARCHED",
    "STATE_NO_COMPANIES",
    "STATE_RANKED",
    "company_read",
    "matches",
    "posting_status",
    "research_status",
]

#: The hinge at the floor, for a user who has not answered the tolerance step.
FLOOR_ZONE = trait_preferences.ALIGNED_FLOOR

#: Below this many `known` traits a company gets no ranking position.
MIN_KNOWN_FOR_READ = 3

#: Company vs posting: both known and at least this far apart is a disagreement
#: (on top of "different sides of 0.5").
POSTING_DISAGREEMENT_GAP = 0.3

STATE_RANKED = "ranked"
STATE_NOT_ENOUGH_EVIDENCE = "not_enough_evidence"
STATE_CORE_REQUIRED = "core_required"
STATE_NO_COMPANIES = "no_companies"
STATE_NOT_RESEARCHED = "not_researched"

FLAG_MUST_HAVE_BREAK = "must_have_break"
FLAG_RISK = "risk"
FLAG_INVESTIGATE = "investigate"

DIRECTION_MORE = "more"
DIRECTION_LESS = "less"
DIRECTION_EVEN = "even"

#: How many paraphrases a known trait's read carries (newest first).
KNOWN_EVIDENCE_LIMIT = 3

_WEIGHTS_SOURCE_VAR = "SOLVERAH_MODEL_WEIGHTS_SOURCE"


# ---------------------------------------------------------------------------
# Weights: the Situation Report's source rule, for the full nested weights
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _priors_weights():
    """(cfg, nested weights at the prior means) from priors.yaml. Needs no database row;
    this is what production serves. Cached: the file never changes under a process."""
    import match_scoring

    cfg, pri = match_scoring.load()
    return cfg, match_scoring.weights_from_priors(cfg, pri)


_run_weights_cache: Dict[str, Any] = {"run_key": None, "value": None}


def _run_weights():
    """(cfg, nested weights) from the latest `model_run`, re-checked per call so a new
    run reaches the next request. No fallback (D-07): no run raises MatchModelError."""
    import match_scoring

    cfg, _ = match_scoring.load()
    run = match_scoring.current_run(db)
    run_key = (run.id, run.trained_at)
    if _run_weights_cache["run_key"] != run_key:
        _, weights = match_scoring.load_run_weights(db, run=run, cfg=cfg)
        _run_weights_cache["run_key"] = run_key
        _run_weights_cache["value"] = (cfg, weights)
    return _run_weights_cache["value"]


def _weights():
    """The same rule as `situation_report_service._dimension_weights`, returning the
    FULL nested weights `match_core.point_z` takes rather than the per-dimension means."""
    source = os.environ.get(_WEIGHTS_SOURCE_VAR) or "priors"
    if source == "priors":
        return _priors_weights()
    if source == "run":
        return _run_weights()
    raise ValueError(
        f"{_WEIGHTS_SOURCE_VAR}={source!r} is not valid -- must be 'priors' or 'run'"
    )


# ---------------------------------------------------------------------------
# Person side (through the doorway; never on the wire)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Person:
    scores: Dict[str, float]
    zones: Dict[str, Tuple[float, float]]
    must_haves: frozenset
    answered: bool


def _person_side(user_id: int) -> Optional[_Person]:
    """The user's six core scores, flat zones and must-haves, or None without core."""
    import assessment_store

    scores = assessment_store.get_dimension_scores(user_id)
    if scores is None or any(k not in scores for k in TRAIT_KEYS):
        return None
    prefs = assessment_store.get_trait_preferences(db, user_id)
    zones = trait_preferences.flat_zones(prefs)
    answered = zones is not None
    if zones is None:
        zones = {k: (FLOOR_ZONE, FLOOR_ZONE) for k in TRAIT_KEYS}
    return _Person(
        scores={k: float(scores[k]) for k in TRAIT_KEYS},
        zones=zones,
        must_haves=trait_preferences.must_have_keys(prefs),
        answered=answered,
    )


# ---------------------------------------------------------------------------
# One trait, one company
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _EndRead:
    """How one company-side value (a known estimate, or one end of a mixed record)
    sits against the person. `estimate` stays internal."""

    estimate: float
    direction: str
    within_tolerance: bool


@dataclass
class _TraitRead:
    dimension: str
    status: str
    must_have: bool
    record: Optional[store.TraitRecordView]
    read: Optional[_EndRead] = None         # known
    low: Optional[_EndRead] = None          # mixed
    high: Optional[_EndRead] = None         # mixed
    flag: Optional[str] = None
    direction_pref: str = content.PREFERS_MORE

    @property
    def direction(self) -> Optional[str]:
        return None if self.read is None else self.read.direction

    @property
    def within_tolerance(self) -> Optional[bool]:
        return None if self.read is None else self.read.within_tolerance


def _end_read(person_score: float, estimate: float, zone: Tuple[float, float]) -> _EndRead:
    """Direction and tolerance for one company-side value. The gap is match_core's
    (person snapped onto the company lattice, then person - env), so what the user is
    told agrees with what the model charged."""
    from match_core import fit_gap

    gap = float(fit_gap(person_score, estimate))
    if gap > 0:
        direction, zone_side = DIRECTION_LESS, zone[0]
    elif gap < 0:
        direction, zone_side = DIRECTION_MORE, zone[1]
    else:
        direction, zone_side = DIRECTION_EVEN, zone[0]
    within = abs(gap) <= float(zone_side) + 1e-12
    return _EndRead(estimate=float(estimate), direction=direction, within_tolerance=within)


def _trait_read(
    dimension: str, record: Optional[store.TraitRecordView], person: _Person
) -> _TraitRead:
    must_have = dimension in person.must_haves
    status = "unknown" if record is None else record.status
    read = _TraitRead(
        dimension=dimension,
        status=status,
        must_have=must_have,
        record=record,
        direction_pref=content.direction_for_person(person.scores[dimension]),
    )
    zone = person.zones[dimension]
    pscore = person.scores[dimension]
    if status == "known":
        read.read = _end_read(pscore, record.estimate, zone)
        if must_have and not read.read.within_tolerance:
            read.flag = FLAG_MUST_HAVE_BREAK
    elif status == "mixed":
        read.low = _end_read(pscore, record.low_end, zone)
        read.high = _end_read(pscore, record.high_end, zone)
        if must_have and not (read.low.within_tolerance and read.high.within_tolerance):
            read.flag = FLAG_RISK
    else:
        if must_have:
            read.flag = FLAG_INVESTIGATE
    return read


# ---------------------------------------------------------------------------
# One company: six reads, coverage, flags, next step
# ---------------------------------------------------------------------------

@dataclass
class _CompanyEval:
    company_id: int
    name: Optional[str]
    slug: Optional[str]
    stage_size: Optional[int]
    reads: Dict[str, _TraitRead]
    conf: Dict[str, Any]                   # raw confounder values, None = missing
    z: Optional[float] = None              # worst-case z; None when not rankable
    rank: Optional[int] = None
    posting_disagreements: List[str] = field(default_factory=list)

    @property
    def known(self) -> List[str]:
        return [k for k in TRAIT_KEYS if self.reads[k].status == "known"]

    @property
    def mixed(self) -> List[str]:
        return [k for k in TRAIT_KEYS if self.reads[k].status == "mixed"]

    @property
    def unknown(self) -> List[str]:
        return [k for k in TRAIT_KEYS if self.reads[k].status == "unknown"]

    @property
    def rankable(self) -> bool:
        return len(self.known) >= MIN_KNOWN_FOR_READ

    @property
    def state(self) -> str:
        return STATE_RANKED if self.rankable else STATE_NOT_ENOUGH_EVIDENCE

    @property
    def must_have_break(self) -> bool:
        return any(r.flag == FLAG_MUST_HAVE_BREAK for r in self.reads.values())

    def flag_counts(self) -> Dict[str, int]:
        flags = [r.flag for r in self.reads.values()]
        return {
            "must_have_breaks": flags.count(FLAG_MUST_HAVE_BREAK),
            "risks": flags.count(FLAG_RISK),
            "investigate": flags.count(FLAG_INVESTIGATE),
        }

    def coverage(self) -> Dict[str, int]:
        return {
            "known": len(self.known),
            "mixed": len(self.mixed),
            "unknown": len(self.unknown),
            "total": len(TRAIT_KEYS),
        }


def _stage_size(headcount: Optional[int], conf: Dict[str, Any]) -> Optional[int]:
    """The 1..5 band: from the company's raw headcount when it has one (the same cut
    `set_company_size` writes), else from a stored stage_size confounder, else None."""
    if headcount is not None:
        return store.stage_size_for_headcount(int(headcount))
    value = conf.get("stage_size")
    if value is None:
        return None
    try:
        band = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return band if 1 <= band <= 5 else None


def _company_eval(
    company_row, records: Sequence[store.TraitRecordView], conf: Dict[str, Any],
    person: _Person,
) -> _CompanyEval:
    by_dim = {r.dimension_key: r for r in records if r.scope == "company"}
    reads = {k: _trait_read(k, by_dim.get(k), person) for k in TRAIT_KEYS}
    return _CompanyEval(
        company_id=company_row.id,
        name=company_row.name,
        slug=company_row.slug,
        stage_size=_stage_size(getattr(company_row, "headcount", None), conf),
        reads=reads,
        conf=conf,
    )


def _next_step(ev: _CompanyEval) -> Dict[str, str]:
    """The v1 rule (module docstring). The reason names the trait that decided it."""
    for k in TRAIT_KEYS:
        read = ev.reads[k]
        if not read.must_have:
            continue
        label = content.TRAIT_LABELS[k]
        if read.status == "unknown":
            return {
                "category": "investigate",
                "reason": "%s is a must-have for you and we could not read it here." % label,
            }
        if read.flag == FLAG_RISK:
            return {
                "category": "investigate",
                "reason": "%s is a must-have for you and the evidence here is split." % label,
            }
        if k in ev.posting_disagreements:
            return {
                "category": "investigate",
                "reason": "%s is a must-have for you and the posting reads differently "
                          "from the company." % label,
            }
    if not ev.rankable:
        return {
            "category": "explore",
            "reason": "Not enough evidence to read this company on at least %d of the six "
                      "traits." % MIN_KNOWN_FOR_READ,
        }
    return {"category": "decide", "reason": "Enough is known to weigh this one up."}


# ---------------------------------------------------------------------------
# Ranking: z through match_core, worst case over mixed traits
# ---------------------------------------------------------------------------

def _conf_rows(cfg, evals: Sequence[_CompanyEval], row_evals: Sequence[int]):
    """Raw confounder arrays plus the missing mask, one entry per z row."""
    from match_core import active

    conf_raw: Dict[str, list] = {}
    conf_missing: Dict[str, list] = {}
    for c in active(cfg["confounders"]):
        if not c.get("measurable"):
            continue
        key = c["key"]
        values, missing = [], []
        for idx in row_evals:
            ev = evals[idx]
            value = ev.stage_size if key == "stage_size" else ev.conf.get(key)
            if c.get("kind") == "categorical":
                ok = value in c.get("levels", [])
                values.append(value if ok else None)
                missing.append(not ok)
            else:
                try:
                    number = None if value is None else float(value)
                except (TypeError, ValueError):
                    number = None
                values.append(math.nan if number is None else number)
                missing.append(number is None)
        conf_raw[key] = (
            np.asarray(values, dtype=object) if c.get("kind") == "categorical"
            else np.asarray(values, dtype=float)
        )
        conf_missing[key] = np.asarray(missing, dtype=bool)
    return conf_raw, conf_missing


def _worst_case_z(evals: Sequence[_CompanyEval], person: _Person,
                  cfg_weights: Optional[Tuple[Any, Any]] = None) -> None:
    """Fill `ev.z` for every rankable company in ONE point_z call. See the module
    docstring for why the worst case over mixed traits is base + sum of min(0, delta).

    `cfg_weights`: an explicit (cfg, nested weights) pair in place of `_weights()`.
    Serving never passes it; `causal_graph/v1_model/sensitivity.py` does, so the
    sensitivity test ranks through THIS function with a nudged penalty table rather
    than through a second copy of the ranking."""
    from match_core import point_z

    rankable = [i for i, ev in enumerate(evals) if ev.rankable]
    if not rankable:
        return
    cfg, weights = _weights() if cfg_weights is None else cfg_weights

    # Row plan: for each rankable company, a base row (mixed at low_end) then one
    # variant row per mixed trait (that trait at high_end).
    row_evals: List[int] = []
    row_variant: List[Optional[str]] = []
    for i in rankable:
        row_evals.append(i)
        row_variant.append(None)
        for k in evals[i].mixed:
            row_evals.append(i)
            row_variant.append(k)
    n = len(row_evals)

    env: Dict[str, np.ndarray] = {}
    env_missing: Dict[str, np.ndarray] = {}
    for k in TRAIT_KEYS:
        col = np.full(n, np.nan, dtype=float)
        mask = np.zeros(n, dtype=bool)
        for r, (i, variant) in enumerate(zip(row_evals, row_variant)):
            read = evals[i].reads[k]
            if read.status == "known":
                col[r] = read.read.estimate
            elif read.status == "mixed":
                col[r] = read.high.estimate if variant == k else read.low.estimate
            else:
                mask[r] = True
        env[k] = col
        if mask.any():
            env_missing[k] = mask
    person_arr = {k: np.full(n, person.scores[k], dtype=float) for k in TRAIT_KEYS}
    conf_raw, conf_missing = _conf_rows(cfg, evals, row_evals)

    z = point_z(
        person_arr, env, conf_raw, cfg, weights,
        conf_missing=conf_missing or None,
        flat_zones=dict(person.zones),
        env_missing=env_missing or None,
    )

    r = 0
    while r < n:
        i = row_evals[r]
        base = float(z[r])
        worst = base
        r += 1
        while r < n and row_evals[r] == i and row_variant[r] is not None:
            worst += min(0.0, float(z[r]) - base)
            r += 1
        evals[i].z = worst


def _order(evals: List[_CompanyEval]) -> List[_CompanyEval]:
    ranked = [ev for ev in evals if ev.rankable]
    unranked = [ev for ev in evals if not ev.rankable]
    ranked.sort(key=lambda ev: (ev.must_have_break, -ev.z, ev.company_id))
    unranked.sort(key=lambda ev: ((ev.name or "").lower(), ev.company_id))
    for position, ev in enumerate(ranked, start=1):
        ev.rank = position
    return ranked + unranked


# ---------------------------------------------------------------------------
# Serialisation: labels, counts, dates, flags. No numbers that are scores.
# ---------------------------------------------------------------------------

def _date(value) -> Optional[str]:
    return None if value is None else value.isoformat()


def _item_side(item: store.EvidenceItemView) -> Optional[str]:
    if item.abstained or item.score is None:
        return None
    if item.score < 0.5:
        return "low"
    if item.score > 0.5:
        return "high"
    return "middle"


def _evidence_item(item: store.EvidenceItemView) -> Dict[str, Any]:
    """Paraphrase, source type, scope, dates, url. Never the excerpt, never the score."""
    return {
        "paraphrase": item.paraphrase,
        "source_type": item.source_type,
        "scope": item.scope,
        "scope_label": item.scope_label,
        "published_at": _date(item.published_at),
        "source_url": item.source_url,
        "abstained": bool(item.abstained),
    }


def _evidence_summary(record: store.TraitRecordView, items) -> Dict[str, Any]:
    return {
        "count": int(record.evidence_count),
        "abstained": int(record.abstain_count),
        "first_dated": _date(record.first_dated),
        "last_dated": _date(record.last_dated),
        "source_types": sorted({i.source_type for i in items}),
    }


def _end_body(end: Optional[_EndRead]) -> Optional[Dict[str, Any]]:
    if end is None:
        return None
    return {"direction": end.direction, "within_tolerance": end.within_tolerance}


def _split_explanation(record: store.TraitRecordView) -> Optional[str]:
    if record.split_explained_by == "scope":
        return ("The split follows where the evidence comes from: different parts of the "
                "company describe different things.")
    if record.split_explained_by == "time":
        if record.status == "known":
            # agg-v2 (C5b, Julie ask 4 PROVISIONAL): a time split whose recent side is
            # well supported reads as known in the recent direction.
            return ("This seems to have changed recently: the read follows the recent "
                    "evidence, and older evidence pointed the other way.")
        return ("The split follows time: recent evidence says one thing, older evidence "
                "another.")
    return None


def _trait_body(read: _TraitRead, *, with_evidence: bool) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "dimension": read.dimension,
        "label": content.TRAIT_LABELS[read.dimension],
        "low_pole": content.TRAIT_POLES[read.dimension][0],
        "high_pole": content.TRAIT_POLES[read.dimension][1],
        "status": read.status,
        "must_have": read.must_have,
        "direction": read.direction,
        "within_tolerance": read.within_tolerance,
        "flag": read.flag,
    }
    if not with_evidence:
        return body
    body.update({
        "evidence": None,
        "scope_note": None,
        "mixed": None,
        "paraphrases": [],
        "explanation": None,
        "questions": [],
    })
    record = read.record
    if record is not None:
        items = store.items_for_record(db, record.id)
        body["evidence"] = _evidence_summary(record, items)
        body["scope_note"] = _split_explanation(record)
        if read.status == "mixed":
            body["mixed"] = {
                "low_end": {
                    **_end_body(read.low),
                    "evidence": [_evidence_item(i) for i in items if _item_side(i) == "low"],
                },
                "high_end": {
                    **_end_body(read.high),
                    "evidence": [_evidence_item(i) for i in items if _item_side(i) == "high"],
                },
                "explanation": _split_explanation(record),
            }
        else:
            scored = [i for i in items if not i.abstained]
            body["paraphrases"] = [_evidence_item(i) for i in scored[:KNOWN_EVIDENCE_LIMIT]]
    if read.status in (content.STATUS_UNKNOWN, content.STATUS_MIXED):
        body["explanation"] = content.explanation(
            read.dimension, read.status, read.direction_pref
        )
        if read.must_have:
            body["questions"] = content.interview_questions(
                read.dimension, read.status, read.direction_pref
            )
    return body


def _must_have_reads(ev: _CompanyEval) -> List[Dict[str, Any]]:
    return [
        _trait_body(ev.reads[k], with_evidence=False)
        for k in TRAIT_KEYS if ev.reads[k].must_have
    ]


def research_status(run: Optional[store.ResearchRunView], company_row=None) -> Optional[Dict[str, Any]]:
    """The run view as the wire shows it. No cost, no model string."""
    if run is None:
        return None
    body = {
        "run_id": run.id,
        "company_id": run.company_id,
        "status": run.status,
        "error": run.error,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }
    if company_row is not None:
        body["company"] = {
            "id": company_row.id, "name": company_row.name, "slug": company_row.slug,
        }
    return body


def posting_status(posting: store.JobPostingView, *, has_read: bool) -> Dict[str, Any]:
    return {
        "id": posting.id,
        "company_id": posting.company_id,
        "title": posting.title,
        "status": posting.status,
        "created_at": posting.created_at.isoformat() if posting.created_at else None,
        "has_read": has_read,
    }


def _entry(ev: _CompanyEval, research: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "id": ev.company_id,
        "name": ev.name,
        "slug": ev.slug,
        "state": ev.state,
        "rank": ev.rank,
        "coverage": ev.coverage(),
        "flags": ev.flag_counts(),
        "next_step": _next_step(ev),
        "must_have_reads": _must_have_reads(ev),
        "missing": ev.unknown,
        "size_note": content.size_note(ev.stage_size),
        "research": research,
    }


# ---------------------------------------------------------------------------
# Evaluate a set of companies for one user
# ---------------------------------------------------------------------------

def _company_rows(company_ids: Sequence[int]):
    from model import Company

    if not company_ids:
        return {}
    rows = (
        db.session.query(Company.id, Company.name, Company.slug, Company.headcount)
        .filter(Company.id.in_(list(company_ids)))
        .all()
    )
    return {row.id: row for row in rows}


def _evaluate(company_ids: Sequence[int], person: _Person) -> List[_CompanyEval]:
    rows = _company_rows(company_ids)
    records = store.shared_records_by_company(db, company_ids, scope="company")
    conf = store.confounder_values(db, company_ids)
    evals = [
        _company_eval(rows[cid], records.get(cid, ()), conf.get(cid, {}), person)
        for cid in company_ids if cid in rows
    ]
    _worst_case_z(evals, person)
    return evals


# ---------------------------------------------------------------------------
# GET /me/matches
# ---------------------------------------------------------------------------

def matches(user: User, *, cursor: Optional[str], limit: Any) -> MatchingResult:
    """Every company with shared records, ranked for this user, one page at a time.

    `core_required` when the user has no current core sitting; `no_companies` when
    nothing has been researched yet. The cursor carries the company id and its position
    in the ranking (an integer index, never a score); a ranking that shifts between
    pages continues from the position, which terminates.
    """
    after = pagination.decode_cursor(cursor)
    page_size = pagination.resolve_limit(limit)

    person = _person_side(user.id)
    if person is None:
        return MatchingResult(status=200, body={
            "state": STATE_CORE_REQUIRED, "data": [], "next_cursor": None,
            "total_companies": 0, "preferences_answered": False,
        })

    company_ids = store.companies_with_shared_records(db)
    if not company_ids:
        return MatchingResult(status=200, body={
            "state": STATE_NO_COMPANIES, "data": [], "next_cursor": None,
            "total_companies": 0, "preferences_answered": person.answered,
        })

    ordered = _order(_evaluate(company_ids, person))
    position = {ev.company_id: index for index, ev in enumerate(ordered)}

    def _key(ev: _CompanyEval) -> Dict[str, Any]:
        return {"id": ev.company_id, "pos": position[ev.company_id]}

    def _follows(ev: _CompanyEval, key: Dict[str, Any]) -> bool:
        wanted = key.get("pos")
        return isinstance(wanted, int) and position[ev.company_id] > wanted

    window, next_cursor = pagination.page(
        ordered, limit=page_size, after=after, key_of=_key, follows=_follows
    )
    runs = {ev.company_id: store.latest_research_run(db, ev.company_id) for ev in window}
    return MatchingResult(status=200, body={
        "state": STATE_RANKED,
        "data": [_entry(ev, research_status(runs[ev.company_id])) for ev in window],
        "next_cursor": next_cursor,
        "total_companies": len(ordered),
        "preferences_answered": person.answered,
    })


# ---------------------------------------------------------------------------
# GET /companies/<id>/read[?posting_id=]
# ---------------------------------------------------------------------------

def _posting_read(ev: _CompanyEval, posting: store.JobPostingView, person: _Person) -> Dict[str, Any]:
    """The role-level records beside the company ones, and the disagreements."""
    records = {r.dimension_key: r for r in store.posting_trait_records(db, posting.id)}
    traits: Dict[str, Any] = {}
    disagreements: List[str] = []
    for k in TRAIT_KEYS:
        record = records.get(k)
        read = _trait_read(k, record, person)
        body = _trait_body(read, with_evidence=False)
        # A posting is one user's private read of a role, not the company: the
        # company's reads carry the flags and the posting carries `disagrees`.
        body["flag"] = None
        body["questions"] = []
        body["explanation"] = None
        body["paraphrases"] = []
        body["disagrees"] = False
        if record is not None:
            items = store.items_for_record(db, record.id)
            body["paraphrases"] = [
                _evidence_item(i) for i in items if not i.abstained
            ][:KNOWN_EVIDENCE_LIMIT]
            body["evidence"] = _evidence_summary(record, items)
        else:
            body["evidence"] = None
        company_read = ev.reads[k]
        if record is not None and record.status == "known" and company_read.status == "known":
            a, b = float(company_read.read.estimate), float(record.estimate)
            if ((a < 0.5) != (b < 0.5) and 0.5 not in (a, b)) or abs(a - b) >= POSTING_DISAGREEMENT_GAP:
                body["disagrees"] = True
                disagreements.append(k)
        traits[k] = body
    ev.posting_disagreements = disagreements
    return {
        **posting_status(posting, has_read=bool(records)),
        "traits": [traits[k] for k in TRAIT_KEYS],
        "disagreements": disagreements,
    }


def company_read(user: User, company_id: int, *, posting_id: Optional[int] = None) -> MatchingResult:
    """The full per-trait read of one company for this user."""
    rows = _company_rows([company_id])
    if company_id not in rows:
        return MatchingResult(status=404, body={"error": "Company not found"})
    company_row = rows[company_id]
    run = store.latest_research_run(db, company_id)

    posting = None
    if posting_id is not None:
        posting = _owned_posting(user.id, posting_id)
        if posting is None or posting.company_id != company_id:
            return MatchingResult(status=404, body={"error": "Job posting not found"})

    person = _person_side(user.id)
    base = {
        "company": {
            "id": company_row.id, "name": company_row.name, "slug": company_row.slug,
            "size_band": None, "size_note": None,
        },
        "research": research_status(run),
        "preferences_answered": False if person is None else person.answered,
    }
    if person is None:
        return MatchingResult(status=200, body={"state": STATE_CORE_REQUIRED, **base})

    records = store.shared_records_by_company(db, [company_id], scope="company")
    if not records.get(company_id):
        return MatchingResult(status=200, body={"state": STATE_NOT_RESEARCHED, **base})

    [ev] = _evaluate([company_id], person)
    base["company"]["size_band"] = ev.stage_size
    base["company"]["size_note"] = content.size_note(ev.stage_size)
    posting_body = None if posting is None else _posting_read(ev, posting, person)
    return MatchingResult(status=200, body={
        "state": ev.state,
        **base,
        "coverage": ev.coverage(),
        "flags": ev.flag_counts(),
        "next_step": _next_step(ev),
        "missing": ev.unknown,
        "traits": [_trait_body(ev.reads[k], with_evidence=True) for k in TRAIT_KEYS],
        "posting": posting_body,
    })


def _owned_posting(user_id: int, posting_id: int) -> Optional[store.JobPostingView]:
    """The posting if it is this user's, else None -- the ownership check the store
    leaves to its caller."""
    for posting in store.job_postings_for_user(db, user_id):
        if posting.id == posting_id:
            return posting
    return None
