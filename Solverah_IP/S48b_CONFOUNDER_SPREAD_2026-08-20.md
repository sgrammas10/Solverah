# S-48(b) — How much stage / comp spread does the 15-20 ground-truth set need?

2026-08-20. Built against the **actual model artifacts**, opened rather than recalled:
`causal_graph/v1_model/solverah_model_config.yaml` and `match_core.py`
(`outcome_logit`, `preprocess_conf`, `fit_gap`).

Scripts: `s48b_confounder_spread_sim.py`, `s48b_lever_demo.py`.
**Status: evidence for Sebastian's call. Does not resolve S-48(b).**

---

## 0. Three things the config says that the S-48 discussion had not used

**(a) The two confounders are not symmetric in reach.**

```yaml
- key: stage_size
  biases: [autonomy, pace, collaboration, feedback, innovation, decision]   # all six
- key: comp
  biases: [pace, autonomy]                                                  # two
```

Each contributes exactly **one** additive term to the logit (`w * standardized_value`) —
`biases` is the DAG pathway, i.e. **which dimensions' `mag`/`dir` weights get biased if that
confounder is badly adjusted.** So a `stage_size` failure contaminates six dimensions; a `comp`
failure contaminates two.

**(b) The config already names ~15 companies, from a source nobody had cited.**

```yaml
- key: comp
  scale: { mean: 3.0, sd: 1.0 }   # "Replace with real distribution once ~15 companies
                                  #  are scored."
```

Independent corroboration of the 15-20 size decision, arrived at from a completely different
direction than the power simulation. Worth noting because S-48's size answer now rests on two
unrelated supports rather than one.

**(c) The design already admits company-level unobserved heterogeneity.**

```yaml
- key: manager_quality
  measurable: false
  biases: [feedback, autonomy]
```

A company-level factor that moves outcomes and is never a model term **is** a company random
intercept. This turns out to be load-bearing — see §3.

---

## 1. The answer, in one line

**`comp` is the binding constraint, not `stage` — which is the opposite of where this
project's attention has been.** D-08's stage-1-2 guard and the "78% stage-5 skew" have been
the recurring worry; on these numbers stage restriction is the milder problem and comp
restriction is severe.

Holding the set at **19 companies × 80 respondents** and changing *only* which companies are
chosen (40 seeds, paired simulation noise):

| | skewed roster | deliberately spread | improvement |
|---|---|---|---|
| empirical SD of `w_stage` | 0.249 | 0.204 | 1.22× |
| empirical SD of `w_comp` | 0.336 | 0.116 | **2.9×** |

An SD estimated from 40 draws carries ~11% relative uncertainty, so a ratio of two SDs carries
~16%. **The 2.9× on comp is far outside that. The 1.22× on stage is not — treat stage's
benefit as directional, not demonstrated.**

Between-company information (sum of squared standardized deviations, which is what the
coefficient precision actually scales with) tells the same story: spreading raises stage's
information **1.5×** and comp's **5.1×**.

**Why comp is worse:** `comp` is self-centering by design — 3 = "at market" — so a roster of
unremarkable employers piles up on the mode and the confounder is nearly constant. `stage_size`
skewed to 5 is at least *at an extreme*, so the few off-mode companies sit far from the mean
and each carries a lot of leverage.

---

## 2. The failure mode to avoid absolutely: zero spread looks perfect

Sweeping how many of the 19 sit off the modal value (RMSE = √(bias² + SD²), which unlike SD
alone penalises a stable-but-wrong estimate):

| companies off-mode on `comp` | RMSE | bias | SD |
|---|---|---|---|
| **0** | **0.400** | **−0.400** | **0.000** |
| 2 | 0.310 | −0.005 | 0.314 |
| 4 | 0.203 | +0.042 | 0.201 |
| 6 | 0.161 | −0.042 | 0.157 |
| 8 | 0.131 | +0.024 | 0.131 |
| 19 | 0.100 | −0.019 | 0.099 |

**Read the top row carefully.** With `comp` constant across the set, the estimate is perfectly
stable (SD **0.000**) and **the bias equals the entire true weight** — the coefficient is
simply not there, and every seed agrees on the wrong answer. This is the worst available
failure: it presents as a tight, reproducible, confident estimate.

**And it collides with the config's own plan.** The comment says to replace comp's fixed
`sd: 1.0` with the real distribution once ~15 companies are scored. If those 15 are all at
comp = 3, the computed real sd is ≈ 0 and standardization divides by ≈ 0. The config authors
guarded the batch-size-1 degenerate case explicitly; a degenerate *set* is not guarded.

The stage sweep is flatter and noisier — 0.215 at zero spread, ~0.15–0.18 from 6 off-mode
upward, with the differences between 6, 8, 10 and 19 inside the noise.

---

## 3. Which lever works — and a way the model will lie to you

Three levers, 40 seeds each. Two quantities per cell: the **model SE** a naive logistic fit
reports, and the **empirical SD** of the estimate across independently drawn rosters (the truth).

**Lever 1 — more respondents per company (19 companies, skewed):**

