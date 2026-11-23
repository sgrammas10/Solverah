---
name: export-delete-g66-company-lookups
description: 2026-11-23 user_company_lookup (G66) exported as company_lookups and DESTROYED on deletion, unlike C6's links; wire change needs openapi regen + contract re-baseline
metadata:
  type: project
---

`user_company_lookup` (G66, matching-model's table: "I looked this company up"): exported as `company_lookups` (oldest first; `company_id`, `created_at` only, mirroring `company_links`, which also carries no company name). DESTROYED on deletion via `delete_company_lookups_for_user(db, user_id, commit=False)` in `delete_personal_rows`.

**Why destroy when C6 links are retained:** both rows lack free text, so the D-7b spelling rule alone would keep both. The deciding test is the reader. Links feed the 90-day Pulse check-ins that validate CompanyLens. Lookups have no reader except that user's own list, so keeping them would be retention with no reader (the `path_wants` answer). The orchestrator's brief set this, and I agreed.

**How to apply:** this added a key to the closed `AccountExportResponse`, so the wire changed. `docs/openapi.json` and `schema.ts` need a regen, and the contract baseline pins the full /me/export body (two steps), so it needs a backend-platform re-baseline. I left both for the orchestrator's join because matching-model's companies-API doc changes land in the same regen.

Related: [[export-delete-c6-company-links]], [[export-delete-c1-c3-tables]].
