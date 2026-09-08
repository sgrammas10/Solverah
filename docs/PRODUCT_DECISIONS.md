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

Last updated 2026-09-08.

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

### OPEN — what the career-development spine actually is

Raised 2026-09-08, unanswered. Do not build against either reading yet.

The instruments Solverah owns — Work Pulse (how you work, 6 dimensions),
FocusType (attention, focus, energy), ManagerMatch (which management styles bring
out your best), and the causal model (environment fit) — all measure **working
conditions**, not occupations. That suggests the differentiated question is
"*what conditions make you effective, how far is your situation from them, and
what do you change*" rather than "*what job title next*".

The counter-consideration is that this is a framing proposed by an agent reading
the code, not a market judgement. It is recorded so it can be argued with, and it
should be settled by Sebastian rather than inherited.

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

### CompanyLens is blocked on the causal model, and that is expected
Sebastian, 2026-09-08.

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

### Do not seed companies to test matching
Sebastian, 2026-09-08. The interim `culture_fit_score` scorer is being replaced,
so measuring its output measures something about to be deleted. Revisit when the
causal model lands. (The xlsx company seeder is separately bit-rotted — 14 of 20
rows parse as "Unknown" — which will need fixing before any seeded run.)

### `Solverah_IP/` stays tracked in this repo
Sebastian, 2026-09-08. ~6 MB tracked (the 32 MB figure was on-disk, dominated by
untracked `node_modules`). Untracking it would pull the ground-truth dataset out
of version control and break the three scheduled packet-pipeline tasks that
commit into that tree. If revisited, the answer is a separate repository with
history preserved, after pausing the pipeline — never a `.gitignore` entry, which
would be a no-op on already-tracked files.

---

## 3. Open

### Path Intelligence / O*NET — keep, reduce, or cut
Sebastian is **sceptical**, 2026-09-08: *"idk if I am going to keep or use it —
the information is hard to interact with and did not seem to give promising
insights because it is so vague."*

The feature works technically: a three-question flow ("What kind of move are you
looking for?" — stay in field / adjacent / fresh direction) producing "career
paths scored against your skills and work profile, with plain-language guidance".
It is badged **Pro**, and it needs nothing from the blocked model.

The structural argument for the scepticism: O*NET is an *occupational taxonomy* —
~1,000 job titles with generic descriptions. It describes occupations in general,
never a person in particular, so scoring against it yields ranked dictionary
entries. It is also a commodity: every career site has the same data.

Three options, none chosen:
1. **Backbone, not product** — keep O*NET as scaffolding for "roles where these
   conditions tend to exist", with a synthesis layer of Solverah's own on top.
   An LLM is already funded (§2).
2. **Cut it** — if nothing else depends on it, it is maintenance plus a footer
   attribution for a feature nobody believes in.
3. **Keep as-is** — only if the output is better than remembered.

**Next step if this is picked up:** complete the flow end to end in the real
browser and look at the actual output before deciding. Neither Sebastian nor any
agent has judged it against the real thing recently.

### What the assessment's payoff is at launch
Open, and consequential. Today a user answers 24 questions, is told there is "no
score to check and nothing to optimise", and lands on a dashboard whose one
matching feature is gated. Work Pulse's payoff was assigned to CompanyLens (§2,
blocked) and the alternative destination (Path Intelligence) is in doubt (above).

The features that *do* deliver something today are FocusType, ManagerMatch and
the six career quizzes. Launch v1 may honestly be those — but that should be
chosen, not discovered.

### Feed — content undecided
Sebastian, 2026-09-08: leaning toward "information on all the products and
companies, kind of like LinkedIn but not necessarily interacting with other
users." Currently ships a "coming soon" state.

Note for whoever builds it: with 0 companies seeded and the seeder bit-rotted, a
company-centric feed launches empty. This is a day-one-content question before it
is a build question.

### Search empty state
Minor, unowned. `/search` with no query renders *"No results found for """* —
reporting failure where it should invite a query. Cosmetic, cheap, first thing a
user sees on that route.

---

## 4. Blocked on someone

| Blocked | On | Notes |
|---|---|---|
| CompanyLens / all matching | The causal model ← Julie's priors + anchors | Julie has the hypothesis form; asked 2026-09-06, chased 2026-09-08 |
| Launch / publicity gate | Sebastian + an attorney | `[ENTITY NAME]` ×8, `[ENTITY STATE]` ×6, `[EFFECTIVE DATE]` ×4, plus dispute resolution. Requires an incorporated entity — real calendar lead time, and nothing downstream moves without it. See `Solverah_IP/AGENT_DECISION_QUEUE.md`. |

---

## 5. Findings that inform the decisions above

Recorded because they were expensive to discover and are not obvious from the
code.

