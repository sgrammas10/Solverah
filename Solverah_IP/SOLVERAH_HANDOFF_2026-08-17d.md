# Solverah — Session Handoff, 2026-08-17d

**Topic: verified round 3 from the raw CSVs rather than the terminal summary, which surfaced
that `SCALE_CALIBRATION_CHECK.md`'s §5 was wrong in three ways at once — one finding
withdrawn, two promoted. The cause was a detector keyed on the wrong variable, specified in
the doc and implemented faithfully in code. Fixed the instrument, then ran four rounds (130
calls, 780 rows) that closed the autonomy cross-dimension bleed completely (5 reproducible
cells → 0) and established a third category of bleed that no rubric change can fix. Then
went offline and answered `-17c` open item 6, finding a deterministic 45%-odds penalty
against pole candidates sitting in shipped model code.** Custom instruction honored
throughout: be logical and future-thinking, do not be agreeable — push back.

Sits on top of `SOLVERAH_HANDOFF_2026-08-17c.md`. `SCALE_CALIBRATION_CHECK.md` was amended
in place (strikethrough + dated correction, the established convention). Two new working
docs: `ANCHOR_BLEED_FIX.md` (the full bleed record) and `lattice_gap_analysis.py` (the
`fit_gap` analysis, runnable and self-documenting).

**`anchors.json` was never touched.** It stays frozen at `v1-frozen-2026-08-15` with
P-01–P-06 outstanding. Everything anchor-related was done through a new `--anchors` flag
that loads an alternate rubric without editing the live file.

---

## 0. The finding that reframes the previous session

`-17c` §5 recorded a "collaboration→autonomy bleed, confirmed 10/10 across two texts."
Recomputed from the raw CSVs: **every one of those readings was exactly 0.5 — the neutral
band.** Nothing moved. It was also not consistent — round 1's three collaboration vignettes
returned confidence 0.6 / 0.3 / 0.1 on that same 0.5, and "10/10" describes one of them
generalized across three that disagreed.

Meanwhile two real bleeds were sitting unrecorded in the same CSVs:

| relationship | raw rows | old detector | verdict |
|---|---|---|---|
| collaboration → autonomy | 0.5 (neutral) on 20/20 runs | **fired** | not a bleed — **withdrawn** |
| autonomy → collaboration | 0.3 on **28/30** runs at autonomy ≥ 0.5 | silent | real — **promoted** |
| autonomy → innovation | **19/20** runs, tracking level (0.1→0.1, 0.9→0.7) | silent | real — **promoted** |

**Root cause, and it is a spec-level error, not a coding one.** The calibration doc's
Finding 3 specified that off-target **confidence ≥ High** is the leakage signal.
`run_vignette_probe.py` implemented it literally (`elif d.confidence >= 0.6`). Confidence is
how sure the scorer is of *where it landed*; the question is whether it landed somewhere it
shouldn't have. The right variable is **displacement off the neutral 0.5 band**. Both real
bleeds ran at confidence 0.1–0.3 and were structurally invisible.

A second, compounding gap: the probe logged `quotes_grounded`/`quotes_total` and **discarded
the quote text** — the one datum that separates a vignette artifact from an anchor defect.
630 rows had been scored without it.

---

## 1. Instrument fixes (all offline, verified before any call was spent)

**`run_vignette_probe.py`:**

* Detector rewritten to trigger on displacement ≥ 0.2 off neutral, not on confidence.
* New `evidence_quotes` and `displacement` CSV columns.
* One flag per off-target dimension instead of one per run — a dimension displacing on 4 of
  5 runs is one finding, and printing it five times is what made the old logs skimmable past.
* A cross-dimension rollup that aggregates **across levels**, which is the resolution the
  finding lives at: autonomy→collaboration is invisible at any single level and unmistakable
  across five.
* `--anchors` / `--allow-rubric-mismatch` so an alternate rubric can be A/B'd without
  touching the frozen file. The mismatch guard is opt-in by design.

Verified by replaying round 3's real CSV through the patched logic with `score_packet`
stubbed — **zero API calls** — confirming the new detector surfaces all three findings from
data already on disk.

**`make_anchors_v3.py` → `anchors_v3_PROPOSED.json`.** A minimal generated diff from the
frozen file, every replacement asserted against the exact v1 string it overwrites so it
fails loudly rather than drifting. Twelve leaf fields change and no others. Each edit carries
an evidence tag: `[VALIDATED]` / `[NEUTRAL]` / `[FALSIFIED]`.

---

## 2. Rounds 4–6: the autonomy bleed, closed

Deliberately one variable at a time, which is what made the results interpretable.

