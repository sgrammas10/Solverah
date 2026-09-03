# Security round S1 — auth hardening + rate-limiter integrity — 2026-09-03

Scope: six items from `docs/audits/SECURITY_AUDIT_2026-09.md`, implemented against
`causal_bayesian_model` at `2d54198`. **Not committed.** Ledger row: `A22` in
`docs/ARCHITECTURE.md`.

---

## ⚠ DEPLOY DEPENDENCY — READ FIRST

**The next production deploy of this branch will fail at boot unless `REDIS_URL`
is set in Render first.**

Production has no Redis today (prod-readiness Q1/Q2). Item 2a makes `memory://`
rate-limit storage a `ConfigError` in production instead of a warning, so
`create_app()` raises and gunicorn never binds. This is intended, and the
ordering is the fix rather than an obstacle to it:

1. Provision a Render Key-Value instance.
2. Set `REDIS_URL` on the `solverah-prod` env group.
3. Confirm the running service still boots (it will — the old code ignores the
   variable except to stop warning).
4. *Then* merge S1 to `main`.

The failure is loud and immediate — a `ConfigError` naming `memory://` and the
variable to set — not a silent degradation, and not a first-request 500. Doing
it in the other order costs one failed deploy, not an outage of a running
service, because Render keeps the previous version serving when a deploy fails
to start. It is still the wrong order.

`render.yaml` now carries `REDIS_URL` with this warning inline, and
`.env.example`'s "all three degrade rather than fail" comment — which became
untrue with this change — has been corrected. Note `render.yaml` remains
doc-only until Blueprint adoption, so **step 2 is a dashboard action**, not
something this change performs.

Setting `REDIS_URL` also silences the pre-existing
`CELERY_TASK_ALWAYS_EAGER` warning and switches the app off Scenario A inline
execution — a larger behavioural change than this round, and worth deploying
deliberately rather than as a side effect.

---

## What landed, item by item

### 1. OTPs from `secrets`, not `random` — audit 2.1 (HIGH)

`solverah/domain/auth.py:62` `random.randint(100000, 999999)` →
`secrets.randbelow(900000) + 100000`. Format preserved exactly: six digits,
100000–999999 inclusive, uniform, no zero-padding step.

**Tree sweep result.** `random` appears in ten files; nine are offline research
scripts using it legitimately for retry jitter (`causal_graph/*`) or synthetic
fixtures (`company_culture_LLM/old_files/synth.py`,
`job_descr_LLM/.../mock_data_for_testing.py`, `old_LLM/...`). None mints a
credential. `solverah/domain/auth.py` was the only security-token use, and the
only one under the request-serving package. `intake_service.py:270` already used
`uuid4().hex` (128-bit, fine).

**Regression cover** — `tests/test_otp_entropy.py`, both mechanisms because each
covers the other's blind spot:
- *Behavioural*: substituting `secrets.randbelow` changes the answer; the span
  requested is 900000; poisoning six `random` entry points and minting a code
  raises nothing.
- *Structural (AST)*: no module under `solverah/` may `import random` —
  parametrized per file, with a guard test asserting the walk sees files at all.
  This is what catches a *new* token minted in a *new* module, which the
  behavioural tests never would.

Fails without the fix: 6 of 6 substantive tests, including a named assertion
("generate_verification_code reached the `random` module").

### 2. Rate-limiter integrity — audit 9.1 (HIGH cond.) + 9.2 (MED cond.)

**2a — boot-strict.** `solverah/config.py`: the `memory://`-in-production
warning becomes a `problems.append`. `security.py`: the missing-`redis`-driver
downgrade becomes a `ConfigError` in production, and `memory://` in production
raises there too. The second guard is not redundant — `Settings.from_env` raises
first on the `create_app()` path, but `init_rate_limiter` is independently
callable with an explicit `storage_uri`, and a guard that holds along one call
path has a hole in it.

`ConfigError` messages are redacted (`_redact`): a Redis URI carries its
password in the netloc and these strings reach boot logs.

*Note:* `redis==8.1.0` is already in `requirements.txt`, so 9.2 is a
packaging-regression guard rather than a live blocker.

**2b — runtime-tolerant.** `RATELIMIT_IN_MEMORY_FALLBACK_ENABLED` +
`RATELIMIT_SWALLOW_ERRORS`. Read in that order by flask-limiter 4.1.1:

