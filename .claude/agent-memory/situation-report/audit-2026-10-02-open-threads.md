---
name: audit-2026-10-02-open-threads
description: Open bugs/gaps found in the read-only lane audit before the Julie content day (2026-10-02); check which are fixed before acting
metadata:
  type: project
---

Read-only audit 2026-10-02 (pre Julie/Sebastian content day ~2026-10-09). Open as of that date:

1. Career-status change after a report is never surfaced: snapshot tense drives the report, so an
   employed->between_jobs user keeps "Negotiate it"/experiments for a lost job (and the reverse).
   Proposed fix: service flag when tense(live) != tense(snapshot) + banner. Needs Sebastian ruling
   on banner-only vs auto re-slice.
2. SituationDashboardCard all-aligned (current mode) shows "pull apart, furthest first" over six
   Aligned chips; its test uses an impossible `dimensions: []` fixture.
3. Pin default `first_completed_core_submission_id` ignores scoring_key_version while
   `has_completed_assessment` is version-keyed; an instrument bump would 500 the report
   (score_stored_choices raises; a None score dict also crashes). Read API is core-assessments'.
4. USER_SCENARIOS S10/S21.2/S22.4/S9.6-9.7 stale vs the 2026-09-29 summary-first layout; no
   scenario for /environment-report/past at all.
5. Past-job offer has no "I had no earlier job" exit (decision).
6. situationReport query not invalidated by career-status/experience saves or core completion
   (60s global staleTime) — hand-off to profile-hub/core-assessments.

**Why:** these were deferred to keep the audit read-only.
**How to apply:** at the next lane task, re-check each against code and delete fixed items.
See [[lane-state-facts]].
