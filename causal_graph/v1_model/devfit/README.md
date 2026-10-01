# devfit -- fitting the match model on a local database

Everything needed to FIT the model already existed. What did not exist was any
**data**, anything that ran assemble -> fit, anywhere to **save** a fit, or any way
to **see** a result -- the Situation Report ships words and an order, never a
number (D-15). This package is those four things, and nothing else.

It is **local only**. PyMC is not a server dependency and must not become one:
fitting is an offline script, and the server only ever reads saved
`weight_posterior` rows through `match_scoring.load_run_weights`.

```
guard.py            the safety catch -- every script calls it before connecting
seed_synthetic.py   N synthetic people, written through the sanctioned stores,
                    with a planted truth
run_fit.py          assemble -> fit_posterior -> one model_run + 20 weight rows
                    (PyMC: SYSTEM PYTHON ONLY)
explain_user.py     the only place the model's numbers are visible
```

---

## The guard

`assert_local_dev_database(url)` raises unless **all three** hold:

* host is `localhost` or `127.0.0.1`
* the database name starts with `solverah_modeldev`
* `APP_ENV` is not `production`

Every script calls it on the URL it will **actually** connect with, before
opening a connection. There is no `--force`, deliberately.

Two things make this more than a formality:

* **The repo's own `.env` carries a Render-internal production `DATABASE_URL`,
  and `app.py` calls `load_dotenv()`.** Always run these scripts with
  `SOLVERAH_IGNORE_DOTENV=1` and an explicit URL. The scripts refuse to run
  without one -- there is no default and no config fallback.
* **`seed_synthetic --reset` deletes rows** and **`explain_user` prints numbers
  D-15 keeps off every payload.**

The guard checks the URL. `seed_synthetic.assert_safe_to_seed` separately checks
the *contents* -- it refuses a database holding a user not marked synthetic, or
one that already holds a cohort. A name is not evidence about rows.

---

## One-time setup

The pipeline database, on the local Postgres 18 at port 5433. `psql` is off PATH
at `C:\Program Files\PostgreSQL\18\bin`. Verify over TCP -- never `docker exec`,
because a native Windows service shadows 5432.

```sh
export PATH="/c/Program Files/PostgreSQL/18/bin:$PATH"; export PGPASSWORD=solverah
psql -h localhost -p 5433 -U solverah -d postgres -c "CREATE DATABASE solverah_modeldev OWNER solverah"
for ext in citext pg_trgm vector; do
  psql -h localhost -p 5433 -U solverah -d solverah_modeldev -c "CREATE EXTENSION IF NOT EXISTS $ext"
done
```

Then migrate it. `FLASK_SKIP_DOTENV=1` is load-bearing: the Flask CLI loads `.env`
**itself**, before the app's own guard can stop it.

```sh
FLASK_SKIP_DOTENV=1 SOLVERAH_IGNORE_DOTENV=1 APP_ENV=testing \
  DATABASE_URL=postgresql://solverah:solverah@localhost:5433/solverah_modeldev \
  JWT_SECRET_KEY=test-jwt-secret-not-a-real-one-32-bytes-min \
  JWT_COOKIE_SECURE=false JWT_COOKIE_SAMESITE=Lax \
  python -m flask db upgrade
```

**Never hand `solverah_modeldev` to pytest.** The test fixtures call `drop_all()`.
The suite has its own databases.

---

## Seeding

```sh
SOLVERAH_IGNORE_DOTENV=1 APP_ENV=testing \
  JWT_SECRET_KEY=test-jwt-secret-not-a-real-one-32-bytes-min \
  JWT_COOKIE_SECURE=false JWT_COOKIE_SAMESITE=Lax \
  python -m causal_graph.v1_model.devfit.seed_synthetic \
    --database-url postgresql://solverah:solverah@localhost:5433/solverah_modeldev \
    --n 1200 --seed 0
```

Rows go in through the same doorways the app uses -- the ORM `User`,
`assessment_store.persist_submission`, `environment_report_store.write_environment_report`,
with environment scores from `work_pulse.situation.score_environment` over the
real item bank. No raw SQL against the sealed person-side profile, and none of
those table names appears anywhere in this package (D-01).

**The planted truth** is the live priors' means with two deviations, written to
`../../../solverah-devfit/last_truth.json` (outside the repo, so it can never be
committed and drift from the run that produced it):

| weight | the expert said | the truth is |
|---|---|---|
| `autonomy_mag` | -0.67 (mildest) | **-3.0** |
| `pace_mag` | -2.52 (costliest) | **-0.5** |

They are nearly swapped, so a fit that recovers them has visibly moved against a
confident prior -- and `explain_user` should reorder those two dimensions for a
user whose autonomy and pace gaps are comparable.

The seeder prints a per-dimension gap histogram and the rating distribution, and
**stops with a non-zero exit** if any rating level holds under 2% of rows: a level
the data barely contains cannot train its own cutpoint.

### Resetting

