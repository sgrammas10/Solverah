---
name: contract-seeds-legacy-work-pulse
description: capture_contract.py seeds a legacy work_pulse sitting (A32) because the retired kind can no longer be submitted; removing the seed moves 9 steps
metadata:
  type: project
---

Since the 2026-10-05 retirement of the legacy 12-question `work_pulse` (A32), `Scripts/capture_contract.py`
cannot score one, so `_seed_legacy_work_pulse` writes the row through `assessment_repository.open_current` +
`profile_repository.update_extra_key("culture_preferences", ...)`, in the final state the deleted
`submit_work_pulse` left. Its four door steps (`submit-work-pulse-sync-gone`, `queue-work-pulse-too-few-answers`,
`queue-work-pulse`, `poll-work-pulse-job` on a fixed `"0"*32` handle) now pin the 410 `kind_retired` tombstone.

**Why:** without the seed, 9 more steps moved (result-work-pulse 200->404, catalogue completed, session
`wpl_completed`, profile/login `culture_preferences`, dashboard "original Work Pulse quiz" activity, export
`wpl_*`). That is lost coverage, not a wire change: prod still holds legacy rows and they must stay readable.
A32 re-baseline DONE 2026-10-05 (uncommitted): exactly 10 field differences in the four door steps, then
0 across 116 after recapture. The situation lane's new default-pin rule has no wire impact here because EMAIL
has one core sitting, which short-circuits. Any multi-sitting scenario step would need its own re-baseline.
**How to apply:** keep the seed until legacy rows are purged from prod. If core-assessments changes what
a legacy row looks like (or deletes `derive_culture_preferences`), the seed must follow. See
[[rebaseline-pending-career-status-changed]].
