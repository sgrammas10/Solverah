---
name: quiz-insight-storage-home
description: Where quiz answers and insights live on the profile doc since 2026-10-02 (one careerQuizzes home), the overall-synthesis coverage rule, and the legacy flat keys still read
metadata:
  type: project
---

Since 2026-10-02 every quiz insight (all six quizzes) is written to
`quizInsights.careerQuizzes.<key>`; the SPA always posts quizGroup
"careerQuizzes" with EVERY saved quiz (`quizPayload.buildAllQuizzesPayload`),
guest previews included. Answers keep their two homes:
`quizResults.careerQuizzes.<key>` for the four career quizzes, flat
`quizResults.careerJobSearch` / `quizResults.yourFutureYourWay`.

`_overallInsight` ("Across all your quizzes") is replaced only when the posted
quiz keys cover every quiz already stored in the group; `_overallKeys` records
what it covers. A partial post updates its own entries only.

Legacy: flat `quizInsights.careerJobSearch` / `.yourFutureYourWay` docs (old
guest replay, G16) are still READ as fallback, and deleted server-side when that
quiz is next written into the career group. The backend still accepts flat
quizGroups (back-compat), the SPA no longer sends them.

**Why:** two homes meant stored insights never preloaded and a replayed guest
insight never showed under /quiz-insights (audit #6/#7, G16).
**How to apply:** new quiz -> add it to `ALL_QUIZZES` in quizPayload.ts; never
write a flat group from the SPA. Related [[agent-and-quiz-cost-caps]].
