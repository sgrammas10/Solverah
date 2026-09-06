r"""
The 22-call combined run: Arm A (S-59 fire rate) + Arm B (S-12 gate).

PRE-REGISTERED in PREREG_COMBINED_RUN_2026-09-01b.md. Read it before acting on output.
In particular: Arm A's fire rate does NOT change the review-queue-not-auto-gate verdict, and
Arm B is a D-21 PILOT whose numbers may not be quoted -- only a qualitative null is actionable.

REPO SAFETY (there is usually another agent working in the Solverah repo)
------------------------------------------------------------------------
  * The repo is added to sys.path and nothing else. Read-only.
  * No git commands, no chdir into the repo, no imports that write.
  * Every output goes to Solverah_IP/analysis_s58/results/.
  * The script ASSERTS its output directory does not resolve inside the repo and refuses
    to start if it does.
  * anchors.json (frozen) is never written. Arm B loads anchors_v3_PROPOSED.json directly and
    passes rubric TEXT to score_packet(), which does no file I/O -- so no SOLVERAH_IP_DIR
    scratch tree is needed and nothing is copied anywhere.

RUNNING IT (Windows; the venv has no python3.exe -- absolute path or you silently get system Python)
    cd <Desktop>\Solverah_IP\analysis_s58
    ..\..\.venv-solverah-3b\Scripts\python.exe s58_combined_run.py --dry-run
    ..\..\.venv-solverah-3b\Scripts\python.exe s58_combined_run.py

--dry-run makes ZERO API calls: it resolves every path, loads and validates both anchor files,
builds the v3 rubric text, reconstructs the saved v1 evidence, and prints the exact call count
per arm. Run it first. If --dry-run is clean, the real run will not fail on plumbing.

If --evidence cannot be found, pass its path. It lives under the scratch decision_test/ tree,
not in the repo (STATE 2). --inspect-evidence prints the file's structure and exits.
"""
import argparse, json, os, re, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
IP   = HERE.parent
DIMS = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]
PKTS = ["P-0%d" % i for i in range(1, 7)]

ap = argparse.ArgumentParser()
ap.add_argument("--repo-causal-graph", default=str(IP.parent / "Solverah" / "causal_graph"))
ap.add_argument("--evidence", default="", help="all_dims_evidence_2026-09-01.json (v1 baseline)")
ap.add_argument("--anchors-v1", default=str(IP / "ground_truth" / "rater_app" / "anchors.json"))
ap.add_argument("--anchors-v3", default=str(IP / "ground_truth" / "rater_app" / "anchors_v3_PROPOSED.json"))
ap.add_argument("--arms", default="A,B")
ap.add_argument("--max-score", type=float, default=0.5, help="Arm A: probe cells at or below this")
ap.add_argument("--env", default="", help=".env with OPENAI_API_KEY (default: repo parent)")
ap.add_argument("--outdir", default=str(HERE / "results"))
ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--inspect-evidence", action="store_true")
args = ap.parse_args()

REPO_CG = Path(args.repo_causal_graph).resolve()
REPO    = REPO_CG.parent
OUT     = Path(args.outdir).resolve()

# ---- repo safety gate ------------------------------------------------------
# Another agent is usually working in the Solverah repo. Identify the repo by its .git
# directory rather than by position, so the guard is exact and does not depend on layout.
def _git_root(p: Path):
    for c in [p, *p.parents]:
        if (c / ".git").exists(): return c
    return None
GIT_ROOT = _git_root(REPO_CG)
for guard in {x for x in (GIT_ROOT, REPO_CG) if x is not None}:
    if OUT == guard or guard in OUT.parents:
        raise SystemExit(f"REFUSING TO RUN: output dir {OUT} resolves inside the repo at {guard}.")
print(f"repo git root    : {GIT_ROOT if GIT_ROOT else '(none found - guard fell back to causal_graph/)'}")
OUT.mkdir(parents=True, exist_ok=True)
print(f"repo (read-only) : {REPO_CG}")
print(f"outputs          : {OUT}")

sys.path.insert(0, str(REPO_CG))

# ---- locate the v1 evidence baseline ---------------------------------------
def find_evidence():
    if args.evidence: return Path(args.evidence)
    for c in [HERE / "all_dims_evidence_2026-09-01.json",
              OUT / "all_dims_evidence_2026-09-01.json"]:
        if c.exists(): return c
    hits = list(IP.parent.glob("**/all_dims_evidence_2026-09-01.json"))
    return hits[0] if hits else None

EV_PATH = find_evidence()
arms = [a.strip().upper() for a in args.arms.split(",") if a.strip()]

