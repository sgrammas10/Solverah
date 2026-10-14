---
name: rebaseline-pending-career-status-changed
description: A31 re-baseline (2026-10-02 bug-fix wave) DONE uncommitted; baseline has no LLM-route steps, so LLM error-shape changes are unpinned by it
metadata:
  type: project
---

A31 (docs/ARCHITECTURE.md) re-baselined docs/contract_baseline.json on 2026-10-02, uncommitted on
causal_bayesian_model. Exactly 3 steps moved, each only by the added `"career_status_changed":false`:
`situation-report-complete`, `situation-report-after-pulse-event`, `situation-report-after-past-report`.
After the recapture: 0 differences across 116. I captured on my own DB `solverah_fx_bp_contract`.

**Why it matters:** the 116-step scenario has NO agent or quiz-insight step. The wave's LLM wire
changes (LlmErrorResponse, agent 422->503, request caps) are pinned only by unit tests, not by the
contract.
**How to apply:** if asked to strengthen the contract, add stubbed-LLM steps for /agent/messages
and /me/quiz-insights (the scenario already stubs `_chat_json`). Open proposal: drop
`application/msword` from storage.ALLOWED_MIME, together with public-funnel removing `.doc` from
IntakeForm.tsx/IntakePromptModal.tsx `accept=`. Do not do it alone, or intake .doc uploads start
failing.
