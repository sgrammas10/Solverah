# User scenarios — the prod walkthrough

**What this is.** Every surface a real person can reach in Solverah, in the order a
person actually reaches them, with the exact thing each screen should say. It exists
to be *walked*, on production, by a human — not to be read. Each step has a stable
ID. When a step does not do what it says here, write the ID down; a fix chunk gets
opened against that ID and nothing else has to be re-explained.

**Who it's for.** Sebastian, walking prod. Secondarily the agents who pick up the
broken IDs afterwards — which is why every step carries the exact copy and the exact
error `code` rather than a description of them.

**Provenance.** Derived by reading the code at commit `b5b8eec`, which is
`origin/main`, which is what production runs. There is no branch drift to account
for: what is written here is what is deployed. If you walk this after the next
deploy, re-derive anything that looks off before filing it.

**Status.** Written 2026-09-14. Never walked. Every expectation below is read out of
the source, not observed in a browser — which is exactly why walking it is worth
doing.

---

## 0. How to walk this

### 0.1 · The ID scheme

- `S<n>.<step>` — a walkthrough step, e.g. `S8.4`. Stable. Do not renumber; if a step
  is inserted later it gets a letter (`S8.4a`).
- `G<n>` — a **known gap**, already understood, listed in §1. If a step fails and the
  failure is a listed `G`, note it as `S8.4 → G7` and move on. Don't re-diagnose it.

### 0.2 · What to record

For each failure, three lines is enough:

```
S10.6  — expected the "Change it in place" register, got nothing at all
         Chrome 141, desktop, ACC-1, 2026-09-15 10:22
```

The exact copy is in this document, so you don't need to transcribe what you saw
unless it differs in a way that matters (wrong words, not just wrong screen).

### 0.3 · Ordering

The scenarios are in dependency order and the numbering follows the product's
precondition spine:

```
Work Pulse (24)  →  wp_v2_completed  →  Environment Report (15)  →  Situation Report complete  →  Experiments
ManagerMatch (15)  →  Manager Profile (16)  →  Playbook
FocusType, Pulse   →  no preconditions, walk any time
```

S1–S7 are one sitting (roughly an hour). S8–S16 are the product proper and want a
second sitting of about two hours, because the instruments are 24 + 15 + 15 + 16
questions and you must answer them honestly for the reports to say anything real.
S17–S23 are short.

### 0.4 · Accounts you need

Five, because career status changes the copy of an entire lane and most instruments
cannot be un-taken from the UI.

| Account | Career status | Walks | Notes |
|---|---|---|---|
| **ACC-1** | employed | S7–S20 | the main lane; do the full spine on this one |
| **ACC-2** | — | S4, S5 | created *through* the guest-quiz replay, to prove the replay |
| **ACC-3** | `first_job` | S21 | never-employed lane; Situation Report deliberately refuses to assemble |
| **ACC-4** | `between_jobs` | S22 | past-tense lane; every prompt has a past twin |
| **ACC-5** | unconfirmed | S6 | register, then never verify |

**Freeing an address for reuse.** Account deletion tombstones the row and rewrites
the email to `deleted-{id}@tombstone.invalid`, which frees the original address for
re-registration. There is no UI for it (that is `G1`), so it is an API call, and on
prod that means carrying the session cookie plus the `X-CSRF-TOKEN` header to
`DELETE /api/v1/me` with body `{"confirm": "DELETE"}`. Simpler for a walkthrough:
use distinct addresses per account. Plus-addressing (`you+acc1@…`) is untested
against the registration validator — if it bounces, that is worth its own note, not
a workaround.

### 0.5 · Things that will look broken but are not

Read this list before you start or you will file five bugs that aren't.

1. **Work Pulse has no results page.** Finishing the 24 questions shows a completion
   card in place and navigates nowhere. This is deliberate — returning dimension
   scores hands a retaker a gradient to optimise against.
2. **Work Pulse and Environment Report restart at question 1 after a reload.** Your
   answers are preserved and pre-selected with a ✓; only the position is lost.
   Manager Profile and ManagerMatch *do* resume at the right index. The
   inconsistency is real but known.
3. **Every draft lives in `sessionStorage`, never on the server.** Close the tab and
   an unfinished instrument is gone. Nothing is wrong when that happens.
4. **`recalibrated: false` is a success.** "Already reading your most recent Work
   Pulse sitting — nothing moved." means the pin was already current.
5. **No numbers in the Situation Report.** Three bucket words and one direction
   phrase, never a score, bar or percentage. If you see a digit in a strain card,
   *that* is the bug.
6. **The Situation Report dashboard card renders nothing while loading and nothing
   on error.** A card that cannot say anything true says nothing.
7. **`/assessment` is a pure redirect** to `/work-pulse`.

### 0.6 · Environment preconditions

These are not UI. Check them before blaming a screen.

| Thing | Needs | If missing |
|---|---|---|
| Any verification / reset code | `RESEND_API_KEY` in the API env | Registration still returns 201 and sends you to `/verify-email`; the code never arrives and **nothing surfaces anywhere**. Silent. |
| A code that failed its first send | `flask outbox sweep` cron running (`*/5 * * * *`) | The retry never happens; the row parks after 8 attempts and is never deleted |
| Pulse prompt emails | the `flask pulse send-prompts` cron existing at all | No prompt email ever sends, silently. **This cron is not in `render.yaml`** — see `G18` |
| Agent chat | `GROQ_API_KEY` (not `GROQ`… not OpenAI) | `/agent` answers 500 and the banner reads `Failed to generate response` |
| WPLL teaser, path suggestions | `OPENAI_API_KEY` | The scoring job fails; the UI shows its generic retry card, not a distinct message |

---

## 1. Known gaps — expected failures

Already understood. Do not file these; reference them.

| ID | Gap | Where |
|---|---|---|
| **G1** | **No account-settings screen exists.** `GET /api/v1/me/export` and `DELETE /api/v1/me` are implemented and tested, but nothing in `src/` calls either. Meanwhile the shipped Privacy Policy ("Download a copy of your data from your account settings at any time"), the Terms ("delete your account at any time in account settings") and `/trust` ("You can delete your account and the data behind it") all promise a screen that does not exist. This is a live copy/compliance mismatch, not just a missing feature. | S20 |
| **G2** | **No mobile menu.** `Header.tsx` has no hamburger and no responsive branch — the same flex row renders at every width, so five nav items plus the user's name overflow on a phone. | S7 |
| **G3** | **The Feed nav item does not navigate.** It calls `preventDefault()` and opens a modal: "Feature coming soon" / "The feed will be available soon. Check back after launch." / "Got it". The `/feed` route exists behind the guard but the header never reaches it. | S17 |
| **G4** | **CompanyLens is coming-soon for everyone**, by decision (⚑3) — the matching model isn't built. Both the Intelligence card and `/company-lens` say so. | S17 |
| **G5** | **Experiments have no loading and no error state.** `experimentsQuery.data?.experiments ?? []` — a failed fetch is indistinguishable from "no experiments", and every start button renders as available. | S12 |
| **G6** | **Environment Report's gate failure is unhandled.** `reportQuery.isError` has no branch, so a failed `GET /me/situation-report` silently renders the intro and un-gates the form. The submit-time 409 is the only remaining catch. | S9 |
| **G7** | **Work Pulse's load-failure state has no retry button** — just the raw `error.message` in red. The user must reload or navigate away. | S8 |
| **G8** | **Raw backend strings leak into the verify-email UI**: a wrong code shows `invalid code` and an expired one `code expired`, lowercase, unpunctuated. (The forgot-password twin normalises correctly to "Invalid or expired code. Please try again.") | S5 |
| **G9** | **Intake-created accounts get a 32-char hex** (`uuid4().hex`) rendered in the letter-spaced box of an email that says "6-digit code". The source file's own comment acknowledges it. | S2 |
| **G10** | **`EarlyAccessModal` on `/` is dead UI** — no button on the page ever sets `isOpen`. | S1 |
| **G11** | **`/landing` advertises "For Recruiters"** and is generally stale relative to `/`. No recruiter role exists anywhere in routing. | S1 |
| **G12** | **`?tab=` is unvalidated** on the profile: `?tab=bogus` selects no tab and renders an empty body under the tab strip. | S19 |
| **G13** | **Career-status modal failure is silent** — a failed `PATCH /me/career-status` just re-enables the buttons, with no error copy. | S19 |
| **G14** | **A failed `/me/dashboard` renders the page anyway**, with empty cards and no error message and no loading state. | S7 |
| **G15** | **`/search` has no error state.** A failed fetch leaves `data` undefined and falls into "No results found for …" — a server failure reads as a successful empty search. | S17 |
| **G16** | **Quiz group mismatch:** the guest branch of `NextChapterYourWayQuiz` posts `quizGroup: "careerJobSearch"`, the signed-in branch posts `"careerQuizzes"`. | S4 |
| **G17** | **Wrong-role redirect is unexplained** — `Navigate to="/"` with no state and no copy. Low impact today, since `job-seeker` is the only role. | S6 |
| **G18** | **`flask pulse send-prompts` is not in `render.yaml`.** It exists only in `cli.py` and as a manual dashboard step in the deploy runbook. It is the one scheduled job that puts mail in a user's inbox, and the one not codified. | S23 |
| **G19** | **Guest dead-end on an unknown quiz key:** "Back to Assessments" points at `/intelligence`, which requires auth, so a signed-out visitor bounces to `/login`. | S4 |
| **G20** | **`/quiz-preview/insights` holds its insight in router state only** — refresh or direct-visit loses it and shows "No insights found." | S4 |
| **G21** | **Monthly cadence is a one-way door.** The anti-nag auto-drop sets `monthly`; checking in clears the unanswered counter but never touches the cadence, and `monthly` is not offered in the UI. The only exit is explicitly choosing Weekly / Every two weeks / Off. Worth a ruling on whether that is intended. | S13 |

