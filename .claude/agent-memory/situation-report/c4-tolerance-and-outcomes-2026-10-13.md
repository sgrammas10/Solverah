---
name: c4-tolerance-and-outcomes-2026-10-13
description: C4 (six-trait build, 2026-10-13) - how the Situation Report reads tolerance/must-haves, the five optional outcome items (env-v3), the design calls and why, and the hand-offs left open
metadata:
  type: project
---

C4 landed uncommitted on 2026-10-13 (orchestrated, CompanyLens six-trait plan).

**Tolerance in the report.** `work_pulse/situation.py`: `classify_gap` / `gap_direction` /
`rank_dimensions` / `build_situation_report` take `zones` (C1's `flat_zones`, None = never
answered) and `must_haves`. None takes the old code path verbatim; a frozen copy of the
pre-change functions in `tests/test_situation.py::test_unanswered_tolerance_is_bit_identical`
pins it. Sort key is (severity, must-have, cost, DIMENSIONS order).
`within_tolerance` = aligned with zones AND not aligned under today's 0.15. Wire adds
`tolerance_applied` (complete only) and per-dimension `must_have` / `within_tolerance`.

**Tolerance IS pinned now** (ruling 2026-10-14, superseding the C4 "latest sitting"
read): see [[tolerance-pin-2026-10-14]].

**Outcome items.** `OUTCOME_ITEMS` and `OUTCOME_COLUMNS` are a separate bank, not inside
`CONTEXT_ITEMS`. The reason is that the training assembler restates `CONTEXT_COLUMNS` as
"confounders + experienced", and its tripwire would fail. Columns: `outcome_satisfaction`,
`outcome_performance`, `outcome_engagement`, `outcome_sustainability`,
`outcome_retention_intention`. `model.ENV_OUTCOME_COLUMNS`. Migration
`20261013_envreport_outcomes`. FORM_VERSION is `env-v3-2026-10-13`.

**Skip UI:** `Next`/`Finish` stay disabled until answered on every step, and a separate
"Skip" button appears on unanswered outcome steps. The reason is that
`tests/e2e/real_stack.spec.ts` (frontend-shell) expects the advance button disabled on
every step. Playwright name match is case-insensitive substring, so "Skip and finish"
would collide with "Finish". Never relabel the advance button.

**Hand-offs open at 2026-10-13:** (1) auth-accounts: `ExportedEnvironmentReport` in
`solverah/schemas/account.py` needs the five outcome fields. Until then
`test_export_carries_subject_on_every_environment_report` fails. (2) The pilot form
(`causal_graph/v1_model/pilot_form`) must be regenerated, or its importer accepts v2; 4
tests in test_pilot_form fail on the version. (3) The contract baseline needs a re-baseline
(backend-platform). (4) matching-model C6 adds the outcome columns to the assembler.

See [[lane-state-facts]].
