---
name: audit-2026-10-02-open-findings
description: Lane audit 2026-10-02 — only the archetype fallthrough (77% "The Operator") is still open; F2-F6 and F8 fixed same day in the fix wave (uncommitted), plus one core-assessments hand-off for a 400 at enqueue
metadata:
  type: project
---

Lane audit run 2026-10-02 for the orchestrator, ahead of Sebastian + Julie's content sprint (~2026-10-09). The fix wave the same day closed everything technical; one item stays open because it needs Julie's rules.

**Still open**
- **F1, archetype fallthrough** (`manager_match/score.py`, the `else: "The Operator"` default). Enumerating all 2^15 answer patterns: 76.9% get "The Operator", 67.1% via the default branch, and 16.4% are users with autonomy >= 0.65 (a low-autonomy archetype on a high-autonomy user). A fix changes what ManagerMatch scores, so it needs Julie's archetype rules, a SCORING_KEY bump, a backfill, and a core-assessments conversation (it rides the unified submissions route). The backfill cannot regenerate stored LLM narratives, so those stay stale.
- **Hand-off to core-assessments (F4 follow-up):** a bad `question_id` now fails the scoring JOB with the scorer's own message, not a 400 at enqueue. A 400 needs `assessment_service.precheck`'s manager_match branch to call `score_manager_match(answers)` in try/except ValueError and return `_error(400, str(exc))`. Two tests in `test_manager_match_api.py` (invalid choice, bad id) would then flip from failed-job to 400.

**Fixed 2026-10-02 (fix wave, uncommitted when written)**
- F2: the `useMM` draft key is now `mm_answers:<userId>` (the legacy bare key is deleted on sight, never adopted). `clearAnswers()` runs on scoring success. A complete draft found on mount asks `GET /me/assessments/manager_match/result` first: a stored result means redirect to results, a 404 means score the draft, any other error means go to results with no re-score. auth-accounts' `draftStorage.ts` logout sweep matches the `mm_answers` prefix, so the two fixes fit together.
- F3: MM success invalidates `managerPlaybookKeys.all`.
- F4: `score_manager_match` rejects unknown, missing, duplicate and non-dict answers with a ValueError.
- F5: the `mmQuestions.ts` parity test is in `tests/test_question_data_parity.py`; the 8 straight apostrophes were changed to curly to match Python.
- F6: `ManagerMatchResultsPage` checks for "no result" with `isNoManagerMatchResult` (status 404), not by matching the message text.
- F8: the decoder docstring now names `mm-q10` (0.70/0.30) and `mm-q14` (0.75/0.25) as off-anchor. A test makes sure any off-anchor item is named there. No threshold or anchor changed.

**Why:** the content sprint must stay on content.
**How to apply:** when asked what's left in this lane, start with F1. When F1 is fixed, record the new SCORING_KEY and which DBs the backfill ran on. Before acting on any of this, check git, because the fix wave may since have been committed or reverted.
