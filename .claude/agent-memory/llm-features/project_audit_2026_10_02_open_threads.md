---
name: audit-2026-10-02-open-threads
description: Lane audit 2026-10-02 + same-day fix wave; which agent/quiz/insight bugs were fixed (uncommitted at the time) and which stay open (primer, recommendations tombstone, queue)
metadata:
  type: project
---

Read-only lane audit 2026-10-02, then a fix wave the same day (orchestrator
dispatch; changes left UNCOMMITTED for Sebastian). Verify against code/git log
before trusting the status column.

FIXED in the 2026-10-02 wave:
- #2 guest lockout: lockout + pending save written only after a successful
  insight (`completeGuestQuiz`), submit gated on answers, empty saves never
  stored/returned, Login replay merges careerQuizzes one level deeper and clears
  the save on a non-retryable 4xx (keeps it on 401/408/429/5xx).
- #3 G20: guest insight stored INSIDE the pending save (localStorage, not the
  sessionStorage the brief named, because sessionStorage does not survive a
  fresh tab); locked-out empty state offers sign-in.
- #4/#14 generic error bodies + stable `code` (LlmErrorResponse); agent never
  names Groq or the model; coerce forces list fields to lists.
- #5 caps -- see [[agent-and-quiz-cost-caps]].
- #6/#7/#8/G16 one insight home -- see [[quiz-insight-storage-home]].
- G19 guest Back on unknown quiz -> /quiz-preview. #13 AgentChat abort/partial/
  cut-off/empty/no 40ms delay.

STILL OPEN:
- #1 streamFetch 401 refresh: auth-accounts was fixing it in AuthContext the
  same day; confirm it landed.
- #9 agent product primer / Situation Report context: waits on copy decision.
- Tombstoning /me/recommendations ([[recommendations-are-stubs]]), /future-your-way,
  and moving quiz insights onto the llm queue: explicitly deferred.
- Intake route's @document still says 500 is LegacyError (public-funnel's file);
  body now also carries `code`.

**Why:** Sebastian + Julie content day on these features the week of 2026-10-09;
technical bugs had to be gone first so the day stays on copy.
**How to apply:** start any lane task by checking the STILL OPEN list.
