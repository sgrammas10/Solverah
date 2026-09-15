# Environment-side items — Bias Review (A-1)

Reviewed `work_pulse/situation_items.py` (12 dimension items + 3 context items) in the
tradition of `manager_match/MANAGER_PROFILE_ITEMS_BIAS_REVIEW.md` and
`causal_graph/v1_model/ASSESSMENT_ITEMS_BIAS_REVIEW.md` — same rubric, same
structural-read caveat: **no pilot data exists, so nothing here is empirical.** This is
what should be fixed *before* a pilot, so the pilot measures the items rather than
re-discovering these. Nothing in `Solverah_IP/` was modified; the rubric was read only.

**The standard applied**, restated from the rater rubric's own first gate: *neither pole is
better*. "Directed" is not worse than "self-directed", "steady" not worse than "fast". A
lean means the item smuggled in a socially-desirable answer. To that, this instrument adds
three requirements:

* **Anchor-order balance.** On a five-point anchored scale the analogue of the
  manager-profile positional key: the high band must not sit systematically at the top or
  the bottom of the option list (Finding 1).
* **The rubric's `keep_distinct` guardrails bind the user-facing wording**, not only the
  raters. They were written because two blind raters bled these dimensions into each
  other; an item that reintroduces a bleed reintroduces it for every user at once
  (Finding 4).
* **Descriptive, not evaluative.** Twelve items describe what the role *offers*. Exactly
  one item in the whole instrument — `experienced` — asks for a verdict, because it is the
  model's outcome node, and it is asked last (Finding 9).

Nine findings, kept separate: **anchor order** (1), **the perception problem** (2 — the
characteristic failure of this instrument and the largest risk), **residual desirability
skew** (3), **cross-dimension bleed** (4), **midpoint behaviour** (5), and **who the items
exclude or expose** — the comp item, `first_job`, industry/remote shape, and the outcome
item's halo (6–9). An **integration note** at the end records a live conflict with A-3 that
is not a bias problem but must not be lost.

---

## Finding 1 — anchor-order balance: PASS, exact

Counts computed from the item table, not eyeballed
(`test_anchor_order_is_balanced_within_every_dimension`):

| Dimension | items | low band listed first | high band listed first |
|---|---|---|---|
| autonomy | 2 | 1 | 1 |
| pace | 2 | 1 | 1 |
| collaboration | 2 | 1 | 1 |
| feedback | 2 | 1 | 1 |
| innovation | 2 | 1 | 1 |
| decision | 2 | 1 | 1 |
| **overall** | **12** | **6** | **6** |

**What it buys.** A respondent who straight-lines any option position — first, last, or
middle — scores **exactly 0.5 on all six dimensions**, because each dimension's two items
run in opposite directions. Asserted for all five positions by
`test_straight_lining_any_position_lands_every_dimension_on_the_midpoint`. This is the
midpoint property `mp-q16` was added to buy on the manager-profile side, here by
construction rather than by count.

It also means satisficing produces **silence, not a wrong diagnosis**: 0.5 everywhere
lands inside A-3's ±0.15 aligned band for any plausible person-side profile, so the report
comes back with nothing to say instead of confidently naming a gap that isn't there. That
is the right failure direction for a product whose whole claim is diagnosis.

**The cost, stated honestly.** Alternating scale direction is a known source of respondent
error in the survey literature — the reversed-item artifact. Two things make it much
smaller here than it would be on an agree/disagree Likert: every option is a substantive
description that has to be read to be chosen (there is no "agree" shortcut to pattern-match
on), and the two items of a dimension are adjacent, so the reversal is visible rather than
buried. **This is a real trade, not a free win**, and the pilot should look for it: a
reversal artifact shows up as an implausible within-dimension disagreement (one item at
0.9 and its partner at 0.1) at a rate above the base rate for genuinely mixed environments.

---

## Finding 2 — the environment score is a perception, and the report treats it as a fact

**This is the instrument's characteristic failure and it is not fixable by wording.** It
is the analogue of halo/horn on the manager-profile side, and it is larger here.

