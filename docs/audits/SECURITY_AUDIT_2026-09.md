# Security Audit — Solverah as-built — 2026-09-02

**What this is:** a security audit of the running application at commit `07e3a80`
(branch `causal_bayesian_model`), across ten areas: auth depth, token/email
flows, the anonymous surface, GDPR export/deletion, uploads, injection, transport
headers, secrets hygiene, rate-limit coverage, and the D-01 employer-isolation
invariant. Read-only: no application code was changed. Findings carry `file:line`
evidence, a concrete exploit, and a one-line fix intent for scoping later rounds —
**not** an instruction to implement.

**How the evidence was gathered:** every cited line was read. The highest-value
claims were additionally *executed*: the app was booted against a scratch
database (`solverah_sec` on `localhost:5433`, CI-style env with
`SOLVERAH_IGNORE_DOTENV=1`, no real keys in-process) and probed with live HTTP.
Findings marked **[probed]** were reproduced against the running app; the rest
are read-verified. No render.com host or third-party service was touched.

**A note on the threat model:** there is no employer principal in the system yet
(`auth_service.py:113` hard-codes `role = "job-seeker"`; intake and `PATCH /me`
refuse any other role). Every D-01 finding is therefore about the boundary
*holding when employers arrive*, not a live cross-tenant leak today. All other
areas are live.

---

## Ranked findings

Severity is impact × exploitability given the current deployment. "Conditional"
means the severity depends on a deployment fact (usually: is the production
rate-limit store Redis or `memory://`).

| # | Sev | Finding | Area |
|---|-----|---------|------|
| 1 | HIGH | Logout revokes nothing server-side; a stolen access cookie survives logout for up to 1h (A7 never built) | Auth |
| 2 | HIGH | Password-reset OTPs come from `random.randint` (Mersenne Twister) and mint a full session | Tokens |
| 3 | HIGH (cond.) | `memory://` rate-limit storage is permitted in production — every limit becomes per-worker and resets each deploy | Rate limits |
| 4 | HIGH | No parse timeout: one crafted PDF pins a worker indefinitely → `default`-queue DoS | Uploads |
| 5 | HIGH | No DOCX decompression-bomb guard: a 10 MB zip-bomb docx OOMs a worker | Uploads |
| 6 | HIGH | Account deletion never scrubs the legacy `users.profile_data` blob — pre-Phase-2a users' full PII survives the tombstone | GDPR |
| 7 | HIGH | `resume_parse_jobs` rows (name-bearing filenames + object keys) survive deletion forever; no purge task exists | GDPR |
| 8 | MED | User enumeration on forgot/resend/register + a login timing oracle | Tokens |
| 9 | MED | Login lockout is per-account only → indefinite victim lockout DoS; password-spraying evades it | Auth |
| 10 | MED | No per-account attempt cap on OTP verification — codes survive wrong guesses | Tokens |
| 11 | MED **[probed]** | Anonymous `wpll` LLM enqueue has no global spend ceiling — cost amplification across IPs | Anon surface |
| 12 | MED | Attacker-controlled text is echoed verbatim into the `wpll` LLM prompt, no length cap | Anon surface |
| 13 | MED | `resumeKey` is client-writable and the agent fetches any key it names with no owner-prefix check → cross-tenant resume read | Uploads |
| 14 | MED | Content-type is client-declared end-to-end; no magic-byte validation anywhere | Uploads |
| 15 | MED | `override_defaults=True` silently dropped the 200/day backstop on auth + LLM routes (36× brute/spend budgets) | Rate limits |
| 16 | MED | `POST /me/resumes/<id>/parse-jobs` enqueue has no explicit limit (rides global default) | Rate limits |
| 17 | MED **[probed]** | Production CORS reflects `http://localhost:<port>` / `127.0.0.1:<port>` with credentials, unconditionally | Headers |
| 18 | MED | `audit_log.event_metadata` stores the user's email and is retained forever, past deletion | GDPR |
| 19 | MED | Export silently omits several identified data classes (statement selections, two instruments' answers, resume corrections, activity log) | GDPR |
| 20 | MED | Outbox parked (8×-failed) rows retain email + OTP payloads indefinitely; deletion never scrubs the outbox | GDPR |
| 21 | MED (cond.) | Missing `redis` driver silently downgrades a Redis-configured limiter to `memory://` in production | Rate limits |
| 22 | LOW | `GET /me/matches` is an O(all-companies) scan that can write on GET, default limit only | Rate limits |
| 23 | LOW (latent) | Four causal-model funnel tables have no export or deletion coverage (no writer exists yet) | GDPR |
| 24 | LOW | `scoring_jobs.result` for owned instruments survives deletion up to ~7 days | GDPR |
| 25 | LOW | `/auth/logout` has no CSRF check — a cross-site page can force-logout a victim | Auth |
| 26 | LOW | Non-constant-time OTP comparison (`!=`) | Tokens |
| 27 | LOW | OTPs stored plaintext in `users` and duplicated into `outbox` payloads | Tokens |
| 28 | LOW | A successful password login does not clear an outstanding reset OTP | Tokens |
| 29 | LOW | Email-as-identity: a stale (≤1h) JWT authenticates as whoever re-registers a tombstoned address | Auth |
| 30 | LOW | Any authenticated user can name an arbitrary Groq model on `/agent/messages` | Injection |
| 31 | LOW | Guest insight endpoint returns exception internals in the body | Injection |
| 32 | LOW | D-01 guard test enforces table-reachability, but the sanctioned doorway's outputs bypass it | D-01 |
| 33 | LOW | Four instruments' raw answers sit outside D-01's enforced doorway | D-01 |
| 34 | LOW | The `/me` upload flow never HEADs the object after upload (intake does) | Uploads |
| 35 | LOW | Export leaks the raw R2 object key via `resumeKey` while the intake block masks it | GDPR |
| 36 | LOW | Cascade drift: 8 tables would break a future hard-delete of a user row | GDPR |
| 37 | LOW | `retention_cleanup.py` is not wired into `BEAT_SCHEDULE` — the compensating sweeps may never run | GDPR |
| 38 | INFO | Assorted (see §11): dead JWT knob, tracked empty `_scratch_key_transfer.env`, uuidv7 handles, guard blind spots, debug files | Multiple |

**Top of the fix queue** (highest impact per line of change): #1 (jti denylist +
revoke on logout), #2 (`secrets` for OTPs), #6/#7 (scrub `profile_data`, delete
`resume_parse_jobs` in `delete_personal_rows`), #4/#5 (Celery `task_time_limit` +
docx expanded-size cap), #3 (make `memory://` fatal in prod).

