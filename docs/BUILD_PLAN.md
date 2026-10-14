# Build plan — launch scope + model lane

**Created 2026-09-08.** Sebastian approved the direction the same day: the top
three ideas from `PRODUCT_IDEAS.md` (Situation Report, the Pulse, Manager
Decoder) plus the small sharp moves are **in scope for launch**; the causal
model implementation is planned here for the moment Julie's blockers clear;
everything else is parked in §9 as future work.

**How to read this file.** Workstreams are lettered; chunks are checkboxes
sized S (≤ half a focused day), M (1–2 days), L (3–5 days). A chunk is the
unit of work one session/subagent takes on: plan mode first, tests green
(including the CI-parity run: `SOLVERAH_IGNORE_DOTENV=1`), contract baseline
captured for any new endpoint, then mark the box. Build order lives in §8 —
it is not the letter order. All work lands on `causal_bayesian_model`; main
is deploy day only (`RUNBOOK_DEPLOY_MAIN_MERGE.md`).

**Design decisions embedded here that Sebastian has NOT yet individually
signed:** marked ⚑ inline and collected in §0.2. They are recommendations
with rationale, not settled facts.

---

## 0. Gates and ground rules

### 0.1 · Chunk 0 — record the decisions (S)

- [x] Draft `PRODUCT_DECISIONS.md` entries for Sebastian's sign-off:
  the §1 spine question closes (career development = conditions
  diagnosis + improvement, with matching as one output); top-3 + small
  moves approved for launch scope (2026-09-08); the D-15 conformance
  ruling for the Situation Report payload (§3.4 below is the proposed
  spec); Manager Decoder green-lit. Sebastian edits/approves wording —
  the entries carry his name, not an agent's.

_2026-09-10: drafted 2026-09-08, **signed by Sebastian 2026-09-10 as drafted,
no edits** — all six entries promoted into PRODUCT_DECISIONS §1/§2. The same
day Sebastian also decided Path Intelligence / O*NET: **keep as backbone**
(recorded there too). **A-4 and A-5 are now unblocked.**_

### 0.2 · ⚑ Embedded design rulings

⚑1, ⚑2, ⚑3 and ⚑5 were put to Sebastian as explicit options and **decided
2026-09-08** (recommended option accepted in each case). ⚑4 and ⚑6 are
routine engineering calls, proceeding as stated. _2026-09-10: all graduated
into `PRODUCT_DECISIONS.md` with proper signed entries (chunk 0 complete)._

| # | Ruling | Status | Where |
|---|---|---|---|
| ⚑1 | Manager Decoder playbook is **template-first** (LLM drafts the ~16 protocol cells once, human-reviewed, served deterministically); per-user LLM polish is a fast-follow | **Decided** — Sebastian, 2026-09-08 | §2.2 |
| ⚑2 | Pulse **condition experiments** are the designated cut line: launch ships check-ins + trends + events; experiments may slip past launch | **Decided** — Sebastian, 2026-09-08 | §4.4 |
| ⚑3 | **Skip** the core→8-dim culture-preferences mapping entirely; CompanyLens stays coming-soon until the causal model serves it | **Decided** — Sebastian, 2026-09-08 | §5.6 |
| ⚑4 | One **shared manager profile** store feeds both the Decoder and the Situation Report's manager section — built once, in Workstream C, consumed by A | Engineering call | §2.1 |
| ⚑5 | Situation Report pins to a **named person-side snapshot** (first completed sitting; explicit logged "recalibrate" action to re-pin), so core retakes are not a watchable gradient — the D-15 mechanism. Unblocks A-4/A-5. | **Decided** — Sebastian, 2026-09-08 | §3.4 |
| ⚑6 | Employer name on the environment report is **optional and unused at launch** (stored for the future aggregation lane, displayed nowhere) | Engineering call | §3.2 |
| ⚑7 | Path Intelligence `adjacent` feedback is **inline on the result cards**, not a questionnaire | **Decided** — Sebastian, 2026-09-16 | §6 F-6 |
| ⚑8 | `path_scoring.py` gets a **substantial rewrite** — not a deletion, not a second scorer | **Decided** — Sebastian, 2026-09-16 | §6 F-4 |
| ⚑9 | `fresh_start` excludes the user's SOC **minor** group, not major — major bars whole families (admin: 8 of 11 unreachable); minor wins on every metric | **Open** — recommend ratify | §6 F-7 |
| ⚑10 | `fresh_start` ships the **diverse seed** (8/8/8/8 clusters) at a measured **−0.09 static nDCG** that two rounds of feedback repay to level, never above — the design's "exceeds after taps" claim did not hold (n=4, one profile poisoned by the fire-metaphor hazard). Ship as-is with F-8's behavioural-profile fix, or revert to the interim similarity page? | **Decided** — Sebastian, 2026-09-21, on W-3a's measurement: **keep the seed for a `fresh_start` user who has stated nothing; drop it once wants are stated** (with wants the seed costs 0.10 on the five `fresh_start` profiles — 0.283 vs 0.385 — harm unchanged; headline 0.409 → 0.443). Built in W-3b | §6 F-7, §6a W-3 |
| ⚑11 | Build **F-9** — `role_w` applied only once feedback exists; F-8 measured 0.20 → **+0.061 nDCG**, clean inverted U, harm 0 (n=4) | **Closed by measurement** 2026-09-21 — no standalone F-9: W-3a re-measured it on top of the wants scorer (`role_w` 0.20 after one round of taps: 0.474 → 0.515, harm 0.060 → 0.020) and shipped 0.20 there | §6a W-3 |
| ⚑12 | Path Intelligence shows **no percentage** — not on the cards, not in the fit panel. Ranking and wire fields stay; the panel stays **as words** | **Decided** — Sebastian, 2026-09-17 (panel-as-words is the agent default, put to him twice, unobjected) | §6a W-1 |
| ⚑13 | Path Intelligence gains a **wants layer**: diagnose what should change in the user's *current* job — its own O*NET **tasks first**, a few **conditions second** — and steer all three paths with it. **Separate from the company model** (own instrument, storage, scorer); does not reopen ⚑3 | **Direction approved** — Sebastian, 2026-09-17. Build past W-1 **gated on W-3's measurement** | §6a |

_2026-09-17: **⚑10 and ⚑11 are overtaken by ⚑13** — both become measured arms inside W-3 (seed vs no seed with wants present; `role_w` after feedback) rather than rulings or a standalone F-9. **⚑9 stands either way**; still recommend ratify._

### 0.3 · Chunk 0b — commit hygiene before new work piles on (S–M)

Done-but-uncommitted lanes accumulate risk with every new workstream:

- [x] Land the ultrareview PR #145 fixes (3, suite at 1559 passed when built)
- [x] Land scorer-run storage (S1-6, built 2026-09-06)
- [x] Land Scenario A cron CLI (batch 3) and `flask backups run`
- [x] Confirm nothing else is stranded: `git status` + memory notes

_2026-09-08: verified in HEAD. All four lanes were found already committed
and pushed to `causal_bayesian_model` (`91b153d`) by the time this check
ran — no separate landing commits were needed for this section._

### 0.4 · External gates (not engineering, tracked so nothing pretends otherwise)

- **Julie:** priors form sent 2026-09-06; she answered the anchors_v3 memo
  from the same email instead (rulings in
  `Solverah_IP/ANCHORS_V3_JULIE_RESPONSE_2026-09-14.md`) and was re-asked for
  the form only on 2026-09-14. **Form RETURNED 2026-09-17** — converted
  clean and swapped into `priors.yaml` the same day (see E-1). The priors
  gate is OPEN: E-5 no longer waits on Julie, only on E-2 and the two
  blockers E-4 named. Async-only — see §5.1.
- **Launch/publicity gate:** entity + attorney (`[ENTITY NAME]`
  placeholders, dispute resolution). Real calendar lead time; §8's launch
  tiers are all hostage to it, so it should start now, in parallel.
  _Unstarted as of 2026-09-14._
