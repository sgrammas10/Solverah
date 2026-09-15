# Solverah — Session Handoff, 2026-08-17b

**Topic: closed out every open item on the board — lifted and completed
`SPRINT_SCORER_PIPELINE_01.md` (S1-1 through S1-7, hold lifted the same session), plus the six
standing tasks that had been carried across prior handoffs (P-03–P-06 variance extension,
re-identification attack, scrub-log hardening, Test 1 re-run, bias review, `assemble_training_data`
spec, scale-calibration spec).** Custom instruction to honor: be logical and future-thinking, do
not be agreeable — push back.

Sits on top of `SOLVERAH_HANDOFF_2026-08-15.md`, `-15b.md`, and `-17.md` (the partial S1-4 data
point that did not lift the hold) and `causal_graph/SPRINT_SCORER_PIPELINE_01.md`, whose status
line now reads **COMPLETE 2026-08-17** — updated in place, history preserved via strikethrough
rather than deletion.

Every live-API step in this session was written and verified offline by Claude, then run by
Sebastian locally (this sandbox cannot reach `api.openai.com` — confirmed via direct `curl`
through the proxy, `403 Forbidden` / `X-Proxy-Error: blocked-by-allowlist`) and the results pasted
back for analysis. Nothing below is a claim taken on faith from a terminal paste — output files
were independently re-verified (row counts, CSV shapes, raw JSON contents) and, for two analyses
below, the underlying numbers were recomputed from the raw CSVs while writing this doc rather than
carried forward from memory.

---

## 1. Sprint `SPRINT_SCORER_PIPELINE_01.md` — hold lifted, all seven tasks done

The sprint's own two blocking decisions were ratified as recommended in the doc: **#6** (what
`confidence` does downstream) is informational-only, stored but inert, reversible. **#7** (discrete
bands) — behavior already forced this per correction #3 in the sprint doc; the DDL keeps the
continuous field and adds an optional `band` column, no rubric change.

### S1-1 — extended response schema + `ScorerResult` (`causal_graph/scorer_pipeline.py`)
Adds `evidence_quotes` (1-3 verbatim strings) to the response schema. **Design decision that
changes a literal reading of the sprint doc:** the model is asked for quote text only, never for
`source_tags`. Source classification is computed downstream by matching each quote against the
packet's addressable excerpts — reusing the exact `classify_source` taxonomy
(company/noncompany/disputed/researcher) `build_rater_page.py` already ships to raters, rather than
asking the model to self-classify and having two disagreeing answers with no way to reconcile them.
`packet_version_for()` parses `build vX.Y` from each packet's header — confirmed all six packets
say `v4.6`.

### S1-2 — `score_packet()` clean provider interface
`score_packet(client, packet_text, rubric_text, *, packet_id, ...) -> ScorerResult`, no file I/O —
unlike `scorer_variance_test_v2.py`'s `run_once()`, which tangles scoring with CSV/raw-JSON output
and can't be reused elsewhere. `call_with_retry()` logs `temperature_honored` and independently
falls back on `reasoning_effort` if the API rejects it — **this exact fallback fired for real**
during the S1-4 gpt-4o run below (reasoning_effort rejected, temperature still honored), which is
why S1-7 tests that branch specifically rather than trusting the live run alone to have exercised
it correctly.

### S1-5 — citation verifier
`verify_quote()` normalizes dashes (`‒–—―‑` → `-`), smart quotes, and whitespace before matching —
the exact bug class 08-15b found by hand on P-02/P-05 (a retype silently introduced em-dashes into
quote bodies, breaking naive string matching). `noncompany_support()` requires a **matched**
non-company quote, not just a claimed one, before a dimension counts as supported above the 0.7
gate.

### S1-6 — `scorer_run` + `dimension_score_citation` DDL (proposed, not applied)
`causal_graph/v1_model/scorer_run_ddl_PROPOSED.sql`. Separate `scorer_run` table (not reusing
`model_run`, which versions the PyMC fit on an unrelated axis). New
`dimension_score_citation` table — one row per evidence quote, `matched` recorded even when
`False` (an unmatched quote is a finding, not something to discard). Includes the exact SQL query
that reproduces `noncompany_support()`'s logic, so Python and SQL can't silently drift apart.
Verified via `sqlparse`: 4 real statements (CREATE, ALTER, CREATE, CREATE INDEX), all parse clean.

