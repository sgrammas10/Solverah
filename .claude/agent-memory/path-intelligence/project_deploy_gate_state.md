---
name: project-deploy-gate-state
description: Where Path Intelligence stands against main and the corpus/S3 deploy gate as of 2026-10-02 - F/W-1..W-15 live via PR #155, W-16..W-19 unmerged, runbook lags
metadata:
  type: project
---

As of 2026-10-02 (read-only audit, verified with git):

- Workstream F + W-1..W-15 reached main via PR #155 (merge cc23475, 2026-09-28). The
  original gate "corpus in S3 before merge" was therefore passed then; all 8 corpus
  objects are in bucket `solverah-intake` under prefix `corpus/` (summaries added 2026-09-29).
- `causal_bayesian_model` is 40 commits ahead of origin/main and carries W-16..W-19
  (cards-first narration, `path_narratives` table, W-17 head-first narration, W-18
  summaries, W-19 retention purge of path_fits/path_narratives, detach_before_run fix).
- The next main merge applies migration `20260928_path_narratives` (plus other lanes'
  migrations). `docs/RUNBOOK_DEPLOY_MAIN_MERGE.md`'s Workstream F section still reads as
  pre-merge ("Then merge"), names service `solverah-api` and says to set
  `SOLVERAH_CORPUS_CACHE_DIR` (not needed per Sebastian 09-28), and does not mention the
  path_narratives migration.

**Why:** the gate history lives only in the global memory file
`solverah-corpus-deploy-dependency.md`; the runbook is what a deploy-day reader follows.
**How to apply:** before the next merge, re-confirm `SOLVERAH_CORPUS_S3_KEY` on the Render
web service and that the boot log shows none of the five "sidecar beside" warnings; update
the runbook section (ops-crons owns the runbook file's other sections). See
[[reference-lane-history]].
