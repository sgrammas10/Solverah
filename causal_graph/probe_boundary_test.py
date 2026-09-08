"""
probe_boundary_test.py -- precision test for extremity_flag.LLMBandProbe at the
0.1 / 0.3 boundary and against off-axis evidence.

WHY
---
The gate test (run_probe_gate_test.py) proved only that the probe is not dead on
arrival: three obvious floor matches, two easy opposite-pole controls. It says
nothing about the boundary that actually produces false positives in production --
distinguishing genuinely-extreme evidence from merely-leaning-low evidence, and
rejecting evidence that belongs to a different dimension entirely.

DESIGN
------
Every quote below is REAL, taken from the six anonymised packets (via the
2026-09-01 run_all_dims_evidence.py run and the round-1 rater returns). Nothing is
synthetic, because synthetic quotes are unrealistically clean and would flatter the
probe.

Four categories, and the labels differ in how much they rest on judgment:

  A  FLOOR        expect True.  Tracks the dimension's own 0.1 band text closely.
                  (judgment-based label, grounded in the band text)
  B  LEANING      expect False. Directionally low but matches the 0.3/0.5 band
                  better than 0.1. *** THE PRODUCTION-CRITICAL CATEGORY *** --
                  failures here mean the flag over-fires on ordinary companies.
                  (judgment-based label, the softest of the four)
  C  OFF-AXIS     expect False. Real quote belonging to a DIFFERENT dimension, fed
                  to this dimension's probe. Objectively labelable: a pace quote is
                  not autonomy evidence regardless of how one reads it. Failures
                  mean the probe matches general negative sentiment rather than the
                  specific description it was given.
  D  OPPOSITE     expect False. Matches the dimension's 0.9 band. Objectively
                  labelable. Failures here would be alarming.

Category C includes deliberate LEXICAL TRAPS -- off-axis quotes that share salient
words with the floor band text (e.g. "mandatory overtime is required" fed to the
autonomy probe, whose 0.1 band text mentions "mandatory procedures"). A probe doing
real semantic matching rejects these; a probe doing keyword matching does not.

Expectations are declared here, in the file, before the run. Do not edit a label to
make a run pass -- a mismatch is a result about the probe, which is the point.

COST: one API call per dimension (6 total).

Run from decision_test/causal_graph/ with SOLVERAH_IP_DIR=../ip_test set.
"""
import argparse
import json
import os
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from openai import OpenAI
import scorer_pipeline as sp
from extremity_flag import LLMBandProbe, ForcedChoiceBandProbe