### S1-3 — mean vs. median, confirmed on the wider P-01–P-06 data
Re-run properly per-cell (first attempt averaged the bootstrap estimator across all 36 cells
*before* taking SD, which measures precision of an average across unrelated cells, not precision
of one cell — caught and redone before reporting). Of the 36 dimension×packet cells (gpt-5.5,
n=5 each), **27 have zero observed variance** — recomputed directly from the CSVs while writing
this doc:

| packet | dimension | obs SD | bootstrap SE(mean) | bootstrap SE(median) |
|---|---|---|---|---|
| P-01 | feedback | 0.098 | 0.044 | 0.093 |
| P-01 | innovation | 0.080 | 0.036 | 0.046 |
| P-02 | feedback | 0.098 | 0.044 | 0.093 |
| P-02 | decision | 0.098 | 0.044 | 0.093 |
| P-04 | autonomy | 0.080 | 0.036 | 0.047 |
| P-05 | collaboration | 0.098 | 0.044 | 0.093 |
| P-06 | autonomy | 0.080 | 0.036 | 0.046 |
| P-06 | pace | 0.098 | 0.044 | 0.093 |
| P-06 | feedback | 0.080 | 0.036 | 0.047 |

Restricted to these 9 real-variance cells (the honest, apples-to-apples comparison — averaging in
27 zero-variance cells mechanically deflates both estimators the same way and hides the ratio):
**mean SE(mean) = 0.0403, mean SE(median) = 0.0723 — mean beats median by 1.80×.** Consistent in
direction with, and slightly stronger than, the original sprint doc's n=5 finding (1.53×) on the
retired thin-packet data. **Aggregator decision stands: mean-of-5, not median.**

### S1-4 — the full 2×2 (P-01, n=5 per cell), recomputed from the raw CSVs

|  | old thin packet (~2,880 char GT-01, retired instrument) | new rich packet (P-01 v4.6, 12,499 char, live instrument) |
|---|---|---|
| **gpt-4o-2024-08-06** | mean score SD **0.088**, mood-effect spread **0.217** | mean score SD **0.106**, mood-effect spread **0.133** |
| **gpt-5.5-2026-04-23** | mean score SD **0.015**, mood-effect spread **0.017** | mean score SD **0.030**, mood-effect spread **0.067** |

Two findings, and they point in different directions — worth being precise about which is solid:

**Model tier is now decisively isolated as the dominant variance factor.** Holding packet
constant, gpt-5.5 beats gpt-4o by 5.7× on the old packet and 3.6× on the new one. This is the
comparison the sprint doc's original design flagged as missing (correction #5) and it's now done:
tier and packet are no longer confounded with each other.

**Packet richness increases score variance for both models — the opposite of the sprint doc's
original working hypothesis** (thin evidence forces the model onto its prior, so richer evidence
was expected to stabilize scores). gpt-4o's SD rose 0.088→0.106 old→new; gpt-5.5's roughly doubled,
0.015→0.030. Two readings, not yet distinguishable with n=1 packet: either richer packets contain
more genuinely conflicting/nuanced evidence that a careful reader should weigh differently run to
run (a real property of the evidence), or thin packets were producing **false stability** —
low variance because the model had nothing to disagree with itself about, not because it was
confident. The mood-effect column argues against a clean story either way: it moved in *opposite*
directions across the two models (gpt-4o's fell old→new, gpt-5.5's rose old→new), so this isn't
"richer packets make everything worse" — don't oversell it past what one packet supports.

**Pre-registered bar from the sprint doc (§5): SD → 0.02–0.03 means tier is load-bearing; SD
staying ~0.05+ means noise dominates regardless of tier.** gpt-5.5 clears the bar on the old packet
(0.015) and lands right at its edge on the new, live-instrument packet (0.030) — the one that
matters, since it's what raters are actually scoring against. gpt-4o clears neither. **This is the
first result all session that cleanly resolves in the sprint doc's own pre-registered terms,
without the "not uniform across dimensions" caveat that undercut the 2026-08-17 partial data point**
— P-01's gpt-5.5-on-new-packet SD of 0.030 (autonomy/pace/collaboration/decision flat at zero,
feedback 0.098, innovation 0.080) is the same shape noted in that earlier note, but now it's
compared against an isolated gpt-4o baseline instead of standing alone.

**Which dimensions wobble is still packet-conditional, confirmed with more data.** Across all six
gpt-5.5 packets (recomputed): feedback wobbled 3/6, autonomy 2/6, pace/collaboration/innovation/
decision 1/6 each. No dimension is safe to single-run yet, and feedback is the standing candidate
for an anchor rewrite — worth checking against the human raters' Agreement tab once their scores
land, per the open item carried from 08-17a.

