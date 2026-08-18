# Solverah — Session Handoff, 2026-08-18c

**Topic: hardened `-18b`'s item work. Added design rule 3 (presentation-order
randomization) after finding that the ladder design re-opens the same gameability hole
rule 2 had just closed — a difficulty-ordered ladder is transparent, so a respondent can
fake a high score and produce a perfectly Guttman-consistent answer set, which makes the
consistency-based confidence measure come out HIGH on the fake. Retired
`assessment_items.yaml` with machine-enforced refusal rather than a comment. Promoted the
one-off `check_items_v2.py` into `check_assessment_items.py` + a pytest wrapper, so the
structural check is a CI gate instead of something someone has to remember to run.**

Sits on top of `SOLVERAH_HANDOFF_2026-08-18b.md`. `anchors.json` untouched, still frozen at
`v1-frozen-2026-08-15`.

---

## 1. Design rule 3 — presentation-order randomization

**The hole.** A graduated ladder displayed in difficulty order is transparent. The four
rungs read visibly as "a little / somewhat / quite / extremely," so a respondent who wants
to look decisive does not have to guess which answers do it — they endorse further down the
list. The result is *perfectly Guttman-consistent*, so internal consistency — the planned
confidence measure — comes out **high** on the faked set, and the model weights it heavily
instead of leaning on the prior.

This is the same failure shape as `-18b` §1's positional straight-liner, arriving through
the ladder design rather than the key layout. Design rule 2 does not close it: balanced keys
say nothing about which item is shown first. Worth noting the ladder redesign *created* this
one — v1's flat-difficulty items were not fakeable this way, because there was no visible
gradient to climb. A fix that introduces a new failure mode is still the right fix, but it
has to be paid for.

**The mitigation.** Shuffle a dimension's four items before display, seeded stably per
respondent so a resumed session does not reshuffle. Scoring is unaffected — `mean_pole` is
order-invariant, and `difficulty_target` preserves the true rung order for analysis.

```yaml
presentation:
  randomize_item_order_within_dimension: true
  order_seed: respondent_id
  randomize_option_order: false
  never_display: [id, difficulty_target, pole, reverse_keyed, grading_variables]
```

`id` is in `never_display` for a non-obvious reason: the ids are sequential within a
dimension (`au1v2`…`au4v2`), so surfacing them re-leaks the order the shuffle just hid.

**Why option order is deliberately NOT randomized.** Three reasons, in order of weight:

1. Rule 2's 2/2 key balance already neutralizes positional bias, and does it
   deterministically rather than in expectation.
2. Probe files key their frozen choices by letter (`person_item_choices: {au1v2: A, …}`);
   per-respondent option shuffling makes every one of them unreproducible.
3. A stored response of "chose A" becomes ambiguous unless the shuffle is persisted
   alongside it — a live source of silent scoring corruption, for no gain over (1).

If it is ever done anyway, responses must be stored as the chosen **pole**, not the letter,
and every probe file needs reworking. The gate emits a warning if the flag is flipped.

## 2. `assessment_items.yaml` retired — enforced, not commented

Retired rather than deleted, because the frozen probe runs in `vignette_probes/results/`
were scored against these items and stop being reproducible if the file disappears.

`status: superseded` is now machine-enforced in three places:

- `check_assessment_items.py` refuses the file
- `test_assessment_items.py` **asserts that it is refused** — so if someone later removes
  the status key, a test fails rather than the file quietly becoming scoreable again
- `score_person_side.py` raises `SystemExit` on it; `--items` now defaults to the v2 file,
  and `--allow-superseded` is the explicit, labelled escape hatch for historical
  reproduction

Its header records both defects (positional key imbalance; flat difficulty) and, more
importantly, records that **no data remediation is required** — never piloted, no real
respondent data, the only `person_dimension_score` rows anywhere are synthetic fixtures in
`assemble_training_data.py` (hardcoded 0.5, `scoring_key_version='v1'`). Future rows must
carry `scoring_key_version` = the v2 `form_version`, which makes the two separable by
construction rather than by memory. That column already exists and is already plumbed
through `_fetch_person_scores()`; it just needs to actually be written.

`check_items_v2.py` moved to `v1_model/_to_delete/`.

## 3. The gate

`check_assessment_items.py` replaces the one-off. It takes paths (default: every
`assessment_items*.yaml` beside it), exits non-zero on failure, and is wired into pytest via
`test_assessment_items.py` — the repo already has `pytest.ini` and `causal_graph/conftest.py`,
so a bare `pytest` picks it up, as does `.github/workflows`.

Current state, run on the real repo:

```
assessment_items.yaml                    1 fail  0 warn   <- refused, as designed
assessment_items_v2_PROPOSED.yaml        0 fail  0 warn
3 passed in 0.20s
```

What it enforces: presentation contract present and not weakened; 4 items per dimension
(load-bearing — `mean_pole` over 4 reproduces `PERSON_LATTICE`); `difficulty_target` on every
item; strictly increasing 0.3/0.5/0.7/0.9 rungs; exactly one reverse-keyed item and it is the
hardest rung; 2/2 key balance; always-A and always-B both flat 0.50; Guttman prefix
endorsement reproduces `PERSON_LATTICE` exactly; six distinct grading variables; the
bias-review vocabulary sweep; option length ratio ≤ 2.0 (warn).

**The general point, which is the reusable part.** Both defects caught this week were
structural, and both survived a careful human read of the item *text* — because they live in
the file's *shape*, not its wording. Content review and structural check are complements,
and only one of them can be automated. This is the same argument
`SOLVERAH_HANDOFF_2026-08-18.md` §7 makes about seeds: a check that has to be remembered is
not a check.

**Honest limit:** the gate catches the classes I thought to enumerate. It says nothing about
whether the instrument measures anything, and passing it is not evidence the ladder works —
only a pilot is that.

---

## Open / next

1. **Ratify or redline `assessment_items_v2_PROPOSED.yaml`.** Unchanged from `-18b` and
   still gating everything downstream. On ratification, flip `status: proposed` →
   `active`, and rename off the `_PROPOSED` suffix.
2. **Implement the presentation shuffle in the actual form renderer.** New. The contract is
   declared in the YAML and enforced against the YAML, but nothing consumes it yet — no
   person-side form UI exists in the repo that reads `presentation:`. Until something does,
   rule 3 is a specification, not a protection.
3. **Write probe pair files for the five new ladders.** The real cost of `-18b`. Consider
   reusing the already-scored company vignettes per band the way v3 did, which would cut
   live API calls to uncovered bands only.
4. **Then run the calibration probe on decision and feedback** — still untested in every
   round to date. Multi-seed per §7.
5. **Notify George / RATER_B.** Still five minutes, still blocking items 6–7, now carried
   into a third message today.
6. **Hand `anchors_v3_PROPOSED.json` to Julie** — gated on raters returning P-01–P-06.
7. **Feedback anchor check vs. raters' Agreement tab** — same block.
8. **Decide whether to instrument the pilot for person-side dimension correlation.** More
   worth doing after `-18b` §2: distinct grading variables mean a measured correlation is now
   interpretable as a real trait relationship rather than an instrument artifact.
9. `pace → autonomy` and `pace → feedback` still unexamined category-3 candidates.
10. Carried: `au3v2` dimension leak; `build_model.py` still has no `OrderedLogistic` path for
    `experienced` outcomes; `schema.sql` never migrated into the app database;
    `Solverah_Ground_Truth_Roster_v2.md` still missing.
11. **Standing, unchanged: anonymization does not prevent re-identification for 5 of 6
    companies.** Fifth session.
