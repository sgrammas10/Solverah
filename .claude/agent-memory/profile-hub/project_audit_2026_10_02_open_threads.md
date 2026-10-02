---
name: audit-2026-10-02-open-threads
description: Read-only lane audit 2026-10-02 (pre Julie content day) found these unfixed bugs in profile/resume/dashboard/hub; check each is still open before acting
metadata:
  type: project
---

Read-only audit for the orchestrator, 2026-10-02, ahead of Sebastian+Julie's content day (~2026-10-09). Nothing was fixed in that session. Open threads, most severe first:

1. Resume parse REPLACES experience/education/skills wholesale (`resume_jobs.run` merge `{**existing, **profile_updates}`); an empty extraction (.doc is accepted but never parsed, scanned PDF, 30s timeout, refused docx) wipes them and reports `succeeded`.
2. Parser `duration` ("March 2019 - Present") lands in `endDate`, `startDate` always "" -> invisible in `type="month"` inputs, and current role never detected.
3. Server never sends `profileComplete`; dashboard "Complete your profile" alert shows for every user after any reload.
4. Experience/education add/edit/remove never call `setIsSaved(false)` -> no unsaved strip, no beforeunload.
5. Save failure: no error shown, the bar says "Saved", and the optimistic cache write is not rolled back.
6. Once set, career status cannot be changed from the UI (modal only reachable via router state while unset; unchecking current role never clears "employed").
7. Dashboard query never invalidated client-side (60s staleTime) -> stale recs after profile/status/pulse writes.
8. Dashboard career_status rec passes no returnTo -> after saving, the user is dumped on /intelligence/paths.
9. Recs empty state says "Suggestions start after Work Pulse" when the client filter hid everything for a user who HAS done it.

**Why:** these block clean content review: Julie will role-play statuses and upload resumes.
**How to apply:** before the next task in this lane, grep each site; strike the fixed ones from this file. See [[resume-parse-runs-inline-in-prod]].
