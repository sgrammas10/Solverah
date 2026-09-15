# S-58 — free analyses against round 1, and three corrections to the item as written

**Date:** 2026-09-01 (second session)
**Pre-registered in:** `PREREG_S58_2026-09-01b.md`, written before any statistic below was computed.
**Scripts:** `s58_free_analyses.py`, `s58_mechanical_checks.py`, `s58_passage_agreement.py`
(all in `Solverah_IP/analysis_s58/`; stdlib only, no API calls, nothing written to the Solverah repo).
**Inputs:** the 18 round-1 JSONs, the frozen `anchors.json`, and the 36 LLM per-cell means
transcribed from `LLM_VS_HUMAN_COMPARISON_2026-09-01.md`.

---

## 1. S-58's headline premise does not survive the data (A1)

S-58 says four labellers "all drifted the same direction on the same construct, reading the 0.1
band as 'bad here'." Band usage over 36 cells each:

| labeller | 0.1 | 0.3 | 0.5 | 0.7 | 0.9 | mean |
|---|---|---|---|---|---|---|
| A (Julie) | **8** | 6 | 10 | 8 | 4 | 0.467 |
| B (Carolynn) | **1** | 10 | 9 | 9 | 7 | 0.561 |
| C (George) | **4** | 8 | 7 | 10 | 7 | 0.544 |
| LLM extractor | **0** | 10 | 8 | 15 | 3 | 0.568 |

*The A/B/C rows reproduce STATE §5's band-usage counts exactly, which is the check that this
pipeline reads the JSONs correctly. The LLM row differs slightly from STATE's 0/10/6/16/4 because
this bins each cell's 5-run mean to the nearest band, where STATE counted per-run bands. The only
load-bearing cell — 0.1, count zero — is identical either way and is independently established
across 72 scoring instances.*

