# Manager-profile items — Bias Review (C-1)

Reviewed `manager_profile.py` (15 items) in the tradition of
`causal_graph/v1_model/ASSESSMENT_ITEMS_BIAS_REVIEW.md` — same rubric, same
structural-read caveat: no pilot data exists, so nothing here is empirical. This is
what should be fixed *before* a pilot, so the pilot measures the items rather than
re-discovering these. Nothing in the v1 review file was modified; this is a separate
document for a separate instrument.

**The standard applied**, restated from the v1 header: *neither pole is the right one*.
A lean means the item smuggled in a socially-desirable answer. To that, this instrument
adds two requirements the v1 core items did not carry:

* **Positional key balance.** The high-scoring pole must not sit systematically in
  option A or option B. The v1 core items failed exactly this (counts in Finding 1).
* **Observational, not evaluative.** Every item describes what the manager *does*.
  Nothing asks how the user feels about it, and no item is a proxy for "is your manager
  good". This is the load-bearing constraint: the instrument is a style read that gets
  diffed against the user's own needs (C-2), and a quality verdict would make the diff
  meaningless — a good manager and a bad manager can both mesh or grind.

Four kinds of problem, kept separate: **positional key** (Finding 1), **halo/horn**
(Finding 2 — new to an observational instrument and the largest risk here), **residual
desirability skew** (Finding 3), and **who the items exclude** — industry, seniority,
and gender coding (Findings 4–6). Finding 7 was a cross-instrument note for C-2 and is
**resolved** (2026-09-10) — the counterpart item it names has been corrected and the
already-stored sittings re-derived.

---

## Finding 1 — positional key balance: PASS, exact

**Updated 2026-09-10** following Sebastian's sign-off to add `mp-q16` (Finding 3). Counts,
computed from the item table, not eyeballed:

| Dimension | items | high pole in A | high pole in B |
|---|---|---|---|
| autonomy | 4 | 2 | 2 |
| feedback_style | 4 | 2 | 2 |
| relationship | 4 | 2 | 2 |
| growth_focus | 4 | 2 | 2 |
| **overall** | **16** | **8** | **8** |

Every dimension is now exactly 2/2, and the overall split is exactly 8/8 — the bounded
residual noted below (originally 1/2 on `relationship`, the floor for an odd count) is
closed, not just bounded.

For contrast, the counterpart instrument this one is diffed against —
`manager_match/questions.py`, the same four dimensions:

| Dimension | items | high pole in A | high pole in B |
|---|---|---|---|
| autonomy | 4 | 0 | **4** |
| feedback_style | 4 | **4** | 0 |
| relationship | 3 | 2 | 1 |
| growth_focus | 4 | **4** | 0 |
| **overall** | **15** | **10** | **5** |

Three of four ManagerMatch dimensions are perfectly straight-keyed: a respondent who
picks A throughout scores 0.25 autonomy / 0.80 feedback / 0.80 growth — a confident,
extreme, entirely artefactual profile. The new items cannot do that. Straight-lining
either position lands mid-scale on every dimension:

* all-A → autonomy 0.525, feedback 0.525, relationship 0.525, growth 0.525
* all-B → autonomy 0.525, feedback 0.525, relationship 0.525, growth 0.525

against an item anchor range of 0.25–0.80. `test_straight_lining_cannot_produce_an_extreme_profile`
holds this to a 0.40–0.65 band, and
`test_straight_lining_lands_on_the_anchor_midpoint_for_every_dimension` — added with
`mp-q16` — pins the exact value, since a band that wide no longer describes what the
instrument does. Two structural tests hold the per-dimension and overall counts to a
difference of at most one, which *is* exactness here rather than a loose bound: an even
count can only split with an even difference, so 2/2 and 8/8 pass and 3/1 and 9/7 fail.
Neither property can regress silently. With `mp-q16` in place, `relationship` lands on
exactly the same 0.525 as the other three dimensions in both directions — the residual
below is closed, not just narrowed.

