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
**How to apply:** any bank change -> rerun generator, parity test goes red until then, and a NEW form must be built (old answers refuse to import on version mismatch) -- UNLESS the change only adds optional items after `experienced`, see below.

### 2026-10-13: v3 outcome items + legacy-form acceptance (UNCOMMITTED, dispatched by orchestrator)

Situation-report bumped the Environment Report to `env-v3-2026-10-13`, adding five optional
exploratory outcome items (satisfaction, performance, engagement, sustainability,
retention_intention, 1-5) after `experienced`. Pilot form side:

- **`spec.PILOT_FORM_VERSION` bumped to `pilot-v2-2026-10-13`.** Each job section gained a
  new `%s_outcomes` page (all 5 items, `required=False`, role `"outcome"`) immediately after
  `%s_overall`; `experienced` stays alone and last among REQUIRED items, but the outcomes
  page is now the actual last page of the slot (the `go_to` that used to sit on `_overall`
  moved there). Regenerated `build_form.gs` / `form_mapping.json`; `--check` passes.
- **Legacy-form acceptance is new and intentional, not a one-off patch.** A v2-built form
  may already be in Sebastian's respondents' hands. Snapshotted the PRE-change committed
  artifacts to `legacy/pilot-v1-2026-10-01/{form_mapping.json,build_form.gs}` -- frozen,
  never regenerated. `responses.resolve_mapping(header, mapping=None)` tries the current
  mapping first, then each path in `LEGACY_MAPPING_PATHS`, picks whichever matches the CSV
  header exactly. This is the pattern to extend if a future bank change is ALSO
  additive-only (new optional items, no change to the 16 required ones): snapshot, add to
  `LEGACY_MAPPING_PATHS`, write the "required items still match live banks" guard test
  (`test_the_legacy_mapping_still_matches_the_live_banks_on_required_items` in
  test_pilot_form.py) for the new pair. If a bank change ever touches a REQUIRED item's
  wording/options, do NOT add it to this list -- that's the old "refuse and rebuild" path,
  still true via `check_bank_versions`.
- **`JobAnswers.outcomes` / `ParsedResponse.{pilot_form_version,env_form_version}`** are the
  new provenance surface: which mapping actually matched, and which outcome items (if any)
  the respondent answered. A legacy-form response's `outcomes` is always `{}`; `payload()`
  simply omits those keys (situation_report_service's `payload.get(item_id)` defaults to
  None either way).
- **KNOWN LIMITATION, not fixed, flagged to situation-report/schema-steward:**
  `situation_report_service.submit_environment_report` (their file) hardcodes
  `version=situation_items.FORM_VERSION` -- the app's CURRENT live version, always,
  regardless of what payload shape the caller actually built. So `environment_reports.version`
  in the DB can NEVER reflect which pilot-form generation a respondent actually answered;
  every pilot row (v2 or v3 source) is stamped with the live FORM_VERSION. The true version
  survives only in this lane's own bookkeeping (`ParsedResponse.pilot_form_version` /
  `.env_form_version`, the import summary note) -- never persisted to the DB. Harmless for
  scoring (16 required items byte-identical, verified by test), but means NULL outcome
  columns are ambiguous in the DB alone ("not offered" vs "offered, skipped") -- only the
  import-time CSV parse can tell them apart, and that's not kept anywhere durable. If this
  distinction ever matters, `submit_environment_report` needs an optional `version` override
  param -- their file, not mine; don't add it here.
- Legacy acceptance window is deliberately open-ended for now (orchestrator is asking
  Sebastian whether a v2 form is actually circulating; revisit once answered).
- Tests: `tests/test_pilot_form.py` (legacy-matches-live-banks guard, resolve_mapping
  fallback, outcome storage/optionality) and `tests/test_pilot_form_import.py`
  (`test_a_legacy_form_response_imports_with_outcomes_null`,
  `test_a_current_form_response_imports_with_outcomes_stored`) -- both green against
  `solverah_c4`, 98 passed/2 skipped as of this write.
