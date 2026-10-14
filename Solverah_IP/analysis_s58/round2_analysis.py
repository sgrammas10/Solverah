"""
round2_analysis.py -- the round-2 finish line, exactly as pre-registered.

Implements PREREG_ROUND2_2026-09-29.md sections 2-7 as amended by addenda A1 and A2 (Sebastian =
rater D, the reference; Julie = rater A on the overlap packets, worked in a fixed order). Written and tested on SYNTHETIC data
before any round-2 reading existed; nothing here was tuned on real data. Changing a threshold
after data exists is a new decision for a future round (prereg section 5), so the constants below
are the pre-registered ones and are not parameters.

    python round2_analysis.py --returned ../ground_truth/rater_app/returned/round2 \
        --llm results/round2 [--expected-poles poles.json] [--out report.json]

Inputs
------
* Returned rater JSONs (the rater page's payload): packet_id, rater, rubric_version,
  anchors_hash, packet_sha256, submitted_at, scores[].
* LLM draw files written by causal_graph/run_round2_scoring.py: packet_id, draw, run_at,
  rubric_version, anchors_hash, packet_sha256, result (ScorerResult.to_dict()), citations.
* Optional expected poles for A1.5: {"P-07": {"autonomy": "low", ...}, ...}.

Every print is ASCII.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RATER_APP = HERE.parent / "ground_truth" / "rater_app"
sys.path.insert(0, str(RATER_APP))
from rater_agreement import AgreementError, band_index, load_readings  # noqa: E402
from build_round2_pages import JULIE_ORDER  # noqa: E402

# ---- pre-registered constants (PREREG section 5, section 6, A1) -- NOT tunable -------------
BANDS = [0.1, 0.3, 0.5, 0.7, 0.9]
DIMENSIONS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]
MARGIN = 0.25                 # non-inferiority margin, bands
COVERAGE_GAP = 0.10           # LLM coverage may trail the reference's by at most this
N_BOOT = 20_000
SEED = 20260929
DRAWS_REQUIRED = 3            # D-21
FLOOR_MIN_REFERENCE_CELLS = 3
LEAK_GAP = 0.20               # A1.5
REFERENCE, EXPERT = "D", "A"


# ---------------------------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------------------------
@dataclass
class HumanReading:
    packet_id: str
    rater: str
    rubric_version: str | None
    anchors_hash: str | None
    packet_sha256: str | None
    submitted_at: datetime | None
    bands: dict[str, int | None]            # dimension -> band, None = insufficient evidence
    eids: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class LLMDraw:
    packet_id: str
    draw: int
    run_at: datetime
    rubric_version: str
    anchors_hash: str | None
    packet_sha256: str | None
    bands: dict[str, int | None]
    eids: dict[str, list[str]] = field(default_factory=dict)


def _ts(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def load_humans(paths) -> dict[tuple[str, str], HumanReading]:
    out: dict[tuple[str, str], HumanReading] = {}
    for p in paths:
        doc = json.loads(Path(p).read_text(encoding="utf-8"))
        # load_readings validates every row (off-band scores, malformed skips) the same way the
        # D-12 tooling does; a v3.1 page is the only thing that emits round-2 files.
        rows = load_readings([p], BANDS, allow_insufficient=True)
        key = (doc["packet_id"], doc["rater"])
        if key in out:
            raise AgreementError(f"{p}: duplicate return for {key}")
        out[key] = HumanReading(
            packet_id=doc["packet_id"], rater=doc["rater"],
            rubric_version=doc.get("rubric_version"), anchors_hash=doc.get("anchors_hash"),
            packet_sha256=doc.get("packet_sha256"), submitted_at=_ts(doc.get("submitted_at")),
            bands={r.dimension: r.band for r in rows},
            eids={s["dimension"]: list(s.get("excerpts_cited") or []) for s in doc.get("scores") or []},
        )
    return out


def load_llm(paths) -> dict[str, list[LLMDraw]]:
    out: dict[str, list[LLMDraw]] = {}
    for p in paths:
        doc = json.loads(Path(p).read_text(encoding="utf-8"))
        bands = {}
        for d in doc["result"]["dimensions"]:
            bands[d["dimension"]] = None if d["score"] is None else band_index(float(d["score"]), BANDS)
        eids: dict[str, list[str]] = {}
        for c in doc.get("citations") or []:
            if c.get("matched"):
                eids.setdefault(c["dimension"], []).append(c["matched_eid"])
        out.setdefault(doc["packet_id"], []).append(LLMDraw(
            packet_id=doc["packet_id"], draw=int(doc["draw"]), run_at=_ts(doc["run_at"]),
            rubric_version=doc["rubric_version"], anchors_hash=doc.get("anchors_hash"),
            packet_sha256=doc.get("packet_sha256"), bands=bands, eids=eids))
    for draws in out.values():
        draws.sort(key=lambda d: d.draw)
    return out


# ---------------------------------------------------------------------------------------------
# The LLM's cell value (PREREG section 3)
# ---------------------------------------------------------------------------------------------
def combine_draws(bands: list[int | None]) -> int | None:
    """Median of three draws. Two or more abstentions -> an LLM skip. Exactly one abstention ->
    the LOWER of the two scored bands (fixed in advance, conservative toward the floor)."""
    if len(bands) != DRAWS_REQUIRED:
        raise ValueError(f"expected {DRAWS_REQUIRED} draws, got {len(bands)}")
    scored = sorted(b for b in bands if b is not None)
    if len(scored) <= 1:
        return None
    if len(scored) == 2:
        return scored[0]
    return scored[1]


# ---------------------------------------------------------------------------------------------
# Equivalence gates (PREREG section 7 + A1.6)
# ---------------------------------------------------------------------------------------------
def gate_packet(pid: str, humans, llm, expected_rubric: str, expected_hash: str) -> list[str]:
    """Reasons this packet is NOT comparable for the finish line; empty list = comparable."""
    reasons = []
    d = humans.get((pid, REFERENCE))
    draws = llm.get(pid, [])
    if d is None:
        return ["no reference (D) reading"]
    if len(draws) != DRAWS_REQUIRED:
        reasons.append(f"{len(draws)} LLM draws, {DRAWS_REQUIRED} required (D-21)")
    if d.anchors_hash != expected_hash:
        reasons.append(f"D anchors_hash {d.anchors_hash} != {expected_hash}")
    if not d.packet_sha256:
        reasons.append("D reading carries no packet_sha256")
    for dr in draws:
        if dr.rubric_version != expected_rubric:
            reasons.append(f"draw {dr.draw} rubric_version {dr.rubric_version} != {expected_rubric}")
        if dr.packet_sha256 != d.packet_sha256:
            reasons.append(f"draw {dr.draw} packet_sha256 differs from D's")
        if d.submitted_at is None or dr.run_at <= d.submitted_at:
            reasons.append(f"draw {dr.draw} ran before D submitted (A1.6 gate 6)")
    return reasons


def gate_overlap(pid: str, humans, expected_hash: str) -> list[str]:
    d, a = humans.get((pid, REFERENCE)), humans.get((pid, EXPERT))
    if d is None or a is None:
        return ["needs both D and A"]
    reasons = []
    if d.packet_sha256 != a.packet_sha256 or not d.packet_sha256:
        reasons.append("D and A read different packet files")
    if a.anchors_hash != expected_hash or d.anchors_hash != expected_hash:
        reasons.append("an overlap reading was not taken under the pre-registered rubric")
    return reasons


# ---------------------------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------------------------
def _pairs(x: dict, y: dict) -> list[tuple[int, int]]:
    return [(x[k], y[k]) for k in DIMENSIONS if x.get(k) is not None and y.get(k) is not None]


def packet_distances(pairs_by_packet: dict[str, list[tuple[int, int]]]):
    """-> (packet ids, per-packet sum of |d|, per-packet exact matches, per-packet cell count)."""
    pids = sorted(p for p, v in pairs_by_packet.items() if v)
    sums = np.array([sum(abs(a - b) for a, b in pairs_by_packet[p]) for p in pids], float)
    exact = np.array([sum(a == b for a, b in pairs_by_packet[p]) for p in pids], float)
    counts = np.array([len(pairs_by_packet[p]) for p in pids], float)
    return pids, sums, exact, counts


def cluster_boot_means(sums, counts, rng, n_boot=N_BOOT) -> np.ndarray:
    """Mean over cells of packets resampled with replacement (cluster bootstrap over packets)."""
    k = len(sums)
    idx = rng.integers(0, k, size=(n_boot, k))
    return sums[idx].sum(axis=1) / counts[idx].sum(axis=1)


def finish_line(llm_pairs: dict, ceiling_pairs: dict, llm_cov: float, ref_cov: float,
                seed: int = SEED, n_boot: int = N_BOOT) -> dict:
    lp, ls, le, lc = packet_distances(llm_pairs)
    cp, cs, ce, cc = packet_distances(ceiling_pairs)
    out = {
        "n_packets_llm": len(lp), "n_cells_llm": int(lc.sum()),
        "n_packets_ceiling": len(cp), "n_cells_ceiling": int(cc.sum()),
        "llm_coverage": llm_cov, "reference_coverage": ref_cov,
        "coverage_guard_ok": llm_cov >= ref_cov - COVERAGE_GAP - 1e-12,
        "margin": MARGIN,
    }
    if not len(lp):
        return {**out, "verdict": "NO DATA", "reason": "no comparable LLM-vs-D cells"}
    out["D_llm"] = float(ls.sum() / lc.sum())
    out["exact_llm"] = float(le.sum() / lc.sum())
    if not len(cp):
        return {**out, "verdict": "NO CEILING", "reason": "no comparable D-vs-A overlap cells"}
    out["D_ceiling"] = float(cs.sum() / cc.sum())
    out["exact_ceiling"] = float(ce.sum() / cc.sum())
    rng = np.random.default_rng(seed)
    # Two different packet sets, so resampled independently (PREREG section 5).
    diff = cluster_boot_means(ls, lc, rng, n_boot) - cluster_boot_means(cs, cc, rng, n_boot)
    lo, hi = np.percentile(diff, [2.5, 97.5])
    out.update(diff=out["D_llm"] - out["D_ceiling"], ci_low=float(lo), ci_high=float(hi))
    if not out["coverage_guard_ok"]:
        out.update(verdict="NOT MET", reason="coverage guard: the LLM scored too few cells")
    elif hi < MARGIN:
        out.update(verdict="PASS", reason=f"95% CI upper bound {hi:.3f} < +{MARGIN}")
    elif lo > MARGIN:
        out.update(verdict="NOT MET", reason=f"95% CI lower bound {lo:.3f} > +{MARGIN}")
    else:
        out.update(verdict="INCONCLUSIVE", reason=f"95% CI [{lo:.3f}, {hi:.3f}] straddles +{MARGIN}")
    return out


def floor_bias(llm_cells: dict, ref_cells: dict, llm_draw_bands: list[int | None]) -> dict:
    """PREREG section 6. `*_cells` map (packet, dim) -> band or None."""
    ref_floor = [k for k, b in ref_cells.items() if b == 0]
    llm_on_ref_floor = [k for k in ref_floor if llm_cells.get(k) == 0]
    out = {
        "llm_floor_uses_all_draws": sum(1 for b in llm_draw_bands if b == 0),
        "llm_draw_cells": len(llm_draw_bands),
        "reference_floor_cells": len(ref_floor),
        "llm_band_on_reference_floor_cells": {f"{p}/{d}": llm_cells.get((p, d)) for p, d in ref_floor},
    }
    if len(ref_floor) >= FLOOR_MIN_REFERENCE_CELLS and not llm_on_ref_floor:
        out["reading"] = "floor bias persists"
    elif ref_floor and len(llm_on_ref_floor) * 2 >= len(ref_floor):
        out["reading"] = "floor bias reduced"
    else:
        out["reading"] = "unresolved"
    return out


def skip_table(llm_cells: dict, ref_cells: dict) -> dict:
    t = {"both_scored": 0, "llm_skip_only": 0, "ref_skip_only": 0, "both_skip": 0}
    by_dim = {d: {"llm": 0, "ref": 0} for d in DIMENSIONS}
    for k in ref_cells:
        ls, rs = llm_cells.get(k) is None, ref_cells[k] is None
        t[{(False, False): "both_scored", (True, False): "llm_skip_only",
           (False, True): "ref_skip_only", (True, True): "both_skip"}[(ls, rs)]] += 1
        by_dim[k[1]]["llm"] += ls
        by_dim[k[1]]["ref"] += rs
    return {"table": t, "by_dimension": by_dim}


def expectation_leak(expected: dict, readers: dict[str, dict]) -> dict:
    """A1.5. `readers` maps a label to {(packet, dim): band}; only overlap cells are passed in."""
    shares = {}
    for label, cells in readers.items():
        hits = n = 0
        for (p, d), b in cells.items():
            pole = (expected.get(p) or {}).get(d)
            if pole not in ("low", "high") or b is None:
                continue
            n += 1
            hits += (b <= 1) if pole == "low" else (b >= 3)
        shares[label] = {"cells": n, "on_expected_side": hits, "share": (hits / n) if n else None}
    d, a = shares.get("D", {}).get("share"), shares.get("A", {}).get("share")
    flag = d is not None and a is not None and d - a >= LEAK_GAP - 1e-12
    return {"shares": shares, "reading": "reference may carry selection priors" if flag
            else ("not assessable" if d is None or a is None else "no leak signal at the pre-set gap")}


def overlap_order_check(humans: dict) -> dict:
    """A2.3. Julie works down JULIE_ORDER and stops when she likes. What she finished is a random
    sample only if it is a prefix of that order. The order counts only packets someone read, so
    a packet that never passed the scrub is not a gap. Descriptive: nothing is dropped for it."""
    read = {p for p, _ in humans}
    order = [p for p in JULIE_ORDER if p in read]
    done = {p for p, r in humans if r == EXPERT}
    out_of_order = sorted(done - set(order[:len(done)]))
    return {
        "order": order, "completed": [p for p in order if p in done],
        "is_prefix": not out_of_order, "out_of_order": out_of_order,
        "reading": "random prefix of the pre-registered order" if not out_of_order
        else "partly self-selected: the ceiling is reported with that caveat",
    }


# ---------------------------------------------------------------------------------------------
# The whole analysis
# ---------------------------------------------------------------------------------------------
def analyse(humans: dict, llm: dict, *, expected_rubric: str, expected_hash: str,
            expected_poles: dict | None = None, seed: int = SEED, n_boot: int = N_BOOT) -> dict:
    ref_pids = sorted({p for p, r in humans if r == REFERENCE})
    not_comparable, comparable = {}, []
    for pid in ref_pids:
        reasons = gate_packet(pid, humans, llm, expected_rubric, expected_hash)
        if reasons:
            not_comparable[pid] = reasons
        else:
            comparable.append(pid)
    overlap, overlap_bad = [], {}
    for pid in sorted({p for p, r in humans if r == EXPERT}):
        reasons = gate_overlap(pid, humans, expected_hash)
        if reasons:
            overlap_bad[pid] = reasons
        else:
            overlap.append(pid)

    llm_cells, ref_cells, draw_bands, dispersion = {}, {}, [], {"cells_band_differs": 0, "cells": 0}
    for pid in comparable:
        draws = llm[pid]
        for d in DIMENSIONS:
            per = [dr.bands.get(d) for dr in draws]
            draw_bands += per
            llm_cells[(pid, d)] = combine_draws(per)
            ref_cells[(pid, d)] = humans[(pid, REFERENCE)].bands.get(d)
            dispersion["cells"] += 1
            dispersion["cells_band_differs"] += len(set(per)) > 1

    llm_pairs = {p: _pairs({d: llm_cells[(p, d)] for d in DIMENSIONS}, humans[(p, REFERENCE)].bands)
                 for p in comparable}
    ceiling_pairs = {p: _pairs(humans[(p, REFERENCE)].bands, humans[(p, EXPERT)].bands) for p in overlap}
    n_cells = len(ref_cells)
    llm_cov = sum(v is not None for v in llm_cells.values()) / n_cells if n_cells else 0.0
    ref_cov = sum(v is not None for v in ref_cells.values()) / n_cells if n_cells else 0.0

    per_dim = {}
    for d in DIMENSIONS:
        ds = [abs(llm_cells[(p, d)] - ref_cells[(p, d)]) for p in comparable
              if llm_cells[(p, d)] is not None and ref_cells[(p, d)] is not None]
        per_dim[d] = {"cells": len(ds), "mean_distance": (sum(ds) / len(ds)) if ds else None}

    # Equivalence gate 3: cells two or more bands apart, citations side by side, for a HUMAN to
    # read before anything is called noise. Canonical order, not ranked.
    review = []
    for p in comparable:
        for d in DIMENSIONS:
            a, b = llm_cells[(p, d)], ref_cells[(p, d)]
            if a is not None and b is not None and abs(a - b) >= 2:
                review.append({"packet": p, "dimension": d, "llm_band": a, "reference_band": b,
                               "reference_eids": humans[(p, REFERENCE)].eids.get(d, []),
                               "llm_eids_by_draw": [dr.eids.get(d, []) for dr in llm[p]]})

    secondary_llm_vs_a = {p: _pairs({d: llm_cells.get((p, d)) for d in DIMENSIONS},
                                    humans[(p, EXPERT)].bands) for p in overlap if p in comparable}
    sp_, ss, se, sc = packet_distances(secondary_llm_vs_a)
    leak = None
    if expected_poles is not None:
        cells = lambda f: {(p, d): f(p, d) for p in overlap for d in DIMENSIONS}  # noqa: E731
        leak = expectation_leak(expected_poles, {
            "D": cells(lambda p, d: humans[(p, REFERENCE)].bands.get(d)),
            "A": cells(lambda p, d: humans[(p, EXPERT)].bands.get(d)),
            "LLM": {k: v for k, v in cells(lambda p, d: llm_cells.get((p, d))).items()},
        })
    return {
        "prereg": "PREREG_ROUND2_2026-09-29.md + addenda A1, A2",
        "expected_rubric": expected_rubric, "expected_anchors_hash": expected_hash,
        "comparable_packets": comparable, "not_comparable": not_comparable,
        "overlap_packets": overlap, "overlap_not_comparable": overlap_bad,
        "overlap_order": overlap_order_check(humans),
        "finish_line": finish_line(llm_pairs, ceiling_pairs, llm_cov, ref_cov, seed, n_boot),
        "secondary_llm_vs_A": {"packets": sp_, "mean_distance": float(ss.sum() / sc.sum()) if len(sc) else None},
        "floor_bias": floor_bias(llm_cells, ref_cells, draw_bands),
        "skips": skip_table(llm_cells, ref_cells),
        "per_dimension": per_dim,
        "llm_dispersion": dispersion,
        "review_cells_for_equivalence_gate_3": review,
        "expectation_leak": leak,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--returned", type=Path, required=True)
    ap.add_argument("--llm", type=Path, required=True)
    ap.add_argument("--anchors", type=Path, default=RATER_APP / "anchors_v3_1_PROPOSED.json")
    ap.add_argument("--expected-poles", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    import hashlib
    cfg = json.loads(a.anchors.read_text(encoding="utf-8"))
    blob = json.dumps({k: v for k, v in cfg.items() if not k.startswith("_")},
                      sort_keys=True, ensure_ascii=False)
    expected_hash = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]
    report = analyse(load_humans(sorted(a.returned.glob("*.json"))),
                     load_llm(sorted(a.llm.glob("*.json"))),
                     expected_rubric=cfg["rubric_version"], expected_hash=expected_hash,
                     expected_poles=json.loads(a.expected_poles.read_text(encoding="utf-8"))
                     if a.expected_poles else None)
    text = json.dumps(report, indent=2, default=str, ensure_ascii=True)
    if a.out:
        a.out.write_text(text + "\n", encoding="utf-8")
    fl = report["finish_line"]
    print(f"finish line: {fl['verdict']} -- {fl.get('reason', '')}")
    print(f"comparable packets: {report['comparable_packets']}  overlap: {report['overlap_packets']}")
    if report["not_comparable"]:
        print(f"NOT comparable: {report['not_comparable']}")
    print(f"floor bias: {report['floor_bias']['reading']}")
    print(f"Julie's overlap: {report['overlap_order']['reading']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