---

## 2. The scenarios

---

### S1 · First contact, signed out

**Account** none · **Routes** `/`, `/landing`, `/privacy`, `/terms`, `/how-matching-works`

- **S1.1** — Open `https://solverah.com` in a clean browser profile (no cookies, no
  localStorage).
  → The prelaunch landing page. **No global header** and **no global footer** — this
  route suppresses both and renders its own `LandingNav`.
- **S1.2** — Read the hero.
  → Badge "AI-Native Career Platform"; H1 "Modern careers deserve more than
  keywords."; buttons **"Request early access"**, **"Preview what you'll unlock"**,
  "See how it works".
- **S1.3** — Click **"Preview what you'll unlock"**. → `/quiz-preview` (walked in S4).
  Come back.
- **S1.4** — Click each nav anchor: How it works, About, FAQ.
  → Scrolls to `#how-it-works`, `#about`, `#faq`. Sections in page order are HERO,
  STATS BAR, FEATURES, WORK PULSE, HOW IT WORKS, ABOUT, FAQ, CTA, FOOTER.
- **S1.5** — Find the three Work Pulse tier cards.
  → "Work Pulse Lite™" → **"Try it free"** → `/start`; "Work Pulse™" → **"Get
  started"** → `/register`; "Work Pulse Pro™" → button reads **"Coming soon"** and
  is **disabled**.
- **S1.6** — Scroll to the footer.
  → Status blurb: "Soft launch — broader access remains closed. Early cohort intake
  is open." Links to `/privacy`, `/terms`, `/how-matching-works`.
- **S1.7** — Open `/privacy`, then `/terms`.
  → Both render from constants in `src/shared/lib/legal.ts`, not a fetch. Each shows
  a `role="note"` draft banner: "This document is a draft undergoing legal review.
  Its substance reflects how Solverah actually operates today; wording may be refined
  before the effective date is set."
- **S1.8** — In the Privacy Policy, find the access/export and deletion clauses.
  → "Access and export. Download a copy of your data from your account settings at
  any time." and "Deletion. Delete your account from account settings…". **Both
  promise a screen that does not exist** — this is `G1`, and S20 is where it bites.
- **S1.9** — Open `/how-matching-works`.
  → Eyebrow "Transparency", H1 "How matching works", six sections: What Work Pulse
  measures / How matches are computed / What matches are not / Who sees your answers
  / Where AI is involved / Your data.
- **S1.10** — Open `/landing` directly.
  → Dark slate theme, stale relative to `/`. H1 "Perfect Job Matches with Solverah
  Intelligence". Contains a "For Recruiters" section — `G11`. (Signed in, this route
  redirects to `/feed`.)
- **S1.11** — Open a nonsense path, e.g. `/nope`.
  → Redirects to `/`. There is no 404 page anywhere in the app.

---

### S2 · The intake wizard

**Account** none · **Route** `/start` · Fully completable signed out.

State persists to `sessionStorage` key **`solverah_intake`**.

- **S2.1** — Click "Request early access" on `/` (or open `/start`).
  → Four-step wizard, **header suppressed**, own `LandingNav`. Progress dots read
  "Your situation" / "Quick pulse" / "Your focus" / "Get started".
- **S2.2** — Step 1.
  → H1 "What's true for you right now?"; sub "Select everything that resonates —
  there's no wrong answer."; seven checkbox cards. CTA **"See what Solverah sees →"**
  is **disabled until at least one is selected**.
- **S2.3** — Select two or three, continue. → Step 2: "Question 1 of 5", radio-style
  options, "Next" disabled until answered, "← Back" present from here on.
- **S2.4** — Answer all five.
  → Step 3 fires `POST /api/v1/assessments/wpll/scoring-jobs` **anonymously** (no
  credentials) and polls. While pending: spinner + "Reading your responses…".
- **S2.5** — Wait for the teaser.
  → Eyebrow "Here's what's emerging from your responses", the insight card, then
  three locked rows each with 🔒 and "Unlock with a free account" (fallback labels:
  Environmental Friction Score / Work Rhythm Pattern / Emerging Archetype Signals),
  a `TierBar` titled "Your Solverah journey", CTA **"Create my free account →"**, and
  "No credit card required. Takes 60 seconds."
  → **If it fails:** "We couldn't generate your insight right now." / "Please try
  again in a moment." / "Try again". A failure here with `OPENAI_API_KEY` unset is
  §0.6, not a UI bug.
- **S2.6** — Step 4, the account gate.
  → Eyebrow "Your Work Pulse report is ready"; H1 "Unlock your full results"; a ✓
  list of four items; **"Create my free account →"** → `/register?from=wpll`;
  "Already have an account? Sign in" → `/login?from=wpll`.
- **S2.7** — Reload mid-wizard at step 3.
  → Returns to where you were; state is in `sessionStorage`.
- **S2.8** — Complete registration from `?from=wpll` and sign in.
  → On sign-in, `Login.tsx` reads `solverah_intake`, POSTs `/intake/claims` with
  `mode: "session"`, and clears the key. **A failure here is swallowed to the console
  and you still land on the dashboard** — so verify the claim landed by checking the
  profile, not by watching for an error.
  → If the account was created through the intake path, the verification email
  carries a **32-character hex string** in a box that says "6-digit code" — `G9`.

---

### S3 · The hero intake form (resume upload)

**Account** none · **Route** `/` → `#waitlist`

- **S3.1** — Scroll to the hero form, or click "Submit your intake now" in the final
  CTA.
  → Header "Early Access" / "Join the Solverah signal" / "Private intake for
  thoughtful collaborators. Resumes upload to secure storage; we store only what you
  choose to share."
- **S3.2** — Submit empty. → "Please enter your name."
- **S3.3** — Walk the validators one at a time.
  → "Please enter your email." / "Please enter your state / region." / "Please agree
  to the privacy notice to continue." / "Please attach your resume to continue." /
  "Please enter a valid LinkedIn URL."
- **S3.4** — Attach a real PDF and submit.
  → Button reads **"Submitting…"** and is disabled. Three calls in sequence:
  `POST /intake/resume-tickets` → `PUT` to the presigned S3 URL → `POST
  /intake/submissions`.
  → Success: green strip "Thanks — your submission was received." **and** the
  `AccountModal` opens.
- **S3.5** — In the modal.
  → "Next step" / "Save your profile?" / "Create an account and we'll auto-fill your
  profile using your resume. You can edit anything later." Then "We'll populate your
  personal info, work experience, skills, and education using the resume you shared."
  with "Sign in" / "Create account".
- **S3.6** — Create the account from the modal.
  → "Create account" → "Creating…" → "Account created! Your profile has been filled
  in from your resume." + "Continue to login".
- **S3.7** — Look for anything that opens the "Request early access" modal
  (`EarlyAccessModal`).
  → **Nothing does.** It is mounted but no button sets `isOpen`. `G10`.
- **S3.8** — Note the presign TTL is 10 minutes. If you leave the form open longer
  than that before submitting, expect "Upload failed. Please try again." — that is
  correct behaviour.

---

### S4 · The guest quiz and its replay

**Account** ACC-2 · **Routes** `/quiz-preview`, `/quiz-preview/*`
**Requires a clean browser profile** — the gate is a `localStorage` read.

Storage: answers go to **`localStorage["pendingQuizSave"]`**; the one-quiz lockout is
**`localStorage["guestQuizCompletedAt"]`**.

- **S4.1** — Open `/quiz-preview`.
  → Eyebrow "Quiz Preview"; H1 "Get a feel for what Solverah delivers"; sub "Take one
  quiz for free and get immediate, actionable insight. Create an account to save
  results and unlock full profile features." Five cards: Early Career / Career
  Transition / Career & Job Search / Mid-Career / Strategic / Your Future, Your Way
  (Teen-Focused). Each CTA reads "Start quiz".
