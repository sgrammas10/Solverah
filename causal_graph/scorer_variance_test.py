"""
Runs the same (RUBRIC + PACKET) evidence packet through the OpenAI API N_RUNS
times, independently, to measure how much the six dimension scores vary
between identical, back-to-back requests (pure sampling variance — no
conversation history is carried between runs, no web search, no tools).

Paste your rubric and anonymized evidence packet into the two constants below,
then run:

    python scorer_variance_test.py

Requires OPENAI_API_KEY in the environment.
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
    OpenAI,
    RateLimitError,
)

load_dotenv()

# ---------------------------------------------------------------------------
# PASTE HERE
# ---------------------------------------------------------------------------

RUBRIC = """SOLVERAH
Company Culture Rating Rubric
Ground-truth scoring instrument · v2.1 · RATER COPY · anchors the 0–1 scale for expert raters
Purpose. This is the instrument an expert rater uses to score a company 0–1 on each culture dimension from evidence. Its job is to make two people reading the same evidence land on the same number. Those scores become the ground-truth set that calibrates the scraping pipeline and the person↔company scale.
The scale is fixed and shared with the person side. 0.0 = the low pole, 1.0 = the high pole — the exact same anchoring the candidate assessment uses. A company’s score and a person’s score on the same dimension are directly comparable; the model subtracts them (person − company) to get a signed gap. If you flip a pole here, every gap on that dimension silently inverts. Do not reinterpret the poles.
How to use this
Gather the evidence packet first (see the scoring workbook). Score from what’s in front of you, not from reputation or memory.
Score each of the six dimensions independently. Finish one, then move on — don’t let a company’s overall vibe set all six numbers.
For each dimension, find the band whose evidence description best matches, then pick a number inside that band. Use 0.5 only when the evidence is genuinely balanced or genuinely absent — not as a way to avoid deciding.
Record a confidence (0–1) and a one-line evidence note — tagged with its source type: [careers], [review], [blog], [job post], [news], or [inference] — beside every score. Tagging the source lets us see, later, which scores leaned on the company’s own marketing vs. employee reports. Low confidence is information, not failure — it tells the model to trust its prior.
Five gates — read before every scoring session
1.  Neither pole is better.  Every dimension runs between two legitimate cultures. “Directed” is not worse than “self-directed.” If you catch yourself scoring toward the pole you personally prefer, stop — that’s bias, not signal.
2.  Score the company as it is, not as you’d like it.  You are describing a culture, not grading it. Aspirational careers-page copy is weak evidence; how people describe daily reality is strong evidence.
3.  Kill the halo.  A prestigious or well-liked brand tends to drag every score toward “good.” Score each dimension only from evidence about that dimension. Prestige is captured separately as a confounder, on purpose.
4.  Evidence over gut.  If you can’t point to a line in the packet that supports the number, lower your confidence. A guess dressed as a 0.9 poisons the ground truth more than an honest 0.5 at low confidence.
5.  Stale culture is wrong culture.  Culture drifts with stage. Date every score (as_of) and prefer recent evidence; a Series-A read from four years ago no longer describes the same company.

The six dimensions
Bands shade from the low pole (blue) through mixed (grey) to the high pole (warm). Pick a number inside the matching band; the bands are guides, not the only allowed values.
Autonomy   Directed (0.0)  →  Self-directed (1.0)
Measures:  How much latitude individuals have to set their own approach, priorities, and decisions vs. following assigned direction, defined process, and approval chains.
Where to look:  Job-post verbs (“execute against the roadmap” vs. “own your domain end-to-end”), number of approval layers, presence of detailed SOP/process docs, review mentions of micromanagement vs. freedom, IC decision rights, remote-trust language.
Keep distinct:  Not the same as Collaboration. A person can be highly self-directed AND work collectively. Autonomy is about who decides the how; Collaboration is about alone vs. together.
Score band
Reads as
What the evidence looks like
0.0–0.2
Directed
Work is assigned and specified top-down. Most decisions need sign-off. Postings stress “follow established processes,” reviews cite micromanagement / rigid procedure.
0.3–0.4
Leaning directed
Manager sets direction and priorities; individual chooses tactics inside clear guardrails. Some latitude, but the frame is given.
0.5
Mixed
Direction set at team level, individuals pick the how within it. No strong signal either way, or genuinely balanced.
0.6–0.7
Leaning self-directed
ICs own outcomes and choose their approach with light approval. “Ownership,” results-over-process language present.
0.8–1.0
Self-directed
Individuals set their own priorities and methods with minimal approval. “Founder mentality,” high-trust, flat decision rights pervade the evidence.

