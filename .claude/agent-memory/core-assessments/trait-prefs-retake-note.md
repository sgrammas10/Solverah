---
name: trait-prefs-retake-note
description: Retake page /trait-preferences carries a one-line note that tolerance reaches CompanyLens now but the Situation Report only at its next sitting (D-15, 2026-10-14)
metadata:
  type: project
---

`RETAKE_SITTING_NOTE` in `traitPreferencesCopy.ts`, rendered by `TraitPreferencesPage` only (not `TraitPreferencesStep`, which is the first-time step whose answers count for that sitting).

**Why:** D-15 ruling 2026-10-14; without it a user who edits tolerance sees no Situation Report change and thinks it is broken.
**G49 (2026-11-23):** reworded to be true for both pin cases: a report with no tolerance yet takes the FIRST answers at once; a later change waits for a retake + Re-read (situation_report_service "THE TOLERANCE PIN").

**How to apply:** keep it off the first-time step; copy is best-guess, Julie revises. See [[trait-preferences-c1]].
