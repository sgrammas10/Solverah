# Solverah — Pre-registration: person-side analyses S-17 and S-18

**Written 2026-08-19, before any respondent data exists.** Production's
`assessment_response` and `person_dimension_score` tables are empty; the only sitting ever
recorded was the 08-19 smoke test, deleted the same day. Every number below comes from
simulation, not from respondents.

**Status: PROPOSED. Not adopted until Sebastian signs off** — one decision in Part 1 changes a
test STATE had already named, and it is flagged there rather than made quietly.

**Amendment convention.** Once adopted, this document is append-only. An amendment is a dated
section at the end saying what changed and why; the original text is never edited. A
pre-registration that can be silently revised is a record of what happened, not a prediction.

**Why this exists.** The prediction it tests was registered in `assessment_items_v2.yaml`
design rule 6 on 2026-08-18. What was never fixed is the part that decides the answer: the
statistic, the threshold, the correction for multiplicity, and the stopping rule. A prediction
whose decision rule is chosen after seeing the numbers is not a prediction (STATE, S-18).

---

## Part 0 — Machinery shared by both analyses

### 0.1 Analysis population

- Sittings stored under the **current** `scoring_key_version` only (D-14, D-18). A sitting of a
  superseded instrument is not comparable and is excluded by construction, not by judgement.
- **One sitting per respondent: the FIRST completed one under that key.** Retakes are excluded
  from the analysis population. A retaker has seen the instrument once, and letting the analyst
  choose which sitting to use is a degree of freedom worth closing now, while it costs nothing.
  Retake sittings are retained in the raw rows (D-16) and may be used for exploratory retake-
  stability work, labelled as such.
- **No exclusions on confidence.** Binding, from D-17(b): the analysis runs on raw
  `assessment_response` patterns and is never confidence-filtered or confidence-weighted.
  Filtering low-e rows would delete exactly the secondary-cell evidence S-18 is looking for.
- **No exclusions on completion speed.** Per-item `answered_at` makes duration derivable, and
  speeding is a real data-quality worry, but a speed cutoff chosen after seeing the data is a
  researcher degree of freedom. Duration is recorded as an exploratory covariate only.

### 0.2 Uncertainty — how every interval here is produced

Per **D-21(a)**, real-data statistics have no seed; the draw is a bootstrap resample.

- **Resample RESPONDENTS, not rows.** Each respondent contributes six dimension patterns, so
  the person is the cluster. Resampling rows would treat one respondent's six dimensions as six
  independent observations and understate every interval — the same mistake, in a different
  costume, as the pooled-CI error corrected in STATE §5 on 08-19b.
- **≥ 2000 resamples**, percentile intervals at 95%.
- Every reported contrast is emitted through `seed_discipline.Finding.paired_contrast` with
  `draw_kind="bootstrap"`: the two arms are computed on the *same* resample, so pairing is
  structural (D-21(b)). A contrast that does not clear D-21 prints its label and no number.

### 0.3 Stopping rule — the analysis runs ONCE

**Both analyses run once, at the first calendar checkpoint at which the analysis population
reaches its stated N threshold.** Not on every new respondent, not "let's peek and see."
Repeated looks with a fixed interval rule inflate the false-positive rate, and this project has
no monitoring reason to look early.

Any run before the threshold is a **pilot: labelled, with no number quoted** (D-21). That is not
a formality — Part 1's power table shows exactly how uninformative an early null would be.

### 0.4 What is pre-registered and what is not

Pre-registered: the analysis population, the primary statistic of each part, its decision rule,
its N threshold, and the consequence of each outcome. **Everything else anyone computes on this
data is exploratory and must be labelled exploratory in any document it enters.** This document
does not constrain exploration; it constrains what may be called a result.

---

## Part 1 — S-18: is feedback a two-factor dimension?

### 1.1 The prediction, unchanged