`--reset` deletes synthetic users' **environment reports** -- the training rows,
and all the assembler reads.

It does **not** delete the users or their core sittings, and that is not an
oversight. Those rows survive even account deletion, de-identified (a decided
reconciliation, `tests/test_account_lifecycle.py`), which is why their foreign
keys are `NO ACTION` rather than `ON DELETE CASCADE` and why there is no doorway
to remove them. Reaching past that from a dev script would mean writing SQL
against tables D-01 seals. Leftover users are harmless -- a user with no report
contributes no training row.

For a genuinely empty database, drop and re-migrate:

```sh
psql -h localhost -p 5433 -U solverah -d postgres -c "DROP DATABASE solverah_modeldev"
# then repeat "One-time setup" above
```

---

## Fitting

**System Python only** (`python` = 3.10.6, pymc 5.25.1). The verification venv has
no PyMC, and nothing should install one.

```sh
SOLVERAH_IGNORE_DOTENV=1 APP_ENV=testing \
  JWT_SECRET_KEY=... JWT_COOKIE_SECURE=false JWT_COOKIE_SAMESITE=Lax \
  python -m causal_graph.v1_model.devfit.run_fit \
    --database-url postgresql://solverah:solverah@localhost:5433/solverah_modeldev \
    --chains 2 --tune 500 --draws 500 --seed 0 --prior-sd-scale 1.0
```

Writes `reports/fit_<run id>.md`: prior vs posterior per weight, the truth column
and the share of the prior->truth distance covered, the cutpoint spacings, row
counts, diagnostics and flags. `reports/` is gitignored -- these describe a
posterior that exists only in one person's local database.

**The diagnostic gate.** `r_hat >= 1.05` or any divergence and the run is **not
saved**; the report is still written and the exit code is non-zero. `current_run()`
serves the newest run, so an unusable posterior would immediately become what the
app reads.

**`--prior-sd-scale`** multiplies every *dimension* weight's prior sd **in memory**
for one run. `priors.yaml` is never edited, and the value used is recorded in the
run's `notes` and in the report. It exists because the expert ticked "confident"
on all twelve dimension weights, so their sd is 0.309 and a few hundred rows
barely move them -- which is what a confident prior *means*, not a bug. The flag
is how you see what the data alone is saying. The intercept, the confounders and
the cutpoint spacings are deliberately left alone.

**`industry` comes back at its prior, always.** The instrument never asks it, so
every row is masked and its five level weights learn nothing. They are exported
unchanged rather than dropped -- the 20-row set is a database interface -- and the
run's `notes` says so.

**The cutpoint spacings are not weight rows.** `unflatten_weights` is strict and
the flat set is pinned at 20, so a 21st row would break every load. Nothing is
lost: the rating-3/4 cutpoint is pinned at 0, which makes `sigmoid(z)` exactly
P(rating >= 4), so serving needs the 20 and nothing else. The spacings go in
`notes` and the report.

---

## Seeing a result

```sh
SOLVERAH_IGNORE_DOTENV=1 APP_ENV=testing JWT_SECRET_KEY=... \
  SOLVERAH_FORM_TOKEN_SECRET=dev-secret-not-a-real-one \
  python -m causal_graph.v1_model.devfit.explain_user \
    --database-url postgresql://solverah:solverah@localhost:5433/solverah_modeldev \
    --email synth-00007@synthetic.solverah.invalid --source run
```

Per dimension: environment score, the sealed person-side score (read through
`assessment_store.dimension_scores_for_submission` on the **pinned** sitting, not
the current-score table -- that one is upserted in place and describes a different
sitting after any retake), gap, bucket, direction, `mag`, `dir`, cost and rank.
Then P(doing well) with its band.

`--source priors` vs `--source run` is the comparison worth making: it shows
whether a fit changed the model's mind. `--run-id N` inspects a *specific* run
rather than the latest -- necessary as soon as you have fitted twice, since
"latest" can only ever show the second.

Pick a user whose autonomy and pace gaps sit in the **same severity bucket** and
are close in size. The bucket is the outer sort key (a green row must never rank
above an amber one, whatever the weights say), so two dimensions in different
tiers cannot trade places no matter what the fit learned.

**Every number this prints is sealed by D-15.** None of it appears on any API
payload. That is why the guard refuses to let this script run anywhere but
`solverah_modeldev`.

---

## Measured, 2026-09-21 (what to expect)

N=1200, seed 0, 2 chains, 500 tune / 500 draws, pure-Python pytensor on system
Python 3.10. **0 rows dropped, 0 divergences on both fits.**

| | prior | posterior | truth | covered | r_hat | wall |
|---|---|---|---|---|---|---|
| **scale 1.0** `autonomy_mag` | -0.674 | **-1.890** | -3.0 | **52%** | 1.0238 | 1043 s |
| **scale 1.0** `pace_mag` | -2.516 | **-1.349** | -0.5 | **58%** | | |
| **scale 3.0** `autonomy_mag` | -0.674 | **-2.614** | -3.0 | **83%** | 1.0172 | 1172 s |
| **scale 3.0** `pace_mag` | -2.516 | **-0.656** | -0.5 | **92%** | | |

