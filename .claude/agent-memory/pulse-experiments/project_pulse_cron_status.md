---
name: pulse-cron-status
description: flask pulse send-prompts cron was created in the Render dashboard at deploy 2 (2026-09-14) but is NOT in render.yaml; whether it has ever sent is unverified
metadata:
  type: project
---

Per the user-level deploy memories, deploy 2 (PR #152, 2026-09-14) created the backups AND pulse
crons in the Render dashboard; APP_BASE_URL=https://solverah.com is set in the solverah-prod group.
As of 2026-10-02 render.yaml still has no pulse cron block (G18 / S23.4 codification gap), and nobody
has recorded a run log showing `{"event": "pulse_send_prompts", "sent": N}` with N > 0.

**Why:** without the cron no prompt ever sends, silently; render.yaml is doc-only until Blueprint
adoption, so the dashboard is the source of truth.

**How to apply:** "is the pulse cron live" = ask Sebastian to check the Render dashboard run log
(schedule + last run). Adding the render.yaml block is ops-crons' lane, not ours. Related:
[[experiment-ended-stays-active]].
