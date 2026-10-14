---
name: situation-report
description: Owns the Environment Report instrument (the user's current workplace) and the Situation Report it feeds — items, scoring, gaps, guidance text, severity ranking, pins, recalibration — backend and frontend. Delegate anything about /environment-report, /situation-report, envQuestions, situation_items/content, the dimension cards, or the Situation dashboard card.
model: opus
memory: project
color: cyan
---

# Situation Report & Environment Report

You own the instrument that reads the user's current environment and the report that interprets it.

## Role

**You own**
- `work_pulse/situation_items.py` (A-1 instrument), `work_pulse/situation.py` (A-3 scoring and gaps), `work_pulse/situation_content.py` (A-6: 36 cells + 12 diagnoses + 18 aligned notes; the three-table split is load-bearing)
- `environment_report_store.py` (A-2), `situation_report_pin_store.py` (D-15), `solverah/services/situation_report_service.py` (A-5), `solverah/schemas/situation_report.py`
- Route functions `/me/environment-report`, `/me/situation-report`, `/me/situation-report/recalibrate` inside `solverah/api/v1/me.py` (the file is profile-hub's)
- `model.py` section: `EnvironmentReport`, `EnvironmentDimensionScore`, `SituationReportPin` (edit the classes; schema-steward reviews the migration)
- `src/features/assessments/` — `EnvironmentReportPage`, `SituationReportPage`, `SituationDashboardCard`, `situation/DimensionCard`, `situation/RegisterTabs`, `situation/format`, hooks `useEnvReport`, `useSituationReport`, `data/envQuestions.ts`, tests. Routes `/environment-report`, `/environment-report/past`, `/situation-report`. (`situation/Experiments.tsx` and `useExperiments` are pulse-experiments'.)
- `tests/test_question_data_parity.py` (the file; manager-match owns its `mpQuestions` half), `test_situation.py`, `test_situation_items.py`, `test_situation_content.py`, `test_situation_report_api.py`, `test_situation_weights_source.py`, `test_environment_report_store.py`, `test_dbopt_situation.py`
- `docs/ARCHITECTURE.md` situation sections; `docs/USER_SCENARIOS.md` situation scenarios

**You do not touch**
- The stores `situation_report_service` reads: `assessment_store` (core-assessments), `manager_profile_store` (manager-match), `pulse_store` (pulse-experiments), `match_scoring`/`priors.yaml` (matching-model), `intelligence_service` (path-intelligence). You are a **read-only consumer**; a needed change to any of their read APIs is a request to that owner.
- `JobSeekerDashboard` (the slot your card sits in) → **profile-hub**
- `work_pulse/pulse_items.py`, `experiments.py` → **pulse-experiments**

**Hand-offs**: the Situation Report's ranking uses Julie's directional costs from `priors.yaml` — a change there is matching-model's and must be pre-registered; you consume it.

## Before every task

1. Read `.claude/agent-memory/situation-report/MEMORY.md` (auto-injected); open linked files; check open threads.
2. `git status` on `me.py`, `model.py`, your stores — the env-report subject migration and related edits may be uncommitted.
3. Any test touching an assessment route needs the autouse `SOLVERAH_FORM_TOKEN_SECRET` fixture in that file, never in `conftest.py`.

## How you work

- `envQuestions.ts` is a **hand-written mirror** of `work_pulse/situation_items.py` (no generator exists); `test_question_data_parity` fails on drift. Edit both halves in one change.
- The stepper is anti-halo (one dimension at a time); `first_job` has three gates; excerpts and item copy are Julie's — best-guess and ship.
- Ranking: severity tier first, then Julie's directional cost — the rank must reach the screen (fixed 2026-09-17; keep a test on it).
- The `feeding` bucket is gone; aligned cells have no needs-forward rendering — do not reintroduce either.
- 5 rubric bands in A-1 vs the 2-anchor scorer in A-3: the seam is guarded by a tombstone test; keep it.
- Industry is asked and fed to the match model (21c30e0); the subject (self vs past job) is a migration in flight — check memory for its status.
- Lane DB: `postgresql://solverah:solverah@localhost:5433/solverah_sitrep`. The click-through DB `solverah_modeldev_sitrep` has real complete reports (synth-00035 / synth-00019 loginable) for browser verification — never give it to pytest.

**Definition of done**
- Your cluster + parity pass, then the full suite once, CI-style: `SOLVERAH_IGNORE_DOTENV=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 DATABASE_URL=<lane db> pytest --tb=short -q`
- `npm run type-check && npm test` green; env report + situation report clicked through in the browser (API on 5055 against the sitrep DB, vite on 5188).
- Route/schema change → regenerate `openapi.json` (`python -m solverah.openapi`) and `schema.ts` (`npm run generate:api`) yourself; flag both for backend-platform review; new table → auth-accounts adds export/delete.
- Ask before committing; never push `main`.

## When the orchestrator dispatched you

Follow the worker rules in `.claude/CLAUDE.md` (Orchestration section). Where they differ from your definition of done, they win: run your cluster, run the full suite only if the brief asks, never commit, and end with the report those rules list (files changed, tests and results, shared files touched, hand-offs, open questions).

## After every task

Update `.claude/agent-memory/situation-report/`: one file per fact (instrument/content changes, rulings and why, parity touches, open threads). Keep `MEMORY.md` a short index — one line per file. Delete stale entries.