Scripts: `scorer_variance_test.py` (fixed this session — see §5 below), `scorer_variance_test_v2.py`.
Data: `runs.csv`, `runs_gpt_55_2026_04_23.csv`, `runs_v2_gpt_4o_2024_08_06_P-01.csv`,
`runs_v2_gpt55_P01.csv`.

### S1-7 — pytest suite + live end-to-end dry run on P-01
`causal_graph/test_scorer_pipeline.py`, 43 offline tests (real anchors.json, real packets, only
the OpenAI client mocked — per this project's "mock external services only" testing convention),
plus one `@pytest.mark.live` test gated behind `-m live` so it doesn't run by default or block on
a missing API key. Offline suite covers: `packet_version_for` against all six packets;
`parse_excerpts`/`classify_source` against exact known-good counts independently confirmed from
`build_rater_page.py`'s own earlier run (P-01 45/24/18/3/0 … P-06 46/24/20/2/0, zero
unclassified); the citation verifier including the real em-dash corruption case; `score_packet()`
against a mocked client; and the `reasoning_effort` retry-fallback path specifically, because it
fired for real in S1-4 above and a live run passing doesn't by itself prove the fallback logic is
correct, only that it didn't crash.

Sebastian ran the live test locally: **18/18 evidence_quotes verified against the real P-01
packet on the first live run** — every quote the model produced is real packet text, correctly
attributed. Cross-referencing against `noncompany_support()`: autonomy, pace, feedback, and
innovation each landed at least one matched non-company-authored quote on this run; **collaboration
and decision were backed only by company-authored and disputed sources** — meaning, under the ≤0.7
gate, neither of those two dimensions can legitimately clear 0.7 on this run's evidence without the
model finding different support next time. That's the citation verifier doing exactly the job S1-5
was built for — catching this mechanically instead of a rater noticing it by hand.

---

## 2. LLM adversarial re-identification attack (`causal_graph/reidentification_attack.py`)

Question: does anonymizing a packet actually prevent an LLM from identifying the real company?
n=3 runs × 6 packets, pinned `gpt-5.5-2026-04-23`, asked for a top guess + confidence + up to 5
quoted clues, no outside tools/browsing.

**5 of 6 real companies identified with HIGH confidence on all 3/3 runs — 100%:** Oscar Health,
Best Buy, R/GA, Doist, Raymond James. **P-03 (Akuna Capital), the one exception, was only 1/3
correct** — the other two guesses were real competitor prop-trading firms (Belvedere Trading,
TransMarket Group). Worth being precise about what that partial failure actually shows: the
model's reasoning converged on the *identical* narrow set of distinguishing details every time
(Chicago HQ, lake view office, no outside capital, STIR options trading, Jan 2023 offer
rescissions) — it wasn't confused about what to look for, it correctly narrowed to a reference
class of maybe three firms and sometimes picked the wrong member of that class. That is a much
weaker anonymization result than "the model couldn't tell" — it's "the model could tell almost
exactly, and only missed by one within a tiny set." Overall auto-matched accuracy: 16/18 (88.9%).

**Anonymization, as currently scoped, is not doing the job its name implies for 5 of 6 companies.**
It survives only for the single most obscure/private company tested. This doesn't invalidate the
scrubbing work — it's still necessary to keep the packets from being a trivial company-name
substitution exercise for a human — but it should not be described as preventing identification,
and any downstream claim that rests on "the model doesn't know which company this is" needs to be
re-examined against this result specifically.

Data: `reid_attack_gpt_5_5_2026_04_23.csv` (18 rows) + `raw_reid_gpt_5_5_2026_04_23_P-0{1-6}/`
(6 dirs, 3 files each — verified, not just trusted from the terminal paste).

---

## 3. Test 1 re-run: blind vs. identified (`causal_graph/test1_blind_vs_identified.py`)

Rebuilt properly rather than patched — imports scoring directly from `scorer_variance_test_v2.py`
(not duplicated) to guarantee byte-identical methodology between conditions, and the BLIND
condition reuses the existing `runs_v2_*` CSVs instead of re-running (halves the API cost and is
the cleaner minimal pair — same runs, not a fresh resample that could itself introduce noise).
IDENTIFIED condition substitutes the real company name only inside quote bodies, never inside
attribution tags, via a regex boundary check.

**Result: 0/36 cells exceeded 1.5×SE.** Mean |delta| = 0.0133, mean SE = 0.0199 — a clean null.
Knowing the company name, with evidence held constant, does not move scores beyond noise. Three
cells (P-01 feedback, P-01 innovation, P-06 autonomy) all landed at an identical z=1.265 —
flagged and confirmed as a repeated combinatorial artifact of the same 3-2 band-split arithmetic at
n=5, not three independent near-misses.