- **S4.2** — Start Early Career.
  → Header "Quiz 1: Early Career", five radio questions, submit button reads **"Get
  Insight"** (the signed-in version says "Save Answers").
- **S4.3** — Submit **without answering anything**.
  → It submits, with an empty `items` array. There is no validation. Note whether the
  insight that comes back is coherent; if it is confidently wrong about you, that is
  worth a separate note.
- **S4.4** — Answer honestly and submit.
  → Modal "Career Quizzes Insight". While generating: "Generating your insight. This
  can take a few seconds." plus a progress bar that is **fake** (ticks to 90% on a
  timer, not real progress). Close is hidden while loading.
  → Success: "Your insights are ready. Choose where you want to go next." + "View
  insights" / "Back to quizzes" / "Close".
  → Rate limits are `5 per hour; 20 per day` per IP. Hit it and you get the backend
  text or "Too many attempts. Please wait a moment and try again."
- **S4.5** — Click "View insights". → `/quiz-preview/insights`. Cards with "Key
  takeaways", "Combined meaning", "Next steps"; buttons "Back to quizzes", "Sign in to
  save results", "Create account".
- **S4.6** — **Refresh that page.** → "No insights found. Please take a quiz to
  generate insights." The insight lives in router state only — `G20`.
- **S4.7** — Go back to `/quiz-preview`.
  → Now locked: "You've already taken a guest quiz. Create an account or sign in to
  take more and save your results." Every card's CTA is replaced by "Sign in" /
  "Create account".
- **S4.8** — Register **and then sign in** as ACC-2.
  → On sign-in (not on registration — registration routes through `/verify-email` →
  `/login`), `getPendingQuizSave()` fires: `PATCH /me/profile` with the quiz results,
  then `POST /me/quiz-insights`, then redirect to `/quiz-insights?group=careerQuizzes`.
  → **Verify you land on `/quiz-insights` and your answers are there.** If the replay
  fails it logs to the console, silently falls through to the dashboard, and **does
  not clear the pending save** — so it will retry on your next sign-in.
- **S4.9** — Open `/quiz-preview/career-job-search` as a guest and complete it.
  → Same shape, modal titled "Career & Job Search Insight". Note that this one saves
  under `quizGroup: "careerJobSearch"` where the signed-in branch of the same
  component saves under `"careerQuizzes"` — `G16`. Check which heading
  `/quiz-insights` shows afterwards.
- **S4.10** — Open `/quiz-preview/not-a-real-quiz`.
  → "Career Quiz" / "That quiz could not be found. Please return to assessments to
  choose a quiz." / "Back to Assessments" — which points at `/intelligence` and
  bounces a signed-out visitor to `/login`. `G19`.

---

### S5 · Register → verify → sign in

**Account** ACC-1 (and ACC-5, which stops at S5.6)

- **S5.1** — Open `/register`.
  → Eyebrow "Get started"; H1 "Create your account". Fields: Full name, Email
  address, Password ("Min. 12 characters"), Confirm password, and a checkbox "I am 16
  or older and agree to the Terms of Service and Privacy Policy."
- **S5.2** — Walk the password validators. They fire one at a time, in this order:
  → "Passwords do not match" → "Password must be at least 12 characters" → "Password
  must contain an uppercase letter" → "Password must contain a lowercase letter" →
  "Password must contain a number" → "Password must contain a symbol" → "Please
  confirm you are 16 or older and accept the Terms of Service and Privacy Policy"
- **S5.3** — Register with an address that already exists.
  → "An account with that email already exists"
- **S5.4** — Register cleanly.
  → 201, and you are sent to `/verify-email`. **There is no success screen on the
  register page itself.**
- **S5.5** — On `/verify-email`: H1 "Check your inbox"; body "We sent a 6-digit code
  to **{your email}**. Enter it below to activate your account."
  → Enter a **wrong** code. → The banner reads **`invalid code`** — lowercase,
  unpunctuated, straight from the backend. `G8`.
  → Wait 15+ minutes and enter the real code. → **`code expired`**. Same gap.
- **S5.6** — Click "Resend code".
  → "Sending…" → "Sent!" and the button is **permanently disabled** — there is no
  timer, just `disabled={isPending || isSuccess}`. Success text: "New code sent!
  Check your inbox." Server-side the limit is 5/min.
  → **Stop here for ACC-5.** Leave it unverified.
- **S5.7** — Enter the correct code.
  → The form is replaced by "Email verified! Redirecting to sign in…" (or, coming
  from the intake path, "Email verified! Signing you in to unlock your results…"),
  then after **2 seconds** it navigates to `/login`.
- **S5.8** — Sign in as ACC-5 (unverified).
  → Banner: "Your email is not confirmed. Please check your inbox." **and** a
  "Resend verification code" link-button appears beneath it. This is the only
  unconfirmed-email gate in the entire API — no `/me/*` route checks the flag.
- **S5.9** — Sign in as ACC-1 with the **wrong password**.
  → "Failed to sign in. Please check your credentials." Note: this one message
  swallows every non-unconfirmed failure, including the 401 "Invalid credentials",
  the 423 lockout, and network errors.
- **S5.10** — Sign in correctly. → `/job-seeker/dashboard`.
- **S5.11** — Open `/confirm-email` and `/check-email`.
  → Both render nothing and redirect to `/verify-email`. Legacy aliases.

---

### S6 · Auth recovery and failure modes

**Account** ACC-1, ACC-5

- **S6.1** — `/forgot-password`.
  → H1 **"Sign in with a code"**; "Enter your email and we'll send a one-time code
  you can use to sign in." Note this is **passwordless sign-in, not a password
  reset** — there is no new-password form anywhere in the app.
- **S6.2** — Submit an address that does not exist.
  → Still succeeds and moves you to `/forgot-password/verify`. The endpoint always
  answers 200 regardless, to avoid confirming which addresses exist. No email sends.
- **S6.3** — Submit ACC-5 (registered but unconfirmed).
  → Also 200, also no email — the send requires `email_confirmed`. Confirm that a
  user in this state has no recovery path except the resend on `/login`.
- **S6.4** — Submit ACC-1 and enter a wrong code.
  → "Invalid or expired code. Please try again." (Correctly normalised here, unlike
  `G8`.) The backend returns the same `invalid_or_expired_code` for wrong, expired,
  and no-pending-reset alike.
- **S6.5** — Enter the correct code. → Signed straight in, to `/job-seeker/dashboard`.
- **S6.6** — Submit `/forgot-password` four times inside a minute.
  → The limit is `3 per minute`; the fourth gets a 429 whose body is problem+json,
  surfacing as the server's detail or "Too many attempts. Please wait a moment and
  try again."
- **S6.7** — Fail the password on `/login` five times.
  → The sixth attempt is locked for 15 minutes. The backend says "Account locked. Try
  again later." but the UI shows "Failed to sign in. Please check your credentials."
  — i.e. **a locked-out user is told their password is wrong**. Worth a ruling.
- **S6.8** — Sign in, then delete the `access_token_cookie` in devtools, then click
  around.
  → The context refreshes once, silently, and replays the request. You should notice
  nothing.
- **S6.9** — Sign in, then delete **both** auth cookies, then navigate to
  `/situation-report`.
  → The refresh fails, the session clears locally (including the whole query cache),
  and the next protected render bounces you to `/login`. **There is no toast and no
  message** — you just arrive at the sign-in page.
- **S6.10** — From that `/login`, sign back in.
  → You should be returned to `/situation-report`, not the dashboard. `RequireAuth`
  plants the attempted URL in router state and `Login` validates and honours it.
- **S6.11** — Sign out via the header icon (its only label is `title="Logout"` — no
  `aria-label`). → `POST /auth/logout`, cache cleared, land on `/`. Note this
  endpoint always returns 200, even with no session.
- **S6.12** — While signed out, open `/pulse` directly.
  → Grey skeleton (no text) during the session probe, then `/login`. After signing in
  you land back on `/pulse`. This is the email deep-link path — S23 depends on it.

---

### S7 · The brand-new dashboard

**Account** ACC-1, immediately after S5.10 · **Route** `/job-seeker/dashboard`

- **S7.1** — Land on the dashboard for the first time.
  → The **`IntakePromptModal` auto-opens** if profile completion is under 50%, which
  it will be. Eyebrow "Profile Autofill"; title "Boost your profile instantly" (or
  "Your profile needs attention" if you came via intake).
- **S7.2** — Dismiss it with "Maybe later".
  → Header block: eyebrow "Dashboard"; H1 "Welcome back, {your name}"; "Here's where
  your working life stands, and the one thing worth doing next."
- **S7.3** — Check the Work Pulse banner.
  → "Complete your Work Pulse" / "24 quick either-or questions about how you actually
  work — takes about 8 minutes." / button "Start now" / a dismiss "X".
- **S7.4** — Dismiss it with the X, then reload.
  → It comes back. The dismissal is local state only, by design.
