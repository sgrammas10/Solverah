# Solverah — System Architecture

**Status:** Target architecture v2 · **Owner:** Engineering · **Last revised:** 2026-08-22

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

- Table is literally named `user` — a reserved word in Postgres, quoted everywhere.
- 32-bit integer PKs on append-only tables (`audit_log`, `rec_action`,
  `assessment_response`, `match_recommendation`) — these overflow, and they are
  exposed directly in URLs (`/api/companies/<int:company_id>`), so they enumerate.
- No partitioning on any append-only table.
- No `updated_at` triggers — `server_default=now()` never updates on UPDATE for several
  tables, so `updated_at` is really a second `created_at`.
- `AuditLog` has an FK to `user.id`, which couples the highest-volume table to the
  identity table and blocks moving it to cheaper storage.

#### P1-9 · Test/prod database divergence

`tests/conftest.py` runs SQLite; production is Postgres. JSON operators, constraint
enforcement, transaction isolation, `citext`, partial indexes, and concurrency
semantics all differ. Every one of the 490 passing tests is passing against a database
the product does not use.

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
│ Postgres 16 primary                      │
│  · pgvector (culture / skill ANN)        │──► read replicas (analytics, heavy reads)
│  · monthly partitions on append-only     │
│  · logical replication → warehouse       │
└──────────────────────────────────────────┘
```

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
| **T2** | 1M | pgvector HNSW for matching. Precomputed match sets refreshed by workers, served from Redis. Move `audit_events` + `rec_actions` to a columnar store via logical replication. |
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
CREATE TYPE user_role   AS ENUM ('job_seeker','recruiter','admin');
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

-- The 8 culture dimensions as a single indexed vector.
CREATE TABLE company_culture_vectors (
    company_id   BIGINT PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
    vec          vector(8) NOT NULL,   -- pgvector; dimension order pinned in code
    dims_version TEXT   NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_culture_vec_hnsw ON company_culture_vectors
    USING hnsw (vec vector_cosine_ops) WITH (m = 16, ef_construction = 64);

CREATE TABLE user_culture_vectors (
    user_id      BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    vec          vector(8) NOT NULL,
    dims_version TEXT   NOT NULL,
    derived_from BIGINT,               -- assessment_submissions.id
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Top-K culture matching becomes one indexed query instead of a full scan:

```sql
SELECT c.id, c.public_id, c.name, c.industry,
       1 - (v.vec <=> :user_vec) AS fit_score
