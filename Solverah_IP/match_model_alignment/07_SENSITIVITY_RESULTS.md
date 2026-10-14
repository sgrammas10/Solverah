# Sensitivity test: which penalty weights move the ranking

**Status:** first run, 2026-10-13. Step (2) of "What changes the weights, cheapest
first" (`docs/PRODUCT_DECISIONS.md` section 2) and item 3 of Tier 2 in
`04_VALIDATION_ROADMAP.md`. Script: `causal_graph/v1_model/sensitivity.py`; results
file: `causal_graph/v1_model/results/sensitivity_2026-10-13.json` (seed 20261013,
priors `sha256:22688a649553`). Re-run with
`python -m causal_graph.v1_model.sensitivity --out <path> --table`.

## The question

Julie's penalty table (`priors.yaml`) has twelve dimension weights: for each of the
six traits a size (`mag`, how much any mismatch costs) and a direction (`dir`, which
way of being wrong is cheaper). This test asks, one weight at a time: **if this number
were half as big, or half again as big, would people see a different top five?** A
weight that cannot move a ranking does not need more of anyone's time until outcome
data exists. A weight that moves rankings for many people is where evidence (blind
raters next, outcomes later) should go first.

## The headline

Four weights move rankings. Eight do not.

| Weight | Julie's value | Verdict | What it means |
|---|---|---|---|
| **pace.mag** | -2.52 | **Needs evidence before launch** | The costliest penalty in the table and the one that moves rankings most: 35% of unanswered-tolerance people on the real set, 26% on the synthetic set, see a different top five or a reordered list when it is halved or half-again-ed. |
| **innovation.mag** | -1.73 | **Needs evidence before launch** | Moves rankings for a third of people on the real set and one in ten on the synthetic set. The six real companies spread widely on innovation (0.25 to 0.80), which is why it bites there. |
| **innovation.dir** | 0 (elicited equal) | **Needs evidence before launch** | Julie's two answers were equal (5 and 5), so this is a zero. A zero cannot be nudged by 50%, so it was moved by an absolute +-0.87 (about "6.5 vs 3.5 in ten" instead of "5 vs 5"). That size of asymmetry would move rankings for a third of people on the real set. The question for Julie is not "is the number right" but "are the two directions really equal". |
| **feedback.mag** | -1.73 | **Needs evidence (borderline)** | Over the line on the real set (12.5% of unanswered people), just under it on the synthetic set (9.5%). The second-largest penalty; it matters where companies differ on feedback. |
| pace.dir | -0.28 | Stop debating | At most 1% of people see a change. |
| autonomy.mag | -0.67 | Stop debating | Under 9% on the real set, under 1% on the synthetic set. |
| autonomy.dir | 0 (elicited equal) | Stop debating | Same absolute probe as innovation.dir (+-0.34); under 9% / under 1%. |
| collaboration.mag | -0.95 | Stop debating | At most 4%. |
| collaboration.dir | +0.28 | Stop debating | At most 0.5%. |
| feedback.dir | +1.06 | Stop debating | At most 5%, although it is Julie's strongest asymmetry. The direction matters less than the size on this trait. |
| decision.mag | -0.87 | Stop debating | At most 6%. |
| decision.dir | +0.87 | Stop debating | At most 6%. |

Plainly: **the size of the pace and innovation penalties, and whether innovation
really is direction-neutral, are the three things worth a rater's or Julie's hour.**
The feedback size is a fourth, close behind. The other eight weights could each be
50% off and almost nobody would see a different list.

A pattern worth naming: every `dir` weight except innovation's is in the "stop
debating" group. The *sizes* of the penalties drive the ranking; the *directions*
barely do, at the sizes Julie gave them. That is not a reason to drop the directions
(the Situation Report reads them for its ordering and its guidance), only a reason not
to spend evidence on them first.

## Full tables

Flagged = share of people whose ranking moved past the threshold under that tolerance
profile (worse of the two nudge directions). Min tau and min top-5 are the single worst
person across all profiles and both directions. "rel" = +-50% of the weight; "abs" = the
zero-weight probe described above.

Threshold: a person is flagged when top-5 overlap < 4 or tau < 0.8; a weight matters when >= 10% of people are flagged under any profile, either direction.

### real (6 companies; 6-6 rankable per person)

