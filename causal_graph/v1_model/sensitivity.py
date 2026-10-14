"""sensitivity.py -- does nudging a penalty weight move the CompanyLens ranking?

PRODUCT_DECISIONS.md section 2, "What changes the weights, cheapest first", step (2):
nudge each weight, see whether rankings move. This is the cheapest check that exists
on Julie's elicited penalty table (priors.yaml): it needs no outcome data, no raters
and no live research run. It answers one question per weight -- if this number were
half again as big, or half as big, would people see a different top five? A weight
that cannot move a ranking is not worth another hour of anyone's time until outcome
data exists; a weight that moves rankings for many people is where the evidence
(blind raters, then outcomes) should go first.

WHAT IS NUDGED
--------------
Each active dimension's `mag` and `dir` weight (12 weights), one at a time, by
+NUDGE and -NUDGE of its own value (NUDGE = 0.5, i.e. +-50%). Two dir weights are
exactly 0 in the live table (autonomy, innovation: Julie's two answers were equal),
and a relative nudge of 0 is a no-op; for those the nudge is ABSOLUTE instead --
+-NUDGE times the same dimension's |mag| -- and the row is labelled so. Confounder
weights and the intercept are not nudged: a per-company constant cannot reorder
companies for one person differently from another, and the intercept cannot reorder
at all.

WHAT IS RANKED, AND HOW
-----------------------
The ranking is PRODUCTION's: `company_match_service._company_eval` (six trait reads
per company -- known / mixed / unknown, the zone, the must-have flag),
`_worst_case_z` (one `match_core.point_z` call per ranking: the hinge through
`flat_zones`, `env_missing` for unknown traits, the worse end of a mixed trait), and
`_order` (must-have breaks last, then z, then id). Only the weights are swapped, through
`_worst_case_z(cfg_weights=...)`. There is no second implementation here.

Only rankable companies (>= 3 known traits) enter the comparison; a
`not_enough_evidence` company has no position to move.

WHO IS RANKED FOR
-----------------
N_PEOPLE synthetic people, scores drawn uniformly from PERSON_LATTICE per trait with
a fixed seed, each run under three tolerance profiles:
  unanswered -> zone 0.15 both sides on every trait (the floor), no must-haves;
  typical    -> 1 step (0.25) both sides;
  wide       -> 2 steps (0.5) both sides.
In the typical and wide profiles a person carries 0, 1 or 2 must-have traits (drawn
once per person, p = 0.5 / 0.3 / 0.2). An unanswered user has none by definition.

WHICH COMPANIES
---------------
Two sets, reported separately:
  real      -> the six round-1 packets (P-01..P-06), every trait KNOWN at the mean of
               every scoring that exists for it: the three round-1 human raters
               (Solverah_IP/ground_truth/rater_app/returned/round1) and the five
               gpt-5.5 scorer-variance v2 runs (causal_graph/results/
               scorer_variance_v2). No round-2 draws exist yet (no live run has
               happened), so this is the best real set there is. Confounders are
               unknown for them (masked): the packets carry no comp posture or
               size band, and the industry levels' prior means are all 0 anyway.
  synthetic -> N_SYNTHETIC companies drawn from the anchor bands (match_core
               BAND_VALUES): most traits known, some mixed, some unknown, with
               drawn confounders. Clearly labelled; it exists because six real
               companies make a top-5 nearly meaningless (see the doc's limits).

WHAT "MATTERS" MEANS
--------------------
Per person and nudge: top-5 overlap with the baseline top five (|intersection|, k
capped at the number of ranked companies) and Kendall's tau-a between the two full
orderings. A person is FLAGGED when overlap < 4 (of 5) or tau < 0.8 -- the two
thresholds PRODUCT_DECISIONS names. A weight MATTERS for a company set when the share
of flagged people reaches MATTERS_SHARE (10%) under ANY profile and either nudge
direction. The share is the one knob the decision left open; 10% is chosen because a
ranking that changes for one person in ten is a product change, and it is written
into the output so the reader never has to guess it.

    python -m causal_graph.v1_model.sensitivity --out <path.json> [--table]

Every print is ASCII. Deterministic for a given seed (tests/test_sensitivity.py).
"""

