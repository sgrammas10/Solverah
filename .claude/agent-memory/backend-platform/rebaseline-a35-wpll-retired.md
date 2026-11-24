---
name: rebaseline-a35-wpll-retired
description: A35 re-baseline (wpll retired + intake session claim removed, 2026-11-23) DONE uncommitted, 156 steps; _seed_legacy_wpll keeps 8 legacy-read steps pinned; audit write_event now tombstone-aware under FOR SHARE
metadata:
  type: project
---

A35 (docs/ARCHITECTURE.md ledger) re-baselined docs/contract_baseline.json on 2026-11-23, uncommitted on
causal_bayesian_model, captured on `solverah_fx_c`. Supersedes [[rebaseline-a34-g66-lookups]] as the standing
baseline. Moves only the four wpll door steps (`claim-wpll-session` now pins the 422, `submit-wpll-sync-gone`,
`queue-wpll`, `poll-wpll-job` 410 on `RETIRED_POLL_JOB_ID`) and the catalogue's wpll `requires_auth` false->true.

**Why the seed:** without `_seed_legacy_wpll` 8 read steps move (catalogue-after completed, session, 3 logins'
`wpll_completed`, both exports' `legacy_quiz.wpll_*`) -- lost coverage of rows prod holds, same rule as
[[contract-seeds-legacy-work-pulse]]. Keep it until legacy wpll rows are purged from prod.

**Audit (same dispatch):** `solverah/services/audit.py` `write_event` reads `users.status` with `FOR SHARE`
and strips ip/ua/metadata (to `account_repository.AUDIT_METADATA_KEPT_KEYS`, imported -- services->repositories
is legal) for a tombstoned actor. The lock is load-bearing; the race test in tests/test_read_path_writes.py fails
without it. Self-deadlock under eager mode is impossible only because GET paths hold no users-row lock -- if a
read path ever UPDATEs `users` before `record_read_event`, eager mode hangs there.

**How to apply:** next re-baseline starts from A35. `security.py` no longer has `WPLL_ANON_*`.
