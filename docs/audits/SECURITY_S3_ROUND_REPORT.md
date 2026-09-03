# Security round S3 — database-backed refresh tokens — 2026-09-03

Scope: `docs/audits/SECURITY_AUDIT_2026-09.md` finding **1.1 (HIGH)** — "logout
revokes nothing; a stolen cookie survives it (A7 never built)" — implemented
against `causal_bayesian_model` at `615f860`. **Not committed.** Ledger row:
`A24` in `docs/ARCHITECTURE.md`.

S1 (`baa5b83`) and S2 (`7867421`) are committed and are not revisited here.

---

## No deploy dependency, and nobody is signed out

Unlike S1, this round adds nothing to the pre-deploy checklist. It needs no new
environment variable, no new service, and no ordering against the S1 Redis work.
The migration is additive — one new table, no existing column changed — and the
downgrade is a drop.

**What a user who is mid-session at deploy time experiences: nothing.** In
detail, because "nothing" is a claim that has to be earned:

- Their access cookie is a signed JWT whose `exp` was fixed when it was minted.
  Lowering `JWT_ACCESS_TOKEN_EXPIRES` from 60 to 15 minutes changes what the app
  *issues*; it cannot reach back into a token already in a browser. So a user
  holding a 1-hour token keeps it for the rest of that hour.
- Every authenticated route keeps working for them. Nothing consults
  `user_sessions` on the request path — that is the point of A7's "one lookup per
  refresh, not per request" — so a session with no row behind it is not a
  session the API can tell apart from any other.
- `POST /auth/logout` works for them and answers `200`. Their token carries no
  `sid` claim (it predates the claim), the handler finds no family, and it
  clears cookies exactly as it did yesterday. There is nothing to revoke,
  because they have no refresh token to revoke. Asserted:
  `test_a_pre_deploy_access_cookie_still_authenticates`.
- When that token does expire — at most an hour after the deploy, and at the
  moment it would have expired anyway — the SPA gets its first 401. It attempts
  a refresh, has no refresh cookie, gets `401`, drops local session state and
  shows the login screen. That is precisely what would have happened before this
  round, at precisely the same moment.
- They log in once. From that login they hold the full pair, and they will not
  see a login screen again for thirty days of inactivity.

**The one behavioural change a returning user will notice is the opposite of a
sign-out.** Before this round the access cookie was a *session cookie*: closing
the browser ended the session. The refresh cookie is persistent (30 days,
`Max-Age` set explicitly), so reopening the browser now restores the session.
That is inherent in a 30-day refresh token and is called out here because it is
a product-visible change that no line of the brief spells out.

---

## What landed

### 1. `user_sessions` — the row that makes a session revocable

`migrations/versions/20260903_user_sessions.py`, revision id
`20260903_user_sessions` (22 characters, inside the VARCHAR(32) the chain guard
enforces). `down_revision = 20260901_scoring_jobs`.

| Column | Why |
|---|---|
| `family_id` UUID, `DEFAULT uuidv7()` | One sign-in is one family, however many times it rotates. Reuse detection revokes on this. |
| `user_id` BIGINT FK → `users` ON DELETE CASCADE | |
| `token_hash` TEXT, UNIQUE | Hex SHA-256 of the opaque token. The lookup key. |
| `parent_id` / `successor_id` BIGINT FK → self, ON DELETE SET NULL | The rotation chain, read in both directions. **SET NULL, not CASCADE** — a cascade would make the retention pass, which deletes oldest-first, take live sessions out with their expired ancestors. |
| `issued_at` / `expires_at` / `retired_at` TIMESTAMPTZ | |
| `retired_reason` TEXT | `rotated` / `logged_out` / `reused` / `expired`, fixed by a check constraint. |