---

## 1. Auth depth

### 1.1 — HIGH — Logout revokes nothing; a stolen cookie survives it (A7 never built)

Decision A7 ("refresh tokens live in the DB for revocation/reuse-detection") was
**never implemented**. Verified exhaustively:

- No `/auth/refresh` route and no `user_sessions` table exist. The architecture
  doc admits both are unbuilt (`docs/ARCHITECTURE.md:1034` "*not built* — needs
  `user_sessions` (A7)"; `model.py:117-122` "Neither exists yet").
- No JWT blocklist callback: `solverah/extensions.py:39` is a bare
  `jwt = JWTManager()`. Grep for `jti|blocklist|denylist|revoked|token_in_blocklist`
  across application code returns nothing. No token-version column on `User`.
- Logout only clears the cookie — the docstring says so:
  `solverah/api/v1/auth.py:207-219`, "*The JWT itself stays valid until it
  expires — clearing the cookie ... cannot revoke the token*."

Access tokens are cookie-only, 1-hour lifetime (`solverah/factory.py:250`).

**Exploit:** an attacker who captures the access cookie (subdomain XSS, proxy
log, shared device) keeps full access to every `@jwt_required()` endpoint for up
to an hour; the victim clicking "logout" does nothing, and no operator action
short of rotating `JWT_SECRET_KEY` fleet-wide revokes it.

*Mitigating nuance (verified):* account **deletion** does effectively revoke,
because identity is the email and `tombstone_user` rewrites it
(`account_repository.py:88-119`), so the stale token's `find_by_email` fails.

**Fix:** register a `@jwt.token_in_blocklist_loader` over a small `jti` denylist
(redis/table) and insert the current `jti` on logout.

### 1.2 — MED — Login lockout is per-account only: victim-lockout DoS and spray evasion

`solverah/services/auth_service.py:204-220` (duplicated for intake sign-in at
`intake_service.py:341-353`): failures increment `users.failed_login_count`; at
5 (`MAX_LOGIN_ATTEMPTS`, `:60`) it sets `locked_until` for 15 min (`:61`).

- Keyed per-email only; the per-IP half is just the `5 per minute` limiter
  (`auth.py:179`). Counter is DB-backed, so *this half* is correctly multi-worker
  safe (negative result).
- After `locked_until` passes, the counter is zero (cleared at lock time, `:213`),
  giving a fresh 5 guesses each window.

**Exploit (DoS):** an attacker POSTs 5 wrong passwords for `victim@x.com` every 15
minutes (well within `5/min`) and locks the victim out **indefinitely**, on both
login and intake sign-in — no CAPTCHA, no unlock email. **Exploit (evasion):**
password-spraying (1 guess × N accounts) never trips the per-account counter, and
lockout is checked *before* the password (`:205-208`) so it is not a password
oracle (that ordering is correct).

**Fix:** add per-IP failure tracking in shared storage + CAPTCHA/backoff instead
of a hard per-account lock (or lock only password-login, with email unlock).

### 1.3 — LOW — CSRF-less logout

`/auth/logout` (`auth.py:207`) carries no `@jwt_required()` and thus no CSRF
check; any cross-site page can POST it and force-clear the victim's cookie.
Nuisance-level. **Fix:** `@jwt_required(optional=True)` or verify CSRF when
cookies are present.

### 1.4 — LOW — Email-as-identity reuse window

The JWT identity claim is the mutable email (`auth.py:104`); tombstoning frees the
address (`account_repository.py:91-98`). A stale ≤1h token bearing an address that
someone re-registers authenticates as the new owner. Narrow (delete→re-register
race). **Fix:** falls out of 1.1, or switch identity to `user.id`.

### 1.5 — INFO — Dead config knob

`Settings.jwt_access_token_minutes` (`config.py:316-318`, env
`JWT_ACCESS_TOKEN_MINUTES`) is validated and stored but never applied —
`factory.py:250` hardcodes `timedelta(hours=1)`. Operators who set it get no
effect.

---

## 2. Token / email flows

### 2.1 — HIGH — OTPs come from Mersenne Twister, and one of them mints a session

`solverah/domain/auth.py:52-62`: `return str(random.randint(100000, 999999))`.
The docstring itself flags it: "*`random` is a Mersenne Twister, so observing
enough codes recovers the state and predicts the next one.*" This one generator
feeds email confirmation (`auth_service.py:138`), resend (`:297`), **and
password-reset / passwordless sign-in** (`:332`), where `verify_password_reset`
(`:344-384`) returns `issue_token=True` — a full authenticated session, never
touching `password_hash`.

**Exploit:** harvest a stream of codes from a worker's RNG via self-registration
/ resend, reconstruct the Twister state, call `/auth/password/forgot` for the
victim, predict the 6-digit code, and post it to `/auth/password/reset` to receive
the victim's session cookie — **without ever touching the victim's inbox**.
*Practical caveat:* state recovery needs ~624 consecutive 32-bit outputs from the
*same* worker with no interleaved `random` use, which a multi-worker prod makes
harder than the one-liner implies — hence HIGH, not critical. It remains a
session-granting predictable secret.

**Fix:** `secrets.randbelow(900000) + 100000`.

### 2.2 — MED — No per-account cap on OTP verification **[probed]**

`confirm_email` (`auth_service.py:254-279`) and `verify_password_reset`
(`:344-369`) return an error on mismatch and **leave the code valid**; there is no
`*_attempt_count`. The only guard is a per-IP limiter (`5/min` verify at
`auth.py:280`; reset at `:360`). Probed: 5 wrong codes returned `429 "5 per 1
minute"` and the *correct* code was then also blocked — so the per-IP throttle
fires, but a distributed attacker gets unthrottled-per-account guessing at a
6-digit code across its 15-minute window (`domain/auth.py:33`), and under `memory://`
in prod (see 9.1) even the per-IP bound resets per worker/deploy.

**Fix:** clear the code after ~5 wrong guesses.

### 2.3 — MED — User enumeration + login timing oracle **[probed]**

| Endpoint | Existing email | Unknown email | Oracle |
|---|---|---|---|
| `POST /auth/register` | `400 "User already exists"` (`auth_service.py:126`) | `201` | **body** |
| `POST /auth/password/forgot` | `200`/(sends) | `404 "No account found with that email address."` (`:328`) | **body + status** |
| `POST /auth/email/verify/resend` | `200`/`400 "Email already confirmed"` (`:294`) | `404 "Account not found"` (`:290`) | **body + status** |
| `POST /auth/login` | uniform `401`, **bcrypt runs** | `401`, bcrypt **skipped** (`:208`) | **timing** |

All four reproduced live against the scratch DB (forgot/resend returned the exact
404 bodies above for an unknown address; the duplicate register returned the 400).
The login short-circuit `if not user or not check_password(...)` (`:208`) makes an
unknown-email 401 return measurably faster than a wrong-password 401, and the
`403 "Email not confirmed"` (`:223-227`) fires only after a *correct* password.

**Exploit:** replay a mailing list against `/auth/password/forgot`; 200-vs-404
yields a clean registered-user list.

**Fix:** uniform 200 responses + a dummy bcrypt hash on the unknown-user login
branch.

### 2.4 — LOW cluster (verified)

- **Non-constant-time compare:** `user.confirmation_token != code` (`:269`),
  `user.reset_token != code` (`:364`) — use `hmac.compare_digest`.
- **Plaintext OTP at rest:** `users.confirmation_token`/`reset_token`
  (`model.py:124,128`) and duplicated into `outbox` payloads (`model.py:1264-1268`);
  a DB read yields live session-granting codes.
- **Login doesn't clear an outstanding reset OTP** (`:217-220` clears only lockout
  fields) — an attacker-triggered code stays live 15 min even after the victim
  logs in.

