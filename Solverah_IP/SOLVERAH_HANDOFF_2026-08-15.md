# Solverah — Session Handoff, 2026-08-15

**Topic: rater scoring pages, the packet anonymization pass, and a rater-plan decision that was
reversed on a partial reading of the record.**

Custom instruction to honor: be logical and future-thinking, do not be agreeable — push back.

---

## ⚠ READ THESE FIRST — ALL OF THEM, BEFORE DOING ANYTHING

**This session made a serious error by skipping one of them. Do not repeat it.**

Read every file in this list, in this order, in full:

1. `SOLVERAH_HANDOFF.md` — the canonical project state (model, dimensions, confounders, locked decisions)
2. `SOLVERAH_HANDOFF_2026-08-10.md` — **the one that was skipped. Contains binding decisions on the
   rater plan, the ≤0.7 rule, dispersion, and confidence that contradict things asserted later.**
3. `SOLVERAH_HANDOFF_2026-08-13.md`
4. `SOLVERAH_HANDOFF_2026-08-13b.md`
5. This file
6. `ground_truth/RUN_CARD.md` — operator guide, contains the freeze rule and a P-01 answer key
7. `ground_truth/anonymization/_STATE.md` — where the scrubbing pass stopped
8. `ground_truth/anonymization/ANONYMIZATION_RULES_DRAFT.md` — the scrubbing ruleset and open judgment calls

**What went wrong.** This session read handoffs 1, 3 and 4 and skipped 2. On that partial record it
argued Sebastian into reversing a rater-plan decision that handoff 2 records him having already made
the other way, with four reasons attached. He agreed to the reversal without either party knowing
the prior argument existed. The error was caught only when he asked a direct question about the 0.7
rule and the repo was grepped.

**The rule this implies:** these handoffs contradict each other by design — they are a record of
decisions being made, reversed and re-made. A later file does not supersede an earlier one unless it
says so explicitly. Reading three of four and reasoning from the gaps produces confident, wrong advice.

---

## What this session was for

The six packets were declared complete and the request was to build the pages two raters would use
to score them, with the scoring form attached to each packet rather than centralised, so raters
cannot compare companies against each other.

That request was correct and is now built. Two blockers were found underneath it, and one settled
decision was wrongly reopened.

---

## Finding 1 — the packets were never anonymized

Section 1 of all six packets is full of company names, live URLs, executive names, product names and
near-unique self-descriptions. **Section 4 of each packet is titled "ANONYMIZATION PRE-FLAGS" and is
exactly that — a list of what to scrub. P-01's ends with the words "Flagged, not resolved."** No
anonymization had been executed on any packet. Had the rater pages been built from the packets as
they stood, every company would have been identifiable on the first line.

## Finding 2 — by the RUN_CARD's own stopping rule, v4.6 did not freeze

`RUN_CARD.md`: *"Zero structural defects → v4.6 freezes. One or more structural defects → revise,
bump the version."*

P-01, P-02, P-04 and P-05 each self-report **six** structural defects. All six packets ran with
**one retrieval method** — the JavaScript renderer was never connected in any build. Every "could
not be reached" finding across all six packets is therefore a one-method finding, and decision 2 of
the 08-13b handoff is explicit: all six get rebuilt under the final prompt version before any rater
sees them.

Sebastian's call, made this session: **connect the renderer and rebuild all six.** Not yet done.

A distinction worth carrying forward: the defects split into those that changed *what is in Section 1*
(one-method builds, 80%/60%/40% truncation) and those that are *prompt ambiguities* invisible to a
rater. Only the first class blocks scoring.

---

## What was built

### `ground_truth/anonymization/` — the scrubbing pass

| File | State |
|---|---|
| `ANONYMIZATION_RULES_DRAFT.md` | Ruleset R1–R8 plus judgment calls. **Draft, JC-2/3/4 open.** |
| `P-01_packet_RATER_DRAFT.txt` | Done. Rename to `P-01_packet_ANON.txt` for consistency. |
| `P-02_packet_ANON.txt` | Done |
| `P-03_packet_ANON.txt` | Done |
| `P-04_packet_ANON.txt` | Done — heaviest scrub of the six |
| `P-05_packet_ANON.txt` | Done |
| **P-06** | **NOT DONE. Section 1 is lines 19–131 of the source packet; pre-flags at line 456.** |
| `_STATE.md` | Where the pass stopped and what needs deciding |

**Governing principle adopted: scrub identifiers, not signal.** Two threats were being bundled.
Recognition from memory (T1) is not fixable by scrubbing and is what the recognition flag exists for.
Lookup by search (T2) is fixable by deleting URLs and forbidding search. Rewriting a quote body fixes
neither, breaks the citation-verification harness that both humans and the LLM depend on, and deletes
the culture signal — the most identifying strings are usually the most dimension-bearing ones.

### `ground_truth/rater_app/` — the scoring pages