# (quote, category, expected_match, note)
CASES: dict[str, list[tuple[str, str, bool, str]]] = {
    "autonomy": [
        ("Typically works under close supervision.", "A", True, "0.1 band: 'work assigned top-down'"),
        ("Follow a range of mandatory procedures", "A", True, "0.1 band: 'follow established processes'"),
        ("they believe in top down micromanagement.", "A", True, "0.1 band: 'reviews cite micromanagement'"),
        ("You'll perform repairs by troubleshooting and following our procedures.", "A", True, "explicit procedure-following"),
        ("Our four priorities give us a clear view of where we're headed", "B", False, "top-down direction, but strategic clarity is not micromanagement -> 0.3/0.5"),
        ("Work within Agile teams to deliver high-quality software in iterative releases.", "B", False, "structured process, but Agile implies team self-direction -> 0.5"),
        ("During our peak period from November to April, mandatory overtime is required.", "C", False, "LEXICAL TRAP: 'mandatory' also appears in the 0.1 band text, but this is a PACE quote"),
        ("Outdated tech and systems", "C", False, "innovation evidence, not autonomy"),
        ("annual performance review process", "C", False, "feedback evidence, not autonomy"),
        ("You act on instinct and initiative, not instruction.", "D", False, "0.9 band"),
        ("No politics, no process tax, no committees.", "D", False, "0.9 band"),
    ],
    "feedback": [
        ("annual performance review process", "A", True, "0.1 band: 'feedback is occasional'"),
        ("mid-year touch points and formal end-of-year discussions", "A", True, "0.1 band: infrequent formal cadence"),
        ("structured performance reviews", "B", False, "cadence exists but frequency unstated -> 0.5, not extreme"),
        ("encourages proactive conversation between managers and employees.", "B", False, "proactive/ongoing implies MORE frequent -> 0.5/0.7"),
        ("Typically works under close supervision.", "C", False, "autonomy evidence, not feedback"),
        ("fast-paced, team-oriented environment", "C", False, "pace evidence, not feedback"),
        ("Give and ask for direct feedback.", "D", False, "directness -> high pole"),
    ],
    "innovation": [
        ("Outdated tech and systems", "A", True, "0.1 band: mature/legacy, not R&D-forward"),
        ("taking a conservative approach that translates into a strong, stable firm", "A", True, "0.1 band: 'operational excellence, efficiency focus'"),
        ("As an established but ever-evolving company", "B", False, "CONTESTED: live probe said False on 2026-09-01, this project's fixture hand-labelled it ambiguous. Re-testing deliberately."),
        ("Develop sustainable processes which simplify outputs while ensuring high quality deliverables", "B", False, "optimization-flavoured but about process quality -> 0.3"),
        ("Heavy micromanagement.", "C", False, "autonomy evidence, not innovation"),
        ("annual performance review process", "C", False, "feedback evidence, not innovation"),
        ("Always on the cutting edge.", "D", False, "0.9 band"),
        ("Trying and failing beats not trying and changing nothing.", "D", False, "0.9 band: 'tolerance for failed experiments'"),
    ],
    "pace": [
        ("[Company team members] are encouraged to work 8-hour days and no more than 40 hours/week.", "A", True, "0.1 band: 'calm, sustainable pace'"),
        ("No one is expected to respond to messages immediately.", "A", True, "0.1 band: deliberate cadence"),
        ("This job can be very busy one day and slow the next.", "B", False, "variable -> genuinely mixed, 0.5"),
        ("We think long term.", "B", False, "long planning horizon leans low but is a values statement -> 0.3"),
        ("they believe in top down micromanagement.", "C", False, "autonomy evidence, not pace"),
        ("A tight v0 in two weeks beats a perfect roadmap in two months.", "D", False, "0.9 band"),
        ("fast iteration in a high-performance environment.", "D", False, "0.9 band"),
    ],
    "collaboration": [
        ("People have the space and trust to disconnect to focus on deep work.", "A", True, "0.1 band: 'heads-down norm', individual focus"),
        ("align with stakeholders faster", "B", False, "alignment activity implies some collective work -> 0.5/0.7"),
        ("Outdated tech and systems", "C", False, "innovation evidence, not collaboration"),
        ("During our peak period from November to April, mandatory overtime is required.", "C", False, "pace evidence, not collaboration"),
        ("Never build alone.", "D", False, "0.9 band"),
        ("You'll work as part of a team", "D", False, "high pole"),
    ],
    "decision": [
        ("no document, including this Code, is a substitute for your good judgment.", "A", True, "0.1 band: 'trust your judgement'"),
        ("amplify their intuition, not replace it.", "A", True, "0.1 band: intuition-led"),
        ("combines systematic pricing infrastructure with trader judgment", "B", False, "explicitly BOTH poles -> 0.5, the mixed band"),
        ("Heavy micromanagement.", "C", False, "autonomy evidence, not decision"),
        ("annual performance review process", "C", False, "feedback evidence, not decision"),
        ("Be scientific.", "D", False, "0.9 band"),
        ("define, monitor, and maintain key performance indicators (KPIs)", "D", False, "0.9 band: metrics-first"),
    ],
}