### 2.5 — NEGATIVE — Form-token secret (D-05) holds; codes are single-use

- `SOLVERAH_FORM_TOKEN_SECRET` has **no default anywhere**. Every consumer raises
  when unset: `assessment_store.py:81-90` (`respondent_id_for_user`,
  `os.environ.get` with no second arg → `RuntimeError`),
  `causal_graph/v1_model/present_items.py:215-225`. No `or "..."` / two-arg default
  grew. The only literals in-tree are test constants and the *untracked*
  `Scripts/load_baseline.override.yml`. Guarded by `tests/test_assessment_form.py`.
- Both OTPs are single-use (cleared on success, `:277`, `:367`), rotate on
  re-request (`:297,:332`), and expire at 15 min (`domain/auth.py:65-90`). There is
  no change-password/change-email endpoint (`me.py` allows name only, `:159-164`),
  so "does password-change invalidate reset tokens" is N/A. The intake variant uses
  a 128-bit `uuid4().hex` token (`intake_service.py:270`) — cryptographically fine.

---

## 3. The anonymous surface (`wpll`)

`wpll` is the anonymous teaser: enqueue at `POST
/assessments/wpll/scoring-jobs`, poll at `GET
/assessments/wpll/scoring-jobs/<job_id>`; `_require_auth_for` skips JWT/CSRF for it
by design (`assessments.py:156-171`).

### 3.1 — MED — No global spend ceiling on the anonymous LLM enqueue **[probed]**

The `wpll` enqueue rides `DEFAULT_LIMITS` = `"200 per day;50 per hour"`
(`assessments.py:94-100`, applied at `:430`), keyed on `get_remote_address`
(`extensions.py:46`) — **per IP**. Every accepted enqueue commits a `scoring_jobs`
row *and* triggers a paid provider call in the worker (`gpt-4o-mini` via
`assessment_service.py:146-153`, no `max_tokens`).

