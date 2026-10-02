---
name: legacy-work-pulse-unreachable
description: The retired 12-question work_pulse kind has no UI entry (WPStepper unmounted) but the backend still scores it with a paid LLM call; its results page claims employers see the narrative
metadata:
  type: project
---

WPStepper, the answer half of useWP and wpQuestions.ts are mounted nowhere. Only `/work-pulse/results` and IntelligencePage read the legacy result, and only for users with `wpl_completed`. Even so, `POST /assessments/work_pulse/scoring-jobs` still accepts 12 answers and calls OpenAI, and WorkPulseResultsPage's enqueue path can no longer be reached. That page used to say employers could see the narrative; rewritten 2026-10-02 to "Only you ... Employers never see them" with a /trust link. WorkPulseUnlock's data branch is likewise dead.

**Why:** the 2026-10-02 audit asked Sebastian whether to retire the kind. `culture_preferences` (the interim matcher's input) derives ONLY from these legacy answers, so new users never get one. That is matching-model's concern.

**How to apply:** do not extend the legacy path. If he rules to retire it, coordinate with matching-model and with the contract baseline (backend-platform).
