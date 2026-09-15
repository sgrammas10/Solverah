# Solverah — Decisions, 2026-08-13 (second session)

**All binding. All implemented in this session — this file records what was decided and why, the
files are already changed.**

Context that drove every ruling: **ship something 70–80% right that can be iterated on, rather than
spend unbounded time perfecting an instrument whose remaining errors cannot be fixed without data
that does not currently exist.** Julie's own instruction. Four of the five decisions below delete or
bound something. That is the point — v4.2, v4.3 and v4.4 each grew the prompt in response to a
defect, and the instrument was accumulating requirements faster than it was accumulating packets.

---

## 1. The prompt freezes on the first clean packet

> **v4.5 freezes after the first packet that surfaces zero STRUCTURAL defects.** A structural defect
> changes what evidence reaches Section 1 or how a section is scoped. Cosmetic and wording defects
> are logged and do not reset the counter. On freeze, all six packets are rebuilt once against the
> frozen version and the ground-truth set is closed.

The 08-13 policy was "revised as failures surface, not frozen — deliberate." Correct at the time and
it has no termination condition. Every remaining company is a type the prompt has not seen, so
"revise until no failures" is equivalent to "revise forever." This is the "packet debate can absorb
unlimited time" problem from 08-07 arriving through a new door.

The freeze rule is deliberately weak. One clean packet is a low bar. That is intentional: the bar
exists to terminate the loop, not to certify the instrument.

---

## 2. Per-title subratings are removed, retroactively, from every packet

> **Glassdoor is demoted to an OPTIONAL recency cross-check. Indeed is the only required review
> source. No packet carries per-title rating numbers.**

Three independent reasons, any one sufficient:

**They fail their own validation.** Three of four recommendation percentages in P-03 and one of two
testable ones in P-04 are arithmetically impossible at the review counts printed beside them.
Systematic failure across two packets means the rate and the count are computed over different
denominators — so the *difference* between two rates has no defined sample size and cannot be
computed at all.

**They cannot be collected uniformly.** P-02 returned empty documents on every Glassdoor route
tried. With six companies, one packet is 17% of the calibration set. Packets carrying different
instruments cannot be merged — the same failure that made the earlier rater's scores unusable.
**Uniform absence beats uneven presence.**

**They are the wrong construct.** Recommendation rate and senior-management score are *evaluative*:
how the writer feels. The six dimensions are *descriptive*: what the environment is like. On P-03
the two orderings disagreed inside one company — one title ranked third on satisfaction and first on
work/life balance. Sound numbers of the wrong construct are still not evidence.

**Within-company variation is not lost.** It is captured as the dispersion ordinal, read from review
prose — which was always the more credible evidence, and unlike a rating table it is a quote a
citation harness can verify.

*Implemented:* P-03 five title blocks stripped, P-04 two title blocks stripped, 2e note added to
both explaining the removal. **Verbatim review text, dates, titles and URLs are byte-identical
before and after — verified by diff.**

---

## 3. The achievability gate is now a hard rule in the prompt

> **Any percentage must be reachable at its stated n, from any source, or it is struck. Not
> reconciled, not footnoted — struck.**

This existed from 2026-08-10 as a note in a handoff, and consequently never propagated. P-03 shipped
with three impossible percentages, and one of them — 24% at n=16, where values step by 6.25 points —
was the sole support for a model-level claim about level effects.

**The general lesson, which matters more than the rule: a rule that lives only in a handoff is not a
rule.** Anything that must fire on every packet belongs in the prompt.

*Implemented:* hard rule 9, section B3 rewritten as a gate, two new lines in the output template and
two in the final check. Verification script `test0_achievability.py`.

---

## 4. Evaluative metrics are barred from Section 1 as dimension evidence

> **Hard rule 8. Recommendation rate, CEO approval, business outlook, star ratings and
> senior-management scores may appear in the QA section as source metadata. They may never appear
> in Section 1 as evidence for a dimension.**

A construct bar, which is stronger than the reliability caution it replaces. The 08-10 ruling said
those percentages are unreliable. This says that even when reliable they measure the wrong thing.

---

## 5. Section D voice composition must be recorded and bounded

> **Record D's voice composition. If it comes back 100% executive, work ONE additional rung looking
> for a non-executive first-person account. Log stale non-executive material as found-and-rejected,
> not absent. Flag all-executive D to the rater.**

P-02's section D was entirely the outgoing and incoming CEO. The mechanism is structural, not
accidental: large public companies publish executive interviews continuously and employee stories
rarely, so the 18-month staleness gate removes the non-executive voice and leaves the executive one
intact. P-02's newsroom carries exactly the right material, all of it 2018–2020.