**Probed:** 40 back-to-back enqueues from one IP all returned `202` (49 s) — no
per-minute cap; the bound is only the 50/hour global default. The *other*
anonymous LLM endpoint, `POST /intake/quiz-preview/insights`, carries the missing
control — a global-key bucket `500 per day` (`intake.py:330-332`,
`security.py:264`) whose own comment states the principle ("*spend scales with the
number of distinct IPs*"). It was simply not applied to `wpll`.

**Exploit:** an attacker with N addresses makes N × (200/day) unauthenticated
provider calls and N × 200 committed rows/day; under `memory://` in prod (9.1) the
per-IP cap resets per worker/deploy too.

**Fix:** add a second `@limiter.shared_limit("<budget> per day",
scope="assessments:submit:wpll:global", key_func=global_rate_limit_key)`, mirroring
the guest-insights route.

### 3.2 — MED — Attacker text echoed verbatim into the LLM prompt, no length cap

`assessment_prompts.py:255`: `option_text = q_data["options"].get(suffix, o_id)` —
when the `option_id` suffix doesn't match a known option, the **raw client string
`o_id`** is placed into the prompt. `WorkPulseAnswer` sets `extra="allow"` with no
length bound (`schemas/assessments.py:52-56`); the only cap is the 2 MB body
(`factory.py:244`).

**Exploit:** (a) cost amplification — each of ≤5 answers can carry a ~2 MB
`option_id`, driving input tokens toward the context limit at zero attacker cost;
(b) prompt injection into the model (impact bounded: the result returns only to the
caller). **Fix:** `.get(suffix)` and drop unmatched answers; add `max_length` +
`extra="forbid"`.

### 3.3 — NEGATIVE (with a fragility note) — Job isolation holds; handles are uuidv7 **[probed]**

- The anonymous poll filters `user_id IS NULL` in the query
  (`scoring_jobs.py:414-436`), so it can read **only** ownerless `wpll` jobs, never
  an owned job. Probed: polling a `wpll` handle at the `work_pulse` path returned
  `401` (auth required); the owned path scopes `user_id` in the query
  (`find_for_user`, `:389-411`). No cross-tenant read.
- The poll body is `{insight_text, locked_sections}` only; the submitted `payload`
  is nulled the moment the job goes terminal (`:261`) and by the reaper (`:480`);
  provider exceptions become a fixed `GENERIC_FAILURE` string (`:130-137`).
- **Fragility:** the handle is `public_id`, defaulted to `uuidv7()`
  (`model.py:1409-1411`) — time-ordered, ~74 random bits vs uuid4's 122. Safe today
  (unguessable under the poll limit; prize is one teaser sentence) but any richer
  `wpll` result or new anonymous job type inherits a weaker-than-uuid4 capability as
  its only auth. **Fix:** mint ownerless handles from `uuid4()` app-side.

---

## 4. GDPR completeness vs schema drift

Coverage was checked table-by-table across `model.py` and every migration. The
export path is `me.py:219-228` → `account_service.export_account_data:161-218`; the
delete path is `me.py:179-209` → `account_service.delete_account:221-270` →
`account_repository.delete_personal_rows:61-85` + `tombstone_user:88-119`. Deletion
tombstones rather than hard-deletes, so **every `ondelete="CASCADE"` is inert** —
child rows must be deleted explicitly, and the tables below are not.

### 4.1 — HIGH — Deletion leaves the legacy `users.profile_data` blob intact

`model.py:113` `profile_data = db.Column(JSON, default=dict)` is kept for
rollback (`model.py:966-972`; migration `20260827_decompose_profile_data.py:9`
"*`user.profile_data` is not dropped*"). `tombstone_user` scrubs email, password,
name, tokens and the *new* profile tables but **never touches `profile_data`**
(grep confirms no reference in `account_repository.py`/`account_service.py`).

**Scenario:** any user who registered before Phase 2a deletes their account; their
entire pre-decomposition profile — phone, LinkedIn, parsed resume text, experience
history, quiz results — remains verbatim in the "scrubbed" tombstone row. **Fix:**
`user.profile_data = {}` in `tombstone_user`, plus the planned column drop.

### 4.2 — HIGH — `resume_parse_jobs` survives deletion forever; no purge exists

`model.py:1328-1334`: `object_key`, `resume_name`, `user_id ondelete=CASCADE`
(inert under tombstoning). `delete_personal_rows` does not mention the table;
`resume_jobs.py` has only `reap_stalled`, no `purge_terminal`; `BEAT_SCHEDULE`
(`infra/queue.py:113-139`) has no resume-jobs purge.

**Scenario:** user deletes their account; rows keyed to the tombstone id remain
indefinitely holding `object_key = profile/{user_id}/{id}/resume.pdf` and
`resume_name` (typically "Firstname Lastname Resume.pdf"). Also absent from export.
**Fix:** delete the user's `ResumeParseJob` rows in `delete_personal_rows` and add
a terminal-row purge mirroring `scoring_jobs.purge_terminal`.

### 4.3 — MED — `audit_log.event_metadata` carries the email, retained forever past deletion

`intake_service.py:431-436` writes `metadata={"submission_id":..., "email":
current_email}`. `retention_cleanup.py:114-121` minimizes only `ip_address` and
`user_agent`; `event_metadata` is never touched and audit rows are kept by design
on deletion (`account_service.py:22-23`). **Scenario:** a user links an intake,
later deletes their account; an audit row with their real email in JSON persists
indefinitely, defeating the tombstone. **Fix:** stop writing the email
(`actor_user_id` already identifies the actor), or scrub it in the sweep.

### 4.4 — MED — Export silently omits several identified data classes

`export_account_data` returns exactly `account, profile, intake_submissions,
legacy_quiz, assessment_answers, dimension_scores, job_recommendations`. Missing:
`user_intake.selected_statement_ids` (existence-checked only, `account_service.py:149`);
`assessment_submissions.answers`/`narrative` for `focus_type` and `manager_match`
(`_legacy_quiz` reads only `wpll`/`work_pulse`, `:145-158`); `resume_parse_correction`
(resume-derived content, `model.py:302-303`); `audit_log`; and the ≤7-day
`scoring_jobs.result` blobs. The guard test is stale — `tests/test_account_lifecycle.py:78`
asserts only email + one answer + one score. **Fix:** add the missing blocks and
enumerate tables in the test.

### 4.5 — MED — Outbox parked rows retain email + OTP payloads indefinitely

Delivered rows *are* purged at 24 h (`outbox.purge_published:296-313`) — so the
common case is fine. But a row that fails `MAX_ATTEMPTS` (8, `:111`) parks forever
with its payload — an address + OTP, or a full early-access lead (name, email,
phone, career_journey). `delete_account` never queries `outbox`. **Scenario:** a
verification email hard-bounces 8×, the user deletes their account; an outbox row
with their email and code persists. **Fix:** purge/scrub parked rows after a
bounded window, and match-delete outbox rows on account deletion.

### 4.6 — LOW/latent — Funnel tables have no export or deletion coverage

`match_recommendation`, `rec_action`, `outcome_appeal`, `outcome_experienced`
(the last holds self-reported job satisfaction, `model.py:938-963`) appear in
neither export nor deletion, and their `user_id` FKs carry no `ondelete`.
*Mitigating:* no production writer exists yet (grep for the constructors outside
model/tests/schemas finds none). **Fix:** decide export/delete/de-identify before
the first writer lands.

### 4.7 — LOW — `scoring_jobs.result` survives deletion up to ~7 days

Deletion doesn't touch the table; `purge_terminal` (`PURGE_DAYS=7`,
`scoring_jobs.py:129`) bounds it. A user's Work Pulse narrative/archetype stays
readable in `result` for up to a week post-deletion. **Fix:** delete the user's
rows in `delete_personal_rows`.

