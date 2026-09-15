"""
scorer_variance_test_v2.py

Corrected re-run of the S1-4 variance cell flagged as confounded in
SPRINT_SCORER_PIPELINE_01.md (correction #5): the original
scorer_variance_test.py hard-codes rubric v2.1 (continuous 0-1) and the
retired v3 GT-01 thin packet (~2,880 chars). Swapping only the model on that
fixture measures tier on an instrument nobody is using anymore.

This version:
  * Builds the rubric from ground_truth/rater_app/anchors.json
    (rubric_version "v1-frozen-2026-08-15") -- the actual frozen instrument
    the three human raters are scoring against right now. Discrete 5-band
    (0.1/0.3/0.5/0.7/0.9), not continuous.
  * Uses ground_truth/anonymization/P-01_packet_ANON.txt, Section 1 only
    (the part between "SECTION 1" and "END OF PACKET" -- exactly what a
    rater sees, scrub log excluded), not the old v3 GT-01 fixture.
  * Pins the model to an exact snapshot string (gpt-5.5-2026-04-23), records
    it on every row, and records reasoning_effort.
  * Attempts temperature=1.0 (matching the original run's sampling-variance
    intent); if the API rejects the parameter (reasoning models frequently
    ignore or reject it), retries without it and records
    temperature_honored=False on every row from that run. Near-zero variance
    from an honored temperature and near-zero variance from a rejected one
    are NOT the same finding -- this must not be silently conflated.

Scope, per Sebastian's decision 2026-08-16: single new cell only
(gpt-5.5-2026-04-23 x P-01 real packet x frozen anchors), n=5. NOT the full
2x2 the sprint doc specs -- that would also require the old model re-run on
the new packet and the new model on the old packet, deferred.

Requires OPENAI_API_KEY in the environment (.env in the Solverah repo root).

    python scorer_variance_test_v2.py
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    BadRequestError,
    OpenAI,
    RateLimitError,
)

# ---------------------------------------------------------------------------
# PATHS -- adjust ANCHORS_PATH / PACKET_PATH if the repo moves
# ---------------------------------------------------------------------------

# Solverah_IP has moved before (sibling of the Solverah repo under Desktop/, then
# in-repo at Solverah/Solverah_IP) and may move again, so instead of hard-coding a
# depth, search upward from this file for the first ancestor holding a Solverah_IP/
# whose anchors.json is real. SOLVERAH_IP_DIR always wins outright when set, honored
# verbatim with no existence check.
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
DEFAULT_PACKET_ID = "P-01"


def packet_path_for(packet_id: str) -> Path:
    if packet_id not in VALID_PACKETS:
        raise ValueError(f"--packet must be one of {VALID_PACKETS}, got {packet_id!r}")
    return REPO_IP / "ground_truth" / "anonymization" / f"{packet_id}_packet_ANON.txt"


ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

load_dotenv(ENV_PATH if ENV_PATH.exists() else None)
load_dotenv()  # also pick up any .env in cwd

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

MODEL = "gpt-5.5-2026-04-23"  # pinned exact snapshot, not the "gpt-5.5" alias
REASONING_EFFORT = "medium"  # matches the model's stated default; recorded on every row
N_RUNS = 5
TEMPERATURE = 1.0  # attempted; falls back and is logged if the model rejects it

DIMENSIONS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]
SCORE_BAND_VALUES = [0.1, 0.3, 0.5, 0.7, 0.9]
CONFIDENCE_BAND_VALUES = [0.1, 0.3, 0.6, 0.9]

OUTPUT_DIR = Path(__file__).parent / "results" / "scorer_variance_v2"


def output_paths_for(packet_id: str, model: str) -> tuple[Path, Path]:
    """Every output is stamped with packet + model so results can never be
    mislabeled -- the exact failure this fixes: hand-editing PACKET_PATH
    used to leave P-02 data sitting in a file still named '..._P01.csv'."""
    model_tag = model.replace(".", "").replace("-", "_")
    raw_dir = OUTPUT_DIR / f"raw_v2_{model_tag}_{packet_id}"
    runs_csv = OUTPUT_DIR / f"runs_v2_{model_tag}_{packet_id}.csv"
    return raw_dir, runs_csv


MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 2.0

# ---------------------------------------------------------------------------
# BUILD RUBRIC TEXT FROM anchors.json (the frozen live instrument)
# ---------------------------------------------------------------------------


def load_anchors() -> dict:
    if not ANCHORS_PATH.exists():
        raise FileNotFoundError(
            f"anchors.json not found at {ANCHORS_PATH}. Set SOLVERAH_IP_DIR if the repo moved."
        )
    return json.loads(ANCHORS_PATH.read_text(encoding="utf-8"))


def build_rubric_text(anchors: dict) -> str:
    lines = []
    lines.append("SOLVERAH")
    lines.append("Company Culture Rating Rubric")
    lines.append(f"Ground-truth scoring instrument · {anchors['rubric_version']} · frozen for round 1")
    lines.append("")
    lines.append(
        "Score each of the six dimensions independently, using ONLY the evidence packet "
        "provided. For each dimension, pick exactly one band value from "
        f"{anchors['band_values']} for the score, and exactly one band value from "
        "the confidence bands below for the confidence. Do not interpolate between bands."
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
    lines.append("Agreement rule (for context, not something you compute): "
                  + json.dumps(anchors["agreement_rule"]))
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


def load_packet_section1(packet_path: Path) -> str:
    if not packet_path.exists():
        raise FileNotFoundError(
            f"Packet not found at {packet_path}. Set SOLVERAH_IP_DIR if the repo moved, "
            f"or check --packet matches an existing P-0N_packet_ANON.txt file."
        )
    raw = packet_path.read_text(encoding="utf-8")
    start_marker = "########## SECTION 1"
    end_marker = "########## END OF PACKET ##########"
    start = raw.find(start_marker)
    end = raw.find(end_marker)
    if start == -1 or end == -1:
        raise ValueError(
            "Could not find SECTION 1 / END OF PACKET markers -- packet format may have "
            "changed. Refusing to guess at the boundary (this is exactly the rater-page "
            "scrub-log leak bug from 08-15b; do not repeat it here)."
        )
    section = raw[start:end + len(end_marker)]
    return section.strip()


# ---------------------------------------------------------------------------
# RESPONSE SCHEMA -- enum-constrained to the frozen bands, not free continuous
# ---------------------------------------------------------------------------

_DIMENSION_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "enum": SCORE_BAND_VALUES},
        "confidence": {"type": "number", "enum": CONFIDENCE_BAND_VALUES},
    },
    "required": ["score", "confidence"],
    "additionalProperties": False,
}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {dim: _DIMENSION_SCHEMA for dim in DIMENSIONS},
    "required": DIMENSIONS,
    "additionalProperties": False,
}

INSTRUCTION = (
    "Score the evidence packet against the rubric on these six dimensions: "
    + ", ".join(DIMENSIONS)
    + ". For each dimension, choose a score from exactly these band values: "
    f"{SCORE_BAND_VALUES}, and a confidence from exactly these band values: "
    f"{CONFIDENCE_BAND_VALUES}. "
    "Base your scoring only on the rubric and packet text provided below. "
    "Do not use any outside knowledge, web search, or tools, even if you recognise the "
    "company from the evidence."
)


def build_messages(rubric: str, packet: str) -> list[dict]:
    user_content = f"RUBRIC:\n{rubric}\n\nEVIDENCE PACKET:\n{packet}\n\n{INSTRUCTION}"
    return [{"role": "user", "content": user_content}]


def call_with_retry(client: OpenAI, messages: list[dict], model: str, temperature: float | None, reasoning_effort: str):
    """Returns (response, temperature_honored: bool)."""
    kwargs = dict(
        model=model,
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "dimension_scores", "strict": True, "schema": RESPONSE_SCHEMA},
        },
    )
    # reasoning_effort is only meaningful on reasoning models; pass it and let the
    # API reject it if unsupported rather than guessing.
    try_kwargs = dict(kwargs, temperature=temperature, reasoning_effort=reasoning_effort)

    last_exc: Exception | None = None
    temperature_honored = True
    active_kwargs = try_kwargs
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(**active_kwargs)
            return response, temperature_honored
        except BadRequestError as exc:
            msg = str(exc).lower()
            # First BadRequestError: try stripping temperature, then reasoning_effort,
            # in case either param is unsupported for this model/endpoint combo.
            if "temperature" in msg and "temperature" in active_kwargs:
                print(f"  [param] temperature rejected by API ({exc}); retrying without it", file=sys.stderr)
                active_kwargs = {k: v for k, v in active_kwargs.items() if k != "temperature"}
                temperature_honored = False
                continue
            if "reasoning_effort" in msg and "reasoning_effort" in active_kwargs:
                print(f"  [param] reasoning_effort rejected by API ({exc}); retrying without it", file=sys.stderr)
                active_kwargs = {k: v for k, v in active_kwargs.items() if k != "reasoning_effort"}
                continue
            raise
        except (RateLimitError, APIConnectionError, APITimeoutError, APIStatusError) as exc:
            last_exc = exc
            is_retryable = isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError)) or (
                isinstance(exc, APIStatusError) and exc.status_code in (429, 500, 502, 503, 504)
            )
            if not is_retryable or attempt == MAX_RETRIES:
                raise
            sleep_s = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 1)
            print(f"  [retry] attempt {attempt}/{MAX_RETRIES} failed ({type(exc).__name__}); retrying in {sleep_s:.1f}s", file=sys.stderr)
            time.sleep(sleep_s)
    raise last_exc  # pragma: no cover


def run_once(client: OpenAI, run_index: int, model: str, temperature: float, reasoning_effort: str, rubric: str, packet: str, packet_id: str, packet_path: Path, raw_dir: Path) -> list[dict]:
    messages = build_messages(rubric, packet)
    response, temperature_honored = call_with_retry(client, messages, model, temperature, reasoning_effort)
    timestamp = datetime.now(timezone.utc).isoformat()
    content = response.choices[0].message.content
    parsed = json.loads(content)

    raw_record = {
        "run_index": run_index,
        "timestamp": timestamp,
        "model": model,
        "requested_temperature": temperature,
        "temperature_honored": temperature_honored,
        "reasoning_effort": reasoning_effort,
        "packet_id": packet_id,
        "packet_path": str(packet_path),
        "rubric_version": "v1-frozen-2026-08-15",
        "response": response.model_dump(),
    }
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"run_{run_index}.json").write_text(json.dumps(raw_record, indent=2), encoding="utf-8")

    rows = []
    for dim in DIMENSIONS:
        dim_result = parsed[dim]
        rows.append(
            {
                "run": run_index,
                "dimension": dim,
                "score": float(dim_result["score"]),
                "confidence": float(dim_result["confidence"]),
                "model": model,
                "packet_id": packet_id,
                "temperature_honored": temperature_honored,
                "reasoning_effort": reasoning_effort,
                "timestamp": timestamp,
            }
        )
    return rows


def print_mood_effect(df: pd.DataFrame, n_runs: int) -> None:
    """The per-run correlated severity shift -- flagged in the 2026-08-07 handoff as
    the finding that mattered more than per-dimension SD, because it's what breaks
    'five of six moved the same direction' style arguments."""
    pivot = df.pivot(index="dimension", columns="run", values="score").reindex(DIMENSIONS)
    pivot = pivot.reindex(columns=range(1, n_runs + 1))
    run_means = pivot.mean(axis=0)
    grand_mean = run_means.mean()
    deviations = run_means - grand_mean
    print("\nPER-RUN MOOD EFFECT (mean deviation across all 6 dims, by run):")
    for run_i, dev in deviations.items():
        print(f"  run{run_i}: {dev:+.4f}")
    print(f"  spread (max-min): {deviations.max() - deviations.min():.4f}")


def print_stat_table(df: pd.DataFrame, value_col: str, n_runs: int) -> pd.DataFrame:
    pivot = df.pivot(index="dimension", columns="run", values=value_col)
    pivot = pivot.reindex(columns=range(1, n_runs + 1))
    pivot.columns = [f"run{c}" for c in pivot.columns]
    pivot = pivot.reindex(DIMENSIONS)
    pivot["mean"] = pivot.mean(axis=1)
    pivot["sd"] = pivot[[f"run{i}" for i in range(1, n_runs + 1)]].std(axis=1, ddof=1)
    pivot["min"] = pivot[[f"run{i}" for i in range(1, n_runs + 1)]].min(axis=1)
    pivot["max"] = pivot[[f"run{i}" for i in range(1, n_runs + 1)]].max(axis=1)
    pivot["range"] = pivot["max"] - pivot["min"]
    print(pivot.to_string(float_format=lambda x: f"{x:.3f}"))
    return pivot


def main() -> None:
    parser = argparse.ArgumentParser(description="Corrected variance re-test: gpt-5.5 x a real anonymized packet x frozen anchors.")
    parser.add_argument("--packet", default=DEFAULT_PACKET_ID, choices=VALID_PACKETS, help=f"Which packet to score (default: {DEFAULT_PACKET_ID})")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--n-runs", type=int, default=N_RUNS)
    parser.add_argument("--temperature", type=float, default=TEMPERATURE)
    parser.add_argument("--reasoning-effort", default=REASONING_EFFORT)
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set in the environment.")

    packet_path = packet_path_for(args.packet)
    raw_dir, runs_csv = output_paths_for(args.packet, args.model)

    anchors = load_anchors()
    rubric = build_rubric_text(anchors)
    packet = load_packet_section1(packet_path)
    print(f"Packet: {args.packet}   Model: {args.model}   Reasoning effort: {args.reasoning_effort}")
    print(f"Loaded rubric {anchors['rubric_version']} ({len(rubric)} chars) and packet ({len(packet)} chars) from:")
    print(f"  {ANCHORS_PATH}")
    print(f"  {packet_path}\n")

    client = OpenAI(api_key=api_key)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    for i in range(1, args.n_runs + 1):
        print(f"Run {i}/{args.n_runs}...")
        rows = run_once(client, i, args.model, args.temperature, args.reasoning_effort, rubric, packet, args.packet, packet_path, raw_dir)
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    df.to_csv(runs_csv, index=False)
    print(f"\nWrote {runs_csv}")
    print(f"Wrote raw responses to {raw_dir}\n")

    temp_honored_values = df["temperature_honored"].unique()
    print("=" * 80)
    print(f"TEMPERATURE HONORED: {temp_honored_values} (requested {args.temperature})")
    print("=" * 80)

    print("\nSCORE")
    score_stats = print_stat_table(df, "score", args.n_runs)
    print("\nCONFIDENCE")
    confidence_stats = print_stat_table(df, "confidence", args.n_runs)

    print_mood_effect(df, args.n_runs)

    max_sd_row = pd.concat(
        [score_stats["sd"].rename("score_sd"), confidence_stats["sd"].rename("confidence_sd")], axis=1
    ).max(axis=1)
    print("\n" + "=" * 80)
    print(f"SUMMARY: mean score SD = {score_stats['sd'].mean():.4f}, mean confidence SD = {confidence_stats['sd'].mean():.4f}")
    print(f"Largest single-dimension SD observed: {max_sd_row.max():.4f} ({max_sd_row.idxmax()})")
    print("Pre-registered bar (SPRINT_SCORER_PIPELINE_01.md): SD ~0.02-0.03 -> tier is load-bearing; SD stays ~0.05+ -> deltas stay inside noise.")
    print("=" * 80)


if __name__ == "__main__":
    main()
