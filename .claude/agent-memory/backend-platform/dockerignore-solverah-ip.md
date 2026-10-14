---
name: dockerignore-solverah-ip
description: Solverah_IP (37 MB) ships in the API image but nothing under solverah/ reads it at runtime since C5b froze anchors_v3_1.json in-package; excluding it in .dockerignore is recommended, not yet done
metadata:
  type: project
---

Checked 2026-10-14. Runtime imports from `solverah/services/company_research/` reach
`causal_graph/scorer_pipeline.py`, which at import only RESOLVES `REPO_IP` (walks parents for a
`Solverah_IP/ground_truth/rater_app/anchors.json`, falling back to a path with no existence check) and
never opens a file there. `score_items.ANCHORS_PATH` is the in-package `anchors_v3_1.json`;
`ANCHORS_SOURCE_PATH` (under Solverah_IP) is read only by `tests/test_company_research_pipeline.py`, and
`tests/` is already excluded from the image. `work_pulse/situation_items.py` names the rubric in prose
only. No cron, CLI, render.yaml or compose entry reads Solverah_IP.

**Why:** 37 MB of research corpus in a production layer is weight and exposure for nothing; the frozen
copy was made precisely so production stops reading the corpus (review F14).
**How to apply:** add `Solverah_IP` to `.dockerignore` (backend-platform's file) once the orchestrator
agrees; `causal_graph/` must STAY in the image (scorer_pipeline, match_core, priors.yaml are runtime).
A side fact: `causal_graph/scorer_pipeline.py` imports `random` at module level and is imported by
`solverah/services/company_research/` -- `test_otp_entropy` scans only `solverah/`, so it does not fire.
