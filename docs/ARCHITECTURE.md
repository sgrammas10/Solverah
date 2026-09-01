# Solverah — System Architecture

**Status:** Target architecture v2 · **Owner:** Engineering · **Last revised:** 2026-08-27

This document is the source of truth for how Solverah is built and where it is going.
Part 1 audits what exists today. Parts 2–7 define the target. Part 8 is the migration
path from one to the other.

---

## Part 1 — Audit of the current system

Measured on branch `causal_bayesian_model`, 2026-08-22. Test baseline: **490 passing.**

### 1.1 What exists

| Layer | Reality |
|---|---|
| API | Single `app.py`, **3,922 lines**, 38 route handlers, 1 blueprint (`account_lifecycle`) |
| Models | `model.py`, 538 lines, 17 tables |
| Frontend | 141 files under `src/`, 24,343 lines, 30+ page components |
| Migrations | 15 Alembic revisions |
| Tests | 490 backend (pytest) + Vitest suites, green |
| CI | GitHub Actions: Vitest + pytest + `npm audit` + `pip-audit`, SHA-pinned actions |
| Deploy | Vercel (SPA) + gunicorn on Render (API) + Postgres + Cloudflare R2 |

The security posture is genuinely good for this stage: SHA-pinned CI actions, pinned
Python deps with a documented CVE rationale, CSP via Talisman *and* `vercel.json`,
`ProxyFix` with an explicit trusted-hop count and a spoofing rationale, CSRF on
state-changing methods, account lockout, GDPR export/delete, retention cleanup.
That work is not being thrown away — it carries forward.

### 1.2 Blocking defects for scale

Ranked by what breaks first as traffic grows.

#### P0-1 · `profile_data` is a read-modify-write JSON blob

`users.profile_data` (JSON) is the primary store for profile fields, quiz results,
skills, proficiencies, culture preferences, and parser snapshots. Every write path
does `merged = {**existing, **incoming}` then rewrites the entire column.

Consequences:
- **Lost updates.** Two concurrent requests (profile save + quiz submit) read the same
  blob and the second write silently discards the first. There is no optimistic lock.
- **No indexing.** Nothing inside the blob can be queried, filtered, or joined without
  a full scan.
- **Row bloat / TOAST churn.** Postgres rewrites the whole tuple on every partial edit.
- **Unbounded growth.** No schema means no size ceiling on a hot-path row.

This is the single largest scale blocker in the system.

**Resolved 2026-08-27** (Phase 2a). The blob is decomposed into `profiles`,
`profile_experiences`, `profile_educations`, `skills`, `profile_skills` and
`resumes`, and no service or repository reads `users.profile_data` any more.

Worth separating the two halves of the fix, because only one of them is the
decomposition. Splitting `experience` into rows stops two writers clobbering each
other's *lists*. It does nothing for two writers touching two scalar fields —
those still land in one row, `profiles.extra` for the keys not yet promoted to
columns. What closes that is `profiles.version`: every write is a compare-and-swap
against the version it read, and a writer that loses re-reads and re-applies its
own merge rather than overwriting. `tests/test_profile_concurrency.py` forces the
interleaving deterministically and failed on the code that preceded this.

Still open, and deliberately: `profiles.extra` is a JSON document and the keys in
it are still unindexable. Part 4.3's model is that each promotion out of `extra`
is its own follow-up migration, and what 2a promoted is listed there.

#### P0-2 · Culture matching is an O(all-companies) in-process scan

`app.py:3511` — `GET /api/v1/company-lens/matches` calls `all_companies()`, pulls every
company row into Python, constructs a `CultureValues` object per row, scores it, sorts,
and slices. Per request. No cache, no index, no limit.

At 10 companies it is invisible. At 100k companies × meaningful RPS it saturates both
the database and every worker.

#### P0-3 · Writes on the read path

`GET /api/profile` writes an `AuditLog` row and calls `db.session.commit()` on every
single read (`app.py:2133`). Session restore fires this on every page load. The audit
table becomes the highest-volume table in the system, synchronously, on the hottest
endpoint — and it takes a write lock on a request that should be replica-servable.

`GET /api/company-lens/matches` also commits a profile backfill mid-read (`app.py:3502`).

#### P0-4 · No app factory; module-level side effects

`app.py` builds the Flask app, reads `os.environ["DATABASE_URL"]` (hard `KeyError` at
import if unset), configures CORS/Talisman/JWT, and dynamically `importlib`-loads the
resume parser from a `sys.path` hack — all at import time.

Consequences: no per-test app configuration, no multiple configs, no clean startup
failure, imports that cannot be reasoned about, and a 3,900-line module that cannot be
split without touching everything.

#### P0-5 · Rate limiting is per-worker and resets on deploy

`security.py` defaults to `memory://`. With N gunicorn workers, configured limits are
effectively N× looser and reset on every deploy. The code already warns about this —
the fix (shared Redis backend) has not been made.

#### P0-6 · Synchronous external I/O in request handlers

OpenAI, Groq, O*NET, Resend, and R2 calls all run inline. `gunicorn.conf.py` raises the
timeout to 120s to accommodate this. With sync workers, one slow LLM call occupies a
whole worker for up to two minutes. A provider slowdown becomes a full outage.

There is no job queue anywhere in the system.

#### P0-7 · No health checks, no error handlers, no pool tuning

- No `/healthz` or `/readyz` → no safe rolling deploys, no autohealing.
- Zero `@app.errorhandler` registrations → unhandled exceptions return Werkzeug's
  default HTML 500 to a JSON API client, and error shapes are inconsistent across the
  38 endpoints.
- No `SQLALCHEMY_ENGINE_OPTIONS` → default pool, no `pool_pre_ping`, no PgBouncer.
  Postgres connection limits are hit long before CPU is.

#### P1-8 · Schema issues

- ~~Table is literally named `user` — a reserved word in Postgres, quoted everywhere.~~
  **Done 2026-08-27 (Phase 2c).** The table is `users`; no live code quotes the
  reserved word, and `tests/test_users_table.py` fails if any does again. The
  historical migrations still say `"user"` and are left alone — they describe the
  schema as it was at their revision, and rewriting them to satisfy a grep would
  make each one a lie about the database it ran on.
- 32-bit integer PKs on append-only tables (`audit_log`, `rec_action`,
  `assessment_response`, `match_recommendation`) — these overflow, and they are
  exposed directly in URLs (`/api/companies/<int:company_id>`), so they enumerate.
  Still open. Phase 2c widened `users.id` to `BIGINT` but left every `user_id`
  child column at `INTEGER`; Postgres accepts the mismatched foreign key, so this
  is latent rather than broken, and fixing it belongs with the partitioning work
  below rather than with a rename.
- No partitioning on any append-only table.
- No `updated_at` triggers — `server_default=now()` never updates on UPDATE for several
  tables, so `updated_at` is really a second `created_at`. Fixed for the five tables
  that have the trigger now: `profiles`, `profile_experiences`, `profile_educations`
  and `profile_skills` (Phase 2a) and `users` (Phase 2c). The remaining tables with
  a stale `updated_at` — `user_intake` among them — are untouched.
- `AuditLog` has an FK to `user.id`, which couples the highest-volume table to the
  identity table and blocks moving it to cheaper storage.

#### P1-9 · Test/prod database divergence

`tests/conftest.py` runs SQLite; production is Postgres. JSON operators, constraint
enforcement, transaction isolation, `citext`, partial indexes, and concurrency
semantics all differ. Every one of the 490 passing tests is passing against a database
the product does not use.

**Resolved 2026-08-27** (Phase 2 prerequisite). The suite — 926 tests by then — moved
onto a Postgres service container. Eight failed on the first run, and all eight were the
same defect: child rows inserted against a `user_id` no `user` row had. SQLite's foreign
keys are off by default and are a per-connection pragma, so every foreign key in the
schema had been decoration for the entire life of the test suite. The tests now seed the
parent row, and conftest turns the pragma on so a SQLite run cannot report green on that
class again.

**The SQLite job is retired as of Phase 2a** (2026-08-27). Part 4.3's tables use five
things SQLite cannot express — `DEFAULT uuidv7()`, identity columns, JSONB, `TEXT[]`,
and a GIN trigram index — and the fixtures build the schema with `db.create_all()`, so
the job could not reach a single test. The alternative, making those defaults
application-side for portability, is the one this document already ruled out on a
measurement of the real database (A13), and it would be a permanent change to every
table in Part 4 bought to satisfy a container. `tests/conftest.py` now defaults
`DATABASE_URL` to the compose stack's Postgres.

#### P1-10 · API surface

No versioning, no pagination on any list endpoint, no request/response schema
validation (handlers poke at raw dicts), no OpenAPI spec, no idempotency keys, no
conditional requests, and inconsistent error bodies. `/api/profile` is a GET+POST
god-endpoint that returns the entire user document.

#### P1-11 · Frontend

- `AuthContext` owns auth **and** every data-fetch primitive (`fetchWithAuth`,
  `streamFetch`, `saveProfileData`, …). Any auth state change re-renders the app.
- `fetchWithAuth<T = any>` defaults to `any` — type safety is opt-in.
- No server-state library: every component hand-rolls loading/error/retry. No caching,
  no request dedupe, guaranteed waterfalls.
- **All 30+ pages are statically imported in `App.tsx`** — one bundle, no code
  splitting. Every first-time visitor downloads the entire application.
- `AuthProvider` renders a full-screen spinner until `GET /api/profile` resolves,
  **blocking the public landing page** — the highest-traffic, most LCP-sensitive route
  in the product — on an authenticated API round trip.
- No error boundaries.

#### P2-12 · Operational gaps

No Dockerfile, no compose file, no IaC, no Makefile. No structured logging, no request
IDs, no metrics, no tracing, no error tracking. Repo root carries `_to_delete/`,
`_mutation_tmp/`, `old_LLM/`, `llm_debug.txt`, `scoring_debug.txt`, `recovery_curve.png`,
and eight `.docx` specs.

---

## Part 2 — Target system architecture

### 2.1 Topology

```
                          ┌──────────────────────────────┐
        Users ───────────►│  Cloudflare — DNS/WAF/CDN    │
                          │  bot mgmt, TLS, edge cache   │
                          └───────┬──────────────┬───────┘
                                  │              │
                 solverah.com     │              │  api.solverah.com
                                  ▼              ▼
                    ┌───────────────────┐   ┌──────────────────────┐
                    │ Vercel — SPA      │   │ Load balancer        │
                    │ static, immutable │   │ TLS term, HTTP/2     │
                    └───────────────────┘   └──────────┬───────────┘
                                                       │
                              ┌────────────────────────┴──────────────────────┐
                              ▼                                               ▼
                 ┌──────────────────────────┐                    ┌────────────────────────┐
                 │ api  (stateless)         │                    │ worker (Celery)        │
                 │ gunicorn + gthread       │                    │ queues:                │
                 │ HPA on RPS + p95         │                    │  default · llm · email │
                 │ 3 → 60 replicas          │                    │  scoring · maintenance │
                 └────────────┬─────────────┘                    └───────────┬────────────┘
                              │                                              │
      ┌───────────┬───────────┼───────────────┬──────────────┬───────────────┘
      ▼           ▼           ▼               ▼              ▼
┌───────────┐ ┌────────┐ ┌─────────┐   ┌───────────┐  ┌──────────────────┐
│ PgBouncer │ │ Redis  │ │ R2 / S3 │   │  Broker   │  │ Providers        │
│ txn pool  │ │ cache  │ │ blobs   │   │ SQS/Redis │  │ OpenAI · Groq    │
└─────┬─────┘ │ rate   │ │ resumes │   └───────────┘  │ O*NET · Resend   │
      │       │ locks  │ └─────────┘                  └──────────────────┘
      │       └────────┘
      ▼
┌──────────────────────────────────────────┐
│ Postgres 18 primary                      │
│  · monthly partitions on append-only     │──► read replicas (analytics, heavy reads)
│  · logical replication → warehouse       │
└──────────────────────────────────────────┘
```

The first line of that box used to read `pgvector (culture / skill ANN)`. Struck
2026-08-27 with Phase 2 item 4 — there is no ANN workload here. A16.


### 2.2 Layering inside the API

Strict, one-directional dependencies. A layer may only import downward.

```
  api/v1/*         HTTP only. Parse → validate → call service → serialize.
      │            No business logic, no ORM queries, no external clients.
      ▼
  services/*       Business logic. Owns the transaction boundary. Orchestrates
      │            repositories, queues jobs, emits domain events.
      ▼
  repositories/*   All data access. Returns domain objects or ORM entities.
      │            Every query lives here — nothing else touches `db.session`.
      ▼
  domain/*         Pure functions and value objects: scoring, matching, ranking.
      │            No Flask, no SQLAlchemy, no network. Trivially testable.
      ▼
  infra/*          Adapters: db, cache, object storage, email, LLM, queue.
                   Each behind a Protocol so tests substitute a fake, not a mock.
```

Why it matters here: the culture/path/match scoring already *is* pure and
deterministic — it is just tangled into `app.py`. Extracting it into `domain/` makes
the most valuable IP in the product independently testable and reusable from workers.

### 2.3 Scale plan

| Tier | MAU | What changes |
|---|---|---|
| **T0 — now** | < 10k | Single API service, single Postgres, Redis cache. Everything in this doc's Phases 0–3 is sufficient. |
| **T1** | 100k | Read replicas for `GET` traffic. PgBouncer transaction pooling. Partitioned `audit_events`. CDN cache on public company pages. |
| **T2** | 1M | Precomputed match sets refreshed by workers, served from Redis. (This cell said "pgvector HNSW for matching" until A16 struck it; precomputation is the whole fix, and it is the half that was always doing the work.) Move `audit_events` + `rec_actions` to a columnar store via logical replication. |
| **T3** | 10M | Shard by `user_id` range or extract identity into its own service. Multi-region read paths. Dedicated scoring service. |

The architecture below is designed so T0→T2 requires **no rewrite** — only
configuration, indexes, and replica routing.

### 2.4 Request budget

| Endpoint class | p99 target | Strategy |
|---|---|---|
| Session restore (`GET /me`) | 80 ms | Replica read, no writes, ETag |
| Profile read/write | 150 ms | Indexed columns, no blob rewrite |
| Match list | 200 ms | Redis-cached precomputed set |
| Assessment submit | 300 ms | Sync persist, async scoring |
| LLM-backed (agent, insights) | streamed | SSE first token < 1 s; never blocks a worker |

Anything that cannot meet its budget synchronously returns `202 Accepted` with a job
handle, or streams. No endpoint gets a 120-second timeout.

