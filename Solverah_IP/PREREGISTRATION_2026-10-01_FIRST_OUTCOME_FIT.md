# Solverah — Pre-registration: the first real outcome fit of the match model

**Written 2026-10-01, before any real outcome row exists.** Production has no
environment reports from real users yet; every number below comes from the synthetic
devfit harness (`causal_graph/v1_model/devfit/`), not from respondents.

**Status: ADOPTED 2026-10-01 by Sebastian.** Append-only from here (see below).

**Amendment convention.** Same as `PREREGISTRATION_2026-08-19_S17_S18.md`: once adopted
this document is append-only. An amendment is a dated section at the end saying what
changed and why; the original text is never edited.

**Why this exists.** The model ranks Situation Report cards on one expert's priors
(`priors.yaml`, Julie, adopted 2026-09-17). The first real data will be small, and a
small dataset is exactly where an analyst can talk themselves into a result: by fitting
until it looks right, by choosing which rows count after seeing them, or by looking
every week until something crosses a line. This fixes those choices now, while they
cost nothing.

---

## Part 0 — Machinery

### 0.1 The question, in one line

**Does the person-vs-job gap predict how people rate their job, and is Julie's overall
harshness about right?** That is the only question the first fit answers. Per-dimension
weights are not learnable at this N (see 0.6) and are not part of it.

### 0.2 Analysis population

A row is one environment report, assembled by
`assemble_training_data.assemble_environment_training_data` as it stands at the commit
that adopts this document. Then:

- **One report per respondent: the FIRST eligible one** (earliest `submitted_at`). The
  assembler returns all of a user's reports; later reports are excluded from the primary
  analysis. Letting the analyst pick which report counts is a degree of freedom worth
  closing now. Later reports are kept and may be used for exploratory work, labelled.
- **Career status:** `employed` and `between_jobs` only (`TRAINABLE_CAREER_STATUSES`).
  `first_job` cannot produce a row by design.
- **Outcome present:** `experienced` (1..5) non-null.
- **Excluded accounts, fixed BEFORE Look 1 and never after:**
  - any email ending `@synthetic.solverah.invalid` (devfit seeds);
  - people who designed or know the instrument (Sebastian, Julie, and anyone else who
    built or reviewed it), and any account created for testing. The exact list is
    written into Appendix A, by email, **before** the Look 1 extract is pulled. Adding a
    name to it after seeing outcomes is not allowed.