### 4.8 — LOW — Export leaks the raw R2 object key

`profile_document.py:617` sets `document["resumeKey"] = state.resume.object_key`
and export returns the document verbatim (`account_service.py:176`), while the
intake block deliberately masks keys to basenames (`:187-189`). Inconsistent
application of the same rule. **Fix:** mask `resumeKey` in the export payload.

### 4.9 — LOW — Cascade drift; and 4.10 — retention sweep may not run

8 tables lack `ondelete` (`job_recommendation:45`, `user_intake:217`,
`audit_log.actor_user_id:273`, `resume_parse_correction:299`, `assessment_response:598`,
`person_dimension_score:631`, `match_recommendation:818`, `outcome_experienced:941`);
today no cascade fires (tombstone), but a future `DELETE FROM users` would fail —
and a naïve "fix" that adds cascades to the person-side tables would destroy the
D-16-retained research rows. Separately, `retention_cleanup.py` is a standalone
script absent from `BEAT_SCHEDULE` (`:3` "*Run periodically (Render cron, or
manually)*"); if the external cron isn't wired, the abandoned-intake (90 d),
audit IP/UA (365 d), and **orphaned-R2-object** sweeps never run — and the last is
the compensating control that reclaims resume objects after deletion. Could not
verify the Render cron from the repo.

### 4.11 — NEGATIVE — Verified correct

Anonymous respondents who later link an account are covered (all three claim paths
pin the row to the account's own immutable email — `intake_service.py:334,416`,
`me.py:159-164`); resume bytes in R2 are deleted first with failures surfaced
(`account_service.py:231-233`); the AI agent stores no conversation log
(`agent_service.py` keeps a 10-min in-process cache only); `person_dimension_score`
/`assessment_response` post-deletion retention is a documented, test-asserted
decision (D-16), not drift.

---

## 5. Uploads

Presigned two-step, both flows. The design's core bindings are **correct**
(negative results): the presign passes `ContentType`+`ContentLength` into the
signed params (`resume_service.py:109-119`, `intake_service.py:147-157`) after
size/mime pre-validation (`me.py:387-402`, 10 MB cap `storage.py:20-28`); keys are
uuid4-scoped (`intake/{uuid4}/…`, `profile/{user_id}/{uuid4}/…`); the intake
finalize rejects foreign keys (`domain/intake.py:126-127`) and the authenticated
flow takes no client key at all, rebuilding it under the caller's own id
(`profile_service.py:449-473`); job polling is user-scoped
(`resume_jobs.py:221`); and a hostile file's failure writes a terminal `FAILED`
with no retry storm (`resume_jobs.py:193-200`, conditional claim `:120-132`).

### 5.1 — HIGH — No parse timeout: one crafted PDF pins a worker

`infra/queue.py:175-197` sets `task_acks_late`/`prefetch_multiplier=1` but **no**
`task_time_limit`/`task_soft_time_limit` (grep of `solverah/` for
`time_limit|soft_time`: zero hits). The parse runs
`pdfminer.high_level.extract_text` unbounded (`resume_service.py:74-78`).

**Exploit:** upload a pathological PDF (known pdfminer CPU blowups), POST
`/me/resumes/{id}/parse-jobs` (no per-route limit — see 9.4); the worker spins
forever. `reap_stalled` fails the *row* at 30 min but never kills the *process*.
A handful of uploads exhaust every `default`-queue worker. **Fix:** set
`task_time_limit`/`task_soft_time_limit` (e.g. 60 s / 45 s).

### 5.2 — HIGH — No DOCX decompression-bomb guard

`resume_service.py:80-85` hands the file straight to `docx.Document(str(file_path))`,
which unzips `document.xml` fully via zipfile/lxml with no ratio check. The 10 MB
cap bounds the *compressed* size only; XML compresses >1000:1, so a 10 MB docx can
inflate to ~10 GB. **Exploit:** upload a zip-bomb docx, trigger a parse job, the
worker OOMs; each new parse request murders another worker. **Fix:** before
`docx.Document`, reject via `zipfile.ZipFile` if summed member size exceeds a cap.

### 5.3 — MED — Content-type is client-declared end-to-end

The only checks are `mime in ALLOWED_MIME` on the declared string
(`me.py:398`, `intake_service.py:132`) and the HEAD comparison
`head.get("ContentType") == mime` (`intake_service.py:184-186`) — but R2's stored
ContentType *is* the client's PUT header, so that compares the declaration to
itself. No magic-byte sniffing anywhere (grep for `magic|filetype|%PDF|startswith(b`:
zero hits). **Exploit:** declare `application/pdf`, upload arbitrary ≤10 MB bytes;
it is stored and later served under a presigned GET with `Content-Type:
application/pdf` — the bucket becomes a file host with plausible career-site URLs,
and the declared mime (not the content) selects the parser. **Fix:** sniff magic
bytes in the worker before choosing a parser.

