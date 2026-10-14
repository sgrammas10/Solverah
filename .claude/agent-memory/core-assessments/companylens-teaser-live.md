---
name: companylens-teaser-live
description: WorkPulseResultsPage CompanyLens teaser is now a live link to /company-lens (2026-10-14); how D-15 applied
metadata:
  type: project
---

The legacy results page's "coming soon" teaser and "Fit score: --" placeholders are gone; the card links to `/company-lens` (a real `<Link>`).

**Why a link is allowed:** the D-15 "no links" pins cover the core-instrument completion card (WorkPulsePage / WorkPulseUnlock). WorkPulseResultsPage is the retired 12-question narrative, already full of links, and shows no person-side score. Test asserts no "fit score" and no "%" text.

**How to apply:** if CompanyLens is ever linked from the core completion card, use the button-not-link pattern (as C1 did for /trait-preferences), not a Link.
