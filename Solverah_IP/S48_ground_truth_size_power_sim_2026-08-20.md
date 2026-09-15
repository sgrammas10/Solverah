# S-48 support — how many ground-truth companies does the calibration need?

2026-08-20. Built and run to answer STATE.md's open question (a) under S-48: "how many
ground-truth companies the calibration needs — this is a question with a number behind it
rather than a matter of taste." Discussed with Sebastian before any respondent or rater data
exists, same timing discipline as `prereg_power_sim.py`. **Status: informative, not adopted —
feeds the S-48 decision, does not resolve it.**

Scripts: `s48_ground_truth_size_power_sim.py` (base power curve), `s48_clustering_check.py`
(naive-vs-clustered correction). Both numpy-only, deterministic under a fixed seed, follow the
D-21 discipline — dispersion reported, false-positive rate calibrated, assumptions flagged
rather than asserted.

*(2026-08-20 later, S-55: the original script files were lost before being placed on disk and
were REBUILT the same day from this writeup. The rebuilt run reproduces the results below within
binomial SE — e.g. naive FP 0.345–0.468 vs the 0.348–0.488 recorded here; clustered power
recovering to ≥0.9 by N=15–19. Canonical home of this writeup: the claude.ai project doc
`claude/S48_ground_truth_size_power_sim_2026-08-20.md`; an identical disk copy lives at the
`Solverah_IP/` root since 08-20 so STATE's artifact names resolve on disk.)*

## The question

For a candidate ground-truth set of N companies (6 dimensions each), can we reliably tell
whether the LLM extractor is systematically miscalibrated against the human-rater consensus,
at a magnitude that would actually matter — half a rubric band (0.10) or a full band (0.20,
the same threshold D-12 already uses to call an anchor ambiguous)?

## Model and assumptions (flagged, not hidden)

- True latent score per company-dimension, human rater SD = 0.098 (measured, STATE §5
  lineage), LLM extractor score = true + bias + noise.
- **`n_raters` is swept at 2 and 3, not asserted** — it is exactly the value under dispute in
  this conversation (STATE's rater table and D-12(b) currently say 2 blind raters; that was
  just contested). Sweeping both means this result doesn't need that question resolved first.
- **`sigma_llm` (the extractor's post-mean-of-5 noise) is swept at 0.05 / 0.098 / 0.15** — it
  has never been measured. No LLM-vs-human comparison has been run yet; this is exactly what
  round 1 plus this calibration would give you.
- Dimensions within a company are NOT assumed independent — see the clustering check below,
  which exists specifically because the naive independent-cells assumption is the same shape
  of error STATE §5 already corrected once (the pooled seed-sweep contrast).

## Result 1 — base power curve (cells treated as independent within a company)

Across the full grid (n_raters ∈ {2,3}, sigma_llm ∈ {0.05, 0.098, 0.15}, 400 trials/cell,
power SE ≈ 0.01–0.025):

- **Detecting a full-band bias (0.20): power ≈ 1.00 at every N tested, down to N=6.**
- **Detecting a half-band bias (0.10): power ≥ 0.95 at N=6 in every scenario**, reaching 1.00
  by N=10–15 even under the loosest extractor-noise assumption.
- **Detecting a quarter-band bias (0.05) is the only regime where N=6 is thin**: power ranges
  0.46–0.98 at N=6 depending on extractor noise, climbing to conventional 0.8 power by N=15–19
  under loose extractor noise, or already there by N=10 under tighter noise.
- False-positive rate at bias=0 sits at 0.035–0.092 across the grid (nominal 0.05) — the test
  is calibrated, not anti-conservative, **under the independence assumption**.
- **n_raters (2 vs 3) barely moves any of these numbers.** Pooling 30+ company-dimension cells
  overwhelms the human-rater averaging difference. This is itself informative: the "2 vs 3
  blind raters" question matters a great deal for S-15's anchor-ambiguity flag (which computes
  over exactly those raters, no pooling) but turns out **not to be the load-bearing variable
  for this particular calibration question**.

**Read naively, this says 6 companies is already enough** to catch anything but the smallest
miscalibration. That reading is not trustworthy on its own — see Result 2.

## Result 2 — the naive-pooling correction (the part that changes the recommendation)

The base result pools every company×dimension cell as an independent draw. That is
questionable for the same reason STATE §5 already documents: **if a single company's packet
is unusually clear or unusually ambiguous, it can push the LLM (or a human rater) off in the
same direction on several of that company's dimensions at once.** A packet-level effect is not
a per-dimension coincidence; it's a company-level unit correlated across its 6 sub-observations
— structurally identical to the seed/n confound corrected in §5's sweep re-derivation.

Rerun at within-company noise correlation (rho) = 0 / 0.5 / 0.9, comparing the naive pooled
test against collapsing to one value per company first (the corrected approach — same fix
pattern as `paired_contrast`):

| rho (packet-level noise correlation) | N=6 naive power | N=6 clustered power | N=6 naive false-positive rate | N=6 clustered false-positive rate |
|---|---|---|---|---|
| 0.0 (no packet effect) | 0.998 | 0.998 | 0.064 | 0.102 |
| 0.5 (moderate) | 0.930 | **0.760** | **0.348** | 0.122 |
| 0.9 (severe) | 0.890 | **0.540** | **0.488** | 0.126 |

**The false-positive numbers are the important ones.** At moderate-to-severe packet-level
correlation, the naive pooled test doesn't just overstate power — it becomes badly
anti-conservative: a false "the extractor is miscalibrated" verdict roughly **35–49% of the
time** instead of the nominal 5%, driven by nothing more than one confusing or one unusually
clean packet. The correctly clustered test stays close to nominal (6–13%) at every rho tested.

At the same rho values, clustered power recovers to ≥0.9 by N=15–19 rather than N=6–10.

## What this actually says about S-48

1. **"Is 6 enough" depends entirely on whether packet-level effects are real, and nobody knows
   that yet — it has never been measured.** This is not a reason to defer the decision
   indefinitely; it's a reason to analyze round 1's own data (once it lands) with the CORRECT
   clustered test rather than the naive pooled one, and to treat a positive naive-only signal
   as suspect.
2. **If Sebastian's instinct is that packets vary a lot in clarity/quality (plausible — P-05
   is already flagged as the weakest scrub)**, the honest planning number is closer to
   **15–19 companies**, not 6, to keep calibration power reasonable under a corrected analysis.
3. **If packet quality is fairly uniform**, 6 is plausibly sufficient even under the corrected
   test — but that's an assumption, not a result, until it's checked against real data.
4. **This is a reason to build the clustered test into whatever code eventually runs the real
   calibration check**, the same way `seed_discipline.py` made D-21 structural rather than a
   prose rule. A naive pooled comparison run on round 1's actual six companies risks the exact
   failure this simulation demonstrates — and unlike the simulation, real packets don't come
   with a known rho to sanity-check against.

## Open items this creates

- **Doesn't resolve S-48**, informs it. The company-count decision still needs Sebastian's
  call on which candidate pool (6 / 19 / other) and the stage/comp-spread constraint from
  D-08's range-restriction logic — that's a design question, not a power question, and this
  sim doesn't touch it.
- **The n_raters question (2 vs 3 blind) turned out not to matter much for this specific
  question** — but it still matters for S-15's ambiguity flag and for D-12(b)'s reasoning
  about excluding Julie, which is unresolved as of this writing. See the decision queue entry
  logged the same day.
- If this becomes load-bearing, the next honest step is a small pilot with 2–3 companies where
  BOTH the naive and clustered test are computed, so rho gets an actual estimate instead of a
  swept assumption.
