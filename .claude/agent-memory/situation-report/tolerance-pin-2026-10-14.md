---
name: tolerance-pin-2026-10-14
description: Situation Report tolerance follows D-15 (Sebastian + orchestrator rulings 2026-10-14) - as-of anchor, then first-step-after-pinned-sitting fallback; what was ruled on the four questions
metadata:
  type: project
---

**Ruling** (Sebastian, 2026-10-14, PRODUCT_DECISIONS §2 six-trait "Follow-up rulings"):
a tolerance change reaches the Situation Report at the next fixed sitting. Built
uncommitted on 2026-10-14. `_pinned_trait_preferences` in the service picks the sitting,
in this order:

1. The latest tolerance sitting at or before `_tolerance_as_of`, which is
   max(first current env report `submitted_at`, pin moment). The pin moment is the
   explicit override's `pinned_at`, otherwise the default sitting's `completed_at`.
2. Otherwise, the FIRST sitting created after the pinned core sitting's `completed_at`
   and before the next core sitting's (`assessment_store.first_trait_preferences_after`).
   The orchestrator ruled this on 2026-10-14. **Why:** the step that follows an
   assessment belongs to that sitting. Without this, env-first users were stuck. A
   single first answer is not probing.
3. Otherwise unanswered, which is today's report bit for bit.

A second change waits for a re-pin. There is no tolerance-only re-pin: Recalibrate needs
a newer core sitting (ruled to stay that way). `assessment_store.get_trait_preferences`
gained `as_of=`; that file belongs to core-assessments.

**Ruled, no code:**
- Training rows keep tolerance as of each report's `submitted_at`. They record what the
  user held when describing that job, and they are exploratory (Amendment 3(c)).
- The CompanyLens partial probe is accepted for now, because company estimates are not
  shown. The orchestrator is putting it in the backlog.

**Hand-off:** the contract step `situation-report-with-preferences` PUTs tolerance after
filing. Under rule 2 that answer is still the user's FIRST sitting, so it should still
apply. Backend-platform should verify this on recapture.
