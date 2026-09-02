# API Load Baseline — 2026-09-02

Numbers, not fixes. This is the "what did today look like" snapshot taken before
Phase 5 scale hardening; nothing was optimized, and no application code changed.

> **These are baseline-of-dev numbers, not capacity.** Everything below ran on
> one Windows 11 developer machine under Docker Desktop: API, Postgres, Redis,
> and the load generator all sharing the same host. The primary run uses the
> compose dev command (**1 gunicorn worker × 4 gthread threads, `--reload` on**,
> source bind-mounted). A second run repeats the ladder with the production
> gunicorn geometry from `infra/docker/Dockerfile.api` (**3 workers × 8
> threads, no reload**) on the same dev image — labeled separately. Neither is
> the production image build, the production database size, or production
> hardware. Use these numbers to compare against *later local runs of the same
> recipe*, not to size production.

## Environment

| | |
|---|---|
| Date | 2026-09-02 |
| Commit | `38a5f43` (branch `causal_bayesian_model`, plus the untracked baseline tooling itself) |
| Stack | `docker compose -f infra/docker/compose.yml -f Scripts/load_baseline.override.yml up -d db redis api worker` |
| API | gunicorn gthread; dev run `1w×4t --reload`, prod-geometry run `3w×8t` (`Scripts/load_baseline.prod-config.yml`); gunicorn timeout 30s from `gunicorn.conf.py` |
| DB | pgvector/pg18 in compose, **6 company rows** (5 scorable) unless noted |
| Load tool | `Scripts/load_baseline.py` (asyncio + httpx, closed-loop VUs), venv outside the repo, `pip install -r requirements-dev.txt` |
| Ladder | 1, 5, 10, 25 concurrent users × 60s per step; 25 seeded users |
| Client timeout | 35s (above gunicorn's 30s so worker kills would surface as 5xx/conn errors, not client timeouts) |

**Rate limiter methodology (trap 1).** The limiter is per-IP
(`get_remote_address`, Redis-backed) with global defaults of 50/hour — from one
load-generator IP a naive run measures the limiter, not the API. The limiter
was **not** disabled (no off-switch exists and none was added). Instead the
override file sets `TRUSTED_PROXY_COUNT=1` — an existing, documented knob
(`solverah/factory.py:126-138`) — and the script sends a unique
`X-Forwarded-For` per request, so each request lands in its own limiter bucket.
The limiter's Redis check still runs on every measured request; only the
counters never fill. The `http_429` column stayed **0 for all ~120k requests**,
confirming the spread worked. Real per-IP ceilings to remember when reading
production traffic: 50/hour global default on session/dashboard/matches, 5/min
on register/login and core submissions.

**Error accounting (trap 4).** Every step of every run: 0×429, 0×4xx, 0×5xx,
0 timeouts, 0 connection errors. No gunicorn worker kills were observed —
consistent with the measured 30s-timeout semantics (kills hung processes, not
slow requests); nothing here ever queued anywhere near 30s.

## Dev config (1 worker × 4 threads, `--reload`) — label `dev-1w4t`

### GET /api/v1/auth/session (boot path)

| concurrency | requests | rps | p50_ms | p95_ms | p99_ms |
|---|---|---|---|---|---|
| 1 | 1047 | 17.4 | 54.1 | 73.1 | 107.6 |
| 5 | 1130 | 18.8 | 248.8 | 415.0 | 525.2 |
| 10 | 1314 | 21.8 | 467.4 | 637.5 | 719.5 |
| 25 | 1393 | 22.9 | 1080.5 | 1285.7 | 1394.5 |

### GET /api/v1/me/dashboard (Redis-cached, trap 2)

Cold (cache keys flushed, one sequential hit per user): **p50 13.5ms / p95 16.2ms** over 25 hits.
Warm ladder (cache re-warmed before each step; TTL 300s):

| concurrency | requests | rps | p50_ms | p95_ms | p99_ms |
|---|---|---|---|---|---|
| 1 | 6484 | 108.1 | 8.9 | 12.0 | 14.3 |
| 5 | 10311 | 171.8 | 28.4 | 39.8 | 48.5 |
| 10 | 9854 | 164.1 | 59.2 | 80.2 | 99.5 |
| 25 | 9673 | 160.9 | 152.5 | 192.5 | 223.7 |

### GET /api/v1/me/matches (full scan, P0-2) — 5 scorable companies

| concurrency | requests | rps | p50_ms | p95_ms | p99_ms |
|---|---|---|---|---|---|
| 1 | 3679 | 61.3 | 15.4 | 22.6 | 29.6 |
| 5 | 4037 | 67.2 | 70.4 | 120.3 | 142.7 |
| 10 | 4289 | 71.4 | 135.9 | 183.0 | 237.2 |
| 25 | 4250 | 70.5 | 343.0 | 450.0 | 527.7 |

### GET /api/v1/me/matches at 499 companies — label `dev-1w4t-synthetic500`

The real table holds 6 rows, too few for the P0-2 scan to show. For this run
only, 494 synthetic companies with random culture values were inserted
(`INSERT … generate_series`, deleted afterward) to measure the scan at a
plausible catalog size:

| concurrency | requests | rps | p50_ms | p95_ms | p99_ms |
|---|---|---|---|---|---|
| 1 | 1238 | 20.6 | 41.2 | 92.2 | 172.8 |
| 5 | 1370 | 22.8 | 190.6 | 370.6 | 436.9 |
| 10 | 1640 | 27.2 | 370.8 | 505.6 | 559.1 |
| 25 | 1588 | 26.0 | 942.8 | 1195.7 | 1336.6 |

### POST /api/v1/assessments/core/submissions (sync write)

| concurrency | requests | rps | p50_ms | p95_ms | p99_ms |
|---|---|---|---|---|---|
| 1 | 473 | 7.9 | 120.4 | 162.5 | 251.9 |
| 5 | 522 | 8.6 | 516.3 | 898.1 | 991.1 |
| 10 | 502 | 8.2 | 1207.2 | 1550.2 | 1993.6 |
| 25 | 516 | 8.1 | 2971.0 | 3606.2 | 3857.7 |

## Production gunicorn geometry (3 workers × 8 threads, no reload) — label `prodcfg-3w8t`

Same dev image and bind mount; only the worker geometry matches
`Dockerfile.api`. 6 companies. Cold dashboard: p50 21.4ms / p95 32.2ms
(keys had expired naturally; genuinely cold).

| scenario | conc | requests | rps | p50_ms | p95_ms | p99_ms |
|---|---|---|---|---|---|---|
| session | 1 | 1145 | 19.1 | 49.6 | 64.0 | 84.6 |
| session | 5 | 2104 | 35.0 | 139.6 | 220.2 | 292.7 |
| session | 10 | 2700 | 44.9 | 189.1 | 403.8 | 515.6 |
| session | 25 | 3179 | 52.6 | 458.2 | 649.3 | 747.2 |
| dashboard (warm) | 1 | 6650 | 110.8 | 8.6 | 12.5 | 15.3 |
| dashboard (warm) | 5 | 13384 | 223.1 | 21.0 | 33.8 | 43.9 |
| dashboard (warm) | 10 | 12726 | 212.1 | 44.8 | 70.3 | 88.6 |
| dashboard (warm) | 25 | 13196 | 219.8 | 110.6 | 160.1 | 196.2 |
| matches (5 cos) | 1 | 3815 | 63.6 | 15.0 | 20.7 | 27.8 |
| matches (5 cos) | 5 | 9332 | 155.5 | 30.7 | 46.0 | 57.5 |
| matches (5 cos) | 10 | 9802 | 163.3 | 58.9 | 87.9 | 107.2 |
| matches (5 cos) | 25 | 10393 | 172.9 | 140.9 | 200.2 | 242.4 |
| submit | 1 | 596 | 9.9 | 97.7 | 109.6 | 208.1 |
| submit | 5 | 1194 | 19.8 | 264.8 | 363.0 | 422.3 |
| submit | 10 | 1565 | 26.0 | 418.3 | 557.2 | 618.2 |
| submit | 25 | 1346 | 22.2 | 1042.7 | 1899.8 | 2324.6 |

## Reading

On the dev config the knee is essentially at the door: every scenario's
throughput is flat from 1 VU up (session ~20 RPS, matches ~70, submit ~8) and
added concurrency only buys queueing — session p50 goes 54ms → 1.08s from 1 to
25 VUs on constant RPS, which is a single saturated worker, not the endpoints
degrading. With the production geometry the knee moves out to roughly 5–10 VUs
and throughput lands at ~2.5–3× dev (session 53 RPS, warm dashboard 220,
matches 173, submit 26); beyond 10 VUs it is queue growth again. The slowest
path by an order of magnitude is the surviving sync write,
`POST /assessments/core/submissions`: ~100–120ms alone, 8 RPS ceiling on dev
config with p50 near 3s at 25 VUs — when scale hardening starts, this path
saturates first. P0-2's scan does not show at today's table size (5 scorable
companies, 15ms p50) but is decisively there once the table has rows: at 499
companies the same endpoint is ~2.7× slower per request at 1 VU (41ms) and
sits near 1s p50 at 25 VUs on dev config — the cost is linear in company count
and will track catalog growth one-for-one until the scan goes. One quieter
finding: `GET /auth/session`, the hottest endpoint there is, is the slowest
*read* at ~50ms p50 uncontended — 6× the cached dashboard and 3× the 5-company
scan — so the boot path is worth a look alongside P0-2. The Redis cache earns
its keep but modestly at this profile size: cold dashboard ~13–21ms vs warm
~9ms.

## Reproducing

```
docker compose -f infra/docker/compose.yml -f Scripts/load_baseline.override.yml up -d db redis api worker
docker compose -f infra/docker/compose.yml exec api pip install openpyxl
docker compose -f infra/docker/compose.yml exec -e PYTHONPATH=/app/company_culture_LLM api \
    python -m company_culture_LLM.seed_from_generated_xlsx
python -m venv <somewhere-OUTSIDE-the-repo>\loadenv
<loadenv>\Scripts\pip install -r requirements-dev.txt
<loadenv>\Scripts\python Scripts\load_baseline.py --label dev-1w4t
# prod geometry:
docker compose -f infra/docker/compose.yml -f Scripts/load_baseline.override.yml ^
    -f Scripts/load_baseline.prod-config.yml up -d api
<loadenv>\Scripts\python Scripts\load_baseline.py --label prodcfg-3w8t
```

Notes for the next runner:

- The venv must live **outside** the repo — guard tests rglob the tree.
- The script refuses any non-loopback target (API, DB, and Redis URLs) with no
  override flag, same idiom as `tests/conftest.py::_refuse_non_local_database`.
- `company_culture_LLM/seed_from_generated_xlsx.py` has bit-rotted twice over:
  `openpyxl` is not in the api image, and its `from company import …` predates
  `company.py` moving into `company_culture_LLM/` (hence the `PYTHONPATH`
  shim). Separately, **14 of the 20 profile xlsx files parse their company
  name as "Unknown"** and collapse into one unscorable row — only the 5 bank
  profiles seed correctly. That parser is application code and was left alone
  this round; fixing it is a prerequisite for baselining matches at the real
  intended catalog size.
- Seeding is idempotent: rerunning reuses the `loadbase-NNN@example.test`
  users. The compose DB is disposable; submissions accumulate rows.
- `culture_preferences` cannot be set over HTTP (`clean_profile_data` drops
  it), so the script writes it into `profiles.extra` directly — that is seed
  plumbing, not part of any measured path.
