---
name: fix-wave-2026-10-02-decisions
description: Non-obvious design choices made fixing the 2026-10-02 profile/resume/dashboard audit, and why; read before changing career status, the profile form's hydration, or dashboard recs
metadata:
  type: project
---

Choices made in the 2026-10-02 fix wave that a later change could silently undo:

- **Career status belongs to the control, not the form.** `CareerStatusControl` (Experience tab) saves at once via PATCH /me/career-status. `handleSubmit` strips `career_status` from the draft and derives "employed" from a "Present" role ONLY when no status is stored -- an explicit between_jobs/first_job is never flipped back by a profile save. Why: otherwise a stale status held in the form reverts the control's write.
- **The form is not re-hydrated while dirty.** After the first fill, `useProfileForm`'s hydration effect skips document changes while `isSaved` is false (it re-runs when a save lands). Why: the status control and resume parse write the cached document mid-edit, and re-filling discarded unsaved edits.
- **No optimistic writes on profile save.** Caches are written only from the server answer; the name goes to users.name through PATCH /me after the profile PATCH (separate error copy if only the name fails). Chosen over snapshot+rollback because a rollback re-fills the form and loses the draft.
- **Resume parse:** empty parsed section = keep stored one (`domain.profile.merge_resume_parse`); no text at all = `resume_service.NoResumeText` -> job `failed` with `NO_TEXT_MESSAGE`; storage errors stay GENERIC_FAILURE; intake still degrades to an empty parse.
- **Dashboard recs:** server sends every applicable step (RECOMMENDATION_LIMIT=6 backstop); the client filters what lead cards offer, then shows 3. '/pulse' is no longer in `hrefsOfferedElsewhere` (the pulse step fires only when due). Dashboard query is `refetchOnMount: 'always'`.
- "Complete your profile" alert shows when `profileCompletion` < 100%. Proficiency 2/4 rounds DOWN to the named level.

me.py: NOT edited in this wave (situation-report had an in-flight docstring edit there).

**How to apply:** if Sebastian/Julie rule differently (e.g. a save should auto-set employed), change these deliberately and update the regression tests that pin them.
