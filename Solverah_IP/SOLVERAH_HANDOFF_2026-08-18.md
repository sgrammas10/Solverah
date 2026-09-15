# Solverah — Session Handoff, 2026-08-18

**Single handoff for the 8/18 morning session. Supersedes and consolidates the three
interim docs written during it (`-18`, `-18b`, `-18c`) — those have been retired; this is
the one to read.**

Sits on top of `SOLVERAH_HANDOFF_2026-08-17e.md`.

**Session in one paragraph:** closed `-17e`'s gating item by re-running the recovery curve
properly — and the result was a retraction, not a confirmation. The 2.5x figure was a
single-seed artifact and does not survive. Then closed `-17d` item 2: extended the
graduated-difficulty ladder from autonomy to all six dimensions with the bias-review fixes
bundled in, found and fixed a straight-lining defect the bias review had missed, found and
closed a second one the ladder redesign itself created, retired the v1 item file with
machine-enforced refusal, and promoted the structural check into a CI gate. Work stopped
partway through item ratification on an unanswered product question — see §6, which is
where the next session starts. `anchors.json` untouched, still frozen at
`v1-frozen-2026-08-15`.

---

## 1. RETRACTION — the 2.5x rows figure does not survive

`-17e` §3 reported that lattice-resolution validation data needs "roughly 2.5x the rows" of
the old uniform-based curve to reach the same recovery error, and flagged it as single-seed.
Re-run properly, it is noise.

Two defects in the original comparison, found before re-running:

**(a) It was confounded.** The "uniform (old)" column was continuous-uniform data through
the **unpatched** model (no person snap); the "lattice (new)" column was lattice data
through the **patched** model. Two variables moved at once, so the figure was attributed
entirely to Finding 2 (data resolution) when it also carried Finding 1's snap. Re-running
those two arms at more seeds would have tightened the interval around a quantity that isn't
cleanly interpretable.

**(b) It was unpaired.** `recovery_curve()` seeds one `rng` and draws person, env,
confounders and outcomes from it in sequence. `rng.choice(PERSON_LATTICE, n)` and
`rng.uniform(0,1,n)` consume the stream differently, so at "the same seed=0" the two arms
also got different confounders and different binomial draws — arm effect entangled with draw
noise, the exact failure `lattice_gap_analysis.py` §C documents.

**What was run instead:** `recovery_multiseed.py`, a 2×2 factorial paired across seeds.

| arm | data | model | corresponds to |
|---|---|---|---|
| A `uniform_raw` | continuous uniform | no snap | original pre-patch pipeline |
| B `lattice_snap` | lattice | snap | current post-patch pipeline |
| C `uniform_snap` | continuous uniform | snap | isolates the patch |
| D `lattice_raw` | lattice | no snap | isolates resolution |

One latent stream (`u_person`, `u_env`, `conf`, `u_y`) drawn per seed and shared by all four
arms; arms differ only in how latents are discretised and whether the model snaps. Outcomes
use the same `u_y` against each arm's own `p_true`, so even the binomial draw is paired. DGP
uses the same snap setting as the fit — an arm is a whole pipeline, not a mismatched
DGP/model pair. 5 seeds × 4 arms × n ∈ (200, 800, 2000, 5000) = 80 fits, chains=2,
draws=1000, tune=1000, planted `pace.mag = −2.0`. All `r_hat` ≤ 1.003, `ess_bulk` ≈ 3000+.
55 min wall clock with the compiled backend. Resumable.

**Result — paired |err| difference, lattice_snap − uniform_raw:**

| n | observed | 95% CI | `-17e` reported | inside CI? |
|---|---|---|---|---|
| 200 | −0.036 | [−0.226, +0.155] | +0.315 | **no** |
| 800 | −0.001 | [−0.165, +0.163] | +0.262 | **no** |
| 2000 | −0.009 | [−0.124, +0.105] | +0.116 | **no** |
| 5000 | +0.066 | [−0.033, +0.166] | +0.027 | yes |
| **pooled (20 pairs)** | **+0.005** | **[−0.049, +0.059]** | | |

