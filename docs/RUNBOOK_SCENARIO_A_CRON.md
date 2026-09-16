# Runbook — Scenario A cron jobs (outbox sweep + retention + backups + corpus refresh)

**Context.** Production is one Render web service (native Python,
`gunicorn app:app`) and Postgres. There is no Redis, no Celery worker, no
beat — every job in `BEAT_SCHEDULE` is dead in production, deliberately
(PROD_READINESS_2026-09_ANSWERS.md, N4). Emails publish **inline** in the
request; when that single inline send fails, only these cron commands retry
it, and only they purge the PII the outbox and job tables accumulate.

Backups are the third command here and answer a different question: the whole
posture before it was Render's 7-day PITR plus one manually rehearsed dump —
nothing scheduled, nothing stored off Render (PROD_READINESS_2026-09.md §6).

All three commands boot through `create_app()`, so fatal config validation and
Sentry apply. A crash in a cron pass is a Sentry event, not just a log line.
The cron services share nothing with the web service except the database, and
row locking (`FOR UPDATE` / `SKIP LOCKED` in `solverah/services/outbox.py`)
makes overlapping runs — cron × cron, or cron × an inline request send — safe:
one row, one send. `pg_dump` joins that picture harmlessly: it takes ACCESS
SHARE, which conflicts only with DDL, so a backup never blocks the app.

## The cron jobs

Create one Render **Cron Job** service per command. The first two are native
Python, same repo, same build command (`pip install -r requirements.txt`), same
environment variables as the web service (fatal config validation checks them
at boot). The third is **docker-runtime** and has credentials of its own — see
its section below.

| Command | Suggested schedule | Runtime | What it does |
|---|---|---|---|
| `flask outbox sweep` | every 5 minutes (`*/5 * * * *`) | native python | Retries unpublished outbox rows, respecting attempts + backoff. |
| `flask retention run` | daily (`30 4 * * *`) | native python | Deletes delivered outbox rows older than 72h, terminal `scoring_jobs` older than 7d, terminal `resume_parse_jobs` older than 30d. |
| `flask backups run` | daily (`30 3 * * *`) | **docker** (`infra/docker/Dockerfile.backup`) | Dumps the database, verifies the artifact, uploads it off-platform, prunes past 30 days. |
| `flask corpus refresh` | quarterly (`0 5 1 1,4,7,10 *`) | native python | Rebuilds the O*NET occupation corpus, writes its zone and cluster sidecars, uploads all four to S3 under a new date-stamped key. **Does not put it into service** — see its section below. |

All three print one JSON summary line and share an exit contract, but they
divide "failure" differently and the difference is deliberate:

- **Sweep and retention** exit **0 on a clean pass even if individual rows
  failed** — a flaky provider is normal and the rows are retried next pass.
- **Backups** has no "individual row". A failed dump, a dump that will not
  verify, or a failed upload **is** the pass failing and exits non-zero. What
  does *not* fail is the prune declining to delete (see below).

**Non-zero from any of them means the pass itself failed** (config, database,
a dump that never happened): that is the signal to alert on.

Backups runs an hour before retention on purpose: tonight's dump then still
contains the rows tonight's purge is about to delete.