Both blind raters and the extractor use 0.1 **less** than 0.9 — B by 7:1, and the extractor has never once assigned 0.1 in 72 independent scoring instances.
The two labelling failures S-58 cites (the agent's 46-quote pass, the binary probe) erred
**toward** 0.1. Those are opposite signs.

They are also different tasks: scoring a whole identifiable employer versus classifying an
isolated fragment. That is exactly the distinction the floor-bias work already established — the
model that refuses to score a company 0.1 will happily say "yes" to a membership question on the
same text. **The premise "same direction" is a category error of the same shape as the retracted
Addendum 3.** What the four cases actually share is a *criterion* — band membership judged on
valence rather than posture — which is a weaker and differently-shaped claim than S-58 states.

**Recommendation:** reword S-58's opening. Keep the observation, drop "same direction."

A related instance, worth fixing wherever it appears: STATE and D-12(b) describe Julie's scores as
running **"~1 band harsher."** On a rubric whose first gate is "neither pole is better," scoring
toward the low pole is not harshness. Calling it that is the S-58 error appearing in the project's
own documentation. She scores **lower**, not harsher.

---

## 2. Analysis (i) has now been run. It returns a pre-registered null. (A2)

Per labeller, the 36 scores decomposed as grand mean + packet effect + dimension effect + residual,
with a 10,000-draw within-labeller permutation null. Null expectation for either eta-sq is 5/35 = 0.143.

| labeller | eta-sq packet | perm p | eta-sq dimension | perm p | residual |
|---|---|---|---|---|---|
| A | 0.175 | 0.306 | 0.158 | 0.369 | 0.667 |
| B | 0.059 | 0.867 | 0.094 | 0.698 | 0.847 |
| C | 0.214 | 0.191 | 0.275 | 0.076 | 0.511 |
| LLM | 0.305 | **0.045** | 0.197 | 0.226 | 0.498 |

The pre-registered rule was: global impression present iff p < 0.05 in at least two of the three
human raters. **Zero of three.** No human rater shows a packet-level effect distinguishable from
chance. The only labeller that clears the bar is the extractor — and that is uninformative, because
`run_all_dims_evidence.py` scores all six dimensions in a single call, so a shared packet effect
there is structural, not evidence of halo.

**Mechanism (a) in its halo form — one global impression driving the evaluatively asymmetric
dimensions — is not supported.** This closes the free half of S-58's designed work with a negative
result. It should be recorded as such rather than re-run in another form.

Packet-effect correlations between labellers were computed and are **not reported as evidence**:
n = 6 needs |r| >= 0.81 for p < 0.05 and the largest observed was 0.64. That was pre-registered
before the values were seen.

---

## 3. Confidence does not track reliability — and this is the more dangerous finding (A4)

`confidence` is a field nobody has analysed. Mean confidence per dimension (B and C pooled), against
mean B–C band distance on that dimension:

| dimension | mean B–C band distance | mean B/C confidence |
|---|---|---|
| **decision** | **2.67** | 0.608 |
| autonomy | 1.67 | 0.625 |
| collaboration | 1.33 | 0.750 |
| feedback | 1.33 | 0.517 |
| innovation | 1.33 | 0.500 |
| **pace** | **0.83** | 0.625 |

**Spearman(band distance, mean confidence) over 36 cells = −0.073.** Effectively zero.

Two consequences, both pre-registered:

- **Disagreement is not explained by thin evidence.** The raters were no less confident on the
  cells where they landed furthest apart. This *supports* the claim that the instrument, not
  evidence scarcity, is upstream of the S-15 result.
- **Raters cannot tell which dimensions they are unreliable on.** Decision has 3.2× the disagreement
  of pace and *above-average* confidence. Any downstream use of `confidence` as a weight would
  weight the worst cells as heavily as the best. Nothing currently does this, and per D-17(b)
  nothing may — but the company side has no equivalent rule, and should get one before the
  extractor's confidence field is consumed anywhere.

Separately: the round-1 raters used confidence 0.1 rarely (A 7/36, B 1/36, C 2/36). The Feedback
diagnosis criticised P-04/B for "committing a 0.5 at 0.1 confidence rather than treating the packet
as uninformative" — but 0.1 confidence *is* how the instrument says to express that. There is no
abstain option. That criticism should be withdrawn; the instrument-design question (should there be
one?) is the real item.

---

## 4. The strongest result of the day needs no probe and no labelling (M1/M4)

Every citation was matched by normalised text across raters and dimensions. 282 citations,
34 passages cited by two or more raters.

| | |
|---|---|
| passages cited by >= 2 raters | 34 |
| ...dimension sets overlap at all | 22 (**65%**) |
| ...dimension sets identical | 12 (35%) |
| ...**zero overlap — same words, entirely different constructs** | **12 (35%)** |
| permutation null (labels shuffled within rater x packet, 5000 draws) | 0.226 |
| p(null >= observed) | **0.0002** |

Read this in both directions and do not collapse it:

- **Raters agree on what a passage is evidence *of* far better than chance** (65% vs 23%,
  p = 0.0002). Whatever is wrong with this rubric, wholesale construct drift is not it. Mechanism
  (c) in its strong form is disconfirmed.
- **But a third of shared passages land on entirely disjoint constructs.** The worked example:
  P-01's "heavy micromanagement. good culture. not so great work life balance..." was filed by A as
  **feedback = 0.1** and by C as **autonomy = 0.1**, **collaboration = 0.9** *and* **feedback = 0.5**
  — one review sentence supporting four dimension scores at opposite ends of the scale.
  P-06's "we value independence, we respect autonomy, celebrate individuality..." produced
  A autonomy = 0.3, B autonomy = 0.5, A/C collaboration = 0.7, and C **innovation = 0.1**.

**Which pairs collide** (shared passages, all raters):

| pair | shared passages | guardrail in frozen anchors? |
|---|---|---|
| collaboration <-> feedback | **9** | **none** |
| autonomy <-> collaboration | 8 | yes, both directions |
| autonomy <-> decision | **7** | **none in v1**; added in v3, untested on humans |
| decision <-> innovation | 6 | none |
| autonomy <-> pace | 6 | none |
| collaboration <-> decision | 6 | none |
| ... | | |
| pace <-> innovation | 2 | yes, both directions |

The top-colliding pair, **collaboration <-> feedback, has no `keep_distinct` in v1 or in
`anchors_v3_PROPOSED.json`.** That is a concrete, free, actionable gap.

The guardrail evidence is genuinely mixed and should not be pushed: one guarded pair ranks 2nd of
15, the other 11th. With 15 pairs and 34 shared passages this cannot decide whether prose
guardrails work. It is, however, consistent with the Decision no-op — a warning in prose did not
stop autonomy <-> collaboration colliding 8 times.

---

## 5. A defect in the Feedback fix that is already drafted

`anchors_v3_PROPOSED.json`'s new `feedback.keep_distinct` says psychological safety,
anti-retaliation, mentorship, career development and "we care about our people" language are **NOT
feedback signals**. The 0.1 band directly beneath it is unchanged and still reads:

> "Feedback is occasional and softened. **Harmony valued, conflict avoided, supportive or nurturing
> framing.**"

So a v3 rater is told supportiveness is not a signal, and shown a band definition whose second
sentence is a supportiveness description. The `keep_distinct` even tries to reconcile it —
"extremely supportive and caring while giving feedback rarely and gently (low band)" — but that
sentence *strengthens* the association it is trying to break.

**This means the round-1 raters were not simply off-axis on Feedback.** Citations like "never
retaliate," "comfortable coming forward," "coworkers care about your growth" are close to a literal
match for the frozen 0.1 band's own words. `FEEDBACK_DIMENSION_DIAGNOSIS_2026-09-01.md` scored those
as off-axis rater errors; on the frozen text they are the anchor's own language. The contamination
is in the band definition, not only in the reader.

**Recommendation:** before S-12 goes to Julie, either strip the valence clause from feedback 0.1
(leaving frequency and delivery style: "occasional, softened, conflict avoided") or drop the
`keep_distinct` sentences that contradict it. Shipping both is worse than shipping neither.

---

## 6. Caveat on rater B, stated fairly

B cited **1.03 quotes per cell** (35 of 36 cells have exactly one). C cited 3.58, A 3.22. Her
variance decomposition sits below the chance baseline on *both* main effects. Her cell-level
correlation is +0.20 with A, **−0.20 with C**, +0.21 with the extractor — she covaries with nothing.

Two things follow, and only two:

1. **She did nothing wrong.** `RATER_INSTRUCTIONS.md` requires "at least one passage." One is
   compliant. This is not a criticism of her and must not be presented to her or about her as one.
2. **The S-15 headline is partly a property of B's returns, not only of the anchors.** The −0.195
   B–C correlation that S-58 was built to explain has one nearly-structureless input. Before S-58
   is described as explaining S-15, recompute the S-15 statistics with B's cells weighted by
   evidence volume, or report A–C alongside B–C (+0.40 vs −0.20) so the reader can see it.

A read-through impression that B's free-text notes frequently contradict her scores was **checked
mechanically and not confirmed**: a lexical sign test over all 54 non-empty notes found **2**
inversions, both hers (P-01/autonomy score 0.9 with a note reading "micromanagement"; P-05/pace
score 0.3 with a note reading "fast paced"). Two is not "frequently." The impression is withdrawn.

---

## 7. Analysis (ii): re-scoped, and now confirmatory rather than primary

Script written and dry-run verified: `s58_citation_probe.py` (18 calls; `--dry-run` costs nothing).
Three changes from STATE's description, all forced by evidence:

1. **The primary outcome must be the off-axis rate, not the band delta.** From the probe's own
   comparison table, off-axis detection is 12/12 (100%) and the 0.1/0.3 boundary is 8/10 (80%).
   A band delta *is* a boundary measurement. Measuring a one-band effect with an instrument that is
   one band wrong 20% of the time is not a measurement. Band deltas are computed and printed, and
   labelled descriptive-only.
2. **`ForcedChoiceBandProbe.probe()` cannot answer (ii) as returned.** It collapses the 5-way answer
   to `best_match == 0.1` and folds off-axis into `False`. The script therefore injects the class's
   own `call_fn` hook and captures the full JSON on the way through — prompt and schema stay
   byte-identical to the validated design, and `extremity_flag.py` is not touched.
3. **The control arm is not optional.** An off-axis rate has no scale. The default `--arms B,C,llm`
   runs the extractor's own verified citations through the identical probe. Without it the human
   numbers should not be written up. (It needs `all_dims_evidence_2026-09-01.json`, which lives in
   the scratch `decision_test/` tree — the script errors clearly if it is missing.)

**Honest limit:** B contributes 6–7 fragments per dimension. (ii) can characterise C and the
extractor; it cannot characterise B.

**And it is no longer the main event.** M4 measured construct collision mechanically, with a
permutation p-value, for free. (ii) adds one thing M4 structurally cannot see: a passage cited once,
under the wrong dimension, by one rater. Given the Feedback result that is worth 18 calls — but it
is now confirmatory.

---

## 8. A validation path that does not need Carolynn or George

The constraint is real: no new human labelling, ever. But the pair-collision statistic in §4 is
computed from *citations*, and the extractor produces citations for free.

**Proposed test, ~6 calls:** re-run `run_all_dims_evidence.py` against `anchors_v3_PROPOSED.json`
and recompute the cross-dimension passage-reuse counts. Three outcomes, all informative:

- Collisions drop on the rewritten pairs -> the anchor text is a live lever on the extractor, and
  v3 has evidence behind it for the first time.
- Scores unchanged but citations move -> the rewrite changes what the model *looks at* without
  changing what it *says*. That is a real finding and it reframes the Decision no-op.
- Neither moves -> **anchor prose is inert for the extractor**, the only remaining lever is human
  raters, and human raters are unavailable. That is the negative result that would settle whether
  S-12 is worth Julie's time at all, and it is worth knowing before she spends it.

This does not validate the rubric for humans. Nothing can, and no proposal here pretends otherwise.

---

## 9. What this changes about S-58

S-58 is worth keeping and is worth reframing. As written it claims a rubric-wide misreading of the
low band. The data says something narrower and more actionable:

- No halo (§2, pre-registered null).
- No wholesale construct drift (§4, 65% vs 23% chance, p = 0.0002).
- A **dimension-specific separability problem**, worst on decision (3.2x pace's disagreement),
  concentrated on three pairs, the top one of which has no guardrail in v1 or v3.
- **Confidence that does not track reliability** — arguably the more dangerous defect, and entirely
  absent from S-58's three mechanisms.
- A genuine but narrow valence effect: 0.1 use clusters on autonomy and decision and is **zero in 18
  opportunities on pace**, whose 0.1 band is the most positively worded of the six. That favours
  "negative-sounding evidence routes to the low band" over "the low band is avoided as a bad grade."

Mechanisms (a), (b) and (c) should stay unmerged. But (a) should be narrowed to its evidence-routing
form, (c) should be downgraded to the pair-specific form §4 measures, and a fourth candidate belongs
on the list: **the dimension asks about something the evidence class does not directly report**
(decision's *basis* is almost never stated in public evidence; pace's tempo almost always is), so
each reader fills the gap from their own priors and does so confidently. That is a hypothesis, not a
result. It is the best available explanation of why decision is the worst dimension and pace the
best, and it is not testable on this sample.
