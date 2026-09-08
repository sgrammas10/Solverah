# STATE.md edits — draft for review, 2026-09-01b

Paste-ready blocks. Nothing here has been applied to `claude/STATE.md`.

**REVISED 2026-09-01b (second pass), after Sebastian's three answers.** Blocks 5, 7, 8, 9 and 12
changed. Two claims in the first draft were checked and did not survive: the evidence-weighting fix
for S-15 (inert), and the collection-rule explanation of Feedback-THIN (disconfirmed). Both are
retracted below rather than quietly edited. **S-60 is assigned; S-61 is withdrawn before opening.**

---

## 1. §0 "How this file works" — the S-58 bullet

**REPLACE:**

> - **A labeller's judgement about band membership is evidence, not ground truth** (S-58, new
>   2026-09-01). Four independent labellers — two lawyer raters, the agent, and one LLM probe
>   design — have now each drifted the same direction on the same construct. Do not treat any
>   single labelling pass, including a careful one, as settling what a band means.

**WITH:**

> - **A labeller's judgement about band membership is evidence, not ground truth** (S-58, new
>   2026-09-01, premise corrected same day). Four independent labellers have now each mis-applied
>   the same band on the same construct — but **not in the same direction**, and the original
>   wording of this rule said they did. The blind raters and the extractor move *away* from the
>   floor; the agent's hand labels and the binary probe move *toward* it. What they share is a
>   **criterion** — band membership judged on valence rather than posture — across two different
>   task shapes. Do not treat any single labelling pass, including a careful one, as settling what
>   a band means, and do not restate this as a shared direction.

---

## 2. §2 Artifact inventory — ACTIVE, four new rows

| artifact | what it is | since |
|---|---|---|
| **`S58_FREE_ANALYSES_2026-09-01b.md`** | **NEW 09-01b.** The free half of S-58, run. Corrects S-58's "same direction" premise; records analysis (i) as a pre-registered NULL; adds the confidence/reliability decoupling and the passage-collision measurement; documents the v3 Feedback contradiction and the re-scoping of analysis (ii). Project + `Solverah_IP/analysis_s58/`. | 09-01b |
| **`PREREG_S58_2026-09-01b.md`** | **NEW 09-01b.** Pre-registration for the above, written before any statistic was computed, including the analyst's own hand labels on the six 0.1 band texts and the n=6 power warning that stopped a packet-effect correlation being read as evidence. Project + `Solverah_IP/analysis_s58/`. | 09-01b |
| **`analysis_s58/s58_free_analyses.py`, `s58_mechanical_checks.py`, `s58_passage_agreement.py`** | **NEW 09-01b.** Stdlib-only, no API calls, nothing written to the Solverah repo. A1–A4 plus the mechanical citation-collision checks and the 5000-draw permutation null. Reproduces STATE §5's band-usage counts exactly, which is the pipeline's own correctness check. | 09-01b |
| **`_build_env/Company_Culture_Evidence_Collector_v4.8.md`** | **NEW 09-01b.** 2b now requires a one-clause reason for every THIN/NONE dimension (defect D25). **No collection rule, sampling frame, section minimum or exemption changed**, so v4.7 and v4.8 packets stay directly comparable and nothing is rebuilt. v4.7 archived to `ground_truth/rubric/`; README updated. **One manual step outstanding — `_build_env/Company_Culture_Evidence_Collector_v4.7.md` still needs deleting; the agent could not remove it and the archive copy is byte-identical (`cmp` clean).** | 09-01b |
| **`analysis_s58/s58_s15_recheck.py`** | **NEW 09-01b.** Cluster bootstrap over packets + permutation tests for the S-15 correlation, and the demonstration that evidence weighting is inert. Stdlib only. | 09-01b |
| **`analysis_s58/s58_citation_probe.py`** | **NEW 09-01b, dry-run verified, NOT RUN.** Analysis (ii), re-scoped. 18 calls. Injects `ForcedChoiceBandProbe`'s own `call_fn` hook so the prompt and schema stay byte-identical to the validated design and `extremity_flag.py` is untouched. Lives in `Solverah_IP`, not the repo. | 09-01b |

**REPLACE the `anchors_v3_PROPOSED.json` row in SUPERSEDED / STALE WITH:**

