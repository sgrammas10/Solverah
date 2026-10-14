---
name: sensitivity-test-c9
description: 2026-10-13 C9 (six-trait build) UNCOMMITTED -- penalty-weight sensitivity test (sensitivity.py + 07_SENSITIVITY_RESULTS.md), its headline (pace.mag, innovation.mag/dir, feedback.mag matter; the other 8 do not), the real company set that actually exists (6 round-1 packets, no round-2 draws), build_model flat_zones passthrough, citation-by-URL fix
metadata:
  type: project
---

2026-10-13, lane C9 of the CompanyLens six-trait build. UNCOMMITTED; orchestrator reviews.

**Built.** `causal_graph/v1_model/sensitivity.py` (CLI `python -m causal_graph.v1_model.sensitivity
--out <json> [--table]`), `tests/test_sensitivity.py` (11 tests), results JSON
`causal_graph/v1_model/results/sensitivity_2026-10-13.json`, doc
`Solverah_IP/match_model_alignment/07_SENSITIVITY_RESULTS.md` (the ONLY file I wrote in that
folder -- it is research-ground-truth's). `build_model(flat_zones=None)` + the same kwarg on
`prior_predictive`/`fit_posterior` (passthrough to outcome_logit; 4 PyMC tests in
test_ordinal_head.py section 8). `company_research/research.py::_citations_for` now matches
char_location citations by `cite.url` (infra resolves it from document_index); title match
only when `cite.url is None`; a citation resolved to a DIFFERENT url never falls back to title.
`company_match_service._worst_case_z(evals, person, cfg_weights=None)` gained the optional
pair so the sensitivity ranks THROUGH the service with nudged weights (no second ranking copy).

**Headline (seed 20261013, 200 people, +-50%, share threshold 10%, my choice):** on BOTH sets
pace.mag, innovation.mag and innovation.dir matter; feedback.mag matters on the real set
(12.5%) and is borderline on synthetic (9.5%); the other eight (every other dir, autonomy/
collaboration/decision mag) move < 9% of people. Pattern: sizes drive rankings, directions
barely do. The "unanswered" (0.15 floor) profile flags most -- that is launch's population.

**Traps / facts worth keeping.**
- NO round-2 LLM draws exist (`Solverah_IP/analysis_s58/results/round2/` is absent; no live
  run). The best real company set is 6 packets: round-1 raters A/B/C
  (`ground_truth/rater_app/returned/round1/P-0X_rater*.json`, v1 anchors) + gpt-5.5
  scorer-variance v2 runs (`causal_graph/results/scorer_variance_v2/runs_v2_*.csv`, P-01's file
  is named `runs_v2_gpt55_P01.csv`). Means land mid-scale (0.25-0.88): tau on 6 items is
  coarse (2 adjacent swaps = 0.73 < 0.8) and top-5 never flags; the synthetic set carries the
  top-5 criterion.
- A zero weight (autonomy.dir, innovation.dir) cannot be nudged by 50%; the script probes it
  ABSOLUTELY by +-0.5*|mag| and labels the row "abs". Don't read "does not matter" off a zero.
- Do NOT import `causal_graph/reidentification_attack.py` for packet names: it imports openai
  + pandas at module level. Label by packet id.
- PyMC p_fit at prior means: `model["p_fit"].eval({model[name]: v for name, v in
  model.initial_point().items() if name in model.named_vars})`; `compile_fn(inputs=value_vars)`
  raises UnusedInputError on a deterministic built from RVs.
- Docker Desktop was down mid-task (connection refused on 5433 looks like a missing lane DB
  but was the daemon); `Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"`
  then wait for `(healthy)`.
- Test files must not spell the evidence excerpt column; assert on `source_url`/`source_type`.

**Open.** Doc's limits list: real scores mix two rubric versions; synthetic people are
uniform on the lattice (pole-heavy); the "known" thresholds were NOT varied (pipeline
question, needs real records). Ask for Julie: is innovation really direction-neutral (5/5)?
Blind-rater pairs (C10) should isolate pace-size and innovation-size.

**Why:** PRODUCT_DECISIONS section 2 step (2); roadmap Tier 2 item 3. **How to apply:** re-run
the CLI on real research records after the first live run; a priors change is still
pre-registered first; any new ranking rule in company_match_service is automatically what the
sensitivity measures (it calls the service), so keep `cfg_weights` on `_worst_case_z`.