FROM   company_culture_vectors v
JOIN   companies c ON c.id = v.company_id AND c.status = 'active'
WHERE  v.dims_version = :dims_version
ORDER  BY v.vec <=> :user_vec
LIMIT  :k;
```

`O(all companies)` in Python becomes `O(log n)` in Postgres. Results are cached in
Redis under `match:v1:{user_id}:{dims_version}` and invalidated when the user's vector
changes (assessment completion) or the dimension set is versioned up.

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

Today's 38 handlers, restated. `→` marks the endpoint(s) each one becomes.

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
| POST | `/refresh` | *new* — rotates the refresh token, enables revocation |
| GET | `/session` | *new* — cheap session probe, replaces `GET /api/profile` for auth restore |
| POST | `/email/verify` | `POST /api/confirm-email` |
| POST | `/email/verify/resend` | `POST /api/resend-confirmation` |
| POST | `/password/forgot` | `POST /api/request-password-reset` |
| POST | `/password/reset` | `POST /api/verify-password-reset` |

`GET /auth/session` is the fix for P0-3: it returns `{ user, csrf_token, flags }` from a
replica read with an ETag and **writes nothing**. The heavy `GET /api/profile` is no
longer on the app-boot path.

**Me** — `/api/v1/me`

| Method | Path | Replaces |
|---|---|---|
| GET / PATCH | `/` | identity half of `GET\|POST /api/profile` |
| GET / PATCH | `/profile` | profile half of the same endpoint |
| GET / POST | `/experiences` | `profileData.experience[]` inside the blob |
| PATCH / DELETE | `/experiences/{id}` | — |
| GET / POST | `/educations`, `/educations/{id}` | `profileData.education[]` |
| GET / PUT | `/skills` | `PATCH /api/profile/skills/proficiency` |
| PATCH | `/career-status` | `PATCH /api/profile/career-status` |
| GET | `/dashboard` | `GET /api/dashboard-data` |
| POST | `/resumes` | `POST /api/profile/resume/presign` → returns an upload ticket |
| POST | `/resumes/{id}/complete` | `POST /api/profile/resume/finalize` → **202**, parsing goes async |
| GET | `/resumes/{id}/download-url` | `GET /api/profile/resume-url` |
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
| GET | `/assessments/{kind}/submissions/{id}` | — |
| GET | `/me/assessments/{kind}/result` | `/api/work-pulse/results`, `/api/manager-match/results` |

`{kind}` ∈ `core · work_pulse · wpll · focus_type · manager_match`. Five near-identical
submit handlers collapse into one, with the differences living in `assessment_forms.definition`
and a scoring strategy per kind. Adding assessment #6 becomes a data change.

**Companies** — `/api/v1/companies`

| Method | Path | Replaces |
|---|---|---|
| GET | `/companies?cursor=&limit=&q=&industry=` | *new* — paginated, faceted |
| GET | `/companies/{public_id}` | `GET /api/companies/<int:id>` — no longer enumerable |

**Matching** — `/api/v1/me/matches`

| Method | Path | Replaces |
|---|---|---|
| GET | `/me/matches?cursor=&limit=&lens=culture` | `GET /api/company-lens/matches` — now index-backed and cached |
| POST | `/me/matches/{id}/actions` | *new* — records `rec_action` (view/save/dismiss/apply) |
| GET | `/me/recommendations` | `GET /api/recommendations` |
| POST | `/me/recommendations/refresh` | `POST /api/recommendations` → **202** + job handle |

**Intelligence** — `/api/v1/me`

| Method | Path | Replaces |
|---|---|---|
| GET / PUT | `/me/path-preferences` | `POST /api/intelligence/path-preferences` |
| GET | `/me/path-suggestions` | `GET /api/intelligence/path-suggestions` — served from cache; a miss returns 202 and enqueues |

**Agent** — `/api/v1/agent`

| Method | Path | Replaces |
|---|---|---|
| POST | `/agent/messages` | `POST /api/agent/chat` — SSE, streamed, on a thread worker |

**Intake** (public, aggressively rate-limited) — `/api/v1/intake`

| Method | Path | Replaces |
|---|---|---|
| POST | `/early-access` | `POST /api/early-access-request` |
| POST | `/submissions` | `POST /api/intake/finalize` |
| POST | `/submissions/{id}/resume-ticket` | `POST /api/intake/presign` |
| POST | `/submissions/{id}/claim` | `/api/intake/create-account`, `/api/intake/sign-in`, `/api/intake/link-account`, `/api/intake/save-to-account` |
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
  | Public intake / quiz-preview | 10 / hour per IP |
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
in place. The 490-test suite is the ratchet — it stays green at every step.

### Phase 0 — Foundation *(additive only, zero behaviour change)*

- `create_app()` factory, typed and validated `Settings`, `extensions.py`.
- Problem Details error handlers; `/healthz`, `/readyz`, `/metrics`.
- Structured JSON logging with request IDs.
- SQLAlchemy engine options: `pool_pre_ping`, sized pool, statement timeout.
- Redis-backed rate limiting and cache.
- `Dockerfile`, `compose.yml`, `Makefile`, `.dockerignore`.
- CI switched to Postgres; `pytest-postgresql` or a service container.

**Exit:** existing `app.py` still serves every route; new infrastructure runs alongside.

### Phase 1 — API restructure

- Split `app.py` into `api/v1/*` blueprints, `services/*`, `repositories/*`, `domain/*`.
- Pydantic schemas on every request and response; OpenAPI generated.
- Legacy `/api/*` paths kept as thin 308 redirects (or aliases) into `/api/v1/*` for one
  release, then removed after frontend cutover.
- Extract `packages/ml`; delete the `sys.path` and `importlib` loading.

**Exit:** `app.py` is a 20-line entrypoint. Every route has a schema and a test.

### Phase 2 — Data model v2

Expand/contract, one aggregate at a time, dual-write then backfill then cut over:

1. `users` (rename from `user`, add `public_id`, `status`, `version`).
2. `profiles` + `profile_experiences` + `profile_educations` + `profile_skills`
   — dual-write from `profile_data`, backfill, verify, then stop reading the blob.
3. `assessment_*` unification.
4. `company_culture_vectors` + pgvector + HNSW.
5. Partition `audit_events`, `assessment_responses`, `match_recommendations`, `rec_actions`.

**Exit:** no query reads `profile_data`; culture matching is index-backed.

### Phase 3 — Async and caching

- Celery + Redis broker; queues `default · llm · email · scoring · maintenance`.
- Move off the request path: resume parsing, assessment scoring, path suggestions,
  match precomputation, all email.
- Transactional outbox for email and domain events.
- Redis cache for match sets, company detail, dashboards; invalidation by key on write.
- SSE for the agent; `202 + job handle` for everything else that is slow.

**Exit:** no handler makes a blocking third-party call. Gunicorn timeout drops 120 s → 30 s.

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

- The *generated* typed client (there is no OpenAPI document until Phase 1).
- MSW handlers generated from the contract — hand-write them in the meantime.
- The `/api/*` → `/api/v1/*` path cutover.

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
| A2 | Postgres for everything, including vectors | pgvector handles 8-dim culture vectors and millions of rows comfortably. One datastore to operate, back up, and reason about. Revisit at high-dimensional embedding scale. | Pinecone / Weaviate |
| A3 | Decompose `profile_data` rather than index the JSONB | GIN on JSONB fixes reads but not lost updates, not validation, and not row bloat. The blob is a correctness problem, not only a performance one. | JSONB + GIN |
| A4 | Celery over a bespoke thread pool | Durable queues, retries, scheduling, and observability for free. In-process threads lose work on deploy. | `ThreadPoolExecutor` |
| A5 | Cursor pagination, never offset | `OFFSET 100000` scans 100k rows and skews under concurrent writes. | Offset/limit |
| A6 | Modular monolith, not microservices | One team. Service boundaries here would buy operational cost and distributed-transaction pain to solve a problem the product does not have. The layering makes extraction cheap later if it is ever warranted. | Microservices |
| A7 | Refresh tokens in the database | Revocation, device management, and reuse detection are impossible with stateless JWTs alone. One indexed lookup per refresh (not per request) is an acceptable price. | Long-lived stateless JWT |
| A8 | CI on Postgres, not SQLite | Tests that pass against a database the product does not run are not evidence. | Keep SQLite for speed |

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
