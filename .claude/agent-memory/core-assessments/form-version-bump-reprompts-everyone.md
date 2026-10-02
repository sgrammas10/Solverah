---
name: form-version-bump-reprompts-everyone
description: Changing form_version in assessment_items_v2.yaml is a new instrument -- every completed user reverts to not-completed; wording-only edits do not change item tokens
metadata:
  type: project
---

`scoring_key_version = form_version + "+" + scoring.method`. `has_completed_assessment` and `get_dimension_scores` key on it, so bumping `form_version` (currently `v2-2026-08-18`) flips every user back to the Work Pulse prompt and hides their dimension scores. Item tokens are HMAC(respondent, item_id), so editing wording alone changes no token and breaks no in-progress draft. Changing an item_id does break drafts AND makes `score_stored_choices` fail on old pinned sittings. `first_/latest_completed_core_submission_id` are NOT version-keyed.

**Why:** Julie owns instrument content and may edit item wording. Nothing forces or forbids a version bump on a content edit. The 2026-10-02 audit raised this as an open question for Sebastian.

**How to apply:** for any item-bank edit, ask whether it is wording-only (keep form_version) or a new instrument (bump it; Situation Report pins then rescore old raw rows against the new file). Never rename an item_id casually. Also check `wpQuestions.ts`/`wpllQuestions.ts` mirrors by hand. See [[core-has-no-retake-entry]].
