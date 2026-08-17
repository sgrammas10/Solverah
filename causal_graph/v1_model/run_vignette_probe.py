"""
run_vignette_probe.py

Company-side half of the paired-vignette calibration probe (SCALE_CALIBRATION_CHECK.md).
Scores each company vignette in vignette_probe_pairs_v1.yaml n=5 times via
scorer_pipeline.score_packet() -- the real S1-2 interface, pinned model/config, same
mean-of-5 aggregator the real packets use (S1-3 locked decision) -- then compares the
on-target dimension's mean score against that pair's frozen target_person value.

NEEDS LIVE API ACCESS -- run this locally, not in the cloud sandbox (blocked by the
network allowlist, same as every other live-API step in this project). Person-side
scores are NOT recomputed here; they were already verified offline by
score_person_side.py against assessment_items.yaml -- run that first and confirm it
prints "safe to proceed" before spending API calls here.

Usage:
    pip install openai python-dotenv pyyaml
    python run_vignette_probe.py --pairs vignette_probe_pairs_v1.yaml --out vignette_probe_results.csv

Expects OPENAI_API_KEY in the environment. Loaded the same way scorer_variance_test_v2.py
loads it: explicitly from the Solverah repo-root .env (not just cwd or a bare OS env var),
because this script lives one directory deeper (causal_graph/v1_model/) than
scorer_variance_test_v2.py does (causal_graph/) -- a naive load_dotenv() with no path
looks at cwd first, which is why running from v1_model/ silently misses a key that's
visible when running from causal_graph/. scorer_pipeline.py is importable because this
script adds causal_graph/ to sys.path (scorer_pipeline.py was built by S1-2 specifically
to be reusable this way -- unlike the excerpt-parsing logic it PORTS from
build_rater_page.py, score_packet() is meant to be imported, not re-derived).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scorer_pipeline as sp  # noqa: E402

# Repo root is two levels up from this file (v1_model -> causal_graph -> Solverah), one
# more than scorer_variance_test_v2.py's parent.parent (it lives directly in causal_graph/).
# Load the root .env explicitly first, then fall back to any .env in cwd, matching
# scorer_variance_test_v2.py's own two-step load pattern.
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_ENV_PATH if _ENV_PATH.exists() else None)
load_dotenv()

# Per-dimension tolerance, corrected derivation -- see SCALE_CALIBRATION_CHECK.md,
# "Finding 3 (new)". Worst OBSERVED nonzero per-dimension SD from S1-3 (08-17b), not the
# frequency of nonzero cells: autonomy/innovation topped out at 0.080 (tolerance
# ~2x -> 0.16, default working value 0.08-0.10); pace/collaboration/feedback/decision
# topped out at 0.098 (tolerance ~2x -> 0.20). Decision/feedback aren't scored by this
# script (held per the calibration doc's Recommended order item 2) but are listed for
# completeness in case this script is extended to them later.
TOLERANCE_CEILING = {
    "autonomy": 0.16, "innovation": 0.16,
    "pace": 0.20, "collaboration": 0.20, "feedback": 0.20, "decision": 0.20,
}
TOLERANCE_DEFAULT = {
    "autonomy": 0.09, "innovation": 0.09,
    "pace": 0.20, "collaboration": 0.20, "feedback": 0.20, "decision": 0.20,
}

# Confidence bands from anchors.json, for readability in the leakage warning.
CONFIDENCE_LABEL = {0.9: "High", 0.6: "Medium", 0.3: "Low", 0.1: "Very low"}


def closest_company_band(target_person: float) -> float:
    """Nearest achievable company band (sp.SCORE_BAND_VALUES) to a person-side target.
    FIX, added after the first live run: the original verdict compared company_mean
    directly against the raw target_person value. That's wrong at the extremes -- the
    company rubric has no band below 0.1 or above 0.9, so a person target of 0.0 or 1.0
    can NEVER be matched exactly no matter how well-calibrated the instruments are
    (confirmed empirically: round 1's actual run landed on exactly 0.1/0.9 with zero
    variance on every single low/high pair, across all four dimensions -- that's the
    lattice mismatch from SCALE_CALIBRATION_CHECK.md's Finding 1, not noise or a
    calibration defect). Comparing against the closest ACHIEVABLE band isolates whether
    there's miscalibration BEYOND what Finding 1 already predicts and prices in."""
    return min(sp.SCORE_BAND_VALUES, key=lambda b: abs(b - target_person))


