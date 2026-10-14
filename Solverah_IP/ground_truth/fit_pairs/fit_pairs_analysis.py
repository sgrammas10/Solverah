"""fit_pairs_analysis.py -- the pre-registered comparison of blind raters with the model.

Implements PREREG_FIT_PAIRS_2026-10-13.md, written and committed BEFORE any rater return or
model score exists. Do not edit the decision rules after data arrives; add an addendum.

Inputs
  pair_specs.json          design.py's output (the hook matching-model scores)
  pair_model_scores.json   matching-model's output, schema `fit_pairs_model_scores_v1`
  roster.json              who may rate; who is excluded and why
  returned/*.json          one file per rater, exported by the rater page

Order of operations (prereg section 5), each step able to stop the run:
  0. Cross-check the model's flags against the spec's weight-free gate restatement. A
     mismatch is a claim about the spec or the model, not about raters: stop and report.
  1. Eligibility. A return from a rater who set the weights is REFUSED (raises), never
     silently dropped: Julie (A) and Sebastian (D) are excluded by rule.
  2. Agreement between raters, first. Below the gate, no conclusion about the model.
  3. Raters vs the model: stratified Kendall tau-b inside blocks, per rater and for the
     consensus (median rating).
  4. Pre-registered contrasts and repeats.

Stdlib only. Every print is ASCII (cp1252 console).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

HERE = Path(__file__).resolve().parent

INSTRUMENT = "fit_pairs_v1"
MODEL_SCHEMA = "fit_pairs_model_scores_v1"
RATING_MIN, RATING_MAX = 1, 5

# --- decision thresholds (prereg section 6; sized by power_sim.py) ---------------------
MIN_RATERS = 3                 # eligible raters with enough data
MIN_BLOCKS_PER_RATER = 4       # complete blocks for a rater to count
GATE_INTER_RATER_TAU = 0.40    # mean pairwise rater-rater tau-b
DEFAULTS_STAND_TAU = 0.50      # consensus tau-b at or above: defaults stand
REVIEW_TAU = 0.20              # consensus tau-b below: open a weights review
MIN_RATERS_PER_PAIR = 2        # non-abstaining ratings for a pair to enter the consensus
Z_TIE = 1e-9                   # model z values closer than this are a tie


class AnalysisError(Exception):
    pass


class ExcludedRaterError(AnalysisError):
    """A return from someone who set the weights. Refused, loudly."""


# ---------------------------------------------------------------------------
# Loading and validation
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_spec(path: Path) -> tuple[dict[str, Any], str]:
    raw = Path(path).read_bytes()
    spec = json.loads(raw)
    if spec.get("schema") != "fit_pairs_spec_v1":
        raise AnalysisError("%s: not a fit_pairs_spec_v1 file" % path)
    return spec, hashlib.sha256(raw).hexdigest()


def load_roster(path: Path) -> dict[str, dict[str, Any]]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return {r["rater_id"]: r for r in doc["raters"]}


def is_eligible(entry: dict[str, Any]) -> bool:
    return bool(entry.get("eligible")) and not entry.get("sets_weights")


@dataclass
class Rating:
    item_id: str
    pair_id: str
    is_repeat: bool
    rating: Optional[int]      # None = abstained
    position: int


@dataclass
class RaterReturn:
    rater: str
    ratings: list[Rating]
    path: Path

    def first(self) -> dict[str, Optional[int]]:
        """pair_id -> rating on the FIRST showing (repeats excluded)."""
        return {r.pair_id: r.rating for r in self.ratings if not r.is_repeat}

    def repeats(self) -> dict[str, Optional[int]]:
        return {r.pair_id: r.rating for r in self.ratings if r.is_repeat}


def load_return(path: Path, spec: dict[str, Any], spec_sha: str,
                roster: dict[str, dict[str, Any]]) -> RaterReturn:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("instrument") != INSTRUMENT:
        raise AnalysisError("%s: instrument %r is not %s" % (path, doc.get("instrument"), INSTRUMENT))
    if doc.get("spec_sha256") != spec_sha:
        raise AnalysisError("%s: built from a different pair_specs.json (sha %s, expected %s)"
                            % (path, str(doc.get("spec_sha256"))[:12], spec_sha[:12]))
    rater = doc.get("rater")
    if rater not in roster:
        raise AnalysisError("%s: rater %r is not in the roster. Add them deliberately." % (path, rater))
    entry = roster[rater]
    if entry.get("sets_weights"):
        raise ExcludedRaterError("%s: rater %r helps set the weights (%s) and may not be compared "
                                 "with the model. Remove the file." % (path, rater, entry.get("why_excluded", "")))
    if not entry.get("eligible"):
        raise AnalysisError("%s: rater %r is not eligible (%s)" % (path, rater, entry.get("why_excluded", "")))
    pair_ids = {p["pair_id"] for p in spec["pairs"]}
    repeat_of = {r["repeat_id"]: r["of_pair"] for r in spec["repeats"]}
    out: list[Rating] = []
    seen: set[str] = set()
    for row in doc.get("ratings") or []:
        item_id, pair_id = row.get("item_id"), row.get("pair_id")
        is_repeat = bool(row.get("is_repeat"))
        if item_id in seen:
            raise AnalysisError("%s: item %s appears twice" % (path, item_id))
        seen.add(item_id)
        if is_repeat:
            if repeat_of.get(item_id) != pair_id:
                raise AnalysisError("%s: repeat %s does not point at %s" % (path, item_id, pair_id))
        elif item_id != pair_id or pair_id not in pair_ids:
            raise AnalysisError("%s: unknown pair %r" % (path, pair_id))
        abstain = bool(row.get("abstain"))
        value = row.get("rating")
        if abstain:
            if value is not None:
                raise AnalysisError("%s: %s is both rated and abstained" % (path, item_id))
        elif not (isinstance(value, int) and not isinstance(value, bool)
                  and RATING_MIN <= value <= RATING_MAX):
            raise AnalysisError("%s: %s has rating %r" % (path, item_id, value))
        out.append(Rating(item_id, pair_id, is_repeat, None if abstain else value,
                          int(row.get("position", 0))))
    return RaterReturn(rater, out, Path(path))


def load_returns(directory: Path, spec: dict[str, Any], spec_sha: str,
                 roster: dict[str, dict[str, Any]]) -> list[RaterReturn]:
    returns = [load_return(p, spec, spec_sha, roster) for p in sorted(Path(directory).glob("*.json"))]
    raters = [r.rater for r in returns]
    dup = sorted({r for r in raters if raters.count(r) > 1})
    if dup:
        raise AnalysisError("more than one return for rater(s) %s" % ", ".join(dup))
    return returns


def load_model_scores(path: Path, spec: dict[str, Any], spec_sha: str) -> dict[str, dict[str, Any]]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("schema") != MODEL_SCHEMA:
        raise AnalysisError("%s: schema %r is not %s" % (path, doc.get("schema"), MODEL_SCHEMA))
    if doc.get("spec_sha256") != spec_sha:
        raise AnalysisError("%s: scored a different pair_specs.json" % path)
    rows = {r["pair_id"]: r for r in doc["pairs"]}
    missing = sorted({p["pair_id"] for p in spec["pairs"]} - set(rows))
    if missing:
        raise AnalysisError("%s: no score for %s" % (path, ", ".join(missing)))
    for pid, r in rows.items():
        if r["state"] == "ranked" and not isinstance(r.get("z"), (int, float)):
            raise AnalysisError("%s: ranked pair %s has no z" % (path, pid))
    return rows


# ---------------------------------------------------------------------------
# Model order (prereg section 3): ranked pairs only; must-have break below every other
# ranked pair; then z. Ties in z are KEPT as ties -- the service's id tie-break would
# invent an order the model does not hold.
# ---------------------------------------------------------------------------

def model_key(row: dict[str, Any]) -> Optional[tuple[int, float]]:
    if row["state"] != "ranked":
        return None
    return (0 if row["must_have_break"] else 1, round(float(row["z"]) / Z_TIE) * Z_TIE)


def cross_check_model(spec: dict[str, Any], model: dict[str, dict[str, Any]]) -> list[str]:
    """Step 0. Each disagreement is a defect in the spec or the model's adapter."""
    problems = []
    for p in spec["pairs"]:
        d, m = p["design_check"], model[p["pair_id"]]
        expect_state = "ranked" if d["rankable"] else "not_enough_evidence"
        if m["state"] != expect_state:
            problems.append("%s: state %s, spec says %s" % (p["pair_id"], m["state"], expect_state))
        for flag in ("must_have_break", "risk_flag"):
            if bool(m.get(flag)) != bool(d[flag]):
                problems.append("%s: %s=%s, spec says %s" % (p["pair_id"], flag, m.get(flag), d[flag]))
    for c in spec["contrasts"]:
        for a, b in zip(c["a"], c["b"]):
            ka, kb = model_key(model[a]), model_key(model[b])
            if ka is None or kb is None:
                problems.append("%s: %s/%s not both ranked" % (c["contrast_id"], a, b))
            elif c["rule"] == "tie" and ka != kb:
                problems.append("%s: model does not tie %s and %s" % (c["contrast_id"], a, b))
            elif c["rule"] == "b_last" and not ka > kb:
                problems.append("%s: model does not put %s below %s" % (c["contrast_id"], b, a))
    return problems