Registered 2026-08-18 in `assessment_items_v2.yaml` rule 6, with the terminology addendum of
08-19. Feedback is the only dimension whose ladder changes grading variable mid-climb:
`fb1v2`/`fb2v2` grade **delay**, `fb3v2` grades **audience**, `fb4v2` grades both. So *"tell me
immediately, but not in front of the team"* is coherent and common, endorses rungs 1–2, and
declines rung 3. `fb4v2` then forces that respondent to pick which aversion wins, splitting them
between `{1,1,0,0}` (score 0.50) and `{1,1,0,1}` (score 0.75).

### 1.2 A correction to the test STATE named — Sebastian's call

STATE names the primary test as **conditional composition**: among respondents scoring 0.5 on a
dimension, the fraction who arrived via `{1,1,0,0}`, feedback versus the others. Simulating it
before writing a threshold around it turned up a problem.

**Under the null that statistic already sits at 0.76.** `{1,1,0,0}` is the e=0 pattern, so it
dominates the 0.5 stratum in every dimension whether or not the hypothesis is true. Adding
rule-6 respondents raises a share that is already near its ceiling, and the effect is
compressed:

| rule-6 prevalence φ | Δ composition | Δ climb |
|---|---|---|
| 0.05 | +0.032 | +0.037 |
| 0.10 | +0.059 | +0.076 |
| 0.15 | +0.079 | +0.111 |
| 0.20 | +0.101 | +0.141 |
| 0.30 | +0.131 | +0.198 |

**The proposed primary instead measures the climb across the variable change.** For each
dimension, among respondents who endorsed rungs 1 and 2, what fraction go on to endorse rung 3?

    q_d  =  P(rung3 = 1 | rung1 = 1, rung2 = 1)
    Δ_climb  =  q_pooled_others  −  q_feedback        (positive = feedback climbs LESS)

In every other dimension, rungs 2→3 is the same grading variable getting harder. In feedback
alone it crosses delay → audience, so the audience-averse stop there *however far up the delay
ladder they climbed*. That is the hypothesis stated as an observable, and it is not
ceiling-pinned: q under the null is 0.46, mid-range. It also uses a larger base — ~57% of
respondent-dimensions endorse rungs 1 and 2, against ~35% landing in the 0.5 stratum.

**Both statistics are well calibrated.** Simulated false-positive rate at φ=0 (nominal 0.05):
composition 0.03–0.05, climb 0.01–0.03. The climb statistic is mildly conservative.

**Power (150 simulated trials per cell, so each figure carries roughly ±0.04):**

| N | φ=0.15 composition | φ=0.15 **climb** | φ=0.20 composition | φ=0.20 **climb** |
|---|---|---|---|---|
| 100 | 0.26 | 0.37 | 0.38 | 0.53 |
| 200 | 0.38 | 0.65 | 0.61 | 0.84 |
| 300 | 0.55 | **0.82** | 0.79 | **0.96** |
| 500 | 0.79 | 0.96 | 0.97 | 0.99 |
| 800 | 0.93 | 0.99 | 1.00 | 1.00 |

**The proposal: `Δ_climb` becomes the primary; the composition test is retained as a
pre-registered secondary**, reported with its interval, but the confirmatory claim rests on the
primary alone. Two primaries would reintroduce the multiplicity this design avoids.

**Why this is a legitimate change and not statistic-shopping:** it is being made with zero
respondent data in existence, which is the only honest moment to choose a statistic. It is
flagged here, in the document, rather than folded in — **if Sebastian prefers to keep the
composition test as primary, the only cost is the N threshold rising from 300 to ~500.**

### 1.3 Decision rule

- Compute `Δ_climb` on the analysis population.
- 95% percentile bootstrap interval over ≥2000 respondent-level resamples.
- **CONFIRMED** if the interval lies entirely above 0 (feedback climbs less).
- **NOT CONFIRMED** otherwise. There is no third category; "trending" is not an outcome.
- One contrast, so **no multiplicity correction is required** for the primary. The five
  per-dimension comparisons (feedback vs each other dimension separately) are reported as a
  descriptive table with intervals and carry **no inferential claim**.

