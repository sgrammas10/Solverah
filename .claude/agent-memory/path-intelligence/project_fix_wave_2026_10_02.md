---
name: project-fix-wave-2026-10-02
description: Path page fix wave 2026-10-02 (uncommitted at write time) - four audit bugs fixed frontend-only; two sync obligations and one profile-hub hand-off it left open
metadata:
  type: project
---

Fix wave dispatched by the orchestrator 2026-10-02, ahead of the Sebastian/Julie content
sprint (~2026-10-09). All four audit items fixed in `PathIntelligencePage.tsx` (plus a
comment in `usePathFeedback.ts`); no backend, schema or openapi change. Left uncommitted.

Sync obligations this created:
- `fallbackWhyText` in PathIntelligencePage is a CLIENT COPY of
  `intelligence_service._overlap_sentence`. Change one, change the other (no test ties them).
- Deep-fit cache: the QueryClient outlives navigation (the old staleTime comment claiming a
  new client per navigation was false). `fetchSuggestions` now removes `pathFitKeys.all`;
  any new route into a fresh scoring must go through `fetchSuggestions` or it re-opens the bug.

Open hand-off (profile-hub): AddSkillsPrompt now sends `{returnTo}` only (NOT
`showCareerStatusModal`, which would re-ask a user who already has a status). But
JobSeekerProfile shows the "go back?" dialog only on a save where career_status becomes
"employed", so a between_jobs/first_job user adding skills gets no way back. Theirs to fix.

**Why:** a content sprint on the built product needs every technical bug gone first.
**How to apply:** check `git log` for whether this landed before building on it. See
[[project-deploy-gate-state]].
