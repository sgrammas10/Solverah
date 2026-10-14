---
name: export-delete-c1-c3-tables
description: 2026-10-13 export/delete wiring for person_trait (C1, retained under tombstone) and job_posting_submission (C3, destroyed in the deletion's own transaction); the D-01 substring trap and the excerpt_internal ban
metadata:
  type: project
---

Wired 2026-10-13 (uncommitted, orchestrator wave):
- C1 trait-preference sittings: exported as `trait_preferences` (picked by name from `assessment_store.export_person_side`). RETAINED on deletion under the tombstone, the same as the core assessment's answers and scores: D-01-gated, no `ondelete`, no free text. The coverage test lists it in `_D01_GATED_TABLES` by concatenation. The D-01 guard does a SUBSTRING match on every string literal, docstrings included, so never write the table name in prose.
- C3 `job_posting_submission`: exported as `job_postings` (newest first, posting_text included). DESTROYED in `delete_personal_rows` via `company_evidence_store.delete_job_postings_for_user(db, user_id, commit=False)`, which removes items, scores, private records and link rows too. Matching-model added `commit=False`; the old `_InCallersTransaction` adapter is gone.

**Why commit=False matters:** `delete_personal_rows` must not commit, or a deletion that fails at the tombstone leaves a live account with its postings gone. `test_posting_destruction_waits_for_the_deletions_own_commit` guards it.

**How to apply:**
- `tests/test_company_evidence_internal.py` bans the `excerpt_internal` name, including as a keyword argument, in any file not on its allowlist. Build `EvidenceItemInput` with positional arguments in auth tests.
- Any store row that flows into `/me/export` through a closed schema (`SolverahModel` is extra=forbid) needs its new keys added to `solverah/schemas/account.py`, or `AccountExportResponse.model_validate` breaks. C8's `company_link_id` on pulse check-ins was caught this way; see [[export-delete-c6-company-links]].
- The contract baseline's `export` body does not yet include `job_postings: []`, `trait_preferences: []` or `company_links: []`. Backend-platform must re-baseline it.
