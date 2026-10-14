# Product decisions

What Solverah is deciding to be, and what it has decided not to be. Kept here
because these questions kept getting re-litigated from memory across sessions,
and because the code cannot answer them — several of the entries below explain
why something in the repo looks wrong but is deliberate.

**Scope.** Product shape, feature fate, and launch content. *Not* engineering
decisions (those live in `docs/ARCHITECTURE.md` and the runbooks) and *not* the
compliance/legal queue (`Solverah_IP/AGENT_DECISION_QUEUE.md`, which is a mirror —
do not edit it here).

**How to read it.** Every entry says who decided and when, or says it is open.
An open question recorded here is not a soft decision; it is a question. Do not
build against one without asking.

Last updated 2026-10-13.

---

## 1. The end goal

**Solverah is a career development platform, not a company-pairing app.**
Sebastian, 2026-09-08.

This is the frame everything below is judged against, and it is a correction to
how the product currently reads. The build today narrates company matching as the
destination — the assessment withholds its payoff *because* the payoff was
assigned to matching, the dashboard's quick action is "Browse Jobs — Find
matching opportunities", and the Intelligence hub's headline card is CompanyLens.
Company pairing is intended to be **one output of** the platform, not the point
of it.

### The spine is conditions: diagnose them, improve them, and match as one output
Sebastian, 2026-09-08; signed 2026-09-10, as drafted. Closes the open question
this section carried.

The instruments measure working conditions, so that is what the product is:
**what conditions make you effective, how far your situation is from them, and
what you change.** That is the spine. Company matching is one output of the
same engine — worth building, but not the frame around the product and not a
payoff the rest of it is allowed to defer to.

What this settles in practice:

- An instrument whose result is narrated as a future company match is now
  wrong copy, not merely early copy.
- The dashboard is the largest remaining contradiction — "Here's your job
  search overview", Job Matches / Applications stats, a Browse Jobs modal: a
  job board's information architecture, without jobs. The reframe is
  `BUILD_PLAN` D-6 and is deliberately sequenced last, because it embodies this
  decision and needs the Situation Report and the Pulse to have something to
  show first.
- Matching is not demoted to someday. CompanyLens still waits on the causal
  model (§2), unchanged. What changes is that the rest of the product stops
  holding its breath for it.

The counter-consideration this entry replaced — that the conditions framing was
proposed by an agent reading the code, not by the market — stands, and stays
worth testing. The cheapest test is the Situation Report itself in front of
real users. If the diagnosis is not what they care about, this is the entry to
reopen.

---

## 2. Decided

### Work Pulse keeps the LLM-scored path in principle — but nothing is re-mounted
Sebastian, 2026-09-08.

Cost is explicitly **not** the obstacle ("it's so cheap, and we may decide to keep
it when launching the model"). But the retired 12-item instrument (`WPStepper`,
`wp-q1`…`wp-q12`) is **not** to be re-mounted.

Net effect, stated plainly because it is easy to misread: the shipped instrument
is `core` — 24 items, rules-scored, producing 6 dimension scores and **no
narrative and no archetype**. A user finishing the assessment today gets nothing
to read. That is a consequence of this decision, not a defect.

The copy promising "a personalized narrative, your work archetype" was removed
from the Intelligence page on 2026-09-08 for that reason. Anything that
re-introduces such a promise is a bug until an instrument produces one.

### The six-trait match model: scope, inputs, evidence, penalties (CompanyLens build)
Sebastian, 2026-10-13, in answer to Julie's *Product & Match Model Alignment*
brief (October 2026, working draft; shared in chat as a PDF, not in the repo)
and the orchestrator's follow-up questions. **Build all of it now**; it is not
staged behind launch.

**Scope and output.**
- The six traits (autonomy, pace, collaboration, feedback, innovation, decision)
  are **one signal layer** inside the wider system (Reflection Engine,
  Understanding, Guidance), not the full matching intelligence. Shown as their
  own section, never blended into one number with other layers.
