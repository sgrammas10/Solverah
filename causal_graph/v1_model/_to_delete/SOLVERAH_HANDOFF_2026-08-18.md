# Solverah — Session Handoff, 2026-08-18

**Topic: closed `-17e`'s item 1 — the multi-seed re-run gating the 2.5x figure. The
figure does not survive. `-17e` §3's "lattice data needs roughly 2.5x the rows" was a
single-seed artifact: across 5 paired seeds the effect is +0.005 in |err| (95% CI
[−0.049, +0.059]), and three of the four differences `-17e` reported fall outside the
confidence interval of the repeated measurement. Two further problems with the original
comparison were found and corrected in the process — it was confounded (data resolution
and the Finding-1 patch moved together) and unpaired (each arm drew its own RNG stream).
The corrected 2×2 factorial finds no detectable resolution effect and no detectable
patch effect on recovery. The `-17e` §3 posterior-SD "anomaly" also mostly dissolves; the
small residue now has a mechanism. Custom instruction honored: this retracts a number
this project produced yesterday rather than defending it.**

Sits on top of `SOLVERAH_HANDOFF_2026-08-17e.md`. `build_model.py` was **not** modified.
New file: `causal_graph/v1_model/recovery_multiseed.py` (sweep) + `analyze_sweep.py` +
`plot_multiseed.py`; outputs in `causal_graph/v1_model/results/`. `anchors.json` untouched,
still frozen at `v1-frozen-2026-08-15`.

---

## 1. Two defects in the `-17e` §3 comparison, found before re-running

**(a) It was confounded.** The "uniform (old)" column was continuous-uniform data run
through the **unpatched** model (no person snap). The "lattice (new)" column was lattice
data through the **patched** model. Two variables moved at once, so the 2.5x was
attributed entirely to Finding 2 (data resolution) when it also carried whatever
Finding 1's snap does to recovery. Simply repeating those two arms at more seeds would
have produced a tighter interval around a quantity that isn't cleanly interpretable.

**(b) It was unpaired.** `recovery_curve()` seeds one `rng` and draws person, env,
confounders and outcomes from it in sequence. `rng.choice(PERSON_LATTICE, n)` and
`rng.uniform(0,1,n)` consume the stream differently, so at "the same seed=0" the two arms
also got different confounder values and different binomial draws. Arm effect and draw
noise were entangled — the exact failure `lattice_gap_analysis.py` §C documents.

## 2. What was run instead

`recovery_multiseed.py`: a **2×2 factorial, paired across seeds**.

| arm | data | model | corresponds to |
|---|---|---|---|
| A `uniform_raw` | continuous uniform | no snap | the original pre-patch pipeline |
| B `lattice_snap` | lattice | snap | the current post-patch pipeline |
| C `uniform_snap` | continuous uniform | snap | isolates the patch |
| D `lattice_raw` | lattice | no snap | isolates resolution |

- **Pairing:** one latent stream (`u_person`, `u_env`, `conf`, `u_y`) is drawn per seed and
  shared by all four arms. Arms differ *only* in how the latents are discretised and
  whether the model snaps. Outcomes use the same `u_y` against each arm's own `p_true`, so
  even the binomial draw is paired.
- **Coherent arms:** the DGP uses the same snap setting as the fit. An arm is a whole
  pipeline, not a mismatched DGP/model pair.
- 5 seeds × 4 arms × n ∈ (200, 800, 2000, 5000) = **80 fits**, chains=2, draws=1000,
  tune=1000, planted `pace.mag = −2.0`, prior mean −1.0. All `r_hat` ≤ 1.003,
  `ess_bulk` ≈ 3000+. Wall clock 55 min with the compiled backend. Resumable.

## 3. Result — the 2.5x does not replicate

Paired |err| difference, **lattice_snap − uniform_raw** (the exact contrast `-17e` §3
reported), 5 seeds:

| n | observed diff | 95% CI | `-17e` reported | inside CI? |
|---|---|---|---|---|
| 200 | −0.036 | [−0.226, +0.155] | +0.315 | **no** |
| 800 | −0.001 | [−0.165, +0.163] | +0.262 | **no** |
| 2000 | −0.009 | [−0.124, +0.105] | +0.116 | **no** |
| 5000 | +0.066 | [−0.033, +0.166] | +0.027 | yes |
| **pooled (20 pairs)** | **+0.005** | **[−0.049, +0.059]** | | |

