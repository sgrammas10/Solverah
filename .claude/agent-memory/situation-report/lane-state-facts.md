---
name: lane-state-facts
description: Verified lane facts as of 2026-10-02 that contradict older memories/lane file (seam test, envQuestions mirror, subject migration status)
metadata:
  type: project
---

Verified in code 2026-10-02:

- The A-1/A-3 seam is guarded by a REAL end-to-end test now
  (`test_a3_scores_the_real_twelve_item_environment_bank_end_to_end` in
  tests/test_situation_items.py), not a tombstone. The lane file's "tombstone test" line is stale.
- `envQuestions.ts` is HAND-WRITTEN (no generator; header says checked 2026-09-11 and 2026-10-01).
  The user-level memory "A-7 ... envQuestions.ts is GENERATED" is wrong. Parity guard covers
  dimension items, all four context items (incl. industry values), form order and FORM_VERSION.
- Subject (current vs past) migration LANDED and is committed: `20261002_envreport_subject`
  (down_revision `20261001_envreport_industry`), commit d8406c2. FORM_VERSION was env-v2-2026-10-01;
  it is env-v3-2026-10-13 since C4 ([[c4-tolerance-and-outcomes-2026-10-13]]).
- The parity guard now also covers the five outcome items and the `kind: "outcome"` steps.
- The current-mode payload always carries all six dimensions (aligned rows included); only
  needs_forward drops aligned rows. So `dimensions: []` fixtures in current mode are impossible
  payloads — tests built on them can pass while the real all-aligned case renders wrong.

**Why:** older notes claimed otherwise; acting on them would misjudge what guards what.
**How to apply:** trust these over the lane file / global memory; re-verify if a later commit touches them.
See [[audit-2026-10-02-open-threads]].
