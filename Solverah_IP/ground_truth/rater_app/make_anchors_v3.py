"""Generate anchors_v3_PROPOSED.json -- the single authoritative generator for the
proposed anchor rewrite. Supersedes make_anchors_v2.py, which is kept on disk only as
the record of what round-4 Arm B actually tested.

Each edit below is tagged with its EVIDENCE STATUS from the 2026-08-17 round-4 A/B:
  [VALIDATED]  Arm B measured the bleed disappearing with this change and no other.
  [NEUTRAL]    No measured effect either way. Retained only where it removes a
               contradiction inside the rubric that a future rater could trip on.
  [FALSIFIED]  Was predicted to fix a bleed and demonstrably did not. Kept ONLY if
               independently justified; the failed prediction is recorded, not hidden.
  [NEW]        Added after round 4, not yet tested. Flagged as unvalidated.

Every replacement is asserted against the exact v1 string it overwrites, so this script
fails loudly rather than drifting if anchors.json moves underneath it.

anchors.json itself is NEVER written by this script.
"""
import json, copy
from pathlib import Path

src = json.loads(Path("anchors.json").read_text(encoding="utf-8"))
v3 = copy.deepcopy(src)
edits = []

def dim(d, key):
    return next(x for x in d["dimensions"] if x["key"] == key)

def swap(obj, field, old, new, status, why):
    assert obj[field] == old, (f"v1 text for {obj.get('key')}.{field} is not what this "
                              f"patch expects.\n  expected: {old!r}\n  found: {obj[field]!r}")
    obj[field] = new
    edits.append((obj.get("key"), field, status, why))

def swap_band(d, value, field, old, new, status, why):
    b = next(b for b in d["bands"] if b["value"] == value)
    assert b[field] == old, (f"v1 text for {d['key']} band {value}.{field} is not what "
                             f"this patch expects.\n  expected: {old!r}\n  found: {b[field]!r}")
    b[field] = new
    edits.append((f"{d['key']} band {value}", field, status, why))

A, C, I = dim(v3, "autonomy"), dim(v3, "collaboration"), dim(v3, "innovation")

# ============================================================================
# COLLABORATION -- VALIDATED by round 4 Arm B.
# Proof: at autonomy 0.9 the scorer cited the SAME phrase in both arms -- "own their
# piece end to end" -- and scored collaboration 0.3 under the frozen bands (5/5 runs)
# vs. 0.5 under these bands (5/5 runs). Identical evidence, identical model, different
# band text, different score. Arm A's word-level edit of the same vignette
# ("how their piece gets done end to end") did NOT fix it: still 0.3 on 5/5. The band
# text was the cause, not the vignette's vocabulary.
# ============================================================================
swap_band(C, 0.1, "text",
    "Individual ownership, heads-down norm, low meeting load. Async and individual contribution valued.",
    "Heads-down solo production is the norm. Very low meeting load, little or no pairing, "
    "written async updates in place of live working sessions.",
    "VALIDATED",
    "removes 'Individual ownership', the construct this dimension's own keep_distinct "
    "assigns to Autonomy. Round 4 Arm B: autonomy->collaboration bleed 5/5 -> 0/5 at "
    "level 0.9 and 4/5 -> 1/5 at 0.7, on unchanged vignette text.")

swap_band(C, 0.3, "text",
    "Mostly individual work with periodic syncs. Collaboration is coordination, not co-production.",
    "Work is produced alone and brought together at periodic syncs. Meetings are status "
    "and handoff, not joint problem-solving.",
    "VALIDATED",
    "same substitution one band up. Note the correct NON-effect: Arm B still scored 0.3 "
    "on the 0.5 vignette's 'without looping anyone in first' (5/5) -- that phrase is "
    "genuine meeting-density evidence and these bands are supposed to keep scoring it.")

