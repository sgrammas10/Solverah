# Proposal — split Celery into its own Render service

**Created 2026-09-16, deferred the same day.** See Status below: this is the
plan of record for a change that is **not** being made yet. Nothing here is
built, and nothing should be provisioned without re-opening §6 #1.

**Why now.** The 2026-09-15 production OOM
(`docs/PATH_INTELLIGENCE_REDESIGN.md` §1.3) put a memory-heavy scoring job
in the same process as live HTTP traffic. That is not a tuning accident — it is
the current topology, and it will recur with any other heavy job until the
topology changes.

**Status, 2026-09-16: DEFERRED by Sebastian.** Not rejected — deferred, and the
reason matters. Dropping `workers` 3 -> 1 the same day (`gunicorn.conf.py`)
solved the memory problem this proposal was written to solve, for free:

    baseline     ~444 MB (3 x 148)  ->  148 MB
    cache budget       8 MB         ->  ~179 MB
    footprint    over the ceiling   ->  ~327 MB of 512 MB
    DB conns          45 / 90       ->  15 / 30

What is left unsolved is **isolation**: a heavy scoring job still shares the
process with live traffic, so on 0.5 CPU it can still degrade concurrent
requests — it just no longer kills the box. A smaller problem than the one that
prompted this, so the spend waits until traffic makes it hurt.

**This document stays the plan of record for when it does.** Everything in
§1-§5 and §7 was verified against production and remains accurate; only the
urgency changed. Revisit when scoring latency starts showing up in live request
times, or when the web tier needs upgrading anyway — at which point compare
option D against simply buying more web.

---

## 1. What is actually true today

Established from production logs on 2026-09-16, not from the source's
assumptions:

    "event":"celery_configured","broker":"redis","eager":true

**Both.** This matters, and it is the opposite of what the incident writeup
assumed.

- **Redis is configured and working as a Celery broker.** `REDIS_URL` is set.
- **`CELERY_TASK_ALWAYS_EAGER` is explicitly ON.** Since `is_testing` is False
  in production (`config.py:316`) and the broker is set, `celery_eager_default`
  computes to **False** (`config.py:411`). The observed `true` can only come from
  the variable being set truthy in the Render dashboard. Someone turned it on
  deliberately — almost certainly because there is no worker, so without it
  nothing would run at all.
- The matching `configuration_warning` fires **on every boot** (14 of 14 across
  2026-09-14/15) and has been passing unread.

**Consequence: this is a much smaller change than "stand up a queue."** The
broker exists, is reachable, and is already connected. What is missing is a
process that consumes it.

**Also true, and not codified:** `CELERY_TASK_ALWAYS_EAGER` does not appear in
`render.yaml`'s `envVarGroups`. It is dashboard-only config governing production
behaviour — the third instance of the drift class `gunicorn.conf.py` already
documents twice (the 120s→30s timeout lag; the implicit `workers=1`). Whatever
is decided here, that variable should be codified.

---

## 2. The entrypoint already exists

`solverah/worker.py` is written, documented, and ready. Its own docstring gives
the command:

    celery -A solverah.worker:celery_app worker \
        --queues=default,llm,email,scoring,maintenance --concurrency=4

It already handles the `sys.path` trap that makes a worker "boot perfectly and
then fail every task that reaches a scorer" (see its REPO_ROOT comment — that
was found the hard way in Phase 3b). It honours `SOLVERAH_IGNORE_DOTENV` the
same way `app.py` does.

**Nothing needs to be written to make a worker run.** This is a provisioning and
configuration change, not a development one.

---

## 3. The part that is easy to miss: beat is a second process

`BEAT_SCHEDULE` (`solverah/infra/queue.py:116`) holds five entries:

| task | schedule |
|---|---|
| `solverah.outbox.drain` | 30 s |
| `solverah.outbox.purge_published` | 1 h |
| `solverah.resume.sweep_jobs` | 5 min |
| `solverah.scoring.sweep_jobs` | 5 min |
| `solverah.scoring.purge_jobs` | 6 h |

The module docstring is explicit about why this matters: *"A deployment with
workers and no beat process still delivers most email — and loses exactly the
ones that failed the first time, which are the ones the outbox exists for."*

