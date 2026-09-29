# Pre-registration: round 2, the LLM scorer against human judgement

**Written 2026-09-29, before any round-2 scoring, rating or API call.** Nothing in this file
may be edited after the first round-2 score exists, except by a dated addendum that says what
changed and why. The rater question (the last section) is Sebastian's and is **open**. Sections 1-9
hold whichever way it is answered; the last section says what each answer changes.

**Instrument:** `anchors_v3_1_PROPOSED.json` (`v3.1-PROPOSED-2026-09-29`), rater-page anchors
hash `3e270b206116`. If Julie's confirm sheet changes the wording before round 2 starts, the
version and hash change, and this file gets an addendum naming the new ones. **No round-2 score
may be taken under two different rubric texts.**

**Round 1 is not part of this.** P-01..P-06 were scored under v1-frozen-2026-08-15 and are never
rescored or pooled with round 2. They are a different instrument, so they are not the same
question. That rules out the tempting shortcut of using Julie's round-1 scores as the first half
of a test-retest pair (section 4).

---

## 1. What round 2 is for

The goal is to decide whether the LLM scorer can stand in for human raters, so that humans
become a spot-check. It can do that if it agrees with the human reference **at least as well
as the reference agrees with itself or with other humans**. Beating a perfect standard is not
required; nobody meets that, and round 1 showed two careful humans at Pearson -0.195.

## 2. Units, scale and the skip

- **Cell** = packet x dimension. Six dimensions per packet.
- **Scores are integer band indices 0-4** (0.1 -> 0 ... 0.9 -> 4), compared as integers per
  D-12(a). No float thresholds anywhere.
- **Insufficient evidence** (a skip, human or LLM) has no band. A cell where either side of a
  comparison skipped is excluded from that comparison's distance, and is counted.
- **Packets:** only packets `Scripts/verify_scrub.py` has PASSED, re-run on the day each is
  first used. Candidates are P-07..P-13 now and P-14..P-19 as the pipeline delivers. Each
  packet's collector version (v4.6-v4.11) is recorded and reported per packet. The version is
  not a stratification variable, since the counts are too small.

## 3. The LLM side

- Model and settings as `causal_graph/scorer_pipeline.py` ships them on the run date
  (`gpt-5.5-2026-04-23`, reasoning_effort medium, temperature 1.0), with
  `allow_insufficient_evidence=True` under v3.1.
- **D-21: three independent draws per packet**, with per-cell dispersion reported (SD over
  draws, and the count of cells whose band differs between draws).
- **The LLM's cell value is the median band of its three draws.** Three draws make the median
  exact. If two or more draws abstain, the cell is an LLM skip. If exactly one abstains, the
  cell value is the lower band of the two scored draws. That rule is fixed now and is
  deliberately conservative toward the floor, because the floor bias is the known failure.
- Citations go through `verify_result`. An unverified citation is reported, and never
  counted as evidence.
- **Cost gate:** calls = packets x 3. The number and an estimated cost go to Sebastian before
  the run, and nothing runs without his go-ahead.

## 4. The human side, and the ceiling

Per the answer to the rater question (last section), one of:

- **(a) Two or more blind raters per packet.** Ceiling = the mean human-human distance
  d(r_i, r_j) over rater pairs on each packet. D-12(b) stands: Julie, if she also rates, is
  the expert reference and outside the blind ceiling.
- **(b) Julie as the sole reference, plus test-retest.** Ceiling = d(Julie_t1, Julie_t2) on
  **k repeated packets**, rated at least three weeks apart, under the **same** rubric version
  and hash, on **byte-identical** packet files. The retest packets are chosen now, by rule:
  the first k packets she completes, with k = 3.
- **(c) No human reference.** No ceiling and no finish line. Section 6 still reports the
  LLM-only statistics.

## 5. The finish line: pre-registered, primary

**Like-for-like, or not at all.** The LLM is compared with **one human reading at a time**,
exactly as humans are compared with each other. It is never compared with a median, a mean or
a consensus of humans. A median of two readings sits closer to any third value by
construction, so "LLM vs human median" and "human vs human" are different quantities.
**Round 1's "mean |LLM - human median| = 0.114" is therefore NOT evidence that the LLM beat the
humans, and must not be quoted as such.**

**Primary metric: mean absolute band distance** over cells where both sides scored.

- (a): `D_llm` = mean over cells and over raters r of d(LLM, r). `D_ceiling` = mean over cells
  and over rater pairs of d(r_i, r_j).
- (b): `D_llm` = mean over cells of d(LLM, Julie_t1). `D_ceiling` = mean over the k retest
  packets' cells of d(Julie_t1, Julie_t2). The t1 reading is used everywhere, so the LLM is
  never compared with a reading she made after seeing her own earlier scores.

**Secondary:** the exact-band agreement rate, computed the same way.

**Uncertainty: cluster bootstrap over PACKETS**, 20,000 resamples, seed 20260929. Each
resample draws packets with replacement, and every cell of a drawn packet comes with it. S-48
showed cells within a packet are not independent, and treating them as independent inflates
the false-positive rate to 0.35-0.49.

