# Solverah — I-O Psychology Review Brief

**Scope: narrow and deliberately so.** This is not a request to review 24 items or six
constructs. It is a request to answer two methodological questions where a wrong answer
invalidates architecture already built, and which no amount of pilot data can fix after the
fact. Everything else can wait for a pilot.

Prepared 2026-08-18; revised 2026-08-19 — the confidence measure has since been decided, and
the sections describing it now state the actual design rather than a placeholder. Send with
`assessment_items_v2.yaml` attached.

---

## What the instrument is

A six-dimension work-preference profile, taken voluntarily by a signed-up user of a
career-matching product. It is **not** used for hiring, selection, or any high-stakes decision.
No employer sees an individual's answers or scores — that is a durable commitment, and the
output an employer could ever see is a match result, not the underlying profile.

**Dimensions:** autonomy (directed ↔ self-directed), pace (steady ↔ fast), collaboration
(solo ↔ collective), feedback (sparse/gentle ↔ frequent/blunt), innovation (execute/optimize ↔
invent/explore), decision (intuition ↔ data).

**Item format.** Four **forced-choice binary** items per dimension, 24 total. Each item is a
scenario with two options, one keyed to each pole. There is no Likert scale and no neutral
option.

**Ladder design.** The four items in a dimension are written as a **graduated-difficulty
(Guttman-style) ladder**: each rung is a harder endorsement of the high pole than the last,
graded by a variable specific to that dimension.

| dimension | grading variable | rungs, easiest → hardest |
|---|---|---|
| autonomy | stakes / scope / expected check-in frequency | routine task → low-risk project → others depend on it and it's visible → high-stakes |
| pace | duration sustained | an afternoon → a week → a couple of months → across a career |
| collaboration | coordination cost | one conversation → a recurring daily hour → an entire piece of work → a whole role |
| feedback | exposure (privacy + delay) | delayed/private → immediate → public → across a career |
| innovation | sunk investment discarded | something recent that works badly → a year-old process → something relied on that works → across a career |
| decision | novelty | a familiar call → one that rhymes → genuinely unprecedented → across a career |

Each dimension's grading variable is deliberately distinct, so that a respondent high on one
underlying disposition (e.g. risk tolerance) does not climb every ladder — which would
manufacture cross-dimension correlation out of the instrument's construction.

**Scoring.** `mean_pole` — the proportion of a dimension's four items answered at the high
pole. Over four items this yields exactly {0.00, 0.25, 0.50, 0.75, 1.00}, which is mapped onto
a five-band company-side scale {0.1, 0.3, 0.5, 0.7, 0.9}. Under honest Guttman responding a
respondent endorses a *prefix* of the ladder, so score is a direct function of how far up they
climb.