def load_evidence(p):
    """Schema written by run_all_dims_evidence.py:
       {packet_id: [{dimension, score, confidence, quotes:[{quote,verified,eid,source_tag}]}]}"""
    raw = json.loads(Path(p).read_text(encoding="utf-8"))
    out = {}
    for pk, rows in raw.items():
        if not isinstance(rows, list): continue
        out[pk] = {r["dimension"]: r for r in rows if isinstance(r, dict) and "dimension" in r}
    if not out: raise SystemExit(f"could not parse {p}; run with --inspect-evidence")
    return out

if args.inspect_evidence:
    if not EV_PATH: raise SystemExit("evidence file not found; pass --evidence")
    raw = json.loads(Path(EV_PATH).read_text(encoding="utf-8"))
    print(f"\n{EV_PATH}\n  top-level type: {type(raw).__name__}, keys: {list(raw)[:8]}")
    k = list(raw)[0]; print(f"  raw[{k!r}] type: {type(raw[k]).__name__}")
    print("  first record:", json.dumps(raw[k][0] if isinstance(raw[k], list) else raw[k], indent=2)[:700])
    sys.exit(0)

V1 = load_evidence(EV_PATH) if EV_PATH else None
if "A" in arms and V1 is None:
    raise SystemExit("Arm A needs the v1 evidence baseline. Pass --evidence, or drop A from --arms.\n"
                     "It is under the scratch decision_test/ tree, not in the repo.")

# ---- plan ------------------------------------------------------------------
armA_cells = []
if "A" in arms:
    for pk in PKTS:
        for d in DIMS:
            r = V1.get(pk, {}).get(d)
            if r and r.get("score") is not None and r["score"] <= args.max_score:
                armA_cells.append((pk, d, r))
print(f"\nArm A: {len(armA_cells)} cells at score <= {args.max_score}  -> {len(armA_cells)} calls")
print(f"Arm B: {len(PKTS) if 'B' in arms else 0} packets (one call each, all six dimensions)"
      f"  -> {len(PKTS) if 'B' in arms else 0} calls")
print(f"TOTAL API CALLS = {len(armA_cells) + (len(PKTS) if 'B' in arms else 0)}")

import scorer_pipeline as sp
from extremity_flag import ForcedChoiceBandProbe, flag_result

anchors_v1 = json.loads(Path(args.anchors_v1).read_text(encoding="utf-8"))
anchors_v3 = json.loads(Path(args.anchors_v3).read_text(encoding="utf-8"))
rubric_v3  = sp.build_rubric_text(anchors_v3)
print(f"\nv1 anchors: {anchors_v1.get('rubric_version')}")
print(f"v3 anchors: {anchors_v3.get('rubric_version')}  -> rubric text {len(rubric_v3)} chars")
fb = next(d for d in anchors_v3["dimensions"] if d["key"] == "feedback")
print("v3 feedback 0.1 band:", next(b['text'] for b in fb['bands'] if b['value'] == 0.1)[:100])
assert "nurturing" not in rubric_v3, "v3 rubric still carries the warmth descriptor - wrong file?"

if args.dry_run:
    print("\n--dry-run: plumbing OK, no API calls made.")
    sys.exit(0)

from dotenv import load_dotenv
load_dotenv(args.env or str(REPO / ".env"))
from openai import OpenAI
key = os.environ.get("OPENAI_API_KEY")
if not key: raise SystemExit("OPENAI_API_KEY not set")
client = OpenAI(api_key=key)
probe = ForcedChoiceBandProbe(client, anchors_v1, allow_off_axis=True)   # v1: the frozen bands

def norm(s): return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", (s or "").lower())).strip()[:120]

def collisions(cells):
    """cells: {packet: {dim: [quotes]}} -> (total, {pair: count})"""
    tot = 0; pair = defaultdict(int)
    for pk, dd in cells.items():
        by = defaultdict(set)
        for d, qs in dd.items():
            for q in qs: by[norm(q)].add(d)
        for _, ds in by.items():
            if len(ds) > 1:
                tot += 1
                ds = sorted(ds)
                for i in range(len(ds)):
                    for j in range(i+1, len(ds)): pair[(ds[i], ds[j])] += 1
    return tot, pair