- The engine is the **causal Bayesian model** (`match_scoring.py` →
  `causal_graph/v1_model/`). Tolerance changes the gap it reads; must-have,
  unknown and mixed rules are a gate layer on top of it. The interim
  `culture_fit_score` is retired by this build, per "two scorers" below.
- **No probability reaches a user** until real outcome data has trained the
  model. Users see per-trait reads, coverage and flags.
- Everything company-side surfaces in **CompanyLens**. This supersedes "CompanyLens
  is blocked on the causal model" below: the pipeline that feeds the model and
  CompanyLens is now in scope.

**Outcome ("doing well").** The primary outcome stays as pre-registered: the
1–5 `experienced` rating, "doing well" = 4 or 5 (ruling 2026-09-17). Further
outcomes (satisfaction, performance, engagement, sustainability, retention —
each defined on a 0–1 scale) are added as **exploratory**, via a new amendment
to `Solverah_IP/PREREGISTRATION_2026-10-01_FIRST_OUTCOME_FIT.md`.

**Person side.**
- The 24 core items are the user's **current stated preferences**, not "the
  person's trait".
- Per trait, one asymmetric **tolerance** range (how much more is fine, how much
  less is fine), in steps of the person lattice (0, 1 or 2), plus a **must-have**
  flag, max 2 per user. Asked as a short separate step after core; core itself
  (the D-01 path) is not changed. Users who have not answered get no must-haves
  and a 1-step tolerance.
- The flat zone is the larger of the user's tolerance and the existing 0.15
  `aligned` band (the measurement-noise floor). Inside it: no penalty. Outside:
  growing penalty. A must-have broken on a **known** trait: the company is
  flagged and sorted last, never hidden.
- The same tolerance applies to the **Situation Report**: a gap inside it is
  aligned there too.
- Retakeable at any time; no forced cadence. Situational and lasting-vs-current
  questions belong to the Reflection Engine, not this layer.

**Company side: scope.**
- Every piece of evidence carries a scope: company, division/location, or role.
- A **job posting the user pastes** is a role-level source scored against the
  same rubric. No fetching or scraping. Posting vs company disagreement is shown
  to the user.
- Confidence scales with company size (fixed size buckets, provisional
  discount).
- Manager/team uncertainty becomes guidance: for the user's must-have traits,
  an authored interview-question bank (trait × status × direction; best-guess
  drafts, Julie revises). Teams are not modelled. Manager Match stays separate.

**Company side: each trait is a record, not a number.** `estimate` (0–1, only
with enough evidence), `confidence`, `status` (known / mixed / unknown),
`scope`, and evidence (count, dates, **paraphrased** excerpts — no verbatim
third-party quotes).
- **unknown**: no gap, no penalty, left out of the match and flagged; on a
  must-have it becomes an Investigate step.
- **mixed**: never averaged. First check whether scope or time (review date,
  last 24 months vs older) explains the split; then score both ends; a worst
  case that breaks a must-have is a risk flag (not a disqualification). The
  user is told the evidence disagrees, with paraphrased evidence from both sides.
- **known**: scored normally.
- The scorer scores each evidence item separately, with an explicit
  `insufficient_evidence` abstain (the v3.1 rubric skip); mixed is read from the
  spread.
- **Coverage** is reported ("based on 4 of 6 traits"), never silently rescaled.
  Below 3 of 6 known: "not enough evidence" instead of a match.
- "Known" thresholds (min count, recency, consistency) are ours, provisional,
  and go through the sensitivity test.

