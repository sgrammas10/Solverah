# Solverah — Session Handoff, 2026-08-17c

**Topic: picked up the person↔company scale calibration check (open item 5 from `-17b`), rebuilt
its spec against the code that had moved under it, then actually ran it — two live rounds, 480
scored rows. Result: the company-side scorer is clean and precise across all five bands; the
person-side assessment instrument is structurally incapable of distinguishing "leaning" from
"extreme," confirmed empirically on four dimensions. That is a bigger finding than the check was
scoped to catch, and it moves the fix from "reword some items" to "redesign the person
instrument."** Custom instruction to honor: be logical and future-thinking, do not be agreeable —
push back.

Sits on top of `SOLVERAH_HANDOFF_2026-08-17b.md` (sprint closed, six standing items cleared) and
`causal_graph/v1_model/SCALE_CALIBRATION_CHECK.md`, which was amended in place this session rather
than rewritten — superseded text struck through, corrections dated, same convention the handoffs
use.

Same working split as every prior live-API session: all scripts written and verified offline in the
sandbox (which cannot reach `api.openai.com`), run locally by Sebastian, results pasted back. **Every
number below was recomputed from the returned CSVs in this session, not read off the terminal
summary** — which matters, because the terminal summary was misleading twice and both times the raw
rows were what caught it.

---

## 0. Why this ran, and what got picked instead

The raters have **not** returned their P-01–P-06 files yet, so `-17b`'s open item 1 (feedback anchor
check against the human Agreement tab) is blocked — not deprioritized, blocked. Of the remaining
unblocked items, the person↔company scale lattice mismatch was chosen over the Test 1
citation-verification re-check on the argument that it threatens the validity of the core model
output (the signed gap the whole model is built on) rather than adding assurance to a result that
already came back null.

---

## 1. The spec was stale before it could be run — four corrections

