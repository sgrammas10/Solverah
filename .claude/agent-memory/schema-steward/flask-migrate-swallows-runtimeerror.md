---
name: flask-migrate-swallows-runtimeerror
description: A migration that refuses by raising RuntimeError exits 1 with NO message under `flask db downgrade` in this app
metadata:
  type: project
---

Flask-Migrate's `catch_errors` catches `RuntimeError`/`CommandError` and sends it to `log.error(...)` on the
`flask_migrate` logger. Under this app's logging config that line never reaches the console, so a
migration's "refuse with an explanation" `RuntimeError` (20261002_envreport_subject, 20261002_experiment_completed)
shows only the "Running downgrade ..." line and exit code 1. Measured 2026-10-02 on solverah_fx_review_mig.
An IntegrityError, by contrast, does print its traceback.

**Why:** an operator rolling back sees a bare failure and cannot tell a deliberate refusal from a crash.
**How to apply:** when testing a refusing downgrade, check `alembic_version` and the exit code, not the
output. Fixing the logging route is a backend-platform question; a runbook entry naming the refusal
query is the cheap mitigation. Related: [[pending-experiment-completed-migration]]