---

## Part 3 — File structure

### 3.1 Target layout

```
solverah/
├── apps/
│   ├── api/
│   │   ├── solverah/
│   │   │   ├── __init__.py            # create_app() — the only app factory
│   │   │   ├── config.py              # typed settings, validated at boot
│   │   │   ├── extensions.py          # db, migrate, jwt, limiter, cache, celery
│   │   │   ├── errors.py              # Problem Details + handler registry
│   │   │   ├── api/
│   │   │   │   ├── health.py          # /healthz /readyz /metrics  (unversioned)
│   │   │   │   └── v1/
│   │   │   │       ├── __init__.py    # blueprint registry
│   │   │   │       ├── auth.py        · accounts.py    · profiles.py
│   │   │   │       ├── resumes.py     · assessments.py · companies.py
│   │   │   │       ├── matching.py    · intelligence.py
│   │   │   │       ├── intake.py      · agent.py
│   │   │   ├── schemas/               # pydantic v2 request + response models
│   │   │   ├── services/              # business logic, transaction boundaries
│   │   │   ├── repositories/          # every DB query lives here
│   │   │   ├── domain/                # pure scoring / matching / ranking
│   │   │   ├── models/                # SQLAlchemy, one module per aggregate
│   │   │   │   ├── identity.py  profile.py  assessment.py
│   │   │   │   ├── company.py   matching.py platform.py
│   │   │   ├── infra/
│   │   │   │   ├── db.py  cache.py  storage.py  email.py
│   │   │   │   ├── llm/  (openai.py  groq.py  base.py)
│   │   │   │   ├── onet.py  queue.py  outbox.py
│   │   │   ├── workers/               # celery tasks, one module per queue
│   │   │   └── observability/         # logging, metrics, tracing, request_id
│   │   ├── migrations/
│   │   └── tests/
│   │       ├── unit/  integration/  contract/  factories/
│   └── web/
│       ├── src/
│       │   ├── app/                   # router, providers, shell, error boundaries
│       │   ├── features/              # vertical slices — the unit of ownership
│       │   │   ├── auth/  profile/  assessments/  companies/
│       │   │   ├── matching/  intelligence/  intake/  agent/
│       │   │   └── <slice>/ { api.ts · queries.ts · components/ · types.ts · index.ts }
│       │   ├── shared/
│       │   │   ├── api/               # generated client, queryClient, problem-details
│       │   │   ├── ui/                # design system primitives + tokens
│       │   │   ├── hooks/  lib/  config/
│       │   └── styles/
│       └── tests/  { e2e/ · msw/ }
├── packages/
│   └── ml/                            # resume parsing, culture + path scoring
│       ├── resume/  culture/  paths/  manager_match/
├── infra/
│   ├── docker/  { Dockerfile.api · Dockerfile.worker · compose.yml }
│   ├── terraform/                     # database, redis, buckets, DNS, secrets
│   └── k8s/                           # deployments, HPA, PDB, network policy
├── ops/
│   ├── runbooks/  slo/  dashboards/
└── docs/
```

### 3.2 Rules

1. **A feature slice owns its full stack.** `features/assessments/` contains its API
   calls, queries, components, and types. Cross-slice imports go through the slice's
   `index.ts` only — never deep imports.
2. **`packages/ml` has no Flask dependency.** It is importable from the API, from
   workers, and from a notebook. Today's `sys.path` injection and `importlib` loading
   of `resume_parser.py` disappear.
3. **One module per aggregate** in `models/`. The 538-line `model.py` splits along the
   boundaries it already has.
4. **Tests mirror source.** `tests/unit/domain/test_culture_scoring.py` sits opposite
   `solverah/domain/culture_scoring.py`.

### 3.3 Repo hygiene, first commit

Delete or relocate: `_to_delete/`, `_mutation_tmp/`, `old_LLM/`, `dist/`, `instance/`,
`__pycache__/`, `llm_debug.txt`, `scoring_debug.txt`, `recovery_curve.png`,
`send_test.py`, `test_register_password.py` (root-level stray test), the eight `.docx`
specs (move to a docs drive, linked from `docs/`), and the five `scoring_fix_*_prompt.txt`
files (move to `docs/prompts/` or delete).

`.gitignore` gains: `_to_delete/`, `_mutation_tmp/`, `instance/`, `*.docx`, `.venv/`.

---

## Part 4 — Database schema v2

### 4.1 Principles

1. **JSONB is for genuinely schemaless data only.** Anything queried, filtered,
   sorted, or validated becomes a column. `profile_data` is decomposed.
2. **Two keys per table.** `id BIGINT GENERATED ALWAYS AS IDENTITY` internal;
   `public_id UUID` (v7, time-ordered) for URLs and API payloads. Integer IDs never
   leave the database.
3. **Append-only tables are partitioned by month** and carry no foreign keys into hot
   tables, so they can be aged out or relocated independently.
4. **Optimistic locking** (`version INT`) on any row with concurrent writers.
5. **`updated_at` is maintained by trigger**, not by application code.

### 4.2 Identity

```sql
-- 'job-seeker', hyphenated, and not the 'job_seeker' this originally declared.
-- See "As built" below: the hyphen is the value the system already transmits.
CREATE TYPE user_role   AS ENUM ('job-seeker','recruiter','admin');
CREATE TYPE user_status AS ENUM ('pending','active','suspended','deleted');

CREATE TABLE users (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    public_id          UUID        NOT NULL DEFAULT uuidv7(),
    email              CITEXT      NOT NULL,   -- case-insensitive; no LOWER() index needed
    email_normalized   CITEXT      NOT NULL,   -- dot/plus folding for dedupe
    password_hash      TEXT        NOT NULL,
    name               TEXT,
    role               user_role   NOT NULL DEFAULT 'job_seeker',
    status             user_status NOT NULL DEFAULT 'pending',
    email_confirmed_at TIMESTAMPTZ,
    last_login_at      TIMESTAMPTZ,
    failed_login_count SMALLINT    NOT NULL DEFAULT 0,
    locked_until       TIMESTAMPTZ,
    version            INT         NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at         TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_users_public_id ON users (public_id);
CREATE UNIQUE INDEX uq_users_email     ON users (email) WHERE deleted_at IS NULL;
CREATE        INDEX ix_users_status    ON users (status) WHERE deleted_at IS NULL;

-- Token revocation. A bare JWT cannot log a stolen session out.
CREATE TABLE user_sessions (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    public_id    UUID        NOT NULL DEFAULT uuidv7(),
    user_id      BIGINT      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_hash TEXT        NOT NULL,        -- SHA-256 of the refresh token
    user_agent   TEXT,
    ip           INET,
    issued_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ NOT NULL,
    revoked_at   TIMESTAMPTZ
);
CREATE INDEX ix_sessions_user_active ON user_sessions (user_id) WHERE revoked_at IS NULL;

CREATE TABLE user_consents (          -- GDPR / ToS evidence, append-only
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,        -- terms | privacy | age_attestation
    version     TEXT NOT NULL,
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ip          INET
);
```

#### As built · **2026-08-27**

Shipped as `migrations/versions/20260827_users_table.py`. `users` is built; neither
`user_sessions` nor `user_consents` is, and both stay declared-only until there is
a caller. Six things differ from the SQL above.

**`user_role` is hyphenated.** `'job-seeker'`, not `'job_seeker'`. The underscore
is the tidier SQL and it is the wrong value: `job-seeker` is what is stored, what
`GET /me` and `GET /auth/session` transmit, and what `src/App.tsx` gates fifteen
routes on via `allowedRoles={["job-seeker"]}`. An underscored enum would have made
every protected route in the application reject every user. Changing the spelling
is a wire change and lands with the frontend, in the same phase that turns
`public_id` into the identifier on the wire.

**`GENERATED BY DEFAULT AS IDENTITY`, not `ALWAYS`.** 4.1 rule 2 says `ALWAYS`, and
`ALWAYS` rejects an explicit id without `OVERRIDING SYSTEM VALUE`.
`tests/conftest.py::seed_user` supplies one deliberately — several tests assert
behaviour about a *specific* user id, so the id is load-bearing and cannot be
whatever the sequence hands out. `BY DEFAULT` keeps that fixture written in the
ORM and costs nothing in production, where no code path supplies an id. What rule
2 was actually buying — the sequence belonging to the database rather than the
application — is unchanged.

**`email_normalized` is not created.** 4.2 declares it for dedupe with dot/plus
folding. Folding dots is correct for Gmail and wrong for most other providers:
dots are significant at Fastmail, at Proton, and across corporate domains, so a
global fold would refuse `a.b@fastmail.com` as a duplicate of an unrelated
mailbox. Scoping the fold to the domains where it holds is a product rule with a
list to maintain, and that list belongs with the signup flow, not inside a table
rename. `email` becoming `CITEXT` delivers the part of the dedupe this phase can
honestly claim — case — and removes the footgun that made every caller lower-case
by hand.

**`uq_users_email`'s partial predicate is inert, on purpose.** The index is built
exactly as declared, and nothing sets `deleted_at`.
`account_repository.tombstone_user` still frees a deleted account's address the
way it always has, by rewriting it to `deleted-{id}@{tombstone_domain}`, so the
partial index behaves precisely like the full unique constraint it replaced.
Adopting soft-delete for real is a change to the deletion policy — every user
query grows a `deleted_at IS NULL` filter it does not have yet — and it is not
something a schema migration should do as a side effect.

**Four token columns are carried forward.** 4.2 omits `confirmation_token`,
`confirmation_sent_at`, `reset_token` and `reset_sent_at` because its design
assumes a token store alongside `user_sessions`. That store does not exist and
all four columns are live, behind `POST /auth/email/verify` and the password-reset
OTP. Dropping a live column because the target diagram does not draw it is
deleting a feature by omission. They move when the token table lands.

**`last_login_at` exists and is not maintained.** The row that knows a login
happened is `user_sessions`, which this phase does not create. Writing it from the
login handler would put a write on the login path for a column nothing reads.

**What it is not.** A contract change. `GET /me`, `GET /auth/session` and
`GET /me/profile` return the same bytes they returned before, along with
registration, confirmation, login, the profile and skills writes, the dashboard,
the export, and the 401/403/400 failure paths — 25 responses captured before the
change and diffed after it, with only the CSRF token and timestamps masked
(`Scripts/capture_contract.py`, `Scripts/verify_contract.py`,
`docs/contract_baseline.json`). `docs/openapi.json` regenerates byte-identical. No
file under `src/` was touched.

Three shapes moved underneath that and are adapted before anything is serialized:

| Storage | Wire | Where it is adapted |
| --- | --- | --- |
| `email_confirmed_at TIMESTAMPTZ` | `email_confirmed` boolean | `User.email_confirmed`, a hybrid property |
| `role user_role` | `"job-seeker"` string | nothing to adapt — the enum holds the transmitted value |
| `public_id UUID` | absent | nothing reads it |

The boolean is derived on the model rather than in each serializer because the
same question is asked by three callers that are not serializers — the login gate
in `auth_service`, the tombstone in `account_repository`, and the resend guard.
Four independent derivations of one fact is three chances for them to disagree.

**`users.version` is enforced, not decorative.** `__mapper_args__ =
{"version_id_col": version}`, so every UPDATE carries `AND version = <the value
read>` and a writer that lost the race raises `StaleDataError` rather than
reporting a zero-row update as success. `tests/test_users_table.py` proves it with
two sessions.

**A latent defect this phase fixed on the way past.** `locked_until` was
`timestamp without time zone` and `solverah.domain.auth.utcnow()` is
timezone-aware, so `user.locked_until > utcnow()` in the login path compared a
naive datetime against an aware one and raised `TypeError` — meaning the lockout
branch would have failed with a 500 the first time an account was actually locked
out. No test covered a live lockout. The column is `TIMESTAMPTZ` now, as 4.2
declares; `confirmation_sent_at` and `reset_sent_at` were widened with it.

### 4.3 Profile — decomposing `profile_data`

This is the P0-1 fix. Each block below replaces a key inside the JSON blob.

```sql
CREATE TABLE profiles (
    user_id        BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    headline       TEXT,
    summary        TEXT,
    location_state TEXT,
    location_city  TEXT,
    phone          TEXT,
    linkedin_url   TEXT,
    portfolio_url  TEXT,
    career_status  TEXT,
    completeness   SMALLINT NOT NULL DEFAULT 0,    -- 0-100, maintained by the service
    extra          JSONB    NOT NULL DEFAULT '{}', -- open-ended remainder ONLY
    version        INT      NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE profile_experiences (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    public_id    UUID   NOT NULL DEFAULT uuidv7(),
    user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company_name TEXT   NOT NULL,
    title        TEXT   NOT NULL,
    start_date   DATE,
    end_date     DATE,
    is_current   BOOLEAN NOT NULL DEFAULT false,
    description  TEXT,
    source       TEXT   NOT NULL DEFAULT 'user',   -- user | parsed
    ordinal      SMALLINT NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_experiences_user ON profile_experiences (user_id, ordinal);

-- profile_educations: same shape (institution, degree, field, dates, source, ordinal)

CREATE TABLE skills (                  -- canonical dimension table
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug            TEXT NOT NULL UNIQUE,
    label           TEXT NOT NULL,
    onet_element_id TEXT,
    aliases         TEXT[] NOT NULL DEFAULT '{}'
);
CREATE INDEX ix_skills_trgm ON skills USING gin (label gin_trgm_ops);

CREATE TABLE profile_skills (
    user_id     BIGINT   NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skill_id    BIGINT   NOT NULL REFERENCES skills(id),
    proficiency SMALLINT,              -- 1-5, NULL = unrated
    years       NUMERIC(4,1),
    source      TEXT     NOT NULL DEFAULT 'user',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, skill_id)
);
CREATE INDEX ix_profile_skills_skill ON profile_skills (skill_id);   -- reverse lookup

CREATE TABLE resumes (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    public_id      UUID   NOT NULL DEFAULT uuidv7(),
    user_id        BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    object_key     TEXT   NOT NULL,
    mime           TEXT   NOT NULL,
    size_bytes     INT    NOT NULL,
    status         TEXT   NOT NULL DEFAULT 'pending',  -- pending|stored|parsed|failed
    parser_version TEXT,
    parsed_at      TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_resumes_user ON resumes (user_id, created_at DESC);
```

`profiles.extra` exists so the migration lands without data loss — anything not yet
promoted to a column rides there, and each promotion is a follow-up migration.

#### As built · **2026-08-27**

