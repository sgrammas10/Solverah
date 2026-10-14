---
name: pilot-form-pipeline
description: Pre-launch pilot Google Form pipeline (prereg Amendment 2) - built 2026-10-01, UNCOMMITTED; design choices that are not obvious from the code, lane DBs, open items
metadata:
  type: project
---

Built 2026-10-01 in `causal_graph/v1_model/pilot_form/`, UNCOMMITTED (Sebastian approved the build, not a commit). No Google Form exists yet; Sebastian pastes `build_form.gs` himself.

Non-obvious decisions (keep them unless Sebastian rules otherwise):
- **Column identity = (title, occurrence)**, verified exactly against `form_mapping.json`. The past-tense current section and the previous-job section share all 16 titles; Google writes columns in form order, so occurrence 2 = previous job. A header mismatch refuses the whole file.
- **pilot_id = sha256(row cells minus the email cell)[:16]** - stable across re-exports, carries no PII. Idempotency = "user pilot-<id>@pilotform.solverah.invalid already exists".
- **Provenance = email domain**, surfaced as `respondent_source` ('app'|'pilot_form') on `EnvironmentTrainingRow`; SQL LIKE in `_fetch_respondent_sources`, only ids come back. Byte-identity test vs commit e8a9a72. Synthetic devfit users read 'app' (excluded by their own domain per prereg 0.2).
- **Core order is fixed** = what present_items serves respondent id `pilot-form-v1`; core pages break at 8/16, never at the 6-item block boundaries.
- **Env reports go through `situation_report_service.submit_environment_report`** (the real service), career status via `profile_repository.update_document`, core via `persist_submission` with a ScoredSubmission built like submit_form.
- Guard: `devfit/guard.py` gained `assert_local_database(url, prefix=)` + `PILOT_DB_PREFIX="solverah_pilot"`; devfit API unchanged; each harness refuses the other's DBs.
- App boot needs JWT_SECRET_KEY (+cookie vars) even for the CLI - README carries them.

Lane DBs on 5433: `solverah_pilot_test` (pytest). `solverah_pilot` is Sebastian's research DB - never pytest. Note the guard accepts `solverah_pilot_test` too (prefix match), by design of the brief.

- 2026-10-02 follow-up consent added (Sebastian-approved): optional final-page question; followup_ok yes only with an email; excluded from pilot_id with the email (PRIVATE_ROLES); lives only in emails.csv (old 2-column files load as no). A check-in sender is NOT built; its re-asked experienced ratings are exploratory (prereg Part 3), never Look 1/2.

Open: Appendix A must list any test-fill pilot ids before Look 1; the "first report per respondent" filter and the counting script (prereg Part 4) are still unbuilt.

**Why:** prereg Amendment 2 counts pilot current rows toward Look thresholds, so the form must be the app's instrument and the rows must be separable for the app-only sensitivity call.
**How to apply:** any bank change -> rerun generator, parity test goes red until then, and a NEW form must be built (old answers refuse to import on version mismatch).
