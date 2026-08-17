"""
reidentification_attack.py -- the LLM adversarial re-identification attack.

08-15b, open item 3: three attack types were named against the anonymized packets
(retained strings/typos, combination-of-facts, and "hand an anon packet to a fresh LLM
and ask it to name the company"). That third one was deprioritized at the time but later
reframed (still 08-15b) as measuring something more important than a ground-truth
housekeeping check: it's the missing PRODUCTION control for Test 1 (blind vs identified),
because "does scrubbing actually reduce identification in practice" is exactly the
question a production scorer's prior-leakage risk depends on, and nobody has measured it.

This script: for each of the 6 anonymized packets, hands Section 1 (the exact text a
rater or the production scorer would see -- same extraction boundary as
scorer_variance_test_v2.py, same "refuse to guess if the markers are missing" discipline)
to a FRESH model call with no other context, and asks it to name the real company. Runs
N times per packet (default 3, not 1) because a single guess -- right or wrong -- doesn't
tell you whether the model is confidently right, confidently wrong, or unstably guessing;
same reasoning the project already applied to scoring (single-run scoring was ruled
"unusable").

    pip install openai python-dotenv pandas
    python reidentification_attack.py                  # all 6 packets, n=3 each
    python reidentification_attack.py --packet P-05     # one packet
    python reidentification_attack.py --n-runs 5        # more runs per packet
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
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
# PATHS -- identical resolution to scorer_variance_test_v2.py, same reasoning:
# Solverah/ and Solverah_IP/ are sibling folders under .../Desktop/. This
# script lives at Solverah/causal_graph/, so parent.parent.parent is the
# folder containing both. Override with SOLVERAH_IP_DIR if your layout differs.
# ---------------------------------------------------------------------------
_DEFAULT_IP_DIR = Path(__file__).resolve().parent.parent.parent / "Solverah_IP"
REPO_IP = Path(os.environ.get("SOLVERAH_IP_DIR", str(_DEFAULT_IP_DIR)))

VALID_PACKETS = ["P-01", "P-02", "P-03", "P-04", "P-05", "P-06"]

# Ground truth -- the real companies behind the roster (08-10 handoff: "Roster: the
# six stand"). ALIASES are used only for the automatic match heuristic below; they are
# not shown to the model.
GROUND_TRUTH = {
    "P-01": {"company": "Oscar Health", "aliases": ["oscar health", "oscar"]},
    "P-02": {"company": "Best Buy", "aliases": ["best buy", "bestbuy"]},
    "P-03": {"company": "Akuna Capital", "aliases": ["akuna capital", "akuna"]},
    "P-04": {"company": "R/GA", "aliases": ["r/ga", "rga", "r ga"]},
    "P-05": {"company": "Doist", "aliases": ["doist", "todoist"]},
    "P-06": {"company": "Raymond James", "aliases": ["raymond james", "rj financial", " rj "]},
}

MODEL = "gpt-5.5-2026-04-23"  # same pinned snapshot as scorer_variance_test_v2.py
REASONING_EFFORT = "medium"
N_RUNS = 3
TEMPERATURE = 1.0
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 2.0

OUTPUT_DIR = Path(__file__).parent


def packet_path_for(packet_id: str) -> Path:
    if packet_id not in VALID_PACKETS:
        raise ValueError(f"packet must be one of {VALID_PACKETS}, got {packet_id!r}")
    return REPO_IP / "ground_truth" / "anonymization" / f"{packet_id}_packet_ANON.txt"


def load_packet_section1(packet_path: Path) -> str:
    """Identical boundary logic to scorer_variance_test_v2.py's function of the same
    name -- deliberately duplicated rather than imported, matching this project's
    existing convention of each test script being independently runnable. Refuses to
    guess at the boundary if the markers are missing, same discipline as the rater-page
    scrub-log fix (build_rater_page.py) and the scorer variance test."""
    if not packet_path.exists():
        raise FileNotFoundError(
            f"Packet not found at {packet_path}. Set SOLVERAH_IP_DIR if the repo moved."
        )
    raw = packet_path.read_text(encoding="utf-8")
    start_marker = "########## SECTION 1"
    end_marker = "########## END OF PACKET ##########"
    start = raw.find(start_marker)
    end = raw.find(end_marker)
    if start == -1 or end == -1:
        raise ValueError(
            "Could not find SECTION 1 / END OF PACKET markers -- packet format may have "
            "changed. Refusing to guess at the boundary."
        )
    return raw[start:end + len(end_marker)].strip()


# ---------------------------------------------------------------------------
# RESPONSE SCHEMA -- structured, not free text, so results are comparable across
# runs and packets without hand-parsing prose every time.
# ---------------------------------------------------------------------------
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "top_guess": {
            "type": "string",
            "description": "Your single best guess at the real company's name, or "
                            "'unknown' if you genuinely have no candidate.",
        },
        "confidence": {"type": "string", "enum": ["none", "low", "medium", "high"]},
        "reasoning": {
            "type": "string",
            "description": "Brief explanation of why you landed on this guess (or why you couldn't).",
        },
        "quoted_clues": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 5,
            "description": "Up to 5 short verbatim phrases from the packet that most "
                            "drove your guess. Empty if confidence is 'none'.",
        },
    },
    "required": ["top_guess", "confidence", "reasoning", "quoted_clues"],
    "additionalProperties": False,
}

INSTRUCTION = (
    "The text below is an anonymized evidence packet describing a real company's culture, "
    "assembled from public sources (careers pages, employee reviews, job postings, news, "
    "and regulatory filings) with names, executives, locations, and identifying figures "
    "removed or replaced. Your task: figure out which REAL company this describes.\n\n"
    "Give your single best guess even if you are not certain -- a low-confidence guess is "
    "still useful data. Say 'unknown' only if you truly have no candidate at all. "
    "Do not use any tools or web search; reason only from the text and what you already know. "
    "Quote the specific phrases (verbatim, short) that most informed your guess."
)


def build_messages(packet: str) -> list[dict]:
    return [{"role": "user", "content": f"{INSTRUCTION}\n\nPACKET:\n{packet}"}]


def call_with_retry(client: OpenAI, messages: list[dict], model: str, temperature: float, reasoning_effort: str):
    """Same retry/fallback shape as scorer_variance_test_v2.py's function of the same
    name: try temperature + reasoning_effort, drop whichever the API rejects, retry
    transient errors with backoff. Returns (response, temperature_honored)."""
    kwargs = dict(
        model=model,
        messages=messages,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "reid_guess", "strict": True, "schema": RESPONSE_SCHEMA},
        },
    )
    active_kwargs = dict(kwargs, temperature=temperature, reasoning_effort=reasoning_effort)
    temperature_honored = True
    last_exc: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(**active_kwargs)
            return response, temperature_honored
        except BadRequestError as exc:
            msg = str(exc).lower()
            if "temperature" in msg and "temperature" in active_kwargs:
                print(f"  [param] temperature rejected ({exc}); retrying without it", file=sys.stderr)
                active_kwargs = {k: v for k, v in active_kwargs.items() if k != "temperature"}
                temperature_honored = False
                continue
            if "reasoning_effort" in msg and "reasoning_effort" in active_kwargs:
                print(f"  [param] reasoning_effort rejected ({exc}); retrying without it", file=sys.stderr)
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


_PUNCT_RE = re.compile(r"[^a-z0-9 ]+")


def auto_match(guess: str, packet_id: str) -> str:
    """Cheap heuristic only -- 'correct' / 'no_match'. Deliberately not trying to grade
    partial credit (right industry, wrong specific company) automatically; the reasoning
    and quoted_clues fields are there so a human reads the near-misses rather than
    trusting a string match to characterize them. Same discipline as this project's
    'disputed' source class: record, don't silently resolve ambiguity in code."""
    norm = _PUNCT_RE.sub("", guess.lower())
    aliases = GROUND_TRUTH[packet_id]["aliases"]
    return "correct" if any(_PUNCT_RE.sub("", a) in norm for a in aliases) else "no_match"


