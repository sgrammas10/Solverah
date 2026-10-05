---
name: incident-2026-10-02-idna-oom
description: 2026-10-02 prod outage ("unknown encoding: idna" on every request) - read-only analysis of origin/main; no per-request leak found on the probe path
metadata:
  type: project
---

Prod went down 2026-10-02 ~23:09 UTC. Every request failed with `LookupError: unknown encoding: idna` in werkzeug `Map.bind`, after a linear memory climb that started ~16:38 with no deploy. A read-only review of origin/main (cc23475) found:

- The probe path does not leak. `/healthz` builds a static dict. `/readyz` runs `SELECT 1` through `db.session` and then rolls back, plus two counts through `with db.engine.connect()`. Sentry has `traces_sample_rate=0`. The logging contextvars are reset at teardown. There are no Prometheus metrics, no gunicorn hooks, and no per-call threads or engines.
- Arithmetic: with max_requests=2000 and no sawtooth, fewer than ~317 requests per hour reached the worker. That means more than 150 KB leaked per request, which is implausible for probes. So the growth was either driven by time or sat outside the worker heap.
- The "idna" error is a **poisoned worker**. `encodings.search_function` caches `None` after an ImportError (stringprep pulls in the unicodedata .so, and a dlopen that fails with ENOMEM or EMFILE raises ImportError). A worker that spawns under memory or FD pressure therefore stays broken after the pressure clears, until it is recycled.
- In prod, Celery is NOT eager when REDIS_URL is set (config.py ~390-411), and there is no Celery worker service. Each `.delay()` therefore subscribes the Redis result backend in the web process.

**Why:** this explains why the outage persisted and rules out the obvious suspects.
**How to apply:** next time, ask for the RSS of each process (`ps`/smem on the instance) and the FD count before blaming app code. Restarting the service clears the poison.
