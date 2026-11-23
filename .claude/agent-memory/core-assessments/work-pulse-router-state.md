---
name: work-pulse-router-state
description: /work-pulse takes router state { retake: true } (hub/dashboard retake door) and { traitPreferencesSaved: true } (saved confirmation); both read once and stripped (2026-11-23)
metadata:
  type: project
---

`WorkPulseLocationState` (exported type in WorkPulsePage.tsx): `retake: true` opens the retake form directly for a completed user (ignored before completion; draft is NOT cleared, so the resume prompt still applies); `traitPreferencesSaved: true` shows the "Saved" status line. Both read once in a useState initializer and stripped with `navigate(pathname, {replace, state: null})`, same as FocusTypePage.

/trait-preferences Save passes `traitPreferencesSaved`, Cancel passes nothing (G48). The dashboard card WorkPulseUnlock now LINKS to /work-pulse (retake state) and /trait-preferences; its test pins "no results link", not "no links". The /work-pulse completion card still uses buttons (its own no-links D-15 test).

**Why:** G46/G48 (USER_SCENARIOS §1.2). The hub (profile-hub's IntelligencePage) must pass `{ state: { retake: true } }` for its "Retake Work Pulse" to skip the card.

**How to apply:** a new door into /work-pulse uses this shape; don't invent a second flag. See [[core-retakes-live]], [[trait-prefs-retake-note]].
