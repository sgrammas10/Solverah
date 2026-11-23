---
name: start-route-removed
description: /start (CareerIntakePage, WPLL teaser wizard) and LandingNav were deleted 2026-11-23 (G24); what was left behind in other lanes
metadata:
  type: project
---

Sebastian ruled 2026-11-23: delete `/start`, do not relink it. Removed: the route, `CareerIntakePage`, `useCareerIntake`, `StatementSelector`, `WPLLStepper`, `TeaserResult`, `AccountGate`, `data/careerStatements.ts`, `data/wpllQuestions.ts`, and `src/shared/ui/LandingNav.tsx` (it rendered ONLY on `/start`; the landing page has its own `LandingPageNav` inside LandingPage.tsx, and /login and /register have no nav). Login.tsx's `solverah_intake` replay went too. `TierBar` and `IntakePromptModal` stay (other slices use them).

**Why:** the wizard was unlinked since 2026-09-28 and called an LLM scoring endpoint anonymously.

**How to apply:** the lane file `.claude/agents/public-funnel.md` still lists the deleted files and "Route `/start`"; treat those lines as stale. The landing's sign-up anchor is `/#intake` (`<section id="intake">`). Left for other lanes, backend untouched: `/intake/claims` mode `session` and anonymous `wpll` scoring jobs have no frontend caller; `from=wpll` handling in Register/ConfirmEmail and the `wpll` branch of `useScoringJob` are dead. `solverah_intake` stays in the logout draft sweep on purpose.
