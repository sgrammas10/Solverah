"""End-to-end usability test for extremity_flag.py: what is the FIRE RATE, and do
the fires land where humans actually went to 0.1?

A flag that fires on half the cells is useless as a quarantine trigger no matter how
well the probe works. This measures that directly.

Reuses the saved citation data from run_all_dims_evidence.py -- NO re-scoring calls.
The only API cost is the band probe, one call per (packet, dimension) cell examined.

Cost control: by default only cells scoring <= --max-score are probed, since a
FLOOR_SUSPECT on a high-scoring cell is vanishingly unlikely (it would require
unanimous floor evidence under a high score). Raise it to 0.9 for full coverage at
roughly double the calls. Default 0.5 covers every plausible floor case.

Run from decision_test/causal_graph/ with SOLVERAH_IP_DIR=../ip_test set.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from openai import OpenAI
import scorer_pipeline as sp
from extremity_flag import LLMBandProbe, flag_dimension

# Round-1 human scores (raters B=Carolynn, C=George). Embedded so the sweep is
# self-evaluating: a fire on a cell where neither human went near 0.1 is suspect.
HUMAN = {
    ("P-01","autonomy"):(0.9,0.1), ("P-01","pace"):(0.3,0.7), ("P-01","collaboration"):(0.7,0.9),
    ("P-01","feedback"):(0.3,0.5), ("P-01","innovation"):(0.5,0.3), ("P-01","decision"):(0.3,0.9),
    ("P-02","autonomy"):(0.7,0.5), ("P-02","pace"):(0.9,0.7), ("P-02","collaboration"):(0.5,0.9),
    ("P-02","feedback"):(0.3,0.7), ("P-02","innovation"):(0.3,0.3), ("P-02","decision"):(0.7,0.5),
    ("P-03","autonomy"):(0.5,0.9), ("P-03","pace"):(0.9,0.7), ("P-03","collaboration"):(0.3,0.9),
    ("P-03","feedback"):(0.9,0.5), ("P-03","innovation"):(0.5,0.7), ("P-03","decision"):(0.3,0.7),
    ("P-04","autonomy"):(0.7,0.7), ("P-04","pace"):(0.7,0.7), ("P-04","collaboration"):(0.5,0.9),
    ("P-04","feedback"):(0.5,0.5), ("P-04","innovation"):(0.9,0.3), ("P-04","decision"):(0.7,0.1),
    ("P-05","autonomy"):(0.9,0.7), ("P-05","pace"):(0.3,0.5), ("P-05","collaboration"):(0.3,0.3),
    ("P-05","feedback"):(0.7,0.3), ("P-05","innovation"):(0.7,0.3), ("P-05","decision"):(0.1,0.9),
    ("P-06","autonomy"):(0.5,0.1), ("P-06","pace"):(0.5,0.5), ("P-06","collaboration"):(0.7,0.7),
    ("P-06","feedback"):(0.5,0.3), ("P-06","innovation"):(0.3,0.1), ("P-06","decision"):(0.9,0.3),
}

parser = argparse.ArgumentParser()
parser.add_argument("--evidence", default="results/all_dims_evidence_2026-09-01.json")
parser.add_argument("--max-score", type=float, default=0.5,
                    help="only probe cells at or below this score (cost control; default 0.5)")
args = parser.parse_args()

api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    raise SystemExit("OPENAI_API_KEY not set")

ev_path = Path(args.evidence)
if not ev_path.is_absolute():
    ev_path = Path(__file__).resolve().parent / ev_path
if not ev_path.exists():
    raise SystemExit(f"Evidence file not found: {ev_path}\nRun run_all_dims_evidence.py first.")

data = json.loads(ev_path.read_text(encoding="utf-8"))
client = OpenAI(api_key=api_key)
anchors = sp.load_anchors()
probe = LLMBandProbe(client, anchors, model=sp.MODEL, reasoning_effort=sp.REASONING_EFFORT)

cells = []
for pk, dims in data.items():
    for d in dims:
        if d["score"] <= args.max_score:
            cells.append((pk, d))

print(f"Evidence: {ev_path.name}")
print(f"Probing {len(cells)} cells (score <= {args.max_score}) out of "
      f"{sum(len(v) for v in data.values())} total -> {len(cells)} API calls\n")

flags = []
for pk, d in cells:
    quotes = [q["quote"] for q in d["quotes"]]
    verified_map = {q["quote"]: q["verified"] for q in d["quotes"]}
    source_map = {q["quote"]: q.get("source_tag") for q in d["quotes"]}
    f = flag_dimension(packet_id=pk, dimension=d["dimension"], score=d["score"],
                       quotes=quotes, verified_map=verified_map, probe=probe,
                       source_map=source_map)
    flags.append(f)
    hb, hc = HUMAN.get((pk, d["dimension"]), (None, None))
    human_hit_floor = (hb == 0.1 or hc == 0.1)
    mark = "FLAG" if f.flag else "    "
    human_note = "  <-- a human scored 0.1 here" if human_hit_floor else ""
    print(f"[{mark}] {pk}/{d['dimension']:<13} score={f.score}  "
          f"floor_match={f.n_matching_floor}/{f.n_verified}  "
          f"humans=({hb},{hc}){human_note}")

fired = [f for f in flags if f.flag]
human_floor_cells = {k for k, (b, c) in HUMAN.items() if b == 0.1 or c == 0.1}
fired_cells = {(f.packet_id, f.dimension) for f in fired}

print("\n" + "=" * 78)
print(f"FIRE RATE: {len(fired)}/{len(cells)} probed cells "
      f"({len(fired)/max(len(cells),1)*100:.0f}%), "
      f"{len(fired)}/{sum(len(v) for v in data.values())} of all cells")
print(f"\nCells where a human used 0.1: {sorted(human_floor_cells)}")
print(f"Cells the flag fired on:      {sorted(fired_cells)}")
print(f"  overlap (flag agrees with a human floor vote): {sorted(fired_cells & human_floor_cells)}")
print(f"  fired with NO human floor vote (possible false positives): "
      f"{sorted(fired_cells - human_floor_cells)}")
print(f"  human floor vote the flag did NOT catch: "
      f"{sorted(human_floor_cells - fired_cells)}")
print("\nInterpretation guide:")
print("  - a LOW fire rate with high overlap = usable quarantine trigger")
print("  - a HIGH fire rate = the flag is not selective enough to gate anything")
print("  - misses are expected on cells with countervailing evidence (by design)")
print("=" * 78)

for f in fired:
    print(f"\n--- {f.packet_id}/{f.dimension} ({f.severity}) ---")
    print(f"  {f.rationale}")
    for p in f.probes:
        if p.matches_floor_band:
            print(f"    matched floor band [{p.source_tag}]: \"{p.quote}\"")

out = Path(__file__).resolve().parent / "results" / "flag_sweep.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps([f.as_dict() for f in flags], indent=2), encoding="utf-8")
print(f"\nWrote {out}")