# ---------------------------------------------------------------------------
# Kendall tau-b, stratified by block
# ---------------------------------------------------------------------------

def _sign(v: float) -> int:
    return (v > 0) - (v < 0)


def _cmp(a: Any, b: Any) -> int:
    return (a > b) - (a < b)


def stratified_tau_b(strata: Iterable[Sequence[tuple[Any, Any]]]) -> Optional[float]:
    """tau-b over within-stratum pairs only: sum(C - D) / sqrt(sum(untied in x) * sum(untied in y)).

    Each stratum is a list of (x, y); entries with x or y None are skipped. Pairs from
    different strata are never compared (two people's fit is not one ranking). None when
    either denominator is zero."""
    s = nx = ny = 0
    for stratum in strata:
        pts = [(x, y) for x, y in stratum if x is not None and y is not None]
        for (x1, y1), (x2, y2) in combinations(pts, 2):
            cx, cy = _cmp(x1, x2), _cmp(y1, y2)
            s += cx * cy
            nx += cx != 0
            ny += cy != 0
    if nx == 0 or ny == 0:
        return None
    return s / math.sqrt(nx * ny)


def _blocks(spec: dict[str, Any]) -> list[list[str]]:
    return [b["pair_ids"] for b in spec["blocks"]]


def complete_blocks(spec: dict[str, Any], ret: RaterReturn) -> int:
    first = ret.first()
    return sum(all(pid in first for pid in block) for block in _blocks(spec))


