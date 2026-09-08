# Product ideas — deep pass, 2026-09-08

Written by an agent (Fable, high effort) at Sebastian's request while he was away:
*"analyze what product ideas I have built versus where they lack creativity or
function for the users"* and *"come up with at least 3 good unique ideas."*

**Status of everything in this file: PROPOSED.** Nothing here is decided.
`PRODUCT_DECISIONS.md` decides; this file argues. Ideas that survive Sebastian's
judgment should graduate there as entries with his name on them. This pass read
the live product surface (every page the feature tour visits), the instruments
(`causal_graph/v1_model/`, `focus_type/`, `manager_match/`, `work_pulse/`), the
model's own documents (`SOLVERAH_HANDOFF.md`, `cbm_notes.txt`,
`first_iteration_scope.txt`, `priors.yaml`, `solverah_model_config.yaml`), the
decision register mirror (D-15/16/17), `docs/LLM_ARCHITECTURE.md`, and the Path
Intelligence backend — claims below cite their sources.

---

## 0. The thesis in one paragraph

Everything Solverah owns measures **working conditions** — how a person works
(core's 6 dimensions), how their attention works (FocusType), what management
brings out their best (ManagerMatch), and a causal engine whose entire design is
*person-side score and environment-side score on the same 0–1 scale, gap →
outcome*. Yet the product narrates all of it toward one future-tense question —
"which company should you join someday" — that is blocked on priors, blocked on
company data, and (per §1 of PRODUCT_DECISIONS.md) no longer even the point.
The whitespace no competitor occupies: **turn the engine around and point it at
the job the user already has.** Diagnose the gap between their conditions and
their needs, tell them what to change, measure whether it worked, and only then
— with data the diagnosis itself generates — match them outward. Every idea
below is a piece of that turn, and the top three are: **(1) the Situation
Report** (score the current job), **(2) the actual Pulse** (longitudinal
check-ins + condition experiments), **(3) the Manager Decoder** (managing-up
playbook from ManagerMatch + a profile of the user's real manager).

A structural bonus stated up front because it reframes the roadmap: pointing
the engine at current jobs **solves the model's own two hardest open problems
as a side effect** — the missing outcome data (`cbm_notes.txt` step 4: "if
people stop using Solverah once they've found a job, we have no way to collect
follow-up data") and the company-scoring long pole (`SOLVERAH_HANDOFF.md`:
"Inputs are the long pole"). A user who describes their current employer and
their current engagement *is* a labeled (person, environment, outcome) training
row, arriving at signup instead of trickling in post-placement. The product
idea and the model's data strategy are the same move.

---

## 1. What's built, honestly assessed

### 1.1 Feature-by-feature

| Feature | What it delivers today | Where it lacks **function** | Where it lacks **differentiation** |
|---|---|---|---|
| **core (24-item Work Pulse)** | 6 dimension scores into the engine; user sees "complete — nothing to check" | The funnel's centerpiece pays off in *silence* (deliberate, D-15 — but the silence is unmitigated by any other payoff) | The measurement science is genuinely differentiated (forced-choice, graduated difficulty, Guttman confidence, bias review) — and 100% of it is invisible to the user |
| **FocusType** | Archetype + workplace recommendations + dimension bars | Result is a dead end: nothing downstream consumes it (agent context says quiz results "[Not yet available]") | Scene-based interaction (card sorts, inbox flood) is the creative high-water mark of the whole product — and it's siloed in one quiz |
| **ManagerMatch** | Archetype (5 types) + 4 dimension scores | Ends at self-knowledge: "you're The Autonomist" — with no bridge to *the manager the user actually has* | Conceptually the rarest instrument in the stack; no consumer product owns IC-side manager fit. Currently underexploited as "quiz #3" |
| **CompanyLens** | 400 for every user (expected, blocked on model ← Julie) | The UI is finished for a database that has 0 companies and a scorer being replaced | "Ranked companies with match %" is what every job board already *claims*; the causal engine's real differentiators (explanation, counterfactuals, uncertainty) aren't in the UI design at all |
| **Path Intelligence** | 3-question intake → O*NET occupations ranked by skills-centroid + job zone + title similarity (`path_scoring.py`) | Sebastian's own verdict: vague, hard to interact with | Uses the *commodity half* of O*NET (titles, skills — what every career site uses) and ignores the half that matches Solverah's thesis (Work Context / Work Values — occupation-level *conditions* data) |
| **Six career quizzes** | Static multiple-choice → GPT-4o-mini insight | Fine as top-of-funnel; results don't feed the profile the agent or briefs use | Commodity quiz content; any content site has equivalents |
| **Agent chat** | Groq-streamed "Solverah AI career assistant" with profile/resume/company RAG | Explicit TODO in `agent_service.py`: instrument results not injected — the one conversational surface knows nothing about the product's own instruments | As shipped it's a generic career chatbot, indistinguishable from a GPT wrapper |
| **Feed / Search / Jobs** | Coming-soon modal; commented-out CSV job cards; dark-theme search page inconsistent with the design system; `/search` empty state reports failure for an empty query | Dead weight on the current frame | The dashboard literally says "Here's your **job search** overview" with Job Matches / Applications stats — a job board's information architecture, without jobs |

### 1.2 Three structural observations

**The payoff inversion.** A *guest* who takes the 5-question teaser gets a
paragraph of genuinely well-written diagnosis from `work_pulse/insight_engine.py`
("you're likely absorbing context-switching costs that compound throughout the
day…"). A *registered user* who invests in the 24-item flagship gets "There's no
score to check and nothing to optimise." The deepest engagement receives the
shallowest reward. D-15 explains the absence of scores; it does not require the
absence of *everything* (see §3.1 for the payoff that threads the needle).

**The instrument already asks about the current job — the product just never
answers about it.** Read `wpQuestions.ts`: "What is one thing you would change
about your **current position**?", "how much of **your workday** feels like it
exists to support other people's processes", "after a tough stretch how do
**you** recover". The user hands Solverah a description of their present
working life, and the product's only registers for responding are (a) silence
and (b) a promise about future companies. The data collection and the value
delivery are pointed at different tenses.

**The creativity is unevenly distributed and uncomposed.** FocusType's scenes
prove the team can build instruments that feel like play rather than forms.
The model's internals (two outcome heads, confounder discipline, collider
awareness, anonymized rater packets with re-identification attacks run against
them) prove real scientific seriousness. Neither shows up anywhere a user can
see, and the five instruments never talk to each other: no surface combines
core + FocusType + ManagerMatch into one picture of a person, even though
that combination is the product's actual asset.

---

## 2. The landscape, and the seat nobody is sitting in

| Bucket | Representatives | Structural limitation |
|---|---|---|
| Job boards / marketplaces | LinkedIn Jobs, Indeed, ZipRecruiter | Unit of analysis is the *posting*; "match %" is keyword/embedding similarity; revenue depends on you applying and moving |
| Assessment publishers | 16Personalities, Truity, CliftonStrengths, Hogan | Rich narrative payoffs, but static snapshots of the *person only* — no environment side, no action loop, no learning loop |
| Hiring-side assessment | Plum, Harver (pymetrics), SHL, Criteria | The employer is the customer; the candidate is the input; nothing flows back to the worker |
| Company-signal sites | Glassdoor, Blind, Comparably, levels.fyi | Unstructured reviews and comp data about *companies only* — no model of you, no fit computation, no "for you" |
| AI career copilots | Teal, resume/interview GPT tools, LinkedIn's coach | Tools for the job-search *moment*; no proprietary measurement; user churns the day the search ends |
| Coaching | BetterUp, private coaches | Does conditions-diagnosis and manager-navigation by hand — at $200+/hr, mostly employer-paid. Validates the demand; doesn't scale down |

Two things follow.

**The empty seat:** a worker-side product that measures the person *and* their
environment on one scale, computes the fit causally (explainable, uncertainty-
carrying, counterfactual-capable), works on the job you have as well as jobs
you might take, and gets smarter from its users' outcomes. Solverah's model is
already architected for exactly this — same 0–1 latent scale on both sides,
signed gap, confounders, two outcome heads. Nobody in the table can cheaply
copy that: boards and copilots have no measurement discipline, publishers have
no environment side, hiring vendors have the wrong customer, review sites have
no person side.

**The trust asymmetry, which is a positioning weapon:** every player above
makes money when you *move* (boards, copilots) or when your *employer* buys
(assessment vendors, coaching). A worker-side conditions product can honestly
say: *we have no stake in whether you stay or go — we're the only one whose
answer can be "stay, and change these two things."* None of the incumbents can
ship that sentence. This is also why the deepest ideas below are hard to copy:
"diagnose whether your job is failing you" is structurally unsellable to the
B2B customers the incumbents depend on.

---

## 3. The ideas

Each idea states what it is, why Solverah specifically, what it needs, its
risks, and which open decisions it touches. Ideas 1–3 are the requested "three
good unique ideas." 4–6 extend them; §3.7 is a list of small sharp moves.

---

### 3.1 · IDEA 1 — The Situation Report: point the engine at the job the user already has

**What it is.** After (or independent of) the 24-item assessment, the user
describes their *current* working environment — same 6 dimensions, environment
side: how much autonomy the role actually gives, the real pace, the actual
feedback culture, their manager's style (ManagerMatch's missing other half),
plus the two confounders they can trivially report (stage/size band, comp
posture) and one more thing: the model's own `experienced` outcome question —
"how is this actually going, 1–5." Solverah computes the signed gaps and
returns a **Situation Report**: which conditions are feeding you, which are
starving you, ranked by how much each gap likely costs you, with three kinds of
guidance per gap — *change it in place* (concrete asks and experiments),
*negotiate it* (what to say, to whom), or *this one usually doesn't move*
(what that means for your ceiling here).

**Why this is the strongest single move available:**

1. **It gives the assessment its missing payoff without violating D-15.**
   D-15 (extended 08-19) forbids returning person-side scores or a per-sitting
   narrative — "a gradient a retaker can watch move." The Situation Report's
   output varies with the *environment* inputs, which the user edits freely and
   honestly (there is nothing to game — it's their own job). The person-side
   scores stay sealed inside the engine. The report is *about the world, not
   about the score*. A retaker of core changes the report only through the
   sealed engine, never through a visible number. This needs a careful read
   against the register's exact wording, but the design intent of D-15 —
   protect ground-truth integrity from optimization — is preserved, arguably
   better than silence is preserving it (silence gives users a *reason* to
   retake out of confusion).
2. **It converts the model's two hardest open problems into byproducts.**
   (a) *Outcome data:* `cbm_notes.txt` step 4 says the learning loop starves
   because placed users leave. Inverted, every employed user arrives already
   "placed": person scores + declared environment + `experienced` 1–5 = a
   complete training row on day one. The OrderedLogistic outcome head for the
   1–5 label is already built (`SOLVERAH_HANDOFF.md`). (b) *Company data:*
   the handoff names the company-scoring pipeline the #1 unsolved long pole
   and blesses wisdom-of-crowds "for OBSERVABLE quantities (e.g., scoring
   companies)." Employees describing their own employer on the anchored rubric
   *is* crowd-scoring companies — the "scraped→declared upgrade path" gains a
   third, best channel: **experienced-declared**. Enough users at a company =
   a company profile no scraper could write, on exactly Solverah's 6 axes.
3. **It measures the unmeasurable confounder.** The handoff lists
   `manager_quality` as documented-but-excluded because scraping can't see it.
   The user *can*. A current-job report captures the manager dimension
   first-hand — the single condition the org-psych literature (and folk
   wisdom: "people leave managers") weights most.
4. **Zero cold start.** Needs no seeded companies, no priors even — a
   rules-scored interim version (gap magnitudes + fixed guidance templates,
   exactly the `insight_engine.py` pattern scaled up) ships before Julie's
   numbers land, and the causal model slots in underneath later, the same
   interim→destination pattern already accepted for `culture_fit_score`.
5. **It is the concrete form of §1's open question.** PRODUCT_DECISIONS §1
   asks whether the spine is "what conditions make you effective, how far is
   your situation from them, and what do you change." This is that sentence
   as a screen. Building a thin version is also the cheapest way to *settle*
   §1 — put it in front of five users next to Path Intelligence's output and
   see which one they screenshot.

**What it needs.** An environment-side self-report instrument (the anchored
0–1 rubric built for the two human raters is most of the item-writing already
done — `Solverah_Company_Rating_Rubric_v2.docx` anchors, reworded second
person); the existing sliders/static-form machinery (the MVP
culture-preferences decision already chose this interaction); a scoring rule
(interim: rules; destination: the model); guidance content per
dimension×direction (12 cells, LLM-draftable, human-reviewed once — static
templates, not per-user generation, so cheap and D-15-clean).

**Risks, honestly.** Self-report of one's own employer is biased (halo when
happy, venom when not). Three mitigations already native to the stack: the
model carries per-evidence confidence and source flags by design; `appeal` vs
`experienced` teaches exactly this skepticism; and for the *personal* report
bias barely matters (a user's felt autonomy IS the datum), only for the
*aggregated company profile*, which should require N≥k per company and show
its confidence. Second risk: employees describing employers is sensitive —
aggregation thresholds and anonymization before anything is shown about a
company (the packet pipeline's anonymization + re-identification-attack
discipline is literally in-house expertise), and a legal-review hook before
the aggregated view ships. Third: "describe your job" is real user effort —
mitigate by making it the *bridge* at assessment completion ("24 questions
about you. Now 10 about your job, and we'll show you the gap"), which also
fixes the funnel's dead end.

**Decisions it touches.** §1 OPEN (this is its test), D-15 (needs Sebastian's
read), §2 matching-blocked (unaffected — this runs beside it), Julie (her
elicitation covers person↔company gaps; identical machinery).

---

### 3.2 · IDEA 2 — The actual Pulse: longitudinal check-ins and condition experiments

**What it is.** The flagship is named **Work Pulse** and is taken once. Make
the name true. A weekly (user-chosen cadence) 60-second check-in — 3 rotating
items from the teaser's five friction dimensions (fragmentation,
sustainability, environmental friction, recognition, pace) plus the
`experienced` 1–5 — building a personal time series: energy and friction
trends, annotated with events the user logs in one tap ("new manager",
"went remote", "reorg"). On top of it, **condition experiments**: the
Situation Report's "change it in place" guidance becomes a two-week
experiment card ("protect two 90-minute blocks; ask for written context
before 1:1s"), and the pulse measures the before/after.

**Why Solverah, why it wins.**

1. **Every competitor is a snapshot; conditions are a time series.** The
   assessment publishers sell you a PDF that is stale the day your team
   changes. A trend line of *your* sustainability score crossing into the red
   after the reorg is a product only a longitudinal instrument can make, and
   it is the single most shareable/retentive artifact in this space
   ("here's my quarter, graphed").
2. **It is the model's step-4 answer, permanently.** `cbm_notes.txt` names a
   "periodic check-in" as the needed post-placement signal. This is that,
   built as a product people *want* rather than a survey they tolerate.
   Within-person time series are also causally precious: each user becomes
   their own control, which is far stronger evidence for "does closing an
   autonomy gap raise engagement" than any cross-sectional comparison.
3. **Experiments are the "development" in career-development platform.**
   Advice products end at advice. A loop that says *try this for two weeks —
   we'll measure* is what BetterUp charges four figures for, delivered by
   software, and it generates intervention→outcome pairs no competitor has
   any mechanism to collect.
4. **It solves the Feed's day-one-content problem from the user's own data.**
   §3 of PRODUCT_DECISIONS notes a company-centric feed launches empty. A
   feed whose units are *your* pulse trends, experiment results, milestone
   recaps ("3 months since your assessment — what moved") is full on day 8
   with zero companies seeded, and is a reason to return that no job board
   has between searches.

**What it needs.** The teaser items already exist and are rules-scored (no
LLM dependency); a check-in table + one chart; notification/email cadence
(Celery + Resend already in place); experiment card content (derivable from
the same 12 guidance cells as Idea 1). Genuinely small surface area for what
it buys.

**Risks.** Check-in fatigue is real: keep it to 60 seconds, default to
weekly, let silence be data (a skipped month is itself a signal, and the
product should say so gracefully rather than nag). The chart must degrade
gracefully at 2 data points. Retention products live or die on the first
returned week — the second check-in must visibly *add* something (even
"two points make your first trend").

**Decisions it touches.** Feed content (§3 OPEN — this is a candidate
answer); the launch-v1 question (a thin version — check-in + trend, no
experiments — is launch-sized).

---

### 3.3 · IDEA 3 — The Manager Decoder: from "know your needs" to "navigate your actual manager"

**What it is.** ManagerMatch today measures which management styles bring out
the user's best and stops. Add its missing other half: a short *observational*
instrument about the user's real manager — not "is your manager good" but
behaviorally anchored items in the exact style of `manager_match/questions.py`
("When you're stuck, your manager typically: walks you through it / points
you at the goal and steps back"). Diff the two profiles and generate the
**Managing-Up Playbook**: where you and this manager naturally mesh, where
you'll grind, and — per grind point — the concrete protocol: how to ask for
the feedback cadence you need from a manager of this style, how to pitch for
autonomy to someone who checks in daily, what to put on the 1:1 agenda, the
actual sentences. LLM-generated over the two structured profiles (funded per
§2: "it's so cheap"), reviewed templates as the guardrail.

**Why Solverah, why it wins.**

1. **The manager relationship is the highest-leverage condition and the most
   underserved.** An enormous share of "I need a new job" is "I need a
   different manager dynamic." Every product for this relationship serves the
   *manager* (or HR). A worker-side decoder has no incumbent — and the B2B
   players can't follow (no HR department buys "decode your boss" for ICs).
2. **It's the fastest of the big ideas to ship.** No causal model, no
   company data, no priors. Two 15-item instruments (one exists), a diff, and
   an LLM layer over proprietary structured substrate — which is what makes
   it a *defensible* LLM feature rather than a GPT wrapper: the value is in
   the two profiles, not the prose.
3. **It rescues ManagerMatch from "quiz #3" status** and gives the
   Intelligence hub a second real payoff for launch v1 (per §3 OPEN, the
   honest v1 may be FocusType + ManagerMatch + quizzes — this multiplies
   ManagerMatch's value inside that exact scenario).
4. **It compounds with Ideas 1–2:** the manager profile is one section of the
   Situation Report; a playbook protocol is a natural condition experiment
   ("try the written-context ask for two weeks"); manager changes are pulse
   annotations.

**What it needs.** ~12–15 observational items (an afternoon of item-writing in
an established house style + the existing bias-review discipline); a diff
rule; playbook content templates per style×need cell; one results page.

**Risks.** Tone: it must never read as "your manager is deficient" — the
instrument philosophy already has the answer (both poles legitimate, fit not
fault, the same frame as every other dimension). Privacy: the manager profile
is the user's private working note; it must never surface anywhere else (and
say so). Accuracy: the user's read of their manager is subjective — fine,
because the playbook operates on the *perceived* relationship, which is the
one the user actually lives in.

**Decisions it touches.** None blocked. This is the largest idea in the file
that is entirely unblocked today.

---

### 3.4 · IDEA 4 — Offer & Interview Due Diligence: CompanyLens for the company in front of you

**What it is.** CompanyLens waits on a seeded, scored company database. Flip
the unit of analysis: score **the specific opportunity the user brings** — a
recruiter ping, an interview loop, an offer in hand. Three parts: (a) a
**probe pack** — for each of the user's biggest must-have conditions,
interview questions crafted to *detect* that condition from the inside
("ask how the last disagreement with their manager got resolved" detects
feedback culture better than "what's the culture like?"); (b) a 2-minute
**post-interview capture** of what they observed, on the same environment
items as Idea 1; (c) a **verdict with error bars** — the engine scores this
one company from user-gathered evidence, says what it still can't know, and
compares it against the user's *current* situation report: "this offer moves
your two starving conditions; it likely worsens pace."

**Why it wins.** It deletes the cold-start dependency (the user supplies the
company); it's matching at the moment of highest stakes and willingness to
pay (an offer decision is worth $20 in a way browsing never is — this is the
most natural Pro surface in the file); "compare the offer against your
current job, dimension by dimension, with uncertainty stated" is a screen no
job board can render because they have neither side of the comparison. And
every evaluated company quietly adds an interviewer-observed evidence row to
the company store — a third crowd-fed channel beside scraped and
employee-declared, building toward the browsable CompanyLens organically.

**What it needs.** Probe-pack content per dimension (LLM-draftable against the
rubric anchors, human-reviewed once); the Idea-1 environment items reused
verbatim; interim rules scoring; the JD-ingestion pipeline that already
exists (`job_descr_LLM/`) to pre-fill what a posting reveals.

**Risks.** Requires the user to do homework mid-interview-process — mitigated
by making the probe pack valuable *before* any capture is asked for (it's a
good artifact on its own; people screenshot good interview questions).
Low-evidence verdicts must show their uncertainty honestly or the feature
becomes astrology — the model's confidence machinery is the native answer.

**Decisions it touches.** §2 "do not seed companies to test matching" (fully
compatible — no seeding); the causal-model timeline (interim rules OK).

---

### 3.5 · IDEA 5 — O*NET redeemed: conditions backbone, not title ranking

**What it is.** A concrete third option for the §3 OPEN "keep, reduce, or
cut" question. `path_scoring.py` today ranks occupations by skills-centroid
similarity + job-zone delta + title similarity — the commodity computation.
But O*NET also publishes **Work Context** (autonomy proxies like "freedom to
make decisions," time pressure, consequence of error, telework, social
interaction) and **Work Values** per occupation — occupation-level
*conditions* data. Re-aim the feature: map the user's condition profile onto
Work Context/Values and answer "**in which kinds of work are your must-have
conditions structurally common — and rare?**" Output 3 environments (not 15
ranked titles), each with: why these conditions cluster there, example
occupations as *illustrations* rather than verdicts, and — tying into Idea 4
— what to probe for in interviews, since occupation-level data describes the
average, never the team. The LLM synthesis layer (`path_narrative.py`)
already exists to write this in Solverah's dimension language.

**Why.** It converts the feature Sebastian doesn't believe in from answering
the question the product is moving away from ("what title next") into
evidence for the question it is moving toward ("where do my conditions
live") — using data already integrated and paid for. If after the
end-to-end walkthrough (the decisions doc's named next step) the output is
still vague, **cut it without guilt** — with Ideas 1–4 standing, nothing
else depends on it, which is the cut criterion §3 asked for.

**What it needs.** Work Context/Values endpoints in `onet_client.py` (small);
a crosswalk from Solverah's 6 dims to O*NET context scales (a modeling
judgment — Julie-adjacent, worth one async question on her form's pattern);
a rewritten narrative prompt.

**Risks.** The crosswalk could be judged invalid — in which case the honest
answer is the cut, and this idea's framing loses nothing by saying so.

---

### 3.6 · IDEA 6 — The portable Work Profile: a user manual that travels

**What it is.** One generated, user-owned page: "**How I work best**" —
synthesized from FocusType + ManagerMatch + the quizzes + (if taken) the
environment report; explicitly *not* from core's sealed scores. What feeds
me, what starves me, how to hand me feedback, when I do my best work.
Generated **once**, frozen until the user explicitly regenerates, exportable
and shareable by link — to a new manager in week one, to a team's
onboarding doc, alongside (never inside) a job application.

**Why.** The "personal user manual" is an existing workplace practice that is
currently pure vibes — self-written, unmeasured. An instrument-backed one is
credible in a way a self-description isn't, and it makes the user the
product's distribution channel: every shared manual is a Solverah artifact in
a workplace, seen by exactly the people (managers, teammates) most likely to
want their own. It also gives assessment work a payoff that is *social*
rather than introspective — a reason to finish that "read about yourself"
never provides.

**D-15 note, stated plainly.** This idea lives next to the sharpest
constraint in the register. It is designed to comply — sources are the
non-ground-truth instruments; generation is one-shot on explicit request,
so there is no per-sitting gradient; nothing numeric is shown. But whether
"a synthesis that excludes core" honors the *spirit* of the 08-19 extension
is exactly the kind of call the register says is Sebastian's, not an
agent's. Treat this idea as **decision-required before any build**.

---

### 3.7 · Small sharp moves (cheap, mostly unblocked)

1. **Teach the agent its own product.** `agent_service.py` has the TODO;
   FocusType and ManagerMatch results are sitting in the profile document.
   Injecting them turns the only conversational surface from generic to
   "the assistant that knows how you work." Hours, not days — and it makes
   every conversation a demo of the instruments. (Also fits the deferred
   conversational-culture-capture decision: the agent is where that
   eventually lives.)
2. **End the assessment with a bridge, not a wall.** Even before Idea 1
   ships, "That's everything we need" should hand the user a *next
   verb* — start FocusType, or the environment report when it exists. The
   funnel currently ends in a locked room (the §5 regression makes it
   worse: a promise that 400s).
3. **The trust page.** The compliance mirror itself suggests static
   candidate-facing transparency ("how this is computed, what it doesn't
   mean") is D-15-compatible. Solverah's integrity story — can't-game-it
   instruments, uncertainty-honest model, two-rater blind calibration,
   re-identification attacks on its own anonymization — is a *marketing
   asset* no competitor in the table can write truthfully. One static page:
   "Why you can trust this." It costs copy.
4. **Search empty state** — already in PRODUCT_DECISIONS §3; one string.
   While there: the search page's dark slate styling is from an older
   design system and reads as a different product.
5. **Quiz results into the profile document** so the agent (move 1) and any
   future brief can cite them; six instruments' answers currently evaporate.
6. **Dashboard reframe when the spine lands** — "your job search overview"
   (Job Matches / Applications stats, Browse Jobs CTA) is a job board's IA
   without jobs; the working-life frame (current conditions, trend, next
   experiment) is what Ideas 1–2 fill it with. Copy + card swaps, not a
   rebuild — but sequence it *after* the §1 decision, since it embodies it.

---

## 4. How it composes: one loop instead of six features

**Measure** (core + FocusType + ManagerMatch + environment report) →
**Diagnose** (Situation Report: gaps, ranked) → **Act** (playbook protocols,
condition experiments, probe packs) → **Re-measure** (the Pulse) → **Learn**
(outcome rows and declared-environment rows update the posteriors — the
handoff's blend-toward-data step 4, finally fed) → **Match** (offer
evaluations first; browsable CompanyLens when the crowd-fed company store
earns it) → back to **Measure** as life changes.

Every existing feature has a seat: FocusType and ManagerMatch feed Measure
and the playbooks; the quizzes are top-of-funnel Measure-lite; the agent is
the conversational skin over the loop; the Feed is the loop's diary; Path
Intelligence (if kept) is Match's zoomed-out lens; CompanyLens is Match's
end state rather than the product's premise. The current architecture —
instruments narrating toward a blocked matcher — becomes an engine where
each stage's output is the next stage's input and the model gets smarter at
every turn of the crank. That compounding is the moat: a competitor can copy
any single screen; they cannot copy the loop's data without building the
whole loop.

---

## 5. What this means for launch v1 (input, not a decision)

PRODUCT_DECISIONS §3 says launch v1 may honestly be FocusType + ManagerMatch +
six quizzes — "but that should be chosen, not discovered." These ideas give
that choice a shape with three honest tiers:

- **Floor (all unblocked):** FocusType + ManagerMatch + quizzes + small moves
  1–5 — instruments with real payoffs, an agent that knows them, no broken
  promises. A coherent "know how you work" product.
- **Floor + one bet:** add the interim rules-scored **Situation Report**
  (Idea 1) and the completion bridge — the assessment finally pays off, and
  the product's differentiated sentence ("we diagnose the job you have")
  exists at launch. My read: this is the smallest launch that a user would
  describe to a friend in Solverah's own terms rather than as "a quiz site."
- **Floor + bet + loop-starter:** add the thin Pulse (check-in + trend, no
  experiments). Retention exists from day one; the model's data flywheel
  starts turning at launch rather than after it.

The fix for the §5 regression (the CompanyLens card promising matches that
400) stays urgent under every tier — two copy changes, already specified in
PRODUCT_DECISIONS.

---

## 6. Questions this file puts to Sebastian

1. **§1 OPEN:** Does the Situation Report describe the spine you want? (If
   yes, §1 can close with a concrete referent instead of a framing.)
2. **D-15:** Is a report *about the environment gap* — person-side scores
   sealed, output varying only with environment inputs the user edits freely
   — within the rule? (Gates Idea 1's full form; the environment report
   alone violates nothing.)
3. **ManagerMatch:** Green-light the Decoder as the next build? (Nothing
   blocks it; it is the best value-per-week available today.)
4. **O*NET:** Run the decisions-doc walkthrough, then choose: conditions
   backbone (3.5) or cut. (The middle "keep as-is" seems dominated either way.)
5. **The manual (3.6):** In or out, as a decision — it should not drift into
   existence through copy.
6. **Julie's form:** Worth appending the environment-side self-report anchors
   and the 6-dim→Work-Context crosswalk to her async queue, since both are
   elicitation of the same kind her form already does? (Respects
   async-only; one form, not a second sitting.)

*Filed 2026-09-08. No code was written for any of this.*
