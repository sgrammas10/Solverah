# Solverah — The Level/Role Question

**Decision memo. Resolves open item #1 from the 2026-08-10 handoff.**
Reconciled against `SOLVERAH_HANDOFF_2026-08-13.md` and the P-03 packet as built.
Custom instruction honored: logical, future-thinking, not agreeable.

---

## Headline

**The P-03 dispersion result does not support the claim built on it.** Three of its four
would-recommend percentages — including the 24% that drives the whole finding — **fail the
achievability check you locked on 2026-08-10.** What survives measures satisfaction, not your
dimensions, and is confounded with review-writer selection.

Level does not enter the v1 model. It gets captured, as an extension of the scope block v4.4 already
added, and tested when outcomes exist.

---

## 1. The headline number is arithmetically impossible

From the P-03 packet, Section B-i, per-title filter counts and rates as displayed:

| Title | n at filter | shown | nearest achievable | verdict |
|---|---|---|---|---|
| Trader | 32 | 86% | 84.38% / 87.50% | **impossible** |
| Software Developer | 64 | 91% | 90.62% / 92.19% | ok |
| Quantitative Researcher | 11 | 81% | 72.73% / 81.82% | **impossible** |
| **Junior Trader** | **16** | **24%** | **18.75% / 25.00%** | **impossible** |

At n=16 the recommendation rate steps in 6.25-point increments. 24% is not one of them. At n=11 it
steps in 9.09-point increments; 81% is not one of them either.

This is the **exact defect recorded against P-04 on 08-10** — "99% would recommend from 14 reviews,
impossible, values step by ~7.1%" — which produced the locked rule: *every percentage must be
achievable at that n*, and *treat percentages as unreliable by default*.

**The rule was written for P-04 and never applied backwards to P-03.** Verification script:
`pct_check.py`.

Three failures out of four is not a rounding quirk, it is systematic: the percentage is almost
certainly computed over a **different denominator** than the title-filtered review count shown beside
it — a different window, or the whole-company population. Which means:

* The n values are not the n of the percentages.
* **You cannot compute a gap between two of these rates**, because you don't know either denominator.
* The "67-point recommendation gap" has no defined sample size and should not appear in any packet,
  handoff or decision until it does.

**The subratings are probably fine.** The 08-10 prior — six category ratings sound more often than
the recommend / CEO-approval percentages — holds here. Senior management 4.6 (Trader) vs 2.8 (Junior
Trader) is not challenged by this check.

### Live packet defect

`P-03_packet.txt` lines ~238–249 present the five-title table **to the rater**, including the 24%,
with the prose "a 67-point spread on recommendation rate, inside one firm." That is rater-facing
content resting on a number that fails your own validation gate. Fix it in the v4.4 rebuild — which
decision 2 of 08-13 already requires for all six packets, so the cost is zero.

---

## 2. What survives measures the wrong construct

Even taking the subratings at face value, the P-03 table mixes two different things:

| | Trader | SoftDev | QuantRes | TradIntern | JuniorTrader |
|---|---|---|---|---|---|
| Overall | 4.2 | 4.4 | 4.3 | 4.0 | **3.7** |
| Senior management | 4.6 | 3.9 | 3.9 | 4.0 | **2.8** |
| Work/life balance | 4.7 | 4.5 | 4.1 | **3.0** | 3.6 |

Rank by overall: SoftDev > QuantRes > Trader > TradIntern > JuniorTrader.
Rank by work/life balance: Trader > SoftDev > QuantRes > JuniorTrader > TradIntern.

**The orderings disagree.** Trader is third on satisfaction and first on work/life balance. The
intern is fourth on satisfaction and last on work/life balance. Two measures of one underlying
quantity do not do that.

Work/life balance is the only *descriptive* row — it says what the job is like. Overall and
senior-management are *evaluative* — they say how the writer feels about it. Your six dimensions are
descriptive by construction: autonomy, pace, collaboration, feedback, innovation and decision basis
are statements about an environment, not verdicts on it.

**The dramatic gaps are all in the evaluative rows. They are not measurements of your dimensions and
cannot be read as evidence that your dimensions vary by level.**

Consequence for the rubric: evaluative review metrics must be barred from serving as the verbatim
quote supporting a dimension score. 08-10 ruled them unreliable on *measurement* grounds. This rules
them out on *construct* grounds, which is the stronger and non-negotiable reason — a metric can be
perfectly measured and still be the wrong quantity.

---