**Gap penalties.** `priors.yaml` (Julie's elicited, already asymmetric values)
is the penalty table; it gains a "why" and a date per entry rather than a second
file. Shape: flat inside tolerance, linear outside (the hinge) is the serving
default now; linear-from-zero becomes the comparison in the pre-registration.
Trait weights equal by default, personalised by must-haves. Compounding pairs
(e.g. low autonomy + high pace) are listed (drafted from Julie's notes, she
edits) but ignored by v1 math. Per-outcome penalties stay expert defaults.

**Pipeline calls (Sebastian, 2026-10-13, on the build plan).**
- CompanyLens covers **any company a user names**, researched on demand in the
  background and cached, plus a batch command to pre-fill a starter set.
- Research step on **Anthropic** (the method the packets were validated with; a
  new app vendor, so it gets a `VENDOR_REGISTER` entry); scoring stays on the
  validated `gpt-5.5` snapshot.
- A user who has not answered tolerance keeps **exactly today's behaviour**
  (0.15 floor), replacing the "1-step default" above.
- Automated collection from review sites is built now; **attorney review before
  it is public** (output is paraphrase-only per GAP-14; collection is a separate
  question, cf. ZenSearch paused 2026-08-20).

**What changes the weights, cheapest first.** (1) versioned table with why +
date; (2) sensitivity test — nudge each weight, see whether rankings move
(synthetic people × round-2 scored companies; a weight "matters" if top-5
overlap drops below 4/5 or rank correlation below 0.8); (3) blind raters on
person/company pairs — raters who did not set the weights (not Julie, not
Sebastian if he sets them), unpaid; (4) after launch, 90-day check-ins via
Pulse, linked by an "I took this job" action, directional only; (5) long term,
fit penalties to outcome data with the expert weights as priors — the only
thing that would justify showing a probability.

### CompanyLens is blocked on the causal model, and that is expected
Sebastian, 2026-09-08. *Superseded 2026-10-13 by the six-trait entry above:
CompanyLens and its pipeline are now being built.*

`GET /api/v1/me/matches` returns 400 for every current user. This is **not** a
defect to chase. It waits on the causal Bayesian model, which waits on Julie's
priors and anchors.

The mechanism is worth knowing because it looks like a bug:
`matching_service._derive_culture_preferences` loads a **`work_pulse`** submission
and reads `submission.answers`, and `work_pulse/derive_preferences.py` is
hard-coded to `wp-q1`…`wp-q12` with a/b/c/d options. `core` users have no such
submission, so the derivation returns `None` and the endpoint 400s. Making
matching work therefore needs a defined mapping from `core` (24 items / 6
dimension scores) to the 8 culture-preference dimensions — modelling work, not
plumbing, and plausibly the same work Julie's elicitation feeds.

*2026-09-10: that mapping will **not** be built — see "The core-to-8-dimension
culture-preferences mapping will not be built" below.*

### Do not seed companies to test matching
Sebastian, 2026-09-08. The interim `culture_fit_score` scorer is being replaced,
so measuring its output measures something about to be deleted. Revisit when the
causal model lands. (The xlsx company seeder is separately bit-rotted — 14 of 20
rows parse as "Unknown" — which will need fixing before any seeded run.)
*2026-10-13: the revisit point has arrived (six-trait entry above). The
sensitivity test runs on round-2 scored companies, not seeded ones.*

### `Solverah_IP/` stays tracked in this repo
Sebastian, 2026-09-08. ~6 MB tracked (the 32 MB figure was on-disk, dominated by
untracked `node_modules`). Untracking it would pull the ground-truth dataset out
of version control and break the three scheduled packet-pipeline tasks that
commit into that tree. If revisited, the answer is a separate repository with
history preserved, after pausing the pipeline — never a `.gitignore` entry, which
would be a no-op on already-tracked files.

### Launch scope is the top three ideas plus the small sharp moves
Sebastian, 2026-09-08; signed 2026-09-10, as drafted. **Also closed "what the
assessment's payoff is at launch", formerly in §3.**

Approved for launch, from `docs/PRODUCT_IDEAS.md`: the **Situation Report**
(§3.1), the **Pulse** (§3.2), the **Manager Decoder** (§3.3), and the small
sharp moves (§3.7). They are chunked in `docs/BUILD_PLAN.md` as workstreams A,
B, C and D. Everything else sits in that file's §8 in priority order, and
parked there means not started — not rejected.

The assessment's payoff at launch is the **Situation Report**. §3 asked for
that to be chosen rather than discovered; this is the choice. Twenty-four
questions about you, about ten about your job, and the report is what comes
back. Interim rules scoring ships it before the model is ready, and the model
later replaces the weights underneath without changing the surface — the same
interim-to-destination pattern already accepted for `culture_fit_score`.

Not resolved by this entry: the Feed's content and the portable Work Profile
stay open, and neither is being decided by being left out of launch scope.
(Path Intelligence / O*NET was still open when this was drafted; it was
decided the same day the entry was signed — see the backbone entry below.)

### What a D-15-conforming Situation Report returns
Sebastian, 2026-09-08; signed 2026-09-10, as drafted. **This entry gated
`BUILD_PLAN` A-4 and A-5; both are now unblocked.**

D-15 is unchanged and is not being carved out. The Situation Report conforms by
construction, in two parts.

**The payload.** Per dimension the response carries: the environment score (an
echo of the user's own answer about their own job), a **gap bucket** — one of
*feeding*, *aligned*, *straining* — and references to guidance content. The
thresholds between the three buckets are server-side and unpublished. The
response carries **no** person-side score, **no** numeric gap, and **no**
per-dimension magnitude of any kind. Three coarse buckets are deliberately too
coarse to hill-climb.

*Amended — Sebastian, 2026-09-10.* The bucket names change before any API
ships them: **{aligned, notable, straining}** — magnitude only — plus a
separate **direction** field (*under* / *over*) used purely to select guidance
content. "Feeding" implied that over-supply is good, and it often is not (a
pace above the one you can hold, more autonomy than you want). The D-15
mechanism is unchanged: the buckets stay deliberately too coarse to
hill-climb, and the pinning rule stands as written.

**The pinning.** Each report pins to a **named person-side snapshot** — the
first completed `core` sitting. A later core retake does not silently move the
report. Re-pinning happens only through an explicit "recalibrate" action the
user takes on purpose, and it is logged. A retaker therefore has nothing to
watch move: not a number, and not a report drifting behind one.

Why this is conformance and not an exception. What D-15 protects against is
optimization against ground truth, and optimizing requires a visible, repeatable
signal out of the person-side score. Buckets remove the resolution; pinning
removes the repeatability. What does vary freely is the environment side — the
user's description of their own job, which they can edit as honestly or as
carelessly as they like, and which nobody has a reason to game, because the gap
is the thing they came for.

Binding on every consumer, not only the report page. The agent (`BUILD_PLAN`
D-1) gets the same buckets and the same prohibition: instrument results inform
advice and are never recited as numbers. An agent that can be interrogated for
a person-side score is the same violation with a chat window in front of it.

### The Situation Report orders by severity tier, then expert-weighted cost
Sebastian, 2026-09-17.

Two things were wrong. The ranking was computed and then discarded — the
service emitted dimensions in fixed `DIMENSIONS` order and both frontends
render the order they are handed, so every user saw *autonomy* first whatever
their answers said. And the ranking itself was flat: all six dimensions
treated as equally costly to be wrong on.

Both are fixed. The report now lists dimensions worst-first, by:

1. **severity tier** — `straining`, then `notable`, then `aligned`;
2. **within a tier**, the weighted directional cost of the mismatch, highest
   first;
3. ties by the fixed dimension order.

The tier is the outer key on purpose. The bucket *word* is the only magnitude
a reader ever sees, so a green "Aligned" card sitting above an amber
"Straining" one would read as a contradiction no weight could justify. Tiering
confines the weights to ordering same-severity rows against each other.

The weights are the **expert-elicited priors** adopted 2026-09-17
(`causal_graph/v1_model/priors.yaml`), read through `match_scoring`. They give
the report its directional asymmetry: on *feedback*, a role blunter than the
person wants costs more than one gentler than they want, because that is what
Julie's 3-in-10 versus 7-in-10 answers say. On *decision*, one direction costs
exactly nothing — her answer there equalled her own baseline. That is a real
elicited zero, not a defect, and it is not clamped away.

**This is priors-only.** One expert's judgement converted to logit-scale
weights, with no outcome data behind it. The weights are read from the file,
not from the `model_run` / `weight_posterior` tables — nothing seeds a run in
production. There is no fallback to flat weights if the file cannot be read
(D-07: never degrade to a default); the file ships in the image, so a missing
one is a deploy defect and must surface as one.

**The payload shape does not change.** No cost, no weight, no tier, no
magnitude of any kind reaches the wire — D-15 holds exactly as written above.
Order and the existing `rank` field are the entire change.

### The Situation Report's weight source is a setting, defaulting to priors
Sebastian, 2026-09-21.

`SOLVERAH_MODEL_WEIGHTS_SOURCE` chooses where the ranking weights above come
from: `priors` (the default, and what unset also means) reads
`causal_graph/v1_model/priors.yaml` exactly as described in the entry above,
unchanged. `run` reads the latest `model_run` / `weight_posterior` row instead,
through `match_scoring.load_run_weights`.

**The default stays `priors` because production is unseeded.** Nothing writes
a `model_run` row in production today, so leaving the default as-is means this
change carries no new deploy dependency — prod's behavior does not move. `run`
mode exists so a developer with a local fitted run can see it rank the report
without a code change, ahead of the real fit that will eventually make `run`
the production default.

**No fallback.** Set to `run` with no `model_run` present, or one whose weight
rows do not match the active config, this raises rather than silently serving
the priors file — the same D-07 rule the entry above already applies to a
missing priors file. A typo in the value is treated as an error too, never as
`priors`.

### Manager Decoder is green-lit, and its playbook is template-first
Sebastian, 2026-09-08; signed 2026-09-10, as drafted.

Build it. ManagerMatch measures which management styles bring out a user's best
and then stops; the Decoder adds the missing half — a short observational
instrument about the manager the user actually has — diffs the two profiles,
and returns a private managing-up playbook. Nothing it needs is blocked: no
causal model, no priors, no company data. It is the first of the three big
items to build, for that reason.

**The playbook is template-first.** The roughly sixteen protocol cells (four
dimensions × grind directions) are LLM-drafted once, human-reviewed, and stored
as content; assembly at request time is a deterministic lookup. No per-user
generation at launch — which means no provider dependency in the request path,
no per-sitting variance, and no sentence reaching a user that nobody has read.
A per-user LLM polish pass over the assembled playbook is a fast-follow, not a
launch dependency.

Two guardrails are part of this decision rather than implementation detail. The
tone is fit, not fault — both poles of every dimension legitimate, exactly as
every other instrument is written; there is no "is your manager good" item
anywhere in it. And the manager profile is the user's private working note: it
surfaces nowhere else, and the page says so.

### The Pulse ships thin; condition experiments are the designated cut line
Sebastian, 2026-09-08; signed 2026-09-10, as drafted.

Launch ships the check-in, the trend view and event annotations (`BUILD_PLAN`
B-1 through B-4). **Condition experiments (B-5) are the designated cut line** —
the first thing to slip if the schedule needs something to give, and nothing
else in the plan depends on them.

Named now so that it does not get decided by exhaustion in the last week. The
retention loop and the model's data flywheel both start turning on check-ins
alone; experiments make the loop sharper, not functional.

The anti-nag rule is part of this scope and is not what gets trimmed: three
consecutive unanswered check-ins drop the cadence to monthly on their own, off
is always one click, and silence is treated as data rather than as something to
chase the user about.

### The core-to-8-dimension culture-preferences mapping will not be built
Sebastian, 2026-09-08; signed 2026-09-10, as drafted. **Amends §5.**

Do not build a mapping from `core` (24 items, 6 dimension scores) to the 8
culture-preference dimensions. The interim 8-dimension scorer,
`matching_service._derive_culture_preferences`, and its dependency on a
`work_pulse` submission all retire together when the causal model serves
CompanyLens. Until then CompanyLens stays coming-soon behind honest copy about
the real reason.

This amends the fourth call site in §5's "one unfinished migration, four
places". Its status there is **outstanding by design**; it is now **won't fix,
superseded**. Building the mapping is modelling work whose only product is a
scorer already scheduled for deletion — the same reasoning that says not to
seed companies to test matching (§2).

### Environment-instrument rulings: comp is skippable, first_job skips the form
Sebastian, 2026-09-10. Two rulings from the A-1 bias review.

**comp gains an explicit "not sure" option, stored as NULL.** The item's error
is non-random: isolated underpaid people do not know their market rate and
answer "about the same", so a forced answer under-reports underpayment exactly
where it is worst. The model treats a missing comp as missingness, which is
honest; a forced guess is not.

**first_job users skip the environment form entirely.** A never-employed user
has no role to describe, and forcing the form records a decline as a real
answer (the same failure shape as core-items ratification D1). They get the
needs-forward-only report built from their person-side scores — the same
rendering the plan already gives any user without an environment report.

**industry is asked, optional, NULL on not-sure, 5 placeholder levels.**
Sebastian, 2026-10-01. The match model has carried `industry` as an active
categorical confounder (it biases decision and feedback), but the form never
asked it, so every training row masked it and its weights stayed at their
prior. It is now a context item after comp, with options exactly the model
config's levels (tech, finance, healthcare, retail, other) plus "not sure /
prefer not to say", which stores NULL and leaves that row masked, the same
way comp's "not sure" does. The levels are placeholders and will grow with real
data. The form version moved to `env-v2-2026-10-01`, so a NULL on an older
row ("never asked") stays distinguishable from a NULL on a new one ("not sure").

**A user may describe one past job, after their current one.** Sebastian,
2026-10-01. Three rulings. (1) ONE past report per user, about the job before
their current or most recent one, and only once a report about the current job
exists; first_job users cannot file one (they have no job before the first).
For a between_jobs user "past" means the job before their most recent one. (2)
Past reports are exploratory-only in the first outcome fit's pre-registration
(Amendment 1); they are stored and exported but never change the Situation
Report. (3) The value exchange is a thank-you / done screen only: it says the
answers were saved, that they do not change the Situation Report, and that they
help Solverah learn which gaps matter. No "looking back" gap view, and no
numbers (D-15). Stored as `environment_reports.subject = 'past'` (ARCHITECTURE
A30); `career_status` on that row is still the filer's status that day.

### Path Intelligence / O*NET stays — backbone, not product
Sebastian, 2026-09-10. **Closes the keep-reduce-cut question formerly in §3.**

Option 1 from that question: O*NET is kept as scaffolding — "roles where these
conditions tend to exist", with a synthesis layer of Solverah's own on top —
not as a standalone payoff surface. The reasoning: the information could be
useful, and Solverah currently lacks data; cutting a working data source before
the model lane has real data would be premature. "For now" is part of the
ruling — this is a keep, not a commitment to invest, and it can be revisited
when real data exists.

What it changes now: the 6-dim → O*NET Work Context crosswalk question rides
along in Julie's priors form (`BUILD_PLAN` E-1 had it conditional on exactly
this ruling). What it does not change: Path Intelligence build work stays
parked in `BUILD_PLAN` §8 behind the Target tier, and the real-output
walkthrough the original entry called for is still the right first step
whenever that work is picked up.

### Engineering calls recorded here because they touch product surfaces
Recorded 2026-09-08. Not product decisions, and they did not need sign-off;
they belong to the engineering docs and are noted here only because a reader of
the entries above will otherwise ask. They proceed as stated unless overruled.

| # | Call | Where |
|---|---|---|
| ⚑4 | One **shared manager-profile store** serves both the Decoder's playbook and the Situation Report's manager section. Built once, in workstream C; consumed by A. A grows no second instrument and no second table. | `BUILD_PLAN` §2.1, §3.1 |
| ⚑6 | The environment report stores an **optional normalized employer name** and **displays it nowhere at launch**. It is kept for the future aggregation lane (company profiles from declared reports), which is not in launch scope and does not ship at all before the N-threshold, anonymization and legal review named in `PRODUCT_IDEAS` §3.1. | `BUILD_PLAN` §3.2 |

---

## 3. Open

*(Two entries formerly here closed 2026-09-10 and moved to §2: Path
Intelligence / O*NET — decided "backbone, not product"; and "what the
assessment's payoff is at launch" — the Situation Report, per the launch-scope
entry.)*

### Feed — content undecided
Sebastian, 2026-09-08: leaning toward "information on all the products and
companies, kind of like LinkedIn but not necessarily interacting with other
users." Currently ships a "coming soon" state.

Note for whoever builds it: with 0 companies seeded and the seeder bit-rotted, a
company-centric feed launches empty. This is a day-one-content question before it
is a build question.

### Search empty state — fixed
Was: `/search` with no query rendered *"No results found for """*. Fixed
2026-09-10 (`BUILD_PLAN` D-4): an empty or whitespace query now renders an
invitation and skips the request entirely.

---

## 4. Blocked on someone

| Blocked | On | Notes |
|---|---|---|
| ~~CompanyLens / all matching~~ | ~~The causal model ← Julie's priors + anchors~~ | Unblocked: priors returned 2026-09-17, anchors v3.1 applied 2026-09-29; build approved 2026-10-13 (§2, six-trait entry) |
| Launch / publicity gate | Sebastian + an attorney | `[ENTITY NAME]` ×8, `[ENTITY STATE]` ×6, `[EFFECTIVE DATE]` ×4, plus dispute resolution. Requires an incorporated entity — real calendar lead time, and nothing downstream moves without it. See `Solverah_IP/AGENT_DECISION_QUEUE.md`. |

---

## 5. Findings that inform the decisions above

Recorded because they were expensive to discover and are not obvious from the
code.

**One unfinished migration, four places.** `core` replaced the legacy `work_pulse`
instrument, but four call sites stayed keyed to the old one. Three were UI and
were fixed 2026-09-08 — the Intelligence page unlock gate, the CompanyLens card,
and the progress row's hard-coded ticks. The fourth is the culture-preferences
derivation (§2) — *2026-09-10: now **won't fix, superseded**; the mapping will
not be built (see §2).*

The shared symptom is worth recognising on sight: **a user is told to complete
something they have completed.** Any copy of that shape is probably a fifth
instance.

**The assessment funnel currently ends in a promise that cannot be kept.** After
2026-09-08's unlock fix, the Intelligence hub's CompanyLens card reads "Your
company matches are ready · Open CompanyLens™" and leads to a page that 400s and
blames the user for not completing Work Pulse. This is a *regression introduced
by that fix* and is the most user-visible thing outstanding. Two copy changes fix
it: the card should say coming-soon, and the CompanyLens page's locked state
should name the real reason instead of blaming the user. *(Fixed in
`BUILD_PLAN` D-0, landed 2026-09-08: both surfaces now carry the honest
coming-soon copy.)*

**Unit tests could not have caught any of this.** The frontend suite stubs the
API, and its fixtures set the legacy flags by hand — so the mocks agreed with
themselves while disagreeing with the server. `tests/e2e/real_stack.spec.ts` (real
Flask, real Postgres, real browser) is what found them, and
`tests/e2e/feature_tour.spec.ts` surveys every authenticated route the same way.
Run those before trusting a green suite about user-facing behaviour.

---

## 6. Sign-off record

Drafted 2026-09-08. **All six entries were signed by Sebastian on 2026-09-10,
as drafted, with no edits.** Each moved up into §1 or §2 the same day, per this
section's own rule; the engineering-calls note (⚑4, ⚑6) moved to the end of §2.
Nothing was rejected. The same day, Sebastian also closed the Path
Intelligence / O*NET question ("backbone, not product" — see §2), which had
been left open by the drafts.

This section stays as the record that the promotion happened and when.