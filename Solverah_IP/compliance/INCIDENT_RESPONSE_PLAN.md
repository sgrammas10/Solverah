# Solverah — Incident Response Plan & Secret-Rotation Runbook

**Created 2026-08-20 (GAP-06). One page by design. Review after any real incident and annually.**

## Severity tiers

- **SEV-1:** confirmed unauthorized access to user data (DB, R2 resumes, or a leaked credential with data access). Drop everything.
- **SEV-2:** vulnerability with plausible data exposure but no evidence of access; or account-takeover of a single user.
- **SEV-3:** attempted attacks (credential stuffing spikes, scraping), no access.

## SEV-1/2 checklist — in order

1. **Contain.** Rotate the compromised credential(s) immediately (runbook below). If the API itself is compromised, suspend the Render service — an outage beats an exfiltration.
2. **Preserve evidence.** Export relevant `audit_log` rows and Render/Vercel logs **before** they age out. Note timestamps (UTC) of everything you do.
3. **Assess scope.** Which tables/objects, which users, which fields? `audit_log` (actor, action, IP, UA) is the primary forensic source. Write the scope down even if approximate.
4. **Get counsel.** [ATTORNEY NAME/NUMBER — fill in when engaged]. Breach-notification duties are state-by-state on the *residents affected*, not on Solverah's location; deadlines run from discovery, several states at 30–45 days. Counsel drives the notification decision — do not improvise legal conclusions like "it probably wasn't accessed."
5. **Notify.** Affected users by email, plainly: what happened, what data, what we did, what they should do (password reset first). State AG notifications where thresholds/rules require (counsel). If passwords were exposed (even hashed): force reset all sessions/tokens.
6. **Post-mortem.** Within a week: root cause, what detection was missing, one page, filed in Solverah_IP.

## Secret-rotation runbook

All secrets live in Render env vars (API) / Vercel (frontend) / GitHub Actions secrets (CI). Local `.env` mirrors some — **see S-42: keep prod values out of local `.env`.**

| Secret | Rotate where | Notes |
|---|---|---|
| `JWT_SECRET_KEY` | Render | Invalidates all sessions (1h tokens) — users just re-log-in. Safe anytime. |
| `SOLVERAH_FORM_TOKEN_SECRET` | Render | **Do NOT rotate while assessment forms are in flight** (S-39): breaks open forms. Deploy in a quiet window. |
| R2 `S3_ACCESS_KEY_ID`/`SECRET` | Cloudflare dashboard → Render | Create new key, swap, revoke old. |
| `OPENAI_API_KEY` / `GROQ_API_KEY` | Provider dashboards → Render | Revoke old immediately after swap. |
| `RESEND_API_KEY` | Resend → Render | — |
| `DATABASE_URL` password | Render Postgres | Render-managed; use its rotation. |
| GitHub Actions secrets | Repo settings | Also check Actions logs for leakage when rotating. |

## Standing preparation (the part that makes the above possible)

- ☐ Record Render + Vercel log-retention windows in the vendor register.
- ☐ Enable GitHub secret scanning + push protection on the repo.
- ☐ Keep `audit_log` writing on auth events (exists) — add delete-account and export events (done in this change set).
- ☐ Test account-deletion and export paths after schema changes (suite covers).
- ☐ [ATTORNEY]: engage before launch so step 4 has a phone number.
