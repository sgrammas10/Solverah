---
name: start-route-removed
description: /start (CareerIntakePage, WPLL teaser wizard) and LandingNav were deleted 2026-11-23 (G24); claims mode "session" removed same day (ruling C); what other lanes still hold, and the write-dead user_intake question
metadata:
  type: project
---

Sebastian ruled 2026-11-23: delete `/start`, do not relink it. Removed: the route, `CareerIntakePage`, `useCareerIntake`, `StatementSelector`, `WPLLStepper`, `TeaserResult`, `AccountGate`, `data/careerStatements.ts`, `data/wpllQuestions.ts`, and `src/shared/ui/LandingNav.tsx` (it rendered ONLY on `/start`; the landing page has its own `LandingPageNav` inside LandingPage.tsx). Login.tsx's `solverah_intake` replay went too. `TierBar` and `IntakePromptModal` stay. `solverah_intake` stays in the logout draft sweep on purpose.

Ruling C (same day): `POST /intake/claims` mode `session` removed end to end (schema branch, dispatch, `intake_service.save_to_account`, `MAX_WPLL_ANSWERS`, `tests/test_intake_save.py`). `mode: "session"` now gets the unknown-mode 422 (`literal_error` on `mode`), pinned in `test_intake_claims_api.py`. Claims modes are register / sign_in / link.

**Why:** the wizard was unlinked since 2026-09-28 and called an LLM scoring endpoint anonymously; the session mode's only caller was its replay.

**How to apply:**
- `intake_repository.upsert_user_intake` was KEPT although no app code calls it: auth-accounts' `test_dbopt_profile_account.py` seeds through it. Nothing writes `user_intake` any more, and nothing writes `assessment_submissions` kind `wpll` (so `flags.wpll_completed` is false for every new user). Whether to drop the table / the kind is an open schema decision for Sebastian, not yet ruled.
- Other lanes' tests that posted mode session (core-assessments `test_assessment_storage.py` x2, backend-platform `test_sprint2_integration.py`) were reported to the orchestrator, not edited.
- The landing's sign-up anchor is `/#intake` (`<section id="intake">`).
