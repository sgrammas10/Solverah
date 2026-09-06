# Solverah — Data Retention Schedule

**Adopted [DATE — Sebastian confirms]. Created 2026-08-20 (GAP-04). Enforced by `retention_cleanup.py` where marked ⚙; manual where marked ✋. The privacy policy's retention section must stay consistent with this table.**

| Data | Where | Retention | Mechanism |
|---|---|---|---|
| Account + profile (incl. profile_data JSON) | `user` | Life of account; **de-identified tombstone on account deletion** (D-16 reconciliation, decided 2026-08-20) | Delete endpoint |
| Resume files | R2 bucket | Life of account; deleted on account deletion | Delete endpoint ⚙ |
| Intake submissions attached to an account | `intake_submission` | Deleted on account deletion | Delete endpoint ⚙ |
| **Abandoned intake submissions** (never attached to an account) | `intake_submission` + R2 resume | **90 days** from creation | ⚙ `retention_cleanup.py` |
| Assessment responses + dimension scores | `assessment_response`, `person_dimension_score` | Life of account identified; **retained de-identified after deletion** (linked only to tombstone id, no PII) | Delete endpoint |
| Legacy quiz results (`UserIntake` wpl/wpll) | `user_intake` | Deleted on account deletion; table retires with S-46 | Delete endpoint |
| Job recommendations | `job_recommendation` | Deleted on account deletion | Delete endpoint ⚙ |
| Audit log — event rows | `audit_log` | Keep (security history, actor points to tombstone after deletion) | — |
| Audit log — **IP + user-agent columns** | `audit_log` | **Nulled after 12 months** | ⚙ `retention_cleanup.py` |
| Early-access submissions | info@ inbox (not DB) | Through launch + 6 months, then delete from inbox | ✋ Sebastian |
| Server logs | Render/Vercel | Platform retention — record actual windows in vendor register | ☐ confirm |
| Resume-parse corrections | `resume_parse_correction` | **Deleted on account deletion** — parsed values contain resume content, which is itself identifying, so de-identify-and-keep is not honest here | Delete endpoint |
| LLM/scoring debug artifacts | repo working tree | **Never committed with real user data**; scrub current files, gitignore patterns added | ✋ this change set |
| Backups (Render Postgres) | Render | Platform window; deleted data ages out with backup rotation — disclose "backup-retention window" in policy (done) | — |

**Operating rule:** any new table or file store gets a row here in the same change that creates it.
