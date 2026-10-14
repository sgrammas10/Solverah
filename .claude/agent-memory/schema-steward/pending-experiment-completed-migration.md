---
name: pending-experiment-completed-migration
description: 20261002_experiment_completed (pulse-experiments lane) - uncommitted head after 20261002_envreport_subject; APPROVED 2026-10-02 after the guard fix; rollback = stamp, not downgrade
metadata:
  type: project
---

`migrations/versions/20261002_experiment_completed.py` belongs to **pulse-experiments**. It revises
`20261002_envreport_subject` (situation-report lane) and was the single head on 2026-10-02, uncommitted.
It widens `ck_experiment_status_vocab` to ('active','completed','abandoned') and backfills
`active AND ends_at <= now()` rows to `completed`.

Review 2026-10-02: the first downgrade guard missed "two completed rows" (any repeat user). It was fixed to
the per-user `HAVING count(*) > 1` over ('active','completed'), and tests/test_experiment_completed_migration.py
was added. APPROVED. Rollback path: RUNBOOK_DATABASE_ROLLBACK.md §7, which says
`flask db stamp 20261002_envreport_subject`, not downgrade. Pre-fix code runs on the post-fix schema, and
re-upgrading after the stamp is safe (rehearsed).

Pre-existing drift on `experiments`, NOT from this revision: the migration names the FK
`fk_experiment_user` (ORM gives `experiments_user_id_fkey`) and sets server_default 'active' on status
(ORM has only a Python default).

**Why:** a later session must know whose migration this is and how to roll it back.
**How to apply:** once it is committed, delete this file. Keep the drift note, moved somewhere else, until it is cleaned up.
Related: [[flask-migrate-swallows-runtimeerror]]