**Confidence.** Decided, not yet implemented: the **Guttman error count** — sort a dimension's
four responses into rung order, count e = the minimum answer-flips needed to reach a valid
prefix pattern (e ∈ {0, 1, 2} over four items). It describes how well a single ladder position
summarizes those four answers, and nothing else: a low-e profile is not assumed honest, and a
high-e profile is not assumed careless. An internal-consistency ("do all four answers point the
same pole") measure was considered and **rejected**: on a graduated ladder, item agreement is
equivalent to extremity — only 0.0 and 1.0 scorers could ever look consistent, and every honest
mid-scale respondent would read as maximally inconsistent. Downstream, the profile feeds a
Bayesian model where a low-confidence profile is shrunk toward a prior. One dimension's
confidence (feedback) is deliberately left unpopulated pending the pre-registered test in
Question 2.3.

**Design safeguards already in place**, mentioned so you don't spend time on them: the high
pole sits on option A in exactly two of four items per dimension (so positional straight-lining
scores 0.50, not an extreme); the hardest rung in every dimension is reverse-keyed; item order
within a dimension is randomized per respondent, and items are interleaved across dimensions so
the grouping is not visible; every item is answerable without prior employment history.

---

## Question 1 — reliability of four forced-choice items per dimension

**This is the one that matters most, because it is load-bearing.** Four items per dimension is
not a convenience. `mean_pole` over exactly four items is what produces the five-point lattice
the downstream Bayesian model is built on. Five items would silently invalidate that constant
and every result derived from it. So "add more items" is not a cheap fix here — it is a
re-architecture.

**Please advise on:**

1. Can four binary forced-choice items yield usable reliability for a preference construct in
   this application? What would you expect, and by which coefficient — noting that Cronbach's
   alpha is questionable for a Guttman-scalable set and for binary forced-choice items?
2. Is there a defensible reliability floor for this use case — voluntary self-profiling feeding
   a recommendation, with an explicit confidence measure and shrinkage-to-prior for weak
   profiles — as distinct from the floor you would demand for a selection instrument?
3. If four is too few, is there a construction that preserves a five-point lattice from more
   items? We would rather change the item count and re-derive the constant than ship an
   instrument with unusable reliability, but we need to know that before a pilot, not after.
4. The scoring is **ipsative within an item** (choosing one pole necessarily rejects the other)
   but **not ipsative across dimensions** — a respondent can score high on all six. Does that
   partial ipsativity create problems for the reliability estimate or for the downstream
   correlational analysis we plan?

## Question 2 — is Guttman difficulty ordering defensible for *preference* items?

Guttman scaling comes from ability and attitude measurement, where "harder" has a natural
meaning: a harder item is one fewer people can endorse. We have applied it to **preference**
items, where the analogous claim is that endorsing the high pole gets progressively more
demanding as the grading variable increases.

**Please advise on:**

1. Is that a sound transfer, or does preference measurement break the assumption that makes
   Guttman scaling work? Specifically: an ability ladder is unidimensional by construction
   (you cannot solve the hard item without the skill for the easy one), whereas a preference
   ladder relies on the *designer's* claim that the rungs are ordered on one variable.
2. What should we compute on pilot data to test whether the ordering holds — coefficient of
   reproducibility, coefficient of scalability, something else — and what threshold would you
   treat as the ladder failing rather than being noisy?
3. **A specific known problem.** The feedback dimension's grading variable is stated as
   "exposure — privacy and delay," which is two variables. Rungs 1 and 2 grade *delay*
   (mentioned later vs. immediately); rung 3 grades *audience* (privately vs. in front of the
   team); rung 4 grades both, forcing the "tell me immediately, but not in front of everyone"
   respondent to pick which aversion wins. That preference is coherent and common, and under it
   the error count is wrong in *both directions*: one resolution of rung 4 yields a valid
   prefix (e = 0) — a *confidently wrong* mid-scale score — while the mirror preference ("in
   the room is fine, just not straight away") yields an honest non-prefix pattern that e
   penalizes. We have pre-registered a prediction that these patterns will appear in excess on
   feedback relative to the other five dimensions (conditioning on the score, so "feedback just
   has more moderates" is controlled), and we leave feedback's stored confidence NULL until
   that test runs. Is keeping it as a two-factor construct and measuring it the right call, or
   should the dimension be split or re-graded before any pilot?
4. Related: is the error count the right general treatment of non-prefix patterns? `mean_pole`
   scores them but discards the ordering information; e retains it as a coarse three-level
   quality signal on the score. If you would compute something else — a likelihood under a
   formal Guttman-with-error model, a person-fit statistic — we would rather hear it now than
   after the pilot.
5. **A second, likely-analogous problem, caught late.** Autonomy's grading variable is stated
   as "stakes / scope / expected check-in frequency" — also two variables, not one, and the
   item wording bears it out. The easiest rung (`au1v2`) poses "do it your usual way without
   checking in" against "confirm the expected approach first" at low stakes — a pure
   check-in-frequency contrast. The hardest rung (`au4v2`) poses being left to a high-stakes
   call "with no one available even once to sanity-check" against being "expected to check in
   and get sign-off on the direction and the plan before starting" — check-in frequency again,
   now at high stakes. A respondent who is comfortable with high stakes but wants frequent
   check-ins — the autonomy analog of "tell me immediately, but not in front of everyone" — can
   land on a contradictory rung pattern the same way the feedback respondent above does. We have
   not pre-registered a test for this the way we have for feedback, and autonomy's confidence is
   currently populated on the assumption the ladder is clean. Should it be treated the same way
   as feedback — held out, pre-registered, tested before trusting its confidence — or is stakes
   and check-in frequency close enough in practice that this doesn't rise to the same problem?

---

## What we are explicitly *not* asking

- Whether the 24 items are well-written. We have done bias review and structural review, and
  wording is ratified.
- Whether the six dimensions are the right six. That's a product decision.
- Whether real respondents' answers follow the ordering — that is a pilot question and we plan
  to run one. We are asking whether the *design* is sound enough to be worth piloting.

## What we can provide

`assessment_items_v2.yaml` (all 24 items with design rationale inline), the structural gate that
enforces the design constraints, and the calibration probe methodology. No respondent data
exists yet — nothing here has been piloted.

## What a useful answer looks like

A short written opinion on questions 1 and 2, with any threshold or statistic you would want us
to compute on the pilot. If the answer to question 1 is "four items is not enough," we need
that stated plainly and early, because it changes the architecture rather than the wording.