Sign counts 10/20 each way. Seed-to-seed SD of |err| is 0.06–0.32 — **larger at every cell
than any between-arm difference.** That is the whole story of why the single-seed run read
as signal.

**Factorial decomposition** (paired, pooled over n, 20 pairs each): A vs D (resolution,
unpatched) −0.028, t=−1.28. C vs B (resolution, patched) −0.005, t=−0.17. A vs C (patch,
continuous data) −0.000, t=−0.03. D vs B (patch, lattice data) +0.022, t=+0.73. No cell of
the factorial moves — both candidate explanations are dead, not just their sum.

**The posterior-SD "anomaly" from `-17e` §3 also mostly dissolves.** Paired, it is
−0.002 to −0.011 (2–4% relative), consistent in direction at larger n (5/5 both times) but
immaterial.

**The mechanism, and the actually interesting result of the session.** Mean SD of
`|gap_pace|`:

| arm | gap_sd | distinct \|gap\| values | mean p_true |
|---|---|---|---|
| A uniform/raw | 0.2372 | 1995 | 0.104 |
| B lattice/snap | 0.2350 | **21** | 0.108 |
| C uniform/snap | 0.2308 | 1995 | 0.109 |
| D lattice/raw | 0.2522 | 52 | 0.086 |

Discretising the instruments collapses the number of distinct `|gap|` values **95×** while
leaving the *spread* essentially unchanged (under 1%). Logistic Fisher information goes as
`p(1−p)·x²` — it depends on the **variance** of the predictor, not on how many distinct
values that variance is spread across. So coarse instrument resolution is not, by itself,
expensive for weight recovery.

**What is expensive is range restriction, not resolution** — the env scale's inability to
leave [0.1, 0.9]. Visible above as arm D's inflated `gap_mean` and depressed `p_true`. That
is a separate issue and it is what Finding 1's snap addresses.

**What this retracts and doesn't:**

- **Retracted:** the 2.5x figure, and the claim that Finding 2's validation-distribution
  mismatch made n-needed numbers "optimistic by an unmeasured amount." Measured, it is
  optimistic by approximately nothing. Uniform-validated n-needed figures appear usable.
- **Not retracted — the Finding 2 fix stays.** Validating against what the instruments emit
  is right on principle whether or not it changes the answer, and the project can now say it
  checked rather than assumed. Keep the lattice draws.
- **Not retracted — Finding 1's patch stands and gains support.** Its justification was never
  recovery; it was the pole penalty in P(fit), verified separately in `-17e` §2 (0.392 →
  0.490 against a 0.485 perfect match). The sweep adds that the patch is **recovery-neutral**
  (A vs C: −0.000, t=−0.03) — it fixes the pole penalty at no measured cost.

**Limits.** Paired SD 0.06–0.16, so SE ≈ 0.03–0.07 at 5 seeds: this decisively rules out
effects the size `-17e` claimed, but **cannot rule out a true effect below ~0.10 in |err|**.
"No detectable effect," not "provably zero." One planted effect size, one dimension, one
prior placement. One nominally significant cell reported rather than suppressed: C vs B at
n=5000, t=−2.92 (1/5 signs), with arm B nominally worst at n=5000 — against 20 contrasts
tested that is roughly what chance produces, and the same contrast is +1.10 at n=200 and
−0.22 at n=2000, so no monotone pattern. Treated as noise. **If anyone extends to 10 seeds,
watch that cell**; `--seeds 10` resumes where this left off, ~1 more hour.

Files: `recovery_multiseed.py`, `analyze_sweep.py`, `plot_multiseed.py`,
`results/recovery_multiseed.csv` (80 rows + diagnostics), `results/recovery_multiseed.png`.

## 2. Graduated-difficulty ladder extended to all six dimensions

