---
name: g33-limiter-429-detail
description: Limiter 429s carry RATE_LIMITED_DETAIL (errors.py), which must stay identical to apiError.ts's 429 fallback; contract baseline has no 429 step
metadata:
  type: project
---

G33 (2026-11-23, uncommitted at time of writing): `_handle_http_exception` now answers every
HTTPException 429 (in practice only Flask-Limiter's RateLimitExceeded) with
`RATE_LIMITED_DETAIL` instead of `exc.description`, which was the limit string
("3 per 1 minute") and reached users verbatim. `RateLimitError` raised by a feature
(CompanyLens daily allowance) goes through the ApiError handler and keeps its own copy.

**Why:** the frontend shows `detail` ahead of its own status fallback, so the backend
string won. The sentence is copied from `src/shared/api/apiError.ts` STATUS_FALLBACKS[429]
so front and back agree; Julie owns the copy and may revise it.

**How to apply:** if Julie changes either string, change both (frontend-shell owns
apiError.ts). `docs/contract_baseline.json` records no 429 step at all (A23 sized the
scenario to stay under the limits), so this change is invisible to the contract and
needs no re-baseline. Guards: `test_rate_limits.py::test_a_refusal_speaks_to_a_person_not_in_limit_syntax`,
`test_errors_and_health.py` two 429 tests.
