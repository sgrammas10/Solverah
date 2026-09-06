# Solverah — Session Handoff, 2026-08-18c

Sits on top of `SOLVERAH_HANDOFF_2026-08-18b.md` (item ratification). This session did four
things in order: made design rule 3 real, wrote and verified probe files for all six ladders,
closed the employer-visibility question, and added design rule 7. `assessment_items_v2.yaml`
is `status: active` with rules 1-7 now enforced by `check_assessment_items.py`. `anchors.json`
untouched, still frozen at `v1-frozen-2026-08-15`.

---

## 1. `present_items.py` — design rule 3 is now enforced in code, not just in the YAML

Rule 3 (per-dimension item shuffle, seeded per respondent) has been a specification since
`-18b` — declared in the YAML and checked *against* the YAML by the gate, but nothing in the
repo consumed it. `present_items.py` is the consumer. Three decisions, each a correctness
requirement rather than a style choice:

- **Ordering is server-authoritative.** The client never shuffles. A Python scorer and a
  TypeScript frontend independently computing the same order would have to agree bit-for-bit
  forever across two languages' PRNGs; a divergence there is silent and corrupts a resumed
  session's ordering instead of erroring. There is deliberately no TS shuffle helper.
- **Items are addressed by opaque per-respondent tokens**, not item id — closing a gap in the
  rule 3 contract itself. `never_display` lists `id` because ids are sequential
  (`au1v2`..`au4v2`) and would re-leak the rung order; but a form has to round-trip an answer
  to its item, and posting back `{"au3v2": "A"}` would put the id in the DOM anyway. Tokens are
  `HMAC(respondent_id, item_id)` under `SOLVERAH_FORM_TOKEN_SECRET` — stable across a resumed
  session, unordered, not invertible by the client. **No default fallback for the secret, by
  design** — a hardcoded one would make tokens forgeable.
- **Option order stays fixed**, per rule 3's own reasoning (2/2 key balance already
  neutralizes positional bias deterministically; probe files key choices by letter; a stored
  "chose A" is ambiguous without the shuffle persisted alongside it). The module raises if
  `randomize_option_order` is ever flipped true rather than silently honoring it.

**Every weakening of the contract raises rather than degrading to a safe default** — a form
that silently renders unshuffled produces data that looks fine and isn't.

`test_present_items.py`, 21 tests at this point (32 after rule 7, see §4). The two worth
naming: **uniformity** — 2000 simulated forms checked against a 4σ binomial bound, because a
shuffle that is deterministic and stable but *biased* (rung 1 landing in position 0 more often
than chance) passes every other test while partially re-exposing the ladder, invisibly, until
checked across a population. **Order-invariance of scoring** — asserted, not assumed, because
that invariance is *why* shuffling is safe at all; if a future scoring change made order
matter, the shuffle would start silently changing scores instead of erroring.

**Bug fixed in the same pass, not part of rule 3:** `score_person_side.py --items` defaulted to
`assessment_items_v2_PROPOSED.yaml`, which `-18b` moved to `_to_delete/`. Anyone running the
default would have hit `FileNotFoundError`. Now defaults to `assessment_items_v2.yaml`.

**Not done, and flagged rather than silently skipped:** the React form UI itself. This module
is the correctness layer — a route, a component, session storage for the token map, and a
submit path through `resolve_responses` into `score_person_side` are still needed. Also not
done: the design rule 5 gate got extended for D2 in `-18b`, but per-dimension length balance
was never re-verified after rule 7's payload change — it doesn't need to be, since interleaving
doesn't touch item text, but noting it in case that assumption is ever revisited.

## 2. Probe pair files written and verified for all six ladders

Six files: `vignette_probe_pairs_v3_autonomy_ladder.yaml` (revised, see below),
`_v8_pace_ladder.yaml`, `_v9_collaboration_ladder.yaml`, `_v10_innovation_ladder.yaml`,
`_v11_feedback_ladder.yaml`, `_v12_decision_ladder.yaml`. All 30 pairs' person-side scores
verified by `score_person_side.py` against `assessment_items_v2.yaml` — pure arithmetic, zero
API spend, all reproduce their frozen `target_person`.