def tau_vs_model(spec, model, ratings: dict[str, Optional[float]]) -> Optional[float]:
    return stratified_tau_b(
        [[(ratings.get(pid), model_key(model[pid])) for pid in block] for block in _blocks(spec)])


def tau_between(spec, r1: dict[str, Optional[int]], r2: dict[str, Optional[int]]) -> Optional[float]:
    return stratified_tau_b([[(r1.get(pid), r2.get(pid)) for pid in block] for block in _blocks(spec)])


def consensus(spec, returns: Sequence[RaterReturn]) -> dict[str, Optional[float]]:
    out: dict[str, Optional[float]] = {}
    for p in spec["pairs"]:
        vals = [r.first().get(p["pair_id"]) for r in returns]
        vals = [v for v in vals if v is not None]
        out[p["pair_id"]] = statistics.median(vals) if len(vals) >= MIN_RATERS_PER_PAIR else None
    return out


# ---------------------------------------------------------------------------
# Repeats and contrasts
# ---------------------------------------------------------------------------

def repeat_consistency(ret: RaterReturn) -> dict[str, Any]:
    first, again = ret.first(), ret.repeats()
    rows = [(pid, first.get(pid), v) for pid, v in again.items()
            if first.get(pid) is not None and v is not None]
    return {"n": len(rows),
            "exact": sum(a == b for _, a, b in rows),
            "within_1": sum(abs(a - b) <= 1 for _, a, b in rows),
            "max_diff": max((abs(a - b) for _, a, b in rows), default=None),
            "flagged": sum(abs(a - b) >= 2 for _, a, b in rows) >= 2}