**Residual — closed 2026-09-10.** `relationship` was 1/2 rather than 2/2 because it had
three items, and three cannot split evenly. Sebastian signed off on raising the instrument
to 16 items (this doc's prompt is the authorization on record); `mp-q16` is now item 4 on
`relationship`, keyed high-A, closing this residual and Finding 3's missing warmth
counterweight in the same item. `test_item_count_is_in_the_specified_range` now asserts
`12 <= count <= 16`.

---

## Finding 2 — halo/horn is this instrument's characteristic failure, and it is not fixable by wording

ManagerMatch asks the user about themselves. This asks the user about *a specific person
they may resent, admire, fear, or be managed out by*. That is a different psychometric
object. The standing risk is **global affect** — a respondent who likes their manager
describes them warmly across all four dimensions, and one who is in conflict describes
them coldly across all four, regardless of the manager's actual style. It will show up as
the four dimension scores correlating with each other far more than the constructs should
warrant.

**What the design does about it.** Because no pole is scored as better, a respondent
under halo has nowhere obvious to put it: there is no "good manager" column to walk down.
Five items have no warmer option at all, and on two more — `mp-q6` (states the problem
plainly / frames criticism carefully) and `mp-q14` (pushes back on your ideas / helps you
get them done) — the warmer option is the **low**-scoring one, so warmth does not
translate cleanly into a high profile.

**What it does not do.** The mitigation is partial, and Finding 3 shows the residual
warmth is not evenly distributed across dimensions. Wording cannot finish this job; only
detection can.

**Pilot check, concrete and already affordable:** A-1 collects the model's own outcome
question — *"overall, how well is this role working for you?"* (`experienced`, 1–5), on
the same sitting. If all four manager-profile dimensions correlate with that single item
in the same direction and at similar strength, that is halo, not style, and the item set
needs reverse-keyed additions before the Decoder can be trusted to name a grind. This is
the cheapest real bias test available to the project and it should be run on the first
cohort, not deferred.

---

## Finding 3 — residual desirability skew is dimensionally patterned, and `relationship` carried most of it

**Updated 2026-09-10: `mp-q16` (below) is applied, and it changes both counts in this
finding.** The table and prose immediately following describe the item set at the time of
writing (15 items) so the reasoning that led to `mp-q16` stays legible; the post-fix state
is called out where it changes.

Reading each item for which pole a respondent would pick to flatter their manager:

| Item | Warmer-reading pole | Which end of the key |
|---|---|---|
| `mp-q10` speaks up for you / your record speaks for you | A | **high** |
| `mp-q11` same way with everyone / adapts to you | B (mild) | **high** |
| `mp-q15` leaves your learning to you / sets learning goals | B | **high** |
| `mp-q12` the job now / where you're heading | B (mild) | **high** |
| `mp-q8` speaks up when needed / tells you either way | B | **high** |
| `mp-q1`, `mp-q3` directive / hands-off | B (mild) | **high** |
| `mp-q13` new work / work you're good at | A (mild) | **high** |
| `mp-q6` plainly / frames carefully | B | **low** |
| `mp-q14` pushes back / helps you execute | B | **low** |
| `mp-q16` taken at your word / tracked without asking | B | **low** |
| `mp-q2`, `mp-q4`, `mp-q5`, `mp-q7`, `mp-q9` | neither | — |

Two things are wrong with this distribution, and they are separate.

**First: warmth is positionally concentrated, even though the key is not.** Of the ten
original items carrying any warmth at all, **eight put it in option B** (`mp-q1`, `mp-q3`,
`mp-q6`, `mp-q8`, `mp-q11`, `mp-q12`, `mp-q14`, `mp-q15`) and only two in option A
(`mp-q10`, `mp-q13`); five were neutral. So a respondent flattering their manager and a
respondent straight-lining position B produced similar answer sheets. What saves this is
the balanced *key*, not the wording: because the high pole alternates, picking B throughout
still lands mid-scale on every dimension (Finding 1), so neither respondent produces a
confident profile. The protection is real but narrower than it should be, and it is worth
being precise about rather than claiming a positional balance the warmth audit does not
show. `mp-q16` adds a ninth warmth-in-B item (`mp-q16`'s warmer pole, "taken at your word,"
is option B) without adding one to A, so this positional concentration is slightly worse in
raw count after the fix — the fix targets the *dimensional* imbalance below, not this one.

*Option, needs sign-off:* have C-4 randomize which pole is presented first per item per
sitting, storing the chosen `question_id` + pole rather than a screen position. That
decouples warmth from position entirely. Costs: the frontend must carry the mapping, and
C-3's stored answers must be unambiguous about pole rather than position. Cheaper
alternative: leave it, on the grounds that the key balance already prevents an extreme
profile. Recommend the cheap option for launch and the randomization as a fast-follow —
but the choice should be made, not defaulted into.

**Sebastian's ruling on this option (2026-09-08, recorded here where the question was
raised):** if and when pole-presentation randomization ships, storage persists the
*authored* option identity (A/B as written in this file), never screen position.
Presentation order is a free frontend choice; the backend and stored answers are keyed to
the authored pole regardless of where either option lands on screen for a given sitting.
This binds C-3's stored-answer shape.

