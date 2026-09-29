"""Generate the proposed anchor rewrites -- the single authoritative generator for them.
Supersedes make_anchors_v2.py, which is kept on disk only as the record of what round-4
Arm B actually tested.

TWO LAYERS, both built from the frozen v1 anchors.json:

  build_v3(v1)     -> anchors_v3_PROPOSED.json. The file Julie reviewed (memo of
                      2026-09-01). NEVER rewritten by this script: build_v3() must reproduce
                      it BYTE FOR BYTE, and main() refuses to build v3.1 if it does not.
                      Until 2026-09-29 this script did not reproduce it -- the 2026-09-01
                      Feedback / Decision / Collaboration-guardrail edits had been made by hand
                      in the JSON, so running the old script silently wiped them. They are
                      ported below as the "2026-09-01" block.
  build_v3_1(v3)   -> anchors_v3_1_PROPOSED.json + ANCHORS_V3_1_CHANGELOG.md. Julie's five
                      rulings of 2026-09-14 (ANCHORS_V3_JULIE_RESPONSE_2026-09-14.md) plus
                      two edits DERIVED from ruling 4 that she did not rule on and must
                      confirm. Every change is an entry in V3_1_CHANGES, which is also what
                      the confirm sheet (Solverah_IP/anchors_v31_confirm/) is generated from,
                      so the sheet cannot drift from the file.

Each v3 edit is tagged with its EVIDENCE STATUS from the 2026-08-17 round-4 A/B:
  [VALIDATED]  Arm B measured the bleed disappearing with this change and no other.
  [NEUTRAL]    No measured effect either way. Retained only where it removes a
               contradiction inside the rubric that a future rater could trip on.
  [FALSIFIED]  Was predicted to fix a bleed and demonstrably did not. Kept ONLY if
               independently justified; the failed prediction is recorded, not hidden.
  [NEW]        Added after round 4, not yet tested. Flagged as unvalidated.

Every replacement is asserted against the exact text it overwrites, so this script
fails loudly rather than drifting if a source file moves underneath it.

anchors.json and anchors_v3_PROPOSED.json are NEVER written by this script.

    python make_anchors_v3.py            # verify v3, write v3.1 + changelog
    python make_anchors_v3.py --check    # verify only; exit 1 on any mismatch
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
V1_PATH = HERE / "anchors.json"
V3_PATH = HERE / "anchors_v3_PROPOSED.json"
V3_1_PATH = HERE / "anchors_v3_1_PROPOSED.json"
CHANGELOG_PATH = HERE / "ANCHORS_V3_1_CHANGELOG.md"
_NEVER_WRITE = {V1_PATH, V3_PATH}

V3_1_VERSION = "v3.1-PROPOSED-2026-09-29"


def render(doc: dict) -> str:
    """The on-disk form of every anchors file this script writes."""
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def render_v3(doc: dict) -> str:
    """anchors_v3_PROPOSED.json's exact form: as render(), but with NO trailing newline.

    The 2026-09-01 hand edits were saved by a tool that dropped the final newline this
    script used to write. That is the file Julie reviewed, so it is reproduced as it is.
    """
    return json.dumps(doc, indent=2, ensure_ascii=False)


def dim(d: dict, key: str) -> dict:
    return next(x for x in d["dimensions"] if x["key"] == key)


# ============================================================================
# v3
# ============================================================================
def build_v3(v1: dict) -> tuple[dict, list[tuple]]:
    """v1 -> v3, exactly as anchors_v3_PROPOSED.json stands on disk."""
    v3 = copy.deepcopy(v1)
    edits: list[tuple] = []

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
    F, D = dim(v3, "feedback"), dim(v3, "decision")

    # ------------------------------------------------------------------------
    # COLLABORATION -- VALIDATED by round 4 Arm B.
    # Proof: at autonomy 0.9 the scorer cited the SAME phrase in both arms -- "own their
    # piece end to end" -- and scored collaboration 0.3 under the frozen bands (5/5 runs)
    # vs. 0.5 under these bands (5/5 runs). Identical evidence, identical model, different
    # band text, different score. Arm A's word-level edit of the same vignette
    # ("how their piece gets done end to end") did NOT fix it: still 0.3 on 5/5. The band
    # text was the cause, not the vignette's vocabulary.
    # ------------------------------------------------------------------------
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

    # ------------------------------------------------------------------------
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
    # ------------------------------------------------------------------------
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

    # ------------------------------------------------------------------------
    # AUTONOMY
    # ------------------------------------------------------------------------
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

    # ------------------------------------------------------------------------
    # 2026-09-01 -- made by hand in the JSON that day (S-09 citation review, then the
    # S-58 free analyses) and ported here 2026-09-29 so this script reproduces the file.
    # The full reasoning is feedback._note below and STATE_MIRROR_2026-09-01c.md:208.
    # All [NEW]: none is validated, and no blind human pass can validate them.
    # ------------------------------------------------------------------------
    swap(C, "keep_distinct",
        "Not the same as Autonomy. Collective teams can still hand individuals full ownership of the how. Score meeting and team density here, decision rights under Autonomy.",
        "Not the same as Autonomy. Collective teams can still hand individuals full ownership "
        "of the how. Score meeting and team density here, decision rights under Autonomy.\n\n"
        "Not the same as Feedback. This was the single most-confused pair in round 1 (9 shared "
        "passages, more than any other, and unguarded until now). Warmth and quality of working "
        "relationships -- \"good team,\" \"supportive coworkers,\" \"people feel comfortable "
        "raising concerns\" -- are weak Collaboration signals about how much people work "
        "together, and are NOT Feedback signals at all. Score HOW MUCH joint work happens here. "
        "Score how critique is delivered under Feedback, and only when the evidence actually "
        "describes critique.",
        "NEW",
        "2026-09-01b: first guard on the collaboration<->feedback pair, the top colliding pair "
        "for raters A and C by excerpt id.")

    swap(F, "where_to_look",
        "“Radical candor” or “direct communication” in values, review-cycle frequency, mentions of blunt vs. supportive delivery, debate and critique norms, conflict-avoidant vs. conflict-embracing signals.",
        "Explicit description of HOW critique is delivered (direct/blunt vs. softened/diplomatic) "
        "and HOW OFTEN performance is discussed (frequent 1:1s or check-ins vs. only an annual "
        "review, or no formal cycle mentioned at all). \"Radical candor,\" \"direct "
        "communication,\" specific review-cycle cadence, and explicit conflict/debate norms are "
        "on-axis. General statements about support, recognition, mentorship, career growth, or "
        "team friendliness are NOT on-axis even when they use the word \"feedback\" -- check "
        "whether the quote actually describes delivery style or frequency, not just whether it "
        "uses feedback-adjacent vocabulary.",
        "NEW",
        "2026-09-01 EDIT 1 (S-09): round-1 Feedback citations were mostly supportiveness.")

    swap(F, "keep_distinct",
        "Score the delivery style and frequency of critique, not whether feedback is “nice.” Both poles are legitimate cultures, not good and bad.",
        "Score the delivery style and frequency of critique specifically -- not whether feedback "
        "is \"nice,\" and not general workplace supportiveness. Recognition, appreciation, "
        "psychological safety, anti-retaliation policies, mentorship programs, career-development "
        "support, and \"we care about our people\" language are NOT feedback signals.\n\n"
        "WARMTH IS ORTHOGONAL TO THIS AXIS AND APPEARS AT BOTH POLES. A caring company may give "
        "feedback constantly and bluntly; a cold one may give it rarely and vaguely. "
        "Supportive-sounding evidence is not low-band evidence -- it is not evidence on this "
        "axis at all. Do not let it pull a score toward either end.\n\n"
        "Cross-dimension leaks observed in round 1, in order of how often they occurred:\n"
        "- COLLABORATION is the most frequent collision (9 shared passages across raters, the "
        "highest of any pair, and it had no guardrail in v1 or in the first v3 draft). How often "
        "people talk to each other, how good the working relationships are, and whether the team "
        "is pleasant to be in are Collaboration (team density) or nothing -- not Feedback. "
        "\"Comfortable coming forward with questions or concerns,\" \"friendly vibe, good team, "
        "good supervisor,\" \"diverse voices and disciplines intersect\" were all filed under BOTH "
        "dimensions by the same rater. Feedback needs a statement about CRITIQUE: how bluntly it "
        "is delivered, or how often.\n"
        "- AUTONOMY: \"acts on instinct, not instruction\" is Autonomy, not Feedback.\n"
        "- PACE: response-time expectations (\"no one expected to respond immediately\") and "
        "work-cadence rituals (a weekly \"housekeeping\" or catch-up day) are Pace, not Feedback, "
        "even when they involve people talking to each other regularly.",
        "NEW",
        "2026-09-01 EDITS 1-3: warmth declared orthogonal; the round-1 leak list; edit 3 moved a "
        "rubric-facing re-quote of the v1 warmth wording into feedback._note.")

    swap_band(F, 0.1, "text",
        "Feedback is occasional and softened. Harmony valued, conflict avoided, supportive or nurturing framing.",
        "Feedback is occasional and softened. Critique, when it comes, is cushioned or indirect, "
        "and open disagreement is rare in the evidence.",
        "NEW",
        "2026-09-01 EDIT 2: the warmth descriptor sat at 0.1 with no counterpart at 0.9, so "
        "supportiveness evidence could only push a score down.")

    swap_band(F, 0.3, "text",
        "Feedback mostly on cycles, delivered with care. Directness is the exception.",
        "Feedback arrives mainly on a fixed cycle and is delivered diplomatically. Directness is "
        "the exception.",
        "NEW",
        "2026-09-01 EDIT 2: 'delivered with care' carried the same warmth association one band up.")

    F["_note"] = (
        "v3 draft. Feedback revised twice on 2026-09-01.\n\n"
        "EDIT 1 (morning, S-09 citation review): keep_distinct and where_to_look rewritten after "
        "round-1 citations from BOTH raters, on nearly every packet, pulled general "
        "supportiveness / psychological-safety evidence instead of critique delivery-style or "
        "frequency evidence.\n\n"
        "EDIT 2 (evening, S-58 free analyses -- S58_FREE_ANALYSES_2026-09-01b.md): edit 1 was "
        "internally contradictory and is corrected here. Its keep_distinct declared "
        "supportiveness a non-signal while sitting directly above an UNCHANGED 0.1 band reading "
        "\"Harmony valued, conflict avoided, supportive or nurturing framing\" -- and its "
        "reconciling sentence (\"extremely supportive and caring while giving feedback rarely and "
        "gently (low band)\") strengthened the very association it meant to break. Measured "
        "asymmetry behind this: a warmth descriptor appeared at 0.1 and had no counterpart at "
        "0.9, so supportiveness evidence could only push a score DOWN. On the frozen text, "
        "round-1 citations like \"never retaliate\" and \"coworkers care about your growth\" were "
        "close to a literal match for the 0.1 band's own words -- so those raters were not "
        "simply off-axis, and the 'off-axis rater error' framing in "
        "FEEDBACK_DIMENSION_DIAGNOSIS_2026-09-01.md is withdrawn for them. The 0.1 and 0.3 band "
        "texts are now decontaminated; the Collaboration collision is guarded for the first "
        "time.\n\n"
        "STILL UNVALIDATED, and the constraint is permanent: Carolynn and George are unavailable "
        "for any further rater time, there is no budget for paid raters, and Julie is excluded on "
        "authorship grounds (D-12(b)). No blind human pass can test this. The only measurable "
        "consumer left is the LLM extractor, and the Decision precedent is that an anchor rewrite "
        "can be a complete no-op for it. Evidence scarcity is also still live and unaddressed by "
        "any wording: P-04's own QA records that its one current, detailed account of feedback "
        "delivery sits on a review source the collector is not permitted to quote, so at least "
        "part of Feedback-THIN is a collection-rule artifact rather than a fact about the "
        "world.\n\n"
        "EDIT 3 (same evening, caught by an assertion in s58_combined_run.py before any API "
        "call): edit 2's keep_distinct explained the fix by QUOTING the v1 0.1 band's warmth "
        "phrase and attaching it to the low band. keep_distinct is rubric-facing -- "
        "build_rubric_text() emits it verbatim to the model -- so that parenthetical put the "
        "contaminant straight back into the instrument while describing its removal, and would "
        "have confounded the arm-B measurement it was written to enable. The historical "
        "explanation now lives here in _note, which is NOT rubric-facing. Text removed from "
        "keep_distinct, preserved for the record:\n"
        "(Round 1 measured the failure this sentence exists to stop: the frozen v1 0.1 band read "
        "\"supportive or nurturing framing\" while its guardrail said supportiveness does not "
        "count, so warmth evidence had a home at the bottom of the scale and no counterpart at "
        "the top. Both blind raters filled sparse Feedback evidence with supportiveness "
        "material. The band text is fixed above; this paragraph is why.)"
    )

    swap(D, "where_to_look",
        "“Data-driven” language, A/B testing and analytics infrastructure, metrics-gated launches, dashboards, vs. founder-gut, design-led or “trust your judgement” signals.",
        "“Data-driven” language, A/B testing and analytics infrastructure, metrics-gated "
        "launches, dashboards, KPI- or analytics-heavy job responsibilities, vs. founder-gut, "
        "design-led, “trust your judgement,” or “taste and curation” signals. Do NOT count "
        "language about approval layers, ownership, independence, or process formality here — "
        "that is Autonomy, see keep_distinct.",
        "NEW",
        "2026-09-01: Carolynn's round-1 Decision citations were Autonomy-flavoured. Measured "
        "no-op for the LLM extractor (identical means on all six packets).")

    swap(D, "keep_distinct",
        "Score the basis of decisions, not their quality. A taste-led company is not worse than a data-led one; they select for different people.",
        "Score the basis of decisions, not their quality — a taste-led company is not worse than "
        "a data-led one, they select for different people. Also not the same as Autonomy: this "
        "dimension is about what a decision rests on (data vs. judgement), not who has authority "
        "to make it or how much process surrounds it. “Decisively,” “ownership,” “without a "
        "formalized process,” “little or no direction,” “following procedures,” and "
        "“conservative, long-term view” are Autonomy or values signals, not Decision signals, "
        "even when they sit in the same sentence as something that sounds decision-related. A "
        "company can require heavy approval and still be entirely data-driven within that "
        "approval process, or grant total independence and still run on pure gut feel.",
        "NEW",
        "2026-09-01: the Autonomy guardrail. Same measured no-op.")

    swap_band(D, 0.5, "text",
        "Both judgement and data carry weight depending on the call.",
        "Both judgement and data carry weight depending on the call. Use this band when "
        "different parts of the packet point to different poles — that is what it exists for. "
        "Do not resolve a genuine conflict in the evidence by picking the quote you find most "
        "persuasive; that is exactly the kind of read that produces spread between raters.",
        "NEW",
        "2026-09-01: aimed at Decision's 0/6 blind agreement. Undocumented until 09-01b.")

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
        "place -- that combined run is the last outstanding confirmation.\n\n"
        "2026-09-01b: Feedback's 0.1 and 0.3 BAND TEXTS were edited (previously only "
        "keep_distinct and where_to_look had been touched), and Collaboration's keep_distinct "
        "gained a Feedback guardrail. Neither change is validated and neither can be validated "
        "by a blind human pass. Note that editing band TEXT -- not just guardrail prose -- means "
        "scores produced under this file are not directly comparable to round 1, which was "
        "scored against v1-frozen-2026-08-15. See feedback._note and "
        "S58_FREE_ANALYSES_2026-09-01b.md. A third same-day correction removed a rubric-facing "
        "parenthetical that re-quoted the superseded band wording; see feedback._note EDIT 3."
    )
    return v3, edits


# ============================================================================
# v3.1 -- Julie's rulings of 2026-09-14
# ============================================================================
# Each change names the field it edits by a PATH:
#   ("dimensions", <dim key>, <field>)
#   ("dimensions", <dim key>, "bands", <band value>, <field>)
#   ("gates", <index>)
#   ("confidence_bands", <band value>, <field>)
#   ("agreement_rule", <key>)                 op "add": key must not exist yet
#   (<top-level key>,)                        op "add": inserted after `after`
# op "replace_in" swaps exactly ONE occurrence of `old` inside the field for `new`;
# op "add" creates a field that must not already exist.
#
# `derived: True` marks an edit Julie did NOT rule on -- inferred from a ruling and
# flagged on her confirm sheet as such.
# `her_words` is a short verbatim excerpt of her reply (ANCHORS_V3_JULIE_RESPONSE_2026-09-14.md).
# `ask` is the question the confirm sheet puts to her about this change.

INSUFFICIENT_EVIDENCE = {
    "label": "Insufficient evidence",
    "text": (
        "Nothing in the packet lets you characterise the company on this dimension, so "
        "record no score. This is not 0.5: 0.5 means the evidence genuinely supports a mixed "
        "or balanced position; insufficient evidence means there is not enough to say "
        "either way. Do not pick a number just because one is asked for."
    ),
}

V3_1_CHANGES: list[dict] = [
    {
        "id": "R1",
        "ruling": 1,
        "derived": False,
        "title": "Feedback's lowest band",
        "her_words": (
            "disagreement itself isn't necessarily feedback. I would prefer something like "
            "\"candid developmental or corrective input is rare in the evidence\""
        ),
        "path": ("dimensions", "feedback", "bands", 0.1, "text"),
        "op": "replace_in",
        "old": "and open disagreement is rare in the evidence.",
        "new": "and candid developmental or corrective input is rare in the evidence.",
        "ask": "Is this the wording you meant?",
    },
    {
        "id": "R2a",
        "ruling": 2,
        "derived": False,
        "title": "Raising concerns: Collaboration by default (Collaboration's guardrail)",
        "her_words": (
            "\"People raise concerns freely and managers listen\" is not automatically "
            "Feedback evidence ... A passage can support both dimensions, but it should "
            "independently satisfy each definition"
        ),
        "path": ("dimensions", "collaboration", "keep_distinct"),
        "op": "replace_in",
        "old": (
            "Warmth and quality of working relationships -- \"good team,\" \"supportive "
            "coworkers,\" \"people feel comfortable raising concerns\" -- are weak Collaboration "
            "signals about how much people work together, and are NOT Feedback signals at all."
        ),
        "new": (
            "Warmth and quality of working relationships -- \"good team,\" \"supportive "
            "coworkers\" -- are weak Collaboration signals about how much people work together, "
            "and are NOT Feedback signals at all. \"People raise concerns freely and managers "
            "listen\" is Collaboration / workplace-climate evidence by default. It becomes "
            "Feedback evidence only when the concern carries evaluative, corrective, "
            "developmental or behavioural input directed at someone's work or behaviour. A "
            "passage may be cited under both dimensions only when it independently satisfies "
            "each definition -- never merely because communication occurred."
        ),
        "ask": "Does this draw the line where you drew it?",
    },
    {
        "id": "R2b",
        "ruling": 2,
        "derived": False,
        "title": "Raising concerns: when it IS Feedback (Feedback's where-to-look)",
        "her_words": (
            "unless the concern contains evaluative, corrective, developmental, or behavioral "
            "input directed toward someone's work or behavior"
        ),
        "path": ("dimensions", "feedback", "where_to_look"),
        "op": "replace_in",
        "old": "not just whether it uses feedback-adjacent vocabulary.",
        "new": (
            "not just whether it uses feedback-adjacent vocabulary. A concern raised, or a "
            "manager listening, counts here only when it carries evaluative, corrective, "
            "developmental or behavioural input directed at someone's work or behaviour; "
            "otherwise it is Collaboration evidence (see keep_distinct)."
        ),
        "ask": "Same rule, written from the Feedback side. Right?",
    },
    {
        "id": "R2c",
        "ruling": 2,
        "derived": False,
        "title": "Citing one passage under both (Feedback's guardrail)",
        "her_words": (
            "rather than being assigned to both because communication occurred"
        ),
        "path": ("dimensions", "feedback", "keep_distinct"),
        "op": "replace_in",
        "old": "were all filed under BOTH dimensions by the same rater. Feedback needs",
        "new": (
            "were all filed under BOTH dimensions by the same rater. Raising concerns freely, "
            "and managers listening, is Collaboration / workplace-climate evidence by default; "
            "it is Feedback evidence only when the concern carries evaluative, corrective, "
            "developmental or behavioural input directed at someone's work or behaviour. A "
            "passage may support both dimensions only when it independently satisfies each "
            "definition -- never merely because communication occurred. Feedback needs"
        ),
        "ask": "Right?",
    },
    {
        "id": "R3a",
        "ruling": 3,
        "derived": False,
        "title": "Decision's guardrail: following a procedure vs. a procedure governing decisions",
        "her_words": (
            "Procedures become Decision evidence when they describe how decisions are actually "
            "reached ... I'd distinguish \"following a procedure\" from \"a procedure governing "
            "decision-making.\""
        ),
        "path": ("dimensions", "decision", "keep_distinct"),
        "op": "replace_in",
        "old": (
            "Also not the same as Autonomy: this dimension is about what a decision rests on "
            "(data vs. judgement), not who has authority to make it or how much process "
            "surrounds it. “Decisively,” “ownership,” “without a formalized process,” “little or "
            "no direction,” “following procedures,” and “conservative, long-term view” are "
            "Autonomy or values signals, not Decision signals, even when they sit in the same "
            "sentence as something that sounds decision-related."
        ),
        "new": (
            "Also not the same as Autonomy. “Following a procedure” is Autonomy: it is about how "
            "much latitude a person has over their own approach. “A procedure governing "
            "decision-making” is Decision evidence: required analysis, approval layers, "
            "consensus, escalation, and who holds the final call all describe how decisions are "
            "actually reached. Score such a procedure by what it makes the decision rest on — a "
            "mandated analysis, business case or metrics gate points toward data; escalation to "
            "a senior person's call, or a consensus of experienced people with no stated "
            "analysis, points toward judgement. “Decisively,” “ownership,” “without a formalized "
            "process,” “little or no direction,” and “conservative, long-term view” stay "
            "Autonomy or values signals, not Decision signals, unless the passage also says what "
            "the decision rests on. A passage may support both dimensions only when it "
            "independently satisfies each definition."
        ),
        "ask": (
            "Decision's scale runs judgement to data. I read your ruling as: a decision "
            "procedure counts here, and is scored by what it makes the decision rest on "
            "(required analysis -> data; escalation to a senior person's call -> judgement). "
            "Is that what you meant, or should approval layers, consensus and escalation count "
            "some other way?"
        ),
    },
    {
        "id": "R3b",
        "ruling": 3,
        "derived": False,
        "title": "Decision's where-to-look: stop excluding approval layers",
        "her_words": (
            "for example, required analysis, approval layers, consensus, escalation, or who has "
            "authority to make the call"
        ),
        "path": ("dimensions", "decision", "where_to_look"),
        "op": "replace_in",
        "old": (
            "Do NOT count language about approval layers, ownership, independence, or process "
            "formality here — that is Autonomy, see keep_distinct."
        ),
        "new": (
            "A procedure that governs how decisions are reached — required analysis or business "
            "cases, metric or experiment gates, approval layers, consensus requirements, "
            "escalation paths, who holds the final call — IS evidence here; score it by what it "
            "makes the decision rest on. Merely following a procedure, ownership, independence, "
            "or process formality in general is Autonomy, see keep_distinct."
        ),
        "ask": "Right?",
    },
    {
        "id": "R4",
        "ruling": 4,
        "derived": False,
        "title": "A way to record \"insufficient evidence\"",
        "her_words": (
            "Insufficient evidence is meaningfully different from a 0.5 score ... I don't want "
            "the model creating apparent knowledge simply because the rater was required to "
            "select a number."
        ),
        "path": ("insufficient_evidence",),
        "op": "add",
        "after": "confidence_bands",
        "new": INSUFFICIENT_EVIDENCE,
        "ask": (
            "The rater page and the LLM can now both record this instead of a score. Is this "
            "definition right?"
        ),
    },
    {
        "id": "R4-rule",
        "ruling": 4,
        "derived": False,
        "title": "How a skipped dimension counts in rater agreement",
        "her_words": "no score should mean we don't have enough evidence to characterize the company",
        "path": ("agreement_rule", "insufficient_evidence"),
        "op": "add",
        "new": (
            "a cell where a rater recorded insufficient evidence is neither agreement nor "
            "disagreement; it is counted separately and never averaged or imputed"
        ),
        "ask": None,  # method, not rubric wording -- Sebastian's (D-12); not on Julie's sheet
    },
    {
        "id": "R5",
        "ruling": 5,
        "derived": False,
        "title": "Decision's middle band: when 0.5 applies",
        "her_words": (
            "I wouldn't make contradictory evidence automatically equal 0.5. The strength, "
            "recency, relevance, and amount of evidence still matter."
        ),
        "path": ("dimensions", "decision", "bands", 0.5, "text"),
        "op": "replace_in",
        "old": (
            "Use this band when different parts of the packet point to different poles — that "
            "is what it exists for."
        ),
        "new": (
            "Use this band when credible evidence supports both poles and neither predominates. "
            "Contradictory evidence is not automatically 0.5: the strength, recency, relevance "
            "and amount of evidence on each side still decide whether one pole outweighs the "
            "other, and if one does, score toward it."
        ),
        "ask": "Is this the wording you meant?",
    },
    {
        "id": "D1",
        "ruling": 4,
        "derived": True,
        "title": "The \"Evidence over gut\" gate (my inference, not your ruling)",
        "her_words": None,
        "path": ("gates", 3),
        "op": "replace_in",
        "old": "more than an honest 0.5 at low confidence.",
        "new": (
            "more than an honest low-confidence score. If nothing in the packet bears on the "
            "dimension at all, mark insufficient evidence rather than scoring 0.5."
        ),
        "ask": (
            "The old gate told raters an \"honest 0.5 at low confidence\" was the safe answer "
            "when unsure, which is the thing your ruling 4 separates out. I changed it. OK?"
        ),
    },
    {
        "id": "D2",
        "ruling": 4,
        "derived": True,
        "title": "The lowest confidence band (my inference, not your ruling)",
        "her_words": None,
        "path": ("confidence_bands", 0.1, "text"),
        "op": "replace_in",
        "old": "You are close to guessing.",
        "new": (
            "You are close to guessing. If nothing bears on it at all, mark insufficient "
            "evidence instead of scoring."
        ),
        "ask": (
            "\"Very low\" confidence and \"insufficient evidence\" sit close together. I kept "
            "Very low and pointed it at the new option for the case where nothing bears at all. "
            "OK, or should Very low go?"
        ),
    },
]


def _locate(doc: dict, path: tuple):
    """Return (container, key) for a change path; see the path grammar above."""
    head = path[0]
    if head == "dimensions":
        d = dim(doc, path[1])
        if path[2] == "bands":
            band = next(b for b in d["bands"] if b["value"] == path[3])
            return band, path[4]
        return d, path[2]
    if head == "gates":
        return doc["gates"], path[1]
    if head == "confidence_bands":
        band = next(b for b in doc["confidence_bands"] if b["value"] == path[1])
        return band, path[2]
    if head == "agreement_rule":
        return doc["agreement_rule"], path[1]
    return doc, head


def path_label(path: tuple) -> str:
    return ".".join(str(p) for p in path)


def apply_change(doc: dict, ch: dict) -> dict:
    """Apply one V3_1_CHANGES entry in place; return a changelog record."""
    if ch["op"] == "replace_in":
        container, key = _locate(doc, ch["path"])
        before = container[key]
        n = before.count(ch["old"])
        assert n == 1, (f"{ch['id']}: expected exactly one occurrence of the old text in "
                        f"{path_label(ch['path'])}, found {n}.\n  old: {ch['old']!r}")
        container[key] = before.replace(ch["old"], ch["new"])
        return {**ch, "field_before": before, "field_after": container[key]}
    if ch["op"] == "add":
        if len(ch["path"]) == 1:
            key = ch["path"][0]
            assert key not in doc, f"{ch['id']}: top-level {key!r} already exists"
            items = list(doc.items())
            at = [k for k, _ in items].index(ch["after"]) + 1
            items.insert(at, (key, copy.deepcopy(ch["new"])))
            doc.clear()
            doc.update(items)
        else:
            container, key = _locate(doc, ch["path"])
            assert key not in container, f"{ch['id']}: {path_label(ch['path'])} already exists"
            container[key] = copy.deepcopy(ch["new"])
        return {**ch, "field_before": None, "field_after": ch["new"]}
    raise ValueError(f"{ch['id']}: unknown op {ch['op']!r}")


def build_v3_1(v3: dict) -> tuple[dict, list[dict]]:
    """v3 -> v3.1. Returns (document, changelog records in V3_1_CHANGES order)."""
    v31 = copy.deepcopy(v3)
    log = [apply_change(v31, ch) for ch in V3_1_CHANGES]
    v31["rubric_version"] = V3_1_VERSION
    v31["_note"] = (
        "PROPOSED, NOT ADOPTED. v3 (anchors_v3_PROPOSED.json, the file Julie reviewed) plus "
        "her five rulings of 2026-09-14 and two edits derived from ruling 4 that she has not "
        "yet confirmed. Generated by make_anchors_v3.py; ANCHORS_V3_1_CHANGELOG.md maps every "
        "change to the ruling that produced it. anchors.json (v1-frozen-2026-08-15) is what "
        "round 1 was scored against and is untouched; round 1 is never rescored under this "
        "file. NEW in v3.1: `insufficient_evidence` -- a rater or the LLM may record no score "
        "for a dimension, which is distinct from 0.5, and agreement_rule says how such a cell "
        "counts. Nothing in v3 or v3.1 has been verified by raters."
    )
    return v31, log


# ============================================================================
# Output
# ============================================================================
def changelog_markdown(log: list[dict]) -> str:
    out = [
        "# anchors v3.1 -- changelog",
        "",
        f"`anchors_v3_1_PROPOSED.json` ({V3_1_VERSION}) = `anchors_v3_PROPOSED.json` + the "
        "changes below. GENERATED by `make_anchors_v3.py` from `V3_1_CHANGES`; do not edit "
        "by hand. Julie's rulings: `Solverah_IP/ANCHORS_V3_JULIE_RESPONSE_2026-09-14.md`.",
        "",
        "Entries marked **derived** are inferences from a ruling that Julie did not make "
        "herself; they are on her confirm sheet as such.",
        "",
    ]
    for rec in log:
        tag = "derived from ruling" if rec["derived"] else "ruling"
        out.append(f"## {rec['id']} -- {tag} {rec['ruling']}: {rec['title']}")
        out.append("")
        out.append(f"Field: `{path_label(rec['path'])}` ({rec['op']})")
        out.append("")
        if rec["her_words"]:
            out.append(f"Julie: \"{rec['her_words']}\"")
            out.append("")
        if rec["op"] == "replace_in":
            out.append("Was:")
            out.append("")
            out.append(f"> {rec['old']}")
            out.append("")
            out.append("Now:")
            out.append("")
            out.append(f"> {rec['new']}")
        else:
            out.append("Added:")
            out.append("")
            out.append("```json")
            out.append(json.dumps(rec["new"], indent=2, ensure_ascii=False))
            out.append("```")
        out.append("")
    return "\n".join(out)


def read_lf(path: Path) -> str:
    """A file's exact characters with CRLF folded to LF, and nothing else normalised.

    This machine runs git with core.autocrlf=true, so the committed blob is LF while the
    working copy is CRLF. Line endings are a checkout artefact, not content; every other
    byte must match.
    """
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def _say(text: str) -> None:
    print(text.encode("ascii", "replace").decode("ascii"))


def _write(path: Path, text: str) -> None:
    if path.resolve() in {p.resolve() for p in _NEVER_WRITE}:
        raise RuntimeError(f"refusing to write {path.name}: it is a frozen record")
    path.write_text(text, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="verify only: v3 reproduces byte for byte and v3.1 on disk is current")
    args = ap.parse_args(argv)

    v1 = json.loads(V1_PATH.read_text(encoding="utf-8"))
    v3, edits = build_v3(v1)
    on_disk = read_lf(V3_PATH)
    if render_v3(v3) != on_disk:
        _say("FAIL: build_v3() does not reproduce anchors_v3_PROPOSED.json byte for byte (line endings aside). "
             "Refusing to build v3.1 on a v3 that is not the file Julie reviewed.")
        return 1
    _say(f"v3 reproduces anchors_v3_PROPOSED.json byte for byte ({len(edits)} edits from v1).")

    v31, log = build_v3_1(v3)
    if args.check:
        ok = V3_1_PATH.exists() and read_lf(V3_1_PATH) == render(v31)
        ok = ok and CHANGELOG_PATH.exists() and \
            read_lf(CHANGELOG_PATH) == changelog_markdown(log)
        _say("v3.1 on disk is current." if ok else "FAIL: v3.1 or its changelog is stale.")
        return 0 if ok else 1

    _write(V3_1_PATH, render(v31))
    _write(CHANGELOG_PATH, changelog_markdown(log))
    _say(f"Wrote {V3_1_PATH.name} ({V3_1_VERSION}) and {CHANGELOG_PATH.name}: "
         f"{len(log)} changes, {sum(1 for r in log if r['derived'])} derived.")
    for rec in log:
        _say(f"  {rec['id']:8s} ruling {rec['ruling']}{' (derived)' if rec['derived'] else ''}"
             f"  {path_label(rec['path'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