## 3. The Junior Trader pattern has a selection explanation

The 08-10 handoff noticed the pattern isn't a seniority gradient — interns score 4.0, *above* junior
traders at 3.7. That observation is more damaging to the level hypothesis than it was credited for.

The first permanent trading seat at a prop firm is up-or-out with a high washout rate by design.
Survivors stop being Junior Traders and become Traders. So the Junior Trader bucket is enriched with
people who were cut; the Trader bucket is composed almost entirely of people who weren't. Interns
escape this because an internship ending is not a failure — it ends on schedule for everyone. That
is exactly why the intern row breaks the gradient.

This reproduces the whole table without any claim that juniors experience a different environment. A
washed-out junior and a successful senior can describe blunt feedback, high pace and low early
autonomy *identically* and rate satisfaction 60 points apart.

**Review-writer selection is confounded with level, and the confound is strongest exactly where the
signal looks strongest.** Modeling this table as a level effect imports a survivorship artifact into
the model as an environment property — the same class of error as dollars-comp, patent counts and
embeddings, now rejected three times for importing industry, size and prestige.

---

## 4. The one in-packet quote that bears on your dimensions is about desks, not levels

> work/life balance "can vary significantly depending on team and market conditions", mentorship
> "can depend heavily on the specific desk, manager, and business priorities", project ownership
> "can also be limited depending on the team"

Team. Desk. Manager. **Horizontal, not vertical.** That is the dispersion ordinal locked on 08-10 —
three levels, stored not modeled. **This half needs no new mechanism.** Score P-03 high-dispersion
and move on.

---

## 5. What actually survives

Strip the impossible percentages, the construct error and the selection artifact, and one concern is
left. It has no evidence behind it, and it is still the right thing to worry about.

**Descriptive dimensions are plausibly level-graded almost everywhere.** A junior has less autonomy
and thinner decision basis than a senior at nearly every company. That is a fact about organizations,
not about any one of them — and that is why it is survivable. Solverah **ranks and matches**; it does
not measure in absolute terms. A bias that shifts every company the same direction by roughly the
same amount cancels in the comparison. The candidate still gets the right ordering.

**The dangerous case is the interaction, not the main effect.** Companies differ in how *steeply*
autonomy is level-graded. A flat 40-person startup hands a junior real ownership; a bank hands a
junior none — while their senior populations may look similar. A company-level score built mostly
from senior voices compresses exactly the difference that matters most to an early-career user.

Specific, falsifiable, and completely untested. P-03 does not test it.

---

## DECISION

> **Level does not enter the v1 model. It is captured as an ordinal on every review-derived note —
> an extension of the v4.4 scope block, not a new mechanism — so the interaction hypothesis is
> testable the moment outcome data exists.**

Same shape as the dispersion decision: **storage ≠ features**. Third consistent application of a
framing already locked.

### Why not model it

1. **It cannot be populated.** The 08-13 Best Buy title index settles this: 4,801 Sales Associate
   reviews against **5** Software Engineer, **4** Product Manager, **3** Data Analyst, for an
   employer of 85,000+. Role- or level-conditional scores need a populated cell per (company,
   stratum). Most cells are empty and no amount of effort fills them. **This is the binding
   constraint and it is stronger than every argument below.**
2. **Resolution.** Scorer SD ≈ 0.098; you moved to five bands of width 0.2 because finer
   distinctions sit below the instrument's floor. Level-conditional scoring means 6 dimensions × k
   levels, each from a *thinner* bucket than the pooled score, with junior buckets thinnest. That
   adds noise and calls it resolution — the objection that killed adding dimensions.
3. **Unvalidated priors.** Twelve coefficients already sit on zero training rows. A level interaction
   adds more on theory alone. Fourth instance of the pattern; reject it the same way.
4. **The person side has no level input.** Matching level-conditional scores needs candidate level.
   Self-reported seniority is noisy and inflated — a new measurement error introduced to fix a
   measurement error.
5. **Production parity.** Level-conditional scores need per-title stratified sampling per company.
   Open item #7 flags that this may not be reproducible at scale, and 08-13 decision 8 already bars
   authenticated sources for the same parity reason. If production can't stratify, level-conditional
   scoring cannot exist there, and calibrating against input the extractor never sees is the failure
   you objected to in July.
6. **The evidence is confounded and partly impossible.** Sections 1 and 3 above.

### Why capture it anyway