**What this does and does not settle.** It rules out one specific worry: the model tilting scores
because it recognizes the company and has an opinion about it. It does **not** address the more
concerning version of Test 1's original question — whether the model's *reasoning* invents
out-of-packet facts once it knows the company, even if the final score doesn't move. The original
schema had nowhere to check that. S1-1's `evidence_quotes` addition, built this session, is exactly
what would let this be re-tested properly: run the identified condition again and citation-verify
its quotes the way S1-7 just did for the blind condition. Not done this session — flagged as the
natural next step if Test 1 needs revisiting.

Data: `runs_test1_identified_P-0{1-6}.csv`, `test1_comparison_all_packets.csv`.

---

## 4. Bias review of the 24 draft assessment items (`ASSESSMENT_ITEMS_BIAS_REVIEW.md`)

Structural review, not a rewrite. **Feedback and decision dimensions have zero reverse-keyed
items** — autonomy/pace/collaboration/innovation each have one (au4/pa4/co4/in4), feedback and
decision have none, meaning an acquiescence-biased respondent's score on those two dimensions is
indistinguishable from a genuine one. **Decision's four items (de1-de4) systematically frame the
"data-driven" pole as more professionally rigorous** than the intuition/judgment pole across all
four — a wording bias, not a content one; a respondent who prefers judgment-based decisions has no
item that makes that choice sound equally professional. Smaller skews flagged in pa2 ("quality
bar" language favoring one pole), fb3 ("trusted you" vs. "unfiltered" — asymmetric emotional
valence), and in1. Proposed rewrite directions recorded; the YAML itself was not touched, pending
sign-off.

---

## 5. `assemble_training_data(db)` (`causal_graph/v1_model/assemble_training_data.py`)

Full working implementation, not just a spec — verified end-to-end against the **real**
`build_model.py` (`pm.sample_prior_predictive()` ran successfully on assembled output using the
real `solverah_model_config.yaml` and `priors.yaml`, not a stub). Source-priority resolution
(declared > researched > scraped, tie-broken by `as_of`) is pure and independently tested — a
scraped row inserted first does not win over a declared row inserted later, confirmed explicitly
since insertion order is exactly the kind of bug this join could hide. Uses portable SQLAlchemy
`IN` binding instead of Postgres-only `ANY()`/`DISTINCT ON`, so the real production code path is
testable against sqlite, not just Postgres. `outcome_type` is a required, explicit
`Literal["appeal", "experienced"]` argument — the two outcomes are never blended, per the
project's own locked decision.

**A real gap found while building this, not designed around:** `build_model.py` has no
`OrderedLogistic` path for `experienced` (1-5 ordinal) outcomes — only Bernoulli, despite the
project's own canonical handoff doc (`v1_model/SOLVERAH_HANDOFF.md`) stating "Experienced-fit
outcome is a 1-5 scale → that training run uses OrderedLogistic, NOT Bernoulli." The two-outcome-
head design is documented but not implemented. Not blocking today (zero `experienced` outcomes
exist yet to train on), but it will block the day the first one arrives. Also confirmed:
`schema.sql` has never been migrated into the app's actual Postgres database — no matching files
exist under `migrations/versions/`. Recorded in `ASSEMBLE_TRAINING_DATA_NOTES.md` for sign-off.

---

## 6. Person↔company scale calibration check (`SCALE_CALIBRATION_CHECK.md`)

No check like this existed before. Specifies a concrete paired-vignette probe (18 pairs × 6
dimensions) to test whether the person-side and company-side 0-1 scales actually mean the same
thing at the same number.

**Finding, verified by direct enumeration, not assumed:** person scores are the mean of 4 binary
forced-choice items, so they can only ever land on `{0, 0.25, 0.5, 0.75, 1.0}`. Company scores use
the 5-band rubric, `{0.1, 0.3, 0.5, 0.7, 0.9}`. **The two lattices overlap at exactly one point,
0.5** — every other person score sits on a value a company score can never take, and vice versa.
This is deeper than a rounding nuisance: person items measure *proportion of forced binary choices
answered one way*, company rubric measures *graded judgment across five intensity levels* —
structurally different measurement models being fed into the same signed-gap subtraction. This was
previously undocumented and is a real, unaddressed risk to the validity of the person↔company gap
the entire model is built on. Not fixed this session — the check that would tell you how bad it is
in practice is what got specced.

---