from __future__ import annotations

import argparse
import copy
import csv
import datetime
import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import match_scoring  # noqa: E402,F401  -- installs causal_graph/v1_model on sys.path
from match_core import (  # noqa: E402
    BAND_VALUES,
    PERSON_LATTICE,
    active,
    load,
    weights_from_priors,
)
from solverah.domain.trait_preferences import (  # noqa: E402
    ALIGNED_FLOOR,
    STEP_SIZE,
    TRAIT_KEYS,
)

__all__ = [
    "MATTERS_SHARE",
    "NUDGE",
    "OVERLAP_FLOOR",
    "PROFILES",
    "TAU_FLOOR",
    "TOP_K",
    "Company",
    "kendall_tau",
    "load_real_companies",
    "main",
    "nudged_weights",
    "rank",
    "run",
    "synthetic_companies",
    "synthetic_people",
    "to_markdown",
    "top_k_overlap",
]

DIMS: Tuple[str, ...] = tuple(TRAIT_KEYS)

#: The relative nudge: each weight is tried at (1 - NUDGE) and (1 + NUDGE) times itself.
NUDGE = 0.5
#: Top-k overlap is measured on the first TOP_K ranked companies.
TOP_K = 5
#: A person is flagged when top-k overlap is below this many ...
OVERLAP_FLOOR = 4
#: ... or Kendall's tau is below this.
TAU_FLOOR = 0.8
#: A weight matters when at least this share of people is flagged (any profile, either
#: direction). Our choice; see the module docstring.
MATTERS_SHARE = 0.10

DEFAULT_SEED = 20261013
N_PEOPLE = 200
N_SYNTHETIC = 30

#: Tolerance profiles: steps on the person lattice, None = unanswered (the floor).
PROFILES: Dict[str, Optional[int]] = {"unanswered": None, "typical": 1, "wide": 2}

#: Must-have count per person (typical and wide profiles only).
MUST_HAVE_COUNT_P = (0.5, 0.3, 0.2)

INDUSTRY_LEVELS = ("tech", "finance", "healthcare", "retail", "other")

ROUND1_DIR = REPO_ROOT / "Solverah_IP" / "ground_truth" / "rater_app" / "returned" / "round1"
VARIANCE_V2_DIR = REPO_ROOT / "causal_graph" / "results" / "scorer_variance_v2"
PACKETS = ("P-01", "P-02", "P-03", "P-04", "P-05", "P-06")


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Company:
    """One company for the ranking. `traits` maps each of the six keys to
    ("known", estimate) | ("mixed", low_end, high_end) | ("unknown",). `conf` holds
    raw confounder values (None = missing, which the service masks)."""

    id: int
    name: str
    traits: Dict[str, tuple]
    conf: Dict[str, Any]
    source: str = ""

    def known_count(self) -> int:
        return sum(1 for k in DIMS if self.traits[k][0] == "known")