def run_once(client: OpenAI, run_index: int, model: str, temperature: float, reasoning_effort: str,
             packet: str, packet_id: str, raw_dir: Path) -> dict:
    messages = build_messages(packet)
    response, temperature_honored = call_with_retry(client, messages, model, temperature, reasoning_effort)
    timestamp = datetime.now(timezone.utc).isoformat()
    parsed = json.loads(response.choices[0].message.content)

    raw_record = {
        "run_index": run_index,
        "timestamp": timestamp,
        "model": model,
        "requested_temperature": temperature,
        "temperature_honored": temperature_honored,
        "reasoning_effort": reasoning_effort,
        "packet_id": packet_id,
        "ground_truth_company": GROUND_TRUTH[packet_id]["company"],
        "response": response.model_dump(),
        "parsed": parsed,
    }
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"run_{run_index}.json").write_text(json.dumps(raw_record, indent=2), encoding="utf-8")

    return {
        "packet_id": packet_id,
        "run": run_index,
        "ground_truth": GROUND_TRUTH[packet_id]["company"],
        "top_guess": parsed["top_guess"],
        "confidence": parsed["confidence"],
        "auto_match": auto_match(parsed["top_guess"], packet_id),
        "reasoning": parsed["reasoning"],
        "quoted_clues": " | ".join(parsed["quoted_clues"]),
        "temperature_honored": temperature_honored,
        "timestamp": timestamp,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM adversarial re-identification attack on the 6 anonymized packets.")
    parser.add_argument("--packet", default="all", choices=VALID_PACKETS + ["all"])
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--n-runs", type=int, default=N_RUNS)
    parser.add_argument("--temperature", type=float, default=TEMPERATURE)
    parser.add_argument("--reasoning-effort", default=REASONING_EFFORT)
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    load_dotenv()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set in the environment.")

    packets = VALID_PACKETS if args.packet == "all" else [args.packet]
    client = OpenAI(api_key=api_key)
    all_rows: list[dict] = []

    for packet_id in packets:
        packet_path = packet_path_for(packet_id)
        packet = load_packet_section1(packet_path)
        print(f"\n{packet_id} ({GROUND_TRUTH[packet_id]['company']!r} is the answer, not shown to the model) "
              f"-- {len(packet)} chars")
        raw_dir = OUTPUT_DIR / f"raw_reid_{args.model.replace('-', '_').replace('.', '_')}_{packet_id}"
        for i in range(1, args.n_runs + 1):
            print(f"  run {i}/{args.n_runs}...")
            row = run_once(client, i, args.model, args.temperature, args.reasoning_effort,
                            packet, packet_id, raw_dir)
            all_rows.append(row)
            print(f"    guess: {row['top_guess']!r}  confidence: {row['confidence']}  "
                  f"auto_match: {row['auto_match']}")

    df = pd.DataFrame(all_rows)
    out_csv = OUTPUT_DIR / f"reid_attack_{args.model.replace('-', '_').replace('.', '_')}.csv"
    df.to_csv(out_csv, index=False)
    print(f"\nWrote {out_csv}")

    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    summary = df.groupby("packet_id").agg(
        n_runs=("run", "count"),
        n_correct=("auto_match", lambda s: (s == "correct").sum()),
        confidences=("confidence", lambda s: ",".join(s)),
    )
    summary["correct_rate"] = summary["n_correct"] / summary["n_runs"]
    print(summary.to_string())

    overall_rate = (df["auto_match"] == "correct").mean()
    print(f"\nOverall auto-matched identification rate: {overall_rate:.1%} "
          f"({(df['auto_match'] == 'correct').sum()}/{len(df)} runs)")
    print("\nNOTE: auto_match is a cheap alias-substring heuristic -- 'correct' or 'no_match' only.")
    print("It will not catch a right-industry-wrong-company near miss, or a correct guess phrased")
    print("unusually. Read the 'reasoning' and 'quoted_clues' columns in the CSV for anything the")
    print("heuristic calls no_match but that looks close -- that's exactly the kind of partial")
    print("leak (T2 in 08-15b's attack taxonomy: no single fact identifies, the combination might)")
    print("a string match won't surface on its own.")


if __name__ == "__main__":
    main()
