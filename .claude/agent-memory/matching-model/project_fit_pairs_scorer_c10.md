---
name: fit-pairs-scorer-c10
description: score_fit_pairs.py scores the C10 blind-rater pair specs through company_match_service; 0 design_check mismatches
metadata:
  type: project
---

2026-10-14 UNCOMMITTED: causal_graph/v1_model/score_fit_pairs.py + tests/test_score_fit_pairs.py; writes Solverah_IP/ground_truth/fit_pairs/pair_model_scores.json (schema fit_pairs_model_scores_v1). Scores via cms._company_eval/_worst_case_z/_order/_next_step with cms._priors_weights() (env var ignored). 50 pairs, 0 pair-level design_check mismatches, analysis cross_check_model (tie/b_last contrasts) clean.

**Why:** prereg step 0 stops the run on any mismatch.
**How to apply:** if priors.yaml or pair_specs.json changes, rerun the CLI; spec_sha256 must match or the analysis refuses. Integer company ids = spec order (service tie-breaks by id; analysis ignores rank_in_block). Heredocs with python source failed in Bash here; use the Write tool.