**Running these locally:** the Flask CLI loads `.env` *itself*, before
`app.py`'s `SOLVERAH_IGNORE_DOTENV` guard ever runs — so on a developer
machine `flask outbox sweep` picks up the real `RESEND_API_KEY` from `.env`
and will actually send whatever is owed in the database it points at. Set
`FLASK_SKIP_DOTENV=1` (Flask's own switch) as well when you want a dry
environment. Irrelevant in production, which has no `.env` file.

The same trap has a second edge for `flask backups run`: a populated `.env`
containing `BACKUP_S3_*` means a local run uploads to the **real backup
bucket** and prunes it. Use `FLASK_SKIP_DOTENV=1` together with `--local-dir`
(below) for anything that is not a deliberate production backup.

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

## Backups (`flask backups run`)

**What it replaces.** Until this cron, the entire backup posture was Render's
7-day PITR plus one manual `pg_dump` rehearsed on 2026-08-27
([PROD_READINESS_2026-09.md](audits/PROD_READINESS_2026-09.md) §6): nothing
scheduled, and nothing stored anywhere a compromise of the Render account would
not also reach. PITR still covers "we broke the data an hour ago" better than
this does. What this covers is what PITR does not: a window longer than 7 days,
and a copy outside the platform.

**One pass, four steps, in this order:**

1. `pg_dump -Fc --no-owner --no-acl` to a temporary file. Custom format because
   it is what `pg_restore` needs for a selective restore and what the rehearsed
   rollback path (RUNBOOK_DATABASE_ROLLBACK.md, Path A) already uses. `pg_dump`
   takes ACCESS SHARE, which conflicts only with DDL — it does not block the
   app, and no lock-timeout flags are set because none are needed.
2. **`pg_restore --list` on the artifact, before it is uploaded.** This is what
   separates a file from a backup: a dump truncated by a full disk or a dropped
   connection is a plausible-looking file that fails at the only moment anyone
   will ever try it. A dump that does not list is never uploaded, and the pass
   exits non-zero.
3. Upload to the backup bucket under `daily/solverah-<UTC timestamp>.dump`.
4. Prune, per the policy below.

### The JSON line, field by field

```json
{"event": "backups_run", "destination": "s3://solverah-backups",
 "key": "daily/solverah-20260903T033000Z.dump", "dump_bytes": 71234,
 "dump_seconds": 16.4, "duration_seconds": 18.9, "archive_entries": 412,
 "verified": true, "retention_days": 30, "min_retained": 7, "pruned": 1,
 "pruned_keys": ["daily/solverah-20260803T033000Z.dump"],
 "prune_refused": null, "retained_files": 30, "retained_bytes": 2136420}
```

| Field | What it means, and what a change in it is telling you |
|---|---|
| `dump_bytes` | Size of tonight's artifact. Compare to last night's: this is the database's growth curve, sampled daily. A sudden **drop** is the alarming direction — it means less data was dumped, not less disk used. |
| `dump_seconds` / `duration_seconds` | Time in `pg_dump`, and time for the whole pass. Prod was measured at 16.5s/68KB on 2026-08-27. When `dump_seconds` climbs toward the platform's cron time limit, the fix is the tripwire below, not a longer timeout. |
| `archive_entries` | Objects in the artifact's table of contents. It moves when the *schema* moves (a migration), not when rows are added. An unexplained drop means tables are missing from the backup. |
| `retained_files` / `retained_bytes` | What the bucket holds **after** pruning. In steady state `retained_files` sits at 30–31; anything else means the cron has been missing runs. `retained_bytes` is the storage bill and the growth signal the tripwire watches. |
| `pruned` / `pruned_keys` | What this pass deleted. Normally 0 or 1 per day. |
| `prune_refused` | `null` in steady state. A string means the safety rails declined to delete and **the pass still exited 0** — read the string; it says which rail and why. |

### Retention policy, and the rails around it

Keep dailies for **30 days**. That is the whole rule; the interesting part is
what the pruner refuses to do, because this is the one command in the system
that deletes backups. The policy is a pure function
(`solverah/domain/backup_retention.py`) tested exhaustively in
`tests/test_backup_retention.py`.

- **The newest artifact is never deleted.** A retention window and a broken
  cron look identical from inside the rule: if nothing has uploaded for 40
  days, everything is "expired" and the literal reading empties the bucket at
  exactly the moment nothing is making new backups.
- **Nothing is deleted unless this pass's dump verified.** Pruning is only ever
  "make room now that a good copy exists."
- **Nothing is deleted if the bucket listing does not contain the artifact this
  pass just uploaded.** Wrong prefix, wrong bucket, or a store that reported a
  success it did not perform — all three produce a listing that is not a listing
  of these backups, and every decision taken on it is untrustworthy including
  the ones that look reasonable.
- **Below 7 surviving artifacts, nothing is deleted at all** — not "delete down
  to 7". A bucket that thin means something upstream is wrong (a new bucket, a
  changed prefix, a cron that stopped), and none of those are moments to start
  deleting. **This is why the first week in production prunes nothing, every
  night, correctly, at exit 0.** Do not "fix" it.