# ================= ARM A =================
if "A" in arms:
    print("\n" + "="*78 + "\nARM A - fire rate under ForcedChoiceBandProbe(allow_off_axis=True)\n" + "="*78)
    fires = []
    for pk, d, rec in armA_cells:
        qs  = [q["quote"] for q in rec.get("quotes", []) if q.get("verified")]
        if not qs:
            print(f"  {pk}/{d:<14} skipped - no verified citations"); continue
        res = probe.probe(qs, d)
        n_floor = sum(1 for x in res if x is True)
        fired = (n_floor >= 2 and n_floor == len([x for x in res if x is not None]))
        print(f"  {pk}/{d:<14} score={rec['score']}  floor-matches {n_floor}/{len(qs)}"
              f"  {'** FLAG **' if fired else ''}")
        if fired:
            fires.append({"packet": pk, "dimension": d, "score": rec["score"], "quotes": qs})
    rate = len(fires)/len(armA_cells) if armA_cells else 0
    print(f"\n  FIRE RATE: {len(fires)}/{len(armA_cells)} probed ({rate:.0%}); baseline was 2/16 (12%) "
          f"under the binary probe.")
    print("  Pre-registered: P-06/autonomy should still fire; P-06/feedback should stop.")
    print("  PRE-REGISTERED DECISION RULE: this number does NOT change the review-queue verdict.")
    (OUT / "s59_fire_rate_2026-09-01b.json").write_text(
        json.dumps({"probed": len(armA_cells), "fires": fires}, indent=2), encoding="utf-8")

# ================= ARM B =================
if "B" in arms:
    print("\n" + "="*78 + "\nARM B - v3 anchors, one call per packet (D-21 PILOT: quote no number)\n" + "="*78)
    v3 = {}
    for pk in PKTS:
        ppath = sp.packet_path_for(pk)
        ptext = sp.load_packet_section1(ppath)
        result = sp.score_packet(client, ptext, rubric_v3, packet_id=pk,
                                 rubric_version=anchors_v3.get("rubric_version", "?"),
                                 packet_version=sp.packet_version_for(ppath))
        checks = sp.verify_result(result, ptext)
        rows = []
        for dim in result.dimensions:
            dc = [c for c in checks if c.dimension == dim.dimension]
            rows.append({"dimension": dim.dimension, "score": dim.score,
                         "confidence": dim.confidence,
                         "quotes": [{"quote": q,
                                     "verified": bool(next((c for c in dc if c.quote == q and c.matched), None))}
                                    for q in dim.evidence_quotes]})
        v3[pk] = rows
        print(f"  {pk}: " + "  ".join(f"{r['dimension'][:4]}={r['score']}" for r in rows))
    (OUT / "all_dims_evidence_v3_2026-09-01b.json").write_text(json.dumps(v3, indent=2), encoding="utf-8")

    if V1:
        c1 = {pk: {d: [q["quote"] for q in r.get("quotes", [])] for d, r in dd.items()} for pk, dd in V1.items()}
        c3 = {pk: {r["dimension"]: [q["quote"] for q in r["quotes"]] for r in rows} for pk, rows in v3.items()}
        t1, p1 = collisions(c1); t3, p3 = collisions(c3)
        print(f"\n  cross-dimension passage reuse (within packet):  v1 = {t1}   v3 = {t3}")
        for pair in [("collaboration","feedback"), ("autonomy","decision")]:
            print(f"    {pair[0]}<->{pair[1]}:  v1 = {p1.get(pair,0)}   v3 = {p3.get(pair,0)}"
                  f"   {'(newly guarded)' if pair==('collaboration','feedback') else '(guarded this morning)'}")
        print("\n  score movement, mean |v3 - v1| per dimension:")
        for d in DIMS:
            deltas = [abs(next(r["score"] for r in v3[pk] if r["dimension"]==d) - V1[pk][d]["score"])
                      for pk in PKTS if pk in V1 and d in V1[pk]]
            turn = []
            for pk in PKTS:
                if pk not in V1 or d not in V1[pk]: continue
                a = {norm(q["quote"]) for q in V1[pk][d].get("quotes", [])}
                b = {norm(q["quote"]) for r in v3[pk] if r["dimension"]==d for q in r["quotes"]}
                if b: turn.append(len(b-a)/len(b))
            print(f"    {d:<14} mean|delta| = {sum(deltas)/len(deltas):.3f}"
                  f"   citation turnover = {sum(turn)/len(turn):.0%}" if deltas else f"    {d}: n/a")
        print("\n  READ THIS AGAINST THE PRE-REGISTRATION. One draw per arm; D-21 is NOT satisfied.")
        print("  Only a qualitative null (nothing moved anywhere) is actionable. Anything that moved")
        print("  triggers a seeded follow-up (36 calls), not a claim, and no number here is quotable.")
print("\ndone.")