- **No other exclusions.** Not on completion speed, not on "suspicious" answers, not on
  comp or industry being missing (missing confounders are masked, which is the model's
  job, not the analyst's).
- Reports from form version `env-v1-2026-09-10` (before industry was asked) are
  included; their industry is masked. Form version is recorded on every row.

### 0.3 The model, fixed

- `build_model` with **`global_scale` ON**: dimension weights = `s * prior_mean + delta`,
  `s ~ LogNormal(0, 0.5)`, `delta ~ Normal(0, 0.10)`; confounders, intercept and
  cutpoints unscaled (commit `edb3a23`). Priors from `priors.yaml` at the adopting
  commit. Ordinal head as built (c3 pinned at 0).
- **Sampler:** 4 chains, 1000 tune, 1000 draws, seed `20261001`.
- **Health gate:** `run_fit.is_healthy` (finite max r_hat < 1.05 and zero divergences).
- **One pre-registered remedy:** if the gate fails, re-run once with tune and draws
  doubled, same seed. If it still fails, Look 1 reports **"no result: fit unhealthy"**
  and nothing else. Changing priors, the model, `delta` sd or the row set to get a
  healthy fit is not allowed; that would be a new pre-registration.

### 0.4 The quantities

- **s** — the posterior of the global scale. Reported as mean, sd, 94% HDI (the devfit
  convention).
- **Δ (the premise quantity)** — per posterior draw, the drop in P(doing well) from a
  fully aligned person to one sitting 0.2 below the role on every active dimension, with
  every confounder at its standardized zero:
  `Δ = uniform_gap_p_fit(gap=0) − uniform_gap_p_fit(gap=−0.2)`
  (`causal_graph/v1_model/global_scale.py`). A drop under **0.05** is treated as
  negligible: a five-point change in the chance of doing well across a gap on all six
  dimensions is too small to matter to anyone reading a report.

### 0.5 Stopping rule — fixed looks, nothing in between

- **Checkpoints are the 1st of each month.** At a checkpoint the only thing computed is
  the **count** of eligible rows. The counting script prints the count and nothing about
  outcomes.
- **Look 1** runs once, at the first checkpoint where the count is **≥ 100**.
- **Look 2** runs once, at the first checkpoint where the count is **≥ 300**. Look 2
  supersedes Look 1; the two are never combined or averaged.
- Any fit run before a look's threshold is a **pilot: labelled, with no number quoted**.

### 0.6 What to expect (from the synthetic harness, 2026-09-29)

Planted s = 0.4, one seed, nested cohorts (so these are one observation, not three):

| N | s mean | 94% HDI |
|---|---|---|
| 100 | 0.54 | 0.28 – 0.80 |
| 300 | 0.44 | 0.27 – 0.65 |
| 1200 | 0.47 | 0.36 – 0.59 |

So at Look 1 the **direction** should be readable and the **size** will not be. Real
users likely have a narrower gap spread than the synthetic cohort, which makes real
recovery worse, not better. An "undecided" at Look 1 is a likely and acceptable outcome.

---

## Part 1 — Look 1 (N ≥ 100): decision rules

### 1.1 Premise: does the gap predict the rating?

| Posterior result | Called | Consequence |
|---|---|---|
| P(Δ ≥ 0.05) ≥ 0.95 | **Supported** | Proceed. Look 2 as planned. |
| P(Δ < 0.05) ≥ 0.95 | **Not supported at N** | Stop model-learning work. Do not start per-dimension learning. Review the instrument and the `experienced` item (async with Julie). The Situation Report keeps running on priors, labelled internally as unvalidated. |
| Neither | **Undecided** | No claim. Wait for Look 2. |

### 1.2 Harshness: is Julie's overall level right?

| 94% HDI of s | Called |
|---|---|
| entirely below 1 | **Priors too harsh overall**, by roughly the factor s |
| entirely above 1 | **Priors too soft overall** |
| contains 1 | **Consistent with the priors' overall level** |

Only reported if 1.1 is *Supported*; otherwise it is labelled exploratory.

### 1.3 What Look 1 does NOT change

- **What users see does not change.** Inside a severity tier the Situation Report orders
  dimensions by weighted cost, and multiplying every weight by the same s does not change
  that order. Only the `delta`s could, and at N=100 they are shrunk to near zero by
  design. So production stays on `SOLVERAH_MODEL_WEIGHTS_SOURCE` = `priors` after Look 1
  whatever it finds. Switching production to a fitted run is a separate decision.
- **No absolute P(fit) is quoted to users** (D-15; the "no absolute P(fit) from priors
  alone" rule). The fitted s is the first thing that could ever back such a number for a
  future consumer (offer evaluation, CompanyLens), and only once its HDI is narrow; Look 1
  does not authorize any.
- The `delta`s, industry levels and comp effect are **exploratory** at Look 1.

---

## Part 2 — Look 2 (N ≥ 300): decision rules

1. **Re-run Part 1's rules** on the larger population. These replace Look 1's calls.
2. **Linear vs hinge at 0.15.** Only if a hinge variant (gaps under 0.15 cost nothing)
   has been built **before** Look 2's extract is pulled, with no access to outcome rows.
   Compare by PSIS-LOO: prefer the hinge if `elpd_diff > 2 × se_diff`, otherwise keep
   linear. If no hinge exists by then, this item is skipped, not run late.
3. **Per-dimension deltas.** Any `delta` whose 94% HDI excludes 0 is reported as a
   **candidate re-ordering**, sent to Julie for review. Nothing is changed automatically.

Per-dimension weight learning (~1000+ rows) is out of scope and needs its own
pre-registration.

---

## Part 3 — Exploratory, always labelled

Anything not in Parts 1–2, including: industry level effects; comp; `employed` vs
`between_jobs` split; later reports and Pulse repeats of `experienced`; the rating
distribution (a category under 2% of rows makes its cutpoint weakly identified; report
the counts, it does not void the s result); era (`env-v1` vs `env-v2`) comparisons.

---

## Part 4 — Open before Look 1 (does not block adopting this document)

- **Where the real fit runs.** The rows live in production; devfit's guard refuses
  anything but a local `solverah_modeldev*` database, on purpose. Options: a read-only,
  de-identified training-row export to a directory outside the repo, or a one-off job on
  Render. Not decided here. Whatever is chosen must keep per-user magnitudes off every
  payload (D-15) and off the repo.
- **The "first report per respondent" filter** is a small analysis-side step (the
  assembler returns all reports). Build it and test it before Look 1, without outcome
  data.
- **Appendix A** (excluded accounts) filled in.

---

## Appendix A — Excluded accounts

_To be filled before the Look 1 extract. Emails only._

-

---

## Sign-off

- [x] Adopted by Sebastian — date: 2026-10-01 ("that doc looks good")

## Amendments

### Amendment 1 — 2026-10-01: past-job reports

Adopted by Sebastian 2026-10-01, written before any past-job row exists and before
Look 1.

From migration `20261002_envreport_subject`, a respondent may also file ONE report about
a previous job (`environment_reports.subject = 'past'`); every earlier row is
`'current'`. A past-job report requires an existing current report.

- §0.2's "first eligible report per respondent" means the first eligible report with
  `subject = 'current'`, using the assembler at the amending commit.
- Past-job reports are **never** in the primary population and **never** counted toward
  the §0.5 thresholds. A respondent with only past-job reports contributes no primary row.
- They are exploratory under Part 3 at Look 1 and Look 2, labelled "past-job".

**Why.** A past-job rating is recalled rather than current, describes a job the respondent
has already left, and pairs a person side measured now with a job that has ended. That is
a different population answering the same item.
