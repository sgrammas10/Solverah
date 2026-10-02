---
name: reference-lane-history
description: Where this lane's history lives - the global auto-memory files and in-repo docs that hold Workstream F/W rulings, numbers and open decisions
metadata:
  type: reference
---

This lane's long history predates this directory and lives in the user's global
auto-memory (`C:\Users\Sebastian Grammas\.claude\projects\c--Users-Sebastian-Grammas-Desktop-Solverah\memory\`):

- `solverah-path-intelligence-redesign.md` - 54 KB running log of F and W-1..W-19
  (eval numbers, rulings, every landing). Read its tail, not the whole file.
- `solverah-corpus-deploy-dependency.md` - S3 gate history and deploy-day order.
- `solverah-onet-corpus-artifact.md`, `solverah-local-dev-python310.md`.

In repo: `docs/BUILD_PLAN.md` §6/§6a (W boxes - some unticked boxes are stale),
`docs/PATH_WANTS_DECISIONS.md` (item 7, Stay pool size, deferred to Julie 2026-09-28),
`docs/PATH_WANTS_USER_TESTS.md` (sections A-O; nothing yet for W-16..W-18 or the
2026-09-28 entry gates). `docs/USER_SCENARIOS.md` S16.9-S16.12 predate W and the gates.

See [[project-deploy-gate-state]].
