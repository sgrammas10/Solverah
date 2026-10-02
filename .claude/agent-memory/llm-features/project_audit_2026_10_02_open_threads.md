---
name: audit-2026-10-02-open-threads
description: Read-only lane audit 2026-10-02 before the Julie content day; ranked open bugs in agent chat, guest quiz, insight storage, cost caps — check which are fixed before re-reporting
metadata:
  type: project
---

Lane audit run 2026-10-02 (orchestrator dispatch, read-only, nothing fixed in that pass).
Top open threads at that date — verify against code before acting, some may be fixed since:

1. `streamFetch` (AuthContext.tsx, auth-accounts' file) has no 401 -> refreshSession -> retry,
   unlike `fetchWithAuth`. AgentChat uses only streamFetch, access token is 15 min, so a chat
   past 15 min fails with an error banner. Fix in AuthContext (hand-off) or retry in AgentChat.
2. Guest lockout (`markGuestQuizCompleted`) is set BEFORE the insight call in all three quiz
   components, and submit is not gated on answers -> any 400/429/500 locks the guest out with
   nothing; an empty pending save then fails the replay POST on every login, never cleared.
3. G20 guest insight is router-state only; its empty state links to the locked list (dead end).
4. `insight_service._generate` returns the raw provider exception text in the 500 body, and
   the modal renders it to users.
5. Agent accepts a client-chosen `model`, any `role` (incl. system), unbounded history, no
   max_tokens. Quiz endpoints have no item/length caps (guest = anonymous LLM proxy, 500/day).
6. NextChapter/YourFuture post `quizGroup: careerQuizzes` with one quiz, so the group's
   `_overallInsight` ("Across All Your Quizzes") becomes a one-quiz synthesis.
7. Those two components read stored insights from the flat key, but signed-in writes nest
   under `careerQuizzes.<key>`; guest replay (G16) writes the flat key — two homes.
8. No profile-cache invalidation after a signed-in POST /me/quiz-insights (G22 twin).
9. D-1 never gave the agent a product primer or Situation Report context.

**Why:** Sebastian + Julie spend a content day on these features the week of 2026-10-09;
technical bugs had to be cleared first so the day stays on copy.
**How to apply:** start any lane task by checking which of these are still open; related
[[recommendations-are-stubs]].
