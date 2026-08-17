# Person ↔ company scale calibration — what the check should actually be

The canonical handoff flags this as "load-bearing" but never defines a check — it's a named
worry, not a task. This turns it into one, using the real instruments (`assessment_items.yaml`
and the frozen `anchors.json`), not a hypothetical description of them. Two structural problems
turned up just from reading both side by side, which is itself the argument that this needs a
real check rather than an assumption that "both produce a 0..1 number" is sufficient.

**Amended 2026-08-17b.** This check was specced against a snapshot of the scoring pipeline and the
person-item bias review that has since moved. The changes below are additive corrections, not a
rewrite of the underlying logic — Findings 1 and 2 still hold exactly as originally stated. What
changed: (1) `scorer_pipeline.py` now exists and is the real interface the company side must call,
not the file this doc originally pointed at; (2) `ASSESSMENT_ITEMS_BIAS_REVIEW.md` now exists and
independently flags the same two dimensions (feedback, decision) this doc's own worked example
was already worried about, for a different mechanism — the two findings need to be told apart, not
conflated; (3) the tolerance number this doc originally proposed was derived from a pooled metric
the project's own later work (S1-3, same session) showed to be misleading; (4) the sprint that
built the citation verifier this doc references is now COMPLETE, not on hold, so infrastructure
assumed hypothetically before is now real and tested (S1-7: 43 offline tests + a live dry run).
Superseded text is kept and struck through rather than deleted, per this project's own convention
for handoff docs.

## What "calibrated" has to mean

`build_model.py`'s `fit_gap()` is `person_score - env_score` on the same axis, and every downstream
weight (`mag`, `dir`) is fit against that signed difference. For the gap to mean anything, a
person scoring 0.7 on autonomy and a company scoring 0.7 on autonomy must represent **the same
standing on the underlying trait** — not just the same number from two different instruments that
happen to both output `[0,1]`. That's the whole claim to check. It is not automatically true just
because both sides were designed with the same six dimension names and pole labels.

*Scope note, added: `fit_gap()` currently only has a Bernoulli path wired up (the `appeal` outcome).
`build_model.py` has no `OrderedLogistic` path for `experienced` outcomes yet (flagged 08-17b,
§5/§8, not blocking today since zero `experienced` outcomes exist to train on). Calibration is a
property of the person/company inputs, not of which outcome head consumes them — this check still
matters for the `experienced` path the day it's implemented, even though it can't be tested against
that path yet.*

## Finding 1 — the two sides quantize to different, mostly non-overlapping lattices

Company scores are 5 fixed bands: `{0.1, 0.3, 0.5, 0.7, 0.9}` (deliberate design, 08-10 handoff;
confirmed unchanged in `anchors.json`, still `rubric_version: v1-frozen-2026-08-15`).

Person scores are `mean(pole_value)` over 4 forced-choice items, each contributing exactly 0 or 1.
The only achievable values are:

```
{0.0, 0.25, 0.5, 0.75, 1.0}
```

(verified by enumeration against the live `assessment_items.yaml`, not assumption).

**These two five-value sets overlap at exactly one point: 0.5.** A person can never score 0.3 or
0.7 or 0.1 or 0.9 — the values a company routinely lands on. The closest a person can get to a
company's 0.7 is 0.75 (gap 0.05) or 0.5 (gap 0.2); there is no way to land a true zero gap against
a company scored anywhere except 0.5. This wasn't a deliberate joint design choice — the person
lattice falls out of "4 items, binary each" as a mathematical necessity, and the company lattice
was chosen independently in the 08-10 session for an unrelated reason (band width above the LLM's
measured noise floor). **Nobody designed these to interoperate; they coincidentally both produce
five values.**

