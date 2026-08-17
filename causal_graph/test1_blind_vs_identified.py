"""
test1_blind_vs_identified.py -- Test 1, done properly, n=5 per condition.

Original Test 1 (08-07 session): one blind run and one identified run of a single
company (GT-01/Wayfair) on the OLD retired v2.1 rubric and v3 thin packet. 08-13b's
variance finding (Test 2) showed a single run's SE is too wide to trust any of Test 1's
observed deltas, and the instrument itself has been replaced twice since. Carried as
"still undone" through every handoff since, and 08-15b/08-17 both call it load-bearing
for the "does scrubbing belong in production" decision -- 08-15b reversed that decision
on n=1 evidence.

This version:
  * Same frozen instrument the human raters are using (anchors.json v1-frozen-2026-08-15),
    same pinned model, same call shape as scorer_variance_test_v2.py -- imported directly
    from that module rather than reimplemented, so the BLIND condition here is
    byte-identical in method to the P-01..P-06 runs already on disk.
  * n=5 per condition, not n=1 -- compare condition MEANS against the pooled SE, not
    single values.
  * All SIX ground-truth packets, not one -- the original Wayfair test had no way to
    tell a real effect from company-specific noise. Six companies x six dimensions
    gives 36 independent comparisons.
  * BLIND condition reuses the runs_v2_*.csv files already on disk instead of
    re-running -- literally the same data, not a fresh noisy resample, and it halves
    the number of new API calls needed (only IDENTIFIED needs new runs).
  * IDENTIFIED condition is a MINIMAL, mechanical edit of the same anonymized Section 1
    text: only the company-name substitution tokens inside quote bodies
    ([company], [the company], [Company ...]) are replaced with the real name.
    Source-attribution tags ([company careers page] etc.) are left alone -- they're
    generic source-type labels, not identity, and touching them would widen the
    manipulation beyond "the company is named" into "the packet format changed,"
    reintroducing exactly the kind of confound this project keeps catching (the v3-vs-
    v4.1 packet confound in the original Test 1; the P-02/P-05 em-dash retype bug in
    08-15b). One variable changes: whether the company's name appears in the evidence.

    pip install openai python-dotenv pandas
    python test1_blind_vs_identified.py              # all 6 packets
    python test1_blind_vs_identified.py --packet P-01
Requires runs_v2_*.csv for the target packet(s) to already exist (run
scorer_variance_test_v2.py first) -- this script will not silently regenerate blind data
under a different sample; it fails loudly if the file is missing instead.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from scorer_variance_test_v2 import (  # noqa: E402
    ANCHORS_PATH,
    DIMENSIONS,
    MODEL,
    REASONING_EFFORT,
    TEMPERATURE,
    VALID_PACKETS,
    build_messages,
    build_rubric_text,
    call_with_retry,
    load_anchors,
    load_packet_section1,
    packet_path_for,
)
from openai import OpenAI
import os

OUTPUT_DIR = Path(__file__).parent
N_RUNS = 5

GROUND_TRUTH = {
    "P-01": "Oscar Health", "P-02": "Best Buy", "P-03": "Akuna Capital",
    "P-04": "R/GA", "P-05": "Doist", "P-06": "Raymond James",
}


# ---------------------------------------------------------------------------
# Build the IDENTIFIED packet: minimal, mechanical, quote-body-only substitution.
# ---------------------------------------------------------------------------
# Every excerpt line has the shape: quote body ... "  -- [attribution] -- more metadata
# The em-dash-bracket boundary is the same one build_rater_page.py's classify_source()
# anchors on to separate quote from attribution. Only text BEFORE that boundary is
# eligible for substitution -- attribution tags like [company careers page] are source-
# type labels, not identity, and are left untouched on purpose (see module docstring).
_ATTRIBUTION_START_RE = re.compile(r"—\s*\[")
_COMPANY_TOKEN_RE = re.compile(r"\[\s*(?:the\s+)?[Cc]ompany\b([^\]]*)\]")


def _substitute_line(line: str, company_name: str) -> str:
    m = _ATTRIBUTION_START_RE.search(line)
    boundary = m.start() if m else len(line)
    quote_part, rest = line[:boundary], line[boundary:]
    quote_part = _COMPANY_TOKEN_RE.sub(lambda mm: company_name + mm.group(1), quote_part)
    return quote_part + rest


def make_identified_packet(section1_text: str, company_name: str) -> str:
    return "\n".join(_substitute_line(line, company_name) for line in section1_text.split("\n"))


# ---------------------------------------------------------------------------
# BLIND condition: load already-collected data. Do not regenerate.
# ---------------------------------------------------------------------------
def _model_tag(model: str) -> str:
    return model.replace(".", "").replace("-", "_")


def existing_blind_csv_for(packet_id: str) -> Path:
    # P-01's first run predates the --packet/output-naming fix (08-17 handoff) and is a
    # deliberately-preserved "housekeeping fossil" with no model tag in the filename.
    if packet_id == "P-01":
        candidates = [OUTPUT_DIR / "runs_v2_gpt55_P01.csv"]
    else:
        candidates = [OUTPUT_DIR / f"runs_v2_{_model_tag(MODEL)}_{packet_id}.csv"]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        f"No existing blind-condition data for {packet_id} at {candidates[0]}. "
        f"Run `python scorer_variance_test_v2.py --packet {packet_id}` first -- "
        f"this script reuses that data rather than re-running the blind condition."
    )


def load_blind(packet_id: str) -> pd.DataFrame:
    df = pd.read_csv(existing_blind_csv_for(packet_id))
    if len(df) != N_RUNS * len(DIMENSIONS):
        raise ValueError(
            f"{packet_id}: expected {N_RUNS * len(DIMENSIONS)} rows in the blind CSV, "
            f"found {len(df)}. Re-run scorer_variance_test_v2.py --packet {packet_id} "
            f"with --n-runs {N_RUNS} to regenerate before comparing."
        )
    unexpected_models = set(df["model"]) - {MODEL}
    if unexpected_models:
        print(f"  [warn] {packet_id} blind data was scored with {unexpected_models}, "
              f"not the pinned {MODEL} -- comparison may not isolate identification.",
              file=sys.stderr)
    return df


# ---------------------------------------------------------------------------
# IDENTIFIED condition: fresh runs, same call shape as scorer_variance_test_v2.py.
# ---------------------------------------------------------------------------
def run_identified(client: OpenAI, packet_id: str, rubric: str, packet_identified: str,
                    n_runs: int, temperature: float, reasoning_effort: str) -> pd.DataFrame:
    raw_dir = OUTPUT_DIR / f"raw_test1_identified_{packet_id}"
    raw_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(1, n_runs + 1):
        print(f"    identified run {i}/{n_runs}...")
        messages = build_messages(rubric, packet_identified)
        response, temp_honored = call_with_retry(client, messages, MODEL, temperature, reasoning_effort)
        parsed = json.loads(response.choices[0].message.content)
        (raw_dir / f"run_{i}.json").write_text(json.dumps({
            "run_index": i, "packet_id": packet_id, "condition": "identified",
            "model": MODEL, "temperature_honored": temp_honored,
            "reasoning_effort": reasoning_effort, "response": response.model_dump(),
        }, indent=2), encoding="utf-8")
        for dim in DIMENSIONS:
            rows.append({
                "run": i, "dimension": dim, "score": float(parsed[dim]["score"]),
                "confidence": float(parsed[dim]["confidence"]), "model": MODEL,
                "packet_id": packet_id, "temperature_honored": temp_honored,
            })
    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / f"runs_test1_identified_{packet_id}.csv", index=False)
    return df


# ---------------------------------------------------------------------------
# Comparison: condition means vs. pooled SE, not raw point deltas.
# ---------------------------------------------------------------------------
def compare(packet_id: str, blind: pd.DataFrame, identified: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for dim in DIMENSIONS:
        b = blind[blind.dimension == dim]["score"]
        idn = identified[identified.dimension == dim]["score"]
        b_mean, b_sd = b.mean(), b.std(ddof=1)
        i_mean, i_sd = idn.mean(), idn.std(ddof=1)
        n = len(b)
        se_delta = ((b_sd**2 + i_sd**2) / n) ** 0.5
        delta = i_mean - b_mean
        rows.append({
            "packet_id": packet_id, "dimension": dim,
            "blind_mean": b_mean, "blind_sd": b_sd,
            "identified_mean": i_mean, "identified_sd": i_sd,
            "delta": delta, "se_delta": se_delta,
            "delta_over_se": (delta / se_delta) if se_delta > 0 else float("nan"),
            "exceeds_1.5se": abs(delta) > 1.5 * se_delta if se_delta > 0 else (delta != 0),
        })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Test 1 properly: blind vs identified, n=5/condition, all 6 packets.")
    parser.add_argument("--packet", default="all", choices=VALID_PACKETS + ["all"])
    parser.add_argument("--n-runs", type=int, default=N_RUNS)
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set in the environment.")

    anchors = load_anchors()
    rubric = build_rubric_text(anchors)
    client = OpenAI(api_key=api_key)

    packets = VALID_PACKETS if args.packet == "all" else [args.packet]
    all_comparisons = []

    for packet_id in packets:
        company = GROUND_TRUTH[packet_id]
        print(f"\n{packet_id} ({company})")

        blind_df = load_blind(packet_id)
        print(f"  loaded {len(blind_df)} existing blind rows from {existing_blind_csv_for(packet_id).name}")

        packet_path = packet_path_for(packet_id)
        section1 = load_packet_section1(packet_path)
        packet_identified = make_identified_packet(section1, company)
        # Count actual substitutions made (occurrences of the real name in the output),
        # not raw regex matches -- the regex alone also matches attribution-tag brackets
        # like [company careers page], which _substitute_line's em-dash boundary check
        # correctly excludes from substitution. Counting raw matches overstates this.
        n_subs = packet_identified.count(company)
        print(f"  built identified packet: {n_subs} company-name token(s) substituted "
              f"(source-attribution tags left untouched)")

        identified_df = run_identified(client, packet_id, rubric, packet_identified,
                                        args.n_runs, TEMPERATURE, REASONING_EFFORT)

        cmp_df = compare(packet_id, blind_df, identified_df)
        all_comparisons.append(cmp_df)
        print(cmp_df.drop(columns=["packet_id"]).to_string(
            index=False, float_format=lambda x: f"{x:.3f}"))

    full = pd.concat(all_comparisons, ignore_index=True)
    full.to_csv(OUTPUT_DIR / "test1_comparison_all_packets.csv", index=False)

    print("\n" + "=" * 100)
    print("GLOBAL SUMMARY -- all packets x all dimensions "
          f"({len(full)} independent (packet, dimension) comparisons)")
    print("=" * 100)
    n_exceed = full["exceeds_1.5se"].sum()
    print(f"Cells with |delta| > 1.5x pooled SE: {n_exceed}/{len(full)}")
    print(f"Mean |delta| across all cells: {full['delta'].abs().mean():.4f}")
    print(f"Mean pooled SE across all cells: {full['se_delta'].mean():.4f}")
    if n_exceed:
        print("\nCells exceeding the 1.5x SE bar:")
        print(full[full["exceeds_1.5se"]].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print("\nInterpretation reminder: this measures score-level effect of KNOWING THE COMPANY NAME,")
    print("with the same evidence held constant. It does NOT by itself validate or invalidate whether")
    print("scrubbing helps in production -- the re-identification attack result already showed scrubbing")
    print("often fails to prevent identification outright for 5/6 companies. This test is the other half:")
    print("given that the model KNOWS the company, does that knowledge move the score beyond noise.")


if __name__ == "__main__":
    main()
