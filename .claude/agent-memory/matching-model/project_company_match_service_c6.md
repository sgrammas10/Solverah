---
name: company-match-service-c6
description: 2026-10-13 C6 (six-trait build) UNCOMMITTED -- company_match_service + the /me/matches rewrite, /companies/<id>/read, research/posting/link routes, interim scorer DELETED, assembler gained outcome + tolerance columns; the rules as implemented, the wire shape, the traps hit
metadata:
  type: project
---

2026-10-13, lane C6 of the CompanyLens six-trait build (plan:
docs/superpowers/plans/2026-10-13-companylens-six-trait.md). UNCOMMITTED; orchestrator
reviews. Lane DB solverah_c2.

**Built.** `solverah/services/company_match_service.py` (the read + ranking),
`solverah/services/company_match_content.py` (question bank 6x2x2, size notes,
next-step vocabulary), `solverah/api/v1/companies.py` rewritten (`/me/matches`,
`/companies/<id>/read[?posting_id]`, `POST /companies/research` + `GET .../<run_id>`,
`POST|GET /me/job-postings[/<id>]`, `POST|GET|DELETE /me/company-links`),
`solverah/schemas/matching.py` rewritten, `model.UserCompanyLink` + migration
`20261013_user_company_link` (down_revision `20261013_envreport_outcomes`),
`company_evidence_store` gained `companies_with_shared_records`, `shared_records_by_company`,
`confounder_values`, `research_run`, and the company-link CRUD (`create_company_link`,
`company_links_for_user`, `delete_company_link`, `delete_company_links_for_user(commit=)`).
`company_research/service.existing_run(db, company_id)` = what request_research would return
without starting one.

**Deleted:** `packages/ml/culture/scoring.py`, `solverah/domain/matching.py`,
`solverah/tasks/maintenance_tasks.py` (the culture-pref backfill), `matching_service`'s
matches/_score_all/resolve/backfill, `company_repository.culture_rows` + CULTURE_COLUMNS.
`work_pulse/derive_preferences.py` KEPT: `Scripts/capture_contract.py` (backend-platform)
still imports it for the contract baseline's culture_preferences seed.

**Rules as implemented (document before anyone "fixes" them):**
- Unanswered user -> `{d: (0.15, 0.15)}` (hinge at the floor), never None; `preferences_answered`
  on the wire says which.
- Direction from `fit_gap` (person SNAPPED onto COMPANY_LATTICE, then person - env): gap > 0 ->
  "less" (company offers less than you prefer, UNDER zone), gap < 0 -> "more", 0 -> "even";
  within = |gap| <= zone (+1e-12).
- Mixed: each end read separately; must-have broken by either end = `risk`; ranking uses the
  WORST end via additivity: base row (all mixed at low_end) + per-mixed-trait variant row
  (that trait at high_end); z_worst = base + sum(min(0, variant - base)). One point_z call per
  request. Tested: mixed (0.1, 0.9) ties with known 0.1 for a person at 0.9.
- Unknown -> env NaN + env_missing mask; must-have -> `investigate` + questions.
- Coverage counts known/mixed/unknown/6; `known < 3` -> `not_enough_evidence` (rank None,
  listed after ranked, `missing` lists the unknown dims). Mixed does NOT count toward the 3.
- Order: (must_have_break, -z, id) then unranked by name. Cursor = {"id", "pos"} (no score).
- Next step v1: investigate (must-have unknown / mixed-risk / posting disagreement on a
  must-have, checked in TRAIT_KEYS order) > explore (not_enough_evidence) > decide.
- Posting disagreement: both known and (different sides of 0.5, neither exactly 0.5, or
  |diff| >= 0.3). Posting records never enter the ranking; posting trait `flag` is forced None.
- Confounders: stage_size from Company.headcount band (else confounder table), comp/industry
  from company_confounder_value latest as_of; anything missing or off-vocabulary is MASKED.
- Weights: same env-var rule as situation_report_service (`priors` default needs no
  model_run; `run` raises MatchModelError without one -- tested).
- Question-bank direction: person score >= 0.5 -> prefers_more (tie rule, documented).

**Wire rule + its test:** no float anywhere, no key matching
p_fit|prob|score|percent|pct|estimate|confidence|logit|z, no "N%" string --
`tests/test_company_lens_api.py::_assert_no_numbers_that_look_like_scores` walks every
new response. Evidence items carry paraphrase/source_type/scope/dates/url/abstained and a
"side" only via which list they sit in (never a score).

**Daily research budget (5 new runs/user/day):** NOT a `@limiter.limit` -- Flask-Limiter
checks decorated limits BEFORE the handler, so a user at the budget could not get a cached
hit. Charged by hand with `limiter.limiter.hit(parse("5 per day"), namespace, "user:<id>")`
after the cache answers and after both provider clients resolve, exempt under TESTING like
every house limit (the test flips TESTING off and sets COMPANY_RESEARCH_INLINE=True so
dispatch stays inline).

**Traps hit:** (1) `tests/test_company_evidence_internal.py` reads the excerpt column name
even in tests -- build `EvidenceItemInput` POSITIONALLY in test files. (2) Person scores in
route tests: monkeypatch `assessment_store.get_dimension_scores` (the doorway), never the
table. (3) Assembler sitting ids: the store returns 32-hex, raw SQL gives a hyphenated UUID --
normalise with `.replace("-", "")`. (4) The two historical byte-identity assembler tests pin
the row's FIELD SET: every new row field must be added to both `new_names - old_names`
assertions. (5) Writing a `python - <<'EOF'` heredoc with triple-quoted strings broke bash
once; use a scratch .py file for edit scripts.

**Open at hand-off:** auth-accounts must wire `user_company_link` into export/delete
(`company_links_for_user`, `delete_company_links_for_user(commit=False)` exist) --
test_export_delete_coverage fails until then. `Scripts/capture_contract.py` still seeds the
deleted interim path (derive_preferences + profile culture_preferences) for the A33
re-baseline. `.claude/agents/ops-crons.md` names the deleted `maintenance_tasks.py`.
`solverah/worker.py`'s long comment still cites the deleted backfill task. The frontend
CompanyLens/CompanyDetail pages do NOT import schema.ts types, so `npm run type-check` is
green after the regen; C7 rewrites them against the new shapes.
