---
name: default-pin-port-2026-10-05
description: assemble_training_data._resolve_pinned_submissions ported to the retake-era default pin (anchor on first current env report, fall forward past unreadable); label renamed first_core_sitting -> default_core_sitting; explain_user reads the service's _pinned_sitting
metadata:
  type: project
---

2026-10-05 (UNCOMMITTED at time of writing): the model lane's SQL restatement of the
D-15 pin now follows situation_report_service._default_pin / _pinned_sitting:
explicit override wins (never falls forward); else latest completed core sitting at or
before the user's FIRST current environment report (MIN(submitted_at), subject='current');
first sitting after it if all are newer; latest if no report; then fall forward to the
first sitting whose responses exist and that score_person scores without raising.
`_resolve_pinned_submissions(conn, user_ids, score_person=None)` takes the scorer;
`_default_pin_start` is the pure index rule. `PIN_FIRST_CORE="first_core_sitting"` became
`PIN_DEFAULT="default_core_sitting"` -- the VALUE changed because nothing stored carried the
old one (devfit reports fit_1/fit_2, run_fit, prereg do not name it). The two byte-identity
tests against historical commits (45de8b4, e8a9a72) now ignore `pin_source` and assert the
rename explicitly via `_assert_only_the_pin_label_was_renamed`.

**Why:** core became retakeable (6babb39); the old first-sitting default paired a report
with a sitting the user had replaced before filing. The service is the source of truth;
the tripwire test compares the SQL with `_pinned_submission_id` on 7 states + a fall-forward
test that patches `assessment_form.score_stored_choices` (both resolvers read it at call time).

**How to apply:** if the pin rule changes again, change the service first, then port here and
extend the tripwire; never fix the tripwire by loosening it. Fixture trap: the core form is
shuffled per user, so one answer pattern scores differently for two users. Stale prose left
for others: docs/ARCHITECTURE.md ~line 1117 still says "stays pinned to the first".
