# Person ↔ company scale calibration — what the check should actually be

The canonical handoff flags this as "load-bearing" but never defines a check — it's a named
worry, not a task. This turns it into one, using the real instruments (`assessment_items.yaml`
and the frozen `anchors.json`), not a hypothetical description of them. Two structural problems
turned up just from reading both side by side, which is itself the argument that this needs a
real check rather than an assumption that "both produce a 0..1 number" is sufficient.

## What "calibrated" has to mean

`build_model.py`'s `fit_gap()` is `person_score - env_score` on the same axis, and every downstream
weight (`mag`, `dir`) is fit against that signed difference. For the gap to mean anything, a
person scoring 0.7 on autonomy and a company scoring 0.7 on autonomy must represent **the same
standing on the underlying trait** — not just the same number from two different instruments that
happen to both output `[0,1]`. That's the whole claim to check. It is not automatically true just
because both sides were designed with the same six dimension names and pole labels.

## Finding 1 — the two sides quantize to different, mostly non-overlapping lattices

Company scores are 5 fixed bands: `{0.1, 0.3, 0.5, 0.7, 0.9}` (deliberate design, 08-10 handoff).

Person scores are `mean(pole_value)` over 4 forced-choice items, each contributing exactly 0 or 1.
The only achievable values are:

```
{0.0, 0.25, 0.5, 0.75, 1.0}
```

