---
name: otp-error-strings-are-the-codes
description: The OTP endpoints' error strings ("invalid code", "code expired", "invalid_or_expired_code") ARE the machine codes; contract baseline pins one byte-for-byte, so friendly copy lives in the SPA (otpErrorCopy.ts), never in a new wire field
metadata:
  type: project
---

G8 (fix wave 2026-10-02) was closed WITHOUT adding a `code` field to the legacy `{"error": ...}` body. The three strings are named constants in `auth_service.py` (`CONFIRM_INVALID_CODE`, `CONFIRM_CODE_EXPIRED`, `RESET_INVALID_OR_EXPIRED`), pinned by `test_register_api.py::test_verify_email_error_strings_are_the_stable_codes`, and mapped to copy in `src/features/auth/otpErrorCopy.ts` (used by ConfirmEmail and ForgotPasswordVerify).

**Why:** `docs/contract_baseline.json` step `verify-email-wrong-code` records `{"error":"invalid code"}` byte-for-byte and auth-accounts may not edit that file; `test_intake_claims_api.py` asserts `"code expired"` too. An additive `code` key would need a deliberate re-baseline by backend-platform. Keying the SPA on the exact strings is backwards compatible and ships now.

**How to apply:** never reword those strings as a copy edit. If a real code field is ever wanted, it is a wire change: dispatch backend-platform to re-capture the baseline first, then regenerate openapi/schema. The mapper leaves unknown messages alone on purpose, so a 429 from the 5/min limiter is shown as a rate limit, not a wrong code (ForgotPasswordVerify used to do the latter).