Pace   Steady (0.0)  →  Fast (1.0)
Measures:  The tempo and intensity of work — deliberate, sustainable cadence vs. rapid, high-urgency, quick-turnaround.
Where to look:  “Fast-paced” in postings, release/ship frequency, deadline and crunch culture, review mentions of hours/intensity/burnout vs. calm, growth stage, on-call expectations.
Keep distinct:  Not the same as Innovation. A company can move fast while only optimizing (fast execution), or invent slowly (deliberate R&D). Pace is tempo; Innovation is novelty.
Score band
Reads as
What the evidence looks like
0.0–0.2
Steady
Deliberate cadence, long planning horizons, stability/quality emphasis. Reviews describe a calm, sustainable pace.
0.3–0.4
Leaning steady
Generally measured tempo with occasional pushes. Deadlines exist but rarely dominate.
0.5
Mixed
Ordinary business tempo — some crunch, some calm. No dominant signal.
0.6–0.7
Leaning fast
Regular urgency, frequent releases, tight-ish timelines. Energy is up but not relentless.
0.8–1.0
Fast
“Move fast,” rapid iteration, aggressive deadlines. Reviews cite long hours / intensity / hypergrowth.

Collaboration   Solo (0.0)  →  Collective (1.0)
Measures:  How work actually gets produced — individual, heads-down ownership vs. group, cross-functional, in-the-room problem-solving.
Where to look:  Team structure (pods/squads vs. individual owners), meeting and pairing/mob culture, open-plan vs. deep-work norms, “we win together” vs. “own your area” language, async-individual vs. sync-group.
Keep distinct:  Not the same as Autonomy. Collective teams can still hand individuals full ownership of the how. Score meeting/team density here, decision rights under Autonomy.
Score band
Reads as
What the evidence looks like
0.0–0.2
Solo
Individual ownership, heads-down norm, low meeting load. Autonomy of work product; async / individual contribution valued.
0.3–0.4
Leaning solo
Mostly individual work with periodic syncs. Collaboration is coordination, not co-production.
0.5
Mixed
Balanced individual and group work; no dominant mode.
0.6–0.7
Leaning collective
Cross-functional teamwork common, meetings frequent, decisions shared.
0.8–1.0
Collective
Heavy pairing/meeting/consensus culture, cross-functional pods, “we win together” throughout.

Feedback Culture   Sparse / gentle (0.0)  →  Frequent / blunt (1.0)
Measures:  How performance feedback flows — occasional and softened vs. frequent, direct, and unfiltered.
Where to look:  “Radical candor” / “direct communication” in values, review-cycle frequency, mentions of blunt vs. supportive delivery, debate/critique norms, conflict-avoidant vs. conflict-embracing signals.
Keep distinct:  Score the delivery style and frequency of critique, not whether feedback is “nice.” Both poles are legitimate cultures, not good/bad.
Score band
Reads as
What the evidence looks like
0.0–0.2
Sparse / gentle
Feedback is occasional and softened. Harmony valued; conflict avoided; “supportive / nurturing” framing.
0.3–0.4
Leaning gentle
Feedback mostly on cycles, delivered with care. Directness is the exception.
0.5
Mixed
Normal mix of scheduled and ad-hoc feedback, moderate directness.
0.6–0.7
Leaning blunt
Frequent, fairly direct feedback; debate is normal; thicker skin helps.
0.8–1.0
Frequent / blunt
Radical candor, constant unfiltered input, “we tell it straight,” critique/debate is the default.

Innovation Stance   Execute / optimize (0.0)  →  Invent / explore (1.0)
Measures:  Where the work sits on the create-vs-refine axis — improving and scaling what exists vs. inventing what doesn’t exist yet.
Where to look:  R&D emphasis, “0-to-1” vs. “operational excellence” language, patents/research output, product maturity, tolerance for failed bets, “experiment” vs. “scale what works.”
Keep distinct:  Not the same as Pace. Optimizing can be frantic; inventing can be slow. Score novelty of the work, not its speed.
Score band
Reads as
What the evidence looks like
0.0–0.2
Execute / optimize
Operational excellence, refine and scale existing product, efficiency focus, mature offering.
0.3–0.4
Leaning optimize
Mostly improving known things; occasional new bets at the edges.
0.5
Mixed
Real split between maintaining and creating; no dominant stance.
0.6–0.7
Leaning invent
New-product / new-capability work is common; experimentation encouraged.
0.8–1.0
Invent / explore
R&D-forward, novel products, “0-to-1,” research culture, explicit tolerance for failed experiments.