Two check constraints. `ck_user_sessions_retirement_complete` refuses a
retirement time without a reason or a reason without a time — a death with no
cause is an audit row that cannot answer the question it exists for.
`ck_user_sessions_retired_reason` fixes the vocabulary, because a typo'd reason
is a row that answers nothing and a query that silently misses it.

Two partial indexes rather than one over a shared column: the retention pass
reads two disjoint halves (live rows by `expires_at`, dead rows by `retired_at`)
and in steady state the dead half is almost all of the table.

**Three columns Part 4.2 draws and this does not build**, recorded in
`docs/ARCHITECTURE.md`'s as-built note rather than left as silent drift:
`user_agent` and `ip` are per-request identifying data whose only reader would
be a device-list screen that does not exist — and the same audit raised #18 and
#7 against exactly that shape, identifying data retained past any reader.
`public_id` has no reader at all: the client's handle on a session is the token,
which is a secret, and the family id travels only inside a signed JWT claim.

### 2. The token: opaque, 256-bit, SHA-256 at rest

`solverah/domain/auth.py` gains `generate_refresh_token()` (`secrets.token_urlsafe(32)`)
and `hash_refresh_token()`.

**Opaque, not a JWT** — the design decision this whole finding rests on. A JWT
refresh token is self-validating: the server accepts it without consulting any
state, so there is no state for a logout to change. That is finding 1.1 stated
as a property.

**SHA-256, not bcrypt**, and the difference from passwords is the reason.
Bcrypt's cost parameter exists to make a *dictionary* attack expensive, and a
dictionary attack needs a candidate list — which a human password has and 256
bits of CSPRNG output does not. What a salted per-row digest *would* cost is the
lookup: the presented token has to find its row, and with bcrypt that is a scan
of every session in the table rather than one indexed equality. Deterministic
and unsalted for the same reason: the digest *is* the index key, and a lookup
key may not encode the same input two ways.

### 3. Rotation, reuse detection, and the grace window

`solverah/services/refresh_tokens.py`. Five outcomes, and the order they are
decided in is load-bearing:

| Outcome | When | Answer |
|---|---|---|
| `unknown` | no row hashes to the presented value | 401, revoke nothing |
| `grace` | retired **by rotation** within 30 s | 200, new access token, **no** `Set-Cookie` |
| `reused` | retired any other way, or rotated longer ago | 401, **revoke the family**, audit row |
| `expired` | past `expires_at` | 401, stamp `expired`, family untouched |
| `rotated` | live | 200, new access token **and** new refresh cookie |

**Expiry is not theft, and neither is an unknown token.** Both are refused
without revoking anything. The cheap wrong implementation treats every refusal
as reuse and signs people out of sessions nobody attacked; both negatives are
asserted (`test_an_expired_token_is_refused_without_revoking_the_family`,
`test_an_unknown_token_is_refused_and_revokes_nothing`).

**Reuse revokes the family, not the row.** Once both copies of a token have been
seen they are indistinguishable, so killing one has even odds of killing the
victim's. Ancestors keep the reason they actually died of (`rotated`); the live
descendant is stamped `reused`, which is what makes the family readable
afterwards as "this chain was rotated normally and then something replayed an
old link".

**The security event** is one `AuditLog` row (`refresh_token_reuse`) plus a
WARNING log line. One row and not one per rotation: rotation happens every
fifteen minutes per signed-in user and would drown the table, while this is rare
by construction. Metadata carries ids only — never the address, per audit #18.

### 4. The concurrency trap, both halves

**Server: a 30-second grace window.** A token retired *by rotation* within
`GRACE_SECONDS` is not treated as reuse. The caller gets a fresh access token
and **no refresh cookie**, and that answer is complete rather than partial
because cookies are per-browser and not per-tab: the successor the first request
minted is already in the shared jar by the time anyone reads the second
response.

Two things that look like refinements and are not:

- **The window is a clock, not a shape.** "The presented token is the direct
  parent of a live token" has no clock in it, so a genuinely stolen token
  replayed a week later would also find a live successor and be waved through.