- Under (b) the two means come from different packet sets (all packets vs the k retest
  packets), so they are bootstrapped independently and the difference is taken per resample.

**The finish line is met when BOTH hold:**

1. The 95% CI for `D_llm - D_ceiling` has its upper bound **below +0.25 bands**. That is the
   non-inferiority margin: the LLM may be at most a quarter band worse than the humans'
   own agreement.
2. **Coverage guard.** The share of cells the LLM scored (did not skip) is no more than **10
   percentage points below** the reference's share. Without this, an LLM could buy agreement
   by abstaining on exactly the hard cells.

**If the CI straddles the margin, the result is INCONCLUSIVE, not a pass.** That is the
expected outcome at this sample size (section 8). The 0.25 margin and the 10-point coverage
guard are fixed by this document. Changing either after data exists is a new decision for a
future round, never a retroactive one.

## 6. Pre-registered secondary checks

**Floor bias (the round-1 failure).**

- Report the LLM's 0.1 usage over all cells and draws, alongside the reference's 0.1 usage.
- For every cell the reference places at 0.1, report the LLM's band.
- **Pre-set reading:**
  - "floor bias persists": the reference uses 0.1 on at least 3 cells and the LLM uses 0.1 on
    none of them.
  - "floor bias reduced": the LLM uses 0.1 on at least half of the reference's 0.1 cells.
  - Anything between those is "unresolved".
- The extremity flag stays a review queue, never an auto-gate, whatever this shows (as
  already pre-registered in PREREG_COMBINED_RUN_2026-09-01b).

**Skip agreement.** A 2x2 of LLM skip vs reference skip over all cells, plus skip counts by
dimension. It is descriptive only. Feedback is expected to carry the most skips, because it
came back THIN in 8 of the first 10 packets.

**Per-dimension distances**, descriptive only. There is no per-dimension pass/fail: with n
packets, each dimension's CI is too wide to act on.

**LLM draw-to-draw dispersion** (D-21), reported beside everything above.

## 7. The equivalence gate: before any disagreement is called "noise"

This follows the CLAUDE.md rule from 2026-09-17: a check that disagrees with an expert is first
a claim about the check. **Before any disagreement between two readings is attributed to rater
unreliability or model error, confirm the two readings answered the same question:**

1. **Same packet bytes.** The packet file's sha256 is recorded with each reading and must match.
2. **Same rubric.** The `anchors_hash` in the rater JSON, or the `rubric_version` on the scorer
   run, must match.
3. **Same construct.** For every REVIEW cell (two or more bands apart), the two readings'
   citations are put side by side. If they cite different excerpts for different constructs,
   the finding is **construct routing** (S-58), not noise, and is reported as such.
4. **Test-retest only:** the retest is not re-framed. The same page, the same instructions,
   and no reminder of her earlier scores.

A disagreement that fails any of these is reported as "not comparable", never pooled into
the finish-line statistic.

## 8. Honest power line

With 7 packets (P-07..P-13), or even 13 (to P-19), this is **below S-48's N≈15-19**. The
likely result is **INCONCLUSIVE**, and that is recorded here so it cannot be read later as the
LLM "failing". Under (b) the ceiling rests on k = 3 retest packets (18 cells), so its CI will
be wide. Under (a) it depends on how many packets volunteers actually complete.

## 9. What this does NOT license

- **Fitting a calibration map.** The isotonic harness exists and will refuse to fit on fewer
  than **15 packets with a human reference**, the lower end of S-48's range. Round 2 alone will
  not reach that.
- Changing band values, the D-12 rule, or the anchors in response to round-2 results within
  round 2.
- Rescoring P-01..P-06 under v3.1.

---

## Open for Sebastian: the rater question (not decided here)

| option | ceiling it gives | what it costs | the catch |
|---|---|---|---|
| **(a) new blind raters (volunteers)** | human-human: the standard D-12 was built for | recruiting; each packet took round-1 raters hours, and two per packet is the minimum | volunteers drop out, and a packet with one rater has no ceiling. Round 1 showed blind lawyers at Pearson -0.195, so the ceiling may be low, which makes the finish line easy to meet and weak |
| **(b) Julie alone + test-retest** | Julie vs her own earlier reading | Julie's time: one packet per sitting, async, about 10 packets plus 3 retests weeks apart | she recognised 3 of 6 companies in round 1 and wrote the anchors, so this validates the LLM against the author's reading, not a naive reader's. Memory of her own scores inflates her consistency, which makes the finish line HARDER for the LLM. D-12(b) excludes her from the ambiguity flag on authorship grounds, and using her as the validation reference is a different use you would need to confirm |
| **(c) defer humans; LLM only on P-07..P-13** | none | 21 calls (7 packets x 3), cost quoted before running | scores without validation. Only the section-6 LLM-only statistics (floor usage, abstention rate, dispersion) are available |
