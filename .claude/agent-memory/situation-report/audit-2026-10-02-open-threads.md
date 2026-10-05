---
name: audit-2026-10-02-open-threads
description: What is still open from the 2026-10-02 lane audit after the same-day fix wave (F1/F2/F3/F5/F7/F9 fixed, uncommitted); check before acting
metadata:
  type: project
---

Audit 2026-10-02 (before the Julie/Sebastian content sprint, around 2026-10-09). The fix
wave on the same day (orchestrator dispatch, uncommitted) closed F1 (banner-only
`career_status_changed`), F2's None guard (`needs_core` + `core_unreadable`), F3 (card
all-aligned), F5 (trend error state), F7 (past-mode return label, dead first_job check
removed), and F9 (race test). Still open:

1. F2 remainder: CLOSED 2026-10-05. `dimension_scores_for_submission` returns None for an
   unscoreable sitting, and the default pin falls forward ([[default-pin-rule-2026-10-05]]).
2. `core_unreadable` gate says "take Work Pulse again". That works when no submission
   row exists. It does NOT work for an explicit pin to a vanished sitting, because the
   override persists, so recalibrate is the real exit there. It is a rare edge case.
3. USER_SCENARIOS S10/S21.2/S22.4/S9.6-9.7 are stale against the 2026-09-29 layout, and
   there is no /environment-report/past scenario. A doc pass is planned.
4. Decisions Q2-Q4 are open: the past-job "no earlier job" exit, a duplicate past report,
   and the first_job hub card.
5. F6: the situationReport query is not invalidated on career-status/experience saves
   or core completion. Profile-hub and core-assessments are fixing it. The F1 banner
   depends on this to appear promptly.

**Why:** these were deferred, or belong to another lane.
**How to apply:** re-check each against the code at the next lane task, and delete
the items that are fixed. See [[lane-state-facts]] and [[situation-f1-f2-wire-shape]].
