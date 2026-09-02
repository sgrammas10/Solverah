# Production Readiness Audit — 2026-09-02

**What this is:** `docs/ARCHITECTURE.md` Part 7 (§7.1–7.5) audited claim by claim
against what exists in the repo at commit `c4d6041` (branch
`causal_bayesian_model`). Verdicts are EXISTS / PARTIAL / MISSING with
file:line evidence. Read-only audit; nothing was fixed.

**How to read Part 7:** §7.1 opens "Nothing in the system is currently
observable" — the document describes a *target* state, written before Phase 0
landed. This audit measures against the target, because the target is what
"production ready" means here.

**Headline findings, before the detail:**

1. **Nothing in the repo runs the Celery worker or beat in production.** The
   only worker start command anywhere is the local compose file. If Render has
   no worker service, then with `REDIS_URL` set the app boots green, `/readyz`
   says ready, every request 200s — and no email is ever delivered, no
   assessment is ever scored, no resume is ever parsed, and no sweep or purge
   ever runs. Nothing would surface it except unmonitored log lines.
2. **Config validation became fatal at boot this week (`c4d6041`).** A missing
   *or malformed* environment variable in Render's dashboard now stops boot
   instead of logging. The checklist in §7.5 below must be verified against
   the dashboard **before the next deploy**.
3. **A live Redis outage takes the whole API down.** Flask-Limiter is
   configured without `swallow_errors` or a fallback, so with `REDIS_URL` set,
   Redis going down turns every rate-limited request (i.e. every route) into
   a 500. §7.3 promises the opposite.
4. **Production errors are invisible on both tiers.** No Sentry, no metrics,
   no traces, no sourcemaps. "What was the p95 yesterday" and "what errors
   spiked at 3am" are unanswerable today.
5. **Migrations on a Render deploy are defined nowhere in the repo.** No
   render.yaml, no release phase in `Dockerfile.api`, no CI step. Whatever
   runs them lives only in the Render dashboard or in someone's shell history.

---

## 1. Observability (§7.1)

### Structured JSON logs with request IDs — PARTIAL

The best-built piece of Part 7. `solverah/observability/logging.py` is a
complete stdlib-only structured-logging module, wired in `solverah/factory.py:383-388`
(`init_logging`) and `:420` (`install_request_logging`), tested in
`tests/test_observability.py`.

What a request line actually carries (`logging.py:133-153, 244-247, 295-309`):
`ts, level, logger, message, event="http_request", method, path, route,
status, duration_ms, remote_addr, request_id, service, version` — plus
`user_id` only if bound.

- **request_id — EXISTS.** uuid4-hex contextvar; adopts a validated inbound
  `X-Request-Id` (`logging.py:280, 326-330`), echoed on every response
  (`:286-288`), included in RFC 9457 error bodies (`solverah/errors.py:87-89`).
- **PII redaction at the formatter — EXISTS.** `redact()` at
  `logging.py:105-126`; key-substring match on
  password/secret/token/authorization/cookie/api_key/email/phone/resume_text/ssn.
- **`user_id` — mechanism only.** `bind_user()` (`logging.py:333`) has **zero
  call sites** — the auth path never calls it, so production log lines never
  carry a user id.
- **`db_ms`, `db_queries`, cache hit/miss — MISSING.** No such fields exist
  anywhere in `solverah/`.
- **`audit_events.request_id` — MISSING, and the doc is doubly wrong.** The
  table is `audit_log`, not `audit_events`, and it has no `request_id` column
  (`migrations/versions/0002_audit_logs.py:20-36`; no later migration adds
  one; `solverah/services/audit.py` never references it). The logging
  module's own docstring (`logging.py:14-16`) claims the stamping exists; it
  is implemented nowhere. Logs cannot be joined to audit rows today.

### Prometheus metrics + /metrics — MISSING

No `prometheus_client` in any requirements file; no registry, counter, or
histogram anywhere; no `/metrics` route registered. The only trace of the
promise is `_QUIET_PATHS = frozenset({"/healthz", "/readyz", "/metrics"})`
(`logging.py:318`) — access-log suppression for an endpoint that was never
built. None of the six promised metrics/alerts (RED, pool gauge, queue depth,
LLM duration, login failures) exist.

### OpenTelemetry traces — MISSING

Zero OTel code. The only repo hit is `@opentelemetry/api` as vitest's
*optional* peer dependency in `package-lock.json` — not installed, not used.

### Sentry (API + SPA) — MISSING

No error tracker in `requirements*.txt`, `package.json`, backend, or frontend.
The SPA's error boundaries (`src/app/ErrorBoundary.tsx` etc.) render fallback
UI only — no `captureException`, no reporting. No release tagging, no
source-map upload; `vite.config.ts` doesn't even enable `build.sourcemap`, so
a production stack trace is minified and unreadable if anyone ever sees one.

