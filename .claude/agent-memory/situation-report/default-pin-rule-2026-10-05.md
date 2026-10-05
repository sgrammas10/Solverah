---
name: default-pin-rule-2026-10-05
description: The Situation Report's default D-15 pin since core retakes (2026-10-05) - anchored on the FIRST current env report, falls forward past unreadable; explicit pins never fall forward
metadata:
  type: project
---

Default pin (no explicit recalibrate row), built 2026-10-05 and uncommitted at the time:
the latest completed core sitting at or before the user's FIRST current Environment
Report (`environment_report_store.first_environment_report_submitted_at`). If none is at
or before it, the first sitting after it. With no env report, the latest sitting (only
recalibrate reads it then). A single sitting short-circuits, so there is no env read and
no change for one-sitting users. Then FALL-FORWARD: if that sitting is unreadable
(`dimension_scores_for_submission` returns None), use the first readable sitting after
it. An explicit pin never falls forward. It still gates with `core_unreadable`, and
recalibrate is its exit. Candidates come from `assessment_store.completed_core_sittings`.
That helper is not filtered by scoring-key version: the rule is about time, and
readability is checked per candidate.

**Why:** the pin protects a report the user has SEEN. The old "first sitting" default
built the report from a replaced sitting when the user retook before filing. An
unreadable default shows no person side at all, so it protects nothing. Anchoring on the
FIRST report rather than the latest keeps a re-filed env report from re-anchoring the
person side.

**How to apply:** `causal_graph/v1_model/assemble_training_data._resolve_pinned_submissions`
restates the rule in SQL and is matching-model's code. Its tripwire
(`test_pin_resolution_agrees_with_the_situation_report_service`) fails until that lane
ports the rule. `devfit/explain_user.py` still reads `first_completed_core_submission_id`.
Fixture trap: the core form is shuffled per user, so one answer pattern scores
differently for two users. Never compare reports across users. See
[[audit-2026-10-02-open-threads]].
