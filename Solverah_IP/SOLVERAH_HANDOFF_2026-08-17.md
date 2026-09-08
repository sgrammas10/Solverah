# Solverah — Session Handoff, 2026-08-17

**Topic: corrected re-run of the S1-4 variance cell (gpt-5.5 x real anonymized packets x
frozen rater instrument), two packets deep. Result: real, but narrower than it first looks.**
Custom instruction to honor: be logical and future-thinking, do not be agreeable — push back.

Sits on top of `SOLVERAH_HANDOFF_2026-08-15b.md` (raters unblocked, 18-page grid built) and
`causal_graph/SPRINT_SCORER_PIPELINE_01.md` (ON HOLD since 2026-08-09; this session did not
lift that hold — see scope note below).

---

## Why this ran

Sebastian asked what to do while the three raters (two lawyers + Julie) work the 18-page
grid. He is deliberately not a fourth rater — see the reasoning in this session's chat, same
shape as the "Julie writes the anchors after round 1" argument: not blind, built the packets,
can't be an independent read. Picked up the oldest untouched open item instead: **re-run the
scorer variance test on a stronger model**, carried unresolved since the 2026-08-07 session.

## Correction made before running anything

The naive move — swap the model string in `causal_graph/scorer_variance_test.py` and rerun —
would have reproduced the exact confound `SPRINT_SCORER_PIPELINE_01.md` correction #5 already
flagged: that script hard-codes rubric v2.1 (continuous 0–1) and the retired v3 GT-01 thin
packet (~2,880 chars). Swapping only the model measures tier on an instrument nobody uses
anymore.

Fixed by building `causal_graph/scorer_variance_test_v2.py`, which uses:
* **Rubric from `ground_truth/rater_app/anchors.json`**, `rubric_version: v1-frozen-2026-08-15`
  — the actual frozen instrument the three human raters are scoring against right now.
  Discrete 5-band (0.1/0.3/0.5/0.7/0.9), not continuous — response schema is enum-constrained
  to match, not free-floating.
* **Real anonymized packets** — `ground_truth/anonymization/P-0N_packet_ANON.txt`, Section 1
  only (between the `SECTION 1` and `END OF PACKET` markers — exactly what a rater sees, scrub
  log excluded). The extraction refuses to guess at the boundary if the markers aren't found,
  on purpose — this is the same shape as the rater-app scrub-log leak bug from 08-15b.
* **Pinned model**: `gpt-5.5-2026-04-23` (exact snapshot, not the `gpt-5.5` alias),
  `reasoning_effort: medium`, recorded on every row.
* **Temperature honored, checked, not assumed.** The design constraint from the sprint doc —
  near-zero variance from an ignored temperature is not the same finding as near-zero variance
  from a better model — is enforced in code: the script attempts `temperature=1.0`, catches a
  `BadRequestError` if the API rejects it, retries without, and stamps
  `temperature_honored: False` on every row from that run if it had to fall back. **Confirmed
  `True` on both runs below** — this specific confound is ruled out for this model.

**Explicit scope decision, Sebastian's call, 2026-08-16**: run the single new cell only
(stronger model × real packet × frozen anchors), not the full 2×2 the sprint doc specs (which
would also need the old model rerun on the new packet, and the new model on the old packet, to
separate model tier from packet richness). **That means model, packet, and rubric/schema all
changed simultaneously relative to the original gpt-4o baseline in `runs.csv`. Nothing below
isolates model tier as the cause of anything on its own.**

A near-miss caught and fixed mid-session: the first version of the script hard-coded the P-01
packet path and the output filenames (`runs_v2_gpt55_P01.csv`). Sebastian hand-edited the path
to point at P-02 without changing the output name — which would have written P-02 data into a
file still labeled P01. Fixed with a `--packet` flag; every output file and raw JSON record now
carries both the packet ID and the model tag. **The original P-01 run (below) predates this fix
and is saved as `runs_v2_gpt55_P01.csv` / `raw_v2_gpt55_P01/` — no model tag in the name.
Housekeeping fossil, not a data error; left as-is.**

---

## Results — two packets, n=5 each

### P-01 (Oscar Health, anonymized)

```
SCORE            mean    sd   range
autonomy        0.300 0.000  0.000
pace            0.700 0.000  0.000
collaboration   0.700 0.000  0.000
feedback        0.580 0.110  0.200
innovation      0.540 0.089  0.200
decision        0.700 0.000  0.000
```
Mean score SD = 0.0332. Mean confidence SD = 0.0274.
Per-run mood effect (deviation across all 6 dims, by run): +0.047 / −0.020 / −0.020 / +0.013 /
−0.020. **Spread 0.0667.**

### P-02 (Best Buy, anonymized)

```
SCORE            mean    sd   range
autonomy        0.300 0.000  0.000
pace            0.700 0.000  0.000
collaboration   0.700 0.000  0.000
feedback        0.420 0.110  0.200
innovation      0.300 0.000  0.000
decision        0.580 0.110  0.200
```
Mean score SD = 0.0365. Mean confidence SD = 0.0224. Largest single-cell SD: decision
confidence, 0.134 (a 4-Low/1-Medium split; the one Medium run also carried the one 0.7 score).
Per-run mood effect: 0.000 / −0.033 / 0.000 / 0.000 / +0.033. **Spread 0.0667.**

