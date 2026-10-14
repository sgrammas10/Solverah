---
name: focustype-scene-defects-2026-10-02
description: FocusType after the 2026-10-02 fix wave -- what was fixed, and the two items still open (3000ms rule unreachable = Julie's call; FOCUSTYPE_SPEC.md missing)
metadata:
  type: project
---

Fixed in the 2026-10-02 fix wave (uncommitted at time of writing): Scene 4 sends `avg_decision_time_ms: null` when every card times out and score.py treats null/absent as no timing signal; Scenes 1/2/5 use Mouse+Touch(200ms hold)+Keyboard sensors; malformed scene bodies are a 400; draft key is `focus_type_draft:<user id>`; the retake flag is stripped from router state; success navigates with `replace`. Scene1/2/4/5 now have tests (`focustype/*.test.tsx`, helpers in `dndTestUtils.ts`).

Deliberate deviation: draggables carry `touch-action: manipulation`, NOT `none`. The orchestrator brief asked for `none`, but with TouchSensor's press-and-hold that would stop the page (and Scene 5's timeline) scrolling under a finger. Do not "fix" it back to `none` without re-reading `focustype/dragSensors.ts`.

Still open:
- The `>= 3000 -> deep_focus +1` rule cannot fire: clicks land before the 3000ms timeout and timeouts are now excluded. What timing should mean is Julie's call; thresholds unchanged by ruling of the brief.
- FOCUSTYPE_SPEC.md, which score.py cites as its source of rules, is not in the repo.
- Not device-tested on a real phone; jsdom tests prove sensor wiring only.

**Why:** the Julie content day needs FocusType's thresholds to be trustworthy.

**How to apply:** delete this entry once Julie rules on timing and the spec question is closed.
