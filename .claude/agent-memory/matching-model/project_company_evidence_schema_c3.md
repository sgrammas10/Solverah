---
name: company-evidence-schema-c3
description: 2026-10-13 C3 (six-trait build) UNCOMMITTED -- company evidence tables + company_evidence_store.py + migration 20261013_company_evidence; design calls (link table, derived counts, deferred excerpt), the two guards that read prose, what C5/C6 code against
metadata:
  type: project
---

2026-10-13, lane C3 of the CompanyLens six-trait build (plan:
docs/superpowers/plans/2026-10-13-companylens-six-trait.md; spec: PRODUCT_DECISIONS.md §2
"The six-trait match model"). UNCOMMITTED at time of writing; orchestrator reviews.

Built: model.py company section gained `CompanyResearchRun`, `JobPostingSubmission`
(user-keyed), `CompanyEvidenceItem` (`excerpt_internal` is `deferred`, internal only),
`EvidenceItemScore` (abstained <=> score IS NULL, scorer_run_id NOT NULL),
`CompanyTraitRecord` (known/mixed/unknown; history kept, latest computed_at wins; nullable
`job_posting_id` marks a record PRIVATE to one user's paste -- orchestrator review 2026-10-13:
`trait_records` returns only `job_posting_id IS NULL`, `posting_trait_records` the owner's,
the store refuses to link scores across the private/shared line, deletion destroys them),
`CompanyTraitRecordEvidence` (record -> item-score links; MY addition beyond the brief so
`items_for_record` is exact and counts are derivable), plus `Company.headcount/_as_of/_source`.
Store: `company_evidence_store.py` (repo root). Migration `20261013_company_evidence`
(down_revision `20261013_trait_prefs`, C1's). Guard: tests/test_company_evidence_internal.py.

Design calls worth remembering:
- `write_trait_records` DERIVES evidence_count/abstain_count (and the dated range when not
  given) from the linked score rows; callers pass `score_ids`, never counts.
- stage_size bands (store.STAGE_SIZE_BANDS) = the Environment Report's own item: <10 ->1,
  <100 ->2, <1000 ->3, <10000 ->4, else 5. `set_company_size` upserts the confounder on the
  existing (company, key, source, as_of) key.
- Every write commits; every function takes `db` first (brief's signatures).
- No NULLS NOT DISTINCT key needed (stated in the migration docstring, not assumed).

**Why:** each company trait is a RECORD, not a number; GAP-14 forbids verbatim third-party
text on any surface, so paraphrase is the only user-visible text.

**How to apply:** C5 (research/scoring) writes through the store only and lives in
`solverah/services/company_research/` (pre-granted in the excerpt guard). C6 reads
`trait_records` + `items_for_record` only. TRAP: tests/test_company_confidence_unused.py
reads PROSE -- spelling the S1-6 score table's name in a docstring beside a `confidence`
field fails it; reword, never add to ALLOWED (same as the D-01 guard). Open hand-off:
`job_posting_submission` fails test_export_delete_coverage until auth-accounts wires
`job_postings_for_user` / `delete_job_postings_for_user` (both already in the store).
Lane DB: solverah_c3 (pytest). The alembic-migrated throwaway (c3b) was dropped on
2026-10-13; recreate one from empty for a chain check -- a DB built by an EARLIER version
of a migration cannot downgrade through the revised one (ix_ctrait_posting "does not exist").