### Log aggregation / retention — MISSING (nothing in repo)

No log-drain, vector/fluentd, or retention config anywhere. Whatever Render
retains by default is the entire log story; that is a dashboard fact, not a
repo fact (see Questions).

**Blunt answer to the driving question:** No one can answer "what was the p95
yesterday" or "what errors spiked at 3am" today. The former would require
metrics that don't exist or log aggregation that isn't configured; the latter
requires an error tracker that isn't installed. The JSON logs contain the raw
material (status, duration_ms, request_id) — nothing collects, stores, or
queries it.

**Grep hazard for future auditors:** `old_LLM/Unfiltered_Data/job_postings.csv`
is scraped job ads full of "Prometheus/Datadog/Sentry" strings. A naive
repo-wide grep makes the stack look present.

---

## 2. Health-check semantics

Handlers in `solverah/api/health.py`, wired in `solverah/factory.py:347-352`.

- **`GET /healthz`** (`health.py:71-80`): returns `{status, release,
  uptime_seconds}`, touches nothing external — deliberate (docstring
  `:13-17`), and correct for a liveness probe.
- **`GET /readyz`** (`health.py:82-100`): runs injected named checks; any
  raise → 503. **The only check injected is the database** — a real
  `SELECT 1` + rollback (`database_check`, `health.py:118-138`).

What readyz does **not** check, despite the helpers existing:

- **Redis:** `redis_check` (`health.py:141-147`, does `client.ping()`) is
  defined and **never registered anywhere**.
- **Outbox depth:** `outbox.unpublished_count()`
  (`solverah/services/outbox.py:316`) carries a docstring saying *"For the
  readiness probe"* — the wiring was never done; its only callers are tests.
- Migrations-at-head, worker/queue liveness: no such checks exist.

**Blunt answer:** a wedged Celery worker or an outbox with 10,000 unsent rows
shows up **nowhere**. `/healthz` says ok, `/readyz` says ready, and no
endpoint, metric, or check in the repo would surface either condition. The
only signals are per-event log lines (`outbox_publish_failed` at
`outbox.py:231`, `task_enqueue_failed` at `solverah/infra/queue.py:281`) that
nothing aggregates or alerts on (see §1).

---

## 3. Deploy pipeline

### How the app deploys — dashboard-only infrastructure (FINDING)

There is **no render.yaml, no Procfile, no deploy workflow**. The repo's own
files admit the gap:

- `gunicorn.conf.py:3-4`: "Render's start command doesn't pass `-c`, so
  gunicorn picks this file up by default" — the repo knows a start command
  exists but does not contain it.
- `infra/docker/Dockerfile.api:74-84`: CMD is gunicorn only (gthread,
  3 workers × 8 threads, graceful-timeout 30, **no `--timeout` flag** — the
  conf's 30 governs). No ENTRYPOINT, no migration step, no release phase.
- `.github/workflows/` contains exactly two workflows. `tests.yml` gates
  push/PR (frontend: type-check, vitest, build, bundle budget, `npm audit`;
  backend: pytest against a digest-pinned `pgvector/pgvector:pg18` service
  container, then `pip-audit`). `zensearch.yml` is a paused scraper. **Neither
  builds an image, deploys, or touches Render.**

Everything that determines what production actually runs — build command,
start command, env vars, service topology (web? worker? cron? Redis?) — lives
only in the Render web console. That is unauditable from this machine and
unreproducible from the repo. This is itself a finding.

### Migrations on deploy — MISSING

Nothing in the repo runs `flask db upgrade` on a deploy. The image has no
migration phase; CI doesn't even run the migrations (it builds schema via
`db.create_all()` — admitted in `tests/test_migrations_chain.py:8-10`);
`make migrate` (`Makefile:122-124`) is a manual developer target. **On a
Render deploy, migrations run only if a human runs them by hand against the
production `DATABASE_URL`, or via a dashboard pre-deploy command the repo
knows nothing about.** ARCHITECTURE.md §7.5's "migrations run as a job before
the new version rolls out" has no implementation.

### ⚠️ CRITICAL INTERACTION: fatal config at boot × Render env vars

`c4d6041` (2026-09-02) changed `Settings.from_env()` failures from
CRITICAL-log-and-continue to **`ConfigError` raised in `create_app()` — boot
stops** (`solverah/factory.py:390-397`, `solverah/config.py:320-321`). The
worker boots through the same factory (`solverah/worker.py:94`), so it is
equally exposed. **The next deploy is the first one where a dashboard env-var
problem prevents the app from starting instead of logging.** And the rule
cuts both ways: a variable that is *set but malformed* (a stray value in
`DB_POOL_SIZE`, `LOG_LEVEL`, `CELERY_TASK_ALWAYS_EAGER`, …) is now as fatal
as a missing required one.

