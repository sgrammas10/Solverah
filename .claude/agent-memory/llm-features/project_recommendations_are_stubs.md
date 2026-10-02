---
name: recommendations-are-stubs
description: /me/recommendations and /refresh are permanent empty stubs with no frontend caller; JobRecommendation rows and the jobMatches stat are always 0
metadata:
  type: project
---

As of 2026-10-02 both `/me/recommendations` (GET) and `/me/recommendations/refresh` (POST)
return `{"data": [], "next_cursor": null}` unconditionally. The only frontend reader,
`useRecommendations.ts`, has no consumer since Feed/Search went coming-soon 2026-09-28;
the refresh route has no caller outside tests/openapi/contract baseline. `JobRecommendation`
is never written, so `profile_service`'s `jobMatches` stat is always 0 (and is not rendered).

**Why:** the old ML pipeline was replaced by the agent; the Groq successor was never built.
**How to apply:** removing either route is a contract change (openapi + contract baseline +
schema.ts); ask Sebastian whether to tombstone before touching. See [[audit-2026-10-02-open-threads]].
