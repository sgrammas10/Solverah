---
name: rebaseline-a33-companylens
description: A33 re-baseline (six-trait CompanyLens + C5c research switch, 2026-10-14) DONE uncommitted, 156 steps; both provider keys and the research switch are popped at the top of run_scenario; LLM-route (agent/quiz-insight) steps still absent
metadata:
  type: project
---

A33 (docs/ARCHITECTURE.md) re-baselined docs/contract_baseline.json on 2026-10-14, uncommitted on
causal_bayesian_model. Pre-change verify against A32: exactly 7 differences, all body-only, all additive
(`pulse-history`, both `submit-*environment-report`, the three `situation-report-*`, `export`). 40 steps
appended (116 -> 156): 36 CompanyLens steps, then 4 `research-company-*` steps appended last because C5c
(the `SOLVERAH_COMPANYLENS_RESEARCH_ENABLED` switch, default OFF) landed after the first 36 were recorded.
C5c also moved `post-job-posting-provider-unavailable` in place (LegacyError -> `provider_unavailable`
problem document). After recapture 0 differences across 156. Captured on `solverah_contract`; the pytest
cluster ran on `solverah_contract_tests` (created 2026-10-14 with citext/pg_trgm/vector) so capture and
pytest never share a DB.

**Traps for the next re-baseline (A34):** `run_scenario` pops `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and
the research switch at the top; a step that needs a provider must stub at the service layer like
`_stub_llm`. The two research refusals ask about the same unseeded name (`FRESH_COMPANY_NAME`) because a
refused request writes no Company row -- if a lane ever creates the row before the refusal, the second
refusal becomes a different request and the diff says so. `sitting_id` (trait-preferences export) is a
per-run `uuid4().hex`, masked `<SITTING>`.
**Still open (cross-lane hazard):** `company_research.jobs.dispatch` (matching-model, jobs.py:71) reads the
Flask app off the Celery conf (`solverah_flask_app`, whatever `create_app()` ran last) to decide inline vs
thread pool; any test that calls `create_app()` before the lens tests sends research to a thread and
deadlocks `drop_all`. I made `test_config.py`'s entrypoint test restore the conf; the robust fix is for
`dispatch` to prefer `current_app` inside an app context. Also still open: no agent or quiz-insight step, so LLM error shapes are pinned only by unit tests. The
`.doc` MIME-drop proposal from A31 (storage.ALLOWED_MIME + IntakeForm/IntakePromptModal `accept=`
together, never alone) is still open. Generator limitation worth knowing: declared problem responses
(400/422/503 `PROBLEM_RESPONSE_MODEL`) are documented under `application/json` content while served as
`application/problem+json`; only the `default` response says problem+json. Pre-existing, not A33's.
See [[contract-seeds-legacy-work-pulse]].