**Checklist to verify against Render's dashboard BEFORE the next deploy.**
"Production" = `APP_ENV`/`FLASK_ENV`/`ENV` ∈ {production, prod}
(`config.py:197-200`). The Docker image bakes `APP_ENV=production`
(`Dockerfile.api:38`); **if Render runs a native Python runtime instead of
this image, `APP_ENV=production` must be set in the dashboard or none of the
prod-only rules fire.**

| Variable | Requirement | Boot fails when |
|---|---|---|
| `DATABASE_URL` | **required** | missing/blank (`config.py:203-205`); prod + sqlite scheme (`:206-207`) |
| `JWT_SECRET_KEY` | **required** | missing (`:209-211`); prod + length <32 (`:212-216`) |
| `APP_ENV` | required in effect | never fatal itself, but gates every prod rule |
| `JWT_COOKIE_SECURE` | optional (prod default `true`) | non-boolean string (`:218`); **prod + explicit `false`** (`:219-220`) |
| `JWT_COOKIE_SAMESITE` | optional (prod default `None`) | not in {Strict, Lax, None} (`:222-226`); `None` while secure=false (`:227-230`) |
| `TRUSTED_PROXY_COUNT` | optional (prod default 1) | non-integer or outside 0–10 (`:232-234`) |
| `CELERY_TASK_ALWAYS_EAGER` | optional | non-boolean string (`:274-277`) |
| `CACHE_DEFAULT_TTL_SECONDS` | optional (300) | non-int or outside 1–86400 (`:288-290`) |
| `LOG_FORMAT` / `LOG_LEVEL` | optional | not json/console; not a logging level (`:292-298`) |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_RECYCLE_SECONDS` / `DB_POOL_TIMEOUT_SECONDS` / `DB_STATEMENT_TIMEOUT_MS` | optional | out of range (`:307-315`) |
| `JWT_ACCESS_TOKEN_MINUTES` | optional | outside 1–1440 (`:316-318`) — note: validated but **unused**; factory hardcodes 1h (`factory.py:250`) |
| `REDIS_URL`, `RATELIMIT_STORAGE_URI`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CORS_ORIGINS`, `RELEASE` | optional | never fatal — prod without Redis is a **warning only** (`:240-246, :278-283`) |
| `OPENAI_API_KEY`, `GROQ_API_KEY`, `ONET_API_KEY`, `RESEND_API_KEY`, `S3_ENDPOINT_URL`, `S3_BUCKET_NAME` | optional | never fatal by design (`:165-172, :348-353`) — absence breaks the feature at request time |

**Variables read at CALL time — boot succeeds, requests fail.** These do not
appear in the fatal check and will not stop a deploy; they 500 (or worse,
silently degrade) on first use:

- **`SOLVERAH_FORM_TOKEN_SECRET`** — not in Settings at all;
  `assessment_store.py:81-86` raises per call, no default by design (D-05).
  Missing in the dashboard → **every assessment route 500s while /healthz
  stays green.** The single most important check after the boot set.
- **`S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY`** — bare `os.environ[...]`
  KeyError at call (`solverah/infra/storage.py:41-44`); **absent from
  Settings entirely**, so the config's `providers.s3` flag can be true while
  credentials are missing. `S3_BUCKET_NAME` similarly KeyError'd at call in
  six service call sites.
- `OPENAI_API_KEY` / `GROQ_API_KEY` (`solverah/infra/llm/__init__.py:58,71`),
  `ONET_API_KEY` (`backend/services/onet_client.py:123`), `RESEND_API_KEY` +
  `EMAIL_FROM` (`solverah/infra/email.py:146-147`, enforced at send).
- Boot-time hazards outside the nice error path:
  `solverah/services/auth_service.py:60-61` does
  `int(os.environ.get("MAX_LOGIN_ATTEMPTS", "5"))` at **import time** — a
  non-integer crashes boot with a bare `ValueError`, bypassing the ConfigError
  report. Also: `_is_production()` in `factory.py:101-107` checks `FLASK_ENV`
  first while Settings checks `APP_ENV` first — setting both to conflicting
  values splits prod behavior between the two systems. Don't set `FLASK_ENV`
  in the dashboard.

---

## 4. The worker in production

### Deployment artifacts — MISSING