- **A grace hit must not re-mint.** Re-minting was considered and is actively
  dangerous: it leaves the jar holding whichever response landed last, and if
  that is the *earlier* successor then fifteen minutes later it is outside the
  window and revokes the family it was supposed to save. Asserted:
  `test_the_grace_window_does_not_extend_the_family`.
- **The claim is a conditional `UPDATE`**, not a read-then-write:
  `WHERE id = ? AND retired_at IS NULL`. Two simultaneous requests both pass the
  retirement check — neither row is retired yet — and without the condition both
  would mint a successor, leaving two live tokens in one family. The loser sees
  zero rows updated, re-reads, and lands on the grace path, which is where it
  belongs.

**Client: single-flight.** `refreshSession()` in
`src/features/auth/AuthContext.tsx` holds the in-flight promise in a ref, so N
simultaneous 401s produce one `POST /auth/refresh`. The ref is cleared when the
promise *settles*, not when it succeeds, so a failed refresh does not wedge
every later attempt behind a promise that already resolved false.

Tested both ways, and they fail differently:

- `test_replaying_a_just_rotated_token_inside_the_grace_window_succeeds` — the
  serialised shape, which proves the window.
- `test_two_simultaneous_refreshes_of_one_token_do_not_revoke_the_family` — two
  real requests on two threads released by a `threading.Barrier`, contending on
  one Postgres row. This proves the *claim*: a read-then-write rotation passes
  the sequential test and fails here by minting two successors.
- `AuthContext.refresh.test.tsx` — seven tests over MSW counting requests on the
  network rather than calls to a `fetch` spy: one refresh for two concurrent
  401s, the replay carries the *new* CSRF token, and a second 401 after a
  successful refresh surfaces as an error instead of starting a loop.

### 5. Logout revokes — the finding itself

`POST /auth/logout` reads the `sid` claim off the access token and revokes that
family with reason `logged_out`.

**Why the `sid` claim and not the refresh cookie:** the refresh cookie is
path-scoped to `/api/v1/auth/refresh`, so the browser does not send it to
`/auth/logout`. In practice the access token is always fresh at that point,
because `fetchWithAuth` refreshes before retrying any 401 — so by the time a
logout is sent it carries a token minted seconds ago.

**The JWT is verified best-effort and every swallowed failure is the right
answer**, which is worth naming one by one because "try/except: pass" usually is
not:

- *No token, or an expired one* — nothing to revoke, and the cookies still need
  clearing. Logout has always answered 200 here.
- *A token with no `sid`* — issued before this round; no family exists. This is
  what keeps mid-session users from meeting an error on their first logout.
