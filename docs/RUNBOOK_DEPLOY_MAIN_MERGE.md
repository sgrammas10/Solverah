# Runbook: merging `causal_bayesian_model` → `main`

Shipping the scorer-run storage. `origin/main` is **18 commits** behind the
branch; the security rounds, cache headers, refresh-token table and operational
CLI are **already in production**, deployed 2026-09-03 in PR #147.

Pushing `main` **is** deploying, and auto-deploy is **on** — Render (API) and
Vercel (SPA) both build from `main`, with no staging step between the merge and
production. So everything that can be proven beforehand is proven below, and
everything that cannot is listed as a gate you clear by hand first.

**Status as of 2026-09-08: GO. No open blockers.**

Every code gate is green (§1), the Redis blocker is cleared (§2),
`SOLVERAH_FORM_TOKEN_SECRET` is confirmed set (§3b), and the single migration in
this deploy is provably safe against production data (§3c).

**Correct the framing this document opened with.** It began from a local `main`
ref that was stale at `8046e10`. The real `origin/main` is `8abc424`, and that
commit has been **live in production since 2026-09-03** via auto-deploy. So:

- The branch is **18 commits** ahead of `origin/main`, not 31.
- **The security rounds are already deployed.** S1, S2 and S3 all shipped on
  2026-09-03 in PR #147, along with the cache headers, the refresh-token table
  and the operational CLI. Production has been running them for five days.
- The remaining delta is small and almost entirely research material.

Anyone reading this later: verify `origin/main`, never local `main`. Measuring
the deploy against a stale ref overstated it by 13 commits and by five days of
security work, and produced a "nothing is deployed" reading that was false.

---

## 1. What was verified, 2026-09-08

Run at CI parity from the repo root — `SOLVERAH_IGNORE_DOTENV=1`, no `.env`, and
only the five variables the runner sets. `JWT_SECRET_KEY` is set OS-wide on this
machine and was overridden with the CI value rather than inherited.

| Gate | Result |
|---|---|
| Backend suite (pytest · Postgres 18.6) | **1573 passed, 3 skipped, 0 failed** (7m32s) |
| Migration chain, empty → head | **clean**, 24 migrations, single head `20260906_scorer_run` |
| Migration chain, production's real head (`20260903_user_sessions`) → branch head | **clean** — one migration, rehearsed on a DB stamped at prod's actual revision |
| Frontend type-check (`tsc -b`) | pass |
| Frontend tests (Vitest) | **682 passed** in 66 files |
| Production build | pass |
| Bundle budget | pass — entry 95.7 kB / 99 kB, CSS 8.93 kB / 9.5 kB |
| `npm audit --omit=dev --audit-level=high` | 0 vulnerabilities |
| `pip-audit` | no known vulnerabilities |

**The three skips are correct-by-design, not coverage gaps:** one test that is
only meaningful on file-backed SQLite (we run Postgres), and two documented
layering exceptions (`test_layering.py:110`, `:164`). Nothing skipped for a
missing dependency — in particular the backup cron's dump/verify/prune tests
**executed**, because `pg_dump` 18.1 is on this machine's PATH. (An older note
claimed it was not. It is; re-verified 2026-09-08.)

**Parity caveats, stated so they are not oversold.** This machine ran Python
3.13.5 and Node 22.13.1; CI pins Python 3.11 and Node 24. The suite is green on
both sides of that gap today, but a green local run is evidence about this
interpreter, not the runner's. CI is still the authority — let it run on the
merge commit before pushing anything further.

`npm ci` was not run (it would have rebuilt `node_modules` from scratch); the
gates above ran against the installed tree. CI does run it, and a lockfile drift
would surface there.

### The app-code surface of this merge

Measured against `origin/main`, the app-code delta is **five files and ~741
insertions** — far smaller than the 18-commit count suggests, because the rest is
`Solverah_IP/` research material, tests and docs. The several commits titled
"Refactor code structure for improved readability and maintainability" were each
checked and contain **no app code**, only ground-truth packets and collector
prompts.

| File | What it is | On the request path? |
|---|---|---|
| `migrations/versions/20260906_scorer_run.py` | +225 — the one migration | pre-deploy only |
| `company_score_store.py` | +418, new | **no** — nothing under `solverah/` or `app.py` imports it; only `model.py`, a Script, and tests do |
| `model.py` | +99 — adds `ScorerRun` and `DimensionScoreCitation`, modifies `CompanyDimensionScore` | **yes** — this is the ORM module, imported throughout `solverah/` |
| `.gitignore`, `run_decision_test.ps1` | not runtime | no |

So the only change the serving application actually loads is `model.py`'s two new
ORM classes plus the `CompanyDimensionScore` mapping that matches the migration.
That is the whole risk surface, and §3c takes the migration half of it apart.