* **Free, and not retrofittable.** Job title arrives attached to every review. Packets built without
  the tag need a full rebuild to add it — and all six are being rebuilt under v4.4 right now, so this
  is the only cheap moment it will ever have.
* **It is the only way to test the interaction.** No captured level, no test, and the hypothesis
  stays permanently unfalsifiable — the specific defect you rejected in Julie's tension layer.
* **It buys a v1 product mitigation with zero coefficients.** Below.

### Capture spec — an extension of hard rule 8 / the 2g scope block

Per review-derived note, alongside the existing scope metadata:

`level_ordinal` ∈ { `intern`, `ic_early`, `ic_mid`, `ic_senior`, `manager`, `exec` }
`raw_title` — the verbatim title string, always stored

`intern` stays separate from `ic_early`. The P-03 intern row breaks the gradient and the selection
pressure on interns is structurally different; folding them together destroys the one row that
identifies the artifact.

**Job title is not level.** "Senior Software Engineer" at a startup and at a bank are different rungs.
Map titles to levels by an explicit versioned rule and **always keep the raw string** — the mapping is
revisable, the raw title is not recoverable later. Without this you are modeling title inflation.

Note the interaction with D10 and D11 from the defects log: the same title appears in two function
categories with different counts, and category labels are not function labels. Level tagging must key
off `raw_title`, never off the site's category.

---

## The v1 mitigation that costs no coefficients

The exposed user is the early-career candidate, and the narrative layer can serve them now.

Where level-stratified evidence diverges from the pooled evidence, surface it as prose with evidence
IDs cited per sentence — the architecture agreed on 08-10. "Reviews from junior trading roles
describe mentorship and desk assignment differently from senior reviews" is honest, auditable by the
same citation harness, and moves no score.

**Do not let it move the score.** A hedge in the interface is information; a hedge in the ranking is
an unvalidated prior wearing a disguise.

---

## Pre-registered tests — recorded before looking

**Test 0 — apply the achievability rule to every packet, retroactively. Do this first.**
P-03 and P-04 both carry percentages. Run `pct_check.py` logic over every displayed percentage in
every packet. Any figure that fails is struck from the packet and from any conclusion drawn on it.
Expected: most recommend / CEO-approval / outlook percentages fail; most six-category subratings
pass. **If a decision anywhere in the project rests on a failing figure, that decision reopens.**

**Test A — is the descriptive/evaluative split real? (runnable now)**
Score the six dimensions per title bucket for P-03 and P-04 where bucket n permits, using the
multi-run median discipline the variance test forced. Compare within-company between-title SD on
*descriptive dimension scores* against the ~0.098 noise floor.

* SD ≤ ~0.10 → indistinguishable from scorer noise. Company-level scoring stands, level stays
  stored-only, item #1 closes.
* SD materially > ~0.10 → level-conditional scoring becomes a live v2 candidate and #7 turns blocking.

Buckets are small (11–64, and those counts are themselves suspect per Test 0). Report the estimate as
noisy rather than over-reading it.

**Test B — is the interaction real? (needs outcome data)**
Regress fit-prediction error on candidate level. A level **main effect** is the near-universal grading
and is uninteresting. A **company × level interaction** is the finding, and it enters v2 as an
interaction term — never as separate per-level company scores.

**Test C — the selection control.**
Where a bucket's evaluative scores diverge sharply from its descriptive scores, flag it
**selection-suspect**, not dispersion-high. P-03 Junior Trader is the worked example.

---

## Consequences for rubric v4.4 / rubric v3 (open item #6)

* Add `level_ordinal` + `raw_title` to every review-derived note; add the versioned mapping table.
* Add the achievability check as a **hard gate on recording any percentage**, not advisory. It exists
  in the P-04 notes; it needs to be a rule in the prompt, because it just failed to propagate.
* Bar evaluative metrics (would-recommend, CEO approval, senior-management rating) from serving as
  the verbatim quote behind a dimension score. Construct grounds, not just reliability grounds.
* No change to the scoring surface. No new coefficients. **Rubric work is unblocked.**

---

## What I am not claiming

Not that level doesn't matter. That P-03 does not show it does; that the mechanism P-03 *does* show
is already covered by dispersion; that the headline number fails your own validation rule; and that
adding a level feature now would put an unvalidated, selection-confounded, partly unpopulatable prior
into a model already carrying twelve against zero training rows.

The concern is real on theory, unevidenced in the data you have, cheap to prepare for, and expensive
to act on early. Capture it, test it, let outcomes decide.