*A second-order consequence, added: the company side is reported as a mean-of-5 (locked aggregator
decision, S1-3), and the mean of five samples drawn from a 0.2-spaced band set lands on a grid with
0.04 spacing, not the raw 5-value band set itself. So a single company vignette result is not
actually confined to `{0.1,...,0.9}` — it can land anywhere on a much finer 0.04-spaced grid
depending on the run-to-run split. This makes the two sides' effective resolution closer than
Finding 1's headline suggests, but it doesn't change the finding: the person side's grid (0.25
spacing) is still coarser than the company side's post-averaging grid (0.04 spacing), so the
mismatch this finding describes is if anything understated by comparing raw bands only.*

This alone doesn't invalidate the gap — a quantization offset just adds noise, and 0.05–0.2 is
comparable to the LLM's own measured scorer SD ~~(~0.03–0.11 depending on dimension, per the
2026-08-17 variance re-test)~~. But it means **a "perfect" person-company match can never show
gap=0** except at the single shared value 0.5, which is worth knowing before anyone reads a small
nonzero gap as evidence of mismatch.

*Correction, added: the "~0.03–0.11" figure above was the pooled mean-score-SD from the 08-17
(non-b) partial run — 0.0332 and 0.0365, averaged across all 6 dimensions per packet. That figure
mixes in the dimensions that showed exactly zero variance with the ones that didn't, which is
precisely the mistake S1-3 (08-17b, same day) caught and fixed when computing the mean-vs-median
aggregator comparison: averaging in zero-variance cells mechanically deflates whatever it's
compared against. The corrected, per-dimension figures — the ones this doc's tolerance derivation
should actually use — are below Finding 3.*

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

**Cross-reference, added: `ASSESSMENT_ITEMS_BIAS_REVIEW.md` now exists (08-17b) and independently
flags feedback and decision as the two highest-risk dimensions — but for a different mechanism than
this finding.** This finding is about *intensity mismatch* (does the wording, taken at face value,
reach the same extreme the anchor band describes). The bias review is about *desirability skew*
(does one pole read as the more professionally-correct answer regardless of a real respondent's
true disposition — decision's four items all frame "data-driven" as more rigorous; feedback and
decision are the only two dimensions with zero reverse-keyed items, so straight-lining is invisible
on exactly those two). **These are separable failure modes that can produce the same symptom** — a
person-side score running systematically higher than the matched company score on decision could
be caused by either one, and the fix differs (rewrite item intensity vs. rewrite item framing to be
desirability-neutral). The paired-vignette probe below is only positioned to catch the first kind:
vignettes are hand-scored by the vignette's own author simulating a fixed intended trait level, not
answered by a real self-interested respondent, so desirability skew (a property of real people
picking the flattering answer) has no mechanism to operate in this probe. **A clean pass on the
vignette probe for decision or feedback does not clear the bias-review finding — that still needs
the pilot the bias review itself calls for (its step 4), on real respondents.** See "Recommended
order" below for how this changes sequencing on these two dimensions specifically.

## Finding 3 (new) — the scorer answers all six dimensions every time, not just the one you're probing

Not knowable before `scorer_pipeline.py` existed to read. `score_packet()`'s response schema
requires a score, confidence, and evidence_quotes for **all six dimensions on every call** — there
is no way to ask it to score only autonomy and leave the rest unanswered; the schema is
`additionalProperties: False` with all six dimension keys `required`.

This has two consequences for vignette design that the original method section didn't account for
because the schema didn't exist yet to expose them:

1. **A vignette written to target one dimension will still get non-null scores on the other five**,
   even when the vignette text says nothing about them. `anchors.json`'s own confidence bands
   describe exactly this case — "Almost nothing in the packet bears on this dimension. You are
   close to guessing" (0.1, Very low) — so the honest failure mode is a low-confidence near-guess
   on the untargeted five, not an error. **The returned confidence value on the untargeted
   dimensions is itself a free diagnostic**: if a vignette written purely to target autonomy comes
   back High-confidence on collaboration too, that's evidence the vignette leaked signal across a
   dimension pair `anchors.json` explicitly warns is easy to conflate (autonomy/collaboration,
   pace/innovation are both called out by name in the `keep_distinct` field) — a sign to rewrite the
   vignette narrower, not a result to keep.