- **S7.5** — Look for the Situation Report card.
  → It renders **nothing at all** while `/me/situation-report` is in flight, then the
  `needs_core` state: H2 "Your conditions, once we have your side" / "Your Situation
  Report is the distance between how you work and what your job actually asks of you.
  Work Pulse is the first of those two, and it isn't finished yet."
  → Its "Next" action is **suppressed**, because the Work Pulse banner above is
  already offering the same thing.
- **S7.6** — Check the Pulse card.
  → Eyebrow "Pulse"; H2 "Keep a pulse on work"; "A short weekly check-in — three
  questions, about a minute. It gets more useful the more you do it."; "Take your
  first check-in →".
- **S7.7** — Check the two empty sections.
  → "Recent Activity" → "Nothing here yet." + "Your activity shows up here as you
  complete Work Pulse and fill in your profile."
  → "Recommendations" → "No recommendations yet." + "Once you finish Work Pulse we'll
  suggest what to do next."
- **S7.8** — Check Quick Actions.
  → Exactly two tiles: "Edit Profile" / "Update your information" → `/job-seeker/profile`;
  "Your Solverah profile" / "Work Pulse, FocusType and ManagerMatch" → `/intelligence`.
  Below the fold: "Search companies and roles →".
- **S7.9** — **Resize to phone width (~390px).**
  → The header nav does not collapse; five items plus your name overflow. `G2`.
- **S7.10** — Click "Feed" in the header.
  → A modal, not a navigation: "Feature coming soon" / "The feed will be available
  soon. Check back after launch." / "Got it". `G3`.
- **S7.11** — Note what is **not** in the header: Work Pulse, Situation Report, Pulse,
  Manager Decoder. All four are reachable only from the dashboard, `/intelligence`, or
  a typed URL. Judge whether that is survivable at launch.

---

### S8 · Work Pulse — the core sitting

**Account** ACC-1 · **Route** `/work-pulse` · **24 forced-choice items, ~8 minutes**

Draft storage: `sessionStorage["solverah_assessment_answers"]`.

- **S8.1** — Open `/assessment`. → Redirects to `/work-pulse`.
- **S8.2** — On `/work-pulse`, read the intro.
  → H1 "Work Pulse"; "24 either-or questions about the conditions you do your best
  work in — about eight minutes."; "There are no right answers, and nothing here is
  scored as better or worse. The profile is only useful if it describes you rather
  than the version of you that sounds most employable."; "Employers never see your
  answers or your dimension scores." + link "How this works, and what we hold back →".
  → While the form loads, the word **"Loading…"** appears under the header. No
  spinner, no skeleton.
- **S8.3** — Answer three questions.
  → "Question 3 of 24" + progress bar; the selected option shows a ✓; "← Back" is
  hidden on question 1 and present after.
- **S8.4** — **Reload the page.**
  → You are returned to **"Question 1 of 24"**, with your three answers pre-selected.
  Position is not persisted; answers are. Expected (§0.5), not a bug.
- **S8.5** — **Close the tab and reopen it.**
  → Everything is gone. `sessionStorage` dies with the session.
- **S8.6** — Answer all 24 honestly and click "Finish".
  → Button reads "Saving…". On success, the page **swaps in place** to the completion
  state — no navigation, no results page.
- **S8.7** — Read the completion card.
  → "✦ Work Pulse Complete" / H1 "That's everything we need" / "Your Work Pulse now
  powers your matching. There's no score to check and nothing to optimize — it works
  quietly in the background as we line up the environments where you'd do your best
  work." / "24 questions about you. Now 15 about your job." / "Work Pulse is half of
  your Situation Report. The other half is your own description of the role you're in
  — what it actually offers, not what it was advertised as — and the report is the
  distance between the two."
  → Primary CTA **"Describe your job →"** → `/environment-report`. Secondaries: "Start
  FocusType →", "Start ManagerMatch →", "Back to dashboard".
- **S8.8** — Navigate back to `/work-pulse`.
  → The form never mounts again; you get the completion card.
- **S8.9** — Open `/work-pulse/results`.
  → **Silently redirects** to `/work-pulse` unless you completed the retired
  12-question instrument. No copy, no explanation. Judge whether that's acceptable
  for anyone who bookmarked it.
- **S8.10** — (If you can induce a failed form fetch — e.g. block the request in
  devtools.) → Red `role="alert"` text with the raw error message, and **no retry
  button**. `G7`.

---

### S9 · The Environment Report

**Account** ACC-1 · **Route** `/environment-report` · **15 questions, ~5 minutes**

Draft storage: `sessionStorage["env_report_answers"]`.

- **S9.1** — From the Work Pulse completion card, click "Describe your job →".
- **S9.2** — Read the intro.
  → Eyebrow "Situation Report"; H1 "Now the other half — your job"; "Work Pulse asked
  how you work. These ask what your role actually offers — how much of the how is
  yours, what the tempo is, how decisions get made. Twelve questions about the work,
  plus three about the setup. About five minutes."; "Describe the job as it actually
  is, not as it was advertised or as it ought to be…"; "This is a private working
  note. Nobody at your employer is told you filled it in, and nobody there can see
  it."
- **S9.3** — Start. Note the order — it is load-bearing and must not change:
  `stage_size` first, then `comp`, then the **12 dimension items** (two each for
  autonomy, pace, collaboration, feedback, innovation, decision-making), then
  `experienced` **last**. The last-place position of `experienced` is an anti-halo
  measure.
- **S9.4** — Question 1.
  → "How big is the organization you work for — the whole organization, not your
  team?" Options run from "An early-stage startup — a handful of people, still
  finding its footing." to "A very large enterprise — tens of thousands of people and
  many layers."
- **S9.5** — Question 2 (comp).
  → "Compared with what you could earn elsewhere doing similar work, how does this
  role pay?" — five options **plus a deliberate sixth**: "Not sure how this
  compares." Choosing it counts as answered.
- **S9.6** — Question 3.
  → "How much say do you have over how your work gets done?"
- **S9.7** — Reload mid-way. → Back to the intro, then "Question 1 of 15" with your
  answers pre-selected. Same pattern as S8.4.
- **S9.8** — Question 15.
  → "Overall, how well is this role working for you?" — "It isn't working at all." /
  "It isn't working well." / "A mixed picture." / "It's working well." / "It's working
  very well."
- **S9.9** — Finish.
  → Full-screen spinner + **"Building your Situation Report…"**, then navigation to
  `/situation-report`.
- **S9.10** — (If you can force a submit failure.) → Inline, above the nav row: "We
  couldn't save that just now. Your answers are still here — try again."
- **S9.11** — (Gap check.) If `GET /me/situation-report` fails when this page loads,
  the page **renders the intro anyway** and un-gates the form. `G6`.

---

### S10 · The Situation Report, complete

**Account** ACC-1 · **Route** `/situation-report`

The hard rule this page enforces: **no numbers, ever.** Magnitude is one of three
words; direction is one of two phrases; ranking is document order. A digit in a
strain card is a bug.

- **S10.1** — Land on `/situation-report` from S9.9.
  → While loading: spinner + "Loading your Situation Report…".
- **S10.2** — Read the header.
  → Eyebrow "Situation Report"; H1 **"You, and this job"**; "Ranked by how far apart
  you and the role sit. What is under most strain comes first."
- **S10.3** — "At a glance".
  → Chips reading `{Dimension} — {Bucket}`, where dimension is one of Autonomy, Pace,
  Collaboration, Feedback, Innovation, Decision-making and bucket is one of
  **"Straining" / "Notable" / "Aligned"**.
- **S10.4** — Check the experienced-trend section.
  → With zero check-ins: "You haven't checked in on Pulse yet." + "Check in →".
  (After S13 it becomes "How work's been working for you" with a sparkline.)
- **S10.5** — Read a strain card.
  → Dimension + bucket chip + a direction chip reading **"Less than you need"** or
  **"More than you need"**, then a headline and body.
- **S10.6** — Check the register sections on that card. Depending on the dimension
  you should see one of:
  → **"Change it in place"** — an experiment name, the experiment, steps, then "How
  you'll know it worked" + a signal.
  → **"Negotiate it"** — "Who, and where" / "How to open" / "What to say" (scripts in
  curly quotes) / "If the answer is no".
  → **"This one rarely moves"** — "Why it's usually fixed" / "What staying costs" /
  "What that means".
- **S10.7** — Look for a feedback-dimension card.
  → It should **defer to the Manager Decoder**: "How feedback actually reaches you is
  enacted by one person rather than by the company, so the protocol for it lives in
  the Manager Decoder rather than here." + a CTA.
- **S10.8** — Read the manager section.
  → H2 "The half one person enacts". With no manager profile yet: "Some of what this
  report calls the environment is really one person, and from the inside the two look
  identical. The Manager Decoder separates them: profile the manager you actually
  have, and it returns the protocol for that half."
