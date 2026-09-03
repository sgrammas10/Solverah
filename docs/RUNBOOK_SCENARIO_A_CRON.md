# Runbook — Scenario A cron jobs (outbox sweep + retention)

**Context.** Production is one Render web service (native Python,
`gunicorn app:app`) and Postgres. There is no Redis, no Celery worker, no
beat — every job in `BEAT_SCHEDULE` is dead in production, deliberately
(PROD_READINESS_2026-09_ANSWERS.md, N4). Emails publish **inline** in the
request; when that single inline send fails, only these cron commands retry
it, and only they purge the PII the outbox and job tables accumulate.

Both commands boot through `create_app()`, so fatal config validation and
Sentry apply. A crash in a cron pass is a Sentry event, not just a log line.
The cron service shares nothing with the web service except the database, and
row locking (`FOR UPDATE` / `SKIP LOCKED` in `solverah/services/outbox.py`)
makes overlapping runs — cron × cron, or cron × an inline request send — safe:
one row, one send.

## The two cron jobs

Create one Render **Cron Job** service per command. Same repo, same build
command (`pip install -r requirements.txt`), same environment variables as the
web service (fatal config validation checks them at boot).

| Command | Suggested schedule | What it does |
|---|---|---|
| `flask outbox sweep` | every 5 minutes (`*/5 * * * *`) | Retries unpublished outbox rows, respecting attempts + backoff. |
| `flask retention run` | daily (`15 4 * * *`) | Deletes delivered outbox rows older than 72h, terminal `scoring_jobs` older than 7d, terminal `resume_parse_jobs` older than 30d. |

Both print one JSON summary line (counts of what they did) and exit **0 on a
clean pass even if individual rows failed** — a flaky provider is normal and
the rows are retried next pass. **Non-zero means the pass itself crashed**
(config, database, bug): that is the signal to alert on.

**Running these locally:** the Flask CLI loads `.env` *itself*, before
`app.py`'s `SOLVERAH_IGNORE_DOTENV` guard ever runs — so on a developer
machine `flask outbox sweep` picks up the real `RESEND_API_KEY` from `.env`
and will actually send whatever is owed in the database it points at. Set
`FLASK_SKIP_DOTENV=1` (Flask's own switch) as well when you want a dry
environment. Irrelevant in production, which has no `.env` file.

## Retry math (`flask outbox sweep`)

`MAX_ATTEMPTS = 8` with backoff by row age (`outbox.RETRY_MIN_AGE`): a row
must be 0, 0, 15m, 45m, 2h, 4h, 8h, 16h old before tries 1–8. With a 5-minute
cadence the tries land at roughly **0 (inline), 5m, 15m, 45m, 2h, 4h, 8h, 16h**
— so a Resend outage shorter than ~16 hours never permanently parks a row (the
old flat design parked rows after ~4 minutes of outage). After try 8 the row
**parks**: still in the table, `published_at IS NULL`,
`attempts = MAX_ATTEMPTS`, ignored by the sweep, visible on `/readyz`.

## Retention windows (`flask retention run`)

Deletion requires **both** conditions; nothing else is ever touched, and no
foreign key references any of the three tables (verified — deletes cannot
cascade).

| Table | Deleted when | Window (flag) | Why this window |
|---|---|---|---|
| `outbox` | delivered AND older | 72h (`--outbox-hours`) | addresses + one-time codes; OTPs expire in 15 min; 72h keeps a few days of "did it send?" forensics on a daily cadence |
| `scoring_jobs` | terminal AND older | 7d (`--scoring-days`) | matches `scoring_jobs.PURGE_DAYS`; results live in `assessment_submissions` |
| `resume_parse_jobs` | terminal AND older | 30d (`--resume-days`) | SECURITY_AUDIT_2026-09 #7 (name-bearing filenames, purgeless); 30d support window |

Pending and **parked** outbox rows are never purged — they are email still
owed. Queued/running job rows are never purged — old ones are the reapers'
(`reap_stalled`) to fail first, and those reapers still have no production
scheduler (see "Still not scheduled" below).

## When `/readyz` shows `parked > 0`

`GET /readyz` reports `"outbox": {"pending": N, "parked": M}`. `pending`
clears on its own once sweeps run. `parked` never does — each parked row is
someone's email that failed 8 spaced tries and needs a human:

1. **Look at the rows:**
   `SELECT id, topic, created_at, attempts FROM outbox WHERE published_at IS NULL AND attempts >= 8;`
2. **Find why they failed:** search logs / Sentry for
   `outbox_publish_failed` with those `outbox_id`s. Sixteen-plus hours of
   failure is rarely a blip: expect a dead `RESEND_API_KEY`, an unverified
   sender domain, a provider-rejected address, or a topic an old deploy wrote
   that this one no longer handles.
3. **Fix the cause, then re-arm the rows** so the next sweep retries them:
   `UPDATE outbox SET attempts = 0 WHERE published_at IS NULL AND attempts >= 8;`
   (or per-id). If the payload can never send (bad address), the code inside
   is long-expired — the user will trigger a fresh one; delete the row
   deliberately rather than letting it sit.
4. `pending` that grows sweep after sweep means the sweep cron itself isn't
   running or is crashing — check the cron service's run history and exit
   codes first.

## Still not scheduled in production (known, deliberate)

- `reap_stalled` for resume/scoring jobs: in Scenario A jobs run inline, so a
  stuck `queued`/`running` row takes a process death mid-request. Rare, but a
  row like that polls forever until someone reaps it by hand.
- `retention_cleanup.py` (abandoned intakes, audit-log PII minimization, R2
  orphan sweep): a third cron candidate — it needs S3 credentials and was out
  of scope here.
- Anything Redis/worker-shaped: out of scope by decision — Scenario A stays.