Decision Basis   Intuition / judgement (0.0)  →  Data / analysis (1.0)
Measures:  What decisions actually rest on — experience, taste, and judgement vs. metrics, experiments, and analysis.
Where to look:  “Data-driven” language, A/B-testing and analytics infrastructure, metrics-gated launches, dashboards, vs. founder-gut / design-led / “trust your judgement” signals.
Keep distinct:  Score the basis of decisions, not their quality. A taste-led company is not “worse” than a data-led one; they select for different people.
Score band
Reads as
What the evidence looks like
0.0–0.2
Intuition / judgement
Taste, vision, and experience lead. Founder gut / design-led; “trust your judgement.”
0.3–0.4
Leaning intuition
Judgement-first, data used to confirm rather than decide.
0.5
Mixed
Both judgement and data carry weight depending on the call.
0.6–0.7
Leaning data
Metrics and experiments usually drive decisions; judgement fills gaps.
0.8–1.0
Data / analysis
“Data-driven,” experiment-gated, metrics-first, A/B-everything, analytics-heavy.


Confidence — how sure is this score
Confidence is separate from the score. A 0.9 autonomy score at 0.3 confidence says “probably very self-directed, but I’m not sure.” The model uses it directly: low confidence → the score pulls toward the prior.
Confidence
Reads as
When to use it
0.8–1.0
High
Multiple corroborating first-hand sources (careers page + reviews + eng blog/press) all point the same way.
0.5–0.7
Medium
Some real evidence but from one source type, or sources partly conflict. A defensible read, not a certain one.
0.2–0.4
Low
Thin or indirect evidence — inference from stage/industry, a single ambiguous signal. The model should lean on its prior here.

