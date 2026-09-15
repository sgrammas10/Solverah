# Floor-Bias Workaround — Design, Validation, and What It's Actually Good For

**Date:** 2026-09-01
**Artifacts:** `causal_graph/extremity_flag.py`, `causal_graph/test_extremity_flag.py`, `causal_graph/run_probe_gate_test.py`, `causal_graph/run_flag_sweep.py` (all new, untracked)

## The problem this addresses

Measured across 72 independent scoring instances (two runs, `gpt-5.5-2026-04-23`): the extractor never assigns the 0.1 band on any dimension, while human raters used 0.1 at least five times on the same six packets. An explicit prompt instruction to use extreme bands on unanimous evidence moved nothing. Consequence: any rule of the form "score ≤ 0.2 → flag" can never fire, which blocks the quarantine-gate idea outright.

## Two designs that failed, recorded so they aren't rebuilt

**1. Source-tag counts.** My own earlier proposal, and it doesn't survive contact with the code. `classify_source` returns company / noncompany / disputed / researcher — that is *authorship*, not valence. It cannot tell you cited evidence is negative, so it cannot detect "unanimous negative evidence."

**2. A symmetric citation-consistency check** ("all cited quotes match the extreme band but the score sits inside that pole"). Killed by real data — P-03/autonomy: the model cited three quotes all matching the 0.9 band ("Own your impact on day one", "thrive in autonomous, high-expectation environments", "work independently ... without ... hand-holding") and scored 0.7. Identical citation shape to the true floor cases, but the human median was *also* 0.7, so the model was right and a symmetric flag would be a false positive. Citing vivid extreme quotes then scoring moderately is ordinary behavior. The counterexample is baked into the test suite.

The flag is therefore deliberately **one-sided**. It fires only on the floor, and only because bottom-end truncation is a *measured* property of this model — not because the logic is sound in both directions. If a future model uses 0.1 normally, retire the module rather than making it symmetric.

## The design that works

The bottom-end signal comes from changing the *shape* of the question rather than the wording. Instead of "rate this employer" (the task that triggers the reluctance), the probe asks a binary, company-agnostic, per-quote membership question: *does this isolated fragment match this description?* — the description being the dimension's own 0.1 band text from the frozen anchors.

**Gate test result: PASS.** The same model, on the same text it refuses to score 0.1, returned `True` on all three obvious floor-band matches and `False` on both controls. This is a real dissociation: the reluctance attaches to rendering a verdict on an identifiable employer, not to recognizing harsh evidence. That both confirms the earlier diagnosis and makes the workaround viable.

## Sweep results (16 cells probed, score ≤ 0.5)

**Fire rate: 2/16 probed (12%), 2/36 of all cells.** Selective, not trigger-happy.

| Cell | Result | Assessment |
|---|---|---|
| P-06/autonomy | **FLAG** (3/3 floor matches, score 0.3, human C = 0.1) | **Confirmed true positive** |
| P-06/feedback | **FLAG** (3/3, score 0.3, humans 0.5 / 0.3) | **Unadjudicated** — see below |
| P-01/autonomy | no fire (2/3, one countervailing quote), human C = 0.1 | Miss by design |
| P-04/decision, P-05/decision | no fire, human 0.1 present | Miss by design — both previously established as rater-outlier cells, not real floor cases |
| P-06/innovation | no fire (2/3), human C = 0.1 | Miss; live probe rejected a quote this project's fixture hand-labelled ambiguous |
| 11 others | no fire | — |

**On P-06/feedback:** the probe matched "annual performance review process", "mid-year touch points and formal end-of-year discussions", and "supported when they raise issues" against feedback's 0.1 band ("occasional and softened … supportive or nurturing framing"). That labelling looks correct — annual-plus-mid-year is about as infrequent as formal feedback gets. But the human scores on this cell are *not* a usable yardstick: the same-day Feedback diagnosis established that both raters were scoring the wrong construct on this dimension, and on P-06 specifically all four of George's citations were off-axis. So this cell is genuinely undetermined — not a confirmed false positive, and not claimable as a win.

## Honest limits

