# Feedback Dimension (S-09) — Citation Diagnosis and Anchor Fix

**Date:** 2026-09-01
**Method:** same as the Decision-dimension diagnosis — pull every round-1 rater's cited quotes for this dimension across all 6 packets and check whether they're actually on-axis, rather than trusting the score alone.

**The axis, per `anchors.json` (unchanged in this fix):** low pole "Sparse / gentle" (0.1) vs. high pole "Frequent / blunt" (0.9) — this is specifically about *how* critique is delivered and *how often*, not whether the workplace is good or caring. The existing `keep_distinct` already said "not whether feedback is 'nice'" — that guardrail already existed and evidently isn't working.

## Full citation table, round 1

| Packet | Rater | Score | Cited evidence | On-axis? |
|---|---|---|---|---|
| P-01 | B (Carolynn) | 0.3 | "transparent, systematic approach to human capital frameworks" | Weak/vague — "systematic" gestures at frequency but doesn't describe delivery style |
| P-01 | C (George) | 0.5 | "Give and ask for direct feedback" | **On-axis** |
| | | | "structured performance reviews" | On-axis (frequency) |
| | | | "stab you in the back at a moment's notice" | Off-axis — toxicity, not feedback style |
| | | | "Friendly vibe, good team, good supervisor" | Off-axis — general friendliness |
| | | | "Very stressful... Management could be better" | Off-axis — general negativity |
| | | | "Heavy micromanagement... not supportive" | Off-axis — management/autonomy signal |
| P-02 | B | 0.3 | "Lead efforts to maximize positive results or course-correct" | Weak — vague, borderline |
| | | | note: "cares about developing the employee, allows mistakes" | Off-axis — growth/forgiveness framing |
| P-02 | C | 0.7 | "comfortable coming to you with questions/concerns" | Off-axis — psychological safety |
| | | | "terminated... very bad communications" | Off-axis — fairness/communication complaint, not feedback style |
| | | | "Sales development taken seriously" | Weak — development, not delivery style |
| P-03 | B | 0.9 | "holding employees accountable to commitments, deadlines" | Borderline — accountability implies some directness |
| | | | note: "blamed for something someone else did" | Off-axis — fairness anecdote |
| P-03 | C | 0.5 | "regular talks and workshops... skill sets" | Off-axis — training/development |
| | | | "do not trust leadership... no mentorship model" | Off-axis — trust/mentorship |
| P-04 | B | 0.5 | "listening sessions that encourage creativity" | Off-axis — psychological safety/creativity |
| | | | note: "unclear how feedback plays into work culture" | Rater's own admission of thin evidence |
| P-04 | C | 0.5 | "new manager made it seem like I was messing up" | Borderline-on-axis — describes receiving critical feedback |
| | | | "without feeling recognized or appreciated" | Off-axis — recognition, distinct construct |
| | | | **"You act on instinct and initiative, not instruction"** | **Off-axis — this is an Autonomy quote, not Feedback** |
| P-05 | B | 0.7 | "one day per week for housekeeping, pay off tech debt" | **Off-axis — this is a Pace/cadence quote**, misread as "weekly feedback culture" per Carolynn's own note |
| P-05 | C | 0.3 | "space and trust to disconnect... no one expected to respond immediately" | **Off-axis — this is a Pace/response-time quote**, not feedback delivery style |
| P-06 | B | 0.5 | "training fully prepared me... constant support" | Off-axis — training/support |
| | | | "established but ever-evolving... support of leaders who care" | Off-axis — general investment framing |
| | | | note: "annual performance review process provides feedback" | On-axis (frequency signal) |
| P-06 | C | 0.3 | "established but ever-evolving... support of leaders who care" | Off-axis (same quote Carolynn used) |
| | | | "people-first culture... why many choose to work here" | Off-axis — generic culture marketing |
| | | | "comfortable coming forward... never retaliate" | Off-axis — anti-retaliation / psychological safety |
| | | | "coworkers care about your growth" | Off-axis — career growth |

## What this shows, and how it differs from Decision

Decision's problem was clean and asymmetric: one rater consistently drifted into a neighboring dimension (Autonomy), the other stayed on-axis, and the fix was a `keep_distinct` rewrite naming the specific confusable language. That fix was well-targeted because the failure mode was "wording is ambiguous enough that a careful reader can mis-map it to the wrong axis."

Feedback's failure is broader and hits both raters: across 24 total citations pulled here, only 2-3 are cleanly on-axis ("Give and ask for direct feedback," "structured performance reviews," arguably "annual performance review process"). The overwhelming majority are about a different, unstated construct — call it general workplace supportiveness/psychological safety (recognition, anti-retaliation, mentorship, "we care about you," training support). There are also concrete cross-dimension leaks: one explicit Autonomy citation (P-04/C) and two explicit Pace citations (P-05, both raters) landed under Feedback.

This pattern — both raters drifting the same direction, toward a construct that isn't even one of the six dimensions — looks less like "the wording invites a specific mix-up" (fixable by naming the confusable language, as Decision was) and more like **the packets don't contain much evidence that actually addresses this axis**, so raters default to the nearest tangential material and don't flag their own uncertainty about it. Note P-04/B's free-text note said this directly: "unclear how feedback plays into work culture" — and still committed a 0.5 score at 0.1 confidence rather than treating the packet as genuinely uninformative on this dimension.

## Fix applied

Edited `anchors_v3_PROPOSED.json`'s `feedback.keep_distinct` and `feedback.where_to_look` to explicitly name what does NOT count (recognition, psychological safety, anti-retaliation, mentorship, career development, general team friendliness) and to name the two specific cross-dimension leaks found (Autonomy's "acts on instinct, not instruction"; Pace's response-time and cadence-ritual language). Full text is in the file; `_note` field documents this diagnosis and flags that it has not been tested against round-2 human raters or re-run against the LLM extractor.

**Open question this fix does NOT resolve, and probably can't by itself:** if the underlying problem is that these packets simply don't contain much on-axis Feedback evidence, no amount of anchor wording will manufacture evidence that isn't there. The more direct fix for that half of the problem is a confidence-calibration instruction — explicitly telling raters (and the LLM extractor) to use low confidence when the packet doesn't describe delivery style or frequency directly, rather than defaulting to a mid-band guess dressed up with tangential citations. Worth deciding whether that's worth adding before round 2, rather than treating the `keep_distinct` rewrite alone as sufficient — the Decision-dimension precedent (anchor fix = zero effect on the LLM) is a reason for real skepticism that a similar rewrite alone will move this dimension either.