The **only** thing in the repo that starts a worker or beat is the local dev
compose file (`infra/docker/compose.yml:181-253` — Celery on all five queues
with embedded `--beat`, which the file itself calls "right for a laptop and
wrong for production"). There is no `Dockerfile.worker` (ARCHITECTURE.md:360
names one in the target layout; it does not exist), no Procfile, no Makefile
target, no workflow. **If Render does not have a separately configured
background-worker service, nothing runs the worker.** Whether it does is a
dashboard fact (see Questions).

### What happens today, by scenario (traced from code)

Eager-mode logic: `celery_eager_default = is_testing or not celery_broker_url`
(`config.py:274`); broker = `CELERY_BROKER_URL` else `REDIS_URL`
(`:253`). `REDIS_URL` is optional in every environment including production —
absence is a warning, never fatal.

**Scenario A — prod, no `REDIS_URL`: everything runs inline in the request.**
- Outbox emails: `publish_soon` (`outbox.py:174-188`) executes inline — the
  request that registers a user / requests a password reset makes the Resend
  HTTP call itself before responding. If that send fails, the row parks with
  `attempts+1` and is **never retried** — retries are the beat sweep's job
  and eager mode has no beat.
- Assessment scoring: `scoring_jobs.py:179` runs the whole O*NET + OpenAI
  pipeline (tens of seconds; routed to the `llm` queue precisely because it's
  slow) inside the request that created the job. The 202-then-poll contract
  becomes a lie. Resume parsing (`resume_jobs.py:109`) same shape.
- All beat-scheduled work (below) never runs.

