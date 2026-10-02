---
name: situation-f1-f2-wire-shape
description: Why career_status_changed is complete-only and core_unreadable rides on needs_core instead of being a new state (2026-10-02 fix wave)
metadata:
  type: project
---

Fix wave on 2026-10-02:
- `career_status_changed` is set only in the `complete` state. It is true when
  `is_past_tense(live) != is_past_tense(snapshot)`. It is false when the live status is
  unset, unknown, or `first_job`. `first_job` counts as past tense, but it has no role
  to describe: the form gates it and the submit returns 409. A banner would point at a
  dead end and could never clear (cross-lane review, 2026-10-02). Banner only. Re-slicing the old report was the larger option of an
  open decision and was not chosen. It is NOT declared in the pydantic schema. The
  schema module declares only keys that every state carries. Optional in the TS type,
  so other lanes' fixtures (IntelligencePage, JobSeekerDashboard tests) still type-check.
- An unreadable pin (submission_id None, or no responses) returns `needs_core` with
  `core_unreadable: true`. It is NOT a new state. IntelligencePage, JobSeekerDashboard
  and the dashboard card (profile-hub's files) all branch on `state`, and a new state
  would fall through to their `complete` branch and crash. `needs_core` already
  routes every consumer to "take Work Pulse".

**Why:** this keeps the fix inside the lane, with no edits to other lanes' consumers.
**How to apply:** if a dedicated state is ever wanted, update every `state` consumer
in the same change. See [[audit-2026-10-02-open-threads]].