* `anchors.json` — every word Julie will rewrite lives here. Swap it, rerun the script, pages
  regenerate. The generated page stamps a hash of the anchor text so any score row traces to the
  exact anchors it was produced under, same reasoning as `model_run`.
* `build_rater_page.py` — generator. `python build_rater_page.py --packet <anon file> --packet-id P-0X --rater A --out ./out`
* `out/P-01_raterA.html`, `out/P-01_raterB.html` — generated examples, tested end to end in a headless DOM.

What the page enforces rather than requests:

* **One packet per file**, no cross-company view — scores are absolute positions on a scale shared
  with the person side, not a ranking of these six.
* **All six dimensions visible, scored in any order, each locking on commit.** Changed mid-session at
  a rater's request: they wanted to read the packet once rather than six times. The lock survives, so
  the six scores cannot be retro-tuned into a coherent profile. **Known cost, accepted deliberately:**
  a single overall impression will correlate the six scores, so a wide gap between raters cannot be
  cleanly attributed to anchor ambiguity rather than to one rater's read of the whole company.
* **Click-to-cite, multi-tag.** Evidence is selected from the packet, never typed, so every quote
  string-matches by construction. Commit is disabled without at least one citation. Yields a
  per-rater quote→dimension matrix as a by-product.
* **Locks on submit.** Reopening shows "already submitted." Prevents revisiting P-01 after reading P-05.
* **Records** session start, per-dimension commit timestamps, commit order, total duration,
  recognition (recognised / suspected / no idea, plus what gave it away), and an explicit
  "did you search" question.

Scores are the five band values **0.1 / 0.3 / 0.5 / 0.7 / 0.9**. A fourth confidence band was added
("Very low") — the rubric's lowest was 0.2–0.4 and nothing covered "almost nothing in the packet
bears on this."

---

## Decisions made this session

1. **Deliverable is a self-contained HTML page per packet**, packet text and scoring form together.
2. **Five bands, not continuous 0–1.** Consistent with the 08-10 note that five bands create a 0.5
   middle band ambiguous without dispersion.
3. **Counterbalanced order** — one rater P-01→P-06, the other reversed, so calibration drift over a
   multi-day sequence does not land on the same companies for both.
4. **Rebuild all six packets with the renderer connected.**
5. **Anonymization pass run by hand now, to produce the RULESET**, which folds into v4.7 so Section 1
   is born clean and the manual step leaves production.
6. **JC-1 decided: distinctive verbatim self-descriptions stay.**
7. **Blind re-score DEFERRED, not dropped.** Rationale: rater *offset* is already recoverable from the
   existing design (six companies, compare each rater's mean deviation — the per-run mood analysis
   applied to people). Rater *noise* is what the re-score buys, and it is only needed if gaps come
   back wide enough that anchors are about to be rewritten. Ask for it then, from raters who know the
   job takes forty minutes.

## Decisions REVERSED this session — read the reasoning before touching either

**A. P-05 stays in the ground-truth set.** It was recommended for removal on the grounds that it
cannot be anonymized — fully remote, bootstrapped, async-first, uses its own product internally, zero
open roles, zero reviews. That was wrong: *cannot be anonymized* does not imply *should be removed*.
Anonymization is a test instrument; citation verification is the production control. Positive reasons
to keep it: it is the only stage 1–2 company in the set (Akuna the only stage 3), and `stage_size` is
the largest confounder — a calibration set with no variation in it cannot calibrate. The 08-10 handoff
independently flags "Doist carries three anchors alone" as concentration risk, which is an argument
for care, not removal.

**B. The rater plan is REOPENED and must be decided deliberately.** See the warning at the top.

---

## The rater question — current state, undecided

**What 08-10 settled:** keep Julie, drop the blindness claim entirely, control by citation, recognition
Y/N recorded as data. Four reasons against naive raters were recorded:
1. Selecting for ignorance selects for low judgment; two naive raters can agree because they misread
   the same way, and the Agreement tab cannot tell that from a well-specified anchor.
2. It breaks LLM validation — if the humans read worse than the model, the comparison measures the raters.
3. It removes the expert from the instrument she has to fix.
4. It does not generalise — a production scraper always knows the company, so a control requiring an
   ignorant rater has no production analogue.

**What changed since, and is now known:**
* Two raters are available where before there was a recruiting constraint.
* Both are **lawyers with 30+ years' experience**, and **both have already completed a pilot exercise
  whose scores mapped close to expectation.** This substantially defuses objection 1 — they are not
  selected *for* ignorance; they have high general judgment and happen to lack company knowledge.
  Close document reading, separating what a text says from what it wants you to believe, and applying
  a written standard to facts are the job.
* Objection 3 no longer applies if Julie writes the anchors — that puts her judgment in the instrument
  permanently rather than in six score rows.
* Objection 4 argues about which control you rely on, not about who rates. The citation control is built.
* Objection 2 is the one that still stands and is empirically open.