- **S10.9** — Read the honest footer.
  → H2 "What this is, and what it isn't", four paragraphs, including "It is not a
  score, and there is deliberately not a single number in it…", "It is not advice to
  leave, and not advice to stay…", and "It is pinned. The report reads your Work
  Pulse from one named sitting and stays there…"
- **S10.10** — Click **"Print this report"**. → Browser print dialog. Check the print
  layout is not broken — this is a document people will actually print.
- **S10.11** — If every dimension came back aligned:
  → "Nothing is straining. On every dimension we measure, you and this job are set
  much the same way — which is uncommon enough to be worth noticing rather than
  assuming."
- **S10.12** — (After S13.4.) Log a Pulse event, then return here.
  → A resubmission banner should appear, worded off the newest event: e.g. "You
  logged a new manager since this report — does your Situation Report still describe
  this job?" + "Describe it again →".

---

### S11 · Recalibrating the pin

**Account** ACC-1 · **Route** `/situation-report`, footer

- **S11.1** — Find the pin control at the very bottom.
  → Button: **"Re-read this against my latest Work Pulse"**.
- **S11.2** — Click it without having retaken Work Pulse.
  → "Re-reading…", then **"Already reading your most recent Work Pulse sitting —
  nothing moved."** This is a **success**, not an error (§0.5). Nothing is written and
  nothing is logged.
- **S11.3** — (If you can retake the core sitting on a second account.) Retake, then
  recalibrate.
  → "Re-pinned. This report now reads your most recent Work Pulse sitting."
- **S11.4** — (Not reachable from ACC-1 once S8 is done, but the code path exists.)
  With no core sitting at all, the endpoint answers 409 `no_core_sitting` and the
  footer reads: "There is no Work Pulse sitting to pin to yet."
- **S11.5** — Any other failure → "We couldn't re-read it just now. Please try again
  in a moment."

---

### S12 · Condition experiments

**Account** ACC-1 · **Route** `/situation-report` — **there is no `/experiments` page.**
The entire feature lives inside the complete Situation Report.

- **S12.1** — Find a strain card whose "Change it in place" register carries an
  experiment name. → A button: **"Try this for two weeks →"**.
- **S12.2** — Start it.
  → The cell switches to "Running since {date}, through {date}." plus an **"Abandon"**
  button.
- **S12.3** — Scroll to "Your experiments" below the guidance notice.
  → A row: "{Dimension} — {experiment name}", phase label **"Running"**, and the date
  range.
- **S12.4** — Try to start a **second** experiment on another card.
  → The button is **disabled client-side**, with the hint: "Only one experiment can
  run at a time — finish or abandon the other one first." The server's 409
  `experiment_already_active` is caught and deliberately shows no error message.
- **S12.5** — Click "Abandon".
  → **No confirmation dialog and no success message.** The row simply disappears from
  the cell. Decide whether an unconfirmed destructive-ish action is acceptable here.
- **S12.6** — Check "Your experiments" again.
  → The abandoned one shows with phase label **"Abandoned"**. Abandoning is idempotent
  server-side — a repeat is a 200, not an error.
- **S12.7** — **Before you have ever started one**, look for the experiments section.
  → **There is nothing at all** — no heading, no invitation, no empty state. A user who
  never starts one never learns the feature exists except through a strain card.
- **S12.8** — (Gap.) A failed `GET /me/experiments` is indistinguishable from having
  none, and every start button still renders as available. `G5`.
- **S12.9** — (After two weeks, or on seeded data.) An ended experiment reads out in
  verdict words only: "Your numbers moved up over those two weeks." / "…moved down…" /
  "Your numbers didn't move much over those two weeks." / "There weren't enough
  check-ins on one side of this to say anything yet." — plus "That's based on {n}
  check-ins before, {m} after." Never a delta.

---

### S13 · The Pulse

**Account** ACC-1 · **Routes** `/pulse`, `/pulse/trend` · **No preconditions**

- **S13.1** — Open `/pulse`.
  → Eyebrow "Pulse check-in"; H1 **"Three questions about this week"**; "About a
  minute. Pick the number closest to true for you."
  → Four rows on one screen: three server-chosen dimension items plus `experienced`
  **last**. Each is a stem, five circular 1–5 radios, and a low/high anchor.
- **S13.2** — Answer three of four.
  → "Done" stays disabled until all four are answered.
- **S13.3** — **Reload before submitting.** → Everything is lost. The Pulse check-in
  is the one instrument with **no draft persistence** at all.
- **S13.4** — Submit your first check-in.
  → The form is replaced in place: H1 **"That's your first pulse"** / "Nothing to
  compare it to yet. Check in again next week and you'll start seeing how it moves."
  Eyebrow "Logged". Exits: "See your trend →" and "Done".
- **S13.5** — Check in a second time.
  → H1 **"Two points make a trend"** + a two-point sparkline + "How work's working for
  you is {up|down|about the same} from last time."
- **S13.6** — Check in a third time. → H1 **"This week vs. last week"**.
- **S13.7** — Open `/pulse/trend`.
  → H1 "Your pulse"; "{n} check-ins logged."; "How work's been working for you" with
  the line; then "By dimension" with five cards labelled **Focus / Workload /
  Surroundings / Recognition / Pace**. Sparse coverage is by design — only three of
  five dimensions are asked per check-in, so expect "Not answered yet." on some.
- **S13.8** — Click "+ Log a change".
  → Type chips: "New manager" / "Reorg" / "Remote / office change" / "Role change" /
  "Something else"; a note textarea with a "{n}/280" counter; "Save" / "Cancel".
- **S13.9** — Log a "New manager" event with a note.
  → It appears under "Changes you've logged" with date, label and the quoted note,
  and it annotates the experienced line. **Then go back to S10.12** — the Situation
  Report should now show the resubmission banner.
- **S13.10** — Type 281 characters in the note. → Rejected at 280.
- **S13.11** — Find "Check-in cadence".
  → Exactly three options: **"Weekly"**, **"Every two weeks"**, **"Off"**.
- **S13.12** — Set it to "Off", then back to "Weekly".
  → Each is a single PATCH with **no confirmation step** (a product decision). Error
  copy if it fails: "We couldn't save that just now. Try again."
- **S13.13** — (Cannot be triggered by hand; verify by reading or by seeding.) After
  **three consecutive unanswered prompts**, the **fourth** prompt drops you to
  monthly and carries one extra paragraph — in the email: "We've slowed these
  check-ins down to once a month since it's been quiet -- no rush, and you can check
  in any time." and on `/pulse/trend`: "We've slowed these down to once a month since
  it's been quiet — no rush, and you can check in any time."
  → In that state **none of the three cadence buttons appears selected**, because
  `monthly` is not one of them. **Checking in does not leave monthly** — only
  explicitly picking Weekly / Every two weeks / Off does. `G21`.
- **S13.14** — Empty state check (use a fresh account): `/pulse/trend` with zero
  check-ins → "Nothing to show yet. Your trend builds from check-ins — it takes about
  a minute." + "Check in now →".

---

### S14 · The Manager Decoder

**Account** ACC-1 · **Routes** `/manager-match`, `/manager-profile`, `/manager-profile/playbook`

**The precondition chain is ManagerMatch (15) → Manager Profile (16) → Playbook**, and
the most important thing to test here is that **`/manager-profile` enforces nothing**.

- **S14.1** — **Before taking ManagerMatch**, go straight to `/manager-profile` and
  answer all 16 questions.
  → It lets you. The submit returns a null playbook, the page navigates to
  `/manager-profile/playbook` anyway, and only *there* do you meet the gate: H1
  **"Take ManagerMatch first"** / "Your playbook diffs what you need from a manager
  against how your manager actually works. Take ManagerMatch so there's something to
  compare your manager profile against." / "Take ManagerMatch →".
  → This is intentional (one bridge-rendering path instead of two copies of the same
  copy) **but it means the user does 16 questions of work before being told.** This is
  the single most likely thing in this document to want changing. Judge it.
- **S14.2** — Take ManagerMatch.
  → Eyebrow "WorkPulse Pro"; H1 "ManagerMatch™"; "Discover which management styles
  bring out your best — and which create friction."; amber warning "Each choice is
  final — there is no going back."; button "Start ManagerMatch™".
  → 15 forced choices, prompt line "Which feels more like you?".
- **S14.3** — Finish it.
  → Spinner: "Analysing your management preferences…" / "This usually takes under a
  minute. You can leave this page open." This one is scored by a background job, not
  on the request.
  → On failure: "We couldn't generate your results right now." + "Try again".
- **S14.4** — Read the results.
  → Archetype, narrative, "How you scored" with four dimensions (Autonomy, Feedback
  Style, Relationship, Growth Focus) banded Low/Mid/High, "What to look for", "Watch
  out for", then the bridge: "ManagerMatch tells you what you need. The Manager
  Decoder tells you where your actual manager stands against it." + "Now profile your
  actual manager →".