| run | anchors | vignettes | cells ≥3/5 | rows displaced /125 | mean \|displacement\| |
|---|---|---|---|---|---|
| round 3 | frozen | v3 | 5 | 27 | 0.0592 |
| round 4 Arm A | frozen | v4 cleaned | 4 | 22 | 0.0448 |
| round 4 Arm B | v2 proposed | v3 | 3 | 17 | 0.0336 |
| round 5 | v3 proposed | v3 | 1 | 14 | 0.0240 |
| **round 6** | **v3** | **v4** | **0** | **2** | **0.0032** |

Monotone across all five runs, no interaction (every cell ≤ its best single-fix value),
on-target control at zero variance in every arm.

**Both fixes were necessary and neither was sufficient** — the pre-registered "if Arm A
alone clears every level, drop the anchor proposal" condition did not trigger:

| off-target | level | R3 | Arm A | Arm B | cause |
|---|---|---|---|---|---|
| collaboration | 0.5 | 5/5 | **0/5** | 5/5 | vignette |
| collaboration | 0.7 | 4/5 | 5/5 | **1/5** | anchor |
| collaboration | 0.9 | 5/5 | 5/5 | **0/5** | anchor |
| decision | 0.1 | 4/5 | **1/5** | 4/5 | vignette |

**The `evidence_quotes` column produced a controlled proof, not an inference.** At autonomy
0.9 both arms cited the same phrase and scored it differently:

| arm | cited phrase | collaboration score |
|---|---|---|
| A — frozen bands | "how their piece gets done end to end" | **0.3**, 5/5 |
| B — rewritten bands | "own their piece end to end" | **0.5**, 5/5 |

Same model, same evidence, only band text differed. And the rewrite correctly did *not*
over-fix: Arm B still scored 0.3 on the 0.5 vignette's "*without looping anyone in first*"
(5/5), which is genuine meeting-density evidence a working Collaboration rubric should catch.

**The mechanism.** Collaboration's 0.1 band opened with the words "*Individual ownership*" —
the exact construct Collaboration's own `keep_distinct` assigns to Autonomy. Band text is
what the scorer matches, so the band won and the guard was dead letter. `where_to_look`
compounded it by pointing raters at "*own your area*" language, verbatim Autonomy's 0.7
anchor.

**Innovation needed a second attempt.** The first hypothesis — that Innovation's low pole
being named "*Execute / optimize*" collided with the ordinary verb — was **falsified**: 5/5
in both arms, with the scorer citing "*step-by-step playbook*" every run. Removing the word
from the vignette did nothing; renaming the pole and adding a `keep_distinct` guard did
nothing. The real culprit was process-maturity vocabulary inside Innovation's *own* low band
— "*Operational excellence*", "*efficiency focus*", "*mature offering*". Rewriting those took
it 5/5 → 2/5, mean 0.14 → 0.42, on unchanged vignette text.

**The transferable finding: `keep_distinct` does not override band text.** Collaboration was
fixed by rewriting its bands. Innovation was given a plain-English guard — "*Do not read
'follows a detailed brief' as low Innovation*" — and the scorer did exactly that, 5 times out
of 5. **Guards are documentation for human raters; bands are the instrument.** Any anchor
change intended to move the LLM scorer must land in band text. This is the single most
important thing to carry into Julie's rewrite.

---

## 3. Round 7: `anchors_v3` cleared, and a third category of bleed

Found for free by re-running the corrected detector over rounds 1–2, which had contained it
the whole time: **pace → innovation, 11/20 runs displaced**, and pace↔innovation is the
*other* pair `anchors.json`'s `keep_distinct` warns about. Never examined before because the
old detector never fired on it.

**Prediction 4 held, and it was the gating question.** Rounds 5–6 had only ever scored
*autonomy* vignettes under v3, so the rewritten innovation bands had never been asked to
score innovation evidence. Under v3 they returned on-target innovation 0.1/0.5/0.9 and pace
0.1/0.5/0.9, both at zero variance. **`anchors_v3_PROPOSED.json` is cleared to hand to
Julie.**

**Predictions 1 and 2 were falsified byte-identically.** pace→innovation is 5/5 at 0.30 at
both extremes under the frozen anchors *and* under v3. The rewrite changed nothing. The
quotes say why:

| relationship | cited phrase | genuine evidence for the off-target dimension? |
|---|---|---|
| pace-low → innovation | "the roadmap looks basically the same as it did six months ago" | **yes** |
| pace-high → innovation | "shipping first and refining later" | **yes** |
| innovation-low → pace | "mature, dependable engine", "shaving latency, fixing edge cases" | **yes** |
| innovation-high → pace | "most of which get killed within a quarter" | **yes** |
| pace-high → autonomy | "Deadlines are treated as fixed \| the work bends to fit them" | **yes** |

