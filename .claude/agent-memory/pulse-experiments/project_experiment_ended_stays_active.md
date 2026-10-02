---
name: experiment-ended-stays-active
description: OPEN 2026-10-02 - a naturally ended experiment keeps status='active', so the one-active index and the 409 check block every later start; UI swallows the 409
metadata:
  type: project
---

Found in the 2026-10-02 read-only lane audit (pre-Julie-day). `experiments.status` only has
'active'/'abandoned'; phase 'ended' is derived from ends_at on read. `experiment_store.active_experiment`
filters `status='active'` with no ends_at check, and `uq_experiments_one_active_per_user` is a partial
unique index on status='active'. So after day 14 every new start 409s. The frontend computes
`hasActiveExperiment` from phase==='running' (false), offers an enabled button, and
`ExperimentControl` hides the 409 (`!isExperimentAlreadyActive`) -> a dead button. No UI can abandon
an ended experiment. No test covers "start after natural end".

**Why:** the fix needs a status vocabulary change (e.g. 'completed') + CHECK-constraint migration,
so schema-steward must review; abandoning the ended row instead would relabel it "Abandoned" and
hide its readout.

**How to apply:** before touching experiments, check whether this is fixed (grep active_experiment
for ends_at). Related: [[pulse-cron-status]].