- **Redis:** _done 2026-09-08_ — `REDIS_URL` + `CELERY_TASK_ALWAYS_EAGER`
  set, in production since deploy 1 (PR #150).

---

## 1. Workstream D — immediate fix + small sharp moves

### D-0 · The §5 regression (S) — first chunk of the whole plan

- [x] Intelligence hub CompanyLens card: "Your company matches are ready" →
  coming-soon copy (it leads to a 400 today)
- [x] CompanyLens page locked state: name the real reason (model in
  progress) instead of blaming the user for not completing Work Pulse
- [x] E2E: feature_tour note reclassified (GATED → COMING-SOON, no ERROR-COPY)

### D-1 · Teach the agent its own product (S–M)

- [x] Replace the `agent_service.py` TODO ("Quiz Results — Not yet
  available") with real context: FocusType archetype + recommendations,
  ManagerMatch archetype + dimension summary, quiz insights, and — once A
  ships — the Situation Report's gap buckets. **Never core's person-side
  scores** (D-15 applies to the agent too: it must not be an oracle a
  retaker can interrogate).
- [x] Guardrail line in the system prompt: instrument results inform advice,
  are not to be recited as numbers.
- [x] Tests: `test_agent_api.py` — context assembly with/without each
  instrument; absence degrades gracefully.

### D-2 · Assessment completion bridge (S)

- [x] "That's everything we need" screen gains a next verb *now* (Start
  FocusType → / ManagerMatch →), replaced by the environment-report bridge
  when A-5 ships ("24 questions about you. Now ~10 about your job.").

### D-3 · Trust page (M — content-heavy, code-trivial)

- [x] Static authed page: how the instruments work, what the matching will
  and won't mean, why there are no scores to see (D-15 explained in user
  language), the calibration discipline (two blind raters, bias review,
  re-identification testing) in plain words. Compliance mirror already
  blesses static transparency text as D-15-compatible.
- [x] Linked from assessment intro + Intelligence hub footer. Public/landing
  version waits for the publicity gate.

### D-4 · Search empty state + styling debt (S, then S–M)

- [x] Empty query renders an invitation, not `No results found for ""`
- [ ] (Low priority) `/search` + Feed slate-dark styling → cream design
  system, or park behind the Feed content decision

### D-5 · Quiz results persist into the profile document (M)

- [x] Audit where each of the six quizzes + insight currently lands
  (profile document? evaporates?); wire all six + GuestQuiz import into
  the profile document with stable keys
- [x] Consumed by D-1's agent context; available to future briefs
- [x] Tests per endpoint touched

### D-6 · Dashboard reframe (M) — LAST, after A + B exist

- [x] "Here's your job search overview" + Job Matches / Applications stats +
  Browse Jobs modal → working-life frame: current conditions summary
  (Situation Report card), this week's pulse, next suggested action
  _(Landed 2026-09-14: `SituationDashboardCard` leads, one next action derived
  from report state via `nextActionFor()`, no digits in the complete state;
  `/search` demoted to a plain link below the fold; `/me/dashboard` query
  retained for the intake modal and grid cards.)_
- [x] Keep Edit Profile; quiz/instrument quick action stays
- [x] This chunk *embodies* the §1 decision — sequence strictly after chunk 0
  records it and A/B give it content to show

### D-7 · Export/delete catch-up for the new user-data tables (S–M) — before launch

- [x] `environment_reports`, `manager_profiles`, and `situation_report_pins`
  (added 2026-09-10 by A-5) join `/me/export` and the
  account-deletion tombstone flow (S2's scrub discipline is the pattern).
  _(Landed 2026-09-11. Deletion needed no code: all three ride the existing
  retain-de-identified tombstone precedent. The guard test found 8 allowlisted
  pre-existing gaps — named follow-up D-7b, see the coverage test.)_
  Both tables carry user answers; flagged by C-3 2026-09-10 — the gap is
  shared, so close it in one chunk. Any table added later joins the same
  flows the day it is created (cross-cutting rule, §7).

---

## 2. Workstream C — Manager Decoder  *(build first among the big three: fully unblocked)*

### C-1 · Manager-profile instrument (M)

- [x] ~12–15 observational forced-choice items about the user's actual
  manager, same house style as `manager_match/questions.py`, same 4
  dimensions (autonomy given, feedback style, relationship, growth
  investment). Behavioral, both-poles-legitimate, no "is your manager
  good" item anywhere.
- [x] Bias-review pass in the `ASSESSMENT_ITEMS_BIAS_REVIEW.md` tradition
  (positional key balance! — the v1 core items failed exactly this)
- [x] `manager_match/manager_profile.py`: questions + pure scoring
  (mirrors `score.py`), pytest alongside
- [x] ⚑4: this instrument IS the manager section of the Situation Report —
  one table (§2.3), two consumers. Do not let A grow a second one.
  _(Held: C-3 is the one table; A-7's report links into the Decoder.)_

### C-2 · Diff + playbook engine (M)

- [x] Diff rule: per dimension, user need (ManagerMatch) × manager style
  (C-1) → mesh / grind classification with server-side thresholds
- [x] ⚑1 template-first: ~16 protocol cells (4 dims × grind directions),
  LLM-drafted once, human-reviewed, stored as content. Each cell: why this
  grinds, the ask, the 1:1 agenda items, 2–3 literal sentences.
- [x] Assembly is deterministic and instant (no scoring job, no provider
  dependency, no per-sitting variance). Fast-follow chunk (parked §9):
  LLM personalization pass over the assembled playbook.
- [x] Tone + privacy guardrails in the content review: fit not fault;
  playbook is private to the user and says so on the page.

### C-3 · Storage + API (S–M)

- [x] Migration: `manager_profiles` (user_id, answers, dimension scores,
  version, created_at — append-only, D-16 tradition)
- [x] `POST /api/v1/assessments/manager-profile` (submit → scores + playbook),
  `GET /api/v1/me/manager-playbook`
- [x] Rate limits; OpenAPI regen; contract baseline capture (additive)
- [x] pytest: happy / no-ManagerMatch-yet (409 with clear message → UI
  prompts to take it first) / malformed / retake versioning

### C-4 · Frontend (M)

- [x] Instrument flow (reuse ManagerMatch's forced-choice UI wholesale)
- [x] Playbook page — the payoff surface: mesh/grind map, protocols per
  grind, print/copy-friendly
- [x] ManagerMatch results page bridge: "Now profile your actual manager →"
- [x] Intelligence hub card (replaces nothing; new card beside ManagerMatch)
- [x] Vitest per component; feature_tour route added

---

## 3. Workstream A — Situation Report

### A-1 · Environment-side instrument (M)

- [x] ~10–12 items: the 6 model dimensions, environment side (what the role
  *offers*: real autonomy, actual pace, feedback culture as practiced,
  collaboration shape, innovation stance, decision style), worded from the
  rater rubric's anchors (`Solverah_Company_Rating_Rubric_v2.docx`,
  read-only reference) recast in second person
- [x] Plus: stage/size band 1–5, comp posture 1–5 (market-relative, the
  redefined `comp`), and the model's own outcome question — "overall, how
  well is this role working for you?" 1–5 (`experienced`)
- [x] Employment status via existing `career_status`: employed → current
  role; between_jobs/first_job → most recent role, flagged past-tense, and
  the report renders needs-forward ("what to seek") instead of gaps
- [x] Manager section = C-1's instrument, linked not duplicated (⚑4)
- [x] Same bias-review discipline; items are NOT ground-truth-sensitive the
  way core is (user describes a job, not themselves), so no token-map
  machinery needed — plain form

### A-2 · Storage (M)

- [x] Migration: `environment_reports` (user_id, submitted_at, answers,
  derived env dimension scores 0–1, stage_size, comp, experienced_outcome,
  career_status snapshot, optional normalized employer name ⚑6, version).
  Append-only; history feeds Pulse trends and future training rows.
- [x] Column semantics deliberately aligned with the model lane's
  `schema.sql` long-format expectations so §5.4's assembly is a join, not
  a translation

### A-3 · Interim rules scoring + gap engine (M)

- [x] Env answers → 0–1 per dimension (mean of anchored items — mirrors
  core's `mean_pole` shape)
- [x] Signed gap per dimension against the sealed person-side scores;
  ranking by |gap| with flat weights (honest about priors.yaml being
  placeholder — the model replaces this in §5.5, same interim→destination
  pattern as culture_fit_score)
- [x] Pure functions, no Flask (`work_pulse/situation.py` or sibling
  module), pytest first

### A-4 · D-15-conforming payload spec (S — but the most important design in the workstream)

- [x] Response contains per dimension: env score (echo of the user's own
  input), **gap bucket only** ∈ {feeding, aligned, straining} (3 coarse
  buckets, thresholds server-side), guidance refs. **Never** person-side
  scores, numeric gaps, or per-dim magnitudes.
- [x] ⚑5: the report pins to a named person-side snapshot (first completed
  core sitting). Core retakes do NOT silently move the report; an explicit
  "recalibrate" action re-pins and is logged. A retaker therefore has no
  gradient to watch — the D-15 mechanism, preserved.
- [x] This spec + the pinning rule is the text Sebastian rules on in
  chunk 0; build A-5 only after that ruling. _(Signed 2026-09-10 —
  A-4/A-5 are unblocked.)_

### A-5 · API (M)

- [x] `POST /api/v1/me/environment-report` (submit; sync — rules scoring is
  instant, no Celery job needed), `GET /api/v1/me/situation-report`
- [x] States: env report alone (no core yet) → needs-forward partial +
  bridge to Work Pulse; core alone → hub card prompts the env report
  (D-2's bridge); both → full report
- [x] Rate limits, OpenAPI, contract baseline, pytest per state

### A-6 · Guidance content (M — content, not code)

- [x] 12 cells (6 dims × 2 gap directions) × 3 registers: *change it in
  place* (concrete ask/experiment), *negotiate it* (what to say, to whom),
  *this one rarely moves* (what a ceiling here means). LLM-drafted,
  human-reviewed once, stored as static content — the
  `insight_engine.py` pattern at full scale, no per-user generation.
- [x] Manager-dimension cells defer to the C-2 playbook (link, don't
  duplicate)

### A-7 · Frontend (L)

- [x] Env-report flow: single scrolling form or short stepper (sliders +
  anchored choices — the machinery the MVP culture decision already chose)
- [x] Situation Report page — the flagship payoff surface: gaps ranked,
  three guidance registers per straining dimension, manager section
  linking into the Decoder, an honest "what this is / isn't" footer
  (trust page link)
- [x] Intelligence hub: the "Work Pulse complete — nothing to check" dead
  end becomes the Situation Report card (completion copy remains for
  users with no env report yet)
- [x] Core completion screen bridge (upgrades D-2)
- [x] Vitest; feature_tour + real_stack flows (register → core → env report
  → report renders)

---

## 4. Workstream B — the Pulse

### B-1 · Check-in instrument + storage (M)

- [x] Items: the teaser's five dimensions (fragmentation, sustainability,
  environmental friction, recognition, pace — `insight_engine.py`'s
  QUESTION_DIMENSIONS), 3 per check-in round-robin, + `experienced` 1–5.
  60 seconds, hard budget.
- [x] Migrations: `pulse_checkins` (user_id, taken_at, item scores,
  experienced), `pulse_events` (user_id, at, type enum: new_manager /
  reorg / remote_change / role_change / other+short text). Append-only.

### B-2 · API + cadence engine (M)

- [x] `POST /me/pulse/checkins`, `GET /me/pulse/history`,
  `POST /me/pulse/events`, cadence setting (weekly default / biweekly /
  off) on the profile _(plus `GET /me/pulse/next-checkin` — the client
  never chooses its items)_
- [x] Celery beat job: users due → Resend email with deep link (beat +
  Resend infra already in place) _(Landed 2026-09-11 as `flask pulse
  send-prompts` — the Scenario A cron pattern, not beat: it is the
  scheduling mechanism production actually runs. Runbook carries the new
  cron + `APP_BASE_URL`.)_
- [x] Anti-nag rule: 3 consecutive unanswered → auto-drop to monthly with a
  one-line "we've slowed down" note; off is always one click. Silence is
  data, never a guilt trip. _(Banned-words test greps the real rendered
  email HTML.)_

### B-3 · Frontend (M–L)

- [x] Check-in flow: one screen, tap-tap-tap-done, then ONE thing back
  (this week vs last — even "two points make your first trend")
- [x] Trend view: per-dimension sparklines + experienced line, event
  annotations on the axis; degrade gracefully at 1–2 points (load the
  dataviz discipline when building the chart; prefer a lightweight
  approach over a heavy chart dependency) _(Landed 2026-09-11: inline-SVG
  small multiples labelled Focus / Workload / Surroundings / Recognition /
  Pace; event ticks on the experienced line only.)_
- [x] Dashboard card: "Your pulse this week" (feeds D-6)
- [x] Vitest; feature_tour route

### B-4 · Situation Report ↔ Pulse wiring (S)

- [x] Env-report resubmission prompts when events land (new_manager →
  "does your Situation Report still describe this job?") _(Landed 2026-09-14:
  additive `events_since_report` [{type, date}] on the complete state, never
  the note; banner worded off the newest event, four specific leads + one
  generic; no dismiss state — resubmitting clears it. Contract 89→90.)_
- [x] Report page shows the experienced trend beside the diagnosis _(compact
  PulseSparkline after the at-a-glance strip, sourced from usePulseHistory;
  B-3's 0/1/2+ degrade; "See your full trend →" to /pulse/trend.)_

### B-5 · ⚑2 Condition experiments (M — designated cut line, may slip past launch)

- [x] Experiment cards generated from A-6's *change-it-in-place* cells:
  named change, 2-week window, before/after from pulse deltas _(Landed
  2026-09-14: "Try this for two weeks →" on every change-in-place cell in the
  present-tense rendering; running state shows started/ends dates + a plain
  one-click Abandon; ended state shows the readout in words. Not offered in
  the needs-forward rendering — no live job to run a change against.)_
- [x] `experiments` table (user_id, guidance cell ref, start/end, status)
  _(`dimension`/`direction` name the cell — `work_pulse.situation`'s short
  under/over vocabulary, matching what a `StrainDimensionEntry` already
  carries — plus `register` (always `change_in_place` today), `started_at`,
  `ends_at` (stored, not computed), `status` {active, abandoned},
  `abandoned_at`, `created_at`. One active experiment per user enforced by a
  partial unique index at the database, not only the 409 check. Migration
  `20260914_experiments`, chained on `20260911_pulse_checkins`, proven from
  empty. D-7 wired the same commit: exported unbounded, retained
  de-identified on deletion (no free text on the row).)_
- [x] Honest stats copy: "your numbers moved / didn't" — no causal claims
  per-user; the aggregate is the model lane's food, not the user's chart
  _(Readout is one of four words — `not_enough_data` / `moved_up` /
  `moved_down` / `about_the_same` — plus the two check-in counts, never a
  delta or a mean. Threshold and reasoning live in
  `work_pulse.experiments`'s module docstring; a one-line pointer for the
  model lane lives in `causal_graph/v1_model/ASSEMBLE_TRAINING_DATA_NOTES.md`.
  Routes: `POST /me/experiments` (201; 422 `not_a_change_in_place_cell`; 409
  `experiment_already_active`), `GET /me/experiments` (phase + readout +
  `experiment_name` per row), `POST /me/experiments/{id}/abandon` (200,
  idempotent, 404 cross-user). Contract 90→97, additive (`export` gained one
  key); `docs/ARCHITECTURE.md` A27.)_

---

## 5. Workstream E — model lane (parallel; external gates marked)

### E-1 · Julie round-trip (external gate — send is ready)

- [x] Send the priors form (built + verified 2026-09-06; asked 2026-09-06,
  chased 2026-09-08) _(SENT 2026-09-06; no reply as of 2026-09-11 — a
  gentle follow-up to Julie is the open move)_
- [ ] ⚑ Append to her queue — same async, resumable, valid-half-finished
  format, ONE form not a second sitting: (a) the environment-side
  self-report anchors sanity check (A-1 items vs her rubric reading),
  (b) the 6-dim → O*NET Work Context crosswalk question (IN — the O*NET
  decision went to "backbone", Sebastian 2026-09-10)
- [x] On return: internal appendix maps answers → real `priors.yaml`
  values ({mean, sd} per weight); commit the swap — structure code
  unchanged by design
  _(SWAPPED 2026-09-17: `priors.yaml` now carries the converter's output,
  unedited; the placeholder is kept beside it as `priors_placeholder.yaml`
  — the record of her contribution AND the neutral fixture
  `tests/test_match_scoring.py` uses for its analytic anchors. All twelve
  of her answers reproduce through the real `match_core.point_p_fit` on
  the live file to within 6e-07. Suite 3298 passed / 52 skipped, CI-style.
  No production effect: nothing calls `match_scoring` but its test, and
  the Situation Report still runs A-3's flat weights until E-5.
  **Superseded later the same day** — the Situation Report now ranks on
  these weights (E-5's first-consumer note below), so `match_scoring` has
  a production caller and an edit to this file reaches the report.
  Research
  scripts (`recovery_multiseed.py`, `build_model.recovery_curve`) read the
  LIVE file — their recorded results were made under the placeholder, so
  pass `pri_path=priors_placeholder.yaml` to reproduce them.)_
  _(RETURNED 2026-09-17, all twelve answered, all "confident". Converter
  ran clean, no positive-mag warnings. Pace is her costliest mismatch
  (mag −2.52), autonomy the mildest (−0.67); feedback and decision are
  strongly one-sided (wanting MORE than the role offers is survivable).
  The consistency re-ask is VOID, an instrument defect not a finding: its
  reworded person "doesn't mind the target moving" (a tolerance) where the
  original is "at their best when priorities move quickly" (a need), so her
  3/10 and 8/10 answer two different people — and agree with her own note
  that a preference's cost depends on how much it matters to the person.
  Consequence: there is NO noise-floor read under these numbers; the
  converter's printed "noise floor" line is wrong for this form version.
  Her free-text notes raise four structure questions the model has no
  term for — per-person importance weighting, "doing well" vs "satisfied"
  as the outcome, career-stage × comp, and the manager as a moderator.)_

### E-2 · Anchors / ground-truth calibration (partially external)

- [ ] Complete the evidence-packet set (packet pipeline runs as scheduled
  tasks; round-1 six have known unequal inventories — do NOT re-scrub)
- [ ] Both raters score blind → merge → Agreement tab → reword anchors
  where gap > 0.15 (rubric fix, never averaging)
- [ ] Replace confounder `scale` placeholders (stage_size, comp) with real
  distributions from the scored set
- [ ] Person↔company scale calibration check — load-bearing
  (`SCALE_CALIBRATION_CHECK.md`) — before ANY live ranking ships

### E-3 · Suite + toolchain hygiene (S–M)

- [ ] causal_graph suite: 4 failures are missing packages, not defects —
  fix the env (keep the conftest API-key poisoning; it's deliberate)
- [ ] PyTensor compile fragility: decide conda-forge PyMC vs Python-mode
  slow for the fit runs (fit is offline, so slow is tolerable at first)

### E-4 · DB → model glue (M)

- [x] `assemble_training_data(db)` → (person, env, confounders, outcome):
  person rows from core sittings; env + `experienced` rows from
  A-2's environment_reports (this is the inversion paying off — training
  pairs exist at launch); synthetic fixtures retired (scoring_key_version
  discipline keeps eras separable)
- [x] Funnel/collider fields carried per the handoff (capture how each
  pair entered the data)
  _(Landed 2026-09-11: 14 supplied + 12 explicit NULLs with capture notes as
  data. Two E-5 blockers named in ASSEMBLE_TRAINING_DATA_NOTES.md: the
  Bernoulli outcome likelihood vs 1–5 `experienced`, and preprocess_conf's
  NULL handling.)_
  _(**Both blockers CLEARED 2026-09-17.** `build_model(..., head="experienced")`
  attaches an OrderedLogistic over the same linear predictor, with the
  rating-3/4 cutpoint PINNED at 0 so `sigmoid(z)` is exactly P(rating >= 4) =
  "doing well" — the event Julie's weights were elicited against, so they carry
  over with no rescaling and the serving path's meaning is unchanged. `appeal`
  stays the default and is untouched; `settings.outcome` survives as the legacy
  alias of the new `settings.heads.appeal`. A NULL `comp` now excludes that row's
  term from z via a `conf_missing` mask (no 21st weight); an unmasked NaN raises
  instead of silently NaN-ing p_fit. Recovery on simulated data:
  `causal_graph/v1_model/results/ordinal_recovery.md`. Still unfeedable from this
  source: `industry`, which the instrument never asks and which has no neutral
  level index — a config decision, still unmade.)_
  _(**Third blocker CLOSED 2026-09-21.** The `industry` decision is made, and it is
  the same ruling as for `comp`: EXCLUDE THE TERM. A masked categorical row takes
  level 0 as a placeholder and `preprocess_conf` returns a companion
  `{key}__present` array (1.0 present / 0.0 masked) that `outcome_logit` multiplies
  the per-level weight by, so the row contributes nothing and the placeholder weight
  is never read. Rejected: an `unknown` LEVEL (shared by every row off a source it is
  collinear with the intercept, and would bleed into the "8 in 10 doing well"
  baseline) and DEACTIVATING the confounder (strips it from the company-side path too
  and moves the 20-row flat weight set). Self-reversing: a source that starts
  supplying `industry` gets the term back with no code change. **Nothing in code now
  stands between the environment rows and a fit** — only data volume. Proven
  end-to-end in `tests/test_ordinal_head.py` §7–8 and, on the PyMC side, by a short
  NUTS fit that leaves `w_industry` on its prior. Details and the parked
  "switching industries" note: ASSEMBLE_TRAINING_DATA_NOTES.md, 2026-09-21.)_

### E-5 · Fit run + serving (M–L, after E-1 + E-2)

- [ ] First real-priors fit; posterior snapshot into `weight_posterior`
  (scorer-run storage from chunk 0b)
  _(2026-09-17: the OUTCOME HEAD this needs now exists — E-4's two named
  blockers are cleared (see the E-4 note above), so `experienced` rows can
  reach a likelihood for the first time. **The box stays UNCHECKED: no real fit
  has run.** What has run is `ordinal_recovery.py`, which simulates from known
  weights and known cutpoints and checks the posterior finds them — an
  inference check on data the model generated itself, not evidence about real
  placements. This box is done when a fit on real outcome rows lands a posterior
  in `weight_posterior`, not before.)_
  _(2026-09-21: **the PIPELINE now exists end to end** —
  `causal_graph/v1_model/devfit/` (see its README). Seed synthetic people through
  the real store functions into a local `solverah_modeldev`, assemble them, fit
  the ordinal head, save a `model_run` + its 20 `weight_posterior` rows, and read
  one user's gaps, costs, rank and P(doing well) back out. A guard refuses any
  database that is not local and named `solverah_modeldev*`, because `.env`
  carries a production URL and `explain_user` prints exactly the magnitudes D-15
  keeps off every payload. A diagnostic gate refuses to save a run with a
  divergence, r_hat ≥ 1.05, or — the case that bit — no r_hat at all.
  **The box STILL stays UNCHECKED, and the distance left is the whole distance.**
  Everything fitted so far is SYNTHETIC: rows generated from the model's own
  predictor with a planted truth, which tests the machinery and says nothing
  about real placements. This box wants real outcome rows, and there are none.
  What it does mean: when they arrive, nothing has to be built first.)_
- [ ] Serving seam: `score_fit(person_scores, env_scores, confounders) →
  P(fit), per-dim contributions, uncertainty` — pure function over the
  posterior, no PyMC at request time
- [ ] **First consumer: the Situation Report** (A-3's flat weights →
  posterior weights; payload spec unchanged, so no UI change) — the
  interim→destination swap, proven pattern
  _(PRIORS-ONLY HALF LANDED 2026-09-17. The Situation Report no longer runs
  flat weights: it ranks on `priors.yaml`'s elicited `mag`/`dir` means, read
  through `match_scoring`, ordered severity tier first and weighted
  directional cost second. Payload shape unchanged, no UI change — which is
  the swap this box describes, executed against a file rather than a
  posterior. Same trip fixed the ranking never reaching the client at all:
  the service emitted fixed `DIMENSIONS` order and both frontends render
  what they are handed. **The box stays unchecked.** The weights are one
  expert's judgement with no outcome data behind them, they come from the
  file and not from `weight_posterior`, and there is still no `score_fit`
  serving seam — E-5 is done when a real fit serves this, not before.
  See PRODUCT_DECISIONS §2, "The Situation Report orders by severity tier".
  A run-backed source now exists behind it: `SOLVERAH_MODEL_WEIGHTS_SOURCE=run`
  reads the latest `model_run` / `weight_posterior` row instead of the file
  (PRODUCT_DECISIONS §2, 2026-09-21). Production's default is still `priors`
  and this box stays unchecked until a real fit serves it there.)_
- [ ] Second consumer: offer evaluation (§9). Third: CompanyLens, only
  when a company store exists that earned it

### E-6 · ⚑3 The culture-preferences question (S — a deletion, not a build)

- [ ] Recommendation: do NOT build the core→8-dim mapping.
  `_derive_culture_preferences`, the 8-dim interim scorer, and the
  `work_pulse` submission dependency retire when E-5 serves CompanyLens;
  the 400-blocked endpoint stays coming-soon (D-0's honest copy) until
  then. Record in PRODUCT_DECISIONS either way — it amends §2's "outstanding
  by design" fourth call site to "won't fix, superseded."

### E-7 · Learning loop (post-launch, data-gated)

- [ ] Blend expert priors toward observed outcomes (BayesianEstimator per
  cbm_notes step 4) once env-report + pulse rows cross a pre-registered
  N; S-17/S-18 discipline — pre-register the analysis, no peeking
  _(2026-09-29, BUILT, UNCOMMITTED: an optional **global-scale** fit for the
  low-N regime, approved by Sebastian. `run_fit --global-scale` reparameterizes
  the twelve dimension weights as `s * prior_mean + delta`, s ~ LogNormal(0, 0.5),
  delta ~ Normal(0, 0.10); confounders/intercept/cutpoints unscaled. Default OFF
  and bit-identical off; same 20 exported rows (effective weights), s's posterior
  in `notes`. No schema, serving or API change; production still reads priors.
  Synthetic recovery of a planted s = 0.4: N=100 → 0.54 [0.28, 0.80], N=300 →
  0.44 [0.27, 0.65], N=1200 → 0.47 [0.36, 0.59], 0 divergences. On the same 100
  rows the default fit covers 8–15% of the way to truth, the global scale ~78%.
  Numbers and caveats: `causal_graph/v1_model/devfit/README.md`. Whether to use it
  for the first real fit is still a decision to take when there are real rows.)_
- [ ] The protected-class proxy check rides the same N≥300 gate (compliance
  mirror note)

---

## 6. Workstream F — Path Intelligence rebuild  *(green-lit 2026-09-16; runs while E waits on Julie)*

**CODE COMPLETE 2026-09-16** — eight chunks landed and verified; see the close-out at the end of this section.

Design of record: `docs/PATH_INTELLIGENCE_REDESIGN.md`. Sebastian green-lit the
build 2026-09-16 and made two rulings that close that doc's §5: the `adjacent`
feedback is **inline on the result cards** (⚑7), and `path_scoring.py` gets a
**substantial rewrite** — not a deletion, not a second scorer (⚑8).

Why this exists: the current scorer is expensive (~160 O*NET calls per cold run,
to rank ~40 candidates and show 10) and structurally inaccurate — most of the
compared vocabulary is O*NET's **fixed ~35 generic skills, which every
occupation has**, so the discriminating signal is averaged into constants before
any weight is applied. It also caused the 2026-09-15 production OOM. §1 of the
design doc has the measurements.

**This lane has no external gate, and that is why it was chosen.** E is blocked
on Julie's priors form; F is the largest piece of launch-relevant work that is
not. Keep it that way — see F-2's second warning.

### F-1 · Corpus builder + S3 artifact (M)

- [x] `flask corpus build` CLI: enumerate every O*NET occupation
  (`get_job_families` + `get_job_family_occupations` — ~23 calls, ~1,000
  occupations), fetch description + tasks each, compose the **role document**
  (title + description + tasks + hot tech)
- [x] Two new `onet_client` methods for description and tasks — `Occupation` is
  `code` + `title` only today (`onet_client.py:88`)
- [x] Embed in batches; write a `float32` matrix + JSON sidecar (row → O*NET code)
- [ ] Upload to the **app** bucket (`S3_BUCKET_NAME`), versioned by filename.
  _(deliberately NOT done in F-1 — Sebastian reviews the artifact first, then triggers the upload; F-3 wires the load)_
  NOT the backup bucket — `config.py` validates that pair all-or-nothing and
  refuses overlap by design
- [x] Check O*NET rate limits before firing ~3,000 calls in one batch

_**Embed the role document, not the bare title.** A 2-3 word title is dominated
by one token, so title-only similarity reproduces the exact "Data Scientists →
Political Scientists" failure that the SOC allow-list at `path_scoring.py:154`
was hand-written to suppress — the hack would still be needed. Design doc §2.1._

_~1,016 × 1536 × 4 bytes ≈ 6 MB; build cost ≈ 305k tokens of
text-embedding-3-small, under a cent. Storage decided by Sebastian 2026-09-16:
**`.npy` in S3**. No pgvector, no ANN index — brute-force exact cosine over 6 MB
is sub-millisecond, and an index would trade exactness for a speedup nobody
needs._


_2026-09-16: **F-1 landed** (376c8d7). Artifact at `Desktop/solverah-corpus/`: 1,016 x 1536 float32, 6,242,432 bytes, L2-normalised, sorted by code. 3,073 O*NET calls at 4 req/s (ToS limit is 5/s, 50k/day), ~$0.009 of embeddings. Three latent client bugs fixed on the way: `get_job_families` never worked against v2 (bare array), `get_job_family_occupations` silently capped at 100 (51-0000 has 114), and `get_tech_skills(hot_only=True)` is an unordered set so a new ordered `get_hot_technologies` was added. **For F-3:** 57 "…, All Other" rows are ~50-char title-only documents and should be filtered at retrieval; `/online/occupations` carries Job Zone for the whole catalog in ~11 calls._

### F-2 · Evaluation harness + today's baseline (M) — BEFORE the rewrite

- [x] A labelled set of (profile → acceptable occupations) pairs
- [x] Offline runner + metric (precision@10 / MRR) that can score any scorer
- [x] **Measure the CURRENT scorer first and record the number**
  _(**RECORDED 2026-09-16 16:32Z**, `tests/fixtures/path_eval/runs/baseline_today.json`, `path_scoring.score_paths@HEAD`, 19 non-degenerate profiles, ran in 67 s — the 3,200-call estimate was an upper bound; `_OCC_CACHE` warmed across same-family profiles. **Macro: nDCG@10 0.318 · harmful_rate 0.031 · P@10 0.232 · MRR 0.566 · coverage 0.346 · primary_recall 0.382.** Below F-2's 0.35 "real scorer" line. **EMPTY (= a 500 in prod): p14 electrician, p15 graphic designer, p19 degenerate** — the allow-list prediction confirmed live. Five harmful suggestions across three profiles (retail mgr, warehouse, paralegal). p12 teacher-adjacent scored 0.000 on every metric with 10 results returned — ten unjudged cards. **Caveat:** p08 nursing took 26.8 s and returned 1 of 11 reachable — the shape of 429 backoff dropping candidates, not scorer judgement; F-4 must not count p08 as a win. This is the number F-4 has to beat: nDCG > 0.318 with harm == 0.)_

_Design doc §6 names the absence of this as the plan's weakest point: without
it, every weight in F-4 and F-7 is opinion and "the rewrite is better" is
unfalsifiable. Build it before the thing it judges._

_⚠ **Two warnings.** (1) This is a **scorer-quality** baseline, not a test-suite
baseline — CLAUDE.md's "no baseline runs" rule is about pytest and does not
apply here; do not let anyone collapse the two. (2) **The labelled set must not
become a Julie dependency.** "Is this occupation a reasonable suggestion for
this profile?" is a judgment Sebastian or a careful agent can make; it is not
the anchors/rater work. If it turns into expert elicitation, F inherits E's
blocker and the entire reason this lane was chosen evaporates._


_2026-09-16: **F-2 landed** (f51bef7). 20 profiles, 249 labels — **correction 2026-09-16: four `fresh_start` profiles (p05, p07, p10, p16), not five; verified by loading the fixture. Every fresh_start number in F-7 is n=4, below this note's own n=5 rule** (66 primary / 130 acceptable / 45 harmful / 8 anchor), 56 flagged low-confidence in a `confidence` field (`python -m backend.services.path_eval review`). Every code validated live against O*NET (48 calls). **Metric correction:** precision@10 is rank-blind and MRR saturates on a 10-card shortlist, so the harness adds **nDCG@10 (tune on it)** and **harmful_rate@10 (gate on it, target 0.0)**; calibrated — random scores nDCG ≈ 0.01-0.02, oracle 1.0, so ≥0.35 is a real scorer. **Sample-size rule for F-4:** 20 profiles supports "clearly better or worse", NOT per-axis claims (n=5-6 per cell). **Production finding:** `_DEFAULT_ALLOWED_SOC_PREFIXES` structurally excludes whole families — electrician 0/3 primaries reachable (47-/49- barred), graphic designer 1/3 (27- barred), warehouse 2/4 (53-/49-/51- barred), teacher loses 21-. Three of 20 profiles will likely return empty and 500 today — the ACC-4 shape, hitting tradespeople and designers. See F-4 and F-8._

_2026-09-16, from F-4: **the `anchor` grade is applied inconsistently** — 8 profiles have one for the user's own occupation, the 8 tech/admin ones (p01 15-1252.00, p02, p03, p04 15-2051.00) grade their own job `primary`. Any scorer that correctly excludes the anchor forfeits a top primary on those four. ⚑ Regrade to `anchor`? Sebastian's call; both runs re-score identically either way, so the comparison stays honest._

### F-3 · Retrieval seam (M)

- [x] Load the matrix at boot; `retrieve(query_vec, k, filters)` — one
  `matrix @ query`, exact, no ANN
- [x] Hard filters at this tier, not soft weights: Job Zone feasibility, and
  SOC exclusions where a path calls for them
- [x] **Fail soft when S3 is unreachable at boot**; cache the artifact locally
  after first fetch

_That last box is not optional. A boot-time S3 dependency is a brand-new outage
mode on a service that has just had two (2026-09-08, 2026-09-15)._


_2026-09-16: **F-3 landed** (88dae71). `backend/services/occupation_retrieval.py`: `get_corpus()` lazy + memoised + lock-guarded — **NOT at boot**, deliberately: `create_app()` also runs in `flask db upgrade` and every cron, so boot-loading would put a 6 MB fetch on migrations; two tests guard that `factory.py` never imports it. `retrieve(query_vec, k, *, exclude_codes, exclude_soc_prefixes, zone_max, include_all_other)` → `list[Match]`; `vector_for(code)` returns ANY row incl. filtered ones; `CorpusUnavailable` is a fresh typed exception per call (re-raising one cached instance grows its `__traceback__` — a slow leak). Sources: `SOLVERAH_CORPUS_PATH` (dir or .npy), then `SOLVERAH_CORPUS_S3_KEY` + `S3_BUCKET_NAME`, cached in `SOLVERAH_CORPUS_CACHE_DIR`; S3 mocked, not populated. **All-Other filter = title suffix, 75 rows; contamination 27/200 → 0/200.** Zones in a SEPARATE `*.zones.json` (`flask corpus zones`, 11 calls, run for real); schema untouched, reviewed artifact bytes unchanged. Latency 0.21 ms median k=10, 0.25 ms with all filters. **For F-4:** O*NET v2 has merged Job Zones 1 and 2 — live range is 2–5, `_zone_delta_score`'s 1–5 arithmetic is one step off; zones cover 923/1016 — 18 real occupations (17 military `55-`) have none and are excluded under any ceiling; read `zone.code`, never `zone.title`. Five `get_all_occupations` tests live in `test_occupation_retrieval.py` rather than `test_onet_client.py` (ownership deviation, documented)._

### F-4 · ⚑8 The substantial rewrite of `path_scoring.py` (L)

- [x] **Replace** `_gather_candidates` — the job-family + keyword funnel becomes
  F-3's retrieval
- [x] **Replace** the comparison target — role documents, not a centroid
  dominated by the fixed ~35 generic skills. *This is the accuracy fix; the
  retrieval change alone does not deliver it*
- [x] **Keep** `_zone_delta_score`, `_work_style_similarity`,
  `_role_coverage_score` and the weighting scheme — not broken, and exactly
  what F-5 needs for a single occupation
- [x] Anchor `stay_in_field` on the user's own resolved occupation vector
  (document-to-document, symmetric), not title-to-title
- [x] Beat F-2's recorded baseline, or say plainly why not

_⚑8 Sebastian, 2026-09-16. Closes design doc §5 #1. Two scorers means two
things to keep correct; a clean deletion would throw away per-candidate logic
that is fine. `path_scoring.py:1166` already asks for the retrieval half of
this ("Replace this block with `get_related_occupations` when O*NET adds that
endpoint") — F-3 is that endpoint, self-built._


_2026-09-16: **F-4 landed** (f12dd79) and the overseer re-verified every load-bearing claim: label fixtures byte-identical, `path_eval.py` change purely additive (`--scorer` cost model), both runs re-scored with the current harness. **nDCG@10 0.318 → 0.491 · harm 0.031 → 0.005 · P@10 0.232 → 0.437 · MRR 0.566 → 0.770 · coverage 0.346 → 0.442 · primary_recall 0.382 → 0.557.** Verdict holds with p08 discounted (0.320 → 0.481). The four structural profiles: electrician **500 → nDCG 0.416**, graphic designer **500 → 0.808**, warehouse harm **0.2 → 0** (was shown Software Developers + Accountants), teacher-adjacent **0.000 → 0.194**. **Per-request O*NET calls: ~160 → 0** (two fallback sites remain inside `_resolve_current_zone`; `score_paths`' call graph is entirely corpus + embeddings; `ThreadPoolExecutor` gone). LLM completions 1-3 → 0. `_EMBED_CACHE` 300-700 entries/15-35 MB per run → **3-14 entries/19-90 KB** — the OOM demand is removed, not capped. Wire: `InsufficientProfile` → `_error(400, "profile_incomplete")` → job row `{status: failed, error: profile_incomplete}`, which `stateForFailure()` already branches on; openapi regenerated, contract 0 diffs / 97 responses. Tombstoned 30 names (`TestTombstones`). Parked for F-5, uncalled: `_build_role_profile`, `_compute_centroid_score`, `_find_matched_skills`, `_compute_weighted_user_centroid`, `_role_coverage_score`, `_work_style_similarity`. Zone: unresolved fallback 1 → 2 (a floor of 1 inflated every delta), missing candidate zone = delta 0, curve reshaped from climbing bonus to feasibility signal. **Four findings:** (1) O*NET keyword search was corrupting anchors in prod — "Senior Backend Engineer" → Biofuels Managers, "DevOps Engineer" → Nuclear Engineers; corpus resolution fixes it at zero calls, worth ~+0.05 nDCG. (2) ⚑9 below. (3) **Label-set defect:** 8 profiles carry an `anchor` grade for the user's own job, the 8 tech/admin ones grade it `primary` (p01-p04); excluding the anchor therefore forfeits a top primary and explains 3 of the 6 regressions. Not edited — Sebastian's call, see F-2. (4) `overlapping_skills` used the wrong threshold so **no card ever named a skill**, silently degrading `path_narrative`'s prompt; fixed with a raw floor of 0.30. Also retired: `llm_debug.txt`, which the funnel wrote on **every production request**._

### F-5 · Deep fit on click (M)

- [x] New endpoint: the full analysis for ONE occupation, run on user click
- [x] Stored per `(user, occupation)`, invalidated on profile write, mirroring
  `path_cache`'s `invalidate` discipline — needs a table + migration
- [x] Rate limit, matching `POST /me/path-suggestion-jobs` — this is a per-click
  provider spend
- [x] Synchronous: ~3-4 `_OCC_CACHE`-backed calls for one occupation, ~500ms-1s
  warm. No job/poll pair

_Sebastian's design, 2026-09-16. The budget currently spread thin across ~40
candidates gets spent on the one the user actually cares about — so the analysis
gets **better**, not merely rarer._


_2026-09-16: **F-5 landed** (54ed44c), 3085 passed / 0 failed; overseer verified the commit touched nothing off-limits. **`POST /api/v1/me/path-fit/<onet_code>`**, cookie + CSRF, no body, `shared_limit("10 per minute", scope="intelligence:path-fit")`. POST kept: per-click provider spend with a stored side effect, and a GET would sit outside the CSRF guard. Errors are the `{"error": code}` shape `stateForFailure()` branches on: 400 `career_status_not_set` / `profile_incomplete`; 404 `invalid_onet_code` / `unknown_occupation` / `unsupported_occupation` (All-Other); 503 `corpus_unavailable` — and the code is validated BEFORE the corpus loads, so an S3 outage cannot hide a permanent 404 behind a transient 503. **Latency, measured:** cold 2,384 ms (exactly 4 O*NET calls — tasks is a fourth endpoint; worst case 5 via `_resolve_current_zone` fallbacks), same-user warm 12 ms, **different-user-same-card 844 ms — the common case; F-6 sizes its spinner to ~850 ms, not 12.** Storage `path_fits` `UNIQUE(user_id, onet_code)` JSONB; stale = profile fingerprint mismatch (sha256 of the fields the analysis reads) OR 30-day TTL (O*NET's own content is the one input no profile write can invalidate) OR explicit invalidate at all six `path_cache.invalidate` sites, in-transaction; `test_path_preferences_api.py` now enumerates the RULE (per-file count parity, floor 6, file-set pinned). Migration `20260916_path_fits` proven from empty on alembic-only `solverah_f5m`; ORM vs migrated schema identical except the FK *name*, which is a repo-wide pre-existing convention. Six Tier-2 functions + eight constants moved to `path_deep_fit.py`, maths byte-identical; `TestTombstones` +14, plus `test_tier_two_moved_rather_than_died` and `test_tier_one_makes_no_per_occupation_item_call`; `_EMBED_CACHE` shared by both tiers and asserted to be one object. Wire: openapi +292/−0; contract baseline **re-verified 0 diffs BEFORE recapture**, then +2 steps (99 responses). Narrative deliberately deferred — `narrative: null` on the wire so the shape holds. **Fixed while measuring live:** flat hot-tech importance made the gap list tie-break alphabetically (Alteryx, EC2, Redshift…); now O*NET's own rank. **Routed onward:** (→F-6) `src/shared/api/schema.ts` not regenerated — run `npm run generate:api`, expect the known catch-up diff; feature-tour ROUTES needs nothing (no new frontend route); real_stack flow needs the corpus on the runner (→F-8). (→F-8) `_EMBED_THRESHOLD = 0.70` is too strict for O*NET's verbose names — **a user with "SQL" is told "Structured query language SQL" is a gap**, pre-existing, now product-visible in the panel; fix by normalising names, not by tuning a threshold there is no harness for. (→F-8) `PATCH /me/career-status` invalidates neither cache — pre-existing Tier-1 bug in `set_career_status`; Tier 2 self-corrects via the fingerprint. **For Sebastian, defaults taken:** per-click LLM narrative deferred (spend + latency decision; shape ready); `path_fits` joins account deletion but NOT `/me/export` (derived read-through cache; exporting is a contract change needing an A-number)._

### F-6 · ⚑7 `adjacent` — inline feedback on the result cards (M)

- [x] Result cards carry "too similar" / "interesting"; the list re-ranks as the
  user taps
- [x] Rocchio update: `q' = α·q + β·mean(liked) − γ·mean(disliked)`
- [x] **Both signals, not just the radius.** "Too similar" raises the annulus
  inner radius; "interesting" *rotates* the query — two occupations equidistant
  from the anchor can lie in opposite directions
- [x] ~~MMR for probe diversity (top-K teaches nothing, random teaches nothing)~~ **RETIRED ON EVIDENCE, 2026-09-16** — built, measured in a controlled two-round experiment (taps held fixed across arms; the first, confounded version was caught and re-run), dropped: no configuration beat no-MMR (0.607 vs 0.599 best), and the variants that actually diversified cost 0.05–0.17 nDCG. Full table in `path_scoring.py`. Design doc §3.2 carries the retraction.
- [x] Zero taps must still yield a full default result set

_⚑7 Sebastian, 2026-09-16: **inline, not a questionnaire.** Closes design doc
§5 #3. The doc originally proposed a one-screen elicitation step; that was the
weaker idea — a separate step is friction before the user has seen any value,
most people skip it, and the accuracy benefit never lands. Inline makes the
feedback *be* the browsing, and is valid-half-finished by construction._


_2026-09-16: **F-6 landed** (397aaac), 3158 passed / 0 failed backend, 953 vitest, `tsc -b` clean; overseer verified hygiene (27 files, nothing off-limits), a single alembic head (`20260916_path_fb`, file `path_feedback.py`), and that the **zero-tap run re-scores byte-identical to F-4** (0.491 / 0.005 / 0.437 / 0.770) — the loop changes nothing until a tap. **Endpoints:** `POST`/`DELETE /api/v1/me/path-feedback`, `{onet_code, verdict}`, 20/min on scope `intelligence:path-feedback` (10 would 429 a ten-card shortlist); both write INTO `path_cache` and invalidate nothing, so F-5's enumeration rule needed no carve-out. **Three verdicts** — `not_for_me` added because it is what makes Rocchio's negative term reachable (subtracting a too-similar card subtracts the anchor); +0.011 nDCG at matched constants, harm flat. **Constants:** α 1.0, β 0.40 (hard elbow), γ 0.15, `r_min = min(cos(anchor, rejected)) − 0.01`, `_RADIUS_MIN_SURVIVORS = 10`, `_RETRIEVE_K_ADJACENT = 50`; tuned with taps constrained to cards the profile was actually shown (the first sweep let a tap land on a card retrieval excludes and reported ~2× the gain — caught). **Simulated feedback, real corpus:** macro 0.528 → 0.551, harm 0 → 0; the two worst baselines gain most (teacher 0.194 → 0.445, data analyst 0.399 → 0.497). The radius alone reads as a loss (0.477) — the metric's limit: the nearest-to-anchor card is very often labelled *primary*, so honouring "yes, and I don't want it" deletes a labelled-good result by construction; the test gates on what the labels can answer. **Storage** `path_feedback` `UNIQUE(user_id, onet_code)`, upsert on re-tap, migration proven from empty on `solverah_f6m`; D-7 destroyed on deletion, not exported (a judgement about one's own career is the person's even de-identified). **Frontend:** `PathSuggestionCard` (three `data-verdict` buttons, `aria-pressed`, body-as-button opens the fit, controls outside the click region), `PathFitPanel`, `usePathFeedback.ts`, `pathFailure.ts` (`stateForFailure` lifted out of the page — it was module-private there, not in Login.tsx); spinner asserted at 850 ms; optimistic only where honest (dismissed vanishes, interesting stays, never guesses a Rocchio order); every error code branched, non-retryable ones get no retry; the SQL-gap defect is rendered, not hidden. **Contract** 0 diffs / 99 before recapture → 103 (three POSTs pin verdict → code → corpus ordering), openapi +234/−0, `schema.ts` +455/−5 (the F-5 catch-up). **Findings:** (1) the overseer's brief had the radius backwards — cut at the MINIMUM rejected cosine, and liked cards are exempt (the radius was deleting them; caught by the sim test). (2) Sync re-rank is **3 ms** warm; `generate_narratives` is 1.4–1.7 s per card, 6.7 s for ten — the narrator is off the tap path; existing prose carries across, new cards self-describe from `overlapping_skills` (→F-8 if LLM prose on re-ranked cards is wanted, it must be earned off the request path). (3) Cold generation ignored stored judgements — a reload after a deploy silently rebuilt the default list; fixed, `feedback` now travels with the payload. (4) An offline-only sim test could not be built honestly: a fake embedder collapses the query to the bare anchor and produced artefacts; the test uses the real embedder and **skips in CI** (no `OPENAI_API_KEY`). (5) Process trap: **`TaskStop` kills the wrapper shell, not the pytest child** — two pytest processes on one lane DB, the documented concurrent-pytest failure; kill by PID and verify._

### F-7 · `fresh_start` — diverse seed, same loop (M)

- [x] k-means over the corpus (k ≈ 8-10); take the nearest real occupation to
  each centroid as the seed set
- [x] Transferable-skill floor: retrieve on the user's *skills*, constrained to
  a different SOC major group
  _⚑9 (2026-09-16, from F-4's interim `fresh_start`): **major group is too wide — the same defect as the allow-list.** Measured: it put 8 of 11 labelled-relevant occupations out of reach for the admin assistant (SOC 43 is ALL of Office & Administrative Support; Bookkeeping Clerk is a real job change the labels grade primary) and 4 of 11 for the warehouse worker. **Minor group** wins on every metric vs both major group and no filter (nDCG 0.466 → 0.491, harm 0.011 → 0.005). F-4 shipped minor group on evidence and flagged it. Recommend ratify; F-7 builds on whichever Sebastian rules._
- [x] Job Zone feasibility as a **hard filter**, not a weight
- [x] Behavioral profile (`archetype` / `focus_type` / `work_style_tags`) as the
  **primary** query, not a 0.25 side weight

_Shares F-6's machinery entirely — same probe selection, same update rule, a
different initializer. Build them as one implementation with two seeds._

_⚠ This is the **existing** behavioral profile only. The core→8-dimension
culture-preferences mapping is a different thing and stays skipped (⚑3).
Nothing here reopens it._

_⚠ **Never use distance-from-current-job as a positive signal.** "Far from
software engineering" includes Logging Worker. The current code already fell
into this — `_ZONE_DAMPENING_FRESH_START = 0.6` is the patch over it, and
`path_scoring.py:1355` admits every zone+1 role scores identically "regardless
of relevance"._


_2026-09-16: **F-7 landed** (a428da6), 3208 passed / 0 failed; overseer verified hygiene (6 files, no migration, no frontend), re-scored its run (`f7_fresh_start_seed.json`), and confirmed the headline finding structurally. **This chunk's honest result is a negative one:** the design's trajectory claim — feedback recovers more than the diverse seed costs — **does not hold as stated.** Zero-tap `fresh_start` nDCG **0.332 → 0.242** (four profiles: p05 0.100 → 0.000, p07 0.464 → 0.281, p10 0.397 → 0.300, p16 0.368 → 0.387); harm 0 → 0; every page 10 cards; **the 0.090 is entirely the seed** (mix, ceiling and floor each measured at exactly zero). One simulated round of taps recovers to 0.315, two rounds to 0.332 — level with the interim, never above it. It fails on p05 alone, whose page holds no labelled card so no positive tap exists; over the other three the trajectory holds (0.410 → 0.420 → 0.427). Overall macro 0.491 → **0.472**; the other 16 profiles are byte-identical to F-6. What the seed buys: cluster spread **5/4/2/3 → 8/8/8/8**, SOC minor groups 8/7/5/6 → 9/9/10/7. **Shipped:** q0 = normalise(0.4·skills + 0.6·behavioural) (`_FRESH_START_BEHAVIORAL_MIX` 0.30 → 0.60, the design's value — inert at zero taps, and the n=1 post-tap evidence prefers the LOWER value; see ⚑10); zone ceiling `user_zone + 1` capped at 5 (measured cost zero; a safety filter); own SOC **minor** group (⚑9 still open); transferable-skill floor raw cosine **0.25** (zero cost; above it the floor undoes the design — 0.45 collapses spread to 5/5/5/3); **arm (b)** — best q0-ranked survivor per cluster (arm (a) returns 4/4/4/6 cards, a centroid is not a candidate; (a)+fill actually scores 0.263 vs 0.242, rejected for not filling a page, not on score); **k = 8** (k=10/12 each produce a cluster that is nothing but military `55-`, which every ceiling deletes); clusters as a sidecar `*.clusters.json` via `flask corpus clusters`, 0.93 ms load, **scikit-learn never imported on the request path**; F-6's loop reused unchanged (`is_adjacent` → `takes_feedback`); `TestDistanceIsNotASignal` (4 tests, incl. one asserting `occupation_clusters` never sees `anchor`/`UserProfile`/`move_intent`/`current_title`). No wire change. **Findings:** (1) **PRODUCT HAZARD, not a fixture defect:** `archetype_description` is LLM-written per user; p05's says "you would rather *prevent a fire* than be praised for putting one out" and the embedder reads it literally — its five nearest rows are Firefighting Supervisors, Firefighters, Fire-Prevention Engineers, Forest Fire Inspectors, Fire Inspectors; delete the sentence and all five become operations managers. Behavioural cosines also sit at 0.34–0.38 vs 0.52–0.60 for skills — a weaker signal by construction. → **F-8 box 8.** (2) Only **four** `fresh_start` profiles, not five — below F-2's n=5 rule. (3) k-means DID cluster on document length: the All-Other rows formed their own 58-row cluster (38% of variance; 12% once excluded) — fixed by fitting on retrievable rows only. (4) `_fetch_from_s3` pulls the matrix and zones only — on the S3 path every worker would pay a 0.7 s fit and the sklearn import → **F-8 box 9.** (5) `requirements.txt` pins scikit-learn 1.9.0, the verification venv has 1.7.2 — every "CI-parity" run today used a different sklearn than CI will; determinism is version-bound → **F-8 step 0 + box 10.** (6) `role_w` is 0 for `fresh_start`, so Rocchio changes membership but cannot reorder — F-8 optional. (7) F-8's no-code-fallback box is already satisfied by F-4 (p20 scores 0.605) and F-7 (p07 gets the full seed) — F-8 pins it with tests and closes it._

### F-8 · Cleanup + refresh cadence (S)

- [x] `flask corpus build` on a Render cron, matching Scenario A's shape —
  O*NET content changes quarterly
- [x] Test whether the SOC allow-list is still needed once documents replace
  titles; remove only with evidence, never on assumption (design doc §5 #5)
  _(2026-09-16: **the evidence now exists, and it says remove.** F-2's ceiling analysis shows the list bars entire occupational families from the users IN those families (electrician: 0 of 3 primaries reachable). F-1 showed the title-domination failure it patched does not occur with role documents. F-4 must NOT carry `_filter_candidate_pool`'s prefix allow-list into the new retrieval; F-3's named hard filters replace it. This box becomes: confirm with the harness that removal did not reintroduce the original failure.)_
- [x] ~~`_EMBED_CACHE` retires with the funnel~~ **It does not retire** — F-5 and F-6 use it for the user's own texts and both tiers share one object. Its DEMAND fell from 300–700 entries/run to 3–14 (F-4, measured). Re-derive the 32 MB budget from the new demand, fix the module comment and `test_cache_bounds.py`'s narrative; keep it env-overridable; do not delete
- [x] A title that resolves to no O*NET code falls back to F-7's seed rather
  than erroring — the live ACC-4 / S22 failure (design doc §5 #6)
  _(F-7: already handled — F-4's composed-document query covers an unresolvable title (p20 scores 0.605) and a `fresh_start` user with no title (p07) gets the full seed. F-8 pins both with tests and closes this; no new mechanism.)_
- [x] Skill-name normalisation for Tier-2 matching: O*NET's verbose names ("Structured query
  language SQL") must match a user's "SQL" — normalise/alias, do not tune `_EMBED_THRESHOLD`
  blind (from F-5; product-visible in the deep-fit panel)
- [x] `profile_service.set_career_status` invalidates `path_cache` (and `path_fits`) — the one
  profile-write site the enumeration missed; pre-existing (from F-5)
- [x] real_stack E2E flow for Workstream F — needs the corpus artifact reachable on the runner
  (S3 upload + `SOLVERAH_CORPUS_S3_KEY`, or a small committed test artifact)
- [x] **Behavioural-profile metaphor hazard (F-7; HIGH).** `_build_behavioral_profile` embeds
  LLM-written `archetype_description` prose literally — "prevent a fire" → five firefighting
  occupations. Embed a structured/neutralised form (archetype + focus_type + work_style_tags as
  labels, not free prose) or strip figurative sentences; then re-measure the `fresh_start` mix
  (0.60 vs 0.30) rather than flipping it blind
- [x] `occupation_retrieval._fetch_from_s3` must also pull `*.clusters.json` (F-7) — narrow,
  allowed edit to F-3's module; otherwise every worker on the S3 path pays a 0.7 s fit + sklearn
- [x] scikit-learn pin: `requirements.txt` 1.9.0 vs venv 1.7.2 (F-7). Refresh the venv to the
  pins FIRST; record the sklearn version in the clusters sidecar and warn/refit on mismatch
- [x] ~~(optional)~~ **Measured, not built — promoted to F-9 (⚑11):** `role_w` is 0 for `fresh_start`, so Rocchio changes membership but cannot
  reorder a fixed set; a non-zero role weight once feedback exists needs `_weights` to know
  about feedback (F-7) — propose, do not build without a measurement

_2026-09-16: **F-8 landed** — twelve commits 02dd338…e66292e, **3293 passed / 52 skipped / 0 failed** at CI parity on the venv refreshed to the pins; `tsc -b` clean; `npm test` 952/953 (the one a CPU-contention timeout that passes alone). Overseer verified: 26 files, nothing off-limits, no migration, run re-scored (`f8_structured_behavioural.json`, macro **0.473**), venv at sklearn 1.9.0 / numpy 2.4.6. Three `src/` edits were made without being declared — box 5 rewrote `PathFitPanel`'s comment now that the SQL defect is fixed at the source, box 7 added one `data-onet-code` hook so the E2E can address a specific card — both legitimate, both should have been in the report. **Step 0:** F-7's 1.7.2-fitted clusters sidecar reproduces EXACTLY under 1.9.0 (941/941 rows); also moved numpy 2.2.6→2.4.6, openai 3.3.1→3.6.0, gunicorn 26.1→26.2. **Box 8 reverses F-7's negative result:** with structured fields instead of LLM prose, p05's top-5 goes firefighting → production/operations supervisors (zero `33-` rows; a control arm asserts the old composition still retrieves fire), and the fresh_start one-round trajectory reaches **0.354 vs the interim's 0.332** — the design claim holds at n=4; mix 0.60 is now the measured optimum (0.00→0.341, 0.30→0.340, **0.60→0.354**, 1.00→0.315). p05 stays 0.000 at zero taps by label coverage (its page is now sensible but unlabelled) and reaches 0.155 after one round. **Box 3:** 32 MB kept, argument replaced — eviction is FIFO, so the budget is a residency window for the 76-entry shared core (O*NET's ~35 skills + ~41 activities are the same entries for every occupation); ~615 distinct users before the core is evicted; a second user on the same five cards costs +7 then +0. **Box 5:** two narrow rules mined from 176 real technology names — ALL-CAPS last token (SQL, AWS, CSS…) and a vendor prefix by recurrence ≥3 (Microsoft 29, Apache 9…) — because O*NET's generic skills are title-cased two-word phrases exactly like its product names, so a broad rule credits "Design Thinking" with "Critical Thinking"; guards for R/React, R/Ruby, C/C++, SQL/MySQL, Linux/Red-Hat, and an all-pairs check. **Box 7 EXECUTED**, not shelved: real Flask, real Postgres, production bundle, live OpenAI + O*NET — `PUT preferences → POST job → poll → POST feedback ×2 → POST path-fit → DELETE feedback`, every step asserting the DB, 1 passed in 26 s — **against the REAL corpus**, because F-3's committed fixture is 8-dimensional and cannot meet a 1536-dim embedder (still-open #2). **Box 4:** the "unresolvable title" case is not reachable as written — corpus resolution has no floor, an invented title is *answered*; the real fallback is an All-Other residual anchor; two tests saying two true things. **Found and fixed on the way:** `MAX_PROFILE_DROP` 0.15 was passing by 0.0001 (p09 at 0.1499 on HEAD — something between F-6 and F-8 moved it unrecorded); raised to 0.20 with derivation. **render.yaml** now codifies the corpus keys and a quarterly cron (doc-only until Blueprint adoption); `.env.example` gained them. **Still open, F-8's own list:** (1) `path_suggestions` has no `CorpusUnavailable` branch — untyped 500, not the typed 503 the other two routes return → **CLOSED afa0973** (typed 503 mirrors F-4's `profile_incomplete` branch; two regression tests, both stash-proven red on HEAD; runbook paragraph rewritten; the job-status `error` field is free-text `Optional[str]`, so openapi and the contract baseline were correctly left untouched); (2) the 8-dim fixture; (3) `profile_fingerprint` still hashes `archetype_description`, which nothing reads → **CLOSED e066c88** (dropped from the fingerprint; every other `UserProfile` field has a read-site in the deep-fit chain and stays; invalidates all stored fits once — none exist in prod); (4) Tier-2 coverage/centroid ignore the aliases — deliberate, no Tier-2 harness; (5) ⚑9; (6) the first S3 upload — Sebastian's; (7) `role_w` after feedback → ⚑11._

### F · Workstream close-out — CODE COMPLETE 2026-09-16

Green-lit and built in one day. Eight chunks, every one independently verified by the overseer before being recorded (commit hygiene, numbers re-scored, the load-bearing claim checked), all on `causal_bayesian_model`, **nothing pushed, nothing on main.**

**What it does now, end to end.** Retrieval is one dot product over a 6 MB corpus of 1,016 role documents; **zero O*NET calls per request** (was ~160); the deep fit runs on click for one occupation (four O*NET calls, 844 ms common case); three-verdict feedback re-ranks in 3 ms; `fresh_start` seeds a page spanning 8 clusters and its feedback trajectory now holds. The embedding cache's demand fell from 300–700 entries per run to 3–14 — the 2026-09-15 OOM's cause is removed, not capped.

**The numbers, one line.** Harness macro **nDCG@10 0.318 → 0.473**, harmful_rate **0.031 → 0.005**, P@10 0.232 → 0.405, MRR 0.566 → 0.763; two profiles that were HTTP 500s in production (electrician, graphic designer) score 0.416 and 0.808. Suite **2790 → 3296 passed**, 0 failed, at CI parity on a venv now at the pins. Every wire change captured additively (contract 97 → 103 responses, re-verified at 0 diffs before each recapture). Two design recommendations failed measurement and were retracted at the source: MMR (§3.2) and, briefly, the fresh_start trajectory (§3.3) — the latter reversed once the LLM prose left the behavioural document.

**Decided along the way:** ⚑7 inline feedback, ⚑8 substantial rewrite (Sebastian). **Open rulings:** ⚑9 minor-vs-major group (recommend ratify), ⚑10 ship the diverse seed (evidence now says the claim holds — recommend ship), ⚑11 build F-9 (recommend yes, as a re-measurable chunk). **Open for Sebastian, not rulings:** regrade p01–p04 own-job labels to `anchor`; the 56 low-confidence labels (`p05` first); the first corpus upload + `SOLVERAH_CORPUS_S3_KEY` — **a deploy dependency, see `RUNBOOK_DEPLOY_MAIN_MERGE.md`**; push the branch so CI sees it.

**Still open in the code, honestly:** F-8's seven (its landing note) — **#1 and #3 CLOSED** by the follow-up (afa0973, e066c88; suite 3296 / 0); #2 (an 8-dim fixture that cannot meet a real embedder — regenerate at 1536 and rewrite F-3's hand-written vector assertions) and #4 (Tier-2 coverage ignoring the aliases; no Tier-2 harness to tune against) are their own small chunks; #7 is F-9. Two stale docstrings the follow-up could not touch (file ownership): `score_paths` still says the caller answers 500 for a missing corpus (it is 503 now), and `get_my_path_suggestion_job` lists the known job errors without `corpus_unavailable` — two comment edits, fold into F-9 or the fixture chunk.

**Proposed, not scheduled — F-9 · `role_w` after feedback (S–M).** F-8 measured applying a role weight only once feedback exists: 0 → 0.354, 0.10 → 0.383, **0.20 → 0.414**, 0.30 → 0.389 — a clean inverted U, harm 0.000 throughout, p16 +0.20. n=4, so F-2's rule forbids a per-axis reading; ship 0.20 in a chunk that re-measures on the full harness, not slipped into F-8.

**Deferred by ruling, not forgotten:** per-click LLM narrative (`narrative: null` on the wire, shape ready; and the cold first page still waits 1.4–6.7 s on it); Celery worker service; Blueprint adoption; async narration for re-ranked cards.

---

## 6a. Workstream W — Path Intelligence: what should change (the wants layer)  *(direction approved 2026-09-17; W-1 ungated, everything after it gated on W-3)*

Design of record: `docs/PATH_INTELLIGENCE_REDESIGN.md` **§8**. Sebastian ran
Workstream F locally on 2026-09-17 and redirected it: **no percentage** (⚑12),
and find out **what is going wrong in the user's current job, work-wise** —
people-facing or not, likes coding or not, likes selling or not — then steer all
three paths with it, **kept separate from the company model** (⚑13).

What two scratch looks showed (§8.2; looks, not measurements): marking *more /
less* on the user's **own job's O*NET tasks** — already in the corpus documents —
rotates the query the way F-6's taps do and steered a developer persona well
(Data Scientists 1st → gone, Sales Engineers 4th → 1st). Measured work
**conditions** (O*NET work context, fetched for all 939 retrievable jobs) are a
clear win for a nurse persona and too blunt to rank on alone.

**The order is the point.** W-1 ships regardless. W-2 and W-3 put the idea in the
harness **before any form, table or card work exists. If W-3's number does not
hold, the workstream stops there.** Two confident design claims in Workstream F
failed measurement; this is a hypothesis.

_Letter W, not G: `G1`…`G22` are scenario-gap ids in `USER_SCENARIOS.md`._

### W-1 · Remove the percentage (S) — frontend only, no gate

- [x] `PathSuggestionCard.tsx`: drop "Match score NN%" and its bar. Card order
  is unchanged — the ranking stays, only its display goes
- [x] `PathFitPanel.tsx`: drop the four percent bars (`fit_score`,
  `skills_score`, `coverage_score`, `work_style_score`) and the number on each
  skill gap. Keep the panel **as words**: what carries over, what would be new;
  gaps stay ordered by importance, unnumbered
- [x] Wire untouched: `match_score` and the four fit scores stay on the response
  and in `types.ts` — **no OpenAPI change, no contract recapture**
- [x] Tests beside each component: assert no `%` and no score bar renders;
  `npm test`, `npm run type-check`

_Copy is a best guess; Julie revises on the built product._

_**W-1 landed** (built 2026-09-17, committed 2026-09-21 as 8d35fb2). Four files, all under `src/features/intelligence/components/`; wire, `types.ts`, OpenAPI and contract untouched; Vitest 953/953, `tsc -b` clean. **One overseer correction on the way:** the agent first replaced the four percent bars with graded words — "Strong / Good / Some / Little overlap". That is a percentage in words ("Overall: Little overlap" is exactly the verdict ⚑12 removes), so the whole "Overall fit" section went instead; the panel opens on the training line, then skills you already have, worth picking up (unnumbered, API order), what you'd be doing, tools people use. The tests assert no `%`, no bar and none of the band words. **Found, not touched:** `src/features/matching/components/Feed.tsx` and `SearchResults.tsx` also render "Match score: NN%" — a different feature (job matching), put to Sebastian._

### W-2 · Eval profiles that state wants (M) — BEFORE any scorer

- [x] Extend the fixture schema **additively**: an optional `wants` block per
  profile — `tasks_more` / `tasks_less` (the anchor occupation's real task
  statements from `*.documents.jsonl`, by exact text) and `conditions`
  (`people` / `public` / `leading` / `desk` → more | less)
- [x] **15 new profiles, five per intent**, so every intent clears the n = 5
  rule. Varied domains and Job Zones; at least three whose wants pull *against*
  their skills (the developer who is done with coding)
- [x] Labels by F-2's protocol: drafted by an agent that **has seen no scorer and
  none of §8.2's prototype output**, graded *with the stated wants in mind*,
  `confidence` flagged, low-confidence rows reviewed by Sebastian. Codes
  validated against the corpus sidecar, not live O*NET
- [x] `EvalProfile` gains the optional field; every existing scorer still runs
- [x] **Record the number to beat:** today's wants-blind `score_paths` on the 15
  new profiles. The existing 20 profiles and their 249 labels are **frozen** —
  they become the no-wants regression guard

_⚠ Same two warnings as F-2: this is a scorer-quality baseline, not a pytest
baseline; and the labelled set must not become a Julie dependency._

_**W-2 landed** (built 2026-09-17, committed 2026-09-21 as 1a40d75). `p21`–`p35`, five per intent, six with wants opposed to their skills; Job Zones 2/3/4, twelve domains. `wants` sits **beside** `profile` in the fixture, so it structurally cannot reach `UserProfile`. 201 labels (46 primary / 98 acceptable / 42 harmful / 15 anchor), **76 low-confidence for Sebastian** (`python -m backend.services.path_eval review`); the harmful rows are mostly *excellent skills matches that repeat the problem* (Web Developers for the developer done with code, Orderlies for the CNA with a failing back). The labelling agent states it never opened the design doc, the prototype folder or `runs/`, and ran no scorer. **Overseer verified against git HEAD and the corpus, not the agent's own hash:** the F-2 twenty and their 249 labels identical; all 106 wants tasks are exact corpus task statements of the stated anchor; every label code in the corpus with a Job Zone, none "All Other"; `test_path_eval.py` 49 passed. **One defect fixed:** p26's title "Full Stack Developer" resolved to Web Developers (15-1254.00) while its wants quote Software Developers' tasks — retitled; all 15 now resolve to their stated anchor. That check needs a live embedder, so no CI test can hold it: re-run it whenever a wants profile is added. **THE NUMBER TO BEAT** (`runs/w2_wants_blind_baseline.json`, `score_paths@HEAD`, wants ignored, n=15): **nDCG@10 0.300 · harmful_rate 0.100 · P@10 0.280 · MRR 0.560** — against 0.473 / 0.005 on the old twenty, and a harmful card on 12 of 15 profiles. Today's scorer is clearly worse once people say what they want, which is the gap ⚑13 aims at. **Open for Sebastian:** p32 carries two `primary` labels at Job Zone 4 against a Zone 2 anchor — unreachable under F-7's zone+1 ceiling, so no scorer can earn them; either the labels drop to acceptable or the ceiling is too tight._

_2026-09-21: **W-3 split by the overseer.** **W-3a** (dispatched) is the gate alone: the conditions sidecar from the already-fetched ratings, the scorer, the measurement and the STOP rule. **W-3b** — the tasks sidecar with plain-words labels, `_fetch_from_s3`, the runbook's deploy dependency — is built only if W-3a passes, so a negative result wastes none of it. The boxes below are unchanged; the split is only the order._

### W-3 · Sidecars + the scorer, measured offline (M–L) — THE GATE

- [x] **Conditions sidecar** `*.experience.json` beside the corpus:
  `flask corpus experience` builds it (three `details/` reports per job, 4 req/s,
  resumable; accepts the already-fetched
  `Desktop/solverah-experience-proto/onet_experience_raw.jsonl` so nothing is
  re-fetched). Two new `onet_client` methods. Axes are **percentile ranks across
  the corpus**; an axis averages the elements *present* — a missing element is
  never a zero
- [x] **Tasks sidecar** `*.tasks.json`: per job, up to ~8 task statements chosen
  for spread, each with a plain-words display label written **once, offline**.
  The **original** statement is what gets embedded — display prose never reaches
  the embedder (F-7's metaphor hazard)
- [x] Task vectors are embedded **per request for the tapped tasks only**, in the
  one batched call `score_paths` already makes, cached in `_EMBED_CACHE`. _Not_
  precomputed: every task of every job is ~120 MB at float32 and the instance is
  512 MB
- [x] Scorer, in the harness first: query rotation
  `q' = q + beta*mean(more) - gamma*mean(less)` on each intent's existing query;
  conditions as a **one-sided** term blended into the rank; F-7's hard filters
  unchanged
- [x] **Measured arms, one table:** tasks only · conditions only · both; beta and
  gamma (watch gamma subtracting the anchor — F-6's finding); conditions weight;
  **diverse seed vs none with wants present (this settles ⚑10)**; `role_w` after
  feedback (**this settles ⚑11**; no standalone F-9)
- [x] **Gates:** with no wants, all 20 existing profiles **byte-identical** to
  `f8_structured_behavioural.json`; harmful rate does not rise anywhere; tune on
  nDCG@10; no per-axis claim under n = 5
- [x] **STOP RULE.** If the wants-aware scorer does not clearly beat W-2's
  wants-blind number on the new profiles, stop, write the negative result here
  and in design doc §8, and do not start W-4
- [x] Request path stays clean: no O*NET call, no scikit-learn, no corpus load in
  `create_app()`; `_fetch_from_s3` pulls both new sidecars; both join the deploy
  dependency in `RUNBOOK_DEPLOY_MAIN_MERGE.md`. **No real S3** — the upload is
  Sebastian's trigger

_2026-09-21: **W-3a landed — THE GATE PASSES.** Overseer reproduced every headline number live rather than re-reading the agent's: re-scored `runs/w3_wants_aware.json`, **re-recorded the wants-aware run (15/15 ranked lists identical to the agent's), re-recorded the new fifteen wants-blind on the new code (15/15 identical to W-2's baseline), re-recorded the old twenty with no wants (20/20 identical to `f8_structured_behavioural.json`, macro 0.473 / harm 0.005 unchanged)**; touched test files 540 passed / 43 skipped at CI parity on lane DB `solverah_w2`; nothing outside the chunk's ownership list touched; no label, profile or metric edited; the scorer diff reads no fixture. **Wants-aware vs wants-blind on the fifteen: nDCG@10 0.300 → 0.409 (+36%), harmful_rate 0.100 → 0.080, P@10 0.280 → 0.307, MRR 0.560 → 0.700.** Arms: tasks only 0.330 · conditions only 0.365 · **both 0.409** — the two signals stack, and on this set conditions carry more than §8.2's single-persona look suggested. Per intent (n=5, "clearly better" only): `stay_in_field` 0.279 → 0.427, `adjacent` 0.383 → 0.516, `fresh_start` 0.237 → 0.283. **12 profiles improve, 0 level, 3 worsen** (p23 head chef 0.047 → 0.000, p31 truck driver 0.510 → 0.429, p33 helpdesk 0.332 → 0.318); largest gains p26 developer-done-with-code 0.209 → 0.647 and p24 teacher 0.192 → 0.540. **Not a peak-chase:** nine grid cells at conditions weight 0.2 with beta > 0 sit on a 0.383–0.409 plateau; leave-one-intent-out picks the *same* cell on all three training splits and every held-out five beats its own wants-blind number. **Shipped:** `_WANTS_TASK_BETA 0.80`, `_WANTS_TASK_GAMMA 0.40`, `_WANTS_CONDITIONS_W 0.20`, `_WANTS_CONDITION_SHIFT 0.40`, `_WANTS_FRESH_START_ROLE_W 0.20` (only when tasks are stated); the whole table is in `path_scoring.py` beside them. **F-6's hazard is real and measured:** gamma subtracts the anchor on `stay_in_field` (0.427 at 0.4 → 0.368 at 1.2) while `adjacent` keeps rising — hence one low shared gamma. `score_paths(..., wants=None)`: `Wants` dataclass, empty == absent, unknown axis ignored, missing sidecar = degrade + one warning, conditions never read when nothing is stated. New: `occupation_conditions.py`, `flask corpus experience` (`--from-raw` built the real file; the live-fetch path is mock-tested only), three `onet_client` rating methods, `record-live --wants`. The sidecar `onet_corpus_20260916.experience.json` (334 KB, 911 occupations, seven axes as corpus percentiles) was **added** beside the corpus; no existing artifact file changed. Zero O*NET calls, embeddings under a cent._

_**⚑10, priced with wants present — it costs MORE, not less:** on the five `fresh_start` profiles the diverse seed scores 0.283 against 0.385 for a plain best-N page (0.237 vs 0.297 with no wants), harm 0.040 either way; dropping it would move the fifteen-profile headline 0.409 → 0.443. The better the ordering gets, the more one-card-per-region throws away. The agent left the seed in — it is Sebastian's ruling, and the spread argument (8 of 8 regions vs 2) is a product judgement labels cannot settle. **Overseer recommendation changes to: drop the seed once a user has stated wants; keep it for a `fresh_start` user who has stated nothing.** **⚑11 re-measured and folded in:** `role_w` 0.20 after one simulated round of taps lifts the ten feedback-taking profiles 0.474 → 0.515 on top of the wants scorer (0.400 at zero taps), harm 0.060 → 0.020 — wants and taps stack; no standalone F-9._

_**Carried to W-3b / W-7, not done here by design:** the tasks sidecar and plain-words labels; `_fetch_from_s3` does not pull `*.experience.json` (pinned by a test that names the file, so a production worker degrades silently until W-7 flips it); 28 of 939 retrievable jobs have no work-context report (skipped, never penalised; 84 O*NET calls would fill them); `pace` is built and unused; `test_cache_bounds.py` needs the conditions memo added as a fifth ~0.3 MB entry, and a wants request roughly doubles a user's `_EMBED_CACHE` demand (~8 → ~16 entries, residency window ~615 → ~315 users). **Dev tool:** `Desktop/solverah-experience-proto/lab/` (outside the repo, http://127.0.0.1:5077) shows backend-today, backend-with-wants and a slider formula side by side, with per-card reasons and a "why not this job" lookup; its wants column was checked identical to the harness run._

_2026-09-21: **W-3b landed — W-3 is complete.** Overseer re-recorded all three runs live: **wants-aware 15/15 ranked lists identical to `runs/w3b_wants_no_seed.json`; old twenty with no wants 20/20 identical to `f8_structured_behavioural.json`** (the seed is still there for them); wants-blind fifteen 14/15 identical to W-2's baseline on the first pass and 15/15 on four re-runs — **the one miss was embedding jitter, not code:** OpenAI returned vectors differing in the fourth decimal and two `fresh_start` cards 0.0004 apart swapped inside one cluster (p34, rank 6). **Harness caveat worth keeping: an "identical ranked lists" guard over a live embedder can flake on a near-tie; re-run before believing a single miss.** Touched test files 706 passed / 49 skipped at CI parity (lane DB `solverah_w2`); the corpus folder gained exactly one file, the six existing artifacts untouched by size and timestamp. **⚑10 built** (one condition in `score_paths`: the zero-tap `fresh_start` page is the cluster-spanning seed only while wants are empty): **headline nDCG@10 0.409 → 0.444, harm 0.080 unchanged, P@10 0.307 → 0.360**; `fresh_start` 0.283 → 0.389, the other two intents byte-identical to W-3a. Against the wants-blind 0.300 that is **+48%**. **Tasks sidecar** `onet_corpus_20260916.tasks.json`: 941 occupations, 7,373 tasks, up to 8 per job chosen by greedy farthest-point over the task embeddings (seeded with O*NET's first statement, deterministic), each with the byte-exact original statement and a plain-words label from one offline `gpt-4o-mini` pass — **0 fallbacks, 0 duplicate labels within a job, every `task` verified by the overseer as an exact corpus statement, labels 2–10 words**; 18 military occupations have no task statements and carry empty lists. **Spend: $0.09 of completions + $0.02 of embeddings** (the 25-job gate projected $0.091). `flask corpus tasks` (`--no-labels` costs nothing and is what tests use), `occupation_tasks.py` with a lazy memo. **Production loading:** `_fetch_from_s3` pulls `*.experience.json` and `*.tasks.json` (missing object = degrade; W-3a's pinning test flipped); `corpus publish` carries them as an OPTIONAL tier — not required, because `corpus refresh` builds neither and a hard requirement would stop the quarterly cadence publishing at all; the runbook's corpus dependency is now **six objects, not four**, with a per-file degrade table. Mock S3 only. `test_cache_bounds.py` gains both memos at measured resident sizes — conditions **0.90 MB** (W-3a's note guessed 0.3 from the file size), tasks **2.59 MB** — and the corrected narrative: a wants request takes a user's `_EMBED_CACHE` demand 8.3 → 16.6 entries, residency window ~617 → ~308 users. One file outside the agent's ownership list was edited and flagged, correctly: `occupation_corpus.py`, where publish enumerates sidecars._

_**The panel can say less than the harness assumed — measured by the overseer, not assumed away.** The W-2 profiles quote tasks from each job's FULL O*NET list (up to 30); the panel offers eight. Only **46 of the 106** quoted statements are among the offered eight. Re-scoring the fifteen with wants restricted to what a panel user could actually mark: **nDCG@10 0.399, harm 0.067** (against 0.444 / 0.080 with the full wants, 0.300 / 0.100 wants-blind). So the honest expectation for the shipped panel is **about 0.40, not 0.44** — still a third better than today, with less harm. It is also a pessimistic reading: a real user marks other offered tasks instead of nothing. Raising the panel to twelve tasks would close some of the gap at the cost of a longer screen; left at eight, revisit with real usage. **Not re-swept on purpose:** `_WANTS_FRESH_START_ROLE_W` 0.20 was tuned with the seed in; re-picking it on the same fifteen profiles the seed decision was taken on would be fitting twice to one set._

### W-4 · Storage + API (M) — only after W-3 passes

- [x] `path_wants` table: `(user_id, anchor_onet_code, kind task|condition,
  item_key, verdict more|less)`, unique per user + anchor + item. **One alembic
  head.** A change of current job leaves the old rows inert, not deleted
- [x] `GET /me/path-wants` — the panel's content for the user's resolved
  occupation plus their current answers; a typed `no_anchor` when there is no
  current job. `PUT /me/path-wants` — idempotent, partial answers valid. Rate
  limited like `path-feedback`
- [x] A wants write invalidates `path_cache` and `path_fits` (the enumeration
  test's floor rises by one)
- [x] `score_paths` reads stored wants for **all three** intents;
  `stay_in_field` still ignores *card* feedback, as F-6 decided
- [x] Cards gain an additive `reasons: string[]` — what is **distinctive about
  this card**, never a line that reads the same on every card (§8.2)
- [x] Export + delete coverage for the new table (D-7's rule,
  `test_export_delete_coverage.py`); the D-01 guard reads docstrings — name no
  person-side table in prose
- [x] pytest per endpoint (happy / error / edge), OpenAPI regen, contract
  **re-verified at zero diffs, then** captured additively, `schema.ts` regen

_2026-09-21: **W-4 landed.** Overseer verified rather than re-read: nothing outside the ownership list touched and no git writes; **one alembic head** (`20260921_path_wants`, down_revision `20260916_path_fb`, 20 characters) checked on the alembic lane DB, where the agent ran empty → head → down one → head; **every wire file is additive by numstat** — `contract_baseline.json` +72/−0, `openapi.json` +330/−0, `schema.ts` +280/−0; the agent's contract check read **0 differences across 103 responses BEFORE any wire change**, then 8 additive steps (baseline 111, re-verified at 0); test files and guards **675 passed / 42 skipped** at CI parity on the overseer's own run (employer-visibility, layering, export/delete, frontend-contract, migrations-chain and cache-bounds guards included), 339 / 38 again after the follow-up; `tsc -b` clean. **Rankings unmoved:** all 35 profiles re-recorded on the W-4 tree — old twenty 20/20 identical to F-8, wants fifteen 14/15 identical to W-3b; the one miss (p30, ranks 9/10) is a TRUE TIE, 0.5541 vs 0.5540 on the same ten cards, persistent across re-runs — the second sighting of the near-tie flake W-3b recorded, not a scoring change. **Built:** `path_wants` (user, anchor occupation, kind task|condition, `item_key`, `item_text`, verdict more|less; unique per user + anchor + item; "fine" is the absence of a row; a job change leaves old rows inert, not deleted). A task's key is `t_` + 12 hex of sha256 over the normalised ORIGINAL O*NET statement and the row stores that statement, so an answer survives a quarterly sidecar rebuild and a relabel, and the display label never reaches the embedder. `GET /api/v1/me/path-wants` → `status` ok | `no_anchor` | `unavailable` (the status describes the TASK half: an axis is a name in code and needs no sidecar, so the four conditions stay answerable), anchor, up to 8 tasks `{key, label, verdict}`, four conditions; `PUT` takes `{answers:[{kind,key,verdict|null}]}`, partial answers valid, `null` clears, validated whole before any write — unknown or foreign key → RFC 9457 **422 `not_offered`, nothing written**; both methods share a 20/min bucket; corpus down → the sibling routes' typed 503. **Wants reach `score_paths` at both sites** in `intelligence_service.py` — `path_suggestions` (the cold job) and `_rescore` (the tap re-rank) — for all three intents; `wants_for_scoring` checks `any_for_user` FIRST, so a user who never opened the panel pays no anchor resolution, no embedding and no sidecar read and gets `wants=None` (asserted). Invalidation floor **7 → 8**. **Deleted with the account, not exported** — `path_feedback`'s answer: "I want less of this part of my job" is a statement a person made about their working life, and everything they said is on the panel they said it on with the control that clears it. New: `path_wants_service.py`, `path_wants_repository.py`, `tests/test_path_wants_api.py` (57 tests); a public `resolve_anchor_code()` in `path_scoring.py` so the panel resolves the SAME anchor the scorer does instead of reaching into an underscore name — it also answers `no_anchor` before `get_corpus()`, so a first-job user is not shown a 503 during an S3 outage._

_**Card `reasons: string[]` — additive, deterministic, conditions sidecar only, no LLM, no embeddings, at most two.** Three tiers: a stated axis at the far end in ABSOLUTE terms (percentile ≥ 0.80 for "more", ≤ 0.20 for "less": "Among the most people-facing jobs", "Very little dealing with the public"), then a stated axis compared with the user's own job (margin 0.25), then an unstated axis; every phrase passes the **distinctiveness rule** — a phrase on ≥ 70% of the page's cards is dropped from all of them. §8.2's hazard, caught live: for a developer who stated `people: more`, "More time with people than your current job" was true of 8 of 10 cards and vanished everywhere. **The strong tier is the overseer's follow-up**, because that rule alone meant the axis the user ASKED about could never speak; now Sales Representatives (people 0.81) says "Among the most people-facing jobs". **The agent corrected the overseer's premise and was right:** the overseer named Sales Engineers as the wrongly silent card; Sales Engineers sit at `people` 0.51 — the median — and stay silent correctly. The strong tier deliberately ignores the 0.25 margin (an absolute claim is not about the anchor; a user already at 0.95 asking for more would otherwise be told nothing about a card at 0.97) and still goes through the ubiquity count as its own phrase. **Reasons are built only when wants are stated** — W-3 pins that a user who stated nothing never touches the conditions sidecar, so their cards carry `[]` and keep the existing why-text; Sebastian told, recommendation is to leave it. `reasons` is on `PathSuggestion` in `openapi.json` and pinned by tests, but NOT in the contract baseline: suggestions are captured on a cache miss by design. The panel asks 4 of the 7 measured axes; reasons draw on 6 (`pace` excluded everywhere). Lane DBs `solverah_w4` / `_w4m` / `_w4c`. All copy is a best guess for Julie._

### W-5 · Frontend: the panel + card reasons (M–L)

- [x] A "what should change" panel above the results: own-job tasks in plain
  words plus the conditions, each *more · fine · less*. **Never blocks the first
  result** — the page loads ranked as today and re-ranks on answer (⚑7's lesson).
  One screen, skippable, valid half-finished
- [x] No current job → no panel; taps only
- [x] Reason line on each card, where the percentage used to be
- [ ] Props typed, test beside each component, Vitest; verify in the browser
  against the API on **5055** (a stale Flask holds :5000)

_2026-09-21: **W-5 landed (code); Sebastian's browser click-through is the open box.** Overseer's own run: Vitest **984 / 984** (85 files), `tsc -b` clean, `npm run build` clean (the panel ships in the lazy `PathIntelligencePage` chunk, 29.9 kB / 8.8 kB gzip, not the entry), `tests/test_frontend_contract.py` 6 passed (the agent had read it but not run it); only `src/features/intelligence/` touched, no new dependency, no new route; a grep of the new files finds no `%`, bar, score or graded word — W-1's assertions are re-asserted with reasons present. **Built:** `usePathWants.ts` + `PathWantsPanel.tsx` (tests beside each), the reason line on `PathSuggestionCard`, `isStalePanel` / `pathWantsMessage` in `pathFailure.ts`. **The panel never stands between the user and a result:** it is fetched in parallel and awaited by nothing; while loading, or if its GET fails for any reason, it renders NOTHING — no error, no empty box. `no_anchor` renders nothing; `unavailable` renders the four conditions only, no apology. Collapsed by default to one row ("Tell us what should change about your job, and we'll re-sort these", plus "N things you want to change" once answers exist); expanded: "About your work: Software Developers" (a colon, because O*NET titles are plural and no article reads right), tasks under "What you spend your time on", conditions under "How you work", each a real `fieldset` radio group — Less of this · Fine as it is · More of this — "fine" pre-selected and meaning no answer. **Edits are local; one `PUT` with only the changed rows goes out on "Update my suggestions"** (a scoring job takes seconds, so nothing re-scores per click); "Clear my answers" sends nulls through the same path. **No second job flow:** the save's `onSuccess` writes the returned panel into the query cache (no second GET), invalidates the suggestion-job keys, and the page answers with its own existing `fetchSuggestions()` — the same enqueue-and-poll it runs for a cache miss. 422 `not_offered` is branched on by CODE: draft discarded, panel reloaded against the new job, plain message; nothing was written, so it is not retried. Card reasons: a quiet list of at most two lines where the percentage used to be; `[]` or absent renders nothing at all. 27 ESLint warnings in the feature, none in new files or changed lines. One trap found and defused: the page test's `cardTitles()` helper matched the panel heading's classes, including while collapsed; the heading is `text-base` with a comment saying why. Copy is a best guess for Julie._

_**Click-through prerequisites (Sebastian):** `flask db upgrade` for `20260921_path_wants` or both panel calls 500; `SOLVERAH_CORPUS_PATH` at `Desktop/solverah-corpus/` with `*.tasks.json` and `*.experience.json` present; API on 5055 with `VITE_API_URL`; a signed-in user WITH a current job title. Reasons appear on cards only after wants are saved._

### W-6 · Taps teach the wants (M) — measured, optional

- [x] ~~A run of *interesting* cards~~ **measured, not built** -- a run of *interesting* cards is evidence about a condition the user never
  answered: infer a nudge from the liked cards' measured axes
- [x] Measure in F-6's simulated-feedback harness against taps alone; **ship only
  if it wins**, harm 0. Otherwise record the number and close the box unbuilt

_2026-09-21: **W-6 measured and CLOSED UNBUILT — it does not win as specified.** Run as a measurement only, in scratch outside the repo (`Temp/claude/w6/`, harness + every cell's per-profile nDCG kept in `refine.json`), so nothing in the tree moved while Sebastian clicked through W-5; `git status` identical before and after; embeddings under a cent, zero O*NET, zero LLM. **Rule tested:** for each panel axis the user did NOT state, if every card tapped *interesting* sits on the same side of the user's own job by a margin, treat it as an inferred more/less at reduced weight through the SAME one-sided conditions term; a stated axis always wins and is never diluted. F-6's simulation protocol reused exactly; **control arm reproduces W-3a's printed 0.3997 / 0.5148 to four decimals.** **Pooled, it looks like a win:** wants-stating tappers +0.013 (one round) / +0.019 (two); users who state nothing +0.016 / +0.027; harm never up; a flat plateau (margin 0.00–0.10 × weight 0.35–0.50) positive in all 16 cell×arm combinations; and a **placebo arm inferring the OPPOSITE direction is strongly, monotonically negative (down to −0.148)** — so the direction carries real information, not just an extra term. **It fails the leave-one-intent-out check, which is what that check is for:** the whole gain is `fresh_start` (+0.024 to +0.080); on `adjacent` — the majority of both populations — it is zero at one round and **negative at two (−0.042)**; constants chosen on one intent do not transfer to the other. Pooled by intent, leave-one-profile-out over the plateau: `fresh_start` +0.029 / +0.046, `adjacent` −0.007 / −0.033. **Mechanism that fits:** `adjacent` already carries a tap's direction in the Rocchio rotation under a large role weight, so the measured conditions add nothing the embedding did not have; `fresh_start` has a huge tightly-bunched pool and little anchor ordering, so a conditions term has room to reorder. **Taps do carry condition information the rotation misses, but only where the rotation is weak.** Not built, because the `fresh_start`-only scoping was chosen AFTER seeing the split, on the same nine profiles that produced it (two of which get no inference at all). If revisited: `fresh_start` only, one agreeing like, margin 0.10, inferred weight 0.5 × `_WANTS_CONDITIONS_W`, four panel axes — and new `fresh_start` profiles FIRST. One caveat that applies to every tap number in this plan: the simulated *interesting* tap is chosen by the label grade, so the liked card is by construction a good one; absolute tap effects are upper bounds._

### W-7 · Close-out (S)

- [x] real_stack E2E: wants → re-ranked page → tap → fit panel, asserting the DB
- [x] `feature_tour` ROUTES, runbook (two new sidecars in the corpus dependency),
  `render.yaml` / `.env.example` if a key is added
- [x] Fold in F's two stale docstrings (`score_paths` says 500;
  `get_my_path_suggestion_job` omits `corpus_unavailable`)
- [ ] **One** full CI-parity suite run, backgrounded:
  `SOLVERAH_IGNORE_DOTENV=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, the venv at
  `Desktop/solverah-venv311`; `npm test`; `tsc`

_2026-09-21: **W-7 landed.** **Real-stack E2E EXECUTED, not shelved:** new `tests/e2e/path_wants.spec.ts` beside F's flow — real Flask, real Postgres migrated by `flask db upgrade` from empty (so `20260921_path_wants` is exercised), the production bundle under `vite preview`, live OpenAI, the REAL corpus with both new sidecars, live O*NET on the deep fit, no API stub anywhere — **1 passed in 48.9 s, and again in 46.5 s with byte-identical output.** It asserts the DATABASE at every step: the suggestion list is reached with the panel untouched and collapsed (the panel gates nothing) and carries **zero** reason lines before any wants exist (W-3's pin, seen end to end); three radio clicks write **no** `path_wants` row and send **no** `PUT` (W-5's one-save rule); "Update my suggestions" sends exactly one `PUT 200`, leaves three rows (`task|less`, `task|more`, `condition|more`) on one anchor (`15-1252.00`), whose `item_text` is **byte-equal to the sidecar's ORIGINAL O*NET statement and not the label shown**, and strictly increases `scoring_jobs`; `reasons` is an array on every card and **9 of 10 cards rendered a reason line** ("More dealing with the public" on Sales Engineers; "More leading other people" on Computer and Information Systems Managers); an *interesting* tap writes `path_feedback` and leaves the three wants in place (the `_rescore` site keeps them); the deep-fit dialog opens with **no `%` anywhere in `document.body`**; a reload brings the radios back selected and "3 things you want to change"; "Clear my answers" returns `path_wants` to zero rows and the reason lines to zero. **No defect found in W-3 / W-4 / W-5 code.** One lesson recorded in the spec and the e2e README: a Playwright click returns before React re-renders, so a "has it finished?" check passes against the pre-click DOM — gate on the save button's `aria-busy` going true → false. It used its own ports (5066 / 4188) and lane DBs (`solverah_w7` alembic-only, `_w7t`, `_w7c`), stopped every process by PID, and left 5055 / 5077 / 5173 — Sebastian's click-through — untouched. **Docstrings:** `score_paths` now says every caller answers a typed `503 corpus_unavailable` (it said 500); `get_my_path_suggestion_job` lists `corpus_unavailable`. The route docstring feeds OpenAPI, so `openapi.json` and `schema.ts` moved by that one description string; **contract re-verified at 0 differences across 111 responses.** **Runbook:** it named the two sidecars but not the migration — one subsection added: confirm `20260921_path_wants` in the pre-deploy log, because without the table both panel calls 500 and the panel's GET failing is SILENT by design, so a missed migration looks like "the feature did not ship". `feature_tour` ROUTES, `render.yaml` and `.env.example` need nothing (no new route, no new env key; confirmed by grep). **Found outside W, not fixed:** `profile_skills.proficiency` has no constraint, and a value outside {1, 3, 5} written straight to the column makes `GET /me/profile` raise a bare `KeyError` at `solverah/domain/profile_document.py:613` → untyped 500 → the SPA's route error boundary; the API validates, so it is only reachable by a direct write._

### W-8 · Task wants reach the rank (S–M) — from Sebastian's first click-through

- [x] Reproduce the founder's case term by term before changing anything
- [x] A task-affinity term of its own in the rank, measured against W-3b
- [x] A behavioural acceptance test as well as nDCG — a tie is not a demotion
- [x] Guards: `wants=None` identical; old twenty identical; wants-blind fifteen identical

_2026-09-21: **W-8 landed — a defect found by a person, not the harness.** Sebastian's first browser click-through: a Software Developer on `adjacent` marks LESS "Fixing software issues", MORE "Evaluating user needs for software", people: more — and **Computer Programmers is still the first card.** "It did not drop the weights of them correctly." Reproduced by the overseer on his real account, per term: the scorer HAD reacted — Programmers fell 0.717 → 0.678 — but into a **three-way tie spanning 0.003** (0.6801 / 0.6780 / 0.6772) that live-embedding jitter orders; he saw it first, the overseer's run saw it second. **Cause:** W-3a let the task wants act only through the query rotation, i.e. only through the `role` term (weight 0.45), and a rotated query lowers EVERY card's role cosine together (0.835 → 0.604, 0.627 → 0.516), so the spread it makes is small; `coverage` — the user's skills against the job, weight 0.33 — is untouched by wants and still favours the coding jobs; `zone` is a constant 0.22 on that page. The card most similar to the disliked task (raw cosine 0.399, the highest on the page) had nothing in the rank saying so. nDCG could not see this: a tie among three acceptable cards scores the same either way. **Fix:** per candidate, the cosine of its corpus document to the mean MORE and mean LESS vectors, each **rank-transformed to a percentile within the retrieved pool** (raw cosines of a short statement against a long document are compressed into ~0.25–0.42 and their position depends on how wordy the sentence is, not on fit — W-3a's lesson about raw O*NET ratings, again), `0.5 + 0.5·(pct_more − pct_less)`, neutral 0.5, blended over the conditions blend exactly as that is blended over the base. **One constant, `_WANTS_TASK_AFFINITY_W = 0.10`. Zero extra embedding calls, zero O*NET, two matrix products over rows already retrieved.** **Measured (overseer re-recorded all 35 live: fifteen 15/15 identical to `runs/w8_task_affinity.json`, old twenty 20/20 identical to F-8, wants-blind fifteen 15/15 identical to W-2; touched tests 417 passed / 42 skipped at CI parity): nDCG@10 0.444 → 0.464, harmful_rate 0.080 → 0.060; panel-reachable 0.399 → 0.411, harm 0.067 → 0.060** — against wants-blind 0.300 / 0.100 that is now +55%. Per intent: `adjacent` 0.516 → 0.551, `fresh_start` 0.389 → 0.422, `stay_in_field` 0.427 → 0.412 (one profile); 9 improve / 2 level / 4 worsen, the four being rank-9/10 churn. Plateau, not peak: every weight in 0.05–0.125 is within 0.006 on both metric sets, leave-one-intent-out picks the same cell on all three splits, and 0.10 is the round number both leave-one-profile-out picks bracket, biased low because the panel-reachable arm — the one real users live on — falls away first. **The behavioural result, on Sebastian's real account: Computer Programmers rank 1 → 5, 0.026 below the third card (about fifty times the jitter); Computer Systems Analysts leads — the row closest to what he marked MORE and furthest from what he marked LESS. A demotion, not a deletion.** Over the fifteen, the card that looks most like the disliked tasks moves **median rank 3 → 6**; its mean barely moves because in four profiles that card is legitimately the best match and stays first — the term is not a blanket demotion. `TestTheFoundersCase` is the regression test and both its assertions evaluate False on HEAD (proved by importing `git show HEAD:` into scratch, no git write). **Three findings worth keeping:** affinity alone, without the rotation, never reaches the plateau (0.433) — both mechanisms earn their place; with affinity present, pushing `adjacent`'s gamma to 1.2 now COSTS 0.015 where W-3a measured it still improving, because the LESS direction no longer has to be dragged in through the query — so gamma stays one shared 0.40; and **LESS-only users are the one arm this makes worse** (`fresh_start` 0.333 → 0.235, harm more than halved) — not given its own constant, because a second weight fitted to a synthetic ablation at n = 15 would be fitting to the ablation; first thing to revisit if real users turn out to state LESS alone. The affinity's percentiles are over the retrieved pool, so a change to `_RETRIEVE_K_ADJACENT` changes this term's scale. **Lesson for the plan:** the harness measures average ranking quality; it does not measure whether one person's stated dislike visibly moves the card they are looking at. Both checks now exist._

_**Also from that click-through — not a code defect:** "loading a position takes so long". The server is fast (first open of a card 0.3–0.5 s, second 0.03 s, timed over 127.0.0.1). On this Windows machine `localhost` tries IPv6 (`::1`) first and Flask's dev server binds 127.0.0.1 only, costing **~2.0 s per request** before the fallback — proven with a bare `http.server`: bound to 127.0.0.1, 2.0 s via `localhost`; bound to `::1`, 0.02 s. Local remedy: `flask run --host ::1` (keep `VITE_API_URL` on `localhost`: switching it to 127.0.0.1 makes `localhost:5173` → `127.0.0.1:5000` cross-site and breaks the SameSite=Lax cookies). The real production cost is the cold deep fit's four O*NET calls (~2.4 s); **W-9 proposed, not dispatched:** precompute the deep fit's static O*NET inputs into a sidecar so a card click makes no network call, and warm the top cards when the list lands._

_**The one full suite run (W-7's open box): 3,671 passed · 62 skipped · 2 failed · 3 errors in 28 min — not strictly green, and not a W regression.** All five are `psycopg2.OperationalError: server closed the connection unexpectedly` on `localhost (::1):5433`; the Postgres container was up five days with no termination in its log, so the drops are Docker Desktop's port proxy under load from three clients at once (the suite, Sebastian's Flask, another agent's runs). Re-run alone, the five pass and a DIFFERENT random test catches the same drop. None is in a Workstream W file. Vitest 984 / 984, `tsc -b` clean. A clean re-run on a quieter machine, over 127.0.0.1, is still owed before the box is ticked._

### W-9 · A card click makes no O*NET call (M) — from the same click-through

- [x] `<artifact>.fit.json` beside the corpus: the four static per-occupation answers the deep fit fetched live (skills profile, hot tech, work activities, tasks), raw and unfiltered
- [x] `flask corpus fit` builder — 4 req/s, checkpointed, residual rows skipped, a code with all four failed is NOT stored
- [x] `deep_fit` reads the sidecar first, live path unchanged on a miss; `onet_calls` 0 on the wire
- [x] Frontend: `usePathFit` is a query keyed by occupation; the three cards on screen are prefetched after paint; reopening a card is free
- [x] `POST /me/path-fit` 10 → 30 per minute (what the 10 protected is gone)
- [ ] The seventh S3 object — first upload is Sebastian's (runbook updated)

_2026-09-22: **W-9 landed.** Built by an Opus agent, reviewed by the overseer (touched backend tests re-run at CI parity: 166 passed / 11 skipped). The sidecar is **10.4 MB on disk, 11.8 MB resident** (own slotted types; the same table on `onet_client.Skill`/`Task` measured 19.2 MB), **941 occupations, 910 complete, 31 partial** — all 31 the same O*NET quirk (parent `.00` empty, `.01` sub-code answers 422), for which the live path returns the same nothing. **3,764 O*NET requests in 15.7 min, once.** Per-worker cache budget 32 + 0.9 + 2.6 + 11.8 = 47.3 MB against the 64 MB ceiling in `test_cache_bounds.py`; ceiling not raised. **Equivalence, and the check was tested before the data:** live vs sidecar on five real codes first showed "DIFFERS" on three — all at the 4th decimal, all on the four embedding-cosine fields; the same path run twice differs by up to 0.0012 (OpenAI embeddings are not bit-reproducible), so every non-embedding field (`matched_skills`, `gap_skills` with order and importances, `tasks`, `tech_stack`, `zone`, `weights`, `retrieval_cosine`) is identical and the cosines agree inside the embedder's own noise. **Timings, stated honestly:** the sidecar lookup is 22 µs in place of 2,384 ms cold / 844 ms warm of O*NET; a full unstored `deep_fit` is now median 710 ms (the one embeddings batch, 560–1,958 ms), warm 18 ms; at n = 5 the live-vs-sidecar wall times (mean 1,434 → 994 ms) are dominated by embedding variance and one code came out faster live — the solid claim is zero O*NET requests per click, plus the frontend's prefetch, which makes a prefetched card open with **no request and no spinner**. `PATH_FIT_EXPECTED_MS` stays 850 and is still right. **Full suite at CI parity: 3,753 passed · 70 skipped · 0 failed in 30:38 — the clean run W-7's box was owed; no Docker-proxy drops this time.** Vitest 1,006 / 1,006, `tsc -b` clean. Two test files outside the agent's ownership list were edited because they enumerate the two lists the brief extended (`test_occupation_corpus.py`, `test_occupation_retrieval.py`) — accepted. Left open: the `onet_calls` description in `solverah/schemas/intelligence.py` still says "four unless a call failed" (fix at the next openapi regeneration, not before, to avoid a re-baseline for a docstring); the S3 upload. No browser click-through yet — that is Sebastian's, and the user-test script (`docs/PATH_WANTS_USER_TESTS.md`, G2/G3) is what to run._

### W-10 · Four screen defects from the first user test (S)

- [x] "Re-sorting your paths…" flashed for under a second, then the pills were clickable for the ~11 s the re-score actually took
- [x] The collapsed row counted unsaved edits ("1 thing you want to change" before any save)
- [x] The "Coming soon" tooltip opened upward over the Interesting / Too similar / Not for me row
- [x] "Adjust search preferences" re-opened with all three questions blank

_2026-09-22: **W-10 landed** (Sonnet agent, overseer-reviewed). The first defect was a render-order race: the panel cleared its own "waiting for the re-score" flag on the render after the save, before the page's mutation had flipped `rescoring` to true, so it never saw the re-score at all — the flag now clears only after `rescoring` has been observed true then false, with a 15 s fallback for the never-started case. **Overseer sent one correction back:** the first version of that fallback fired even after the re-score was seen running, and a Fresh-direction re-sort measured 27 s in the user test, so the pills would have unlocked mid-re-sort again; the fallback is now disarmed the moment `rescoring` goes true, with a fake-timer test for exactly that. The count now reads saved answers only (`savedCount`), and "Clear my answers" on a draft-only state drops the draft locally and sends no PUT. Tooltip opens below the button. The preferences form reads `profile.path_preferences` through the same `useProfile()` the page uses and pre-selects them (`aria-pressed` added for the tests). Every fix has a test proven red without it. Vitest 1,018 / 1,018, `tsc -b` clean (re-run by the overseer). Each fix stayed inside its own files while W-9 held the page._

### W-11 · Four scorer rulings from the first user test (M)

- [x] Ruling 1: `stay_in_field` retrieves on the un-rotated anchor; wants act on the rank only
- [x] Ruling 2: Stay honours `not_for_me` / `too_similar` as removals (exclusion + radius); no Rocchio rotation; `interesting` recorded, moves nothing
- [x] Ruling 3: a STATED axis's line (tier 0/1) is exempt from the 70 % ubiquity drop; unstated (tier 2) still dropped
- [x] Ruling 4: a tier-1 line that points against the ask is prefixed "Still …"
- [ ] Sales Engineers on his Stay page — the pool, not the ruling (decisions file item 7)

_2026-09-22: **W-11 landed** (Opus agent, overseer-reviewed, touched backend tests re-run: 603 passed). **Ruling 1 was reproduced first:** on Sebastian's account, Stay with his three answers returned the same ten codes as Adjacent — Logistics Engineers, Sales Engineers, Project Management Specialists, Security Management Specialists among them — because `_wants_rotated_query` rotated the retrieval query for all three intents and for Stay the query WAS the field. Fix: the rotation is gated to `adjacent`/`fresh_start`; Stay's pool comes from the anchor as with no wants. **Within that pool the `role` term was measured two ways** on p21–p25 against W-8's run: (a) anchor cosine, macro nDCG 0.412 → 0.380 (−0.11 on two profiles, same ten cards in a worse order); (b) rotated-query cosine over the anchored pool, 0.412 → 0.412, harmful 0.120 unchanged in every arm — shipped (b). **The honest finding: the labelled set cannot see ruling 1** — on all five Stay profiles the anchored and rotated pools agree about the top ten, so the gate asserts "not worse" and the fix's proof is `TestTheFoundersStayCase` on the real corpus (his profile, `move_intent="stay_in_field"`). After: Logistics Engineers, PM Specialists and Security Management Specialists are gone from his Stay page; **Sales Engineers stays at 7th** — it is the 29th-closest of the anchor's 30 neighbours and his `people: more` promotes it; only the pool (`_RETRIEVE_K` or a same-major-group filter) could remove it, which is a new ruling and is item 7 in `docs/PATH_WANTS_DECISIONS.md`. Stay with no wants is byte-identical. **Ruling 2** needed no service-layer change (`path_suggestions` and `_rescore` already pass `feedback` for every intent; the frontend never gated the buttons), so the buttons a Stay user already had now take effect. Guards all re-recorded live: adjacent + fresh_start 10/10 identical to W-8, wants-blind 15/15 to W-2, old twenty 20/20 to F-8; headline on the fifteen unchanged 0.464 / 0.060. Two W-4 tests were overturned rather than adjusted (the strong phrase now survives ubiquity; the stated axis speaks on a page it describes everywhere). **Full suite at CI parity: 3,782 passed · 74 skipped · 0 failed — the clean run W-8's note owed, with W-12's suite running alongside on its own DB.** Run fixture `runs/w11_stay_anchored.json`. Recorded caveat: `_anchored_role_scores` scores against a rotated query whose cosines compress toward `_COSINE_FLOOR`; it never bound on the fifteen, but a much larger beta would flatten the term silently._

### W-12 · Cards after a tap, and the fit panel's lists (M) — "do them now"

- [x] B: the fit panel shows each tool once, under the user's own name for it
- [x] A: cards that surface after a tap carry a real narrative and pills (a reserve of ten narrated in the job)
- [ ] The reserve is per worker, like the payload — hidden while prod runs one worker; the Redis adapter is the fix for both

_2026-09-22: **W-12 landed** in two parts (Opus agent, overseer-reviewed). **B first, because A was blocked.** On Software Developers, "Tools people use" listed twelve items of which **eleven were repeats** of "Skills you already have" or "Worth picking up" — three of them the user's own skills under O*NET's long names ("Structured query language SQL"). `tech_stack` now excludes anything shown in either list; the de-dup compares the *role item* each skill matched (O*NET's own vocabulary, exact by construction) rather than names, because "Amazon Web Services" and "Amazon Web Services AWS software" share no alias and were matched by cosine. Filter-then-trim. `fit_score`, `matched_skills`, `gap_skills` byte-identical before and after; wire shape unchanged. Three W-9/F-5 tests that had pinned the defect (`tech_stack == ["Python", …]` for a user whose skill IS Python) were re-pointed at an outsider profile with every assertion intact. **A stopped honestly on the first pass:** `score_paths` returns exactly ten and the file was W-11's, so the agent measured the design and reported instead of improvising. Measured on three real profiles, cold: narrating ten takes 10.3–11.1 s today (F-6's docstring said 6.7 s — corrected in place; the provider got slower); **two parallel batches of ten add −0.20 s mean** (+1.52 / −1.72 / −0.39) where one call of twenty costs ~18 s; three taps surface 14 / 12 / 20 distinct occupations, so a reserve of ten is the measured depth (five would leave the worst profile's first tap short). Built once W-11 released the file: `score_paths(..., reserve=0)` returns `page + scored[10:10+reserve]` with `_attach_reasons` still over the ten shown (a test spies that it is handed exactly `PAGE_SIZE`); the reserve lives in `path_cache` as a second dict behind the same lock, bound and `invalidate` — so every writer that drops the shortlist (eight sites, none edited) drops the prose with it, and a tap (which writes through `store`) keeps it; `generate_narratives_batched` fans batches onto a thread pool, best-effort per batch, a missing page batch still a 500 and a missing reserve batch nothing at all; `_describe` reads the reserve BEFORE its carry-forward, which is the fix rather than a detail (the carry-forward keeps any truthy `why_text`, including a fallback it wrote itself). Tap stays LLM-free at 1.5–3.2 ms; ~1,524 extra tokens per job (≈ $0.0007). **Full suite at CI parity: 3,806 passed · 74 skipped · 0 failed.** Open: the reserve is per worker (prod = one worker after the OOM fix, so hidden until that goes back up — same Redis fix as the payload cache); a user who taps more than three or four times runs past the reserve and sees the fallback again; `PathFitResponse.tech_stack`'s schema description understates the new rule (fix at the next openapi regeneration)._

### W-13 · Five findings from the third user test (S)

- [x] The narrator graded the fit ("…making it a strong fit for your background") — ⚑1
- [x] After a reload the "Start over" bar was gone while the taps stayed in force
- [x] Two options read as selected in the preferences form
- [x] O*NET's "Hypertext markup language HTML" names on the fit panel
- [x] Subtitle said "scored"

_2026-09-22: **W-13 landed** (Opus agent, overseer-reviewed: touched backend tests 233 passed, Vitest 1,023 / 1,023, `tsc -b` clean). **The grade was the prompt's own doing:** `_build_prompt` handed the model every card's `match_score` and headed the list "sorted by match_score, highest first" — a model given a number writes about the number. The score is gone from the prompt (the order is still the order), a system rule now bans rating language outright, and — because a prompt is a request, not a guarantee — a deterministic `_scrub_grades` runs over every `why_text` and tag: it cuts the smallest thing carrying the grade (a graded lead-in at its colon, else the trailing clause at the last boundary that removes it, else the whole sentence), falls back to `_describe`'s own "Uses your …" sentence when nothing is left (imported, not copied), and logs once per batch with the codes so a prompt regression is visible. Word list in one tuple, Julie may extend it; bare "match"/"fit" deliberately absent so "Matches your Deep Diver archetype" survives. **The reload bug was the backend's:** `_rescore` returned `feedback` on the tap's own response but stored the cached payload WITHOUT it, so a reload's warm-cache job carried no map and the page (correctly reading `jobData.feedback`) showed no bar — diagnosed on the running stack before any change; three tests failed with `KeyError: 'feedback'` on HEAD; `feedback` now lives on the payload. **The double selection was a hover colour:** unselected options used `hover:border-forest-light`, the same green family as the selected state, so the pointer resting on the way to "Next" lit a second option; now a neutral hover, and the test asserts an unselected option carries no `forest` class, `hover:` included. **Acronyms:** `_display_name` collapses "Hypertext markup language HTML" → "HTML" only when the preceding words *spell* the trailing all-caps token in consecutive runs (not initials — "Hypertext markup language" is H-M-L); applied at DeepFit construction only, so W-12's role-name de-dup still compares O*NET names to O*NET names; 17 names measured, "Oracle Java" / "Node.js" / "Amazon Elastic Compute Cloud EC2" untouched. Subtitle now "matched to". Full backend suite at CI parity: **3,848 passed · 74 skipped · 0 failed.** One trap recorded by the agent: inserting a test class between a `@pytest.mark.skipif` and the class it decorated silently moved the skip — three corpus tests went green by being skipped until caught._

### W-14 · Two tap-path bugs found by the overseer on the real stack (S)

- [x] Start over returned the cards a tap had removed as fallback sentences with no pills
- [x] A tap or Start over on a cold cache cached a page of ten fallbacks, served as narrated by every job after it

_2026-09-22: **W-14 landed** (Opus agent, overseer-reviewed: touched tests re-run, 152 passed). Found while checking the fourth user-test run, which had been made against a stale API process (Flask started 13:30, W-13 written after 14:10 — rule now: the overseer checks the process start time against the file times before any test prompt goes out). Driving the current code on the real stack with the E2E account (`<scratch>/repro_reserve*.py`) showed newcomers narrated, the reload keeping taps and bar, and Start over restoring the original ten in order — **but the two cards the taps had removed came back as "Uses your SQL." with no pills** (their prose was on the page copy only; the reserve held ranks 11–20), and **a tap on a freshly started API stored a page of ten fallbacks that the next job served as if narrated**, for every reload after, until something invalidated — in production, every user's first tap after a deploy. Fixes: the job keeps all twenty narratives in the reserve, page included (it was discarding half the narrator's output; no extra call); and the cache entry carries a `narrated` flag — inside the entry, not on the payload (the payload is the wire) and not in a parallel dict (hand-maintained eviction in the module that once OOM-killed production) — computed by `_describe` from where each card's prose came from, and `path_suggestions` treats an un-narrated cached payload as a miss. The variant "`_rescore` doesn't store on a cold cache" was rejected because it re-opens W-13 (a reload would again poll a payload without `feedback`). Cold tap still answers in 30–70 ms. Six tests red on HEAD, three guards green by design. **Full suite at CI parity: 3,855 passed · 74 skipped · 0 failed.** Open: the reserve is now 20 per cached user under the same 500-entry cap — a few MB per worker at the cap, worth a glance in `test_cache_bounds.py`; the tree now carries another lane's landing-page work (`index.html`, `tailwind.config.js`, `src/features/landing/`, `IntakeForm.tsx`) — stage by path only._

### W-16 · Cards first, narratives after; narrator 4x5; narratives stored (M) — first post-launch chunk

- [x] The scoring job returns as soon as cards are scored; narration runs on an in-process pool of 4 and the poll picks it up (`narration_pending` on the wire)
- [x] Narrator batches of 5 in parallel (measured 8.2 s -> 4.4 s for twenty, +26 % tokens)
- [x] `path_narratives` table: sentences stored per (user, occupation, fingerprint of the narrator's exact inputs); re-sorts reuse them
- [ ] `flask retention run` does not yet call `path_narrative_repository.purge_older_than()` (rows past 30 days are ignored on read, not deleted)

_2026-09-28: **W-16 landed** (Opus agent, overseer-reviewed: key backend files re-run, 438 passed). Sebastian, the day Path Intelligence reached production: "the loading phase is 5-10 s with one user, imagine 10 users". Cause, measured: with eager Celery the whole job — scoring (0.3-3 s) plus the narrator (~10 s) — ran inside the POST on one of the single gunicorn worker's 8 threads, so ten users queued behind each other. The deep-fit panel (W-9) was not the problem. Real stack, 8-thread cap, three profiles: **first cards 13.7 / 7.4 / 9.4 s -> 2.7 / 0.8 / 0.5 s; narratives 5-7 s; a repeat re-sort 8-12 s -> 0.06 s; ten users at once, first cards p95 20.0 s -> 1.1 s, request-thread time held 105 s -> 8 s.** Narratives for ten concurrent users arrive in three waves (p95 13.8 s) because the narration pool is 4 — one constant (`NARRATION_WORKERS`), kept small for Render's 0.5 CPU / 512 MB. The fingerprint hashes the system prompt, the person block exactly as the prompt renders it, and the card (code, title, overlapping skills) — NOT wants, taps, score or reasons — so a panel save or a tap reuses every sentence, and a skill or preference change re-narrates; `_build_prompt` refactored onto the same helpers and byte-identical to HEAD. Additive wire change: `narration_pending` on the suggestions and feedback responses, `overlapping_skills` per card, `why_text` may be empty while pending; `succeeded` now arrives at scored. A narrator failure no longer fails the job (cards take the fallback). Worker death mid-narration: any read 60 s past `generated_at` serves fallbacks, the client stops after its poll cap, a pending list is never served as a cache hit (W-14's rule held). Grade scrub before storage; fallbacks never stored; deleted-account race stores nothing; table in the D-7b delete path. Contract baseline recaptured byte-identical (111). **Full suite at CI parity: 4,050 passed · 74 skipped · 0 failed** (third run; the first two caught a layering violation and a test-only queue/app race, both fixed). Vitest 1,137 / 1,137, `tsc -b` clean. Migration `20260928_path_narratives`, single head, upgrade/downgrade/upgrade proven; no env var, nothing to set on Render. A database-optimisation lane was dirty in other files during the run (none of W-16's); stage by path._

_Still open from Workstream F and **not** absorbed here: regrade the own-job
labels on p01–p04 to `anchor`; review the 56 low-confidence labels (p05 first);
the first corpus upload to S3 before any main merge; ⚑9._

---

## 7. Cross-cutting engineering notes

- **Every new endpoint:** pytest (happy/error/edge), rate limit, OpenAPI
  regen, contract-baseline capture (additive), assessment routes get the
  form-token-secret fixture rule from CLAUDE.md.
- **Every suite claim:** CI-parity run (`SOLVERAH_IGNORE_DOTENV=1`, cleared
  `JWT_SECRET_KEY`, `FLASK_SKIP_DOTENV=1` for CLI), lane DBs on 5433,
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, venvs outside the repo.
- **E2E:** feature_tour ROUTES gains every new route the moment it mounts;
  real_stack gains one full flow per workstream (the mocked frontend suite
  has already proven it cannot catch cross-layer drift).
- **Naming:** "Situation Report", "environment report", "Manager Decoder",
  "Pulse check-in" are working names; brandable names (™ pattern) are
  Sebastian's call before launch copy freezes.
- **No company seeding anywhere in this plan** (decided 2026-09-08); the
  xlsx seeder stays bit-rotted and unneeded.

---

## 8. Sequencing

```
now ──► D-0 regression fix (S)
     ├─► 0  decisions recorded ──► gates A-4/A-5
     ├─► 0b commit hygiene (S–M)
     ├─► D-1 agent context ─┐
     ├─► D-2 bridge         ├─ quick wins, any order, parallel-friendly
     ├─► D-3 trust page     │
     ├─► D-4 search string ─┘
     ├─► D-5 quiz persistence ──► enriches D-1
     │
     ├─► C-1 → C-2 → C-3 → C-4          Manager Decoder (unblocked, ships first)
     │            └───────────► shared manager profile ready for A
     ├─► A-1 → A-2 → A-3 → A-4(ruling) → A-5 → A-6 → A-7   Situation Report
     │                                            └─► D-2 upgraded
     ├─► B-1 → B-2 → B-3 → B-4                    Pulse (thin)
     │                        └─► B-5 experiments (cut line)
     └─► D-6 dashboard reframe (after A + B)

parallel, NO external gate (green-lit 2026-09-16, runs while E waits):
  F-1 corpus ─┬─► F-3 retrieval ──► F-4 rewrite ─┬─► F-5 deep fit on click
              │                        ▲          └─► F-6 adjacent ──► F-7 fresh_start
              └─► F-2 eval harness ────┘                                   │
                  (baseline BEFORE the rewrite, or F-4 is unfalsifiable)    │
                                                          F-8 cleanup ◄─────┘

after F (direction approved 2026-09-17), gated on its OWN measurement:
  W-1 no percentage (ships regardless)
  W-2 wants profiles + labels ──► W-3 sidecars + scorer, offline ──┬─ holds ──► W-4 API ──► W-5 panel ──► W-6 ──► W-7
      (labelled BEFORE the scorer exists)                          └─ does not hold ──► STOP, record it

parallel, gated externally:
  E-1 Julie ──► E-5 fit + serving ──► Situation Report weight swap
  E-2 packets/raters ──► anchors + scales ──► E-5
  E-3, E-4 anytime (E-4 after A-2 exists)
  entity/attorney lane ──► launch gate (start immediately; longest lead time)
```

**Launch tiers** (from PRODUCT_IDEAS §5, now with chunk names):

- **Floor:** D-0…D-5 + C complete. Coherent "know how you work" product,
  nothing broken, agent that knows the instruments.
- **Target:** + A (interim rules scoring) + B-1…B-4 + D-6. The
  differentiated product: assessment pays off in a Situation Report, the
  Pulse starts the loop, dashboard tells the working-life story.
- **Stretch:** + B-5 experiments, + E-5 if Julie's round-trip lands early
  (report quietly upgrades from flat weights to posterior weights — no UI
  change, one decisions-doc entry).

Rough effort to Target, in focused agent-days: D≈4–6 · C≈5–7 · A≈8–11 ·
B≈4–6 → **~21–30 agent-days** of build, plus review cycles and the content
passes (A-6, C-2, D-3) which want Sebastian's eyes. The external lanes
(Julie, raters, attorney) are calendar time, not build time — which is why
they all start now.

---

## 9. Future ideas (parked, in priority order)

1. **Offer & Interview Due Diligence** (PRODUCT_IDEAS §3.4) — probe packs,
   post-interview capture, offer-vs-current comparison. Natural Pro
   surface; reuses A's instrument + E-5's scorer; each evaluation feeds
   the company store. Build after Target tier.
2. **O*NET as conditions backbone** (§3.5) — DECIDED "backbone, not
   product" (Sebastian, 2026-09-10; entry in PRODUCT_DECISIONS §2). The
   build stays parked here behind Target tier: Work Context/Values
   endpoints in `onet_client.py`, crosswalk via E-1's appended Julie
   question (now confirmed IN), rewritten narrative. The real-output
   walkthrough is still the right first step when picked up.
3. **Portable Work Profile / user manual** (§3.6) — decision-required
   (D-15 adjacency); one-shot generation from non-core instruments;
   distribution loop.
4. **LLM playbook personalization** (C-2 fast-follow) and **agent-led
   conversational capture** of culture preferences (the deferred MVP
   decision, natural once D-1 matures).
5. **Company profiles from aggregated declared reports** — N≥k thresholds,
   anonymization discipline (in-house via packet pipeline), legal review
   BEFORE any display. The organic CompanyLens data supply.
6. **Feed content decision** (§3 of PRODUCT_DECISIONS stays open) — the
   Pulse gives it a candidate answer (your working life, observed);
   company-news feed stays blocked on content anyway.

---

*Chunks get checked off here as they land. Corrections to scope or
sequencing belong in this file, dated. Decisions belong in
`PRODUCT_DECISIONS.md`.*