`assessment_items_v2_PROPOSED.yaml` — 24 items, proposal not applied, same convention as
`anchors_v3_PROPOSED.json`. Bias-review fixes bundled in rather than applied separately,
because reordering an item's difficulty and de-skewing its wording are the same edit to the
same sentence.

**Design rule 1 — every dimension gets its own grading variable.** Reusing "stakes"
everywhere would make a risk-tolerant respondent climb *every* ladder, manufacturing
person-side cross-dimension correlation out of the instrument's own construction —
indistinguishable in pilot data from the real trait correlation `-17d` §4 finding 3 wants to
measure.

| dimension | grading variable |
|---|---|
| autonomy | stakes / scope / expected check-in frequency *(unchanged)* |
| pace | duration the tempo must be sustained |
| collaboration | coordination cost in the respondent's own working time |
| feedback | exposure — privacy and delay |
| innovation | sunk investment discarded |
| decision | novelty — how unprecedented the situation is |

**Bias review findings, closed.** Finding 1 (no reverse-keyed items on feedback or
decision): closed, rung 4 is reverse-keyed in all six. Finding 2 (decision skews to the data
pole on every item): closed by full rewrite, see below. Finding 3: closed structurally
rather than by rewording — `pa2v2` drops all quality language; `fb3v2` grades by exposure
rather than bluntness so the valence asymmetry has nowhere to attach; `in1v2`–`in4v2` grade
by sunk investment so the high pole becomes "discard working value" rather than "create,"
explicitly wasteful at rung 4. Finding 3 secondary (`de3` quoted dialogue): closed. Finding
4: `pa2`'s leak is gone; **`au3v2`'s remains open** and was left deliberately — it is the one
ladder with a probe behind it and rewording throws that away. Watch it in pilot data; the
tell is correlating more with decision than autonomy.

**Decision rewrite — deliberately departs from the bias review's own proposal.** The review
suggested speed vs. information-sufficiency. Rejected: that grades by cost-of-being-wrong,
which **is** stakes, which **is** autonomy's grading variable, violating design rule 1 on the
one dimension where finding 4 already flags a confound. Chosen instead, with Sebastian's
sign-off: **both poles are a kind of evidence.** Low pole is pattern-recognition from having
seen the situation before — a real and defensible basis for a call, not "gut." High pole is
explicit measurement. Neither option is "deciding without information," which is what made
the v1 wording indefensible. The ladder climbs by novelty: as the situation gets more
unprecedented, accumulated pattern-recognition gets objectively weaker.

## 3. NEW DEFECT — positional key imbalance (missed by the bias review)

The bias review checked semantic framing — which option *reads* as desirable. It did not
check which letter the high pole sits on. In `assessment_items.yaml`:

| dimension | A = high pole on | always-picking-A scores |
|---|---|---|
| autonomy | 4 of 4 | **1.00** |
| pace | 4 of 4 | **1.00** |
| feedback | 4 of 4 | **1.00** |
| decision | 0 of 4 | **0.00** |
| collaboration | 1 of 4 | 0.25 |
| innovation | 1 of 4 | 0.25 |

`autonomy_items_v2_POC.yaml` inherited it (A=high on all four).

**Why it matters more than it looks:** the planned confidence measure is *internal
consistency*. A positional straight-liner is perfectly consistent, so confidence comes out
**high** on a fabricated profile that is maximally extreme on three dimensions at once. The
model would weight it heavily instead of leaning on the prior. In pilot data it would read as
a genuine population of decisive, fast-paced, feedback-hungry respondents.

**Fixed throughout v2:** every dimension is exactly 2 A=high and 2 B=high. Always-A and
always-B both produce `[0.5]×6` — harmless (midpoint, not extreme) and detectable. **Not
proof**: a genuinely middling respondent produces the identical vector, so it should raise a
review flag, never an auto-reject.

**No data remediation required.** `assessment_items.yaml` is `form_version: v1-draft`, never
piloted; no real respondent data exists. The only `person_dimension_score` rows anywhere are
synthetic fixtures in `assemble_training_data.py` (hardcoded 0.5,
`scoring_key_version='v1'`). The defect was caught in the only window where it costs nothing.

