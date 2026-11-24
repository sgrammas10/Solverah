---
name: wpll-retired
description: wpll (anonymous WPLL teaser) retired 2026-11-23 under ruling C; 410 kind_retired everywhere, no anonymous door left; owner constraint still grants NULL wpll rows
metadata:
  type: project
---

`wpll` was retired on 2026-11-23 (Sebastian's ruling C) when `/start` was deleted. `/start`'s TeaserResult was the only caller of the anonymous `wpll` scoring job, and no signed-in flow used the kind either. It was retired the same way as `work_pulse` ([[legacy-work-pulse-retired]]), not deleted from the registry. The catalogue still lists it, and claimed legacy rows still count as completed.

- Every write door (submissions, scoring-jobs POST, poll) answers 410 `kind_retired` with `RETIRED_WPLL_MESSAGE`, before auth. An ownerless wpll job queued before the deploy fails in the worker (`_score_assessment` checks `kind.retired` before the owner lookup), with no provider call.
- Deleted: `wpll_insight`, `build_wpll_insight_prompt`, the Wpll* schemas, `find_anonymous`, `requires_auth` on `AssessmentKind` (the catalogue still emits `requires_auth: true`), and the global-key ceiling on the enqueue. `JOB_ELIGIBLE_KINDS = ("manager_match",)`.
- Kept: `work_pulse/insight_engine.py`, because Pulse reads `QUESTION_DIMENSIONS`. Its `generate_result`/templates have no app caller now.
- Not done (Sebastian decides): tightening `ck_scoring_jobs_owner_required` to plain `user_id IS NOT NULL` needs a migration. Purge or fail any NULL-owner rows first. The 7-day purge removes terminal ones; queued or running ones get reaped after 30 minutes, then purged.
- The `wpll_completed` session flag can only be true for legacy claimed rows. public-funnel removed the session claim the same day.

**Why:** the anonymous path cost LLM money and had no caller after `/start` went.
**How to apply:** don't reopen wpll behind auth. A new teaser is a new kind.
