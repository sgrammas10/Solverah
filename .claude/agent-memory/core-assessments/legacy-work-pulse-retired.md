---
name: legacy-work-pulse-retired
description: The 12-question work_pulse kind was retired 2026-10-02 -- every write door is 410 kind_retired, scorer deleted, read-only result kept; culture_preferences now has no new source
metadata:
  type: project
---

Retired by Sebastian's ruling 2026-10-02. `AssessmentKind.retired=True` keeps the kind in the registry so `GET /me/assessments/work_pulse/result` still serves stored narratives (no narrative = 404, the old 422 "resubmit" is gone) and rows stay in export/delete. `POST .../work_pulse/submissions`, `POST .../work_pulse/scoring-jobs` and the job poll all answer 410 `kind_retired`, no `replaced_by`, before auth/body. `assessment_service.submit` also refuses it, so a pre-deploy queued job fails with no provider call. Deleted: `submit_work_pulse`, `build_wp_narrative_prompt`, `WorkPulseSubmitRequest`, `WorkPulseScoringJobStatus`, WPStepper, wpQuestions.ts, useWP's answer side, WorkPulseUnlock's data branch, the results page's enqueue/resubmit. `/work-pulse/results` is a read-only view; route line in App.tsx unchanged.

**Why:** it was unreachable from the UI but still paid for an OpenAI call per request.

**How to apply:** `culture_preferences` (interim matcher input) derives only from legacy answers, so users who never took the old quiz get `/me/matches` 400 forever; handed to matching-model. `Scripts/capture_contract.py` still queues work_pulse and will KeyError on the 410 -- backend-platform must update it and re-baseline. `derive_preferences.py` was DELETED 2026-10-14 (C6 removed its last caller) with its test and `work_pulse_answers_for_users`. See [[core-retakes-live]].
