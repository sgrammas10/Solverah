---
name: pending-six-trait-migrations
description: The five uncommitted 20261013_* revisions (trait_prefs -> company_evidence -> envreport_outcomes -> user_company_link -> pulse_company_link) -- all reviewed 2026-10-13, chain proven from empty + round trip; what is still open before commit
metadata:
  type: project
---

Five uncommitted revisions for the six-trait CompanyLens build
(docs/superpowers/plans/2026-10-13-companylens-six-trait.md), head `20261013_pulse_company_link`,
chained after `20261002_experiment_completed`:

- `20261013_trait_prefs` (core-assessments, C1) -- person_trait_preference. APPROVED.
- `20261013_company_evidence` (matching-model, C3, amended in place by C5b: diagnostics_internal,
  speaker, iscore confidence, ck_ctrait_split_not_unknown, ix_ctrait_latest DESC/DESC). APPROVED.
  In-place amendment was legitimate only because the file was never committed or deployed.
- `20261013_envreport_outcomes` (situation-report, C4) -- five outcome_* SMALLINT 1..5. APPROVED.
- `20261013_user_company_link` (matching-model, C6). APPROVED WITH NITS: `ended_on` has no write
  path and no overlap rule (product question, not a schema defect); store docstring says the
  deletion flow must clear pulse's column first, which SET NULL made false.
- `20261013_pulse_company_link` (pulse-experiments, C8) -- pulse_checkins.company_link_id,
  ON DELETE SET NULL. APPROVED WITH NITS: add a plain index on company_link_id (ledger rule:
  an ON DELETE SET NULL target makes every delete scan the referencing table; precedent
  ix_user_sessions_parent). pulse_checkins is NOT partitioned.

Verified 2026-10-13 on a throwaway DB: upgrade from empty -> head; downgrade all five with
populated rows -> 20261002_experiment_completed; re-upgrade -> head; compare_metadata and a
pg_constraint CHECK/index/FK-action diff both clean on every touched table. Note
compare_metadata does NOT compare CHECK constraints -- diff pg_constraint by hand.

**Open before commit:** `test_export_delete_coverage` fails on `user_company_link` until
auth-accounts lands export (`company_links_for_user`) + deletion
(`delete_company_links_for_user(commit=False)` inside delete_personal_rows) + a COVERED entry.
Rollback of the whole deploy is `flask db downgrade 20261002_experiment_completed`; no runbook
entry written (each step is a plain downgrade -1).

Ownership rows for PersonTraitPreference (core-assessments) and the evidence classes +
UserCompanyLink (matching-model) were added to `.claude/agents/schema-steward.md` 2026-10-13.

**Why:** a later session must know these were reviewed, what is still blocking, and that
the chain head moved five links in one uncommitted batch.
**How to apply:** once committed, delete this file. Related: [[experiments-table-drift]]
