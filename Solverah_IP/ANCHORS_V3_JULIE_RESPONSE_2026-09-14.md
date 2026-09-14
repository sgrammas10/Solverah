# anchors_v3 — Julie's response (received 2026-09-14)

Reply to `ANCHORS_V3_FOR_JULIE_2026-09-01.md`. Her words are verbatim below; the
"applies as" lines are the derived edits and are NOT yet made. `anchors_v3_PROPOSED.json`
still carries the memo's wording; the frozen `rater_app/anchors.json` is untouched and
stays untouched. Round-1 scores were taken against the frozen file and are not rescored.

## 1. Feedback's low bands

> I agree with removing warmth/supportiveness from the low bands. I think warmth is
> orthogonal to feedback style and shouldn't inherently push Feedback downward. I would
> reconsider "open disagreement is rare," though, because disagreement itself isn't
> necessarily feedback. I would prefer something like "candid developmental or corrective
> input is rare in the evidence" to keep the construct focused on critique.

Applies as: warmth-orthogonal rewrite CONFIRMED. Feedback 0.1 band becomes
"Feedback is occasional and softened. Critique, when it comes, is cushioned or indirect,
and candid developmental or corrective input is rare in the evidence." Drop "open
disagreement is rare".

## 2. The Collaboration / Feedback line

> I initially thought both, but I want to qualify that. "People raise concerns freely and
> managers listen" is not automatically Feedback evidence. I would treat it as
> Collaboration/workplace-climate evidence unless the concern contains evaluative,
> corrective, developmental, or behavioral input directed toward someone's work or
> behavior. A passage can support both dimensions, but it should independently satisfy
> each definition rather than being assigned to both because communication occurred.

Applies as: the rule for BOTH dimensions' where-to-look and boundary text. Default is
Collaboration. Feedback requires evaluative / corrective / developmental / behavioral
input aimed at someone's work or behavior. Dual citation is allowed only when each
definition is independently met — never because communication occurred.

## 3. Decision's guardrail

> I agree that following procedures and ownership alone shouldn't count as Decision
> evidence, but I think the exclusion is too absolute. Procedures become Decision evidence
> when they describe how decisions are actually reached—for example, required analysis,
> approval layers, consensus, escalation, or who has authority to make the call. I'd
> distinguish "following a procedure" from "a procedure governing decision-making."

Applies as: guardrail rewritten to the distinction. "Following a procedure" and
"ownership" stay Autonomy. "A procedure governing decision-making" (required analysis,
approval layers, consensus, escalation, who holds the call) IS Decision evidence.

## 4. Skipping a dimension

> Yes. I think we need it. Insufficient evidence is meaningfully different from a 0.5
> score. A 0.5 should mean the evidence genuinely supports a mixed/balanced position; no
> score should mean we don't have enough evidence to characterize the company on that
> dimension. I don't want the model creating apparent knowledge simply because the rater
> was required to select a number.

Applies as: a rater-app feature (skip / no score per dimension) and a data-model change
(nullable score). Downstream consumers — agreement stats, merge, the extractor
comparison, `CompanyDimensionScore` — must tolerate a missing cell. Relationship to the
existing lowest-confidence band needs defining (skip replaces "almost nothing bears on
this" + forced number).

## 5. Decision 0.5 (unprompted)

> I agree with using the midpoint for genuinely mixed evidence, but I wouldn't make
> contradictory evidence automatically equal 0.5. The strength, recency, relevance, and
> amount of evidence still matter. If credible evidence meaningfully supports both poles
> and neither predominates, 0.5 makes sense. If one side clearly outweighs the other, the
> score should still reflect that.

Applies as: soften the memo's 0.5 text. Remove "that is what it exists for". Keep the
"do not resolve a genuine conflict by picking the most persuasive quote" warning; add
that strength, recency, relevance and amount of evidence still decide whether one pole
predominates.

## Status

- All five recorded; none applied. Next: v3.1 via `rater_app/make_anchors_v3.py`, regen
  `anchors_v3_rubric.docx`, keep PROPOSED.
- Sequenced behind the launch chunks (BUILD_PLAN B-4, D-6).
- Nothing in v3 or v3.1 is verified by raters; that gate is unchanged.
