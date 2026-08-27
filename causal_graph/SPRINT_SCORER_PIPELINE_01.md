# Sprint: Scorer Pipeline 01 — "Instrument before build"

> **STATUS: COMPLETE 2026-08-17.** Hold lifted same day. All seven tasks (S1-1 through S1-7) built,
> verified, and — where they touch the live API — run for real. Full results in
> `SOLVERAH_HANDOFF_2026-08-17b.md`. The two blocking decisions (#6 confidence role, #7 discrete
> bands) were ratified as recommended below (informational-only, keep continuous + optional band
> column). Nothing in this doc's original scope, corrections, or design constraints was changed —
> S1-1 through S1-7 below are the historical plan and were followed as written.
>
> ~~**STATUS: ON HOLD 2026-08-09 — not approved, do not start.** Sebastian is reviewing before any
> code is written.~~
>
> **Amendment, same day:** the 19-company v3 kit has been scrapped; ground truth is the 6-company
> v4.1 / rubric v3 kit only. This does not invalidate the corrections below. The v3 GT-01 packet and
> `runs.csv` survive as a **thin-packet test fixture** (2,880 chars vs P-01's 12,499) for the S1-4
> richness contrast — retired as a rater instrument, still valid as a stimulus. Open item #1
> (George holding RATER_B against v3) is resolved by the scrap, but he needs to be told.
>
> Also outstanding and not yet reflected here: the **source matrix** workstream. It is two distinct
> objects — (A) per-packet source × dimension *coverage*, which fixes §3 defect 1, and (B) global
> source-type *authority*, which is what makes the 0.7 rule mechanical and defines the closed
> `source_tags` vocabulary S1-1 needs. (A) carries a contamination risk: a source × dimension map is
> dimension-routing by definition, so it must be computed post-hoc from a frozen packet and may drive
> re-collection **by source rung only, never by dimension**.

**Planned 2026-08-09.** Source: `SOLVERAH_HANDOFF_TECHNICAL_PLANNER_2026-08-09.md`, verified against the
repo. Sprint goal: make the LLM scorer a *pinned, measurable instrument* that emits verifiable
evidence, and settle the two open measurement questions that would otherwise force a rewrite of the
runner and aggregator later.

Explicitly **not** in this sprint: the collector, the anonymizer, `assemble_training_data`, serving.

---

## Corrections to the handoff (verified against the repo, 2026-08-09)

These change the plan, so they are recorded before the tasks.

**1. Section 8's ordering is wrong. The citation verifier cannot be built first.**
`causal_graph/scorer_variance_test.py`'s `RESPONSE_SCHEMA` emits only `{score, confidence}` per
dimension. There is no `evidence_quotes`, no `source_tags`. The pipeline spec in section 4.1 requires
both, and the verifier consumes them. Nothing in the codebase produces the verifier's input.
Extending the scorer output schema is a hard prerequisite, not item 4.

**2. "`model_run` already has the slot" for the LLM model string is false.**
`schema.sql`'s `model_run` holds `model_version`, `dimension_set_version`, `priors_version` — it
versions the *PyMC fit*. There is no column anywhere for the LLM model string, temperature, rubric
version, or packet version. Reusing `model_run` would fuse two unrelated versioning axes: the
scorer changes when a vendor ships an update, the Bayesian model changes when priors or dimensions
change, and they must be independently queryable. A separate `scorer_run` table is required.

**3. Discrete bands are not a proposal (§4.3) — they are the measured behavior.**
Across 30 score cells in `runs.csv`, `gpt-4o-2024-08-06` used seven distinct values
(0.4 / 0.5 / 0.6 / 0.7 / 0.75 / 0.8 / 0.9). Confidence used four (0.5–0.8). The "continuous 0–1"
output schema is a fiction the model does not honor. Adopting explicit bands would document reality
rather than change it. The decision that actually matters is downstream, in item 4.

**4. Median is the wrong aggregator, and this is decidable today.**
Bootstrap over the observed per-dimension distributions in `runs.csv` (20,000 reps):

| n runs | SE of median | SE of mean | mean advantage |
|---|---|---|---|
| 5 | 0.0602 | 0.0393 | 1.53× tighter |
| 7 | 0.0525 | 0.0332 | 1.58× |
| 9 | 0.0469 | 0.0293 | 1.60× |

Two things to note. First, mean beats median at every n. Second — the more important one —
**median barely improves as n grows.** Median-of-9 (0.0469) is still worse than mean-of-5 (0.0393).
That is quantization: the median can only ever return a value the model actually emitted, so on a
~0.1 lattice it cannot converge between bands no matter how many runs you buy. Paying 9× API cost
to get an estimator worse than 5× is the wrong trade.

The usual argument for median — robustness to a wild outlier run — does not apply here. The observed
noise is a **per-run mood effect**: run 2 sits −0.102 and run 4 sits +0.115 across *all six*
dimensions together. That is a correlated shift, not a single wild value, and the median gives no
protection against it. Nor is it removable: each company is scored in an independent stateless API
call, so run identity is not shared across companies and the mood offset is unidentifiable. It just
is variance, and only n reduces it.

*Caveat, stated so it is not oversold:* this bootstrap resamples five observed values per dimension,
so it is an empirical-distribution approximation, not a true sampling distribution. The direction is
structural (lattice quantization) and will hold; the exact ratio should be re-confirmed on the wider
data from S1-4.

**5. The re-test in §8 item 5 is confounded as specced.**
The script hard-codes rubric **v2.1** and the **v3** GT-01 packet (~2,880 chars). The live kit is
rubric **v3** with **v4.1** packets (P-01 is 12,499 chars). Swapping only the model measures tier on
a retired instrument. Swapping both makes tier and packet richness inseparable — and packet richness
is a live hypothesis, since §3 argues thin evidence is exactly what forces the model onto its prior.
Run the 2×2.

---

## Sprint scope

| # | Task | Depends on | Rough size |
|---|---|---|---|
| S1-1 | Extract rubric + packet to versioned files; extend response schema with `evidence_quotes` + `source_tags`; define `ScorerResult` | — | M |
| S1-2 | Thin provider interface: `score_packet(packet, rubric, model_cfg) -> ScorerResult` | S1-1 | M |
| S1-3 | Confirm mean-over-median on the wider data; set the aggregator estimator | S1-4 | S |
| S1-4 | 2×2 variance matrix: {gpt-4o pinned, stronger pinned} × {v3 packet, v4.1 P-01 packet} | S1-2 | S |
| S1-5 | Citation verifier + `citation_check.csv` | S1-1 | M |
| S1-6 | Propose (do not apply) schema extension DDL | S1-1 | S |
| S1-7 | pytest suite + end-to-end dry run on P-01 | all | M |

### Design constraints carried in from the handoff

- Pin the exact model snapshot string, never an alias. Record it on every row.
- Browsing off, no tools, strict JSON schema.
- **Log whether the temperature parameter was rejected.** Reasoning models silently ignore it, and
  near-zero variance from an ignored temperature is not the same finding as near-zero variance from
  a better model. This must appear as a `temperature_honored` boolean on `scorer_run`, not a
  print statement.
- A failed run is recorded as a row, not an aborted sweep.
- Every pipeline stage returns proof of what it *attempted*, not just what it produced — the yield-audit
  lesson from §3, applied to code. The verifier's unmatched-quote dump is the direct analogue.

### Pre-registered bar for S1-4 (set before looking, per §5)

- SD → ~0.02–0.03: Test 1's 0.08 deltas become interpretable; model tier becomes load-bearing.
- SD stays ~0.05+: deltas remain inside noise regardless of tier, and n must go up.
- Re-check the per-run mood effect **separately** — low per-dimension SD with a surviving correlated
  run-level severity shift is still fatal to the "five of six" confidence argument.

> **PARTIAL DATA POINT, 2026-08-17 — does not lift this hold.** A narrower cell than this
> section specs (stronger model × real anonymized packet × the frozen `anchors.json`
> instrument, NOT the full 2×2 — old model was not rerun on the new packet, new model was not
> rerun on the old packet) was run against P-01 and P-02, n=5 each. Full writeup:
> `SOLVERAH_HANDOFF_2026-08-17.md`. Headline: mean SD cleared the bar on both (0.033, 0.037),
> but the bar assumed roughly uniform per-dimension SD and neither packet is uniform — both are
> four dimensions at exactly zero plus two wobbling a full band, and *which* two changes between
> packets (decision solid on P-01, the least stable cell on P-02; innovation the reverse).
> Feedback failed on both. **The result that actually replicated cleanly is the per-run mood
> effect: 0.0667 spread on both packets, against gpt-4o's original 0.22** — the specific failure
> mode this section cares most about. Model tier is still not isolated from packet/schema.
> Script: `scorer_variance_test_v2.py`, same folder.

---

## Decisions this sprint forces, that are yours (§9)

Sequenced by when the code will actually block on them.

**Blocks S1-1 (schema shape) — needed now:**

- **#6, what does `confidence` do downstream?** The output schema and the DDL both bake this in.
  Recommendation: **informational only for now**, stored but inert. It is reversible, and the
  handoff already rules out the shrink-toward-0.5 option on product grounds. Weighting the likelihood
  is defensible but should not be chosen before the calibration check in §8 item 7 exists.
- **#7, discrete bands?** Per correction 3 this is now a documentation question, not a behavior
  question. Recommendation: keep the continuous field in the DDL, add an optional `band` column,
  and defer the rubric change — changing the rubric mid-sprint invalidates the S1-4 comparison.

**Blocks nothing in code, but the cost of delay is running:**

- **#1, George on v3 packets.** Open since 2026-08-07. His `RATER_B` scores are on a different
  instrument and cannot merge with a v4.1 rater's. Every day is either useful work or wasted work,
  and there is no third state. This is the single highest-cost open item in the handoff and it is
  not a technical decision — it needs a call.
- **#8, the 0.15 agreement threshold.** S1-4 produces the number that should set it. If the
  instrument itself wobbles ~0.098 on identical input, a 0.15 human-disagreement threshold is
  measuring noise. Hold the threshold until S1-4 lands, then set it from measured instrument SD.

---

## Why not `assemble_training_data` first

The handoff lists it as item 2 and notes it has been "missing in every handoff since July." It is
still the right thing to defer. A training row requires an `outcome_experienced`, and there are
zero. The function would be written, untestable against real data, and then rewritten once the
scorer output shape settles — which is what this sprint settles. The project's own §10 principle
applies: inputs are the long pole.