Data: `causal_graph/runs_v2_gpt55_P01.csv`, `causal_graph/runs_v2_gpt_55_2026_04_23_P-02.csv`,
raw per-run JSON in the matching `raw_v2_.../` directories.

---

## What this does and does not establish

**Both means sit at or near the pre-registered "good" bound (SD ~0.02–0.03) from
`SPRINT_SCORER_PIPELINE_01.md` §5.** But the pre-registered bar assumed a roughly uniform SD
across dimensions, matching the shape of the original gpt-4o run (0.055–0.130, nothing near
zero). Neither result here is uniform — both are four dimensions at exactly zero averaged
against two dimensions wobbling a full band. The mean threshold reads as cleared; the
assumption behind the threshold does not hold. Treat the headline number as misleading on its
own.

**"Four dimensions stabilize" is not a property of the model — it's packet-conditional.**
P-01's solid four: autonomy, pace, collaboration, decision. P-02's solid four: autonomy, pace,
collaboration, innovation. Decision went from perfectly stable (P-01) to the least stable
single cell measured in either run (P-02). Innovation went the other way. **No dimension has
yet proven safe to single-run — the unstable pair changes company to company, and there's no
way yet to predict which two a given company will land on.**

**Feedback is the one dimension that failed on both packets.** SD 0.110 in both — identical to
three decimals, but this is arithmetic, not a deep signal: any 3-2 split between two adjacent
0.2-apart bands at n=5 produces SD≈0.1095 regardless of which values are involved. Do not read
significance into matching SD figures without checking the underlying score distribution — it
nearly happened while writing this up.

**What is a real signal on feedback: confidence stayed pinned at Low (0.3) on every single run,
in both packets, even as the score flipped.** That is the instrument working, not failing — the
model consistently recognizes this dimension's evidence as thin and hedges accordingly, it just
can't converge on which side of a genuinely ambiguous read to land on. Reads as an
anchor-ambiguity or genuine-evidence-ambiguity signature. Worth checking against the human
Agreement tab once rater scores land: if feedback is also where the three humans disagree most,
that's convergent evidence the anchor wording is the weak point, not the model.

**The strongest result, and the one worth leading with: the per-run mood effect replicated
exactly.** Spread of 0.0667 on P-01, spread of 0.0667 on P-02 — same magnitude, two independent
companies, against gpt-4o's original 0.22 (`SOLVERAH_HANDOFF.md`, Test 2, 2026-07/08-07
session). That's the specific correlated-severity-shift failure that broke Test 1's confidence
argument, tightened by roughly 3.3x, and it held twice. More defensible than any single
per-dimension SD number in this dataset.

**Still not enough to license single-run-per-company scoring.** A different dimension misfires
on every company tested so far, and there's no basis yet for predicting which one in advance.
Keep mean-of-5 as the working aggregator, per the 2026-08-09 sprint doc's own median-vs-mean
finding (mean beats median at every n on this lattice, and by more as n grows).

**Model tier remains unisolated.** Model, packet, and schema all moved at once relative to the
gpt-4o baseline. The mood-effect replication is suggestive of a real model-tier effect because
it held across two different packets while everything else about those packets differed — but
the sprint doc's specced 2×2 was deliberately not run this session, so this is evidence, not
proof, that tier specifically is doing the work.

---

## Open / next

1. **Feedback anchor check against human Agreement data**, once the three raters' P-01 and
   P-02 files come back. If humans also disagree most on feedback, rewrite that anchor first —
   independent of anything the LLM scorer does.
2. **Decision dimension has no track record yet outside these two packets** — solid on one,
   the wobbliest cell measured on the other. Do not generalize either direction from n=2.
3. **The full 2×2 from `SPRINT_SCORER_PIPELINE_01.md` is still undone and the sprint is still
   ON HOLD.** This session's result narrows the case for resuming it (the mood-effect
   replication is a genuine data point) but does not resolve the hold on its own — that's
   Sebastian's call, not a technical trigger.
4. **Third packet not yet run.** P-05 was offered (smallest/thinnest packet, good stress test)
   and declined for now in favor of logging at n=2. Revisit if/when useful.
5. Carried and untouched from prior handoffs: re-run the blind/identified test (Test 1) at n=5
   per condition; the correction owed to Julie on the confidence claim; bias-test the 24
   assessment items; write `assemble_training_data(db)`; find or reconstruct
   `Solverah_Ground_Truth_Roster_v2.md` (still missing per 08-15b item 5).

---

## Framings that survived pushback this session

* **"Four dimensions stabilize" is not a model property — it's packet-conditional.** Which four
  differs completely between the two packets tested. There is no currently-safe dimension.
* **A dimension's SD can match another's to three decimals purely from discrete-band
  combinatorics.** A 3-2 split of adjacent 0.2 bands at n=5 always gives SD≈0.1095. Don't infer
  meaning from matching SD values without checking the score distribution underneath.
* **Stable low confidence plus an unstable score is a coherent thin-evidence signal, not
  contradictory noise.** Feedback's behavior on both packets is the instrument doing its job.
* **A result replicating exactly across two independent, otherwise-different packets is stronger
  evidence than a single packet's full table.** The mood-effect spread matching at 0.0667 twice
  carries more weight than either packet's per-dimension SD column on its own.
* **Averaging a bimodal distribution into one mean SD hides the finding.** Both packets' means
  cleared the pre-registered bar; neither packet's actual shape matches what that bar assumed.