### 1.4 N threshold

**N ≥ 300** completed first-sittings under the current scoring key. That is where the primary
reaches ~0.82 power against φ=0.15, the smallest prevalence worth acting on.

Below 300 the analysis may be run, but its output is a **pilot with no number quoted**. At
N=100 the primary has ~0.37 power against φ=0.15: a null there is close to uninformative, and
reporting it as evidence of absence would be the error this whole rule exists to prevent.

**This has a product consequence Sebastian should see now.** Launch is expected to bring
"10s–100s of users" (STATE §1). At the low end of that range neither of these analyses can
return a result. If they matter, respondent volume is the lever — not statistical technique.

### 1.5 Secondary cells, pre-registered now

Named in STATE and retained. Each is conditioned within its own score stratum, because the
patterns do not share one:

- `{1,1,0,1}` — score **0.75**, the mirror resolution of `fb4v2` (e=1, honest, flagged by the
  confidence measure). **Not visible to the primary test**, which is why it is listed separately.
- `{0,0,1,0}` — score **0.25**, the "in the room is fine, just not straight away" respondent.
- `{0,0,1,1}` — score **0.50**, the same preference resolving `fb4v2` the other way.

Reported as shares with bootstrap intervals, feedback versus pooled others, descriptive.

### 1.6 What each outcome triggers — committed before the data exists

- **CONFIRMED.** The fix is **instrument surgery**: feedback is re-specified as timing ×
  audience, which means a new item set for that dimension, a new `form_version`, and therefore a
  new `scoring_key_version` — under D-18 that re-prompts everyone, by design. It is explicitly
  **not** a special-cased confidence formula for feedback (D-17(a)); papering over a construct
  error inside the scoring key is how the error becomes permanent.
- **NOT CONFIRMED.** Feedback's stored confidence is **backfilled from raw rows** (D-16) using
  the same `1 − e/2` mapping as the other five, and `CONFIDENCE_PENDING_DIMENSIONS` is emptied.
  No re-prompting; nothing about the item file changes.
- **PILOT (N < 300).** Nothing changes. Feedback's confidence stays NULL, the item file stays
  as it is, and no number from the run is quoted anywhere.

### 1.7 Assumptions, stated so they can be attacked

The power table depends on a generative model: rung positions drawn from
`[0.10, 0.22, 0.36, 0.22, 0.10]`, per-item error ε = 0.10, and rule-6 respondents producing
`{1,1,0,0}` deterministically. **All three are guesses.** A flatter rung distribution, a higher
error rate, or a rule-6 population that splits more evenly across `fb4v2` all reduce power and
raise the required N. The N threshold is therefore a floor derived under favourable assumptions,
not a guarantee. If the observed rung distribution at N=100 is much flatter than assumed, the
right move is to raise the threshold — **which must be decided from the rung distribution alone,
without computing the primary statistic**, so that the threshold is not chosen by its answer.

---

## Part 2 — S-17: what a dimension correlation would mean

### 2.1 What is computed

All 15 pairwise correlations among the six scores in `person_dimension_score`, on the analysis
population of §0.1, with bootstrap intervals per §0.2.

### 2.2 The finding that has to be settled first: attenuation

Scores live on the 5-point `PERSON_LATTICE`, and coarse discretisation plus response error
attenuates correlation severely. Simulated, with latent traits of known correlation pushed
through the ladder (ε = 0.10, n = 200k):

| latent r | observed r |
|---|---|
| 0.00 | 0.000 |
| 0.20 | 0.128 |
| 0.30 | 0.190 |
| 0.50 | 0.315 |
| 0.70 | 0.444 |

**The attenuation factor is ≈ 0.63 and is close to constant across the range.** An observed
0.19 corresponds to a latent 0.30; a latent 0.70 shows up as 0.44 and **never reaches the 0.7
that a naive threshold would look for.**