2. **Each vignette call is free data on the other five dimensions, not just the targeted one.**
   18 vignettes × n=5 runs × 6 dimensions is 540 (score, confidence) pairs from 90 API calls, not
   18. The 15 off-target readings per vignette (5 runs × 3 non-focal... actually 5 runs × 5
   off-target dimensions) are lower-value than the on-target ones but cost nothing extra to collect
   and are a real check on cross-dimension bleed across the whole set — worth logging, not
   discarding, consistent with this project's "every pipeline stage returns proof of what it
   attempted" convention (S1-6 DDL comment).

**Tolerance derivation, corrected.** The original spec's "~0.15–0.2" tolerance cited a pooled
mean-score-SD that Finding 1's correction above shows was measuring the wrong thing. The corrected,
per-dimension nonzero-variance figures now exist (S1-3, 08-17b, isolated on gpt-5.5 specifically):
of 36 dimension×packet cells, 27 showed exactly zero variance and 9 showed nonzero variance
clustering at **0.080 or 0.098**, depending on which discrete band-split produced it (a 4-1 vs. 3-2
split of adjacent bands at n=5, not a smooth continuum — this is itself a property of scoring on a
fixed 5-band scale, not sampling noise in the usual sense). No dimension has yet shown a measured SD
above 0.098; the original "~0.11" ceiling doesn't correspond to anything actually observed once the
pooled figure is thrown out.

Per-dimension, across all 6 packets: feedback was the noisiest (nonzero on 3 of 6: 0.098, 0.098,
0.080), autonomy nonzero on 2 of 6 (0.080, 0.080), pace/collaboration/innovation/decision nonzero
on 1 of 6 each (pace 0.098, collaboration 0.098, innovation 0.080, decision 0.098). ~~feedback and
innovation should use a tolerance around 2×0.098 ≈ 0.20 ... autonomy, pace, collaboration, and
decision ... should use a tighter tolerance ... 2×0.080 ≈ 0.16~~ — **corrected: this grouped the
wrong dimensions together.** Going by each dimension's own *worst observed value*, not frequency:
autonomy and innovation top out at 0.080 (tolerance ≈ 2×0.080 ≈ 0.16); pace, collaboration,
feedback, and decision top out at 0.098 (tolerance ≈ 2×0.098 ≈ 0.20). **Use each dimension's own
worst observed nonzero SD as its tolerance width, not one blanket number, and not the grouping this
doc first proposed**: autonomy and innovation get the tighter ~0.16 ceiling (with ~0.08–0.10 as a
working default, since both showed zero variance on 4–5 of 6 real packets and a looser tolerance
would let a real miscalibration hide inside it); pace, collaboration, feedback, and decision get
the looser ~0.20 ceiling. **Feedback in particular now has three independent reasons to expect a
noisy, hard-to-interpret read on this probe**: it's the noisiest dimension in the variance data
(nonzero on half the packets tested, not just one), it's one of the two dimensions with zero
reverse-keyed items in the bias review, and it's the dimension flagged across two prior sessions
(08-15b, 08-17) as the standing candidate for an anchor rewrite. A null or a failure on feedback
specifically should not be over-read as calibration-specific until the other two explanations are
ruled out.

## The check to actually run — paired vignette probe

This is buildable now, doesn't need real users or more companies, and directly tests
cross-instrument agreement using content where the "true" answer is fixed by construction (the
same trick the ground-truth packet exercise uses to validate the company scorer alone — this
extends it to validate agreement *between* the two scorers).

**Method:** for each of the 6 active dimensions, write 3 short paired vignettes per dimension (low,
mid, high on the pole) — 18 total pairs, 36 short texts:

1. A **person vignette**: a short first-person scenario description, written to deliberately imply
   a specific point on the dimension (e.g., "extremely self-directed" for the 0.9 target).
2. A **company vignette**: a short company-culture description, written by the same author in the
   same sitting, deliberately targeting the *same* point on the same dimension.

**Guardrail, added: do not reuse the anchor or item wording verbatim.** If a company vignette
echoes an anchor's own key phrases ("high-trust, flat decision rights"), agreement between the
scorer and the anchor is guaranteed by construction and the probe tests nothing. Paraphrase the
intended intensity in the vignette's own words.