CATEGORY_MEANING = {
    "A": "FLOOR (expect match)      -- misses => flag under-fires (conservative, tolerable)",
    "B": "LEANING (expect NO match) -- failures => flag OVER-FIRES in production  *** CRITICAL ***",
    "C": "OFF-AXIS (expect NO match)-- failures => probe matches sentiment, not the description",
    "D": "OPPOSITE (expect NO match)-- failures => probe is not reading the description at all",
}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dimensions", nargs="*", default=list(CASES.keys()))
    parser.add_argument("--probe", choices=["binary", "forced", "forced_escape"], default="binary",
                        help="binary = LLMBandProbe (yes/no vs the 0.1 description); "
                             "forced = ForcedChoiceBandProbe (pick best of all 5 bands); "
                             "forced_escape = forced choice PLUS an explicit off-axis opt-out")
    parser.add_argument("--seed", type=int, default=17, help="shuffle seed; quotes are shuffled so the probe cannot infer category from ordering")
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY not set")

    client = OpenAI(api_key=api_key)
    anchors = sp.load_anchors()
    if args.probe == "binary":
        probe = LLMBandProbe(client, anchors, model=sp.MODEL, reasoning_effort=sp.REASONING_EFFORT)
    else:
        probe = ForcedChoiceBandProbe(client, anchors, model=sp.MODEL,
                                      reasoning_effort=sp.REASONING_EFFORT,
                                      allow_off_axis=(args.probe == "forced_escape"))
    print(f"Probe: {args.probe} ({type(probe).__name__})")

    print(f"Anchors: {anchors.get('rubric_version')}")
    print(f"Testing {len(args.dimensions)} dimensions -> {len(args.dimensions)} API calls\n")

    by_cat = defaultdict(lambda: {"correct": 0, "total": 0, "failures": []})
    all_rows = []

    for dim in args.dimensions:
        cases = list(CASES[dim])
        random.Random(args.seed).shuffle(cases)
        quotes = [c[0] for c in cases]
        got = probe.probe(quotes, dim)

        print("=" * 78)
        print(f"{dim}")
        for (quote, cat, expected, note), actual in zip(cases, got):
            ok = (actual is expected)
            by_cat[cat]["total"] += 1
            by_cat[cat]["correct"] += ok
            if not ok:
                by_cat[cat]["failures"].append((dim, quote, expected, actual, note))
            mark = "ok  " if ok else "FAIL"
            print(f"  [{mark}] {cat}  expected={str(expected):<5} got={str(actual):<5}  \"{quote[:64]}\"")
            if not ok:
                print(f"         why this label: {note}")
            all_rows.append({"dimension": dim, "quote": quote, "category": cat,
                             "expected": expected, "actual": actual, "note": note, "correct": ok})
        print()

    print("=" * 78)
    print("PER-CATEGORY RESULTS")
    print("=" * 78)
    for cat in ["A", "B", "C", "D"]:
        d = by_cat[cat]
        if not d["total"]:
            continue
        pct = d["correct"] / d["total"] * 100
        print(f"  {cat}  {d['correct']}/{d['total']} ({pct:3.0f}%)   {CATEGORY_MEANING[cat]}")

    print()
    b = by_cat["B"]
    c = by_cat["C"]
    crit_ok = (b["total"] and b["correct"] == b["total"])
    offaxis_ok = (c["total"] and c["correct"] == c["total"])

    print("=" * 78)
    if crit_ok and offaxis_ok:
        print("VERDICT: probe holds the boundary. It rejected every leaning-low quote and every")
        print("off-axis quote, including the lexical traps. False-positive risk from probe")
        print("labelling is low on this set; the flag's remaining weakness is sample size, not")
        print("probe precision.")
    elif not crit_ok:
        print("VERDICT: *** THE PRODUCTION-CRITICAL CATEGORY FAILED. *** The probe called")
        print("leaning-low evidence an extreme-band match. The flag will over-fire on ordinary")
        print("companies. Do NOT wire it into any review queue until the failures below are")
        print("understood -- and do not fix this by editing the labels.")
    else:
        print("VERDICT: off-axis rejection failed while the boundary held. The probe is matching")
        print("general sentiment rather than the specific band description it was handed. The")
        print("flag would fire on the wrong dimension.")
    print("=" * 78)

    for cat in ["B", "C", "D", "A"]:
        for dim, quote, expected, actual, note in by_cat[cat]["failures"]:
            print(f"\n  [{cat} FAIL] {dim}: expected {expected}, got {actual}")
            print(f"    \"{quote}\"")
            print(f"    label rationale: {note}")

    out = Path(__file__).resolve().parent / "results" / f"probe_boundary_test_{args.probe}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "summary": {cat: {"correct": by_cat[cat]["correct"], "total": by_cat[cat]["total"]}
                    for cat in ["A", "B", "C", "D"] if by_cat[cat]["total"]},
        "rows": all_rows,
    }, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