This matters because every threshold in the personality literature is stated on a true-score
scale. Importing one unadjusted would mean a real, model-breaking dependency between two
dimensions could sit at observed 0.44 and be waved through as "moderate." **All thresholds below
are stated on the OBSERVED scale**, with the latent equivalent in brackets, and the factor is
documented rather than applied silently — it depends on ε and the rung distribution, both of
which are assumptions (§1.7).

### 2.3 Thresholds and their pre-committed consequences

Applied to the **interval bound nearest zero**, not the point estimate — conservative by
construction, and it removes the need for a formal correction across 15 pairs.

- **|r_obs| ≥ 0.44 [latent ≈ 0.70] — NOT SEPARABLE AT THIS RESOLUTION.** The two dimensions are
  not carrying independent information at the instrument's resolution. Consequence: the pair is
  a **model identification problem**, not a curiosity — `build_model.py` estimates a `mag` and
  `dir` weight per dimension, and collinear predictors make those weights individually
  unidentified however much data arrives. Triggers an explicit decision: merge the dimensions,
  re-specify one of the ladders, or accept and document that the two weights are interpretable
  only jointly. **Proceeding unchanged is not one of the options.**
- **0.19 ≤ |r_obs| < 0.44 [latent 0.30–0.70] — REAL RELATIONSHIP, RECORD AND MODEL.** Because
  rule 1 gives each dimension its own grading variable, a correlation in this band reads as a
  trait relationship rather than an instrument artifact. Recorded in STATE §5; no instrument
  change; may motivate a causal-candidate item (the S-19 convention: a new ID, not a
  resurrection).
- **|r_obs| < 0.19 [latent < 0.30] — NO ACTION.**

### 2.4 The one inferential contrast: S-24's leak, pre-registered

S-24 records a suspected dimension leak in `au3v2` and names its tell exactly: the item would
correlate *more with decision than with autonomy*. That is a directional prediction, and it gets
the same treatment as Part 1's primary — a single paired bootstrap contrast, not a fishing trip:

    Δ_leak  =  r(autonomy, decision)  −  mean r(autonomy, {pace, collaboration, feedback, innovation})

**CONFIRMED** if the 95% bootstrap interval lies entirely above 0. Consequence: `au3v2` is
rewritten, which is a `form_version` change and therefore a scoring-key change (D-14, D-18).
**NOT CONFIRMED** closes S-24 as considered-and-cleared.

### 2.5 N threshold

Mean 95% bootstrap CI width on an observed r, simulated at latent r = 0.30:

| N | CI width | ± around the estimate |
|---|---|---|
| 100 | 0.370 | ±0.185 |
| 200 | 0.266 | ±0.133 |
| 300 | 0.217 | ±0.109 |
| 500 | 0.167 | ±0.084 |
| 800 | 0.132 | ±0.066 |

**N ≥ 300**, matching Part 1. At N=300 the interval is ±0.109 observed, which is ±0.17 on the
latent scale — just enough to tell the three bands of §2.3 apart. At N=100 the interval spans
±0.185 observed (±0.29 latent), wide enough to cover two bands at once, which makes every
threshold decision arbitrary. Below 300: **pilot, no number quoted.**

### 2.6 Limits

- Correlations here are between **scores**, and a score is a function of (choices, item file,
  scoring method). They are comparable only within one `scoring_key_version` (D-14) and must be
  recomputed, never carried across, an instrument change.
- The attenuation factor is model-dependent (§2.2). Report observed values as primary; treat
  disattenuated values as an aide to interpretation and never quote one as a result.
- A correlation is not a cause. Nothing in §2.3 licenses a causal claim; the causal-candidate
  route is a separate item with its own evidence bar.

---

## Part 3 — What this document does not cover

- **Company-side and match analyses.** Untouched here; they depend on the roster (S-48) and the
  packets (S-49), neither settled.
- **Anything about respondent recruitment.** §1.4 states the volume both analyses need; where
  respondents come from is a product decision.
- **Instrument reliability.** That is the I-O review's question (S-05), and no amount of the
  data described here answers it — four items per dimension is a design constraint (D-02), not
  something these analyses can test.