- *A missing or wrong CSRF header* — the interesting one. A cross-site page can
  still force a logout (audit #25, LOW, unchanged), but it cannot satisfy the
  CSRF check, so it lands here and clears cookies without revoking anything.
  **Forged logout stays the nuisance it was rather than becoming a way to end
  somebody's session for real** — which matters more now than it did before,
  precisely because logout now does something. Asserted:
  `test_a_forged_cross_site_logout_cannot_revoke_anything`.

**The residue, stated plainly.** An access token already minted is a signed JWT
and stays valid until its `exp`. Fifteen minutes, down from sixty. Closing that
last window needs a denylist consulted on every authenticated request, and A7
deliberately chose one lookup per *refresh* over one per request. What was an
hour of full access after logout is now a quarter of an hour, and nothing
survives past it.

### 6. Every path that opens a session opens both halves

`auth._respond` and `intake._respond` both funnel through a single
`auth.start_session()`. `POST /intake/claims` in `signin` mode is a third
sign-in path and it was minting its own access token; left alone it would have
handed users a session that dies in fifteen minutes with nothing to renew it,
and nothing would have failed until the sixteenth minute.
`test_every_session_issuing_response_sets_the_refresh_cookie` asserts the funnel
rather than the call sites, so a fourth path minting its own token fails.

### 7. Rate limits

`security.REFRESH_PER_IP_LIMIT = "30 per minute;300 per hour"`, applied as
`@limiter.shared_limit(..., scope="auth:refresh")` — S1's idiom, below the route
decorator, one bucket.

**What the limit is not for:** brute force. The token is 256 bits, so guessing
is not a strategy at any rate a limiter could permit and a stolen token needs
exactly one call. What it bounds is *work* — two row writes per accepted refresh
on the auth path.

**No day term, deliberately**, and this is the one place the shape differs from
`WPLL_ANON_PER_IP_LIMIT`. That endpoint spends money per call and a daily
ceiling is the budget; this one spends two INSERTs, and four refreshes per
browser per hour times an office is a legitimately large daily number. A day
term sized to survive an office bounds nothing the minute term did not; one
sized to look tight signs the office out every afternoon. `override_defaults`
(true by default on `shared_limit`) drops `DEFAULT_LIMITS`' `200 per day`, and
that is the intent here rather than the accident audit #15 describes.
`test_the_refresh_endpoint_carries_exactly_one_explicit_per_ip_bucket` asserts
one bucket, not two — the "do not stack conflicting per-IP buckets"
instruction as an assertion — and `test_the_refresh_limit_fires` proves the
decorator actually wraps what Flask calls.

### 8. CSRF on the refresh POST — **the one place I depart from the brief**

The brief says "CSRF still applies to the refresh POST". It does. The
*mechanism* is not the double-submit token every other state-changing route
uses, and that is a deliberate departure I am flagging rather than taking
silently.

**Why double-submit cannot work here.** The scheme works because the client
holds the CSRF token in memory, handed to it in the body of the response that
signed it in. `POST /auth/refresh` is reached at exactly the moment the client
holds nothing: a returning visitor's first request after fifteen minutes away is
a page load, the session probe 401s, and this tab has never been signed in. The
`csrf_refresh_token` cookie flask-jwt-extended writes for precisely this purpose
is unreadable from `solverah.com`, because the API is on `api.solverah.com` and
cookies are per-host — which is the same reason the token is echoed in the login
*body* in the first place. Requiring a double-submit token on refresh would sign
out every visitor who closed the tab: this round's feature, inverted.

**What is enforced instead**, and it is a CSRF control rather than a substitute
for one:

1. `Origin` (falling back to `Referer`) must be an origin this deployment
   serves. A browser sets these itself and a page cannot forge them, so a form
   or `fetch` on `evil.com` announces `evil.com` and is refused with `403`. This
   is the standard defence for a cookie-authenticated endpoint that cannot carry
   a token, and against an attacker who can *write* a cookie it is stronger than
   double-submit — such an attacker satisfies double-submit by writing both
   halves.
2. `Content-Type: application/json`, else `415`. A cross-site HTML form can send
   three content types and none of them is this one, which closes the case of a
   browser that sends no `Origin` at all.

The allowlist is the one S1 built, read from `app.extensions["solverah_cors_rules"]`,
so the guard and the CORS configuration cannot come to different conclusions.
`_cors_origin_rules` splits exact origins from regex patterns for this check:
reading `https://solverah.com` as a regex also matches `https://solverahXcom`, a
domain somebody else can register. `test_a_look_alike_origin_is_refused` pins
that.

Neither check is load-bearing alone; together they leave nothing a cross-site
page can send. If you would rather have the double-submit token, the price is
that a returning visitor must log in again, and it is worth deciding
deliberately rather than by mechanism-matching.

### 9. Retention

`flask retention run` gains `--session-days` (default 30, Part 4.8's "30 days
past expiry") and two steps:

1. `refresh_tokens.expire_stale()` stamps `expired` on rows past `expires_at`
   that nobody ever came back for — most of them, since a token is only examined
   when presented.
2. `refresh_tokens.purge_terminal()` deletes on a two-condition OR:
   `retired_at < cutoff` **OR** (`retired_at IS NULL AND expires_at < cutoff`).

**A real bug the double-condition discipline caught.** `expire_stale` first
stamped `retired_at = now()`. That restarts the retention clock on every row it
touches: a token that expired thirteen months ago would survive another thirty
days from the day it was first swept, and a fleet of them would survive thirty
days from whenever the sweep was first deployed. Retention that resets itself
when you look at it is not retention. It now stamps `retired_at = expires_at` —
the row died when the token stopped being usable, not when a cron job noticed —
so a row whose window has already passed is stamped and deleted in the same
pass. The failing assertion was `payload["sessions_deleted"] == 2` returning 1.

The second half of the OR is unreachable inside a normal pass, because
`expire_stale` runs first. It is the belt for the pass that never ran — a cron
outage, a skipped day — and without it those rows would be unreachable by every
*later* run too, since each one also stamps before deleting.
`test_purge_terminal_reaches_a_row_that_was_never_stamped` exercises it alone.

The seeded matrix in `tests/test_ops_cli.py` has four session rows: one dead on
each half of the OR, one retired inside the window, and one **live** — the only
row here whose deletion would be visible to a user.
`test_retention_run_leaves_a_live_session_alone_at_any_window` runs with
`--session-days 0` so the window cannot be what protects it.

### 10. Account deletion destroys sessions

`account_repository.delete_personal_rows` now deletes the user's
`user_sessions`. Deletion *tombstones* the user row rather than removing it, so
`ON DELETE CASCADE` never fires — the same reason the assessment submissions are
deleted explicitly one line above. Without this, a refresh token issued before
deletion would keep minting access tokens for a tombstoned account
indefinitely: the tombstone frees the address and kills the password, and this
would have been the one way back in that neither of those closed.

Deleted rather than retired, which is the opposite of what happens to these rows
everywhere else: a retired row is kept because it is the audit trail of a
session that ended, and there is no account left for that trail to be about.

### 11. Frontend

`src/features/auth/AuthContext.tsx` is the only file that changed.

- **`fetchWithAuth`**: a 401 refreshes once and replays the request once. If the
  refresh fails, local session state is dropped (`queryClient.clear()`, same
  hygiene as logout) and the original error surfaces. One retry,
  unconditionally — a retry that re-entered the refresh path would turn one
  expired family into an unbounded storm from every open tab.
- **The boot probe** does the same, which is what stops a fifteen-minute access
  token becoming a fifteen-minute session for anyone who closes a tab.
- **The CSRF token moved from state to a ref.** Nothing ever rendered off it,
  and state is now actively wrong: the replay happens in the same tick as the
  refresh, and a `setState` is not visible to the closure that has to attach the
  new header. Dropping the state also removes a re-render nothing was waiting
  for.
- **`localStorage["solverah.hasSession"]`**, and the reason it exists is a
  regression the existing tests caught. Without it, every anonymous landing-page
  load spends a second request on a guaranteed 401 — against a rate-limited
  endpoint, which behind one NAT gateway is how real users start seeing 429s on
  refreshes that matter. It is not a credential and cannot be one: the refresh
  cookie is HttpOnly and cross-origin, so forging the hint costs the forger one
  extra 401 and losing it costs a returning user one sign-in. Reads and writes
  are wrapped in try/catch — Safari in private mode throws on access rather than
  returning null.
- `logout()` still does `queryClient.clear()`; the `authEvents` inversion and
  `ProfileCacheSync` wiring are untouched; no cross-slice deep import was added
  (`npm run lint` is unchanged at 157 warnings, 0 errors, exactly the baseline).

---

## The contract

`docs/contract_baseline.json`: **60 steps → 71**, deliberately, and `A24` is the
ledger entry.

**Of the 60 steps standing at A23, exactly one moved**, and that was verified
*before* the recapture by running the unextended scenario against the standing
baseline:

```
contract diff: 1 difference(s)

login POST /api/v1/auth/login -- cookies_set:
  baseline ['access_token_cookie', 'csrf_access_token'],
  this run ['access_token_cookie', 'csrf_access_token', 'refresh_token_cookie']
```

`logout` did **not** move, which is worth stating because it looks like it
should have: `unset_jwt_cookies` already cleared all four cookie names, and
`cookies_set` records names rather than values, so a logout that now revokes a
family server-side is wire-identical to one that did not. The revocation shows
up in the database, and `refresh-after-logout` is what makes it visible on the
wire.

Eleven steps are appended at positions 61–71, after the A23 block so the
existing records keep their positions. **Read two of them as a pair**, the way
A23's anti-enumeration records are read: `refresh` and
`refresh-replayed-in-grace` are both `200` with identical bodies, and the
property is that their `cookies_set` **differ** — the first rotates and returns
a new refresh cookie, the second is the second tab in a stampede and returns
none. A future diff that makes those two identical is a design regression that
no unit test phrases as a wire fact.

The three `401`s — `refresh-replayed-after-grace`, `refresh-after-family-revoked`,
`refresh-after-logout` — are byte-identical to each other on purpose: S1's
uniform-answer rule applied here, so the endpoint cannot be used to tell a stale
token from a stolen one from one that never existed.

A diff against this commit is expected. A diff against any other commit is still
a defect.

`docs/openapi.json` regenerated (one new path, one new schema, two rewritten
descriptions) and `src/shared/api/schema.ts` regenerated from it.

---

## Verification

| Gate | Result |
|---|---|
| Backend baseline at `615f860` (git worktree, own lane DB) | **1514 passed, 3 skipped, 0 failed** |
| Backend with S3 | **1556 passed, 3 skipped, 0 failed** (+42) |
| Frontend `npm test -- --run` | **682 passed, 66 files** (was 672 / 65) |
| Frontend `npm run type-check` (`tsc -b`) | clean |
| Frontend `npm run build` | built in 11.4 s |
| `npm run lint` | 157 warnings, **0 errors** — byte-identical to the baseline |
| `flask db upgrade` from EMPTY against pg18 | reaches `20260903_user_sessions`; database matches repo head |
| `flask db downgrade` then `upgrade` | table dropped and rebuilt, chain head restored |
| `Scripts/verify_contract.py` vs the **old** baseline (unextended scenario) | **1 difference across 60** — `login`'s third cookie, and nothing else |
| `Scripts/verify_contract.py` vs the **new** baseline | 0 differences across 71 |

CI parity: `SOLVERAH_IGNORE_DOTENV=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`,
`JWT_SECRET_KEY` cleared from the environment and supplied only where CI
supplies it, venv at `Desktop/solverah-venv311`, own lane databases
(`solverah_sec3` for the suite, `solverah_sec3b` for spot checks,
`solverah_sec3_chain` for the migration, `solverah_sec3_contract` for the
capture, `solverah_sec3c` for the baseline worktree). The 3 skips are the
`pg_dump`-gated backup tests and are unchanged from baseline. **The baseline was
clean, so every failure during this round was mine.**

### The migration, run from empty against pg18 (18.6 local; prod is 18.3)

```
$ psql -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
0
$ flask db upgrade
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial, Initial schema
... 21 revisions ...
INFO  [alembic.runtime.migration] Running upgrade 20260901_scoring_jobs -> 20260903_user_sessions, S3: the refresh-token table.

$ flask db heads | awk '/\(head\)/ {print $1}'
20260903_user_sessions
$ psql -tAc "SELECT version_num FROM alembic_version"
20260903_user_sessions
```

And the downgrade, which is a real one rather than a `pass`:

```
$ flask db downgrade 20260901_scoring_jobs
INFO  [alembic.runtime.migration] Running downgrade 20260903_user_sessions -> 20260901_scoring_jobs, S3: the refresh-table.
$ psql -tAc "SELECT count(*) FROM information_schema.tables WHERE table_name='user_sessions'"
0
$ flask db upgrade
INFO  [alembic.runtime.migration] Running upgrade 20260901_scoring_jobs -> 20260903_user_sessions, S3: the refresh-token table.
$ psql -tAc "... version_num ..., user_sessions tables: ..."
now at: 20260903_user_sessions, user_sessions tables: 1
```

### Each security property, shown failing without its fix

Every mutation below is a *plausible* implementation of the same feature — the
one a careful person writes without the specific insight the test encodes — not
a syntax error. A test that only fails against nonsense proves nothing.

| Property removed | Tests that go red |
|---|---|
| **Logout revokes nothing** (the pre-S3 handler: clear cookies, return) | `test_logout_revokes_the_refresh_family_server_side`, `test_a_refresh_token_captured_before_logout_is_worthless_after_it`, `test_a_token_retired_by_logout_is_never_inside_the_grace_window` — **3 failed, 41 passed** |
| **Reuse detection refuses the token but leaves the family alive** | `test_replayed_token_outside_the_grace_window_revokes_the_whole_family`, `test_reuse_detection_writes_a_security_event` — **2 failed, 42 passed** |
| **Rotation never retires the presented row** | 7 failed, 37 passed — including both concurrency tests, because an unretired row makes the grace path unreachable |
| **The rotated token never reaches the client** ("refresh just re-issues an access token") | `test_refresh_rotates_the_token_on_every_use`, `test_rotation_keeps_one_family_and_links_the_chain`, `test_two_simultaneous_refreshes_of_one_token_do_not_revoke_the_family` — **3 failed, 41 passed** |
| **No grace window** (any replay is theft — the design that works single-tab) | `test_replaying_a_just_rotated_token_inside_the_grace_window_succeeds`, `test_two_simultaneous_refreshes_of_one_token_do_not_revoke_the_family` — **2 failed, 42 passed** |
| **`expire_stale` stamps the clock instead of the death** | `test_expire_stale_stamps_only_rows_past_their_expiry`, `test_retention_run_deletes_exactly_the_expired_delivered_and_terminal_rows` — **2 failed, 42 passed** |
| **No CSRF guard on the refresh POST** | `test_a_cross_site_origin_is_refused`, `test_a_look_alike_origin_is_refused`, `test_a_form_content_type_is_refused` — **3 failed, 41 passed** |
| **Account deletion keeps the sessions** | `test_deleting_the_account_destroys_its_sessions` — **1 failed, 43 passed** |
| **Client single-flight removed** (each 401 issues its own refresh) | `issues ONE refresh for two simultaneous 401s` — *"expected [ 'POST /api/v1/auth/refresh', …(1) ] to have a length of 1 but got 2"* |
| **`if` → `while` on the 401 retry** | `does not loop when the replay 401s again` — *"promise resolved 'undefined' instead of rejecting"* |
| **The boot probe never refreshes** (the fifteen-minute session) | `refreshes and re-probes when a returning visitor's access token has expired`, `does not retry the refresh in a loop when it fails`, `forgets the session hint once the refresh has failed` — **3 failed, 4 passed** |

The four the brief names by hand, in its words:

- *logout invalidates a refresh token* — row 1, and
  `test_a_refresh_token_captured_before_logout_is_worthless_after_it` is the
  exploit run end to end.
- *a retired token outside the grace window revokes its family* — row 2.
- *rotation issues a new token each time* — row 4.
- *concurrent refresh does NOT self-revoke* — rows 5 and 9, one on the server
  (two threads on one Postgres row, released by a barrier) and one on the client
  (two 401s, one exchange).

### Two defects found and fixed in passing

1. **`expire_stale` reset the retention clock** — described under §9. Found by
   the double-condition matrix in `tests/test_ops_cli.py`, not by reading the
   code.
2. **`tests/test_users_table.py::test_the_rename_left_nothing_carrying_the_old_name`
   was a prefix allowlist wearing a rule's clothes.** It flagged any index or
   sequence not starting `users` or `user_intake` as a leftover from the Phase
   2c rename, so `user_sessions_pkey` and `user_sessions_id_seq` — a table Part
   4.2 always spelled that way, never renamed from anything — failed it. The
   check now derives the allowlist from the tables that actually exist, which
   says what was meant, needs no maintenance, and is strictly stricter:
   `user_pkey` fails it because there is no `user` table, which is exactly the
   leftover being hunted.

One thing tidied while there: `model.UserSession` names its three foreign-key
constraints explicitly, so `db.create_all()` (what the suite builds) and the
migration (what production runs) produce the same constraint names. Unnamed,
Postgres would generate `user_sessions_user_id_fkey` in one and
`fk_user_sessions_user` in the other — a divergence that stays invisible until
something addresses a constraint by name, which
`test_a_session_whose_account_is_gone_is_refused_not_a_500` does.

### One hardening added beyond the brief

`rotate()` refuses a session whose account row is gone, rather than
dereferencing `None` and answering `500` on the path that mints credentials.
Very nearly unreachable — `user_id` cascades, and deletion removes these rows
explicitly — but "very nearly" is not a thing to leave unhandled where an
attacker controls the input.

---

## Not implemented, deliberately

### "Sign out everywhere"

The rows support it — one `UPDATE ... WHERE user_id = ?` — and there is no
screen that asks for it. An endpoint with no caller is a surface with no test
behind it in practice; it lands with the settings screen that drives it.

### A denylist for the last fifteen minutes

Closing the post-logout access-token window entirely needs a `jti` denylist
consulted on every authenticated request. A7 explicitly traded that for one
lookup per refresh. The finding's exploit — an attacker with a captured cookie
keeping access after the victim logs out — went from an hour to fifteen minutes,
and the refresh half of it went to zero. Recorded rather than closed.

### `user_agent` / `ip` on `user_sessions`

Part 4.2 draws them. They are identifying data whose only reader would be a
device-list screen, and the same audit raised #18 and #7 against retaining
identifying data past any reader. They arrive with the screen.

### Audit #25 (`/auth/logout` has no CSRF check)

Still open, and its severity is unchanged rather than raised: a forged logout
clears cookies (as before) and now provably cannot revoke a family, because the
CSRF failure is what puts it on the no-`sid` path. Making logout hard-require
CSRF would mean a caller whose access token expired cannot clear their own
cookies, which is a worse trade than the one being made.

---

## Files changed

**Application** — `model.py`, `security.py`, `solverah/domain/auth.py`,
`solverah/services/refresh_tokens.py` *(new)*, `solverah/api/v1/auth.py`,
`solverah/api/v1/intake.py`, `solverah/factory.py`, `solverah/schemas/auth.py`,
`solverah/repositories/account_repository.py`, `solverah/cli.py`

**Migration** — `migrations/versions/20260903_user_sessions.py` *(new)*

**Frontend** — `src/features/auth/AuthContext.tsx`

**Generated / contract / docs** — `docs/openapi.json`,
`src/shared/api/schema.ts`, `docs/contract_baseline.json`,
`Scripts/capture_contract.py`, `docs/ARCHITECTURE.md` (A24),
`docs/audits/SECURITY_S3_ROUND_REPORT.md` *(this file)*

**Tests, new** — `tests/test_refresh_tokens.py`,
`src/features/auth/AuthContext.refresh.test.tsx`

**Tests, updated** — `tests/test_ops_cli.py`, `tests/test_users_table.py`,
`tests/msw/handlers.ts`, `src/features/auth/AuthContext.boot.test.tsx`