The Situation Report subtracts a *sealed, instrumented* person-side score from a *live,
self-reported* environment score and calls the difference a gap. But the environment score
is not a measurement of the job; it is the user's description of the job, produced by a
person whose own dispositions are the very thing being differenced out. Someone who needs
high autonomy is more likely to notice and resent the approval step. The gap and the
perception are therefore not independent, and part of every gap this product reports is
the user's own reading of the job rather than the job.

Three things make this smaller than it first looks, and one makes it worse:

* **The items are behavioural, not evaluative.** "Most decisions go up for sign-off before
  you act" is checkable; "I don't have enough freedom" is not. Every one of the twelve is
  written at the checkable level, on purpose.
* **The product's claim is already scoped to this.** PRODUCT_DECISIONS §2 says the
  environment side is "the user's description of their own job, which they can edit as
  honestly or as carelessly as they like". The report is a diagnosis of *your experience of
  the conditions*, and A-7's "what this is / isn't" footer is where that has to be said
  out loud. It is currently the only place it will be said.
* **Both poles being legitimate removes most of the motive.** There is no score to inflate
  and no reward for describing the job as better or worse than it is.
* **Worse:** the same correlation contaminates the *training* data, not just the report.
  E-4 assembles `(person score, environment score, experienced outcome)` rows from exactly
  these fields. If the environment score is partly a function of the person, the causal
  model is fitting a relationship that is partly circular. This belongs in §5's model
  design as a known limitation of self-reported environment rows, not as a surprise at
  fit time.

**Recommended measurement, cheap and decisive.** Where two users report the same
`employer_name_normalized` (⚑6 stores it and displays it nowhere), compare their
environment scores. Between-user variance within one employer that exceeds between-employer
variance is a direct read on how much of this score is perception. That is a query, not a
study, and the storage for it already exists.

---

## Finding 3 — residual desirability skew is dimensionally patterned, and it pulls high on three dimensions

Audited pole by pole. Three dimensions are clean, three carry a residual, all three in the
same direction.

**Clean:**

* **pace** — "an intense week" and "an unhurried week" each carry a cost in the other's
  eyes. Deliberately worded so: an earlier draft had "calm and sustainable" at the low
  pole, which is the rubric's phrase and is straightforwardly the good job. It was cut.