**Company side checked and clean.** `build_rater_page.py` renders bands as an ordered ordinal
scale with the numeric value visible — order is meaningful there, and "always pick the first"
means 0.1 on everything, obvious rather than disguised as consistency. No action. Dimension
presentation order is fixed, but raters are told to score in any order and `commit_order` is
recorded, so order effects are already instrumented if you want to look.

## 4. SECOND NEW DEFECT — the ladder redesign created one, now closed (design rule 3)

A graduated ladder displayed in difficulty order is transparent. The four rungs read visibly
as "a little / somewhat / quite / extremely," so a respondent who wants to look decisive does
not have to guess — they endorse further down the list. The result is *perfectly
Guttman-consistent*, so consistency-based confidence again comes out **high** on the fake.

Same failure shape as §3, arriving through the ladder design rather than the key layout, and
rule 2 does not close it. **Worth being explicit: the ladder redesign created this. v1's flat
items were not fakeable this way because there was no visible gradient to climb.** Still the
right fix, but it wasn't free.

Mitigation, declared in the YAML:

```yaml
presentation:
  randomize_item_order_within_dimension: true
  order_seed: respondent_id       # a resumed session must not reshuffle
  randomize_option_order: false   # intentional
  never_display: [id, difficulty_target, pole, reverse_keyed, grading_variables]
```

`id` is in `never_display` for a non-obvious reason: ids are sequential within a dimension
(`au1v2`…`au4v2`), so surfacing them re-leaks the order the shuffle just hid.

**Option order deliberately NOT randomized.** (1) Rule 2's 2/2 balance already neutralizes
positional bias, deterministically rather than in expectation. (2) Probe files key frozen
choices by letter; per-respondent shuffling makes every one unreproducible. (3) A stored
"chose A" becomes ambiguous unless the shuffle is persisted with it — silent scoring
corruption for no gain over (1). If ever done anyway: store the chosen **pole**, not the
letter, and rework every probe file. The gate warns if the flag is flipped.

## 5. v1 retired, and the structural check promoted to a gate

**`assessment_items.yaml` retired, not deleted** — the frozen probe runs in
`vignette_probes/results/` were scored against it and stop being reproducible if it
disappears. `status: superseded` is enforced in three places: `check_assessment_items.py`
refuses it; `test_assessment_items.py` **asserts that it is refused**, so stripping the
status key fails a test rather than quietly making the file scoreable again; and
`score_person_side.py` raises on it, with `--items` now defaulting to v2 and
`--allow-superseded` as the explicit labelled escape hatch. `check_items_v2.py` moved to
`v1_model/_to_delete/`.

**`check_assessment_items.py` + `test_assessment_items.py`** replace the one-off. Takes paths
(default: every `assessment_items*.yaml` beside it), exits non-zero, picked up by a bare
`pytest` and by `.github/workflows` via the existing `pytest.ini` / `causal_graph/conftest.py`.
Verified against the real repo:

```
assessment_items.yaml              1 fail  0 warn   <- refused, as designed
assessment_items_v2_PROPOSED.yaml  0 fail  0 warn
3 passed in 0.20s
```

Enforces: presentation contract present and not weakened; **4 items per dimension —
load-bearing**, since `mean_pole` over 4 reproduces `build_model.py`'s `PERSON_LATTICE` and
five items would silently invalidate that constant and every lattice result in §1 (do not
"just add one more"); `difficulty_target` on every item; strictly increasing 0.3/0.5/0.7/0.9
rungs; exactly one reverse-keyed item and it is the hardest rung; 2/2 key balance; always-A
and always-B both flat 0.50; Guttman prefix endorsement reproduces `PERSON_LATTICE` exactly;
six distinct grading variables; bias-review vocabulary sweep; option length ratio ≤ 2.0 (warn).

The gate caught three key-balance errors in the first draft of v2 (pace, innovation and
decision were 3/1, 1/3 and 3/1) — the argument for writing it before eyeballing the file.

