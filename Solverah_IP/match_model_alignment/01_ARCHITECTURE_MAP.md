# Architecture map: evidence to guidance

**Status:** working draft, 2026-10-13. Maps your five conceptual components onto what
exists in Solverah today and what is being built this month. Read the legend first.

Legend: **[LIVE]** in the product now. **[BUILDING]** in the October 2026 CompanyLens
build. **[CONCEPT]** exists only as a concept; nothing built does this yet.

```
 PERSON SIDE                                   COMPANY SIDE
 -----------                                   ------------
 Reflection Engine / Authentic Intelligence     CompanyLens evidence  [BUILDING]
   [CONCEPT] no conversation about experience     - research step finds sources
                                                  - each item: scope (company /
 Core instrument, 24 items  [LIVE]                  division-location / role),
   = current stated preferences, 6 traits           date, paraphrase
 Tolerance + must-have step  [BUILDING]           - each item scored per trait,
   how much more / less is fine; max 2              or "insufficient evidence"
   must-haves                                     - pasted job posting = role item
 Environment Report (current job)  [LIVE]                |
 Pulse check-ins  [LIVE]                                 v
 Manager Match (separate)  [LIVE]               Trait records per company
        |                                         status known / mixed / unknown,
        v                                         estimate, confidence, coverage
 Understanding  [CONCEPT]                                |
   known / tentative / curious                           |
   (today: scores sit side by side,                      |
   nothing holds or revises an                           |
   interpretation)                                       |
        |                                                |
        +-------------------+----------------------------+
                            v
          Match logic
            Situation Report: person vs current job  [LIVE]
            Bayesian match model + your penalties  [LIVE engine, BUILDING use]
            gap read through tolerance (flat zone)  [BUILDING]
            gate layer: must-have broken, unknown, mixed  [BUILDING]
            OUTPUT: per-trait reads, coverage, flags. NO probability.
                            |
                            v
          Guidance / Next Best Step
            Situation Report guidance text  [LIVE]
            Manager Decoder / Playbook  [LIVE]
            Experiments (try something, read back)  [LIVE]
            Investigate step: interview questions per trait  [BUILDING]
            Six next-step categories as a system  [CONCEPT]
```

## Where uncertainty lives at each stage

| Stage | How uncertainty is carried |
|---|---|
| Evidence | Scope, date and source type on every item. Old evidence (over 24 months) counts less. A scorer may abstain ("insufficient evidence") instead of guessing. |
| Company picture | Each trait is known, mixed or unknown. Mixed keeps both ends; it is never averaged. Confidence is adjusted by company size. |
| Person picture | The 24 items are current stated preferences, with an internal consistency check. Tolerance and must-haves are the person's own words about what matters. Nothing yet separates lasting needs from current circumstances. |
| Match | Coverage is always stated. Under 3 of 6 known traits there is no match, only "not enough evidence". Unknown traits add no penalty. No probability is shown. |
| Guidance | An unknown must-have becomes an Investigate step with questions to ask, not a verdict. |

## What this map does not claim

- The Reflection Engine and Understanding are **not built**. The product today has
  scores and reports that sit side by side. Nothing yet holds known, tentative and
  curious as separate states, or revises an interpretation without overwriting it.
- Only **Investigate** among your six next-step categories has a component being built
  for it. Decide, Prepare, Explore, Act and Don't Act Yet are not yet distinct outputs.
- The match engine's probability exists inside the code. It is used only to rank, and
  never reaches a page.
