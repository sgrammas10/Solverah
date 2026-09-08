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