**Company-side coverage: 17 of 30 vignettes reused from cache, 13 need a live run.**

| dimension | cached | new |
|---|---|---|
| autonomy | 5 | 0 |
| pace | 4 | 1 (band 0.3) |
| collaboration | 4 | 1 (band 0.3) |
| innovation | 4 | 1 (band 0.3) |
| feedback | 0 | 5 (never probed) |
| decision | 0 | 5 (never probed) |

13 vignettes × 5 runs (locked mean-of-5) = **65 live calls**, vs. 150 with no reuse.

### Three corrections to `-18b`'s autonomy claims — two were wrong

`-18b` asserted the autonomy 0.3 band still needed a live call, that all five cached autonomy
levels were invalidated by ratification, and that autonomy had "no empirical support." Checked
this session and corrected in the revised v3 file:

- **Wrong.** The 0.3 band was already run — company-side n=15, sd 0.0, across three separate
  result CSVs. No outstanding autonomy call exists.
- **Wrong.** Only `company_vignette` is ever sent to the scorer
  (`run_vignette_probe.py:~211`); `person_vignette` is documentation nothing reads. Company
  vignettes didn't change during ratification, and every item kept its A/B pole assignment, so
  every cached result and every `person_item_choices` mapping is still valid untouched.
- **Overstated.** Autonomy's *company-side* precision is measured at all five bands with zero
  variance. What it lacks — like every dimension — is evidence that real respondents follow the
  difficulty ordering, which was true before ratification too.

What actually needed fixing: the `person_vignette` *prose*, because it paraphrases item wording
and `au3v2` was rewritten under D4. Rewritten throughout the v3 file to match.

### Feedback: construct mismatch found while writing the file, recorded rather than worked around

`anchors.json` (frozen) grades feedback on frequency and directness — its 0.9 band literally
says "constant unfiltered input." The v2 item rewrite moved the person-side axis to **exposure**
(privacy and delay) specifically because bias-review finding 3 showed bluntness language
carried valence rather than trait; `check_assessment_items.py` now *bans* the word
"unfiltered" in item text. The two sides now share only timing; company grades bluntness with
no person-side counterpart, person grades audience with no company-side counterpart.

The company vignettes in `v11_feedback_ladder.yaml` are written on the shared timing axis only,
to keep the probe interpretable, but that makes it exercise a **narrower construct than either
artifact defines**. Flagged explicitly in the file: **a poor gap result on feedback is not
evidence the ladder failed** — it's equally consistent with the two sides measuring different
things. The real fix is a rubric change, meaning `anchors_v3_PROPOSED.json`, which is stalled
behind raters. This is now the largest item on the carried list (see Open §5).

Decision has a milder version of the same issue — anchors say "founder gut," items deliberately
don't say "gut" (banned by the gate) — but it's a framing difference, not an axis difference, so
results there stay interpretable.

## 3. Employer-visibility question answered — closes the last open funnel item

**Decision: employers never see an individual's answers or six dimension scores.** Scoped as a
**durable data commitment**, not a true-for-now statement — deliberately written to hold even
after employers eventually join the platform. If an employer ever sees anything, it's a match
result, never the underlying scores.

**Context that shaped the scoping, not just the answer:** there are no employers on the
platform for the first several launch iterations — credibility gets built first — so the
company side of an early match is the generated company-profile database, not signed-up
employers. That's exactly why the commitment was scoped durably *now*: a promise about a party
that doesn't exist yet is the easiest kind to make and the hardest to unwind once users have
already answered under it.

**Honest limit, written into the YAML rather than left implicit:** in a hiring context, "no
employer sees this" removes the incentive to soften. Here it removes much less, because the
pressure was never toward an employer — it's toward the *matching algorithm*. A self-profiling
user wants to be matched to companies they find impressive, and privacy doesn't touch that at
all. **Rule 3's shuffle remains the primary defense**; the disclosure line should not be
mistaken for a mitigation of aspirational answering.