**Guardrail, added: write each vignette to say as little as possible about the other five
dimensions.** Per Finding 3, the scorer will still produce a value for all six regardless — the
goal is to keep the off-target five near the "almost nothing bears on this" confidence floor, not
to accidentally write a vignette that also reads as high-pace or low-collaboration.

**Guardrail, added: freeze the 18 target levels and their expected direction in a committed file
before scoring anything.** Nothing currently in this doc does that. Without it, an ambiguous
vignette's "intended" level is too easy to reinterpret after seeing how the model scored it.

Score the person vignette by hand-answering the 4 real `assessment_items.yaml` items for that
dimension as the vignette character would answer them, and run it through the real scoring
function. Score the company vignette by calling **`scorer_pipeline.py`'s `score_packet(client,
packet_text, rubric_text, packet_id=..., rubric_version=..., packet_version=..., model="gpt-5.5-
2026-04-23", reasoning_effort="medium")`** — the vignette text passed directly as `packet_text`;
no packet markers or section structure needed, since `score_packet()` doesn't parse either, it just
inserts the text into the prompt. ~~Score the company vignette by running it through the real
frozen rubric / LLM scorer (the same call `scorer_variance_test_v2.py` already makes)~~ —
superseded: `scorer_variance_test_v2.py`'s `run_once()` tangles scoring with its own CSV/raw-JSON
output shape and isn't meant to be reused (S1-2's own stated reason for building `score_packet()`
in the first place). Use n=5 per vignette per the locked mean-of-5 aggregator decision (S1-3),
consistent with how the real packets are scored.

**On citation verification, decided: do not run the full `parse_excerpts()` / `classify_source()`
machinery against vignette text.** That machinery expects the real packet's structural format —
section markers, bulleted excerpts, `— [source]` attribution lines — to classify a quote as
company/noncompany/disputed/researcher. Forcing a natural short vignette into that structure to
satisfy the parser would make the vignette artificial and defeats the purpose of testing plain
intensity-matching. **Do, however, reuse `verify_quote()`'s normalization + substring match
directly against the raw vignette text** (skip `parse_excerpts`/`classify_source` entirely, just
normalize-and-substring-match each returned `evidence_quote` against the vignette) as a free,
cheap sanity check that the model's score is actually grounded in what the vignette says rather
than confabulated — this uses infrastructure S1-5 already built and costs nothing extra since
`evidence_quotes` come back on every call regardless. This is *not* the same thing as the ≤0.7
non-company-support gate (S1-6) — that gate is a source-diversity measurement specific to real
evidence packets with multiple source types, and a single-paragraph vignette has no source-type
diversity to measure by design. Don't apply that gate here; it isn't the right tool for this input.

**What would pass:** for a pair both targeting "high," the person score and the mean company
score should be within the target dimension's own tolerance (see Finding 3's corrected derivation
above — roughly 0.08–0.10 for autonomy/innovation, roughly 0.20 for pace/collaboration/feedback/
decision) of each other — not exact agreement, given Finding 1's lattice mismatch, but no
*systematic* directional gap. ~~across all 18 pairs~~ — **corrected: evaluate this per dimension
(3 pairs), not pooled across all 18.** Pooling would repeat the exact averaging mistake S1-3 caught
the same session this doc was written — a real offset on one dimension can be diluted by five clean
ones if judged as one aggregate number.

**What would fail, and what it would mean:** if person scores systematically run higher (or lower)
than company scores across a dimension's 3 pairs at the same intended level, that's a real
calibration offset for that dimension — evidence the two instruments' "0.7" don't mean the same
thing there, most likely traceable to Finding 2 (item wording not matching anchor-text intensity).
**Before concluding that, rule out the cheaper explanations first**: (a) check whether the same
pair's off-target readings (Finding 3) show cross-dimension leakage, which would mean the vignette
itself was the problem, not the instruments; (b) if the failing dimension is decision or feedback,
check the direction of the offset against the bias review's predicted direction (decision:
predicted to skew person-scores *toward the data/high pole*; feedback: predicted to be
under-determined by straight-lining, not directionally biased) — a match to that predicted
direction points at desirability skew or missing reverse-keying (bias review's problem, different
fix) rather than intensity mismatch (this doc's problem). The fix, once isolated, is rewriting the
affected items' wording — either for intensity (this doc) or for desirability-neutrality (bias
review) — not adjusting the model.

