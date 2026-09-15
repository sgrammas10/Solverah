# Pre-registration — the 22-call combined run

**Written before any call is made.** Two independent arms, one local sitting.
Script: `Solverah_IP/analysis_s58/s58_combined_run.py`. Nothing is written to the Solverah repo;
the repo is read-only on `sys.path` and the script refuses to start if its output path resolves
inside the repo.

---

## Arm A — S-59: flag fire rate under the settled probe (~16 calls)

**What changes vs. the 12% baseline: the probe, and only the probe.** Arm A reuses the SAVED v1
citation data (`all_dims_evidence_2026-09-01.json`) rather than re-scoring, so citations are held
constant and the measured difference is attributable to `ForcedChoiceBandProbe(allow_off_axis=True)`
replacing `LLMBandProbe`. Cells with score <= 0.5 are probed, matching `run_flag_sweep.py`'s cost
control.

**Pre-registered predictions**, from `FLOOR_BIAS_WORKAROUND_2026-09-01.md`:
- **P-06/autonomy still fires** (all three citations matched under the boundary test).
- **P-06/feedback stops firing** ("mid-year touch points and formal end-of-year discussions"
  correctly lands on 0.3 under forced choice + escape).
- Overall fire rate is expected to fall, since the settled probe scored 9/13 on category A against
  the binary probe's 12/13. A rate ABOVE 12% would contradict the boundary test and is the result
  that would need explaining.

**Decision rule, fixed now — this is the important one.** The standing verdict is **review queue,
not auto-gate**, and **no fire rate produced by this run changes it.** A low rate is not evidence of
precision; it is evidence of selectivity. Precision requires adjudicated ground truth on the fired
cells, which does not exist and cannot be created (no rater time). If this run returns 0/16 or 4/16,
the verdict is identical. **Nothing here licenses auto-quarantining a company.**

**What a 0/16 result would mean:** the flag under the settled probe never fires on this sample,
which makes it useless as a triage signal on six packets and is worth recording as such — not worth
re-tuning the probe to make it fire, which would be fitting the instrument to the desired answer.

---

## Arm B — S-12 gate: does the v3 anchor edit move the extractor at all? (6 calls)

**The intervention is strictly stronger than the one that produced the Decision no-op.** That test
changed guardrail PROSE only. `anchors_v3_PROPOSED.json` now additionally changes Feedback's **0.1
and 0.3 BAND TEXTS** and adds a Feedback guardrail to Collaboration. If band text does not move the
extractor either, "anchor edits are inert for this model" is a much better-supported claim than it
was this morning.

**Primary outcome (descriptive):** within-packet cross-dimension passage reuse — the count of cited
passages filed under two or more dimensions — v1 vs v3, overall and broken out for
**collaboration<->feedback** (newly guarded) and **autonomy<->decision** (guarded this morning).

**Secondary:** per-dimension mean |v3 score − v1 score|, and per-dimension citation turnover
(fraction of v3 quotes not present in v1).

**D-21 APPLIES AND IS NOT SATISFIED. Arm B is a PILOT and no number from it may be quoted.**
One draw per packet per arm; D-21 requires >= 3 independent draws, paired where arms are compared,
with dispersion reported. A compliant version costs 36 calls (3 draws x 6 packets x 2 arms) and is
not what is being run. **Consequence, fixed now:**
- The only outcome that can be acted on from a pilot is the **qualitative null** — nothing moves at
  all, on any packet, on any dimension. That is what the Decision test found, and a null needs no
  precision to be informative.
- **If anything DOES move, that triggers a properly seeded follow-up, not a claim.** Do not write a
  moved number into STATE, a handoff, or anything Julie reads.

**Three pre-registered readings:**
- **Collisions drop** -> the anchor text is a live lever on the extractor; v3 has empirical support
  for the first time. Seed it properly before quoting anything.
- **Scores static, citations move** -> the rewrite changes what the model looks at without changing
  what it says. Reframes the Decision no-op, which only ever measured scores.
- **Neither moves** -> anchor prose AND band text are inert for the extractor. The only remaining
  lever is human raters, and human raters are permanently unavailable. **S-12 then becomes a request
  for Julie's expert judgement with no empirical component at all, and she should be told exactly
  that when the file is handed over.**

**Confound recorded, not controlled:** v3 also carries the previously validated Collaboration and
Innovation band-bleed fixes and the unvalidated Decision rewrite. A movement on those dimensions is
not attributable to this session's Feedback edit. Only feedback and collaboration are clean tests of
today's changes.

---

## What neither arm can do

Neither validates the rubric for human raters. Carolynn and George are permanently unavailable,
there is no budget for paid raters, and Julie is excluded on authorship grounds (D-12(b)). Arm B
measures one LLM's sensitivity to anchor text. That is the only empirical lever left, and it is a
weak proxy for the thing that actually matters.