- The fallback logs `"Rate limit storage unreachable - falling back to in-memory
  storage"` at **WARNING** and re-evaluates *the same configured limits* against
  per-worker memory. So the degraded mode still enforces something — N times
  looser and resettable, not unlimited. It polls the real backend and logs
  `"Rate limit storage recovered"` at INFO when Redis returns, so recovery needs
  no deploy.
- `swallow_errors` is the backstop beneath that: if even the fallback raises, the
  request proceeds. `RateLimitExceeded` is re-raised by the library *before*
  this is consulted, so a real 429 is still a 429 — asserted, not assumed,
  because a limiter that failed open on breach would be worse than none.

The state it degrades into is exactly the state boot refuses to start in. That
asymmetry is the design: entering it by accident is impossible, entering it
because Redis died is survivable and temporary. A rate limiter is a control *on*
the service, not a dependency of it.

**Regression cover** — `tests/test_rate_limiter_integrity.py` (10),
`tests/test_rate_limit_storage.py`, `tests/test_config.py`. The runtime test
breaks the live app's storage mid-flight (every counter op raises
`ConnectionError`) and asserts 200 + a WARNING; without the flags it is a 500.
Fails without the fixes: 5 tests, spanning both halves.

**Latent defect found and fixed in passing.** `init_rate_limiter`'s
`limiter is None` branch passed `request_filter=` as a `Limiter()` constructor
kwarg. flask-limiter has no such parameter — it is a decorator method — so every
call down that path raised `TypeError`. `create_app()` always passes `limiter=`,
so the branch was dead and the defect survived since `bb67227`. My tests were
the first to exercise it. Now constructs then registers the filter, matching what
the other branch already did.

### 3. User enumeration on forgot / resend — audit 2.3 (MED, probed)

| Endpoint | Before | After |
|---|---|---|
| `POST /auth/password/forgot` | `200` / `404 "No account found with that email address."` | `200 reset_sent` for all |
| `POST /auth/email/verify/resend` | `200` / `400 "Email already confirmed"` / `404 "Account not found"` | `200 confirmation_sent` for all three |

The malformed-email `400` on resend stays and is not a leak: it depends on the
string, never on who owns it, so it answers the same for both populations —
asserted rather than assumed.

Uniform *responses*, not uniform *work*: an unknown address writes no row,
queues no outbox entry, and sends no mail — otherwise this would be a uniform
spam relay. Tested.

**Frontend coherence — checked, and no change was needed.**
- `ForgotPassword.tsx:23` navigates to `/forgot-password/verify` on 200 and
  shows the server's wording on an error. An unknown address now reaches the
  code-entry screen and the code never arrives — the standard shape of this
  flow. `verify_password_reset` already answered a single
  `invalid_or_expired_code` for every failure mode, so the code someone types
  next cannot re-open the question.
- `ConfirmEmail.tsx` / `ForgotPasswordVerify.tsx` resend buttons show "New code
  sent! Check your inbox." on 200. Coherent.
- Nothing in `src/` reads `"Account not found"`, `"No account found"`, or
  `"Email already confirmed"` — verified by grep.

One frontend test did have to change: `ForgotPassword.test.tsx` mocked a **404**
to exercise the generic error-display branch, and `mock().reply()` is typed off
the generated schema, so that became a *type* error once the 404 left
`docs/openapi.json`. It now uses `.resolve()` with a **429** — a status that
endpoint genuinely returns (`3 per minute`) — via the same escape hatch the
neighbouring off-contract test uses. A second test was added asserting the
user-visible half: an unknown address advances to the code screen like a known
one.

**Regression cover** — `tests/test_user_enumeration.py` (8). Comparison is on
`(status, body bytes, headers)`, not parsed JSON: key order and whitespace are
observable on the wire and invisible to `==` on dicts, and `Content-Length`
tracks the body closely enough to be its own oracle. Two headers are excluded
and both are enumerated by name rather than pattern-matched, so a *new* varying
header fails the file loudly — `date` (clock) and `x-request-id` (unique by
construction). That exclusion list is the only thing between the two
fingerprints; everything else, CSP and `Set-Cookie` included, is compared.

Fails without the fix: 2 tests (the two byte-identity assertions).
`test_forgot_password_hides_the_unconfirmed_case_too` passes both before and
after — the old code answered 404 for unconfirmed *and* unknown alike, so it
pins a property rather than catching this regression. Stated plainly rather than
counted as cover.

