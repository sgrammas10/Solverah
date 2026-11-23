---
name: user-fk-ondelete-convention
description: users.id FKs are mixed (about 11 of 32 CASCADE, rest NO ACTION); account deletion tombstones the users row, so CASCADE never fires in the app path -- either choice is acceptable for a new table
metadata:
  type: project
---

Account deletion (account_service.delete_account) TOMBSTONES the users row; it never deletes
it, so a users FK's ON DELETE action only matters for hard deletes (test teardown, an operator).
model.py had 11 CASCADE vs 21 NO ACTION users FKs on 2026-11-23; neither is "the" convention.
Each user-keyed table still needs explicit export/delete wiring by auth-accounts
(test_export_delete_coverage), CASCADE or not.

Scripts/delete_user_by_email.sql is badly stale (DELETE FROM "user", pre-Phase-2 tables) --
it would not run against the current schema. Not yet raised as a task.

**Why:** reviewers keep asking whether a new table's CASCADE is "inconsistent".
**How to apply:** don't block on CASCADE vs none; if a table CASCADEs, make sure user_id
leads an index (the cascade scan). Related: [[pending-g66-user-company-lookup]]
