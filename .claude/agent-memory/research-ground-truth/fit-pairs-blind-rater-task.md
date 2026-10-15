---
name: fit-pairs-blind-rater-task
description: C10 blind-rater fit task in Solverah_IP/ground_truth/fit_pairs/ -- 10 blocks x 5 pairs + 4 repeats; Amendment 1 (2026-10-14) made Sebastian (D) eligible with an excluding-D twin report that governs
metadata:
  type: project
---

Built 2026-10-13/14 (lane C10), committed in 147ee1d. PRODUCT_DECISIONS section 2 step (3): raters
who did not set the weights judge person/company fit; compared with the model's within-person order.
Prereg `PREREG_FIT_PAIRS_2026-10-13.md`; changes go in as dated amendments appended under Addenda.

**Amendment 1 (2026-10-14, uncommitted at time of writing):** ruling "weights are Julie's alone"
(PRODUCT_DECISIONS six-trait entry, Follow-up rulings). Only A is refused (sets_weights). D is
eligible with roster flag `knows_model_design`; `analyse_twin` runs everything twice (all /
excluding D) and **excluding-D governs** on any disagreement (gate, band, each K, overall).
E and F are unnamed reserved slots; the builder refuses an unnamed slot. D's page is at
`out/fit_pairs_raterD.html` (untracked). Recruit cover note: `RECRUIT_NOTE.txt` (tested: plain, blind).

**The trap to keep surfacing:** MIN_RATERS = 3 is unchanged, so with D + 2 recruits the governing
(excluding-D) verdict is DESCRIPTIVE ONLY. A real verdict needs 3 counted raters besides D. The
power sim shows R=2 behaves almost like R=3, so lowering the floor is defensible, but that is
Sebastian's call and must be a second amendment BEFORE any return is read.
**Why:** a design-aware rater biases toward "defaults stand", hence excluding-D governs.

**Design facts:** block order B1,B9,B2,B10,B3..B8; repeats byte-identical (consistency is an upper
bound); thresholds gate 0.40, stand >=0.50, review <0.20; contrasts K1-K11; model z ties kept as
ties (never rank_in_block). DESCRIPTIVE ONLY now prints numbers under numbers["descriptive"].
test_fit_page.cjs hardcodes rater Z: on D's page 3 checks fail by design (id, download filenames).

**Hand-off:** matching-model scores `pair_specs.json` into `pair_model_scores.json` (spec sha
5ad05452..., unchanged by Amendment 1). We never compute rankings.

**How to apply:** after any design.py change: `python design.py`, rebuild the Z test page,
re-run test_fit_page.cjs (pass a scratchpad PAYLOAD_OUT unless you mean to refresh the fixture),
then pytest. node is at %APPDATA%/fnm/node-versions/v22.13.1/installation/node.exe.
Related: [[companylens-production-coupling]], [[match-model-alignment-response]].
