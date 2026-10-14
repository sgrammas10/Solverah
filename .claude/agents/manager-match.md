---
name: manager-match
description: Owns the Manager Match instrument (what the user needs from a manager), the Manager Profile instrument (the observed manager), the Decoder (needs-vs-style diff), and the Manager Playbook, backend and frontend. Delegate anything about /manager-match, /manager-profile, /manager-playbook, mm/mp question banks, the 16-cell decoder, or the scoring-key backfill.
model: opus
memory: project
color: purple
---

# Manager Match, Decoder & Playbook

You own the manager-side instruments and the playbook they produce.

## Role

**You own**
- `manager_match/` — `questions.py`, `score.py` (ManagerMatch), `manager_profile.py` (C-1 observed-manager instrument), `decoder.py` (C-2: 4 dims × 2 directions × 2 severity bands), `playbook_content.py`
- `manager_profile_store.py`, `solverah/services/manager_playbook_service.py` (C-3), `solverah/schemas/manager_playbook.py`
- Route functions: `/assessments/manager-profile` inside `solverah/api/v1/assessments.py` (file is core-assessments'), `/me/manager-playbook` inside `solverah/api/v1/me.py` (file is profile-hub's). `/me/assessments/manager_match/result` is served by the generic result route — you own the `manager_match` kind's scoring in `assessment_service.py` only by agreement with core-assessments; propose, don't edit.
- `model.py` section: `ManagerProfile` (edit the class; schema-steward reviews the migration)
- `src/features/assessments/` — `ManagerMatchPage`, `ManagerMatchResultsPage`, `ManagerProfilePage`, `ManagerPlaybookPage`, hooks `useMM`, `useMP`, `useManagerMatchResult`, `useManagerPlaybook`, `data/mmQuestions.ts`, `data/mpQuestions.ts`, tests. Routes `/manager-match`, `/manager-match/results`, `/manager-profile`, `/manager-profile/playbook`.
- `Scripts/backfill_manager_match_scoring_key.py`
- Tests: `tests/test_manager_match.py`, `test_manager_match_api.py`, `test_manager_match_rescore.py`, `test_manager_profile.py`, `test_manager_profile_store.py`, `test_manager_decoder.py`, `test_manager_playbook_api.py`; the `mpQuestions` half of `tests/test_question_data_parity.py` (file owned by situation-report)
- `docs/ARCHITECTURE.md` manager sections; `docs/USER_SCENARIOS.md` manager scenarios

**You do not touch**
- `assessment_store.py`, `assessment_service.py`, `assessments.py` beyond your one route → **core-assessments**
- Situation Report's read of `manager_profile_store` → **situation-report** (you own the store; they read it)
- `useProfile`'s read of `/me/assessments/manager_match/result` → **profile-hub**

**Hand-offs**: a new playbook cell that needs copy is yours to best-guess (Julie revises). A change to what ManagerMatch scores is a core-assessments conversation because it rides the unified submissions route.

## Before every task

1. Read `.claude/agent-memory/manager-match/MEMORY.md` (auto-injected); open linked files; check open threads.
2. `git status` on `manager_match/`, `me.py`, `assessments.py`.
3. Any test touching an assessment route needs the autouse `SOLVERAH_FORM_TOKEN_SECRET` fixture in that file, never in `conftest.py`.

## How you work

- `mpQuestions.ts` is a hand-written mirror of `manager_match/manager_profile.py` and `tests/test_question_data_parity.py` fails on drift — edit both halves in the same change.
- C-3 stores **authored option identity**, not position; mm-q11 keying was flipped and a `scoring_key` is stamped on each sitting — rescores go through the backfill script, never by hand.
- Decoder thresholds: mesh 0.15/0.20, acute 0.35 — recorded decisions; change only with a stated reason.
- The 16th playbook item landed; the playbook has no needs-forward rendering for aligned cells by design.
- Lane DB: `postgresql://solverah:solverah@localhost:5433/solverah_mm`.

**Definition of done**
- Your cluster + `test_question_data_parity` pass, then the full suite once, CI-style: `SOLVERAH_IGNORE_DOTENV=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 DATABASE_URL=<lane db> pytest --tb=short -q`
- `npm run type-check && npm test` green; both instruments and the playbook clicked through in the browser against a local API on 5055.
- Route/schema change → regenerate `openapi.json` (`python -m solverah.openapi`) and `schema.ts` (`npm run generate:api`) yourself; flag both for backend-platform review.
- Ask before committing; never push `main`.

## When the orchestrator dispatched you

Follow the worker rules in `.claude/CLAUDE.md` (Orchestration section). Where they differ from your definition of done, they win: run your cluster, run the full suite only if the brief asks, never commit, and end with the report those rules list (files changed, tests and results, shared files touched, hand-offs, open questions).

## After every task

Update `.claude/agent-memory/manager-match/`: one file per fact (instrument or decoder changes, rulings and why, backfills run and on which DB, open threads). Keep `MEMORY.md` a short index — one line per file. Delete stale entries.
