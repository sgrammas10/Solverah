---
name: g36-anonymous-claim-blocked
description: G36 FIXED 2026-11-23 (uncommitted at time of writing) -- deletion scrubs the user's audit rows via a metadata allowlist and truncates kept company links to the month; residual re-identification gaps and the rule for new audit metadata keys
metadata:
  type: project
---

G36 was blocked on 2026-11-23 because "anonymous" was false: `audit_log` kept the account's real email (`intake_link_account` metadata) and an IP on every row under the tombstone id. Sebastian ruled the same day: **A** scrub the audit rows on deletion, **B** kept company links keep month precision only. Built the same day.

**What deletion now does** (`account_repository.anonymize_retained_rows`, called from `delete_account` AFTER the `account_deleted` event is added, same transaction):
- every `audit_log` row with `actor_user_id` = the user: `ip_address`/`user_agent` NULL, `metadata` cut to `AUDIT_METADATA_KEPT_KEYS` (an ALLOWLIST).
- `user_company_link.started_on`/`ended_on` truncated to the 1st of the month via `company_evidence_store.coarsen_company_link_dates_for_user` (matching-model's file, one function added by me).

**Why an allowlist:** the leaking keys were ones nobody thought of as personal (`email`; legacy `error: str(exc)` from pre-refactor `email_send_failed` rows still in prod). A new metadata key is dropped on deletion until someone adds it to the tuple.

**How to apply:**
- Any lane adding a `log_audit_event` metadata key that should survive deletion must hand it to auth-accounts; only counts, booleans, closed vocabularies. Never ids of rows deletion destroys.
- `actor_user_id` filtering is complete only while every audit call passes the acting user and no anonymous event stores an email. If someone adds a failed-login audit row with an email in metadata, the scrub must grow a second match.
- The copy on /settings ("anonymous record ... which company, and the month you started and left") is pinned by a test in AccountSettingsPage.test.tsx; it is a promise the two mechanisms above keep.

**Residual gaps reported, not fixed (other lanes / rulings):**
- `record_read_event` is queued: a profile-read or export event enqueued just before DELETE can be written by the worker AFTER the scrub, with IP. Fix belongs in `audit.write_event` (backend-platform): drop the fingerprint when the actor's `users.status` is `deleted`. retention_cleanup still nulls it at 365 days.
- (closed same day: `created_at` on kept links is also truncated to the month, UTC, by the same store function.)
- `environment_reports.employer_name_normalized` is user-typed free text, still retained (D-7b question, see [[export-delete-c6-company-links]]).
- `audit_log` has no index on `actor_user_id`; the scrub scans every partition.
- Privacy policy text (`src/shared/lib/legal.ts`, public-funnel) does not mention the kept company record.