| weight | value | nudge | flagged unanswered | flagged typical | flagged wide | min tau | min top-5 | verdict |
|---|---|---|---|---|---|---|---|---|
| autonomy.dir | +0.000 | abs | 9.0% | 7.0% | 4.5% | 0.47 | 4 | does not move rankings |
| autonomy.mag | -0.674 | rel | 8.5% | 6.5% | 3.0% | 0.47 | 4 | does not move rankings |
| pace.dir | -0.276 | rel | 1.0% | 0.0% | 0.0% | 0.73 | 4 | does not move rankings |
| pace.mag | -2.516 | rel | 35.0% | 20.0% | 7.5% | 0.07 | 4 | MATTERS |
| collaboration.dir | +0.276 | rel | 0.5% | 0.0% | 0.5% | 0.60 | 4 | does not move rankings |
| collaboration.mag | -0.950 | rel | 4.0% | 1.5% | 1.0% | 0.60 | 4 | does not move rankings |
| feedback.dir | +1.059 | rel | 5.0% | 2.5% | 2.0% | 0.47 | 4 | does not move rankings |
| feedback.mag | -1.733 | rel | 12.5% | 7.0% | 8.0% | 0.20 | 4 | MATTERS |
| innovation.dir | +0.000 | abs | 33.0% | 21.0% | 5.5% | -0.07 | 4 | MATTERS |
| innovation.mag | -1.733 | rel | 34.0% | 27.0% | 9.5% | -0.07 | 4 | MATTERS |
| decision.dir | +0.866 | rel | 6.0% | 1.5% | 1.0% | 0.60 | 4 | does not move rankings |
| decision.mag | -0.866 | rel | 5.5% | 1.5% | 1.0% | 0.60 | 4 | does not move rankings |

### synthetic (30 companies; 30-30 rankable per person)

| weight | value | nudge | flagged unanswered | flagged typical | flagged wide | min tau | min top-5 | verdict |
|---|---|---|---|---|---|---|---|---|
| autonomy.dir | +0.000 | abs | 0.5% | 0.5% | 0.0% | 0.89 | 3 | does not move rankings |
| autonomy.mag | -0.674 | rel | 0.5% | 1.0% | 0.0% | 0.89 | 3 | does not move rankings |
| pace.dir | -0.276 | rel | 0.0% | 0.0% | 0.0% | 0.95 | 4 | does not move rankings |
| pace.mag | -2.516 | rel | 25.5% | 13.5% | 13.0% | 0.63 | 1 | MATTERS |
| collaboration.dir | +0.276 | rel | 0.5% | 0.0% | 0.0% | 0.94 | 3 | does not move rankings |
| collaboration.mag | -0.950 | rel | 1.0% | 0.5% | 0.0% | 0.85 | 3 | does not move rankings |
| feedback.dir | +1.059 | rel | 2.0% | 1.5% | 0.0% | 0.83 | 3 | does not move rankings |
| feedback.mag | -1.733 | rel | 9.5% | 3.0% | 3.5% | 0.73 | 2 | does not move rankings |
| innovation.dir | +0.000 | abs | 10.5% | 9.5% | 1.5% | 0.66 | 2 | MATTERS |
| innovation.mag | -1.733 | rel | 11.0% | 10.0% | 1.5% | 0.66 | 2 | MATTERS |
| decision.dir | +0.866 | rel | 2.5% | 1.0% | 1.5% | 0.79 | 2 | does not move rankings |
| decision.mag | -0.866 | rel | 3.0% | 1.0% | 1.5% | 0.79 | 2 | does not move rankings |

## Method

**What is nudged.** Each of the twelve dimension weights, one at a time, to 0.5x and
1.5x its value. The two weights that are exactly zero (autonomy.dir, innovation.dir)
get an absolute probe instead: +-0.5 times that trait's `mag`, labelled "abs". The
intercept and the confounder weights are not nudged; they shift every company by the
same amount for a given person (or every person by the same amount) and cannot reorder.

