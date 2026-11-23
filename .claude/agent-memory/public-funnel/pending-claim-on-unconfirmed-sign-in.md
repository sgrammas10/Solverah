---
name: pending-claim-on-unconfirmed-sign-in
description: How a hero-form sign_in claim that hits 403 (email unconfirmed) is parked server-side and completed at email confirmation; why it is not client-side
metadata:
  type: project
---

Sebastian ruled 2026-11-23 that a hero submission must end up on the account even when the modal's sign-in stops at "email not confirmed". Built server-side, with no migration and no wire change: at the 403 (password already verified, submission email already matched) `intake_service.sign_in` sets `intake_submissions.status` to `claim_pending:<user_id>`; `auth_service.confirm_email` calls `intake_service.apply_pending_claims(user)` in its own transaction.

**Why:** security was the constraint. Knowing an email must never attach a submission. The server already holds the full proof at the 403, so nothing is kept in browser storage, nothing can be adopted by another account on the same tab, and it works when the code is entered on another device. The user id is inside the status value so a parked claim can only complete on the account whose password parked it.

**How to apply:** `status` is a free String(50) with these values now: uploaded, account_created, account_linked, claim_pending:<id>. Anything that starts filtering on status must expect the fourth. The hook in `auth_service` (auth-accounts' file) is a function-level import because `intake_service` imports `auth_service`. Each parked claim merges in a savepoint so a bad one never blocks email confirmation.