def _abstain_share(returns: Sequence[RaterReturn], pair_id: str) -> float:
    seen = [r.first()[pair_id] for r in returns if pair_id in r.first()]
    return 0.0 if not seen else sum(v is None for v in seen) / len(seen)


def contrast_result(contrast: dict[str, Any], model, returns: Sequence[RaterReturn],
                    cons: dict[str, Optional[float]]) -> dict[str, Any]:
    """Per instance: the model's direction (+1 a above b, 0 tie, -1 b above a), how many
    raters agree / reverse / tie, and the consensus direction. A contrast FAILS when, in
    every instance with data, a majority of raters with both ratings and the consensus
    order the pair against the model (for a model tie: strictly in one shared direction)."""
    instances = []
    for a, b in zip(contrast["a"], contrast["b"]):
        ka, kb = model_key(model[a]), model_key(model[b])
        mdir = None if ka is None or kb is None else _cmp(ka, kb)
        dirs = []
        for r in returns:
            f = r.first()
            if f.get(a) is not None and f.get(b) is not None:
                dirs.append(_sign(f[a] - f[b]))
        cdir = None if cons.get(a) is None or cons.get(b) is None else _sign(cons[a] - cons[b])
        # Prereg section 8: if most raters who reached either pair abstained on it, the
        # raters could not judge it, and the instance is not judged.
        too_unsure = any(_abstain_share(returns, pid) > 0.5 for pid in (a, b))
        if mdir is None or not dirs or cdir is None or too_unsure:
            against = None
        elif mdir == 0:
            # Model says equal. "Against" = a majority strictly prefer one side, and the
            # consensus prefers the same side.
            up, down = dirs.count(1), dirs.count(-1)
            side = 1 if up > down else -1 if down > up else 0
            against = side != 0 and max(up, down) * 2 > len(dirs) and cdir == side
        else:
            against = dirs.count(-mdir) * 2 > len(dirs) and cdir == -mdir
        instances.append({"a": a, "b": b, "model": mdir, "raters_a_above": dirs.count(1),
                          "raters_tie": dirs.count(0), "raters_b_above": dirs.count(-1),
                          "consensus": cdir, "against_model": against})
    judged = [i["against_model"] for i in instances if i["against_model"] is not None]
    # A model tie broken by raters only counts if it is broken the SAME way every time
    # (contrasts list `a` on a consistent side, e.g. K11's a = "more inventing").
    tie_sides = {i["consensus"] for i in instances if i["model"] == 0 and i["against_model"]}
    if len(tie_sides) > 1:
        judged = [False]
    return {"contrast_id": contrast["contrast_id"], "name": contrast["name"],
            "default_at_stake": contrast["default_at_stake"], "instances": instances,
            "fails": bool(judged) and all(judged) and len(judged) == len(instances)}


# ---------------------------------------------------------------------------
# The verdict (prereg section 6)
# ---------------------------------------------------------------------------

@dataclass
class Report:
    stage: str
    verdict: str
    lines: list[str] = field(default_factory=list)
    numbers: dict[str, Any] = field(default_factory=dict)