Left alone, **D's voice composition becomes a function of company size and press profile — which is
`stage_size`, a confounder already in the model, entering through the evidence instead of through
the adjustment.** Same failure shape as gating a section on the yield of a source class only large
companies possess, which was ruled on 08-10.

The extra rung is bounded at one. This is a correction, not an open-ended search.

---

## 6. The level/role question is closed

> **Level does NOT enter the v1 model. It is captured as an ordinal on every review-derived note and
> tested when outcome data exists.** Third consistent application of *storage ≠ features*, after
> dispersion and the evidence graph.

The binding reason is not the withdrawn P-03 arithmetic. It is that **role- and level-conditional
cells cannot be populated.** P-02's title index: 4,801 Sales Associate reviews against 5 Software
Engineer, 4 Product Manager, 3 Data Analyst, for an employer of 85,000+. Most cells are empty and no
amount of effort fills them.

Supporting reasons, in descending strength: scorer SD ≈ 0.098 against five bands of width 0.2 means
thinner buckets add noise, not resolution; twelve coefficients already sit on zero training rows;
the person side has no level input and self-reported seniority is inflated; and per-title stratified
sampling may not be reproducible at production scale, which would mean calibrating against input the
extractor never sees.

**The v1 mitigation costs no coefficients:** where level-stratified evidence diverges from pooled
evidence, say so in the narrative layer with evidence IDs cited per sentence. A hedge in the
interface is information. A hedge in the ranking is an unvalidated prior in disguise.

Full reasoning and the pre-registered tests are in `LEVEL_ROLE_DECISION.md`.

*Open item #1 from the 2026-08-10 handoff is CLOSED.*

---

## 7. Packets are built in a clean context, matching production

> **Every packet build runs this prompt in a fresh chat or via API, with nothing else in the
> window, against a pinned and recorded model string.**

Production runs one prompt against one company with no memory of the previous one. A packet built
inside a long working session — carrying prior packets, defect logs and decisions — is built by an
instrument production does not have. That is the parity violation running backwards, the same shape
as collecting from authenticated sources.

**This qualifies today's work and the qualification should be recorded rather than glossed.** P-02
was completed, and P-01 was started, inside a session that already knew every defect from P-03,
P-04 and P-05. Both are sound as EVIDENCE — the quotes are real, sourced and dated. Neither is a
clean test OF THE PROMPT, because the builder knew what to look for.

The distinction that matters: hardening runs may be contextual, because knowing the last five
defects is how you find the sixth. But the packet that triggers the freeze, and the final rebuild
of all six, must be clean-room. **A freeze certified by a builder who knew in advance what to look
for certifies the builder, not the prompt.**

---

## Files changed this session

```
ground_truth/rubric/Company_Culture_Evidence_Collector_v4.5.md   NEW — supersedes v4.4
ground_truth/packets/P-02_best_buy/P-02_packet_IN_PROGRESS.txt   B/D/E/F complete, QA closed out
ground_truth/packets/P-03_akuna_capital/P-03_packet.txt          numeric layer struck, dispersion
                                                                 block withdrawn, 2e note added
ground_truth/packets/P-04_rga/P-04_packet.txt                    numeric layer struck, 2e note added
ground_truth/DECISIONS_2026-08-13b.md                            this file
LEVEL_ROLE_DECISION.md                                           the level/role reasoning
```

---

## What is still open

1. **P-01 Oscar Health is MISSING** — the folder is empty and no packet file exists in the repo.
   Unresolved since 08-13 morning. If unrecoverable it is a from-scratch build.
2. **P-04 is internally contradictory** — header says v4.2, Section B carries a v4.3 correction, and
   the yield audit still shows `B within 24 months: 0/15 FAIL` which that correction withdrew. Needs
   reconciling. Untouched today beyond the numeric strip.
3. **Rater B has no name.** George is off, Julie is one rater. One rater's scores are
   indistinguishable from that rater's lens, so the two-rater design is not currently running. This
   is now the largest unaddressed hole in the ground-truth exercise and it is a people decision, not
   a technical one.
4. **P-05 Doist** — first-person library still undated; each candidate must be opened individually.
5. **P-06 Raymond James** — not started. Expect it to reproduce P-02's population split
   (advisors dominating the review population the way store staff do).
6. Carried, untouched: re-run the scorer variance test on a stronger model; re-run the blind /
   identified test at n=5 per condition; build the citation-verification harness; bias-test the 24
   assessment items; write `assemble_training_data(db)`.