### 5.4 — MED — `resumeKey` is client-writable; the agent fetches any key it names

`validators.py:13-35`: `ALLOWED_PROFILE_FIELDS` includes `resumeKey` (`:31`) and
`uploadedResume` (`:30`), so `PATCH /me/profile` can set them (`me.py:264-284`).
Then `agent_service.py:126-150` reads `resume_key = profile_data.get("resumeKey")`
and calls `s3.get_object(Key=resume_key)` **with no owner-prefix check** (verified:
lines 136-150 contain no `startswith`), and the extracted text enters the agent's
system prompt (`intelligence.py:131-133`).

**Exploit:** an attacker who learns any victim object key (keys travel in intake
notification emails, outbox rows, job rows) sends `PATCH /me/profile {"profile":
{"resumeKey": "profile/42/<uuid>/resume.pdf", "uploadedResume": {"type":
"application/pdf"}}}`, then asks `/agent/messages` "summarize my resume" — the
victim's resume text streams back. uuid4 keys make blind guessing infeasible →
MED. **Fix:** require `resumeKey.startswith("profile/%s/" % user.id)` in
`fetch_resume_text`, or drop `resumeKey`/`uploadedResume` from the writable
whitelist (they are server-derived).

### 5.5 — LOW — The `/me` flow never HEADs the object post-upload

`POST /me/resumes/{id}/parse-jobs` (`me.py:483-517`) validates only re-declared
mime/size and queues; the worker swallows fetch failures into `""`
(`resume_service.py:134-157`). Contained (size enforced by the signed PUT, key is
own-prefix), but an empty extraction "succeeds" and blanks the caller's own
profile. **Fix:** HEAD before enqueue (mirror `intake_service.verify_upload`) and
treat empty extraction as `failed`.

---

## 6. Injection + raw surfaces

**Overwhelmingly clean (negative results).** Every runtime raw-SQL site is
parameterized — SQLAlchemy Core/ORM constructs throughout
(`repositories/*`, `services/{outbox,resume_jobs,scoring_jobs,audit}.py`), the one
`sa.text(...)` in `profile_repository.py:328` uses bound params, and
`intake_repository.py:76-99` uses psycopg2 `%s` placeholders with an args tuple.
`company_repository.py:151` interpolates the search term into a LIKE *pattern* but
sends the pattern as a bound param (no SQLi; wildcard-in-own-search only). No
f-string/`.format`/concat SQL reaches any `execute()`. No `subprocess`/`os.system`/
`eval`/`exec`/`pickle` in runtime code; Celery is pinned to JSON serialization
(`queue.py:180-183`), closing broker-pickle RCE. `yaml.safe_load` only, on a
repo-local file. No `render_template_string`, no request-derived filesystem paths
(tempfiles use `NamedTemporaryFile`), no XXE surface beyond python-docx's internal
lxml (the zip bomb in 5.2 is the real docx risk). No SSRF: every outbound URL is a
fixed base (O*NET, OpenAI/Groq SDKs, boto3, Resend); `linkedin_url`/`portfolio_url`
are format-validated and never fetched. **The AI agent has no tools** — it is a
plain streaming completion (`intelligence.py:136-139`), so resume-borne prompt
injection can distort *that user's* answer but cannot trigger actions; keep this
no-tools invariant.

Residual LOWs: **6.1** any authenticated user can name an arbitrary Groq model on
`/agent/messages` (`intelligence.py:130` `data.get("model")`) — spend/probing;
pin to an allowlist. **6.2** the guest insight endpoint returns exception internals
in the body (`insight_service.py:108-110`, `"Unable to generate insight: %s: %s"`)
— reachable unauthenticated; SDK exception strings can carry endpoint/quota
details; log the detail, return a generic 500. **6.3** guest quiz text has no
per-field length caps (`schemas/intelligence.py:128-136`) — bounded only by the
2 MB body + rate limits.

---

## 7. Headers / transport

**[probed]** Live response headers (dev) and config read together:

- **CSP is solid** and applied (`factory.py:313-330`, confirmed on the wire):
  `default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors
  'none'; base-uri 'self'` — no `unsafe-inline`. Plus `X-Frame-Options:
  SAMEORIGIN`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`.
- **HSTS / force_https are production-gated** (`factory.py:325-329`,
  `strict_transport_security=is_production`, max-age 1 y + subdomains + preload) —
  correct; absent in dev as expected.
- **JWT cookies:** `Secure` defaults to `is_production`, `SameSite=None` in prod /
  `Lax` dev, `HttpOnly`, CSRF double-submit on all mutating methods
  (`factory.py:247-271`); prod config is fatal if `SameSite=None` without `Secure`
  (`config.py:209-230`). Correct.

### 7.1 — MED — Production CORS reflects `localhost`/`127.0.0.1` with credentials, unconditionally **[probed]**

`factory.py:293-306` lists `r"http://localhost:\d+"` and `r"http://127\.0\.0\.1:\d+"`
in `origins` with `supports_credentials=True`, **not gated on `is_production`**.
Probed: `Origin: http://localhost:9999` was reflected as
`Access-Control-Allow-Origin: http://localhost:9999` with
`Access-Control-Allow-Credentials: true` (while `https://evil.example.com` was
correctly *not* reflected).

