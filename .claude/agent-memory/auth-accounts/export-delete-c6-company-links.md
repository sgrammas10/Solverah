---
name: export-delete-c6-company-links
description: 2026-10-13 user_company_link (C6) exported as company_links and RETAINED on deletion by the environment_reports.employer_name_normalized precedent; the D-7b tension that leaves open for Sebastian
metadata:
  type: project
---

`user_company_link` (C6, "I took this job"): exported as `company_links` (newest start first; id, company_id, started_on, ended_on, created_at; no user_id). RETAINED on account deletion under the tombstone. `delete_personal_rows` deliberately does not call `delete_company_links_for_user`.

**Why retain:** the orchestrator expected DESTROY but told me to follow house precedent. The precedent for an employer identity tied to a person is `environment_reports.employer_name_normalized` (flag 6 in PRODUCT_DECISIONS), which survives the tombstone, kept for the future aggregation lane. The link also passes the D-7b spelling test (no free text) and it has a research reader: PRODUCT_DECISIONS §2, "What changes the weights" (4) and (5), the 90-day check-ins tied to the CompanyLens read. That reader is the thing `path_wants` and `path_feedback` lack. Destroying the links would NULL `pulse_checkins.company_link_id` and strip what C8 added the column for.

**Open threads (2026-10-13):**
- A question for Sebastian: `employer_name_normalized` is user-typed free text. D-7b says free text is never retained de-identified, so the precedent itself may be an oversight from D-7. If he rules it must go, both it and the links flip to destroy. For the links that is one line, `delete_company_links_for_user(db, user_id, commit=False)` in `delete_personal_rows`, plus flipping `test_delete_retains_company_links_and_the_checkins_keep_their_anchor`.
- Docstrings outside this lane still describe destruction: `company_evidence_store.delete_company_links_for_user` ("the account-deletion read") and the model.py comment on `PulseCheckin.company_link_id`. Matching-model and pulse-experiments own those files.
- `ExportedPulseCheckin` gained `company_link_id`. pulse_store serialised it, and the closed export schema rejected it.

Related: [[export-delete-c1-c3-tables]].