Each refusal names itself in `prune_refused`, so the JSON line says which rail
fired rather than leaving "pruned: 0" to be interpreted.

`--retention-days` and `--min-retained` exist as flags, but production runs the
defaults; changing them is a decision to record here, not a flag to pass once.

### Credentials are deliberately separate (`BACKUP_S3_*`)

The backup bucket uses `BACKUP_S3_ENDPOINT_URL`, `BACKUP_S3_BUCKET_NAME`,
`BACKUP_S3_ACCESS_KEY_ID`, `BACKUP_S3_SECRET_ACCESS_KEY` — **not** the
application's `S3_*`. The threat is the application's own key being stolen: a
backup that key can read or delete is a copy, not a backup. Consequences,
enforced in `solverah/config.py` and asserted in the suite:

- The group is optional **as a group** and fatal when **partially** set. Three
  of four is a backup destination that looks configured until the restore.
- There is **no fallback** to `S3_*` anywhere. An unconfigured backup cron
  fails its pass loudly rather than writing the database into the resume bucket.
- Reusing the app's **bucket** or the app's **access key id** is fatal at boot.
  Because `Settings` is shared, that fatal applies to the web service too — the
  error names the variable and the fix is a dashboard edit.

The bucket wants its own lifecycle posture on the provider side as well:
versioning and an object-lock / retention policy if the provider offers one, so
that a stolen *backup* key cannot destroy history either. That is a dashboard
fact, not a repo one — record it here when it is set.

### This cron is docker-runtime; the other two are native

`flask backups run` shells out to `pg_dump`, and **the client major must be >=
the server's** (18.3 in production — `pg_dump` refuses a newer server outright).
Render's native Python runtime guarantees no PostgreSQL client at all, so this
service builds `infra/docker/Dockerfile.backup`, which installs
`postgresql-client-18` from PGDG and fails its own build if `pg_dump --version`
is ever below 18. The other two crons need no client and stay on the native
runtime.

Consequences worth knowing before an incident: this service's deploys are image
builds (slower, and they can fail for reasons the other crons cannot), and its
disk holds one artifact at a time in `/tmp` — the retention window lives in the
bucket, not on the container.

### Rehearsing it locally

`--local-dir` writes artifacts to a directory instead of the bucket. Everything
else is real: the dump, the verification, the prune decisions and the deletes.
It is refused when `APP_ENV=production` — a backup on a cron container's
ephemeral disk is not a backup — and it is never selected implicitly.

```bash
FLASK_SKIP_DOTENV=1 \
DATABASE_URL=postgresql://solverah:solverah@localhost:5433/solverah \
JWT_SECRET_KEY=local-development-only-not-a-real-secret \
flask backups run --local-dir /tmp/solverah-backup-rehearsal
```

`FLASK_SKIP_DOTENV=1` is load-bearing here, not decoration: without it the
Flask CLI loads `.env` before the app's own guard and a populated `.env` points
this at the real database and the real bucket.

Measured on the compose database 2026-09-03, for a sense of scale at the small
end: 1.5 MB artifact, 270 archive entries, 0.4–1.7 s per pass. That artifact was
then restored into an empty scratch database and matched the source row for row
(users 27, outbox 26, assessment_submissions 6730) — which is the check
`pg_restore --list` does *not* perform, and the reason the drill named under
"Still not scheduled" below is worth doing periodically against a real artifact
from the bucket.

### Tripwire: when the numbers say "big"

`retained_bytes` and the object-storage bill are the two places growth shows up
first. When either crosses the point where a nightly full dump is uncomfortable
— the dump approaching the cron's time limit, or storage cost becoming a line
item somebody notices — **the documented next step is changing the mechanism to
WAL archiving / incremental backups, not raising the alert threshold and not
shortening the 30-day window.**