**Exploit:** combined with prod `SameSite=None` cookies, any content the victim
runs on `http://localhost:<port>` (a local dev server, an Electron app, a
malicious npm package's localhost listener) is a permitted credentialed origin and
can read every GET response — `/me`, `/me/export`, `/me/profile`. Writes still need
the CSRF header. **Fix:** gate the two localhost regexes on `not is_production`.

*Sub-finding (LOW, not browser-reachable):* flask-cors 6.0.5 matches origin regexes
with `re.match` (unanchored — `try_match_pattern`,
`site-packages/flask_cors/core.py:410-425`), so `http://localhost:3000.evil.com`
*matches the pattern*; verified in the installed lib. It is not exploitable because
a browser cannot emit that as an Origin (invalid port), and the **literal** origins
(`https://solverah.com`, …) are kept as exact-match strings (verified — no
subdomain-suffix bypass). Still, anchor the regexes with `$`.

**Note:** `vercel.json`'s SPA header story was not reachable for full review before
this report; it is called out in ARCHITECTURE as separate from the API CSP and
should be spot-checked in a later round (the API-side CSP above governs only
API-served responses).

---

## 8. Secrets hygiene

**Repo history is clean of committed secrets (negative result).** No env/pem/key
file is tracked except `causal_graph/_scratch_key_transfer.env`, which is and was
always **empty** (0 bytes at its only commit `e980d62`; verified) — but its name is
not caught by `.gitignore`'s `.env*` glob (that glob matches names *starting* with
`.env`; this one ends with it), so a future `echo $KEY > _scratch_key_transfer.env`
would be committable. INFO. A working-tree scan and history pickaxe for
`sk-proj-`/`AKIA`/`re_…`/`xoxb-`/`ghp_` patterns returned nothing;
`send_test.py` and the tracked `scoring_fix_*_prompt.txt` hold no keys.
`.env.example` is untracked (the `.env*` glob swallows it despite the
`!.env.example` negation — consistent with the known issue), and `llm_debug.txt`
/`scoring_debug.txt` are untracked local artifacts.

**Logging is well-designed for PII (negative result).** `observability/logging.py`
provides a recursive `redact()` (`:107-137`) keyed on sensitive substrings
(`password, secret, token, authorization, cookie, api_key, email, phone,
resume_text, ssn`) applied to all structured `extra` fields; the access line logs
`method, path, route, status, duration, remote_addr` — **path only, never the query
string** (`:298-308`), so no token rides a logged URL; inbound `X-Request-Id` is
length/charset-validated before it is adopted and stored (`:326-332`). The only
call sites that interpolate into the *message* string log an integer `user_id`, not
an email (`auth.py:128`, `intelligence_service.py:292,311`). Third-party loggers
are pinned to WARNING.

- **8.1 — INFO** — tracked empty `_scratch_key_transfer.env` outside the `.env*`
  ignore (above). **Fix:** delete it and add `*_scratch_key_transfer.env` (or
  `*.env`) to `.gitignore`.
- **8.2 — INFO** — LLM debug files (`llm_debug.txt`, `scoring_debug.txt`) are
  written to the working tree by `backend/services/path_scoring.py` and embed
  scored-user context; overwritten per run, untracked, but present locally. Ensure
  they are absent from production images and gated behind a debug flag.

---

## 9. Rate-limit coverage map

Key function `get_remote_address` for everything except the one global-key guest
bucket (`extensions.py:46`, `intake.py:330`); defaults `["200 per day", "50 per
hour"]` (`security.py:33`); storage `RATELIMIT_STORAGE_URI` > `REDIS_URL` >
`memory://` (`security.py:52-69`). ProxyFix trusts `TRUSTED_PROXY_COUNT` hops
(prod default 1, dev 0), boot-fatal if non-integer, `x_host=0`
(`factory.py:139-192`). **[probed]** XFF spoofing does **not** bypass the limit in
dev (three forged `X-Forwarded-For` values still hit the same `429`), confirming
the dev topology ignores the header — residual risk is operational (adding a CDN
layer without incrementing the count).

### 9.1 — HIGH (conditional) — `memory://` storage permitted in production

`security.py:125-136` and `config.py:240-247`: `memory://` in production emits only
a `logger.warning`, not a `ConfigError`. With N gunicorn workers each keeps its own
counters, so **every limit in this report is N× looser and every deploy resets all
budgets** — the auth brute-force bounds (2.2, 1.2) and the guest/`wpll` ceilings
(3.1) become "decorative rather than protective" (the module's own words,
`security.py:13-15`). **Fix:** make `memory://` + production fatal, consistent with
the c4d6041 "invalid config is fatal" policy.

### 9.2 — MED (conditional) — Missing `redis` driver silently downgrades to `memory://`

`security.py:108-123`: if the URI starts `redis` and the driver is absent, it logs
an error and serves on `memory://`. A packaging regression turns an operator's
explicit Redis config into per-worker limits with only one log line. **Fix:** fail
boot in production instead of degrading.

### 9.3 — MED — `override_defaults=True` dropped the 200/day backstop on decorated routes

`@limiter.limit`/`shared_limit` default to `override_defaults=True`. The codebase
restated day caps only on `POLL_LIMIT` and `wpll` (`assessments.py:77-93`); every
other decorated route lost the daily backstop and rides its per-minute limit alone:
`auth.py:145` register / `:179` login (`5/min` = 7,200/day/IP — 36× the intended
200), `intelligence.py:283` quiz-insights (`10/min` = 14,400 paid calls/day),
`:356` agent (`30/min`), `:405` path-suggestion-jobs (`10/min` — the most expensive
op in the system), and the intake routes. **Fix:** append a daily term to each
limit string, or pass `override_defaults=False`.

### 9.4 — MED — `POST /me/resumes/<id>/parse-jobs` has no explicit limit