def grounded_count(quotes: list[str], vignette_text: str) -> tuple[int, int]:
    """Lightweight reuse of S1-5's normalization, applied directly to the raw vignette
    text instead of parsed packet excerpts (SCALE_CALIBRATION_CHECK.md's explicit
    decision NOT to run parse_excerpts/classify_source against vignettes -- see that
    doc's 'On citation verification' section). Returns (grounded, total)."""
    norm_vignette = sp._normalize(vignette_text)
    grounded = 0
    for q in quotes:
        if len(sp._normalize(q)) >= 10 and sp._normalize(q) in norm_vignette:
            grounded += 1
    return grounded, len(quotes)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="vignette_probe_pairs_v1.yaml")
    ap.add_argument("--out", default="vignette_probe_results.csv")
    ap.add_argument("--n", type=int, default=5, help="runs per vignette (locked mean-of-5 default)")
    ap.add_argument("--model", default=sp.MODEL)
    args = ap.parse_args()

    import os
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit(
            f"OPENAI_API_KEY is not set in the environment. Looked for a .env at "
            f"{_ENV_PATH} ({'found' if _ENV_PATH.exists() else 'not found'}) and in the "
            f"current directory. Set it in the Solverah repo root's .env, or export it "
            f"directly in this shell, then re-run."
        )

    pairs_doc = yaml.safe_load(Path(args.pairs).read_text(encoding="utf-8"))
    anchors = sp.load_anchors()
    expected_rv = pairs_doc.get("rubric_version_expected")
    if expected_rv and anchors["rubric_version"] != expected_rv:
        print(f"WARNING: anchors.json rubric_version is {anchors['rubric_version']!r}, "
              f"vignette pairs were frozen against {expected_rv!r}. The anchors have "
              f"moved since these vignettes were written -- stop and reconcile before "
              f"spending API calls.", file=sys.stderr)
        return 1
    rubric_text = sp.build_rubric_text(anchors)

    client = OpenAI()

    rows = []          # every (vignette, run, dimension) reading -- Finding 3's full data
    pair_summaries = []  # one row per vignette: on-target mean vs. target_person

    for dim_name, dim_body in pairs_doc["dimensions"].items():
        for pair in dim_body["pairs"]:
            level = pair["level"]
            packet_id = f"VIGN-{dim_name}-{level}"
            vignette_text = pair["company_vignette"].strip()
            print(f"Scoring {packet_id} (n={args.n})...", file=sys.stderr)

            on_target_scores = []
            leakage_flags = []

            for run_idx in range(1, args.n + 1):
                result = sp.score_packet(
                    client, vignette_text, rubric_text,
                    packet_id=packet_id, rubric_version=anchors["rubric_version"],
                    packet_version="vignette-v1", model=args.model,
                )
                for d in result.dimensions:
                    g, t = grounded_count(d.evidence_quotes, vignette_text)
                    is_target = d.dimension == dim_name
                    if is_target:
                        on_target_scores.append(d.score)
                    elif d.confidence >= 0.6:
                        leakage_flags.append(
                            f"run {run_idx}: off-target {d.dimension} scored {d.score} "
                            f"at {CONFIDENCE_LABEL.get(d.confidence, d.confidence)} confidence"
                        )
                    rows.append({
                        "packet_id": packet_id, "target_dimension": dim_name, "level": level,
                        "run": run_idx, "dimension": d.dimension, "is_target": is_target,
                        "score": d.score, "confidence": d.confidence,
                        "quotes_grounded": g, "quotes_total": t,
                        "temperature_honored": result.temperature_honored,
                    })

            company_mean = sum(on_target_scores) / len(on_target_scores)
            target_person = pair["target_person"]
            structural_expected = closest_company_band(target_person)
            structural_gap = round(structural_expected - target_person, 4)
            delta = company_mean - target_person          # raw, for transparency only
            residual = company_mean - structural_expected  # what verdict is actually based on
            tol = TOLERANCE_DEFAULT[dim_name]
            tol_ceiling = TOLERANCE_CEILING[dim_name]
            if abs(residual) <= tol:
                verdict = "PASS"
            elif abs(residual) <= tol_ceiling:
                verdict = "BORDERLINE"
            else:
                verdict = "FAIL"

            pair_summaries.append({
                "dimension": dim_name, "level": level,
                "target_person": target_person, "structural_expected": structural_expected,
                "structural_gap": structural_gap, "company_mean": round(company_mean, 4),
                "delta": round(delta, 4), "residual": round(residual, 4),
                "tolerance_default": tol, "tolerance_ceiling": tol_ceiling, "verdict": verdict,
                "company_scores": on_target_scores,
                "leakage_flags": leakage_flags,
                "note": pair.get("note", ""),
            })

    # Full per-run, per-dimension log -- Finding 3's off-target data included.
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {args.out}", file=sys.stderr)

    # Per-dimension summary -- NOT pooled across all 12 pairs, per the calibration doc's
    # corrected "What would pass" section. Verdict is based on RESIDUAL (company_mean vs.
    # the closest ACHIEVABLE company band), not raw delta vs. the person's raw target --
    # see closest_company_band()'s docstring for why the original delta-based check was
    # wrong at the extremes.
    print(f"\n{'dimension':<15}{'level':<9}{'target':<8}{'struct.exp':<11}{'company':<9}"
          f"{'residual':<10}{'verdict'}")
    print("-" * 90)
    by_dim: dict[str, list[dict]] = {}
    for s in pair_summaries:
        by_dim.setdefault(s["dimension"], []).append(s)
        print(f"{s['dimension']:<15}{s['level']:<9}{s['target_person']:<8}"
              f"{s['structural_expected']:<11}{s['company_mean']:<9}{s['residual']:<10}{s['verdict']}")
        if s["leakage_flags"]:
            for flag in s["leakage_flags"]:
                print(f"    LEAKAGE WARNING: {flag}")
        if s["note"]:
            print(f"    NOTE: {s['note']}")

    print("\nPer-dimension systematic-offset check (same sign on 2+ pairs, "
          "beyond half the default tolerance, using RESIDUAL not raw delta):")
    for dim_name, summaries in by_dim.items():
        signs = [1 if s["residual"] > TOLERANCE_DEFAULT[dim_name] / 2 else
                 (-1 if s["residual"] < -TOLERANCE_DEFAULT[dim_name] / 2 else 0)
                 for s in summaries]
        nonzero = [s for s in signs if s != 0]
        systematic = len(nonzero) >= 2 and len(set(nonzero)) == 1
        direction = "person > company" if systematic and nonzero[0] < 0 else (
            "company > person" if systematic and nonzero[0] > 0 else "no clear direction")
        print(f"  {dim_name}: {direction}"
              + (" -- SYSTEMATIC, see calibration doc's 'What would fail' section "
                 "before concluding intensity mismatch" if systematic else ""))

    return 0


if __name__ == "__main__":
    sys.exit(main())
