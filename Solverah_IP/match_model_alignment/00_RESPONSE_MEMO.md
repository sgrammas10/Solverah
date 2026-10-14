# Response to your alignment brief

**For:** Julie. **From:** Sebastian (drafted with the research lane), 2026-10-13.
**Status:** working draft. Everything here is yours to edit. Where something reads as
settled and you disagree, say so; it is cheaper to change now than after data arrives.

Your brief is in this folder as `JULIE_BRIEF_2026-10.md`. The short version of our answer:
we agree with your working position. The six traits stay a **candidate component**, and
**no probability reaches a user** until real outcome data has trained and checked the
model. Users see per-trait reads, how much evidence there is, and flags.

The other documents in this folder are your five requested deliverables, plus one extra
(06, a draft list of gap combinations for you to edit). Each stands alone.

---

## Your questions, one at a time

**1. What is the outcome?** The primary outcome is the last question of the Environment
Report: "Overall, how well is this role working for you?", rated 1 to 5. "Doing well"
means a 4 or 5. This was fixed in a pre-registration on 2026-10-01 before any real data
existed. We heard your note that "doing well" is vague and that someone can be doing well
without thriving. So we are adding satisfaction, performance, engagement, sustainability
and retention as **exploratory** outcomes. They are measured and reported, but they do not
change the primary analysis. Definitions are in `02_OUTCOME_DEFINITIONS.md`.

**2. Is "perfect match = 80%" meaningful?** Not yet, and we agree an S-curve only keeps
numbers between 0 and 1. The 80% is your own baseline answer from the priors form ("8 out
of 10 people who genuinely fit are still doing well"). It is an expert hypothesis. It will
not be shown to anyone as a chance. `04_VALIDATION_ROADMAP.md` sets the bar a number would
have to clear first.

**3. Do six traits cover enough?** No, and we no longer claim they do. The six traits are
**one signal layer** inside the wider system, shown as their own section and never blended
into a single score. Values, trust, influence, management, sustainability, pay and team
are outside them. Manager fit is handled by Manager Match, which stays separate. See
`03_SIX_TRAIT_BOUNDARY.md`.

**4. Can four forced-choice items separate preference from tolerance and context?** No.
We now treat the 24 items as the person's **current stated preferences**, not as "their
trait". Tolerance and non-negotiables are asked as a short separate step: for each trait,
how much more and how much less would still be fine, and up to two **must-haves**. Whether
a preference is lasting or a reaction to current circumstances is a Reflection Engine
question, and that component does not exist yet. People can retake at any time.

**5. Company-wide versus role, team, manager, location?** Every piece of company evidence
now carries a scope: company, division or location, or role. A user can paste a job
posting, which is scored as role-level evidence, and any disagreement between the posting
and the company picture is shown. Confidence is adjusted by company size, in fixed size
buckets; the size of that adjustment is provisional. Teams are not modelled. Manager uncertainty becomes
guidance: questions to ask in interview.

**6. Unknown and mixed evidence without a misleading midpoint?** Each trait is a record,
not a number. **Unknown** means no score, no penalty, and a flag; on a must-have it becomes
an Investigate step. **Mixed** is never averaged: we first check whether scope or recency
explains the split, then show both ends and tell the user the evidence disagrees. This
builds directly on your ruling that insufficient evidence is different from 0.5. Coverage
is always stated ("based on 4 of 6 traits"), and below 3 of 6 the answer is "not enough
evidence" rather than a match.

**7. What assumptions sit in the expert weights?** The penalty table is your twelve
elicited answers plus your baseline. The main assumptions: one expert; a full
pole-to-pole mismatch is the reference gap; no cost inside a person's tolerance and a
straight-line cost beyond it; all six traits weighted equally unless the person names a
must-have; no combined effects between traits. Each entry will carry a "why" and a date.
What would change them, cheapest first, is in `04_VALIDATION_ROADMAP.md`.

**8. Explanation plus uncertainty instead of a chance?** Yes. Adopted as the rule.

## What we kept from your "retain" list

| You said retain | What we did |
|---|---|
| Endpoints are positions, not judgments | Kept. It is gate 1 of the rubric and a design rule of the item bank. |
| Gathering and scoring are separate | Kept, and now separate vendors too: research on Anthropic, scoring on the validated OpenAI model. |
| Scores backed by quotations and confidence | Confidence kept. **Quotations changed**: users see paraphrased evidence with source type and date, never verbatim third-party text. Quoting reviews in the product is a legal risk (our rule GAP-14). Verbatim text stays in the research layer. |
| Person-side consistency check | Kept (internal consistency of the 24-item ladder). |
| Plan to learn from outcomes | Kept: pre-registered outcome fit, plus 90-day check-ins once someone takes a job. |

## Decided versus still a hypothesis

| Decided (Sebastian, 2026-10-13) | Still a hypothesis |
|---|---|
| No probability shown to users | That the person-vs-job gap predicts the outcome at all |
| Six traits are one layer, never blended | Your penalty values, and their asymmetries |
| Tolerance, must-haves (max 2), retake any time | The no-cost-inside-tolerance shape (compared against straight-line in the pre-registration) |
| Known / mixed / unknown records, coverage shown | The "known" thresholds (count, recency, spread), which are ours and provisional |
| Paraphrase only, scope on every item | That four traits of evidence are enough to say anything (the 3 of 6 floor) |
| Primary outcome unchanged; others exploratory | Which gap combinations compound (06, ignored by v1 math) |

## Where we went faster than your recommended sequence

You recommended scope, then outcomes, then interfaces, and only then weights. Sebastian
chose to build the whole pipeline now rather than stage it. The protection is that the
weights are versioned, the outcome analysis is pre-registered before any data, and no
probability is shown. If you think that protection is not enough, that is the conversation
to have first.