**Scenario B — prod, `REDIS_URL` set, no worker deployed (the state the
repo's artifacts produce): total, silent non-delivery.** `enqueue`
(`queue.py:262-289`) succeeds, the message sits in Redis forever, and nothing
consumes it. Verification/reset emails never send (outbox rows sit
`published_at IS NULL`); scoring jobs sit `queued` with clients polling an
indefinite spinner; the sweeps that would rescue anything are themselves beat
tasks. App boots green, `/readyz` ready, every request 200s.

**What dies with beat specifically** (`BEAT_SCHEDULE`, `queue.py:115-142`:
outbox-drain 30s, outbox-purge 1h, resume/scoring sweeps 5m, scoring purge
6h): failed sends never retried (the outbox's entire reason to exist —
`queue.py:48-52` says so verbatim); delivered outbox rows holding **email
addresses and one-time codes are never purged** (PII retention,
`outbox.py:296-303`); lost enqueues never re-driven; stalled jobs never
failed; the unbounded anonymous `scoring_jobs` table never trimmed.

### Redis dependents, per subsystem

| Subsystem | `REDIS_URL` unset | Redis down at runtime |
|---|---|---|
| Celery broker (`queue.py:213-221`) | eager/inline (Scenario A) | `enqueue` catches all, logs, returns None; sweep re-delivers **iff worker+beat exist** — fail open |
| Cache (`solverah/infra/cache.py:91-105, 124-153, 172-220`) | disabled, INFO log | genuinely fail-open — every op answers "miss"; 250ms socket timeouts. Caveat: client resolution is memoized once; Redis dead at *first* touch disables the cache for the process lifetime even after Redis recovers |
| Rate limiter (`security.py:52-160`) | `memory://` with warnings — per-worker counters, reset each deploy; makes `GUEST_INSIGHTS_GLOBAL_LIMIT` (the OpenAI spend cap, `security.py:264`) decorative | **fails broken: 500 on every request.** No `swallow_errors`, no `in_memory_fallback` (`security.py:138-160`); Flask-Limiter 4.1.1 re-raises storage errors, `default_limits` cover every route, only healthz/readyz/OPTIONS exempt. §7.3's "fails closed to a conservative in-process limit" is FALSE. Also: no socket timeout on the limiter's storage — a black-holed Redis blocks requests indefinitely |

---

## 5. Resilience (§7.3)

**§7.3's summary sentence — "Every outbound client gets a timeout, a retry
policy, and a breaker" — is one-third true.** Timeouts mostly exist, retries
partially, and **there is not a single circuit breaker anywhere in the
codebase** (grep for breaker/circuit/pybreaker: a comment and a quiz
tiebreaker).

**Framing correction on "who hits the 30s gunicorn timeout first": nobody.**
Under gthread (both `gunicorn.conf.py:48` and the Dockerfile CMD), the 30s
timeout is a process-liveness check, not a per-request killer — measured in
this repo (`gunicorn.conf.py:14-24`: a 46s stream survived). When a
dependency hangs, gunicorn kills nothing; the request blocks until the client
library's own timeout fires, and each hang silently consumes one of 24
threads (3w×8t). **A provider hang browns the API out with no gunicorn
defense tripping.**

### Per-client reality vs the §7.3 table

| Client | Timeout | Retries | Breaker | Context | Reality vs promise |
|---|---|---|---|---|---|
| OpenAI (`solverah/infra/llm/__init__.py:46-61`) | 60s SDK | 2, SDK backoff | none | mostly Celery `llm` queue; **in-request** for quiz insights (`intelligence.py:282-296`, `intake.py:340` — worst case ~3 min in a thread) | failures return **500**, never "cached or degraded" (`insight_service.py:108-110`) — promise false |
| Groq (`:74-85`) | 30s | 1 | none | in-request SSE (named exception A20/A21) | pre-stream failure → 503/422; acceptable |
| O*NET (`backend/services/onet_client.py:27,146-154`) | **10s**, not the promised 3s | 3 attempts **only on HTTP 429**, linear 0.25s, no jitter, none on timeout/5xx | none | Celery `llm` only (fanned on `ThreadPoolExecutor(8)`) | cached-stale exists for **one** endpoint (bright-outlook, `:350-352`); other caches are read-through — a miss during an outage fails the job |
| Resend (`solverah/infra/email.py`) | SDK default 30s (not set by app) | none in SDK; retry = outbox sweep | none | Celery `email` queue only | see outbox below — no backoff |
| R2/boto3 (`solverah/infra/storage.py:31-45`) | **no `botocore.Config` anywhere** → 60s connect/60s read, legacy retry mode (up to 5 attempts) | library default | none | **in-request**: `head_object` intake finalize (`intake_service.py:177`), `get_object` agent context (`agent_service.py:148-151`), delete loop in erasure (`account_service.py:104-116`) | the least-bounded in-request client — worst case minutes in a thread |
| Redis cache | 250ms explicit | none (correct) | n/a | in-request | **fail-open, genuinely — the best-implemented §7.3 promise** |
| Redis limiter | **none set** | n/a | n/a | every request | **fails broken** (see §4 table) |

No timeout-less `requests`/`httpx` calls exist in live code.

### Database

Engine options (`config.py:358-384`, applied `factory.py:238`):
`pool_pre_ping=True` ✓, `pool_size=10`, `max_overflow=5`,
`pool_recycle=1800`, `pool_timeout=10`, server-side
`statement_timeout=15000` ✓ (15s). **No PgBouncer anywhere**, despite §7.3
naming it in the failover row.

Connection math vs Render `max_connections=103`: API (3 workers × pool
10+5) ceiling **45**; worker (compose `--concurrency=2` × 15) ceiling **30**;
total **75 of 103 — fits**. But a rolling deploy overlapping two API
instances is 45+45+30 = **120 > 103** at full pool saturation;
`pool_timeout=10` at least converts exhaustion into a 10s error rather than a
hang. Production worker concurrency is undefined (no render.yaml), so the
worker term is an assumption.

### Email outbox

Real and well-shaped (transactional enqueue, `FOR UPDATE SKIP LOCKED` drain
every 30s via beat, `outbox.py:274-293`), **but §7.3's "retries with
backoff" is false — the cadence is a flat 30s sweep, and `MAX_ATTEMPTS=8`
(`outbox.py:111`) parks a row permanently.** Consequence: **a Resend outage
longer than ~3.5 minutes permanently parks every verification/reset code
enqueued in its first minutes** (1 fast-path attempt + 7 sweeps × 30s).
Parked rows are never retried, never purged, and visible only via the
readiness-probe counter that was never wired in (§2). Manual DB intervention
is the only recovery.

"Honest 202s" ✓ conditionally: job rows commit before enqueue, `enqueue`
swallows broker failures, 5-minute sweeps requeue/fail — honest **iff beat +
workers run**, which nothing in the repo ensures. There is no HPA-on-queue-
depth anywhere; that §7.3 row is aspirational.

---

## 6. Backup / restore reality (§7.5-adjacent, runbook)

**What's real and rehearsed:** `docs/RUNBOOK_DATABASE_ROLLBACK.md` covers
three restore paths; Path A (self-taken `pg_dump` + in-place restore) was
drilled end-to-end **2026-08-27** with row counts and a dropped column
recovered at two DB sizes (restore 1.4s @10MB, 15.0s @424MB); prod dump
measured 16.5s/68KB. `make db-snapshot` (`Makefile:142-149`) dumps with
`-Fc`, verifies with `pg_restore --list`; `db-restore` is `CONFIRM=yes`-gated.

**What runs on a schedule: nothing.** No cron in either workflow
(`zensearch.yml`'s cron was removed 2026-08-20 and was a scraper anyway), no
backup task in `BEAT_SCHEDULE`, no pre-deploy snapshot hook — the snapshot is
a manual checklist step (runbook line 164). `retention_cleanup.py:3` says
"Run periodically (Render cron job, or manually)" — whether a Render cron
exists is a dashboard fact (see Questions).

**Staleness note:** the PITR window (7 days) and `archive_mode=on` were
confirmed on **2026-08-27** — six days ago, one plan change away from wrong.
A real Render PITR has never been triggered; Path C's "tens of minutes" is an
estimate, and it lands on a **new instance with new credentials** — every
service must be repointed (the runbook calls this "the trap").

---

## 7. SLOs (§7.2) — prose only

All five SLOs (99.9% availability, read p99 <400ms, write p99 <800ms, scoring
<30s p95, email <60s p95) and the error-budget freeze rule are unmeasurable
today, as a direct consequence of §1: there are no metrics, no log
aggregation, and no uptime probe. Measuring them would require, at minimum:
an external availability check hitting `/healthz`; latency histograms — either
the promised Prometheus histograms or a pipeline that aggregates the existing
JSON logs' `duration_ms` by route (the raw material is already emitted);
timestamps to compute scoring latency (job rows already carry created/finished
times, so this one is a SQL query away — the only SLO measurable today, ad
hoc); and outbox `created_at → published_at` deltas for email delivery. None
of this is a design problem; it is entirely "finding 1 first."

---

## 8. Security carry-forward and additions (§7.4)

The eight promised additions:

| # | Item | Verdict | Evidence |
|---|---|---|---|
| 1 | Secrets in managed store + JWT key-ID rotation | **MISSING** | no Doppler/SM/vault/kid anywhere; secrets are flat env vars via `load_dotenv` |
| 2 | Refresh-token rotation w/ reuse detection | **MISSING — no refresh token exists at all** | the code says so itself: `solverah/api/v1/auth.py:211-215` ("…which is what Part 5.3's database-backed refresh tokens are for"). Single 1h access JWT; logout cannot revoke |
| 3 | Rate limiting on Redis | **EXISTS in code; prod depends on `REDIS_URL` being set** | `security.py:52-149`; prod fallback to `memory://` is a warning, not fatal (`config.py:237-245`) |
| 4 | Idempotency keys (account creation, submission) | **MISSING** | no `Idempotency-Key` handling anywhere; submissions have partial natural protection via `open_current` semantics (`assessment_repository.py:78`) |
| 5 | Row-level authz in the repository layer | **EXISTS** | repo signatures take `user_id` and scope queries (`profile_repository.py:99-108`, `assessment_repository.py:52,78,145,164`); resume keys rebuilt from caller's own id (`profile_service.py:449-455`) |
| 6 | `public_id` in URLs | **PARTIAL** | UUID `public_id` on users/experiences/resumes/jobs, and job polling uses it (`assessments.py:461`, `me.py:507`); users expose no id (`model.py:68`). **But `/companies/<int:company_id>` is still a sequential integer** (`api/v1/companies.py:46`) |
| 7 | Dependabot/Renovate | **EXISTS** | `.github/dependabot.yml`, weekly grouped npm/pip/actions (12 PRs currently held per triage) |
| 8 | Migration safety gate in CI | **PARTIAL, mostly MISSING** | chain-integrity test exists (`tests/test_migrations_chain.py`); `make migrate-check` exists but **CI never runs it**, CI builds schema via `db.create_all()`; no destructive-DDL scanner, no `# expand-contract:` mechanism |

"Already correct — keep" spot checks all hold: SHA-pinned actions
(`tests.yml:19,24,112,117`), Talisman CSP (`factory.py:275`), explicit
ProxyFix hop count (`factory.py:133,184`), bcrypt (`auth.py:194`), account
lockout (`auth_service.py:205-212`).

---

## 9. Environments and deployment (§7.5)

| Claimed env | Verdict |
|---|---|
| `local` (api, worker, pg+pgvector, redis, mailpit, minio) | **EXISTS, matches the doc** — all six services in `infra/docker/compose.yml` |
| `ci` (ephemeral, Postgres service container) | **EXISTS** — digest-pinned pg18 container, extensions applied, five env vars |
| `preview` (per-PR, auto-torn-down) | **MISSING** — zero traces (all "preview" hits are `vite preview` or the quiz-preview endpoint). Backend CORS also locks Vercel preview URLs out (below) |
| `staging` (production mirror) | **MISSING** — only hits are the ARCHITECTURE.md table itself and noise |
| `production` | Render, defined entirely outside the repo (§3) |

The promised pipeline (lint → … → build image → migration dry-run → staging →
smoke → canary 5% → progressive rollout with SLO-burn rollback): **CI covers
typecheck/tests/audits and nothing after that.** No image build, no migration
dry-run (CI doesn't run migrations at all), no staging, no deployed-env
smoke (Playwright runs against local `vite preview`), no canary, no rollout,
no rollback automation. "CI runs against Postgres, not SQLite" — **done**, the
one fully delivered §7.5 sentence.

---

## 10. Frontend production story (Vercel)

The live frontend is at repo root (`src/`, `vite.config.ts`); `frontend/` is
untracked legacy. `vercel.json` (repo root, tracked):

- **SPA fallback — EXISTS** (`/(.*)` → `/index.html`).
- **Cache headers — MISSING entirely.** Hashed assets
  (`assets/entry-[hash].js` per `vite.config.ts:19`) are not `immutable`;
  `index.html` is not `no-cache`. Vercel's ETag defaults make this
  correct-but-slower, not broken.
- **Security headers — EXIST and solid** (CSP, nosniff, DENY, HSTS 1y). One
  looseness: `connect-src 'self' https:` allows fetch to *any* https host.
- **API base — env-driven with a silent footgun.** `VITE_API_URL`
  (`src/shared/api/api.ts:24-28`), normalized, `/api/v1` appended. **If unset
  at Vercel build time, the prod bundle silently points at
  `http://localhost:5000`** — no build-time guard. The prod value lives only
  in the Vercel dashboard and is documented only in a code comment; no
  `.env.production`, and `.env.example` has zero `VITE_*` entries.
- **No proxy** — browser goes straight to Render, relying on CORS. Backend
  CORS (`factory.py:293-306`) hardcodes origins (localhost,
  `solverah.vercel.app`, `solverah.com`, `www.`, `api.`); the parsed
  `CORS_ORIGINS` config (`config.py:300-302`) is a **dead knob nothing
  consumes**, and **Vercel preview deployments cannot make credentialed API
  calls**.
- **Cross-site cookie auth — coherent as coded, fragile in the wild.** Prod
  defaults are exactly the viable pair (`Secure=true`, `SameSite=None`,
  validated at boot, `config.py:218-230`); CSRF token is body-delivered and
  header-echoed; `credentials:"include"` everywhere. What nothing addresses:
  **third-party-cookie blocking** — Safari ITP blocks `solverah.vercel.app` ↔
  `*.onrender.com` cookies outright and Chrome is restricting them. The
  hardcoded `solverah.com`/`api.solverah.com` origins show the intended fix
  (same-site custom domains); until those are live there is no fallback.
- **Error tracking / sourcemaps — MISSING** (§1); production frontend errors
  are invisible and stack traces are minified.

---

## 11. Capacity note (evidence: docs/LOAD_BASELINE.md, 2026-09-02)

A measured baseline now exists — dev-machine numbers, explicitly **not
capacity** (everything shared one Windows/Docker Desktop host). What it
establishes for this audit: under the production gunicorn geometry (3w×8t)
throughput is ~2.5–3× the dev config (session ~53 RPS, warm dashboard ~220,
matches ~173, submit ~26) with the knee at ~5–10 concurrent users; the
slowest path by an order of magnitude is the surviving **sync** write
`POST /assessments/core/submissions` (~26 RPS ceiling at prod geometry, p50
>1s at 25 VUs) — it saturates first; the matches scan cost is linear in
company count (~2.7× slower per request at 499 companies vs 6); zero
429/4xx/5xx/worker-kills across ~120k requests. These are comparison
baselines for later local runs of the same recipe, not production sizing —
actual production capacity is unmeasured and, per §1, unmeasurable today.

---

## Ranked gaps

1. **No worker/beat in production (repo-side).** Nothing in the repo runs
   Celery on Render; depending on `REDIS_URL`, production is either silently
   not delivering email/scoring/parsing at all, or running multi-provider
   LLM pipelines inline inside web requests. Either state is invisible (gap 4).
2. **Fatal-config × Render dashboard.** Next deploy is the first under
   fail-at-boot; the §3 checklist is unverified, and the call-time set
   (`SOLVERAH_FORM_TOKEN_SECRET`, `S3_ACCESS_KEY_ID`/`SECRET`, bucket, API
   keys) can leave a green-booting app that 500s on core routes.
3. **Rate limiter fails broken.** With `REDIS_URL` set, a Redis outage turns
   every request into a 500 (no `swallow_errors`, no fallback, no socket
   timeout). One config line away from the promised behavior.
4. **Zero error tracking, metrics, or log aggregation** on either tier.
   Every other gap on this list is currently undetectable in production.
5. **Deploy is dashboard-only infrastructure; migrations are manual.** No
   render.yaml, no release phase, no pre-deploy snapshot automation; CI never
   runs the migrations it ships.
6. **Outbox hard-parks in ~4 minutes of Resend outage** (flat 30s cadence,
   MAX_ATTEMPTS=8, no backoff), rows never retried/purged, and the
   readiness-probe counter meant to surface it was never wired into `/readyz`
   (which checks only the DB; the Redis check helper is also dead code).
7. **No refresh tokens, no managed secrets, no idempotency keys** (§7.4
   items 1/2/4 flatly missing; logout cannot revoke a live JWT).
8. **No circuit breakers anywhere;** boto3 unconfigured (60s×legacy-retries
   in-request — the least-bounded client); O*NET timeout 10s not 3s, retries
   on 429 only; under gthread nothing kills a hung request thread, so
   provider hangs brown out the 24-thread pool.
9. **Frontend prod gaps:** no cache headers; `VITE_API_URL` silent-localhost
   footgun; preview deploys CORS-blocked; dead `CORS_ORIGINS` knob;
   third-party-cookie fragility until custom domains ship.
10. **Rolling-deploy connection math can exceed max_connections=103**
    (45+45+30 = 120 worst case; no PgBouncer).
11. **No scheduled or pre-deploy backups;** PITR window last confirmed
    2026-08-27 and never actually exercised.
12. **Preview/staging/canary pipeline exists only in the document;** the
    migration-safety CI gate is mostly missing.
13. **SLOs unmeasurable** (consequence of 4); only scoring latency could be
    computed today, ad hoc, from job-row timestamps.

Observability paper cuts worth one line each: `bind_user()` dead code (no
`user_id` in logs), `audit_log` has no `request_id` column despite the
logging docstring claiming it, `/metrics` pre-suppressed in access logs but
never built, `JWT_ACCESS_TOKEN_MINUTES` validated but unused.

---

## QUESTIONS FOR THE USER

Everything below is unknowable from this machine — it lives in the Render or
Vercel dashboards, or in your head.

**Render service topology (decides gap 1):**
1. Is there a Render **background worker** service running `celery -A ... worker`?
   With `--beat` or a separate beat? If yes: what start command and concurrency?
2. Is there a Render **Redis/Key-Value** instance, and is `REDIS_URL` set on
   the web service (and the worker, if any)? This decides whether production
   is Scenario A (inline) or Scenario B (silent queue black hole) in §4.
3. Is there a Render **cron job** for `retention_cleanup.py` (its docstring
   assumes one may exist)?

**Render web service config (decides gap 2):**
4. Does the web service deploy from `infra/docker/Dockerfile.api` or a native
   Python runtime? If native: what are the exact build and start commands, and
   is `APP_ENV=production` set in the dashboard?
5. Please diff the dashboard env vars against the §3 checklist — specifically
   confirm: `JWT_SECRET_KEY` ≥32 chars, **`SOLVERAH_FORM_TOKEN_SECRET`
   present**, `S3_ENDPOINT_URL`/`S3_ACCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY`/
   `S3_BUCKET_NAME` all present, `OPENAI_API_KEY`/`GROQ_API_KEY`/
   `ONET_API_KEY`/`RESEND_API_KEY`/`EMAIL_FROM` present, no `FLASK_ENV` set,
   and no leftover/typo'd optional vars (each is now fatal if malformed).
6. How do migrations actually run on a deploy today — a dashboard pre-deploy
   command, or someone running `flask db upgrade` by hand? Has every past
   deploy's migration been run?
7. Is auto-deploy on push enabled, and from which branch?

**Render platform facts:**
8. What is the Postgres plan now (PITR window was 7 days on 2026-08-27 —
   still true? `max_connections` still 103?), and does the plan include
   scheduled logical backups independent of PITR?
9. What is Render's log retention on the current plan, and is any log
   stream/drain configured?

**Vercel:**
10. Is `VITE_API_URL` set in Vercel's production environment (and preview,
    if previews should work)? What value?
11. What is the timeline for the custom domains (`solverah.com` /
    `api.solverah.com`)? Until then, has anyone tested login on Safari
    (third-party-cookie blocking against vercel.app ↔ onrender.com)?

**Ground truth:**
12. Has real production traffic exercised registration email, password
    reset, or assessment scoring since Phase 3 shipped the outbox/queue? If
    users exist: do `outbox` rows show `published_at` set, and do
    `scoring_jobs` complete? (A read-only query against the prod DB would
    answer §4's scenario question definitively — I did not have reachable
    credentials to run it.)
13. Which of the missing pieces are consciously deferred vs believed to
    exist? In particular: was a Sentry account/decision ever made, and is
    anyone under the impression the worker is deployed?
