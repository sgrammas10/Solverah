---
name: pending-g66-user-company-lookup
description: Uncommitted 20261123_user_company_lookup (matching-model, G66) on top of 20261013_pulse_company_link -- reviewed 2026-11-23, APPROVED; open items before commit
metadata:
  type: project
---

`20261123_user_company_lookup` (matching-model, G66: CompanyLens "Your companies" lists only
what THIS user looked up). Table user_company_lookup: bigserial id, user_id BIGINT FK users
ON DELETE CASCADE, company_id INT FK company (no action), created_at timestamptz now(),
UNIQUE uq_user_company_lookup (user_id, company_id). No backfill possible (requester never stored).
Head before it: 20261013_pulse_company_link (six-trait batch, committed 0b7cd8c 2026-10-14).

Reviewed 2026-11-23: chain from empty -> head, populated downgrade to pulse_company_link ->
re-upgrade clean (table + sequence dropped), compare_metadata zero diffs on the table,
schema cluster 132 passed. APPROVED with nits (no company_id index -- fine while nothing
deletes company rows; serial PK matches matching-model neighbours, not Part 4 Identity).

**Open before commit:** auth-accounts' export/delete wiring + COVERED entry in
test_export_delete_coverage (in flight in parallel 2026-11-23).

**Why:** next session must know the head moved and that this was reviewed.
**How to apply:** once committed, delete this file. Related: [[user-fk-ondelete-convention]]
