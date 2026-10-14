---
name: msw-companylens-review
description: Open review points on tests/msw/companyLensHandlers.ts (matching-model C7, 2026-10-14) — fall-through convention and the no-probability guard's gaps
metadata:
  type: project
---

Reviewed 2026-10-14, approved with follow-ups for matching-model (not yet confirmed fixed):

1. `researchProgresses` answers 404 for a non-matching `run_id`; the folder convention
   (scoringJobHandlers.ts header) is to return `undefined` so `onUnhandledRequest: "error"`
   catches a call to the wrong id.
2. `researchRefused` / `companyProfileReply` / `DAILY_LIMIT_PROBLEM` bodies are untyped
   through `resolve()`; the convention is an explicitly typed body.
3. `assertNoProbabilityText` misses bare decimals ("0.82") and ratings ("3.9") — the very
   values `LEGACY_PROFILE` carries. Today LegacyProfile drops them, so the tests pass by
   rendering, not by guard.

**How to apply:** on the next review touching this file, check whether these were taken up;
delete this entry once they are.