- **n=1 confirmed true positive.** One clean hit is not a precision estimate.
- **Both fires landed on the same packet (P-06).** Could mean Raymond James is genuinely low on multiple axes; could mean something about that packet's structure. Unresolved on this sample.
- **Both fires were "mild" severity** (score 0.3, one band above floor). The flag has never caught a severe case, consistent with the model landing at 0.3 rather than 0.5+ when it avoids the floor.
- **The test suite validates flag logic, not probe accuracy.** The 5/5 pass is against hand labels; the live probe demonstrably diverges from those labels (P-06/innovation). A green suite is not evidence the probe is accurate.
- **The 0.1-vs-0.3 boundary is untested.** The gate test used easy controls. Probe precision on genuinely marginal evidence — exactly where false positives would come from — remains unmeasured.
- Everything here rests on **6 packets**.

## What this is good for, and what it is not

**Good for:** surfacing cells for human review. A 12% fire rate on a selective, evidence-grounded criterion is a usable triage signal, and each flag comes with its matched quotes and source tags so a person can adjudicate in seconds.

**Not good for:** auto-gating anything. With one confirmed true positive, a flag cannot justify automatically quarantining a company — the cost of a wrong quarantine (falsely marking a real employer) is far too high for this evidence base. If the quarantine gate ships, this flag should feed a review queue, not the gate itself.

## Probe design settled (boundary test, three designs, same day)

Built `probe_boundary_test.py`: 46 real quotes from the six packets, four categories, expectations pre-registered in the file. A = floor matches (expect True), B = leaning-low (expect False, the production-critical category), C = off-axis quotes fed to the wrong dimension's probe (objectively labelable, includes lexical traps), D = opposite pole (objectively labelable).

| Category | Binary | Forced choice | **Forced + off-axis escape** |
|---|---|---|---|
| A floor | 12/13 (92%) | 10/13 (77%) | 9/13 (69%) |
| B boundary | 6/10 (60%) | 8/10 (80%) | **8/10 (80%)** |
| C off-axis | 12/12 (100%) | 9/12 (75%) | **12/12 (100%)** |
| D opposite | 11/11 | 11/11 | **11/11** |

**Binary** asks membership against one description in isolation, so any partial resemblance earns a "yes" — it over-matches at the 0.1/0.3 boundary. Proof case: decision / "combines systematic pricing infrastructure with trader judgment", which names both poles explicitly and still matched the floor band.

**Plain forced choice** fixed that but removed the ability to say "none of these", so it mapped negative-sounding off-axis quotes onto the low band — including the lexical trap ("mandatory overtime is required", a pace quote, fed to the autonomy probe whose 0.1 text mentions "mandatory procedures"). That is the dangerous failure: it can manufacture unanimity out of irrelevant evidence.

**Forced choice plus an explicit off-axis opt-out** keeps both fixes and is the settled default. Its lower A score is the tolerable direction (the flag under-fires; a human gets no suggestion) and on review 3 of its 4 A misses were bad hand labels rather than probe errors.

**Measured effect on the flag:** P-06/autonomy — the one confirmed true positive — still fires, all three quotes matching. The unadjudicated P-06/feedback fire disappears, because "mid-year touch points and formal end-of-year discussions" correctly lands on 0.3. Precision up, solid hit retained.

**Not re-measured:** the overall fire rate under this probe. The 12% above was measured with the binary probe. Re-running `run_flag_sweep.py` (~16 calls) would give the real number.

## The finding that outlasts the flag

Across the boundary test the labeller (me) got at least 5 labels wrong, all in the same direction: pulling quotes to 0.1 that belong at 0.3, by treating "bad on this axis" as equivalent to "matches the low band". The human raters made the identical error on Feedback (see FEEDBACK_DIMENSION_DIAGNOSIS_2026-09-01.md). The binary probe made a version of it too.

That is four independent labellers drifting the same way on the same construct. It suggests the rubric has a systematic readability problem at the extremes — the low band reads as "bad here" rather than "matches this specific posture" — and that no anchor rewording has fixed it in either dimension tried so far. If that holds up, it is a finding about the instrument rather than about any model, and it deserves attention ahead of further extractor work. It is also a standing caution: any single labeller's judgment on this rubric, including a careful one's, is weaker evidence than it feels.