**Timing is deliberately not asserted here**, and there is a residual: the
unknown-address path still does strictly less *work* (no row write, no outbox
row). It is a much weaker signal than a status code and no wall-clock assertion
could hold it down without flaking. Recorded, not closed.

### 4. Login timing oracle — audit 2.3 (MED, probed)

`auth_service.login` short-circuited on `if not user or not check_password(...)`,
so an unknown address answered 401 without bcrypt ever running while a known
address answered the same 401 tens of milliseconds later. Now the `user is None`
branch verifies `domain.TIMING_EQUALISER_HASH` — a real `$2b$12$` digest whose
32-byte plaintext came from `secrets.token_bytes` and was never recorded — then
falls through to the identical 401.

Hashing a *dummy* rather than the submitted password is what makes the cost
constant: bcrypt's work factor is carried by the digest, not the candidate, so
an attacker cannot vary the cost by varying what they send. The result is
discarded; branching on it would put the branch back.

**Regression cover** — `tests/test_login_timing_equalisation.py` (6). Asserts
the **code path**, not the clock: `check_password` is replaced with a recorder
and calls are counted. Also pinned — the digest used is the dummy and never a
real user's hash; real bcrypt cannot match it for any candidate; and its cost
prefix equals that of a freshly minted hash, so overriding `BCRYPT_LOG_ROUNDS`
fails the test instead of silently reopening the gap.

Fails without the fix: 3 tests.

### 5. Anonymous `wpll` enqueue limits — audit 3.1 (MED, probed)

Per-IP tightened and a global ceiling added, mirroring
`POST /intake/quiz-preview/insights`:

```
WPLL_ANON_PER_IP_LIMIT = "5 per minute;20 per hour;50 per day"   # was 200/day;50/hour
WPLL_ANON_GLOBAL_LIMIT = "500 per day"                            # keyed on global_rate_limit_key
```

Three scoping calls, each a place the next person could reasonably do the
opposite:

- **The per-IP limit replaces the bare defaults; it does not stack on them.** Two
  per-IP buckets on one door is the conflicting-bucket shape you warned about —
  the effective limit is whichever is tighter and neither string says which. The
  day term is kept explicitly because `shared_limit` defaults to
  `override_defaults=True`.
- **Its own global scope** (`assessments:submit:wpll:global`), not the existing
  `intake:quiz-preview-insights:global`. One shared bucket would mean abuse of
  either endpoint silently closes the other — two funnel entrances failing
  together for a reason neither log would explain.
- **The ceiling is on the enqueue only, never on `POST
  /assessments/wpll/submissions`.** That route answers `410 Gone` for `wpll`
  before auth and before the body is read, so it spends nothing. Counting free
  refusals into a bucket shared by every caller would hand anyone 500 zero-cost
  hits to close the teaser for real visitors. The per-IP bucket still counts
  them, and should — it bounds only the caller doing it. Same distinction
  `POLL_LIMIT` already makes.

`exempt_when=_is_authenticated_kind` keys off `AssessmentKind.requires_auth`
rather than a literal `kind == "wpll"`, so a second anonymous instrument
inherits the control instead of arriving without one. An unknown `{kind}` is
exempt too — it is about to 404 and reaches no provider, so it must not be able
to spend the shared budget.

**Regression cover** — `tests/test_anonymous_enqueue_limits.py` (13). Read off
`limiter.limit_manager` rather than off decorator arguments, because a limit
declared but never attached is precisely the defect this codebase was bitten by
once (every `@limiter.limit` above its `@app.route` in the pre-Phase-1 `app.py`).
Counts *buckets* — `(key_func, resolved scope)` — not limits, since a three-term
limit string expands to three `RuntimeLimit`s that all count into one bucket.

Fails without the fix: 3 tests. The remaining ten pin policy and scoping, which
the constants carry.

### 6. Production CORS — audit 7.1 (MED, probed)

`_cors_origins(is_production)` in `solverah/factory.py`. Production returns
exactly the four real origins (`solverah.com`, `www.solverah.com`,
`api.solverah.com`, `solverah.vercel.app`); the two localhost patterns are
dev/test only. The sub-finding is closed too: both patterns are anchored with
`\Z` (not `$`, which also matches before a trailing newline), so
`http://localhost:3000.evil.com` no longer matches under flask-cors' `re.match`.

`solverah.vercel.app` is kept — it is the real Vercel production alias behind the
custom domain, not a preview. Preview deploys stay CORS-blocked, which is the
status quo (Q10) rather than a change here; wiring them up is the `CORS_ORIGINS`
decision recorded in the prod-readiness doc and not this round's to make.

