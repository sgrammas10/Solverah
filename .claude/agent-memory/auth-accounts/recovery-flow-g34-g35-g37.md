---
name: recovery-flow-g34-g35-g37
description: G34/G35/G37 fixed 2026-11-23 (uncommitted at write time) — resend reads res.ok, both OTP screens ask for the email when unrouted, "forgot password" copy says sign-in-with-code
metadata:
  type: project
---

Three auth-screen gaps from docs/USER_SCENARIOS.md §1.2 were fixed on 2026-11-23 by an orchestrator dispatch. The follow-up was approved the same day. None of it was committed when this note was written.

- **G34**: `ForgotPasswordVerify` resend now throws `parseApiError(res, data)` with **no** call-site fallback, so a body-less failure gets apiError's status wording. `ConfirmEmail`'s resend already checked `res.ok`. Its network failure now reads "Network error. Please try again." instead of the runtime's "Failed to fetch".
- **G35 and its twin**: with no router state and no `?email=`, both `/verify-email` (ConfirmEmail) and `/forgot-password/verify` show an "Email address" input. The typed value is trimmed and lower-cased. Submit and resend report the missing address and send nothing. `/forgot-password/verify` now also reads `?email=`, matching `/verify-email`.
- **G37**: `/auth/password/reset` never changes the password. It only mints a session. The login link reads "Forgot your password? Sign in with a code", and the page says "Your password stays as it is." Don't add copy that promises a reset unless a real new-password form exists.

**Why:** these were found by reading the code during the 2026-10-25 re-derive. The 429 copy relies on backend-platform's G33 (friendly limiter `detail`), so the frontend renders the server's detail and never special-cases 429.

**How to apply:** a new OTP screen should use the same pattern: ask for the address when it isn't routed, and render the server's message on failure. See [[otp-error-strings-are-the-codes]].
