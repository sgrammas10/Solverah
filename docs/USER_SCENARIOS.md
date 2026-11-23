# User scenarios — the prod walkthrough

**What this is.** Every surface a real person can reach in Solverah, in the order a
person actually reaches them, with the exact thing each screen should say. It exists
to be *walked*, on production, by a human — not to be read. Each step has a stable
ID. When a step does not do what it says here, write the ID down; a fix chunk gets
opened against that ID and nothing else has to be re-explained.

**Who it's for.** Sebastian, walking prod. Secondarily the agents who pick up the
broken IDs afterwards — which is why every step carries the exact copy and the exact
error `code` rather than a description of them. (Showing the product to an investor
is a different job with a different document: `docs/INVESTOR_DEMO.md`.)

**Provenance.** Derived by reading the code, not by using the product. Every
expectation below is read out of source — which is exactly why walking it is worth
doing.

> ### Deploy state — read this first
>
> **Re-derived 2026-10-25** from `causal_bayesian_model` at `6e51713`, and checked
> step by step against **production = `origin/main` at `02707ab`** (PR #160, merged
> 2026-10-14).
>
> The branch is **15 commits ahead of prod**. Those commits carry the six-trait build:
> the tolerance and must-have step (`/trait-preferences`, S24), the env-v3 Environment
> Report (five optional outcome questions), the tolerance-aware Situation Report and
> its pin (D-15), real CompanyLens (research a company, trait reads), and export/delete
> for the new tables. **Every step that differs is marked "Branch only — not on prod
> until the next merge", and says what prod shows today.** Walk prod as the unmarked
> text plus each "On prod today" note; after the next merge, walk the branch-only steps.
>
> **Hard-refresh before you start** (`Ctrl+Shift+R`). A stale bundle is still the
> single most likely way to see a "failure" that isn't one.
>
> **Newest, never walked by anyone:** the whole landing page (S1, rebuilt 2026-09-28),
> the dashboard's real activity and recommendations (S7.7a–b), the summary-first
> Situation Report (S10), the past-job report (S25), the resume-or-start-over prompt
> on every instrument, the mobile menu (S7.9a), and — after the merge — S24 and the
> CompanyLens flow in S17. **S20.3 really deletes an account** — use a throwaway.

**Status.** Written 2026-09-14; revised 2026-09-15; **fully re-derived 2026-10-25**
(148 commits after the first version). S1–S21 were walked on prod on 2026-09-15
against the old build; that walk predates most of what is below.

---

## 0. How to walk this

### 0.1 · The ID scheme

- `S<n>.<step>` — a walkthrough step, e.g. `S8.4`. Stable. Do not renumber; if a step
  is inserted later it gets a letter (`S8.4a`). A step that no longer applies keeps
  its ID and reads **Retired YYYY-MM-DD** with the reason.
- `G<n>` — a **known gap**, already understood, listed in §1. If a step fails and the
  failure is a listed `G`, note it as `S8.4 → G7` and move on. Don't re-diagnose it.
  `G1`–`G22` are the 2026-09 set (most now closed); `G23` onward were found by reading
  source on 2026-10-25 and **none has been confirmed in a browser yet** — a step that
  contradicts one of them is a finding about the gap, not about you.

### 0.2 · What to record

For each failure, three lines is enough:

```
S10.6  — expected the "Negotiate it" tab, got nothing at all
         Chrome 141, desktop, ACC-1, 2026-10-26 10:22
```

The exact copy is in this document, so you don't need to transcribe what you saw
unless it differs in a way that matters (wrong words, not just wrong screen).

### 0.3 · Ordering

The scenarios are in dependency order and the numbering follows the product's
precondition spine:

```
Work Pulse (24)  →  wp_v2_completed  →  Environment Report (16; 21 on the branch)  →  Situation Report complete  →  Experiments
    └→ Trait preferences (S24, branch only): optional, shown once after each sitting; gates nothing,
         changes what S10 shows. Answer it BEFORE the Environment Report so S10 has something to show.
Situation Report complete  →  Past-job report (S25, one per account)
ManagerMatch (15)  →  Manager Profile (16)  →  Playbook
FocusType, Pulse   →  no preconditions, walk any time
```

**Set career status before the Environment Report.** On a fresh account with no
status and no "I currently work here" role, the Environment Report asks for it only
*after* the last question (S9.10a, `G53`).

S1–S7 are one sitting (roughly an hour). S8–S16 are the product proper and want a
second sitting of about two hours: the instruments are 24 + 16 + 15 + 16 questions and
you must answer them honestly for the reports to say anything real. S17–S25 are short.

### 0.4 · Accounts you need

Six, because career status changes the copy of an entire lane, most instruments
cannot be un-taken from the UI, and two steps destroy state for good.

| Account | Career status | Walks | Notes |
|---|---|---|---|
| **ACC-1** | employed ("I currently work here" on a role) | S7–S20, S24, S25 | the main lane; do the full spine on this one. Do **S25 last** — filing a past-job report removes both entry points for good |
| **ACC-2** | — | S4, S5 | created *through* the guest-quiz replay, to prove the replay |
| **ACC-3** | `first_job` | S21 | never-employed lane; Situation Report deliberately refuses to assemble. Also carries S16.1 and S16.10, which need a pre-Work-Pulse / pre-status account |
| **ACC-4** | `between_jobs` | S22, S22.1a | past-tense lane; every Environment Report prompt has a past twin |
| **ACC-5** | unconfirmed | S5.8, S6 | register, then never verify |
| **ACC-6** | any | S20.3 | throwaway: **S20.3 deletes it** |

**Freeing an address for reuse.** Account deletion tombstones the row and rewrites
the email to `deleted-{id}@tombstone.invalid`, which frees the original address for
re-registration. The UI is `/settings` → "Delete my account" → type `DELETE` (S20.3).
Simpler for a walkthrough: use distinct addresses per account.

**Re-walking the guest quiz (S4)** needs `localStorage` keys `guestQuizCompletedAt`
and `pendingQuizSave` removed, or a fresh browser profile. The lockout survives logout
on purpose.

### 0.5 · Things that will look broken but are not

Read this list before you start or you will file bugs that aren't.

1. **Work Pulse has no results page.** Finishing the 24 questions swaps the page in
   place to a completion card and navigates nowhere. Deliberate: returning dimension
   scores hands a retaker a gradient to optimise against. A retake (S8.8a) ends on the
   same card. *(Branch: Finish first shows the optional tolerance step, S24, then the
   card.)*
1a. **A retake does not move your Situation Report.** The report stays on the sitting
   it was built from until you press its Re-read button (S11). "Describe it again" (a
   new Environment Report) does not move the pin either.
2. **Every instrument asks before resuming.** Reload part-way through Work Pulse, the
   Environment Report, the past-job form, ManagerMatch, Manager Profile or FocusType and
   you get "You have answers saved from last time" with "Pick up where you left off" /
   "Start over". Pick up = the first unanswered question (FocusType: the first
   unfinished scene). *(Replaces the old "restarts at question 1" item, false since
   2026-09-28.)*
3. **Every draft lives in `sessionStorage`, never on the server.** Close the tab, or
   sign out, and an unfinished instrument is gone. A silent session expiry keeps them.
   The Pulse check-in and the tolerance step have no draft at all.
4. **`recalibrated: false` is a success.** "Already reading your most recent Work
   Pulse sitting — nothing moved." means the pin was already current. *(Branch: also
   expected after a tolerance change, which waits for a new Work Pulse sitting.)*
5. **No numbers in the Situation Report diagnosis.** Three bucket words and one
   direction phrase per row, never a score, bar or percentage. Dates and check-in
   counts in the experiment control are fine; a digit in a row's name, bucket,
   direction or takeaway is the bug.
5a. **The Situation Report opens collapsed.** Six one-line rows; the guidance is
   behind each row (or "Open all"). Experiments live inside a row's "Try a change" tab.
6. **The Situation Report dashboard card renders nothing while loading and nothing on
   error**, and the Intelligence hub shows no Situation card at all for a `first_job`
   account. A card that cannot say anything true says nothing.
7. **`/assessment` is a pure redirect** to `/work-pulse`; `/work-pulse/results`
   redirects too for anyone who never took the retired 12-question quiz.
8. **Once Work Pulse is complete you reach `/work-pulse` by typing it.** Retake lives
   only on that page (`G46`).
9. **A past-job report changes nothing on the Situation Report**, by design. It ends
   on a thank-you card.
10. **The header's "Feed" opens a "Feature coming soon" modal** rather than navigating;
   `/feed` exists only by URL. The "Pro · coming soon" pill on Path Intelligence sits
   beside a working button — decorative, kept by the 2026-09-28 ruling.
11. **The dashboard's Work Pulse banner comes back after a reload**, and the profile
   autofill dialog reopens on every dashboard visit while the profile is under 50%
   complete. Both are local state.
12. **Recommendations may show fewer than three cards, or "You're up to date."** —
   steps already offered by the cards above are dropped.
13. **"Resend code" stays disabled after one click** on both code screens. No timer;
   reload to try again.
14. **The landing hero "doesn't scroll" for several screens** — it is a pinned scroll
   story changing step. Its example cards ("The Autonomist") are invented and labelled
   so.
15. **`/landing`, `/nope`, `/trait-preferences` (on prod) and `/quiz-preview/<unknown>`
   all quietly become `/`.** There is no 404 page.
16. **The header is hidden when printing.**
17. **A Pulse confirmation has no "check in again" button**, and a logged change does
   not draw on the line until there are two check-ins.
18. **Until the next merge, prod's hub, `/trust` and `/company-lens` all say CompanyLens
   is coming soon.** Consistent, not stale.

### 0.6 · Environment preconditions

These are not UI. Check them before blaming a screen. Rows marked **branch** only matter
once `causal_bayesian_model` is merged. Nothing here claims what the Render dashboard
holds: every "exists?" is **confirm in the dashboard**.

| Thing | Needs | If missing |
|---|---|---|
| Walking prod at all | a hard refresh (`Ctrl+Shift+R`) before you start | A stale bundle makes shipped fixes look absent. |
| Any verification / sign-in code email | `RESEND_API_KEY` in the API env (`EMAIL_FROM` defaults to `no-reply@solverah.com`) | Registration still returns 201 and sends you to `/verify-email`; the code never arrives and **nothing surfaces to the user**. The only trace is the boot log's `providers.resend: false` and an outbox row that retries and then parks (S23.6). |
| A code whose first send failed | the `solverah-outbox-sweep` cron (`flask outbox sweep`, `*/5 * * * *`) — **confirm in the dashboard** | The inline attempt is the only attempt. With the cron, retries land at roughly 5m, 15m, 45m, 2h… of row age; after 8 attempts the row parks. Codes expire at **15 minutes**, so only the first retry or two help the user. |
| Pulse prompt emails | a cron running `flask pulse send-prompts`, and `APP_BASE_URL` (default `https://solverah.com`) | No prompt email ever sends, silently. **Still not in `render.yaml`** — `G18`. Step 4 of the post-deploy list in `docs/RUNBOOK_DEPLOY_MAIN_MERGE.md`; **confirm in the dashboard**. |
| `render.yaml` | — | **Still doc-only**, by its own header: "THIS FILE GOVERNS NOTHING TODAY". Do not read it as proof of what runs. |
| Rate limiting | `REDIS_URL` (or `RATELIMIT_STORAGE_URI`) | `memory://` is FATAL at boot in production, so the failure is "API will not start", not a silent one. |
| Cookies across `solverah.com` ↔ `api.solverah.com` | `JWT_COOKIE_SECURE` true, `JWT_COOKIE_SAMESITE` set, `JWT_SECRET_KEY` ≥ 32 chars | API refuses to boot in production if missing. A wrong SAMESITE looks like "sign-in works, then the next request is 401" (S6.8/S6.9). |
| Any assessment route | `SOLVERAH_FORM_TOKEN_SECRET` | No default by design (D-05): every assessment route 500s while boot stays green. |
| Guest quiz insight (S4.4), WPLL teaser (S2.4) | `OPENAI_API_KEY` (`OPENAI_QUIZ_MODEL`, default `gpt-4o-mini`) | The modal / teaser shows its "We couldn't generate your insight right now." card; no guest lockout is written. |
| ManagerMatch results (S14.3) | `OPENAI_API_KEY` (`OPENAI_WP_MODEL`, default `gpt-4o-mini`) | "We couldn't generate your results right now." with the generic retry. |
| Resume upload (S3.4), account-deletion file removal (S20.3) | `S3_ENDPOINT_URL`, `S3_BUCKET_NAME`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | `POST /intake/resume-tickets` fails ("Unable to start upload."); a failed object delete during deletion is surfaced, not hidden. |
| Agent chat (S18) | `GROQ_API_KEY`; model `openai/gpt-oss-20b` unless `SOLVERAH_AGENT_MODEL` overrides | Missing/invalid key: "Something went wrong generating a reply. Please try again." (500). Retired model: "The assistant is unavailable right now. Please try again in a few minutes." (503). The old "Failed to generate response" text no longer exists. |
| Path suggestions (S16.9–S16.12) | `SOLVERAH_CORPUS_S3_KEY` + the S3 credentials (corpus published to `solverah-intake/corpus/onet_corpus_20260916.npy` on 2026-09-28); `OPENAI_API_KEY` for embeddings and the narrator | No corpus: every job fails `corpus_unavailable` → "We couldn't load your path suggestions right now." No OpenAI: cards get fallback sentences. **That the key is set on the Render web service is unverified from source.** |
| Path sidecars (`.tasks`, `.experience`, `.fit`, `.summaries`) | published beside the corpus | Silent degradation: no task half of the wants panel, slow deep fits (live O*NET via `ONET_API_KEY`), no summary line. |
| Daily retention sweep of intakes, audit PII, orphan R2 objects | the `solverah-retention` dashboard command to be `flask retention run && flask retention cleanup` **and** the `S3_*` variables added to that cron by hand | With the old command the cleanup never runs, and the Privacy Policy's "deleted after 90 days" (S1.8) is untrue in practice. See S23.5. |
| **Branch** — CompanyLens research (S17.6a–h) | `ANTHROPIC_API_KEY` **and** `OPENAI_API_KEY` **and** `SOLVERAH_COMPANYLENS_RESEARCH_ENABLED` truthy (default **off** until the attorney gate opens) | 503 → "Company research isn't available right now. Please try again a little later." Prefill while off: `flask companies research --allow-when-disabled "Name"`. With nothing prefilled, CompanyLens shows "No companies yet" (`G62`). |
| **Branch** — pasted job postings (S17.7) | `OPENAI_API_KEY` (not behind the switch) | "Reading postings isn't available right now. Please try again a little later." |
| **Branch** — stuck research runs | the `solverah-companies-sweep` cron (`flask companies sweep`, `*/10 * * * *`), **not yet created in Render**; needs both API keys | A run orphaned by a deploy or crash stays `queued`/`running` forever and "Research on this company is under way…" never clears. |
| **Branch** — ranking weights | `SOLVERAH_MODEL_WEIGHTS_SOURCE` **unset** (reads `priors.yaml`) | Set to `run` with no `model_run` row: no fallback. |

---

## 1. Known gaps — expected failures

Already understood. Do not file these; reference them. Re-verified against source on
2026-10-25.

### 1.1 · The 2026-09 set (G1–G22)

Most are closed. A closed gap keeps its row so an old note like `S8.4 → G7` still
resolves.

| ID | Status | Gap | Where |
|---|---|---|---|
| **G1** | CLOSED 2026-09-14 | No account-settings screen. `/settings` ships export and deletion. | S20 |
| **G2** | CLOSED 2026-09-28 (`835cfbf`) | No mobile menu. Below 768px the header is now the logo plus a menu button ("Open menu" / "Close menu"); Settings and "Log out" are inside. A possible overflow at 768–860px is `G38`. | S7.9 |
| **G3** | **OPEN by decision** (2026-09-28 ruling) | The header's Feed item opens a full-screen modal: "Feature coming soon" / "We're still building the feed. It'll show up here when it's ready." / "Got it". `/feed` is an honest coming-soon page reachable only by URL. | S7.10, S17.5 |
| **G4** | **OPEN on prod; closes at the next merge** | CompanyLens is coming-soon on prod: the hub card is faded with no button, `/company-lens` says "CompanyLens™ is coming soon". Real on the branch (S17.6a–h) — see `G62` for merge-day. | S16.6, S17.6 |
| **G5** | CLOSED 2026-09-14 | Experiments loading/error states. Re-verified. | S12.8 |
| **G6** | CLOSED 2026-09-14 | Environment Report gate failure. Re-verified. | S9.11 |
| **G7** | CLOSED 2026-09-14 | Work Pulse load-failure retry. Re-verified; no in-flight feedback on retry is `G47`. | S8.10 |
| **G8** | CLOSED 2026-10-02 (`368c768`) | Raw `invalid code` / `code expired` on verify-email. Now "That code didn't match. Check the six digits and try again, or request a new code below." / "That code has expired. Request a new one below and we'll send it right away." Raw 429 text is the remaining member of this family: `G33`. | S5.5 |
| **G9** | CLOSED in code 2026-09-16 (`deb4104`); **not re-walked live** | Hero-intake accounts got an unenterable hex token. Now a 6-digit code and a "Verify my email" button to `/verify-email`. Password-rule mismatch left behind: `G30`. | S3.6 |
| **G10** | CLOSED 2026-09-28 (`cea54d6`) | Dead `EarlyAccessModal`. Deleted; orphan endpoint is `G31`. | S3.7 |
| **G11** | CLOSED 2026-09-28 (`eeba7b7`) | Stale `/landing` with "For Recruiters". The route is gone. | S1.10 |
| **G12** | CLOSED 2026-09-28 (`140d66b`) | `?tab=` unvalidated. Unknown tabs now fall back to Personal. | S19.3 |
| **G13** | CLOSED 2026-09-14 | Career-status modal failure silent. | S19.9 |
| **G14** | CLOSED 2026-09-14 | Failed `/me/dashboard` rendered anyway. | S7.7 |
| **G15** | SUPERSEDED 2026-09-28 (`835cfbf`) | `/search` error state. `/search` makes no request now; it is a coming-soon page. | S17.3 |
| **G16** | CLOSED 2026-10-02 (`bf4b785`) | Quiz group mismatch. Both branches save under `careerQuizzes`. | S4.9 |
| **G17** | **OPEN**, low | Wrong-role redirect is unexplained (`Navigate to="/"`, no state, no copy). `job-seeker` is still the only role. | S6 |
| **G18** | **OPEN** | `flask pulse send-prompts` is not in `render.yaml`. Whether the dashboard cron exists: **confirm in the dashboard**. Without it no Pulse email ever sends and the cadence system is inert. | S23.4 |
| **G19** | CLOSED 2026-10-02 (`bf4b785`) | Guest dead end on unknown quiz key. The not-found screen now points guests at `/quiz-preview` — but it is unreachable by URL, since `/quiz-preview/<unknown>` hits the catch-all. | S4.10 |
| **G20** | CLOSED 2026-10-02 (`bf4b785`) — **behaviour changed** | Guest insight was router-state only. It is now kept in `pendingQuizSave`, so a new tab **shows** the insight. | S4.6 |
| **G21** | CLOSED 2026-09-14 | Monthly cadence one-way door. Re-verified. | S13.11, S13.13 |
| **G22** | CLOSED 2026-09-28 (`140d66b`) | Guest-quiz replay landed on a stale cache. `Login.tsx` now invalidates the profile query before redirecting; no reload needed. | S4.8 |

### 1.2 · Found reading source, 2026-10-25 (G23–G68)

**None of these has been confirmed in a browser.** Each was found by reading source at
`6e51713` and carries its evidence in the step it is cited from. "Prod" means it is on
`origin/main` today; "branch" means it arrives with the next merge. Severity is the
finder's estimate.