def _rater_scores(path: Path) -> Dict[str, Optional[float]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {s["dimension"]: s.get("score") for s in doc.get("scores", [])}


def _variance_scores(path: Path) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if not row.get("model", "").startswith("gpt-5.5"):
                continue
            score = row.get("score")
            if score in (None, ""):
                continue
            out.setdefault(row["dimension"], []).append(float(score))
    return out


def _variance_file(packet: str) -> Optional[Path]:
    compact = packet.replace("-", "")
    candidates = [
        VARIANCE_V2_DIR / f"runs_v2_gpt_55_2026_04_23_{packet}.csv",
        VARIANCE_V2_DIR / f"runs_v2_gpt55_{compact}.csv",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def load_real_companies(packets: Sequence[str] = PACKETS) -> List[Company]:
    """The six round-1 packets, each trait known at the mean of every scoring on file.
    Raises if a packet has no scoring at all (D-07: no silent empty set)."""
    companies = []
    for idx, packet in enumerate(packets, start=1):
        per_dim: Dict[str, List[float]] = {k: [] for k in DIMS}
        n_sources = 0
        for path in sorted(ROUND1_DIR.glob(f"{packet}_rater*.json")):
            n_sources += 1
            for k, score in _rater_scores(path).items():
                if k in per_dim and score is not None:
                    per_dim[k].append(float(score))
        variance = _variance_file(packet)
        if variance is not None:
            n_sources += 1
            for k, scores in _variance_scores(variance).items():
                if k in per_dim:
                    per_dim[k].extend(scores)
        if n_sources == 0:
            raise FileNotFoundError(f"no round-1 rater file or scorer-variance run for {packet}")
        traits = {}
        for k in DIMS:
            if not per_dim[k]:
                traits[k] = ("unknown",)
            else:
                traits[k] = ("known", round(float(np.mean(per_dim[k])), 6))
        companies.append(Company(
            id=idx, name=packet, traits=traits,
            conf={"stage_size": None, "comp": None, "industry": None},
            source=f"round-1 raters + scorer-variance v2 ({n_sources} sources)",
        ))
    return companies


def synthetic_companies(n: int = N_SYNTHETIC, seed: int = DEFAULT_SEED) -> List[Company]:
    """A labelled synthetic set drawn from the anchor bands. A known estimate is the
    mean of three band draws (an aggregate of the minimum three items); a mixed trait
    has one end in the low bands and one in the high bands; every company keeps at
    least three known traits so it is rankable."""
    rng = np.random.default_rng(seed)
    bands = np.asarray(BAND_VALUES, dtype=float)
    companies = []
    for idx in range(1, n + 1):
        n_not_known = int(rng.choice(4, p=[0.4, 0.3, 0.2, 0.1]))
        not_known = set(rng.choice(len(DIMS), size=n_not_known, replace=False).tolist())
        traits: Dict[str, tuple] = {}
        for j, k in enumerate(DIMS):
            if j in not_known and rng.random() < 0.6:
                low = float(rng.choice(bands[:2]))
                high = float(rng.choice(bands[3:]))
                traits[k] = ("mixed", low, high)
            elif j in not_known:
                traits[k] = ("unknown",)
            else:
                traits[k] = ("known", round(float(np.mean(rng.choice(bands, size=3))), 6))
        conf = {
            "stage_size": int(rng.integers(1, 6)),
            "comp": None if rng.random() < 0.25 else int(rng.integers(1, 6)),
            "industry": None if rng.random() < 0.15 else str(rng.choice(INDUSTRY_LEVELS)),
        }
        companies.append(Company(id=idx, name=f"S-{idx:02d}", traits=traits, conf=conf,
                                 source="synthetic (anchor bands)"))
    return companies


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------

def synthetic_people(n: int = N_PEOPLE, seed: int = DEFAULT_SEED) -> List[dict]:
    """{scores: {dim: lattice value}, must_haves: tuple of dims} per person."""
    rng = np.random.default_rng(seed + 1)
    lattice = np.asarray(PERSON_LATTICE, dtype=float)
    people = []
    for _ in range(n):
        scores = {k: float(rng.choice(lattice)) for k in DIMS}
        n_mh = int(rng.choice(3, p=MUST_HAVE_COUNT_P))
        must = tuple(DIMS[i] for i in sorted(rng.choice(len(DIMS), size=n_mh, replace=False).tolist()))
        people.append({"scores": scores, "must_haves": must})
    return people


def _zone_for(steps: Optional[int]) -> float:
    if steps is None:
        return ALIGNED_FLOOR
    return max(ALIGNED_FLOOR, steps * STEP_SIZE)


def _service():
    from solverah.services import company_match_service as cms
    return cms


def _person_for(cms, person: dict, steps: Optional[int]):
    zone = _zone_for(steps)
    return cms._Person(
        scores=dict(person["scores"]),
        zones={k: (zone, zone) for k in DIMS},
        must_haves=frozenset() if steps is None else frozenset(person["must_haves"]),
        answered=steps is not None,
    )


# ---------------------------------------------------------------------------
# Ranking through the service
# ---------------------------------------------------------------------------

_RECORD_STAMP = datetime.datetime(2026, 10, 13, tzinfo=datetime.timezone.utc)


def _records(company: Company):
    import company_evidence_store as store

    out = []
    for i, k in enumerate(DIMS):
        shape = company.traits[k]
        status = shape[0]
        out.append(store.TraitRecordView(
            id=company.id * 10 + i, company_id=company.id, job_posting_id=None,
            dimension_key=k, scope="company", scope_label=None, status=status,
            estimate=shape[1] if status == "known" else None,
            low_end=shape[1] if status == "mixed" else None,
            high_end=shape[2] if status == "mixed" else None,
            confidence=None, evidence_count=3 if status != "unknown" else 0,
            abstain_count=0 if status != "unknown" else 1,
            first_dated=None, last_dated=None, split_explained_by=None,
            aggregation_version="sensitivity", computed_at=_RECORD_STAMP,
        ))
    return out


def _evals(cms, companies: Sequence[Company], person) -> list:
    evals = []
    for c in companies:
        row = types.SimpleNamespace(id=c.id, name=c.name, slug=c.name.lower(), headcount=None)
        evals.append(cms._company_eval(row, _records(c), dict(c.conf), person))
    return evals


def _ranking(cms, evals: list, person, cfg, weights) -> List[int]:
    cms._worst_case_z(evals, person, cfg_weights=(cfg, weights))
    return [ev.company_id for ev in cms._order(evals) if ev.rankable]


def rank(companies: Sequence[Company], person_scores: Dict[str, float], cfg, weights, *,
         steps: Optional[int] = None, must_haves: Sequence[str] = ()) -> List[int]:
    """Company ids in production order for one person. Convenience for tests."""
    cms = _service()
    person = _person_for(cms, {"scores": person_scores, "must_haves": tuple(must_haves)}, steps)
    return _ranking(cms, _evals(cms, companies, person), person, cfg, weights)


# ---------------------------------------------------------------------------
# Nudges and metrics
# ---------------------------------------------------------------------------

def nudged_weights(weights, dim: str, feat: str, delta: float):
    """A deep copy with weights[dimensions][dim][feat].mean moved by `delta` of itself
    -- or, when that mean is exactly 0, by `delta` of the dimension's |mag| (absolute).
    Returns (weights, new_mean, mode) with mode "relative" or "absolute"."""
    out = copy.deepcopy(weights)
    leaf = out["dimensions"][dim][feat]
    base = float(leaf["mean"])
    if base != 0.0:
        leaf["mean"] = base * (1.0 + delta)
        return out, leaf["mean"], "relative"
    scale = abs(float(weights["dimensions"][dim]["mag"]["mean"]))
    leaf["mean"] = base + delta * scale
    return out, leaf["mean"], "absolute"


def top_k_overlap(a: Sequence[int], b: Sequence[int], k: int = TOP_K) -> int:
    return len(set(a[:k]) & set(b[:k]))


def kendall_tau(a: Sequence[int], b: Sequence[int]) -> float:
    """Kendall's tau-a between two strict orderings of the same items. 1.0 for a
    single item (nothing to disagree about)."""
    if set(a) != set(b):
        raise ValueError("orderings must rank the same items")
    n = len(a)
    if n < 2:
        return 1.0
    pos_b = {item: i for i, item in enumerate(b)}
    ranks_b = np.array([pos_b[item] for item in a])
    i, j = np.triu_indices(n, k=1)
    signs = np.sign(ranks_b[j] - ranks_b[i])
    return float(signs.sum() / len(signs))


def _flagged(overlap: int, k_effective: int, tau: float) -> bool:
    floor = OVERLAP_FLOOR - (TOP_K - k_effective)   # 4 of 5; 3 of 4; ...
    return overlap < floor or tau < TAU_FLOOR


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def _weight_names(cfg) -> List[Tuple[str, str]]:
    feats = cfg["settings"]["gap_features"]
    return [(d["key"], feat) for d in active(cfg["dimensions"]) for feat in feats]


def _summary(rows: List[Tuple[int, int, float, bool]]) -> dict:
    if not rows:
        return {"n": 0, "overlap_mean": None, "overlap_min": None, "tau_mean": None,
                "tau_min": None, "share_flagged": None}
    overlaps = np.array([r[0] for r in rows], dtype=float)
    taus = np.array([r[2] for r in rows], dtype=float)
    flags = np.array([r[3] for r in rows], dtype=bool)
    return {
        "n": int(len(rows)),
        "overlap_mean": round(float(overlaps.mean()), 4),
        "overlap_min": int(overlaps.min()),
        "tau_mean": round(float(taus.mean()), 4),
        "tau_min": round(float(taus.min()), 4),
        "share_flagged": round(float(flags.mean()), 4),
    }


def run(companies: Sequence[Company], people: Sequence[dict], cfg, weights, *,
        nudge: float = NUDGE, profiles: Optional[Dict[str, Optional[int]]] = None,
        label: str = "") -> dict:
    """The sensitivity of one company set to every dimension weight."""
    cms = _service()
    profiles = PROFILES if profiles is None else profiles
    names = _weight_names(cfg)
    deltas = ((-nudge, f"-{int(round(nudge * 100))}%"), (+nudge, f"+{int(round(nudge * 100))}%"))

    # rows[(dim, feat, delta_label, profile)] -> list of (overlap, k, tau, flagged)
    rows: Dict[tuple, list] = {}
    variants = {}
    for dim, feat in names:
        for delta, dlabel in deltas:
            w, value, mode = nudged_weights(weights, dim, feat, delta)
            variants[(dim, feat, dlabel)] = (w, value, mode)

    n_rankable = []
    for profile, steps in profiles.items():
        for person in people:
            p = _person_for(cms, person, steps)
            evals = _evals(cms, companies, p)
            base = _ranking(cms, evals, p, cfg, weights)
            n_rankable.append(len(base))
            k = min(TOP_K, len(base))
            for (dim, feat, dlabel), (w, _value, _mode) in variants.items():
                alt = _ranking(cms, evals, p, cfg, w)
                overlap = top_k_overlap(base, alt, TOP_K)
                tau = kendall_tau(base, alt)
                rows.setdefault((dim, feat, dlabel, profile), []).append(
                    (overlap, k, tau, _flagged(overlap, k, tau)))

    out_weights: Dict[str, Any] = {}
    for dim, feat in names:
        base_mean = float(weights["dimensions"][dim][feat]["mean"])
        entry: Dict[str, Any] = {"baseline_mean": round(base_mean, 6), "nudges": {}}
        max_share = 0.0
        for _delta, dlabel in deltas:
            w, value, mode = variants[(dim, feat, dlabel)]
            per_profile = {}
            pooled: list = []
            for profile in profiles:
                r = rows.get((dim, feat, dlabel, profile), [])
                per_profile[profile] = _summary(r)
                pooled.extend(r)
            nudge_entry = {"value": round(float(value), 6), "mode": mode,
                           "profiles": per_profile, "pooled": _summary(pooled)}
            entry["nudges"][dlabel] = nudge_entry
            for s in per_profile.values():
                if s["share_flagged"] is not None:
                    max_share = max(max_share, s["share_flagged"])
        entry["max_share_flagged"] = round(max_share, 4)
        entry["matters"] = bool(max_share >= MATTERS_SHARE)
        out_weights[f"{dim}.{feat}"] = entry

    return {
        "label": label,
        "n_companies": len(companies),
        "rankable_per_person_min": int(min(n_rankable)) if n_rankable else 0,
        "rankable_per_person_max": int(max(n_rankable)) if n_rankable else 0,
        "companies": [
            {"id": c.id, "name": c.name, "source": c.source,
             "traits": {k: list(c.traits[k]) for k in DIMS}, "conf": c.conf}
            for c in companies
        ],
        "weights": out_weights,
    }


def _priors_version() -> str:
    """The same content hash match_scoring stamps on the priors-only model run."""
    return match_scoring._priors_version()


def run_all(*, seed: int = DEFAULT_SEED, n_people: int = N_PEOPLE,
            n_synthetic: int = N_SYNTHETIC, nudge: float = NUDGE,
            include_real: bool = True) -> dict:
    cfg, pri = load()
    weights = weights_from_priors(cfg, pri)
    people = synthetic_people(n_people, seed)
    sets = {}
    if include_real:
        sets["real"] = run(load_real_companies(), people, cfg, weights, nudge=nudge,
                           label="real: six round-1 packets, traits at the mean of every scoring on file")
    sets["synthetic"] = run(synthetic_companies(n_synthetic, seed), people, cfg, weights,
                            nudge=nudge, label="synthetic: drawn from the anchor bands")
    return {
        "meta": {
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "seed": seed,
            "n_people": n_people,
            "nudge": nudge,
            "top_k": TOP_K,
            "overlap_floor": OVERLAP_FLOOR,
            "tau_floor": TAU_FLOOR,
            "matters_share": MATTERS_SHARE,
            "profiles": {name: {"steps": steps, "zone": _zone_for(steps)} for name, steps in PROFILES.items()},
            "must_have_count_p": list(MUST_HAVE_COUNT_P),
            "priors_version": _priors_version(),
        },
        "sets": sets,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def to_markdown(results: dict) -> str:
    """A plain table per company set: one row per weight, the flagged share per
    profile (worse of the two directions), the worst tau, and the verdict."""
    meta = results["meta"]
    lines = []
    lines.append("Threshold: a person is flagged when top-%d overlap < %d or tau < %.1f; a weight "
                 "matters when >= %d%% of people are flagged under any profile, either direction."
                 % (meta["top_k"], meta["overlap_floor"], meta["tau_floor"],
                    int(round(meta["matters_share"] * 100))))
    lines.append("")
    for set_name, data in results["sets"].items():
        # The JSON is written with sorted keys; read it back in the product's order.
        profiles = [p for p in PROFILES if p in meta["profiles"]] +                    [p for p in meta["profiles"] if p not in PROFILES]
        lines.append("### %s (%d companies; %d-%d rankable per person)"
                     % (set_name, data["n_companies"], data["rankable_per_person_min"],
                        data["rankable_per_person_max"]))
        lines.append("")
        header = ["weight", "value", "nudge"] + ["flagged " + p for p in profiles] + \
                 ["min tau", "min top-5", "verdict"]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
        ordered = sorted(data["weights"], key=lambda n: (
            DIMS.index(n.split(".")[0]) if n.split(".")[0] in DIMS else len(DIMS), n))
        for name in ordered:
            entry = data["weights"][name]
            modes = {n["mode"] for n in entry["nudges"].values()}
            mode = "abs" if modes == {"absolute"} else "rel"
            shares = []
            for p in profiles:
                s = max(n["profiles"][p]["share_flagged"] or 0.0 for n in entry["nudges"].values())
                shares.append("%.1f%%" % (s * 100))
            min_tau = min(n["pooled"]["tau_min"] for n in entry["nudges"].values()
                          if n["pooled"]["tau_min"] is not None)
            min_overlap = min(n["pooled"]["overlap_min"] for n in entry["nudges"].values()
                              if n["pooled"]["overlap_min"] is not None)
            verdict = "MATTERS" if entry["matters"] else "does not move rankings"
            lines.append("| %s | %+.3f | %s | %s | %.2f | %d | %s |"
                         % (name, entry["baseline_mean"], mode, " | ".join(shares),
                            min_tau, min_overlap, verdict))
        lines.append("")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--out", required=True, help="where to write the JSON results")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--people", type=int, default=N_PEOPLE)
    parser.add_argument("--synthetic", type=int, default=N_SYNTHETIC)
    parser.add_argument("--nudge", type=float, default=NUDGE)
    parser.add_argument("--no-real", action="store_true", help="skip the round-1 packet set")
    parser.add_argument("--table", action="store_true", help="print the markdown tables")
    args = parser.parse_args(argv)

    results = run_all(seed=args.seed, n_people=args.people, n_synthetic=args.synthetic,
                      nudge=args.nudge, include_real=not args.no_real)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    print("wrote %s" % out)
    if args.table:
        print(to_markdown(results))
    for set_name, data in results["sets"].items():
        matters = [n for n, e in data["weights"].items() if e["matters"]]
        print("%s: %d of %d weights matter: %s" % (set_name, len(matters), len(data["weights"]),
                                                   ", ".join(matters) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
