---
name: hinge-serving-shape-2026-10-13
description: C2 of the CompanyLens six-trait build (UNCOMMITTED 2026-10-13) - match_core hinge (flat_zones), env_missing mask, point_z ranking entry, priors.yaml why/date keys, prereg Amendment 3; the rescaling form and the traps found while pinning bit-identity
metadata:
  type: project
---

Built 2026-10-13 as lane C2 (orchestrator dispatch), UNCOMMITTED at time of writing.

**What exists now.** `match_core.outcome_logit(..., flat_zones=None, env_missing=None)`,
`point_z` (z only, for ranking - no probability may reach a user), `point_p_fit` /
`score_pairs` with the same two args LAST, `excess_gap(gap, under_zone, over_zone)`,
`POLE_GAP` (0.8, derived from COMPANY_LATTICE max - min). `match_scoring` passes them
through and adds `z_with_current_run`. `priors.yaml` has `why` + quoted `date` per
entry (numbers byte-identical, verified by loaded-leaf repr vs HEAD); the `cutpoints`
block in priors_placeholder.yaml carries the same two keys because a test asserts the
two blocks are equal. Prereg Amendment 3 appended (exploratory outcomes, hinge pre-built
for Look 2 as the FIXED 0.15 variant, personalised zone exploratory, tolerance/must-have
exploratory, transfer gap (d) with no decision rule). Tests: tests/test_match_hinge.py.

**The rescaling (my call, documented in match_core):** excess = max(0, |gap| - zone),
then `(excess / (POLE_GAP - zone)) * POLE_GAP` - divide by the run FIRST so at the pole
the ratio is x/x == 1.0 and a pole gap is a pole gap to the bit; Julie's twelve answers
reproduce under any zone. Zone must be in [0, 0.8); floor 0.15 is applied upstream
(C1's `solverah/domain/trait_preferences.flat_zones`), never here. gap = person - env;
gap > 0 reads the UNDER zone (tuple index 0), gap < 0 the OVER zone (index 1). Zone
applies AFTER the person-side lattice snap. Written with abs/+/-/*/ only (tensor-safe;
np.where and np.maximum both fail on a pytensor TensorVariable, checked).

**Traps found.** (1) Floating-point addition is not associative: accumulating
`term = mag + dir` then `z += term` broke bit-identity by 1 ulp vs HEAD's two separate
`z +=`. Keep the same association in every branch. (2) A masked env row may be NaN and
NaN * 0.0 is NaN, so the masked branch substitutes 0.5 with np.where first (numpy-only
branch, like closest_achievable). (3) `date:` must be QUOTED in YAML or PyYAML loads a
datetime.date. (4) Adding keys changes `match_scoring._priors_version` (sha256 of the
file): any DB that already held a v1-priors-only run seeds a SECOND one on the next
`seed_priors_model_run` - harmless (idempotency is per hash), but prod never seeds.

**Open at the C6 join:** C1's `flat_zones` returns None for an UNANSWERED user
("today's path"); in match_core None = linear-from-zero, not the 0.15 hinge. Whether an
unanswered CompanyLens user gets `{d: (0.15, 0.15)}` or None is C6's/Sebastian's call
(PRODUCT_DECISIONS says both "hinge is the serving default" and "unanswered = exactly
today's behaviour (0.15 floor)"). Amendment 3 was worded to not pre-empt it.

**Done by C9 (2026-10-13):** build_model / prior_predictive / fit_posterior take
`flat_zones=None` and pass it to outcome_logit (test_ordinal_head.py section 8). No devfit
recovery run - the fit path is bit-identical with zones off. Situation Report tolerance = C4; match service = C6
(score mixed traits by calling point_z twice, once per end, or mask the trait).

**Why:** PRODUCT_DECISIONS section 2 (2026-10-13) made the hinge the serving default and
the penalty table self-documenting; Amendment 3 keeps the prereg honest before Look 2.
**How to apply:** any new predictor branch must be pinned bitwise against a verbatim HEAD
copy on random rows AND keep the addition order; never re-floor zones in match_core.