**Beat must be exactly one process.** `infra/docker/compose.yml` runs `--beat`
embedded and says why that is a laptop-only choice: *"production runs `celery
beat` as its own single process, because two workers each with `-B` schedule
every task twice."*

### The cost-saving exception, stated precisely

The "two workers each with `-B`" hazard requires **two or more** workers. With
**exactly one** worker, `--beat` embedded is safe and correct, and saves a whole
Render service. That is a legitimate launch-scale configuration, provided it is
written down that adding a second worker **must** be accompanied by extracting
beat into its own service. Getting that order wrong double-schedules every sweep.

### Overlap with the existing crons

`render.yaml` defines `solverah-outbox-sweep` (`flask outbox sweep`, every 5 min)
and `solverah-retention`. Their header says exactly why they exist: *"the job
that eager mode (no Redis, no worker) otherwise never runs."* **They are a
substitute for beat.**

Once beat runs, `solverah.outbox.drain` (30 s) and `flask outbox sweep` (5 min)
do the same work. `cli.py` states the sweep is idempotent and shares the outbox
sweep's contract, so double-running is wasteful rather than dangerous — but it
should be a decision, not an accident. See §6 #3.

---

## 4. Two risks that will bite on day one

### 4.1 ⚠ Fork safety — unhandled, and the repo already knows this trap

`solverah/worker.py` calls `create_app()` **at module scope**, so the parent
process builds the SQLAlchemy engine before Celery forks. Celery's default pool
on Linux is **prefork**. Children inherit the parent's live pooled connections
and two processes then use the same socket.

This is the *identical* failure `gunicorn.conf.py` refuses `preload_app` over,
in its own words: *"intermittent 'server closed the connection unexpectedly'
errors which are far harder to diagnose than the problem being solved... It
needs a `post_fork` calling `db.engine.dispose()`."*

**I searched the repo: there is no `worker_process_init` handler and no
`engine.dispose()` outside `tests/conftest.py`.** `compose.yml` sets no `--pool=`
either, so the laptop worker has the same exposure and has simply not been run
hard enough to show it.

Three ways out, cheapest first:

1. **`--pool=threads`** — no fork at all, and it mirrors the `gthread` choice
   already made on the web side for the same class of reason. Recommended for
   the first deployment.
2. `--pool=solo` — one process, simplest, lowest throughput.
3. A `worker_process_init` signal handler calling `db.engine.dispose()` — the
   proper fix, and the one to build if prefork is ever wanted. Should land with
   tests of its own, exactly as the `preload_app` note says.

**Do not deploy a prefork worker without one of these.**

### 4.2 ⚠ Database connection ceiling

`DB_POOL_SIZE` defaults to 10 and `DB_MAX_OVERFLOW` to 5 (`config.py:444-445`),
so **15 connections per process**. `gunicorn.conf.py` already does this
arithmetic for the web tier and states Render's ceiling:

    web: 1 worker x 15 = 15    (30 during a rolling deploy overlap)
    Render max_connections = 103

(Was 45/90 at `workers = 3`. Dropping to 1 on 2026-09-16 is what left this
much headroom — a worker service now fits without re-running the arithmetic.)

A prefork Celery worker at `--concurrency=4` is **four child processes**, each
with its own engine and pool: `4 x 15 = 60`. Added to a rolling web deploy that
is 90 against a ceiling of 103 — **a failed deploy, not a slow one** — at the
old `workers = 3`. At 1 worker the same sum is 60 + 30 = 90: survivable, but
with almost nothing spare, and only because the web tier shrank.

`--pool=threads` (§4.1) collapses this to one pool of 15 for the whole worker,
which is the second independent reason to prefer it. If prefork is ever used,
`DB_POOL_SIZE` must be lowered for the worker service specifically.

---

## 5. Proposed topology and the render.yaml diff

Minimum viable, launch-scale — **one worker, embedded beat, threads pool**:

```yaml
  # ------------------------------------------------------------- worker
  # Consumes the queues the web service currently runs inline.
  # `--pool=threads`: no fork, so no inherited SQLAlchemy connections
  # (docs/CELERY_WORKER_SPLIT.md §4.1) and one pool of 15, not four.
  # `--beat`: SAFE ONLY WHILE THIS IS THE SINGLE WORKER. A second worker
  # must be accompanied by extracting beat into its own service, or every
  # sweep is scheduled twice (§3).
  - type: worker
    name: solverah-worker
    runtime: python
    branch: main
    buildCommand: pip install -r requirements.txt
    startCommand: >
      celery -A solverah.worker:celery_app worker
      --queues=default,llm,email,scoring,maintenance
      --pool=threads --concurrency=4 --beat --loglevel=INFO
    envVars:
      - fromGroup: solverah-prod
      - key: DATABASE_URL
        fromDatabase:
          name: solverah-db
          property: connectionString
```

And, in `envVarGroups.solverah-prod`, codifying what is currently dashboard-only:

```yaml
      # Must be FALSE once solverah-worker exists. True today, set by hand in
      # the dashboard, because with no worker nothing would run at all.
      # Flip order is load-bearing: see docs/CELERY_WORKER_SPLIT.md §7.
      - key: CELERY_TASK_ALWAYS_EAGER
        sync: false