**Second, and larger: the dimensional spread was not balanced either.**

* `feedback_style` is clean: `mp-q6`'s warmth pulls low, `mp-q8`'s pulls high, `mp-q5`
  and `mp-q7` are neutral. Skew roughly cancels.
* `autonomy` is mildly upward (`mp-q1`, `mp-q3`) with no counterweight, but the pull is
  weak — being directed is a legitimate and commonly-described experience.
* `growth_focus` is upward on three items with one counterweight (`mp-q14`).
* **`relationship` had no counterweight at all** before the fix below. After the `mp-q9`
  rewrite, one item was neutral and two (`mp-q10`, `mp-q11`) put the warmer reading on the
  high end, with nothing pulling the other way. `mp-q16` is that counterweight: its warmer
  reading ("taken at your word") sits on the **low** pole, so `relationship` now has one
  counterweight, same as `growth_focus` and `autonomy` — no dimension is left at zero.

**Consequence, and it is a real one for C-2:** halo inflates `relationship` and
`growth_focus` specifically. Those are the two dimensions where the Decoder will
*under-detect grind* — a user whose relational needs are unmet but who is loyal to their
manager reads as mesh. That is the wrong direction to fail in for the surface the whole
workstream is building toward.

**`mp-q10` is the single most skewed item.** Advocacy carries positive valence almost
universally; "speaks up for you when decisions about you get made without you there" is
close to a virtue. Its ManagerMatch counterpart `mm-q10` is the only item in that file
scored 0.70/0.30 rather than 0.80/0.25 — the v1 authors evidently discounted the same
item for what looks like the same reason. This instrument uses uniform anchors on purpose
(no item weighted above another while `priors.yaml` is placeholder), so the discount is
not available here; the item is flagged instead. Its low pole is at least a genuine
philosophy ("your record speaks for you", i.e. don't play politics on someone's behalf),
which is why it survived the both-poles-legitimate cut.

**Applied during authoring** (recorded here rather than left implicit): `mp-q9`'s low pole
was originally *"Your manager keeps your conversations to the work itself"*, which reads
cold. It is now *"Your manager keeps out of your life outside work unless you bring it
up"* — respecting privacy is warm, so both poles of that item are now defensible-warm and
the item is neutral rather than skewed. Three further items (`mp-q4`, `mp-q5`, `mp-q15`)
had their option texts tightened for length parity; the worst A/B length gap is now 14
characters, median 8, so no item's high pole is also its longer, more-considered-looking
option.

**Applied 2026-09-10, with Sebastian's sign-off** (raising the count to 16): a fourth
`relationship` item whose warmth sits on the *low* pole and whose high pole sits in
position A — closing Finding 1's residual and this finding's counterweight gap together:

> `mp-q16` (relationship)
> A: *"Your manager keeps track of how you’re doing personally, whether or not you raise it."* (0.80)
> B: *"Your manager takes you at your word about how you’re doing."* (0.25)