**The reusable point.** Both defects caught this session were structural and both survived a
careful human read of the item *text*, because they live in the file's *shape*. Content
review and structural check are complements, and only one can be automated. Same argument as
the seeds rule below: a check that has to be remembered is not a check.

**Honest limit:** the gate catches the classes that were enumerated. It says nothing about
whether the instrument measures anything. Passing it is not evidence the ladder works.

**Autonomy probe remap:** `vignette_probe_pairs_v3_autonomy_ladder.yaml`'s
`person_item_choices` letters were remapped for `au2v2` and `au4v2` (option order changed,
text did not). All five cached levels still reproduce their `target_person`
(0.0/0.25/0.5/0.75/1.0), verified. **No API re-run needed** for 0.1/0.5/0.7/0.9; the 0.3 band
still needs its one live call, exactly as before.

## 6. WHERE WORK STOPPED — read this first next session

Item-by-item ratification of the 24 items began and was **halted immediately**, on realising
these are the literal questions a respondent sees. That surfaced a question the design cannot
be signed off without, and it is a product question, not a psychometric one:

> **Who fills out this assessment, and at what point? And does the employer ever see an
> individual respondent's answers or dimension scores?**

**Why it gates the items rather than being a detail.** The reverse-keyed item is the **hardest
rung in every dimension**, and it is the one asking about past job dissatisfaction — "jobs
have frustrated you most when…", "the managers you've found hardest to work for…", "roles that
drained you…". If this runs anywhere near a hiring context, respondents have an obvious
incentive to soften how they answer questions about disliking previous employers. If they do,
rung 4 is systematically under-endorsed across all six dimensions, every score compresses
toward the middle, and it looks like a population of moderates rather than a measurement
artifact.

That is not a wording problem in any single item. It is the interaction between the
reverse-keying pattern and where the instrument sits in the funnel, and depending on the
answer it may change the **design** rather than the wording.

**Candidate answers considered:** signed-up user self-profiling for matching (lowest pressure,
frustration framing safest); candidate mid-application (highest pressure, rung 4 at risk
across all six); existing employee at a client company (medium, and the framing may read as
being asked to criticise a current employer); internal pilot only (fine as a staging answer,
but the design still has to assume an eventual context). Second axis: whether the employer
sees individual scores at all, or only a match result — that is what makes honest answering
rational, and if it's "no," it is worth stating on the form itself.

**Who should answer what.** The funnel question is Sebastian's alone — Julie cannot answer it.
The wording pass is also fine for Sebastian; it is "does this question mean what I think it
means to a stranger," not specialist work. **Neither is the right expert for whether the
ladder is psychometrically real** — Julie's involvement has been company-side (profiling
prompts, rubric anchors), and person-side item design is psychometrics. Whether the difficulty
ordering holds and the dimensions are separable in respondents is answerable by a pilot, and
possibly by an I-O psychology review — not by inspection. Worth naming as a gap now rather
than after building vignettes for five ladders. Also: do not add this to Julie's queue while
`anchors_v3_PROPOSED.json` is already stalled behind raters; that produces two blocked queues,
not faster answers.

## 7. Process decisions made this session

- **One handoff per chat**, written at the end — not one per set of code produced or edited.
  This document is the first for 8/18; the three interim docs it consolidates have been
  retired to `_to_delete/`.
- **Handoffs live at the top level of `Solverah_IP`**, not in the `Solverah` git repo
  (`Solverah_IP` = non-code files, `Solverah` = code and specs). Today's were initially
  written to the repo in error and have been moved.
- **Proposed standing rule, not yet adopted:** no quantitative comparison enters a handoff
  without ≥3 seeds and a paired design, or it enters explicitly labelled as a pilot with no
  number quoted. Three single-seed results have now been reported as findings across three
  sessions (`-17d` finding 3, `-17e` §3, and one earlier documented in
  `lattice_gap_analysis.py` §C). Compute was never the bottleneck — 80 fits took 55 minutes.