```

**Note the `preDeployCommand` is deliberately absent.** `flask db upgrade` runs
once per deploy on the web service; a second service running it concurrently is
a race on the migration lock.

**Memory sizing.** The worker is where the embedding cache will now live — it
inherits the very problem that caused this incident. Size it accordingly, and
**land the interim cache fix before creating this service**, or the leak simply
relocates.

---

## 6. What this costs, and the open decisions ⚑

**Cost shape, not a quote.** A Render background worker is a separate paid
instance priced like a web service at the same tier. This proposal adds **one**.
Confirm the current per-instance price and pick the plan in the dashboard — do
not take a number from this document.

The real cost question is not the worker's price but the web service's: after
the split, scoring/LLM/email work leaves the web dyno entirely, which may mean
the **web** tier can stay where it is rather than being upgraded to survive the
next scoring job. Weigh those together, not separately.

| # | Decision |
|---|---|
| 1 | ~~**Approve the spend at all?**~~ **DEFERRED — Sebastian, 2026-09-16.** `workers = 1` removed the memory pressure for free; what remains is isolation, not survival. Dashboard prices that day: Starter (0.5 CPU / 512 MB) $7/mo, 1 CPU / 2 GB $25/mo. When revisited, the worker wants the 2 GB tier, not Starter — it is where the embedding cache would live. |
| 2 | **One worker with `--beat`, or two services?** One is cheaper and correct *today*; the constraint in §3 must be recorded so a future second worker does not silently double-schedule. |
| 3 | **What happens to `solverah-outbox-sweep`?** It duplicates beat's `outbox.drain` once beat runs. Retire it, or keep it as belt-and-braces. Recommend **keep initially**, retire after a week of clean worker logs — it is idempotent and it is the safety net for the exact case beat is new at. |
| 4 | ~~**Blueprint adoption?**~~ **ADOPT, AFTER LAUNCH — Sebastian, 2026-09-16.** The drift has now caused four incidents: the 120s->30s timeout lag, the implicit `workers=1`, `CELERY_TASK_ALWAYS_EAGER` set only in the dashboard, and the instance plan never being recorded at all. `RENDER_DEPLOYMENT.md` has the two paths. Not during a stability incident. |

---

## 7. Migration — the order is load-bearing

**The rollback is a single environment variable, which is what makes this safe.**

1. **Land the interim cache fix first.** Otherwise the worker is born with the
   474 MB/worker leak and the incident just moves house.
2. **Create `solverah-worker` in the dashboard** with the §5 command.
   With `CELERY_TASK_ALWAYS_EAGER` still **true**, `.delay()` runs inline and
   nothing reaches the broker — **so the new worker sits idle and changes
   nothing.** This step is observable and risk-free.
3. **Verify** the worker boots: `celery_configured` in its logs, broker
   connected, no `ModuleNotFoundError` on first task, connection count within
   ceiling.
4. **Flip `CELERY_TASK_ALWAYS_EAGER` to false.** Jobs now flow to the worker.
   This is the only step that changes behaviour.
5. **Watch** one full cycle: a scoring job completes on the worker, an outbox
   row drains, web dyno memory drops.
6. **Then** decide §6 #3 on the cron overlap.

**Rollback at any point after step 4: set the flag back to true.** An environment
variable change, no deploy, no code revert. Work returns to running inline —
degraded, but serving.

**Never flip the flag before step 2.** Eager is currently the only reason
scoring runs at all. Off with no worker means every Work Pulse, path suggestion,
manager match and situation report enqueues and hangs forever, with no error —
strictly worse than the memory problem it would be trying to fix.

---

## 8. What this does not fix

- **Not the embedding cache.** That is the interim fix, and then
  `PATH_INTELLIGENCE_REDESIGN.md`. This proposal changes *where* heavy work runs,
  not how much memory it uses. Both are needed; neither substitutes.
- **Not `preload_app`** on the web tier, which would cut per-worker baseline but
  needs its own `post_fork` work and its own tests.
- **Not the worker-count question.** Production logs show one or two
  `celery_configured` lines per boot, not the three that `workers = 3` and no
  `preload_app` should produce. Unresolved, and it changes the web tier's memory
  arithmetic. Check `Booting worker with pid` counts per boot.
- **Not release tracking.** Production logs carry `"version":"dev"`, so no log
  line or Sentry event can be attributed to a deploy. Unrelated, cheap, worth
  its own chunk.

---

## Related

- `docs/PATH_INTELLIGENCE_REDESIGN.md` §1.3 — the OOM measurements and §4 sequencing
- `docs/RENDER_DEPLOYMENT.md` — the two Blueprint adoption paths
- `solverah/infra/queue.py` — the five queues, BEAT_SCHEDULE, and why eager exists
- `solverah/worker.py` — the entrypoint, and the `sys.path` trap it already solves
- `gunicorn.conf.py` — the `preload_app` / fork-safety precedent §4.1 relies on
