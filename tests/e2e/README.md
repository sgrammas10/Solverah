# E2E smoke suite (Playwright)

The E2E row of `docs/ARCHITECTURE.md` §6.5: **critical paths only — register →
verify → assessment → matches.**

One spec, `smoke.spec.ts`, one test, five `test.step`s. The fifth step is *sign
in*, which §6.5 does not list; it is there because the app requires it —
`ConfirmEmail` redirects to `/login` on success and issues no session of its own,
and `/work-pulse` is behind `ProtectedRoute`.

## Running it

Node is on fnm and off `PATH` on the Windows dev box. In PowerShell:

```powershell
$env:PATH = "C:\Users\<you>\AppData\Roaming\fnm\node-versions\v22.13.1\installation;" + $env:PATH
```

Then, from the repo root:

```
npm run test:e2e
```

Browsers are not installed by `npm ci`. Once per machine:

```
npx playwright install chromium
```

There is nothing else to start. `playwright.config.ts` owns the web server: it
runs `npm run build && npm run preview` and waits on `http://localhost:4173`.
Override the port with `E2E_PORT`. Because `reuseExistingServer` is on outside
CI, a `npm run preview` you already have open is reused — which also means a
**stale** one is reused, so kill it if you want the build step to run.

Useful variants:

```
npx playwright test --headed        # watch it drive
npx playwright test --debug         # step through
npx playwright show-report          # last HTML report
npx playwright show-trace test-results/<dir>/trace.zip
```

## It serves the production build, not the dev server

`vite preview` serves exactly what `npm run build` produced, so the suite covers
the real chunk graph — including the `lazy(() => import(...))` route splitting
Phase 4b introduced and the bundle budget in `.size-limit.cjs` measures. A broken
dynamic import fails here and in no other test we run. A dev-server run would
resolve modules through Vite's transform pipeline and could pass while the built
artifact was broken.

## What is real and what is stubbed

**The API is stubbed.** Every `/api/v1/**` request is intercepted by
`fixtures/api.ts` and answered from a small state machine. No Flask process, no
database, no email.

Two of the four named steps cannot be driven against a live backend without
reaching into the database or reading a mailbox: registration mails a 6-digit
code that is never returned on the wire, so `verify` has no automatable input;
and `matches` returns rows only after companies have been scored against the
respondent's stored culture profile. Supplying either behind the app's back is a
worse lie than a stub, and a slower one. The stubs also write nothing, so this
suite cannot collide with the backend suite over the shared development database.

Exercised for real:

- the built production bundle, served over HTTP, in Chromium;
- routing, navigation, the post-verify redirect, and the `ProtectedRoute` role
  check on `/work-pulse` and `/company-lens`;
- form behaviour — the register page's password rules and terms gate, the
  6-digit verify guard, the stepper's per-question advance gating across all 24
  questions;
- **the request side of the contract.** Every payload the SPA sends is recorded
  and asserted: the register body (including `terms_accepted` / `terms_version`),
  the verify body, the login body, all 24 assessment responses keyed by the
  opaque tokens the form served, and that both `order=best` and `order=worst`
  are requested.

Not exercised: **any backend code at all.** Response shapes in `fixtures/api.ts`
are transcribed from the types the frontend declares (`SessionResponse`,
`AssessmentForm`, `MatchesPage`), so they can drift from what Flask returns.
`tests/test_frontend_contract.py` is the check that catches that drift — it
asserts every path the SPA calls is one the API actually serves. The two are
complementary; neither replaces the other.

The spec also asserts `api.unhandled` is empty. Any `/api/v1` endpoint the SPA
calls that the stubs do not model fails the run, so new or moved call sites
surface here instead of being silently answered with `{}`.

## Not a CI gate

Deliberately, and it is not an oversight. Browser downloads (~115 MB) and E2E
flake turn a new required check into a broken one, and a gate that is red by
construction gets disabled in its first busy week — taking whatever signal it had
with it. This landed runnable and green locally. Promoting it is a later,
separate change, and should arrive with a decision about caching the browser in
the runner and a retry policy.

## Known issue found while writing this, deliberately not fixed

`LandingNav` hardcodes two `<a href="/register">` CTAs and ignores the
`onRequestEarlyAccess` callback the prelaunch page passes it. "Get Started"
therefore goes to `/register` where `/start` was intended, and both are anchors
rather than `<Link>`, so they force a full page reload. Two callers disagree
about the intent, so it needs a product decision rather than a patch. The smoke
path enters at `/register` directly and does not depend on it either way.