| resp/co | rows | model SE (stage) | empirical SD | ratio |
|---|---|---|---|---|
| 20 | 380 | 0.308 | 0.485 | 1.6× |
| 80 | 1,520 | 0.143 | 0.249 | 1.7× |
| 320 | 6,080 | 0.072 | 0.262 | 3.6× |
| 1,280 | 24,320 | 0.036 | 0.225 | **6.2×** |

**64× the rows improves the reported SE 8.4× and the real uncertainty only 2.2×, flattening
after ~80/company.** The overconfidence ratio grows from 1.6× to 6.2×. Piling on respondents
mostly buys precision the model *claims* but does not *have* — because `stage_size` and `comp`
are company-level constants and `manager_quality` is an admitted company-level unknown, so
rows within a company are not independent.

**This is the same error this project has already corrected twice** — the seed/n pooled-CI
confound in STATE §5, and per-cell pooling in the S-48 size sim — arriving a third time in a
new costume. It will arrive again when the real model is fitted, unless the fit accounts for
company clustering.

**Lever 2 — more companies** (80 resp each, skewed): empirical SD(stage) falls 0.575 → 0.194
going 10 → 40 companies. Real, monotone, expensive.

**Lever 3 — spread, at fixed cost:** §1's table. **Free** — it is only which companies you pick.

---

## 4. Recommendation (Sebastian's call, not made here)

1. **At least ~6 of the 15-20 off the modal value on `comp`**, spread *both* directions —
   below market (1-2) and above market (4-5). Comp is self-centering, so both tails are needed.
   Returns flatten past ~8. Six is roughly a third of the set.
2. **At least ~6 off stage-5**, spread across stages 1-4. Weaker evidence than comp; this is
   also what D-08's range-restriction guard already asks for, so it costs nothing new to honour.
3. **Do not satisfy both constraints with the same companies.** The efficient-looking move —
   pick 8 "unusual" companies that are off-mode on both axes — correlates the two confounders
   (mean |corr| 0.245 vs 0.136) and costs ~25-30% precision on both:

   | off-mode assignment | RMSE(`w_stage`) | RMSE(`w_comp`) | mean \|corr\| |
   |---|---|---|---|
   | same companies both axes | 0.219 | 0.178 | 0.245 |
   | disjoint companies | 0.169 | 0.140 | 0.136 |
   | random | 0.173 | 0.155 | 0.181 |

   Directional at this resolution, but the mechanism is plain collinearity and it points the
   same way for both coefficients. Concretely: a stage-2 startup that also pays far above
   market is a *worse* pick than a stage-2 startup at market plus a stage-5 incumbent paying
   far above market.
4. **Respondent volume is not a substitute.** §3. It is also not free, and past ~80 per company
   it mostly buys overconfidence.

---

## 5. Honest limits — read before quoting any number here

- **The "78% stage-5 / comp-3" profile is a reconstruction, not a measurement.** STATE records
  the 2026-07-25 roster that way; the docx is in Sebastian's Drive and
  `ground_truth/roster/` on disk is **empty**. If the real roster spreads comp more than the
  both-at-mode reading assumes, §1's comp finding softens proportionally. **This is the single
  cheapest thing to check and it would firm up or overturn the headline.**
- **True weights are illustrative** (`w_mag −1.2`, `w_stage 0.5`, `w_comp 0.4`), so absolute
  RMSE values are not predictions. The *shapes* — where curves flatten, which lever moves
  which quantity, the ratios between arms — are what the argument rests on.
- **`COMPANY_RE_SD = 0.5` is assumed, not measured.** No placement data exists to estimate
  company-level outcome heterogeneity. A larger value widens the §3 overconfidence gap; a
  smaller one narrows it. The *direction* follows from the design, not from the number.
- **No detectable difference in `w_mag` bias across spread profiles** at N=19 (all ≈ −0.1,
  SD ≈ 0.35). So the case for spread rests on confounder-weight precision and on serving-time
  behaviour — **not** on in-sample gap-weight bias. STATE §5's "range restriction is the
  expensive thing for weight recovery" is not reproduced here for *confounder* range
  restriction at this N; recorded as a discrepancy rather than smoothed over.
- **One draw of one design.** Per D-21 these are simulation findings under stated assumptions
  with dispersion reported across 40 seeds — not measurements of anything real. Nothing here
  clears D-21 for a third-party-facing document without re-derivation on real data.

---

## 6. Method note — a bug worth recording, because it is the D-21 shape again

The first version of the spread simulation seeded **one** RNG per (seed, arm). The company
profile functions consume **different amounts of randomness per arm** (the skewed profile
draws `n − n_mode` values, the spread profile draws `2n`), so the stream state entering the
data generator diverged and the person draws and outcome noise were **not matched across
arms**. The contrasts were silently unpaired while being reported as paired — every headline
value looked plausible and only the paired SDs were wrong.

Fixed by splitting into two streams (`rng_co` for the roster, `rng_sim` identical across arms).
This is exactly what D-21(b) means by *pairing must be structural rather than asserted*, and it
is the same class of defect `seed_discipline.paired_contrast` exists to make impossible.

A second correction: the initial run omitted company-level unobserved heterogeneity, which made
rows within a company conditionally independent — and under that wrong model more respondents
buy confounder precision **without limit**, which is how §3's finding was nearly missed
entirely. The config's own `manager_quality: measurable: false` is what says that model was
wrong.
