r"""
S-58 analysis (ii), RE-SCOPED — run every human rater citation through the settled
band probe.

WHY THE SCOPE CHANGED FROM WHAT STATE.md DESCRIBES
--------------------------------------------------
STATE's (ii) names the primary outcome as "band implied by the cited evidence vs
band the rater assigned". That rests on the probe's WEAKEST measured capability.
From the probe comparison table in extremity_flag.py's own docstring:

    ForcedChoice + off-axis escape:  A floor 9/13 (69%) | B boundary 8/10 (80%)
                                     C off-axis 12/12 (100%) | D opposite 11/11 (100%)

An implied-vs-assigned band delta lives at the 0.1/0.3 boundary, where the probe is
80% accurate and where the same-day boundary test showed the ANALYST's hand labels
were wrong at least 5 times in one direction. Measuring a one-band effect with an
instrument that is one band wrong 20% of the time is not a measurement.

OFF-AXIS DETECTION is the probe's only 100% category, and it is the one that
separates S-58's three candidate mechanisms:

    (c) construct drift  -> HIGH off-axis rate, concentrated by dimension
    (a) valence conflation -> LOW off-axis rate, on-axis quotes displaced toward 0.1
                              on dimensions whose evidence reads negative
    (b) intensity conflation -> LOW off-axis rate, displacement confined to the
                              0.1/0.3 boundary and present on neutral dimensions too

So: PRIMARY OUTCOME = per-(rater, dimension) off-axis rate.
    SECONDARY, DESCRIPTIVE ONLY = implied-vs-assigned band. Do not quote a band
    delta as a finding; the probe cannot support it at this precision.

THE CONTROL ARM IS NOT OPTIONAL
-------------------------------
An off-axis rate has no scale on its own. Is 40% high? Against what? The --arms
default includes `llm`, which runs the EXTRACTOR's own verified citations
(results/all_dims_evidence_2026-09-01.json) through the identical probe. That gives
a same-instrument, same-packets, same-dimensions comparison: do the humans cite
more off-axis material than the extractor does? Without that arm the human numbers
are uninterpretable and should not be written up.

PROMPT IDENTITY
---------------
This script does NOT modify or reimplement ForcedChoiceBandProbe. It injects a
`call_fn`, which is the class's own dependency-injection hook, and captures the
full JSON answer on the way through. The prompt and schema are therefore
byte-identical to the design validated on 2026-09-01. ForcedChoiceBandProbe.probe()
collapses its answer to `best_match == 0.1` and folds off-axis into False, which is
why the full answer has to be captured this way rather than read off the return.

COST
----
One call per (arm, dimension), all six packets' quotes batched into that call --
the same unordered-fragment presentation the probe was validated under.
    --arms B,C,llm  -> 18 calls (default)
    --arms B,C      -> 12 calls
Add A (Julie) only if you want her as a labelled reference; she is excluded from
the S-15 flag on authorship grounds (D-12(b)) and must not be pooled with B/C here.

RUNNING IT (Windows; venv has no python3.exe -- resolve python.exe by absolute path)
    cd <Desktop>\Solverah_IP\analysis_s58
    ..\..\.venv-solverah-3b\Scripts\python.exe s58_citation_probe.py --dry-run
    ..\..\.venv-solverah-3b\Scripts\python.exe s58_citation_probe.py

--dry-run makes ZERO API calls and prints the exact batch sizes and call count.
Run it first. Nothing in the Solverah repo is written to; output lands here.
"""
import argparse, json, glob, os, re, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIMS = ["autonomy","pace","collaboration","feedback","innovation","decision"]
PKTS = ["P-0%d" % i for i in range(1,7)]

ap = argparse.ArgumentParser()
ap.add_argument("--repo-causal-graph", default=str(HERE.parent.parent / "Solverah" / "causal_graph"),
                help="path to the Solverah repo's causal_graph/ (read-only; nothing is written there)")
ap.add_argument("--anchors", default=str(HERE.parent / "ground_truth" / "rater_app" / "anchors.json"),
                help="FROZEN v1 anchors. The probe must see the same text the raters saw.")
ap.add_argument("--returned", default=str(HERE.parent / "ground_truth" / "rater_app" / "returned" / "round1"))
ap.add_argument("--llm-evidence", default="",
                help="path to all_dims_evidence_2026-09-01.json for the control arm")
ap.add_argument("--arms", default="B,C,llm")
ap.add_argument("--model", default="gpt-5.5-2026-04-23")
ap.add_argument("--reasoning-effort", default="medium")
ap.add_argument("--env", default="", help=".env holding OPENAI_API_KEY (default: repo root)")
ap.add_argument("--out", default=str(HERE / "s58_citation_probe_results.json"))
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()

sys.path.insert(0, args.repo_causal_graph)
anchors = json.load(open(args.anchors, encoding="utf-8"))
print(f"anchors rubric_version = {anchors.get('rubric_version')!r}  (must be v1-frozen-2026-08-15)")

# ---------------- collect quotes ----------------
arms = [a.strip() for a in args.arms.split(",") if a.strip()]
# quotes[arm][dimension] = list of (packet, quote_text, assigned_score)
quotes = {a: defaultdict(list) for a in arms}

for f in sorted(glob.glob(os.path.join(args.returned, "*.json"))):
    d = json.load(open(f, encoding="utf-8"))
    if d["rater"] not in quotes: continue
    for row in d["scores"]:
        for q in (row.get("quotes") or []):
            quotes[d["rater"]][row["dimension"]].append((d["packet_id"], q["text"], row["score"]))