swap(C, "where_to_look",
    "Team structure (pods/squads vs. individual owners), meeting and pairing culture, open-plan vs. deep-work norms, “we win together” vs. “own your area” language, async-individual vs. sync-group.",
    "Team structure (pods/squads vs. single-threaded owners), meeting and pairing culture, "
    "open-plan vs. deep-work norms, “we win together” vs. “heads-down, protect your focus time” "
    "language, async-written vs. sync-group.",
    "NEUTRAL",
    "'own your area' is verbatim Autonomy's 0.7 construct ('Ownership'). Not separately "
    "measured -- it moved together with the band edits -- but pointing raters at it under "
    "Collaboration reintroduces by hand the collision the bands just removed.")

# ============================================================================
# INNOVATION -- the v2 attempt FAILED, and this is the corrected diagnosis.
# Round 4: autonomy 0.1 -> innovation stayed at 5/5 displaced in BOTH arms. The scorer
# cited "step-by-step playbook" on every run of every arm. So:
#   * removing the word "execute" from the vignette (Arm A) did nothing;
#   * renaming the pole and adding a keep_distinct guard (Arm B) did nothing.
# The lexical hypothesis is dead. What survived both is PROCESS-MATURITY vocabulary
# sitting inside Innovation's own low-band text -- "Operational excellence", "efficiency
# focus", "mature offering", and where_to_look's "operational excellence"/"product
# maturity". A mandatory step-by-step playbook matches those directly. Innovation's low
# band is currently written to reward process rigidity, which is an Autonomy fact.
#
# THE TRANSFERABLE FINDING: keep_distinct does NOT override band text. Collaboration was
# fixed by rewriting its BANDS; Innovation was given a guard and a pole rename and did
# not budge. For Julie's rewrite: guards are documentation, bands are the instrument.
# ============================================================================
swap_band(I, 0.1, "text",
    "Operational excellence, refine and scale existing product, efficiency focus, mature offering.",
    "The work is making an existing product better rather than creating a new one — "
    "incremental improvement to something already in market, no new-category bets.",
    "VALIDATED",
    "strips 'Operational excellence' / 'efficiency focus' / 'mature offering': all three "
    "are process-and-maturity signals that a rigid-playbook company matches regardless of "
    "how novel its output is. Rewritten purely in terms of novelty of output, which is "
    "what this dimension's 'measures' field says it scores. Round 5 (2026-08-17): "
    "autonomy 0.1 -> innovation bleed 5/5 -> 2/5, mean 0.14 -> 0.42, on UNCHANGED vignette "
    "text. The scorer still cites 'step-by-step playbook' but now reads it as 0.3-0.5 "
    "instead of 0.1 -- same evidence, different band text, different score, the same "
    "controlled pattern that validated the Collaboration edits.")

swap_band(I, 0.3, "text",
    "Mostly improving known things; occasional new bets at the edges.",
    "Mostly improving things that already exist; occasional genuinely new bets at the edges.",
    "NEUTRAL",
    "minor: 'known things' can read as 'things with a known procedure'. Moved together "
    "with the 0.1 band in round 5 and was NOT independently isolated -- do not claim this "
    "one is validated.")

swap(I, "where_to_look",
    "R&D emphasis, “0-to-1” vs. “operational excellence” language, product maturity, tolerance for failed bets, “experiment” vs. “scale what works.”",
    "R&D emphasis, “0-to-1” vs. “scale what works” language, how much of the roadmap is "
    "new capability vs. improvement of shipped capability, tolerance for failed bets. "
    "Ignore process rigidity here — a documented, tightly-governed process says nothing "
    "about whether the output is novel, and belongs under Autonomy.",
    "NEUTRAL",
    "removes 'operational excellence' and 'product maturity', the two phrases most likely "
    "to make a process-heavy company read as low Innovation. Moved together with the 0.1 "
    "band in round 5 and was NOT independently isolated. Plausibly load-bearing, "
    "unproven.")

swap(I, "low_pole", "Execute / optimize", "Refine / optimize",
    "FALSIFIED",
    "predicted that 'Execute' -- the ordinary verb for doing assigned work -- caused the "
    "autonomy->innovation bleed by lexical collision. Round 4 Arm B: no effect, still 5/5 "
    "displaced. RETAINED anyway on the independent ground that a pole label which doubles "
    "as a generic verb is a hazard for human raters, not because it fixed anything.")
