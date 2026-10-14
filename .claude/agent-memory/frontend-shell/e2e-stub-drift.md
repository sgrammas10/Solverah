---
name: e2e-stub-drift
description: The three e2e specs break silently when feature lanes change the signup/Work Pulse/CompanyLens path; what changed on 2026-10-14 and what to check next time
metadata:
  type: project
---

Playwright is not a CI gate, so feature lanes change pages the e2e specs walk and nobody
notices. On 2026-10-14 (six-trait CompanyLens build) all three were stale:

- `/company-lens` is now one `GET /me/matches?limit=` call with `state`
  core_required / no_companies / ranked; no `order=best|worst`, no percentage. The smoke
  stub serves core_required before the core submission and a ranked list after, and the
  spec asserts both states plus `assertNoProbabilityText` (imported from
  `tests/msw/companyLensHandlers.ts` — works under Playwright).
- Work Pulse now opens a tolerance step ("How much give is there?") after Finish; all
  three specs click "Skip for now" before expecting "That's everything we need".
- The dashboard calls `GET /me/situation-report` (stub serves needs_core /
  needs_environment_report); this one was already unmodelled before the CompanyLens work.
- Situation Report's "What this is, and what it isn't" heading became "About this report"
  (0796599).

**Why:** the smoke's `api.unhandled` check and the real-stack headings are the only places
these drifts show up.
**How to apply:** when reviewing a lane that touches register/verify/login/dashboard/
Work Pulse/CompanyLens/Situation Report copy or calls, run `npx playwright test
tests/e2e/smoke.spec.ts` (stubbed, ~30 s, no backend). See [[e2e-real-stack-recipe]].
