---
name: pulse-company-link-id
description: 2026-10-13 (C8, six-trait build) — PulseCheckin.company_link_id attaches the active UserCompanyLink at write time; resolution rule, ownership boundary, migration
metadata:
  type: project
---

Six-trait build item 4 (PRODUCT_DECISIONS.md §2): 90-day check-ins get linked to the
CompanyLens "I took this job" action so a later `experienced` rating can be checked
against the read. C6 (matching-model) built `UserCompanyLink` + `company_evidence_store`
(`company_links_for_user`, `create_company_link`, `delete_company_link`,
`delete_company_links_for_user`). C8 (this lane) added `PulseCheckin.company_link_id`.

**Design:**
- `pulse_checkins.company_link_id` is nullable, FK to `user_company_link.id`,
  `ondelete="SET NULL"`. Migration `migrations/versions/20261013_pulse_company_link.py`,
  revises `20261013_user_company_link`. Deleting a link (user action or account
  deletion's `delete_company_links_for_user`, which bulk-deletes with
  `synchronize_session=False`) relies on the DB-level FK action, not ORM cascade — that
  works regardless of how the delete is issued.
- Resolution happens in `pulse_store._active_company_link_id`, called from
  `pulse_store._add_checkin` (so both `write_pulse_checkin` and
  `write_pulse_checkin_row` get it). "Active" = `started_on <= today` and (`ended_on`
  IS NULL or `ended_on >= today`), read through `company_evidence_store
  .company_links_for_user` (cross-lane read only — this lane never writes
  `user_company_link`).
- `_serialize_checkin` and `_CHECKIN_KEYS`/`_CHECKIN_FORMATS` in `pulse_store.py` now
  include `company_link_id`, so it rides along in `/me/pulse/history` AND `/me/export`
  (`account_service` calls `pulse_checkin_history` for export unchanged — no
  auth-accounts wiring needed on the pulse side).
- Added `PulseCheckinRecord.company_link_id: Optional[int]` in
  `solverah/schemas/pulse.py` — required because `SolverahModel`'s default is
  `extra="forbid"`; without it `GET /me/pulse/history` 500s on the new key.
  `PulseCheckinResponse` (the POST echo) was deliberately left alone — the brief
  didn't ask for API surface changes, just export/storage.
- No ~90-day schedule tied to the link is wired. Flagged as a follow-up idea only, not
  built.

**Regenerated** `docs/openapi.json` and `src/shared/api/schema.ts` for the schema change
(my lane's definition of done requires it for a route/schema change). The diff was much
larger than my one field — catch-up from concurrent uncommitted lane work already on
disk, same pattern as [[schema-ts-drift-not-in-ci]] if that memory exists in this lane
(it's core-assessments'; same phenomenon applies here). Flagged for backend-platform
review, not reviewed by me.

**fnm/npm trap:** `npm`/`node` are NOT on PATH in either Bash or PowerShell tool shells
here, even though the environment-constraints memory says "npm DOES work." The actual
fix: `fnm env --shell bash` from
`/c/Users/Sebastian Grammas/AppData/Local/Microsoft/WinGet/Packages/Schniz.fnm_Microsoft.Winget.Source_8wekyb3d8bbwe/fnm`,
eval'd, then `fnm use default`, in the SAME Bash call as the npm command (shell state
doesn't persist between calls).

**Known-expected failure:** `test_export_delete_coverage
.py::test_every_user_keyed_table_is_covered_or_allowlisted` fails on
`user_company_link` — that's C6's table, auth-accounts wires it next. Not this lane's
to fix.
