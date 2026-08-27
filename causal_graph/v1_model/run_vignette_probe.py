"""
run_vignette_probe.py

Company-side half of the paired-vignette calibration probe (SCALE_CALIBRATION_CHECK.md).
Scores each company vignette in vignette_probes/pairs/vignette_probe_pairs_v1.yaml n=5 times via
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
    python run_vignette_probe.py --pairs vignette_probes/pairs/vignette_probe_pairs_v1.yaml --out vignette_probes/results/vignette_probe_results.csv

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
import json
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

# --------------------------------------------------------------------------------
# BLEED DETECTION -- rewritten 2026-08-17. The original detector fired on
# `d.confidence >= 0.6` for off-target dimensions. That is the WRONG VARIABLE, and it
# inverted the project's record for three rounds:
#
#   * It fired on collaboration-vignette -> autonomy readings, which scored exactly
#     0.5 -- the NEUTRAL band -- at 0.6 confidence. A confident reading of "no signal"
#     is not contamination; nothing moved. SCALE_CALIBRATION_CHECK.md §5 recorded this
#     as a confirmed 10/10 bleed. Recomputed from the raw CSVs, it is not a bleed at
#     all, and it was not even consistent: the three round-1 collaboration vignettes
#     returned confidence 0.6 / 0.3 / 0.1 on that same neutral 0.5.
#   * It NEVER fired on autonomy-vignette -> collaboration readings, which scored 0.3
#     -- a full band off neutral -- at 0.1-0.3 confidence, on 28 of 30 runs across
#     rounds 1, 2 and 3. That is real contamination and it went unrecorded.
#   * It likewise missed autonomy -> innovation, which tracks the autonomy level
#     monotonically at the extremes (0.1 -> 0.1, 0.9 -> 0.7) on 19 of 20 runs across
#     two independently written vignette sets. §5 dismissed this as "1/5, incidental."
#
# The quantity that matters is DISPLACEMENT OFF NEUTRAL, not the model's confidence in
# whatever it landed on. A dimension the vignette is silent about should read 0.5; any
# off-target dimension that moves a full band off 0.5 is the signal. Confidence is
# still recorded per row for context, but it is no longer the trigger.
NEUTRAL_SCORE = 0.5
BLEED_MIN_DISPLACEMENT = 0.2   # one full band off neutral (0.5 -> 0.3 or 0.7)
BLEED_MIN_RUNS = 3             # of n, before calling it reproducible rather than incidental


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


_QUOTE_SEP = " || "


def pack_quotes(quotes: list[str]) -> str:
    """Serialize evidence quotes into one CSV cell.

    ADDED 2026-08-17, and this is the fix that should have come first. The probe was
    logging only quotes_grounded/quotes_total and discarding the quote TEXT, so when an
    off-target dimension came back displaced there was no way to see WHICH phrase the
    scorer had read as evidence for it -- the single datum that distinguishes "the
    vignette genuinely contains that evidence" (a vignette-writing artifact, fix the
    vignette) from "the anchor claims vocabulary that belongs to another dimension" (an
    anchors.json defect, goes to Julie's post-round-1 rewrite). Three rounds and 630
    scored rows were spent without it, and diagnosing the autonomy->collaboration bleed
    still requires a re-run purely to recover text the API already returned each time.
    Newlines are collapsed so a quote can never break the CSV row."""
    return _QUOTE_SEP.join(" ".join(q.split()) for q in quotes)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="vignette_probes/pairs/vignette_probe_pairs_v1.yaml")
    ap.add_argument("--out", default="vignette_probes/results/vignette_probe_results.csv")
    ap.add_argument("--n", type=int, default=5, help="runs per vignette (locked mean-of-5 default)")
    ap.add_argument("--model", default=sp.MODEL)
    ap.add_argument(
        "--anchors", default=None,
        help="Path to an alternate anchors JSON. ADDED 2026-08-17 so a PROPOSED anchor "
             "rewrite can be tested against the same vignettes WITHOUT editing "
             "anchors.json, which is frozen at v1-frozen-2026-08-15 while raters are "
             "mid-round on P-01..P-06. Editing the live file to test a hypothesis would "
             "silently invalidate the ground-truth round in progress.")
    ap.add_argument(
        "--allow-rubric-mismatch", action="store_true",
        help="Proceed even when the anchors' rubric_version differs from the pairs "
             "file's rubric_version_expected. Required with --anchors, and deliberately "
             "opt-in: the mismatch guard is what stops a silent comparison across two "
             "different rubrics.")
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
    if args.anchors:
        anchors_path = Path(args.anchors)
        if not anchors_path.exists():
            raise SystemExit(f"--anchors file not found: {anchors_path}")
        anchors = json.loads(anchors_path.read_text(encoding="utf-8"))
        print(f"*** Using ALTERNATE anchors: {anchors_path} "
              f"(rubric_version {anchors['rubric_version']!r}). anchors.json is "
              f"untouched. ***", file=sys.stderr)
    else:
        anchors = sp.load_anchors()
    expected_rv = pairs_doc.get("rubric_version_expected")
    if expected_rv and anchors["rubric_version"] != expected_rv:
        msg = (f"anchors rubric_version is {anchors['rubric_version']!r}, vignette pairs "
               f"were frozen against {expected_rv!r}.")
        if not args.allow_rubric_mismatch:
            print(f"WARNING: {msg} The anchors have moved since these vignettes were "
                  f"written -- stop and reconcile before spending API calls. Pass "
                  f"--allow-rubric-mismatch if this is a deliberate A/B of two rubrics.",
                  file=sys.stderr)
            return 1
        print(f"*** RUBRIC MISMATCH ALLOWED BY FLAG: {msg} Results from this run are "
              f"NOT comparable to runs scored under {expected_rv!r} except as a "
              f"deliberate paired A/B on identical vignette text. ***", file=sys.stderr)
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
            bleed_runs: dict[str, list[float]] = {}

            for run_idx in range(1, args.n + 1):
                result = sp.score_packet(
                    client, vignette_text, rubric_text,
                    packet_id=packet_id, rubric_version=anchors["rubric_version"],
                    packet_version="vignette-v1", model=args.model,
                )
                for d in result.dimensions:
                    g, t = grounded_count(d.evidence_quotes, vignette_text)
                    is_target = d.dimension == dim_name
                    displacement = round(d.score - NEUTRAL_SCORE, 4)
                    if is_target:
                        on_target_scores.append(d.score)
                    elif abs(displacement) >= BLEED_MIN_DISPLACEMENT:
                        # Displacement off neutral, NOT high confidence -- see the
                        # BLEED DETECTION note above for why the old trigger was wrong.
                        bleed_runs.setdefault(d.dimension, []).append(d.score)
                    rows.append({
                        "packet_id": packet_id, "target_dimension": dim_name, "level": level,
                        "run": run_idx, "dimension": d.dimension, "is_target": is_target,
                        "score": d.score, "confidence": d.confidence,
                        "displacement": displacement if not is_target else "",
                        "quotes_grounded": g, "quotes_total": t,
                        "evidence_quotes": pack_quotes(d.evidence_quotes),
                        "temperature_honored": result.temperature_honored,
                    })

            # One flag per off-target dimension, not per run: a dimension that displaces
            # on 4 of 5 runs is one reproducible finding, and printing it five times is
            # what made the round-1/2 logs easy to skim past.
            leakage_flags = []
            for off_dim, scores in sorted(bleed_runs.items()):
                mean_off = sum(scores) / len(scores)
                label = "reproducible" if len(scores) >= BLEED_MIN_RUNS else "incidental"
                leakage_flags.append(
                    f"{off_dim} displaced to {mean_off:.2f} (neutral 0.5) on "
                    f"{len(scores)}/{args.n} runs -- {label}"
                )

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
                "bleed_runs": bleed_runs,
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

    # ----------------------------------------------------------------------------
    # CROSS-DIMENSION BLEED ROLLUP -- added 2026-08-17. Aggregates displacement across
    # every level of a dimension, because that is the resolution at which the finding
    # actually lives: autonomy->collaboration is invisible at any single level (0.3 on
    # 5 of 5 runs looks like one odd vignette) and unmistakable across levels (0.3 at
    # every level from 0.5 upward, never at 0.1 or 0.3). Per-pair warnings alone are
    # what let this hide for three rounds.
    # ----------------------------------------------------------------------------
    print("\nCross-dimension bleed (off-target dimensions displaced >= "
          f"{BLEED_MIN_DISPLACEMENT} off neutral {NEUTRAL_SCORE}):")
    any_bleed = False
    for dim_name, summaries in by_dim.items():
        agg: dict[str, list[tuple]] = {}
        for s in summaries:
            for off_dim, scores in s["bleed_runs"].items():
                agg.setdefault(off_dim, []).append((s["level"], scores))
        if not agg:
            print(f"  {dim_name}: none")
            continue
        for off_dim, entries in sorted(agg.items()):
            hits = sum(len(sc) for _, sc in entries)
            total = sum(args.n for _ in entries)
            all_scores = [x for _, sc in entries for x in sc]
            mean_off = sum(all_scores) / len(all_scores)
            levels = ", ".join(f"{lv}({len(sc)}/{args.n})" for lv, sc in entries)
            monotone = len({round(x, 4) for x in all_scores}) > 1
            any_bleed = True
            print(f"  {dim_name} -> {off_dim}: {hits}/{total} runs displaced, "
                  f"mean {mean_off:.2f} | by level: {levels}"
                  + ("  [VARIES WITH LEVEL -- suspect a coupling, not a constant offset]"
                     if monotone else "  [constant offset]"))
    if any_bleed:
        print("\n  To tell a vignette artifact from an anchor defect, read the "
              "evidence_quotes column of the output CSV for the displaced rows. If the "
              "cited phrase genuinely is evidence for the off-target dimension, rewrite "
              "the vignette. If the cited phrase is on-target language that the "
              "off-target dimension's own band text also claims, it is an anchors.json "
              "defect and belongs in Julie's post-round-1 rewrite -- do NOT edit the "
              "frozen anchors mid-round.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