Saying that plainly here is the whole point of this section. Both of the easy
moves quietly buy time by reducing what is recoverable, and both are invisible
in the JSON line afterwards: a raised threshold looks like a healthy system, and
a shortened window looks like a smaller bill. Neither is a fix; a full dump per
night simply stops being the right shape at some size, and that is the moment to
change the shape.

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

## Corpus refresh (`flask corpus refresh`)

**Workstream F-8 box 1. Not yet created in the dashboard, and not urgent.** The
artifact only goes stale as fast as O*NET publishes, which is quarterly.

`flask corpus refresh` is four steps invoked in order — it does not
reimplement them, it calls the same commands:

| Step | Command | Cost |
|---|---|---|
| 1 | `flask corpus build` | ~3,073 O*NET requests at 4/s (~13 min), ~$0.01 of `text-embedding-3-small` |
| 2 | `flask corpus zones` | 11 O*NET requests |
| 3 | `flask corpus clusters` | none — reads the artifact, fits k-means locally |
| 4 | `flask corpus publish` | 4 uploads: `.npy`, `.json`, `.zones.json`, `.clusters.json` |

3,084 requests is 6% of O*NET's 50,000/day cap, and the 4/s rate is under their
documented 5/s threshold. Every request in the run passes through one
process-wide limiter, so `--workers` changes latency hiding and never the rate.

### It publishes a candidate. It does not deploy one.

This is the part to understand before running it.

`publish` writes to a **new date-stamped key** and never touches the one in
service. Production keeps serving whatever `SOLVERAH_CORPUS_S3_KEY` names until
somebody changes that variable. A published version is immutable by rule: a
worker caches the 6 MB artifact on first fetch and never re-fetches it, so
replacing the bytes under a key in use would put half the fleet on one corpus
and half on another — with a row-to-code sidecar that may be indexing the other
one's matrix. `publish` refuses a key that already exists with different
content, and skips one that exists with identical bytes (which is what makes a
refresh that died halfway resumable — nothing else bookkeeps progress).

So the loop is: the cron produces a candidate every quarter, and a person
promotes it.

    flask corpus clusters --show --corpus <the new .npy>   # cheapest look
    # then, in Render: set SOLVERAH_CORPUS_S3_KEY to the `corpus_s3_key`
    # the publish echoed, and redeploy the web service

**Rolling back is pointing that variable at the previous key.** No rebuild, no
re-upload; the old objects are still there.

If nobody ever promotes a candidate, production keeps serving a known-good
corpus. That is the right failure mode and it is why this cron is safe to
schedule before anyone is watching it.

### The first upload is a manual, deliberate act

F-1 deliberately stopped at local files so that a corpus is reviewed before it
goes anywhere, and that has not changed: **the first real upload is Sebastian's
trigger.** Nothing in this repo has ever written to S3 with this command.

    # check the plan without touching anything — no S3 call, not even a HEAD
    FLASK_SKIP_DOTENV=1 flask corpus publish --dry-run \
      --corpus <dir holding the .npy> --prefix occupation_retrieval

    # the real thing
    flask corpus publish --corpus <dir> --prefix occupation_retrieval

`--dry-run` is available on `refresh` too, and there it also makes **no**
network call of any kind: it reports the four keys it would write, the value
`SOLVERAH_CORPUS_S3_KEY` would need afterwards, and every environment variable
that is missing. Exit code is non-zero if the run would fail, so it is worth
running before spending thirteen minutes of O*NET.

### Deploy dependency

Until an artifact is in S3 **and** `SOLVERAH_CORPUS_S3_KEY` points at it, Path
Intelligence does not work, and it does not fail at boot to tell you —
`get_corpus()` is lazy and per-worker by design, so the first symptom is a
user's error page:

- `POST /me/path-fit` → `503 corpus_unavailable`
- `POST`/`DELETE /me/path-feedback` → `503 corpus_unavailable`
- the path-suggestions job → `500 Unable to score career paths` (that path has
  no `CorpusUnavailable` branch; it falls into the generic handler)