Shipped as `migrations/versions/20260827_decompose_profile_data.py`. Five things
differ from the SQL above, each because the round trip demanded it.

**Three added columns.** `profile_experiences.extra`, `profile_educations.extra`,
and `profile_skills.label`.

The two `extra` columns are the same idea as `profiles.extra`, one level down. The
blob's dates are free text — the parser writes `"endDate": "2019 - 2020"` and the
UI writes `"Present"` — so a `DATE` column fits almost none of them. Without a
per-row remainder the only entries that could become rows would be the ones whose
dates happen to be ISO, and the decomposition would decompose almost nothing.
They also hold the frontend's list `id` and education's `gpa`, neither of which
has a column.

`profile_skills.label` is the raw text *that user* typed. It is not
`skills.label`, which is the canonical spelling: two users can write "Python" and
"python", they resolve to one dimension row, and each must read back their own
capitalisation. Reassembling from the canonical label would hand the second user
the first user's spelling.

**`profile_skills.ordinal`**, nullable. `skills` in the document is an ordered
array and the primary key `(user_id, skill_id)` is a set, so order has to be
stored. NULL means "rated but not listed" — a state `skill_levels` could
represent, so one the rows have to.

**`resumes.mime` is nullable and `size_bytes` defaults to 0.** A blob holding a
`resumeKey` with no `uploadedResume` sub-document has no MIME type to carry over,
and NULL says that where an invented `application/octet-stream` would not.

**`resumes` holds one row per user, not a history.** `retention_cleanup` deletes
object-storage keys no row references, so keeping superseded uploads would stop
them ever being reclaimed — a retention change smuggled in with a storage change.
The index is `(user_id, created_at DESC)` so history is a data change when
`POST /me/resumes` is ready to keep it.

#### What 2a promoted, and what it did not

Promoted to columns or child tables: `summary`, `phone`, `linkedinUrl`,
`career_status`, `experience[]`, `education[]`, `skills[]`, `skill_levels`,
`resumeKey`. Everything else rides in `profiles.extra` — `firstName`, `lastName`,
`email`, `location`, `primaryLocation`, `secondaryLocations`, `certifications`,
`performanceReviews`, `psychometricResults`, `quizResults`, `_quizSummary`,
`quizInsights`, `applications`, `uploadedResume`, `_parsedResumeSnapshot`,
`legal_acceptance`, `path_preferences`, `culture_preferences`,
`focus_type_result`, `manager_match_result`, `skills_proficiency_confirmed`.

`headline`, `location_state`, `location_city` and `portfolio_url` are declared
above and are left NULL. There is no headline and no portfolio URL in the
document at all; `location` and `primaryLocation` are one free-text field that
may hold a state, a city, or "Austin, TX", and splitting it means guessing. A
guess written into a column is indistinguishable from a fact once it is there.
That promotion is gated on the frontend collecting city and state separately.

#### The promotion rule

One rule, and it is what makes `GET /me/profile` byte-identical:

> A key is promoted to a column only when its value fits that column exactly.
> Anything else rides in `extra` verbatim. A NULL column means the key was
> absent; a key in `extra` means it was present with that value.

So `"phone": ""` promotes and returns `""`; `"phone": null` does not promote,
rides in `extra`, and returns `null`; an absent `phone` leaves the column NULL and
the key absent. Three states stay three states, which a nullable column alone
cannot do. Lists apply the rule at list level rather than per entry: if any
`experience` entry is not decomposable, the whole key rides in `extra`, because
half in rows and half in a blob would make the assembled order a coin toss.

`assemble(decompose(d)) == d` for every `d`, including malformed ones — a
migration that quietly repairs bad data has changed data it was not asked to
change. `tests/test_profile_decomposition.py` holds the corpus.

#### Skill normalisation

`skills.slug` is `solverah/domain/skills.py::slugify`: NFKD normalise, drop
combining marks, casefold, substitute symbols, then reduce every remaining run of
non-alphanumerics to `-`.

It collapses **case** (`Python` = `python` = `PYTHON`), **separator and
punctuation** (`Node.js` = `Node JS` = `node-js` = `node_js`), **whitespace runs**
(`  machine   learning ` = `machine-learning`), and **diacritics** (`Café` =
`Cafe`).

The symbol substitution — `++`→`pp`, `#`→`sharp`, leading `.`→`dot` — runs
*before* punctuation is stripped, and that ordering is the whole reason it exists.
Strip first and `C`, `C++` and `C#` all reduce to `c`: three unrelated skills in
one row, and every profile claiming one claims all three. They are generic
character rules, not a list of language names, so `F#` and `.tmux` behave without
anyone having thought about them.

It does **not** collapse near-duplicates by meaning. `JS` and `JavaScript` stay
two rows, as do `React`/`React.js`, `k8s`/`Kubernetes`, `Postgres`/`PostgreSQL`.
Merging those needs a curated dictionary, and inventing one inside a storage
migration would change which skills a profile matches on — a scoring change
wearing a schema change's clothes. `skills.aliases` and the trigram index on
`skills.label` exist so that curation can land later as data.

`skills.label` is first-writer-wins; later spellings that slugify the same way are
appended to `aliases`.

#### Carried over, not dual-written

The migration creates the tables and decomposes every existing `profile_data` in
one pass. There is no dual-write window and no reconciliation loop, because there
is nothing at this scale to reconcile: production is tester accounts and companies
reseed from `docs/company_profiles_in_db.xlsx`. A blob that will not decompose is
carried into `profiles.extra` verbatim rather than skipped — `extra` assembles
back to exactly what it holds, so "did not decompose" costs indexability, never
data.

`users.profile_data` is **not dropped**. Nothing reads or writes it; it stays one
more release so a rollback is a redeploy rather than a restore. The runbook exists
and has been walked, but exercising it costs downtime and this costs a column. The
drop is the next release's migration.

### 4.4 Assessments

Five assessment products (Work Pulse, WP-Lite-Lite, Focus Type, Manager Match, and the
D-17 core assessment) currently have bespoke tables, columns, and endpoints. They unify:

```sql
CREATE TABLE assessment_forms (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind         TEXT NOT NULL,   -- work_pulse|wpll|focus_type|manager_match|core
    version      TEXT NOT NULL,
    definition   JSONB NOT NULL,  -- items, scales, scoring-key reference
    published_at TIMESTAMPTZ,
    UNIQUE (kind, version)
);

CREATE TABLE assessment_submissions (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    public_id    UUID   NOT NULL DEFAULT uuidv7(),
    user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind         TEXT   NOT NULL,
    form_version TEXT   NOT NULL,
    status       TEXT   NOT NULL DEFAULT 'in_progress',  -- in_progress|complete|scored
    result       JSONB,
    narrative    TEXT,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    scored_at    TIMESTAMPTZ
);
CREATE INDEX ix_submissions_user ON assessment_submissions (user_id, kind, completed_at DESC);

CREATE TABLE assessment_responses (      -- PARTITION BY RANGE (answered_at)
    id            BIGINT GENERATED ALWAYS AS IDENTITY,
    submission_id BIGINT NOT NULL,
    item_id       TEXT   NOT NULL,
    choice        TEXT   NOT NULL,
    answered_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, answered_at),
    UNIQUE (submission_id, item_id, answered_at)
) PARTITION BY RANGE (answered_at);

CREATE TABLE person_dimension_scores (
    user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    dimension_key       TEXT   NOT NULL,
    score               REAL   NOT NULL,
    confidence          REAL,
    scoring_key_version TEXT   NOT NULL,
    submission_id       BIGINT NOT NULL,
    scored_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, dimension_key, scoring_key_version)
);
```

#### As built · **2026-08-27**

Phase 2d created the first two tables. Four deltas from the SQL above, each of them
a decision rather than an oversight.

**`assessment_submissions.answers JSONB`, which is not declared here.** The four
client-rendered instruments need their raw answers kept — the Work Pulse narrative
prompt reads the claimed WPLL answers, `/me/export` returns both sets, and the
culture-preference backfill re-derives from the Work Pulse answers. This schema's
home for raw answers is `assessment_responses`, which is partitioned and therefore
item 5. Decomposing four instruments' answers into it now would put them behind
D-01's doorway and force every one of those readers through it. The column is the
interim home and goes when item 5 lands.

**`UNIQUE (user_id, kind) WHERE kind <> 'core'`, which is not declared here
either.** The four instruments have one current sitting each and a retake updates
it in place; `core` appends, because its raw responses are append-only so a score
stays re-derivable. That asymmetry was going to exist either way — this makes it a
constraint instead of a convention every reader has to remember, and it is what
makes a concurrent double-submit collide before the LLM call rather than after it.

**A composite foreign key `(kind, form_version) → assessment_forms (kind,
version)`.** Implied by `UNIQUE (kind, version)` existing at all, but worth
stating: without it `form_version` is free text, and the `UNIQUE` constrains a
table nothing joins to. Versions register on first use, so a new item file needs
no deploy step ahead of it.

**Three check constraints**: `kind` and `status` against their declared domains,
and `kind <> 'core' OR (result IS NULL AND answers IS NULL)` — the D-01 boundary
inside the shared table, expressed where it cannot be forgotten.

`assessment_responses` and `person_dimension_score` are **not** as built. The
existing `assessment_response` and `person_dimension_score` are unchanged: no
column added, no type changed, no row rewritten. A sitting joins to its submission
by `submission_id = assessment_submissions.public_id.hex`. Partitioning is item 5.

### 4.5 Companies and the matching fix

This is the P0-2 fix — the full scan disappears.

```sql
CREATE TABLE companies (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    public_id  UUID   NOT NULL DEFAULT uuidv7(),
    name       TEXT   NOT NULL,
    slug       TEXT   NOT NULL,
    domain     TEXT,
    industry   TEXT,
    size_band  TEXT,
    hq_state   TEXT,
    status     TEXT   NOT NULL DEFAULT 'active',
    profile    JSONB  NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_companies_slug ON companies (slug);
CREATE INDEX ix_companies_facets ON companies (industry, size_band, hq_state)
    WHERE status = 'active';
```

**Struck 2026-08-27 — `company_culture_vectors`, `user_culture_vectors`, the HNSW
index, and the top-K cosine query that used them.** They were the schema behind
Phase 2 item 4, and they cannot compute the score this product actually has: the
scorer is per-axis L1 proximity with a Jaccard dimension in it, cosine ranks a
different quantity, and the corpus is too small for an index to be the reason to
do anything. A16 has the measurements. Nothing replaces them here — the
destination is the causal Bayesian model in `match_scoring.py`, which is a
per-pair predictor and has no ANN formulation to index.

What is *not* struck is the `companies` table above it. Its facet index is
ordinary B-tree work and stands on its own.

The `company_dimension_score` / `company_confounder_value` / `model_run` /
`weight_posterior` tables from the causal model carry forward unchanged in shape — only
key types and `updated_at` triggers change.

### 4.6 Matching outcomes — partitioned

```sql
CREATE TABLE match_recommendations (     -- PARTITION BY RANGE (shown_at)
    id             BIGINT GENERATED ALWAYS AS IDENTITY,
    public_id      UUID   NOT NULL DEFAULT uuidv7(),
    user_id        BIGINT NOT NULL,
    company_id     BIGINT NOT NULL,
    model_run_id   BIGINT,
    p_fit          REAL,
    p_fit_low      REAL,
    p_fit_high     REAL,
    rank           SMALLINT,
    is_exploration BOOLEAN NOT NULL DEFAULT false,
    channel        TEXT    NOT NULL DEFAULT 'onsite',
    shown_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, shown_at)
) PARTITION BY RANGE (shown_at);
CREATE INDEX ix_match_user ON match_recommendations (user_id, shown_at DESC);

-- rec_actions, outcome_appeals, outcomes_experienced: same partitioning treatment.
```

**Item 5 partitions the existing tables in place, under their existing names.**
The code today has `match_recommendation`, `rec_action`, `outcome_appeal`,
`outcome_experienced`, and — 4.7 below — `audit_log`, all singular; the plural
forms above are Part 4's target spelling, matching 4.1's two-key rule, and
renaming to reach them is deferred, the same way 2c's `user` → `users` was its
own contract-surface change rather than a side effect of another migration.
Likewise the `public_id UUID` and `BIGINT GENERATED ALWAYS AS IDENTITY` columns
above are Part 4's target shape, not item 5's: item 5 adds the partition key to
each table's primary key and the composite foreign keys that follow from it, on
the `INTEGER` ids and without a `public_id`, exactly as the tables are built
today. See A17 for what item 5 actually does, including the one table this
section lists that it does not touch.

### 4.7 Platform tables

```sql
CREATE TABLE audit_events (              -- PARTITION BY RANGE (created_at)
    id            BIGINT GENERATED ALWAYS AS IDENTITY,
    actor_user_id BIGINT,                -- deliberately NOT a foreign key
    action        TEXT   NOT NULL,
    resource      TEXT   NOT NULL,
    ip            INET,
    user_agent    TEXT,
    request_id    TEXT,                  -- joins to application logs
    metadata      JSONB  NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);
CREATE INDEX ix_audit_actor ON audit_events (actor_user_id, created_at DESC);

-- Transactional outbox: domain events and emails commit with the business write and
-- are published by a worker. Removes "the email send failed so the request 500'd".
CREATE TABLE outbox (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic        TEXT   NOT NULL,
    payload      JSONB  NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ,
    attempts     SMALLINT NOT NULL DEFAULT 0
);
CREATE INDEX ix_outbox_unpublished ON outbox (created_at) WHERE published_at IS NULL;

CREATE TABLE idempotency_keys (
    key             TEXT PRIMARY KEY,
    user_id         BIGINT,
    endpoint        TEXT NOT NULL,
    request_hash    TEXT NOT NULL,
    response_status SMALLINT,
    response_body   JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL
);
```

**Audit writes move off the read path.** `GET` handlers no longer commit. Audit events
append to the outbox inside a transaction that already exists, or are emitted to a
Redis stream and drained by a worker — never a synchronous commit on a read.

### 4.8 Retention

| Table | Retention | Mechanism |
|---|---|---|
| `audit_events` | 13 months | Drop partition |
| `assessment_responses` | 24 months | Drop partition (scores are kept) |
| `match_recommendations`, `rec_actions` | 13 months hot | Drop partition after export |
| `user_sessions` | 30 days past expiry | Nightly job |
| `idempotency_keys` | 24 h | Nightly job |
| Deleted users | 30-day grace, then purge | `retention_cleanup.py`, extended |

