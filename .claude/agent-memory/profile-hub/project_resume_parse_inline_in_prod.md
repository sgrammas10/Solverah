---
name: resume-parse-runs-inline-in-prod
description: Prod runs CELERY_TASK_ALWAYS_EAGER=true with no worker/beat (split deferred 2026-09-28), so resume parse jobs run inside the POST and the reap/sweep never runs
metadata:
  type: project
---

Production has no Celery worker and no beat (worker split DEFERRED, Sebastian 2026-09-28; CELERY_TASK_ALWAYS_EAGER=true per docs/CELERY_WORKER_SPLIT.md / RUNBOOK_DEPLOY_MAIN_MERGE.md). So `POST /me/resumes/{id}/parse-jobs` runs the whole parse inline (up to PARSE_TIMEOUT_SECONDS=30 plus the R2 download) and the 202 arrives after the job is already terminal. `sweep_resume_jobs` / `reap_stalled` never run in prod, so a row orphaned in `running` by a killed request stays there.

**Why:** the async design (poll + reaper) is only half-live; reasoning about "a job that hangs" must assume eager mode.
**How to apply:** don't rely on the reaper for user-facing correctness in prod; the client poll has no ceiling of its own (`useResumeParseJob.ts`) and would spin forever if eager were turned off without a beat. Re-check when the worker split lands. Related: [[audit-2026-10-02-open-threads]].
