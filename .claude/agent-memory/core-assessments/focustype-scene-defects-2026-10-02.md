---
name: focustype-scene-defects-2026-10-02
description: Open FocusType defects found 2026-10-02 -- Scene 4 timing rules inverted/unreachable, drag scenes have no touch-action or keyboard sensor, scenes untested
metadata:
  type: project
---

Open as of 2026-10-02 (audit only, nothing fixed):
- Scene4 sends `avg_decision_time_ms: 0` when every card times out. `score.py` reads `< 1500` as a fast decider, so a user who never clicked gets reactivity +1. The `>= 3000 -> deep_focus +1` rule cannot fire, because TIMER_MS is 3000 and a click must land before the timeout.
- Scene1/2/5 use dnd-kit PointerSensor and set no `touch-action: none`. Scene2/5 have no KeyboardSensor. They are likely broken on phones (inferred, not device-tested) and confirmed keyboard-inaccessible.
- FocusTypePage.test mocks every Scene, and no Scene*.test exists.
- A malformed scene body that passes validation (e.g. `scene_2.now: 5`) causes a 500 in score.py.
- FOCUSTYPE_SPEC.md, which score.py cites as the source of its rules, is not in the repo.

**Why:** the Julie content day needs FocusType's thresholds to be trustworthy. What a timed-out card should score is expert judgment, so it is Julie's call.

**How to apply:** delete this entry once each item is fixed or ruled on.
