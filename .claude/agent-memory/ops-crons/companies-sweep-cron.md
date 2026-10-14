---
name: companies-sweep-cron
description: flask companies sweep + render.yaml solverah-companies-sweep (*/10) built 2026-10-14; NOT created in Render; gated on a double-run race decision; first run unverified
metadata:
  type: project
---

`flask companies sweep` (cli.py, companies group) calls matching-model's
`service.sweep_research_runs`: fails `running` research rows > 1560 s as `timed_out`,
re-dispatches `queued` rows > 5 min. Mirrored in render.yaml as `solverah-companies-sweep`,
native Python runtime, `*/10 * * * *`, solverah-prod group. No `--dry-run`: the service has
no read-only mode (do not add one there; it is matching-model's file).

**Open thread:** the cron is NOT created in the Render dashboard. It is created on the
six-trait deploy day (RUNBOOK_DEPLOY_MAIN_MERGE.md, "CompanyLens six-trait"). After you
create it, run it once by hand. Expect `{"reaped": 0, "requeued": 0}`.

**Why it is gated:** a requeue runs the job INSIDE the cron process (eager Celery, then the
thread pool). Python 3.9+ joins pool threads at exit, so the cron waits for the run
(confirmed). Meanwhile the web pool may still pick up the same queued row:
`run_research_job` claims it without a lock and proceeds on a `running` row, so the run
executes twice. Handed to matching-model 2026-10-14. Without the cron, a deploy during a
run leaves that company stuck `running` forever.

**How to apply:** before creating the cron, check whether matching-model made the claim
atomic. The cron needs ANTHROPIC_API_KEY and OPENAI_API_KEY, because requeued runs execute
inside it. Related: [[anthropic-key-is-the-public-switch]], [[six-trait-merge-migrations]].