**How the ranking is made.** Exactly as the app makes it. The script calls the
production match service's own functions (`company_match_service`: the six trait
reads, the one `point_z` call, the ordering) with only the weights swapped. So the
hinge is on (no penalty inside the person's tolerance, growing penalty outside), an
unknown trait is left out of the score, a mixed trait counts at its worse end, and a
company that breaks a must-have sorts last whatever its score. Only companies with at
least three known traits have a position to move.

**Who.** 200 synthetic people, each trait drawn uniformly from the five-point person
lattice, fixed seed. Each person is run three times:

| Profile | Flat zone per trait | Must-haves |
|---|---|---|
| unanswered | 0.15 both sides (the floor; "today's behaviour") | none |
| typical | 1 step = 0.25 both sides | 0, 1 or 2 traits (50% / 30% / 20%) |
| wide | 2 steps = 0.50 both sides | same draw as typical |

**Which companies.** Two sets, reported separately.

*Real:* the six round-1 evidence packets (P-01 to P-06; the packet-to-company map is
`causal_graph/reidentification_attack.GROUND_TRUTH`). Each trait is treated as
**known** at the mean of every scoring on file for it: the three round-1 human raters
(A, B, C; v1 anchors) and the five gpt-5.5 scorer-variance v2 runs. No round-2 draws
exist yet (no live run has happened), so this is the best real set there is. Their
confounders (size band, comp posture, industry) are unknown and masked. The values:

| Packet | autonomy | pace | collaboration | feedback | innovation | decision |
|---|---|---|---|---|---|---|
| P-01 | 0.33 | 0.65 | 0.68 | 0.48 | 0.53 | 0.70 |
| P-02 | 0.35 | 0.73 | 0.65 | 0.43 | 0.30 | 0.58 |
| P-03 | 0.68 | 0.88 | 0.68 | 0.58 | 0.65 | 0.68 |
| P-04 | 0.70 | 0.80 | 0.68 | 0.48 | 0.80 | 0.43 |
| P-05 | 0.75 | 0.38 | 0.35 | 0.33 | 0.38 | 0.58 |
| P-06 | 0.33 | 0.43 | 0.70 | 0.38 | 0.25 | 0.65 |

*Synthetic:* 30 companies drawn from the anchor bands (0.1 / 0.3 / 0.5 / 0.7 / 0.9),
same seed. A known trait is the mean of three band draws; about a quarter of companies
have one to three traits that are mixed (one end low, one high) or unknown; every
company keeps at least three known traits. Size band, comp posture and industry are
drawn, with some missing. This set exists because six companies are too few to read a
top five from (next section).

**What "matters" means.** For each person and nudge: the overlap between the baseline
top five and the nudged top five, and Kendall's tau (rank correlation) between the two
full orderings. A person is flagged when overlap is below 4 of 5 or tau is below 0.8,
the two thresholds `PRODUCT_DECISIONS` set. A weight matters when at least **10% of
people** are flagged under any profile, in either direction. The 10% is our choice (the
decision left the share open): a ranking that changes for one person in ten is a
product change. It is written into the results file so the reader never has to guess
it.

## Limits

1. **Six real companies is a small ranking.** With six items a top five can lose at
   most one company, so top-5 overlap never flags on the real set; tau does all the
   work there, and tau on six items is coarse (two adjacent swaps already read as
   0.73). The synthetic set is where the top-5 criterion is meaningful. Read the real
   set as "which weights move the order of *these six*", and the synthetic set as the
   general stability result. The two agree on pace.mag, innovation.mag and
   innovation.dir; they disagree only at the margin on feedback.mag.
2. **The real company scores are the mean of eight scorings under two rubric
   versions** (human raters on v1 anchors, gpt-5.5 on v2). They are the best estimate
   on file, not a validated company read. Re-run on real research records when the
   first live research run has happened.
3. **The synthetic people are uniform on the lattice**, which puts more people at the
   poles than a real population would have; pole people are the ones a `mag` change
   moves most. Real core-score distributions will shift these shares, probably down.
4. **A 50% nudge is one size.** It is roughly the difference between "7 in 10" and
   "5 in 10" on Julie's form. A weight that is robust to 50% could still be wrong by
   more; this test says where a moderate error would show, not that the table is right.
5. **Unanswered tolerance flags most.** The floor zone (0.15) is where small weight
   changes move the most people; a stated 2-step tolerance absorbs most of them. The
   first users will mostly be unanswered, so the "unanswered" column is the one that
   describes launch.
6. **Not tested here:** the "known" thresholds (count, recency, spread) named in the
   roadmap as going through this test. They act on whether a trait is known at all,
   which is a research-pipeline question, not a weight. The script takes any company set
   as input, so a second run that varies those thresholds on real records is a small
   follow-up once records exist.

## What this changes

- Blind-rater pairs (roadmap Tier 2, item 5; C10) should be built so they can separate
  a pace-size error and an innovation-size error from everything else: pairs that
  differ mainly on pace, and pairs that differ mainly on innovation, with the
  direction of the innovation gap varied.
- The one question worth putting to Julie from this run, when she has a minute: on
  innovation, is a person who wants to invent in an execute-and-optimise role really
  as badly off as the reverse? Her two answers were 5 and 5; this test says that if
  they were 6.5 and 3.5 either way, a third of people would see a different list.
- Nothing here changes `priors.yaml`. A weight change is pre-registered first.