`SCALE_CALIBRATION_CHECK.md` was written against a snapshot that had since moved. Sanity-checking it
before spending API calls (Sebastian's call, and the right one) surfaced four real problems:

**1a. It pointed at the wrong interface.** The method said to score company vignettes "the same call
`scorer_variance_test_v2.py` already makes." But S1-2 built `score_packet()` in `scorer_pipeline.py`
*specifically because* `run_once()` tangles scoring with its own CSV/raw-JSON output shape and can't
be reused. Corrected to call `score_packet()` directly. Also established by reading the code, not
assuming: vignette text can be passed straight in as `packet_text` — `score_packet()` doesn't parse
packet structure, it just inserts the text into the prompt, so no fake section markers are needed.

**1b. Its tolerance number was derived from a figure this project had already proven misleading.**
The spec proposed "~0.15–0.2, using the larger of the two sides' measured SDs," citing ~0.03–0.11.
That range was the **pooled** mean-score-SD from the `-17` partial run (0.0332, 0.0365) — averaged
across all six dimensions including the ones at exactly zero variance. That is precisely the error
S1-3 caught and fixed the same day when computing mean-vs-median. Replaced with per-dimension
tolerances derived from the corrected S1-3 data (worst observed nonzero SD per dimension).

**1c. `ASSESSMENT_ITEMS_BIAS_REVIEW.md` didn't exist when the spec was written, and it flags the
same two dimensions for a different reason.** The calibration doc's Finding 2 is about *intensity
mismatch*; the bias review is about *desirability skew* and *missing reverse-keying*. Both can
produce the same symptom on feedback and decision, and the fixes differ. Added an explicit rule for
telling them apart, and — the substantive change — **resequenced the work**: run the probe now on
the four dimensions the bias review calls structurally sound (autonomy, pace, collaboration,
innovation), hold decision and feedback until their item rewrites are signed off. Running them now
against known-flawed items would produce a result that has to be thrown out when the items change,
and risks misattributing a skew failure to an intensity failure.

**1d. New Finding 3: the scorer answers all six dimensions on every call.** Not knowable before
`scorer_pipeline.py` existed to read — `RESPONSE_SCHEMA` is `additionalProperties: False` with all
six keys `required`. Two consequences the original method couldn't have accounted for: vignettes
must be written to say as little as possible about the other five dimensions, and **the off-target
readings are free diagnostic data** on cross-dimension bleed, not noise to discard. This turned out
to matter (see §5).

Also decided, and worth recording because the opposite is the tempting default: **do not run
`parse_excerpts()` / `classify_source()` against vignette text.** That machinery expects real packet
structure (section markers, bulleted excerpts, `— [source]` attribution) to classify provenance;
forcing a short natural vignette into that shape to satisfy the parser would make the instrument
artificial and defeat the point. **Do** reuse `verify_quote()`'s normalization + substring match
directly against the raw vignette as a free grounding check. The ≤0.7 non-company-support gate is
explicitly *not* applied — a single-paragraph vignette has no source-type diversity to measure by
design, so that gate is the wrong tool for this input.

---

## 2. Two errors of mine, both caught before they corrupted a conclusion

Recorded because the pattern matters more than either fix.

**2a. Wrong tolerance grouping.** Having correctly thrown out the pooled figure, I then grouped the
dimensions by *how often* they showed nonzero variance instead of by *how large* their worst
observed SD was. That put pace and collaboration in the tight-tolerance group. Going by worst
observed value — the thing a tolerance should actually be sized against — autonomy and innovation
top out at 0.080, while pace, collaboration, feedback and decision top out at 0.098. Fixed in both
the spec and the script before round 1 ran.

**2b. The verdict compared against an unreachable target.** The first version of
`run_vignette_probe.py` compared `company_mean` against the raw `target_person` value. That is wrong
at the extremes: the company rubric has no band below 0.1 or above 0.9, so a person target of 0.0 or
1.0 can never be matched no matter how well calibrated the instruments are. Worse, my own tolerance
for autonomy/innovation (0.09) was *tighter than the guaranteed 0.1 structural gap*, so those two
dimensions could not register a clean PASS at the extremes under any circumstances. Fixed with
`closest_company_band()`: the verdict now runs on the **residual** (company mean vs. nearest
*achievable* band), with the raw delta retained for transparency. Re-scored round 1's existing CSV
under the corrected logic — no new API calls — and all 12 pairs come back PASS at residual exactly
0.0.

**The generalizable lesson: a verdict function that can't return PASS for a correct input is a
broken instrument, and it will read as a real finding.** Both errors were mine, both were caught by
recomputing from raw rows rather than trusting a summary line, and the first one would have quietly
labeled two well-calibrated dimensions "BORDERLINE" in a document someone later cites.

---

## 3. Round 1 — extremes and midpoint (12 pairs, 4 dimensions × 3 levels, n=5)

Files: `vignette_probe_pairs_v1.yaml` (frozen before scoring), `score_person_side.py`,
`run_vignette_probe.py`, results in `vignette_probe_results.csv` (360 rows).

Person-side scores were verified mechanically against the real `assessment_items.yaml` **before**
any API call — `score_person_side.py` recomputes each vignette's score from its frozen item choices
and refuses to bless a mismatch. All 12 reproduced exactly.

**Results, recomputed from the CSV:**

| | result |
|---|---|
| Per-run variance | **Zero on all 12 vignettes** — every run of every vignette returned an identical score |
| Quote grounding | **176/176** on-target evidence quotes verified against the vignette text |
| `temperature_honored` | `True` on all 360 rows |
| Residual after the §2b fix | **0.0 on all 12 pairs** |

Every "low" vignette scored exactly 0.1, every "high" exactly 0.9, every "mid" exactly 0.5.

**What this establishes:** at the extremes and at the single shared lattice point, these four
dimensions show no measurable miscalibration beyond what Finding 1 already predicts and prices in.
The 0.1 raw gap at the extremes is the company rubric's floor/ceiling, not a defect — no item
rewrite closes it.

**What it does not establish, and this is the important part:** round 1 could not test the concern
that motivated the whole document. Finding 2's worked example is about `au1`'s "checking in only
when needed" reading like the company's **0.7** band while still earning full credit toward a 1.0
person score. Testing at 0.1/0.5/0.9 never puts that question. Flagged at the time rather than
after, and round 2 was built to answer it.

---

## 4. Round 2 — the 0.7 boundary probe (4 pairs, n=5). Finding 2 confirmed.

File: `vignette_probe_pairs_v2_boundary.yaml`, results in `vignette_probe_results_v2.csv` (120 rows).

One pair per dimension. Company vignettes written to match **only** the 0.7 "leaning" anchor,
deliberately withholding each anchor's 0.9-band intensifying language. Person vignettes written by
paraphrasing each item's high-pole option *as literally as possible*, without round 1's deliberate
extra intensity. Both possible outcomes were pre-registered in the file before scoring, including
the outcome that would have falsified Finding 2.

**Result: all four dimensions scored exactly 0.7, zero variance, 60/60 quotes grounded. Residual
−0.2 on every dimension. FAIL on all four, exactly as predicted.**

Two conclusions, and they need to be kept separate:

**The company scorer comes out of this looking good.** It discriminated 0.7-level evidence from
0.9-level evidence perfectly and noiselessly — round 1's rich "high" vignettes scored 0.9, round 2's
deliberately moderate ones scored 0.7, with zero run-to-run wobble either way. The pre-registered
alternative — that the company side would also drift up to 0.9 out of sloppiness, meaning *neither*
instrument could resolve the boundary — did not happen. Worth stating plainly because it is the
opposite of what the anonymization and variance work has conditioned this project to expect from LLM
scoring.

**The person instrument is where the miscalibration lives, and it is structural, not lexical.** All
four items in a dimension are pitched at roughly the same intensity, so a genuinely moderate
respondent endorses all four and is forced to 1.0. Mean-of-binary-forced-choice has no way to
express "how strongly" — only "which side." **This applies to all six dimensions by construction,
not just the four tested**; decision and feedback inherit it *on top of* their already-flagged bias
review problems. Rewording `au1` does not fix it. This is the finding that moves the work out of the
scope `SCALE_CALIBRATION_CHECK.md` was written under.

---

## 5. A separate, independently confirmed finding: collaboration→autonomy bleed

The collaboration vignette read as legitimate autonomy evidence — 0.5, Medium confidence, fully
grounded — on **5/5 runs in round 1 and 5/5 runs in round 2**, with two differently-worded vignettes.
Ten for ten across two independent texts is not incidental phrasing; it is a reproducible property of
how "individual ownership" language is read, and it lands exactly where `anchors.json`'s own
`keep_distinct` field warns these two dimensions are easy to conflate.

This came entirely from Finding 3's off-target logging — data that would have been discarded under
the original spec. Two other flags (autonomy→innovation, innovation→pace) fired on 1/5 runs each and
should **not** be treated as the same class of finding.

---

## 6. The redesign decision, and the proof-of-concept built against it

Four options were laid out with their real trade-offs: (A) graded/Likert response items, (B)
graduated-difficulty forced-choice items, (C) rank/percentile-based `fit_gap()`, (D) ship coarse and
make the model robust to it. **Sebastian chose B**, with the correct reasoning stated in his own
terms — some questions should sit at 0.3 or 0.7 rather than every question being a hard lean either
way.

B keeps the forced-choice format `assessment_items.yaml`'s header defends on purpose, avoids
reopening central-tendency and scale-usage confounds that A would introduce, and is the only option
that addresses the actual mechanism round 2 identified. C was rejected as not fixing anything (if
most respondents pile onto 1.0, ranking them doesn't separate them) and unusable before real
population data exists; D was rejected as capitulation.

**Timing argument that decided "now" over "later":** `assessment_items.yaml` is still `v1-draft` and
has never been run on a real person. That is the cheapest possible moment for a structural redesign —
no collected data to reconcile or re-gather — and it should be bundled with the bias review's pending
decision/feedback rewrites rather than touching the same file across three separate
edit-and-re-pilot cycles.

**Built this session:** `autonomy_items_v2_POC.yaml` — a Guttman-style ladder, one item calibrated
per company band (`au1v2` @0.3 routine/low-stakes → `au2v2` @0.5 new-but-low-risk → `au3v2` @0.7,
kept close to the original `au1` since that is the item Finding 2 anchored on → `au4v2` @0.9,
reverse-keyed, high-stakes). The grading variable is **stakes/scope**, not an explicit intensity
label — a labeled intensity scale would be option A wearing option B's clothes.

Plus `vignette_probe_pairs_v3_autonomy_ladder.yaml`, which validates the ladder across all five
bands. Four of five company vignettes are **reused verbatim from rounds 1 and 2** — company scoring
does not depend on which person items exist, and those inputs are already measured at zero variance,
so only the new 0.3-band vignette requires fresh calls. Person side verified offline: the ladder
produces exactly 0.0 / 0.25 / 0.5 / 0.75 / 1.0. **Not yet run.**

Predicted if the design holds: every gap ≤0.1 — the same irreducible floor/ceiling minimum round 1
found — instead of round 2's 0.2 at the 0.7 level.

---

## Open / next

1. **Round 3 has not been run.** `python run_vignette_probe.py --pairs
   vignette_probe_pairs_v3_autonomy_ladder.yaml --out vignette_probe_results_v3.csv` — 25 calls.
   Two things it tests that have never been tested: whether the company scorer resolves the **0.3**
   band (rounds 1–2 covered 0.1/0.5/0.7/0.9 only), and whether the ladder is internally coherent.
2. **What round 3 cannot establish, and must not be reported as establishing: that real people
   answer this way.** Every person-side score in all three rounds was hand-picked by whoever wrote
   the vignette to match the intended level. A clean round 3 licenses "the design is coherent and
   ready to pilot," nothing stronger. The difficulty ordering is a claim about real respondents and
   only a real pilot tests it — the same limitation `assessment_items.yaml`'s own header already
   states about the original items.
3. **If round 3 holds, extend the ladder to the other five dimensions** — and bundle it with the
   bias review's decision/feedback rewrites, per §6's timing argument. Decision needs both fixes at
   once (whole-dimension desirability skew *and* graduated intensity); feedback needs both plus the
   missing reverse-keyed item.
4. **Then re-run the calibration probe on decision and feedback**, which have been held from every
   round so far and remain untested.
5. **Collaboration/autonomy bleed (§5) is unresolved.** Confirmed 10/10 across two texts. Decide
   whether it is a vignette-writing artifact or an anchor problem — if the latter, it belongs in
   Julie's post-round-1 anchor rewrite alongside feedback.
6. **`fit_gap()` may need revisiting regardless.** Even a perfect ladder leaves the person side on a
   0.25-spaced lattice against a company side that averages onto a 0.04-spaced one. Round 1 measured
   that cost at ≤0.1; that is now a known, quantified quantity rather than an unknown — but it has
   never been decided whether raw subtraction is the right operation over two lattices that coarse.
7. Carried, untouched, from `-17b`: feedback anchor check vs. the raters' Agreement tab (**blocked**
   on raters); Test 1 identified-condition re-check with citation verification; `build_model.py` has
   no `OrderedLogistic` path for `experienced` outcomes; `schema.sql` never migrated into the app
   database; George/RATER_B notification; `Solverah_Ground_Truth_Roster_v2.md` still missing.
8. **Standing, from `-17b`, unchanged by this session: anonymization does not prevent
   re-identification for 5 of 6 companies.** Restated here only because it is the single finding most
   likely to be forgotten and most damaging if a downstream claim quietly assumes otherwise.

---

## Framings that survived pushback this session

* **A clean PASS on a well-designed probe can still be an artifact of a broken verdict function.**
  Round 1's two BORDERLINE calls were caused entirely by my own tolerance being tighter than a
  structurally guaranteed gap. Recomputing from raw rows caught it; the summary table would not have.
* **"The instruments disagree by 0.2" is not one finding — it is a finding about which side is
  wrong.** Round 2's company side was exactly right and its person side was exactly wrong. A pooled
  "calibration gap" number would have obscured which, and the fix differs completely by answer.
* **Empirical confirmation of a predicted failure is a success of the instrument, not a failure of
  the work.** Round 2 was pre-registered with both outcomes written down before scoring, including
  the one that would have falsified Finding 2. FAIL on all four was the informative result.
* **Zero variance across runs is evidence about the scorer's determinism, not about its
  correctness.** Round 1 and round 2 both returned zero variance. In round 1 that accompanied correct
  scores; in round 2 it accompanied scores that correctly refused to match a broken person
  instrument. The variance number alone distinguishes neither.
* **Off-target data you were about to discard can be the session's second-best finding.** The
  collaboration→autonomy bleed exists in the record only because Finding 3 forced the question of
  what to do with the five dimensions nobody asked about.
* **The cheapest moment to make a structural change to an instrument is before it has ever collected
  data.** `assessment_items.yaml` is still `v1-draft`; that fact, not the size of the redesign,
  should drive the timing.