Only two environment variables are newly read by code on this branch —
`OPENAI_API_KEY` and `SOLVERAH_ALLOW_LIVE_CALLS` — and both are in
`causal_graph/conftest.py`, offline research tooling that is never on a request
path. **The merge introduces no new runtime environment requirement.**

---

## 2. The Redis blocker — CLEARED 2026-09-08

> **Resolved.** `solverah-redis` is provisioned, and `REDIS_URL` +
> `CELERY_TASK_ALWAYS_EAGER` are both set on the web service (named **`Solverah`**
> in the dashboard, not `solverah-api` as this repo's `render.yaml` claims — see
> §6). Its metrics show non-zero connections, which is direct evidence the
> running service is using it rather than inference from config.
>
> That evidence is stronger than it looks: legacy `main` reads both variables
> through the *same* `_read_bool` and the same URI resolution as the branch — the
> only difference is that `memory://` is a warning there rather than fatal. So
> the values are already proven well-formed by a service that is up and serving.
> Production is rate-limiting on Redis today, before the merge.
>
> The rest of this section is retained because it explains *why* two variables
> were needed rather than one, which is not obvious and would otherwise be
> rediscovered the hard way.

### Original analysis — why this gated the deploy

Since S1, `memory://` rate-limit storage is **fatal at boot in production**
([solverah/config.py:371](../solverah/config.py#L371)). This was a deliberate
choice: per-worker limits mean the OTP-guessing throttle resets on every deploy
and the global LLM spend ceilings bound nothing.

This was confirmed empirically rather than read off a comment — running
`Settings.from_env()` against a production environment holding exactly the five
CI variables produces **one** fatal problem, and it is this one. A
drop-one-at-a-time sweep over a known-good production environment shows exactly
three variables are fatal at boot:

| Variable | Fatal if missing in prod? |
|---|---|
| `DATABASE_URL` | **yes** |
| `JWT_SECRET_KEY` | **yes** |
| `REDIS_URL` | **yes** (via the `memory://` rule) |
| `JWT_COOKIE_SECURE` | no — defaults to `true` when `APP_ENV=production` |
| `JWT_COOKIE_SAMESITE` | no — defaults to `None` in production, which is correct for `solverah.com` ↔ `api.solverah.com` |
| `SOLVERAH_FORM_TOKEN_SECRET` | no at boot — **but see §3** |

The two `JWT_COOKIE_*` defaults are right, so their `sync: false` entries in
`render.yaml` are belt-and-braces rather than requirements.

**`render.yaml` declares the `REDIS_URL` key but declares no Redis service
anywhere in the blueprint.** There is currently nothing for it to point at.
`render.yaml` is also doc-only — the Blueprint has not been adopted — so the live
configuration is whatever the dashboard holds, and the dashboard is the thing to
check.

### Setting `REDIS_URL` alone is a trap — it needs a second variable

One variable configures the platform's whole shared state, deliberately:
`celery_broker_url` falls back to `REDIS_URL`, and
`celery_eager_default = is_testing or not celery_broker_url`. So the moment a
broker exists, `CELERY_TASK_ALWAYS_EAGER` defaults to **false** and `.delay()` /
`.apply_async()` stop running inline and start enqueueing for real.

**There is no worker service.** `render.yaml` declares one web service and three
crons; `grep -c "type: worker"` returns 0. Two call sites enqueue real user
work — `parse_resume_job` ([resume_tasks.py:35](../solverah/tasks/resume_tasks.py#L35))
and `run_scoring_job` ([scoring_tasks.py:44](../solverah/tasks/scoring_tasks.py#L44)).
With a broker and no consumer, both sit in `queued` forever and the user gets an
indefinite spinner.

The sweeps written for exactly this failure (`sweep_resume_jobs`,
`sweep_scoring_jobs`) do not rescue it: they are themselves Celery tasks on the
maintenance queue, and `solverah/cli.py` exposes only `outbox`, `retention` and
`backups` — there is no `flask` command that drains them. No worker means no
sweep either.

Verified by running `Settings.from_env()` against all three candidates:

| Production env | Boots? | Rate-limit storage | Tasks run inline? |
|---|---|---|---|
| A. no `REDIS_URL` (today, on new code) | **FATAL** | — | — |
| B. `REDIS_URL` only | yes | redis | **false** — jobs never execute |
| C. `REDIS_URL` + `CELERY_TASK_ALWAYS_EAGER=true` | yes (1 warning) | redis | **true** — unchanged from today |

**Take option C.** It fixes the boot blocker and makes rate limiting real while
leaving task execution exactly as production behaves today. The warning it emits
("queued work runs inline in the web worker") is accurate and is the current
posture, not a regression. Moving work off the request path is a separate
project — a `type: worker` service plus a beat schedule for the sweeps — and it
should not ride along on a deploy whose purpose is to ship the security rounds.

**To clear this gate:**

1. In the Render dashboard, provision a managed Redis instance (listed as
   **Key Value** in current Render UI) in the same region as `solverah-api`.
2. On `solverah-api`, set **both**:
   - `REDIS_URL` = its **internal** connection string
   - `CELERY_TASK_ALWAYS_EAGER` = `true`
3. Redeploy the *current* `main` and confirm the service still boots. The legacy
   code ignores both variables, so this is a no-op deploy that proves they are
   present and well-formed before either becomes load-bearing.
4. Only then proceed to §4.

Do not merge first and set the variables after. The boot failure is immediate and
total — the API will not come up at all.

While you are in the dashboard, add the Redis instance to `render.yaml` so the
blueprint stops disagreeing with reality.

---

## 3. Verify by hand before merging — things unreachable from this machine

### 3a. Production's alembic head

The `DATABASE_URL` in the local `.env` uses Render's **internal** hostname
(`dpg-…-a`), which does not resolve outside Render's network — so production's
migration state could not be read from here, and an earlier note claiming
"prod alembic is at branch head" could not be confirmed or refuted.

It matters, because `preDeployCommand: flask db upgrade` runs on every deploy.
Expected state, if production is running `main`, is `20260901_scoring_jobs` —
`main` carries no migration after it. The branch adds exactly two:
`20260903_user_sessions` and `20260906_scorer_run`.

From a Render shell on `solverah-api`:

```bash
flask db current
```

**ANSWERED 2026-09-08.** The shell returned `20260903_user_sessions (head)`,
and that is exactly right: `origin/main` is `8abc424`, which carries
`20260903_user_sessions.py` and does not carry `20260906_scorer_run.py`. The
`(head)` marker confirms the deployed tree matches `origin/main` precisely.

The momentary alarm this caused is worth recording, because the trap is easy to
fall into again: measured against the *local* `main` ref -- stale at `8046e10` --
`20260903_user_sessions` looks like a branch-only migration that never reached
`main`, which reads as "production is running unmerged code". It is not. Always
resolve `origin/main`.

**What this means for the deploy:** production is at `20260903_user_sessions`, so
`flask db upgrade` applies exactly **one** migration, `20260906_scorer_run`.
Rehearsed on a pg18 database stamped at production's actual revision: clean.

### 3c. The one risky operation, and why it is safe

`20260906_scorer_run` is additive except for one step: it **drops and recreates
the unique constraint** on `company_dimension_score`, a table that holds
production data. A `create_unique_constraint` against existing rows is the one
operation in this deploy that could fail -- and the local rehearsals did not
exercise it, because those databases had no rows in that table.

It cannot fail here, and the reason is structural rather than empirical:

- `NEW_KEY` is `OLD_KEY + ("scorer_run_id",)` -- a strict superset.
- `scorer_run_id` is newly added, nullable, and NULL on every pre-existing row.
- The four `OLD_KEY` columns -- `company_id`, `dimension_key`, `source`, `as_of`
  -- are all `NOT NULL` in the live schema (verified against a migrated
  database).
- The constraint is created `postgresql_nulls_not_distinct=True`, so those NULL
  `scorer_run_id` values compare **equal** to each other.

Therefore, on legacy rows the new constraint reduces to exactly the old one,
which was already enforced -- so no violating pair can exist. The creation is
satisfied by construction.

This is what makes `NULLS NOT DISTINCT` load-bearing rather than stylistic.
Under Postgres' default (`NULLS DISTINCT`), NULL != NULL would make the
five-column key *weaker* than the four-column key it replaces, and duplicate
legacy rows could be inserted afterwards. `_require_nulls_not_distinct()` in the
migration refuses to run where that cannot be expressed, for this reason.

Should it ever fail anyway, it fails during `preDeployCommand` -- the deploy
aborts and the running version keeps serving. That is the safe failure mode.

### 3b. The runtime-fatal variable that boots clean

`SOLVERAH_FORM_TOKEN_SECRET` has **no default, by design** (D-05) and is read at
call time in [assessment_store.py:82](../assessment_store.py#L82). If it is
missing, the service starts perfectly and then every assessment route raises.
Boot is not evidence here. Confirm it is set on `solverah-api` before merging.

### 3c. `VITE_API_URL` on Vercel

It falls back to the local API when unset, so a missing value produces a
production SPA that quietly calls localhost. It is presumably set already — the
current site works — but confirm it survived any project changes.

---

## 4. The merge sequence

Only after §2 and §3 are clear.

```bash
# 1. Confirm the branch is still clean and current
git checkout causal_bayesian_model
git status                       # expect: clean
git fetch origin

# 2. Merge main into the branch first, so any conflict is resolved
#    on the branch rather than on main.
git merge origin/main

# 3. Re-run the gates if step 2 changed anything. If the merge was a
#    fast-forward with no changes, the §1 results still stand.

# 4. Push the branch and let CI run it
git push origin causal_bayesian_model

# 5. Only when CI is green on that commit, open and merge the PR to main.
```

Push `main` only when CI is green on the identical tree. The merge to `main` is
the deploy — there is no further confirmation step after it.

**Watch, in this order:** the Render pre-deploy log for `flask db upgrade`
applying the two migrations; the boot log for a clean start with no `ConfigError`;
then a real login through the browser, because the refresh-token work
(`20260903_user_sessions`) changes the auth path and cookie behaviour is the one
thing no test on either side proves.

---

## 5. Rollback

The migrations in this merge are additive — two new tables — so code rollback and
schema rollback are separable, and you almost certainly only need the first.

- **Code:** redeploy the previous `main` commit from the Render dashboard.
  `scorer_run`, `dimension_score_citation` and `user_sessions` are simply unused
  by the older code.
- **Schema:** see [RUNBOOK_DATABASE_ROLLBACK.md](RUNBOOK_DATABASE_ROLLBACK.md).
  Do not downgrade unless a migration itself is the fault.

Note that rolling the code back does **not** restore `memory://` tolerance —
once `REDIS_URL` is set it simply stays set, which is harmless.

---

## 6. Non-blocking findings, worth fixing but not before this deploy

- **`CORS_ORIGINS` is dead config.** `solverah/config.py` reads it into
  `settings.cors_origins`, and nothing consumes that field — `solverah/factory.py`
  uses a hardcoded `PRODUCTION_CORS_ORIGINS` list. The Vercel-preview CORS
  decision recorded in the prod-readiness notes was never wired up. Either wire
  it or delete the field; today it invites someone to set a variable that does
  nothing.
- **The entry bundle is at 97% of its budget** (95.7 kB of 99 kB). The next
  eager-path import breaks the build. Worth knowing before someone adds a
  dependency and is surprised by a red CI.
- **`Solverah_IP/` is tracked — 213 files, ~6 MB — and that is fine.** Reviewed
  and closed 2026-09-08, Sebastian's call.

  An earlier draft of this runbook called it 32 MB and recommended excluding it.
  Both halves were wrong. The 32 MB is the *on-disk* figure and is dominated by
  `ground_truth/rater_app/node_modules`, which is untracked and never reaches the
  repo or the host; the tracked footprint is ~6 MB of text and documents.

  And `.gitignore` could not have fixed it anyway: all 213 files are already
  tracked, and git ignores only untracked paths. Making it real would take
  `git rm -r --cached Solverah_IP/`, which would (a) remove the ground-truth
  dataset — the scrubbed packets, the anonymization ruleset, `PIPELINE_LOG.md` —
  from version control, losing the history that makes a packet's provenance
  auditable, and (b) break the three scheduled packet-pipeline tasks, which
  commit `to_be_researched.txt`, `to_be_scrubbed.txt`, run archives and log
  entries into that tree.

  6 MB of text on a web server, served by no route, is not worth either cost.
  If it is ever revisited, the correct fix is a **separate repository** with
  history preserved — and it needs the packet pipeline paused first, so it is not
  a pre-merge task.
- **`.env` carries `S3_Region`** where the code reads `S3_REGION`
  ([storage.py:147](../solverah/infra/storage.py#L147)). It falls back to `"auto"`,
  which is what R2 wants anyway, so the typo is harmless — but it is a typo.
- **`Settings.redacted()` is never called by the application.** It builds exactly
  the operator-facing boot summary you want — `ratelimit_storage: redis|memory`,
  `celery_broker`, `celery_eager`, `cache`, plus provider presence — is covered by
  tests in `tests/test_config.py`, and is wired to nothing. Confirming Redis was
  actually in use on 2026-09-08 therefore needed the Render metrics page, because
  the service itself never says. Logging it once at startup in `create_app()`
  would make every future deploy self-evidencing for the cost of one line.
- **The web service is named `Solverah` in the dashboard**, not `solverah-api` as
  `render.yaml` declares. Harmless today, because the file governs nothing — but
  Render matches Blueprint services **by name**, so adopting this file as-is would
  try to *create* a second service rather than adopt the existing one. Reconcile
  the name before any Blueprint adoption; see `docs/RENDER_DEPLOYMENT.md` for the
  two adoption paths.
