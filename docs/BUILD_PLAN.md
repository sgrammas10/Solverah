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
  the form only on 2026-09-14. Everything in §5 behind the "priors gate"
  waits on her returned form. Async-only — see §5.1.
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
- [ ] On return: internal appendix maps answers → real `priors.yaml`
  values ({mean, sd} per weight); commit the swap — structure code
  unchanged by design

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

### E-5 · Fit run + serving (M–L, after E-1 + E-2)

- [ ] First real-priors fit; posterior snapshot into `weight_posterior`
  (scorer-run storage from chunk 0b)
- [ ] Serving seam: `score_fit(person_scores, env_scores, confounders) →
  P(fit), per-dim contributions, uncertainty` — pure function over the
  posterior, no PyMC at request time
- [ ] **First consumer: the Situation Report** (A-3's flat weights →
  posterior weights; payload spec unchanged, so no UI change) — the
  interim→destination swap, proven pattern
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
- [ ] The protected-class proxy check rides the same N≥300 gate (compliance
  mirror note)

---

## 6. Workstream F — Path Intelligence rebuild  *(green-lit 2026-09-16; runs while E waits on Julie)*

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
- [ ] **Measure the CURRENT scorer first and record the number**
  _(harness ready; the live run — ~3,200 O*NET calls — is sequenced after F-3's calls finish, so two processes never race one API key)_

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


_2026-09-16: **F-2 landed** (f51bef7). 20 profiles, 249 labels (66 primary / 130 acceptable / 45 harmful / 8 anchor), 56 flagged low-confidence in a `confidence` field (`python -m backend.services.path_eval review`). Every code validated live against O*NET (48 calls). **Metric correction:** precision@10 is rank-blind and MRR saturates on a 10-card shortlist, so the harness adds **nDCG@10 (tune on it)** and **harmful_rate@10 (gate on it, target 0.0)**; calibrated — random scores nDCG ≈ 0.01-0.02, oracle 1.0, so ≥0.35 is a real scorer. **Sample-size rule for F-4:** 20 profiles supports "clearly better or worse", NOT per-axis claims (n=5-6 per cell). **Production finding:** `_DEFAULT_ALLOWED_SOC_PREFIXES` structurally excludes whole families — electrician 0/3 primaries reachable (47-/49- barred), graphic designer 1/3 (27- barred), warehouse 2/4 (53-/49-/51- barred), teacher loses 21-. Three of 20 profiles will likely return empty and 500 today — the ACC-4 shape, hitting tradespeople and designers. See F-4 and F-8._

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

- [ ] **Replace** `_gather_candidates` — the job-family + keyword funnel becomes
  F-3's retrieval
- [ ] **Replace** the comparison target — role documents, not a centroid
  dominated by the fixed ~35 generic skills. *This is the accuracy fix; the
  retrieval change alone does not deliver it*
- [ ] **Keep** `_zone_delta_score`, `_work_style_similarity`,
  `_role_coverage_score` and the weighting scheme — not broken, and exactly
  what F-5 needs for a single occupation
- [ ] Anchor `stay_in_field` on the user's own resolved occupation vector
  (document-to-document, symmetric), not title-to-title
- [ ] Beat F-2's recorded baseline, or say plainly why not

_⚑8 Sebastian, 2026-09-16. Closes design doc §5 #1. Two scorers means two
things to keep correct; a clean deletion would throw away per-candidate logic
that is fine. `path_scoring.py:1166` already asks for the retrieval half of
this ("Replace this block with `get_related_occupations` when O*NET adds that
endpoint") — F-3 is that endpoint, self-built._

### F-5 · Deep fit on click (M)

- [ ] New endpoint: the full analysis for ONE occupation, run on user click
- [ ] Stored per `(user, occupation)`, invalidated on profile write, mirroring
  `path_cache`'s `invalidate` discipline — needs a table + migration
- [ ] Rate limit, matching `POST /me/path-suggestion-jobs` — this is a per-click
  provider spend
- [ ] Synchronous: ~3-4 `_OCC_CACHE`-backed calls for one occupation, ~500ms-1s
  warm. No job/poll pair

_Sebastian's design, 2026-09-16. The budget currently spread thin across ~40
candidates gets spent on the one the user actually cares about — so the analysis
gets **better**, not merely rarer._

### F-6 · ⚑7 `adjacent` — inline feedback on the result cards (M)

- [ ] Result cards carry "too similar" / "interesting"; the list re-ranks as the
  user taps
- [ ] Rocchio update: `q' = α·q + β·mean(liked) − γ·mean(disliked)`
- [ ] **Both signals, not just the radius.** "Too similar" raises the annulus
  inner radius; "interesting" *rotates* the query — two occupations equidistant
  from the anchor can lie in opposite directions
- [ ] MMR for probe diversity (top-K teaches nothing, random teaches nothing)
- [ ] Zero taps must still yield a full default result set

_⚑7 Sebastian, 2026-09-16: **inline, not a questionnaire.** Closes design doc
§5 #3. The doc originally proposed a one-screen elicitation step; that was the
weaker idea — a separate step is friction before the user has seen any value,
most people skip it, and the accuracy benefit never lands. Inline makes the
feedback *be* the browsing, and is valid-half-finished by construction._

### F-7 · `fresh_start` — diverse seed, same loop (M)

- [ ] k-means over the corpus (k ≈ 8-10); take the nearest real occupation to
  each centroid as the seed set
- [ ] Transferable-skill floor: retrieve on the user's *skills*, constrained to
  a different SOC major group
- [ ] Job Zone feasibility as a **hard filter**, not a weight
- [ ] Behavioral profile (`archetype` / `focus_type` / `work_style_tags`) as the
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

### F-8 · Cleanup + refresh cadence (S)

- [ ] `flask corpus build` on a Render cron, matching Scenario A's shape —
  O*NET content changes quarterly
- [ ] Test whether the SOC allow-list is still needed once documents replace
  titles; remove only with evidence, never on assumption (design doc §5 #5)
  _(2026-09-16: **the evidence now exists, and it says remove.** F-2's ceiling analysis shows the list bars entire occupational families from the users IN those families (electrician: 0 of 3 primaries reachable). F-1 showed the title-domination failure it patched does not occur with role documents. F-4 must NOT carry `_filter_candidate_pool`'s prefix allow-list into the new retrieval; F-3's named hard filters replace it. This box becomes: confirm with the harness that removal did not reintroduce the original failure.)_
- [ ] `_EMBED_CACHE` retires with the funnel — confirm the interim bound from
  the 2026-09-15 OOM work is genuinely dead before deleting it
- [ ] A title that resolves to no O*NET code falls back to F-7's seed rather
  than erroring — the live ACC-4 / S22 failure (design doc §5 #6)

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
