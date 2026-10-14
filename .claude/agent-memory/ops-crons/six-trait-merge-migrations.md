---
name: six-trait-merge-migrations
description: next main merge applies 10 revisions from 20260921_path_wants (measured 2026-10-14); a code rollback to old main needs `flask db stamp` first
metadata:
  type: project
---

Measured on 2026-10-14 against `origin/main` = cc23475 (PR #155), whose head is
`20260921_path_wants`. The next merge applies 10 revisions: 5 from 09-28 to 10-02
(path_narratives, ledger_indexes, envreport_industry, envreport_subject,
experiment_completed) and 5 from the six-trait build (trait_prefs, company_evidence,
envreport_outcomes, user_company_link, pulse_company_link). The brief said "six new";
there are five. Re-measure if anything lands on main or new revisions appear.

The trap: redeploying an older main commit runs its pre-deploy `flask db upgrade`, which
fails with "Can't locate revision" whenever production is ahead of that commit's chain.
The deploy is then refused, and the new code keeps serving. A code rollback is therefore
`flask db stamp <old head>` first, then the redeploy. To roll forward again, stamp back
to head, otherwise the `CREATE TABLE`s replay. The deploy-2 rollback note ("redeploy the
previous commit; tables sit unused") skipped this.

**How to apply:** every deploy runbook's rollback section must name the stamp target.
Written into RUNBOOK_DEPLOY_MAIN_MERGE.md ("CompanyLens six-trait" → Rollback) and
RUNBOOK_DATABASE_ROLLBACK.md §8. The six-trait downgrade chain is unrehearsed.