The `audit_events` row above is target design — whole-row expiry via partition
drop, once the table has been renamed and the retention job rebuilt to use it.
What runs today, against `audit_log`, is `retention_cleanup.py`: a nightly
`UPDATE` that nulls `ip_address` and `user_agent` once a row is older than
`AUDIT_PII_DAYS` (365 days), leaving the row — `action`, `resource`,
`event_metadata`, `created_at` — in place. That is a narrower policy, PII
fields rather than the whole event, and partitioning does not replace it:
dropping a partition would delete rows this job is deliberately keeping past
their PII expiry. Partition drop is the mechanism for whole-row expiry; item 5
does not change what `retention_cleanup.py` does to `audit_log` today.

---

## Part 5 — API design v2

### 5.1 Conventions

| Concern | Rule |
|---|---|
| Versioning | `/api/v1/...` in the path. v1 is frozen once public; breaking changes go to v2. |
| Naming | Plural resource nouns. `/me` is the alias for the authenticated principal. |
| Errors | RFC 9457 Problem Details, `application/problem+json`. One shape everywhere. |
| Pagination | Opaque cursor: `?cursor=&limit=` → `{ "data": [...], "next_cursor": "..." }`. Never offset. |
| Idempotency | `Idempotency-Key` header honoured on every non-GET that creates a resource. |
| Caching | `ETag` + `If-None-Match` on `GET`. `Cache-Control: private, max-age=0, must-revalidate`. |
| Long work | `202 Accepted` + `{ "job_id": ... }` + `Location`, or SSE. Never a 120 s request. |
| Correlation | `X-Request-Id` echoed on every response and stamped into logs and audit rows. |
| Contract | OpenAPI 3.1 generated from pydantic models; the TS client is generated from it. |

**Error body:**

```json
{
  "type":     "https://solverah.com/errors/validation",
  "title":    "Validation failed",
  "status":   422,
  "detail":   "linkedin_url must be an HTTPS linkedin.com URL",
  "instance": "/api/v1/me/profile",
  "request_id": "01JX8T3Q4Y7ZK2M9",
  "errors": [ { "field": "linkedin_url", "code": "invalid_url" } ]
}
```

Internal failures never leak a stack trace or a driver message. The `request_id` is the
only thing a user is given, and it is enough for an engineer to find the trace.

### 5.2 Endpoint map

The 38 pre-Phase-1 handlers, restated as the 40 operations the API now serves.
Phase 1b built this map; the **Replaces** column names what each one took over
from, and rows marked *not built* say what they are waiting on — Part 8's Phase
1b entry has the reasoning per row.

**Platform** (unversioned, not rate-limited, not logged as traffic)

| Method | Path | Notes |
|---|---|---|
| GET | `/healthz` | Liveness. Process is up. No dependency checks. |
| GET | `/readyz` | Readiness. DB + Redis reachable. Gates rolling deploys. |
| GET | `/metrics` | Prometheus. Bound to the internal interface only. |

**Auth** — `/api/v1/auth`

| Method | Path | Replaces |
|---|---|---|
| POST | `/register` | `POST /api/register` |
| POST | `/login` | `POST /api/login` |
| POST | `/logout` | `POST /api/logout` |
| POST | `/refresh` | *not built* — needs `user_sessions` (A7). Phase 2. |
| GET | `/session` | *new* — cheap session probe, replaces `GET /api/profile` for auth restore |
| POST | `/email/verify` | `POST /api/confirm-email` |
| POST | `/email/verify/resend` | `POST /api/resend-confirmation` |
| POST | `/password/forgot` | `POST /api/request-password-reset` |
| POST | `/password/reset` | `POST /api/verify-password-reset` |

`GET /auth/session` is the fix for P0-3: it returns `{ user, csrf_token, flags }` and
**writes nothing**, where `GET /api/profile` returned the whole user document and
committed an `AuditLog` row on every page load. Read replicas and the `ETag` are Phase 5
and Phase 3 respectively; what landed in 1b is the write and the payload coming off the
boot path, which is the part that took a lock.

**Me** — `/api/v1/me`

| Method | Path | Replaces |
|---|---|---|
| GET / PATCH | `/` | identity half of `GET\|POST /api/profile` |
| GET / PATCH | `/profile` | profile half of the same endpoint |
| GET / POST | `/experiences`, `/experiences/{id}` | *not built* — decomposes the blob. Phase 2. |
| GET / POST | `/educations`, `/educations/{id}` | *not built* — decomposes the blob. Phase 2. |
| GET / PUT | `/skills` | `PATCH /api/profile/skills/proficiency` |
| PATCH | `/career-status` | `PATCH /api/profile/career-status` |
| GET | `/dashboard` | `GET /api/dashboard-data` |
| POST | `/resumes` | `POST /api/profile/resume/presign` → an upload ticket. Returns a `resume_id`, never a storage key. |
| POST | `/resumes/{id}/complete` | `POST /api/profile/resume/finalize`. Still 200; **202** when Phase 3 has a queue. |
| GET | `/resumes/{id}/download-url` | `GET /api/profile/resume-url`. `current` is a valid id until Phase 2 gives resumes rows. |
| GET | `/export` | account-lifecycle export |
| DELETE | `/` | account-lifecycle deletion |

Splitting the god-endpoint means the dashboard stops shipping the entire user document
on every page load, and a profile edit stops rewriting unrelated data.

**Assessments** — `/api/v1/assessments`, `/api/v1/me/assessments`

| Method | Path | Replaces |
|---|---|---|
| GET | `/assessments` | *new* — catalogue with per-user completion state |
| GET | `/assessments/{kind}/form` | `GET /api/assessment/form` |
| POST | `/assessments/{kind}/submissions` | `/api/assessment/submit`, `/api/work-pulse/submit`, `/api/work-pulse/lite-lite/result`, `/api/focus-type/submit`, `/api/manager-match/submit` |
| GET | `/assessments/{kind}/submissions/{id}` | *not built* — only the person-side instrument has ids. Phase 2. |
| GET | `/me/assessments/{kind}/result` | `/api/work-pulse/results`, `/api/manager-match/results` |

`{kind}` ∈ `core · work_pulse · wpll · focus_type · manager_match`. Five near-identical
submit handlers collapse into one, with the differences living in `assessment_forms.definition`
and a scoring strategy per kind. Adding assessment #6 becomes a data change.

**Companies** — `/api/v1/companies`

| Method | Path | Replaces |
|---|---|---|
| GET | `/companies?cursor=&limit=&q=&industry=` | *new* — paginated, faceted |
| GET | `/companies/{public_id}` | `GET /api/companies/<int:id>`. Still the integer id, so still enumerable, until Phase 2 adds `public_id`. |

**Matching** — `/api/v1/me/matches`

| Method | Path | Replaces |
|---|---|---|
| GET | `/me/matches?cursor=&limit=&lens=&order=` | `GET /api/company-lens/matches`. Cursor-paginated; `order=best\|worst` carries the two slices over. Not yet index-backed (P0-2). |
| POST | `/me/matches/{id}/actions` | *not built* — needs `rec_actions`. Phase 2. |
| GET | `/me/recommendations` | `GET /api/recommendations` |
| POST | `/me/recommendations/refresh` | `POST /api/recommendations`. Still 200; **202** when Phase 3 has a queue. |

**Intelligence** — `/api/v1/me`

| Method | Path | Replaces |
|---|---|---|
| GET / PUT | `/me/path-preferences` | `POST /api/intelligence/path-preferences` |
| GET | `/me/path-suggestions` | `GET /api/intelligence/path-suggestions` — served from cache. A miss still computes inline; **202** when Phase 3 has a queue. |

**Agent** — `/api/v1/agent`

| Method | Path | Replaces |
|---|---|---|
| POST | `/agent/messages` | `POST /api/agent/chat` — SSE, streamed. Still on the request worker until Phase 3. |

**Intake** (public, aggressively rate-limited) — `/api/v1/intake`

| Method | Path | Replaces |
|---|---|---|
| POST | `/early-access` | `POST /api/early-access-request` |
| POST | `/submissions` | `POST /api/intake/finalize` |
| POST | `/resume-tickets` | `POST /api/intake/presign`. Not under `/submissions/{id}` — the ticket is what mints the id. |
| POST | `/claims` | `/api/intake/create-account`, `/api/intake/sign-in`, `/api/intake/link-account`, `/api/intake/save-to-account`. Not under `/submissions/{id}` — two of the four modes have no submission. |
| POST | `/quiz-preview/insights` | `POST /api/quiz-insights-guest` |

Four near-identical account-attachment endpoints become one `claim` with a `mode`
discriminator, which removes three copies of the same "does this email already exist"
branch.

### 5.3 Auth model

- **Access token**: JWT, 15 min, HttpOnly + `Secure` + `SameSite=None`, CSRF token in
  the body (the current scheme — kept, it is correct).
- **Refresh token**: opaque, 30 days, HttpOnly, hashed in `user_sessions`, **rotated on
  every use** with reuse detection. This is what makes logout, "sign out everywhere",
  and stolen-token revocation actually possible — none of which the current 1-hour
  access-token-only scheme supports.
- **Rate limits**, shared across workers via Redis:

  | Scope | Limit |
  |---|---|
  | `POST /auth/login` | 5 / 15 min per IP **and** per email |
  | `POST /auth/register` | 3 / hour per IP |
  | `POST /auth/password/forgot` | 3 / hour per email |
  | Public intake | 10 / hour per IP |
  | `POST /intake/quiz-preview/insights` | 5 / hour **and** 20 / day per IP, under a **500 / day global** ceiling |
  | LLM-backed endpoints | 20 / hour per user |
  | Authenticated default | 1000 / hour per user |

---

## Part 6 — Frontend architecture

### 6.1 State ownership

The single biggest change: **stop putting server data in React Context.**

| State | Owner | Why |
|---|---|---|
| Session identity | `AuthProvider` (thin — user + csrf only) | Rarely changes; a context re-render is cheap |
| All server data | TanStack Query | Cache, dedupe, retry, background refetch, invalidation |
| Form state | react-hook-form + zod | Uncontrolled inputs; no re-render per keystroke |
| Ephemeral UI | `useState` local to the component | — |
| Cross-cutting UI (toasts, modal stack) | small Zustand store | Avoids a second god-context |
| URL state (filters, tabs, pagination) | `useSearchParams` | Shareable, back-button correct |

`AuthContext` sheds `fetchWithAuth`, `streamFetch`, `fetchProfileData`,
`saveProfileData`, `updateProfileData`, and `fetchProfile`. Those become a module-level
HTTP client plus query hooks — no context, no re-render coupling.

### 6.2 The data layer

```ts
// shared/api/client.ts — one fetch wrapper, fully typed, no `any`.
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Request-Id": crypto.randomUUID(),
      ...(isMutation(init?.method) ? { "X-CSRF-TOKEN": getCsrfToken() } : {}),
      ...init?.headers,
    },
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ProblemError(res.status, body);   // typed Problem Details
  return body as T;
}
```

```ts
// features/matching/queries.ts — the component never sees a fetch or a loading flag it owns.
export const matchKeys = {
  all:  ["matches"] as const,
  list: (lens: Lens) => [...matchKeys.all, lens] as const,
};

export function useMatches(lens: Lens) {
  return useInfiniteQuery({
    queryKey: matchKeys.list(lens),
    queryFn: ({ pageParam }) =>
      request<Paginated<Match>>(`/v1/me/matches?lens=${lens}&cursor=${pageParam ?? ""}`),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    staleTime: 5 * 60_000,
  });
}
```

Mutations invalidate by key, so completing an assessment refreshes matches without any
component knowing the two are related:

```ts
onSuccess: () => queryClient.invalidateQueries({ queryKey: matchKeys.all })
```

**Types are generated, not written.** `openapi-typescript` runs against the API's
OpenAPI document in CI; a backend field rename fails the frontend type-check instead of
surfacing as a runtime `undefined` in production.

### 6.3 Routing and the render path

Two defects to fix in `App.tsx`:

1. **All 30+ pages are statically imported** → one bundle for every visitor.
2. **`AuthProvider` blocks the whole tree on a spinner** until `GET /api/profile`
   resolves → the public landing page waits on an authenticated round trip.

```tsx
// app/routes.tsx — every route lazy, split at the route boundary.
const JobSeekerDashboard = lazy(() => import("@/features/dashboard/DashboardPage"));
const CompanyLensPage    = lazy(() => import("@/features/matching/CompanyLensPage"));

// Public routes render immediately. Only protected routes await the session.
<Routes>
  <Route element={<PublicLayout />}>
    <Route index element={<LandingPage />} />        {/* no auth dependency */}
    <Route path="login" element={<LoginPage />} />
  </Route>
  <Route element={<RequireAuth roles={["job_seeker"]} />}>
    <Route path="dashboard" element={<JobSeekerDashboard />} />
  </Route>
</Routes>
```

`RequireAuth` — not `AuthProvider` — is where the session gate lives, and it suspends
only the subtree it guards. Landing-page LCP stops depending on the API.

Each route is wrapped in an `<ErrorBoundary>` with a `<Suspense>` fallback, so one
component's failure degrades one panel instead of white-screening the app.

**Budget:** initial JS ≤ 180 KB gzip; route chunks ≤ 60 KB; LCP < 2.0 s on 4G.
Enforced by `size-limit` in CI, not by intention.

### 6.4 Feature slice anatomy

```
features/assessments/
├── api.ts            # request() calls, typed by the generated schema
├── queries.ts        # useAssessmentForm, useSubmitAssessment, query keys
├── types.ts          # slice-local view models
├── components/
│   ├── AssessmentStepper.tsx
│   ├── AssessmentStepper.test.tsx
│   └── ...
└── index.ts          # public surface — the ONLY legal import path for other slices
```

An ESLint `no-restricted-imports` rule enforces the boundary: `features/*/` may not deep-import
from another `features/*/`. This is what keeps a 141-file frontend from becoming a graph
where every change touches everything.

### 6.5 Testing

| Layer | Tool | Rule |
|---|---|---|
| Unit / component | Vitest + RTL | Test behaviour through the DOM, not implementation |
| Network | **MSW** | Handlers generated from the same OpenAPI doc — mocks cannot drift from the contract |
| E2E | Playwright | Critical paths only: register → verify → assessment → matches |
| Visual | Playwright screenshots | Landing page + dashboard, light/dark |
| Budget | size-limit | Fails CI on bundle regression |

MSW replaces hand-rolled `vi.fn()` fetch mocks. Those mocks currently encode a *guess*
about the API shape; MSW handlers built from the contract encode the *actual* shape.

---

## Part 7 — Production readiness

### 7.1 Observability