Sign counts are 10/20 each way. There is no effect here.

Mean |err| across 5 seeds, all four arms:

| n | A uniform/raw | B lattice/snap | C uniform/snap | D lattice/raw |
|---|---|---|---|---|
| 200 | 0.683 | 0.647 | 0.711 | 0.705 |
| 800 | 0.486 | 0.485 | 0.515 | 0.521 |
| 2000 | 0.341 | 0.332 | 0.318 | 0.360 |
| 5000 | 0.187 | 0.253 | 0.155 | 0.221 |

Seed-to-seed SD of |err| is 0.06–0.32 — **larger at every cell than any between-arm
difference.** That single number is the whole story of why `-17e` §3 read as signal.

### Factorial decomposition (paired, pooled over n, 20 pairs each)

| contrast | isolates | mean diff | t | signs |
|---|---|---|---|---|
| A vs D | resolution, model unpatched | −0.028 | −1.28 | 6/20 |
| C vs B | resolution, model patched | −0.005 | −0.17 | 12/20 |
| A vs C | patch, data continuous | −0.000 | −0.03 | 9/20 |
| D vs B | patch, data lattice | +0.022 | +0.73 | 11/20 |

No cell of the factorial moves. Both candidate explanations for the 2.5x are dead, not
just their sum.

Figure: `results/recovery_multiseed.png`. Raw: `results/recovery_multiseed.csv`
(80 rows, one per arm × seed × n, with diagnostics).

## 4. The posterior-SD anomaly, resolved

`-17e` §3 left this "unexplained rather than rationalized": lattice data gave a *tighter*
posterior SD at every n, which doesn't fit "coarser resolution, therefore worse."

Paired, the effect largely dissolves and what remains is tiny:

| n | mean SD diff (B − A) | 95% CI | seeds tighter |
|---|---|---|---|
| 200 | −0.0020 | [−0.0147, +0.0108] | 3/5 |
| 800 | −0.0031 | [−0.0132, +0.0069] | 3/5 |
| 2000 | −0.0109 | [−0.0214, −0.0004] | 5/5 |
| 5000 | −0.0064 | [−0.0133, +0.0004] | 5/5 |

So: consistent in direction at the larger n (5/5 both times), but ~2–4% relative — an
order of magnitude smaller than `-17e`'s framing implied, and immaterial to any decision.

**The mechanism, from the logged diagnostics — and it is the actually interesting result
of this session.** Mean SD of `|gap_pace|` in the generated data:

| arm | gap_sd | distinct \|gap\| values | mean p_true |
|---|---|---|---|
| A uniform/raw | 0.2372 | 1995 | 0.104 |
| B lattice/snap | 0.2350 | **21** | 0.108 |
| C uniform/snap | 0.2308 | 1995 | 0.109 |
| D lattice/raw | 0.2522 | 52 | 0.086 |

Discretising the instruments collapses the number of distinct `|gap|` values by **95×**
(1995 → 21) while leaving the *spread* of `|gap|` essentially unchanged (0.2372 → 0.2350,
under 1%). Logistic Fisher information per row goes as `p(1−p)·x²` — it depends on the
**variance** of the predictor, not on how many distinct values that variance is spread
across. So the lattice costs almost nothing in recovery, and the small SD difference that
remains tracks the small `p_true` differences, not resolution.

**This is the sentence that should replace `-17e` §3:** coarse instrument resolution is
not, by itself, expensive for weight recovery. What would be expensive is *range
restriction* — the env scale's inability to leave [0.1, 0.9] — and that is a separate
issue, already addressed by Finding 1's snap, and visible in the table above as arm D's
inflated `gap_mean` and depressed `p_true`.

## 5. What this does and does not retract

**Retracted:** the 2.5x rows figure, and the claim that Finding 2's validation-distribution
mismatch made every n-needed number "optimistic by an unmeasured amount." Measured, it is
optimistic by approximately nothing. Any n-needed figure computed against uniform
validation data appears usable as-is.

