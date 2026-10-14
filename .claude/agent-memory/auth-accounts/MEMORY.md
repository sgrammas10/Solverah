# auth-accounts memory index

- [OTP error strings are the codes](otp-error-strings-are-the-codes.md) — G8 closed client-side; baseline pins `{"error":"invalid code"}`, never add a wire field without a re-baseline
- [Draft storage sweep](draft-storage-sweep.md) — logout/clearSessionLocally clear per-user drafts by prefix via draftStorage.ts; other lanes hand new keys to auth-accounts
- [sendWithRefresh core](send-with-refresh-core.md) — fetchWithAuth and streamFetch share one refresh core; raw-fetch audit; createApiClient has no refresh and no importers
- [Lane DB + verification recipe](lane-db-and-verification-recipe.md) — solverah_fx_auth pytest command that works; other lanes' in-flight failures are theirs
- [Export/delete C1+C3 tables](export-delete-c1-c3-tables.md) — trait prefs retained (D-01 gated), job postings destroyed with commit=False; closed-schema trap
- [Export/delete C6 company links](export-delete-c6-company-links.md) — retained on employer_name precedent; D-7b question open for Sebastian
