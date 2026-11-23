---
name: g36-anonymous-claim-blocked
description: 2026-11-23 G36 deletion copy ("we keep ANONYMOUS company data") NOT shipped -- audit_log keeps the real email and IP keyed to the tombstone id, so "anonymous" is false; decision returned to Sebastian
metadata:
  type: project
---

G36 (settings deletion copy should say company data is kept, "anonymous") was STOPPED before any copy change, 2026-11-23. Checked the claim first and it fails.

**Why "anonymous" is false:** retained rows (user_company_link, environment_reports, assessment rows, pulse_checkins...) all key on the tombstone `users.id`, and `audit_log` rows are kept pointing at that same id (`actor_user_id`). Two audit fields still identify the person:
- `intake_link_account` events store the account's real email in `metadata` (`intake_service.link_account`, metadata `{"submission_id", "email": current_email}`). Nothing scrubs audit metadata -- not delete_account, not retention_cleanup. Forever.
- every audit row carries `ip_address`/`user_agent`, including the `account_deleted` event itself; `retention_cleanup._minimize_audit_pii` nulls them only after 365 days.
Softer: `environment_reports.employer_name_normalized` is user-typed free text (D-7b tension, see [[export-delete-c6-company-links]]), and company_id + exact start/end dates is a quasi-identifier at a small employer.

**The existing copy has the same flaw:** "assessment responses are kept only in de-identified form, no longer linked to you" rests on the same tombstone + audit join. Flagged, not changed.

**How to apply:** if Sebastian rules the fix in, it is mine: in `delete_account` scrub the user's audit rows (drop `email` from metadata, null ip/user_agent) or re-point `actor_user_id` to NULL, plus log `account_deleted` without IP; then the copy can ship. If he rules the wording instead, use "not linked to your name or email" only after the metadata scrub, never before.