**Caveat on the pilot result:** "mapped close to expected" is a check against Sebastian's expectation,
which is itself unvalidated — the single-rater problem one level up. What it does establish, which is
what was needed, is that the rubric is usable by a careful reader without domain background.

**Standing recommendation: use all three.** Two lawyers as the primary pair, Julie as a third set on
the same six packets, recognition recorded for all three. Lawyer-vs-lawyer holds the reading lens
roughly constant, so those disagreements approximate pure rubric ambiguity — which is what the >0.15
rule is meant to detect and currently cannot isolate. Julie-vs-lawyers varies the lens deliberately and
measures what expertise and prior knowledge contribute, a number worth having before the LLM enters as
a scorer. Two raters of any kind give one number with three possible causes.

**NOT YET DECIDED.** Do not treat the recommendation as adopted.

---

## Corrections to things asserted earlier in this session

* **The ≤0.7 rule is a MEASUREMENT, not an enforced cap.** Settled in 08-10 decision 3: one score per
  dimension plus a flag for whether non-company-authored evidence supports it. Enforcing it as a
  ceiling was explicitly rejected because it would compress every small private company toward the
  middle — the shrink-toward-0.5 failure through another door. This session described it as a ceiling
  and built an argument about P-05 "capping out" on that basis. **That argument is void.**
* Banding was flagged as a risk to person↔company scale calibration. On inspection it is not — coarser
  company measurement does not invert or rescale the poles, and given the measured scorer SD of ~0.098,
  resolution finer than one band is fictional.

---

## Open questions, in rough priority order

1. **The rater plan.** Two lawyers, or three including Julie? Blocks everything downstream.
2. **JC-2 — does Section E survive?** P-04 is the packet to decide it on: fully scrubbed, its Section E
   still reads as an agency sold by its long-time holding-company parent to private equity in a
   management buyout, then acquiring an AI design studio. Instant identification for anyone in that
   trade, near-zero dimension signal. Against dropping it: the ownership change is the single most
   important fact for reading Section B, because every review predates it.
3. **JC-3** — does the scrubbed file become the canonical packet? It must, if humans and the LLM are to
   score the same bytes for citation verification. Assumed yes; confirm, because it changes what "the
   packet" means in every other document.
4. **JC-4** — the scope declaration names the sector ("a health insurer"). Assumed harmless and kept.
5. **Does employee-bylined writing on a company-run publication count as "company-authored"** for the
   0.7 flag? P-05's Section D is entirely this. Affects the flag's accuracy, not the score range.
6. **Confidence definition** — still open from 08-10, and the rater pages now ask for it.

## Rules that must go into v4.7 before the rebuild

* The scrubbing ruleset (R1–R8) so Section 1 is born anonymized.
* **A named-clients rule.** P-04 quotes a review naming a major client. No previous packet had one and
  the prompt has no rule. A generic descriptor was substituted.
* **A↔F double-counting must key on the CLAIM, not the sentence.** DEF-5's rule caught P-01's seven
  value names but missed a reworded restatement of the mission appearing in both Section A and the
  10-K. Not an identification problem — the rater reads a careers page and a legal filing as two
  independent voices when it is one claim in two costumes, manufacturing false triangulation inside
  the company-authored layer.
* **Figure-stripping must cover Section E, not just Section F.** Section E carried "$60 million in
  administrative cost savings" and "a $137 million third quarter loss" with no protection.
* **`[the company]` substitutions need harness support** — the citation-verification harness must
  normalise the token before string-matching or every quote containing a substitution fails.

## Inconsistencies introduced by the scrubbing pass — flagged, not hidden

* Third-party developer tool names were **generalised in P-05** and **retained in P-03**. Both
  defensible in isolation; pick one rule.
* Two equipment-allowance dollar figures were **retained in P-05** after figures were stripped from
  P-02's Section E. Rationale: not identifying alone, and the only pay-posture signal in that packet.
* "enrich lives through technology" retained in P-02 under JC-1, but it is the strongest candidate for
  a single JC-1 exception — a trademarked purpose statement, not a description of how people work, so
  removing it costs almost no dimension signal.

---

## Immediate next steps

1. **Read handoff 08-10 in full.** Everything else waits on it.
2. Decide the rater plan.
3. Scrub P-06 — the only packet left. Ruleset and five worked examples are in place.
4. Adversarial re-identification check on all six: search every retained distinctive phrase and
   preserved typo, confirm no name/URL/product/executive survives, confirm quotes still string-match.
5. Connect the renderer, fold the new rules into v4.7, rebuild all six clean-room per the RUN_CARD.
6. Regenerate rater pages against the rebuilt packets — the generator makes this a swap-in.
7. Write rater instructions and the counterbalanced schedule.

## Untouched, still open from prior handoffs

1. Re-run the scorer variance test on a stronger model against the pre-registered bar.
2. Re-run the blind-vs-identified test at n=5 per condition.
3. The correction owed to Julie on the confidence claim.
4. Build the citation-verification harness.
5. Bias-test the 24 assessment items; write `assemble_training_data(db)`.
