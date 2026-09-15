# Solverah — Session Handoff, 2026-08-17e

**Topic: closed `-17d`'s item 1, the gating item before any further work. Patched
`fit_gap()` to correct the pole penalty (Finding 1) and switched `sanity_check()` /
`recovery_curve()` to draw from the real person/company lattices instead of
`rng.uniform(0,1)` (Finding 2). Verified both fixes against the unpatched code with
matched seeds and a matched compute backend: the pole-candidate P(fit) moved from 0.392
to 0.490 (now indistinguishable from a true perfect match at 0.485-0.489), and the
lattice-based recovery curve needs roughly 2.5x the rows of the old uniform-based curve to
reach the same |error| — a first empirical number for what Finding 2 called "optimistic by
an unmeasured amount." Custom instruction honored: be logical and future-thinking, do not
be agreeable — flagged one place below where the result is single-seed and could be noise,
rather than reporting it as settled.**

Sits on top of `SOLVERAH_HANDOFF_2026-08-17d.md`. `build_model.py` was patched in place (no
strikethrough convention needed — this is code, not a rubric doc; the diff is in git).
`anchors.json` was not touched, still frozen at `v1-frozen-2026-08-15`.

---

## 1. What changed in `build_model.py`

**New: `PERSON_LATTICE`, `BAND_VALUES`, `N_RUNS`, `COMPANY_LATTICE`, `closest_achievable()`.**
Same values as `lattice_gap_analysis.py` section A, deliberately duplicated rather than
imported — that script executes its full printed report as a module-level side effect on
import, so it isn't safe to treat as a library. If `BAND_VALUES` or `N_RUNS` ever change in
one file, the other has to be updated by hand; noted in both files now.

**`fit_gap(person_score, env_score, snap_person=True)`.** `snap_person=True` (new default)
replaces `person_score` with its closest value on `COMPANY_LATTICE` before differencing.
This is the actual fix: a person at either pole of their own 5-point ladder was being
compared against an env scale that structurally cannot reach past [0.1, 0.9], so even a
perfectly-matched pole candidate carried a permanent ~0.10 `|gap|` floor per dimension that
a mid-scale candidate never paid. `snap_person=False` reproduces the old, unfixed behavior
(used once below, deliberately, for the comparison).

**Where the snap actually happens.** `closest_achievable()` is a numpy argmin and cannot run
on a pytensor/`pm.Data` symbolic tensor, so it can't live inside `outcome_logit()`'s
symbolic path. The snap is applied once, in plain numpy, at the top of `build_model()`,
before `person` is wrapped in `pm.Data`; `outcome_logit()` is then called with
`snap_person=False` inside the model so it isn't (and structurally can't be) reapplied to a
symbolic value. Every other caller of `outcome_logit()`/`fit_gap()` — `sanity_check()`,
`recovery_curve()`, anything written later — gets the fix by default without needing to know
this plumbing exists.

**`sanity_check()` and `recovery_curve()` now draw person from `PERSON_LATTICE` and env from
`closest_achievable(rng.random(n))`** instead of `rng.uniform(0, 1, n)` for both. This is
Finding 2: the real pipeline can only ever emit 5 person values and 53 achievable env
values, and validating against continuous uniforms assumes gap resolution the instruments
don't have.

**Minor, unrelated to the two findings but touched in the same pass:** `PYTENSOR_FLAGS` is
now set with `os.environ.setdefault(...)` instead of a hard assignment. The original dev
machine has no C++ compiler, so the hard assignment forced the slow pure-Python linker
everywhere, including on machines that do have one (this session's sandbox has `g++`; a
full `recovery_curve()` run went from "still running after 10 minutes, killed" to ~5
minutes real time once compiled mode was allowed). Set `PYTENSOR_FLAGS=cxx=<path-to-g++>`
before running to opt in; unset environments get the exact original behavior.

---

## 2. Verification — Finding 1 (pole penalty), same seeds, patched vs. unpatched

Ran the identical `(person=1.0, env=0.9)` pole-candidate scenario and `(person=0.5,
env=0.5)` perfect-match scenario through the unpatched model (compiled backend, for a fair
timing comparison — see §1) and the patched one, `draws=1000`, same random seeds:

| | perfect match (0.5/0.5) | pole, closest-achievable match (1.0/0.9) | gap between them |
|---|---|---|---|
| **unpatched** | P(fit) = 0.489 ± 0.269 | P(fit) = 0.392 ± 0.256 | 0.097 |
| **patched** | P(fit) = 0.485 ± 0.272 | P(fit) = 0.490 ± 0.261 | **0.005** |

The unpatched model rated a *perfectly matched* pole candidate as meaningfully worse than a
perfectly matched mid-scale candidate — the exact bias `lattice_gap_analysis.py` predicted
from the deterministic algebra (there w_mag was a fixed point value, not a distribution;
under the real model with prior uncertainty on every weight the gap softens to ~0.10 P(fit)
instead of the ~0.15 the point-estimate odds-ratio implied, but the direction and rough
magnitude match). After the patch the two are within noise of each other, which is what
"the pole penalty is gone, genuine gaps aren't inflated" should look like. This check is now
wired permanently into `sanity_check()` so it re-runs every time the script does.

