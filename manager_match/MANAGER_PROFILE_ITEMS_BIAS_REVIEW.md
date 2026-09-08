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
and gender coding (Findings 4–6). Finding 7 is a cross-instrument note for C-2.

---

## Finding 1 — positional key balance: PASS, with one bounded residual

The requirement the chunk was written to meet. Counts, computed from the item table, not
eyeballed:

| Dimension | items | high pole in A | high pole in B |
|---|---|---|---|
| autonomy | 4 | 2 | 2 |
| feedback_style | 4 | 2 | 2 |
| relationship | 3 | 1 | 2 |
| growth_focus | 4 | 2 | 2 |
| **overall** | **15** | **7** | **8** |

For contrast, the counterpart instrument this one is diffed against —
`manager_match/questions.py`, the same four dimensions:

| Dimension | items | high pole in A | high pole in B |
|---|---|---|---|
| autonomy | 4 | 0 | **4** |
| feedback_style | 4 | **4** | 0 |
| relationship | 3 | 1 | 2 |
| growth_focus | 4 | **4** | 0 |
| **overall** | **15** | **9** | **6** |

Three of four ManagerMatch dimensions are perfectly straight-keyed: a respondent who
picks A throughout scores 0.25 autonomy / 0.80 feedback / 0.80 growth — a confident,
extreme, entirely artefactual profile. The new items cannot do that. Straight-lining
either position lands mid-scale on every dimension:

* all-A → autonomy 0.525, feedback 0.525, relationship 0.433, growth 0.525
* all-B → autonomy 0.525, feedback 0.525, relationship 0.617, growth 0.525

against an item anchor range of 0.25–0.80. `test_straight_lining_cannot_produce_an_extreme_profile`
holds this to a 0.40–0.65 band, and two structural tests hold the per-dimension and
overall counts to a difference of at most one, so neither can regress silently.

**Residual:** `relationship` is 1/2 rather than 2/2 because it has three items, and three
cannot split evenly. The imbalance is one item, which is the floor for an odd count — but
it is the same dimension flagged in Finding 3, and a fourth relationship item keyed high-A
would close both at once. Held back deliberately: the chunk spec caps the instrument at 15
items, and `test_item_count_is_in_the_specified_range` asserts that cap. Raising it to 16 is
Sebastian's call, not a silent edit — draft item in Finding 3.

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

## Finding 3 — residual desirability skew is dimensionally patterned, and `relationship` carries most of it

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
| `mp-q2`, `mp-q4`, `mp-q5`, `mp-q7`, `mp-q9` | neither | — |

Two things are wrong with this distribution, and they are separate.

**First: warmth is positionally concentrated, even though the key is not.** Of the ten
items carrying any warmth at all, **eight put it in option B** (`mp-q1`, `mp-q3`, `mp-q6`,
`mp-q8`, `mp-q11`, `mp-q12`, `mp-q14`, `mp-q15`) and only two in option A (`mp-q10`,
`mp-q13`); five are neutral. So a respondent flattering their manager and a respondent
straight-lining position B produce similar answer sheets. What saves this is the balanced
*key*, not the wording: because the high pole alternates, picking B throughout still lands
mid-scale on every dimension (Finding 1), so neither respondent produces a confident
profile. The protection is real but narrower than it should be, and it is worth being
precise about rather than claiming a positional balance the warmth audit does not show.

*Option, needs sign-off:* have C-4 randomize which pole is presented first per item per
sitting, storing the chosen `question_id` + pole rather than a screen position. That
decouples warmth from position entirely. Costs: the frontend must carry the mapping, and
C-3's stored answers must be unambiguous about pole rather than position. Cheaper
alternative: leave it, on the grounds that the key balance already prevents an extreme
profile. Recommend the cheap option for launch and the randomization as a fast-follow —
but the choice should be made, not defaulted into.

**Second, and larger: the dimensional spread is not balanced either.**

* `feedback_style` is clean: `mp-q6`'s warmth pulls low, `mp-q8`'s pulls high, `mp-q5`
  and `mp-q7` are neutral. Skew roughly cancels.
* `autonomy` is mildly upward (`mp-q1`, `mp-q3`) with no counterweight, but the pull is
  weak — being directed is a legitimate and commonly-described experience.
* `growth_focus` is upward on three items with one counterweight (`mp-q14`).
* **`relationship` has no counterweight at all.** After the `mp-q9` rewrite below, one
  item is neutral and two (`mp-q10`, `mp-q11`) put the warmer reading on the high end.

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

**Proposed fix, needs sign-off (raises the count to 16):** a fourth `relationship` item
whose warmth sits on the *low* pole and whose high pole sits in position A — closing
Finding 1's residual and Finding 3's counterweight gap together:

> `mp-q16` (relationship)
> A: *"Your manager keeps track of how you're doing personally, whether or not you raise it."* (0.80)
> B: *"Your manager takes you at your word about how you're doing."* (0.25)

The warmer reading — being taken at your word, treated as an adult — is the **low** pole,
and the high pole sits in **A**, which is what makes this item close both gaps. It is also
distinct from the rewritten `mp-q9`: that item is about the manager's interest in your life
outside work, this one about whether they monitor your state without being told. Not
applied: 16 items exceeds the chunk's stated 12–15 range and would need the range test
relaxed.

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

## Finding 7 — cross-instrument: the counterpart `relationship` scale is internally inconsistent

Not a defect in these items, but it lands on C-2 and should not be discovered there.
Within ManagerMatch's `relationship` dimension:

* `mm-q9` keys **personal closeness** high (0.80: *"knows you as a person"*)
* `mm-q10` keys **advocacy** high (0.70: *"advocates strongly for your interests"*)
* `mm-q11` keys **distance** high (0.80: *"trusts you enough to be hard to reach"*)

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
2. **Decide `mp-q16`** (Finding 3) — the fourth `relationship` item. Closes the positional
   residual and the missing warmth counterweight on the most exposed dimension. Needs
   Sebastian's sign-off because it moves the count to 16.
3. **C-2 content review carries Findings 4 and 6**: the environment-may-be-the-cause hedge
   on low-autonomy and low-feedback protocol cells, and behavior-not-person language
   throughout.
4. **Decide the pole-randomization question** (Finding 3, first half) before C-3 fixes the
   stored answer shape — it is cheap to allow for now and expensive to retrofit once
   answers are persisted by position.
5. **C-2 threshold decision on `relationship`** (Finding 7) — either a conservative
   threshold or a scheduled `mm-q11` rewrite.
6. Watch `growth_focus` by tenure band in pilot data (Finding 5). No action before data.

Nothing in `manager_profile.py` was changed after this review was written except as
recorded under Finding 3, and nothing in the v1 review file was touched — consistent with
how the rubric anchors went through Sebastian's ratification before being frozen.