**Not retracted — the Finding 2 *fix* is still correct.** Validating against the values the
instruments can actually emit is right on principle regardless of whether it changes the
answer, and now the project can say it checked rather than assumed. Keep the lattice
draws in `sanity_check()` and `recovery_curve()`.

**Not retracted — Finding 1's patch stands, on its own evidence.** Its justification was
never recovery; it was the pole penalty in P(fit), which `-17e` §2 verified separately
(0.392 → 0.490 against a 0.485 perfect match). This sweep adds that the patch is
**recovery-neutral** (A vs C: −0.000, t = −0.03) — i.e. it fixes the pole penalty at no
measured cost to weight recovery. That is a supporting result for the patch, not against it.

## 6. Honest limits of this sweep

- **Power.** Paired SD is 0.06–0.16 depending on n, so SE ≈ 0.03–0.07 at 5 seeds. This
  decisively rules out effects of the size `-17e` claimed (+0.26 to +0.32 at low n) but
  **cannot rule out a true effect below ~0.10 in |err|.** "No detectable effect," not
  "provably zero."
- **One planted effect size, one dimension.** Everything here is `pace.mag = −2.0` against
  a −1.0/0.5 prior. A smaller planted effect, or one where the prior is badly placed, could
  behave differently. Not tested.
- **One nominally-significant cell, reported because suppressing it would be exactly the
  error this session is correcting.** C vs B at n=5000 gives t = −2.92 (1/5 signs), and
  arm B is nominally worst at n=5000 (0.253 vs 0.155–0.221). Against 20 contrasts tested,
  one |t| ≈ 2.9 is roughly what chance produces, and the same contrast is +1.10 at n=200
  and −0.22 at n=2000 — no monotone pattern. Treated as noise. **If anyone extends this to
  10 seeds, watch that cell specifically**; the script is resumable, so `--seeds 10` picks
  up where this left off and costs about another hour.
- Every posterior in every arm is still biased toward the prior at every n (signed error
  positive throughout). That is ordinary shrinkage, identical across arms, not an arm effect.

## 7. Process note for the project

Two single-seed results have now been reported as findings in two consecutive sessions
(`-17d` finding 3's correlation, `-17e` §3's 2.5x), and `lattice_gap_analysis.py` §C
documents a third from earlier. **Suggest a standing rule: no quantitative comparison
enters a handoff doc without ≥3 seeds and a paired design, or it enters explicitly labelled
as a pilot with no number quoted.** The compute is not the bottleneck — 80 fits took 55
minutes. The bottleneck was that the single-seed run looked convincing.

---

## Open / next

1. ~~Re-run `recovery_curve()` at 3-5 seeds~~ — **done, figure retracted.** `-17e` §3
   should be marked superseded by this doc.
2. **Extend the graduated-difficulty ladder to the other five dimensions**, bundled with
   the bias review's decision/feedback rewrites. Now the top item. Decision needs
   desirability-skew + graduated-intensity fixes together; feedback needs both plus the
   missing reverse-keyed item.
3. **Then re-run the calibration probe on decision and feedback** — still untested in
   every round to date.
4. **Hand `anchors_v3_PROPOSED.json` to Julie** — still gated on raters returning P-01–P-06.
5. **Decide whether to instrument the pilot for person-side dimension correlation**
   (`-17d` §4 finding 3). Free now, expensive later. Note this is itself a single-seed
   finding and should be treated as a pilot, not a result, per §7 above.
6. `pace → autonomy` and `pace → feedback` still unexamined category-3 candidates.
7. Carried, untouched: feedback anchor check vs. raters' Agreement tab (blocked); Test 1
   identified-condition re-check; `build_model.py` still has no `OrderedLogistic` path for
   `experienced` outcomes; `schema.sql` never migrated into the app database; George/RATER_B
   notification; `Solverah_Ground_Truth_Roster_v2.md` still missing.
8. **Standing, unchanged: anonymization does not prevent re-identification for 5 of 6
   companies.** Fifth session carrying this. Outside raters are handling packets described
   as anonymized; that description is not currently backed. Either fix it or change what
   the raters are told.