def analyse(spec, spec_sha, model, returns: Sequence[RaterReturn]) -> Report:
    problems = cross_check_model(spec, model)
    if problems:
        return Report("0-cross-check", "STOP: the model's output disagrees with the spec's gate "
                      "rules. Fix the spec or the adapter before reading any rater.", problems)

    counted = [r for r in returns if complete_blocks(spec, r) >= MIN_BLOCKS_PER_RATER]
    rep = Report("1-eligibility", "", numbers={"raters_returned": len(returns),
                                                 "raters_counted": len(counted)})
    for r in returns:
        rep.lines.append("rater %s: %d complete blocks, %d first-showing ratings, %d abstentions"
                         % (r.rater, complete_blocks(spec, r),
                            sum(v is not None for v in r.first().values()),
                            sum(v is None for v in r.first().values())))
    if len(counted) < MIN_RATERS:
        rep.verdict = ("DESCRIPTIVE ONLY: %d rater(s) with >= %d complete blocks; the rules need %d."
                       % (len(counted), MIN_BLOCKS_PER_RATER, MIN_RATERS))
        return rep

    pairwise = [tau_between(spec, a.first(), b.first()) for a, b in combinations(counted, 2)]
    pairwise = [t for t in pairwise if t is not None]
    inter = statistics.mean(pairwise) if pairwise else None
    rep.stage, rep.numbers["inter_rater_tau_mean"] = "2-agreement", inter
    rep.lines.append("inter-rater tau-b, mean of %d pairs: %s" % (len(pairwise), _f(inter)))
    if inter is None or inter < GATE_INTER_RATER_TAU:
        rep.verdict = ("NO CONCLUSION ABOUT THE MODEL: raters do not agree with each other "
                       "(gate %.2f). Defaults stand by default, not by evidence." % GATE_INTER_RATER_TAU)
        return rep

    rep.stage = "3-model"
    for r in counted:
        t = tau_vs_model(spec, model, r.first())
        rep.numbers["tau_%s" % r.rater] = t
        rep.lines.append("rater %s vs model: tau-b %s; repeats %s"
                         % (r.rater, _f(t), json.dumps(repeat_consistency(r))))
    cons = consensus(spec, counted)
    T = tau_vs_model(spec, model, cons)
    rep.numbers["consensus_tau"] = T
    rep.lines.append("consensus vs model: tau-b %s" % _f(T))

    results = [contrast_result(c, model, counted, cons) for c in spec["contrasts"]]
    failed = [c for c in results if c["fails"]]
    for c in results:
        rep.lines.append("%s %s: %s" % (c["contrast_id"], "FAILS" if c["fails"] else "holds",
                                        c["name"]))
    rep.numbers["contrasts_failed"] = [c["contrast_id"] for c in failed]

    # Prereg section 7: sensitivity without raters flagged on their repeats.
    flagged = [r.rater for r in counted if repeat_consistency(r)["flagged"]]
    rep.numbers["flagged_raters"] = flagged
    if flagged:
        kept = [r for r in counted if r.rater not in flagged]
        t2 = tau_vs_model(spec, model, consensus(spec, kept)) if len(kept) >= 2 else None
        rep.numbers["consensus_tau_without_flagged"] = t2
        rep.lines.append("sensitivity: without flagged rater(s) %s, consensus tau-b %s"
                         % (", ".join(flagged), _f(t2)))

    if T is None:
        rep.verdict = "NO CONCLUSION: no rankable pairs with a consensus."
    elif T < REVIEW_TAU:
        rep.verdict = ("OPEN A WEIGHTS REVIEW: consensus tau-b %.2f < %.2f. Pre-registration "
                       "conversation with matching-model and Sebastian before anything changes." % (T, REVIEW_TAU))
    elif T < DEFAULTS_STAND_TAU or failed:
        rep.verdict = ("EXAMINE THE FAILED CONTRASTS: consensus tau-b %.2f; failing: %s. Each failure "
                       "proposes a change to the named default, through the pre-registration route."
                       % (T, ", ".join(c["contrast_id"] for c in failed) or "none"))
    else:
        rep.verdict = "DEFAULTS STAND: consensus tau-b %.2f >= %.2f and no contrast fails." % (T, DEFAULTS_STAND_TAU)
    return rep


def _f(v: Optional[float]) -> str:
    return "n/a" if v is None else "%.3f" % v


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--spec", type=Path, default=HERE / "pair_specs.json")
    ap.add_argument("--model", type=Path, default=HERE / "pair_model_scores.json")
    ap.add_argument("--roster", type=Path, default=HERE / "roster.json")
    ap.add_argument("--returns", type=Path, default=HERE / "returned")
    a = ap.parse_args(argv)
    spec, sha = load_spec(a.spec)
    roster = load_roster(a.roster)
    returns = load_returns(a.returns, spec, sha, roster)
    model = load_model_scores(a.model, spec, sha)
    rep = analyse(spec, sha, model, returns)
    print("stage: %s" % rep.stage)
    for line in rep.lines:
        print("  " + line)
    print("VERDICT: " + rep.verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
