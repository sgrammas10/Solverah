---
name: companylens-production-coupling
description: Since 2026-10-13 production CompanyLens imports causal_graph/scorer_pipeline and reads anchors_v3_1_PROPOSED.json at runtime; our 2026-10-13 fidelity review findings and the Julie asks it raised
metadata:
  type: project
---

matching-model's `solverah/services/company_research/` (built 2026-10-13, uncommitted at review)
IMPORTS `causal_graph.scorer_pipeline` (build_rubric_text, call_with_retry, band values,
DIMENSIONS) and reads `Solverah_IP/ground_truth/rater_app/anchors_v3_1_PROPOSED.json` at
runtime. So an edit in our lane to `build_rubric_text`, the band constants, or that anchors
file silently changes PRODUCTION scoring. Solverah_IP is not in `.dockerignore`, so it ships
in the image.

**Why:** Sebastian decided per-item scoring on gpt-5.5 + v3.1 (PRODUCT_DECISIONS §2 six-trait
entry). The validated method was whole-packet, scrubbed, and rater-compared; per-item +
aggregation has never been compared to packet-level scores.

**How to apply:** treat scorer_pipeline's rubric/band code as a production contract: any
change needs matching-model told and their SCORING_PROMPT_VERSION bumped (we recommended a
rubric-text hash test on their side). Review of 2026-10-13 (reported to the orchestrator,
nothing fixed by us): excerpt verification accepts any 10-char cited fragment or 8-word run
from ANY URL (fabricated / blended / false-quote-mark excerpts pass); scorer confidence and
speaker are discarded so gates 2 and 5 are lost; no scrub before scoring (halo); estimate
drops 0.5 items when a minority side exists; split "scope" fires on per-title singletons;
company-authored-only evidence can be "known"; re-runs double-count items; paraphrase gate
passes 13/16-word near copies and verbatim short excerpts. Concordance study (item-level
aggregate vs packet scores on round-1/2 packets) is OUR offer, needs a cost go. Julie asks
(written up 2026-10-14 as match_model_alignment/08_JULIE_ASKS_AGGREGATION.md + 08_EMAIL_TO_JULIE.txt,
six one-tap questions incl. Q6 innovation direction from 07; NOT yet sent): ruling-5 cases (6:2, 5:2 etc.), strength/recency weighting,
company-authored-only "known", time-explained splits. v3.1 stays FROZEN (A2): autonomy/pace
0.5 text "no strong signal" is handled in their per-item instruction, never by editing anchors.
See [[match-model-alignment-response]] and [[round2-rating]].