| ID | Where | Gap | Severity |
|---|---|---|---|
| **G23** | S1.2, S1.5, S2.6 | **The landing page and the account gate describe a Work Pulse that no longer exists**: "Answer twelve questions.", "12 questions · free · account required", "A full narrative insight, your primary work archetype…", "Your full 12-question Work Pulse assessment". The shipping instrument is 24 questions with deliberately no results screen. Factual claims, not tone — take the facts to Julie. Prod. | High (first thing a visitor reads) |
| **G24** | S2 | **FIXED on the branch 2026-11-23 (ruling: delete), not yet walked.** `/start`, its components and Login.tsx's `solverah_intake` replay removed; `/start` now falls through to `/`. **`/start` is an unlinked, half-retired route.** Nothing links to it, yet it still mounts the 5-question WPLL, calls an LLM endpoint anonymously, and `Login.tsx` still claims `solverah_intake`. Delete it or link it again. Prod. | Medium |
| **G25** | S2.1a | **FIXED on the branch 2026-11-23, not yet walked.** `LandingNav` deleted with `/start` (it rendered nowhere else). `LandingNav` on `/start` has four dead links (`#features`, `#about`, `#faq`, and "Get Started" → `/start` itself). Prod. | Low |
| **G26** | S3.2–S3.3a | **FIXED on the branch 2026-11-23, not yet walked.** **Browser validation pre-empts the intake form's own messages**, and the hidden `required` file input can swallow a submit with no message at all; the `type=url` fields reject the form's own placeholder text. Confirm in Chrome. Prod. | Medium |
| **G27** | S1.2, S1.4a, S1.6 | **DEFERRED (ruling 2026-11-23):** the person-review step will be added later; claim left as is. **"Checked by a person" / "Every reading is reviewed by someone before it reaches you."** No code path has a person review a reading before the user sees it. A decision for Sebastian and Julie, not a copy tweak. Prod. | High (an unmet promise on the first page) |
| **G28** | S4.7 | The guest-quiz lockout is cosmetic: the quiz URLs never check it. Prod. | Low |
| **G29** | S3.5a | **FIXED on the branch 2026-11-23, not yet walked.** The hero modal's "Sign in" opens a server session the app doesn't notice; the page still looks signed out until a reload. Its 403 offers no resend link. Prod. | Low–medium |
| **G30** | S3.6 | **FIXED on the branch 2026-11-23, not yet walked.** Account-modal password check says "at least 8 characters"; the server requires 12 plus character classes. Prod. | Low |
| **G31** | S3.7 | **FIXED on the branch 2026-11-23, not yet walked.** `POST /intake/early-access` is still live with no UI caller and no visible rate limit. Ops tidy-up. Prod. | Low |
| **G32** | S1.9 | `/how-matching-works` describes company matching as live. Prod. | Low–medium |
| **G33** | S5.3a, S5.5, S6.6, S18.7 | **FIXED on the branch 2026-11-23, not yet walked.** **Rate-limit 429s show Flask-Limiter's raw description** ("3 per 1 minute", "5 per 1 minute", "30 per 1 minute") on register, verify, forgot-password and the agent. `/login` hides it behind the generic line; Path Intelligence and CompanyLens branch on 429 and escape it. One-place fix. Prod. | Medium |
| **G34** | S6.4a | **FIXED on the branch 2026-11-23, not yet walked.** "Resend code" on `/forgot-password/verify` ignores `res.ok`, so a 429 still says "New code sent! Check your inbox.". Prod. | Low–medium |
| **G35** | S5.5a | **FIXED on the branch 2026-11-23, not yet walked.** `/verify-email` opened without router state (a new tab) shows "your email" and a misleading error. Prod. | Low |
| **G36** | S20.3 | **RULING PENDING (2026-11-23):** Sebastian ruled the copy should say we keep anonymous company data, but it is not anonymous yet: audit rows keep the real email (`intake_link_account` metadata) and IP/UA for 365 days against the same tombstone id. Waiting on: scrub audit rows on deletion? exact dates or month? **Branch — decision before merge:** account deletion keeps company links (they name the user's employer and dates) under the tombstone; the settings copy does not say so. | Medium (trust copy) |
| **G37** | S6.1 | **FIXED on the branch 2026-11-23, not yet walked.** "Forgot your password?" leads to a page titled "Sign in with a code" (passwordless; there is no reset). Copy. Prod. | Low |
| **G38** | S7.9c | Possible desktop-nav overflow at 768–860px with a long name. Arithmetic only — walk before filing. Prod. | Low |
| **G39** | S16.2a | **FIXED on the branch 2026-11-23, not yet walked.** The hub step strip lists the retired "Work Pulse Lite" and never ticks CompanyLens or Future Path. Prod. | Low |
| **G40** | S16.7a | **FIXED on the branch 2026-11-23, not yet walked.** The hub quizzes strip says "…help you stand out to employers", contradicting `/trust`. Copy. Prod. | Low |
| **G41** | S7.2 | **FIXED on the branch 2026-11-23, not yet walked.** "Maybe later" snoozes the prompt 7 days per user (`solverah.intakePromptSnoozedUntil:<id>`, survives logout). `IntakePromptModal` reopens on every dashboard visit while the profile is under 50%; "Maybe later" does not persist. Decide if intended. Prod. | Low |
| **G42** | S16.14, S19.6a | **FIXED on the branch 2026-11-23, not yet walked.** Two `alert()` calls survive on the profile page (resume upload and View Resume failures). Prod. | Medium (polish) |
| **G43** | S19.7 | **FIXED on the branch 2026-11-23, not yet walked.** The career-status modal says "We need this to generate your path suggestions." even when you arrive from the dashboard or the Environment Report. Prod. | Low |
| **G44** | S19.11 | Possible profile tab-strip overflow at 390px. Arithmetic only. Prod. | Low |
| **G45** | S24 | **Branch:** trait preferences has no hub or dashboard entry. | Info |
| **G46** | S8.8, S24 | **FIXED on the branch 2026-11-23, not yet walked.** **Once Work Pulse is complete, nothing links to `/work-pulse`**, so "Retake Work Pulse" (and, on the branch, the card's way into `/trait-preferences`) is reachable only by typing the URL. The retake shipped with no entry point. Prod. | Medium |
| **G47** | S8.10 | **NOT A BUG (2026-11-23):** React Query resets a no-data query to pending on refetch, so the page already shows "Loading..." during Try again; pinned by useAssessment.test.tsx. Walk to confirm, then close. Work Pulse's "Try again" shows no sign of activity while it retries; `WorkPulseResultsPage` already handles this. Prod. | Low |
| **G48** | S24.6, S24.8 | **FIXED on the branch 2026-11-23, not yet walked.** **Branch:** saving tolerance gives no confirmation, and on `/trait-preferences` Save and Cancel land on the same screen. | Low |
| **G49** | S24.8, S24.11 | **FIXED on the branch 2026-11-23, not yet walked.** **Branch:** the note "picks them up the next time you re-read it against a new Work Pulse" is wrong for a first answer, which applies straight away (tested). | Low |
| **G50** | S24.12 | **LEFT OPEN (ruling 2026-11-23).** **Branch:** `/trait-preferences` has no Work Pulse precondition on client or server. Needs a ruling. | Low |
| **G51** | S12.5 | **FIXED on the branch 2026-11-23, not yet walked.** A failed experiment abandon is silent. Prod. | Low |
| **G52** | S22.3, S22.6a | **The forward-facing (between_jobs) report carries present-tense copy**: every row headline, the "What staying costs" tab, and "Profile your manager" for a job the user has left. The form itself is clean. Content is Julie's; a `needs_forward` headline per cell is the structural fix. Prod. | Medium |
| **G53** | S9.10a | **FIXED on the branch 2026-11-23, not yet walked.** **Career status is asked for only after the last Environment Report question**, by a modal subtitled for path suggestions whose return dialog names the wrong page. The first trap a new user hits. Prod. | Medium |
| **G54** | S11.6 | **FIXED on the branch 2026-11-23, not yet walked.** **Branch:** the tolerance pin is invisible — after a tolerance change, Re-read says "nothing moved" with no hint that it waits for the next Work Pulse sitting. | Low–medium |
| **G55** | S9 | **FIXED on the branch 2026-11-23, not yet walked.** **Branch:** the hub card and Work Pulse card still say "16 questions" while the branch form has 21 steps (16 required). | Low |
| **G56** | S14.4 | **"The Operator" is the ManagerMatch catch-all archetype**: about 77% of answer patterns get it, including strongly autonomous respondents. Needs Julie's archetype rules, a `SCORING_KEY` bump and a backfill. Prod. | High (content) |
| **G57** | S13.6 | **FIXED on the branch 2026-11-23, not yet walked.** The Pulse confirmation says "This week vs. last week" whatever the real gap. Prod. | Low |
| **G58** | S14.3a | **FIXED on the branch 2026-11-23, not yet walked.** Reloading during ManagerMatch scoring enqueues a second job (two OpenAI calls; the later wins). Prod. | Low |
| **G59** | S14.7 | **FIXED on the branch 2026-11-23, not yet walked.** `mp_answers` is not per-user (unlike `mm_answers:{userId}`); after a silent session expiry a complete draft auto-submits as the next user on that tab. Prod. | Medium–low |
| **G60** | S13.7a | Logged changes don't annotate the trend line at one check-in. Probably intended. Prod. | Info |
| **G61** | S18.5 | **The agent doesn't know the product.** Its context carries the user's data and a list of legacy company rows, but no description of Work Pulse, the Situation Report, the Decoder or Path Intelligence, so answers about them are invented. Prod. | Medium |
| **G62** | S17.6a | **Branch, merge-day:** after the merge the hub, `/trust` and the Work Pulse teaser all say CompanyLens is live, but the page shows "No companies yet" and research answers "isn't available right now" because the switch defaults off. Prefill a starter set or hold the copy. | Medium |
| **G63** | S16.12c | "Skip for now" on "Edit skill ratings" re-scores the list and nags a user whose ratings are confirmed. Prod. | Low |
| **G64** | S16.12c | "Adjust search preferences" has no way out short of finishing all three questions. Prod. | Low |
| **G65** | S16.10a | The skills gate's way back is wrong ("Status saved." after adding skills) or missing (`between_jobs`). Prod. | Low |
| **G66** | S17.6f | **FIXED on the branch 2026-11-23, not yet walked.** New `user_company_lookup` table (migration 20261123_user_company_lookup); `/me/matches` lists only the caller's lookups; export + deletion wired; contract A34. Note: `GET /companies` and `/companies/<id>` still serve every company to any signed-in user. **Branch:** "Your companies" is every company anyone has researched; a user can see what others looked up. Decision for Sebastian. | Low–medium |
| **G67** | S17.7 | Prod only: an account with a stored legacy `culture_preferences` key may still see "{n}% match". Existence unverified; the merge removes the path. | Low |
| **G68** | S17.7a | **FIXED on the branch 2026-11-23, not yet walked.** **Branch:** a permanent 404 on `/companies/{id}` offers a "Try again" that can never work. | Low |
| **G69** | S6.4a | **FIXED on the branch 2026-11-23, not yet walked.** `/forgot-password/verify` opened in a new tab (no router state) said "your email", resent to nobody and submitted an empty address. Now asks for the email, like `/verify-email` (G35). Found by auth-accounts while fixing G34. | Low |
| **G70** | S3.5a | **FIXED on the branch 2026-11-23, not yet walked.** Hero modal "Sign in" on an unconfirmed account: the 403 offered a resend, but after verifying and signing in the submission was never attached. The 403 now parks the claim against that account (`claim_pending:<id>`, password already checked) and `confirm_email` attaches it. Pre-fix submissions are not backfilled. | Medium |

---

## 2. The scenarios

---

### S1 · First contact, signed out

**Account** none · **Routes** `/`, `/privacy`, `/terms`, `/how-matching-works`, and the catch-all `*`. (`/landing` is gone — see S1.10.)
**Requires a clean browser profile** (no cookies, no localStorage). A browser that has ever held a session is held behind the skeleton while the session probe runs, and a signed-in one is sent to the dashboard — `RedirectIfAuthenticated` wraps `/`, `/login` and `/register`.
**Whole scenario verified identical on `origin/main` and `HEAD`** — nothing in S1–S4 is branch-only except the `/trait-preferences` route line in `App.tsx`, which is signed-in and walked in S24.

- **S1.1** — Open `https://solverah.com` in a clean browser profile.
  → The landing page. **No global header** and **no global footer** — `/` suppresses both and renders its own `LandingPageNav`. The nav reads "Solverah" (left), "How it reads" / "Work Pulse" / "FAQ" (centre, desktop only), "Sign in" and **"Get started"** (right). Below 768px the centre and right collapse behind a three-bar button labelled "Open menu" (becomes "Close menu"); the opened panel lists the same three anchors plus "Sign in" and a full-width "Get started". A first Tab press reveals a "Skip to main content" link.
- **S1.1a** *(new)* — Arrive on `/` having just deleted an account (this is the redirect S20.3 ends on; you cannot reach it by typing the URL).
  → A `role="status"` strip above the nav: "Your account has been deleted." and a "Dismiss" button. If the file removal failed it continues: "One or more uploaded files couldn't be removed from storage yet. Email info@solverah.com and we'll confirm once they're gone." The strip lives in router state only — a reload or a new tab never shows it.
- **S1.2** — Read the hero. It is a **scroll story**: the stage pins under the nav while you scroll, and the words, the three example cards and the background tone change at five steps. Dots on the right ("Story steps"; aria-labels "Start", "Work Pulse", "Situation Report", "Manager Decoder", "Checked by a person") jump to a step.
  → Step 1: H1 "See how you actually work." / "Short assessments turn into a reading you can use: how you work, what your job costs you, and how to work with your manager." / buttons **"Get started"** (→ `#intake`) and **"Preview a quiz"** (→ `/quiz-preview`).
  → Step 2: "Answer twelve questions." — **`G23`**: Work Pulse is 24 questions.
  → Step 3: "See what your job is costing you." Step 4: "Work with the manager you have." Step 5 (the dark scene): "Checked by a person. Kept from employers." / "Every reading is reviewed by someone before it reaches you. Your data is never sold, and never shown to an employer." with a three-item check list "Read by a person" / "Never sold" / "Never shown to employers" and the two buttons again — **`G27`**.
  → The three cards ("Work Pulse™ reading — The Autonomist", "Situation Report — Where your job fits you", "Manager playbook — Working with a hands-on manager") are invented examples; a note under them reads "Example results. Yours come from your own answers." Below 900px only one card shows at a time.
  → There is no "Request early access" button and no "AI-Native Career Platform" badge any more; the old hero is gone.
- **S1.3** — Click **"Preview a quiz"**. → `/quiz-preview` (walked in S4). Come back.
- **S1.4** — Click each nav anchor: How it reads, Work Pulse, FAQ.
  → Scrolls to `#how-it-reads`, `#work-pulse`, `#faq`. Sections in page order: scroll-story hero; "What a reading is made of." (`#how-it-reads`); "Six instruments, one profile." (`#ecosystem`); "Start with Work Pulse™." (`#work-pulse`); "Start your reading." (`#intake`); the three commitments; "Questions we get." (`#faq`); the closing section; the footer.
- **S1.4a** *(new)* — Read "What a reading is made of."
  → Three ledger rows: "Your answers are evidence, not conclusions." / "Read against conditions, not templates." / "Checked by a person before it reaches you." (the body of the third: "Every submission gets a human review. Automated analysis is where a reading starts. Someone's judgment is where it finishes." — **`G27`**), then two panes "What we read" and "What we won't do" (the latter ends "Sell your data, or show it to an employer.").
- **S1.4b** *(new)* — Scroll to the ecosystem section.
  → H2 "Six instruments, one profile." / "Each one adds to the same profile, so every new reading starts from what you've already told us." and a list of six: Work Pulse™ / FocusType / ManagerMatch™ / Situation Report / Manager Decoder / Path Intelligence, each with a one-line description. An animated hub-and-spoke diagram sits beside it; hovering a list row lights that spoke. `?eco=card|split|flow|off` swaps the layout (default `split`); the dev-only switcher in the corner is **not** in the production build.
- **S1.5** — Find the Work Pulse section ("Start with Work Pulse™." / "Twelve questions about how you actually work. Free, with an account, so your reading has somewhere to live.").
  → Three ledger rows. **"Work Pulse™"** ("12 questions · free · account required") → button **"Create an account"** → `/register`. **"Quiz previews"** ("No account · a few minutes") → button **"Preview a quiz"** → `/quiz-preview`. **"Work Pulse Pro™"** ("On the roadmap") → no button, the text "Not yet available". The description of the first row promises "A full narrative insight, your primary work archetype, and the emerging signals shaping how you experience work" — **`G23`**. "Work Pulse Lite" is no longer mentioned anywhere on this page, and the "Try it free" → `/start` link is gone — **`G24`**.
- **S1.5a** *(new)* — Read the three commitments (heading is screen-reader-only: "What Solverah will never do with your data").
  → "Never sold." / "Never shown to employers." / "Never a decision." — the second continues "No recruiter, hiring manager, or company sees your profile. That rule is enforced in the code, not just written in a policy."
- **S1.5b** *(new)* — Open each FAQ entry (native `<details>`).
  → Six: "What is Authentic Intelligence?" / "Is this the same as artificial intelligence?" / "What information does it use?" / "Does it make career or employment decisions?" / "Are the insights personalized?" / "Why focus on conditions instead of labels?"
- **S1.5c** *(new)* — Read the closing section.
  → "Your title is where the reading starts, not where it ends." with **"Get started"** (→ `#intake`) and **"Preview a quiz first"** (→ `/quiz-preview`).
- **S1.6** — Scroll to the footer.
  → Dark footer. Blurb: "Career readings built from conditions and context, checked by a person, and kept away from employers." Three columns: **"This page"** (How it reads / Work Pulse / FAQ), **"Account"** (Sign in / Create an account / Preview a quiz), **"Legal"** (Privacy policy / Terms / How matching works). "© {current year} Solverah. All rights reserved." and the O*NET 30.3 attribution paragraph. The old "Soft launch — broader access remains closed. Early cohort intake is open." blurb is gone (no "early access", "waitlist" or "soft launch" wording remains; a unit test guards it).
- **S1.7** — Open `/privacy`, then `/terms`.
  → Both render from constants in `src/shared/lib/legal.ts`, not a fetch, inside the global Header (signed-out: "Sign in" / "Get started" → `/register`) and the O*NET footer. Layout: "Back to Solverah"; H1 "Privacy Policy" / "Terms of Service"; "Last updated 28 September 2026"; a `role="note"` banner whose bold line is "Draft under legal review" and body "This document describes how Solverah works today. Its wording may be refined before the effective date is set."; a sticky "Contents" column on wide screens (a collapsible "Contents" box on narrow ones) listing every `##` section; and a "Related pages" strip at the bottom. Privacy has nine sections (What we collect … Contact); Terms has fourteen, numbered ("1. Who can use Solverah" … "14. Contact").
- **S1.8** — In the Privacy Policy, find "Your choices and rights".
  → "**Access and export.** Download a copy of your data from your account settings at any time." and "**Deletion.** Delete your account from account settings. This permanently removes your identity and personal information — account, profile, resume, and intake records…". Both are honoured by `/settings` (was `G1`; S20 tests it). Also read "How long we keep it": "incomplete intake submissions that are never attached to an account are deleted after 90 days" — that promise is only true if the retention-cleanup cron has been switched over (§0.6).
- **S1.9** — Open `/how-matching-works`.
  → H1 "How matching works" / "What Solverah measures, how a match is worked out, and who gets to see any of it."; **no eyebrow any more**; six sections: What Work Pulse measures / How matches are computed / What matches are not / Who sees your answers / Where AI is involved / Your data; "Related pages" → Privacy policy, Terms of service. The second section describes company culture matching as if live — **`G32`**.
- **S1.10** — **Retired 2026-09-28** — `/landing` no longer exists as a route (commit `eeba7b7` renamed the prelaunch page to `LandingPage` and dropped the second route; `5544978` deleted the old file). `/landing` now falls through to the catch-all and lands on `/`. `G11` closed with it. Opening `/landing` is still worth one second: expect "/", not a dark slate page.
- **S1.11** — Open a nonsense path, e.g. `/nope` (or `/landing`, or `/quiz-preview/not-a-real-quiz`).
  → `<Navigate to="/" replace />`: you land on the landing page, URL rewritten to `/`. There is no 404 page anywhere in the app. Signed in, `/` in turn redirects to `/job-seeker/dashboard`.


---

### S2 · The intake wizard

**Account** none · **Route** `/start` · Fully completable signed out. **Not linked from anywhere** — see S2.1 and `G24`.

State persists to `sessionStorage` key **`solverah_intake`** (statements picked, WPLL answers, the generated insight text, current step). The wizard's question position is *not* persisted.

- **S2.1** — Open `/start` **by typing the URL**.
  → **Changed 2026-09-28** (`5544978`/`eeba7b7`): the landing page no longer links here. The old "Request early access" and "Try it free" buttons were the only in-product entrances; `LandingNav`'s own "Get Started" is rendered only on `/start`. Reaching it from `/` by clicking is no longer possible (`G24`).
  → Four-step wizard, **global header suppressed**, shared `LandingNav` (the *older* nav — see S2.1a). Progress dots read "Your situation" / "Quick pulse" / "Your focus" / "Get started"; the global O*NET footer still renders.
- **S2.1a** *(new)* — Click each link in the `/start` nav: "How it works", "About", "FAQ", and "Get Started".
  → **All dead.** The nav points at `#features`, `#about` and `#faq`, and none of those ids exists on `/start` (the only `#faq` in the app is on `/`). "Sign In" → `/login` works. "Get Started" → `/start`, the page you are on. Same on the mobile menu (opens as "Open menu"; the three-bar button). `G25`.
- **S2.2** — Step 1.
  → H1 "What's true for you right now?"; sub "Select everything that resonates — there's no wrong answer."; seven checkbox cards (text + a small category line), the last one full-width: "I'm not sure what I want to do next professionally" / "I'm trying to find companies or environments that actually fit me" / "I feel pulled in too many directions at work" / "I'm doing fine professionally, but I don't feel as engaged or fulfilled as I used to" / "Different managers bring out different versions of me" / "I'm trying to understand what a sustainable long-term career path looks like now" / "I want to better understand how I naturally operate". CTA **"See what Solverah sees →"** is **disabled until at least one is selected**.
- **S2.3** — Select two or three, continue. → Step 2: "Question 1 of 5" with a progress bar, H2 "How often do you find yourself switching between unrelated tasks throughout a typical workday?", four radio-style options ("Rarely — I can usually stay focused on one thing" …), **"Next"** disabled until answered, "← Back" present from question 2 on (and from step 2 on the page-level "← Back" above the content).
- **S2.4** — Answer all five (the last button still reads "Next").
  → Step 3 fires `POST /api/v1/assessments/wpll/scoring-jobs` **anonymously** (no credentials) and polls. While pending: spinner + "Reading your responses…". Anonymous limit: 5/min, 20/hour, 50/day per IP, 500/day globally.
- **S2.5** — Wait for the teaser.
  → "Here's what's emerging from your responses", the insight card, then three locked rows each with 🔒 and "Unlock with a free account" (fallback labels when the job returns fewer than three: Environmental Friction Score / Work Rhythm Pattern / Emerging Archetype Signals), a `TierBar` titled "Your Solverah journey" with the three tiers "✓ Work Pulse Lite" / "→ Work Pulse" / "Work Pulse Pro · coming soon" (nothing on the bar is clickable), the button **"Create my free account →"** and "No credit card required. Takes 60 seconds."
  → **If it fails:** "We couldn't generate your insight right now." / "Please try again in a moment." / "Try again". A failure here with `OPENAI_API_KEY` unset is §0.6, not a UI bug.
- **S2.5a** *(new)* — Click **"Create my free account →"** on the teaser.
  → It does **not** navigate: it advances the wizard to step 4 in place (the page-level "← Back" returns to the teaser, using the cached insight — no second scoring job).
- **S2.6** — Step 4, the account gate.
  → "Your Work Pulse report is ready"; H1 "Unlock your full results"; "Create a free account to access:" and a ✓ list of four: "Your full 12-question Work Pulse assessment" / "A complete snapshot narrative of how you work" / "Emerging signals about your friction and flow" / "A partial Solverah profile you can build over time" — **`G23`** (the first item is wrong: 24 questions; the second has no counterpart: no narrative results screen). **"Create my free account →"** → `/register?from=wpll`; "Already have an account? Sign in" → `/login?from=wpll`; "No credit card required. Takes 60 seconds."
- **S2.7** — Reload mid-wizard.
  → At step 3 or 4 you return to that step (state is in `sessionStorage`); at step 3 the cached insight shows without a new job. **At step 2 you return to "Question 1 of 5"** with your earlier answers still ticked — position is local state and is lost. Closing the tab loses everything.
- **S2.8** — Complete registration from `?from=wpll` and sign in.
  → This path always goes through the plain `Register.tsx` component and the normal `POST /auth/register` — `?from=wpll` only changes some post-registration copy, not which endpoint runs. **Expect an ordinary 6-digit code.**
  → On sign-in, `Login.tsx` reads `solverah_intake` (only if it holds at least one WPLL answer), POSTs `/intake/claims` with `mode: "session"`, and removes the key. **A failure here is swallowed to the console and you still land on the dashboard**, with the key left in place so the next sign-in retries — verify the claim landed by checking the profile / Work Pulse Lite state, not by watching for an error. The key is also swept at logout (`draftStorage`).
  → Signed-in visitors are *not* turned away from `/start` (it is not under `RedirectIfAuthenticated`); the wizard renders for them, and step 4's links bounce to the dashboard.


---

### S3 · The hero intake form (resume upload)

**Account** none · **Route** `/` → `#intake`

- **S3.1** — Click any **"Get started"** (nav, hero, closing) or scroll to the "Start your reading." band.
  → Left column: H2 "Start your reading." / "Share your resume and a little context. You set up your account in the same step, and a person reviews what you send before anything comes back to you." and three bullets ("Resume as PDF or DOCX. We read it for context, not to score you." / "Your file goes to private storage and is never shown to employers." / "Already have an account? Sign in." — "Sign in" → `/login`). Right column: a white card, H2 "Tell us who you are" / "Your resume goes to private storage and we keep only what you choose to share. A person reads it before anything comes back to you."
  → The old "Early Access" / "Join the Solverah signal" header, the `#waitlist` anchor and the "Submit your intake now" button are gone (**retired 2026-09-28**, `cea54d6`).
- **S3.1a** *(new)* — Read the field labels.
  → "First name" / "Last name" / "Email" / "State / region" / "Phone (optional)" / "LinkedIn (optional)" / "Portfolio (optional)" / "Resume (PDF or DOCX — required)" with "Upload your resume" / "We read for context, not to score you. Your file stays private." and a green "Choose file" button; two checkboxes: "I consent to Solverah securely storing my resume and contact information so a person can review my submission, as described in the Privacy Policy." (link opens `/privacy` in a new tab) and "I want more information about how Solverah can help me." Placeholders: "you@example.com", "Where are you based?", "(555) 555-5555", "linkedin.com/in/you", "your-site.com".
- **S3.2** — Submit empty.
  → **Expected by the code:** "Please enter your name." **What a browser will actually do:** every text field carries `required` and the `<form>` has no `noValidate`, so the browser's own bubble ("Please fill out this field.") fires first and the app's message never appears. Record what you see — `G26`.
- **S3.3** — Walk the validators one at a time.
  → The app-level messages, in the order the code checks them: "Please enter your name." / "Please enter your email." / "Please enter your state / region." / "Please agree to the privacy notice to continue." / "Please attach your resume to continue." / "Please enter a valid LinkedIn URL." Of these, only the **privacy** and **LinkedIn** messages can plausibly show in a real browser (the checkbox is not `required`; the other four are pre-empted). With **no file chosen** the submit may do *nothing visible at all*: the file input is `required` *and* `display:none`, so Chrome cannot focus it to show a bubble. `G26`.
- **S3.3a** *(new)* — Type the placeholder format into the optional URL fields: LinkedIn `linkedin.com/in/you`, Portfolio `your-site.com`.
  → Both inputs are `type="url"`, so the browser rejects a value with no scheme ("Please enter a URL.") before any app code runs. With a scheme, the **server** is stricter than the client: `http://…` or non-LinkedIn URLs come back as "LinkedIn URL must be https://linkedin.com" / "Portfolio URL must be https://", a bad phone as "Invalid phone format", and these render in the red strip under the button. `G26`.
- **S3.4** — Attach a real PDF (or DOCX) and submit.
  → The idle button reads **"Begin setting up my account"**; clicking it flips it to **"Submitting…"**, disabled. Three calls in sequence: `POST /intake/resume-tickets` (10/min) → `PUT` to the presigned R2 URL → `POST /intake/submissions` (20/min). Errors that can show in the red strip: "Unsupported file type", "File too large (max 10MB)", "Invalid file size", "Upload failed. Please try again.", "Upload initialization failed. Please try again.", or the fallback "We couldn't save this right now. Please try again in a moment." (A `.doc`/`.docx` whose browser-reported type is empty is refused as "Unsupported file type".)
  → Success: green strip "Thanks — your submission was received." **and** the `AccountModal` opens (the form fields clear).
- **S3.5** — In the modal (Escape or a click on the dimmed backdrop closes it; "✕" labelled "Close").
  → "Next step" / "Save your profile?" / "Create an account and we'll auto-fill your profile using your resume. You can edit anything later." Then "We'll populate your personal info, work experience, skills, and education using the resume you shared." with "Sign in" / "Create account".
- **S3.5a** *(new)* — Click "Sign in" in the modal (for someone who already has an account under this email).
  → An "Email" field pre-filled from the submission and a "Password" field with a show/hide eye ("Show password" / "Hide password"); "Back" / "Sign in" (→ "Signing in…"). Errors come straight from the server: "Email does not match submission" (400, the field is editable but must equal the submission's email), "Account not found" (404), "Invalid credentials" (401), "Account locked. Try again later." (423), "Email not confirmed. Please confirm your email before signing in." (403), or client-side "Please enter your password." Success: "Signed in! Your profile has been updated from your intake submission." + **"Continue"** (just closes the modal). The server has opened a session at this point but the page does not know — the nav and landing stay as they were until you reload, after which `/` sends you to the dashboard. `G29`.
- **S3.6** — Create the account from the modal: "Create account" → "Create a password" / "Confirm password" (both with show/hide) → "Create account" → "Creating…".
  → **`G9` is fixed** (`deb4104`, 2026-09-16; on `origin/main`). `intake_service.create_account` now mints the same 6-digit code `/auth/register` does. Success copy: "Account created! Your profile has been filled in from your resume. We emailed you a 6-digit code to verify your address." and the button is **"Verify my email"** → `/verify-email` with your address in router state. Enter the code there (S5); after verifying you are sent to `/login`.
  → Client-side errors: "Please choose a password with at least 8 characters." / "Passwords do not match." / "We couldn't find your submission ID. Please resubmit the form." Server errors: "Password must be at least 12 characters." (and the uppercase / lowercase / number / symbol twins — the client says 8, the server demands 12 plus all four classes, `G30`), "User already exists" (400, the address is registered — the modal does not steer you to its Sign in step), "Submission not found" (404). Claims are limited to 5/min per mode.
  → The profile is seeded from a **rule-based** resume parse that degrades silently: the success sentence says "filled in from your resume" even when the parse yielded nothing, so check the profile after first sign-in rather than trusting it.
  → **Re-walk live:** the fix has been verified by code and tests, not yet by a live walk on prod.
- **S3.7** — **Retired 2026-09-28** — `EarlyAccessModal` and `useEarlyAccess` were deleted in `cea54d6`. Nothing on `/` mentions early access any more. (`G10` closed.) The backend route `POST /intake/early-access` still exists with no caller — `G31`.
- **S3.8** — Note the presign TTL is 10 minutes. If you leave the form open longer than that after choosing the file but before submitting, the `PUT` fails and the strip reads "Upload failed. Please try again." — that is correct behaviour. (The ticket is requested at submit time, so in practice you only hit this if the PUT itself stalls.)


---

### S4 · The guest quiz and its replay

**Account** ACC-2 · **Routes** `/quiz-preview`, `/quiz-preview/insights`, `/quiz-preview/early-career`, `/quiz-preview/career-transition`, `/quiz-preview/career-job-search`, `/quiz-preview/mid-career`, `/quiz-preview/teen-focused`
**Requires a clean browser profile** — the lockout is a `localStorage` read. These pages render under the global Header.

Storage: the answers, the insight request **and the insight itself** go to **`localStorage["pendingQuizSave"]`** (replayed at sign-in; swept at logout); the one-quiz lockout is **`localStorage["guestQuizCompletedAt"]`** (survives logout). **Both are written only after an insight has been generated** — a failed attempt locks nobody out.

- **S4.1** — Open `/quiz-preview`.
  → H1 "Try a quiz before you sign up."; sub "Take one quiz for free and get your insight straight away. Create an account to save your results and take the rest." Top-right: **"Create account"** (→ `/register`) and **"Sign in"** (→ `/login`). Five rows, in this order: Early Career / Career Transition / Career & Job Search / Mid-Career / Strategic / Your Future, Your Way (Teen-Focused). Each row's button reads "Start quiz" (accessible name "Start quiz: Early Career" etc.).
- **S4.2** — Start Early Career.
  → Heading "Quiz 1: Early Career" (also repeated as the section title), **ten** radio questions of four options each (the first: "What is one thing you would change about your current position?"). The submit button reads **"Get Insight"** (the signed-in version says "Save Answers") and is **disabled until at least one question is answered**. Other titles: "Quiz 2: Career Transition", "Quiz 3: Mid-Career / Strategic", "Quiz 4: Your Future, Your Way (Teen-Focused)", all ten questions; Career & Job Search is 25 questions in five sections (Career & Job Search / Work Style & Adulting / Growth & Identity / Networking & Social Life / Stress & Balance).
- **S4.3** — Try to submit **without answering anything**.
  → **Changed 2026-10-02** (`bf4b785`): you cannot. The button is disabled, and an empty request is refused in code before anything is sent ("Answer at least one question to get your insight." — unreachable from the UI). Partial answers *are* accepted: only answered items are sent. Check that the insight for a two-answer submission reads as appropriately tentative, not confidently wrong.
- **S4.4** — Answer honestly and submit.
  → Modal "Career Quizzes Insight" (eyebrow "Insight"). While generating: "Generating your insight. This can take a few seconds." plus a progress bar that is **fake** (ticks to 90% on a timer, not real progress). Close is hidden while loading.
  → Success: "Your insights are ready. Choose where you want to go next." + **"View insights"** / **"Back to quizzes"** / "Close".
  → Failure: a red box with the server's text — "We couldn't generate your insight right now. Please try again in a moment." (provider error; also the client-side "We couldn't generate your insight right now. Please try again." for an empty result), or on a 429 the backend text / "Too many attempts. Please wait a moment and try again." Limits: `5 per hour; 20 per day` per IP, `500 per day` globally. **A failure here writes nothing to localStorage — return to `/quiz-preview` and the quiz is still available.**
- **S4.5** — Click "View insights". → `/quiz-preview/insights`. H1 "Your quiz insights" / "What your answers point to, and what to try next. Create an account to keep them."; a "Summary" pane (if present), then one row per insight with "Key takeaways", **"What it means together"** (was "Combined meaning"), "Next steps". Buttons: "Back to quizzes", **"Create account"** (→ `/register`), "Sign in to save results" (→ `/login`).
- **S4.6** — **Open a new tab and paste in this exact URL.**
  → **Changed 2026-10-02** (`bf4b785`; `G20` closed): the insight now persists with the pending save, so the new tab **shows the same insight**. That is the intended behaviour, not a leak. To see an empty state, use a private window (nothing stored, not locked): "No insights found. Take a quiz to generate your insights." + **"Choose a quiz"**. If you are *locked out but the save is gone* (you completed a quiz, then signed in and out — logout sweeps `pendingQuizSave` but not the lockout): "We couldn't find your insight on this device. Sign in or create an account to take more quizzes and keep your results." + "Sign in".
- **S4.7** — Go back to `/quiz-preview`.
  → Now locked: a `role="status"` strip "You've already taken a guest quiz. Create an account or sign in to take more and save your results." followed, when the insight is stored, by a **"See your insight"** link → `/quiz-preview/insights`. Every row's button is replaced by a lock icon and "Sign in above to unlock" (the real actions are "Create account" / "Sign in" at the top of the page).
  → The lock is the **list page only**. Typing `/quiz-preview/early-career` directly still renders the quiz and a second insight can be generated, overwriting the first save — `G28`.
- **S4.8** — Register **and then sign in** as ACC-2.
  → On sign-in (not on registration — registration routes through `/verify-email` → `/login`), `getPendingQuizSave()` fires: `PATCH /me/profile` with the quiz results (merged one level below the server's merge so existing career-quiz answers survive), then `POST /me/quiz-insights`, then **`await queryClient.invalidateQueries({ queryKey: profileKeys.document() })`**, then redirect to `/quiz-insights?group=careerQuizzes`.
  → **`G22` is fixed** (`140d66b`, 2026-09-28; on `origin/main`): you should land on `/quiz-insights` with the insights already showing — **no reload needed**. If you do see "No insights found yet." on arrival, that is a regression of `G22`: record it as `S4.8 → G22 (regressed)`.
  → If the replay fails: a 4xx other than 401/408/429 **drops** the save (it would fail identically forever); a 401/408/429 or a 5xx/network error keeps it for the next sign-in. Either way it logs to the console and falls through to the dashboard — no visible error.
- **S4.9** — Open `/quiz-preview/career-job-search` as a guest and complete it.
  → Same shape, heading "Career & Job Search", modal titled "Career & Job Search Insight". **`G16` is fixed** (`bf4b785`, 2026-10-02): the guest and signed-in branches now both file under `quizGroup: "careerQuizzes"` (and a pre-fix save sitting in localStorage is normalised on read). Check `/quiz-insights` after the replay shows it under the Career quizzes group.
- **S4.10** — Open `/quiz-preview/not-a-real-quiz`.
  → **Redirects to `/`** (the catch-all) — there is no wildcard guest route, so the "That quiz could not be found" screen is **unreachable for a guest by URL**. It was this way in the source the doc was first derived from; the old expectation here was wrong. `G19` is closed in code (`bf4b785`): the in-component guest branch now reads "That quiz could not be found. Go back to the quiz list to choose one." with "Back to quizzes" → `/quiz-preview`, but nothing can route to it. Walk this step as: *expect a redirect to the landing page, no error*.
- **S4.11** *(new)* — Open `/quiz-preview` while **signed in**.
  → It renders as a guest (public route, no redirect); the global Header shows your nav. Taking a guest quiz while signed in writes `pendingQuizSave` for the *current* account's next sign-in. Low priority; note only if something looks off.


---

### S5 · Register → verify → sign in

**Account** ACC-1 (and ACC-5, which stops at S5.6)

*Re-derived 2026-10-25 from HEAD. Every file under `src/features/auth/` and `src/app/RequireAuth.tsx` / `RedirectIfAuthenticated.tsx` is identical on `origin/main` (02707ab) and HEAD, so nothing in S5 is branch-only. `G8` is closed (`368c768`); the changed copy is in S5.5.*

- **S5.1** — Open `/register`.
  → Eyebrow "Get started"; H1 "Create your account". Fields: Full name (placeholder "Your full name"), Email address ("you@example.com"), Password ("Min. 12 characters"), Confirm password ("Repeat your password"), and a checkbox "I am 16 or older and agree to the Terms of Service and Privacy Policy." Both password fields have a show/hide eye with `aria-label` "Show password" / "Hide password". Submit button "Create account" ("Creating account…" in flight).
- **S5.2** — Walk the password validators. They fire one at a time, in this order, client-side:
  → "Passwords do not match" → "Password must be at least 12 characters" → "Password must contain an uppercase letter" → "Password must contain a lowercase letter" → "Password must contain a number" → "Password must contain a symbol" → "Please confirm you are 16 or older and accept the Terms of Service and Privacy Policy"
  → The server runs the same checks again (`validators.py`, e.g. "Password must be at least 12 characters.") but the client gate catches them first, so you will not see the server wording from the form.
- **S5.3** — Register with an address that already exists.
  → The server answers 400 `{"error": "User already exists"}`; the form shows "An account with that email already exists". (Note: this endpoint therefore *does* confirm which addresses are registered, unlike `/forgot-password` and resend, which were made uniform. Not a step failure; a known asymmetry.)
- **S5.3a** — Register six times inside a minute.
  → The limit is `5 per minute`. The sixth gets a 429, and the form shows the limiter's raw description, **"5 per 1 minute"** — see `G33`.
- **S5.4** — Register cleanly.
  → 201, and you are sent to `/verify-email` carrying your address in router state (and `from: "wpll"` only if you arrived with `?from=wpll`). **There is no success screen on the register page itself.** The code email is written to the outbox in the same transaction as the account, so the account exists even if the send later fails.
- **S5.5** — On `/verify-email`: eyebrow "Verify your email"; H1 "Check your inbox"; body "We sent a 6-digit code to **{your email}**. Enter it below to activate your account." Input placeholder "000000"; non-digits are stripped and the field caps at 6. Button "Verify email" is **disabled until six digits are typed** ("Verifying…" in flight). "Back to sign in" link top-left.
  → Enter a **wrong** code. → Banner: **"That code didn't match. Check the six digits and try again, or request a new code below."** (server `invalid code`; `G8` closed `368c768`).
  → Wait 15+ minutes and enter the real code. → **"That code has expired. Request a new one below and we'll send it right away."** (server `code expired`).
  → Enter more than five codes in a minute. → The server's 429 text passes through untouched (`otpErrorMessage` deliberately does not rewrite it) — currently the raw limiter string, `G33`.
- **S5.5a** — Open `/verify-email` directly in a **new tab** (no router state, no `?email=`).
  → Body reads "We sent a 6-digit code to **your email**." and a six-digit submit posts an empty address; the server answers `email and code are required`, which the UI maps to **"Please enter the 6-digit code from your email."** — a misleading message for the real problem. "Resend code" then says "No email available." See `G35`. A same-tab reload is fine (router state survives it).
- **S5.6** — Click "Resend code".
  → "Sending…" → "Sent!" and the button is **permanently disabled** — there is no timer, just `disabled={isPending || isSuccess}`. Success text: "New code sent! Check your inbox." Server-side the limit is `5 per minute`; a failure here shows the server's message raw (the resend path was **not** given friendly copy by the G8 fix — it shows `error.message`, or "Network error." / "Failed to resend code." fallbacks).
  → The endpoint answers 200 for an unknown address, an already-confirmed address and a real one alike, so Resend never tells you which you are.
  → **Stop here for ACC-5.** Leave it unverified.
- **S5.7** — Enter the correct code.
  → The form is replaced by "Email verified! Redirecting to sign in…" (or, when `from` is `wpll`, "Email verified! Signing you in to unlock your results…"), then after **2 seconds** it navigates to `/login` (`/login?from=wpll` in the second case).
- **S5.8** — Sign in as ACC-5 (unverified), with the **correct** password.
  → The server answers 403 "Email not confirmed. Please check your inbox or use the resend option." The UI shows the banner **"Your email is not confirmed. Please check your inbox."** and a "Resend verification code" link-button beneath it. This is the only unconfirmed-email gate in the entire API — no `/me/*` route checks the flag. (With the *wrong* password for an unconfirmed account you get the generic failure, never this banner — the password is checked first.)
- **S5.8a** — Click "Resend verification code" (after typing your email in the field above it).
  → "Sending…", then you are taken to `/verify-email` with that address filled in. With the email field empty: "Please enter your email above before resending."
- **S5.9** — Sign in as ACC-1 with the **wrong password**.
  → "Failed to sign in. Please check your credentials." Note: this one message swallows every non-unconfirmed failure, including the 401 "Invalid credentials", the 423 lockout (`S6.7`), a 429 from the login limiter, and network errors.
- **S5.10** — Sign in correctly. Button reads "Signing in…". → `/job-seeker/dashboard`. (If a guest quiz or `/start` intake answers were waiting in this tab, the redirect goes to `/quiz-insights?group=…` instead — that replay is walked in S4.8, and the stale-cache `G22` is fixed.)
- **S5.10a** — Close the tab. Reopen `https://solverah.com`, then `/login`, then `/register`, in the same browser (cookies intact).
  → Each one shows at most a brief grey skeleton and then **`/job-seeker/dashboard`**. The landing page, the sign-in form and the register form never appear; the header never shows your name over a "Sign In" link. This is `RedirectIfAuthenticated` (the mirror of `RequireAuth`) on `/`, `/login` and `/register`. A **clean** browser profile (no `solverah.hasSession` in localStorage) still draws the landing page instantly — S1.1 — with no wait on the session probe. The verdict is taken once per mount, so a sign-in completed *on* `/login` is never pre-empted by the redirect.
- **S5.11** — Open `/confirm-email` and `/check-email`.
  → Both render nothing and redirect (replace) to `/verify-email`, carrying `state.email` or `?email=` if present. Legacy aliases.


---

### S6 · Auth recovery and failure modes

**Account** ACC-1, ACC-5

*Re-derived 2026-10-25. Frontend auth is identical on prod and HEAD; backend `auth.py` and `auth_service.py` are identical too. Nothing here is branch-only.*

- **S6.1** — `/forgot-password`.
  → Eyebrow "Forgot password"; H1 **"Sign in with a code"**; "Enter your email and we'll send a one-time code you can use to sign in." Button "Send code" ("Sending…"). Reached from `/login` by the link **"Forgot your password?"**. Note this is **passwordless sign-in, not a password reset** — there is no new-password form anywhere in the app, and the link text promises one. (Copy mismatch, Julie's call; not filed as a gap.)
- **S6.2** — Submit an address that does not exist.
  → Still succeeds and moves you to `/forgot-password/verify`. The endpoint always answers 200 `reset_sent`, to avoid confirming which addresses exist. No email sends.
- **S6.3** — Submit ACC-5 (registered but unconfirmed).
  → Also 200, also no email — the send requires `email_confirmed`. Confirm that a user in this state has no recovery path except the resend on `/login` (S5.8a).
- **S6.4** — On the code screen (eyebrow "Check your inbox", H1 **"Enter your code"**, "We sent a 6-digit code to **{email}**. Enter it below to sign in.", button "Sign in") submit ACC-1 and enter a wrong code.
  → **"That code is invalid or has expired. Request a new one below and try again."** (This replaces the older "Invalid or expired code. Please try again."; keyed on the server string `invalid_or_expired_code`, which is returned identically for wrong, expired and no-pending-reset.)
- **S6.4a** — On that screen press "Resend code" three times quickly, then once more inside the same minute.
  → First press: "Sending…" → "Sent!" and "New code sent! Check your inbox." The resend is a bare `fetch` whose response is **never inspected**, so when the server answers 429 (limit `3 per minute` on `/auth/password/forgot`) the screen **still says "New code sent! Check your inbox."** and no email arrives. See `G34`.
- **S6.5** — Enter the correct code. → Signed straight in, to `/job-seeker/dashboard` (`replace`). It does not honour a return-to-origin and does not replay a guest quiz — only `/login` does.
- **S6.6** — Submit `/forgot-password` four times inside a minute.
  → The limit is `3 per minute`; the fourth gets a 429. The page shows whatever the server put in the problem's `detail` — for flask-limiter that is its raw description, **"3 per 1 minute"** (the component test asserts exactly this text), not the friendly "Too many attempts. Please wait a moment and try again." that `apiError.ts` keeps as a fallback. `G33`.
- **S6.7** — Fail the password on `/login` five times, **all against the same account** (ACC-5, not ACC-1 — see the trap below).
  → The sixth attempt is locked for 15 minutes (`MAX_LOGIN_ATTEMPTS=5`, `LOGIN_LOCKOUT_MINUTES=15` defaults). The backend says 423 "Account locked. Try again later." but the UI shows "Failed to sign in. Please check your credentials." — i.e. **a locked-out user is told their password is wrong**. **Still open, verified at HEAD**: `Login.tsx` branches only on the substring "email not confirmed" and folds everything else into the generic line. Worth a ruling.
  → To prove the lock is real: make the sixth attempt with the **correct** password. If it still fails with the same generic message, the lock is confirmed; if it succeeds, the account was never locked.
  → **Testing trap, confirmed 2026-09-15:** `/auth/login`'s `5 per minute` rate limit is scoped **per IP address** (`get_remote_address`), not per account. Five failed attempts on ACC-5 consume that IP's entire login budget for the minute — the very next login on **any other account from the same connection**, including a correct one, gets a 429 in that same window, rendered **identically** to a wrong password. Wait roughly a minute between this step and logging into a different account, or do this step last.
- **S6.8** — Sign in, then delete the `access_token_cookie` in devtools, then click around.
  → The context refreshes once, silently (single-flight 401 → `POST /auth/refresh` → one replay), and you notice nothing. This now also covers the streaming agent chat (`368c768`: `streamFetch` shares the refresh core).
- **S6.9** — Sign in, then delete **both** auth cookies, then navigate to `/situation-report`.
  → The refresh fails, the session clears locally (including the whole query cache), and the next protected render bounces you to `/login`. **There is no toast and no message.** Half-finished answers in `sessionStorage` are **kept** on this path on purpose (a network blip must not cost a 24-answer sitting); only an explicit logout or account deletion sweeps them (S6.11a).
- **S6.10** — From that `/login`, sign back in.
  → You should be returned to `/situation-report`, not the dashboard. `RequireAuth` plants the attempted location in router state; `Login` validates it (same-app absolute path only; `//` and `/\` rejected) and honours it, ahead of the quiz-replay path.
- **S6.11** — Sign out via the header icon. Desktop: the icon-only button has `title="Logout"` and **no `aria-label`** (the gear beside it has both). **Still open, verified at HEAD** (`Header.tsx` lines 175–178). On a narrow viewport the header now collapses into a menu (button `aria-label` "Open menu" / "Close menu"; panel `aria-label` "Mobile") whose entries are *visible text* "Settings" and "Log out" — so the missing label is a desktop-only accessibility gap, not a mobile one.
  → `POST /auth/logout`, cache cleared, land on `/`. This endpoint always returns 200, even with no session, and the header awaits it before navigating so `RedirectIfAuthenticated` does not bounce you to the dashboard.
- **S6.11a** — *(new since the old doc)* Before step S6.11, start the Work Pulse and answer a few questions (or note any of the keys in Appendix A in devtools → Application → Storage). Then log out.
  → All per-user drafts are gone from `sessionStorage` **and** `localStorage`: `solverah_assessment_answers`, `env_report_answers*`, `mp_answers`, `mm_answers`, `solverah_wp`, `solverah_intake`, `focus_type_draft*`, `pendingQuizSave`. `solverah.hasSession` is removed. `guestQuizCompletedAt` (the one-quiz-per-device lock) is **kept**. Sign back in as a different account and confirm you are not offered the previous person's half-finished instrument. (`draftStorage.ts`, `368c768`.)
- **S6.12** — While signed out, open `/pulse` directly.
  → Grey skeleton (no text) during the session probe, then `/login`. After signing in you land back on `/pulse`. This is the email deep-link path — S23 depends on it.
- **S6.13** — Sign in as ACC-1, then open `/login` by typing the URL.
  → Straight to the dashboard (S5.10a). Wrong-role case: the only role is `job-seeker`; a session with any other role reaching a guarded route is sent to `/` with no state and no copy (`RequireAuth` line 3 of its contract), and `RedirectIfAuthenticated` renders the page rather than loop. `G17`, **still open, verified at HEAD**, unreachable in practice today.


---

### S7 · The brand-new dashboard

**Account** ACC-1, immediately after S5.10 · **Route** `/job-seeker/dashboard` ·
**Re-derived from HEAD 2026-10-25.** Everything in S7 is identical on prod
(`origin/main` 02707ab) and on the branch, except one hint string in S7.5 (marked).

- **S7.1** — Land on the dashboard for the first time.
  → The **`IntakePromptModal` auto-opens** when the server's `profileCompletion` is under
  50%. That figure is the share of seven fields (first name, last name, email, summary,
  skills, experience, education), so a fresh account sits at about 42% (three of seven)
  and the modal opens. Eyebrow "Profile Autofill"; title "Boost your profile instantly"
  (or "Your profile needs attention" if the account came through the hero intake form).
  → Body, no-intake variant: "Fill out the Solverah Signal form and we'll automatically
  populate your profile with your resume, experience, and contact details — no manual
  entry needed." / "What gets filled in:" / "Name, location, and contact info", "Work
  experience parsed from your resume", "Education and skills", "LinkedIn and portfolio
  links". Buttons "Get started →" and "Maybe later".
  → Has-intake variant: "Your profile is still incomplete. Head to your profile page to
  fill in the remaining details and improve your job matches." / "Sections to complete:"
  (four bullets) with the same two buttons.
  → It does **not** open while `/me/dashboard` is loading or has failed.
- **S7.1a** — Click "Get started →" and walk the modal form (optional, but it is a real
  upload path).
  → Title "Join the Solverah signal"; "Private intake for thoughtful collaborators.
  Resumes upload to secure storage; we store only what you choose to share." Fields:
  First name, Last name, State / region, plus optional phone, LinkedIn, portfolio, then
  "Upload your resume" / "We read for context, not to score you. Your file stays private."
  Two checkboxes: "I consent to Solverah securely storing my resume and contact
  information so a person can review my submission, as described in the Privacy Policy."
  and "I want more information about how Solverah can help me."
  → Client-side refusals, in this order: "Please enter your name." / "Please enter your
  state / region." / "Please attach your resume to continue." / "Please agree to the
  privacy notice to continue."
  → Submit button "Submit & autofill profile" ("Submitting…"), then title "You're all
  set!" / "Profile autofill complete!" / "Your resume has been processed and your profile
  has been updated with the extracted information." / "View my profile →" (goes to
  `/job-seeker/profile`).
- **S7.2** — Dismiss it with "Maybe later" (or the X, or the backdrop).
  → Header block: eyebrow "Dashboard"; H1 "Welcome back, {your name}"; "Here's where
  your working life stands, and the one thing worth doing next."
  → **The modal returns on every arrival at the dashboard** while completion is under 50%
  (the dashboard refetches on every mount, and the effect reopens it). Expected from the
  code; decide on the walk whether that is too eager. `G41`.
- **S7.3** — Check the Work Pulse banner.
  → "Complete your Work Pulse" / "24 quick either-or questions about how you actually
  work — takes about 8 minutes." / button "Start now" / a dismiss "X" (aria-label
  "Dismiss"). (A legacy completer of the retired 12-question quiz instead sees "Work
  Pulse has been rebuilt" / "The new version replaces the one you took — 24 quick
  either-or questions, about 8 minutes, and it powers your matching directly." /
  "Retake it now".)
- **S7.4** — Dismiss it with the X, then reload.
  → It comes back. The dismissal is local state only, by design.
- **S7.4a** — Look for the "Complete your profile" alert.
  → Amber strip: "Complete your profile — it's what the rest of Solverah reads from." /
  "Complete Profile →" (to `/job-seeker/profile`). Shown while completion is under 100%,
  and hidden while the dashboard document is unknown. (It used to say "…to get better job
  matches and increase visibility"; that job-board register was removed.)
- **S7.5** — Look for the Situation Report card.
  → It renders **nothing at all** while `/me/situation-report` is in flight (and on a
  failed fetch), then the `needs_core` state: eyebrow "Situation Report"; H2 "Your
  conditions, once we have your side" / "Your Situation Report is the distance between how
  you work and what your job actually asks of you. Work Pulse is the first of those two,
  and it isn't finished yet."
  → Its "Next" action is **suppressed**, because the Work Pulse banner above is already
  offering the same thing. (After the banner is dismissed or Work Pulse is done, the card
  offers "Start Work Pulse →" / "Twenty-four either-or questions, about eight minutes.")
  → **Branch only — not on prod until the next merge.** The `needs_environment_report`
  state's Next hint now reads "Sixteen questions about the role you're in, plus five
  optional, about five minutes." Prod reads "Sixteen questions about the role you're in,
  about five minutes." Not visible on ACC-1 at this point of the walk; check it in S9.
- **S7.6** — Check the Pulse card.
  → Eyebrow "Pulse"; H2 "Keep a pulse on work"; "A short weekly check-in — three
  questions, about a minute. It gets more useful the more you do it."; "Take your first
  check-in →".
  → While loading it renders nothing. On a failed fetch: H2 "Your pulse" / "We couldn't
  load your pulse right now." / "Try again" and "Check in →".
- **S7.7** — Check the two cards in the lower grid (Recent Activity, Recommendations).
  They are **no longer static placeholders** (A28, built 2026-09-28, `b48348d`); both are
  built per user from real rows. For a brand-new account:
  → "Recent Activity" → "You're just getting started." + "When you take Work Pulse or
  update your profile, you'll see it listed here." (A new account that came through the
  hero form may already have a "You uploaded your resume" row; that is correct.)
  → "Recommendations" → see S7.7a. The old empty copy ("No recommendations yet." /
  "Once you finish Work Pulse we'll suggest what to do next.") is gone. The empty state
  is now "Suggestions start after Work Pulse." / "Once you've taken it, we'll point you to
  what's worth doing next." before Work Pulse, and "You're up to date." / "The cards above
  have your next step. New suggestions show up here as they come." after it.
  → (If you can force `/me/dashboard` to fail — block it in devtools.) Both cards are
  replaced by one notice: "We couldn't load your dashboard right now." + "Try again".
  While it loads, each card reads "Loading…" and neither empty state shows. (Was `G14`;
  closed 2026-09-14.)
- **S7.7a** — Read the Recommendations on a brand-new account.
  → Up to three cards, most important first. The server sends every step that applies;
  the page drops any whose destination a lead card above already links to, then shows the
  first three. Expect, in order, the ones that apply to you: "Tell us where you are in
  your career" / "Working, between jobs, or looking for your first one. It changes what we
  ask and suggest." / "Set your status →" / badge **"Action Needed"**; then "Add your
  skills" / "A few skills make your path suggestions much sharper." / "Add skills →" /
  "Optional"; then "Check in on your week" / "A one-minute pulse keeps your picture of
  work up to date." / "Check in →" / "Optional". "Take Work Pulse" / "24 questions about
  how you work best. Most of Solverah builds on it." / "Start Work Pulse" is **not shown**
  while the Work Pulse banner is on screen (same destination).
  → Clicking "Set your status" goes to `/job-seeker/profile?tab=experience` with the
  career-status modal open and a way back to the dashboard (S19.7/S19.8). "Add skills"
  goes to the profile's Experience tab. "Check in" goes to `/pulse`.
  → Later states: "Describe your current job" / "The Environment Report is how we compare
  your job with what you need." / "Start the report" (Work Pulse done, no job report, not
  `first_job`); "Read your Situation Report" / "Where your job fits you, and where it pulls
  against you." / "Open the report" (both halves done; filtered out when the Situation
  card already links there).
- **S7.7b** — After completing something (a Work Pulse, a profile save, a pulse), return to
  the dashboard.
  → Recent Activity lists it, newest first, at most five, with a humanized time ("just
  now", "5 min ago", "yesterday"). Row texts, from source: "You took Work Pulse", "You
  took FocusType", "You took ManagerMatch", "You described your current job", "You
  described your manager", "You checked in on your week", "You uploaded your resume",
  "You got insights from your career quizzes", and for a legacy sitting "You took the
  original Work Pulse quiz". The page refetches on every arrival, so there should be no
  stale card; if the new row is missing, that is a bug in cache invalidation.
- **S7.8** — Check Quick Actions.
  → Exactly two tiles: "Edit Profile" / "Update your information" → `/job-seeker/profile`;
  "Your Solverah profile" / "Work Pulse, FocusType and ManagerMatch" → `/intelligence`.
  → **Retired 2026-10-05** — the "Search companies and roles →" link below the fold was
  removed (`fb34d02`), because `/search` is a coming-soon page. There is no path from the
  dashboard to `/search` or `/company-lens`; the second tile and the hub are the route.
- **S7.9** — **Resize to phone width (~390px), signed in.**
  → **`G2` is closed** (`835cfbf`, 2026-09-28; on prod). Below 768px the inline nav is
  gone: the bar shows "Solverah" and one menu button (aria-label "Open menu"). The
  seven-item overflow no longer exists. Nothing should scroll sideways.
- **S7.9a** — Tap the menu button.
  → The button becomes "Close menu" and a panel drops under the bar with five stacked
  links, "Feed", "Dashboard", "Intelligence", "Profile", "Agent" (current page
  highlighted), then a divider, your name, "Settings" and "Log out".
  → Tapping any link closes the panel; so does Escape and any change of route.
- **S7.9b** — In the open menu, tap "Feed".
  → The panel closes and the coming-soon modal opens (S7.10). Tap "Log out".
  → You are signed out and land on `/` (landing), not bounced to `/dashboard` or
  `/login`.
- **S7.9c** — At roughly 768–860px (tablet portrait, a long name) check the desktop bar.
  → The menu collapses below `md` (768px), and above it the bar is five links, your name,
  the gear and the logout icon in one non-wrapping row. By arithmetic it may be about
  50px too wide at the bottom of that range. Unverified; look, and file `G38` if the
  row overflows.
- **S7.10** — Click "Feed" in the header (desktop).
  → A modal that **now covers the whole page** (it is portaled to `body`; it used to be
  trapped in the 64px header): "Feature coming soon" / "We're still building the feed.
  It'll show up here when it's ready." / "Got it". Escape also closes it. **Copy changed**
  from the old "The feed will be available soon. Check back after launch." `G3` — still
  open, by decision (09-28 ruling: feed is coming-soon). Prod matches HEAD.
- **S7.10a** — Type `/feed` into the address bar.
  → A real page, which the header never links to: H1 "Your feed, {first name}"; H2 "The
  feed is coming soon" / "This is where roles, messages and updates will collect once
  they're ready. None of that is live yet, so there's nothing to show here for now. Your
  dashboard and Intelligence pages are up and running." / "Go to your dashboard" and "Open
  Intelligence".
- **S7.11** — Note what is **not** in the header: Work Pulse, Situation Report, Pulse,
  Manager Decoder. All four are reachable only from the dashboard, `/intelligence`, or a
  typed URL. Judge whether that is survivable at launch.
- **S7.11a** — Print the dashboard (Ctrl+P, or the print preview).
  → The header is hidden (`print:hidden`), including the Feed modal if it is open.
- **S7.11b** — Signed out, look at the header on `/`.
  → "Sign in" and "Get started" only; none of the signed-in nav. (Signed-in visitors to
  `/` are redirected to the dashboard before they see this.)


---

### S8 · Work Pulse — the core sitting

**Account** ACC-1 · **Routes** `/assessment`, `/work-pulse`, `/work-pulse/results` ·
**24 forced-choice items, ~8 minutes**

Draft storage: `sessionStorage["solverah_assessment_answers"]` (answers only, keyed by
opaque per-respondent item token; swept on sign-out).

> **Prod vs branch.** Everything in S8 is on prod (`origin/main` 02707ab) except three
> things, each marked below: the tolerance step that now opens right after Finish
> (S8.6, S24), the "Change how much give…" link on the card (S8.8), and the CompanyLens
> card on the legacy results page (S8.9). The resume prompt (9b638d0, 2026-09-28),
> retakes (6babb39, 2026-10-05) and the house submit error (7dfe752) are all on prod.

- **S8.1** — Open `/assessment`. → Redirects (replace) to `/work-pulse`. No flash of
  anything else.
- **S8.2** — On `/work-pulse`, read the intro.
  → H1 "Work Pulse"; "24 either-or questions about the conditions you do your best
  work in — about eight minutes."; "There are no right answers, and nothing here is
  scored as better or worse. The profile is only useful if it describes you rather
  than the version of you that sounds most employable."; "Employers never see your
  answers or your dimension scores." + link "How this works, and what we hold back →"
  (→ `/trust`).
  → While the form loads, the word **"Loading…"** appears under the header. No
  spinner, no skeleton. On a failing request it stays up for a few seconds (two
  bounded retries) before S8.10's panel replaces it.
- **S8.2a** — *(Only for an account that finished the retired 12-question quiz —
  none of ACC-1…5 will have.)* An extra line under the intro: "You completed the
  original Work Pulse — this new version replaces it." + "View your previous
  analysis →" (→ `/work-pulse/results`). It disappears once the new one is complete.
- **S8.3** — Answer three questions.
  → "Question 3 of 24" + progress bar; the selected option shows a ✓; **"Next"** stays
  disabled until the current question has an answer (no auto-advance); "← Back" is
  hidden on question 1 and present after. The last question's button reads "Finish".
  → No section headings, no block labels, nothing that names a dimension. Two
  adjacent questions should never feel like the same topic.
- **S8.4** — **Reload the page.** *(Changed 2026-09-28, 9b638d0 — was "returns to
  Question 1 with answers pre-selected".)*
  → The intro stays, and in place of the stepper a card: eyebrow "Work Pulse"; H2
  "You have answers saved from last time"; "You got through 3 of 24 questions. Pick up
  where you left off, or clear them and start again from the beginning."; buttons
  **"Pick up where you left off"** and **"Start over"**.
  → "Pick up where you left off" opens at **"Question 4 of 24"** (the first unanswered
  one), earlier answers still ✓'d. "Start over" opens at "Question 1 of 24" with every
  answer cleared — and a reload before you answer anything new shows no prompt.
- **S8.5** — **Close the tab and reopen `/work-pulse`.**
  → Everything is gone, no prompt: `sessionStorage` dies with the tab.
- **S8.5a** — *(New.)* Answer two, **sign out**, sign back in as the same account,
  open `/work-pulse`.
  → No prompt, question 1, nothing selected. Logout sweeps the draft
  (`clearUserDrafts`). An expired session that fails to refresh does **not** sweep it —
  deliberately, so a network blip at Finish cannot cost 24 answers.
- **S8.6** — Answer all 24 honestly and click "Finish".
  → Button reads "Saving…". On success the page **swaps in place** — no navigation, no
  results page.
  → **Prod:** straight to the completion card (S8.7).
  → **Branch only — not on prod until the next merge.** First the tolerance step,
  under the eyebrow "✦ Work Pulse Complete" (walk it as **S24**); "Save" or "Skip for
  now" then gives the card.
- **S8.6a** — *(New, 7dfe752.)* **Submit failure.** Before pressing Finish, block
  `POST …/assessments/core/submissions` in devtools.
  → Under the question, in red: "We couldn't save your Work Pulse. Your answers are
  still here. Reload the questions, then press Finish again." + **"Reload the
  questions"**. The server's own text is never shown. Unblock, press "Reload the
  questions" (the message hides; the stepper reopens at the first unanswered question,
  i.e. question 24), press Finish → S8.6.
- **S8.7** — Read the completion card.
  → "✦ Work Pulse Complete" / H1 "That's everything we need" / "Your Work Pulse now
  powers your matching. There's no score to check and nothing to optimize — it works
  quietly in the background as we line up the environments where you'd do your best
  work."
  → The middle of the card depends on `/me/situation-report`, and is **empty for a
  moment** while it loads (only the three secondary buttons show). Then one of:
  - *No job described yet (ACC-1 here):* "24 questions about you. Now 16 about your
    job." / "Work Pulse is half of your Situation Report. The other half is your own
    description of the role you're in — what it actually offers, not what it was
    advertised as — and the report is the distance between the two." / primary
    **"Describe your job →"** → `/environment-report`.
  - *Job already described:* "You've already described your job, so both halves of
    your Situation Report are in. It's ready to read." / primary **"See your Situation
    Report →"**.
  - *`first_job` (ACC-3):* "When you start a job, sixteen questions about it turn this
    into your Situation Report. Until then, FocusType and ManagerMatch need no
    employer, and they're most useful while you're choosing between offers." — no
    primary; "Start FocusType →" becomes the primary.
  → Secondaries: "Start FocusType →", "Start ManagerMatch →", "Back to dashboard"
  (replace-navigates, so Back does not return here).
  → **No link to any result anywhere on the card.** Not a missing feature (§0.5 #1).
- **S8.8** — Navigate back to `/work-pulse`.
  → You get the completion card, not the form, and **no request to `core/form` is
  made**. At the bottom, below a rule: "If the way you work has changed, you can take
  Work Pulse again. Your earlier sitting stays stored." and a secondary button
  **"Retake Work Pulse"**.
  → **Branch only — not on prod until the next merge.** Under it, a text-style button
  "Change how much give you have on each area →" (→ `/trait-preferences`, S24.8). Prod
  has no such line.
  → Note how you got here: **nothing in the product links to `/work-pulse` once it is
  complete** — not the header, not the dashboard's "Work Pulse complete — your answers
  now power your matching" card, not the hub's Work Pulse card. You typed it.
  `G46`.
- **S8.8a** — Press **Retake Work Pulse**.
  → The normal 24-question stepper, with a line above it: "You're retaking Work Pulse.
  This is a new sitting: the one you finished before stays stored, and your Situation
  Report keeps reading it until you choose to re-read the report." and a **Not now**
  link-button that returns to the card. The questions are the same ones in the same
  order (tokens are stable per person). Answer a few, then reload the page.
  → The completion card again (Work Pulse is still complete; the dashboard and hub do
  not change). Its bottom line now reads "You started a new sitting and didn't finish
  it. Your answers so far are saved in this browser." and the button **"Continue your
  retake →"**. Press it: the S8.4 prompt ("You have answers saved from last time").
  Finish the retake.
  → **Prod:** the completion card. **Branch only:** the tolerance step again (S24.1),
  this time pre-filled with whatever you saved last, then the card.
  → If you already have a Situation Report, the card now reads "Your Situation Report
  still reads the sitting it was built from. To move it to this one, open the report
  and choose “Re-read this against my latest Work Pulse”." (S11.3). That line shows
  only straight after a retake in the same visit; a later visit shows the ordinary
  "You've already described your job…" line.
- **S8.9** — Open `/work-pulse/results`.
  → **Silently redirects** to `/work-pulse` (replace) unless the account finished the
  retired 12-question quiz *and* a narrative was stored (a 404 also redirects). None
  of ACC-1…5 qualifies, so the redirect is what you should see.
  → For a legacy account only: "Loading your results…" with a spinner, then eyebrow
  "Your original Work Pulse"; H1 "Here's how you work"; "This is the analysis from the
  first version of Work Pulse, which has since been replaced. It's kept here for you
  to read; it no longer changes." + "Go to the current Work Pulse →"; the narrative;
  "Emerging signals"; "Your primary work archetype"; "Who sees this" / "Only you. Your
  archetype and narrative stay in your Intelligence Hub, where they shape what Solverah
  shows you. Employers never see them." + "How this works →" + "Go to Intelligence Hub
  →"; a "Based on your results" card; the tier bar; "Work Pulse Pro · coming soon" /
  "Deeper analysis, personalised recommendations, and more." On failure: "We couldn't
  load your results right now." / "Please try again in a moment." / "Try again".
  → The "Based on your results" card differs. **Prod:** "Work Pulse Pro, coming soon,
  will map your work patterns against real company environments. Some companies
  consistently amplify the friction you described. Others are built in ways that
  reduce it. CompanyLens will show you which is which." with two blurred tiles reading
  "Fit score: --" and the label "CompanyLens™ · Pro · coming soon". **Branch only — not
  on prod until the next merge:** "CompanyLens reads real company environments against
  what you need, and shows you what each company looks like on the things that matter
  to you, where the evidence is thin, and what to ask next." + **"Open CompanyLens →"**.
- **S8.10** — **Form load failure.** *(Ordering trap retired 2026-10-05 — retakes
  give a way back to the form.)* You no longer have to do this before S8.6. Reload
  `/work-pulse` (so the form is not cached), block
  `…/assessments/core/form` in devtools (filter Network for `form`; not the
  `work-pulse` document request itself), then:
  - *before completion*: the form fetches on arrival;
  - *after completion*: press **Retake Work Pulse** (the card makes no form request
    until you do).
  → "Loading…" for a few seconds, then a red panel: "We couldn't load Work Pulse right
  now." / "Please try again in a moment." / **"Try again"**, which refetches. The raw
  error text is never shown. (Was `G7`; fixed 2026-09-14; still holds.)
  → While a retake is open the "Not now" line stays above the panel, so there is a way
  out.
  → Press "Try again" *with the block still on*: the panel stays exactly as it is for
  several seconds with no sign anything happened. `G47`. Unblock and press it
  again: the stepper appears.


---

### S9 · The Environment Report

**Account** ACC-1 · **Route** `/environment-report` · **On prod: 16 questions, ~5 minutes.**
**Branch only: 16 + 5 optional = 21.**

Draft storage: `sessionStorage["env_report_answers"]` (the past-job form at
`/environment-report/past` keeps its own key, `env_report_answers_past`; see S25).

> **Before S9.10a only:** ACC-1 must have a career status the server can read, or the
> submit is refused *after the last question* (S9.10a). Set **"Currently employed"**
> on `/job-seeker/profile?tab=experience` ("Where are you in your career?") before you
> start, unless you are deliberately walking S9.10a.

- **S9.1** — From the Work Pulse completion card, click "Describe your job →".
  → **Branch only — not on prod until the next merge.** On the branch, finishing Work
  Pulse first shows the optional tolerance step ("How much give is there?", buttons
  "Save" / "Skip for now") before the completion card. That step belongs to S8; for
  this scenario either is fine, but what you choose there changes S10.5a. On prod
  today: the completion card appears straight away.
- **S9.1a** — The loading state, while `GET /me/situation-report` (the gate) resolves.
  → Spinner + "Loading…".
- **S9.2** — Read the intro.
  → Eyebrow "Situation Report"; H1 "Now the other half — your job"; the lead paragraph:
  - **On prod today:** "Work Pulse asked how you work. These ask what your role actually
    offers — how much of the how is yours, what the tempo is, how decisions get made.
    Twelve questions about the work, plus four about the setup. About five minutes."
  - **Branch only — not on prod until the next merge:** "… Twelve questions about the
    work, plus four about the setup, then five optional ones about how it's going.
    About five minutes."

  → Then "Describe the job as it actually is, not as it was advertised or as it ought
  to be. Both ends of every question are a legitimate way to organise work — there is
  no answer here that makes a job a good one, and the report is only useful if it has
  the real thing to work from."; then "This is a private working note. Nobody at your
  employer is told you filled it in, and nobody there can see it." + link "How this
  works, and what we hold back →"; button **"Start"**.
- **S9.3** — Start. Note the order. It is load-bearing and must not change:
  1. `stage_size`
  2. `comp`
  3. `industry`
  4–15. the **12 dimension items**, two per dimension, in this order: autonomy-1,
     autonomy-2, pace-1, pace-2, collaboration-1, collaboration-2, feedback-1,
     feedback-2, innovation-1, innovation-2, decision-1, decision-2
  16. `experienced`, straight after the twelve. Nothing sits between them: that
     position is the anti-halo measure.
  17–21. **Branch only — not on prod until the next merge:** the five optional outcome
     questions, `satisfaction`, `performance`, `engagement`, `sustainability`,
     `retention_intention`, always *after* `experienced`, never before it. **On prod
     today:** question 16 is the last one.

  → The eyebrow reads "Question {n} of 16" on prod and "Question {n} of 21" on the
  branch, with a progress bar. A selected option shows a ✓. "← Back" is hidden on
  question 1 and present after it. Options render in the authored order; do not
  expect them sorted. Within each dimension one item runs low-pole-first and the
  other high-pole-first, on purpose.
- **S9.4** — Question 1.
  → "How big is the organization you work for — the whole organization, not your
  team?" Five options, running from "An early-stage startup — a handful of people,
  still finding its footing." to "A very large enterprise — tens of thousands of
  people and many layers."
- **S9.5** — Question 2 (comp).
  → "Compared with what you could earn elsewhere doing similar work, how does this
  role pay?" Five options **plus a deliberate sixth**: "Not sure how this compares."
  Choosing it counts as answered (it is stored as null).
- **S9.5a** — Question 3 (industry, since 2026-10-01).
  → "Which industry is the organization you work for in?" with "Technology —
  software, hardware, internet or IT services." / "Finance — banking, insurance,
  investment or accounting." / "Healthcare — hospitals, clinics, pharma or health
  services." / "Retail — shops, e-commerce or consumer goods." / "Something else." /
  "Not sure, or I’d rather not say." **It is not skippable.** Next stays disabled
  until you pick one. "Not sure, or I’d rather not say." is the opt-out, and it counts
  as answered (stored as null). The earlier wording "industry (optional)" meant this
  option, not a Skip.
- **S9.6** — Question 4.
  → "How much say do you have over how your work gets done?"
- **S9.7** — Reload partway through.
  → The spinner, then **not** the intro and **not** question 1. You get the shared
  resume card: eyebrow "Situation Report", H2 "You have answers saved from last time",
  "You got through {n} of {16|21} questions. Pick up where you left off, or clear them
  and start again from the beginning.", buttons **"Pick up where you left off"** and
  **"Start over"**. "Pick up…" lands on the first unanswered question. "Start over"
  clears the draft and opens question 1. (Prod and branch alike. The old "back to
  question 1 with answers pre-selected" behaviour is gone; see §0.5.)
- **S9.7a** — Close the tab and reopen it. → Back to the intro; the draft is gone.
- **S9.8** — Question 16 (`experienced`).
  → "Overall, how well is this role working for you?" with "It isn’t working at all."
  / "It isn’t working well." / "A mixed picture." / "It’s working well." / "It’s
  working very well." It is required, and there is no Skip button. **On prod today**
  the button on this question reads **"Finish"**.
- **S9.8b** — **Branch only — not on prod until the next merge.** Questions 17–21, in
  this order: "All things considered, how satisfied are you with this job?" / "How
  well do you think you’re performing in this role?" / "How energised are you by the
  work itself?" / "Could you keep working the way you do now for another year?" / "How
  likely is it that you’ll still be in this role a year from now?" Each one shows
  "Optional. Skip any of these you'd rather not answer." under the prompt. While the
  question is unanswered, a **"Skip"** button sits beside the disabled "Next" (or
  "Finish" on question 21). Skip one and answer the rest.
  → A skipped question is stored as null, and a resumed draft does not land back on it.
  The report never reads these five. On prod today these questions do not exist.
- **S9.9** — Finish (on the branch, "Skip" on question 21 also submits).
  → Full-screen spinner + **"Building your Situation Report…"**, then navigation to
  `/situation-report`.
- **S9.10** — (If you can force a submit failure: block `POST …/me/environment-report`
  in devtools.) → Inline, above the nav row: "We couldn't save that just now. Your
  answers are still here — try again."
- **S9.10a** — **(New step.) Career status missing.** On an account whose profile
  has no career status and no current role (`endDate` "Present"/"Current"), answer
  every question and press Finish.
  → The form is replaced by a card: H1 **"One thing first: where are you right now?"**
  / "These questions read differently depending on whether you're describing the job
  you're in or the one you most recently left, and we don't have that on file yet. Set
  your career status and come straight back — your answers so far are saved." /
  **"Set your career status →"**, which goes to `/job-seeker/profile?tab=experience`
  with the career-status modal open. After you save a status, the profile asks "Go back
  to your Situation Report?". Accepting goes to `/environment-report` (the form, not
  the report), and the resume card brings you back to the last question. Nothing warns
  you about this before question 1 (`G53`).
- **S9.11** — (If `GET /me/situation-report` fails when this page loads.) → "We
  couldn't load your report right now." / "Please try again in a moment." / "Try
  again". Never the intro, never the form. While a retry is in flight you see the
  "Loading…" spinner, not a dead button. (Was `G6`; fixed 2026-09-14; verified again
  2026-10-25, prod and branch.)
- **S9.12** — **(New step.)** With a report already complete, open
  `/environment-report` again (the resubmission path S10.12 links to).
  → The same intro and the same questions. No gate. A new submission becomes the
  report's environment side. It does **not** move the Work Pulse pin (S11).


---

### S10 · The Situation Report, complete

**Account** ACC-1 · **Route** `/situation-report`

The hard rule this page enforces is **no numbers in the diagnosis.** Magnitude is one
of three words, direction is one of two phrases, and the ranking is document order.
A digit in a dimension row's name, bucket, direction or takeaway is a bug. Dates and
check-in counts in the experiment control (S12) are allowed. Prod and branch render
this page identically **except** where S10.5a and S10.1b say otherwise.

**The layout changed on 2026-09-28/29 (on prod).** The page leads with a summary:
one list of six compact rows, collapsed. Guidance opens one row at a time and sits
behind tabs. The old "At a glance" chips, the "half one person enacts" section and
the four-paragraph footer are gone.

- **S10.1** — Land on `/situation-report` from S9.9.
  → While it loads: spinner + "Loading your Situation Report…".
- **S10.1a** — **(New step.)** (If `GET /me/situation-report` fails.) → "We couldn't
  load your Situation Report right now." / "Please try again in a moment." / "Try
  again".
- **S10.1b** — **(New step.) The gate states.** Walk these before S9, on an account
  that has not reached them yet. Each one has "← Intelligence Hub" at the top.
  → Work Pulse not done: H1 **"This one needs your side first"** / "The Situation
  Report compares how you work with what your job asks of you. Work Pulse is your
  half, and it isn't finished yet." / "Work Pulse is 24 either-or questions and takes
  about eight minutes." (or, if a job description is already saved: "Your description
  of the job is saved — that half is done. Work Pulse takes about eight minutes.") /
  **"Start Work Pulse"**.
  → Work Pulse done, no job described: H1 **"One half to go"**, then the "The job, or
  your manager?" panel (S10.8) and the button **"Describe your job"**. The lead text:
  - **On prod today:** "Work Pulse told us how you work. Now sixteen questions about
    your job, in your own words. About five minutes, and the report comes back
    straight away."
  - **Branch only — not on prod until the next merge:** "Work Pulse told us how you
    work. Now sixteen questions about your job, in your own words, and five optional
    ones at the end. About five minutes, and the report comes back straight away."

  → A Work Pulse sitting the report cannot read (not walkable by hand; it needs an
  item-bank change): H1 **"We couldn't read your side"** / "The Situation Report
  compares how you work with what your job asks of you, and we couldn't read the Work
  Pulse sitting it's built on." / **"Take Work Pulse again"**. It is never a 500.
- **S10.2** — Read the header.
  → Top row: "← Intelligence Hub" on the left, **"Print this report"** on the right.
  H1 **"You, and this job"**. One lead line that names the most strained dimension:
  "{Dimension} is where you and this job sit furthest apart. The rest follow in order,
  most strain first." No count and no digit.
- **S10.3** — **Retired 2026-09-28** — the "At a glance" chip strip was removed by the
  summary-first layout (1db4e6e, on prod). The bucket words now sit on each row
  (S10.5). The chips survive only on the dashboard card (S7).
- **S10.4** — Find "Dimension by dimension".
  → An H2 "Dimension by dimension", then **one ordered list of all six dimensions**,
  aligned ones included, most strained first. It is not grouped by bucket. If more
  than one row can open, an **"Open all"** / **"Close all"** toggle sits beside the
  heading.
- **S10.5** — Read a strained row, collapsed.
  → The dimension name (Autonomy, Pace, Collaboration, Feedback, Innovation or
  Decision-making), then the bucket word, **"Straining"** or **"Notable"**, a "·",
  and the direction, **"Less than you need"** or **"More than you need"**. Below that
  is a one-line headline, for example "The work runs steadier than you would choose".
  The left edge is amber for Straining. A chevron on the right shows the whole header
  is clickable.
  → An aligned row shows "Aligned" with no direction, and the first sentence of its
  note as the takeaway. It opens to the rest of the note, or has no chevron when the
  note is a single sentence.
- **S10.5a** — **Branch only — not on prod until the next merge.** Tolerance and
  must-haves. Only appears if ACC-1 saved the tolerance step (S9.1, or
  `/trait-preferences`) **before** this report was built. Order and buckets are
  otherwise identical to prod.
  → A row for a trait you marked a must-have carries a small **"Must-have"** pill
  after its name. Must-haves sort first *within* their bucket and never jump a bucket.
  → An aligned row that is aligned only because of your stated range carries one
  extra line: "This isn't quite what you prefer, but it's inside the range you said
  you're fine with."
  → On prod today neither appears, and buckets use the fixed bands.
- **S10.6** — Open a strained row.
  → The diagnosis paragraph, then the registers as **three tabs, on every strained
  row, every dimension** (all twelve cells carry all three): **"Try a change"** /
  **"Negotiate it"** / **"If it won't move"**. The first tab is selected, and arrow
  keys move between tabs.
  → "Try a change": the experiment name (bold), the experiment, a bulleted list of
  steps, then a row labelled "How you'll know it worked" with the signal, then the
  experiment control (S12).
  → "Negotiate it": rows "Who, and where" / "How to open" / "What to say" (scripts in
  curly quotes, italic) / "If the answer is no".
  → "If it won't move": rows "Why it's usually fixed" / "What staying costs" / "What
  that means".
  → **Print check:** the print view shows every tab's panel, each under its own
  heading, and every row expanded.
- **S10.7** — Open the Feedback row, if it is strained, and the Autonomy row.
  → Feedback: under the tabs, a panel that reads "How feedback reaches you is set by
  one person more than by the company, so the playbook for it lives in the Manager
  Decoder." + **"Profile your manager"** (or **"Open your playbook"** once a manager
  profile exists).
  → Autonomy: a similar panel with the server's cross-reference paragraph and the
  same CTA.
- **S10.8** — Read the panels under the list.
  → Two side-by-side panels. First, "How work's been working for you", with zero
  check-ins: "You haven't checked in on Pulse yet." + link "Check in". After one
  check-in it shows a single dot + "One check-in so far — the line fills in as you add
  more." + "See your full trend". If the fetch fails: "We couldn't load your Pulse
  check-ins just now." + "Try again". Second, **"The job, or your manager?"** with no
  manager profile: "Some of what feels like the job may be your manager, and from the
  inside the two look the same. The Manager Decoder tells them apart." + **"Profile
  your manager"**. With one: "Some of what feels like the job may be your manager.
  Read your manager playbook alongside this." + **"Open your playbook"**.
- **S10.9** — Read the footer.
  → H2 **"About this report"**, then the server's notice ("This guidance is general,
  not personal. Every one of these suggestions was written before we knew anything
  about you; … It is a private working note, and nobody at your company can see
  it."), then "It isn't advice to leave or to stay. You can see things about your
  situation that it can't, so what to do with it is your call.", then "It reads one
  Work Pulse sitting and stays there, so retaking Work Pulse won't change it until
  you ask." Then the pin button (S11), the link **"Tell us about the job before this
  one →"** (only until the past-job report is filed; see S25), and "How this works,
  and what we hold back".
- **S10.10** — Click **"Print this report"**. → The browser print dialog opens. In
  the preview, every row should be expanded and every tab's panel present. The back
  link, the buttons and the banners should be hidden. This is a document people will
  actually print.
- **S10.11** — If every dimension came back aligned:
  → The lead line reads "Nothing is straining: on every dimension we measure, you and
  this job are set much the same way." and the list shows six "Aligned" rows. (The
  boxed "Nothing is straining. On every dimension we measure, you and this job are set
  much the same way — which is uncommon enough to be worth noticing rather than
  assuming." is still in source, but the current-role report always sends all six
  rows, so that box can no longer render here. Not a defect; it is dead copy.)
- **S10.12** — (After S13.4.) Log a Pulse event, then come back here.
  → A banner under the header, worded from the newest event, e.g. "You logged a new
  manager since this report — does your Situation Report still describe this job?" +
  **"Describe it again"** (no arrow). The other leads: "Your team went through a reorg
  since this report" / "Where you work changed since this report" / "Your role
  changed since this report" / "Something about this job has changed since this
  report". Only describing the job again clears it.
- **S10.12a** — **(New step; on prod since 2026-10-02.) Career-status change.** On
  the Experience tab, switch ACC-1 to "Currently unemployed", then come back here.
  → A banner: "Your career status says you've moved on from this job since this
  report. Describe it again and the report will turn to what to look for next." +
  **"Describe it again"**. The report itself does **not** turn forward-facing. **Switch
  back to "Currently employed" without resubmitting.** The banner clears, because the
  flag is computed from the live status.


---

### S11 · Recalibrating the pin

**Account** ACC-1 · **Route** `/situation-report`, footer ("About this report")

- **S11.1** — Find the pin control under the footer's three paragraphs.
  → A quiet button: **"Re-read this against my latest Work Pulse"**.
- **S11.2** — Click it without having retaken Work Pulse.
  → "Re-reading…", then **"Already reading your most recent Work Pulse sitting —
  nothing moved."** This is a **success**, not an error (§0.5). Nothing is written,
  nothing is logged, and the report does not refetch.
- **S11.3** — Retake Work Pulse (S8.8a) **after** this report exists, come back here,
  and press the button.
  → "Re-pinned. This report now reads your most recent Work Pulse sitting." The report
  refetches, and rows may reorder or change bucket. (A retake made *before* the first
  Environment Report would already be the sitting the report was built on, so it
  would give S11.2's answer.)
- **S11.4** — (Not reachable from the UI. The button only renders on a complete
  report, which implies a sitting.) With no core sitting, the endpoint answers 409
  `no_core_sitting`, and the footer would read: "There is no Work Pulse sitting to pin
  to yet."
- **S11.5** — Any other failure → "We couldn't re-read it just now. Please try again
  in a moment."
- **S11.6** — **Branch only — not on prod until the next merge.** (New step; D-15
  ruling 2026-10-14, "a change to tolerance reaches the Situation Report at the next
  fixed sitting".) Change your answers at `/trait-preferences` (the tolerance step
  says "Optional, and you can change it any time."), then come back.
  → The report does **not** change. Pressing Re-read gives S11.2's "nothing moved",
  because tolerance has no re-pin of its own. The change applies only after a **new
  Work Pulse sitting** and then Re-read, per S11.3. Nothing on the page says this
  (`G54`). Exception: if this report was built with no tolerance answered, the
  *first* answer given after the pinned sitting applies once. On prod today there is
  no tolerance step and no `/trait-preferences` route.


---

### S12 · Condition experiments

**Account** ACC-1 · **Route** `/situation-report`. **There is no `/experiments` page.**
The feature lives entirely inside the complete, current-role Situation Report, and
since the 2026-09-28 layout it sits **inside a collapsed row's "Try a change" tab**.

- **S12.1** — **Do S12.7 first** (below). Starting any experiment, even one you later
  abandon, permanently makes the "Your experiments" section appear on this account.
  Then open a strained row and stay on its "Try a change" tab.
  → Under the signal: a button **"Try this for two weeks"** (no arrow).
- **S12.2** — Start it.
  → That control becomes "Running since {date}, through {date}." with an **"Abandon"**
  link-button, then "The readout compares your Pulse check-ins before and during these
  two weeks, so it only works if you keep checking in." + link "Check in now".
- **S12.3** — Scroll to "Your experiments". It sits under the trend and manager
  panels, above "About this report".
  → H2 "Your experiments". A row reads "{Dimension} — {experiment name}" with the
  phase label **"Running"** and "{start date} – {end date}".
- **S12.4** — Open a **second** strained row's "Try a change" tab.
  → "Try this for two weeks" is **disabled**, with the hint "Only one experiment can
  run at a time — finish or abandon the other one first." **Changed since af0b351:**
  if the server still answers 409 `experiment_already_active` (the list was stale,
  e.g. a start in another tab), the cell is no longer silent. It shows "Another
  experiment is already running — finish or abandon that one first. We've refreshed
  this page to show it." and refetches.
- **S12.5** — Click "Abandon".
  → **No confirmation and no success message** (verified 2026-10-25). The cell
  immediately offers "Try this for two weeks" again, because an abandoned attempt is
  treated as never having happened. The Abandon button is disabled while the request
  is in flight. **If the request fails, nothing is shown at all** (`G51`).
  Whether one click with no confirm is acceptable is still Sebastian's call: it is
  reversible in practice (start again), but the two weeks restart.
- **S12.6** — Check "Your experiments" again.
  → The abandoned one is listed with phase label **"Abandoned"**. Abandoning is
  idempotent on the server: a repeat is a 200, not an error.
- **S12.7** — **Before you have ever started one**, look for the experiments section.
  → **There is nothing at all**: no heading, no invitation, no empty state (verified
  2026-10-25, prod and branch). The only way in is a strained row → expand → "Try a
  change". That is one level deeper than when this step was written, so a user who
  never opens a row never learns the feature exists.
- **S12.8** — (Loading and failure.) While `/me/experiments` loads, the "Try a change"
  tab shows a quiet "Loading…" in place of the start button. If the load fails, no
  start button appears anywhere, and a "Your experiments" section appears with "We
  couldn't load your experiments right now." + "Try again". (Was `G5`; fixed
  2026-09-14; verified again 2026-10-25.)
- **S12.9** — (After two weeks, or on seeded data.) An ended experiment reads out in
  words only: "Your numbers moved up over those two weeks." / "Your numbers moved down
  over those two weeks." / "Your numbers didn't move much over those two weeks." /
  "There weren't enough check-ins on one side of this to say anything yet.", plus
  "That's based on {n} check-ins before, {m} after." ("check-in" when n is 1). Never a
  delta. The list label is **"Ended"**, and the cell offers **"Try this again for two
  weeks"** under the readout.
  → **Since 2026-10-02 (53c0e49, on prod):** an ended experiment no longer blocks the
  next start. Starting another one on a different row after the end date must work,
  not 409.


---

### S13 · The Pulse

**Account** ACC-1 · **Routes** `/pulse`, `/pulse/trend` · **No preconditions** ·
*Re-derived 2026-10-25 from `causal_bayesian_model` (6e51713); production is `origin/main` 02707ab. Every S13 frontend file is byte-identical between the two, so every step below is on prod except where marked **Branch only**.*

- **S13.1** — Open `/pulse`.
  → While the questions load: spinner + "Loading…". (If that fails: "We couldn't load this check-in right now." / "Please try again in a moment." / "Try again".)
  → Eyebrow "Pulse check-in"; H1 **"Three questions about this week"**; "About a
  minute. Pick the number closest to true for you."
  → Four rows on one screen: three server-chosen dimension items (round-robin, 3 of the 5 dimensions per check-in) plus the `experienced` item **last**. Each is a stem, five circular 1–5 radios, and a low/high anchor. The five dimension stems are: "How well could you focus without interruption this week?" (Constantly pulled away / Stayed focused), "How sustainable did this week's workload feel?" (Draining / Comfortable), "How much did your surroundings help you do good work?" (Worked against you / Worked for you), "How much of your work got real notice this week?" (Went unnoticed / Got noticed), "How well did this week's pace match what works for you?" (Badly mismatched / Matched well). The last row is always "This week, how well is work working for you?" (Not working / Working very well).
- **S13.2** — Answer three of four.
  → "Done" stays disabled until all four are answered. It is also disabled while the page's background history fetch is still loading (so the confirmation never compares against a history that had not arrived), and reads "Saving…" while the POST is in flight.
- **S13.3** — **Reload before submitting.** → Everything is lost: the answers live in component state only. Re-verified at HEAD: the Pulse check-in is still the one instrument with **no draft persistence** and **no resume prompt** (every other instrument now asks "You have answers saved from last time"). Expected, not a gap. The reload serves the *same* four items, because the server's choice is keyed off your check-in count.
- **S13.4** — Submit your first check-in.
  → The form is replaced in place: eyebrow "Logged"; H1 **"That's your first pulse"** / "Nothing to
  compare it to yet. Check in again next week and you'll start seeing how it moves."
  Exits: "See your trend →" and "Done" (Done goes to `/job-seeker/dashboard`).
- **S13.4a** — *(New. Cannot be triggered by hand.)* If the history fetch failed or had not landed but the server says this is not your first check-in, the confirmation does not claim a first: H1 **"Check-in logged"** / "Saved. Your trend has the comparison with your earlier check-ins." Same two exits. (Fix F10, 2026-10-02.)
- **S13.5** — Check in a second time. **The confirmation screen has no "check in
  again" button** — its two exits are "See your trend →" and "Done" only. Navigate
  back to `/pulse` directly (retype the URL, the dashboard Pulse card's "Check in →", or the trend page's "Check in →" link).
  Nothing server-side blocks a second submission right away; the missing button is
  a UI nudge toward weekly use, not a real gate.
  → H1 **"Two points make a trend"** + a two-point sparkline + "How work's working for
  you is {up|down|about the same} from last time."
- **S13.5a** — *(New.)* **Stale form.** Open `/pulse` in two tabs; submit in tab A; submit in tab B. The server has moved to the next set of dimensions, so B's POST is refused with 422 `invalid_checkin`.
  → In tab B: red alert "This check-in was out of date, so we've refreshed the questions. Check your answers and tap Done again." The questions are refetched in place; answers are keyed by item id, so any item still shown keeps its selection and the rest are blank (Done disabled until they are answered). Any other submit failure: "We couldn't save that just now. Your answers are still here — try again."
- **S13.6** — Check in a third time. → H1 **"This week vs. last week"** + "How work's working for you is {up|down|about the same} from last week." The chart now plots **up to 12 recent check-ins, oldest left, this one at the end** (it used to plot only two dots after a third check-in; fixed in 9b638d0). *Note: the wording says "last week" whatever the real gap was; see G57.*
- **S13.7** — Open `/pulse/trend`.
  → "Loading your pulse…", then top row "← Dashboard" and "Check in →"; eyebrow "Pulse"; H1 "Your pulse"; "{n} check-in(s) logged." ("1 check-in logged." singular); "How work's been working for you" with
  the line; then "By dimension" with five cards labelled **Focus / Workload /
  Surroundings / Recognition / Pace** (fragmentation, sustainability, environmental_friction, recognition_friction, work_pace — verified against source). Sparse coverage is by design — only three of
  five dimensions are asked per check-in, so expect "Not answered yet." on some, and "One answer so far." on a card with a single point.
  → Failure: "We couldn't load your pulse right now." + "Try again".
- **S13.7a** — *(New.)* With exactly **one** check-in the line card shows the single point and "One check-in so far — the line fills in as you add more." Logged changes are **not** drawn on the line at one check-in (events only annotate once there are two or more); they still appear in the list below.
- **S13.8** — Click "+ Log a change".
  → Type chips: "New manager" / "Reorg" / "Remote / office change" / "Role change" /
  "Something else"; a note textarea (placeholder "Add a short note (optional)") with a "{n}/280" counter; "Save" / "Cancel". "Save" is disabled until a chip is chosen; "+ Log a change" is hidden while the form is open.
- **S13.9** — Log a "New manager" event with a note.
  → It appears under "Changes you've logged" with date, label and the quoted note,
  and (with two or more check-ins) it annotates the experienced line. With no events: "No changes logged yet." **Then go back to S10.12** — the Situation
  Report should now show the resubmission banner. Failure: "We couldn't save that just now. Try again." (the UI does not branch on the event error code).
- **S13.10** — Type 281 characters in the note. → **Clipped, not rejected**: the textarea silently truncates at 280 and the counter stops at "280/280".
- **S13.11** — Find "Check-in cadence".
  → While loading: "Loading your cadence…" (never four unpressed buttons). Failure: "We couldn't load your cadence right now." + "Try again".
  → Exactly four options: **"Weekly"**, **"Every two weeks"**, **"Monthly"**, **"Off"**; the current one is pressed (a fresh account: "Weekly").
  (Monthly added by ruling 2026-09-14, `G21`; verified at HEAD.)
- **S13.12** — Set it to "Off", then back to "Weekly".
  → Each is a single PATCH with **no confirmation step** (a product decision); the buttons are disabled while one is in flight. Error
  copy if it fails: "We couldn't save that just now. Try again." (shown for every failure including 422 `invalid_cadence`; the UI does not branch on the code).
- **S13.13** — (Cannot be triggered by hand; verify by reading or by seeding.) After
  **three consecutive unanswered prompts**, the **fourth** prompt drops you to
  monthly and carries one extra paragraph — in the email: "We've slowed these check-ins down to once a month since it's been quiet -- no rush, and you can check
  in any time." (two hyphens, in the HTML body) and on `/pulse/trend`: "We've slowed these down to once a month since
  it's been quiet — no rush, and you can check in any time."
  → In that state **"Monthly" appears selected** and the note above is shown (`auto_slowed: true`).
  Checking in does not change the cadence (by ruling, 2026-09-14). Picking any
  cadence — including "Monthly" itself — clears the note and the anti-nag counters; a user who chose Monthly
  never sees it. A user already at monthly who goes quiet again gets a plain monthly
  prompt, never a second "slowed down" paragraph. (Was `G21`; closed 2026-09-14, re-verified 2026-10-25.)
- **S13.13a** — *(New. Cadence rules, for reading or seeding.)* Intervals are counted in **UTC calendar days**: weekly 7, every two weeks 14, monthly 30. The clock starts at the **later** of your last prompt and your last check-in (so a voluntary check-in three days ago buys a full quiet interval), and a user with **zero** check-ins is never prompted at all. "Off" is never due. The prompt email: subject and H2 "How's work been going?", eyebrow "Pulse check-in", "Three quick questions, about a minute.", button "Check in" linking to `/pulse`. No streak language by design. Whether the cron has ever sent is still unverified (**G18**: no `flask pulse send-prompts` block in `render.yaml`; created by hand in the Render dashboard at deploy 2, no run log seen).
- **S13.14** — Empty state check (use a fresh account): `/pulse/trend` with zero
  check-ins → "Nothing to show yet. Your trend builds from check-ins — it takes about
  a minute." + "Check in now →". "Changes you've logged" and "Check-in cadence" still render below it (the page degrades per section, not as one gate).
- **S13.15** — *(New.)* The dashboard Pulse card (`/job-seeker/dashboard`). Zero check-ins: "Keep a pulse on work" / "A short weekly check-in — three questions, about a minute. It gets more useful the more you do it." / "Take your first check-in →". With check-ins: heading "Your pulse this week" if the latest is within seven days, otherwise "Your pulse"; "Last check-in {date}." then "How work's working for you is {up|down|about the same} from before." (or, with one check-in, "One check-in so far — a trend builds after the next one."); links "See your trend →" and "Check in →". Failure: "We couldn't load your pulse right now." + "Try again" + "Check in →" (never the first-check-in invitation).
- **S13.16** — **Branch only — not on prod until the next merge.** *(New; not visible in the UI.)* Each history row now carries `company_link_id` (the id of your active "I took this job" company link when the check-in was recorded, else `null`) — `GET /me/pulse/history` in devtools. Nothing on screen changes; the `POST /me/pulse/checkins` response does not carry it. On prod the field is absent.


---

### S14 · The Manager Decoder

**Account** ACC-1 · **Routes** `/manager-match`, `/manager-match/results`, `/manager-profile`, `/manager-profile/playbook`

*Re-derived 2026-10-25 from `causal_bayesian_model` (6e51713). `git diff origin/main..HEAD` is empty for all four pages, their hooks, the question banks and `manager_match/`, so every step below is on prod. The only branch-side change near this lane is the CompanyLens card on `/intelligence` (S16's), not the Manager cards.*

**The precondition chain is ManagerMatch (15) → Manager Profile (16) → Playbook**, and
`/manager-profile` enforces the first link **before question 1** (ruling
2026-09-14; frontend gate only, the API still accepts a profile without ManagerMatch and answers `playbook: null`). All three pages are reached from the Intelligence hub cards ("✦ Unlocked · ManagerMatch™" with "View results →" and "Retake"; "✦ Unlocked · Manager Decoder" with "View your playbook →" and "Retake"). The two "Retake" buttons navigate with `{ retake: true }`.

- **S14.1** — **Before taking ManagerMatch**, go straight to `/manager-profile`.
  → You never reach a question. The page checks `GET /me/manager-playbook` first (a
  brief "Loading…"), and on 409 `no_manager_match` renders the hand-off in place of the
  intro: H1 **"Take ManagerMatch first"** / "Your playbook diffs what you need from a
  manager against how your manager actually works. Take ManagerMatch so there's
  something to compare your manager profile against." / "Take ManagerMatch →" (to `/manager-match`).
  Nothing is submitted, nothing is saved. A partial or complete draft in
  sessionStorage does not bypass it (the auto-submit of a complete draft is withheld until the gate has resolved to "go ahead").
  → If that check fails for another reason: "We couldn't load your manager profile
  status right now." / "Please try again in a moment." + "Try again" — never the form. **Verified at HEAD (code + test).** "Go ahead" is either 409 `no_manager_profile` (the ordinary first-time state) or a 200 (a playbook exists, i.e. a retake).
- **S14.2** — Take ManagerMatch.
  → Eyebrow **"Manager fit"** *(was "WorkPulse Pro" in the 2026-09-14 draft; the Pro label was removed because ManagerMatch is free and live and Pro is not purchasable)*; H1 "ManagerMatch™"; "Leadership and management alignment"; "Discover which management styles
  bring out your best — and which create friction."; amber warning "Each choice is
  final — there is no going back."; button "Start ManagerMatch™".
  → 15 forced choices, each "Question {n} of 15" with a dot row, prompt line "Which feels more like you?", two large cards (A and B); **no back button**.
- **S14.2a** — *(New; replaces the old "resumes at the right index" claim — see S14.7.)* **Reload mid-quiz.** → The intro is replaced by the shared resume card: eyebrow "ManagerMatch™"; H2 **"You have answers saved from last time"**; "You got through {n} of 15 questions. Pick up where you left off, or clear them and start again from the beginning."; buttons "Pick up where you left off" (lands on the first unanswered question) and "Start over" (clears the draft and the cached result, goes to question 1). The draft is `mm_answers:{userId}` in `sessionStorage` (per user since 92be5c8).
- **S14.2b** — *(New.)* **Retake** from the Intelligence hub. → `/manager-match` with `retake: true` skips the resume card, wipes the draft and the cached result, and shows the normal intro. Finishing replaces the stored result and **refreshes the cached playbook** (a retake changes the diff), so `/manager-profile/playbook` does not show a pre-retake playbook. Visiting `/manager-match` directly with no draft and no `retake` flag also shows the intro with **no warning that completing will replace your results**.
- **S14.3** — Finish it.
  → Spinner: "Analysing your management preferences…" / "This usually takes under a minute. You can leave this page open." This one is scored by a background job (deterministic archetype and dimension scores, then an OpenAI-written narrative; needs `OPENAI_API_KEY`), not on the request. On success the draft is cleared and you land on `/manager-match/results`.
  → On failure: "We couldn't generate your results right now." + the scorer's own message if it wrote one, otherwise "Please try again in a moment." + "Try again".
- **S14.3a** — *(New.)* **Reload while the job is running.** → The draft is still complete, so the page shows "Checking for your results…", asks `GET /me/assessments/manager_match/result`: a stored result sends you to the results page (and drops the draft — no silent re-score of a finished sitting); a 404 ("not finished yet") enqueues the draft **again** (no dedupe, so a second LLM job may run beside the first — see G58); any other error goes to the results page with its own error card.
- **S14.4** — Read the results.
  → "Loading your results…", then back link "← Intelligence Hub"; eyebrow "Your ManagerMatch™"; H1 the archetype (one of "The Autonomist", "The Operator", "The Challenger", "The Nurtured", "The Collaborator"); a one-line description; a narrative card; "How you scored" with four dimensions (Autonomy, Feedback
  Style, Relationship, Growth Focus) as bars banded Low (<0.4) / Mid (≤0.65) / High, "What to look for", "Watch
  out for", then the bridge: "ManagerMatch tells you what you need. The Manager
  Decoder tells you where your actual manager stands against it." + "Now profile your
  actual manager →", then "Back to Intelligence Hub". With no stored result the page redirects (replace) to `/manager-match`. Fetch failure: "We couldn't load your results right now." + "Try again". *Expect "The Operator" often — see G56.*
- **S14.5** — Return to `/manager-profile/playbook` now.
  → Second gate: H1 **"Profile your manager"** / "You've completed ManagerMatch. Now
  tell us how your actual manager works, so we can build your playbook." / "Profile your manager →" (Note neither
  gate uses the words "unlock" or "locked" — deliberate.) Before ManagerMatch the same URL shows the S14.1 hand-off ("Take ManagerMatch first"). While loading: "Loading your playbook…"; other failure: "We couldn't load your playbook right now." + "Try again".
- **S14.6** — Take Manager Profile properly.
  → Eyebrow "Manager Decoder"; H1 "Profile your actual manager"; "16 questions about
  how your manager actually operates — not how you feel about it. We diff this against what you told ManagerMatch you need, and turn the distance into a private playbook for working with them."; amber "Each choice
  is final — there is no going back."; button "Start".
  → 16 questions ("Question {n} of 16"), prompt "Which is closer to how your manager works?", **no back
  button anywhere**.
- **S14.7** — Answer 8, then reload. *(Rewritten 2026-10-25: the old claim "resumes at question 9" and "the inconsistency with S8.4" are both superseded.)*
  → After the gate's "Loading…", the shared resume card appears: eyebrow "Manager Decoder"; H2 "You have answers saved from last time"; "You got through 8 of 16 questions. Pick up where you left off, or clear them and start again from the beginning."; "Pick up where you left off" lands on **question 9**; "Start over" clears and starts at 1. Work Pulse, Environment Report and FocusType use the same card, so there is no longer a resume inconsistency between instruments. The draft key here is the **unscoped** `mp_answers` (see G59).
  → A *complete* draft (16 answers, e.g. a reload right after question 16) is not offered a resume: once the gate clears it is re-submitted automatically.
- **S14.8** — Finish. → Spinner "Scoring your manager profile…" then the playbook. Failure: "Something went wrong submitting your answers." / "Please try again — your answers are still saved." / "Try again". Scoring is deterministic and instant (no job).
- **S14.9** — Read the playbook.
  → "← Intelligence Hub" and "Print this playbook"; eyebrow "Manager Decoder"; H1 "Your managing-up playbook"; a privacy notice, verbatim: "This playbook is yours. It was built from two things you told us: what you need from a manager, and your own read on how your manager works. It is a private working note, not an assessment of them. Nobody at your company can see it, your manager is never shown it and is never told it exists, and nothing in it is shared with anyone. It describes the fit between two ways of working, both of which are legitimate — it is not a verdict on either of you."; "Where to focus first" as
  ordered chips ("1. Autonomy", widest gap first); "The full map" in fixed order Autonomy, Feedback Style, Relationship, Growth Focus, with grind cards (badge "Notable"/"Acute", "More than you
  need"/"Less than you need", a headline, "Why", "The ask", "Bring to your 1:1", "What to say" in quotes, and for under-supplied autonomy, feedback and growth a small grey caveat that the cause may be circumstance rather than your manager) and mesh cards (badge "Mesh" + one sentence).
  → If nothing grinds: "No grinds — your manager profile meshes with what you need
  across all four dimensions." The Intelligence hub card then reads "All four dimensions mesh"; otherwise "{n} dimension(s) to work on".
- **S14.10** — Click "Print this playbook". → Check the print layout (the back links, print button and footer button are hidden in print; background turns white).
- **S14.11** — Go back to `/situation-report` (S10.8).
  → *(Copy corrected 2026-10-25; the 2026-09-14 text is no longer in the source.)* The manager side-panel, headed "The job, or your manager?", reads the *has-profile* variant: "Some of what feels like the job may be your manager. Read your manager playbook alongside this." + "Open your playbook" (→ `/manager-profile/playbook`); without a profile it reads "Some of what feels like the job may be your manager, and from the inside the two look the same. The Manager Decoder tells them apart." + "Profile your manager". The per-dimension cross-reference notes and the dashboard Situation card follow the same switch ("Open your playbook" / "Open your manager playbook" vs "Profile your manager"). *(S10.8's wording should be checked against this by the S10 re-deriver.)*


---

### S15 · FocusType

**Account** ACC-1 · **Routes** `/focus-type`, `/focus-type/results` · **No
preconditions** · Identical on prod and branch (no diff under `focustype/` or the two
pages).

Draft storage: `sessionStorage["focus_type_draft:<your user id>"]` — completed scenes
only (since 2026-10-02, 7dfe752; it used to be unscoped and was picked up by whoever
signed in next).

- **S15.1** — Open `/focus-type`.
  → A bare spinner while the profile loads (so a returning user is never shown
  "Begin"), then: eyebrow "FocusType™"; H1 "Discover how you actually focus."; "Most
  people don't know how their attention really works — they just adapt to whatever
  environment they're placed in. FocusType is a five-scene workday simulator that
  reveals your natural focus patterns, energy rhythms, and the conditions where you do
  your best work."; "You'll move through five short interactive scenes — no questions,
  just decisions. Your behaviour across all five produces one of six FocusType
  archetypes."; amber box "Each choice is final. There's no going back." + "Each scene
  commits when you complete it — treat every decision as real."; "⏱ Takes about 4
  minutes"; button "Begin".
- **S15.2** — Walk all five scenes; "Scene {n} of 5" with a five-segment indicator.
  **Do at least one on a phone.** Scenes 1, 2 and 5 now take touch (press and hold)
  and keyboard (Space / arrows / Space).
  - **Scene 1 · "The Morning Stack"** — "It's 9am. Six things are waiting for you.
    Drag them into the order you'd actually tackle them — top to bottom." Button reads
    "Drag the cards to set your order first" (disabled) until you have dragged at
    least once — even if the default order is already yours — then "Lock in my
    priorities →".
  - **Scene 2 · "The Inbox Flood"** — "Ten things just landed. Drag each card into a
    bucket: NOW, LATER, or IGNORE." Button "Sort all {n} remaining cards to continue",
    then "See what this says about you →". **That label leads to scene 3, not to a
    result** — copy note for Julie, not a bug.
  - **Scene 3 · "The Free Day"** — "You have 4 uninterrupted hours — no meetings, no
    Slack. It's all yours. Allocate the time across five activities however feels
    natural to you." Five sliders; pill "{x} hrs remaining" / "{x} hrs over" /
    "Perfect — exactly 4 hours"; button "Add {x} more hours to continue" / "Reduce
    sliders to exactly 4 hours" / "That's my day →".
  - **Scene 4 · "The 2:30 Crash"** — an explainer first ("How it works", an example
    card, "↑ this is what you'll see — the bar drains over 3 seconds") and **"I'm
    ready — start the 2:30 Crash →"**. Then eight cards, 3 seconds each, "Do it now" /
    "Push to tomorrow", "No click in 3 seconds → goes to tomorrow automatically".
    Letting every card time out is legal and no longer reads as "fastest".
  - **Scene 5 · "The Evening Build"** — "Drag blocks onto the 6pm–10pm timeline to
    plan your evening. Fill at least 3 hours to continue. Blocks can't overlap — not
    everything needs to fit." Tray "{n} blocks available — drag onto the timeline" /
    "All blocks placed ✓"; button "{n} more slots needed to continue" / "That's my
    evening →".
- **S15.2a** — *(New, 7dfe752.)* Finish scenes 1–2, then **reload** mid-scene 3.
  → Eyebrow "FocusType™"; "You have answers saved from last time"; "You got through 2
  of 5 scenes. Pick up where you left off, or clear them and start again from the
  beginning."; "Pick up where you left off" (→ "Scene 3 of 5") / "Start over" (→
  "Scene 1 of 5", draft cleared). The scene you were *in* is not saved — only finished
  ones. Close the tab instead → gone. Sign out → swept.
  → "Start over" sits uneasily with the intro's "Each choice is final. There's no going
  back." Note it, don't file it.
- **S15.3** — Finish scene 5.
  → Spinner + "Calculating your FocusType…", then `/focus-type/results` (replace —
  Back does not restart the simulator).
- **S15.4** — Read the result.
  → "← Intelligence Hub"; eyebrow "FocusType™"; "Your FocusType"; the archetype name
  as an H1, one of: Deep Diver / Sprint & Reset / Reactive Flow / Structured Builder /
  Pressure Igniter / Collaborative Charger, with its one line (e.g. Deep Diver: "You do
  your best work when nothing breaks your flow."); "Your workplace recommendations";
  "What drove your result" with six bars (Deep Focus, Burst Energy, Reactivity,
  Structure Need, Urgency Drive, Social Fuel) sorted high to low **and the raw number
  printed at the end of each bar**; "Back to Intelligence →".
  → **The tension, and the verdict.** FocusType shows bars and digits; Work Pulse
  shows nothing. `/trust`'s aside "Then why does FocusType show me a result?" answers:
  "Because that asymmetry is deliberate. FocusType and ManagerMatch hand you something
  to read, since they are built to be read and acted on by you. Work Pulse is the
  instrument the matching model reads, so Work Pulse is the one that stays quiet." —
  **It holds** for the company match model, which reads only Work Pulse (core). One
  thing it leaves out: the FocusType archetype is part of the profile Path
  Intelligence's deep fit reads (`path_fit_repository`, `"focus_type"`), so a FocusType
  retake can move path fit. Low stakes; judge whether the aside needs a clause.
- **S15.5** — Revisit `/focus-type`.
  → Spinner, then redirected to the results, not the intro. **Exception:** a saved
  result *plus* an unfinished draft (a retake in progress) gets the S15.2a prompt
  instead.
- **S15.5a** — *(New.)* From `/intelligence`, the FocusType card ("✦ Unlocked ·
  FocusType™", your archetype, "View results →") → press **"Retake"**.
  → The intro with "Begin", draft cleared. Finish scene 1, reload: the resume prompt,
  not a bounce to the old result. Leave without finishing: the old result stands.
  The hub is the only place that offers the retake.
- **S15.6** — On submit failure (block `…/assessments/focus_type/submissions`, finish
  scene 5): "Something went wrong submitting your results." / "Please try again — your
  scene answers are still saved." / "Try again" (resends the saved scenes; nothing to
  replay). Reloading here instead: the prompt says 5 of 5, and "Pick up where you left
  off" submits at once.


---

### S16 · The Intelligence hub and its satellites

**Account** ACC-1 · **Routes** `/intelligence`, `/solverah-profile`, `/intelligence/paths`,
`/quiz-insights`, `/career-quizzes/*`, `/career-job-search`, `/trust` ·
**Re-derived from HEAD 2026-10-25.** Differences between the branch and prod are marked
inline; they are the CompanyLens hub card (S16.6), the `/trust` copy and date (S16.13).

- **S16.1** — Open `/intelligence` **before** Work Pulse. **Deferred to ACC-3
  2026-09-15** — ACC-1 already has Work Pulse by the time this scenario is reached,
  and S7 never actually visited `/intelligence`, so this was never incidentally
  covered. See S21.1's consolidated pre-Work-Pulse checklist.
  → A hard gate, and nothing else on the page renders: "Complete Work Pulse to unlock
  your profile." / "Work Pulse takes about 8 minutes and unlocks your Solverah profile
  — the foundation everything else in the ecosystem builds on." / "Start Work Pulse".
  The gate reads `wp_v2_completed` (the 24-item instrument).
- **S16.1a** — While the hub loads, and if it fails.
  → Spinner and "Loading your profile…". If the Work Pulse result read fails: "We
  couldn't load your profile right now." / "Please try again in a moment." / "Try again".
  (A failed profile *document* does not show this; it goes to the route error boundary.)
- **S16.2** — Open it as ACC-1 (post-Work Pulse).
  → Eyebrow "Your Intelligence Hub"; H1 "Everything we know about how you work."; "Your
  profile grows as you complete more of the Solverah ecosystem."; a step strip (Work
  Pulse Lite, Work Pulse, FocusType, ManagerMatch, CompanyLens, Future Path).
- **S16.2a** — Read the step strip.
  → Ticks (✓) appear for Work Pulse (done), FocusType and ManagerMatch (when you have a
  result). **"Work Pulse Lite" never ticks for a new account** (the 12-question quiz it
  names was retired; only a legacy completer sees a tick), and **CompanyLens and Future
  Path never tick for anyone**; the code has no completion test past step four. On the
  branch, where CompanyLens is live, an unticked CompanyLens step reads as "not done"
  even after you have used it. `G39`.
- **S16.3** — Read the Work Pulse card.
  → "✦ Unlocked · Work Pulse™" / "Work Pulse complete" / "It’s powering your matching
  in the background. There’s no score to check and nothing to optimise — what it
  learned about how you work is already shaping which environments we put in front of
  you."
- **S16.4** — Read the Situation Report card. → Should reflect your actual state. Three
  possible cards, each under the Work Pulse card:
  → Complete: "✦ Situation Report" / "Your Work Pulse and your description of your job,
  read against each other — where the two are set the same way, and where they pull
  apart." / "View your Situation Report →".
  → Not yet described (and not `first_job`): "✦ Situation Report" / "Work Pulse knows how
  you work. What it can’t tell you on its own is how far your current job sits from that.
  Sixteen questions about the role close the gap and turn the two halves into your
  Situation Report." / "Describe your job →" (to `/environment-report`).
- **S16.4a** — With a complete current report and no past-job report filed, and a status
  other than `first_job`: a further card.
  → "✦ Your earlier job" / "Tell us about the job before your current or most recent one.
  It won’t change your Situation Report — it helps Solverah learn which gaps matter most.
  About five minutes." / "Describe your earlier job →" (to `/environment-report/past`).
  Hidden for `first_job` and once the past report is filed.
- **S16.5** — Read the FocusType and ManagerMatch cards.
  → Done: "✦ Unlocked · FocusType™" (or "ManagerMatch™") with the archetype name, "View
  results →" and "Retake". Not started: "FocusType™" / "Attention, focus, and energy
  patterns" / "Understand how your attention works and which environments protect it." /
  "Start FocusType™ →"; "ManagerMatch™" / "Leadership and management alignment" /
  "Discover which management styles bring out your best — and which create friction." /
  "Start ManagerMatch™ →".
- **S16.5a** — Read the Manager Decoder card. → Post-S14: "✦ Unlocked · Manager Decoder"
  with "{n} dimension(s) to work on" or "All four dimensions mesh", plus "View your
  playbook →" and "Retake". Before that, three other states, driven by the two 409 codes
  from `GET /me/manager-playbook`:
  → ManagerMatch not taken (`no_manager_match`): "Manager Decoder" / "A private playbook
  for working with your actual manager" / "Take ManagerMatch first — the Decoder diffs
  your manager profile against it." / "Take ManagerMatch™ →".
  → Manager not profiled (`no_manager_profile`): same title and tagline / "Profile how
  your manager actually works, and we'll diff it against your ManagerMatch needs." /
  "Profile your manager →".
  → Anything else: "We couldn't check your Manager Decoder status just now." + "Try again".
  While it loads, the card is a grey pulsing skeleton.
- **S16.6** — Read the CompanyLens card. **Differs between prod and branch.**
  → **Branch only — not on prod until the next merge.** Live: "CompanyLens™" / "Company
  environment and cultural alignment" / "See how companies you're considering line up with
  what you've told us you need, trait by trait, with the evidence behind each read." /
  button "Open CompanyLens →" (to `/company-lens`). The card is no longer dimmed and is
  not gated on any assessment.
  → **On prod today:** a dimmed card, "CompanyLens™" / "Company environment and cultural
  alignment" / "Our matching model is still being built. Your Work Pulse results are
  already saved and will feed it the moment it's ready." **No button at all.** (The
  disabled "Coming soon" button this document used to describe was removed 2026-10-05,
  `fb34d02`, and that is on prod.) `G4` is still true on prod, closed on the branch.
  → Where the branch card leads: `/company-lens`, H1 "Companies, read against how you
  like to work" (S17 owns that page). On prod the same URL shows "CompanyLens™ is coming
  soon" / "We're still building the matching model behind it. …" / "Back to Intelligence".
- **S16.6a** — Read the Path Intelligence card.
  → "Path Intelligence" with a pill **"Pro · coming soon"** / "Career path scoring and
  guidance" / "See which career paths best match your skills and profile, with plain-language
  guidance on why each one fits." / "View Your Paths →". The pill is decorative (there is no
  entitlement check) and the button is live. Kept by the 09-28 ruling; do not file it.
- **S16.7** — Check the footer. → "No scores here, and that is deliberate." + "How
  this works, and what we hold back →" (to `/trust`).
- **S16.7a** — Read the quizzes block between the cards and the footer.
  → H2 "Solverah Career & Psychometric Quizzes" / "Explore our curated set of quizzes to
  uncover your strengths, personality traits, and career motivations. Your responses will
  be automatically saved to your profile." Five cards, each with "Start Quiz" (or "View
  Answers" plus "View Insights" once taken): "Early Career", "Career Transition", "Career
  & Job Search", "Mid-Career / Strategic", "Your Future, Your Way (Teen-Focused)".
  → Closing amber strip: "Complete Your Assessments" / "Taking these quizzes will improve
  your personalized job matching accuracy and help you stand out to employers." The "stand
  out to employers" promise contradicts `/trust` ("Employers do not see your answers…").
  `G40`.
- **S16.8** — Open `/solverah-profile`. → Identical page. Confirm nothing differs.
  (It is the same component; the header highlights "Intelligence" on both.)

#### S16.9–S16.12 · Path Intelligence

**Account** ACC-1 (gates: ACC-3 / ACC-4, see S16.10) · **Route** `/intelligence/paths` ·
**Re-derived from HEAD 2026-10-25.** Every file behind this page is **identical on prod**
(`origin/main` 02707ab) and on the branch: `git diff origin/main HEAD` touches none of
`src/features/intelligence/components/Path*`, `src/features/intelligence/usePath*`,
`pathFailure.ts`, `solverah/api/v1/intelligence.py` or `solverah/services/intelligence_service.py`.
Workstream F (corpus retrieval, deep fit, feedback) and W (wants panel, no-score cards,
cards-before-sentences) are both live on prod since #155 (2026-09-28).

**No number on this page is a score.** Not on the cards (8d35fb2), not in the deep-fit
panel, not in words ("Strong overlap" was removed for the same reason). A digit that
grades you is the bug.

- **S16.9** — From `/intelligence`, the Path Intelligence card: "Path Intelligence" with a
  "Pro · coming soon" pill / "Career path scoring and guidance" / "See which career paths
  best match your skills and profile, with plain-language guidance on why each one fits." /
  "View Your Paths →". Click it.
  → Page header: eyebrow "Path Intelligence" with a **"Pro · coming soon"** pill; H1 "Your
  Career Paths"; "Career paths matched to your skills and work profile, with plain-language
  guidance on why each one fits."
  → **Corrected 2026-10-25:** the pill now reads "Pro · coming soon" (140d66b, 2026-09-28;
  it said "Pro" when this doc was written). It is still **not an entitlement check** —
  nothing anywhere gates the page — and d96bb24 records Sebastian's ruling that the badge
  stays. It means "a Pro tier is coming", not "this page is coming". Read it as a user
  would: on a page that works, "coming soon" next to the title is easy to misread as
  "this isn't real yet". A positioning call, not a defect.
  → The hub card's subtitle still says "Career path scoring and guidance", the one place
  the word *scoring* survives after W-13 took it off this page. Julie's copy.
  → Loading: three pulsing skeleton cards (`aria-label` "Loading suggestions"). While the
  skeletons show, the wants panel (S16.9a) can already render above them.
  → The **"placeholder SOL-31" comment is gone** (9a56d12, 2026-10-02). Nothing on this
  page is marked as a placeholder in source any more.
- **S16.9a** — *(New.)* The wants panel, above the cards. **Only for a user with a current
  job title the server can anchor to.** `first_job` (and any title that resolves to no
  occupation) gets nothing here at all, by design (`no_anchor`). A `between_jobs` user with
  a last title is anchored to it (the server builds the same profile the scorer uses), so
  ACC-4 should see a panel about the old job. Confirm the heading reads sensibly in that
  lane: it says "About your work", present tense.
  → One collapsed row: "Tell us what should change about your job, and we'll re-sort
  these", "Open" on the right ("Hide" once open). After a save, a second line: "1 thing you
  want to change" / "{n} things you want to change".
  → Open: "About your work: {O*NET title}" (plural O*NET titles, e.g. "Software
  Developers", on purpose) / "Mark anything you'd like more or less of. Answer as many or as
  few as you like — leaving something as it is tells us nothing is wrong with it."
  → Two groups: "What you spend your time on" (your own O*NET tasks) and "How you work",
  with the four conditions "Time working with other people", "Dealing with customers or
  the public", "Leading or directing other people", "At a desk, rather than on your feet".
  Each row: "Less of this" · "Fine as it is" · "More of this".
  → "Update my suggestions" is disabled until something changed; pressing it reads
  "Re-sorting your paths…" and every pill locks until the new list lands. **Measured 11–27 s**
  in the user test — not a hang. "Clear my answers" appears once anything is answered.
  → Save failures, inline in red: "That's a lot of changes at once. Give it a minute and try
  again." (429) / "We couldn't reach the occupation data just now. Give it a moment and try
  again." (503) / "Your job details changed, so we've reloaded this. Have another look and
  press the button again." (`not_offered`, two tabs) / "We couldn't save that just now. Try
  again in a moment."
  → If the panel's own `GET /me/path-wants` fails it renders **nothing** — no error, no
  retry. That's deliberate (§8.3 of the design doc): the panel doesn't get to report an
  outage on a page that works.
- **S16.10** — **Gate order rebuilt 2026-09-28 (140d66b) — the confirmed sequencing finding
  of 2026-09-15 is fixed on prod.** The mount decision now runs, in order: (1) career
  status, (2) skills, (3) skill-proficiency modal, (4) preferences form, (5) scoring. A user
  with no career status sees the prompt **first**, before any skill rating or preference
  question.
  → "Has a career status" means a stored status **or** any experience entry whose end date
  is "Present"/"Current" (the server's own derivation rule, mirrored client-side).
  → No status: "Set your career status to get started." / "Tell us where you are in your
  career so we can tailor your path suggestions." / "Update Profile" → `/job-seeker/profile?tab=experience`
  with the career-status modal open (S19.4). After saving, the profile asks "Status saved."
  / "Go back to Path Intelligence?" with "Stay here" and "Go back" (new since this doc was
  written).
  → **Still deferred to ACC-3** (ACC-1's status was set during S9). Walk it after ACC-3
  finishes Work Pulse and **before** setting career status — see S21.1's checklist. It is
  now cheap to walk: the prompt is the first thing on screen.
- **S16.10a** — *(New, 140d66b.)* Career status set, **zero skills on file**.
  → "Add a few skills to get started." / "Path Intelligence matches career paths to what you
  can already do. Add at least one skill in the Skills section of your profile's Experience
  tab, then come back here." / "Add skills" → `/job-seeker/profile?tab=experience`.
  → This client gate is **stricter than the server**: the scorer accepts a job title with no
  skills, the page does not. A title-only user is asked for skills.
  → After adding skills and saving, the way back is uneven — see `G65`. Use the
  Intelligence link in the header if no "Go back" appears.
- **S16.10b** — Skills on file but proficiency never confirmed.
  → Modal: "Rate your skills" / "Help us understand which skills you use most — it makes
  your career matches significantly more accurate." One card per skill with "Beginner" ·
  "Intermediate" · "Advanced" (every skill starts at Beginner). Buttons "Skip for now" and
  "Save & continue" ("Saving…").
  → No close button and no Escape: Skip or Save are the only ways out. A failed save is
  swallowed and the page proceeds anyway, by design.
  → Skip shows, once the list is up, an amber nudge: "Rate your skills to get more accurate
  career matches." / "Rate skills".
- **S16.10c** — No `path_preferences` yet: the three-question form.
  → "Question {n} of 3" with a three-dot progress bar. Q1 "What kind of move are you
  looking for?" — "Stay in my field" / "Something adjacent" / "Fresh direction". Q2 "What
  seniority level are you targeting?" — "Looking to move up" / "Similar level" / "Open to
  either". Q3 "What matters most in your next role?" — "Pay & title" / "Interesting work" /
  "Work-life balance" / "Learning & growth". Each option has a one-line description.
  → "Next →", then "See my paths →" ("Saving…"); "← Back" from Q2. Save failure: "Something
  went wrong saving your preferences. Please try again."
  → **Fixed since this doc (W-13):** only the selected option is green with a ✓. Hover is
  neutral now — two options lit at once was the hover colour, not a double selection.
- **S16.11** — **The `profile_incomplete` gate: backend now real, frontend pre-empts it.**
  → **Corrected 2026-10-25 — "confirmed dead code" no longer holds.** The server now
  answers `400 profile_incomplete` when the profile has **neither** a job title **nor** any
  skill (`InsufficientProfile`, `intelligence_service.py:508–522`; branch added in the F-4
  → F-6 run, all on main). The comment there names this very step: "This is the ACC-4 /
  S16.11 defect".
  → But you will still not see the card from a fresh mount: S16.10a's skills gate fires
  first for anyone with zero skills, and anyone with a skill has "signal". The card's copy
  ("Add a job title and a few skills to get started." / "Path Intelligence needs your
  current (or most recent) job title and at least one skill to find matching career paths."
  / "Complete Your Profile") is now reachable only when a deep fit or a feedback tap comes
  back `profile_incomplete` — skills deleted in another tab mid-session. Not a pass
  condition; reference only.
- **S16.12** — Complete the gates and get suggestions.
  → **Cards first, sentences after (W-16).** Scored cards land in roughly 0.3–3 s. Each
  opens with O*NET's own one-line summary of the job; the personal "why this fits" sentence
  and its 2–3 tag pills fade in a few seconds later. Until then a card holds its space with
  three grey placeholder lines (screen-reader text "Writing why this path could suit you…").
  The card does not move when the sentence lands; that is W-18's reserved height.
  → If a sentence never arrives (the narrator's 60 s deadline, or the poll gives up), the
  card gets the house fallback: "Uses your {skill}." / "Uses your {a}, {b} and {c}." / "A
  different direction. Open it to see how it lines up with your skills."
  → Each card: the occupation title; a progression line "{current title} → {target}"
  ("Current Role" if no title; "Previously {last role} → {target}" for `between_jobs`;
  "Starting out → {target}" for `first_job`); the summary; up to two reason lines when you
  have answered the wants panel (e.g. "More time with people than your current job",
  "Among the most people-facing jobs"); the sentence and tags.
  → Ten paths, three at a time: "Show 3 more paths" (then "Show 1 more path" style
  remainders).
  → Below the list: "Edit skill ratings" and "Adjust search preferences".
  → **Retired 2026-10-05 — "Coming soon — goal tracking is on the way" / "Set as target
  role".** d96bb24 removed the disabled CTA and its tooltip from every card; a test asserts
  it never renders. If you see it, you're on a stale bundle.
  → Scoring failure: "We couldn't load your path suggestions right now." / "Please try
  again in a moment." / "Try again". A corpus outage (`corpus_unavailable`) lands here
  too; only the deep-fit panel words it differently.
- **S16.12a** — *(New, F-6.)* Click a card's body.
  → A panel over the page: eyebrow "How this fits you", the title, "✕" (Escape and the
  backdrop also close). Spinner "Working out how this fits you…" — sized for **~850 ms**
  (2.4 s cold, near-instant on a card you already opened; the first three cards are
  prefetched).
  → Sections, each only when it has content: "Training" ("Needs more training than your
  current level." [+ " (we've estimated your level)"] / "Needs less training than your
  current level." / "About the same training as your current level." / "We don't have
  training requirements for this one."); "Skills you already have" (pills); "Worth picking
  up" (a list, importance order, no numbers); "What you'd be doing" (O*NET tasks); "Tools
  people use" (pills).
  → Failures stay in the panel: "We couldn't reach the occupation data just now. Give it a
  moment and try again." (+ "Try again") / "There isn't enough detail about this occupation
  to break it down." / "This path isn't available any more. Refresh your suggestions to see
  the current list." / "Something went wrong opening this path." / "We couldn't open this
  path right now." (+ "Try again"). Only the retryable ones offer the button.
- **S16.12b** — *(New, F-6.)* Under each card: "Interesting" · "Too similar to my job" ·
  "Not for me". Tap one.
  → "Too similar…" and "Not for me" remove the card **at once**; "Interesting" lights up and
  stays. The re-ranked list then replaces the old one in place; how far you had opened the
  list with "Show more" is kept.
  → On "Stay in my field" (ruling 2, PATH_WANTS_DECISIONS) the two "no"s remove cards and
  nothing re-orders; "Interesting" is remembered and moves nothing. Expected.
  → Once any verdict stands: "These paths are shaped by what you've told us." / "Start
  over" (clears every verdict and re-ranks).
  → Verdicts survive a reload: you come back with the lit buttons and "Start over".
  → A failed tap reverts, then: "We couldn't save that just now." / "Your suggestions
  haven't changed." / "Try again". **Since 9a56d12 "Try again" resends the same tap**, not
  just the dismissal.
- **S16.12c** — *(New.)* Ask for a re-score while a list is on screen (a wants save, or
  "Edit skill ratings" → Save), several times quickly. The enqueue is capped at 10 a minute.
  → The old list **stays**, with: "That's a lot of updates at once, so these are your paths
  from before." / "Give it a minute, then try again." / "Update my paths" (429), or "We
  couldn't update your paths just now, so these are the ones from before." / "Please try
  again in a moment." (anything else).
  → "Edit skill ratings" → **"Skip for now" also re-scores**, and puts up the "Rate your
  skills…" nudge for someone who already rated — `G63`.
  → "Adjust search preferences" opens S16.10c's form in place of the list, with **no way
  out but answering all three** (no Back on Q1, no Cancel), and finishing re-scores —
  `G64`.

- **S16.13** — Open `/trust`.
  → H1 "How this works, and what we hold back". Sections: "The questions are forced
  choices, and both answers are real"; "There is no score to see, and that is the
  point" (+ the FocusType aside, "Then why does FocusType show me a result?");
  "What matching means, and what it does not"; "How we check our own instruments" (+
  aside "The honest limits of all that"); "Your answers". Closing: "Nothing on this page
  describes something that does not exist yet. Where a thing is still being built, it
  says so, and when that changes, this page changes with it." Related links: "How matching
  works" (`/how-matching-works`), "Privacy policy", "Terms of service"; back link "Back to
  your Intelligence hub".
  → **Branch only — not on prod until the next merge.** Third section title is "What
  matching means, and what it does not" (prod: "What matching will mean, and what it will
  not"). Its first paragraph says "Company matching is live in CompanyLens, as one signal
  among others. … It never shows a score, a percentage or a probability … The evidence it
  shows is paraphrased, not quoted." The fourth section adds that company reads "are
  scored automatically, by an AI scorer applying that same rubric … Checking that
  automatic scoring against the human raters is part of the unfinished work below," and
  the limits aside says the model "runs on expert estimates and has not yet been trained
  on real outcomes". Footer line "Last reviewed 14 October 2026".
  → **On prod:** "Company matching is not live. The model it depends on is still being
  built, and rather than ship a plausible-looking number in the meantime, CompanyLens says
  coming soon." and "Last reviewed 10 September 2026". Prod's page is internally
  consistent with prod's CompanyLens card.
  → **Promise-by-promise, read against the page's own rule.** "You can delete your
  account and the data behind it": true (`/settings`, S20). "You can retake Work Pulse
  from its page": true (S8.8a), and "your Situation Report stays on the sitting it was
  built from until you choose to re-read it": true (S11). "Employers never see your
  individual answers or your dimension scores": enforced in code (D-01). "Your answers are
  not sold and are not used for advertising": a policy statement, not walkable. **The
  branch copy "CompanyLens is live" is only true once the branch is deployed with the
  research pipeline running; merging the page without the CompanyLens build would make
  `/trust` the one page that lies.** The two ship together or not at all.
- **S16.14** — Open `/career-quizzes` signed in.
  → H2 "Career Quizzes & Archetypes", all four quizzes ("Quiz 1: Early Career", "Quiz 2:
  Career Transition", "Quiz 3: Mid-Career / Strategic", "Quiz 4: Your Future, Your Way
  (Teen-Focused)") with radio options, and an "Archetypes" list. No loading state at all —
  questions render unanswered while the profile loads, then re-render with your saved
  answers. A **failed** profile read is still indistinguishable from "never taken"
  (the page quietly opens in edit mode). There is no draft: reload mid-quiz and the
  answers are gone.
  → **`alert()` dialogs on quiz submit: closed** (`bf4b785`, 2026-10-02; on prod).
  Failures now show an inline red alert above the button: "Answer at least one question to
  get your insight." (nothing answered) or "We couldn't save your answers. Please try
  again." (or the server's own message). **But two `alert()` dialogs survive on the
  profile page**, not the quizzes: "Unable to process resume right now." (upload failed)
  and "Unable to open resume right now." (View Resume failed). See S19.6a and `G42`.
- **S16.14a** — Open `/career-quizzes/early-career`, then `/career-quizzes/career-transition`,
  `/career-quizzes/mid-career`, `/career-quizzes/teen-focused`.
  → Each shows one quiz under its own title. "Save Answers" is disabled until one question
  is answered; it reads "Saving…" while it saves. `/future-your-way` is **gone** (route
  and component removed 2026-10-05, `882ac5a`; it had no link anywhere). Its data stays so
  old stored insights still render.
- **S16.14b** — Press "Save Answers".
  → A modal, eyebrow "Insight", title "Career Quizzes Insight": "Generating your insight.
  This can take a few seconds." with a progress bar, then "Your insights are ready. Choose
  where you want to go next." with "View insights" and "Back to assessments", or the error
  in red. Afterwards the page flips to "Your Results" / "Review your saved responses. You
  can update them anytime." with "View Insight", "Back to Assessments", "Change Answers".
- **S16.14c** — Open `/career-job-search`.
  → H2 "Career & Job Search"; five sections ("Career & Job Search", "Work Style &
  Adulting", "Growth & Identity", "Networking & Social Life", "Stress & Balance"); same
  buttons and modal, modal title "Career & Job Search Insight". **`G16` is closed:** it now
  stores under the same `careerQuizzes` group as the others (`bf4b785`), and "View Insight"
  goes to `/quiz-insights?group=careerQuizzes`.
- **S16.15** — Open `/quiz-insights`.
  → Eyebrow "Insights"; H1 "Career Quizzes Insights" (or "Quiz Insights" for an unknown
  `?group=`); "Personalized takeaways based on your quiz responses."; "Back to
  assessments". Loading: "Loading insights…". Empty: "No insights found yet. Complete a
  quiz and generate insights to view them here." Populated: filter pills ("All", one per
  quiz, "Overall Summary"), one card per quiz ("Key takeaways", "Combined meaning", "Next
  steps"), and a dark "Combined Insight" / "Across All Your Quizzes" panel.
  → **`G22` is closed** (`140d66b`, 2026-09-28; on prod): the guest-quiz replay now
  invalidates the profile cache before navigating, so insights appear on arrival without
  a reload. (Walk-confirm in S4.8.)


---

### S17 · The matching surfaces

**Account** ACC-1 · **Routes** `/search`, `/feed`, `/company-lens`, `/companies/:id` ·
**Re-derived from HEAD 2026-10-25.**

**Two builds, two answers.** `/search` and `/feed` are identical on prod and the branch:
honest coming-soon screens since 835cfbf (2026-09-28), per the user-testing ruling of that
day. `/company-lens` and `/companies/:id` are **completely different** on the branch:
a8d6850 (CompanyLens six-trait: match service, API and pages) and 77610c2 (the research
pipeline) are on `causal_bayesian_model` only. S17.6 and S17.7 give prod first, then the
branch flow as lettered steps, each marked.

- **S17.1** — **Retired 2026-10-05** — the dashboard's "Search companies and roles →" link
  is gone (fb34d02, "remove dead coming-soon UI"). Nothing in the product links to
  `/search` any more. (The dashboard's file header still says "`/search` keeps a plain link
  below the fold"; that comment is stale.)
- **S17.1a** — *(New.)* Type `/search` into the URL bar.
  → One card with a search icon: "Search is coming soon" / "We're still building search for
  companies and roles, so there's nothing to look through yet. We'll switch it on once it can
  give you real answers." / "Back to your dashboard".
  → The page makes **no request**. Cream background, ink text.
- **S17.2** — **Retired 2026-09-28** (835cfbf) — the "no query can ever return a result"
  finding is answered by removing the results UI: no input, no pagination, no "Match score",
  no fetch. `useRecommendations` has no consumer now.
- **S17.3** — Type `/search?q=anything` (real or gibberish).
  → **Identical** to S17.1a. `?q=` is ignored and **not echoed**, deliberately — echoing it
  would imply it was used.
- **S17.4** — **Retired 2026-09-28** (835cfbf). With no fetch there's no error state to
  force, so `G15`'s "We couldn't run that search right now" no longer exists anywhere. The
  near-white-text defect (`text-slate-100` with no background) is **fixed**: the page now
  sets `bg-cream-base` and ink colours.
- **S17.5** — Click "Feed" in the header (desktop nav or the mobile menu).
  → It does **not** navigate (`G3`). A full-screen modal: "Feature coming soon" / "We're
  still building the feed. It'll show up here when it's ready." / "Got it". **Copy changed**
  in 835cfbf; it used to read "The feed will be available soon. Check back after launch."
- **S17.5a** — *(New.)* Type `/feed` into the URL bar.
  → H1 "Your feed, {first name}" ("Your feed" if the account has no name); one card: "The
  feed is coming soon" / "This is where roles, messages and updates will collect once
  they're ready. None of that is live yet, so there's nothing to show here for now. Your
  dashboard and Intelligence pages are up and running." / "Go to your dashboard" · "Open
  Intelligence".
  → **The 2026-09-15 findings are all gone**: no search box, no handler-less "Filters" or
  "Start a Conversation", no "--" stats, no Messages/Notifications tabs, no near-white text.
  No request is made.
- **S17.6** — Open `/company-lens`. **Prod today (`origin/main`).**
  → No organic path: the hub's CompanyLens card on prod is a faded card with **no button**
  ("CompanyLens™" / "Company environment and cultural alignment" / "Our matching model is
  still being built. Your Work Pulse results are already saved and will feed it the moment
  it's ready."). Type the URL.
  → Loading: "Scoring companies against your Work Pulse results…"
  → Then, for a current-instrument user: "CompanyLens™ is coming soon" / "We're still
  building the matching model behind it. Your Work Pulse results are already saved and will
  feed it the moment it's ready — there's nothing you need to do." / "Back to
  Intelligence". `G4` — expected. The page gets there by matching the **prose** of a 400
  ("culture preferences" / "Work Pulse not completed"), not a code.
  → **One prod-only caveat (`G67`):** an account that still carries a stored legacy
  `culture_preferences` value skips that 400 and gets the interim scorer's two-ended list
  with "{n}% match" on every card. Every current-instrument account gets coming-soon.
  → **Branch only — not on prod until the next merge.** On HEAD the page is CompanyLens
  itself: S17.6a–S17.6h.
- **S17.6a** — **Branch only.** From `/intelligence`, the CompanyLens card is live:
  "CompanyLens™" / "Company environment and cultural alignment" / "See how companies you're
  considering line up with what you've told us you need, trait by trait, with the evidence
  behind each read." / "Open CompanyLens →".
  → Loading: "Reading companies against your answers..."
  → Load failure: "We couldn't load CompanyLens right now." / "Please try again in a
  moment." / "Try again".
- **S17.6b** — **Branch only.** As a user with **no current core sitting** (ACC-3 before
  Work Pulse).
  → "← Back to Intelligence"; eyebrow "CompanyLens™"; H1 "Companies, read against how you
  like to work"; lead "We read what's public about each company on six traits (autonomy,
  pace, collaboration, feedback, innovation and how decisions get made) and set it beside
  what you told us you prefer. Where the evidence is thin or disagrees, we say so."
  → Then "Start with how you like to work" / "CompanyLens compares companies with your own
  preferences, so it needs your Work Pulse answers first. It's a short set of questions,
  and every read here builds on it." / "Take Work Pulse" → `/work-pulse`.
- **S17.6c** — **Branch only.** As ACC-1 (core done), **before** anything is researched.
  → Same header. If you haven't done the tolerance step: "These reads use a narrow range
  around each of your answers. Tell us how much give you have on each trait, and which ones
  are must-haves." ("Tell us how much give you have" links to `/trait-preferences`, a
  branch-only route.)
  → The research form: label "Research a company" / "Name any company. We read what's public
  about how work runs there and add it to your list." / placeholder "Company name" /
  "Research".
  → "No companies yet" / "Name a company you're curious about above, whether it's one you're
  interviewing with or one you've always wondered about. Once it's researched, its read
  shows up here."
- **S17.6d** — **Branch only.** Submit the form empty, then with a real name.
  → Empty: "Enter a company name to research." (red, no request).
  → Real name, progress in a polite live region (polled at 3 s, backing off to 20 s):
  "Starting research on {name}..." → "{name} is in the queue. Research usually takes a few
  minutes, and it keeps going if you leave this page." → "Researching {name}: reading what's
  public about how work runs there. It keeps going if you leave this page." → "Research on
  {name} is finished." + "Open the read on {name}". The list refreshes on its own.
  → A company somebody already researched: "{name} was already researched, so there was
  nothing to wait for."
  → A run that fails: "We couldn't finish researching {name}. Please try again later."
  → **A run takes minutes (hard limit 26).** A reload loses the progress line; the
  company still appears in the list when the run finishes.
- **S17.6e** — **Branch only.** The start refusals.
  → **Expected on the first post-merge walk:** "Company research isn't available right now.
  Please try again a little later." That's the `503 research_disabled` answer: the public
  switch `SOLVERAH_COMPANYLENS_RESEARCH_ENABLED` is **off by default** until the attorney
  review, and a missing provider key (`provider_unavailable`) reads the same. §0.6.
  → Sixth new company in a day: "You've started research on five new companies today, which
  is the daily limit. Companies that are already researched are always free to look at,
  and you can start more tomorrow."
  → Burst (over 10 a minute): "That was a lot of requests in a short time. Wait a minute,
  then try again."
  → Polling lost (three failed polls): "We lost track of that research. Come back in a few
  minutes and refresh the page to see whether it finished."
  → Anything else: "Something went wrong starting that research. Please try again."
- **S17.6f** — **Branch only.** With researched companies present: "Your companies" / "Closest
  to how you like to work first. A company that breaks one of your must-haves is flagged and
  listed last, never hidden."
  → Each card: the name (a link); "Based on {k} of 6 traits" with a breakdown "({n} clear,
  {n} where the evidence disagrees, {n} with too little evidence)"; "Next step" chip —
  "Decide" ("Enough is known to weigh this one up."), "Investigate" ("{Trait} is a
  must-have for you and we could not read it here." / "…the evidence here is split." /
  "…the posting reads differently from the company."), or "Explore"; "Your must-haves" with
  one line each (e.g. "More on the {pole} side than you prefer, outside your give", "About
  where you prefer", "The evidence disagrees", "Not enough evidence yet") and a badge
  ("Must-have outside your give" / "Must-have at risk" / "Must-have to find out about");
  amber counts ("1 must-have outside your give", "{n} to find out about"); a size note
  (e.g. "We do not know how big this company is. The bigger it is, the less a company-wide
  read says about any one team."); "See the full read".
  → While a company's research is being refreshed: "We're updating the research on this
  company now."
  → **No percentage, score or probability anywhere** — the order is the ranking. The only
  numbers are the coverage counts and dates.
  → The list is **every researched company, for every user** — not yours (`G66`).
- **S17.6g** — **Branch only.** Companies with fewer than 3 clear traits: "Not enough
  evidence yet" / "We found too little to read these companies on at least three traits, so
  we don't place them. Here's what's missing." Each row: "Clear reads on {k} of 6 traits so
  far, which is not enough to say how it compares. Too little evidence on {Autonomy, Pace and
  Feedback}." + an "Explore" next step. Unranked by design.
- **S17.6h** — **Branch only.** Past 20 companies: "Show more companies" ("Loading...").
- **S17.7** — Open `/companies/{a real id}`. **Prod today (`origin/main`).**
  → The legacy research profile: "Loading company profile…"; then name, "industry · size ·
  headquarters", and only populated sections (Culture, Work Environment, Remote & Office,
  Employee Ratings, Interview Process, Compensation, Workforce Signals, Tech Stack). Error or
  missing id: "Couldn't load this company profile." / "Please try again in a moment." /
  "Try again".
  → **No organic path on prod** (CompanyLens is coming-soon, so no match card links here).
  URL only. The "Your CompanyLens™ fit score" block with a percentage appears only when a
  match card passes one in router state, so never by URL.
  → **Branch only — not on prod until the next merge.** On HEAD this route is the company
  read: S17.7a–S17.7f.
- **S17.7a** — **Branch only.** Header on every state: "← Back to CompanyLens", eyebrow
  "CompanyLens™", H1 the name, then "industry · size · headquarters" and the website if the
  legacy profile has them.
  → Loading "Loading your read..."; failure (a bad id included) "We couldn't load this
  company." / "Please try again in a moment." / "Try again" — a permanent 404 still offers
  Try again (`G68`).
  → No core sitting: "Start with how you like to work" / "Your read of {name} compares it
  with your own preferences, so it needs your Work Pulse answers first." / "Take Work
  Pulse".
- **S17.7b** — **Branch only.** A company in the table but never researched (any legacy id).
  → "We haven't researched {name} yet" / "We read what's public about how work runs there,
  on six traits, and set it beside your answers. It takes a few minutes." / button
  "Research {name}" ("Researching..."). Same messages and refusals as S17.6d–e (with the
  switch off: "Company research isn't available right now. Please try again a little
  later.").
  → While a run is going: "Research on this company is under way. Come back in a few minutes
  and your read will be here." / "Check again".
- **S17.7c** — **Branch only.** A researched company. "Your read": the coverage line and
  breakdown, the next-step chip with its reason, the flag counts, the size note; if
  tolerance is unanswered, "These reads use a narrow range around each of your answers. Tell
  us how much give you have."
  → `not_enough_evidence` adds: "That's too few clear reads to say how this company compares
  with the others, so we don't place it. What we did find is below."
  → Then **one TraitReadCard per trait**: the label, a status chip ("Clear read" /
  "Evidence disagrees" / "Not enough evidence"), "Must-have" and flag badges, "From {low
  pole} to {high pole}".
  → Clear: the read line ("More on the {pole} side than you prefer, inside your give."),
  "From {n} pieces of evidence, dated {Mar 2023 to Sep 2025}, from {careers page and
  employee review}.", an optional scope note, up to three **paraphrases** (never quotes),
  each with "{Source type} · {scope} · {month}" and a "Source" link that opens a new tab.
  → Disagrees: the explanation, then two panels side by side, "Evidence on the {low pole}
  side" and "Evidence on the {high pole} side", each with its own read and paraphrases.
  **Never averaged.**
  → Not enough evidence: the plain explanation, no read, no penalty.
  → On a must-have that's unclear or split: "Ask in your interview" with 2–3 questions.
- **S17.7d** — **Branch only.** "Paste a job posting" / "A posting describes one role, which
  can differ from {name} as a whole. Paste one and we'll read it on the same six traits and
  show where it and the company evidence disagree. Only you see it."
  → "Role title (optional)", "The posting's text" ("Copy the whole posting from the job page
  and paste it here."), "Read this posting" ("Sending..."). Empty: "Paste the posting's text
  first."
  → After submit the id goes into the URL as `?posting=`, so a reload keeps it. "Reading the
  posting. This usually takes under a minute, and it keeps going if you leave." → either
  "This posting's read is beside the company's below, trait by trait. They don't disagree
  anywhere." or "This posting's read is beside the company's below. They disagree on
  {traits}: the role may not work the way the company evidence suggests. It's worth asking
  about." Each trait card gains "Your pasted posting (this role)" and, on a disagreement, an
  amber line ("This posting describes {trait} as more on the {pole} side than the company
  evidence does.").
  → A requirements-only posting: "This posting lists what the role needs but says nothing
  clear about how the work runs, so there's nothing to set beside the company's read."
  → Failures: "We couldn't read that posting. You can try pasting it again." / "We couldn't
  find that posting any more. You can paste it again." / "That's a lot of postings in a short
  time. Wait a little, then try again." / "Reading postings isn't available right now.
  Please try again a little later." "Paste a different posting" resets. Not behind the
  research switch, but needs `OPENAI_API_KEY`.
- **S17.7e** — **Branch only.** "Did you take a job here?" / "Tell us and we'll tie your
  Pulse check-ins to this read, so we can learn whether it was right. You can remove it any
  time." + "Start date" + "I took this job". **Writes a real row** — use a throwaway
  company, or remove it afterwards.
  → Linked: "You took a job at {name}, starting {date}. Your Pulse check-ins from here on
  help us learn whether this read was right." / "I left this job" (→ "Last day", "Save",
  "Cancel") / "Remove this". A last day before the start: "We couldn't use that date. Your
  last day needs to be on or after your start date."
  → Linking a second company adds "This replaces the job you recorded at {other}."
- **S17.7f** — **Branch only.** A company with a legacy profile shows it last, dashed and
  secondary: "Background research" / "An older, general profile of this company. It isn't
  part of your read above." The 8-dimension culture bars and the Glassdoor rating grid are
  **gone** (no-score rule).


---

### S18 · The agent

**Account** ACC-1 · **Route** `/agent` · **Re-derived from HEAD 2026-10-25.** Identical on
prod and the branch: `AgentChat.tsx` and `solverah/api/v1/intelligence.py` don't differ, and
the branch's `solverah/infra/llm/__init__.py` diff only *adds* the CompanyLens clients.

> ### ✓ The 2026-09-15 outage is fixed on prod — walk S18 in full
>
> **Fixed 2026-09-28 in 88c978d** ("fix(agent): move off the retired Groq model to
> openai/gpt-oss-20b"), on `origin/main`: `DEFAULT_AGENT_MODEL = "openai/gpt-oss-20b"`
> (`git show origin/main:solverah/infra/llm/__init__.py`, line 47), and it can now be
> swapped without a deploy through `SOLVERAH_AGENT_MODEL`. gpt-oss runs with
> `reasoning_effort: "low"`, so the first token waits on a short think.
> **Never walked live since.** This is the first pass.
>
> A missing model no longer surfaces as a 422 with the model's name: it's a 503, code
> `agent_model_unavailable`, "The assistant is unavailable right now. Please try again in
> a few minutes." (bf4b785: provider and model names stay in the log).

- **S18.1** — Open `/agent`.
  → Title "Solverah AI" / "Your personal career assistant"; the permanent disclosure:
  "You're chatting with an AI. It uses your profile and resume to personalize answers, and
  it can make mistakes — verify anything important."
  → Empty state: a faded icon + "Ask me anything about your career, job search, or skill
  development."
- **S18.2** — Send a message with Enter. Try Shift+Enter for a newline.
  → Placeholder "Message Solverah AI… (Enter to send, Shift+Enter for new line)". The send
  button is disabled for an empty box.
  → **New (bf4b785):** the box stops at 4,000 characters, and only the newest 20 turns are
  sent.
- **S18.3** — Watch the reply arrive.
  → It streams (SSE). Three bouncing dots until the first chunk; replies render as
  Markdown (paragraphs, bold, lists).
  → **Corrected:** there's **no 40 ms per-chunk delay** any more ("Rendered as it arrives",
  bf4b785). Chunks show as fast as the provider sends them.
  → New stream-failure copy, in the red banner: "The reply was cut off before it finished.
  Please try again." (stream ended without `done`) / "The assistant didn't send a reply.
  Please try again." (empty reply) / "The reply was interrupted. Please try again." (server
  error mid-stream). The partial reply is dropped and your own message stays.
- **S18.4** — Try to type while a reply streams.
  → The textarea is disabled while pending (unchanged). Now testable: the window lasts as
  long as a real reply.
- **S18.5** — Ask product questions: "What is the Situation Report?" / "What does Work Pulse
  measure?" / "How do I profile my manager?"
  → **Corrected 2026-10-25: the agent is not taught the product.** D-1 put **your own
  results** in its system prompt (name, summary, up to 20 skills with levels, 5 roles, 3
  degrees, FocusType archetype + recommendations, ManagerMatch archetype + dimension
  numbers, quiz insights, your resume as delimited data) plus a "Companies in Network" list
  (the first ten company rows by id). There is **no description of any Solverah feature**
  in it, and D-1's "once A ships — the Situation Report's gap buckets" never landed. So
  every answer to these three questions is the model's guess. Judge them as such and
  expect invention — `G61`.
  → It's told not to recite assessment results "as numbers, scores, or percentages". Ask
  "What's my ManagerMatch score on autonomy?" and see whether it holds; the number is in
  its context.
- **S18.6** — Ask for something it should refuse or hedge on: salary advice, legal advice,
  a guarantee about a job. The prompt has **no guardrail for these**, only the
  no-numbers line, so this is a pure read of the model.
- **S18.7** — Go over the limit: 30 messages a minute, shared per user.
  → **Corrected:** the banner will **not** fall back to "Too many attempts. Please wait a
  moment and try again." The 429 is a Problem Details body whose `detail` is Flask-Limiter's
  own text, and the client prefers `detail` — so expect a banner reading **"30 per 1
  minute"** — `G33`.
  → Practical: with real replies taking seconds each, 31 sends inside a minute by hand is
  hard. Send short messages and press Enter the moment the box re-enables, or skip this and
  take the copy from `G33`.
- **S18.8** — Click "Clear chat" mid-stream.
  → The stream aborts, the conversation empties, and no banner appears (unchanged).
  → **New:** leaving the page mid-reply also cancels the stream (bf4b785), and **the
  conversation is not saved anywhere** — navigate away and back, it's empty. Not a bug.
- **S18.9** — (Config check.) **Corrected copy.** Most config failures now read like any
  other failure: a missing or invalid `GROQ_API_KEY` gives the generic 500 "Something went
  wrong generating a reply. Please try again." (code `agent_failed`). Provider unreachable
  gives the 503 "The assistant is unavailable right now. Please try again in a few
  minutes." (`agent_unavailable`), and so does a retired model (`agent_model_unavailable`).
  The old "Failed to generate response" no longer exists. To tell them apart, read the API
  log line `agent_chat error (model=…)`. §0.6.
- **S18.10** — *(New, 368c768.)* Leave `/agent` idle for **more than 15 minutes**, then
  send.
  → It works. Until 2026-10-02 the first message after the access token aged out failed
  **every time**: the streaming fetch had no refresh. It now refreshes once and replays.
- **S18.11** — *(New.)* Send an empty or whitespace-only message: nothing happens, no
  request. Paste past 4,000 characters: the box truncates. (Server-side, over 40 messages or
  over 4,000 characters per message is a 422, which the client caps prevent.)


---

### S19 · Profile and career status

**Account** ACC-1 · **Route** `/job-seeker/profile` · **Re-derived from HEAD 2026-10-25.**
`JobSeekerProfile`, `useProfileForm` and the tabs are byte-identical on prod and branch.

- **S19.1** — Open the profile.
  → H1 "Job Seeker Profile"; sub "Complete your profile to get better job matches and
  increase visibility to recruiters." — still there on prod and HEAD. "Recruiters" is
  wrong twice: no recruiter role exists, and the dashboard's equivalent alert was already
  rewritten to drop this register (S7.4a). Worth a copy ruling; Julie owns it. Gap stays
  open.
- **S19.2** — Click each of the **three** tabs.
  → `personal` "Personal Info" / `experience` "Experience" / `education` "Education".
  Each click rewrites `?tab=`. **The "Performance" tab was removed 2026-10-05**
  (`fb34d02`; its "Add Review" button had no handler). The fourth tab is a retired step,
  not a failure.
- **S19.2a** — Open `?tab=performance` directly.
  → Falls back to Personal Info with that tab highlighted.
- **S19.2b** — Read the Personal Info tab.
  → "Personal Information": First Name, Last Name, Email, Phone, LinkedIn Profile URL
  (placeholder "https://www.linkedin.com/in/your-profile"), "Primary Location (where you
  live)" (placeholder "e.g., Annapolis, MD"), "Open to work locations" (placeholder "Add a
  location (press Enter)"; cap message "You have reached the maximum of 20 locations."),
  "Professional Summary", then "Resume".
- **S19.3** — Open `?tab=bogus` directly.
  → **`G12` is closed** (`140d66b`, 2026-09-28; on prod): an unknown `?tab=` (or hash, or
  router state) is ignored and you land on Personal Info with it highlighted. The URL
  keeps `?tab=bogus` until you click a tab. Pass if the body is never empty.
- **S19.4** — Edit a field without saving.
  → Amber strip: "You have unsaved changes — don't forget to click **Save Profile**." This
  now fires for every edit, including adding/removing experience, education, skills and
  locations (it used to fire only for the personal fields).
- **S19.5** — Try navigating away **two different ways**, since they behave
  differently:
  → **A real page exit** (refresh, close the tab, type a new URL) — a native
  `beforeunload` dialog appears. This is the only path the guard covers
  (`useProfileForm.ts`, a bare `window.addEventListener("beforeunload", …)`).
  → **An in-app link instead** (e.g. "Dashboard" in the header, or a tab in the mobile
  menu) — **still open as of HEAD (no `useBlocker`/prompt anywhere in `src`):** no
  warning, the change is silently discarded. `beforeunload` never fires for client-side
  navigation. Confirmed live 2026-09-15; re-confirmed by source 2026-10-25. Also note
  that switching between the three tabs on this page does *not* lose edits, because the
  form state lives above the tabs.
- **S19.6** — Save. → Button "Saving...", a progress bar labelled "Saving profile" that
  fills and then reads "Saved" before it disappears; the amber strip goes away. A failed
  save no longer fills the bar: red alert "We couldn't save your profile. Your changes
  are still here, so try again." If the profile saved but the name did not: "Your profile
  was saved, but we couldn't update your name. Try saving again." A successful name change
  updates "Welcome back, {name}" and the header. (`68d4a34`, `140d66b`.)
- **S19.6a** — Upload a resume on the Personal Info tab.
  → Drop zone: "Upload your resume" (or "Replace resume") / "or drag and drop" / "PDF or
  DOCX, up to 10MB". A `.doc` or other file is refused on the spot: "We can only read PDF
  and DOCX files. Save your resume as one of those and upload it again." Then "Uploading
  resume" bar, "Parsing resume…", and on failure a red alert with the parser's message or
  "We couldn't read that file. Try uploading again." / "Unable to start resume parsing."
  / "Unable to check resume parsing status." / "Resume parsing did not complete. Try
  uploading again." A failed parse leaves the profile as it was (it used to be able to
  wipe it; `68d4a34`). A "View Resume" button opens the file in a new tab.
  → **Two failure paths still use a browser `alert()`**: "Unable to process resume right
  now." when the upload itself fails, "Unable to open resume right now." when View Resume
  fails. `G42`.
- **S19.7** — Arrive here from S16.10 (the Path Intelligence deep link), or from the
  dashboard's "Set your status" recommendation (S7.7a), or from the Environment Report's
  "Set your career status →" gate.
  → URL `/job-seeker/profile?tab=experience`, the career-status modal opens: "Where are
  you in your career?" / "We need this to generate your path suggestions." / "If you're
  currently employed, check **I currently work here** on your most recent role below and
  save your profile." / "Or select your status now:" with two options — "Currently
  unemployed" ("You're between roles and actively looking") and "Looking for my first
  job" ("You're early in your career and seeking an entry-level role"). The subtitle says
  "path suggestions" even when you came from the dashboard or the Situation Report;
  `G43` (copy only).
  → Behind the modal, the Experience tab starts with the always-visible control (S19.10a).
- **S19.8** — Pick one. → `PATCH /me/career-status`. Then, if you were sent here with a
  way back (Path Intelligence, the dashboard, the Environment Report): a small dialog,
  "Status saved." / "Go back to {Path Intelligence | your dashboard | …}?" / "Stay here"
  and "Go back" (Escape means stay). If there is no way back: you are sent to
  `/intelligence/paths`. The dashboard's next steps and the Situation Report are
  refreshed either way.
- **S19.9** — (If that PATCH fails.) → A red alert inside the modal: "We couldn't save
  that just now. Try again." The buttons re-enable and the modal stays open. (Was
  `G13`; closed 2026-09-14.)
- **S19.10** — **"Employed" is not an option in this modal**, but it is set two ways: by
  checking "I currently work here" on a role in the Experience tab and pressing Save
  Profile (this sets `employed` only when no status is stored; an explicit choice is
  never overwritten by a save), or by the control below. Confirm the checkbox path works,
  because it is the one that puts ACC-1 in present tense.
- **S19.10a** — Open the Experience tab.
  → First, an always-visible card, "Where are you in your career?" / "This changes what we
  ask and suggest. You can change it any time." with three radio buttons: "Currently
  employed" ("You have a job right now"), "Currently unemployed" ("You're between roles
  and actively looking"), "Looking for my first job" ("You're early in your career and
  seeking an entry-level role"). Each click saves at once (not part of Save Profile) and
  shows "Status saved."; a failure shows "We couldn't save that just now. Try again."
  This is the only way to **change** a status after it is set (added 2026-10-02).
- **S19.10b** — Rest of the Experience and Education tabs.
  → "Work Experience" / "Add Experience" / "Experience #1" with Company, Position, Start
  Date, End Date, "I currently work here", Description (max 20: "You have reached the
  maximum of 20 experiences."). "Skills" / "Click a skill tag to set your expertise
  level." / "Add a skill (press Enter)" / "Add" (max 50). Education tab: "Education" /
  "Add Education" (max 10), "Certifications" / "Add Certification" (max 20) / "No
  certifications added yet. Click "Add Certification" to get started."
- **S19.11** — Narrow the window to ~390px on the profile page.
  → The three tab buttons sit in one `space-x-8` row with no scroll or wrap; by arithmetic
  they need about 400px against about 358px available. Unverified; if the strip runs off
  the edge, file `G44`.


---

### S20 · Export and deletion — account settings

**Account** ACC-1 · **Route** `/settings` · Built 2026-09-14 (was `G1`) — on prod since PR #153. **Use a throwaway account for S20.3: it really deletes.**

*Frontend (`AccountSettingsPage.tsx`) is identical on prod and HEAD apart from `368c768` (drafts sweep), which is on prod. The backend export/delete payload **differs on the branch** (`42254ae`): marked below.*

- **S20.1** — Signed in, find the account-settings screen.
  → Desktop: the gear icon in the header, left of the logout icon (`aria-label` and `title` both "Account settings"). Narrow viewport: open the menu, then the visible text link "Settings". Either goes to `/settings`. H1 **"Account settings"**, your name and email beneath it.
  → `/settings` is inside the `RequireAuth` tree and lazy-loaded, so a signed-out visit shows the grey skeleton, bounces to `/login`, and returns you here after sign-in.
  → (Aside, not a step: the gear has an `aria-label`; the logout button beside it has only a `title`. Same gap as S6.11.)
- **S20.2** — "Your data" (H2). Body: "Download everything Solverah holds about you as a JSON file — your account and profile, your assessment answers and scores, your check-ins, and the records behind your recommendations." → **"Download a copy of your data"**.
  → The button reads "Preparing your download…" in flight, then the browser saves `solverah-data-YYYY-MM-DD.json` (your local date, not UTC). Nothing from the payload is ever rendered on screen. On failure: "We couldn't prepare your download just now." + "Please try again in a moment." + "Try again".
  → **Then open the file.** Confirm it is non-empty, parses as JSON, and contains your assessment answers (top-level key `assessment_answers`) and `dimension_scores`. The blob URL is deliberately revoked **60 seconds** after the click, to dodge a Firefox bug that otherwise saves a 0-byte file; a unit test cannot prove that in a real browser.
  → **Do this step in Firefox as well as Chrome.**
  → **Branch only — not on prod until the next merge.** The file also carries three new top-level keys: `trait_preferences` (every sitting of the per-trait tolerance / must-have form, oldest first), `job_postings` (every posting you pasted, with `posting_text`), `company_links` (every "I took this job" link). Environment-report entries gain five optional `outcome_*` fields and each Pulse check-in gains `company_link_id`. On prod today none of these keys exist.
- **S20.3** — "Delete your account" (H2). Body: "This permanently removes your account, profile, resume and intake records. Your assessment responses are kept only in de-identified form, no longer linked to you. This cannot be undone." → **"Delete my account"**.
  → Reveals "Type DELETE to confirm" and a text box. "Permanently delete" stays disabled until the input, **trimmed**, equals `DELETE` (so ` DELETE ` enables it; `delete` and `DELET` do not); the request always sends the literal `DELETE`. There is also a "Cancel" button. Confirming ("Deleting…") lands you signed out on `/` with a dismissible strip "Your account has been deleted." and a "Dismiss" button. A second sentence — "One or more uploaded files couldn't be removed from storage yet. Email info@solverah.com and we'll confirm once they're gone." — appears **only** if the server reported `r2_delete_failures`. Drafts in browser storage are swept (S6.11a). A 404 from the DELETE (account already gone) is treated as success.
  → A login with the old address now shows, **in the UI, "Failed to sign in. Please check your credentials."** The old doc said "Invalid credentials"; that is only the raw server string, which `Login.tsx` never shows (S5.9).
  → On failure: "We couldn't delete your account just now." + "Please try again in a moment. Nothing has been changed.", and you stay signed in.
  → **Branch only — not on prod until the next merge.** Deletion also destroys your pasted job postings (`posting_text` is free text) together with everything derived from them. Your "I took this job" company links are deliberately **retained** under the tombstone, along with trait-preference sittings. The settings page copy above does not say so. See `G36`.
- **S20.4** — Re-read the Privacy Policy clause from S1.8 and the Trust page line from S16.13 with that in mind.
  → All three promises are honoured verbatim: each says "account settings", none names a path, and that is the page's title.
- **S20.5** — (Optional, to confirm the backend half is sound.) Call the endpoints directly with your session cookie and CSRF header.
  → `GET /api/v1/me/export` returns `application/json` — **not a file download**, no `Content-Disposition`. The SPA builds the file client-side (a Blob).
  → `DELETE /api/v1/me` with `{"confirm": "DELETE"}` returns "Account deleted. Assessment responses are retained in de-identified form." plus `r2_delete_failures` (empty list when clean). It tombstones the user row (email rewritten to `deleted-{id}@tombstone.invalid`), hard-deletes personal content and every session, clears your cookies, and frees the email address. A wrong or missing `confirm` is 400 `Confirmation required: send {"confirm": "DELETE"}`.


---

### S21 · The first-job lane

**Account** ACC-3 · career status `first_job`

This is the product's most opinionated refusal: it declines to assemble a report
rather than invent one. Prod and branch are identical across this scenario.

- **S21.1** — Register ACC-3. **Three things were deferred here from earlier
  scenarios on 2026-09-15. Do them in this exact order before continuing into S21
  proper:**
  1. **S16.1**: visit `/intelligence` now, before touching Work Pulse at all. Expect
     the hard gate "Complete Work Pulse to unlock your profile."
  2. **S8.10**: block the `assessments/core/form` request in devtools, reload
     `/work-pulse`, and confirm the red "We couldn't load Work Pulse right now."
     panel. Remove the block afterwards.
  3. Complete Work Pulse (S8) for real, all 24 questions.
  4. **S16.10**: visit `/intelligence/paths` now, before setting career status. Expect
     "Set your career status to get started." / "Update Profile".
  5. *Now* set the career status to "Looking for my first job" (S19.7) and continue
     into S21 as written below.
- **S21.2** — Open `/situation-report`.
  → "← Intelligence Hub", then H1 **"Your report starts when the job does"** / "Work
  Pulse is done, and it holds. The other half is a job to measure it against, and you
  haven't started one yet — so there is nothing to report, and we won't invent one.
  Once you're in a role, sixteen questions about it bring the report back the same
  day." / "Until then, FocusType and ManagerMatch need no employer, and they're most
  useful while you're choosing between offers."
  → Buttons **"Start FocusType"** and **"Start ManagerMatch"** (no arrows), then "How
  this works, and what we hold back". **There must be no environment-report CTA
  anywhere on this screen.**
- **S21.3** — Go to `/environment-report` **directly by URL**.
  → Eyebrow "Situation Report", H1 **"There's no job to describe yet"** / "These
  questions ask about a role you've held, and you've told us you're heading into your
  first one. So we skip the form rather than ask you to invent answers about a job you
  haven't had." / **"Back to your Situation Report →"**.
  → **Three independent gates** land here: the report state
  (`can_submit_environment_report: false`), the live profile status, and a 409
  `first_job_no_role` on submit. The direct-URL one is the one a curious user will
  hit; confirm it holds.
- **S21.3a** — **(New step.)** Go to `/environment-report/past` directly by URL.
  → H1 **"There's no earlier job to describe"** / "This form asks about a job you've
  held before, and you've told us you're heading into your first one. There's nothing
  to fill in here." / **"Back to your Intelligence Hub →"**.
- **S21.4** — Check the dashboard card.
  → Eyebrow "Situation Report", H2 "Your report starts when the job does" / "Work
  Pulse is done and it holds. The other half is a role to measure it against, and you
  haven't started one yet — so there's nothing to report, and we'd rather say so." +
  link "See your Situation Report →".
  → Under "Next": **"Start FocusType →"** / "How you concentrate — worth knowing while
  you're choosing, not after."
- **S21.5** — Check `/intelligence`.
  → **Verified 2026-10-25, prod and branch:** for `first_job` the hub shows **no**
  Situation Report card, **no** "Describe your job" card and **no** "Your earlier job"
  card. All three conditions are false, so nothing renders. That is silence by
  design: the source comment says a prompt here would be one the user cannot act on.
  Still open for Sebastian: is silence right, or should the hub carry the same
  one-line "starts when the job does" the dashboard card has? Not a defect.


---

### S22 · The past-tense lane

**Account** ACC-4 · career status `between_jobs`

Every Environment Report prompt and option has a past-tense twin, and the whole
Situation Report turns forward-facing. Prod and branch are identical here except for
the question count (16 on prod, 21 on the branch).

- **S22.1** — Register ACC-4, complete Work Pulse, and set the career status to
  "Currently unemployed".
- **S22.1a** — **(New step; do it now, before S22.2. It cannot be walked once a report
  exists.)** Open `/environment-report/past` by URL.
  → H1 **"Start with your current job"** / "Describe your current or most recent job
  first. Once that's done, you can come back and tell us about the one before it." /
  **"Describe your current job →"** (→ `/environment-report`) / "Not now" (→
  `/intelligence`). This is S25.2.
- **S22.2** — Open `/environment-report`.
  → Eyebrow "Situation Report", H1 **"Now the role you left"**. The lead says "…These
  ask what your most recent role actually offered — how much of the how was yours,
  what the tempo was, how decisions got made. Twelve questions about the work, plus
  four about the setup. About five minutes." **Branch only — not on prod until the
  next merge:** "…plus four about the setup, then five optional ones about how it
  went. About five minutes." Then "Describe the role as it actually was, not as the
  job description had it. …", plus the extra line: "Because that role is behind you,
  your report comes back facing forward — what to look for next, rather than what to
  change where you are."
- **S22.3** — Walk every question and **check that every prompt and every option is in
  the past tense.** The source was audited 2026-10-25: all 12 dimension items, the 4
  context items and (branch) the 5 outcome items have clean past twins, e.g. "How much
  say did you have over how your work got done?", "Overall, how well was that role
  working for you?", "Back then, how likely did it seem that you’d still be in that
  role a year later?". Options that are noun phrases ("A large organization —
  thousands of people, established in its market.") are the same in both tenses on
  purpose. **The stragglers are on the report, not the form** (S22.6a, `G52`).
- **S22.4** — Submit and read the report.
  → H1 **"What to look for next"** (not "You, and this job"). Lead: "{Dimension} was
  where you and that role sat furthest apart. What comes first is what to look hardest
  at in the next one." Then the honesty line: "If you and that role fitted on some
  dimension, it is not listed below: the report can see that the job ended, not why."
  → Only strained or notable rows are listed. **Aligned rows are dropped.**
- **S22.4a** — **(New step.)** Check the dashboard card.
  → H2 "What to look for next" / "Where you and that role pulled apart, furthest
  first." + bucket chips + "See your Situation Report →".
- **S22.5** — Check the direction words. → "Less than you needed" / "More than you
  needed": past tense.
- **S22.6** — Open a row.
  → The diagnosis paragraph is the forward-facing text, beginning "What to seek: …".
  There are **two tabs**: **"What to look for"** (only a row labelled **"What to watch
  for next time"** and its signal, with no experiment name, steps or button) and
  **"Why it rarely moves"**. **"Negotiate it" is absent.**
- **S22.6a** — **(New step.) Present-tense stragglers on the report**, prod and
  branch (`G52`). Expect to see them; note them, don't re-diagnose:
  → Every row's one-line takeaway is the **present-tense headline**, e.g. "The role
  decides more of the how than you want decided", "More gets rebuilt here than you
  would rebuild". The server has no past headline to send.
  → "Why it rarely moves" keeps the current-role rows "What staying costs" / "What
  that means", whose text talks about "here".
  → The panel "The job, or your manager?" reads "Some of what feels like the job may
  be your manager…" + "Profile your manager", and a strained Feedback row still offers
  "Profile your manager". That manager belongs to a job this user has left.
- **S22.7** — Look for the experiments section.
  → **It does not render at all** in the forward-facing state, and no row carries a
  start button. You cannot run an experiment on a job you have left. Verified
  2026-10-25.
- **S22.8** — If nothing strained: no lead line, no honesty line, just a box reading
  "Nothing came back to carry forward: on every dimension we measure, you and that
  role were set much the same way. That is worth knowing about the kind of role to
  look for, even though the report will not turn it into an instruction."
- **S22.9** — **(New step; optional, and it mutates ACC-4 last.)** Set ACC-4 to
  "Currently employed" on the Experience tab, then reload the report.
  → A banner: "Your career status says you're in a job now, but this report is about
  the one you left. Describe where you are now and the report will be about this
  job." + **"Describe your job"**. `/environment-report` now renders in the present
  tense. Set the status back to "Currently unemployed" and the banner clears.


---

### S23 · Emails and scheduled jobs

**Ops-side. Not walkable from a browser alone.** Re-derived 2026-10-25 from `solverah/infra/email.py`, `solverah/services/outbox.py`, `solverah/cli.py` and `render.yaml`.

There are exactly five email topics in the product (`outbox.TOPICS`). Three reach users; two go to `info@solverah.com`. None has changed since the old doc.

| Email | Subject | Trigger | Link |
|---|---|---|---|
| Verification | **"Your Solverah verification code"** (heading "Confirm your Solverah account") | register, resend, intake account creation | **none** — code only; "This code expires in 15 minutes. If you didn't create a Solverah account, you can safely ignore this email." |
| Sign-in code | **"Your Solverah sign-in code"** (heading "Your Solverah sign-in code") | `/auth/password/forgot`, only for confirmed accounts | **none** — code only; "This code expires in 15 minutes. If you didn't request this, you can safely ignore this email — your password has not changed." |
| Pulse prompt | **"How's work been going?"** ("Three quick questions, about a minute.") | `flask pulse send-prompts` cron only | **`{APP_BASE_URL}/pulse`** (default `https://solverah.com/pulse`), button "Check in"; optional line "We've slowed these check-ins down to once a month since it's been quiet -- no rush, and you can check in any time." |
| Intake notification | "New Early Access Submission" | resume intake finalised | ops only |
| Early-access notification | "New Early Access Modal Submission" | early-access modal | ops only |

- **S23.1** — Confirm both user-facing codes expire at **15 minutes** and that the copy says so ("This code expires in 15 minutes.").
- **S23.2** — Confirm the pulse email's only link is `/pulse` and that it **carries no token** — a plain authenticated route with no expiry. Clicking it signed out goes through `/login` and returns you (S6.12).
- **S23.3** — Check the crons in the Render dashboard, not in `render.yaml` (that file still governs nothing; see §0.6). What `render.yaml` *describes*, for reference:
  → `solverah-outbox-sweep` every 5 min (`flask outbox sweep`) — **load-bearing**: without it, any email that failed its first send never retries.
  → `solverah-retention` daily 04:30 UTC (`flask retention run && flask retention cleanup`). `run` deletes delivered outbox rows (older than 72 h), terminal jobs, dead sessions (30 d), stored path fits and narratives (30 d). **Never signs a live user out.**
  → `solverah-backups` daily 03:30 UTC (`flask backups run`, Docker runtime).
  → `solverah-corpus-refresh` quarterly, 05:00 UTC on 1 Jan/Apr/Jul/Oct (`flask corpus refresh`) — builds a candidate corpus; does **not** put it into service.
  → **Branch only:** `solverah-companies-sweep` every 10 min (`flask companies sweep`) — reaps stuck CompanyLens research runs.
- **S23.4** — **Check whether `flask pulse send-prompts` exists as a cron at all.** It is **still not in `render.yaml`** (`grep -n pulse render.yaml` returns nothing at HEAD) and is only step 4 of the deploy runbook. Without it **no prompt email ever sends, silently**, and the whole Pulse cadence system — including the anti-nag slowdown — is inert. `G18`, **still open**. Confirm in the dashboard; this remains the highest-value item in this scenario.
- **S23.5** — `retention_cleanup.py` is **no longer a standalone script** (`be4761b`, on prod): it is `flask retention cleanup`, with `--dry-run`, and `render.yaml` chains it onto the retention cron. It enforces: abandoned intake submissions older than 90 days whose email never became a confirmed account (row and R2 resume deleted), audit-log IP and user-agent nulled after 365 days, and R2 objects under `intake/` and `profile/` that no row references past 48 h. **Whether it is live depends on the dashboard cron's command and on the `S3_*` variables being added to that cron by hand** — `render.yaml` itself says to change the dashboard command only after the runbook's dry run. Confirm in the dashboard. If it runs, an early-access submitter returning after 90 days gets "Submission not found" and their uploaded resume is gone; that is the policy, not a bug.
- **S23.6** — Confirm a keyless environment fails **silently to the user**: registration still returns 201 and sends the user to `/verify-email`, and they wait forever. **Partly changed:** the operator now has two traces — the boot log's `providers.resend` flag and an outbox row that parks after 8 attempts — but `/healthz` checks nothing external by design and `/readyz` checks the database only, so nothing alerts. Still open as a launch decision: does it need a health or alert check?
- **S23.7** — *(new)* Confirm the code email actually lands. The sender is `EMAIL_FROM` (default `no-reply@solverah.com`) through Resend. Register a throwaway on a Gmail and an Outlook address and note: time-to-arrive, inbox vs spam, and whether the 40px code box renders. A code that arrives after 15 minutes is already expired (S5.5).


---

### S24 · Trait preferences (tolerance and must-haves)

**Branch only — not on prod until the next merge.** Commit 2cd89a6 (2026-10-14), the
route `/trait-preferences`, and `GET`/`PUT /me/trait-preferences` are all absent from
`origin/main` 02707ab. On prod, Finish on Work Pulse goes straight to the completion
card, `/trait-preferences` falls to the catch-all `*` route and is redirected to `/` (S1.11), and none of the
Situation Report tolerance lines exist. **Walk S24 only after the merge.**

**Account** ACC-1, straight after S8.6 · **Routes** `/work-pulse` (the step, in
place), `/trait-preferences` · **Six traits × two questions + up to 2 must-haves, ~2
minutes** · **Precondition:** none enforced; it is meant to follow Work Pulse.

Draft storage: **none.** The answers live in component state until Save.

**Where it sits.** Shown once, in place, right after any Work Pulse sitting is saved —
the first one or a retake. Optional. After that it is reached from the Work Pulse
completion card ("Change how much give you have on each area →"), the CompanyLens page
and a company's detail page ("Tell us how much give you have", both branch-only), and
nowhere else — not the hub, dashboard or header.

**When it counts for the Situation Report (D-15 pin, 791cf9e).** The report reads the
newest answers saved *at or before* the report came into being; failing that, the
*first* answers saved after the Work Pulse sitting it is pinned to. Any later change
waits until you retake Work Pulse and press "Re-read this against my latest Work
Pulse". CompanyLens uses the newest answers immediately. **Walk order:** answer the step
at S24.1–S24.6 **before** the Environment Report (S9), with at least one trait set to
"A lot is fine" in both directions and one must-have, so that S10 has a tolerance line
and a must-have pill to show.

- **S24.1** — Finish Work Pulse (S8.6).
  → In place of the card: eyebrow "✦ Work Pulse Complete"; "Loading…" briefly; H2
  "How much give is there?"; "No job matches what you prefer exactly. For each of the
  six areas Work Pulse covers, tell us how far a job could drift from what you prefer,
  in either direction, and still be fine. Then mark up to 2 you won't bend on.";
  "Optional, and you can change it any time. Employers never see these answers."
- **S24.2** — Read the six sections, in this order.
  → "Autonomy" / "How much say you have over how, and in what order, your work gets
  done." · "Pace" / "How fast the work moves and how quickly things are expected to
  happen." · "Collaboration" / "How much of the work happens together with other
  people rather than on your own." · "Feedback" / "How often, and how directly, you
  hear how your work is landing." · "Innovation" / "How much of the work is building
  new things and taking bets, rather than improving what exists." · "Decision-making"
  / "How much decisions rest on numbers and evidence, rather than judgement and
  experience."
  → Each has two questions, "If your job had more of this than you prefer" and "If
  your job had less of this than you prefer", with three radios: "Not at all" / "A
  little is fine" / "A lot is fine"; and a checkbox "{Trait} is a must-have for me".
  → **Nothing is pre-selected** on a first sitting. **Nowhere does it tell you where
  you landed on a trait** — by design (D-15), the questions are framed against "what
  you prefer". If you see a position, a word like "high", or a number, that is the bug.
- **S24.3** — Answer only some.
  → "Save" is disabled and beside it: "Answer both questions for all six to save."
  Below the sections: "Must-haves picked: 0 of 2."
- **S24.4** — Tick two must-haves.
  → The line becomes "You've picked 2 must-haves, the most you can choose. Untick one
  to pick another." The other four checkboxes grey out and cannot be ticked. Untick
  one: they come back, and the line reads "Must-haves picked: 1 of 2."
- **S24.5** — **Reload in the middle of the step.**
  → The completion card, not the step. Nothing was saved and nothing is kept. The only
  way back is the card's "Change how much give you have on each area →" (S24.8).
  Same thing if you navigate away. Expected: there is no draft.
- **S24.6** — Answer all twelve and press **Save**.
  → "Saving…", then the completion card (S8.7). **No "saved" message anywhere.**
  `G48`.
  → *(Alternative, on another account or before saving:)* **"Skip for now"** → the
  card. Writes nothing; matching and the Situation Report behave exactly as before the
  step existed.
- **S24.7** — **Save failure.** Block `PUT …/me/trait-preferences`, press Save.
  → In red: "We couldn't save these. Your choices are still here, so please try
  again." Your choices are still selected; "Save" is live again. The UI shows that one
  message for every failure, including the server's 400 `invalid_trait_preferences`.
- **S24.8** — From the card, press "Change how much give you have on each area →".
  → `/trait-preferences`: eyebrow "Work Pulse"; then "Changes show up in CompanyLens
  right away. Your Situation Report picks them up the next time you re-read it against
  a new Work Pulse."; the same form, **pre-filled with what you saved**; the secondary
  button reads **"Cancel"**, not "Skip for now".
  → Save or Cancel both land on `/work-pulse` (the card), again with no confirmation.
  Each Save is a new stored sitting; earlier ones are kept.
  → **Check that note against S24.10/S24.11** — it is wrong for some users.
  `G49`.
- **S24.9** — **Failed read.** Block `GET …/me/trait-preferences`, reload
  `/trait-preferences`.
  → "Loading…" for a few seconds, then a **blank** form — no error, nothing selected.
  Deliberate ("the step must never stand between them and the rest of the product"),
  but it reads as "my answers were lost"; Cancel leaves the saved ones intact.
- **S24.10** — *(After S9, S10.)* Read the Situation Report.
  → On a must-have trait, a small "Must-have" pill beside the dimension name; inside a
  severity tier, must-haves sort first.
  → On a row that is aligned only because of the range you gave: "This isn't quite
  what you prefer, but it's inside the range you said you're fine with." Never a step
  count, a range, or a number.
- **S24.11** — Change a tolerance at `/trait-preferences`, Save, reopen
  `/situation-report`, press "Re-read this against my latest Work Pulse".
  → Nothing moves: "Already reading your most recent Work Pulse sitting — nothing
  moved." That is the D-15 pin working. Now retake Work Pulse (S8.8a), skip or answer
  the step, and press Re-read → "Re-pinned. This report now reads your most recent Work
  Pulse sitting." and the newest tolerance applies.
  → **Exception to test:** if you skipped the step at S24.6, the *first* answers you
  save at `/trait-preferences` apply to the report **at once**, without a retake — the
  opposite of what S24.8's note says. Only the second change waits. `G49`.
- **S24.12** — *(ACC-3 or a fresh account, before any Work Pulse.)* Type
  `/trait-preferences`.
  → It opens and saves. No gate, nothing about Work Pulse; Cancel/Save land on the Work
  Pulse form. The note promises "Changes show up in CompanyLens right away", but
  CompanyLens asks for Work Pulse first. An answer given now does count once Work Pulse
  and the Environment Report are in (tested behaviour). `G50`.


---

### S25 · The past-job report

**Accounts** ACC-1 (employed) for the main walk; ACC-4 for the gate in S22.1a; ACC-3
for the `first_job` refusal in S21.3a · **Route** `/environment-report/past` · **On
prod since 2026-10-01** (d8406c2, e8a9a72) · 16 questions on prod, 21 on the branch.

**Why this is its own scenario and not part of S22:** it is not a between_jobs
feature. Any user with a current report can file it, the employed main account
included. It has its own route, its own draft key, three gates of its own and a
thank-you ending instead of a report. It is also **one-shot per account**: filing it
permanently removes both entry points, which is the same trap as S12.7. Walking it
inside S22 would leave ACC-1's copy unwalked.

What it is (ruling 2026-10-01): **one** report per user, about the job *before* the
current or most recent one, accepted only once a current-job report exists. It is
stored and exported, feeds only the exploratory outcome analysis, and **never
changes the Situation Report** beyond hiding its own entry points. No gap view and
no numbers (D-15).

- **S25.1** — With ACC-1's report complete (after S10), find the two entry points.
  → In the report footer: **"Tell us about the job before this one →"**.
  → On `/intelligence`, a card: eyebrow "✦ Your earlier job" / "Tell us about the job
  before your current or most recent one. It won’t change your Situation Report — it
  helps Solverah learn which gaps matter most. About five minutes." / **"Describe your
  earlier job →"**. (Hidden for `first_job`.)
- **S25.2** — The no-current-report gate: walk it as S22.1a on ACC-4. → "Start with
  your current job" as quoted there. If the server refuses on submit instead (409
  `current_report_required`), you land on the same card.
- **S25.3** — Open it from either entry point and read the intro.
  → Eyebrow "Your earlier job", H1 **"Now the job before that one"**, then:
  - **On prod today:** "The same questions you answered about your work, asked about
    the job before your current or most recent one. Twelve about the work, four about
    the setup. About five minutes."
  - **Branch only — not on prod until the next merge:** "… Twelve about the work, four
    about the setup, and five optional ones at the end. About five minutes."

  → Then "Describe it as it actually was. It won't change your Situation Report — it
  helps Solverah learn which gaps matter most." / "This is a private working note.
  Nobody at any employer can see it." + "How this works, and what we hold back →" /
  **"Start"**.
- **S25.4** — Answer a few questions.
  → Same order and options as S9.3, but **always past tense, even on an employed
  account**: e.g. "How big was the organization you worked for in that role — the
  whole organization, not your team?" The eyebrow reads "Question {n} of 16" on prod
  and "of 21" on the branch.
- **S25.5** — Reload.
  → The resume card again, with its eyebrow reading **"Your earlier job"**. Then open
  `/environment-report` in the same tab: it must **not** offer to resume this draft
  (separate keys, `env_report_answers_past` vs `env_report_answers`). Come back and
  pick up where you left off.
- **S25.6** — Finish.
  → Spinner + **"Saving your answers…"** (not "Building your Situation Report…"), then
  a card in place: eyebrow "Saved" / H1 **"Thanks — your earlier job is saved"** /
  "This doesn't change your Situation Report. It helps Solverah learn which gaps
  between a person and a job matter most, so the guidance gets better for you and for
  everyone after you." / **"Back to your Intelligence Hub →"**. It does not navigate
  to the report.
- **S25.7** — Open `/situation-report` and `/intelligence`.
  → The report is unchanged: same rows, same order. The footer link and the hub card
  are both **gone**.
- **S25.8** — Go to `/environment-report/past` again by URL.
  → H1 **"You've already described your earlier job"** / "We only ask about one
  earlier job, and yours is saved. Thanks for filling it in." / **"Back to your
  Intelligence Hub →"**. The same card answers a 409 `past_report_limit` on a
  double-submit.
- **S25.9** — (Only on an account with no career status; see S9.10a.) Finish the past
  form. → "One thing first: where are you right now?". After you set a status, the
  profile asks "Go back to the form about your earlier job?".

---

## 3. Coverage map

Every route in `src/app/App.tsx` at `6e51713`, and where it is walked.

### Public

| Route | Scenario |
|---|---|
| `/` | S1, S3 (signed in: redirects to the dashboard, S5.10a) |
| `/start` | S2 (unlinked — `G24`) |
| `/login` | S5.8–S5.10a, S6.7, S6.10, S6.13 |
| `/register` | S5.1–S5.4 |
| `/verify-email` | S5.5–S5.7 |
| `/confirm-email`, `/check-email` | S5.11 (legacy aliases) |
| `/forgot-password` | S6.1–S6.3, S6.6 |
| `/forgot-password/verify` | S6.4, S6.4a, S6.5 |
| `/privacy`, `/terms` | S1.7, S1.8 |
| `/how-matching-works` | S1.9 |
| `/quiz-preview` | S4.1, S4.7, S4.11 |
| `/quiz-preview/insights` | S4.5, S4.6 |
| `/quiz-preview/early-career`, `/career-transition`, `/mid-career`, `/teen-focused` | S4.2–S4.4 |
| `/quiz-preview/career-job-search` | S4.9 |
| `*` (incl. `/landing`, `/nope`, `/quiz-preview/<unknown>`) | S1.10 (retired), S1.11, S4.10 |

### Authenticated (`RequireAuth`, role `job-seeker`)

| Route | Scenario |
|---|---|
| `/job-seeker/dashboard` | S7, S13.15 |
| `/job-seeker/profile` | S19 (career status: S19.7–S19.10b) |
| `/settings` | S20 |
| `/assessment` | S8.1 |
| `/work-pulse` | S8; S24.1–S24.7 (**branch**) |
| `/work-pulse/results` | S8.9 |
| `/trait-preferences` | S24.8–S24.12 (**branch only**; on prod it falls to `*`) |
| `/environment-report` | S9, S21.3, S22.2 |
| `/environment-report/past` | S25, S21.3a, S22.1a |
| `/situation-report` | S10, S11, S12, S21.2, S22.4, S25.7 |
| `/pulse` | S13.1–S13.6, S6.12, S23.2 |
| `/pulse/trend` | S13.7–S13.14 |
| `/manager-match` | S14.2–S14.3a |
| `/manager-match/results` | S14.4 |
| `/manager-profile` | S14.1, S14.6–S14.8 |
| `/manager-profile/playbook` | S14.5, S14.9, S14.10 |
| `/focus-type` | S15 |
| `/focus-type/results` | S15.4 |
| `/intelligence`, `/solverah-profile` | S16 |
| `/intelligence/paths` | S16.9–S16.12c |
| `/trust` | S16.13 |
| `/quiz-insights` | S16.15 |
| `/career-quizzes` + 4 variants | S16.14–S16.14b |
| `/career-job-search` | S16.14c |
| `/agent` | S18 |
| `/search` | S17.1a, S17.3 |
| `/feed` | S7.10a, S17.5, S17.5a |
| `/company-lens` | S17.6 (prod); S17.6a–S17.6h (**branch**) |
| `/companies/:id` | S17.7 (prod); S17.7a–S17.7f (**branch**) |

**Removed since the first version:** `/landing` (2026-09-28, `eeba7b7`) and
`/future-your-way` (2026-10-05, `882ac5a`).

---

## 4. Appendix A — draft storage keys

All client-side. **Nothing is drafted server-side anywhere in the product.** Every
draft key below is swept at explicit logout and at account deletion
(`draftStorage.ts`), but **not** when a session expires silently (S6.9).

| Key | Storage | Surface | Survives reload? | Survives tab close? |
|---|---|---|---|---|
| `solverah_assessment_answers` | session | Work Pulse core (24), first sitting and retake | yes — resume card, then the first unanswered question | no |
| `env_report_answers` | session | Environment Report (16 on prod, 21 on the branch) | yes — resume card | no |
| `env_report_answers_past` | session | past-job form `/environment-report/past` (S25) | yes — resume card | no |
| `mm_answers:{userId}` | session | ManagerMatch (15). The old bare `mm_answers` is deleted on sight | yes — resume card | no |
| `mp_answers` | session | Manager Profile (16). **Not user-scoped** — `G59` | yes — resume card | no |
| `focus_type_draft:{userId}` | session | FocusType, finished scenes only. The old unscoped key is deleted on arrival | yes — resume card, then the first unfinished scene | no |
| `solverah_wp` | session | retired 12-question Work Pulse — **nothing writes it** since 2026-10-02; read as a cache only | — | no |
| `solverah_intake` | session | `/start` wizard | yes | no |
| `pendingQuizSave` | **local** | guest quiz answers + insight, for the replay and for `/quiz-preview/insights` | yes | **yes** |
| `guestQuizCompletedAt` | **local** | one-quiz guest lockout — **not** swept at logout, on purpose | yes | **yes** |
| `solverah.hasSession` | **local** | refresh hint on boot; holds `/`, `/login`, `/register` behind a skeleton during the probe | yes | yes |
| — none — | — | **Pulse check-in**, **tolerance step** (branch), signed-in career quizzes, profile form, agent chat | **no** | no |

Router state (not storage, lost on reload): `/verify-email` `{email, from}`,
`/forgot-password/verify` `{email}`, `/login` `{from}`, `/` `{accountDeleted,
filesLeftBehind}`. Branch CompanyLens keeps a pasted posting id in the URL
(`?posting=` on `/companies/:id`).

---

## 5. Appendix B — the error codes the UI branches on

When a step fails, these are the strings that decide which screen you get. A fix
chunk should branch on the `code`, never on the prose.

| Code | Status | Screen it produces |
|---|---|---|
| `no_core_sitting` | 409 | Recalibrate footer: "There is no Work Pulse sitting to pin to yet." Unreachable from the UI (the button renders only on a complete report). |
| `no_manager_match` | 409 | `/manager-profile` pre-question gate (S14.1) and the playbook: "Take ManagerMatch first". Hub card: "Take ManagerMatch first — the Decoder diffs your manager profile against it." |
| `no_manager_profile` | 409 | Playbook gate: "Profile your manager". On `/manager-profile` it means "go ahead" (no screen). |
| `first_job_no_role` | 409 | Environment Report: "There's no job to describe yet". Past form: "There's no earlier job to describe". |
| `career_status_not_set` | 400 (legacy `{"error": …}` body; the client matches the message) | Environment Report and past form: "One thing first: where are you right now?"; Path Intelligence: "Set your career status to get started." |
| `current_report_required` | 409 | Past form: "Start with your current job" (S25) |
| `past_report_limit` | 409 | Past form: "You've already described your earlier job" (S25) |
| `experiment_already_active` | 409 | **No longer silent:** "Another experiment is already running — finish or abandon that one first. We've refreshed this page to show it." + refetch |
| `not_a_change_in_place_cell` | 422 | "We couldn't start that just now. Please try again in a moment." (unreachable from the UI) |
| `invalid_checkin` | 422 | Pulse: refetches the questions and shows "This check-in was out of date, so we've refreshed the questions. Check your answers and tap Done again." |
| `invalid_cadence`, `invalid_event` | 422 | **Not branched on** — the generic "We couldn't save that just now. Try again." |
| `invalid code` | 400 | Verify-email: "That code didn't match. Check the six digits and try again, or request a new code below." (`G8` closed) |
| `code expired` | 400 | Verify-email: "That code has expired. Request a new one below and we'll send it right away." |
| `invalid_or_expired_code` | 400 | Forgot-password verify: "That code is invalid or has expired. Request a new one below and try again." |
| `email and code are required` | 400 | Either code screen: "Please enter the 6-digit code from your email." |
| "already exists" (substring) | 400 | Register: "An account with that email already exists" |
| "email not confirmed" (substring, case-insensitive) | 403 | Login: "Your email is not confirmed. Please check your inbox." + "Resend verification code" |
| `Invalid credentials` / `Account locked. Try again later.` / any 429 | 401 / 423 / 429 | Login: "Failed to sign in. Please check your credentials." — all folded together |
| `rate_limited` | 429 | Register / verify / forgot / agent: **raw** "N per 1 minute" (`G33`). Path Intelligence and CompanyLens use their own 429 copy |
| `profile_incomplete` | 400 | Path Intelligence: "Add a job title and a few skills to get started." (normally pre-empted by the skills gate) |
| `corpus_unavailable` | 503 | Deep fit / wants save: "We couldn't reach the occupation data just now. Give it a moment and try again."; scoring job: "We couldn't load your path suggestions right now." |
| `unsupported_occupation` / `unknown_occupation` / `invalid_onet_code` | 404 | Deep fit: "There isn't enough detail about this occupation to break it down." / "This path isn't available any more. Refresh your suggestions to see the current list." / "Something went wrong opening this path." (no retry) |
| `not_offered` | 422 | Wants save: "Your job details changed, so we've reloaded this. Have another look and press the button again." |
| `agent_model_unavailable`, `agent_unavailable` | 503 | Agent: "The assistant is unavailable right now. Please try again in a few minutes." |
| `agent_failed` | 500 | Agent: "Something went wrong generating a reply. Please try again." |
| `agent_stream_interrupted` | SSE event | Agent: "The reply was interrupted. Please try again." |
| **Branch:** `invalid_trait_preferences` (+ sub-codes) | 400 | Not branched on — generic "We couldn't save these…" (S24.7); the client normally cannot produce one |
| **Branch:** `research_daily_limit` | 429 | "You've started research on five new companies today…" |
| **Branch:** `research_disabled`, `provider_unavailable` | 503 | "Company research isn't available right now. Please try again a little later." (branches on status) |
| **Branch:** `/me/matches`, `/companies/{id}/read` `state` (`core_required`, `no_companies`, `ranked`, `not_enough_evidence`, `not_researched`) | 200 | Body states, not errors; each has its own screen in S17.6b–S17.7c |
| `retake_cooldown` | 409 | **Dormant** (`CORE_RETAKE_COOLDOWN = None`). If switched on, the client would show only the generic submit message |
| `moved_to_scoring_jobs` | 410 | Not user-facing; a client calling the retired sync submit path |
| `kind_retired` | 410 | Not user-facing; any write to the retired `work_pulse` kind |

**Two error shapes coexist in this API**, which matters when reading a failure in
devtools: RFC 9457 problem+json (`application/problem+json`, with `errors[].code`) for
anything raised as an `ApiError` or an HTTP exception, and a legacy `{"error": "..."}`
string for handler branches. A third shape, `{"msg": "..."}`, comes from
flask-jwt-extended's own defaults on any auth failure.

---

*Re-derived from source at `6e51713` (`causal_bayesian_model`), checked against
production at `02707ab` (PR #160), 2026-10-25. When this document and the product
disagree, the product is right and this document is a bug — file it the same way,
against the step ID.*