- **S14.5** — Return to `/manager-profile/playbook` now.
  → Second gate: H1 **"Profile your manager"** / "You've completed ManagerMatch. Now
  tell us how your actual manager works, so we can build your playbook." (Note neither
  gate uses the words "unlock" or "locked" — deliberate.)
- **S14.6** — Take Manager Profile properly.
  → Eyebrow "Manager Decoder"; H1 "Profile your actual manager"; "16 questions about
  how your manager actually operates — not how you feel about it."; amber "Each choice
  is final — there is no going back."
  → 16 questions, prompt "Which is closer to how your manager works?", **no back
  button anywhere**.
- **S14.7** — Answer 8, then reload.
  → Unlike Work Pulse, this one **resumes at question 9**. Confirm the inconsistency
  with S8.4 is what you see.
- **S14.8** — Finish. → Spinner "Scoring your manager profile…" then the playbook.
- **S14.9** — Read the playbook.
  → H1 "Your managing-up playbook"; a privacy notice; "Where to focus first" as
  ordered chips; "The full map" with grind cards ("Notable"/"Acute", "More than you
  need"/"Less than you need", "Why", "The ask", "Bring to your 1:1", "What to say")
  and mesh cards.
  → If nothing grinds: "No grinds — your manager profile meshes with what you need
  across all four dimensions."
- **S14.10** — Click "Print this playbook". → Check the print layout.
- **S14.11** — Go back to `/situation-report` (S10.8).
  → The manager section should now read the *has-profile* variant: "Some of what this
  report calls the environment is really your manager. You have already profiled them,
  so that half has its own playbook — read the two together where they touch the same
  dimension." And CTAs across the report should now say "Open your playbook →" rather
  than "Profile your manager →".

---

### S15 · FocusType

**Account** ACC-1 · **Routes** `/focus-type`, `/focus-type/results` · **No preconditions**

- **S15.1** — Open `/focus-type`.
  → Eyebrow "FocusType™"; H1 "Discover how you actually focus."; two paragraphs; amber
  box "Each choice is final. There's no going back." + "Each scene commits when you
  complete it — treat every decision as real."; "⏱ Takes about 4 minutes"; button
  "Begin".
- **S15.2** — Walk all five scenes.
  → "Scene {n} of 5" with a segmented indicator. These are interactive scenes, not
  questions — drag/sort/slider interactions. **Check each scene actually works on
  your device**; these are the most interaction-heavy screens in the product.
- **S15.3** — Finish scene 5.
  → Spinner + "Calculating your FocusType…", then `/focus-type/results`.
- **S15.4** — Read the result.
  → Eyebrow "FocusType™"; "Your FocusType"; the archetype name as an H1, one of: Deep
  Diver / Sprint & Reset / Reactive Flow / Structured Builder / Pressure Igniter /
  Collaborative Charger; a one-line description; "Your workplace recommendations";
  "What drove your result" with six dimension bars (Deep Focus, Burst Energy,
  Reactivity, Structure Need, Urgency Drive, Social Fuel).
  → **Note the tension worth watching:** FocusType shows a visible result and score
  bars, where Work Pulse deliberately withholds them. `/trust` addresses this in an
  aside titled "Then why does FocusType show me a result?" — check that aside actually
  reconciles it.
- **S15.5** — Revisit `/focus-type`.
  → You are redirected to the results, not the intro.
- **S15.6** — On submit failure: "Something went wrong submitting your results." /
  "Please try again — your scene answers are still saved." / "Try again".

---

### S16 · The Intelligence hub and its satellites

**Account** ACC-1 · **Routes** `/intelligence`, `/solverah-profile`, `/intelligence/paths`,
`/quiz-insights`, `/career-quizzes/*`, `/trust`

- **S16.1** — (Use a fresh account, or recall S7.) Open `/intelligence` **before**
  Work Pulse.
  → A hard gate, and nothing else on the page renders: "Complete Work Pulse to unlock
  your profile." / "Work Pulse takes about 8 minutes and unlocks your Solverah profile
  — the foundation everything else in the ecosystem builds on." / "Start Work Pulse".
- **S16.2** — Open it as ACC-1 (post-Work Pulse).
  → Eyebrow "Your Intelligence Hub"; H1 "Everything we know about how you work."; a
  step strip (Work Pulse Lite, Work Pulse, FocusType, ManagerMatch, CompanyLens,
  Future Path).
- **S16.3** — Read the Work Pulse card.
  → "✦ Unlocked · Work Pulse™" / "Work Pulse complete" / "It's powering your matching
  in the background. There's no score to check and nothing to optimise — what it
  learned about how you work is already shaping which environments we put in front of
  you."
- **S16.4** — Read the Situation Report card. → Should reflect your actual state
  (complete → "View your Situation Report →").
- **S16.5** — Read the Manager Decoder card. → Post-S14: "✦ Unlocked · Manager
  Decoder" with "{n} dimensions to work on" or "All four dimensions mesh", plus "View
  your playbook →" and "Retake".
- **S16.6** — Read the CompanyLens card.
  → Disabled for everyone: "Our matching model is still being built. Your Work Pulse
  results are already saved and will feed it the moment it's ready." + a disabled
  "Coming soon" button. `G4` — expected.
- **S16.7** — Check the footer. → "No scores here, and that is deliberate." + "How
  this works, and what we hold back →".
- **S16.8** — Open `/solverah-profile`. → Identical page. Confirm nothing differs.
- **S16.9** — Open `/intelligence/paths`.
  → Header carries a **"Pro" pill**, but **there is no entitlement check anywhere** —
  the pill is decorative. Decide whether shipping a "Pro" badge on a free feature is
  what you want at launch.
  → Loading: three pulsing skeleton cards.
- **S16.10** — If your career status is unset, you get: "Set your career status to get
  started." / "Tell us where you are in your career so we can tailor your path
  suggestions." / "Update Profile" → which deep-links to
  `/job-seeker/profile?tab=experience` with the career-status modal open. Follow it
  into S19.4.
  → Note this component is marked in-source as a **placeholder** ("will be replaced by
  the full component in SOL-31").
- **S16.11** — If your profile lacks a job title or skills: "Add a job title and a few
  skills to get started." / "Path Intelligence needs your current (or most recent) job
  title and at least one skill to find matching career paths." / "Complete Your
  Profile".
- **S16.12** — Complete it and get suggestions. → A suggestion list plus "Edit skill
  ratings" / "Adjust search preferences". Look for "Coming soon — goal tracking is on
  the way" on the suggestion cards.
- **S16.13** — Open `/trust`.
  → H1 "How this works, and what we hold back". Sections: "The questions are forced
  choices, and both answers are real"; "There is no score to see, and that is the
  point" (+ the FocusType aside from S15.4); "What matching will mean, and what it will
  not"; "How we check our own instruments"; "Your answers". Closing: "Nothing on this
  page describes something that does not exist yet. Where a thing is still being
  built, it says so — and when that changes, this page changes with it."
  → **Check that claim against `G1`.** This page says "You can delete your account and
  the data behind it." There is no screen for that.
  → Footer says "Last reviewed 10 September 2026" — decide whether that needs bumping
  before launch.
- **S16.14** — Open `/career-quizzes` signed in.
  → No loading state at all — questions render unanswered while the profile loads,
  then re-render with your saved answers. A **failed** profile read is indistinguishable
  from "never taken".
  → Submit failures surface as **browser `alert()` dialogs**: "Unable to save responses
  (not authenticated)." and "Failed to save responses. Check console for details." An
  `alert()` in a shipped product is worth a note.
- **S16.15** — Open `/quiz-insights`.
  → Loading "Loading insights…"; empty "No insights found yet. Complete a quiz and
  generate insights to view them here."; populated shows heading per `?group=`.

---

### S17 · The matching surfaces

**Account** ACC-1 · **Routes** `/search`, `/feed`, `/company-lens`, `/companies/:id`

All four are wholly or partly coming-soon. The point of this scenario is to confirm
each one **says so honestly** rather than looking broken.

- **S17.1** — Click "Search companies and roles →" on the dashboard.
  → `/search` with no query: "Search for companies and roles" / "Type a company name,
  job title, or keyword to get started." / "← Back to Feed".
- **S17.2** — Search for something.
  → Loading is a spinning icon with **no text**. Results show "Search results for
  '{query}'", "Showing X–Y of N results", "Match score: N%" and pagination.
- **S17.3** — Search for gibberish.
  → "No results found for '{query}'" / "Try adjusting your search terms."
- **S17.4** — (Gap.) A **failed** fetch renders the same empty state. There is no
  error branch, so a server failure reads as a successful empty search. `G15`.
  → Also note `/search` is dark-slate themed, unlike the rest of the app. Decide if
  that ships.
- **S17.5** — Navigate to `/feed` **by typing the URL** (the header won't take you —
  `G3`).
  → "Welcome to your feed, {firstName}!"; a search box that does work; a "Filters"
  button **with no handler**; "Job recommendations coming soon" / "Complete your
  profile and generate recommendations to start seeing personalized jobs."; stats
  hard-coded to "--"; "Company trends coming soon"; a "Start a Conversation" button
  **with no handler**.
  → This page has neither a loading nor an error state. Decide whether it should be
  reachable at all at launch.
- **S17.6** — Open `/company-lens`.
  → Loading: "Scoring companies against your Work Pulse results…"
  → Then, for every current user: **"CompanyLens™ is coming soon"** / "We're still
  building the matching model behind it. Your Work Pulse results are already saved and
  will feed it the moment it's ready — there's nothing you need to do." / "Back to
  Intelligence". `G4` — expected and correct.
- **S17.7** — Open `/companies/{a real id}`.
  → This one is a **real feature**. Loading "Loading company profile…"; then name,
  "industry · size · headquarters", and sections that render only when populated.
  Error or missing: "Couldn't load this company profile." / "Try again".
  → Reaching it organically requires CompanyLens, which is off — so confirm whether
  any path to it exists for a real user today.

---

### S18 · The agent

**Account** ACC-1 · **Route** `/agent`

- **S18.1** — Open `/agent`.
  → Title "Solverah AI" / "Your personal career assistant"; a permanent disclosure:
  "You're chatting with an AI. It uses your profile and resume to personalize answers,
  and it can make mistakes — verify anything important."
  → Empty state: a faded icon + "Ask me anything about your career, job search, or
  skill development."
- **S18.2** — Send a message with Enter. Try Shift+Enter for a newline.
  → Placeholder reads "Message Solverah AI… (Enter to send, Shift+Enter for new line)".
- **S18.3** — Watch the response arrive.
  → It **streams** (SSE), with a deliberate 40ms delay per chunk. Three bouncing dots
  appear while waiting for the first chunk.
- **S18.4** — Try to type while a response is streaming.
  → The textarea **is disabled** while pending. Confirm that is what you want — it
  prevents queueing a follow-up.
- **S18.5** — Ask it something product-specific: "What is the Situation Report?" /
  "What does Work Pulse measure?" / "How do I profile my manager?"
  → D-1 taught the agent its own product. **Judge the answers.** A wrong answer here
  is a content bug, not a code bug, and belongs in its own note.
- **S18.6** — Ask it something it should refuse or hedge on — salary advice, legal
  advice, a guarantee about a job.
- **S18.7** — Send 31 messages in a minute.
  → Limit is 30/min. Expect a red banner with the parsed error, falling back to "Too
  many attempts. Please wait a moment and try again." There is **no bespoke rate-limit
  copy**.
- **S18.8** — Click "Clear chat" mid-stream. → The stream aborts cleanly and no error
  banner appears.
- **S18.9** — (Config check.) If the banner reads "Failed to generate response", that
  is a missing or invalid **`GROQ_API_KEY`** — the agent runs on Groq, not OpenAI.
  §0.6, not a UI bug.

---

### S19 · Profile and career status

**Account** ACC-1 · **Route** `/job-seeker/profile`

- **S19.1** — Open the profile.
  → H1 "Job Seeker Profile"; sub "Complete your profile to get better job matches and
  increase visibility to recruiters." — note "recruiters", when no recruiter role
  exists and the product has been reframed away from company pairing. Worth a copy
  ruling.
- **S19.2** — Click each of the four tabs.
  → `personal` "Personal Info" / `experience` "Experience" / `education` "Education" /
  `performance` "Performance". Each click rewrites `?tab=`.
- **S19.3** — Open `?tab=bogus` directly. → No tab selected, empty body under the tab
  strip. `G12`.
- **S19.4** — Edit a field without saving.
  → Amber strip: "You have unsaved changes — don't forget to click **Save Profile**."
- **S19.5** — Try to navigate away with unsaved changes. → A native `beforeunload`
  dialog.
- **S19.6** — Save. → Button "Saving...", a progress bar labelled "Saving profile".
- **S19.7** — Arrive here from S16.10 (the Path Intelligence deep link).
  → The career-status modal opens: "Where are you in your career?" / "We need this to
  generate your path suggestions." / "If you're currently employed, check **I
  currently work here** on your most recent role below and save your profile." / "Or
  select your status now:" with two options — "Currently unemployed" ("You're between
  roles and actively looking") and "Looking for my first job" ("You're early in your
  career and seeking an entry-level role").
- **S19.8** — Pick one. → `PATCH /me/career-status`, then you are sent to
  `/intelligence/paths`.
- **S19.9** — (Gap.) If that PATCH fails, the buttons simply re-enable with **no error
  copy at all**. `G13`.
- **S19.10** — Note that **"employed" is not an option in this modal** — it is set by
  checking "I currently work here" on a role in the Experience tab. Confirm that path
  works, because it is the one that puts ACC-1 in present tense.

---

### S20 · Export and deletion — the known hole

**Account** ACC-1 · **This scenario is expected to fail. Walk it anyway.**

- **S20.1** — Signed in, look for an account-settings screen. Check the header, the
  profile page, every tab, and the footer.
  → **There isn't one.** There is no `/settings` route and no `/account` route in the
  entire route table.
- **S20.2** — Look for a data-export control anywhere in the UI.
  → Nothing calls `GET /api/v1/me/export`. `G1`.
- **S20.3** — Look for an account-deletion control anywhere in the UI.
  → Nothing calls `DELETE /api/v1/me`. `G1`.
- **S20.4** — Re-read the Privacy Policy clause from S1.8 and the Trust page line from
  S16.13 with that in mind.
  → Three shipped documents promise a screen that does not exist. **This is the single
  most launch-relevant finding in this document**: it is a compliance statement the
  product does not honour, not a missing nice-to-have.
- **S20.5** — (Optional, to confirm the backend half is sound.) Call the endpoints
  directly with your session cookie and CSRF header.
  → `GET /api/v1/me/export` returns `application/json` — **not a file download**, no
  `Content-Disposition`, no filename. Even once a button exists, it will need
  client-side download handling.
  → `DELETE /api/v1/me` with `{"confirm": "DELETE"}` returns "Account deleted.
  Assessment responses are retained in de-identified form." It tombstones the user
  row, hard-deletes personal content and every session, clears your cookies, and frees
  the email address. A subsequent login with the old address gives "Invalid
  credentials", indistinguishable from a never-registered address.

---

### S21 · The first-job lane

**Account** ACC-3 · career status `first_job`

The product's most opinionated refusal: it declines to assemble a report rather than
invent one.

- **S21.1** — Register ACC-3, complete Work Pulse (S8), then set career status to
  "Looking for my first job" (S19.7).
- **S21.2** — Open `/situation-report`.
  → H1 **"Your report starts when the job does"** / "This report is the distance
  between how you work and what a role actually asks of you. You have given us the
  first half — Work Pulse is done, and it holds. The second half is a job to measure
  against, and you haven't started one yet." / "So there is nothing to report, and we
  would rather say that than assemble something out of a role you have never held. The
  moment you are in one, describe it in fifteen questions and the report comes back the
  same day." / "What is worth doing now is the half that needs no employer. FocusType
  maps how you concentrate, and ManagerMatch tells you which management styles bring
  out your best — which is a useful thing to know while you are choosing between offers
  rather than after."
  → Buttons: "Start FocusType →", "Start ManagerMatch →". **There must be no
  environment-report CTA anywhere on this screen.**
- **S21.3** — Navigate to `/environment-report` **directly by URL**.
  → H1 **"There's no job to describe yet"** / "These questions ask about a role you've
  held, and you've told us you're heading into your first one. So we skip the form
  rather than ask you to invent answers about a job you haven't had." / "Back to your
  Situation Report →".
  → There are **three independent gates** that land here (the report state, the live
  profile status, and a 409 `first_job_no_role` on submit). Confirm the direct-URL one
  holds — it's the one a curious user will hit.
- **S21.4** — Check the dashboard card.
  → H2 "Your report starts when the job does" / "Work Pulse is done and it holds. The
  other half is a role to measure it against, and you haven't started one yet — so
  there's nothing to report, and we'd rather say so."
  → Its "Next" action should be **"Start FocusType"** / "How you concentrate — worth
  knowing while you're choosing, not after."
- **S21.5** — Check `/intelligence`.
  → The Situation Report card is **silent** for `first_job` — it renders nothing rather
  than a gate. Confirm that is what you see, and decide whether silence or an
  explanation is right there.

---

### S22 · The past-tense lane

**Account** ACC-4 · career status `between_jobs`

Every prompt in the Environment Report has a past-tense twin, and the whole Situation
Report turns forward-facing.

- **S22.1** — Register ACC-4, complete Work Pulse, set career status to "Currently
  unemployed".
- **S22.2** — Open `/environment-report`.
  → H1 **"Now the role you left"**. The intro should read "…what your most recent role
  actually offered…" and "Describe the role as it actually was…", plus an extra line:
  "Because that role is behind you, your report comes back facing forward — what to
  look for next, rather than what to change where you are."
- **S22.3** — Walk all 15 questions and **check every prompt is past tense.** This is
  the highest-volume copy risk in the product — 15 prompts plus all their options have
  twins, and a single present-tense straggler will read as a bug to a user who just
  lost a job.
- **S22.4** — Submit and read the report.
  → H1 **"What to look for next"** (not "You, and this job"); "Ranked by how far apart
  you and the role sat. What comes first is what to look hardest at in the next one.";
  plus the honesty line: "If you and that role fitted on some dimension, it is not
  listed below — the fit was real, but this report can see that the job ended and not
  why, and a past match turned forward would be a guess wearing the report's voice."
- **S22.5** — Check the direction chips. → "Less than you needed" / "More than you
  needed" — past tense.
- **S22.6** — Check a "Change it in place" register.
  → The signal heading should read **"What to watch for next time"**, not "How you'll
  know it worked".
- **S22.7** — Look for the experiments section.
  → **It should not render at all** in the forward-facing state. You cannot run an
  experiment on a job you have left.
- **S22.8** — If nothing strained: "Nothing came back to carry forward: on every
  dimension we measure, you and that role were set much the same way. That is worth
  knowing about the kind of role to look for, even though the report will not turn it
  into an instruction."

---

### S23 · Emails and scheduled jobs

**Ops-side. Not walkable from a browser alone.**

There are exactly five emails in the product. Three reach users; two go to
`info@solverah.com`.

| Email | Subject | Trigger | Link |
|---|---|---|---|
| Verification | **"Your Solverah verification code"** | register, resend, intake account creation | **none** — code only |
| Password / sign-in code | **"Your Solverah sign-in code"** | `/auth/password/forgot`, only for confirmed accounts | **none** — code only |
| Pulse prompt | **"How's work been going?"** | `flask pulse send-prompts` cron only | **`https://solverah.com/pulse`**, button "Check in" |
| Intake notification | "New Early Access Submission" | resume intake finalised | ops only |
| Early-access notification | "New Early Access Modal Submission" | early-access modal | ops only |

- **S23.1** — Confirm both user-facing codes expire at **15 minutes** and that the
  copy says so ("This code expires in 15 minutes.").
- **S23.2** — Confirm the pulse email's only link is `/pulse` and that it **carries no
  token** — it is a plain authenticated route with no expiry. Clicking it signed out
  goes through `/login` and returns you (S6.12).
- **S23.3** — Check the three crons in the Render dashboard, not in `render.yaml`
  (that file governs nothing today):
  → `solverah-outbox-sweep` every 5 min — **load-bearing**: without it, any email that
  failed its first send never retries.
  → `solverah-retention` daily 04:30 — deletes delivered outbox rows, terminal jobs,
  dead sessions. **Never signs a live user out.**
  → `solverah-backups` daily 03:30.
- **S23.4** — **Check whether `flask pulse send-prompts` exists as a cron at all.**
  It is not in `render.yaml` and is only a manual step in the deploy runbook. Without
  it **no prompt email ever sends, silently**, and the entire Pulse cadence system —
  including the anti-nag slowdown — is inert. `G18`. This is the highest-value item in
  this scenario.
- **S23.5** — Note `retention_cleanup.py` is a standalone script, wired into neither
  `render.yaml` nor the Flask CLI. If it ever runs, an early-access submitter returning
  after 90 days gets "Submission not found" and their uploaded resume is gone.
- **S23.6** — Confirm a keyless environment fails **silently**: registration still
  returns 201 and sends the user to `/verify-email`, and they wait forever. Nothing
  surfaces. Decide whether that needs a health check before launch.

---

## 3. Coverage map

Every route in `App.tsx`, and where it is walked.

### Public

| Route | Scenario |
|---|---|
| `/` | S1, S3 |
| `/landing` | S1.10 |
| `/start` | S2 |
| `/login` | S5, S6 |
| `/register` | S5 |
| `/verify-email` | S5 |
| `/confirm-email`, `/check-email` | S5.11 |
| `/forgot-password` | S6 |
| `/forgot-password/verify` | S6 |
| `/privacy`, `/terms` | S1.7 |
| `/how-matching-works` | S1.9 |
| `/quiz-preview` | S4 |
| `/quiz-preview/insights` | S4.5 |
| `/quiz-preview/early-career` | S4.2 |
| `/quiz-preview/career-transition` | S4 |
| `/quiz-preview/mid-career` | S4 |
| `/quiz-preview/teen-focused` | S4 |
| `/quiz-preview/career-job-search` | S4.9 |
| `*` | S1.11 |

### Authenticated (`RequireAuth`, role `job-seeker`)

| Route | Scenario |
|---|---|
| `/job-seeker/dashboard` | S7 |
| `/job-seeker/profile` | S19 |
| `/assessment` | S8.1 |
| `/work-pulse` | S8 |
| `/work-pulse/results` | S8.9 |
| `/environment-report` | S9, S21.3, S22.2 |
| `/situation-report` | S10, S11, S12, S21.2, S22.4 |
| `/pulse` | S13 |
| `/pulse/trend` | S13.7 |
| `/manager-match` | S14.2 |
| `/manager-match/results` | S14.4 |
| `/manager-profile` | S14.1, S14.6 |
| `/manager-profile/playbook` | S14.5, S14.9 |
| `/focus-type` | S15 |
| `/focus-type/results` | S15.4 |
| `/intelligence`, `/solverah-profile` | S16 |
| `/intelligence/paths` | S16.9 |
| `/trust` | S16.13 |
| `/quiz-insights` | S16.15 |
| `/career-quizzes` + 4 variants | S16.14 |
| `/career-job-search` | S16.14 |
| `/future-your-way` | S16.14 |
| `/agent` | S18 |
| `/search` | S17.1 |
| `/feed` | S17.5 |
| `/company-lens` | S17.6 |
| `/companies/:id` | S17.7 |

---

## 4. Appendix A — draft storage keys

All client-side. **Nothing is drafted server-side anywhere in the product.**

| Key | Storage | Surface | Survives reload? | Survives tab close? |
|---|---|---|---|---|
| `solverah_assessment_answers` | session | Work Pulse core (24) | answers yes, position no | no |
| `env_report_answers` | session | Environment Report (15) | answers yes, position no | no |
| `mp_answers` | session | Manager Profile (16) | **yes, fully** | no |
| `mm_answers` | session | ManagerMatch (15) | **yes, fully** | no |
| `solverah_wp` | session | legacy 12-question Work Pulse | — | no |
| `solverah_intake` | session | `/start` wizard | yes | no |
| `pendingQuizSave` | **local** | guest quiz answers, for replay | yes | **yes** |
| `guestQuizCompletedAt` | **local** | one-quiz guest lockout | yes | **yes** |
| `solverah.hasSession` | **local** | refresh hint on boot | yes | yes |
| — none — | — | **Pulse check-in** | **no** | no |

---

## 5. Appendix B — the error codes the UI branches on

When a step fails, these are the strings that decide which screen you get. A fix
chunk should branch on the `code`, never on the prose.

| Code | Status | Screen it produces |
|---|---|---|
| `no_core_sitting` | 409 | Recalibrate footer: "There is no Work Pulse sitting to pin to yet." |
| `no_manager_match` | 409 | Playbook gate: "Take ManagerMatch first" |
| `no_manager_profile` | 409 | Playbook gate: "Profile your manager" |
| `first_job_no_role` | 409 | Environment Report: "There's no job to describe yet" |
| `career_status_not_set` | 400 (legacy body) | Environment Report: "One thing first: where are you right now?" — and Path Intelligence's career-status prompt |
| `experiment_already_active` | 409 | **Nothing** — caught and deliberately silent; the button was already disabled |
| `not_a_change_in_place_cell` | 422 | Generic start failure card |
| `invalid_checkin` | 422 | Pulse: "We couldn't save that just now." |
| `invalid_cadence` | 422 | Cadence: "We couldn't save that just now. Try again." |
| `invalid_or_expired_code` | 400 | Forgot-password verify: "Invalid or expired code. Please try again." |
| `invalid code` / `code expired` | 400 | Verify-email — **raw lowercase**, `G8` |
| `moved_to_scoring_jobs` | 410 | Not user-facing; a client calling the retired sync submit path |

**Two error shapes coexist in this API**, which matters when reading a failure in
devtools: RFC 9457 problem+json (`application/problem+json`, with `errors[].code`) for
anything raised as an `ApiError` or an HTTP exception, and a legacy `{"error": "..."}`
string for handler branches. A third shape, `{"msg": "..."}`, comes from
flask-jwt-extended's own defaults on any auth failure — no custom loaders are
registered.

---

*Derived from source at `b5b8eec`. When this document and the product disagree, the
product is right and this document is a bug — file it the same way, against the step
ID.*
