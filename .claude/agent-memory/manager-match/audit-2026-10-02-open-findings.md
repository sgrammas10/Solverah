---
name: audit-2026-10-02-open-findings
description: Read-only lane audit 2026-10-02 (pre Julie content day) — archetype fallthrough labels 77% of answer patterns "The Operator"; mm_answers never cleared on success; mmQuestions.ts has no parity test
metadata:
  type: project
---

Lane audit run 2026-10-02 for the orchestrator, ahead of Sebastian + Julie's content day (~2026-10-09). Nothing was fixed in that pass; these are open until a fix chunk lands. Verify each against the code before acting — the fix may have landed since.

1. **Archetype fallthrough** (`manager_match/score.py`, the `else: "The Operator"` default). Enumerating all 2^15 answer patterns: 76.9% get "The Operator", 67.1% via the default branch, and 16.4% are users with autonomy >= 0.65 (a low-autonomy archetype on a high-autonomy user). Changing it changes what ManagerMatch scores: needs Julie's archetype rules, a SCORING_KEY bump, a backfill, and a core-assessments conversation (rides the unified submissions route). Stored LLM narratives would stay stale (the backfill cannot regenerate them).
2. **`mm_answers` sessionStorage is never cleared on scoring success** (`ManagerMatchPage.tsx` success effect), and the mount effect auto-resubmits any complete 15-answer draft when the in-memory query cache is empty (after a reload). Result: re-entering `/manager-match` (e.g. "Start ManagerMatch" on WorkPulse results / Situation Report) after a reload re-scores silently, which costs an LLM call and replaces the narrative. In a shared tab it also submits the previous user's answers as the next user's. `useMP` clears on success, so only MM has this.
3. **`mmQuestions.ts` is not covered by `tests/test_question_data_parity.py`** (only mp/env are). Today it differs from `questions.py` only in curly vs straight apostrophes (8 items).
4. MM success does not invalidate `managerPlaybookKeys`, so a cached playbook can sit stale for up to 60s after a ManagerMatch retake.
5. `score_manager_match` has no unknown or duplicate question_id check (it raises KeyError, so the job fails with a generic message instead of returning a 400). `manager_profile._validate` already has these checks.

**Why:** the content day must stay on content, so these were scoped as technical pre-work.
**How to apply:** when asked what is left in this lane, start here. When #1 is fixed, record the new SCORING_KEY and which DBs the backfill ran on.
