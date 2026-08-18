# Solverah — Session Handoff, 2026-08-18b

**Topic: closed `-17d` item 2 / today's board item 1 — extended the graduated-difficulty
ladder from autonomy to all six dimensions, with the `ASSESSMENT_ITEMS_BIAS_REVIEW.md`
fixes bundled in rather than applied as a separate pass. Output is
`assessment_items_v2_PROPOSED.yaml` (24 items, all six dimensions), a structural checker
`check_items_v2.py` (0 fails, 0 warns), and a remapped
`vignette_probe_pairs_v3_autonomy_ladder.yaml`. One new defect was found that the bias
review missed and that would have survived into the pilot: option key positions are not
balanced, so a respondent who just picks the first option throughout scores 1.0 on three
dimensions and 0.0 on a fourth, with perfect internal consistency. Custom instruction
honored: the decision-dimension rewrite deliberately departs from the bias review's own
recommended fix, with the reason stated.**

Sits on top of `SOLVERAH_HANDOFF_2026-08-18.md` (the multi-seed retraction).
`assessment_items.yaml` was **not** modified — this is a proposal file, same convention as
`anchors_v3_PROPOSED.json`. `anchors.json` untouched, still frozen at `v1-frozen-2026-08-15`.

---

## 1. New defect — positional response bias, unguarded on four of six dimensions

Not in `ASSESSMENT_ITEMS_BIAS_REVIEW.md`, which checked semantic framing (which option
*reads* as the desirable one) but not which letter the high pole sits on. In
`assessment_items.yaml`:

| dimension | A = high pole on | effect of always picking A |
|---|---|---|
| autonomy | 4 of 4 | scores **1.00** |
| pace | 4 of 4 | scores **1.00** |
| feedback | 4 of 4 | scores **1.00** |
| decision | 0 of 4 | scores **0.00** |
| collaboration | 1 of 4 | 0.25 |
| innovation | 1 of 4 | 0.25 |

`autonomy_items_v2_POC.yaml` inherits it — A is the high pole on all four rungs.

Why this matters more than it looks: the planned confidence measure is *internal
consistency of the items*. A positional straight-liner is perfectly consistent, so
confidence comes out **high** on a fabricated profile that is maximally extreme on three
dimensions at once. The model would then weight that profile heavily rather than leaning
on its prior — the precise inverse of the intended behavior. And it would be invisible in
pilot data, reading as a genuine population of decisive, fast-paced, feedback-hungry
respondents.

**Fix applied throughout v2:** every dimension is exactly two A=high and two B=high.
Always-A and always-B now both produce `[0.5, 0.5, 0.5, 0.5, 0.5, 0.5]`. That is both
harmless (midpoint, not extreme) and detectable — a flat 0.50 across all six at once is a
straight-lining signature. It is **not proof**: a genuinely middling respondent produces
the identical vector, so it should raise a review flag, never an auto-reject.

## 2. Design rule that drove the rest — one grading variable per dimension

A ladder needs something that gets harder as you climb. Autonomy uses stakes/scope. The
tempting move is to reuse stakes everywhere; that would be a mistake. A risk-tolerant
respondent would then climb higher on *every* ladder, and the instrument would manufacture
person-side cross-dimension correlation out of its own construction — indistinguishable in
pilot data from the real trait correlation `-17d` §4 finding 3 wants to measure.

| dimension | grading variable |
|---|---|
| autonomy | stakes / scope / expected check-in frequency *(unchanged)* |
| pace | duration the tempo must be sustained |
| collaboration | coordination cost in the respondent's own working time |
| feedback | exposure — privacy and delay |
| innovation | sunk investment discarded |
| decision | novelty — how unprecedented the situation is |

Six distinct, deliberately non-nested. If two correlate in pilot data, that is a finding
about people rather than an artifact of this file.

## 3. Bias-review findings, closed

- **Finding 1 (no reverse-keyed items on feedback or decision).** Closed. Rung 4 is
  reverse-keyed in all six dimensions now, `fb4v2` and `de4v2` included.
- **Finding 2 (decision skews to the data pole on all four items).** Closed by full
  rewrite — see §4, which departs from the review's own proposal.
- **Finding 3 (`pa2` "quality bar", `fb3` valence, `in1` prestige).** Closed structurally
  rather than by rewording. `pa2v2` drops all quality language (the trade is now tempo
  against sustainability). `fb3v2` grades by exposure rather than bluntness, so the axis is
  *when and in front of whom*, not *how harsh* — the valence asymmetry the review found had
  nowhere to attach. `in1v2`–`in4v2` grade by sunk investment, so as the ladder climbs the
  high pole stops meaning "create" and starts meaning "discard working value," which is not
  self-evidently the impressive choice; at rung 4 it is explicitly wasteful. The review said
  `in1`'s skew was near-inherent to the construct and hard to reword away — agreed, which is
  why this is a structural answer. **If innovation still leans in a pilot after this, the
  construct is the problem, not the items, and that is worth knowing.**
- **Finding 3 secondary (`de3` was the only quoted-dialogue item).** Closed; everything is
  a behavioral scenario now.
- **Finding 4 (`au3`, `pa2` leak into a second dimension).** `pa2`'s leak is gone — it
  bundled pace with a quality-vs-speed values question and the quality side no longer
  exists. `au3v2` is carried over verbatim and still plausibly taps risk tolerance; left
  alone deliberately, because autonomy is the one ladder with a probe behind it and
  rewording it would throw that away. **Still open, still worth watching in pilot data.**

