# PROD_READINESS_2026-09 — Intake Answers

Answers to the 13 "QUESTIONS FOR THE USER" at the end of
`PROD_READINESS_2026-09.md`, gathered from the Render/Vercel dashboards on
2026-09-02. Env-var answers record **presence and shape only, never values**.

Status legend: ✅ answered · ⏳ pending · ❓ open (couldn't be answered)

---

## Q6 — How do migrations run on deploy? ✅

**Answer (2026-09-02):** Render runs `flask db upgrade` at **every deployment**,
configured in the dashboard (which is exactly why the repo scan saw nothing and
concluded "manual"). The audit's "migrations are manual" claim (ranked gap 5,
§ deploy) is **factually wrong** on this point.

**Remaining sub-question:** WHERE does the command live?
- **Pre-Deploy Command** — runs once per deploy, before instances are swapped;
  a failed migration fails the deploy cleanly and the old version keeps serving.
- **Start Command** (chained before gunicorn) — re-runs on **every instance
  boot**; a multi-instance deploy can race two concurrent `upgrade` runs, and a
  failed migration crash-loops the service instead of failing the deploy.

**Location (answered in Batch 2, Q6-remainder below):** **Pre-Deploy
Command** — the clean failure mode.

**Affects findings:** ranked gap 5; §3 deploy-process section; "CI never runs
the migrations it ships" remains true regardless of the answer.

---

## Batch 1 — Services list / add-ons screen

### Q1 — Background worker service (celery worker / beat)? ✅

**Answer (2026-09-02):** **No.** The Render services list contains exactly two
rows: the web service and a PostgreSQL database. No Background Worker service
exists; nothing runs `celery worker` or beat in production. The user had never
heard of a worker service (relevant to Q13: nobody believes one is deployed —
it was simply never set up).

**Affects findings:** ranked gap 1 (worker absence CONFIRMED); §4 scenario
question; gap 6 (outbox has no publisher in prod).

### Q2 — Redis/Key-Value instance exists? ✅ (REDIS_URL presence checked in Batch 3)

**Answer (2026-09-02):** **No.** No Key Value / Redis row in the services list.
Barring an external Redis provider (checked via `REDIS_URL` in Batch 3), there
is no Redis in production — pointing at §4 **Scenario A (inline/degraded)**,
not Scenario B (silent queue black hole).

