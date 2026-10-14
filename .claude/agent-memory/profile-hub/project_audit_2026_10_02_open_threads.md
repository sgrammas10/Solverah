---
name: audit-2026-10-02-open-threads
description: Read-only lane audit 2026-10-02 found 9 profile/resume/dashboard bugs; the same-day fix wave fixed all of them (uncommitted); what is still open after it
metadata:
  type: project
---

The 2026-10-02 audit (pre content day ~2026-10-09) listed 9 bugs; the orchestrator's fix wave the same day added 4 more (name to users.name, G12 unknown tab, proficiency 2/4 KeyError, career_status validation on PATCH /me/profile). All 13 were fixed in the working tree, UNCOMMITTED as of 2026-10-02 -- check `git log` before assuming they landed. Decisions taken in that wave: [[fix-wave-2026-10-02-decisions]].

Still open after the wave:
- Backend MIME allowlist `infra/storage.py` ALLOWED_MIME still accepts application/msword (backend-platform's file). The parse now fails .doc with a clear message, and our picker no longer offers it, but the intake forms (IntakeForm.tsx, IntakePromptModal.tsx, public-funnel's) still accept .doc.
- Profiles parsed BEFORE the fix still hold "March 2019 - Present" in endDate with startDate "" (invisible in month inputs). No backfill written.
- Replace vs merge for a NON-empty parsed section: Sebastian's open decision; filled sections still replace wholesale.
- No in-app navigation guard for unsaved edits (needs frontend-shell); only beforeunload.
- Not browser-verified against a local API in that wave (cluster tests + type-check only).

**Why:** Julie will role-play statuses and upload resumes on content day.
**How to apply:** before the next task, verify the wave landed (grep `merge_resume_parse`, `CareerStatusControl`); strike items here as they close. See [[resume-parse-runs-inline-in-prod]].