> **`anchors_v3_PROPOSED.json`** — **EDITED TWICE on 2026-09-01.** Carries (a) the previously
> VALIDATED Collaboration and Innovation band-bleed fixes, (b) the **unvalidated** Decision rewrite,
> measured to be a complete no-op for the LLM extractor, and (c) a Feedback rewrite that was
> **drafted in the morning and corrected in the evening.** The morning edit declared supportiveness
> a non-signal while sitting above an unchanged 0.1 band reading "supportive or nurturing framing" —
> an internal contradiction. The evening edit **changes Feedback's 0.1 and 0.3 BAND TEXTS** (not
> just guardrail prose) to remove the warmth descriptor, and adds a Feedback guardrail to
> `collaboration.keep_distinct` — the highest-colliding pair in round 1 and previously unguarded in
> both v1 and v3. **Editing band text means scores produced under this file are not directly
> comparable to round 1.** Backup at `anchors_v3_PROPOSED.json.bak-2026-09-01b`. **Still blocked on
> S-12 — and S-12 should now wait on the 6-call citation test, see below.**

---

## 3. §3 — S-58, full replacement

**REPLACE the entire S-58 block WITH:**

> **S-58 — The rubric does not achieve construct separation on three specific dimension pairs, and
> rater confidence does not track rater reliability.** `carried: 0` — **RE-SCOPED 2026-09-01b after
> the free analyses ran. The original framing was wrong in a way that mattered.**
>
> **What the item used to say, and why it changed.** S-58 opened as "the low band is read as 'bad on
> this axis' rather than 'matches this specific posture,' by every labeller tried so far," resting on
> four labellers drifting the same direction. **Band usage over 36 cells each disconfirms the shared
> direction:** Julie 8× at 0.1 vs 4× at 0.9; **Carolynn 1 vs 7**; George 4 vs 7; **the extractor 0 in
> 72 independent scoring instances.** Three of the four move away from the floor. The two cases that
> moved toward it — the agent's 46-quote hand-labelling pass and the binary probe — were doing a
> different task (classifying an isolated fragment, not scoring an identifiable employer), and the
> floor-bias work had already established that those two task shapes dissociate in this model.
> **Merging them was the same category error as the retracted Addendum 3, made one document later.**
>
> **Analysis (i) has been RUN and returns a pre-registered NULL.** Per-labeller variance
> decomposition over packet × dimension, 10,000-draw permutation null, null baseline 5/35 = 0.143:
>
> | labeller | eta-sq packet | perm p | eta-sq dimension | perm p |
> |---|---|---|---|---|
> | A | 0.175 | 0.306 | 0.158 | 0.369 |
> | B | 0.059 | 0.867 | 0.094 | 0.698 |
> | C | 0.214 | 0.191 | 0.275 | 0.076 |
> | LLM | 0.305 | 0.045 | 0.197 | 0.226 |
>
> The pre-registered rule required p < 0.05 in ≥2 of 3 human raters. **Zero of three.** The only
> labeller clearing the bar is the extractor, which scores six dimensions in one call, so its packet
> effect is structural rather than halo. **Mechanism (a) in its halo form is dead. Do not re-run this
> in another form.**
>
> **What replaced it, all from existing data:**
> 1. **Construct collision is real but far better than chance.** Of 34 passages cited by ≥2 raters,
>    65% have overlapping dimension sets against a permutation null of 22.6% (p = 0.0002). **Strong
>    construct drift is disconfirmed.** But **35% land on entirely disjoint constructs** — one P-01
>    review sentence supports feedback 0.1, autonomy 0.1, collaboration 0.9 and feedback 0.5 across
>    two raters.
> 2. **The collisions concentrate on pairs the rubric does not guard.** collaboration↔feedback 9,
>    autonomy↔collaboration 8, autonomy↔decision 7, decision↔innovation 6. **The top pair had no
>    `keep_distinct` in v1 or v3** — now added. The two pairs that ARE guarded rank 2nd and 11th of
>    15, so guardrail effectiveness is genuinely undecided on this sample and should not be claimed.
> 3. **Confidence does not track reliability.** Spearman(B–C band distance, mean B/C confidence) over
>    36 cells = **−0.073**. Decision has 3.2× pace's disagreement (2.67 vs 0.83 bands) at
>    **above-average** confidence. Two consequences: disagreement is **not** explained by thin
>    evidence, which supports the instrument being upstream of S-15; and raters cannot tell which
>    dimensions they are unreliable on.
> 4. **A narrow, real valence effect.** 0.1 use clusters on autonomy (4/18) and decision (4/18) and is
>    **zero in 18 opportunities on pace**, whose 0.1 band is the most positively worded of the six.
>    That favours "negative-sounding evidence routes to the low band" over "the low band is avoided
>    as a bad grade."
>
> **The three mechanisms stay unmerged, with two narrowed and one added.** (a) narrows to its
> evidence-routing form. (b) intensity conflation is untouched and untested. (c) narrows to the
> pair-specific form measured above. **Proposed (d), a hypothesis and not a result:** the dimension
> asks about something the evidence class does not directly report — decision's *basis* is almost
> never stated in public evidence, pace's tempo almost always is — so each reader fills the gap from
> their own priors, confidently. Best available explanation of why decision is worst and pace best.
> **Not testable on this sample. Do not act on it.**
>
> **Work remaining:** analysis (ii), re-scoped and now **confirmatory rather than primary** —
> `s58_citation_probe.py`, 18 calls, dry-run verified. Primary outcome is the **off-axis rate**
> (the probe's only 12/12 category), not the band delta (8/10 at exactly the boundary being measured).
> The control arm running the extractor's own citations is **not optional**: an off-axis rate has no
> scale without it. **Honest limit: Carolynn contributes 6–7 fragments per dimension, so (ii) can
> characterise George and the extractor and cannot characterise her.**
>
> **The validation ceiling is unchanged and permanent.** No new human labelling, ever. S-58 can be
> characterised from existing data and cannot be validated by a fresh independent human pass.

---

## 4. §3 — S-59, CLOSE IT

The one outstanding measurement is done. **REPLACE the S-59 block WITH:**

> **S-59 — The extremity flag: fire rate measured under the settled probe.** **CLOSED 2026-09-01b.**
> Re-run over the same 16 cells the binary-probe sweep used, reusing the saved v1 citations so the
> probe is the only thing that changed. **Fire rate 1/16 (6%), down from 2/16 (12%).**
> **Both pre-registered predictions confirmed:** P-06/autonomy still fires (3/3 floor matches);
> P-06/feedback stopped — and not marginally, it went 3/3 to **0/3**.
> **The standing verdict is unchanged and was pre-registered as unchangeable by this number:
> review queue, not auto-gate.** It is now weaker evidence than before, not stronger — one fire means
> precision is estimable from n=1, which requires adjudicated ground truth that no longer exists.
> **Unplanned observation worth keeping:** every feedback cell probed returned **zero** floor matches
> (P-02, P-03, P-04, P-05, P-06 — five cells, fourteen quotes). The probe independently declines to
> read the extractor's feedback citations as floor evidence on the dimension the free analyses found
> most construct-confused.
> **Caveat on provenance:** Arm A's firing condition is inline in `s58_combined_run.py`, not a call
> to `flag_dimension`. Logically equivalent (>=2 matches, all verified citations matching, verified-only
> pre-filter) but `test_extremity_flag.py`'s 5 cases do **not** cover the code that produced this number.

---

## 5. §3 — S-09, replacement of the closing paragraph

**REPLACE** the "Also now a candidate instance of S-58…" ending **WITH:**

> **2026-09-01b — the fix as drafted was internally contradictory, and has been corrected.** The
> morning `keep_distinct` declared recognition / psychological safety / anti-retaliation /
> "we care about our people" language non-signals, while the 0.1 band directly beneath it still read
> **"Harmony valued, conflict avoided, supportive or nurturing framing"** — unchanged from v1. Its
> reconciling sentence ("extremely supportive and caring while giving feedback rarely and gently
> (low band)") strengthened the association it meant to break. **Measured asymmetry:** a warmth
> descriptor appeared at 0.1 with no counterpart at 0.9, so supportiveness evidence could only push a
> score down.
>
> **This partly withdraws the diagnosis.** Round-1 citations such as "never retaliate" and
> "coworkers care about your growth" are close to a **literal match for the frozen 0.1 band's own
> words.** Those raters were following the anchor text, not drifting off-axis. The contamination was
> in the band definition. The "off-axis rater error" framing in
> `FEEDBACK_DIMENSION_DIAGNOSIS_2026-09-01.md` is withdrawn for that subset.
>
> **Also withdrawn:** that document criticised P-04/B for "committing a 0.5 at 0.1 confidence rather
> than treating the packet as uninformative." **0.1 confidence is exactly how the instrument says to
> express that** — the frozen anchors define it as "almost nothing in the packet bears on this
> dimension." There is no abstain option. Whether there should be is a real question and belongs to
> the proposed S-60, not to this item as a rater error.
>
> **Evidence scarcity is partly a collection-rule artifact, not a fact about the world.** P-04's own
> QA block states: *"The one current, detailed employee account of how feedback is delivered at this
> company sits on the review source Section B is not permitted to quote."* Collector v4.7 line 163
> makes Indeed the only required review source; P-04 records a second source whose newest review is
> **26 June 2026** against Section B's newest of **4 July 2024**. **On P-04, Feedback-THIN is caused
> by the rule.** §5's "source-class pattern, not a company-selection problem" is at least partly
> wrong. **Do not over-read this:** only P-01 and P-04 of ten packets record the excluded source's
> recency at all, and P-01 came back COVERED anyway. One confirmed instance, not a pattern. See the
> proposed S-61.

---

## 6. §3 — S-12, replacement of the closing sentence

**REPLACE** "Sending her the file is now partly a request for expert judgement *in place of* an
empirical check." **WITH:**

> Sending her the file is now partly a request for expert judgement *in place of* an empirical check.
> **2026-09-01b: do not send it yet.** The file has changed again (Feedback's band texts, and a new
> Collaboration guardrail), and there is a 6-call test that should run first: re-run
> `run_all_dims_evidence.py` against `anchors_v3_PROPOSED.json` and recompute cross-dimension
> passage reuse. Three outcomes, all informative — collisions drop (the anchor text is a live lever
> and v3 has evidence for the first time); scores unchanged but citations move (the rewrite changes
> what the model looks at, which reframes the Decision no-op); **neither moves (anchor prose is inert
> for the extractor, the only remaining lever is human raters, and human raters are unavailable).**
> **RUN 2026-09-01b. The answer is the third outcome, but the reason is more specific and more
> defensible than "anchor prose is inert."**
>
> Scores: roughly six cells moved one band. **Nine of 36 cells already have non-zero SD across five
> runs under IDENTICAL anchors**, so a strictly stronger intervention than the Decision test — band
> text, not just guardrail prose — produced **less** movement than the model's own run-to-run
> instability. Decision replicated its no-op exactly at 0.000.
>
> Cross-dimension citation collisions, measured by excerpt id (the text-matched version was a metric
> artifact — the model generates spans, raters select from a fixed inventory): **v1 = 7 collisions
> over 94 distinct eids; v3 = 6 over 91. Seven per cent both ways.** The edit changed nothing
> measurable.
>
> **The finding that actually decides S-12 is the pair composition, not the rate.**
> Collaboration<->feedback is the **top colliding pair for both Julie (4) and George (4)** and does
> not appear among the extractor's top pairs in **either** anchor version. **The guardrail added on
> 2026-09-01b addresses a real human defect that this extractor structurally cannot test, because it
> does not make that error.** The model's own worst pair is decision<->pace, which the humans barely
> show.
>
> **So the honest sentence for Julie is not "anchor edits do not work." It is: the only test
> instrument available does not exhibit the defect being fixed, so this edit rests on expert judgement
> alone — hers.** Send the file with that stated plainly.
>
> **D-21 was not satisfied and this stays a pilot:** one draw per arm. The pair composition reshuffled
> completely between v1 and v3 (inno/pace=3 to deci/pace=3) but at 6-7 collisions across 15 possible
> pairs that is uninterpretable, and no number here is quotable. A compliant version is 36 calls.

---

## 7. §3 — S-15, replacement of the correlation claim

**Evidence weighting was tried and does not work.** `min(quotes_B, quotes_C)` is **1 in 35 of 36
cells** — Carolynn is the binding constraint everywhere, so the weight has essentially no variance.
Weighted r = −0.186 against unweighted −0.195. A "both raters cited ≥2 quotes" filter leaves **1 of
36 cells**. There is nothing to reweight.

**What the check found instead is stronger, and it is a fourth appearance of an error §5 already
tracks.** Cells cluster within packet, so a cell-level SE (1/√35 = 0.169) is too narrow — the same
"effective N is distinct companies, not rows" error §5 records as having appeared three times.
Cluster bootstrap resampling **packets** (n = 6, 20,000 draws):

| pair | r | 95% CI | |
|---|---|---|---|
| **B–C (the headline)** | **−0.195** | **[−0.408, +0.069]** | **INCLUDES 0** |
| A–C | +0.401 | [+0.248, +0.568] | EXCLUDES 0 |
| A–B | +0.201 | [−0.175, +0.542] | INCLUDES 0 |

Permutation test (shuffle one rater's 36 scores, own band distribution preserved): B–C p = **0.28**,
A–C p = **0.016**, A–B p = 0.25.

**REPLACE:**

> **B and C are not correlated as predicted — the measured Pearson correlation across their 36
> paired cells is −0.195.** … the honest reading of a loud one is that **the instrument, as worded,
> does not produce convergent readings between two intelligent independent readers.**

**WITH:**

> **B and C are not correlated as predicted: r = −0.195, 95% CI [−0.408, +0.069], permutation
> p = 0.28.** The interval includes zero, so the supportable claim is **"uncorrelated"** — the
> earlier reading of "not merely uncorrelated, faintly negative" put weight on a sign the data does
> not carry. **The CI is from a cluster bootstrap over packets; a naive cell-level interval would be
> far too narrow, which is the fourth appearance of the clustering error tracked in §5 — this time
> inside S-15's own headline.**
>
> **And two humans reading this rubric DO converge to a measurable degree: A–C is +0.401, CI
> [+0.248, +0.568], p = 0.016.** That is evidence against "the instrument does not produce
> convergent readings between two intelligent independent readers," which should be withdrawn as
> stated. **Caveat that keeps it honest:** Julie authored the anchors and recognised or suspected
> the company on 3 of 6 packets, so A–C is not a clean blind–blind pair and cannot replace B–C. It
> does show the rubric is readable enough for two people to land together.
>
> **What survives untouched: the flag counts.** 17 REVIEW / 12 WATCH / 7 AGREE, ~47% of cells ≥2
> bands apart, decision 0/6. Those are descriptive, not inferential, and the correlation was always
> the weaker of the two claims. **Do not read this correction as the rubric being fine.**

**APPEND, on the inputs:**

> Carolynn cited **1.03 quotes per cell** (35 of 36 cells have exactly one) against George's 3.58 and
> Julie's 3.22, and her variance decomposition sits **below the chance baseline on both main
> effects**. **She did nothing wrong** — `RATER_INSTRUCTIONS.md` requires "at least one passage."
> This is not a criticism of her, must never be presented to her as one, and does not license
> discarding her data. It is why the B–C interval is as wide as it is. A read-through impression that
> her notes frequently contradicted her scores was checked mechanically over all 54 non-empty notes
> and found **2**; the impression was withdrawn.

---

## 8. §3 — S-53, replacement of item 2 and addition of item 3

**REPLACE S-53 item 2's closing sentence WITH:**

> **2026-09-01b: checked.** `P-06_defects.txt` exists in the packet folder and covers S1–S2 and
> C1–C8 — **all of them collector-*prompt* defects.** None of the three packet-CONTENT defects
> (the quote absent from Section 1, the review count of six where the correct count is eight, the
> attribution title contradicting the body) appear in it. **The structural reason they went unwritten
> for two weeks: the build process produces prompt-defect files and has no artifact type for
> packet-content defects.** The fix is a `P-0X_content_defects.txt` convention in the `_build_env`
> kit, not a one-off write-up of P-06.

**ADD as S-53 item 3:**

> 3. **Julie's P-04 stale-review claim is ADJUDICATED: refuted as a build defect, confirmed as a
>    collection-rule consequence.** The packet declares it to the rater in bold three ways (newest
>    review 4 July 2024, zero inside the 24-month window, median ~42 months; the March 2025 PE sale
>    postdates every review; 60% truncated at source) plus an explicit second-source note. Collector
>    v4.7 line 163: *"Indeed supplies the verbatim review TEXT — this is what goes in Section 1, and
>    it is the ONLY required review source."* **The builder followed the rule.** Her question "Why?"
>    has an answer, and it is a deliberate collector-design decision. **Her claim was
>    nonetheless worth checking and produced a real result — just not the one expected. The loss on
>    P-04 was real, and `B1a-REMEDY` in v4.7 already fixed it, thirteen days after P-04 was built.
>    No further rule change was needed for it.** See the corrected block 9.

---

## 9. §3 — S-49 / S-57, replacement (the first draft's version was based on a wrong premise)

**RETRACTED from the first draft:** *"Only P-01 and P-04 of ten packets record what the excluded
review source held."* Wrong — that was a grep artifact. **Every one of the ten packets records
`Newest review date BY SITE` in its 2f vintage block**, and that logging was sufficient to test the
hypothesis. Which means the proposed logging line was unnecessary, and the hypothesis it was meant
to support is disconfirmed:

| | Feedback THIN |
|---|---|
| recency cross-check FIRES (P-03, P-04, P-05, P-08) | **4 / 4** |
| recency cross-check ABSENT (P-01, P-02, P-06, P-07, P-09, P-10) | **4 / 6** |

**Feedback comes back THIN at the same rate whether or not the required review source is current.**
§5's existing attribution — *"a source-class pattern, not a company-selection problem"* — **stands.**
The first draft's claim that it is "at least partly wrong" is retracted; it was generalised from
P-04 alone, which is the same n=1 over-reach as the 2026-09-01 Addendum 3 retraction.

**APPEND to S-49 instead:**

> **2026-09-01b — collector at v4.8, and the Feedback-THIN cause is now known to be unknown.**
> The one hypothesis testable from existing packets (the single-required-review-source rule hiding
> fresher on-axis material) is **disconfirmed**: THIN in 4/4 packets where the recency cross-check
> fired and 4/6 where it did not. P-04's specific loss was real and was already fixed by
> `B1a-REMEDY` in v4.7, thirteen days after P-04 was built.
>
> **v4.8 adds one thing and changes no collection rule:** 2b must now give a one-clause reason for
> every dimension marked THIN or NONE. Eight of ten packets recorded Feedback as THIN and nothing
> else, so the most persistent coverage gap in the set has a symptom and no diagnosis anywhere.
> Because no sampling frame, section minimum or exemption moved, **v4.7 and v4.8 packets are built
> from identical evidence rules and stay directly comparable**, and the freeze rule is unaffected —
> nothing is rebuilt. **This is directly upstream of S-09's open question** ("can Feedback be scored
> reliably from evidence that is consistently sparse?"), which currently has no instrument pointed
> at it.

---

## 10. §4 — D-12(b), two words

**REPLACE:** "her scores run ~1 band harsher than both blind raters"
**WITH:** "her scores run ~1 band **lower** than both blind raters (bands 1.83 vs 2.31 and 2.22)"

Rationale: on a rubric whose first gate is *"Neither pole is better,"* calling a low score "harsh" is
the S-58 error appearing in the project's own governing text. The same substitution is owed in §2's
people table and in `RATER_A_JULIE_NOTES_2026-09-01.md` §0.

---

## 11. §5 — new measured results block

**ADD under "Round 1 — the rater returns":**

> **NEW 2026-09-01b — the free S-58 analyses** (`S58_FREE_ANALYSES_2026-09-01b.md`; pre-registered;
> stdlib only, no API calls):
> - **Global-impression test: null.** Packet-effect eta-sq vs a 10k permutation null — A 0.175
>   (p=0.31), B 0.059 (p=0.87), C 0.214 (p=0.19). No human rater shows a packet effect
>   distinguishable from chance. LLM 0.305 (p=0.045), structural, one call per packet.
> - **Passage-level construct agreement: 65% overlap vs a 22.6% permutation null, p = 0.0002**
>   over 34 passages cited by ≥2 raters. Strong construct drift disconfirmed. 35% zero-overlap.
> - **Collision counts:** collaboration↔feedback 9, autonomy↔collaboration 8, autonomy↔decision 7,
>   decision↔innovation 6, autonomy↔pace 6, collaboration↔decision 6, pace↔innovation 2.
> - **Spearman(B–C band distance, mean B/C confidence) = −0.073** over 36 cells. Mean band distance
>   by dimension: decision 2.67, autonomy 1.67, collaboration/feedback/innovation 1.33, pace 0.83.
> - **Citations per cell: A 3.22, B 1.03, C 3.58.** C wrote zero free-text notes in 36 cells.
> - **0.1 use by dimension** (A+B+C, 18 opportunities each): autonomy 4, decision 4, innovation 2,
>   feedback 2, collaboration 1, **pace 0**.
> **NEW 2026-09-01b — the 22-call run** (pre-registered in `PREREG_COMBINED_RUN_2026-09-01b.md`):
> - **Extremity flag fire rate under `ForcedChoiceBandProbe(allow_off_axis=True)`: 1/16 (6%)**,
>   against 2/16 under the binary probe, same 16 cells and same saved citations. Both pre-registered
>   predictions held. All five probed feedback cells returned zero floor matches.
> - **v3 anchors move the extractor less than its own run-to-run noise.** ~6 cells moved one band;
>   9 of 36 cells have non-zero SD across five runs of identical input. Decision 0.000, replicating
>   the morning's no-op.
> - **Cross-dimension citation collisions by excerpt id — humans and extractor in the same units for
>   the first time** (159/159 human-cited eids exist in the model's parsed excerpts):
>   **Julie 20/93 = 22%, George 19/106 = 18%, Carolynn 4/33 = 12%, extractor v1 7/94 = 7%,
>   extractor v3 6/91 = 7%.** The extractor separates constructs 2-3x more cleanly than any human
>   rater. **A text-matched version of this metric returned 0 for the extractor and was an artifact**
>   — the model generates spans while raters select from a fixed excerpt inventory.
> - **collaboration<->feedback is the top colliding pair for Julie (4) and George (4) and is absent
>   from the extractor's top pairs under both v1 and v3.** The extractor cannot validate a fix for a
>   defect it does not have.
> - **inno<->pace was the extractor's top v1 pair (3)** — one of only two pairs the frozen anchors
>   guard in both directions. n=3; consistent with the human-side finding that guardrail presence does
>   not obviously reduce collision, and not strong enough to carry alone.
> - **Integrity check, reusable:** `anchors.json` recomputes to `anchors_hash` **`55c4501b25c5`**,
>   byte-identical to the value recorded in all 18 rater JSONs. The frozen file is provably what
>   round 1 was scored against.

---

## 12. One new item assigned, one withdrawn

**S-60 — ASSIGNED. Nothing constrains how the company side may use a confidence field, and round 1
shows confidence does not track reliability.** `carried: 0` — NEW 2026-09-01b.
D-17(b) forbids filtering or weighting by confidence on the **person** side pending S-18. There is
**no equivalent rule on the company side.** Spearman(B–C disagreement, mean B/C confidence) =
**−0.073**: decision carries 3.2× pace's disagreement at above-average confidence, so a confidence
weight would weight the worst cells as heavily as the best. **Nothing consumes the field yet, which
is exactly why this is cheap now.** Carries the open instrument question S-09 surfaced: **should the
rater app have an abstain option**, given 0.1 confidence ("almost nothing in the packet bears on this
dimension") still requires committing a score, and the criticism of P-04/B for doing precisely that
has been withdrawn.

**S-61 — WITHDRAWN BEFORE OPENING, 2026-09-01b.** Proposed as "the single-required-review-source
rule may be manufacturing Feedback-THIN," then disconfirmed from data already on disk before an ID
was spent — see block 9. **Recorded here rather than dropped silently** so the question is not
re-opened by a later session: it was asked, it was answered, the answer was no. The specific P-04
instance was real and `B1a-REMEDY` (v4.7) already fixed it.

---

## 13. One proposed `check_state.py` addition

STATE's rule *"`anchors.json` … Never edit it"* currently has **no mechanical enforcement**, and
`check_state.py`'s known limit is that it cannot verify a claim citing no artifact. This claim cites
an artifact **and** the expected value is recorded inside the round-1 data:

```python
# recompute build_rater_page.py's own hash and compare to what the raters recorded
h = sha256(json.dumps({k:v for k,v in anchors.items() if not k.startswith("_")},
                      sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
assert h == every rater JSON's anchors_hash   # 55c4501b25c5
```

Mutation-test it by flipping one character of a band description; the check must fail.