**Affects findings:** ranked gaps 1, 3 (no Redis ⇒ limiter's fail-broken path
can't trigger; limiter presumably on in-memory fallback), §4.

### Q3 — Cron job for `retention_cleanup.py`? ✅

**Answer (2026-09-02):** **No.** No Cron Job row in the services list.
Retention cleanup never runs in production.

**Affects findings:** §4 retention discussion; ranked gap 1 (adjacent).

### Q8 — Postgres plan: PITR, max_connections, scheduled backups? ✅ (partial)

**Answer (2026-09-02):** Recovery tab confirms **PITR to any timestamp within
7 days** — same window as 2026-08-27. No separate scheduled logical backups
were observed on the Recovery screen (PITR is the only recovery mechanism
shown). Plan name and `max_connections` not captured — assume 103 (unverified,
unchanged since audit).

**Affects findings:** ranked gap 11 (PITR confirmed; still never exercised;
no scheduled logical backups), gap 10 (max_connections still assumed 103).

### Q9 — Log retention on current plan; any log stream/drain configured? ✅

**Answer (2026-09-02):** Retention is **14 days** on the current plan (30 days
requires a more expensive plan). No log stream/drain configured.

**Affects findings:** ranked gaps 4, 13 (14-day window is the only forensic
record; nothing aggregated).

## Batch 2 — Web service Settings / Deploy screen

### Q4 — Docker or native runtime? Build/start commands? ✅

**Answer (2026-09-02):** **Native Python runtime — NOT Docker.**
`infra/docker/Dockerfile.api` is not used in production at all.
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- (`APP_ENV=production` presence: checked in Batch 3.)

**Implication the audit could not pin down (now resolved):** the start
command passes no flags, so gunicorn auto-loads the repo-root
`gunicorn.conf.py` from the working directory (exactly the case that file's
docstring anticipates). That yields `worker_class=gthread`, `threads=8`,
`timeout=30` — but `workers` is deliberately unset in the conf, so prod runs
**1 worker × 8 threads**, not the Dockerfile's 3×8. Production capacity is
roughly one-third of the audited/load-tested "prod geometry"; the gap-8
brown-out pool is 8 threads, not 24; and the gap-10 connection math shrinks
to 15 per instance.

**Affects findings:** §11 capacity note (divide by ~3); ranked gaps 8, 10;
the Dockerfile (and its timeout work) applies to local/docker only.

### Q6 (remainder) — Migration command location ✅

**Answer (2026-09-02):** **Pre-Deploy Command** field: `flask db upgrade`.
This is the clean failure mode: it runs once per deploy before instance
swap; a failed migration fails the deploy and the old version keeps serving.
No per-boot re-run, no multi-instance upgrade race, no crash-loop mode.

**Affects findings:** ranked gap 5 — the "migrations are manual" half is
WRONG and the failure mode is the good one. Still true from gap 5: no
render.yaml (config lives only in the dashboard), no pre-deploy DB snapshot,
CI never runs migrations.

### Q7 — Auto-deploy on push enabled? From which branch? ✅

**Answer (2026-09-02):** **Yes — auto-deploy on push to `main`.**

**Affects findings:** gap 2 (next merge to main is the first deploy under
fail-at-boot config, with no manual gate); gap 12 (no staging step between
merge and prod).

## Batch 3 — Web service Environment screen (presence/shape only)

### Q5 — Env-var diff vs §3 checklist ✅

**Answer (2026-09-02, from a names-only screenshot of the Environment tab;
values never shared):** Variables present:

`APP_ENV` (= `production`), `CONFIRM_TOKEN_EXP_HOURS`, `DATABASE_URL`,
`EMAIL_FROM`, `FRONTEND_URL`, `GROQ_API_KEY`, `JWT_COOKIE_DOMAIN`,
`JWT_COOKIE_SAMESITE`, `JWT_COOKIE_SECURE`, `JWT_SECRET_KEY` (user: "quite
long" — treated as ≥32 chars), `ONET_API_KEY`, `OPENAI_API_KEY`,
`RESEND_API_KEY`, `S3_ACCESS_KEY_ID`, `S3_BUCKET_NAME`, `S3_ENDPOINT_URL`,
`S3_Region` (sic — mixed case), `S3_SECRET_ACCESS_KEY`,
`SOLVERAH_FORM_TOKEN_SECRET` (below the screenshot's crop; user confirms set,
"quite long").

Checklist verdict:
- **Every §3-checklist variable is present**, including
  `SOLVERAH_FORM_TOKEN_SECRET` and the full S3 quartet. `FLASK_ENV` is
  correctly **absent**.
- **`S3_Region` is a live casing typo**: `infra/storage.py` reads `S3_REGION`
  (env vars are case-sensitive on Linux), so the dashboard value is ignored
  and the region falls back to `"auto"`. Harmless iff the endpoint is an
  R2-style provider where `auto` works; otherwise a latent misconfig.
- **Three dashboard vars are read by no code**: `CONFIRM_TOKEN_EXP_HOURS` and
  `FRONTEND_URL` appear only in `.env.example`/compose, and
  `JWT_COOKIE_DOMAIN` appears nowhere in the backend (flask-jwt-extended
  takes it from `app.config`, which the factory never sets from env). All
  three are inert — whatever behavior they were meant to configure is running
  on code defaults. Notably `JWT_COOKIE_DOMAIN` being inert is *good* right
  now (a domain-scoped cookie against `onrender.com` could break auth), but
  it signals config-vs-code drift.

**Affects findings:** ranked gap 2 (checklist confirmed — the fatal-boot risk
is now low; the call-time-secret risk resolved: form-token secret and S3 creds
present), §3, gap 9 (`FRONTEND_URL`/cookie-domain drift adjacent).

### Q2 (remainder) — Is `REDIS_URL` set on web service? ✅

**Answer (2026-09-02):** **No.** `REDIS_URL` is not in the environment list.
Combined with Batch 1 (no Redis instance), production definitively has **no
Redis at all** → §4 **Scenario A**: Celery-backed work (email publish,
scoring, parsing) has no broker and no worker; the rate limiter runs on its
in-memory per-process fallback.

**Affects findings:** ranked gap 1 (confirmed worst-case-A), gap 3 (MOOT —
the Redis-outage 500 path cannot trigger with no `REDIS_URL`), gap 6 (outbox
has no publisher), §4.

## Batch 4 — Vercel

### Q10 — `VITE_API_URL` in production (and preview) env? ✅ (partial)

**Answer (2026-09-02):** Set in **Vercel** (correct — it's a build-time
frontend var; it does not belong on Render, and is indeed not there), and it
points at **`api.solverah.com`**. Whether it is also scoped to the
**Preview** environment was not confirmed — the audit's "preview deploys
CORS-blocked + silent-localhost" caveat stays open for previews only;
production is not on the silent-localhost footgun.

**Affects findings:** ranked gap 9 (production half resolved; preview half
open).

### Q11 — Custom-domain timeline; Safari login tested? ✅ (partial)

**Answer (2026-09-02):** **`solverah.com` is already live**, and the API runs
behind **`api.solverah.com`** (per Q10, `VITE_API_URL` points there). The
audit assumed custom domains were future work — they are shipped. Frontend
and API therefore share the registrable domain: auth cookies are **same-site**,
exactly the fix the backend's hardcoded CORS origins anticipated. Confirmed
empirically: **login works on iPhone Safari** (the strictest cookie-blocking
browser).

**Affects findings:** ranked gap 9 (third-party-cookie fragility MOOT;
"until custom domains ship" caveats throughout §10 are satisfied).

## Batch 5 — Ground truth

### Q12 — Has real traffic exercised email/scoring? ✅ (empirically; DB query still open)

**Answer (2026-09-02):** **Yes — the user completed email verification on the
live site today (2026-09-02).** With no Redis and no worker (Q1/Q2), the only
way that email can send is §4 **Scenario A**: `publish_soon` executes inline
in the registering request, calling Resend before responding. Production is
therefore confirmed to be the inline-execution scenario, not the silent
queue black hole — deliverability works, at the cost of doing provider I/O
(and, for scoring, the full O*NET + OpenAI pipeline) inside web requests.

**Still open — the read-only DB check** (would show whether any rows ever
parked after a failed inline send, since eager mode never retries):

```sql
BEGIN; SET TRANSACTION READ ONLY;
SELECT count(*) AS total_rows, count(published_at) AS published,
       count(*) FILTER (WHERE published_at IS NULL) AS unpublished,
       min(created_at) AS oldest, max(created_at) AS newest
FROM outbox;
SELECT status, count(*) FROM scoring_jobs GROUP BY status;
ROLLBACK;
```

No prod credentials were shared; run it in the Render Postgres shell whenever
convenient. Any `unpublished > 0` rows are permanently parked (no beat sweep
exists to retry them).

**Affects findings:** ranked gaps 1 (Scenario A confirmed), 6 (outbox retry
path never runs at all — parking is permanent on first failure, not after 8
attempts), §4.

### Q13 — Consciously deferred vs believed-to-exist? ✅

**Answer (2026-09-02):** The user states plainly: **no error tracking and no
workers currently** — both known-absent, not believed-deployed. No Sentry
account or decision exists. Nobody is under the impression a worker runs; the
worker/Redis/cron layer was never set up (the user had not encountered the
Render "Background Worker" concept before this intake). These are de facto
deferrals rather than documented decisions.

**Affects findings:** ranked gaps 1, 4 (both LIVE and now *acknowledged*);
removes the audit's worst fear (a team believing infrastructure exists that
doesn't).

---

## Re-grade of conditional findings

The audit's ranked gaps 1–13 (its headline findings 1–5 map onto gaps
1/2/3/4/5 respectively), graded against the confirmed topology:
**web service (native Python, 1 gthread worker × 8 threads) + Postgres.
Nothing else. No Redis, no worker, no beat, no cron. Scenario A (inline)
confirmed empirically. Migrations run per-deploy via Pre-Deploy Command.
Custom domains live.**

| # | Finding | Grade | Why |
|---|---|---|---|
| 1 | No worker/beat in production | **LIVE** (shape confirmed) | Confirmed: no worker, no Redis → Scenario A. The scary half (silent non-delivery) is disproven — email verification worked today, sent inline. What's actually dead: **everything beat-scheduled** — failed sends never retried (a row parks permanently on its *first* failure in eager mode), delivered outbox rows holding emails + one-time codes **never purged (PII retention)**, stalled scoring/resume jobs never swept, `scoring_jobs` never trimmed. Also inline LLM pipelines run inside web requests on an 8-thread pool. |
| 2 | Fatal-config × Render dashboard | **MOOT** | Full §3 checklist verified present and well-formed: `APP_ENV=production`, `JWT_SECRET_KEY` long, `SOLVERAH_FORM_TOKEN_SECRET` present, S3 quartet + all API keys + `EMAIL_FROM` present, `FLASK_ENV` absent. Residue: `S3_Region` casing typo (ignored; region falls back to `auto` — evidently fine for the current endpoint) and three inert vars (`CONFIRM_TOKEN_EXP_HOURS`, `FRONTEND_URL`, `JWT_COOKIE_DOMAIN`) — drift, not breakage. |
| 3 | Rate limiter fails broken on Redis outage | **MOOT** | No `REDIS_URL` anywhere → the 500-on-outage path cannot trigger. The substitute state from §4's table is LIVE but mild: `memory://` per-process counters, reset each deploy, and the `GUEST_INSIGHTS_GLOBAL_LIMIT` OpenAI spend cap is decorative. With exactly 1 worker process, in-memory counters are at least coherent today. |
| 4 | Zero error tracking / metrics / aggregation | **LIVE** | Confirmed and acknowledged (Q13): no Sentry account or decision, nothing configured. The entire forensic record is Render's 14-day log tail with no drain (Q9). Still the gap that makes every other gap invisible. |
| 5 | Deploy dashboard-only; migrations manual | **DOWNGRADED** (half was wrong) | The "migrations are manual" half is **WRONG**: `flask db upgrade` runs in the **Pre-Deploy Command** on every deploy — the clean failure mode (failed migration fails the deploy; no race; no crash-loop). Still LIVE: no render.yaml (this intake is the only written record of prod config — the 1-worker geometry surprise is exactly the cost), CI never executes migrations, no pre-deploy snapshot, auto-deploy from `main` with no gate (Q7). |
| 6 | Outbox hard-parks in ~4 min of Resend outage | **LIVE, resharpened** | The audited math (flat 30s cadence × MAX_ATTEMPTS=8) assumed a beat sweep that doesn't exist. Reality is *harsher*: inline mode gets **one** attempt — any transient Resend failure parks that verification/reset row **permanently, immediately**. Unpublished-row counter still not wired into `/readyz`. The Q12 read-only query (above) tells you if this has already happened. |
| 7 | No refresh tokens / managed secrets / idempotency keys | **LIVE** | Topology-independent; Q5 confirms secrets are flat dashboard env vars. Logout still cannot revoke a live JWT. |
| 8 | No circuit breakers; unbounded boto3; hangs brown out pool | **LIVE, worse than graded** | Geometry correction: the pool is **8 threads in 1 worker**, not 24 in 3. gthread's timeout=30 kills hung *processes*, not blocked threads (measured, per the conf), so each provider hang eats 1/8 of total capacity — and boto3 (60s×legacy retries) plus inline scoring pipelines now demonstrably run in-request (Scenario A). Brown-out threshold is a third of what the audit assumed. |
| 9 | Frontend prod gaps | **DOWNGRADED** | Third-party-cookie fragility **MOOT**: `solverah.com` + `api.solverah.com` are live, cookies same-site, Safari login verified. `VITE_API_URL` set correctly in prod (silent-localhost footgun moot for prod; preview scoping unconfirmed). Still LIVE, all minor: no cache headers, preview deploys CORS-blocked, dead `CORS_ORIGINS` knob, no sourcemaps. |
| 10 | Rolling-deploy connection math > max_connections | **MOOT** | Real topology: 1 worker × (pool 10 + overflow 5) = **15** per instance; a rolling overlap is 30; no worker service exists. Versus max_connections assumed 103 — enormous headroom. Re-check only if workers are scaled up or a worker service ships. |
| 11 | No scheduled or pre-deploy backups | **LIVE** | PITR 7-day window re-confirmed today (Q8) and is the **only** recovery mechanism — no scheduled logical backups observed, no pre-deploy snapshot, PITR never actually exercised. |
| 12 | Preview/staging/canary pipeline missing | **LIVE** | Confirmed sharper by Q7: auto-deploy on push to `main` — merge *is* deploy, nothing in between. |
| 13 | SLOs unmeasurable | **LIVE** | Direct consequence of gap 4; unchanged. Scoring latency remains the one SLO computable ad hoc from job rows. |

New facts the audit lacked, worth carrying forward:
- **N1:** Prod gunicorn geometry is **1w×8t** (conf auto-loaded, `workers`
  unset). One config line (`workers = 3` in `gunicorn.conf.py`, or flags in
  the Render start command) triples capacity and restores the load-tested
  geometry.
- **N2:** `S3_Region` dashboard typo (app reads `S3_REGION`); three inert
  dashboard vars (`CONFIRM_TOKEN_EXP_HOURS`, `FRONTEND_URL`,
  `JWT_COOKIE_DOMAIN`).
- **N3:** Log retention is 14 days, no drain.
- **N4:** The queue/worker layer is a de facto deferral, not a decision —
  Scenario A is load-bearing and undocumented.

---

## Prioritized fix queue (scoped to confirmed reality)

Each batch is sized for one agent round. Nothing here is started — this is
the queue, pending user go-ahead.

**Batch 1 — dashboard + one-line conf (no behavior risk, biggest lever):**
1. Set `workers = 3` (or start with 2) in `gunicorn.conf.py` — gap 8/N1;
   re-check connection math when done (still fine: 45 < 103).
2. Rename dashboard `S3_Region` → `S3_REGION` (N2); delete or wire the three
   inert vars.
3. Run the Q12 read-only outbox/scoring query; record results here. If
   parked rows exist, list them for manual re-send.

**Batch 2 — make failures visible (gap 4, unlocks everything):**
4. Sentry on API + SPA (create account — decision recorded in Q13 as never
   made): backend SDK, frontend SDK, enable `build.sourcemap` + upload,
   release tagging.
5. Wire `outbox.unpublished_count()` into `/readyz` (finishes what the
   docstring promised — gap 6's only tripwire) and call `bind_user()` in the
   auth path (audit paper-cut).

**Batch 3 — own Scenario A deliberately (gaps 1, 6):**
6. Decide and document: inline execution is the production model for now
   (N4). Then make inline sends survivable — retry-with-backoff around the
   inline Resend call, or a lightweight in-process periodic drain of parked
   rows.
7. Render **Cron Job** for `retention_cleanup.py` and an outbox purge —
   the PII-retention hole (delivered rows holding emails + one-time codes)
   is the least defensible piece of gap 1.

**Batch 4 — deploy reproducibility (gap 5 remainder, gap 12):**
8. Commit a `render.yaml` capturing what the dashboard now provably runs
   (build cmd, start cmd, pre-deploy `flask db upgrade`, env-var *names*),
   so prod config is auditable and the N1 class of surprise can't recur.
9. CI: run `flask db upgrade` against the pg18 service container instead of
   `db.create_all()`; add `make migrate-check` to CI.

**Batch 5 — backup discipline (gap 11):**
10. Pre-deploy `pg_dump` step (runbook already has `make db-snapshot`), and
    schedule a periodic logical backup; exercise PITR once, on a scratch
    restore, and record timings in the runbook.

**Batch 6 — resilience trims (gap 8 residue, gap 9 residue):**
11. `botocore.Config` with sane connect/read timeouts + `retries={'mode':
    'standard', 'max_attempts': 2}` (least-bounded client).
12. `vercel.json` cache headers (immutable hashed assets, no-cache
    index.html); decide preview CORS (wire `CORS_ORIGINS` or delete it).

**Deferred / larger (gap 7, gap 12):** refresh-token rotation,
idempotency keys, managed secrets, staging environment — real projects,
scheduled separately.