* **collaboration** — "heads-down and alone" and "constant pairing … a team you are
  working alongside all day" both have committed advocates, and neither is described in
  terms of how good the relationships are (which is also Finding 4's requirement).
* **autonomy** — mostly clean, but see below.

**Residual, all pulling toward the high band:**

* **feedback.** "Delivered straight and unsoftened … open disagreement is routine" reads as
  brave and high-performing in a tech-adjacent audience; "cushioned or indirect … open
  disagreement is rare" reads as conflict-avoidant. **This is not repairable in the
  wording**, and the attempt is actively dangerous: the obvious fix is to make the low pole
  sound considerate, which reintroduces warmth to an axis the rubric spent two revisions
  removing it from (`feedback._note`, edits 2 and 3 — a warmth descriptor at 0.1 with no
  counterpart at 0.9 meant supportiveness evidence could only push a score *down*). The
  asymmetry is accepted here for the same reason the rubric accepted it: every available
  fix is worse than the defect.
* **decision.** "Data-driven" reads rigorous, "instinct" reads unserious. Partly mitigated
  by using the rubric's own legitimating vocabulary at the low pole — "taste, experience
  and vision", "a well-argued judgement call" — rather than "gut feel". Residual remains.
* **innovation.** "Creating things that don't exist yet" carries more status than
  "improvement and scale". Mitigated by wording the low pole as a description of the work
  rather than as a ceiling ("making something that already exists work better"), never as
  "no new work is allowed".

**Also worth naming on autonomy:** "changing it takes permission" (`env-autonomy-2`, low
band) is the most negatively-loaded phrase in the twelve. It is the rubric's own content
("most decisions need sign-off") and there is no neutral synonym for permission, so it
stands — but it is the single most likely item to be under-endorsed by someone who does
have to ask.

**The quantitative consequence, so this is falsifiable.** Each dimension is the mean of two
items, so **one item shifted one band moves the dimension score by 0.10, and both items
shifted moves it by 0.20.** A-3's aligned band is ±0.15. A systematic one-band inflation on
*both* items of a dimension therefore flips `aligned` to `feeding` — the report tells the
user their job over-supplies something it merely supplies. The prediction to test in pilot
data: **feedback, decision and innovation show a higher `feeding` rate than autonomy, pace
and collaboration**, with no corresponding difference on the person side.

---

## Finding 4 — cross-dimension bleed: the rubric's own band text had to be overruled twice

The rubric's `keep_distinct` guardrails are the record of what two blind raters actually
confused. Recasting band text into user-facing items is exactly the moment those
collisions get rebuilt, so the guardrails were applied as constraints on the wording and
are now enforced by
`test_no_item_reintroduces_a_bleed_its_rubric_guardrail_names`, which greps every item's
prompt and all ten option strings (both tenses) against a forbidden-substring list drawn
from that dimension's own `keep_distinct`.

**Two places where a rubric band text contains a phrase its own `keep_distinct` forbids.
The guardrail won.**

1. **Collaboration 0.7 reads "decisions shared."** Collaboration's `keep_distinct` says
   "Score meeting and team density here, decision rights under Autonomy." The phrase is
   not carried across; `env-collaboration-1`'s 0.7 band is "most problems get worked
   through as a group" — density, not authority. Same for the 0.9 band, where "consensus
   culture" was dropped for "standing group sessions".
2. **Innovation's `where_to_look` says to ignore process rigidity, but "tolerance for
   failed bets" sits next to language that reads as psychological safety.**
   `env-innovation-2` is worded about the fate of the *work* ("some of them are expected
   not to pan out", "that is budgeted for"), never about how people are treated when work
   fails — which would be feedback, or nothing.

**The collaboration ↔ feedback collision** was round 1's worst (9 shared passages, more
than any other pair). It is fenced from both sides: no feedback item mentions the team,
relationships, support, mentorship, recognition, career development or safety; no
collaboration item mentions critique, feedback or how supportive anyone is. The feedback
items ask only *how often* critique arrives (`env-feedback-1`) and *how it is delivered*
(`env-feedback-2`), which is precisely the two-part definition the rubric settled on.

**Response-time expectations are pace, not feedback** — the rubric says so explicitly, and
`env-pace-2` takes that facet deliberately, so the wording lives on the axis the rubric
assigns it to rather than being available to leak onto feedback.

**Autonomy ↔ decision**, the rubric's other named leak: no decision item contains
approval, sign-off, permission, ownership or process language. The two dimensions can be
answered independently — a role can require heavy sign-off and still settle every question
with numbers, which is the case `decision.keep_distinct` says must remain expressible.

**One residual, not fixed.** `env-autonomy-2`'s mixed band says "You and your manager set
your priorities together". "Together" is collaboration vocabulary, but the item is about
who holds priority-setting authority, which is autonomy. It is left as-is because the
alternative phrasings ("jointly", "between you") read worse and carry the same word-sense
risk. Called out here so a later reader does not think it was missed.

---

## Finding 5 — the five-band scale, and what the midpoint does

Five bands rather than a forced choice because the rubric anchors on five and the rater
round already paid for that resolution; collapsing to two would make an environment score
and a rater's company score incomparable, which is the premise of E-4 assembling them into
one training row.

**Achievable dimension scores:** with two items × five bands, a dimension can land on any
of 0.1, 0.2, … 0.9 — nine levels, in steps of 0.10. A-3's ±0.15 aligned band is therefore
one-and-a-half steps wide: the tightest resolution any bucket decision can turn on is a
single item moving a single band. That is a deliberate coarseness (D-15: "three coarse
buckets, too coarse to hill-climb"), but it also means **there is no slack**. A third item
per dimension would halve the step; it was not added because BUILD_PLAN §3.1 caps the
instrument at ~10–12 items and this one is at 12.

**Central tendency.** The mixed band is a legitimate state, not an escape hatch — the
rubric's decision `0.5` text explicitly exists for genuinely split evidence. But for a
self-report about your own job it is also the satisficer's exit, and the mixed options are
on average the *shortest* in the instrument (80.9 characters against 85.6 low / 89.3 high),
which is a mild pull toward them since shorter reads as easier. Small, but it is the one
length asymmetry in the set and it points at the midpoint. As Finding 1 notes, the
consequence of midpoint-picking is an empty report rather than a wrong one.

**Option length parity otherwise:** worst within-item spread 32 characters, median 24, and
per-band means run 80.9–89.3 with no monotonic gradient — no band is systematically the
longer, more-considered-looking option. (`env-collaboration-1`'s low anchor was rewritten
during this review; at 60 characters against a 125-character high anchor it was the one
real outlier.)

---

## Finding 6 — the comp item: the sensitive one, and it is asked the least sensitive way available

`comp` is the only item that touches money, and money is where a career-platform
respondent is most likely to abandon a form.

**What it does right:**

* **It asks for no figure.** No salary, no band, no currency, no equity. Asserted by
  `test_comp_item_is_market_relative_and_asks_for_no_figure`.
* **Market-relative by definition, matching `schema.sql`'s redefinition of the `comp`
  confounder** — "1 well below .. 3 at market .. 5 well above, vs. talent-market peers for
  comparable roles". The item asks exactly that and nothing else.
* **It is a judgement the user already holds.** "Compared with what you could earn
  elsewhere doing similar work" is the comparison people make anyway.

**What remains, and cannot be fixed by wording:**

* **It is a guess about the market, and the accuracy of that guess is not evenly
  distributed.** People with strong networks, recent interview experience, or a
  transparent-pay industry know their market rate; people who are underpaid and isolated —
  precisely the population this platform should serve best — are the least likely to know,
  and the most likely to say "about the same" because they have nothing to compare against.
  **The expected error is toward band 3 and it is not random**, so `comp` will under-report
  underpayment exactly where underpayment is worst.
* **It sits adjacent to a legally and emotionally loaded topic** even without a figure. A
  user in a jurisdiction or workplace with pay-secrecy norms may decline.
* **Position in the form is a deliberate trade** (see Finding 9): `comp` is item two, not
  item fifteen, specifically to keep it away from the outcome question.

**Recommended:** `comp` should be the first item A-7 allows to be skipped if any item is
skippable, and A-2's column is `NOT NULL`, so that is a decision A-5 must make on purpose
rather than discover.

**Resolved 2026-09-10** (PRODUCT_DECISIONS.md §2, "Environment-instrument rulings"; reconciliation
pass): `comp` gains a sixth option, "not sure," storing `None` rather than a guessed posture.
`model.EnvironmentReport.comp` and the `20260910_environment_reports` migration's
`ck_envreport_comp_range` CHECK are both nullable now, and `environment_report_store.write_environment_report`
accepts `comp=None`. The measurement-error problem this finding names is not eliminated — a user who
guesses instead of picking "not sure" still produces the same non-random error — but the instrument no
longer forces a guess where the user has none to give.

---

## Finding 7 — `first_job` has no role to describe, and the module cannot fix that

BUILD_PLAN A-1 says `between_jobs`/`first_job` describe the most recent role in past tense,
and the module implements exactly that (`is_past_tense`, `TENSE_BY_CAREER_STATUS`, full
past-tense variants for every prompt and every option).

**For `between_jobs` this is right.** For `first_job` it is not always coherent: in this
codebase `first_job` means a user who is starting out (`PathSuggestionCard` renders it as
"Starting out → Target"), and a genuinely never-employed user has no role to describe at
all. Handed a past-tense form about "the organization you last worked for", they can only
guess, abandon, or answer about something that isn't a job.

**This is a known repo failure mode, not a novel risk.** It is precisely ratification
decision **D1** on the core items (`assessment_items_v2.yaml`, 2026-08-18): four rung-4
items required an employment history, "a self-profiling user on a career platform is
disproportionately a student, new grad or career-changer", and the failure was
**asymmetric** — an inapplicable item most likely gets declined, which is not the same as
scoring low, and the instrument recorded it as low anyway. The same asymmetry applies here
and would produce a fabricated environment profile with fabricated gaps against it.

**Fix direction — A-5's, not this module's.** Three options, in preference order:

1. **A skip path.** A `first_job` user with no employment history is offered the Situation
   Report's needs-forward half from the core sitting alone — a state A-5 already has to
   build (BUILD_PLAN A-5: "core alone → hub card prompts the env report"). The env report
   simply is not offered until they have a role.
2. Let them describe an internship, placement or substantial part-time role, with the
   prompt saying so. Workable, but it silently widens what an `environment_reports` row
   means, and E-4 will read those rows as jobs.
3. Do nothing and let them answer about a hypothetical. Rejected — this is D1's failure
   with extra steps.

`is_past_tense`'s docstring names this so the next reader does not have to rediscover it.

**Resolved 2026-09-10** (PRODUCT_DECISIONS.md §2, "Environment-instrument rulings"; reconciliation
pass): option 1 above, ratified — a `first_job` user skips the environment form entirely rather than
describing a role they may not have. The routing itself is A-5's, which does not exist yet, so nothing
in this module changes; the ruling exists so A-5's build does not have to rediscover or re-litigate the
choice, and so nothing already built here (the past-tense `first_job` rendering, still correct for a
`first_job` user who *does* have a most-recent role to describe) precludes it.

---

## Finding 8 — industry, remote and role-shape assumptions

**Checked and largely clean.** The items avoid software-shop vocabulary throughout: no
sprints, standups, releases, deploys, tickets, roadmaps, A/B tests or OKRs. "Work goes out
often" replaced "ships frequently"; "new offerings, new capabilities" replaced "new
products"; "measurements, tests or analysis" replaced "A/B testing". Every item reads for a
ward, a site, a shop floor, a school and an office as well as a studio.

**Remote-neutral by construction.** `env-collaboration-2` was written to avoid co-location
assumptions: "calls, working sessions, back-and-forth throughout" rather than any
open-plan or in-the-room framing. The one place physical presence is implied —
`env-collaboration-1`'s high band, "a team you are working alongside all day" — reads as
naturally for a permanently-on-call video room as for a shared floor.

**Four residual assumptions, each real:**

* **`env-autonomy-1` and `env-autonomy-2` assume you have a manager.** A contractor,
  founder or genuinely solo worker has no honest answer, and both items name a manager
  explicitly. `env-autonomy-2`'s mixed band is the worst of the two.
* **`env-decision-2` assumes you get to make cases for things.** In tightly-scoped or
  highly-proceduralized roles, nobody proposes anything and the item measures the job's
  scope rather than its decision basis.
* **`env-innovation-1` and `-2` assume discretion over what gets built.** In regulated,
  clinical or safety-critical work, "a good share of what is tried is expected to fail" is
  not a culture choice; it is prohibited. Such a respondent scores low on innovation
  correctly but for a reason the report cannot see.
* **`stage_size` asks for organization headcount**, which is a poor proxy for felt scale in
  franchised, agency, federated or public-sector settings — a 40,000-person health system
  can feel like a 30-person clinic. The prompt says "the whole organization, not your team"
  to at least make the intended referent unambiguous.

**Fix direction, same as the manager-profile Finding 4:** hedge downstream, not in the
instrument. A-6's guidance cells for low `autonomy` and low `innovation` should carry the
line that some of this may be the work rather than the workplace, and pivot the ask
accordingly. That costs nothing structurally and keeps the anchored scale intact. An
"inapplicable" escape hatch is rejected for the same reason it was there: it makes each
dimension's denominator variable.

---

## Finding 9 — the outcome item's halo, and why form order is what it is

`experienced` ("Overall, how well is this role working for you?") is the only evaluative
item in the instrument, and it is the model's outcome node
(`outcome_experienced.working_scale`, 1–5). It creates two ordering problems that pull in
opposite directions, and the form order is the resolution:

    stage_size → comp → [12 descriptive items] → experienced

* **`experienced` must not come first.** A user who has just declared the job a 2/5 will
  describe every dimension through that verdict — classic halo, and it would contaminate
  the twelve items that are the actual instrument. So it goes last.
* **`experienced` must not sit next to `comp`.** Adjacency between "how does it pay" and
  "how well is it working" inflates their correlation, and that correlation is a weight
  the causal model is later asked to *estimate* (`priors.yaml`'s `comp` weight). Putting
  them together would manufacture the very effect the model is meant to measure. So `comp`
  goes to position two, twelve items away.
* **The residual cost:** `comp` at position two means the form opens on money, which may
  colour the descriptive items with a compensation frame. This is judged the smaller of
  the two harms — the model's `comp` weight is a quantity we are trying to learn, and the
  descriptive items are behavioural enough to resist mood effects that a satisfaction
  rating would not.
* **Asking last still means `experienced` is answered by someone who has just spent five
  minutes enumerating what is wrong with their job.** That is a real priming effect on the
  outcome label and it cannot be removed by ordering — only by asking it in a separate
  sitting, which is the Pulse's job (B-1). Worth knowing before the first outcome rows are
  trained on.

---

## Not flagged, checked and fine

* **Both poles legitimate, verified per item.** Directed and self-directed work; steady and
  fast tempo; solo and collective production; sparse-gentle and frequent-blunt critique;
  refining and inventing; judgement-led and data-led decisions. Each pair names two
  working environments a competent organization could run on purpose. The three residual
  leans are Finding 3's, and they are leans, not reversals.
* **No item asks the user to evaluate the job.** Checked one at a time and asserted by
  `test_no_dimension_item_asks_the_user_to_evaluate_the_job`. The closest is
  `env-autonomy-2`'s "changing it takes permission" (Finding 3), and even that is a
  description of a process, not a verdict on it.
* **No token-map machinery, and that is correct rather than lazy.** Core's D-01 apparatus
  exists because a self-profiling user has an incentive to answer as the person they want
  matched. Misdescribing your own job corrupts only your own report — there is nothing to
  game — so plain item ids straight into `raw_answers` is the right shape (BUILD_PLAN
  §3.1). It also makes the answers legible for the Pulse's re-ask (B-4) without a
  re-derivation step.
* **Anchor values are the rubric's `band_values`, unscaled and unshifted** — asserted
  against the JSON by `test_anchor_values_match_the_rubric_band_values`, so an environment
  score and a rater's company score remain one axis. Scaling belongs in
  `solverah_model_config.yaml`, per `schema.sql`.
* **Tense variants cannot drift.** Same ids, same option keys, same poles, same order,
  both tenses non-empty, and `test_tense_never_changes_a_score` asserts the score keys off
  the band and never off the wording.
* **Item ids name their dimension and are stable.** They become keys in
  `EnvironmentReport.raw_answers`, so a rename orphans every stored row;
  `FORM_VERSION` (`env-v1-2026-09-10`) stamps which item set produced a blob, the role
  `assessment_response.form_version` plays on the core side.
* **`stage_size`, `comp` and `experienced` are stored raw and are never averaged into a
  dimension**, asserted by `test_context_items_are_not_scored_as_dimensions`. Two
  confounders and an outcome node, not three more items.
* **The manager section is not duplicated here.** ⚑4: it is C-1's instrument, linked. No
  item in this file asks about a manager's behaviour — the two autonomy items mention a
  manager only as the source of direction, which is an autonomy fact, not a manager
  reading.

---

## Integration note — A-3 cannot score a five-band instrument yet (RESOLVED 2026-09-10)

Not a bias finding; recorded here because it is the one thing that stops A-1 and A-3
working together, and it appeared *during* this chunk.

**Resolved 2026-09-10 (reconciliation pass).** The premise below turned out to be stale by
the time A-3's own working tree was read directly: `work_pulse/situation.py` had already
been generalized to `EnvironmentItemSpec.pole_values: Mapping[str, float]` — it was never a
two-anchor `tuple[float, float]` restricted to the literals `"low"`/`"high"`. The real,
narrower gap was that `item_spec()` emitted the mapping under the key `anchor_values`, which
`score_environment` does not read. Fixed by renaming `anchor_values` → `pole_values` in
`item_spec()`; the tombstone test below is gone, replaced by
`test_a3_scores_the_real_twelve_item_environment_bank_end_to_end` and
`test_item_spec_conforms_to_what_a3_actually_requires` in `tests/test_situation_items.py`,
which prove the real seam rather than assert its absence. The rest of this section is left
as written, for the history.

`work_pulse/situation.py` (A-3) was written while A-1 did not exist and assumes **two**
anchors per item: `EnvironmentItemSpec.anchor_values` is a `tuple[float, float]` and an
answer must be the literal string `"low"` or `"high"`. This instrument is anchored on the
rubric's **five** bands. A-3's `score_environment` therefore rejects a real sitting.

**The fix is one line on A-3's side**, and it is a generalization rather than a change of
idea: `entry["anchor_values"][choice]` in place of `low, high = entry["anchor_values"]`,
after which a two-anchor spec is simply `{"low": …, "high": …}` and both shapes work.
`item_spec()` in `situation_items.py` already emits the mapping form.

A-3 was not modified — it is another chunk's file and this chunk was told to touch only its
own. Instead `tests/test_situation_items.py` carries a **tombstone test**,
`test_a3_cannot_yet_score_a_five_band_instrument`, which asserts the incompatibility so it
cannot be silently forgotten, and which **starts failing the day A-3 is generalized** — the
same device `test_manager_match_relationship_keying_is_known_contaminated` used on the C-1
side. Its docstring carries the real end-to-end assertion to replace it with.

One further note for whoever does that work: `tests/test_situation.py` and
`work_pulse/situation.py` were mutually out of step at the time of writing (the test file
imports `HIGH`/`LOW` and an `EnvironmentItemSpec` shape that the module acquired only
mid-session). Both are uncommitted. Confirm which is current before changing either.

---

## Recommended order of work

1. **Generalize A-3's `anchor_values` to a mapping** (Integration note). Nothing in
   Workstream A runs end to end until this is done, and it is one line plus a test swap.
2. **A-5 must decide the `first_job` path** (Finding 7) before the form is reachable. The
   preferred answer — do not offer the env report to a user with no employment history —
   is a state A-5 is already building for a different reason.
3. **A-5 must decide whether `comp` is skippable** (Finding 6). A-2's column is `NOT NULL`,
   so silence is a decision either way.
4. **A-6's guidance content carries Finding 8's hedge** on low `autonomy` and low
   `innovation` cells: some of this may be the work rather than the workplace.
5. **A-7's "what this is / isn't" footer carries Finding 2.** It is currently the only
   surface where the perception-not-measurement caveat will be said, and the footer is
   already in A-7's scope.
6. **Run Finding 2's within-employer variance query on the first cohort.** Everything else
   here is a structural prediction; this is the one measurement that says whether the
   environment score means anything about the environment.
7. **Watch Finding 3's prediction in pilot data**: a higher `feeding` rate on feedback,
   decision and innovation than on autonomy, pace and collaboration, with no matching
   difference on the person side. No action before data.
8. **Watch Finding 1's reversal artifact**: within-dimension disagreement at 0.9/0.1 above
   the base rate. If it is real, the fix is A-7 presentation (grouping and labelling), not
   the item bank.

`Solverah_IP/` was not modified. `work_pulse/situation.py`, `work_pulse/situation_content.py`
and `tests/test_situation.py` were read and not modified. The only files this chunk wrote
are `work_pulse/situation_items.py`, `tests/test_situation_items.py` and this document.
