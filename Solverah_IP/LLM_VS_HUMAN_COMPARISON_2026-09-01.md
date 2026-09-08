# LLM Extractor vs. Human Rater Comparison — Round 1

**Date:** 2026-09-01
**Why this exists:** S-49 states the ground-truth set has two purposes — (1) validate the anchors, (2) validate the LLM extractor against human consensus. Purpose (1) has been worked (S-15 agreement report, this session's Decision-anchor fix). Purpose (2) had never been executed — `grep -rl "raterB\|raterC\|rater_agreement\|human_consensus" --include="*.py" .` across the whole repo returns nothing. No script compares `scorer_pipeline.py`'s output to the human B/C JSONs. This document is that comparison, run once, by hand, against data that already existed and cost nothing to compute.

**Source data:**
- LLM side: `causal_graph/results/scorer_variance_v2/*.csv` — model `gpt-5.5-2026-04-23`, 5 runs per packet, **scored against the frozen v1 `anchors.json`** (each row is tagged `rubric_version: "v1-frozen-2026-08-15"` in the script itself — confirmed by reading `scorer_variance_test_v2.py`). This predates the Decision-anchor edit made earlier this session to `anchors_v3_PROPOSED.json`. These numbers do not reflect that fix.
- Human side: round-1 B (Carolynn) and C (George) JSONs only — A (Julie) excluded per D-12(b)/the separate finding that her scores run ~1 band harsher and aren't blind on identity for half the packets.

## Headline numbers

| Metric | Value |
|---|---|
| Cells compared | 36 (6 packets × 6 dimensions) |
| Mean \|LLM mean − human median\| | **0.114** |
| Mean LLM within-model SD (5 runs) | **0.023** (max 0.098) |
| Max gap | 0.300 (2 cells) |
| Cells with gap ≥ 0.25 | 2 |
| LLM score floor across all 36 cells | **0.3 — the 0.1 band was never used, even when a human rater used it** |

## What this settles

**Repeated sampling of one model is not the fix.** Mean within-model SD across 5 runs was 0.023 — most cells were exactly or near-0.000, the rest topped out at 0.098. That's roughly a quarter of one band-step of pure decoding noise. Your instinct earlier that "run it a bunch and average" would "just be noise" was right, but for a specific reason: there wasn't much noise to average out. The 0.114 mean gap against human consensus is not sampling variance — it's the model's systematic read of the rubric differing from raters' systematic read, and no amount of repeated sampling of the same model touches that.

**The average gap (0.114) is under half a band — moderate, not alarming on its own.** Most cells land at 0.0–0.2. This is genuinely useful: it means the extractor isn't wildly miscalibrated against the rubric as raters applied it.

## What this does not settle — and one new, more concerning finding

**Full per-cell table:**

| Packet | Dim | LLM mean | LLM SD | Human B | Human C | Human median | Gap |
|---|---|---|---|---|---|---|---|
| P-01 | autonomy | 0.30 | 0.000 | 0.9 | 0.1 | 0.5 | 0.20 |
| P-01 | pace | 0.70 | 0.000 | 0.3 | 0.7 | 0.5 | 0.20 |
| P-01 | collaboration | 0.70 | 0.000 | 0.7 | 0.9 | 0.8 | 0.10 |
| P-01 | feedback | 0.58 | 0.098 | 0.3 | 0.5 | 0.4 | 0.18 |
| P-01 | innovation | 0.54 | 0.080 | 0.5 | 0.3 | 0.4 | 0.14 |
| P-01 | decision | 0.70 | 0.000 | 0.3 | 0.9 | 0.6 | 0.10 |
| P-02 | autonomy | 0.30 | 0.000 | 0.7 | 0.5 | 0.6 | **0.30** |
| P-02 | pace | 0.70 | 0.000 | 0.9 | 0.7 | 0.8 | 0.10 |
| P-02 | collaboration | 0.70 | 0.000 | 0.5 | 0.9 | 0.7 | 0.00 |
| P-02 | feedback | 0.42 | 0.098 | 0.3 | 0.7 | 0.5 | 0.08 |
| P-02 | innovation | 0.30 | 0.000 | 0.3 | 0.3 | 0.3 | 0.00 |
| P-02 | decision | 0.58 | 0.098 | 0.7 | 0.5 | 0.6 | 0.02 |
| P-03 | autonomy | 0.70 | 0.000 | 0.5 | 0.9 | 0.7 | 0.00 |
| P-03 | pace | 0.90 | 0.000 | 0.9 | 0.7 | 0.8 | 0.10 |
| P-03 | collaboration | 0.70 | 0.000 | 0.3 | 0.9 | 0.6 | 0.10 |
| P-03 | feedback | 0.50 | 0.000 | 0.9 | 0.5 | 0.7 | 0.20 |
| P-03 | innovation | 0.70 | 0.000 | 0.5 | 0.7 | 0.6 | 0.10 |
| P-03 | decision | 0.70 | 0.000 | 0.3 | 0.7 | 0.5 | 0.20 |
| P-04 | autonomy | 0.74 | 0.080 | 0.7 | 0.7 | 0.7 | 0.04 |
| P-04 | pace | 0.90 | 0.000 | 0.7 | 0.7 | 0.7 | 0.20 |
| P-04 | collaboration | 0.70 | 0.000 | 0.5 | 0.9 | 0.7 | 0.00 |
| P-04 | feedback | 0.50 | 0.000 | 0.5 | 0.5 | 0.5 | 0.00 |
| P-04 | innovation | 0.90 | 0.000 | 0.9 | 0.3 | 0.6 | **0.30** |
| P-04 | decision | 0.50 | 0.000 | 0.7 | 0.1 | 0.4 | 0.10 |
| P-05 | autonomy | 0.70 | 0.000 | 0.9 | 0.7 | 0.8 | 0.10 |
| P-05 | pace | 0.30 | 0.000 | 0.3 | 0.5 | 0.4 | 0.10 |
| P-05 | collaboration | 0.42 | 0.098 | 0.3 | 0.3 | 0.3 | 0.12 |
| P-05 | feedback | 0.30 | 0.000 | 0.7 | 0.3 | 0.5 | 0.20 |
| P-05 | innovation | 0.30 | 0.000 | 0.7 | 0.3 | 0.5 | 0.20 |
| P-05 | decision | 0.70 | 0.000 | 0.1 | 0.9 | 0.5 | 0.20 |
| P-06 | autonomy | 0.34 | 0.080 | 0.5 | 0.1 | 0.3 | 0.04 |
| P-06 | pace | 0.38 | 0.098 | 0.5 | 0.5 | 0.5 | 0.12 |
| P-06 | collaboration | 0.70 | 0.000 | 0.7 | 0.7 | 0.7 | 0.00 |
| P-06 | feedback | 0.34 | 0.080 | 0.5 | 0.3 | 0.4 | 0.06 |
| P-06 | innovation | 0.30 | 0.000 | 0.3 | 0.1 | 0.2 | 0.10 |
| P-06 | decision | 0.70 | 0.000 | 0.9 | 0.3 | 0.6 | 0.10 |

**Two things worth separating, not averaging together:**

1. **The two worst cells (P-02/autonomy, P-04/innovation, both gap = 0.30) read differently on inspection.** P-04/innovation is the LLM picking a side of a genuine human split (B=0.9, C=0.3 — a REVIEW-level disagreement in the S-15 sense) — the "human median" it's being scored against there is itself a low-confidence number, so scoring the LLM as "wrong" against it is arguably unfair. P-02/autonomy is different: both humans agree closely (0.7, 0.5) and the LLM lands at 0.3, clearly outside both. That's the one real, unambiguous LLM miss in the set — worth a manual look at what evidence the LLM cited there before concluding anything.

2. **The floor-bias finding is the one that should worry you more than the average gap.** Scan the LLM mean column: it never once outputs 0.1, across all 36 cells, on any packet, any dimension — including three cells where a human rater independently landed on 0.1 (P-04/decision, P-05/decision, P-06/autonomy). This looks like a systematic reluctance to assign the harshest band, not noise (SD is 0.000 on all three of those specific cells — the model is *consistently* not going there, not randomly avoiding it). If this holds up, it means the extractor is structurally biased toward the middle of the scale and may under-flag genuinely bad companies — the exact failure mode Julie's "quarantine" idea (P-05/Doist notes) was written to catch. This is worth checking before it's trusted as a scoring engine, not filed as a known quirk.

**Caveat that applies to the whole comparison:** it's scored against v1 anchors, before the Decision-dimension fix made this session (`anchors_v3_PROPOSED.json`). The Decision column's numbers here (mean gap ~0.12, no outliers) reflect the *old, ambiguous* wording — not evidence the fix worked or didn't. That has to be re-run against v3 to mean anything for Decision specifically.

## Addendum, same day: Decision-anchor re-test — negative result

Re-ran `scorer_variance_test_v2.py` against all 6 packets (5 runs each, 30 calls, model `gpt-5.5-2026-04-23`, `reasoning_effort=medium`), with a test copy of `anchors.json` where the `decision` dimension block was swapped wholesale for the fixed version from `anchors_v3_PROPOSED.json` (the Autonomy-conflation guardrail added earlier this session). Ran from a scratch `decision_test/` directory via `SOLVERAH_IP_DIR` override so nothing in the real repo or the original baseline CSVs was touched. (Side finding during setup, unrelated to the anchor question: the original script invoked `python3`, which on this Windows machine silently resolved to system Python rather than the project's `.venv-solverah-3b` — worth checking whether `scorer_pipeline.py` has the same landmine anywhere it's invoked.)

**Result: the LLM's decision score did not move, at all, on any packet.**

| Packet | Old anchor (v1) mean | New anchor (v3 patch) mean | Old SD | New SD |
|---|---|---|---|---|
| P-01 | 0.70 | 0.70 | 0.000 | 0.000 |
| P-02 | 0.58 | 0.58 | 0.098 | 0.110 |
| P-03 | 0.70 | 0.70 | 0.000 | 0.000 |
| P-04 | 0.50 | 0.50 | 0.000 | 0.000 |
| P-05 | 0.70 | 0.70 | 0.000 | 0.000 |
| P-06 | 0.70 | 0.70 | 0.000 | 0.000 |

On P-01, P-03, P-04, P-05, P-06 the model was fully deterministic across all 5 runs both before and after (SD = 0.000) — it made the identical deterministic call both times, not just the same average of noisy draws. Only P-02 had any run-to-run spread, and even there the mean held.

**Interpretation, not just the number:** the anchor edit was written for a human-reading failure mode — Carolynn citing Autonomy-flavored evidence ("ownership," "little direction," "conservative, long-term view") under the Decision dimension. That's a plausible, still-untested fix for round-2 human raters, who read prose guardrails the way this text was written for. But it measurably did nothing to the LLM extractor, which isn't sensitive to that clarifying paragraph one way or the other. The ~0.12 mean gap between the LLM and human consensus on Decision is unchanged and needs its own diagnosis — most likely by pulling the model's actual `evidence_quotes`/reasoning on the worst cells (in the `raw_v2_*` JSON output, not in this document) and checking whether it's making the same Autonomy/Decision mix-up Carolynn made, or missing something else entirely. Fixing the anchor text and fixing the LLM's calibration on this dimension are two different problems that happened to present as the same round-1 symptom — this test is what separates them.

## Addendum 2, same day: what the LLM actually cites on Decision

Ran `scorer_pipeline.py` (the real production extractor, not the variance-test harness — this one requests `evidence_quotes` per dimension and runs them through the citation verifier) once per packet, same v3-patched Decision anchor, model `gpt-5.5-2026-04-23`. All 18 quotes across 6 packets verified against the packet text (no fabricated citations).

**Ruled out:** none of the 18 quotes show the Autonomy-conflation pattern Carolynn showed (no "ownership," "little direction," "conservative long-term view," approval-process language). Every citation is genuinely about the data/judgment axis. This explains the Addendum 1 null result — the anchor edit had nothing to fix in the LLM's behavior because the LLM was never making that mistake in the first place.

**Found instead — a consistent directional bias, 6 for 6:**

| Packet | Rater B | Rater C | LLM | LLM lands closer to |
|---|---|---|---|---|
| P-01 | 0.3 | 0.9 | 0.7 | whichever rater read MORE data-driven (C) |
| P-02 | 0.7 | 0.5 | 0.5 | C |
| P-03 | 0.3 | 0.7 | 0.7 | C |
| P-04 | 0.7 | 0.1 | 0.5 | B (0.7 — the more data-driven reading here) |
| P-05 | 0.1 | 0.9 | 0.7 | C |
| P-06 | 0.9 | 0.3 | 0.7 | B (0.9 — the more data-driven reading here) |

In every packet with any human split, the LLM's score sits closer to whichever rater scored the company toward the "Data / analysis" pole (0.9) than toward "Intuition / judgement" (0.1) — regardless of whether that rater happened to be B or C. This is the same shape as the floor-bias finding from the original 36-cell comparison (LLM never used the 0.1 band anywhere in that set either): when evidence is genuinely mixed, the model resolves toward the more favorable/rigorous-sounding pole instead of splitting the difference or weighing skeptically. This looks like one underlying tendency showing up on two different dimensions, not two separate bugs.

Two secondary data-quality notes from the same run: P-06's three citations all came from a single excerpt (`eid=C7`) — one paragraph cited three times, not independent corroboration across the packet. P-05's citations were majority `source=disputed` (2 of 3) — the anonymization pipeline itself couldn't confirm authorship on the evidence actually driving that score.

**What this means for next steps:** the Decision-anchor wording fix is done and can stay (it addresses a real human-reading failure even though it's a no-op for the LLM). The LLM's ~0.12 mean gap on Decision is not an anchor-wording problem and won't be fixed by editing anchors further.

## Addendum 3, same day: the "leans toward the favorable pole" theory does not generalize — correction

Addendum 2 proposed that the Decision-specific directional lean (LLM sits closer to whichever human rater read the company as more data-driven, 6/6) was "the same underlying tendency" as the floor-bias finding, just showing up again. That claim was checked against fresh data and does not hold. It was an overreach and is retracted here rather than left standing.

Ran `score_packet()` once more per packet (same 6 calls, now capturing and saving all six dimensions per packet, not just Decision — script `run_all_dims_evidence.py`, output saved to `decision_test/causal_graph/results/all_dims_evidence_2026-09-01.json`). Checked the same "does the LLM lean toward the higher-scoring human rater" logic against Autonomy, the other dimension with a floor-bias hit:

| Packet | Rater B | Rater C | LLM | Direction |
|---|---|---|---|---|
| P-01 autonomy | 0.9 | 0.1 | 0.3 | toward the LOWER reading |
| P-02 autonomy | 0.7 | 0.5 | 0.3 | below both raters |
| P-03 autonomy | 0.5 | 0.9 | 0.7 | toward the higher reading |
| P-04 autonomy | 0.7 | 0.7 | 0.9 | above consensus |
| P-05 autonomy | 0.9 | 0.7 | 0.7 | toward the LOWER reading |
| P-06 autonomy | 0.5 | 0.1 | 0.3 | ~midpoint |

No consistent direction. Feedback is worse for the theory: the LLM lands closer to the *lower*-scoring rater in 4 of 6 packets there. Source-tag weighting (company- vs. noncompany-authored citations) was also checked as an alternative explanation and doesn't hold either — e.g. P-02/autonomy cites three company-authored quotes and scores low (0.3); P-04/innovation cites three noncompany quotes and scores high (0.9). No clean pattern there either.

**What actually replicated, and is the finding worth keeping:** across this fresh set of 36 cells plus the original 36 (72 independent scoring instances total, two separate runs, same model), the LLM never once assigned the 0.1 band, on any dimension, in either run. Human raters used 0.1 at least five times across the same six packets (P-01/autonomy-C, P-04/decision-C, P-05/decision-B, P-06/autonomy-C, P-06/innovation-C). That's a structural floor bias — the model appears unable or unwilling to reach for the harshest band — not a directional "leans toward the favorable reading" tendency. The Decision-specific lean documented in Addendum 2 is real and worth keeping on record for that dimension specifically, but should not be treated as evidence of a general mechanism; it doesn't reproduce elsewhere.

**Revised next-step implication:** the floor-bias is the one well-evidenced, generalizable finding here, and it's the one worth acting on if this extractor is trusted for anything company-facing (it directly undercuts Julie's "quarantine bad companies" idea — a model that won't say 0.1 can't flag the worst cases). The Decision-dimension lean and the Feedback-dimension counter-lean are both real in their own data but don't point to one fixable root cause — they may just be ordinary per-dimension noise in a 6-packet sample, which is small enough that a single-direction result on one dimension isn't strong evidence of anything beyond that dimension. Don't chase a unified theory further on this sample size; the floor-bias is the actionable, well-replicated finding to carry forward.

## Addendum 4, same day: reading the five floor-bias cells individually

The floor-bias claim (LLM never assigns 0.1) is a count across 72 cells. Read the model's actual cited evidence, not just the score, on the five specific cells where a human rater used 0.1 and the LLM didn't, to check whether the model is declining to follow its own evidence to the bottom band, or whether something else is going on. Used the console output already captured in `run_all_dims_evidence.py`'s run — no new API calls.

**Three cells are genuine floor-avoidance** — the model's own cited evidence supports the harshest band and it still doesn't use it:

- P-06/autonomy (human C=0.1, LLM=0.3): all three cited quotes support low autonomy ("Typically works under close supervision," "Follow a range of mandatory procedures," "they believe in top down micromanagement") — unanimous, no countervailing quote — and the score still lands one band above the evidence.
- P-01/autonomy (human C=0.1, LLM=0.3): two of three quotes are independent employee complaints of "Heavy micromanagement" / "Very micromanage"; one weaker countervailing quote pulled the score up to 0.3.
- P-06/innovation (human C=0.1, LLM=0.3), weaker case: two of three quotes support low innovation ("Outdated tech and systems," "taking a conservative approach"); the third ("established but ever-evolving") is neutral marketing language, not real counter-evidence.

**Two cells are not floor-bias — they're extreme rater disagreement, and the LLM happened to land near the non-extreme rater:**

- P-04/decision (human C=0.1, human B=0.7, LLM=0.5): B independently read this packet as fairly data-driven, close to the LLM. C is the outlier, not the model. The LLM's own citations support a genuinely mixed read.
- P-05/decision (human B=0.1, human C=0.9, LLM=0.7): same shape — B and C are at opposite extremes on this packet; the LLM's citations (performance testing, before/after comparisons, cohort queries — all empirical/data-flavored) land near C. B looks like the outlier.

**Conclusion:** conflating all five into one "floor-bias" story would have overstated the case. The real, actionable finding is narrower and stronger where it holds: on Autonomy- and Innovation-flavored "how bad is this workplace" evidence, the model appears to structurally decline to follow clearly one-sided harsh evidence down to the bottom band (3 of 5 cases here, 2 of them unanimous). On Decision specifically, what looked like floor-bias was actually just capturing normal high-variance rater disagreement — not a model defect. If this is worth fixing before the extractor is trusted for anything like Julie's quarantine-gate idea, the target is narrower than "fix the model's floor bias generally" — it's specifically whether the model will call a workplace bad when the cited evidence is unanimous and harsh, which is a testable, scoped question rather than a vague calibration worry.

## Addendum 5, same day: prompt-level fix attempt — negative result

Tested whether an explicit calibration instruction moves the three genuine floor-avoidance cases. Added to the scoring instruction: *"if the cited evidence is unanimous and clearly one-sided, with no meaningful countervailing signal, use the most extreme band (0.1 or 0.9) that the evidence supports — do not default to a more moderate band as a hedge against unanimous evidence."* Re-ran P-01 and P-06 (2 calls — covers all three cases, since one call scores all six dimensions).

**Result: zero movement.** All three cases stayed at exactly 0.3.

| Case | Baseline | With calibration instruction |
|---|---|---|
| P-01/autonomy | 0.3 | 0.3 — unchanged |
| P-06/autonomy | 0.3 | 0.3 — unchanged |
| P-06/innovation | 0.3 | 0.3 — unchanged |

P-06/autonomy's re-cited evidence was, if anything, more unanimous this time ("Under direct supervision," "Typically works under close supervision," "top down micromanagement" — three-for-three negative, zero countervailing quote) and still didn't move. A direct, explicit instruction to stop hedging should have worked at least some of the time if this were an implicit-default problem. It didn't move once across two packets.

**Conclusion:** this looks like a structural property of the model rather than a prompting gap — plausibly trained-in reluctance to assign the harshest judgment to a specific real company, not something that responds to in-context instruction. Not worth chasing further with more prompt variants on this model; further iteration here has a low expected payoff given a direct attempt already failed cleanly. If the floor-bias matters in practice (it does, for anything like a quarantine/red-flag feature), the more promising path is designing around it rather than trying to prompt-fix it — e.g., have the citation verifier's own source-tag counts (already computed, already verified against the packet) flag "unanimous negative evidence, zero countervailing citations" algorithmically, rather than trusting the model's own score field to reach the bottom band on its own.