The warmer reading — being taken at your word, treated as an adult — is the **low** pole,
and the high pole sits in **A**, which is what makes this item close both gaps. It is also
distinct from the rewritten `mp-q9`: that item is about the manager's interest in your life
outside work, this one about whether they monitor your state without being told.
`test_item_count_is_in_the_specified_range` in `tests/test_manager_profile.py` now asserts
`12 <= count <= 16` rather than `<= 15`.

---

## Finding 4 — some of these behaviors are chosen by the industry, not by the manager

This is the observational instrument's own version of the confound problem, and it has no
analogue in a preference instrument. Four items describe behaviors that in some workplaces
are simply not the manager's to choose:

* **`mp-q3`** (signs off before you act) — mandatory in regulated, licensed, clinical, or
  spend-controlled work. The manager signs off because the law or the insurer says so.
* **`mp-q4`** (leaves the order to you) — impossible where the sequence is fixed by the
  process: a line, a kitchen, clinical rounds, a route.
* **`mp-q5`** (tells you the moment they notice) — impossible where the manager is not
  present while the work happens: field work, night shift, distributed teams, lone working.
* **`mp-q13`** (puts you on work you haven't done before) — constrained by role scope, not
  by managerial intent, in narrowly-defined jobs.

For those respondents the item measures the industry and the Decoder reports a grind the
manager has no power to fix — which is precisely the "fault not fit" failure C-2's tone
guardrail is meant to prevent, arriving through the data rather than through the copy.

**Fix direction — not an item rewrite.** The behaviors are real and worth capturing; the
problem is downstream interpretation. Two options, and this is a design question C-2/C-3
should answer deliberately rather than inherit:

1. **Preferred: hedge in the playbook, not the instrument.** A-1 already collects enough
   context to know the respondent's setting; the protocol cells for `autonomy`-low and
   `feedback_style`-low grinds should carry a line acknowledging that some of this may be
   the work rather than the manager, and pivot the ask accordingly. Costs nothing
   structurally and keeps forced-choice intact.
2. An "the work decides this, not my manager" escape hatch. Rejected as a default: it
   changes the instrument's shape, makes each dimension's denominator variable, and gives
   halo a comfortable place to hide.

**Checked and clean otherwise:** the item set is free of office-job vocabulary. No email,
Slack, documents, meetings, 1:1s, desks, calendars, or reviews-as-a-process. Every item
reads for a warehouse, a ward, a site, a shop floor, and an office alike. Three weaker
spots worth knowing: `mp-q11` assumes the manager manages more than one person; `mp-q14`
assumes the role involves proposing ideas; `mp-q10` assumes decisions about you sometimes
happen elsewhere, which is thin at a five-person employer where the manager is the owner.

---

## Finding 5 — seniority coding: mild, and partly self-correcting

No item assumes the user is junior, and no item uses seniority-coded vocabulary (no
"reports", "stakeholders", "IC", "exec", "promotion track", "career ladder"). But two
`growth_focus` items — `mp-q13` (work you haven't done before) and `mp-q15` (goals for
what you'll learn next) — are more natural early in a career than late in one. A
tradesperson thirty years in may read the growth dimension as *inapplicable* rather than
*low*, and forced choice will record it as low.

**Why this is smaller than it looks:** the diff structure absorbs much of it. ManagerMatch
measures the user's own growth appetite on the same dimension, so a senior respondent who
does not want development scores low on *both* sides and the diff correctly reads mesh.
The error only survives where the user wants growth and the items misread its absence —
a narrower case. Worth watching in pilot data (growth_focus mean by tenure band), not
worth a rewrite now.

---

## Finding 6 — gendered language: clean in the text; not fixable in the text

**The items themselves pass.** Every item says "your manager" and "they/them". No
gendered nouns, no gender-coded trait vocabulary ("aggressive", "bossy", "nurturing",
"emotional"), no appearance or manner terms.

**The deeper problem is that this instrument rates a real person who has a gender.**
`mp-q6` (plain vs. cushioned criticism) and `mp-q9`/`mp-q11` (personal engagement,
individualized treatment) sit exactly where the performance-evaluation literature
consistently finds identical behavior described differently for men and women managers —
directness read as decisive or as harsh, warmth read as supportive or as unprofessional.
No wording of an observational item escapes this; the rater brings it.

**Mitigation by design, which is genuinely load-bearing here:** because neither pole is
scored as better, a gender-shifted perception shifts a *style* reading, not a *quality*
verdict. The Decoder can say "your manager runs direct" and never "your manager is
harsh". That is a meaningful difference in blast radius and it should be protected in
C-2's content review — every protocol cell must describe behavior and the user's response
to it, never characterize the person.

**Residual, stated plainly:** the diff still drives a playbook, so a gender-shifted style
reading yields a gender-shifted playbook. There is no correction available.

**Recommendation: do not collect the manager's gender.** There is nothing to correct with,
and it would create a demographic record about a *named third party who has not consented*
— a re-identification surface the project's own testing discipline would flag immediately.
Handle it in D-3's trust page instead, in plain words: this describes how your manager
works with *you*, it is your read and not a verdict, and it stays private to you.

---

## Finding 7 — cross-instrument: the counterpart `relationship` scale is internally inconsistent — **RESOLVED 2026-09-10**

Stated below as it was found, in the present tense it was written in; the fix, the
mechanism and what it leaves for C-2 are under **Resolved 2026-09-10** further down.

Not a defect in these items, but it lands on C-2 and should not be discovered there.
Within ManagerMatch's `relationship` dimension:

* `mm-q9` keys **personal closeness** high (0.80: *"knows you as a person"*)
* `mm-q10` keys **advocacy** high (0.70: *"advocates strongly for your interests"*)
* `mm-q11` keyed **distance** high (0.80: *"trusts you enough to be hard to reach"*)
  **— corrected 2026-09-10; it now keys availability high, with the other two. The rest
  of this finding is kept as written, and its resolution is below.**

`mm-q11` runs opposite to the other two. The new items key `relationship` the way `mm-q9`
and `mm-q10` do — closeness and advocacy high — because that is what two of the three
counterpart items mean, and it is the reading the Decoder needs.

**Consequence for C-2:** the relationship diff subtracts a clean scale from a contaminated
one. A user whose true relational need is high, but who answered `mm-q11` toward the
"hard to reach" pole, has a user-side relationship score depressed by up to 0.183 (one of
three items moving 0.55) for reasons unrelated to the construct — enough to flip a
threshold. **Not fixed here on purpose:** changing `mm-q11` changes ManagerMatch's scoring
and its committed tests, which is out of C-1's scope and is a product decision (users have
already taken it). Flagged for C-2 to either set the relationship threshold more
conservatively than the other three, or to schedule a `mm-q11` rewrite with a version bump.

**Resolved 2026-09-10 — corrected in place, with a scoring-key stamp and a rescore
backfill from stored answers.** Sebastian authorized the `mm-q11` rewrite this finding
recommends and named the mechanism: flip the item, stamp the key, and re-derive the
already-stored sittings from the answers they kept. `mm-q11` now keys availability high
(0.80 A / 0.25 B), with `mm-q9`'s closeness and `mm-q10`'s advocacy. The `relationship`
scale is internally consistent, and the C-2 diff no longer subtracts a clean manager-side
scale from a contaminated user-side one.

*What made it possible without the era-tracking chunk an earlier draft here called a
prerequisite.* That draft went looking for a **version column**, found none, and stopped.
The mechanism already in place is the **raw answers**. `assessment_submissions.answers`
holds the payload each respondent actually sent, for all four non-`core` kinds — an
addition to Part 4.4 whose own docstring names re-derivation as one of the reasons the
column exists — and the culture-preference backfill
(`matching_service.backfill_culture_preferences`) already re-derives from stored Work Pulse
answers. Scores are derived; answers are the source of truth. So the stored rows never
needed to be *interpretable side by side under two keys*; they needed to be *re-derived
under one*, which turns "separate the eras" into "eliminate the old one" and removes the
prerequisite rather than satisfying it.

*The stamp, and why it is a payload field rather than a column.*
`manager_match.score.SCORING_KEY` (`"mm-v2"`) is returned by `score_manager_match` and
lands in `assessment_submissions.result` as `result["scoring_key"]`. `result` is JSONB and
`ManagerMatchResult` is `extra="allow"`, so the field costs nothing on the wire or in the
schema. The alternatives both cost a migration: a per-kind scoring-version column, or
bumping `form_version` for `manager_match` alone — which additionally needs
`CLIENT_FORM_VERSION` de-shared across the four client-rendered instruments and an
`assessment_forms('manager_match', <new>)` row seeded for the composite foreign key. None
of that is a side-effect a bias-review fix gets to have; a field on a blob that is already
returned verbatim is. **`"mm-v1"` is never written anywhere:** it is the *absence* of the
key, which is precisely what every pre-correction row has.

One supporting change at the write site: `submit_manager_match` now merges
`{**llm_result, **scoring}` rather than `{**scoring, **llm_result}`, so a model reply
carrying `archetype`, `dimension_scores` or `scoring_key` cannot shadow the deterministic
values. A marker a model could overwrite would not be a marker, and the backfill takes this
field at its word.

*The backfill.* `Scripts/backfill_manager_match_scoring_key.py` finds every `manager_match`
submission without the marker, re-scores it from its stored answers under the corrected
key, replaces the deterministic half of the stored result, and stamps it. It is idempotent
— a second run finds only already-stamped rows — and it never reads or writes any other
kind. `core` least of all: its answers and dimension scores are behind `assessment_store`
(D-01) and are not in this table, but the reason the script cannot reach them is the query,
which names `manager_match` and nothing else. Rows whose answers are missing or malformed
are counted and their public ids printed, **never rewritten and never stamped**: leaving
one unmarked says truthfully that it is still scored under the old key, whereas stamping it
would make it indistinguishable from a row that was actually re-derived.

The property that makes re-deriving legitimate rather than a guess is asserted, not
assumed: `tests/test_manager_match_rescore.py` seeds a sitting as it was stored under the
contaminated key, submits the identical answers fresh through the job pair, and requires
the backfilled row and the new one to agree exactly on `archetype`, `dimension_scores` and
`scoring_key`.

*What propagates on its own, and what does not.* `profile_repository.load_document` merges
`manager_match_result` out of the submission row on every read — unconditionally, so a
stale copy left anywhere else cannot shadow it — and `GET
/me/assessments/manager_match/result` serves the same blob verbatim. Correcting the row is
therefore the whole propagation; there is no second write site. What does **not** move is
the stored prose: `narrative`, `what_to_look_for`, `red_flags` and `archetype_description`
were generated by the LLM at submit time from the *old* archetype and dimension scores, and
a backfill making a provider call per user is a different piece of work with a different
cost. The script preserves them verbatim and reports how many rows changed archetype
underneath them, so the consequence is visible rather than silent.

*Tripwire inverted, not deleted.*
`test_manager_match_relationship_keying_is_known_contaminated` in
`tests/test_manager_profile.py` is now `test_manager_match_relationship_keying_is_consistent`
and asserts the property instead of the defect. `tests/test_manager_match.py` gains
`test_relationship_items_all_key_closeness_high`, which states the invariant behaviourally —
choosing the closer pole must raise `relationship` on **every** item of the scale — so a
future item cannot reintroduce this by being keyed backwards.

**Still standing for C-2, and this is not a leftover.** The `relationship` mesh threshold of
0.20 was chosen for *two independent* reasons, and only one of them was this contamination.
The other is arithmetic: `relationship` has three user-side items to the other dimensions'
four, so one item moves its mean by 0.183 rather than 0.1375. That reason is untouched, and
0.20 remains the smallest threshold at which a single item cannot manufacture a grind. What
*is* now stale is prose, not numbers: `manager_match/decoder.py`'s module docstring and
`test_finding_7_contamination_cannot_manufacture_a_relationship_grind` still describe the
contamination as live. Neither goes red — the correction swaps which *option text* carries
which anchor and leaves every achievable dimension score unchanged — so they are C-2's to
reword, not C-1's to touch.

---

## Not flagged, checked and fine

* **No item approaches "is your manager good."** Checked one at a time. The closest is
  `mp-q10` (Finding 3), and even there the low pole is a stated philosophy rather than a
  failure to advocate.
* **Both poles legitimate, verified per item.** Directive and delegating management;
  immediate and scheduled feedback; blunt and cushioned delivery; boundaried and personal
  relationships; consistent and individualized treatment; stretch assignments and playing
  to strengths; challenging ideas and backing them. Each pair names two management styles
  a competent manager could hold on purpose.
* **`mp-q2`, `mp-q4`, `mp-q5`, `mp-q7`, `mp-q9`** read as genuinely balanced forced
  choices with no warmer option in either direction — the five the halo mitigation leans on.
* **Uniform anchors (0.80/0.25) are a deliberate flat-weight choice**, not an oversight:
  it keeps this scale directly comparable to ManagerMatch's for the C-2 subtraction, and
  matches A-3's stated flat-weight stance while `priors.yaml` remains placeholder.
* **Option length parity:** worst A/B gap 14 characters, median 8. No item's high pole is
  systematically the longer option.
* **Dimension keys are identical to ManagerMatch's**, asserted by
  `test_dimensions_match_manager_match_exactly` so the C-2 diff cannot silently mismatch.

---

## Recommended order of work

1. **Run Finding 2's halo check on the first cohort** (manager-profile dimensions against
   A-1's `experienced` outcome item). Everything else here is a structural prediction;
   this is the one measurement that would tell us whether the instrument works at all.
2. ~~Decide `mp-q16`~~ **Done 2026-09-10.** Sebastian signed off; the fourth `relationship`
   item is live in `manager_profile.py`, closing the positional residual and the missing
   warmth counterweight on the most exposed dimension.
3. **C-2 content review carries Findings 4 and 6**: the environment-may-be-the-cause hedge
   on low-autonomy and low-feedback protocol cells, and behavior-not-person language
   throughout.
4. **Pole-randomization storage decided, build pending** (Finding 3, first half):
   Sebastian ruled 2026-09-08 that storage persists the authored option identity, never
   screen position, if and when C-4 builds randomized presentation. C-3 should treat this
   as settled, not open.
5. ~~Schedule the `mm-q11` rewrite~~ **Done 2026-09-10** (Finding 7). The item is
   corrected, `manager_match.score.SCORING_KEY` stamps which key produced a stored result,
   and `Scripts/backfill_manager_match_scoring_key.py` re-derives the pre-correction
   sittings from the answers they kept. It landed **before** C-2 ships, which is the order
   that mattered: the decoder re-scores the user side from stored answers on every diff, so
   a key change after C-2 went live would have moved what users see. **C-2's `relationship`
   threshold does not move with it.** 0.20 was chosen for two independent reasons and only
   one was this contamination; the other — three user-side items to the other dimensions'
   four, so one item moves the mean by 0.183 — is untouched. What C-2 still owes is prose:
   `decoder.py`'s docstring and
   `test_finding_7_contamination_cannot_manufacture_a_relationship_grind` describe the
   contamination as live. Neither goes red, because the correction swaps which option text
   carries which anchor and leaves every achievable dimension score unchanged.
6. Watch `growth_focus` by tenure band in pilot data (Finding 5). No action before data.

`manager_profile.py` has one change beyond this review's writing: `mp-q16`, added
2026-09-10 with Sebastian's sign-off (Finding 3). The v1 review file was not touched —
consistent with how the rubric anchors went through Sebastian's ratification before being
frozen. `manager_match/questions.py` (`mm-q11`) **was** changed on 2026-09-10, with Sebastian's
authorization and by the mechanism he named — flip, stamp, and rescore the stored
sittings from their answers. See Finding 7.