if "llm" in arms:
    p = args.llm_evidence or str(HERE / "all_dims_evidence_2026-09-01.json")
    if not os.path.exists(p):
        raise SystemExit(
            f"control arm requested but {p} not found.\n"
            "It lives under the scratch decision_test/ tree, not in the repo (see STATE §2).\n"
            "Copy it here, pass --llm-evidence, or drop 'llm' from --arms -- but read this\n"
            "script's docstring first: without the control arm the human off-axis rates have\n"
            "no scale and should not be written up.")
    ev = json.load(open(p, encoding="utf-8"))
    # Schema written by run_all_dims_evidence.py, confirmed by reading that file:
    #   {packet_id: [{dimension, score, confidence, quotes:[{quote, verified, eid, source_tag}]}]}
    def walk(ev):
        for pk, rows in ev.items():
            if not isinstance(rows, list): continue
            for rec in rows:
                if isinstance(rec, dict) and rec.get("dimension") in DIMS:
                    yield pk, rec["dimension"], rec
    for pk, dim, rec in walk(ev):
        sc = rec.get("score")
        for q in (rec.get("quotes") or []):
            t = q if isinstance(q, str) else (q.get("text") or q.get("quote") or "")
            if t: quotes["llm"][dim].append((pk, t, sc))

print("\nbatches (one API call each):")
ncalls = 0
for a in arms:
    for d in DIMS:
        n = len(quotes[a][d])
        if n: ncalls += 1
        print(f"  arm={a:<4} {d:<14} {n:>4} fragments")
print(f"\nTOTAL API CALLS = {ncalls}")
if args.dry_run:
    print("\n--dry-run: no API calls made. Re-run without --dry-run to execute.")
    sys.exit(0)

# ---------------- probe ----------------
from dotenv import load_dotenv
load_dotenv(args.env or str(Path(args.repo_causal_graph).parent / ".env"))
from openai import OpenAI
from extremity_flag import ForcedChoiceBandProbe

key = os.environ.get("OPENAI_API_KEY")
if not key: raise SystemExit("OPENAI_API_KEY not set")
client = OpenAI(api_key=key)

captured = {}
def make_call_fn(tag):
    def call_fn(messages, schema):
        resp = client.chat.completions.create(
            model=args.model, messages=messages,
            reasoning_effort=args.reasoning_effort,
            response_format={"type":"json_schema","json_schema":{
                "name":"band_choice","strict":True,"schema":schema}})
        captured[tag] = json.loads(resp.choices[0].message.content)["answers"]
        return resp
    return call_fn

rows = []
for a in arms:
    for d in DIMS:
        items = quotes[a][d]
        if not items: continue
        tag = f"{a}:{d}"
        probe = ForcedChoiceBandProbe(client, anchors, model=args.model,
                                      reasoning_effort=args.reasoning_effort,
                                      call_fn=make_call_fn(tag), allow_off_axis=True)
        probe.probe([t for _, t, _ in items], d)      # return value deliberately unused
        ans = {x["index"]: x for x in captured.get(tag, [])}
        for i, (pk, t, sc) in enumerate(items):
            a_i = ans.get(i, {})
            rows.append({"arm": a, "dimension": d, "packet": pk, "quote": t,
                         "assigned_score": sc,
                         "on_axis": a_i.get("describes_this_property"),
                         "implied_band": a_i.get("best_match")})
        print(f"  probed {tag}: {len(items)} fragments")

json.dump(rows, open(args.out, "w", encoding="utf-8"), indent=1)
print(f"\nwrote {args.out}  ({len(rows)} rows)")

# ---------------- report ----------------
print("\n" + "="*78)
print("PRIMARY OUTCOME — OFF-AXIS RATE (probe's only 100%-validated category)")
print("="*78)
print(f"{'dimension':<15}" + "".join(f"{'arm '+a:>12}" for a in arms))
for d in DIMS:
    cells = []
    for a in arms:
        r = [x for x in rows if x["arm"]==a and x["dimension"]==d and x["on_axis"] is not None]
        cells.append(f"{sum(1 for x in r if not x['on_axis'])/len(r):.0%} (n={len(r)})" if r else "-")
    print(f"{d:<15}" + "".join(f"{c:>12}" for c in cells))
for a in arms:
    r = [x for x in rows if x["arm"]==a and x["on_axis"] is not None]
    if r: print(f"  arm {a}: overall off-axis {sum(1 for x in r if not x['on_axis'])/len(r):.0%}  (n={len(r)})")

print("\n" + "="*78)
print("SECONDARY, DESCRIPTIVE ONLY — implied band vs band the rater assigned")
print("(on-axis fragments only; probe is 80% accurate at the 0.1/0.3 boundary —")
print(" do NOT quote a band delta from this as a finding)")
print("="*78)
for a in arms:
    print(f"  arm {a}:")
    for d in DIMS:
        r = [x for x in rows if x["arm"]==a and x["dimension"]==d and x["on_axis"]
             and x["implied_band"] is not None and x["assigned_score"] is not None]
        if not r: continue
        delta = sum(x["implied_band"] - x["assigned_score"] for x in r)/len(r)
        lo = sum(1 for x in r if x["implied_band"]==0.1)
        print(f"    {d:<14} mean(implied - assigned) = {delta:+.3f}   "
              f"implied 0.1 on {lo}/{len(r)} on-axis fragments")
