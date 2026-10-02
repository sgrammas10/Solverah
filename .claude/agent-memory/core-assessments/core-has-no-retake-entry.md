---
name: core-has-no-retake-entry
description: The 24-item core (Work Pulse) cannot be retaken from the UI, yet /trust, the D-15 pin and Situation Report "recalibrate" all assume retakes exist
metadata:
  type: project
---

Once `wp_v2_completed` is true, WorkPulsePage renders only the completion card; no link anywhere in the SPA starts a second core sitting. But TrustPage promises "a retake does not overwrite the sitting before it", PRODUCT_DECISIONS/BUILD_PLAN flag 5 pin the Situation Report to the first sitting with an explicit "recalibrate" re-pin, and SituationReportPage ships a Recalibrate button. With one sitting possible, recalibrate always answers `recalibrated: false`.

**Why:** found in the 2026-10-02 pre-Julie-sprint lane audit; asked Sebastian whether and when core should be retakeable (a cooldown? only after N months?). Not decided as of that date.

**How to apply:** do not build a retake button without his ruling. If he rules yes, the entry belongs on the completion card and the Intelligence card. Situation-report owns recalibrate. See [[form-version-bump-reprompts-everyone]].