**One unfinished migration, four places.** `core` replaced the legacy `work_pulse`
instrument, but four call sites stayed keyed to the old one. Three were UI and
were fixed 2026-09-08 — the Intelligence page unlock gate, the CompanyLens card,
and the progress row's hard-coded ticks. The fourth is the culture-preferences
derivation (§2) and is outstanding by design.

The shared symptom is worth recognising on sight: **a user is told to complete
something they have completed.** Any copy of that shape is probably a fifth
instance.

**The assessment funnel currently ends in a promise that cannot be kept.** After
2026-09-08's unlock fix, the Intelligence hub's CompanyLens card reads "Your
company matches are ready · Open CompanyLens™" and leads to a page that 400s and
blames the user for not completing Work Pulse. This is a *regression introduced
by that fix* and is the most user-visible thing outstanding. Two copy changes fix
it: the card should say coming-soon, and the CompanyLens page's locked state
should name the real reason instead of blaming the user.

**Unit tests could not have caught any of this.** The frontend suite stubs the
API, and its fixtures set the legacy flags by hand — so the mocks agreed with
themselves while disagreeing with the server. `tests/e2e/real_stack.spec.ts` (real
Flask, real Postgres, real browser) is what found them, and
`tests/e2e/feature_tour.spec.ts` surveys every authenticated route the same way.
Run those before trusting a green suite about user-facing behaviour.

---

## 6. DRAFT — awaiting Sebastian's sign-off

**Drafted 2026-09-08. Nothing in this section is decided yet.** The entries are
written the way they would read once approved — same register, carrying the
name and date they would carry — so that signing one off is an edit rather than
a rewrite. On approval each entry moves up into §1 or §2 and this section
shrinks; anything rejected gets a line here saying so and why. Until then these
are not decisions and nothing should be built against them, per this file's own
rule about open questions.

`docs/BUILD_PLAN.md` §0.1 is the chunk that closes this section. The Situation
Report payload entry below is the one with a build waiting on it: A-4 and A-5
do not start until it is signed.

---

### DRAFT — The spine is conditions: diagnose them, improve them, and match as one output
Sebastian, 2026-09-08. *Awaiting sign-off.* **Closes the open question in §1.**

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

The counter-consideration recorded in §1 — that the conditions framing was
proposed by an agent reading the code, not by the market — stands, and stays
worth testing. The cheapest test is the Situation Report itself in front of
real users. If the diagnosis is not what they care about, this is the entry to
reopen.

### DRAFT — Launch scope is the top three ideas plus the small sharp moves
Sebastian, 2026-09-08. *Awaiting sign-off.* **Also closes "what the
assessment's payoff is at launch" in §3.**

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

Not resolved by this entry, and still open: Path Intelligence / O*NET (§3 —
which still wants the walkthrough of the real output before keep-or-cut), the
Feed's content, and the portable Work Profile. None of the three are in launch
scope, and none of them are being decided by being left out of it.

### DRAFT — What a D-15-conforming Situation Report returns
Sebastian, 2026-09-08. *Awaiting sign-off.* **This entry gates `BUILD_PLAN`
A-4 and A-5 — the payload and the API wait on it.**

D-15 is unchanged and is not being carved out. The Situation Report conforms by
construction, in two parts.

**The payload.** Per dimension the response carries: the environment score (an
echo of the user's own answer about their own job), a **gap bucket** — one of
*feeding*, *aligned*, *straining* — and references to guidance content. The
thresholds between the three buckets are server-side and unpublished. The
response carries **no** person-side score, **no** numeric gap, and **no**
per-dimension magnitude of any kind. Three coarse buckets are deliberately too
coarse to hill-climb.

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

### DRAFT — Manager Decoder is green-lit, and its playbook is template-first
Sebastian, 2026-09-08. *Awaiting sign-off.*

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

### DRAFT — The Pulse ships thin; condition experiments are the designated cut line
Sebastian, 2026-09-08. *Awaiting sign-off.*

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

### DRAFT — The core-to-8-dimension culture-preferences mapping will not be built
Sebastian, 2026-09-08. *Awaiting sign-off.* **Amends §5.**

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

### DRAFT — Engineering calls recorded here because they touch product surfaces
Recorded 2026-09-08. Not product decisions, and they do not need sign-off; they
belong to the engineering docs and are noted here only because a reader of the
entries above will otherwise ask. They proceed as stated unless overruled.

| # | Call | Where |
|---|---|---|
| ⚑4 | One **shared manager-profile store** serves both the Decoder's playbook and the Situation Report's manager section. Built once, in workstream C; consumed by A. A grows no second instrument and no second table. | `BUILD_PLAN` §2.1, §3.1 |
| ⚑6 | The environment report stores an **optional normalized employer name** and **displays it nowhere at launch**. It is kept for the future aggregation lane (company profiles from declared reports), which is not in launch scope and does not ship at all before the N-threshold, anonymization and legal review named in `PRODUCT_IDEAS` §3.1. | `BUILD_PLAN` §3.2 |