Companion file: your copy of the Solverah scoring workbook. For each of the six dimensions, record your score (0–1), your confidence (0–1), and a one-line evidence note. Score blind: work only from the evidence packet in front of you, and do not compare numbers with the other rater.
"""

PACKET = """Company GT-01
A. Company careers / values page (the company’s own stated principles)
“Great ideas come from anywhere within our walls and are grounded in both data and instinct.”
“Deliver Results With Agility — We prioritize work that drives long-term value. We execute with urgency, learn from failure, and nimbly pivot. The outcomes of our efforts are impactful, measurable results.”
“Use Good Judgement — We make reasoned, calculated decisions based on data, critical thinking, and pattern recognition.”
“Build the Best Team — We lead by setting the bar high, articulating clear goals, and diving deep. We hire, develop, and leverage only the best… We expect and demonstrate excellence.”
“Collaborate Effectively — We invest in cross-functional global partnerships that maximize impact and minimize duplication… We disagree, align, and commit. Effectiveness and efficiency in collaboration are required.”
“Respect Others — … We balance confidence and candor with humility and kindness.”
“Be an Owner — We are [the Company] first. We act on what’s best for the company, ahead of team or individual goals. We spend every dollar as if it is our own… We always think long-term.”
“Innovate & Improve — We are not limited by precedent. We boldly challenge the norm… We value incremental improvements, but we also look for game-changing breakthroughs.”
“Adapt & Grow — We value adaptability and self-reflection. We find opportunity in every change, experience, and mistake.”
“Come join the team… through data-driven product design [and a] modern end-to-end tech stack.”
B. Employee reviews (most recent found)
Aggregate at collection: ~38% would recommend; culture 2.9/5; work-life 3.3/5; compensation 3.3/5. - 5.0 — Mar 25, 2025 — Operations Manager, current employee — Pros: “Good salary, great schedule, fantastic team.” Cons: “Quick to implement changes with no notice.” - 5.0 — Jul 19, 2026 — Senior Manager, former employee — Pros: “great benefits, competitive pay, growth opportunities, equity.” Cons: “many layers of management, competitive culture.” - 4.0 — Oct 17, 2025 — Sr. Office Administrator, former employee — Pros: “Good work life balance within.” Cons: “Fear of Layoff are always looming.” - Site-compiled review snippets — Pros: “Good work life balance and clear KPIs”; “they tend to listen to employee opinions (in my department anyways).” Cons: “Poor management and little to no change in a company that doesn’t seem to know what they are doing”; “The salaries are low compared to similar jobs nationwide.” - (A second review site’s pages could not be accessed.)
C. Job postings (current)
Numerous “Operations Manager,” “Senior Operations Manager,” and “Senior Manager, Site Operations” roles across US distribution/logistics sites; employer-provided pay ranging roughly $83K–$169K/yr. Postings center on running site/warehouse operations.
D. Engineering / tech blog (the company’s own technical writing)
The company runs a large public engineering blog. Its topics are dominated by data/analytics work — post counts by tag include: “Data Science (90),” “Machine Learning & Artificial Intelligence (68),” “Search & Recommender Systems (19),” “Computer Vision (10),” “Causal Inference (6).”
Recent post title (Jun 2026): “How We Used AI as a Lab Assistant to Run 110 Experiments in Three Days and Cut Projected Tag-Validation Cost by 94%.”
From a Dec 2025 post: “With deadlines getting tighter and codebases growing, we’re all looking for ways to work smarter.”
From a warehouse-operations post (Mar 2026): a “Computer Vision model that automatically detects damaged packages in real-time… moving toward a scalable, automated solution.”
E. Recent news (last 12 months)
Announced a restructuring in 2025 that included closing a distribution warehouse (~215 roles) and realigning logistics; the company framed it as optimizing its distribution network. (It had earlier exited a European market, cutting ~730 roles.)
Publicly described a transition of its technology infrastructure to “a modern, scalable, cloud-based system” and improving “data analytics… to optimize last-mile delivery.”
End of packet GT-01.
"""

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

MODEL = "gpt-4o-2024-08-06"  # pinned exact snapshot, not an alias like "gpt-4o"
N_RUNS = 5
TEMPERATURE = 1.0  # deliberately not 0 — we want to observe normal sampling variance

DIMENSIONS = [
    "autonomy",
    "pace",
    "collaboration",
    "feedback",
    "innovation",
    "decision",
]

OUTPUT_DIR = Path(__file__).parent
RAW_DIR = OUTPUT_DIR / "raw"

MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 2.0

# ---------------------------------------------------------------------------

_DIMENSION_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
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
    + ". For each dimension, give a score from 0.0 to 1.0 and a separate "
    "confidence from 0.0 to 1.0 reflecting how confident you are in that score. "
    "Base your scoring only on the rubric and packet text provided below. "
    "Do not use any outside knowledge or tools."
)


def build_messages() -> list[dict]:
    if not RUBRIC.strip():
        raise ValueError("RUBRIC is empty — paste the scoring rubric before running.")
    if not PACKET.strip():
        raise ValueError("PACKET is empty — paste the evidence packet before running.")
    user_content = (
        f"RUBRIC:\n{RUBRIC}\n\n"
        f"EVIDENCE PACKET:\n{PACKET}\n\n"
        f"{INSTRUCTION}"
    )
    return [{"role": "user", "content": user_content}]


def call_with_retry(client: OpenAI, messages: list[dict], model: str, temperature: float):
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "dimension_scores",
                        "strict": True,
                        "schema": RESPONSE_SCHEMA,
                    },
                },
            )
        except (RateLimitError, APIConnectionError, APITimeoutError, APIStatusError) as exc:
            last_exc = exc
            is_retryable = isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError)) or (
                isinstance(exc, APIStatusError) and exc.status_code in (429, 500, 502, 503, 504)
            )
            if not is_retryable or attempt == MAX_RETRIES:
                raise
            sleep_s = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 1)
            print(
                f"  [retry] attempt {attempt}/{MAX_RETRIES} failed ({type(exc).__name__}); "
                f"retrying in {sleep_s:.1f}s",
                file=sys.stderr,
            )
            time.sleep(sleep_s)
    raise last_exc  # pragma: no cover — unreachable, loop either returns or raises


def run_once(client: OpenAI, run_index: int, model: str, temperature: float, raw_dir: Path) -> dict:
    messages = build_messages()
    response = call_with_retry(client, messages, model, temperature)
    timestamp = datetime.now(timezone.utc).isoformat()
    content = response.choices[0].message.content
    parsed = json.loads(content)

    raw_record = {
        "run_index": run_index,
        "timestamp": timestamp,
        "model": model,
        "temperature": temperature,
        "response": response.model_dump(),
    }
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"run_{run_index}.json"
    raw_path.write_text(json.dumps(raw_record, indent=2), encoding="utf-8")

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
                "timestamp": timestamp,
            }
        )
    return rows


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


def print_deviation_table(df: pd.DataFrame, value_col: str, n_runs: int) -> pd.DataFrame:
    pivot = df.pivot(index="dimension", columns="run", values=value_col)
    pivot = pivot.reindex(columns=range(1, n_runs + 1)).reindex(DIMENSIONS)
    means = pivot.mean(axis=1)
    deviations = pivot.sub(means, axis=0)
    deviations.columns = [f"run{c}" for c in range(1, n_runs + 1)]

    def fmt_signed(x: float) -> str:
        return f"{x:+.3f}"

    print(deviations.to_string(formatters={col: fmt_signed for col in deviations.columns}))
    return deviations


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure run-to-run score variance for a fixed evidence packet."
    )
    parser.add_argument("--model", default=MODEL, help=f"Model string (default: {MODEL})")
    parser.add_argument("--n-runs", type=int, default=N_RUNS, help=f"Number of runs (default: {N_RUNS})")
    parser.add_argument(
        "--temperature", type=float, default=TEMPERATURE, help=f"Sampling temperature (default: {TEMPERATURE})"
    )
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set in the environment.")

    client = OpenAI(api_key=api_key)

    # SAFETY FIX (found while wiring up S1-4's missing gpt-5.5-on-old-packet cell):
    # this script used to write to a hardcoded runs.csv / raw/ regardless of --model,
    # which would silently overwrite the original gpt-4o-2024-08-06 baseline data the
    # instant anyone ran it with a different --model. Same class of bug as the P-01/P-02
    # output-naming near-miss already caught in scorer_variance_test_v2.py (08-17
    # handoff). Fix here is deliberately narrow: the DEFAULT model still writes to the
    # original runs.csv / raw/ paths, unchanged, so nothing that references those exact
    # filenames breaks. Only a NON-default --model gets a model-tagged path instead.
    if args.model == MODEL:
        csv_path, raw_dir = OUTPUT_DIR / "runs.csv", RAW_DIR
    else:
        model_tag = args.model.replace(".", "").replace("-", "_")
        csv_path = OUTPUT_DIR / f"runs_{model_tag}.csv"
        raw_dir = OUTPUT_DIR / f"raw_{model_tag}"
    print(f"Model: {args.model}{'  (default -- writing to the original runs.csv/raw/)' if args.model == MODEL else '  (writing to model-tagged output so the gpt-4o baseline is not touched)'}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    for i in range(1, args.n_runs + 1):
        print(f"Run {i}/{args.n_runs}...")
        rows = run_once(client, i, args.model, args.temperature, raw_dir)
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    df.to_csv(csv_path, index=False)
    print(f"\nWrote {csv_path}")
    print(f"Wrote raw responses to {raw_dir}\n")

    print("=" * 80)
    print("SCORE")
    print("=" * 80)
    score_stats = print_stat_table(df, "score", args.n_runs)

    print("\n" + "=" * 80)
    print("CONFIDENCE")
    print("=" * 80)
    confidence_stats = print_stat_table(df, "confidence", args.n_runs)

    print("\n" + "=" * 80)
    print("SCORE — signed deviation from per-dimension mean")
    print("=" * 80)
    score_deviations = print_deviation_table(df, "score", args.n_runs)

    print("\n" + "=" * 80)
    print("CONFIDENCE — signed deviation from per-dimension mean")
    print("=" * 80)
    confidence_deviations = print_deviation_table(df, "confidence", args.n_runs)

    all_deviations = pd.concat(
        [score_deviations.stack(), confidence_deviations.stack()]
    )
    n_positive = int((all_deviations > 0).sum())
    n_negative = int((all_deviations < 0).sum())
    max_sd_row = pd.concat(
        [score_stats["sd"].rename("score_sd"), confidence_stats["sd"].rename("confidence_sd")],
        axis=1,
    ).max(axis=1)
    max_sd_dimension = max_sd_row.idxmax()
    max_sd_value = max_sd_row.max()

    print("\n" + "=" * 80)
    print(
        f"SUMMARY: {n_positive} positive / {n_negative} negative deviations across "
        f"all dimensions and runs. Largest single-dimension SD observed: "
        f"{max_sd_value:.3f} ({max_sd_dimension})."
    )
    print("=" * 80)


if __name__ == "__main__":
    main()