**Enforcement flagged as a build item, not left as policy prose:** `person_dimension_score`
must be unreachable from any employer-facing endpoint, enforced in the data layer as a CI test
— same argument as rule 3, which sat unconsumed until this session.

**Form copy drafted** (short and long versions) framed on self-interest in accuracy rather than
on privacy — "describing yourself as someone you're not doesn't cost you privacy, it costs you
the match" — since that's the framing that actually counters aspirational answering. Not yet
placed in a component; the form UI doesn't exist yet (§1).

**Consequence for the deferred 65 calls (open item, see §5):** with no employer pulling a launch
date forward, there's no urgency argument for running feedback/decision before `anchors_v3`
lands. Decided this session to defer.

## 4. Design rule 7 added — cross-dimension interleaving

Rule 3 hides the *rung order* within a dimension. It does not hide the *grouping*: shown as six
blocks of four, a respondent can see which four items measure one thing. That interacts with
the same failure family as rules 2 and 3 — a respondent who notices the grouping has a pull
toward answering it "consistently" as self-presentation rather than reporting four independent
preferences, which inflates the internal-consistency confidence measure on a *less* accurate
profile.

**Scheme: 4 blocks of 6, one item per dimension per block.** Rule 3's existing per-dimension
permutation now decides which block a given rung lands in (block *b* takes position *b* of that
dimension's shuffle, so rung-order hiding is unchanged); the order of the six dimensions
*within* a block is shuffled independently per block. No two same-dimension items are ever
adjacent, in exchange for the payload shape changing from six `dimensions` groups to a flat
`blocks` list. `dimension` joined `never_display` — grouping revealed it before; leaving the
field now would hand back exactly what the interleave removes. Decided and built *before* the
form UI exists, deliberately — after it ships this becomes a payload contract change instead of
an edit.

**Bug found and fixed in the same pass: the block-seam adjacency case.** Shuffling each block
independently is not sufficient — a block can end on `feedback` and the next begin on
`feedback`, putting two same-dimension items adjacent across the seam. Every per-block
correctness check passes; only a check that scans the *flattened* form catches it. Caught by
`test_no_two_adjacent_items_share_a_dimension` failing on a live seed (`r3`), not by
inspection. Fixed with a deterministic single-swap repair: since every dimension appears
exactly once per block, only the block's first item can collide with the previous block's last
item, so index 1 can never collide — one conditional swap always fixes it and can't introduce a
new collision.

**One test of mine was wrong, not the code — worth recording the shape of the mistake.**
Asserted no dimension *name* string appears anywhere in the serialized payload; failed because
`de4v2`'s prompt legitimately contains "the decisions that frustrated you." Dimension names are
ordinary English words. Removed the over-strict assertion rather than fixing the payload — the
actual requirement (the `dimension` *field* is absent) was already covered elsewhere.

`test_present_items.py` now 32 tests. `check_assessment_items.py` extended to fail on
`interleave_dimensions` not true or `block_count` != 4.

## 5. I-O psychology review — scoped and drafted, not sent

`IO_REVIEW_BRIEF.md` written to `Solverah_IP`. Deliberately narrow: two questions, not a review
of the 24 items or six constructs.

1. **Can four binary forced-choice items give usable reliability?** This is the one that
   matters most because it's load-bearing — `mean_pole` over exactly four items produces the
   five-point lattice the whole downstream Bayesian model is built on. Five items would
   silently invalidate that constant. "Add more items" isn't a cheap fix here; it's a
   re-architecture, so the brief asks for this answered plainly and early if it's bad.
2. **Is Guttman difficulty ordering defensible for preference items rather than ability items?**
   An ability ladder is unidimensional by construction; a preference ladder rests on the
   designer's claim that the rungs are ordered on one variable. The feedback two-factor problem
   (§2) goes in as a concrete sub-question a reviewer can actually rule on.

Brief states explicitly what is *not* being asked — item wording, dimension choice, whether
real respondents follow the ordering — so review isn't paid for twice or substituted for the
pilot. Not yet sent to anyone.

---

## Open / next

### 1. Build the form UI ← the actual launch blocker

`present_items.py` is the correctness layer; nothing renders it yet. Needs: a route serving
`build_form`'s payload, a React component that walks `blocks` (not `dimensions`), session
storage for the token map, a submit path through `resolve_responses` into
`score_person_side.score_choices`, and `SOLVERAH_FORM_TOKEN_SECRET` provisioned in the
environment — no default exists by design.

### 2. Enforce the employer-visibility commitment in the data layer

Currently a decision and a form-copy draft, not code. `person_dimension_score` needs to be
unreachable from any employer-facing endpoint, as a CI test rather than a policy someone has to
remember. Same shape of gap as rule 3 had until this session.

### 3. Send the I-O review brief, or decide against it

Drafted, scoped, sitting in `Solverah_IP`. No blocker left on sending it.

### 4. Feedback construct mismatch — needs `anchors_v3`, which needs raters

§2. The largest carried item from this session. Company-side feedback probing should not run
until this is resolved, which folds into the existing decision to defer the 65 calls.

### 5. The 65 company calls — deferred, not cancelled

Decided this session to wait for `anchors_v3_PROPOSED.json` rather than spend 65 calls against
a rubric that's queued for replacement, especially since feedback's 25 of those 65 aren't
cleanly interpretable yet regardless (§2). No employer-driven launch date is pulling this
forward (§3), which was the deciding factor. Revisit once `anchors_v3` lands or is definitively
stalled.

### 6. Decide the seeds-rule enforcement mechanism

Discussed, not yet decided at end of session: write the ≥3-seeds-and-paired rule down as
prose (again — it's already been written down twice and violated three times), or build a
small helper that any analysis script must call to emit a comparison, which refuses without
seed count and paired-design metadata stated. Leaning toward the enforced version, on the same
logic as rule 3 and rule 7: a check that has to be remembered is not a check.

### Ready to build once §1 exists

7. Wire `present_items` + `score_person_side` into the actual Flask/React app.
8. Run the 13 new company vignettes (65 calls) — blocked on item 5's resolution, not on
   readiness; the files are written and person-side verified.
9. Calibration probe on decision and feedback, multi-seed — same block.
10. `OrderedLogistic` path in `build_model.py` for `experienced` outcomes.
11. Migrate `schema.sql`.
12. Populate `scoring_key_version` for real — overdue since v2 went active.

### Decisions, not work

13. Instrument the pilot for person-side dimension correlation (`-17d` §4 finding 3).
14. Instrument the pilot for design rule 6's pre-registered feedback prediction — must be set
    up before data arrives or the pre-registration is worthless.
15. `pace → autonomy` and `pace → feedback` — unexamined category-3 candidates, six sessions.

### Blocked on people

16. **Notify George / RATER_B.** Five minutes. Now the root of the longest dependency chain in
    the project — it blocks Julie, which blocks `anchors_v3`, which blocks a clean feedback
    probe (§2, §5). Carried across many sessions, raised repeatedly without action.
17. Hand `anchors_v3_PROPOSED.json` to Julie — gated on 16.
18. Feedback anchor check vs. the raters' Agreement tab — same block.
19. `Solverah_Ground_Truth_Roster_v2.md` still missing.

### Carried

20. Rung-4 prompt convergence — two collisions caught and fixed during `-18b`'s ratification.
    Candidate for an eighth gate rule if a future edit reintroduces one.
21. `co3v2` "in the room" assumes co-location — considered during ratification, not changed.
22. `pa1v2` simultaneity-vs-tempo confound — accepted as minor.
23. Stray `SOLVERAH_HANDOFF.md` in `Solverah/causal_graph/v1_model/`.
24. Test 1 identified-condition re-check.

### Standing

25. **Anonymization does not prevent re-identification for 5 of 6 companies.** Seventh session
    carrying this unchanged. Two lawyers and Julie are holding packets described to them as
    anonymized, and that description is not currently backed. One email. It has now outlasted
    the complete redesign, ratification, *and* presentation-layer implementation of the
    person-side instrument.