Nothing in the system is currently observable: no structured logs, no request IDs, no
metrics, no traces, no error tracking. At millions of users, an unobservable system is
an unoperable one.

**Logs** — JSON to stdout, one line per request, collected by the platform:

```json
{"ts":"2026-08-22T14:03:11.482Z","level":"info","event":"http_request",
 "request_id":"01JX8T3Q4Y7ZK2M9","method":"GET","path":"/api/v1/me/matches",
 "status":200,"duration_ms":47,"user_id":8123,"db_ms":31,"db_queries":3,
 "cache":"hit","service":"api","version":"2026.08.22-a1b2c3d"}
```

Every log line carries `request_id`; `audit_events.request_id` joins audit rows to logs
to traces. PII is redacted at the formatter — emails, tokens, and resume text never
reach a log sink.

**Metrics** — Prometheus, RED per endpoint plus:

| Metric | Alert |
|---|---|
| `http_request_duration_seconds` (histogram, by route) | p99 > 1 s for 5 min |
| `http_requests_total{status=~"5.."}` | error rate > 1 % for 5 min |
| `db_pool_in_use / db_pool_size` | > 0.8 for 10 min |
| `celery_queue_depth{queue}` | `llm` > 500, `default` > 100 |
| `llm_request_duration_seconds{provider}` | p95 > 10 s |
| `auth_login_failures_total` | 10× baseline (credential stuffing) |

**Traces** — OpenTelemetry auto-instrumentation for Flask, SQLAlchemy, requests, redis,
boto3; manual spans around scoring and LLM calls. 100 % sampling on errors, ~1 % on
success.

**Errors** — Sentry with release tagging and source maps, on both the API and the SPA.

### 7.2 SLOs

| SLO | Target | Window |
|---|---|---|
| API availability | 99.9 % | 30 d rolling |
| Read p99 (`/me`, `/companies`, `/matches`) | < 400 ms | 30 d |
| Write p99 (`PATCH /me/profile`, assessment submit) | < 800 ms | 30 d |
| Assessment scoring latency | < 30 s p95 | 7 d |
| Email delivery | < 60 s p95 | 7 d |

Error budget: 43 min/month. Two consecutive weeks of budget burn freezes feature work
in favour of reliability. That rule is what stops "we'll fix it later" from compounding.

### 7.3 Resilience

| Failure | Behaviour |
|---|---|
| OpenAI / Groq down | Circuit breaker opens after 5 failures in 30 s; the endpoint returns a cached or degraded result, never a 500 |
| O*NET slow | 3 s timeout, 2 retries with jittered backoff, then cached-stale |
| Resend down | Email is in the outbox and already committed; the worker retries with backoff |
| Redis down | Cache reads fail open (fall through to Postgres); rate limiting fails **closed** to a conservative in-process limit |
| Postgres primary failover | `pool_pre_ping` + PgBouncer reconnect; writes 503 for < 30 s, replica reads unaffected |
| Worker backlog | HPA on queue depth; `202` responses remain honest because the job is durable |

Every outbound client gets a timeout, a retry policy, and a breaker. There are currently
30 `except Exception` blocks in `app.py` doing this job by hand, inconsistently.

### 7.4 Security carry-forward and additions

Already correct — keep: SHA-pinned CI actions, pinned deps + `pip-audit`/`npm audit`
gates, CSP on both tiers, `ProxyFix` with an explicit hop count, CSRF on state-changing
methods, bcrypt, account lockout, GDPR export/delete, retention cleanup, R2 presigned
uploads with `ContentLength` binding.

To add:

1. **Secrets** out of `.env` files and into a managed store (AWS Secrets Manager / Doppler),
   injected at runtime. Rotation runbook for `JWT_SECRET_KEY` with a key-ID header so
   rotation does not invalidate every live session at once.
2. **Refresh-token rotation with reuse detection** (§5.3) — currently impossible.
3. **Rate limiting on Redis** — currently per-worker and therefore near-useless in prod.
4. **Idempotency keys** on account creation and assessment submission, to make client
   retries safe.
5. **Row-level authorization asserted in the repository layer**, not in each handler.
   `repo.get_experience(user_id, experience_id)` cannot return another user's row; a
   handler that forgets a check gets an empty result rather than an IDOR.
6. **`public_id` in URLs** — sequential integer IDs are currently enumerable.
7. **Dependabot / Renovate** with grouped weekly PRs, so pins stay current instead of
   ageing until a manual CVE sweep.
8. **Migration safety gate in CI**: fail the build if models and migrations diverge, and
   reject destructive DDL (`DROP COLUMN`, `NOT NULL` without default) without an
   explicit `# expand-contract:` annotation.

### 7.5 Environments and deployment

| Env | Purpose | Data |
|---|---|---|
| `local` | Docker Compose: api, worker, postgres+pgvector, redis, mailpit, minio | Seeded fixtures |
| `ci` | Ephemeral, Postgres service container | Factories |
| `preview` | Per-PR, auto-torn-down | Anonymised snapshot |
| `staging` | Production mirror | Anonymised snapshot |
| `production` | — | Live |

**CI runs against Postgres, not SQLite.** This is a correctness fix, not a nicety —
490 tests currently pass against a database the product does not use.

**Pipeline:** lint → typecheck → unit → integration (Postgres + Redis service
containers) → contract (OpenAPI diff, breaking-change gate) → build image → migration
dry-run against a staging snapshot → deploy staging → smoke → canary 5 % → progressive
rollout with automatic rollback on SLO burn.

**Migrations run as a job before the new version rolls out**, and every migration must
be backward-compatible with the previous release (expand/contract), because during a
rolling deploy both versions serve traffic simultaneously.

---

## Part 8 — Migration roadmap

Strangler fig. The current app keeps serving traffic throughout; nothing is rewritten
in place. The test suite is the ratchet — it stays green at every step, and it
grows at every step. Phase counts are recorded per phase below rather than in
one number here: a figure quoted in the prose goes stale the first time anyone
adds a test, and a stale ratchet is worse than none, because the next person
reads it as the floor.

### Phase 0 — Foundation *(additive only, zero behaviour change)*

- `create_app()` factory, typed and validated `Settings`, `extensions.py`.
- Problem Details error handlers; `/healthz`, `/readyz`, `/metrics`.
- Structured JSON logging with request IDs.
- SQLAlchemy engine options: `pool_pre_ping`, sized pool, statement timeout.
- Redis-backed rate limiting and cache.
- `Dockerfile`, `compose.yml`, `Makefile`, `.dockerignore`.
- ~~CI switched to Postgres~~ — **done 2026-08-27.** A `pgvector/pgvector:pg18`
  service container, digest-pinned, is the gate; the SQLite job survives as
  non-gating early signal. See Phase 2's prerequisites below.

**Exit:** existing `app.py` still serves every route; new infrastructure runs alongside.

### Phase 1 — API restructure

Split into **1a (relocation)** and **1b (the Part 5.2 endpoint redesign)**, because
only 1b changes request and response shapes and only 1b needs frontend coordination.

#### Phase 1a — relocation · **done 2026-08-26**

- `create_app()` in `solverah/factory.py`; `app.py` is a 69-line entrypoint that
  keeps `app = create_app()` module-level for gunicorn, `flask run`, and the fixtures.
- All 38 routes plus the 2 account-lifecycle routes moved into
  `solverah/api/v1/{auth,profiles,intake,assessments,companies,intelligence,account}.py`.
  **Same paths — only the `/api/v1` prefix is added.** The Part 5.2 renaming is 1b.
- Legacy `/api/*` kept as **aliases, not 308 redirects**: a second URL rule bound to
  the same endpoint and the same view function. A redirect on a CORS-preflighted POST
  is unreliable, and — the reason that settled it — Flask-Limiter keys its storage on
  the endpoint name, so a second *endpoint* would have given every auth limit a second
  independent bucket.
- Business logic in `services/*`, every query in `repositories/*`, pure rules in
  `domain/*`, provider adapters in `infra/*`. Enforced by `tests/test_layering.py`.
- Pydantic v2 pinned; `packages/ml/{culture,resume}` extracted; the `sys.path.insert`
  and the `importlib` file-path load of `resume_parser.py` are gone.
- OpenAPI 3.1 generated by `solverah/openapi.py` into a committed `docs/openapi.json`,
  with a CI drift check. Written in-house rather than with apiflask/flask-openapi3/
  spectree — all three want to own either the app object or the error body, and
  pydantic v2 already emits JSON Schema 2020-12, which *is* OpenAPI 3.1's dialect.

**Found and fixed en route:** every `@limiter.limit(...)` in `app.py` was written
*above* its `@app.route(...)`. Flask registers the function it is handed and returns
it unchanged, so the limiter wrapper was never the registered view — the 5/minute on
login and register, the 3/minute on password reset, and the 1/day on guest quiz
insights had **no effect at all**. Only `default_limits` applied. Blueprint ordering
fixed it; `tests/test_rate_limits.py` is the regression cover.

**Exit met:** backend tests green, up from a 570 baseline. The figure recorded
here at the time was 729, and it was already wrong when it was written — the
conftest cleanup and the new safety and route-limit tests had taken it to 770
before Phase 1b started. The lesson is in the paragraph above Phase 0: quote the
baseline you measured against, not a number that will drift.

#### Phase 1b — endpoint redesign · **done 2026-08-26**

The Part 5.2 map is live and is the only surface the API serves: 40 operations
under `/api/v1`, no unversioned aliases, no superseded paths.

- **`/me/*`.** `GET|POST /profile` split into `GET|PATCH /me` (identity),
  `GET|PATCH /me/profile` (the blob), `GET|PUT /me/skills`,
  `PATCH /me/career-status`, `GET /me/dashboard`, and a resume resource. The
  account-lifecycle routes folded in as `GET /me/export` and `DELETE /me`.
- **One assessment route.** `POST /assessments/{kind}/submissions` replaces five
  submit handlers, `GET /assessments` is a new catalogue with per-user
  completion state, and `GET /me/assessments/{kind}/result` replaces the two
  result endpoints. `{kind}` selects the request body, the response body, the
  auth requirement, and the rate-limit bucket.
- **One claim.** `POST /intake/claims` replaces `create-account`, `sign-in`,
  `link-account`, and `save-to-account`, discriminated on `mode`.
- **Cursor pagination.** `GET /companies` (new) and `GET /me/matches` page with
  an opaque keyset cursor; `GET /me/recommendations` carries the envelope ahead
  of having rows to put in it.
- **`GET /auth/session`.** The P0-3 fix: identity, CSRF token and flags, with no
  `profile_data` and no audit write, so session restore no longer takes a write
  lock on the hottest read in the system.
- **Enforced schemas.** `@document(..., enforce=True)` on every route.
  Enforcement lives in a `before_request` hook, not in the decorator — see
  "Where enforcement lives" below.
- **Frontend cut over**, then the legacy `/api/*` aliases and the superseded
  handlers were deleted. `solverah/api/v1/{profiles,account}.py` are gone
  entirely; `register_legacy_aliases` is gone with them.

**Exit met:** 917 backend tests green, against a 770 baseline.

##### Where enforcement lives, and why not in the decorator

`@document` is written *above* `@bp.route` throughout, and `Blueprint.route`
registers the object it is handed and returns it unchanged — so a decorator
above it annotates something Flask has already registered. A wrapper written
there would never run. That is precisely how every `@limiter.limit` in the
pre-Phase-1 `app.py` came to be inert. Enforcement therefore resolves the spec
from `request.endpoint` at request time, which makes declaration order
irrelevant; `tests/test_request_validation.py` asserts that directly.