## 7. Scrub-log hardening (`Solverah_IP/ground_truth/rater_app/build_rater_page.py`)

Fixed a fragile string-match: the packet-truncation cut used to rely on finding a "SCRUB LOG"
substring by informal matching. Replaced with an explicit `^#{3,}\s*END OF PACKET\s*#{3,}\s*$`
regex marker, and — the actual fix — changed the failure mode from silently including everything
past the boundary (i.e., leaking the scrub log itself into what a rater sees) to raising loudly if
the marker is missing. Verified byte-identical output across all 18 existing rater pages (P-01–P-06
× raters A/B/C) before and after.

---

## 8. A latent bug caught proactively, not from a bug report

While preparing the S1-4 gpt-4o-on-old-packet command, found that `scorer_variance_test.py`
hardcoded `runs.csv`/`raw/` as output paths **regardless of the `--model` flag** — running it with
`--model gpt-5.5-2026-04-23` would have silently overwritten the original, canonical gpt-4o
baseline referenced throughout the whole project. Caught before handing off the command, not after.
Fixed with conditional path logic: the default model preserves the exact original paths (confirmed
via `md5sum` and unchanged mtimes), any other model gets a distinctly-named `runs_<model_tag>.csv`
/ `raw_<model_tag>/` pair.

---

## Open / next

1. **Feedback anchor check against the human raters' Agreement tab**, once the three raters' P-01–
   P-06 files land. Feedback is now the standing candidate for a rubric rewrite across two
   independent sessions of evidence (3/6 packets wobbled, and it's the one dimension that failed on
   both P-01 and P-02 in the earlier partial data point).
2. **Anonymization does not prevent identification for 5/6 real companies.** Any downstream
   reasoning that assumes "the model doesn't know which company this is" should be re-examined
   against the re-identification attack result specifically, not assumed to still hold.
3. **Re-test Test 1's identified condition with citation verification**, now that S1-1's
   `evidence_quotes` exist. The score-level null result stands, but whether the model's *reasoning*
   invents out-of-packet facts once it knows the company was never actually checked.
4. **`build_model.py` has no OrderedLogistic path for `experienced` outcomes** — documented as the
   design in the canonical handoff, not implemented in code. Not urgent (zero experienced outcomes
   exist), but it will block the first one that arrives.
5. **Person↔company scale lattice mismatch** — `{0, .25, .5, .75, 1}` vs. `{.1, .3, .5, .7, .9}`,
   overlapping only at 0.5, with different underlying measurement models. The calibration check
   that would quantify the practical impact is specced (`SCALE_CALIBRATION_CHECK.md`) but not run.
6. **`schema.sql` has never been migrated into the actual app database.** No files under
   `migrations/versions/` correspond to it.
7. Carried, still untouched: bias-rewrite the 24 assessment items per §4 above (spec exists,
   YAML not touched); George/RATER_B v3-packet notification (resolved by the v3 scrap per the
   08-09 sprint doc amendment, but he still needs to be told); find or reconstruct
   `Solverah_Ground_Truth_Roster_v2.md`, deprioritized this session since the 19-company roster is
   out of scope (rater time constraint).

---

## Framings that survived pushback this session

* **Model tier and packet richness are now separable, and they point in opposite directions.**
  Tier is the dominant variance factor (3.6-5.7× better on gpt-5.5). Richer packets increase
  variance for both models — the opposite of the sprint doc's original hypothesis. Don't collapse
  these into one "the new pipeline is better" story; they're two different findings.
* **"The model correctly narrowed to a 3-firm reference class and missed" is not the same finding
  as "the model was confused."** P-03's 1/3 re-identification result looks like a partial win for
  anonymization until you read the reasoning — it wasn't. Precision about what a near-miss actually
  shows matters more than the headline hit rate.
* **A null result on score deltas (Test 1) does not clear a hypothesis about reasoning
  fabrication that the schema couldn't check at the time.** The evidence_quotes addition built this
  session makes that re-test possible; not having done it yet should be stated as an open item, not
  implied to be settled by the score-level null.
* **27 of 36 dimension×packet cells having zero variance mechanically flatters any pooled average.**
  The honest comparison for mean-vs-median is the 9 cells with real signal, not all 36 — averaging
  in the flat cells makes both estimators look tighter than they are without changing their ratio.
* **A citation-verifier result of 18/18 is not by itself evidence the scores are correct.** It's
  evidence the model isn't fabricating quotes. Whether the *scores themselves* are well-calibrated
  is a separate, still-open question — the ≤0.7 gate finding on collaboration/decision this run is
  the closer analogue to a real substantive check.
