---
name: send-with-refresh-core
description: fetchWithAuth and streamFetch share one sendWithRefresh core in AuthContext.tsx (single-flight refresh, one replay, fresh CSRF on replay); the refresh tests are the spec for both; audit of raw fetch sites and the unused createApiClient
metadata:
  type: project
---

Since the 2026-10-02 fix wave, `AuthContext.tsx` has a private `sendWithRefresh(endpoint, options)` that owns credentials, CSRF header (read from the ref inside `send`, so a replayed POST carries the rotated token), the single-flight `refreshSession()` and exactly one replay; a failed refresh calls `clearSessionLocally()` and returns the original 401. `fetchWithAuth` parses JSON and throws on top of it; `streamFetch` returns the raw response (its caller, AgentChat, handles non-ok). `AuthContext.refresh.test.tsx` has a parallel `describe` for each, plus a cross-helper single-flight test.

**Why:** `streamFetch` had no refresh at all, so the agent chat's first message after the 15-minute access token aged out failed every time. Duplicating the logic is how they drifted in the first place.

**How to apply:** any new "talk to the API with the session" helper builds on `sendWithRefresh`, never on a bare `fetch`. Audit result (2026-10-02): the only raw `credentials: "include"` fetches outside AuthContext are sign-in/pre-session paths (ConfirmEmail verify, ForgotPasswordVerify reset, `useIntakeForm` claims) which correctly need no refresh; `src/shared/api/client.ts` `createApiClient` attaches CSRF but has no 401-refresh middleware and currently has zero importers, so it must gain one before any call site migrates onto it (frontend-shell owns it). Guest quiz-preview fetches send no credentials.
