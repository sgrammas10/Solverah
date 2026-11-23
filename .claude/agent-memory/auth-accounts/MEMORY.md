# auth-accounts memory index

- [OTP error strings are the codes](otp-error-strings-are-the-codes.md) — G8 closed client-side; baseline pins `{"error":"invalid code"}`, never add a wire field without a re-baseline
- [Draft storage sweep](draft-storage-sweep.md) — logout/clearSessionLocally clear per-user drafts by prefix via draftStorage.ts; other lanes hand new keys to auth-accounts
- [sendWithRefresh core](send-with-refresh-core.md) — fetchWithAuth and streamFetch share one refresh core; raw-fetch audit; createApiClient has no refresh and no importers
- [Lane DB + verification recipe](lane-db-and-verification-recipe.md) — solverah_fx_auth pytest command that works; other lanes' in-flight failures are theirs
- [Export/delete C1+C3 tables](export-delete-c1-c3-tables.md) — trait prefs retained (D-01 gated), job postings destroyed with commit=False; closed-schema trap
- [Export/delete C6 company links](export-delete-c6-company-links.md) — retained on employer_name precedent; D-7b question open for Sebastian
- [Export/delete G66 company lookups](export-delete-g66-company-lookups.md) — exported, DESTROYED (no reader); wire change, openapi/baseline regen left to the join
- [G36 "anonymous" claim blocked](g36-anonymous-claim-blocked.md) — audit_log keeps real email + IP on the tombstone id; no deletion copy shipped, fix needs Sebastian's call
- [Recovery flow G34/G35/G37](recovery-flow-g34-g35-g37.md) — resend reads res.ok; both OTP screens ask for email when unrouted; reset never changes password
