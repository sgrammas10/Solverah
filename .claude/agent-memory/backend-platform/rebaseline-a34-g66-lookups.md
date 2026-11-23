---
name: rebaseline-a34-g66-lookups
description: A34 re-baseline (G66 per-user company lookups, 2026-11-23) DONE uncommitted, still 156 steps; the company seed must record the lookup or both ranked /me/matches reads collapse to no_companies
metadata:
  type: project
---

A34 (docs/ARCHITECTURE.md) re-baselined docs/contract_baseline.json on 2026-11-23, uncommitted on
causal_bayesian_model (orchestrator dispatch, sprint bug batch). Pre-change verify against A33: exactly 4
body-only differences -- `export`, `export-after-companylens` (`company_lookups` added) and
`matches-ranked` / `matches-ranked-with-preferences` (collapsed to `no_companies`). After the seed fix only
the two exports move: `export` gains `company_lookups: []`, `export-after-companylens` gains
`[{company_id: 1, created_at: <TS>}]`. Recapture verified: 0 differences across 156. Captured on
`solverah_fx_c` (an orchestrator-made throwaway DB, not `solverah_contract`).

**Why the seed change:** since G66, `GET /me/matches` lists only companies in `user_company_lookup` for the
caller. `_seed_company_records(app, email, company_id)` now calls
`company_evidence_store.record_company_lookup` for EMAIL after closing the run. The lookup is seeded rather
than written by a research POST because the research-door steps are appended last; moving one would reorder
recorded steps.

**How to apply:** any future seed of a company that a ranked read should list must also record a lookup for
the reading user. The intake sign-in door (`claim_pending:<id>` parking) is NOT in the scenario; it is
pinned by unit tests only. Carry-overs from [[rebaseline-a33-companylens]] (provider keys popped, no
LLM-route steps, the jobs.dispatch Celery-conf hazard) still stand.