**Regression cover** — `tests/test_cors_allowlist.py` (15). Matching goes through
flask-cors' **own** `probably_regex` + `try_match_pattern`, not a
re-implementation — it classifies each entry itself (metacharacter sniff, then
`==` or `re.match`), so a test that assumed one or the other would be checking a
matcher the library does not use, and would miss a metacharacter silently
reclassifying a literal into a pattern. The four production entries are asserted
to *be* literals, which is what makes `https://solverah.com.evil.net` unmatchable
with no anchor to remember. One live test pins that `_cors_origins`' answer is
what actually reaches flask-cors.

Fails without the fix: 7 tests.

---

## Contract discipline

`Scripts/capture_contract.py` run against `docs/contract_baseline.json`:
**all 55 steps byte-identical, zero diff. No re-baseline in this round.**

**That zero is not evidence that nothing changed on the wire, and this is the
most important caveat in this report.** Item 3 *did* change response bytes on two
endpoints. The fixture is blind to them:

- its scenario never calls `/auth/password/forgot` or
  `/auth/email/verify/resend` (steps 0–54 cover register, login, verify, the five
  instruments, `/me`, export, companies, logout);
- it sends no `Origin` header and records only `status`, `mimetype`,
  `cookies_set`, `body` — so item 6 is outside its field of view by construction.

So the honest statement is "the flows the baseline watches are unchanged", not
"the API is unchanged". A22 records this explicitly, because the reasonable
inference from "zero diff" is the wrong one here.

