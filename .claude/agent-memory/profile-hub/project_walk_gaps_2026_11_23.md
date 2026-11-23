---
name: walk-gaps-2026-11-23
description: G39/G40/G42/G43/G46/G55 fixed on the hub and profile 2026-11-23 (uncommitted); career-status reason nav-state key; hand-offs still open
metadata:
  type: project
---

Fixed 2026-11-23 from docs/USER_SCENARIOS.md §1.2, uncommitted at hand-back:
- G39: the hub step strip is now Work Pulse, FocusType, ManagerMatch (tick on a result), then CompanyLens and Path Intelligence drawn as arrow links. "Work Pulse Lite" was dropped, and "Future Path" was renamed to match the card.
- G40: the quizzes strip no longer promises matching or employer visibility. The quizzes feed View Insights only; nothing on the backend reads quizResults for matching.
- G42: both resume `alert()`s now set `resumeFileError` (the RESUME_UPLOAD_FAILED / RESUME_VIEW_FAILED messages).
- G43: the router-state key is `careerStatusReason`, with values `path_suggestions` (the default), `dashboard`, `environment_report`. `careerStatusNavState(path, label, reason?)` builds it and `readCareerStatusReason` validates it. The dashboard passes `dashboard`.
- G46: the hub's Work Pulse card (both shapes) has "Retake Work Pulse →" (goes to /work-pulse) and a link to /trait-preferences.
- G55: the hub copy now reads "sixteen ... plus five optional ones".

**Why:** these gaps were found by reading the code during the scenario walk.
**How to apply:** open threads that belong to other lanes:
- situation-report still has to make EnvironmentReportPage send `careerStatusReason: "environment_report"`.
- core-assessments: the dashboard's `WorkPulseUnlock` card has no retake link. WorkPulsePage line ~422 still says "sixteen questions". /work-pulse ignores any retake nav state, so it takes 2 clicks.
- uploadResume PUT ok-check FIXED same day (non-ok throws into onError, no parse enqueued). Still open, Sebastian's ruling — G41: the IntakePromptModal effect reopens the modal on every `dashboardData` change.
- Pending: core-assessments is adding `{ retake: true }` nav-state support to WorkPulsePage; the orchestrator will hand over the state shape, then update the hub's "Retake Work Pulse →" navigate call (leave it alone until then).