swap_band(I, 0.1, "reads_as", "Execute / optimize", "Refine / optimize",
    "FALSIFIED", "consistency with the renamed pole. Same non-effect.")

swap(I, "keep_distinct",
    "Not the same as Pace. Optimizing can be frantic; inventing can be slow. Score novelty of the work, not its speed.",
    "Not the same as Pace. Optimizing can be frantic; inventing can be slow. Score novelty "
    "of the work, not its speed. Also not the same as Autonomy. How prescribed the method "
    "is says nothing about how novel the output is — a rigid playbook can govern genuinely "
    "new work, and a fully self-directed team can spend all of it refining what exists. Do "
    "not read “follows a detailed brief” as low Innovation or “builds their own approach” "
    "as high Innovation; those are decision-rights facts and belong under Autonomy.",
    "FALSIFIED",
    "this guard says in plain words exactly what the round-4 scorer then did anyway, on "
    "5/5 runs. Retained as documentation for human raters. Do not expect it to move the "
    "LLM scorer -- that is what the band rewrite above is for.")

# ============================================================================
# AUTONOMY
# ============================================================================
swap(A, "keep_distinct",
    "Not the same as Collaboration. A person can be highly self-directed AND work collectively. Autonomy is about who decides the how; Collaboration is about alone vs. together.",
    "Not the same as Collaboration. A person can be highly self-directed AND work "
    "collectively. Autonomy is about who decides the how; Collaboration is about alone vs. "
    "together — score meeting and pairing density there, never here. Not the same as "
    "Innovation either: a prescribed method can produce novel work and a self-directed team "
    "can spend all its time optimizing.",
    "NEUTRAL",
    "directional restatement plus the matching Innovation guard. No measured effect on the "
    "LLM scorer, consistent with the keep_distinct finding above; kept for human raters.")

v3["rubric_version"] = "v3-PROPOSED-2026-08-17"
v3["_note"] = (
    "PROPOSED, NOT ADOPTED. Generated from anchors.json v1-frozen-2026-08-15 by "
    "make_anchors_v3.py. anchors.json is UNTOUCHED and stays frozen while raters are "
    "mid-round on P-01..P-06; adopting this mid-round would invalidate the ground-truth "
    "round in progress. The Collaboration band edits are VALIDATED by a measured A/B "
    "(round 4, 2026-08-17): identical vignette text, bleed 5/5 -> 0/5. The Innovation band "
    "band rewrite is VALIDATED by round 5 (5/5 -> 2/5, mean 0.14 -> 0.42) and supersedes a "
    "v2 attempt that was FALSIFIED. Across rounds 4-5 the reproducible-bleed count fell "
    "from 5 cells to 1, and that survivor is a vignette artifact, not an anchor one. "
    "Per-edit evidence status is in make_anchors_v3.py; the full record is "
    "ANCHOR_BLEED_FIX.md. Nothing here has been tested with the corrected vignettes in "
    "place -- that combined run is the last outstanding confirmation."
)

Path("anchors_v3_PROPOSED.json").write_text(
    json.dumps(v3, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

print(f"Wrote anchors_v3_PROPOSED.json  ({len(edits)} edits)\n")
by = {}
for where, field, status, why in edits:
    by.setdefault(status, []).append((where, field, why))
for status in ["VALIDATED", "NEW", "NEUTRAL", "FALSIFIED"]:
    if status not in by: continue
    print(f"[{status}]  ({len(by[status])})")
    for where, field, why in by[status]:
        print(f"   {where}.{field}\n      {why}\n")

a = json.loads(Path("anchors.json").read_text(encoding="utf-8"))
b = json.loads(Path("anchors_v3_PROPOSED.json").read_text(encoding="utf-8"))
changed = []
def walk(x, y, p=""):
    if isinstance(x, dict):
        for k in x: walk(x[k], y[k], f"{p}.{k}")
    elif isinstance(x, list):
        for i,(xi,yi) in enumerate(zip(x,y)): walk(xi, yi, f"{p}[{i}]")
    elif x != y: changed.append(p)
walk(a, b)
print(f"leaf fields changed: {len(changed)} (expect {len(edits)} edits + _note + rubric_version = {len(edits)+2})")