---

## Open / next

### 1. ANSWER THE FUNNEL QUESTION, THEN RATIFY THE 24 ITEMS ← start here

§6 has the full framing. Two sub-steps, in order:

- **1a.** Decide who fills out the assessment and when, and whether the employer sees
  individual scores. Sebastian's call, nobody else's. May change the design, not just wording.
- **1b.** Then ratify or redline `assessment_items_v2_PROPOSED.yaml` item by item. On
  ratification: flip `status: proposed` → `active` and drop the `_PROPOSED` suffix. If
  item-by-item questioning is the wrong format, the alternative is laying all 24 out in a
  markup document instead.

Everything below is blocked on this — the probe vignettes encode the item wording, so writing
them against unratified text means writing them twice.

### Ready to build once item text is stable

2. **Implement the presentation shuffle in the form renderer.** The rule 3 contract is
   declared in the YAML and enforced *against* the YAML, but nothing consumes it — there is no
   person-side form UI in the repo reading `presentation:`. Until one exists, rule 3 is a
   specification, not a protection, and the passing gate does not cover it.
3. **Write probe pair files for the five new ladders.** The real cost of §2 — five levels of
   person *and* company vignette each. Check whether already-scored company vignettes can be
   reused per band the way v3 did, cutting live API calls to uncovered bands only.
4. **Then run the calibration probe on decision and feedback** — untested in every round to
   date. Multi-seed, not a single run.
5. **`OrderedLogistic` path in `build_model.py`** for `experienced` outcomes. Still absent.
6. **Migrate `schema.sql`** into the app database.
7. **Populate `scoring_key_version` for real.** Column and plumbing exist
   (`_fetch_person_scores()`); nothing writes it meaningfully. Do it when v2 goes active, or
   the v1/v2 separation exists only in memory.

### Decisions, not work

8. **Instrument the pilot for person-side dimension correlation** (`-17d` §4 finding 3). More
   worth doing after §2: with six distinct grading variables a measured correlation is now
   interpretable as a real trait relationship rather than an instrument artifact. Before, it
   would have been uninterpretable. Note the finding itself is single-seed — treat as pilot
   signal, not result. Free now, expensive later.
9. **`pace → autonomy` and `pace → feedback`** — unexamined category-3 candidates, four
   sessions.
10. **Adopt the ≥3-seeds-and-paired rule** (§7) as standing discipline.
11. **Decide whether an I-O psychology review of the ladder design is worth buying**, once
    item text is stable (§6).

### Blocked on people — one of whom is Sebastian

12. **Notify George / RATER_B.** Five minutes, blocks 13 and 14, carried across multiple
    sessions and raised four times on 8/18 alone without action.
13. **Hand `anchors_v3_PROPOSED.json` to Julie** — gated on raters returning P-01–P-06.
14. **Feedback anchor check vs. the raters' Agreement tab** — same block.
15. **`Solverah_Ground_Truth_Roster_v2.md` still missing.** Nobody has said where it went.

### Carried

16. **`au3v2` dimension leak** (§2) — left deliberately, watch in pilot data.
17. **`au2v2` option length ratio is exactly 2.00** (78 vs 39 chars), the worst in the set. It
    passes the gate but sits on the line, and the longer option is the LOW pole — if it draws
    the eye it biases toward low autonomy. Not changed because the text has a probe behind it.
18. **Stray `SOLVERAH_HANDOFF.md`** still in `Solverah/causal_graph/v1_model/` — predates
    today, unclear whether anything references it.
19. Test 1 identified-condition re-check.

### Standing

20. **Anonymization does not prevent re-identification for 5 of 6 companies.** Fifth session
    carrying this unchanged. Two lawyers and Julie are holding packets described to them as
    anonymized, and that description is not currently backed. The cheap version is not fixing
    the anonymization — it is changing what the raters were told. One email. It has now
    outlasted two complete redesigns of other parts of the system.
