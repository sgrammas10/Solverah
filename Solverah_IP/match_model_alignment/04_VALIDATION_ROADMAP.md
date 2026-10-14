# Validation roadmap

**Status:** working draft, 2026-10-13. Three tiers, from weakest to strongest kind of
evidence. Nothing in a lower tier can stand in for a higher one. The bar for showing any
probability is at the end; it is a proposal for you and Sebastian to set, not a decision.

## Tier 1: Expert hypotheses (what we believe, and who believes it)

| Hypothesis | Source | Status |
|---|---|---|
| Penalty for each trait gap, in each direction | Your priors form, adopted 2026-09-17 (12 answers plus baseline) | Adopted as defaults. One expert. Each entry to gain a "why" and a date. |
| "8 in 10 who genuinely fit are still doing well" | Your baseline answer | Hypothesis. Not shown to users. |
| What each trait means and how to score evidence | Anchors v3.1, with your five rulings | PROPOSED, not verified by raters. |
| No cost inside a person's tolerance, straight-line cost beyond it | Sebastian, 2026-10-13 | Serving default; straight-line-from-zero kept as the comparison. |
| Which gap combinations compound | Draft from your notes (06) | Listed only. Ignored by the v1 math. |
| "Known" needs 3 or more scored items, one within 24 months, spread 0.4 or less | Ours | Provisional; goes through the sensitivity test. |

## Tier 2: Internal tests (does the machinery behave as designed)

These test whether the system is coherent and stable. They cannot show it predicts
anything about real people.

1. **Recovery simulations** (done for the outcome fit, 2026-09-29). Plant known weights in
   synthetic people, fit, see whether they come back. Result: at 100 people the direction
   is readable, the size is not.
2. **Your answers reproduce.** Your twelve answers are driven back through the live model
   and come out within 6e-07. Any change to the shape must keep this true at a full
   pole-to-pole gap.
3. **Sensitivity test** (planned). Nudge each penalty up and down by half, across
   synthetic people and the round-2 scored companies. A weight "matters" if the top five
   companies change by more than one, or rank correlation drops below 0.8. Weights that
   do not matter need less of your time; weights that do need more.
4. **Rater agreement on company scoring** (round 2, running). Independent raters score the
   same evidence packets. Agreement tells us whether the rubric is readable, not whether
   it is right.
5. **Blind pair raters** (planned). Raters who did not set the weights (not you, not
   Sebastian) judge person and company pairs. If their sense of "good fit" disagrees with
   the model's ranking, that is a finding about the weights.

## Tier 3: Real-world predictive evidence (does it predict outcomes)

1. **Pre-registered outcome fit**, written 2026-10-01 before any data. Look 1 at 100
   eligible people, Look 2 at 300, nothing in between. It asks one question: does the
   person-versus-job gap predict the "how well is this role working" rating, and is your
   overall harshness about right? An "undecided" at Look 1 is likely and acceptable.
2. **Exploratory outcomes** (02) reported alongside, labelled.
3. **90-day check-ins** after "I took this job", through Pulse. Directional only at first.
   This is the only route that tests CompanyLens's researched company picture, rather
   than people's descriptions of their own job.
4. **Long term:** fit the penalties to outcome data, with your values as the starting
   point. At roughly 1,000 outcomes per-trait weights become learnable.

## The bar before any probability is shown (proposed)

All of the following, not some:

1. Look 2 has run and the premise is **supported** (the gap predicts the outcome).
2. The model's overall scale is pinned down: its uncertainty range is narrow enough that
   the shown number would not change meaningfully across that range. The width is to be
   agreed before Look 2.
3. **Calibration is checked on held-out people.** Among those the model says have a 70%
   chance, about 70% are doing well, across the range, not only on average.
4. That check is done on the **population that would see the number.** For CompanyLens,
   that means people who took a job through the link and reported back, not only
   Environment Reports of current jobs.
5. You have read the result and agree the number means what its label says.

Until then users see per-trait reads, coverage and flags. That is the rule today.