---

## 3. Verification — Finding 2 (validation distribution mismatch), before/after `recovery_curve()`

Ran `recovery_curve(ns=(200, 800, 2000, 5000), chains=2)` twice, same seed=0, same compiled
backend, once against the original `rng.uniform(0,1)` data and once against the new
lattice-drawn data (planted `pace.mag = -2.0`, prior mean -1.0):

| n | uniform (old) post_mean | uniform \|err\| | lattice (new) post_mean | lattice \|err\| |
|---|---|---|---|---|
| 200 | -1.019 | 0.981 | -0.704 | 1.296 |
| 800 | -1.536 | 0.464 | -1.274 | 0.726 |
| 2000 | -1.682 | 0.318 | -1.566 | 0.434 |
| 5000 | -1.710 | 0.290 | -1.683 | 0.317 |

At every matched n the lattice-based fit is further from the planted truth than the
uniform-based fit was — most strikingly, **lattice n=5000 (\|err\|=0.317) lands about where
uniform n=2000 (\|err\|=0.318) did.** Read plainly: hitting the same recovery precision on
data with the instruments' real resolution took roughly 2.5x the rows the old (uniform)
curve implied. That is a first concrete number for what Finding 2 called "optimistic by an
unmeasured amount" — it isn't optimistic by an unknown amount anymore, it's optimistic by
roughly this amount, for this planted effect size, at this n range.

Plots: `recovery_curve_UNIFORM_ORIGINAL.png` (old validation) and
`recovery_curve_LATTICE_FIXED.png` (new), both in `causal_graph/v1_model/` alongside this
doc.

**Caveat, stated because the project's own discipline requires it and the pattern is exactly
what `lattice_gap_analysis.py`'s method note warns about:** this is a single seed per
condition, not a multi-seed average. Section C of `lattice_gap_analysis.py` documents
getting burned by exactly this — one draw per condition reading as signal when it was
noise. The posterior SD also came out slightly *tighter* under the lattice data at every n
(0.434 vs 0.451 at n=200, down to 0.190 vs 0.201 at n=5000), which doesn't fit a clean
"coarser resolution, therefore worse everywhere" story and is left unexplained rather than
rationalized. The \|err\| pattern is directionally consistent with Finding 2 and large
enough (32-56% worse at three of four n's) that I don't think it's pure noise, but it has
not been run at multiple seeds and should not be quoted as a settled number without that.
**Open item, not closed: re-run with 3-5 seeds per condition before this 2.5x figure goes
into anything Julie or a rater sees.**

---

## 4. What this does and doesn't unblock

Per `-17d`'s own reasoning, item 1 gated item 2 (extending the ladder to the other five
dimensions) because re-centering the gap changes what person-side resolution buys — building
five more ladders first risked a re-pilot. That gate is now cleared: the gap is re-centered,
and the lattice-based recovery curve gives an actual (if single-seed) number for what
resolution buys under the corrected model.

It does **not** resolve `-17d` §4 finding 3 (pace↔innovation correlation) — that's still an
open pilot-instrumentation question with no Solverah data behind it, unaffected by this fix.
It does not touch `anchors_v3_PROPOSED.json`'s readiness for Julie, or anything in
`ANCHOR_BLEED_FIX.md`.

---

## Open / next

1. **Re-run `recovery_curve()` at 3-5 seeds per n** before quoting the 2.5x figure to anyone
   outside this repo (§3 caveat). Cheap now — the single-seed run took ~5 minutes at
   chains=2 with a compiled backend; a proper multi-seed sweep is an afternoon, not a
   re-architecture.
2. **Extend the graduated-difficulty ladder to the other five dimensions**, bundled with the
   bias review's decision/feedback rewrites — this was `-17d` item 2, now unblocked by item 1
   closing. Decision needs both fixes at once (desirability skew *and* graduated intensity);
   feedback needs both plus the missing reverse-keyed item.
3. **Then re-run the calibration probe on decision and feedback**, still untested in every
   round to date.
4. **Hand `anchors_v3_PROPOSED.json` to Julie** — unchanged from `-17d`, still gated on
   raters returning P-01–P-06, not on this session's work.
5. **Decide whether to instrument the pilot for person-side dimension correlation**
   (`-17d` §4 finding 3) — free now, expensive later, unaffected by this session.
6. `pace → autonomy` and `pace → feedback` still unexamined category-3 candidates, carried
   unchanged from `-17d` item 6.
7. Carried, untouched: feedback anchor check vs. raters' Agreement tab (still blocked);
   Test 1 identified-condition re-check; `build_model.py` still has no `OrderedLogistic` path
   for `experienced` outcomes (the fix this session touched `fit_gap`/`sanity_check`/
   `recovery_curve`, not the outcome-type gap); `schema.sql` never migrated into the app
   database; George/RATER_B notification; `Solverah_Ground_Truth_Roster_v2.md` still missing.
8. **Standing, unchanged: anonymization does not prevent re-identification for 5 of 6
   companies.** Restated again because nothing has been done about it in four sessions now.