**Cost:** cheap. Writing 36 short vignettes is an afternoon; scoring the company side is 18 × 5 =
90 LLM calls (a few dollars); scoring the person side is answering 18 × 4 = 72 forced-choice items
by hand, which can be done by whoever writes the vignettes since the "true" answer is baked in by
design.

## A weaker, later check: distributional sanity once real data exists

Once real people have taken the assessment (n≳30) and enough companies are scored, compare the
two marginal distributions per dimension. This has limited power on its own — there's no reason
real people and real companies should be distributed identically — but it's a useful red-flag
check: if one side's distribution is collapsed into 1–2 bands while the other spreads across all
five (a real risk on the company side, per the 08-17b variance finding that several dimensions
landed at the same band on every single run of a given packet), that predicts systematically
inflated or deflated gaps for reasons that have nothing to do with actual person-company mismatch.
Cheap to check once the data exists; not actionable before then.

## The eventual real test — not actionable yet

The gold-standard check is behavioral: does the *sign* and *magnitude* of a dimension's gap
predict the *direction* of dissatisfaction in `outcome_experienced` data (e.g., large positive
autonomy gaps — person wants more than the company gives — showing up disproportionately in low
`working_scale` ratings, specifically with autonomy-flavored complaints). This is exactly what the
`dir` weight in the model is meant to eventually capture, but it requires real placement outcomes,
which don't exist yet and won't for a while, and — per the scope note under "What calibrated has to
mean" above — the `experienced`-outcome model path this would eventually run against isn't
implemented yet either (`build_model.py` has no `OrderedLogistic` head, 08-17b §5/§8). Naming it as
the real target, not proposing it as next-step work.

## Recommended order

1. **Run the paired-vignette probe now, but only for autonomy, pace, collaboration, and
   innovation.** These are the four dimensions the bias review calls structurally sound (no
   desirability-skew or reverse-keying gap found), so a calibration result on them is
   interpretable immediately without a confound from item-wording problems the project already
   knows about independently.
2. **Hold decision and feedback until their bias-review fixes are drafted and signed off**
   (`ASSESSMENT_ITEMS_BIAS_REVIEW.md`'s own recommended order: decision rewrite first, then the two
   missing reverse-keyed items) — then run the vignette probe on those two against the *revised*
   item wording. Running it now against known-flawed items risks a result that has to be thrown out
   and redone once the items change anyway, and risks misattributing a desirability-skew failure to
   an intensity-mismatch one (see Finding 2's cross-reference above).
3. Evaluate pass/fail per dimension, using that dimension's own tolerance (Finding 3), not one
   pooled number across all 18 pairs.
4. If a dimension fails, rule out vignette cross-dimension leakage (Finding 3) and — for decision/
   feedback specifically — desirability skew (Finding 2's cross-reference) before concluding it's an
   intensity-mismatch problem calling for an item rewrite.
5. Revisit the distributional check once real assessment + company data exist at meaningful volume.
6. Keep the eventual outcome-based check in view as the actual validation, once outcomes exist and
   the `experienced`-outcome model path is built.

Nothing here has been run — this is the check specified, not executed. Running it needs: (a) the
18 vignette pairs written and frozen before scoring, (b) LLM API access for the company side
(blocked in the cloud sandbox by the network allowlist, same as the other pending tasks — run
locally per this project's established workflow), (c) someone to hand-score the person side against
the real item bank, (d) — new — sign-off on the decision/feedback item rewrites from the bias
review before those two dimensions' vignettes are scored, per the sequencing above.
