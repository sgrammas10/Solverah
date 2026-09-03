# Render Deployment — topology, render.yaml, and how (whether) to adopt it

**What this is:** the repo-side record of Solverah's Render production
topology, and the decision document for `render.yaml`. Facts come from the
2026-09-02 dashboard intake
([PROD_READINESS_2026-09_ANSWERS.md](audits/PROD_READINESS_2026-09_ANSWERS.md));
env-var facts are presence-only, never values.

## The topology, as confirmed 2026-09-02

| Piece | Fact |
|---|---|
| Web service | Native **Python runtime** (not `infra/docker/Dockerfile.api`) |
| Build command | `pip install -r requirements.txt` |
| Pre-Deploy Command | `flask db upgrade` — runs once per deploy, before instance swap; a failed migration fails the deploy and the old version keeps serving |
| Start command | `gunicorn app:app` — bare, so the repo-root `gunicorn.conf.py` is auto-loaded from the working directory |
| Database | One managed PostgreSQL, measured 18.3 (`uuidv7()` is native and the schema depends on it — never downgrade anything to 16 to make a migration pass) |
| Auto-deploy | On push to `main`; merge *is* deploy, nothing in between |
| Domains | `api.solverah.com` on the Render web service; `solverah.com` is the Vercel frontend (not Render's concern) |
| Not present | No worker, no beat, no Redis, no cron jobs (as of the intake) |

`render.yaml` at the repo root transcribes exactly this, plus two **cron job
services that do not exist yet**: `solverah-outbox-sweep` (`flask outbox
sweep`, every 5 minutes) and `solverah-retention` (`flask retention run`,
daily). Those two commands are a contract with the round building the CLI —
the names are fixed; the cron services themselves still have to be created
(in the dashboard, or via Blueprint adoption below).

## ⚠️ render.yaml governs nothing until a Blueprint adopts it

This is the trap the file's own header repeats: **Render only reads
`render.yaml` through a Blueprint instance.** The production web service and
database were created by hand in the dashboard; no Blueprint exists, so
merging, editing, or deleting `render.yaml` changes zero infrastructure.
Today the file is *reviewed documentation* — nothing more. Do not treat a
merged change to it as deployed.

There are two ways to live with that. **DECIDED 2026-09-03: Path B** — it
matches how production has been operated all along; revisit Path A at the
next restore-to-new-instance per the deciding factor below. Last verified
against dashboard: 2026-09-03.

### Path A — link a Blueprint (render.yaml becomes enforcement)

Create a Blueprint instance in Render pointing at this repo; Render then
provisions and manages the resources the file declares.

- **What you gain:** the file becomes the source of truth. Config drift of
  the kind the audit was built to catch (the 1-worker gunicorn surprise, the
  `S3_Region` casing typo, three inert env vars) becomes visible in review
  instead of discovered in an intake. The two cron jobs get created by the
  same mechanism that documents them.
- **The risks, and they are real:**
  - **A Blueprint only manages resources it creates.** The existing
    dashboard-created web service and database cannot simply be re-parented.
    Adoption in practice means the Blueprint provisions *new* resources —
    including a **new, empty Postgres** — followed by a data migration
    (`make db-snapshot` / restore, runbook applies) and a DNS/domain cutover
    of `api.solverah.com`. That is a migration project with a maintenance
    window, not a checkbox.
  - Every `sync: false` secret must be re-entered at adoption time; a missed
    one now **fails boot** (fatal config) or, worse, boots green and 500s at
    call time (`SOLVERAH_FORM_TOKEN_SECRET`, S3 credentials).
  - `plan`, `region`, and the Python version are **not captured** in the
    YAML (unknown at intake). Adopting as-is gets Render defaults — fill
    them from the dashboard first or the new service is quietly on the wrong
    plan in possibly the wrong region.
  - After adoption, dashboard edits and YAML fight each other; the team must
    actually stop hand-editing settings the Blueprint owns.

### Path B — stay dashboard-managed (render.yaml stays documentation)

Keep the existing services; treat `render.yaml` as the reviewed, versioned
description of what the dashboard should say. Create the two cron jobs by
hand in the dashboard, copying the commands/schedules from the file.

- **What you gain:** zero migration risk, no data move, no domain cutover,
  no re-entry of secrets. The file still kills the worst property of
  dashboard-only infra — that nobody can review it — because changes to
  intended prod config now go through PRs even if application is manual.
- **The risks:**
  - **Nothing enforces agreement.** The file is one forgotten dashboard edit
    away from being wrong, which is precisely the failure mode that made the
    audit necessary. Mitigation is discipline: any dashboard change lands as
    a same-day PR to `render.yaml`, and the file's header keeps a
    "last verified against dashboard" date.
  - The cron jobs' dashboard config (command, schedule, env vars) is
    hand-copied, so it can typo-drift from the contract the code expects.

**Deciding factor, honestly stated:** Path A is the right end state and the
wrong first move while the database migration cost is unpaid; Path B costs
nothing now and rots without discipline. If Path B is chosen, revisit Path A
the next time a restore-to-new-instance is happening anyway (e.g. a PITR
exercise — runbook), since that pays A's largest cost as a side effect.

## What CI now proves about migrations

The Pre-Deploy Command means every deploy's first act is running the
migration chain — so CI must run the same chain, not approximate it. The
pytest job never does: fixtures build schema via `db.create_all()`, and
`tests/test_migrations_chain.py` checks the chain's *structure* (revision-id
length, linkage, single head) without executing a single migration.

The `backend-migrations-postgres` job in
[.github/workflows/tests.yml](../.github/workflows/tests.yml) closes that
gap: same digest-pinned `pgvector/pgvector:pg18` container as the test gate,
same three extensions, then `flask db upgrade` from an **empty** database,
then an assertion that the database's `alembic_version` equals the repo's
declared head. A chain that breaks — a bad revision id, a migration that
fails on real Postgres 18, a fork in the graph — now fails CI instead of
failing the next deploy's pre-deploy step.

Notes for whoever sees it fail:

- The job sets `DATABASE_URL` and `JWT_SECRET_KEY` (the pytest job's test
  value). `JWT_SECRET_KEY` is unconditionally required in every environment
  (`config.py`); the job's first live run failed on it because the local
  verification had inherited the variable invisibly from the developer
  machine. Honest local repro: `FLASK_SKIP_DOTENV=1` and explicitly clear
  `JWT_SECRET_KEY` — a machine that sets it OS-wide can never simulate CI
  by omission alone.
- **Never downgrade the Postgres container to make a migration pass** — prod
  is 18.3 and the schema uses `uuidv7()`. This has been relearned before;
  see the container comment in the workflow.
- `flask db check` (model/migration drift) is deliberately absent: as of
  2026-09-03 it false-positives on the partition child tables
  (`rec_action_2026_*`, `audit_log_*`, `match_recommendation_*` — real in
  the database, invisible to the models) plus composite-FK/index
  representation diffs on the partitioned parents. Making it clean needs
  `include_object` filtering in `migrations/env.py`; until then it would be
  a permanently red gate.