Not one is vocabulary collision. **The facts co-occur in real companies.** A company whose
roadmap hasn't moved in six months genuinely is both slow and non-novel. That is not
measurement error.

### The taxonomy this forces

1. **Anchor defect** — the off-target band claims a construct belonging to the target
   dimension. *Fix: rewrite band text.* (autonomy↔collaboration, autonomy→innovation — both
   fixed and validated.)
2. **Vignette artifact** — the vignette gratuitously states something about the off-target
   dimension. *Fix: rewrite the vignette.* (the 0.5 autonomy vignette.)
3. **Genuine construct correlation** — the cited phrase is real evidence for both dimensions.
   *No rubric fix exists, and attempting one would make the rubric stop measuring something
   true.* (pace↔innovation, pace→autonomy.)

**The displacement detector cannot tell these apart** — all three look like a displaced
score. Only the quote column can, which justifies the instrumentation change more than the
original bleed did. Supporting signal: round 6's residual is 2 rows at confidence 0.1; round
7's is 34 rows at 0.1/0.3/0.6. The scorer is not guessing in round 7.

**Do not sweep all 15 dimension pairs.** I recommended this mid-session and then withdrew it.
A sweep mixes categories 1 and 3 and produces a count nobody can interpret without reading
every quote. Three pairs examined, two anchor defects and one correlation — that base rate
does not justify 15 pairs of calls on spec.

---

## 4. `fit_gap()` over two lattices — `-17c` item 6, answered offline

`lattice_gap_analysis.py`, numpy/scipy only, no API calls, no PyMC. Person lattice
`{0, .25, .5, .75, 1}` (4-item `mean_pole` ladder) against a company lattice of 21 values on
a 0.04 grid in [0.1, 0.9].

**Finding 1 — the pole penalty. Real, deterministic, in shipped code.** The person lattice
cannot reach a matching company value at the extremes: a person at 0.0 has nothing closer
than 0.1. So a *perfectly matched* pole candidate carries |gap| = 0.10 on every dimension,
and `w_mag * |gap|` turns that into a penalty:

```
pole candidate, perfect match:  sum|gap| 0.60   logit -0.600   P(fit) 0.354
mid  candidate, perfect match:  sum|gap| 0.00   logit  0.000   P(fit) 0.500
odds ratio 0.549
```

**A decisive candidate loses 45% of its odds for being decisive** — 40% of a genuine ladder
rung, on all six dimensions at once. A fit product that systematically rates distinctive
people as worse matches than bland ones. **The fix already exists in the repo:**
`run_vignette_probe.py`'s `closest_company_band()` does exactly this correction for the probe
verdict — §2b of `-17c` reasoned it out — and it never reached `build_model.py`.

**Finding 2 — the model has only been validated on data the instruments cannot produce.**
`sanity_check()` and `recovery_curve()` draw person and env from `rng.uniform(0,1)`. Mean and
SD of |gap| match the real lattices closely, which is why this was easy to miss. Resolution
does not: **~176,000 distinct |gap| values under uniforms vs 53 under the real lattices.**
Every n-needed figure quoted so far is optimistic by an unmeasured amount.

**Finding 3 — correlation, DOWNGRADED, and this corrects what I claimed after round 7.**
Env-side correlation does not propagate into `fit_gap()`'s design matrix. Because
|gap| = |person − env| and person is drawn independently per dimension, person variance
swamps it — **realized design correlation was 0.04 even at env rho = 1.0**, with zero
estimator degradation. Degradation needs *both* sides correlated on the same pair; at 0.9/0.9
the per-dimension SD nearly doubles while the SD on their sum does not move. So round 7
measured only the env side and is **not sufficient** to establish a `fit_gap()` problem.
Whether real respondents' pace and innovation answers correlate is an empirical question
about people with no Solverah data behind it — **a pilot instrumentation decision, free
before fielding and expensive after.**

**Finding 4 — `mag`/`dir` collinearity. Watch item, not a defect.** `outcome_logit` adds both
`w_mag*|g|` and `w_dir*g`; when a dimension's gap keeps one sign these are the same
regressor. Max VIF is 1.3 at 85% one-sided and 9.1 at 99% — only severe near-degenerate.
Costs nothing to defer, since `priors.yaml` already pins every `dir` mean at 0.0.

---

## 5. My own errors this session, recorded because the pattern matters more than the fixes

* **Read round 3 off the terminal summary and called it a clean sweep** — the exact error
  `-17c` flags twice. The summary shows residuals and verdicts and nothing else: no variance,
  no grounding, no off-target readings. Corrected within the same turn.
* **Over-claimed "5/5 PASS" on round 3** when four of five company vignettes were reused
  verbatim from earlier rounds. One new band, four replications.
