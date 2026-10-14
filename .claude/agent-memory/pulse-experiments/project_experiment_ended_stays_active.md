---
name: experiment-ended-stays-active
description: FIXED 2026-10-02 (uncommitted at write time) - experiments.status gained 'completed'; the service closes ended rows lazily before every read/write; why that design and not a cron or read-time derivation
metadata:
  type: project
---

Found in the 2026-10-02 read-only lane audit, fixed the same day in the fix wave (F1). Until then
`experiments.status` only knew 'active'/'abandoned', phase 'ended' was derived from ends_at on read,
and a naturally ended row stayed 'active' forever -- so `uq_experiments_one_active_per_user` and the
409 check refused every later start, and `ExperimentControl` hid the 409 (dead button).

**The design chosen:** a third stored status `completed`, written LAZILY by
`experiment_store.close_ended_experiments(db, user_id, now=)` which `experiment_service._close_ended`
calls (and commits on its own only if a row moved) at the top of start / list / abandon. No cron.
Migration `20261002_experiment_completed` (revises `20261002_envreport_subject`) widens the CHECK and
backfills `active AND ends_at <= now()` -> `completed`; its downgrade relabels completed -> active and
REFUSES if any user holds completed + active (the old schema cannot hold that). Proven up/down on
solverah_fx_pulse with planted rows. The partial index is unchanged -- completed rows just leave it.

**Why:** a partial index cannot carry a time predicate (`now()` is not immutable), so the index can
only stay the race backstop if an ended row stops being 'active'. Lazy close over a cron because the
service is the only reader of experiments. `abandon` on a completed row is a 200 no-op (keeps the
readout) -- relabelling it "Abandoned" would hide a real result.

**How to apply:** `derive_phase('completed', ...)` is always ENDED; 'active' is still judged against
the clock as a fallback. Frontend `Experiment.status` is `"active" | "completed" | "abandoned"`; the
ended cell shows the readout AND a "Try this again for two weeks" button; `useStartExperiment`
invalidates the list on a 409 and `StartOffer` shows the message. The one test fixture pairing
status:"active" with phase:"ended" lived in SituationReportPage.test.tsx (situation-report's file,
one line changed). Related: [[pulse-cadence-rules]].