F-4 tombstoned the old O*NET job-family funnel, so there is no fallback to
degrade to. Order on deploy day: **upload, set the key, verify one worker loads
it, then merge.** The log line to look for is `occupation corpus loaded:`, which
reports the row count, the dimensions and whether the zone sidecar came down.

### Why all four files, every time

`publish` refuses an incomplete set, because a partially populated bucket fails
quietly rather than loudly:

- no `.zones.json` → `zone_max` raises `CorpusUnavailable`, so `adjacent` and
  `fresh_start` fail on **every** request while the bucket looks full
- no `.clusters.json` → every worker pays a 0.7 s k-means fit *and* the
  scikit-learn import, on the 512 MB dyno that OOMed on 2026-09-15

The loader is deliberately more forgiving than this — it treats both sidecars as
optional, because refusing to serve would turn a missing optional file into an
outage. The publisher is the place that stops the bucket from getting into that
state in the first place.

### A scikit-learn bump is a corpus job

`<artifact>.clusters.json` records the scikit-learn and numpy versions that
fitted it (F-8 box 10). `KMeans(random_state=0)` is deterministic for one build
of the library and makes no promise across builds, and two workers holding
different cluster labels would show one user two different first pages on
alternate requests -- with nothing in the logs to say so. So on a version
mismatch the sidecar is refused and every worker refits in-process.

That refit costs ~0.7 s **and** the scikit-learn import, per worker, on the
512 MB dyno that OOMed on 2026-09-15. It is the same cost as having no sidecar
at all, which is what box 9 and box 1 exist to stop.

**So: bumping `scikit-learn` or `numpy` in `requirements.txt` means re-running
`flask corpus clusters` and publishing the new sidecar.** No rebuild, no O*NET,
no spend -- the command reads the artifact and writes one 19 KB file. The
warning in the logs names it:

```
occupation clusters: sidecar ... was fitted with scikit-learn X / numpy Y,
this process runs A / B; ... Re-run `flask corpus clusters` and publish the
sidecar to stop paying for this
```

Measured 2026-09-16 on the 1.7.2 -> 1.9.0 bump this repo just took: the fresh
fit reproduced the old labels **exactly**, 941/941 rows. The guard is therefore
against a hazard that has not fired, kept because the cost of being wrong is
silent and per-worker while the check is one metadata read.

### Running it locally

The same `.env` trap as every other command here, and one extra edge: a
populated `.env` gives a local run real `ONET_API_KEY`, `OPENAI_API_KEY` **and**
`S3_*`, so `flask corpus refresh` on a developer machine will spend thirteen
minutes of the shared O*NET budget and upload to the real app bucket. Use
`FLASK_SKIP_DOTENV=1`, and use `--dry-run` for anything that is not a deliberate
production refresh.

## Still not scheduled in production (known, deliberate)

- `reap_stalled` for resume/scoring jobs: in Scenario A jobs run inline, so a
  stuck `queued`/`running` row takes a process death mid-request. Rare, but a
  row like that polls forever until someone reaps it by hand.
- `retention_cleanup.py` (abandoned intakes, audit-log PII minimization, R2
  orphan sweep): a further cron candidate — it needs the app's S3 credentials
  and was out of scope here.
- Anything Redis/worker-shaped: out of scope by decision — Scenario A stays.
- **`solverah-corpus-refresh` itself.** Codified in `render.yaml` and
  documented above, but not created in the dashboard — and it cannot
  usefully be until a corpus has been published at all. Quarterly work with
  a manual promotion step is also reasonable to run by hand the first time.
- **A restore drill on an artifact this cron produced.** The backup path is
  verified nightly (`pg_restore --list`) but listing an archive is not
  restoring it; the last end-to-end restore was the manual 2026-08-27
  rehearsal, from a manually taken dump. Pulling one artifact out of the bucket
  and restoring it into a scratch database is the thing that turns "we have
  backups" into "we have restores", and it is not scheduled.