* **Wrong relative path** for `--anchors` in two docs (`../../` for a three-level hop).
  Caught before it cost a run.
* **Section C of the lattice analysis was wrong twice, and both wrong versions returned a
  clean-looking null** I nearly wrote up as "correlation doesn't matter." v1 destroyed the
  correlation by snapping to the lattice after inducing it; v2 induced it on env only. What
  caught it both times was printing the **realized** quantity beside the nominal one.
* **A throwaway analysis script silently dropped every 0.7 reading**, because
  `abs(0.7 - 0.5)` is 0.19999999999999996 and fails `>= 0.2`. The probe rounds before
  comparing and is correct; the throwaway did not. Any future re-analysis of these CSVs must
  round before thresholding.
* **Recommended a 15-pair sweep, then withdrew it** one round later when round 7 showed the
  categories are not separable by count.

---

## Open / next

1. **Patch `fit_gap()` to center on the closest achievable band** (§4 finding 1) and **swap
   `sanity_check()`/`recovery_curve()` to draw from the lattices** (finding 2), then re-run
   `recovery_curve`. Both offline. **This gates the ladder extension** — re-centering the gap
   changes what person-side resolution buys, so building five more ladders first risks a
   re-pilot. That argument was the reason this analysis ran before the extension, and it held.
2. **Then extend the graduated-difficulty ladder to the other five dimensions**, bundled with
   the bias review's decision/feedback rewrites per `-17c` §6's timing argument. Decision
   needs both fixes at once (desirability skew *and* graduated intensity); feedback needs both
   plus the missing reverse-keyed item.
3. **Then re-run the calibration probe on decision and feedback**, still untested in every
   round to date.
4. **Hand `anchors_v3_PROPOSED.json` to Julie** for the post-round-1 rewrite the frozen file's
   own `_note` already schedules. Lead with the `keep_distinct`-vs-band-text finding (§2) —
   without it she will spend effort on guard text that does not move the scorer. Do **not**
   adopt it before raters return.
5. **Decide whether to instrument the pilot for person-side dimension correlation** (§4
   finding 3). Free now, expensive later, and it is the only thing that can settle whether
   pace↔innovation is a real modelling problem.
6. **`pace → autonomy` and `pace → feedback` are unexamined category-3 candidates** (5/5 and
   4/5 in round 7). Probably genuine correlation; not confirmed by reading quotes.
7. Carried, untouched: feedback anchor check vs. the raters' Agreement tab (**still blocked** —
   raters have not returned P-01–P-06); Test 1 identified-condition re-check with citation
   verification; `build_model.py` has no `OrderedLogistic` path for `experienced` outcomes;
   `schema.sql` never migrated into the app database; George/RATER_B notification;
   `Solverah_Ground_Truth_Roster_v2.md` still missing.
8. **Standing, unchanged: anonymization does not prevent re-identification for 5 of 6
   companies.** Restated because it is the finding most likely to be forgotten and most
   damaging if a downstream claim quietly assumes otherwise. Nothing has been done about it in
   three sessions.

---

## Framings that survived pushback this session

* **A detector keyed on the wrong variable does not fail loudly — it reports a confident
  finding about the thing it can see.** `keep_distinct` correctly named autonomy/collaboration
  as the pair at risk; the instrument then confirmed a bleed on that pair *in the wrong
  direction*, and that read as corroboration.
* **The same evidence scored differently under two rubrics is a causal claim; a change in
  aggregate counts is not.** Everything load-bearing this session came from the quote column,
  not the score column.
* **A fix that removes a bleed it was not supposed to remove is a broken fix.** The anchor
  rewrite correctly kept scoring "without looping anyone in first" as solo. Had it zeroed that
  too, the rubric would have stopped measuring Collaboration.
* **Vary one thing at a time even when it costs a run you are confident about.** Arm B's 25
  calls re-scored vignettes already measured at zero variance. That repetition was the control,
  and without it nothing could be attributed.
* **Pre-register both outcomes, then honor the falsifications.** Three predictions were
  falsified this session and each one is tagged as such in the artifact rather than quietly
  dropped — including edits retained for independent reasons after failing their stated test.
* **"Neither alone, both together" is a real category and it is easy to miss.** Round 6 cleared
  cells that neither single fix touched. §6's "the lexical hypothesis is dead" was true of the
  word removal *in isolation* and wrong about its contribution in combination.
* **Not every cross-dimension correlation is a defect.** Category 3 exists, and forcing a
  correlated pair to read as independent would make the rubric less true, not more precise.
* **The cheapest instrument fix is the one that records what the API already returned.** Three
  rounds and 630 rows were spent discarding the quote text that would have diagnosed this in
  one.
