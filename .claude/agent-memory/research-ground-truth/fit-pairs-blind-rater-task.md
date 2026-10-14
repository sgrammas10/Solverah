---
name: fit-pairs-blind-rater-task
description: C10 blind-rater fit task (2026-10-13/14) in Solverah_IP/ground_truth/fit_pairs/ -- 10 blocks x 5 pairs + 4 repeats, prereg, hook for matching-model; NO eligible rater exists yet
metadata:
  type: project
---

Built 2026-10-13/14 (lane C10), uncommitted. PRODUCT_DECISIONS section 2 step (3): raters who did
not set the weights judge person/company fit; compared with the model's within-person order.
Prereg `PREREG_FIT_PAIRS_2026-10-13.md` (commit before any page goes out; addenda only after data).

**The blocker:** the round-2 roster is only Julie (A) and Sebastian (D), and both are excluded
by rule (sets_weights). Carolynn (B) and George (C) are recorded as permanently unavailable.
So `roster.json` has ZERO eligible raters. New raters take E onward, and only Sebastian can recruit them.
The builder refuses A/D/B/C; the analysis raises ExcludedRaterError on an A or D return.

**Design facts worth knowing:** block order B1,B9,B2,B10,B3..B8 (B9/B10 added 2026-10-14 from
matching-model's 07 sensitivity run: isolate pace.mag, innovation.mag, innovation.dir with
same-size single gaps vs an autonomy control; placed inside the 4-block minimum). Repeats
reference the same pair id and render byte-identical cards (the need-vs-tolerance lesson);
consistency is therefore an upper bound. Verdict thresholds: inter-rater tau-b gate 0.40,
consensus tau-b >=0.50 stand / <0.20 review; contrasts K1-K11. Model z ties are kept as ties
(never use rank_in_block, which breaks ties by id).

**Hand-off:** matching-model scores `pair_specs.json` (schema fit_pairs_spec_v1) into
`pair_model_scores.json` (fit_pairs_model_scores_v1, schema in prereg section 3) through
company_match_service's own path with priors weights. We never compute rankings.

**How to apply:** after any design.py change: `python design.py`, rebuild the Z test page,
re-run test_fit_page.cjs (it rewrites fixtures/captured_payload_raterZ.json), then pytest.
Related: [[companylens-production-coupling]], [[match-model-alignment-response]].