## 4. Decision dimension — departing from the bias review's recommended fix

The review proposed reframing decision around *speed vs. information-sufficiency*
("decide today on what you know" / "wait a day and be sure"). Rejected, and it is worth
being explicit about why, because the review is otherwise being followed closely:
speed-vs-sufficiency grades by cost-of-being-wrong, which **is** stakes, which **is**
autonomy's grading variable. Adopting it would have violated §2 on the one dimension where
the review's own finding 4 already flags a confound risk.

Chosen instead: **both poles are a kind of evidence.** The low pole is no longer "gut" or
"judgment" — it is pattern-recognition from having seen the situation before, which is a
real and defensible basis for a call. The high pole is explicit measurement. Neither option
is "deciding without information," which is what made the v1 wording indefensible. The
ladder climbs by novelty: as the situation gets more unprecedented, accumulated
pattern-recognition gets objectively weaker, so continuing to rely on it says something
progressively more distinctive about the respondent.

## 5. Verification — what was actually checked

`check_items_v2.py`, **0 fails / 0 warns**. It caught three key-balance errors in my own
first draft (pace, innovation and decision were 3/1, 1/3 and 3/1), which is the argument
for having written it before eyeballing the file.

- 4 items per dimension — **load-bearing**, not stylistic: `mean_pole` over 4 items yields
  exactly `{0, 0.25, 0.5, 0.75, 1.0}`, which is `build_model.py`'s `PERSON_LATTICE`. Five
  items would silently invalidate that constant and every lattice result in
  `SOLVERAH_HANDOFF_2026-08-18.md`. Do not "just add one more."
- Difficulty targets strictly increasing, exactly the 0.3/0.5/0.7/0.9 rungs
- Exactly one reverse-keyed item per dimension, and it is the hardest rung
- Key balance 2/2; always-A and always-B both give a flat 0.50 vector
- Guttman prefix-endorsement reproduces `PERSON_LATTICE` exactly, all six dimensions
- All six grading variables distinct
- Flagged-vocabulary sweep: none of `"quality bar"`, `"unfiltered"`, `"trusted you"`,
  `"gut"`, `"evidence and analysis"`, `"judgment and experience"` survive into v2
- Option length ratios all ≤ 2.0 (worst: `au2v2` at exactly 2.00, carried over verbatim
  from the POC — flagging it, not changing it, for the same reason as `au3v2`)

**Probe remap verified separately:** all five cached levels in
`vignette_probe_pairs_v3_autonomy_ladder.yaml` still reproduce their `target_person`
(0.0 / 0.25 / 0.5 / 0.75 / 1.0) under the new key positions. Autonomy item *text* is
unchanged — only `au2v2` and `au4v2`'s option order — so the cached company-side results
stay valid and **no API re-run is needed** for the 0.1/0.5/0.7/0.9 bands. The 0.3 band
still needs its one live call, exactly as before.

## 6. What this does NOT establish

- **Nothing here is empirically validated.** Same limitation the POC carried and stated:
  no real respondent data exists, so nothing demonstrates that real people's answer
  patterns follow the difficulty ordering. Face-valid design only.
- **Five of six ladders have no probe pair file at all.** Autonomy has v3; pace,
  collaboration, feedback, innovation and decision have none. Writing them means five
  levels of person vignette *and* company vignette each — that is the next substantial
  chunk of work, and it is what board item 3 (the calibration probe on decision and
  feedback) is actually blocked on.
- **The probes need live API access**, which the Claude sandbox cannot reach. Those runs
  happen locally.
- Per `SOLVERAH_HANDOFF_2026-08-18.md` §7, no number from a single probe run enters a
  handoff doc as a result.

---

## Open / next

1. **Ratify or redline `assessment_items_v2_PROPOSED.yaml`.** Nothing downstream should
   move until the item text is signed off — the probe pair files in item 2 encode the item
   wording into vignettes, so writing them against unratified items risks doing it twice.
2. **Write probe pair files for the five new ladders.** The real cost of this session's
   output. Consider whether the company-side vignettes from `vignette_probe_pairs_v1.yaml`
   and `_v2_boundary.yaml` can be reused per-band the way v3 reused autonomy's, which would
   cut the live API calls to the uncovered bands only.
3. **Then run the calibration probe on decision and feedback** — still untested in every
   round to date. Multi-seed per §7, not a single run.
4. **Notify George / RATER_B.** Unchanged, still five minutes, still blocking items 5–6.
5. **Hand `anchors_v3_PROPOSED.json` to Julie** — gated on raters returning P-01–P-06.
6. **Feedback anchor check vs. raters' Agreement tab** — same block.
7. **Decide whether to instrument the pilot for person-side dimension correlation.** Note
   this session made it *more* worth doing: §2's distinct grading variables mean a measured
   correlation would now be interpretable as a real trait relationship rather than an
   instrument artifact. Before, it would have been uninterpretable.
8. `pace → autonomy` and `pace → feedback` still unexamined category-3 candidates.
9. Carried: `au3v2` dimension leak (§3); `build_model.py` still has no `OrderedLogistic`
   path for `experienced` outcomes; `schema.sql` never migrated into the app database;
   `Solverah_Ground_Truth_Roster_v2.md` still missing.
10. **Standing, unchanged: anonymization does not prevent re-identification for 5 of 6
    companies.** Fifth session.
