---
name: core-retakes-live
description: Work Pulse (core) is retakeable since 2026-10-02, no cooldown; what a retake changes, what it does not, and the open pin surprise handed to situation-report
metadata:
  type: project
---

Ruling (Sebastian, 2026-10-02): core is retakeable, no cooldown "for now". Entry is the "Retake Work Pulse" button at the bottom of the /work-pulse completion card ("Continue your retake" when a sessionStorage draft exists). The switch for a cooldown is `assessment_service.CORE_RETAKE_COOLDOWN` (None); set it and a retake inside the window is 409 `retake_cooldown` with `retake_available_at`. The client does not know the window, so turning it on needs the card to hide the button too.

Decided: an unfinished retake is still "completed" everywhere (the draft is client-only; nothing server-side changes until Finish).

Which sitting each consumer reads: Situation Report = explicit pin else FIRST; recalibrate = LATEST; `get_dimension_scores` / `has_completed_assessment` = current scoring-key rows (newest sitting); assemble_training_data = pin rule; devfit explain_user = FIRST only (ignores explicit pin). Interim matcher and path intelligence never read core at all.

**Why:** the trust page, D-15 pin and Recalibrate all assumed retakes but the UI had none.

**How to apply:** open surprise, reported to situation-report not fixed: a user who retakes BEFORE their first environment report gets a report built from the older sitting (default pin = first). Respondent-seeded shuffle means a retake sees the same item order and tokens (D-04, by design). See [[form-version-bump-reprompts-everyone]], [[legacy-work-pulse-retired]].
