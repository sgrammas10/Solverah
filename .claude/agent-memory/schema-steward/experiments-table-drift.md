---
name: experiments-table-drift
description: Known, harmless ORM-vs-migration drift on the experiments table (FK name, status server default) -- not from any pending revision; do not re-report it
metadata:
  type: project
---

`experiments` has pre-existing drift that compare_metadata and `\d` will keep showing:
the migration (20260914_experiments.py:46) names the user FK `fk_experiment_user` while
the ORM gives `experiments_user_id_fkey`, and the migration sets server_default 'active'
on `status` where the ORM has only a Python default. Noted during the
20261002_experiment_completed review (that revision is committed in 53c0e49).

**Why:** a reviewer running the parity script sees it in the "other diffs" list and may
blame the revision under review.
**How to apply:** treat it as background noise alongside the partition-child
false positives; cleaning it up is a standalone chore, not part of any lane's migration.