`me.py:483-485`: `@jwt_required()` only, no `@limiter` (verified) — rides the
global default. Each job is an R2 download + pdfminer/python-docx parse; its *poll*
got the A19 poll-limit fix but the *enqueue* — the door to the actual work — did
not. Pairs with 5.1/5.2 for a queue-DoS. **Fix:** `@limiter.limit("10 per minute;100
per day")`.

### 9.5 — LOW — `GET /me/matches` scan on the cheapest verb

`companies.py:96-102`: the route's own doc calls it "*an O(all-companies) in-process
scan that can commit a backfill on the read path (P0-2)*", no limiter decorator.
50/hour/IP per account of full-table scoring scans. **Fix:** a modest explicit limit
until the Phase 2 rework.

### 9.6 — LOW/INFO — `/intake/early-access` (unauth email gen on defaults only,
`intake.py:155`); `/readyz` limiter-exempt with a `SELECT 1` per hit
(`factory.py:363`, `health.py:131-135`). Both low-impact.

### 9.7 — NEGATIVE — The shared-scope discipline is correct: `shared_limit(scope=...)`
(not `limit(scope=...)`) joins each instrument's sync-submit and enqueue doors into
one budget (`assessments.py:300,430`), so they cannot be alternated for 2× allowance;
the test-client exemption is gated on `TESTING` and itself tested
(`security.py:173-207`); OPTIONS preflights are exempt (correct). One doc inaccuracy:
comments at `factory.py:360` describe `default_limits` as one shared cross-route
budget, but Flask-Limiter applies them per-endpoint — so the default-only anonymous
surface is 200/day/IP *per route*, not in total.

---

## 10. D-01 re-verification (employer isolation)

**No current violation — the boundary holds everywhere it is enforced.** There is
no employer principal yet (`auth_service.py:113` hard-codes job-seeker; intake and
`PATCH /me` refuse other roles), so "employer calls X, sees candidate Y" is
unconstructible today. Every route keys strictly off the JWT identity; no route
takes a user-id path parameter; job-status lookups scope `user_id` in the query
(`scoring_jobs.find_for_user:406-411`, `resume_jobs.find_for_user:221`), so
cross-user job reads are impossible by construction; `core` scores never enter the
job path (`JOB_ELIGIBLE_KINDS`, `scoring_jobs.py:109`); provider exceptions carrying
prompt fragments are replaced by `GENERIC_FAILURE`.

The real exposure is the **shape of the guard**, which matters the day employers
arrive:

### 10.1 — LOW — The guard enforces table-reachability, not leak-reachability

`tests/test_employer_visibility.py:137-154` is a static AST walk that fails any
file (outside a 6-entry allowlist) referencing one of four names
(`PersonDimensionScore`, `AssessmentResponse`, and their table strings). It
auto-discovers new *files* but only for those four names. The **sanctioned doorway**
`assessment_store.py` exports `get_dimension_scores` (`:200`) and
`export_person_side` (`:253`) — which return the full D-01-sensitive object — and
any module may import *those* freely; the constraint on callers is prose only
(`:207`). A new `GET /companies/{id}/candidates` that does `from assessment_store
import get_dimension_scores` and serializes the six scores would pass **every guard
test green**. **Fix:** add a companion allowlist test over importers of those two
functions, and a response-side D-01 test the day the first employer route lands.

### 10.2 — LOW — Four instruments' raw answers sit outside the enforced doorway

D-01's text says "assessment answers", but the enforced boundary (guard + the
`kind <> 'core'` check constraint) covers only `core`. Raw answers for `work_pulse`,
`wpll`, `focus_type`, `manager_match` live in `assessment_submissions.answers`
(`model.py:497-504`), imported plainly by `assessment_repository.py:37`. A documented
interim (until partitioning item 5), but any employer-facing work must treat those
as D-01 material meanwhile.

### 10.3 — INFO — Latent points to record before employers/analytics arrive

The agent context is D-01-clean *by construction, not by a filter* — quiz results
are stubbed `"[Not yet available]"` (`agent_service.py:96-97`); if that TODO is
filled via `get_dimension_scores`, the six scores enter a user-extractable prompt
and the guard stays green (feed narratives/archetypes, never raw scores). No
endpoint aggregates over respondents today, so there is no small-n
de-anonymization surface — **and also no minimum-n threshold mechanism anywhere**
for when company analytics arrive. The guard's `SKIP_DIRS` excludes `Scripts/`
(real Python), and anonymous-job handles are uuidv7 (see 3.3).

---

## 11. INFO roll-up

Dead JWT knob `jwt_access_token_minutes` (1.5); tracked empty
`_scratch_key_transfer.env` outside the ignore glob (8.1); local LLM debug files
(8.2); uuidv7 capability handles weaker than uuid4 (3.3); D-01 guard blind spots
and missing small-n threshold (10.1–10.3); `readyz`/`early-access` low-impact
rate-limit gaps (9.6); company-id enumeration is self-documented and pre-existing.

---

## Verification notes

- Booted at commit `07e3a80` against `solverah_sec` on `localhost:5433`
  (`citext`, `pg_trgm`, `vector`), CI-style env with `SOLVERAH_IGNORE_DOTENV=1`
  and no real keys in-process. Migrations applied cleanly through
  `20260901_scoring_jobs`.
- **[probed]** items reproduced live: user enumeration (forgot/resend/register
  bodies + statuses), the OTP verify `429` throttle, XFF non-bypass of the limiter,
  40 unthrottled `wpll` enqueues, anonymous-job isolation (cross-kind poll → 401),
  and the CORS localhost credential reflection.
- All other `file:line` citations were read directly. "Missing" claims
  (`user_sessions`, jti/blocklist, `task_time_limit`, magic-byte sniffing,
  `profile_data` in the tombstone, `resume_parse_jobs` in deletion) were checked by
  tree-wide grep, not a single directory.
