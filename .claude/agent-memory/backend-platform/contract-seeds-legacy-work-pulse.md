---
name: contract-seeds-legacy-work-pulse
description: capture_contract.py seeds a legacy work_pulse sitting (A32) and the profile's culture_preferences as a LITERAL (A33); removing either moves legacy-read steps for lost coverage, not a wire change
metadata:
  type: project
---

Since the 2026-10-05 retirement of the legacy 12-question `work_pulse` (A32), `Scripts/capture_contract.py`
cannot score one, so `_seed_legacy_work_pulse` writes the row through `assessment_repository.open_current`
and the profile's `culture_preferences` through `profile_repository.update_extra_key`. Since A33
(2026-10-14) the preferences are the literal `LEGACY_CULTURE_PREFERENCES`, not a call into
`work_pulse.derive_preferences`: the interim `culture_fit_score` path that consumed the key was deleted
by the six-trait build, and the script must not depend on what is left of it. The key is still echoed in
the profile document (`NARROW_EXTRA_KEYS`) and the export, so five steps still pin it
(`me-profile-after-write`, `export`, the three later logins).

**Why:** without the sitting, 9 steps move (result-work-pulse 200->404, catalogue, session
`wpl_completed`, profile/login/dashboard/export); without the preferences literal, 5 move. Both are lost
coverage of rows prod still holds, not wire changes.
**How to apply:** keep both seeds until legacy rows are purged from prod. If core-assessments changes
what a legacy row looks like, the seed must follow. The four door steps still pin the 410 `kind_retired`.
See [[rebaseline-a33-companylens]].
