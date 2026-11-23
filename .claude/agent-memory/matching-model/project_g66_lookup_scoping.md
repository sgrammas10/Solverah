---
name: g66-lookup-scoping
description: 2026-11-23 UNCOMMITTED (G66) -- /me/matches scoped to the user's own lookups via new user_company_lookup table + migration 20261123_user_company_lookup; recorded by POST /companies/research incl. cache/in-flight hits; hand-offs to auth-accounts (export/delete) and backend-platform (capture_contract seed)
metadata:
  type: project
---

G66, Sebastian's ruling 2026-11-23: CompanyLens "Your companies" lists only companies the
signed-in user looked up. Before this, NOTHING recorded who requested research (runs are
per company and shared; a cache hit wrote no row), so a migration was unavoidable.

Built: `model.UserCompanyLookup` (`user_company_lookup`, unique (user_id, company_id),
user FK ON DELETE CASCADE), migration `20261123_user_company_lookup` (revises
`20261013_pulse_company_link`). Store: `record_company_lookup` (ON CONFLICT DO NOTHING),
`company_lookups_for_user`, `delete_company_lookups_for_user(commit=)`,
`companies_with_shared_records(db, looked_up_by=)`. The route records the lookup right
after `request_research` returns (new, cached, or in-flight); refused requests write none.
No backfill possible; solverah_julie had 0 research runs.

**Why:** privacy -- users saw what others looked up. **How to apply:** test helpers that
seed records through the store must also record a lookup or the company is invisible in
/me/matches (`_records` in test_company_lens_api defaults to every registered user).
Open: auth-accounts wires export/delete (test_export_delete_coverage red until then);
backend-platform's `Scripts/capture_contract._seed_company_records` must record a lookup
or `matches-ranked*` steps capture `no_companies`. Detail page `/companies/<id>/read`,
`GET /companies`, and research-run polling are still unscoped by user (left as is).
