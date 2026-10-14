---
name: draft-storage-sweep
description: Logout and clearSessionLocally sweep per-user browser-storage drafts via src/features/auth/draftStorage.ts; the prefix list there is the one source of truth and other lanes hand new keys to auth-accounts
metadata:
  type: project
---

`clearUserDrafts()` (fix wave 2026-10-02) removes every sessionStorage/localStorage key that STARTS WITH one of: `solverah_assessment_answers`, `env_report_answers`, `mp_answers`, `mm_answers`, `solverah_wp`, `solverah_intake`, `focus_type_draft`, `pendingQuizSave`. Kept on purpose: `guestQuizCompletedAt` (one-quiz-per-device lockout) and `solverah.hasSession` (handled by `rememberSession`). It runs ONLY via `clearSessionLocally({ drafts: true })`, which `logout()`'s `finally` and AccountSettingsPage's deletion pass. The failed-refresh path calls bare `clearSessionLocally()` and keeps drafts — orchestrator ruling 2026-10-02: `refreshSession()` resolves false on a network error too, and a blip at submit must not cost 24 Work Pulse answers; drafts are tab-scoped sessionStorage, so the explicit sign-out is the shared-device case that matters.

**Why:** drafts are keyed by instrument, not account; on a shared tab user B was offered user A's Manager Match and the guest-quiz replay attached A's answers to B. Prefix match because manager-match and core-assessments are suffixing keys with the user id this wave (`focus_type_draft:<id>`, `focusTypeDraftKey()`), and `env_report_answers_past` already exists.

**How to apply:** sign-in NEVER clears `pendingQuizSave` (a guest who answered then signs in must get the replay). When a lane adds a draft key, add its prefix to `USER_DRAFT_KEY_PREFIXES` and the list in `draftStorage.test.ts`; the hand-off rule is the same as account_service: they tell auth-accounts, they do not edit the file. Choose prefixes that are full instrument names so `startsWith` cannot over-match.