Budget **~20 minutes per fit**. The pure-Python pytensor mode is the cost; set
`PYTENSOR_FLAGS=cxx=<path to g++>` if you have a compiler.

---

## `--global-scale` (approved 2026-09-29, default OFF)

One shared scale on the expert's whole gap cost, for the 50-300-row regime where
twelve independent weights cannot move:

    weight_k = s * prior_mean_k + delta_k
    s ~ LogNormal(0, 0.5)        delta_k ~ Normal(0, 0.10)

Dimension weights only; intercept, confounders and cutpoints are unchanged. Every
number's reason is in `../global_scale.py`. Off, the model is bit-identical to
before (pinned by `../test_global_scale_fit.py`). On, the 20 exported rows are
the EFFECTIVE weights and `notes["global_scale"]` holds s's posterior (mean, sd,
94% HDI), the prior and the delta sd. Refuses `--prior-sd-scale` other than 1.0.

Recovery is measured with a planted scale -- every dimension weight = her mean x S,
no swap:

```sh
python -m causal_graph.v1_model.devfit.seed_synthetic --database-url <...modeldev_x> \
  --n 300 --seed 0 --planted-scale 0.4 --truth-out ../solverah-devfit/gscale_truth.json
python -m causal_graph.v1_model.devfit.run_fit --database-url <...modeldev_x> \
  --global-scale --truth ../solverah-devfit/gscale_truth.json
```

Use a separate `solverah_modeldev_<suffix>` database per cohort: the seeder refuses
a database that already holds a cohort. Reports are named `fit_<run id>.md`, so two
databases' first runs overwrite each other's report -- copy it out between fits.

### Measured, 2026-09-29 (planted s = 0.4, seed 0, 2 chains, 500/500)

| N | s mean | s sd | 94% HDI | covers 0.4 | max r_hat | div | wall |
|---|---|---|---|---|---|---|---|
| 100 | 0.535 | 0.147 | [0.280, 0.804] | yes | 1.0185 | 0 | 324 s |
| 300 | 0.440 | 0.105 | [0.269, 0.648] | yes | 1.0111 | 0 | 514 s |
| 1200 | 0.472 | 0.064 | [0.360, 0.593] | yes | 1.0231 | 0 | 1555 s |

Same 100 rows with the switch OFF (her twelve weights at sd 0.309): the dimension
weights cover only **8-15%** of the prior->truth distance (`pace_mag` -2.35 vs a
true -1.01); with it on, **~78%** (`pace_mag` -1.34).

Three things worth knowing before you read your own numbers:

* **The order flips at scale 1.0 already.** The posterior puts `autonomy_mag`
  (-1.89) above `pace_mag` (-1.35) even though the prior had them the other way
  round by a wide margin. 1200 rows is enough to reverse a confident prior's
  ranking, if not to reach the truth.
* **`--prior-sd-scale 3.0` roughly doubles the distance covered** and barely
  moves anything else. That is the flag doing its job -- and the reason a
  widened posterior must never be read as the expert's.
* **The cutpoint spacings come back at ~1.51-1.56** against a true 1.5 on both
  fits, which is the ordinal head checking out independently of the weights.
* **The sixteen non-planted dimension weights stay put**, worst case
  `innovation_dir` about 2.1 sd from its true 0.0 -- unremarkable across twelve
  weights, and both fits share one cohort so it is one observation, not two. A
  different `--seed` settles it.

## Tests

```sh
# main suite (no pymc) -- guard, record_fitted_run, the row path
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 SOLVERAH_IGNORE_DOTENV=1 APP_ENV=testing \
  JWT_SECRET_KEY=test-jwt-secret-not-a-real-one-32-bytes-min \
  JWT_COOKIE_SECURE=false JWT_COOKIE_SAMESITE=Lax \
  DATABASE_URL=postgresql://solverah:solverah@localhost:5433/solverah_g21 \
  "/c/Users/Sebastian Grammas/Desktop/solverah-venv311/Scripts/python" \
  -m pytest tests/test_model_devfit.py -q

# pymc side -- BY PATH, never `pytest causal_graph`
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest \
  causal_graph/v1_model/devfit/test_devfit_fit.py -q
```

The three cohorts share seed 0, so N=100 and N=300 are prefixes of N=1200: one
observation, not three. At 1200 the intercept comes back +0.15 high (1.53 vs
1.39) while s sits +1.1 sd high -- the two trade off along the same "overall
level" direction. What the "0.2 gap on all six" example (person 0.2 below the
role everywhere) becomes: her priors 0.33; s = 0.535 (N=100) 0.57; s = 0.44
(N=300) 0.62; s = 0.472 (N=1200) 0.60; true s = 0.4 gives 0.64.