(verified by enumeration, not assumption — see the arithmetic in this repo's session log).

**These two five-value sets overlap at exactly one point: 0.5.** A person can never score 0.3 or
0.7 or 0.1 or 0.9 — the values a company routinely lands on. The closest a person can get to a
company's 0.7 is 0.75 (gap 0.05) or 0.5 (gap 0.2); there is no way to land a true zero gap against
a company scored anywhere except 0.5. This wasn't a deliberate joint design choice — the person
lattice falls out of "4 items, binary each" as a mathematical necessity, and the company lattice
was chosen independently in the 08-10 session for an unrelated reason (band width above the
LLM's measured noise floor). **Nobody designed these to interoperate; they coincidentally both
produce five values.**

This alone doesn't invalidate the gap — a quantization offset just adds noise, and 0.05–0.2 is
comparable to the LLM's own measured scorer SD (~0.03–0.11 depending on dimension, per the
2026-08-17 variance re-test). But it means **a "perfect" person-company match can never show
gap=0** except at the single shared value 0.5, which is worth knowing before anyone reads a small
nonzero gap as evidence of mismatch.

## Finding 2 — the two sides aren't just differently-quantized, they measure differently in kind

This is the bigger issue. Compare, for autonomy:

* **Company anchor at 0.7** ("leaning self-directed"): *"ICs own outcomes and choose their
  approach with light approval. 'Ownership,' results-over-process language present."*
* **Company anchor at 0.9** ("self-directed"): *"Individuals set their own priorities and methods
  with minimal approval. High-trust, flat decision rights pervade the evidence."*
* **Person item `au1`, high-pole option**: *"Map out your own approach and run with it, checking
  in only when needed."*

`au1`'s high-pole wording — "checking in only when needed" — reads closer to the company's 0.7
band ("light approval") than its 0.9 band ("minimal approval... high-trust, flat decision
rights"). But a person who picks the high-pole option on `au1` gets full credit (1.0 on that item)
toward what could become a 1.0 dimension score if they also pick high on `au2`–`au4` — even though
none of the four items individually describes anything as extreme as the company's top band.

The company rubric is **one graded judgment across five explicit intensity levels.** The person
instrument is **a proportion of forced binary choices**, where each item only asks "which pole,"
never "how strongly." A mildly self-directed person and an extremely self-directed person can both
land at 1.0 if the item wording doesn't force them to distinguish — the format has no room for
"somewhat," only "which side." **These are two different measurement models that happen to both
output a number in `[0,1]`.** Matching numbers between them is an assumption, not a verified
property, and Finding 1 shows nobody has tested it.

## The check to actually run — paired vignette probe

This is buildable now, doesn't need real users or more companies, and directly tests
cross-instrument agreement using content where the "true" answer is fixed by construction (the
same trick the ground-truth packet exercise uses to validate the company scorer alone — this
extends it to validate agreement *between* the two scorers).

**Method:** for each of the 6 active dimensions, write 3 short paired vignettes per dimension (15
low, mid, high on the pole) — 18 total pairs, 36 short texts:

1. A **person vignette**: a short first-person scenario description, written to deliberately imply
   a specific point on the dimension (e.g., "extremely self-directed" for the 0.9 target).
2. A **company vignette**: a short company-culture description, written by the same author in the
   same sitting, deliberately targeting the *same* point on the same dimension.

Score the person vignette by hand-answering the 4 real `assessment_items.yaml` items for that
dimension as the vignette character would answer them, and run it through the real scoring
function. Score the company vignette by running it through the real frozen rubric / LLM scorer
(the same call `scorer_variance_test_v2.py` already makes) — ideally n=5 per vignette, given the
now-measured per-dimension scorer noise, so a single run's band-edge landing doesn't get
over-read.

**What would pass:** for a pair both targeting "high," the person score and the mean company
score should be within roughly one instrument-noise-width of each other (~0.15–0.2, using the
larger of the two sides' measured SDs) — not exact agreement, given Finding 1's lattice mismatch,
but no *systematic* directional gap across all 18 pairs.

**What would fail, and what it would mean:** if person scores systematically run higher (or
lower) than company scores across most pairs at the same intended level, that's a real
calibration offset — evidence the two instruments' "0.7" don't mean the same thing on that
dimension, most likely traceable to Finding 2 (item wording not matching anchor-text intensity).
The fix would be rewriting the affected items' wording to intensity-match the anchor bands they're
meant to correspond to, not adjusting the model.

**Cost:** cheap. Writing 36 short vignettes is an afternoon; scoring the company side is 18 × 5 =
90 LLM calls (a few dollars); scoring the person side is answering 18 × 4 = 72 forced-choice items
by hand, which can be done by whoever writes the vignettes since the "true" answer is baked in by
design.

## A weaker, later check: distributional sanity once real data exists

Once real people have taken the assessment (n≳30) and enough companies are scored, compare the
two marginal distributions per dimension. This has limited power on its own — there's no reason
real people and real companies should be distributed identically — but it's a useful red-flag
check: if one side's distribution is collapsed into 1–2 bands while the other spreads across all
five (a real risk on the company side, per the 08-17 variance finding that several dimensions
landed at the same band on every single run), that predicts systematically inflated or deflated
gaps for reasons that have nothing to do with actual person-company mismatch. Cheap to check once
the data exists; not actionable before then.

## The eventual real test — not actionable yet

The gold-standard check is behavioral: does the *sign* and *magnitude* of a dimension's gap
predict the *direction* of dissatisfaction in `outcome_experienced` data (e.g., large positive
autonomy gaps — person wants more than the company gives — showing up disproportionately in low
`working_scale` ratings, specifically with autonomy-flavored complaints). This is exactly what the
`dir` weight in the model is meant to eventually capture, but it requires real placement outcomes,
which don't exist yet and won't for a while. Naming it as the real target, not proposing it as
next-step work.

## Recommended order

1. **Run the paired-vignette probe** (buildable now, cheap, directly tests the load-bearing claim)
   before trusting any live person-company ranking, per the canonical handoff's own instinct that
   this should happen "before trusting live rankings."
2. If it fails on a specific dimension, rewrite that dimension's person-side item wording to
   intensity-match the anchor bands — not the company rubric, which is already frozen and signed
   off for round 1.
3. Revisit the distributional check once real assessment + company data exist at meaningful volume.
4. Keep the eventual outcome-based check in view as the actual validation, once outcomes exist.

Nothing here has been run — this is the check specified, not executed. Running it needs: (a) the
18 vignette pairs written, (b) LLM API access for the company side (blocked in this sandbox by the
network allowlist, same as the other pending tasks), (c) someone to hand-score the person side
against the real item bank.