Three decisions came out of auditing what the handlers tolerated before the flip:
unknown keys are **dropped**, not rejected (live call sites send more than the
schemas name — `role` on register would have broken); types are **coerced**, not
policed (pydantic's lax mode matches what `int(data.get("size") or 0)` did); and
missing required fields are **rejected**. The third is the live change: eight
failures that answered 400 from a hand-written check now answer 422 with the
offending field named. Nothing in the frontend branches on 400, and
`src/utils/apiError.ts` already read both bodies.

One consequence is worth knowing: a request refused by the hook is **not**
charged to its endpoint's rate-limit bucket, because Flask-Limiter evaluates
decorated limits inside the view wrapper rather than in middleware. That is the
behaviour to want — a 422 is cheaper than the handler it prevents, and charging
for it would let a stranger behind the same NAT gateway spend a real user's
login allowance with garbage — but it means a flood of *malformed* bodies is
bounded only at the edge.

##### Rate-limit buckets after the collapse

Collapsing routes merges their limiter buckets, and this was decided rather than
inherited. Flask-Limiter composes its storage key from the endpoint name, so
five submit handlers at 5/minute each became one handler with one shared
5/minute budget — a user finishing Work Pulse and starting FocusType would have
been spending a single allowance across two unrelated instruments.

**Decision: key the bucket by the discriminator, preserving each instrument's
budget exactly, rather than raising the limit.** Raising it to 25 would have let
any *one* instrument be hit five times harder than before, and the limit exists
to bound provider spend, which is per call to a specific instrument. The same
applies to `/intake/claims`, whose four modes did not even share a number —
three at 5/minute, `save-to-account` at 10 — so the limit value is resolved per
mode as well as the bucket.

Two mechanics bit while implementing this and are recorded so they do not bite
again:

| Trap | What happens |
|---|---|
| `limiter.limit(scope=...)` | Keys the bucket as `"{endpoint}:{scope}"`, so the scope *sub-divides one endpoint* rather than joining two. It reads correctly and does nothing. Only `limiter.shared_limit` drops the endpoint from the key. |
| A new view written as `return login()` | At module scope `login` is the limiter wrapper, not the handler, so the shared bucket is charged **twice** per request and the route silently runs at half its stated allowance. Caught by a test that expected the breach on the sixth request and saw it on the fourth. |
| A bare `"5 per minute"` on a route that had no per-endpoint limit | `@limiter.limit` defaults to `override_defaults=True`, so it *removes* the global 200/day while appearing to tighten. `wpll` needed its defaults named explicitly. |

Scopes are kept now that the cutover is over, for a different reason: dropping
them would rename every live bucket at deploy time and hand every caller a fresh
allowance mid-release.

##### Guest quiz insights — the outstanding 1a follow-up

`POST /quiz-insights-guest` carried `@limiter.limit("1 per day")` keyed on the
IP, with a docstring saying it existed to cap OpenAI spend. Both halves of that
deserved to be taken seriously and they pull in opposite directions.

`1 per day per IP` is not one preview per person. Behind corporate NAT it is one
per *office*; behind mobile CGNAT it is one per *carrier segment*. The second
visitor gets a 429 having done nothing, at the unauthenticated top of the
pre-launch funnel, with no account and no way to tell a limit from a fault — it
reads as a broken quiz, and the visitor leaves. But it cannot simply be loosened
either: every call is a paid request with no account behind it, so a per-IP limit
alone bounds nothing that matters, because spend scales with the number of
distinct IPs and that is the one quantity an abuser controls freely.

**Recommended and implemented: a per-IP allowance sized for a human plus a
global daily ceiling sized to a spend budget** — `5/hour;20/day` per IP and
`500/day` overall, both named in `security.py` with the reasoning attached so
tuning them is a one-line change. The trade is explicit: a global ceiling means
a determined abuser can exhaust the day's budget and leave real visitors seeing
429s. That is still the better failure, because the alternative is an unbounded
invoice, and the per-IP limit means exhausting the global budget takes many
distinct addresses rather than one.

**This one needs a decision to stand.** The numbers are a recommendation, not a
measurement — nobody has looked at what the endpoint actually receives. And the
global half only works if the counter is shared: on `memory://` it is per-worker
and resets on deploy (P0-5), which makes it decorative in exactly the deployment
where it matters. Set `REDIS_URL` before relying on it.

##### Deliberately not built

Part 5.2 lists these; each is gated on something Phase 1b does not have.

| Not built | Gated on |
|---|---|
| `/me/experiences`, `/me/educations` | These replace `profileData.experience[]` *inside the blob*. Building them now means CRUD endpoints doing read-modify-write on sub-arrays of a JSON column — starting the decomposition with none of the row-level storage that makes it safe, and widening P0-1's lost-update window once per list item. Phase 2. |
| `POST /auth/refresh` | Needs the `user_sessions` table (A7). Phase 2. |
| `202` + job handle on resume-complete, recommendations-refresh, path-suggestions | Needs a queue. Returning 202 for work that then runs inline hands the client a job to poll that has already finished. Phase 3. |
| `POST /me/matches/{id}/actions` | Needs the `rec_actions` table. Phase 2. |
| `GET /assessments/{kind}/submissions/{id}` | Only the person-side instrument has submission ids to serve it from. Phase 2's `assessment_*` unification. |
| `/companies/{public_id}` | `companies.public_id` does not exist; the integer id still enumerates. Phase 2 / Part 4.2. |

Two paths deviate from Part 5.2's sketch on purpose:

- **`POST /intake/resume-tickets`**, not `/intake/submissions/{id}/resume-ticket`.
  The id does not exist until the ticket mints it — the flow is ticket → browser
  uploads → `POST /intake/submissions` commits the row. A path taking the id
  would need either a draft row inserted before any validation ran or a
  client-generated id, and that id is the *only* thing protecting an anonymous
  submission, so it has to come from a server-side CSPRNG.
- **`POST /intake/claims`**, not `/intake/submissions/{id}/claim`. Two of the
  four modes have no submission id: `link` files a *new* submission rather than
  claiming an existing one, and `session` adopts a quiz session that was never a
  submission at all.

##### What Phase 1b made temporarily worse

`profile_data` was not touched — it is still the storage, and Phase 2 decomposes
it. Splitting the endpoint therefore widens **P0-1** in one specific way: a
client that sent one `POST /profile` now sends `PATCH /me` and
`PATCH /me/profile`, so a failure between them leaves identity and profile out of
step, and two concurrent editors have two windows to lose an update in rather
than one. This is accepted, recorded in `solverah/schemas/profile.py` where the
shapes live, and the `ProfileDocument` envelope is what Phase 2 hangs `version`
off to close it.

**P0-3 is fixed at the API and only half-realised at the client.** `GET
/auth/session` writes nothing, but `AuthContext.tsx` still fetches
`GET /me/profile` alongside it on boot, because the `User` type carries
`profileData` and six components read it off the user object. The two requests
are issued together so a restore is one round trip's latency rather than two.
Deleting the second request from that `Promise.all` is what finishes the job,
and it is Phase 4 work — the split it needs has already happened.

##### One bug this phase created and caught

Deleting the superseded handlers took a helper with them that a *new* handler
still called, leaving `POST /intake/early-access` raising `NameError` on its
first real request. Every test passed, because nothing in the suite called that
endpoint. `tests/test_route_surface.py` is the answer: a static check that every
name a route module loads is one it defines, plus the behaviour coverage the
funnel was missing. Worth noting which one would have caught it — the static
check would; the "no route returns 5xx" sweep would not, because the enforced
schema rejects an empty body before the handler runs.

### Phase 2 — Data model v2

#### Prerequisites · **done 2026-08-27**

Three things had to be true before any migration ran, and all three were checked against
the live system rather than assumed:

- **CI runs on Postgres** (above). 926 tests, 8 real failures, fixed.
- **The target supports the design.** Render reports
  `PostgreSQL 18.3 (Debian 18.3-1.pgdg12+1)`, and `CREATE EXTENSION` succeeds for
  `vector` (0.8.1), `citext` (1.8), and `pg_trgm` (1.6) under the application role —
  tested for real inside a transaction that was then rolled back.

  This settles an open question in 4.2: **`uuidv7()` is a native built-in here and
  works.** `DEFAULT uuidv7()` stands exactly as written, and no table in Part 4 needs
  app-side ULID or UUIDv7 generation. It also corrects this document, which said
  "Postgres 16" in 2.1 — 16 has no `uuidv7()`, so the CI container is pinned to pg18 to
  match production rather than to match that line.
- **The rollback path exists and has been walked.** `docs/RUNBOOK_DATABASE_ROLLBACK.md`.
  The load-bearing detail: Render's point-in-time recovery provisions a **new instance
  with a new connection string**, so it is not a rollback until every service is
  repointed. The fast path is a pre-migration `pg_dump` restored in place — 16.5 s to
  take against production, 1.4 s to restore, connection string untouched. Rehearsed
  by dropping a column and deleting a million rows, then restoring both.

  Behind it, Render's PITR window is **7 days** (confirmed 2026-08-27), rolling rather
  than daily snapshots. That is the outer bound on how late a Phase 2 defect can be
  discovered and still be recoverable from Render's side — a backfill whose wrongness
  only surfaces in a monthly report is outside it, which is an argument for verifying
  each aggregate's backfill before moving to the next rather than batching them.

#### The migrations

Expand/contract, one aggregate at a time, dual-write then backfill then cut over:

1. **Phase 2c · done 2026-08-27.** `users` (rename from `user`, add `public_id`,
   `status`, `version`). Numbered first and shipped second — see 2a's note on why
   the profile tables went ahead of it.
2. **Phase 2a · done 2026-08-27.** `profiles` + `profile_experiences` +
   `profile_educations` + `skills` + `profile_skills` + `resumes`.
3. **Phase 2d · done 2026-08-27.** `assessment_*` unification —
   `assessment_forms` + `assessment_submissions`, and the three storage homes
   carried into them.
4. ~~`company_culture_vectors` + pgvector + HNSW.~~ **Struck 2026-08-27 (A16).**
   Cosine over an 8-vector does not compute `culture_fit_score`, and 2,071
   companies do not need an index. The 4.5 schema behind it is struck with it.
   Renumbering the item below would break every reference to "item 5", so the
   numbering stands and this entry stays as the record of why there are four.
5. Partition `audit_events`, `assessment_responses`, `match_recommendations`, `rec_actions`.

**Exit:** no query reads `profile_data`; every assessment product reads and writes
one storage shape.

The exit criterion used to read "culture matching is index-backed". That went
stale with item 4 and is struck with it — the full scan in `_score_all` is still
P0-2 and still open, but an index was never the fix for it. A16.

#### Phase 2a — decomposing `profile_data` · **done 2026-08-27**

Ran ahead of the `users` rename rather than after it, which is why the new tables
reference `user.id` and not `users.id`. The rename is orthogonal to this and
sequencing it first would have meant two schema changes landing on the same
release for no gain.

**What it is not.** It is a storage change and not a contract change. `GET
/me/profile`, `GET /auth/session`, `PATCH /me/profile`, `PUT /me/skills`, `GET
/me/dashboard` and `GET /me/export` return the same bytes they returned before —
verified by capturing every response on both sides of the change and diffing
them, with only the CSRF token and two timestamps masked. `docs/openapi.json`
regenerated with no change to a single path, schema or status code; the only diff
is prose in four `description` strings that said the blob was still the storage.
No frontend file was touched. `AuthContext.toUser()` was the documented seam and
it held.

**What it cost.** `load_document` is five queries where the blob was zero — the
blob rode along on the user row the handler had already loaded. That lands on
`GET /me/profile`, not on the boot path, which is `GET /auth/session` and touches
none of it. Phase 3's cache is where this gets paid back.

**Left for a follow-up, on purpose.**

- `public_id` on an experience or education row is not a stable handle. Writes are
  delete-then-insert, because a profile save has always replaced these lists
  wholesale and the document carries no stable per-entry identity — the
  frontend's list `id` is `Date.now()` for a new row and an array index for a
  parsed one. It becomes a handle when Part 5.2's `/me/experiences` lands and an
  entry is addressed individually.
- `profile_experiences.source` is always `'user'`. The document records no
  per-entry provenance; the parser can write `'parsed'` directly once Phase 3
  moves parsing off the request path.
- `profiles.completeness` is maintained on write and the dashboard still computes
  its percentage from the assembled document. That is deliberate — a read-time
  computation cannot drift — and the column is there so "how many profiles are
  more than 80% complete" is a query rather than a scan of a JSON column. A test
  asserts the two agree.

**One defect introduced by this phase, found 2026-08-27 and fixed.**
`education[].field` was silently dropped on every profile save. `_write_children`
builds an ORM-enabled bulk insert — `sa.insert(ProfileEducation)` with a list of
dicts — and those key on *attribute* names; the dict said `"field"`, which is the
column name. `ProfileEducation.field_of_study = db.Column("field", …)` is the only
renamed column in the profile tables, so it was the only key of the twenty-odd
across three inserts where the two names differ, and SQLAlchemy dropped it with no
error and a NULL in the column. The migration was never wrong — it writes raw SQL
against the real column — so data carried across by 2a is intact; only writes
through the application lost the value, from 2a until the fix.

Two things are worth taking from it. The first is that every test in
`test_profile_decomposition.py` passed throughout, because `RICH_PATCH`'s
education entry carries no `field`. The second is that the same trap is armed for
any future renamed column, so `test_the_set_of_renamed_columns_is_still_these_two`
now pins the set to `profile_educations.field` and `audit_log.metadata` — the
tripwire fires when a third appears, which is months before someone bulk-inserts
into it. `audit_log.event_metadata` is safe today: its only write is an ORM
constructor, and constructors key on attributes.

**Two pre-existing defects found while verifying this, neither fixed here.**

- `alembic_version.version_num` is `VARCHAR(32)` and the revision id
  `20260203_add_email_confirmation_to_user` is 39 characters, so `flask db
  upgrade` cannot build a database from scratch. It has been true since February
  and nothing caught it because no test runs the migration chain — the fixtures
  use `db.create_all()`. It does not affect deploying to an existing database,
  whose `alembic_version` already holds a shorter id and whose next value
  (`20260827_profile_tables`, 23 characters) fits.
- `make migrate-check` (`flask db check`) already reported drift before this
  phase: `company_slug_key` versus `ix_company_slug`, and
  `ix_resume_parse_correction_user_id`. The six tables added here contribute
  nothing to that diff.

#### Phase 2c — the `users` table · **done 2026-08-27**

Ran after 2a rather than before it, so the four foreign keys 2a created against
`user.id` were carried through the rename by Postgres rather than written twice.
They were, along with the eight that predate them; `tests/test_users_table.py`
asserts all twelve.

The column-by-column decisions are in 4.2's "As built". What is worth recording
here is the shape of the phase rather than its contents.

**A rename moves the table and nothing else.** Postgres carries foreign keys
across `ALTER TABLE ... RENAME`, and does not carry the sequence, the primary key,
or the indexes — those keep `user_` forever unless something renames them.
`user_pkey` and `ix_user_confirmation_token` were renamed explicitly;
`user_email_key` was dropped and replaced by `uq_users_email` because the
predicate is new; and the sequence was destroyed rather than renamed, because
converting `SERIAL` to an identity column drops the old sequence and lets Postgres
create `users_id_seq` under the right name itself. A test now fails on any object
in `public` still carrying the pre-rename name.

**The migration was executed, not merely written.** The fixtures build the schema
with `db.create_all()`, so a migration that no test runs is a file nobody has
proved. This one was applied to a scratch database in both directions —
`downgrade` reproduces the pre-2c table exactly (same columns, same types, the
same three index names, all twelve foreign keys), `upgrade` reproduces the target,
and `flask db check` against the result reports *"No new upgrade operations
detected"*. That last line is the one that matters: it is the model and the
migration agreeing, which nothing else in this repo checks.

**The contract fixture is new and is reusable.** `Scripts/capture_contract.py`
records the masked bytes of 25 responses across the whole authenticated surface;
`Scripts/verify_contract.py` re-runs them and diffs. 2a verified its equivalent by
hand. This is that method, kept — the phase that flips `public_id` onto the wire
needs it to prove the opposite result, that the bytes *did* change and only where
intended.

**Not done here, and named so it is not mistaken for done.** `user_sessions` and
`user_consents` are still declared-only. `users.profile_data` is still not dropped
— 2a's one-release stay is still running. Every `user_id` child column is still
`INTEGER` against a `BIGINT` parent. `last_login_at` and `deleted_at` exist and
are never written. And `status` is maintained at exactly two transitions,
confirmation and tombstoning, because those are the two that already existed in
code; the rest of the state machine arrives with whatever needs to read it.

#### Phase 2d — assessment storage unification · **done 2026-08-27**

Five products, four storage locations, one shape. Work Pulse in
`user_intake.wpl_*`, the Lite-Lite session in `user_intake.wpll_*`, FocusType and
ManagerMatch as two keys inside the profile document, and the core assessment in
its own two tables. `GET /assessments` read three of them to answer one question.

**A storage change, not a contract change — and this time that was measured
rather than argued.** 2a verified its equivalent by hand and 2c built the fixture;
2d extended it. `Scripts/capture_contract.py` now drives 44 responses instead of
25: all five instruments submitted, the three that store a result re-read, the
anonymous WPLL session claimed onto the account, and the catalogue and session
captured with `wpl_completed` / `wpll_completed` / `wp_v2_completed` **true**. The
2c scenario never touched an assessment, so those three booleans had only ever
been compared in the state where nothing sets them. `verify_contract.py` reports
**0 differences across 44 responses**. `docs/openapi.json` regenerated with no
change to a single path, schema or status code; the only diff is prose in two
`description` strings that said `user_intake` was still the storage — the same
result 2a got, for the same reason.

**What the fixture cannot see, and what covers it instead.** The Work Pulse
narrative prompt reads the claimed WPLL answers and the intake row's statement
selections. Neither reaches the wire, and the fixture stubs the prompt builders to
keep the provider deterministic, so a Work Pulse narrative could have quietly lost
its context with every byte still identical. `tests/test_assessment_storage.py`
asserts the two inputs arrive.

**The one addition to 4.4, and the reason for it.** `assessment_submissions` has an
`answers` column that Part 4.4 does not declare, because 4.4 puts raw per-item
answers in `assessment_responses` — the table partitioned by `answered_at`, which
is item 5 and its own phase. The four non-core instruments need their answers kept
(the narrative prompt, `/me/export`, the culture-preference backfill), so until
item 5 lands they live on the submission as the payload the client sent. The
alternative was decomposing them into the person-side response table now, which
would have put four instruments' answers behind D-01's doorway and forced every
one of those readers through it — the exact surface widening the phase was not
allowed to do.

**D-01 came out of this exactly as wide as it went in.** A `core` row in the shared
table carries a kind, a version, a status and three timestamps. `result` and
`answers` are null, under a check constraint rather than a convention, and the
core row is written by `assessment_store` inside the same transaction as the raw
responses rather than by the repository the other four use. The person-side tables
were not altered at all: no column added, no type changed, no row rewritten. The
join is `submission_id = public_id.hex` — the id those tables already carried,
still 32 hex characters on the wire, now a key into the shared table instead of a
`uuid4()` joined to nothing.

One allowlist entry was added, and it is the thing to argue with if anything here
is wrong: the migration reads `DISTINCT (submission_id, user_id, form_version)`
off the response table to build one submission row per existing sitting. It reads
a sitting's identity and nothing else — no choice, no dimension key, no score —
and it cannot route through `assessment_store`, which writes through the ORM
against today's model while a migration must run against the schema at its own
revision. Same class of grant as the 2026-08-19 entry that creates the tables.

**Retake semantics differ by kind, and the schema says so.**
`uq_assessment_submissions_current` is a partial unique index over
`(user_id, kind) WHERE kind <> 'core'`. The four client-rendered instruments have
one current sitting each and a retake updates it in place, which is what
`user_intake`'s one-row-per-user and a profile-document key gave them before.
`core` is excluded because its sittings are append-only. That index is also what
replaced `get_or_create_user_intake`'s cheap-collision trick: a concurrent double
submit now collides on the constraint before the LLM call rather than after it.

**`assessment_forms` is load-bearing, not decoration.**
`assessment_submissions (kind, form_version)` is a composite foreign key into it,
so a submission cannot name a version nobody registered — which is what stops the
version string being free text that drifts per instrument. Versions register on
first use (`AssessmentForm.register`, `ON CONFLICT DO NOTHING`), so a new item file
is usable the moment it ships rather than after a deploy step. `definition` is
empty for the four client-rendered instruments on purpose: their questions ship in
the client bundle, and writing a copy here would create a second source of truth
for something no server code reads. Their `form_version` is the placeholder `v1`
for the same reason. Both become real when Phase 4 moves those definitions
server-side.

**The migration was executed, not merely written**, in both directions, against a
scratch database seeded with one row of every shape it reads — including the Work
Pulse account whose second commit never landed, the account that picked statements
but never answered the quiz, and two core sittings under two different item files.
Thirty-four checks, all passing: the carry-over, the `complete`-versus-`scored`
distinction preserved rather than flattened, the two profile keys removed from
`extra` with unrelated keys untouched, `public_id` equal to the pre-existing
submission id, and the downgrade putting all four instruments back. Autogenerate
then reports **0 operations** against the migrated schema, which is the model and
the migration agreeing — the check nothing else in this repo makes.

**Left behind on purpose.** `user_intake.wpl_*` and `wpll_*` are not dropped. Read
by nothing after this phase, they go in the next release — the same one-release
stay `users.profile_data` has been serving since 2a. `selected_statement_ids`
stays permanently: statement selections are intake data, not an assessment, and no
instrument produces them. `culture_preferences` also stays in `profiles.extra`,
and that is now a loose end rather than a decision — it is derived from Work Pulse
and consumed by matching, and 4.5's `user_culture_vectors` was where it was going
until A16 struck that table. It has no declared destination now.

**Not done here, and named so it is not mistaken for done.** `assessment_responses`
is still the unpartitioned `assessment_response`; partitioning is item 5.
`GET /assessments/core/form` still serves items from the item file rather than
from `assessment_forms.definition`, which is correct while the shuffle is
server-authoritative (D-04) and the definition is a version record rather than a
question bank. `status` never takes the value `in_progress` on a committed row,
because every instrument still arrives complete in one request; the constraint
keeps it because partial saves are what the column is for.

### Phase 3 — Async and caching

- ~~Celery + Redis broker; queues `default · llm · email · scoring · maintenance`~~ —
  **done 2026-08-27 (3a).** `solverah/infra/queue.py`. Broker and result backend fall
  back to `REDIS_URL`, so one variable configures the queue, the rate limiter and the
  cache. With no broker — CI, and a developer without Redis — tasks run eagerly in the
  calling process, which is what lets the suite stay green on a runner that has no
  Redis service container. `solverah/worker.py` is the worker entrypoint and
  `infra/docker/compose.yml` gains a `worker` service on all five queues.
- Move off the request path: **resume parsing (3a)**, **assessment scoring (3b)**,
  **path suggestions (3b)**, match precomputation, **all email (3a)**.
  Assessment scoring moved for the three provider-scored instruments only --
  `work_pulse`, `wpll`, `manager_match`. `core` and `focus_type` score from
  deterministic tables without opening a socket and stay synchronous; see A19.
  Match precomputation remains open and is gated on the causal model that
  replaces `culture_fit_score` (A16, A18), which does not exist yet.
- ~~Transactional outbox for email and domain events~~ — **done 2026-08-27 (3a).**
  Part 4.7's table, `solverah/services/outbox.py`. Every outbound email in the
  application now commits with the business write that occasions it. Three endpoints
  changed behaviour as a result and all three were compensating for the send being
  outside the transaction: `POST /intake/early-access` answered 500 on a mail failure
  and now answers 200 (the lead is durable before it returns), and
  `POST /auth/email/verify/resend` and `POST /auth/password/forgot` answered 500 after
  having already rotated the token — telling the user nothing had happened while the
  code in the database had just changed underneath them.
- Redis cache for ~~match sets~~, company detail, dashboards; invalidation by key on
  write. **Company detail and the dashboard done 2026-08-27 (3a)**
  (`solverah/infra/cache.py`). **Match sets struck — see A18.**
- SSE for the agent; `202 + job handle` for everything else that is slow.
  **Resume parsing done 2026-08-27 (3a)**: `POST /me/resumes/{id}/parse-jobs` +
  `GET /me/resume-parse-jobs/{job_id}`, an addition alongside the synchronous
  `/complete`, which is unchanged until the frontend moves.
  **Assessment scoring and path suggestions done 2026-09-01 (3b)**, the same
  shape and the same state machine: `POST /assessments/{kind}/scoring-jobs` +
  `GET /assessments/{kind}/scoring-jobs/{job_id}`, and
  `POST /me/path-suggestion-jobs` + `GET /me/path-suggestion-jobs/{job_id}`.
  Both are additions; the synchronous `POST /assessments/{kind}/submissions`
  and `GET /me/path-suggestions` are byte-identical and stay until 3c.
  **The SSE half was already done and is not safe under the worker model that
  actually runs — see A20.** It is the one item in this phase where the
  finding, not the feature, was the deliverable.
- ~~Writes on the read path (P0-3, server half)~~ — **done 2026-08-27 (3a).** No `GET`
  handler commits. The audit rows `GET /me/profile` and `GET /me/export` wrote are
  recorded by a worker; the culture-preferences backfill `GET /me/matches` committed is
  now a maintenance sweep and the read derives what it needs without persisting; the
  `career_status` derivation `GET /me/path-suggestions` committed is applied in memory
  only. `tests/test_read_path_writes.py` counts commits on the request's own session.

**Exit:** no handler makes a blocking third-party call. Gunicorn timeout drops 120 s → 30 s.

**Still not met after 3b, and now for a different reason.** 3a could not claim it
because assessment scoring and path suggestions were synchronous. They are not any
more — but *both synchronous routes still exist*, deliberately, because a client
cannot move from awaiting a 200 to polling a job in the deploy that first gives it
something to poll. So there are still handlers making blocking third-party calls;
they are just no longer the only way to do that work. Dropping the timeout now would
kill precisely the requests the frontend has not yet stopped issuing.

The remaining blockers are therefore named and countable:

1. **The frontend cuts over** to the job endpoints, and the synchronous submits,
   `GET /me/path-suggestions` and `POST /me/resumes/{id}/complete` are deleted (3c).
2. **`POST /agent/messages` streams from Groq inside the request** and always will
   -- a stream is not a job. It is what makes the timeout a question about worker
   class rather than about queues (A20), and it is the reason 30 s is not simply
   safe once 3c lands.
3. **Match precomputation** is still on the read path, gated on the causal model
   (A16, A18).

Until 3c, `gunicorn.conf.py` stays at 120.

### Phase 4 — Frontend restructure

Splits into work that is independent of the backend and work that is gated on the
Phase 1 contract. Only the second group needs backend coordination.

**Independent of every backend phase — startable immediately:**

- Route-based code splitting; public routes decoupled from the session fetch.
- Error boundaries; feature-sliced directories; ESLint boundary rule.
- Design-system extraction into `shared/ui`.
- Playwright smoke suite; `size-limit` budget in CI.
- TanStack Query adoption against the *current* endpoints — a query hook does not
  care whether the path is `/api/profile` or `/api/v1/me`; that is one constant.
- ~~Problem Details error parsing~~ — **done 2026-08-22.** `src/utils/apiError.ts`
  reads both the problem+json shape Phase 0 introduced and the legacy `{error}`
  bodies `app.py` still returns, across 17 call sites. Without it the specific
  message Phase 0 started sending was present in the response and discarded.

**Gated on Phase 1:**

- The *generated* typed client. `docs/openapi.json` exists as of Phase 1a and is
  enforced as of 1b, so this is unblocked — nothing generates from it yet.
- MSW handlers generated from the contract — hand-written in the meantime.
- ~~The `/api/*` → `/api/v1/*` path cutover~~ — **done 2026-08-26** with Phase 1b.
  `API_BASE` carries the version, so the 37 call sites moved by changing one
  constant plus each path that Part 5.2 actually renamed. The unversioned
  aliases are deleted; `tests/test_frontend_contract.py` tracks the surface and
  fails if a call site drifts off it.

Phase 1b leaves one item here with a name: `AuthContext.tsx` still fetches
`GET /me/profile` alongside `GET /auth/session` on boot, because the `User` type
carries `profileData` and six components read it off the user object. Moving
those onto their own queries and deleting the second request is what finishes
P0-3 on the client.

**Exit:** initial bundle under budget; no component owns a `loading` boolean for server data.

### Phase 5 — Scale hardening

- Read replicas + a `read_only` session router.
- PgBouncer transaction pooling.
- HPA on RPS and queue depth; PodDisruptionBudgets.
- Load test to 10× projected peak; fix what the test finds.
- Game days: kill the primary, kill Redis, black-hole OpenAI.

### Sequencing note

Phases 0 and 1 are prerequisites for everything else and carry near-zero product risk.
Phase 2 is the highest-value and highest-risk work — it is what actually unblocks scale,
and it is the phase that most deserves a full dual-write/verify/cutover discipline
rather than a big-bang migration.

**Phase 1 is what decouples the frontend from the backend, so it is not something to
route around.** Phase 4's independent group (above) can start today alongside anything.
Its remainder cannot: the generated client needs Phase 1's OpenAPI document, and 13
frontend files currently read the `profile_data` blob shape directly. Whether Phase 2
disturbs those 13 files depends entirely on ordering — with Phase 1 done first, schemas
sit at the API boundary and the storage decomposition never reaches the client; without
it, the decomposition leaks into response shapes and those files churn twice. Phase 3
has its own client-visible edge: resume-finalize, recommendations-refresh, and
path-suggestions become `202` + poll or SSE, which changes the interaction model
regardless of ordering.

So: run Phase 4's independent group now, then Phase 1, and only then Phases 2/3 backend
in parallel with the rest of Phase 4.

---

## Appendix A — Decision log

| # | Decision | Rationale | Alternative rejected |
|---|---|---|---|
| A1 | Stay on Flask; do not rewrite in FastAPI | The value is in the domain logic and the schema, not the framework. A rewrite spends the whole budget re-earning today's behaviour. Pydantic + OpenAPI on Flask gets ~90 % of the benefit. | FastAPI rewrite |
| A2 | ~~Postgres for everything, including vectors~~ — **superseded by A16, 2026-08-27** | The decision was right and its stated reason was wrong. "One datastore" stands; "pgvector handles 8-dim culture vectors" was never tested against the scorer, and A16 shows the 8 dimensions are not a vector space this product ranks in. There is no vector workload to keep in Postgres, so the decision it was arguing against never arises. `vector` stays installed on Render (0.8.1) and is unused. | Pinecone / Weaviate |
| A3 | Decompose `profile_data` rather than index the JSONB | GIN on JSONB fixes reads but not lost updates, not validation, and not row bloat. The blob is a correctness problem, not only a performance one. | JSONB + GIN |
| A4 | Celery over a bespoke thread pool | Durable queues, retries, scheduling, and observability for free. In-process threads lose work on deploy. | `ThreadPoolExecutor` |
| A5 | Cursor pagination, never offset | `OFFSET 100000` scans 100k rows and skews under concurrent writes. | Offset/limit |
| A6 | Modular monolith, not microservices | One team. Service boundaries here would buy operational cost and distributed-transaction pain to solve a problem the product does not have. The layering makes extraction cheap later if it is ever warranted. | Microservices |
| A7 | Refresh tokens in the database | Revocation, device management, and reuse detection are impossible with stateless JWTs alone. One indexed lookup per refresh (not per request) is an acceptable price. | Long-lived stateless JWT |
| A8 | CI on Postgres, not SQLite | Tests that pass against a database the product does not run are not evidence. Landed 2026-08-27 and immediately caught 8 orphaned foreign keys SQLite had accepted for months. SQLite was kept briefly as a non-gating fast job; **retired the same day by Phase 2a** (A14). | Keep SQLite for speed |
| A14 | Retire the SQLite job rather than make Part 4 portable | Part 4.3's tables need `DEFAULT uuidv7()`, identity columns, JSONB, `TEXT[]` and a GIN trigram index; the fixtures build the schema with `db.create_all()`, so the job could not reach a test. Making the defaults app-side reverses A13 for a container's benefit and permanently changes every table in Part 4. Skipping the new tables there leaves the fast job blind to the only thing that changed, which is the laxness A8 rules out. Phase 2 item 4 (pgvector/HNSW, struck by A16) and item 5 (partitioning) are not expressible on SQLite under any option, so portability bought here is spent inside the same phase. The cost is real and named: ordinary breakage now surfaces in ~3 minutes rather than ~1. | App-side UUIDs; or skip the new tables on SQLite |
| A15 | Optimistic locking with server-side retry, not a client-supplied version | `profiles.version` is compared and swapped inside the repository, and a losing writer re-reads and re-applies its own merge. Exposing the version in `ProfileDocument` and answering 409 would have been a contract change — 1b shipped a week earlier and the SPA does not send one. An If-Match becomes worth adding when a client actually wants to say "only if I still have what I read"; nothing does yet. | `version` in the envelope + 409 on conflict |
| A13 | Pin CI Postgres to 18, matching Render, not to 16 | Part 4 defaults every `public_id` to `uuidv7()`, which exists only in Postgres 18+. Render was measured at 18.3, so a pg16 runner would fail migrations production accepts — divergence in the opposite direction, and the tempting workaround (generate ids in the app) would be a permanent change to every table made to satisfy a container. `tests/test_database_parity.py` asserts the floor. | `pgvector/pgvector:pg16` |
| A9 | Collapsed routes keep one rate-limit bucket per discriminator | Five submit handlers at 5/min were five budgets; one handler is one, so finishing Work Pulse would have spent FocusType's allowance. The limit bounds provider spend, which is per call to a specific instrument — raising it to 25 buys any one instrument a 5× to fix a bucketing problem. | Raise the limit on the collapsed route |
| A10 | Schema enforcement in a `before_request` hook, not in `@document` | `@document` sits above `@bp.route`, which registers the object it is handed — a wrapper written there never runs. That exact ordering made every `@limiter.limit` in the old `app.py` inert. Resolving the spec from `request.endpoint` makes declaration order irrelevant. | A wrapping decorator |
| A11 | Enforced request models ignore unknown keys rather than forbidding them | Handlers read fields with `data.get(...)` and ignore the rest, and live call sites send more than the schemas name. A 422 on a key the server was going to drop is the "worked yesterday" incident enforcement is supposed to prevent. Closed models still generate a strict client. | `extra="forbid"` on requests |
| A12 | One route per collapsed group, but a response model per discriminator | The five assessments produce genuinely different payloads — `core` deliberately returns no dimension scores at all. A lowest-common-denominator envelope would have to be open enough to hold any of them, which makes it a document that promises nothing. | A shared result envelope |
| A16 | Strike `company_culture_vectors`, pgvector and the HNSW index (Phase 2 item 4) rather than build them | **The index would rank the wrong quantity.** `culture_fit_score` is `max(0, 1 - |company - user|)` per axis (`packages/ml/culture/scoring.py:_score_numeric`) — L1 proximity, where a user at 0.5 and a company at 0.5 score 1.0 on that axis. Cosine measures the angle between whole vectors and is blind to that: it cannot distinguish "matches on every axis" from "is proportionally larger on every axis". Measured over the 2,071-company corpus, ranking by cosine reproduces 3 of the exact scorer's top 10 (recall@10 = 3/10), so an HNSW index would be a fast answer to a different question. **One of the eight dimensions is not a vector component at all.** `work_environment` is Jaccard over an open tag vocabulary, at weight 1.5 — joint-heaviest with `pace` — and set overlap has no fixed-width numeric encoding to put in a `vector(8)`. Any embedding of it changes the score before the index is reached. **There is no performance case either.** The corpus is 2,071 companies and the exact in-Python scan measures 34 ms; ANN exists to avoid scanning millions, and at this size the index build and the recall loss are both pure cost. **And the destination is not a nearest-neighbour problem.** The replacement for `culture_fit_score` is the causal Bayesian model (`match_scoring.py`): a per-pair logistic predictor with a signed directional feature and company-level confounders. It is evaluated per (user, company) pair against a fitted posterior, not looked up by distance — no ANN index serves it, however indexed. P0-2's full scan is still real and still open; the fix is precomputation and caching (Phase 3), not a different index. | Build the vectors and the HNSW index as specified |
| A18 | Strike the Redis cache for match sets (Phase 3's first caching item); cache company detail and the dashboard instead | **The cache would be built around a scorer that is being deleted.** A16 already struck the pgvector work on the finding that `culture_fit_score` is an interim scorer and the causal Bayesian model in `match_scoring.py` is the destination. A cache is not neutral about what it caches: the key would be the user's eight-dimension preference vector plus the lens and the page, invalidated by a Work Pulse submit — and the replacement is a per-pair logistic predictor against a fitted posterior, keyed by (user, company) and invalidated by a model run. Nothing about the first survives into the second, so it would be written, deployed, and deleted inside one phase. **And the performance case is A16's measurement, not a guess:** the exact in-Python scan is 34 ms over 2,071 companies, which is not the number that justifies a cache with an invalidation story. What P0-2 needs is precomputation under the model that replaces the scorer, which is work that cannot start until that model exists. The two reads that *were* cached are the ones whose payloads are stable, large, and read far more often than written: a company's research document is identical for every caller, and the dashboard is three queries behind the screen a user lands on first. **The read-path write removal was done first, and the order matters:** a cached response skips the handler, so it also skips whatever the handler wrote — landing the cache before removing the writes would have hidden their absence behind a cache hit rather than surfacing it. | Build the match-set cache as specified and migrate it when the scorer is replaced |
| A17 | Partition `audit_log`, `match_recommendation` and `rec_action` by range; leave `assessment_response` unpartitioned; widen the foreign keys into `match_recommendation` to a composite `(id, shown_at)` rather than drop them (Phase 2 item 5) | **Decided and dispatched 2026-08-27; implementation in flight — not landed.** The three tables partition on their own event time: `audit_log` on `created_at`, `match_recommendation` on `shown_at`, `rec_action` on `acted_at`. `assessment_response` is excluded even though Part 4.4 lists it as partitioned: it carries `UniqueConstraint(submission_id, item_id)` — one answer per item per submission — and Postgres requires the partition key in every unique constraint on a partitioned table, so partitioning it would force `answered_at` into that constraint. A constraint widened that way stops catching a genuine duplicate answer, and a duplicate is exactly the row `mean_pole`'s denominator cannot tolerate silently double-counting. `assessment_response` is also the lowest-volume of the four candidate tables, so the case for partitioning it was weakest to begin with. Partitioning `match_recommendation` forces its primary key from `id` to `(id, shown_at)` for the same reason — the partition key has to be in the key — which means a bare `id` no longer identifies a unique row. `rec_action`, `outcome_appeal` and `outcome_experienced` each carry a foreign key into `match_recommendation`, so each gained a `shown_at` column and a composite foreign key to `(id, shown_at)` rather than losing the constraint. All three feed the causal model, where a dangling `recommendation_id` is not a visible error — it is silent corruption of training data, a worse failure than the write friction of carrying a second column. `outcome_appeal` keeps its uniqueness on `recommendation_id` alone, not widened to match the new key: one appeal per recommendation is the rule, and widening would let two rows name the same recommendation under different `shown_at` values, only one of which can be about a real event. | Drop the foreign keys into `match_recommendation` instead of widening them, the precedent `audit_events`'s `actor_user_id` already sets in this document |
| A19 | Queue only the three provider-scored instruments; keep one `scoring_jobs` table for both job types; gate the enqueue with the submit's own rate-limit bucket (Phase 3b) | **Three decisions, and the middle one is the only one that looks like a shortcut.** *Which instruments move:* `assessment_service` already records `scored_by` per instrument, and it is the right axis. `work_pulse`, `wpll` and `manager_match` block on an OpenAI call of seconds to tens of seconds and are why the timeout is 120. `core` and `focus_type` score from deterministic tables without opening a socket -- the contract capture measures them at 211 ms and 40 ms *including* the database writes and the HTTP round trip -- and handing a client a job to poll for work that finishes before the poll could be issued costs two extra round trips and a row to reap in order to deliver a slower answer. `core` has a second and stronger reason: it is the instrument carrying the six person dimension scores, it withholds them even from its own respondent (A12), and a job would put them in `scoring_jobs.result` behind a new endpoint that serves them back -- a second place they live, which is exactly what D-01 is for. *One table:* `job_type` discriminates `assessment_scoring` from `path_suggestions`. Both are 'a user's input, a provider call, a result' over one state machine, and splitting them buys two copies of the claim, the reaper, the lost-enqueue sweep and the purge -- four things that must not drift -- to separate two column sets differing by one nullable `kind`. **This is not A12 conceded.** A12 governs the response model per discriminator, and each poll endpoint publishes and validates that instrument's own model; `{kind}` is in the path, so it selects the shape exactly as it does on the submit route. What is shared is where the row lives, not what the wire promises, and `find_for_user` filters on `job_type` and `kind` so a handle cannot be redeemed at another instrument's path. Three check constraints hold the invariants the application could otherwise break -- notably `ck_scoring_jobs_owner_required`, which grants ownerless rows to `wpll` by name because it is the anonymous teaser and its handle is the whole of its authorisation. *The rate limit:* A9's budgets exist to bound provider spend, and moving the call to a worker changes who waits for it, not what it costs. A job endpoint with its own bucket would hand every instrument a second allowance reachable by queueing instead of submitting -- A9 undone without a line of it being edited. The enqueue therefore carries the *same* `shared_limit` expression and the same kind-keyed scope as the submit, so the two count into one per-instrument budget in both directions. `POST /me/path-suggestion-jobs` gains a limit its synchronous `GET` does not have, which is deliberate rather than an oversight in one of them: the `GET` is self-limiting because the caller holds the connection for the whole fan-out and a repeat inside the cache window reaches no provider, and neither property survives an enqueue that returns in milliseconds. *One thing the job endpoints needed that the submits did not:* a poll must not run on the global `50 per hour` default. Measured, both new poll endpoints 429'd after exactly 50 requests before this was set -- a budget a client polling every two seconds exhausts inside one scoring, and one it shares with every other default-limited route the same browser is using. A poll is a single indexed-row read with no provider call, so A9's reasoning does not reach it, and the day cap is restated explicitly because `@limiter.limit` overrides the defaults. **`GET /me/resume-parse-jobs/{job_id}` (3a) has the identical exposure and was deliberately not changed**: it is an existing route, its limit is behaviour no contract test covers, and a parse finishes in seconds where a narrative does not. Recorded here rather than fixed in passing. | Queue all five behind one generic `{status, result}` envelope; a separate table per job type; a fresh rate-limit bucket on the job endpoints |
| A20 | Do not ship SSE work in 3b. **The agent already streams, and the worker class that `gunicorn.conf.py` actually produces is `sync`** -- deliver the finding and leave the change to a deploy decision (Phase 3b) | **The feature was already there, so the deliverable was the risk.** `POST /agent/messages` has returned `text/event-stream` since Phase 1b: one `data: {"chunk": ...}` frame per token, then a `done` frame, with `X-Accel-Buffering: no`. Phase 3's 'SSE for the agent' line item was already met before 3b began. What was not checked is what serves it. **Measured, not inferred:** loading `gunicorn.conf.py` through gunicorn's own config machinery with no command-line flags yields `worker_class=sync, workers=1, threads=1` -- the file sets `timeout` and nothing else. One in-flight request. **And that is the file production loads:** the config's own docstring says Render's start command does not pass `-c`, so gunicorn picks it up from the working directory. `infra/docker/Dockerfile.api` and the compose `api` service both pass `--worker-class gthread` explicitly on the command line (3x8 and 1x4), so the containers are fine and **the one path with no worker class named is the one that reaches users.** There is no `render.yaml` in this repository, so whether the deployed start command overrides it cannot be answered from here -- and a safety property nobody can verify from the source is the finding. Under sync workers a single open agent conversation occupies a whole worker for the length of the turn; under gthread 3x8 the ceiling is 24 concurrent requests *including* streams, which is a capacity number rather than a fix. A demo that works and falls over at twenty users is worse than a written decision, so nothing was changed here. **The options, cheapest first:** (1) pin `worker_class` and `threads` in `gunicorn.conf.py` so the file that reaches production states what the Dockerfile already does, and the two stop disagreeing -- one line, no new dependency, and it makes the ceiling explicit instead of accidental; (2) move to `gevent`, which makes a held stream cost a greenlet rather than a thread, at the cost of auditing monkey-patching against psycopg2 and SQLAlchemy's pooling; (3) serve the stream from its own process or a different path so streams cannot starve the JSON API whatever the API's worker class is; (4) drop SSE and poll, which costs the token-by-token render the endpoint exists for. **Recommendation: (1) now, as a deploy-reviewed change, and (3) before the agent is promoted.** It is also why Phase 3's exit is not simply 'safe once 3c lands': a stream is not a job and cannot be queued, so 120 -> 30 is a question about worker class, not only about whether the queue took the blocking calls. | Build an SSE feature on top of a worker model that cannot serve it; or silently change `worker_class` as part of a phase that was not asked to touch deployment |

## Appendix B — What already works and is not being changed

Called out explicitly so it does not get refactored away by accident:

- CSRF-token-in-body + HttpOnly-JWT-cookie scheme (`AuthContext.tsx`, `app.py`) — correct
  for a cross-site SPA and preserved verbatim.
- `ProxyFix` hop-count resolution and its reasoning about spoofing (`app.py:236`).
- Presigned two-step upload with `ContentLength` binding — resumes never transit Flask.
- Deterministic, offline resume parsing and culture/path scoring. Keeping the ML
  deterministic is a genuine architectural asset: it is testable, cheap, and auditable.
  It moves into `packages/ml`, unchanged in behaviour.
- The causal-model table design (`model_run`, `weight_posterior`, `*_dimension_score`,
  `outcome_*`) — the shape is right; only key types and partitioning change.
- GDPR export/delete and retention cleanup.
- The security work in CI: SHA-pinned actions, dependency audit gates, dependency
  pinning with a written rationale.
