---
name: pulse-cadence-rules
description: Since 2026-10-02 pulse_settings.is_due runs the clock from the LATER of last_prompted_at and the last check-in, and counts the interval in UTC calendar days (not seconds); why, and the test fixtures that depend on it
metadata:
  type: project
---

Two cadence changes landed in the 2026-10-02 fix wave (F4, F5), both in `pulse_settings.is_due`:

- **Anchor = max(last_prompted_at, last_checkin_at).** Before, once a user had ever been prompted the
  clock ran from the prompt alone, so a voluntary check-in three days ago still earned a "time to
  check in" email. `send_due_prompts` already passes `last_checkin_at` for every candidate.
- **Interval counted in UTC calendar days** (`(now.date() - last.date()).days >= interval.days`).
  Before, `now - last >= 7 days` lost the coin flip whenever the daily cron's clock ran a hair early,
  and the weekly prompt drifted to day 8. Day 7 is now due whatever the time of day either side.

**Why:** both were audit findings; neither needed a product ruling (the cadence vocabulary and the
anti-nag drop are untouched).

**How to apply:** any `test_pulse_cadence_cli.py` fixture that expects a user to be due "by prompt
age" must seed its check-in OLD (`_seed_checkin(user_id, taken_at=_ago_dt(days=60))`) -- a check-in
seeded at "now" defers the prompt, which is the point of F4. Related:
[[experiment-ended-stays-active]], [[pulse-cron-status]].