**Recommendation (not done — outside this round's scope):** extend the capture
scenario to cover `forgot` and `resend` for a known *and* an unknown address.
Those two are now load-bearing security behaviour whose whole value is that the
bytes are identical, and the fixture is the only mechanism that would notice them
drifting apart. That extension *is* a deliberate re-baseline and wants its own
A-row.

`docs/openapi.json` regenerated (two `404` branches removed, two descriptions
rewritten) and `src/shared/api/schema.ts` regenerated from it.

---

## Verification

| Gate | Result |
|---|---|
| Backend baseline, before changes (`42ac0c5`) | **1354 passed, 3 skipped, 0 failed** |
| Backend, my changes only, isolated worktree at `2d54198` | **1493 passed, 3 skipped, 0 failed** |
| Frontend `npm test -- --run` | **672 passed, 65 files** |
| Frontend `npm run type-check` (`tsc -b`) | clean |
| `Scripts/capture_contract.py` vs baseline | 55/55 identical |

CI parity: `SOLVERAH_IGNORE_DOTENV=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, venv
at `Desktop/solverah-venv311`, and exactly the five variables
`.github/workflows/tests.yml` sets. The 3 skips are the `pg_dump`-gated backup
tests and are unchanged from baseline.

**Pre-existing failures: none.** The baseline was clean, so every failure during
this round was mine. Two are worth naming:

1. `tests/test_backups_cli.py::test_the_rehearsal_store_is_refused_in_production`
   built a production `Settings` with no `REDIS_URL`, which item 2a now rejects
   before the test reaches its assertion. Fixed by adding `REDIS_URL` to that
   fixture env — the test is about the rehearsal store, not about Redis. The same
   correction was applied to `test_config.py`'s `PROD_ENV`, with a comment saying
   why, since a production environment without a shared store is simply no longer
   a valid one.
2. `test_config_and_limiter_agree_on_the_backend[env_extra3]` and
   `test_memory_backend_in_production_warns_in_both_layers` in
   `tests/test_rate_limit_storage.py` asserted the old warn behaviour. Both were
   restructured rather than deleted: the agreement-between-layers property is now
   asserted against `resolve_storage_uri` directly (where it still holds), and
   the production verdict became `test_memory_backend_in_production_is_fatal`.

**One pre-existing defect swept up, flagged rather than hidden:**
`src/shared/api/schema.ts` was already stale against `docs/openapi.json` at
`2d54198` — the committed schema says `src/utils/apiError.ts` where the committed
openapi.json says `src/shared/api/apiError.ts`. So `npm run generate:api:check`
was already red before this round; a Python docstring was edited without
regenerating. My regeneration fixes it, which means one hunk of the `schema.ts`
diff is not mine.

**A note on the working tree.** Another lane was actively editing this tree
during the round (`solverah/services/resume_service.py`,
`solverah/repositories/account_repository.py`, `tests/test_account_lifecycle.py`,
`solverah/infra/resume_extract/`, `tests/test_resume_parse_hardening.py` — the
GDPR/upload findings, presumably), and `2d54198` landed mid-session. Because a
shared-tree run cannot attribute a failure, the headline backend number above
comes from a **git worktree containing only my 21 files**, on its own database
lane (`solverah_sec2`). A shared-tree run was also done and showed the same
single failure and nothing else. **None of the other lane's files are in my
change set.**

---

## Not implemented, deliberately

### Register-flow enumeration — a product decision, per your instruction

`POST /auth/register` still answers `400 "User already exists"`. `Register.tsx:11`
matches that message and renders "An account with that email already exists", and
`Register.test.tsx:142` asserts it. Changing the API breaks a UX contract the
frontend genuinely depends on. Three options:

**A. Leave it (recommended for now).** Signup enumeration is the least valuable
of the four oracles, because the address is one the user is already volunteering,
and the flow's whole job is to tell them "you already have an account, sign in
instead". Every mainstream product does this. It costs nothing to defer, and
items 3 and 4 already closed the two oracles an attacker can point at an
*arbitrary* address.
- *Residual:* a mailing list POSTed at `/auth/register` still sorts into
  registered/unknown, bounded by `5 per minute` per IP — which, after item 2a,
  is finally a real bound.

**B. Uniform 201, disambiguate by email.** Register always answers 201; if the
address already exists, send a "someone tried to sign up with your address —
sign in instead" email rather than creating anything. Closes the oracle
completely. Costs a new email template, a new outbox topic, and a real UX
regression: a user who forgot they had an account now waits on an inbox instead
of being told on screen. This is the option that trades product quality for the
finding.

**C. Keep the 400 but make it cost more.** Leave the message; add a per-IP
sliding limit on *distinct addresses tried* rather than on requests, so a single
caller can probe a handful of addresses but not a list. Keeps the UX exactly,
turns a free oracle into an expensive one, does not close it. Needs new state
(a per-IP set with a TTL) — cheap on Redis, which after item 2a is guaranteed
present in production.

My read: **A now, C if signup abuse ever shows up in logs.** B trades a real
user-facing regression for a marginal security gain and I would not ship it
without a product decision. Nothing implemented either way.

### Other residuals recorded, not closed

- **Locked accounts still answer `423`**, which discloses existence for the
  narrow population of locked accounts. That is audit 1.2's territory
  (per-account lockout, victim-lockout DoS) and changing it needs the lockout
  redesign, not a response tweak.
- **The intake claim sign-in** (`intake_service.py:339`) has its own
  `404 "Account not found"` and the same bcrypt short-circuit. It is a much
  narrower oracle — the caller must already hold a valid `submission_id` whose
  email matches — and the audit did not count it among the four. Worth a look in
  a later round; not touched here, to keep this round's diff to what was scoped.
- **Item 3's work asymmetry** (no row write / no outbox row for an unknown
  address), as described above.
- Audit 2.2 (no per-account OTP attempt cap), 9.3 (`override_defaults` dropped
  the daily backstop on other routes), 9.4, and 9.5 are all rate-limit findings
  adjacent to this round and all still open. 9.3 in particular is now the largest
  remaining limiter gap: login and register are `5/min` with no day term, i.e.
  7,200/day/IP.

---

## Files changed

**Application** — `security.py`, `solverah/config.py`, `solverah/factory.py`,
`solverah/domain/auth.py`, `solverah/services/auth_service.py`,
`solverah/api/v1/auth.py`, `solverah/api/v1/assessments.py`

**Generated / deploy / docs** — `docs/openapi.json`, `src/shared/api/schema.ts`,
`render.yaml`, `.env.example`, `docs/ARCHITECTURE.md` (A22)

**Tests, new** — `tests/test_otp_entropy.py`, `tests/test_user_enumeration.py`,
`tests/test_login_timing_equalisation.py`,
`tests/test_rate_limiter_integrity.py`, `tests/test_cors_allowlist.py`,
`tests/test_anonymous_enqueue_limits.py`

**Tests, updated** — `tests/test_config.py`, `tests/test_rate_limit_storage.py`,
`tests/test_rate_limits.py`, `tests/test_password_reset.py`,
`tests/test_backups_cli.py`, `src/features/auth/components/ForgotPassword.test.tsx`
