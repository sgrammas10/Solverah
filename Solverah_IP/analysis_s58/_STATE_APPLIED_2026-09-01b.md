# Solverah — STATE

**This is the only document that answers "what is true right now." Read it first, every run.**

Last rewritten: 2026-09-01b (second pass: S-58 re-scoped after its premise was disconfirmed, S-59 closed, S-60 opened, S-61 withdrawn before opening, the S-15 correlation claim corrected, collector at v4.8; original 09-01 entry follows) (round 1 rater JSONs returned and analysed; the S-15 flag fired far harder than pre-registered; the Decision and Feedback anchor fixes were drafted, and the Decision one was MEASURED to be a no-op for the LLM extractor; a structural floor bias in the extractor was found, confirmed unfixable by prompting, and worked around; and a new cross-cutting instrument problem — S-58 — was opened).

## How this file works — read once, then follow it

- **Mutable.** Rewritten in place every session. Not dated, not versioned, not archived.
- **Handoffs are history, not state.** Never read one to learn what to do next. If an item is
  not in §3, it is not open.
- **Item IDs are permanent.** `S-nn` assigned once, never reused, never renumbered. Closed items
  move to §6 with their ID intact.
- **`carried:` is a defect counter.** Increments every session an item stays open and untouched.
  **At `carried: 5` it must be closed, re-scoped, or moved to §7.**
  **Exception, stated 2026-08-19: items in *Blocked on people* do not increment.**
- **Every artifact named anywhere must appear in §2** with a status.
- **A rule quoted from a retired artifact is not a locked rule** (S-35). **Open the artifact
  before writing a rule into §4.**
- **A claim that cites NO artifact is invisible to `check_state.py`** — it verifies only claims
  naming a file. **Four instances so far:** the `> 0.15` threshold (S-35), the 6-vs-18 rater
  count, the "65 company calls" description, and D-08. **The fix is opening the source, not
  extending the checker.** Added 2026-08-20 after the third and fourth.
- **A check whose fixture makes the failure invisible is not a check** (S-40). Mutation-test any
  check whose absence would be silent.
- **An urgency claim is a fact about the world, and the world changes** (S-44). Re-derive before
  repeating that something is blocking.
- **No number enters this file, a handoff, or anything a third party reads unless it clears
  D-21** (the seeds rule): ≥3 independent draws, paired where arms are compared, dispersion
  reported. Otherwise it is labelled a pilot and **no number is quoted**.
- **A labeller's judgement about band membership is evidence, not ground truth** (S-58, new
  2026-09-01, premise corrected same day). Four independent labellers have now each mis-applied the
  same band on the same construct — but **not in the same direction**, and the original wording of
  this rule said they did. The blind raters and the extractor move *away* from the floor; the
  agent's hand labels and the binary probe move *toward* it. What they share is a **criterion** —
  band membership judged on valence rather than posture — across two different task shapes. Do not
  treat any single labelling pass, including a careful one, as settling what a band means, and do
  not restate this as a shared direction.
- **Answer the question that was asked.**
- **`[UNVERIFIED]`** marks a line derived by inference rather than stated.

---

## 1. What Solverah currently is, in five lines

A two-sided matching instrument. **Person side:** 24 forced-choice binary items, 4 per dimension
across 6 dimensions, arranged as a graduated-difficulty (Guttman) ladder; `mean_pole` over
exactly 4 items yields a five-point lattice. **Company side:** evidence packets scored against
rubric anchors, by human raters and by an LLM extractor. **Model:** Bayesian, consumes the
person-side lattice and company-side scores and estimates fit from the gap between them.
Six dimensions: autonomy, pace, collaboration, feedback, innovation, decision.

**As of 2026-08-19 the person side runs end to end AND ships under the Work Pulse name at
`/work-pulse`** (S-43, S-01 in §6), **grades its own confidence** (D-17, S-31), and the model is
**app-callable** (`match_scoring.py`). What still waits on the rater round is the company-side
DATA and the match surface, not the machinery.

**2026-09-01: round 1 rater data has RETURNED (all 18 JSONs) and been analysed.** The result is
not the one the instrument was expected to produce — see S-15 and §5. The company-side rubric is
now the project's weakest link, not its machinery.

**Launch, defined 2026-08-19:** no users yet. Launch = finish the first product iteration —
WorkPulse v2 AND the Bayesian match replacing CompanyLens, **together, not staged** — then
publicize; 10s–100s of users expected. **The gate is publicity, not deployment**, but deploys are
additionally frozen (S-34). **2026-08-20: the publicity gate now ALSO requires S-54 (counsel
sign-off on the legal documents) — see §3 Compliance.**

**One company = one culture score, for v1 (D-22).** Segmentation of large heterogeneous employers
is a decided v2 feature — see S-51.

**Not this.** The 7-dimension cosine-similarity culture pipeline is DEAD (columns survive on
`company` → S-33). The LEGACY Work Pulse chain is superseded but deliberately still running —
S-46.

---

## 2. Artifact inventory

### The people — letter mapping 2026-08-19; blindness corrected and D-12(b) resolved 2026-08-20

| letter | who | role | blind? |
|---|---|---|---|
| **A** | **Julie Fontaine** | Sebastian's **partner** and the project's **domain expert**. Owns the rubric and **rewrites `anchors.json` after round 1**. | **Blind — stated 2026-08-20: all three raters are blind.** Corrects the prior table ("NO — on both axes"). **Still excluded from the S-15 ambiguity flag under D-12(b), on AUTHORSHIP not blindness** — she wrote `anchors.json`, so she cannot be an independent reader of its wording whatever she was told about company identity. **RESOLVED 2026-08-20, no longer deferred.** §5's Wayfair recognition note is a *recognition* event under D-09, not a blindness contradiction; which round it describes is still unconfirmed. **2026-09-01: her round-1 returns recognised or suspected the company on 3 of 6 packets — see §5 and `RATER_A_JULIE_NOTES_2026-09-01.md`.** |
| **B** | **Carolynn** | lawyer, rater | yes — **round 1 returned; recognised zero companies** |
| **C** | **George** | lawyer, rater. Notified 08-18 (S-14). | yes — **round 1 returned; recognised zero companies** |

**NEW CONSTRAINT, stated by Sebastian 2026-09-01: Carolynn and George cannot be asked for more
rater time, for any purpose — not re-scoring, not validation, not a round 2.** The exercise was
far more time-intensive than expected and they did it as a favour with no stake in the project.
**There is also no budget for paid raters.** Every proposal that assumes new human labelling is
dead on arrival; this is why S-58's validation path is a genuine problem rather than an
inconvenience.

**The ambiguity flag computes over exactly two readings (B and C)** — D-12(b), **confirmed
2026-08-20**. `rater_agreement.py` unchanged. The two-vs-three question is closed; what was added
instead is a separate non-triggering diagnostic (`three_way_dispersion.py`, below).

### ACTIVE

| artifact | what it is | since |
|---|---|---|
| `assessment_items_v2.yaml` | the 24 person-side items. `status: active`, `form_version: v2-2026-08-18`. Rules 1–7. Design rule 6 carries the pre-registered feedback prediction + its dated addendum. `difficulty_target` is load-bearing (D-17(c)). | 08-18 |
| `check_assessment_items.py` / `test_assessment_items.py` | CI gate over the item file; asserts v1 is refused | 08-18 |
| `present_items.py` / `test_present_items.py` | server-authoritative shuffle + interleave + opaque tokens; 32 tests | 08-18 |
| `score_person_side.py` | whole-form scorer + the D-17 confidence measure (`guttman_error_count`, stored value 1 − e/2; refuses ambiguous rung order). Committed 2026-08-20 (`causal_bayesian_model`). | 08-19b |
| `assessment_form.py` | the web layer's only doorway to the instrument. `CONFIDENCE_PENDING_DIMENSIONS = {feedback}` implements D-17(a). Committed 2026-08-20 (`causal_bayesian_model`). | 08-19b |
| `assessment_store.py` | single write path + `has_completed_assessment()` (D-18) + `get_dimension_scores()` / `get_dimension_confidences()`, the sanctioned reads (D-01). Committed 2026-08-20 (`causal_bayesian_model`). | 08-19b |
| `seed_discipline.py` | **D-21 enforced where numbers are born.** Provenance derived FROM the per-draw arrays; pairing structural; a non-quotable Finding renders no number. Committed 2026-08-20 (`causal_bayesian_model`). | 08-19b |
| `analyze_sweep.py` | the 2×2 sweep reader; first consumer of `seed_discipline`. Corrected the pooled contrast (20 correlated cells → 5 seeds). Committed 2026-08-20 (`causal_bayesian_model`). | 08-19b |
| `match_core.py` | deterministic core of the match model, numpy-only — lattices, snap, `fit_gap`, `preprocess_conf`, THE `outcome_logit`, `score_pairs`. Committed 2026-08-20 (`causal_bayesian_model`). | 08-19b |
| `match_scoring.py` | the web layer's only doorway to the match model. Refuses unseeded/corrupt weights (D-07); never touches person-side tables (D-01). `seed_priors_model_run()` has run only in tests. Committed 2026-08-20 (`causal_bayesian_model`). | 08-19b |
| `check_state.py` + `tests/test_check_state.py` | **S-28.** Verifies STATE's claims against the artifacts they cite; fixtures ARE the incident history. 16 tests, 5 mutations caught. **Honest limit, now demonstrated four times: it cannot verify a claim that cites no artifact.** Committed 2026-08-20 (`causal_bayesian_model`). **NOT re-run against this 2026-09-01 rewrite — do that first next session.** | 08-19b |
| `three_way_dispersion.py` + `test_three_way_dispersion.py` | Non-triggering diagnostic added alongside (never inside) the S-15 flag. Records per-cell integer band distance for all three rater pairs + three-way spread; **primary output is a distribution over cells, not a ranked list**. Guard pre-registered in the docstring before any JSON was opened. 12 tests, 5 mutations caught. Placed: `ground_truth/rater_app/`. **RAN AGAINST REAL DATA 2026-09-01 — see §5.** | 08-20 |
| `tests/test_seed_discipline.py` | 12 tests; the discriminating one catches a "simplification" that leaves every headline VALUE identical and changes only dispersion | 08-19b |
| `tests/test_match_scoring.py` | 13 tests incl. analytic anchors and an AST guard that `build_model.py` imports the core rather than redefining it | 08-19b |
| `tests/test_confidence_measure.py` | 9 tests incl. the D-17 justification pair against the real item file, and a synthetic set whose id order disagrees with difficulty order | 08-19b |
| `tests/test_assessment_form.py` / `test_assessment_store.py` / `test_employer_visibility.py` | 21 / 3 / 7 checks. The visibility suite is D-01 as a reachability allowlist. | 08-19 |
| `migrations/versions/20260819_add_person_side_assessment.py` | **APPLIED to production 08-19.** | 08-19 |
| `migrations/versions/20260819_add_company_side_model_tables.py` | S-07's migration: 8 tables + `company.domain`, per D-19. Verified on fresh Postgres 16. **Presumed committed with the 08-20 push [UNVERIFIED]; NOT applied.** **`company.domain`'s UNIQUE constraint is what makes v2 segmentation a migration rather than a data change — see D-19(a) and S-51.** | 08-19b |
| `migrations/env.py` | + the S-38 `fileConfig` block. Committed 2026-08-20 (`causal_bayesian_model`). | 08-19b |
| `tests/test_company_side_tables.py` | 9 constraint-level tests; mutation-verified | 08-19b |
| `model.py` | + `AssessmentResponse`, `PersonDimensionScore`, `Company.domain` and the 8 S-07 models. Committed 2026-08-20 (`causal_bayesian_model`). | 08-19b |
| `app.py` | + the two assessment endpoints and `wp_v2_completed` via `_wp_v2_completed`, an error boundary that never breaks auth. **08-20: + terms-acceptance gate on register, account-lifecycle blueprint registration, hardened CSP, PII-free error logs, delimited resume text in agent context.** | 08-19 |
| `account_lifecycle.py` + `tests/test_account_lifecycle.py` | `/api/account/export` + `/api/account/delete` implementing D-23's tombstone design. 7 tests. Committed 2026-08-20. | 08-20 |
| `retention_cleanup.py` | Enforces the retention schedule's ⚙ rows. Needs a Render cron once deploys unfreeze. Committed 2026-08-20. | 08-20 |
| **Frontend legal set** (`src/data/legal.ts`, `LegalPage.tsx`, `HowMatchingWorksPage.tsx` + routes, acceptance checkbox in `Register.tsx`/`AuthContext.tsx`, footer links, AI label in `AgentChat.tsx`) | `/privacy`, `/terms`, `/how-matching-works`; registration requires 16+ attestation + ToS/privacy acceptance. Legal text renders behind a "draft under review" banner until S-54 clears. Committed 2026-08-20. | 08-20 |
| `.github/workflows/tests.yml` + `zensearch.yml` + `dependabot.yml` | pip-audit + npm audit gates; ZenSearch manual-only. **CI GREEN with the gates as of 2026-08-20.** | 08-20 |
| `package.json` / `package-lock.json` / `requirements.txt` | 08-20 audit-gate fixes: react-router floor `^7.18.2`; `setuptools>=83.0.0`. CI green. | 08-20 |
| `Solverah_IP/compliance/` (6 docs) | The Phase 0 document set. Legal drafts carry counsel placeholders — S-54. | 08-20 |
| `SOFTWARE_STANDARDS_COMPLIANCE_REFERENCE.md` / `COMPLIANCE_GAP_ANALYSIS_AND_PLAN.md` | The generic standards reference and the 20-gap audit + phased plan. | 08-20 |
| **`anchors.json`** | company-side rubric. **FROZEN `v1-frozen-2026-08-15`**. `band_values` `[0.1,0.3,0.5,0.7,0.9]` + the authoritative `agreement_rule` — D-12. **This is what round 1 was scored against. Never edit it.** | 08-15 |
| `RATER_INSTRUCTIONS.md` | what the raters were told. **Round 1 is complete, so this is no longer binding-in-flight** — but it is the record of what the three raters were actually told. | 08-15 |
| `SOURCE_CLASS_RULING.md` (`rater_app/`) | the four source classes + the ≤0.7 ruling. `disputed` counts as COMPANY-authored. **≤0.7 is a MEASUREMENT, not a cap.** Implemented in `build_rater_page.py::classify_source`. Confirmed by Julie 2026-08-20. | 08-15 |
| `ANONYMIZATION_RULES_DRAFT.md` | **the LIVE anonymization ruleset.** R1–R8, JC-1–JC-4, amendments A1–A4 DECIDED 2026-08-15. **Read this, not the subfolder `_STATE.md`.** | 08-15 |
| `rater_agreement.py` + tests | the anchor-ambiguity flag; 16 tests, mutation-verified. **Computes over B and C.** **RAN AGAINST REAL DATA 2026-09-01 — see S-15 and §5.** | 08-19 |
| `build_rater_page.py` | generator of the rater HTML files; carries `classify_source` | 08-19 |
| **18 returned rater JSONs** (`ground_truth/rater_app/returned/round1/P-0X_rater{A,B,C}.json`) | **ALL 18 RETURNED and placed 2026-09-01.** `P-01`–`P-06` × A, B, C. This is the round-1 dataset every 2026-09-01 finding rests on. Schema below. | 09-01 |
| `run_agreement_report.py` (`rater_app/`) | Operator entry point wiring `rater_agreement.py` + `three_way_dispersion.py` into one command: `python run_agreement_report.py <returned_dir> [--anchors PATH]`. Reads `packet_id`/`rater` from file CONTENTS, not filenames. **RUN against the real returns 2026-09-01.** | 08-27 |
| `build_model.py` | PyMC research/training harness; deterministic core lives in `match_core.py`. Committed 2026-08-20. | 08-19b |
| `assemble_training_data.py` (`causal_graph/v1_model/`) | **the glue from DB → model.** Draws its company universe from `outcome_appeal JOIN recommendation` and `outcome_experienced` — **NOT from the ground-truth set.** | — |
| `recovery_multiseed.py` / `lattice_gap_analysis.py` / `plot_multiseed.py` | sweep runner, frozen analysis snapshot, figure | 08-18 |
| `run_vignette_probe.py` + `vignette_probe_pairs_v3`…`_v12` | probe runner; what S-10's 65 calls run on — synthetic, not real companies | 08-18 |
| **6 evidence packets** (`ground_truth/packets/`) | `P-01_oscar_health`, `P-02_best_buy`, `P-03_akuna_capital`, `P-04_rga`, `P-05_doist`, `P-06_raymond_james`. VERIFIED stage/comp from the roster. | 08-15 |
| **6 scrubbed packets** (`ground_truth/anonymization/P-0n_packet_ANON.txt`) | what the raters and the extractor both actually score. Becomes canonical as `P-0X_packet_RATER.txt` per S-50 Q3 at the v4.7 rebuild. | 08-15 |
| `Ground_Truth_Roster_v2.1_FINAL` | 19 companies with per-company confounders and expected pole lean. **The authority for confounder values.** Lives in Sebastian's Drive. | 07-24 |
| **19 internal evidence documents** (`GT-01`–`GT-19`, Drive) | Pre-existing v3-prompt "researcher copy" packets. **NOT directly reusable.** GT-01 = Wayfair, excluded. | 07-2x |
| `reid_attack_gpt_5_5_2026_04_23.csv` | re-identification test, 18 rows | 08-17 |
| `PREREGISTRATION_2026-08-19_S17_S18.md` | the S-18/S-17 analysis specs. Status **PROPOSED** — one decision pending. | 08-19b |
| `prereg_power_sim.py` | the simulation the pre-registration's thresholds come from. | 08-19b |
| `s48_ground_truth_size_power_sim.py`, `s48_clustering_check.py` | **S-48 SIZE support — NOT retracted.** Basis for 15-20. Rebuilt 08-20, reproduces the recorded result. | 08-20 |
| `S48b_CORRECTION_2026-08-20.md` | **the retraction** of the confounder-spread analysis. Read before citing `S48b_CONFOUNDER_SPREAD_2026-08-20.md`. | 08-20 |
| `S50_DECISION_SHEET_2026-08-20.md` | S-50's six decisions as answered by Julie | 08-20 |
| `IO_REVIEW_BRIEF.md` | **SEND-READY** — attach `assessment_items_v2.yaml`; sending is Sebastian's (S-05) | 08-19b |
| `AGENT_OPERATING_POLICY.md` / `AGENT_DECISION_QUEUE.md` | authority grant; Sebastian's answers authoritative. Canonical = project docs; dated DO-NOT-EDIT disk mirrors in `Solverah_IP/`. | 08-19 |
| `_build_env/`: `BUILD_BRIEF.md` + `Company_Culture_Evidence_Collector_v4.7.md` + `README.txt` | The isolated clean-room build kit for P-07–P-12, one fresh session per company outside this project. Step 1 table current through P-10; README made version-agnostic 08-28. | 08-27 |
| **P-07 (Cummins), P-08 (DigitalOcean), P-09 (Warby Parker), P-10 (Twilio)** | **BUILT and on disk.** P-07/P-08 under v4.6, P-09/P-10 under v4.7. P-09 is the only packet with all six dimensions COVERED. See §5's Feedback-THIN finding. Defect lists reviewed for P-07/P-08 only; quote spot-checks still owed for all four; anonymization ahead for all four. | 08-27/28 |
| **`RATER_A_JULIE_NOTES_2026-09-01.md`** | **NEW 09-01.** Julie's round-1 free-text notes pulled and organised, with the case for why her *scores* are not usable as ground truth (systematically ~1 band lower; matches the B/C consensus exactly on only 3 of 7 cells; recognised/suspected the company on 3 of 6 packets) while her *notes* carry real signal: independent corroboration of S-51's segment-coverage gap, a specific checkable stale-evidence claim on P-04, a missing-source-class list, a candidate 7th signal (company stability/layoffs), and a new product idea (a "quarantine" gate for self-contradicting or scam-reading companies). Also documents her P-05 scores as a live instance of the single-impression-correlation risk the 08-15 design doc accepted: the same sentence pasted into all six dimension notes at confidence 0.1 throughout. Project + `Solverah_IP/`. | 09-01 |
| **`LLM_VS_HUMAN_COMPARISON_2026-09-01.md`** | **NEW 09-01.** The first execution of S-49's *second* stated purpose — validating the LLM extractor against human consensus. Carries the 36-cell comparison, five dated addenda (the Decision-anchor no-op; what the extractor actually cites; the retraction of an over-generalised directional-lean theory; the per-cell read of the five floor cells; the failed prompt-level calibration fix). Project + `Solverah_IP/`. | 09-01 |
| **`FEEDBACK_DIMENSION_DIAGNOSIS_2026-09-01.md`** | **NEW 09-01.** S-09's citation-level diagnosis: the full round-1 Feedback citation table for B and C across all six packets, the finding that both raters (not one) scored a different construct, the two concrete cross-dimension leaks, and the anchor fix applied to `anchors_v3_PROPOSED.json` — with an explicit warning that the fix may not be sufficient because the problem is partly evidence scarcity. Project + `Solverah_IP/`. | 09-01 |
| **`FLOOR_BIAS_WORKAROUND_2026-09-01.md`** | **NEW 09-01.** Design record for the extremity flag: two failed designs recorded so they are not rebuilt, the gate test, the sweep, the three-way probe comparison, the honest limits, and the S-58 finding. Project + `Solverah_IP/`. | 09-01 |
| **`causal_graph/scorer_pipeline.py`** | **the real LLM extractor** (S1-1/S1-2/S1-5). `score_packet(...) -> ScorerResult` with `evidence_quotes` in the response schema, plus the citation verifier (`parse_excerpts`, `verify_quote`, `verify_result`, `noncompany_support`) that matches each quote against the packet's addressable excerpts and normalises whitespace/dashes/smart-quotes. Reads the frozen `anchors.json` via `SOLVERAH_IP_DIR`. **First used against real packets 2026-09-01.** | 08-17 |
| `causal_graph/scorer_variance_test_v2.py` | repeated-sampling harness; builds its rubric from `anchors.json` and stamps every row `rubric_version: v1-frozen-2026-08-15`. **Schema is score+confidence ONLY — it captures no evidence and cannot answer "what did it cite".** Results in `causal_graph/results/scorer_variance_v2/`. | 08-17 |
| **`causal_graph/extremity_flag.py`** | **NEW 09-01, untracked.** The floor-bias workaround: supplies a bottom-end signal without trusting the extractor's score field. `flag_dimension` / `flag_result` fire `FLOOR_SUSPECT` only when every VERIFIED citation matches the dimension's own 0.1 band description and none contradicts it. Deliberately **one-sided** — documented in the header as resting on a measured property of this model, to be retired rather than made symmetric. Ships three probes; **`ForcedChoiceBandProbe(allow_off_axis=True)` is the tested default**, with the full three-way comparison table in the docstring. | 09-01 |
| **`causal_graph/test_extremity_flag.py`** | **NEW 09-01, untracked.** 5 cases against real citation data, including the P-03/autonomy counterexample that killed the symmetric design. Carries a standing warning that it validates FLAG LOGIC against hand labels and does **not** validate the probe's labelling. | 09-01 |
| **`causal_graph/run_probe_gate_test.py`**, **`run_flag_sweep.py`**, **`probe_boundary_test.py`**, **`run_all_dims_evidence.py`**, **`run_decision_evidence.py`** | **NEW 09-01, untracked.** The gating test (does the probe escape the reluctance), the fire-rate sweep, the 46-quote pre-registered boundary test with `--probe binary|forced|forced_escape`, and the two evidence-capture runners. `.ps1` wrappers at the Solverah repo root resolve the venv python by absolute path. | 09-01 |
| `causal_graph/results/all_dims_evidence_2026-09-01.json` | Every dimension's score, confidence, evidence quotes, verification status and source tag for all 6 packets, from one call per packet. **Saved so follow-up questions about any dimension need no new API calls.** Lives under the scratch `decision_test/` tree, not in the repo. | 09-01 |
| **`S58_FREE_ANALYSES_2026-09-01b.md`** | **NEW 09-01b.** The free half of S-58, run. Corrects S-58's "same direction" premise; records analysis (i) as a pre-registered NULL; adds the confidence/reliability decoupling and the passage-collision measurement; documents the v3 Feedback contradiction and the re-scoping of analysis (ii). Project + `Solverah_IP/analysis_s58/`. | 09-01b |
| **`PREREG_S58_2026-09-01b.md`** / **`PREREG_COMBINED_RUN_2026-09-01b.md`** | **NEW 09-01b.** Pre-registrations for the free analyses and for the 22-call run, both written before any statistic or call. The first fixes the analyst's own hand labels on the six 0.1 band texts and an n=6 power warning; the second fixes the rule that **no fire rate changes the review-queue verdict** and that arm B is a D-21 pilot. Project + `Solverah_IP/analysis_s58/`. | 09-01b |
| **`analysis_s58/` scripts** | **NEW 09-01b, none in the repo.** `s58_free_analyses.py`, `s58_mechanical_checks.py`, `s58_passage_agreement.py`, `s58_rater_b_check.py`, `s58_s15_recheck.py`, `s58_eid_collisions.py` (all stdlib / zero-API), plus `s58_combined_run.py` (the 22-call run) and `s58_citation_probe.py` (18 calls, dry-run verified, NOT RUN). The runners import the repo read-only on `sys.path`, find it by walking up for `.git`, and **refuse to start if their output path resolves inside it**. | 09-01b |
| **`_build_env/Company_Culture_Evidence_Collector_v4.8.md`** | **NEW 09-01b.** 2b now requires a one-clause reason for every THIN/NONE dimension (defect D25). **No collection rule, sampling frame, section minimum or exemption changed**, so v4.7 and v4.8 packets stay directly comparable and nothing is rebuilt. v4.7 archived to `ground_truth/rubric/` and removed from the kit. | 09-01b |
| `analysis_s58/results/` | `s59_fire_rate_2026-09-01b.json`, `all_dims_evidence_v3_2026-09-01b.json` — the 22-call run's outputs. | 09-01b |

### SUPERSEDED / STALE — named so nobody reads them as live

| artifact | status |
|---|---|
| **`ground_truth/anonymization/_STATE.md`** | **STALE and a filename collision with this file.** Still presents A1–A4 as open and frames ≤0.7 as a cap, which `SOURCE_CLASS_RULING.md` explicitly rejects. **It misled two separate reads on 2026-08-20. Rename it or delete it.** Its still-useful content is in S-53. |
| `s48b_confounder_spread_sim.py`, `s48b_lever_demo.py`, `s48b_set_designer.py`, `S48b_CONFOUNDER_SPREAD_2026-08-20.md` | **premise RETRACTED 2026-08-20.** R1–R4 void; do not run the set-designer as a selection gate. §5 retains the two surviving findings, which apply to the PRODUCTION model. |
| `src/data/wpQuestions.ts` / `useWP.ts` / `WPStepper.tsx` / `WorkPulseResultsPage.tsx` | LEGACY 12-question quiz; kept so old completers reach their narrative. Retire via S-46. |
| `/api/work-pulse/submit`, `/api/work-pulse/results`, `derive_preferences.py` | old submit/narrative path onto the DEAD 7-dim pipeline. Retire via S-46. |
| CompanyLens / path_scoring placeholder | replaced when the Bayesian match ships. **Known seam:** `IntelligencePage` gates on `wpl_completed`. |
| `Solverah_Company_Scoring_Workbook_v2_*.xlsx` | retired 08-18. Its `ABS(A−B) > 0.15` was **never the live rule** — S-35. |
| `assessment_items.yaml` | retired; `status: superseded`, kept on disk deliberately |
| `anchors_v2_PROPOSED.json` | proposed; superseded by v3. |
| **`anchors_v3_PROPOSED.json`** | **EDITED THREE TIMES on 2026-09-01.** Carries (a) the previously VALIDATED Collaboration and Innovation band-bleed fixes, (b) the **unvalidated** Decision rewrite, measured to be a complete no-op for the LLM extractor, and (c) a Feedback rewrite drafted in the morning and corrected twice that evening. The morning edit declared supportiveness a non-signal while sitting above an unchanged 0.1 band reading "supportive or nurturing framing"; the second changed Feedback's **0.1 and 0.3 BAND TEXTS** to remove the warmth descriptor and added a Feedback guardrail to `collaboration.keep_distinct` — the top-colliding human pair, previously unguarded in v1 and v3; the third removed a rubric-facing parenthetical that re-quoted the superseded wording back into the instrument. **Editing band text means output under this file is not directly comparable to round 1.** Backup at `anchors_v3_PROPOSED.json.bak-2026-09-01b`. **Gate run — see S-12.** |
| stray `SOLVERAH_HANDOFF.md` in `causal_graph/v1_model/` | the 2026-07-23 pre-STATE handoff, referenced by nothing, violates D-11 → S-20 |
| `@vitalets/google-translate-api` (npm dep) | **CLEARED.** Confirmed absent from `package.json` and the lock 08-27. |

### The rater JSON schema

Top level: `packet_id`, `rater`, `rubric_version`, `anchors_hash`, `session_start`,
`submitted_at`, `duration_seconds`, `commit_order`, `recognition`, `recognition_detail`,
`searched`, `search_detail`, `free_note`, `scores[]`.

Each `scores[]` row: `dimension`, `score`, `confidence`, `quotes[]`, `note`, `committed_at`,
`commit_position`, `source_mix{company,noncompany,disputed,researcher}`, `noncompany_support`,
`excerpts_cited[]`. **`quotes[]` entries are objects: `{text, eid, sec, src}`** — confirmed
against the real returns 2026-09-01; the field is `quotes`, not `citations`.

`score` ∈ `[0.1,0.3,0.5,0.7,0.9]` — one band = 0.2. `confidence` ∈ `[0.1,0.3,0.6,0.9]`.
**`disputed` stays a DISTINCT recorded class and is folded into `company` only at analysis time**
(S-50 Q1). Do not collapse it at capture.

**`duration_seconds` is not a usable effort proxy across raters.** Julie's P-03 session reads
777,173 s (~9 days, a session left open); P-06 ~23 h. Carolynn's and George's were same-day or
overnight. Do not compare raw durations across raters.

---

## 3. Open items

### The instrument — NEW and now the highest-value thread

**S-58 — The rubric does not achieve construct separation on three specific dimension pairs, and
rater confidence does not track rater reliability.** `carried: 0` — **RE-SCOPED 2026-09-01b after
the free analyses ran. The original framing was wrong in a way that mattered.**

**What the item used to say, and why it changed.** S-58 opened as "the low band is read as 'bad on
this axis' rather than 'matches this specific posture,' by every labeller tried so far," resting on
four labellers drifting the same direction. **Band usage over 36 cells each disconfirms the shared
direction:** Julie 8x at 0.1 vs 4x at 0.9; **Carolynn 1 vs 7**; George 4 vs 7; **the extractor 0 in
72 independent scoring instances.** Three of the four move away from the floor. The two cases that
moved toward it — the agent's 46-quote hand-labelling pass and the binary probe — were doing a
different task (classifying an isolated fragment, not scoring an identifiable employer), and the
floor-bias work had already established that those two task shapes dissociate in this model.
**Merging them was the same category error as the retracted Addendum 3, made one document later.**

**Analysis (i) has been RUN and returns a pre-registered NULL.** Per-labeller variance decomposition
over packet x dimension, 10,000-draw permutation null, null baseline 5/35 = 0.143:

| labeller | eta-sq packet | perm p | eta-sq dimension | perm p |
|---|---|---|---|---|
| A | 0.175 | 0.306 | 0.158 | 0.369 |
| B | 0.059 | 0.867 | 0.094 | 0.698 |
| C | 0.214 | 0.191 | 0.275 | 0.076 |
| LLM | 0.305 | 0.045 | 0.197 | 0.226 |

The pre-registered rule required p < 0.05 in >=2 of 3 human raters. **Zero of three.** The only
labeller clearing the bar is the extractor, which scores six dimensions in one call, so its packet
effect is structural rather than halo. **Mechanism (a) in its halo form is dead. Do not re-run this
in another form.**

**What replaced it, all from existing data:**
1. **Construct collision is real but far better than chance.** Of 34 passages cited by >=2 raters,
   65% have overlapping dimension sets against a permutation null of 22.6% (p = 0.0002). **Strong
   construct drift is disconfirmed.** But **35% land on entirely disjoint constructs** — one P-01
   review sentence supports feedback 0.1, autonomy 0.1, collaboration 0.9 and feedback 0.5 across
   two raters.
2. **The collisions concentrate on pairs the rubric does not guard.** By excerpt id (the sounder
   metric, see §5): collaboration<->feedback is the **top pair for both Julie (4) and George (4)**,
   and **had no `keep_distinct` in v1 or in the first v3 draft** — now added. The two pairs that ARE
   guarded rank 2nd and 11th of 15 on the text metric, so guardrail effectiveness is genuinely
   undecided on this sample and should not be claimed.
3. **Confidence does not track reliability.** Spearman(B-C band distance, mean B/C confidence) over
   36 cells = **-0.073**. Decision has 3.2x pace's disagreement (2.67 vs 0.83 bands) at
   **above-average** confidence. Two consequences: disagreement is **not** explained by thin
   evidence, which supports the instrument being upstream of S-15; and raters cannot tell which
   dimensions they are unreliable on. **This is now S-60.**
4. **A narrow, real valence effect.** 0.1 use clusters on autonomy (4/18) and decision (4/18) and is
   **zero in 18 opportunities on pace**, whose 0.1 band is the most positively worded of the six.
   That favours "negative-sounding evidence routes to the low band" over "the low band is avoided as
   a bad grade."
5. **The defect is HUMAN, and the extractor cannot proxy for it.** Measured in the same units for
   the first time (§5): humans collide on 12-22% of cited excerpts, the extractor on 7%, and
   collaboration<->feedback — the top human pair — is absent from the extractor's top pairs under
   both v1 and v3 anchors. **Any fix aimed at a human reading failure has no available test
   instrument.**

**The three mechanisms stay unmerged, with two narrowed and one added.** (a) narrows to its
evidence-routing form. (b) intensity conflation is untouched and untested. (c) narrows to the
pair-specific form measured above. **Proposed (d), a hypothesis and not a result:** the dimension
asks about something the evidence class does not directly report — decision's *basis* is almost
never stated in public evidence, pace's tempo almost always is — so each reader fills the gap from
their own priors, confidently. Best available explanation of why decision is worst and pace best.
**Not testable on this sample. Do not act on it.**

**Work remaining:** analysis (ii), re-scoped and now **confirmatory rather than primary** —
`s58_citation_probe.py`, 18 calls, dry-run verified, NOT RUN. Primary outcome is the **off-axis
rate** (the probe's only 12/12 category), not the band delta (8/10 at exactly the boundary being
measured). The control arm running the extractor's own citations is **not optional**: an off-axis
rate has no scale without it. **Honest limit: Carolynn contributes 6-7 fragments per dimension, so
(ii) can characterise George and the extractor and cannot characterise her.**

**The validation ceiling is unchanged and permanent.** No new human labelling, ever. S-58 can be
characterised from existing data and cannot be validated by a fresh independent human pass.

**S-59 — The extremity flag: fire rate under the settled probe.** **CLOSED 2026-09-01b.**
Re-run over the same 16 cells the binary-probe sweep used, reusing the saved v1 citations so the
probe is the only thing that changed. **Fire rate 1/16 (6%), down from 2/16 (12%).**
**Both pre-registered predictions confirmed:** P-06/autonomy still fires (3/3 floor matches);
P-06/feedback stopped — and not marginally, it went 3/3 to **0/3**.
**The standing verdict is unchanged and was pre-registered as unchangeable by this number: review
queue, not auto-gate.** It is now weaker evidence than before, not stronger — one fire means
precision is estimable from n=1, which requires adjudicated ground truth that no longer exists.
**Unplanned observation worth keeping:** every feedback cell probed returned **zero** floor matches
(P-02, P-03, P-04, P-05, P-06 — five cells, fourteen quotes). The probe independently declines to
read the extractor's feedback citations as floor evidence on the dimension the free analyses found
most construct-confused.
**Caveat on provenance:** Arm A's firing condition is inline in `s58_combined_run.py`, not a call to
`flag_dimension`. Logically equivalent (>=2 matches, all verified citations matching, verified-only
pre-filter) but `test_extremity_flag.py`'s 5 cases do **not** cover the code that produced it.

### Launch path

**S-45 — The launch-blocker list.** `carried: 0`
1. **Rater round 1 returns** — **DONE 2026-09-01. All 18 JSONs returned, placed, and analysed.**
   The blocker is discharged; what it produced is S-15's result and S-58.
2. **S-12** anchors_v3 → Julie — **still open, and now carries two unvalidated new edits.**
3. **S-09** feedback construct mismatch — **fix drafted 09-01, unvalidated.** See below.
4. **S-10** the 65 calls — 13 synthetic vignettes × 5 runs, NOT company scoring. Defer until
   anchors_v3. His spend, his call.
5. **S-07** company-side migration — GO, code complete, unapplied. **Unblocked by everything
   above; pure execution.**
6. **S-06 + productionize `build_model.py`** — DONE (D-20 + the serving path). Remaining: run
   `seed_priors_model_run` against prod once the migration is applied.
7. **Match surface** — waits on company-side data assembly, D-01-constrained output design, UI.
8. **S-46** — with zero users, do any real old-quiz completers exist? One prod query answers it.
9. **S-34** — deploys frozen.
10. **S-18 + S-17 specs** — deferred to pre-publicity.
11. **S-05** — GO. Send the I-O brief. **Still unsent.**
12. **Product QA pass** — later.
13. **S-38** — fixed (§6).
14. **S-54 counsel sign-off** — the publicity gate includes it.

**S-46 — Retire the legacy Work Pulse chain when the match replaces CompanyLens.** `carried: 1`
Leave it running until then. When the match ships: remove `derive_culture_preferences` + the old
endpoints, rework `IntelligencePage`, decide the fate of stored `wpl_result` narratives, fold in
S-33's dead columns. **Do not partially retire it.** Open question: if a prod query finds zero
real `wpl_result` rows, early retirement becomes a simplification, not a breakage.

### Compliance

**S-54 — Counsel review of the legal documents.** `carried: 0` — **Blocked on people**
Privacy policy and ToS drafts live in-app behind a "draft under review" banner
(`LEGAL_IS_DRAFT = true`). Counsel must resolve: [ENTITY NAME], [ENTITY STATE], dispute
resolution, the liability cap, the effective date. **Publicity does not open before this closes.**
Entity formation / IP assignment / trademark sweep (GAP-15) rides the same engagement.

**S-56 — Vendor register blanks.** `carried: 1`
`compliance/VENDOR_REGISTER.md` has unfilled cells that are facts, not writing: Groq's API
data-use terms (**verify before launch; if weaker than OpenAI's, route PII-bearing prompts to
OpenAI only**), DPA acceptance for Render/Vercel/Cloudflare/Resend, log-retention windows,
whether the unused Anthropic key can be removed, GitHub secret-scanning toggles.

**Event-triggered, deliberately NOT opened as S-items:** PCI/tax/subscription (first paid plan),
FCRA legal opinion (**must precede the first employer conversation**), state privacy-law
threshold re-check (each 10× growth), GDPR (EU marketing intent), SOC 2 (first enterprise
questionnaire).

**Data-in-git note (08-27, not an S-item):** `zensearchData/`, `Filtered_Data/`, and
`old_LLM/Filtered_Data/` are tracked and already pushed to `origin/causal_bayesian_model`.
Gitignoring now would not remove what is pushed; that needs a history rewrite. Left as a fact.

### Ground truth — the company set

**S-48 — The ground-truth company set.** `carried: 0` — **SIZE + CRITERION decided 08-20; next
batch membership decided 08-27; P-07–P-10 BUILT; P-11 (Regeneron) and P-12 (Duke Energy) remain**

**Size: 15–20**, from `s48_ground_truth_size_power_sim.py` (**not** affected by the 08-20
retraction — it measures LLM-extractor calibration, a real job of the set). **The exact number
(15 vs 20) was deferred until round 1's JSONs returned. They have now returned** — but note the
decision was framed around pole assignments being pre-scoring expectations, and round 1's actual
result (S-15) raises a prior question about whether the instrument is measuring what it should
before more packets are scored against it.

**All six built packets STAY.** Three raters completed a round against them; round 1's guaranteed
output is the S-15 flag, a property of rubric wording.

**The selection criterion is DIMENSION POLE COVERAGE, not confounder spread** (see the retraction
in §5). Five of twelve poles rest on a single company in the six: Best Buy (autonomy low,
innovation optimize), Doist (pace steady, collaboration solo/async), Akuna (feedback blunt).

**NEXT BATCH DECIDED 2026-08-27: Cummins, DigitalOcean, Warby Parker, Twilio, Regeneron, Duke
Energy** — built via the isolated clean-room kit, fresh session per company, outside this project.
Four are built (P-07–P-10). **P-11 and P-12 remain.** Duke Energy is the one to watch under the
new D23 homonym check — "Duke" is a generic-name collision of exactly the P-08 Tillamook shape.
**Hudson River Trading** stays the held fallback for blunt-feedback, but §5's cross-packet finding
says it will very likely also come back THIN; do not treat it as a fix.

**Still open:** the final total count; whether a genuine non-remote-tech solo/async anchor gets
identified; and whether ANY company-selection move can close the blunt-feedback pole given
Feedback is THIN in 8 of 10 packets regardless of company.

**S-49 — Packets for the rest of the set.** `carried: 0` — **four of six built; P-11/P-12 next**
Six packets are scored; 9–14 more are needed. **P-11 (Regeneron) and P-12 (Duke Energy) remain**,
via the `_build_env` kit. Still owed for P-07–P-10: defect-list review (only P-07/P-08 done),
quote spot-checks, and anonymization — P-07's with the S3 URL-scrubbing decision attached.
**2026-09-01: S-49's SECOND stated purpose — validating the LLM extractor against human
consensus — has now been executed for the first time** (`LLM_VS_HUMAN_COMPARISON_2026-09-01.md`).
It had never been run: no script in the repo compared extractor output to the rater JSONs.
**Why it is its own item:** real-company LLM scoring reads the *same frozen packets the humans
scored*, so it cannot run on a company with no packet.
**2026-09-01b — collector at v4.8, and the Feedback-THIN cause is now known to be unknown.**
The one hypothesis testable from existing packets — that the single-required-review-source rule was
hiding fresher on-axis material — is **disconfirmed**: Feedback is THIN in **4/4** packets where the
recency cross-check fired and **4/6** where it did not. §5's existing "source-class pattern, not a
company-selection problem" attribution **stands**. P-04's specific loss was real and `B1a-REMEDY`
(v4.7) already fixed it.

**v4.8 adds one thing and changes no collection rule:** 2b must now give a one-clause reason for
every dimension marked THIN or NONE (defect D25). Eight of ten packets recorded Feedback as THIN and
nothing else, so the most persistent coverage gap in the set has a symptom and no diagnosis anywhere.
Because no sampling frame, section minimum or exemption moved, **v4.7 and v4.8 packets are built from
identical evidence rules and stay directly comparable**, and the freeze rule is unaffected — nothing
is rebuilt. **This is directly upstream of S-09's open question** ("can Feedback be scored reliably
from evidence that is consistently sparse?"), which currently has no instrument pointed at it.
**S-51 — Packet representativeness for large heterogeneous employers.** `carried: 1` — **core
question decided (D-22); two follow-through items open**
**OPEN 1 — scope-label heterogeneous packets at creation time.** An unlabelled row reading
"Best Buy — autonomy 0.3" is indistinguishable from a whole-company measurement. Free now,
expensive later. Where the label lives is undecided. **2026-09-01: Julie's round-1 rater notes
independently corroborate this from the scoring side, on the same packet (P-02) her QA read
flagged — two independent passes landing on the same defect.**
**OPEN 2 — `company.domain` is nullable-UNIQUE (D-19(a)), so v2 segmentation is a migration.**
Cheapest to change before the S-07 migration is applied, which it still has not been.

**S-52 — The "separate broader company sample" is deferred to by two artifacts and specified by
neither.** `carried: 1`
Supplies the real `{mean, sd}` that `preprocess_conf()` standardizes `stage_size` and `comp`
against; the constants (3.0/1.5 and 3.0/1.0) are placeholders applied to **every served
prediction**. Nothing says what the sample is, who builds it, how big, or when. D-08's retired
concern is re-filed here. Not urgent; the cost lands at serving time.

**S-57 — The ground-truth packets are built richer than production can afford to reproduce.**
`carried: 1`
The worry is upstream of scoring: the automated production packet-*builder* will not afford
Opus-tier multi-fetch stratified research per company, so its output will be thinner than
P-01–P-12, regardless of which model built the ground-truth packets. **Switching the builder
model does not address this** — the gap is in research *method*, not model, and downgrading
would add an unplanned confound.
**What would address it, none done:** (1) characterise what a real production scraper can gather;
(2) test whether the extractor degrades gracefully on thin evidence — **and §5's Feedback-THIN
finding means the ground-truth set ALREADY contains that test case, today**; (3) decide whether
production gets its own budgeted research pass. Candidate raised 08-27, unevaluated: per-company
evidence-gathering as scheduled Cowork tasks against the subscription rather than metered API.

**S-53 — Packet-quality findings with no owner.** `carried: 1`
1. **P-02 and P-05's anon files were retyped rather than edited**, converting ASCII hyphens to em
   dashes inside quote bodies. **Three quotes will fail citation verification on punctuation**
   unless the harness normalises dashes and smart quotes. **2026-09-01 UPDATE: `scorer_pipeline.py`'s
   verifier DOES normalise dashes, smart quotes and whitespace, and all 18 extractor citations
   verified against the packets in the 09-01 run — so this is handled on the extractor path.
   Whether the human-side tooling normalises the same way is unchecked.**
2. **P-06's source packet contains a quote that does not exist in Section 1** — "written from
   memory" — plus a review count of six where the correct count is eight, and an attribution title
   contradicting the reviewer's own body text. **A fabricated quote is exactly what the real-time
   verification habit exists to catch, and it got past it once.** P-07's S2 defect is the same
   class recurring. **2026-09-01: these two P-06 defects were re-encountered while reading the
   anonymised packet and remain unwritten-up anywhere except here and the stale `_STATE.md`.**
**2026-09-01b: checked.** `P-06_defects.txt` exists in the packet folder and covers S1-S2 and C1-C8
— **all of them collector-*prompt* defects.** None of the three packet-CONTENT defects appear in it.
**The structural reason they went unwritten: the build process produces prompt-defect files and has
no artifact type for packet-content defects.** The fix is a `P-0X_content_defects.txt` convention in
the `_build_env` kit, not a one-off write-up of P-06.

3. **Julie's P-04 stale-review claim is ADJUDICATED: refuted as a build defect, confirmed as a
   collection-rule consequence.** The packet declares it to the rater in bold three ways (newest
   review 4 July 2024, zero inside the 24-month window, median ~42 months; the March 2025 PE sale
   postdates every review; 60% truncated at source) plus an explicit second-source note. Collector
   v4.7 line 163 makes Indeed the only required review source. **The builder followed the rule**, and
   **`B1a-REMEDY` in v4.7 already fixed the mechanism, thirteen days after P-04 was built.** No
   further rule change was needed for it. The general version of the worry is disconfirmed — see S-49.
### Pre-registration

**S-18 — Specify the test for design rule 6's feedback prediction.** `carried: 1` — deferred
Feedback is the only dimension whose ladder switches grading variable mid-climb. **SPEC DRAFTED —
`PREREGISTRATION_2026-08-19_S17_S18.md`, PROPOSED. One decision needs sign-off:** the composition
test is ceiling-compressed (0.76 of the 0.5 stratum under the null). **Proposed primary instead:
the conditional climb** `q_d = P(rung3 | rung1, rung2)`, null q = 0.46, ~1.5× the effect.
**N ≥ 300 first-sittings, analysis runs ONCE.** D-21 with `draw_kind="bootstrap"`, resampling
RESPONDENTS not rows.

**S-17 — Specify what dimension correlation would mean.** `carried: 1` — deferred
**The 5-point lattice attenuates correlation by ≈0.63**, so latent 0.70 presents as 0.44.
**All thresholds stated on the OBSERVED scale:** ≥0.44 = not separable, a model identification
problem; 0.19–0.44 = real relationship, model it; <0.19 = no action. S-24 folded in. N ≥ 300.
**GAP-08 addition: once N ≥ 300 exists, add a pre-registered check that dimension scores do not
proxy for protected classes.**

### Instrument and model

**S-05 — Send the I-O psychology review brief.** `carried: 1` — **GO; send-ready; still unsent**
(a) can four binary forced-choice items give usable reliability — load-bearing, since "add more
items" is a re-architecture (D-02); (b) is Guttman difficulty ordering defensible for *preference*
rather than *ability* items. The pre-publicity window is when a re-architecture verdict is free.
**2026-09-01 note: S-58 arguably strengthens the case for sending this — an outside
psychometrician is the one remaining source of independent instrument judgement that costs no
rater time.**

**S-07 — Migrate the rest of `schema.sql`.** `carried: 1` — **CODE COMPLETE; unapplied**
`company.domain` + 8 tables, per D-19. Verified on fresh Postgres 16. Application rides the next
deploy, then `seed_priors_model_run`. **Before applying, read D-19(a)'s note on `domain`'s UNIQUE
constraint (S-51 OPEN 2).** **This is the one launch-path item blocked on nothing at all.**

**S-09 — Feedback construct mismatch.** `carried: 0` — **DIAGNOSED and a fix DRAFTED 2026-09-01;
neither validated**
`anchors.json` grades feedback on frequency and directness; v2 items grade it on **exposure**.
**A poor gap result on feedback is not evidence the ladder failed.**
**2026-09-01, the citation-level diagnosis** (`FEEDBACK_DIMENSION_DIAGNOSIS_2026-09-01.md`):
across 24 round-1 citations from B and C, only 2–3 are cleanly on-axis. **Both raters, not one,**
cited general workplace-supportiveness evidence instead of critique delivery-style or frequency,
plus two concrete cross-dimension leaks (an Autonomy quote on P-04/C; Pace quotes on P-05 from
both). The existing `keep_distinct` already said "not whether feedback is nice" and did not
prevent it. **A fix is now written into `anchors_v3_PROPOSED.json`** naming what does not count
and the observed leaks. **Unvalidated, and possibly insufficient:** this may be an
evidence-scarcity problem as much as a wording one (§5's Feedback-THIN finding), and the Decision
precedent shows an anchor rewrite can be a complete no-op for the extractor. **Also now a
candidate instance of S-58 rather than a standalone dimension defect.**
**Also now a candidate instance of S-58 rather than a standalone dimension defect.**

**2026-09-01b — the fix as drafted was internally contradictory, and has been corrected.** The
morning `keep_distinct` declared recognition / psychological safety / anti-retaliation / "we care
about our people" language non-signals, while the 0.1 band directly beneath it still read
**"Harmony valued, conflict avoided, supportive or nurturing framing"** — unchanged from v1. Its
reconciling sentence ("extremely supportive and caring while giving feedback rarely and gently (low
band)") strengthened the association it meant to break. **Measured asymmetry:** a warmth descriptor
appeared at 0.1 with no counterpart at 0.9, so supportiveness evidence could only push a score down.

**This partly withdraws the diagnosis.** Round-1 citations such as "never retaliate" and "coworkers
care about your growth" are close to a **literal match for the frozen 0.1 band's own words.** Those
raters were following the anchor text, not drifting off-axis. The contamination was in the band
definition. The "off-axis rater error" framing in `FEEDBACK_DIMENSION_DIAGNOSIS_2026-09-01.md` is
withdrawn for that subset.

**Also withdrawn:** that document criticised P-04/B for "committing a 0.5 at 0.1 confidence rather
than treating the packet as uninformative." **0.1 confidence is exactly how the instrument says to
express that** — the frozen anchors define it as "almost nothing in the packet bears on this
dimension." There is no abstain option. Whether there should be is S-60, not a rater error.

**A third correction, same evening:** edit 2's `keep_distinct` explained the fix by QUOTING the v1
0.1 band's warmth phrase. `keep_distinct` is rubric-facing — `build_rubric_text()` emits it verbatim
to the model — so the parenthetical put the contaminant back into the instrument while describing
its removal, and would have confounded the measurement it was written to enable. Caught by an
assertion before any API call; moved to `_note`, which is not rubric-facing.

**Evidence scarcity was investigated and is NOT a collection-rule artifact.** Feedback comes back
THIN in 4 of 4 packets where the review-source recency cross-check fires and 4 of 6 where it does
not — see S-49. The cause remains unknown, which is what collector v4.8 now records.
**S-10 — The 65 calibration-probe calls. DEFERRED.** `carried: 3` Blocked on S-09.
**RED for unattended runs (live API spend).** 13 synthetic vignettes × 5 runs. No dependency on
the roster. A targeted feedback-dimension subset against v1 anchors would turn S-09's reasoning
into a measurement Julie could use *while* writing v3.

**S-11 — Calibration probe on decision and feedback**, multi-seed. `carried: 5` — **AT THE LIMIT.
Must be closed, re-scoped, or moved to §7 next session.** Recommendation: re-scope or retire — the
2026-09-01 work has partly overtaken it, since Decision and Feedback have both now been probed
against real packets by other means.
**S-60 — Nothing constrains how the company side may use a confidence field, and round 1 shows
confidence does not track reliability.** `carried: 0` — **NEW 2026-09-01b**
D-17(b) forbids filtering or weighting by confidence on the **person** side pending S-18. There is
**no equivalent rule on the company side.** Spearman(B-C disagreement, mean B/C confidence) =
**-0.073**: decision carries 3.2x pace's disagreement at above-average confidence, so a confidence
weight there would weight the worst cells as heavily as the best. **Nothing consumes the field yet,
which is exactly why this is cheap now.** Also holds the open instrument question S-09 surfaced:
**should the rater app have an abstain option**, given 0.1 confidence ("almost nothing in the packet
bears on this dimension") still requires committing a score, and the criticism of P-04/B for doing
precisely that has been withdrawn.

**S-61 — WITHDRAWN BEFORE OPENING, 2026-09-01b.** Proposed as "the single-required-review-source rule
may be manufacturing Feedback-THIN," then disconfirmed from data already on disk before an ID was
spent (see S-49). **Recorded so a later session does not re-open it: it was asked, it was answered,
the answer was no.** The ID is retired unused.

### Blocked on people — `carried:` frozen here

**S-12 — Hand `anchors_v3_PROPOSED.json` to Julie.** `carried: 4` **Content gate resolved
2026-09-01b; the file is ready and the covering message is now specified.**
The file carries the previously validated Collaboration/Innovation band-bleed fixes, the
**unvalidated** Decision rewrite (a measured no-op for the extractor), and a Feedback rewrite
corrected three times on 2026-09-01 — including a change to the **0.1 and 0.3 BAND TEXTS**, not just
guardrail prose, plus a new Collaboration guardrail. **Editing band text means output under this
file is not directly comparable to round 1.**

**The 6-call gate was run. Result: the anchor edit changes nothing measurable in the extractor.**
Scores moved ~6 cells by one band, against **9 of 36 cells that already carry non-zero SD across
five runs of identical input** — a strictly stronger intervention than the Decision test produced
less movement than the model's own run-to-run noise, and Decision replicated its no-op at 0.000.
Cross-dimension citation collisions by excerpt id: **v1 7/94, v3 6/91 — 7% both ways.**

**The finding that decides S-12 is the pair composition, not the rate.** Collaboration<->feedback is
the **top colliding pair for both Julie (4) and George (4)** and appears in **neither** version of
the extractor's top pairs. **The guardrail added on 2026-09-01b addresses a real human defect that
this extractor structurally cannot test, because it does not make that error.** The extractor's own
worst pair is decision<->pace, which the humans barely show.

**What Julie must be told, verbatim in substance:** this is not "anchor edits do not work." It is
that **the only test instrument available does not exhibit the defect being fixed**, so the edit
rests on expert judgement alone — hers — and no blind human pass can ever check it, because Carolynn
and George are permanently unavailable and she is excluded on authorship grounds (D-12(b)).

**D-21 was not satisfied and the gate stays a pilot:** one draw per arm. Pair composition reshuffled
completely between v1 and v3 (inno/pace=3 to deci/pace=3) but at 6-7 collisions across 15 possible
pairs that is uninterpretable, and no number from it is quotable. A compliant version is 36 calls.
**S-13 — Feedback anchor check vs. rater agreement.** `carried: 0` — **DATA HAS ARRIVED.**
Tooling was ready and waiting on data; the data returned 2026-09-01 and the check was performed
(S-09's diagnosis). **Effectively discharged into S-09 and S-58** — close it or re-scope it next
session rather than carrying it as "waiting."

**S-15 — The anchor-ambiguity flag.** `carried: 0` — **RAN AGAINST REAL DATA 2026-09-01. The
result is the headline finding of the round.**
`rater_agreement.py` + 16 tests, integer band distance over B and C, Julie as expert reference,
`expert_divergence` separate. **`run_agreement_report.py` was run against all 18 returns.**

**The result, against the pre-registered expectation:**
> The sensitivity warning recorded before the data arrived said: *"Two lawyers reading the same
> packet correlate heavily, so the realistic expectation over 36 cells is few flags, possibly
> zero. A near-empty REVIEW list is not evidence the rubric is unambiguous."*

**What actually happened is the opposite failure mode: 17 REVIEW, 12 WATCH, 7 AGREE.** Roughly
47% of cells are ≥2 bands apart and only ~19% agree exactly. **B and C are not correlated as
predicted — the measured Pearson correlation across their 36 paired cells is −0.195.** The
pre-registered warning guarded against manufacturing flags from a quiet result; the honest reading
of a loud one is that **the instrument, as worded, does not produce convergent readings between
two intelligent independent readers.** That is what S-58 now exists to explain.
**`expert_divergence` (D-12(c)) was checked and is NOT present** in the 7 B-C agreement cells —
max divergence from Julie there was 1 band. **Decision is the worst dimension: 0/6 agreement.**
**Do not retro-fit a looser threshold to make this look better, and do not treat the size of the
REVIEW list as licence to skip diagnosing why.**

**2026-09-01b — the correlation claim is corrected; the flag counts are not.**
**Evidence weighting was tried and does not work:** `min(quotes_B, quotes_C)` is **1 in 35 of 36
cells**, so the weight has essentially no variance (weighted r = -0.186 vs -0.195), and a "both
raters cited >=2 quotes" filter leaves **one cell**.

Cells cluster within packet, so a cell-level SE is too narrow — **the fourth appearance of the
clustering error §5 tracks, this time inside S-15's own headline.** Cluster bootstrap over packets
(n = 6, 20,000 draws), with permutation tests:

| pair | r | 95% CI | | perm p |
|---|---|---|---|---|
| **B-C (the headline)** | **-0.195** | **[-0.408, +0.069]** | **INCLUDES 0** | 0.28 |
| A-C | +0.401 | [+0.248, +0.568] | EXCLUDES 0 | 0.016 |
| A-B | +0.201 | [-0.175, +0.542] | INCLUDES 0 | 0.25 |

**The supportable claim is "uncorrelated."** The earlier reading — "not merely uncorrelated, faintly
negative" — put weight on a sign the data does not carry. **And two humans reading this rubric DO
converge measurably (A-C).** The sentence *"the instrument, as worded, does not produce convergent
readings between two intelligent independent readers"* is **withdrawn as stated.** Julie authored the
anchors and recognised or suspected the company on 3 of 6 packets, so A-C is not a clean blind-blind
pair and cannot replace B-C — but it does show the rubric is readable enough for two people to land
together.

**What survives untouched: the flag counts.** 17 REVIEW / 12 WATCH / 7 AGREE, ~47% of cells >=2 bands
apart, decision 0/6. Those are descriptive, not inferential, and the correlation was always the
weaker of the two claims. **Do not read this correction as the rubric being fine.**

**A property of the inputs that must be stated alongside the headline.** Carolynn cited **1.03 quotes
per cell** (35 of 36 cells have exactly one) against George's 3.58 and Julie's 3.22, and her variance
decomposition sits **below the chance baseline on both main effects**. **She did nothing wrong** —
`RATER_INSTRUCTIONS.md` requires "at least one passage." This is not a criticism of her, must never
be presented to her as one, and does not license discarding her data. It is why the B-C interval is
as wide as it is. A read-through impression that her notes frequently contradicted her scores was
checked mechanically over all 54 non-empty notes and found **2**; the impression was withdrawn.

**S-20 — Stray `SOLVERAH_HANDOFF.md`.** `carried: 1` Investigated; nothing references it; violates
D-11. **One line of disposition from Sebastian.**

**S-26 — Test 1 identified-condition re-check.** `carried: 5` — **AT THE LIMIT.** Close, re-scope,
or move to §7 next session.

**S-27 — Deduplicate project docs.** `carried: 2` Every handoff stored twice. Needs Sebastian.

**S-54 also lives here** — see Compliance above.

### Carried / low

**S-21 — Rung-4 prompt convergence.** `carried: 3` Candidate for an eighth gate rule.
**S-22 — `co3v2` "in the room" assumes co-location.** `carried: 3` Considered, not changed.
**S-23 — `pa1v2` simultaneity-vs-tempo confound.** `carried: 4` Accepted as minor.
**S-24 — `au3v2` dimension leak.** `carried: 4` Left deliberately; folded into S-17 as its one
inferential contrast. The tell is correlating more with decision than autonomy.
**S-25 — `au2v2` option length ratio is exactly 2.00.** `carried: 4` On the line; not changed.
**S-33 — Dead 7-dimension columns still on `company`.** `carried: 1` — retire with S-46.

**S-34 — Commit the 08-19 work.** `carried: 0` — **COMMITTED 2026-08-20; deploys still frozen**
Render does not serve `causal_bayesian_model`, so the freeze is intact. What remains is the
original second half: nothing merges or deploys to prod until the causal Bayesian model is
deployable. **2026-09-01: Sebastian had a separate coding agent working in the Solverah repo
concurrently — a live `.git/index.lock` was observed mid-session. The agent ran no git commands
after seeing it and created only new untracked files (`causal_graph/extremity_flag.py` and the
other 09-01 scripts, plus `.ps1` wrappers at the repo root). Those files are uncommitted and
invisible to whoever is committing.**

**S-41 — Scratch in the repo a run cannot delete.** `carried: 0` — **CLEARED 08-27**
**2026-09-01 addition, minor:** `causal_graph/_scratch_key_transfer.env` and
`_scratch_key_transfer2.env` exist in the repo. Both were used to move an API key to a sandbox and
**both have been truncated to empty**, but they cannot be deleted from the agent side and should
be removed by hand. `_test_anchors_v1_with_v3decision.json` is also there — a legitimate test
fixture, keep or move as preferred.

**S-47 — A fresh database cannot run the migration chain unmodified.** `carried: 1`
(a) `alembic_version.version_num` is `varchar(32)` and one revision id is 40 chars. Keep future
ids ≤32 chars and/or widen the version table in `env.py`.
(b) Pre-existing model-vs-migration drift; cosmetic. **On SQLite the chain dies earlier, so SQLite
dev DBs must come from `db.create_all()`, never the chain.**

**S-35 / S-40 / S-44** — resolved; retained in §6 reasoning. See §6.

---

## 4. Locked decisions — do not re-litigate; write an argument into the decision queue instead

- **D-01. Employers never see an individual's answers or six dimension scores.** If an employer
  ever sees anything it is a match result. **Honest limit:** the pull here is toward the
  *matching algorithm*, so rule 3's shuffle is the primary defense against aspirational
  answering, not the disclosure line. Enforced by `tests/test_employer_visibility.py` as a
  reachability allowlist. **Do not add a module to that allowlist to make it pass.**
- **D-02. Exactly four items per dimension.** Enforced by `score_all_dimensions()`.
- **D-03. Mean-of-5 for company-side runs.**
- **D-04. Ordering is server-authoritative.** The client sorts, groups and shuffles nothing.
- **D-05. No default for `SOLVERAH_FORM_TOKEN_SECRET`.**
- **D-06. Option order is never randomized.**
- **D-07. Every weakening of a contract raises rather than degrading to a safe default.**
- **D-08. RETIRED 2026-08-20.** It read *"P-05 stays — the only stage 1–2 company."* Its basis was
  wrong three ways: the roster lists Doist as **stage 3**; R/GA is also stage 3; there are **zero**
  stage 1–2 companies on the roster. **Stage was never a selection criterion.** **Doist stays
  regardless, on pole-coverage grounds.** The underlying concern is **re-filed against S-52**.
- **D-09. Blindness is not claimed.** Control is by citation; recognition is recorded as data.
  **This reconciles "all three raters are blind" with the recorded Wayfair recognition event.**
  **2026-09-01: the round-1 `recognition` fields make this concrete — Julie recognised or
  suspected 3 of 6; Carolynn and George recognised zero.**
- **D-10. Say "de-identified," never "anonymized."**
- **D-11. One handoff per chat**, at the top level of `Solverah_IP`.
- **D-12. The agreement rule is the one in `anchors.json`; Julie is rater A and is excluded from
  the flag.**
  **(a) Band distance, compared as integers — not a numeric threshold.** Same band = agreement;
  **one band apart = expected instrument resolution, NOT ambiguity**; **two or more = reword, do
  not average.** **Do not re-express this as a float.** `0.7 - 0.3 == 0.39999999999999997`, so a
  genuine two-band gap **fails** a `> 0.4` test. Regression-tested.
  **(b) Julie's scores do not enter the flag.** Compute over **B and C**; record Julie in full,
  labelled, as expert reference. **The ground is AUTHORSHIP, not blindness.** The flag estimates
  how far apart independent readers land on the same words; Julie has privileged access to their
  intended meaning, so pooling her yields a *different quantity*. **2026-09-01 empirical support,
  which was not available when this was decided:** her scores run ~1 band **lower** than both blind
  raters (mean band 1.83 vs 2.31 and 2.22) and reproduce the B-C consensus exactly on only 3 of
  the 7 cells where B and C agree.
  **(c) `expert_divergence` is a real signal.** Both blind raters agreeing *and* sitting ≥2 bands
  from Julie means they read the anchor consistently and differently from its author.
  **Checked 2026-09-01: not present in round 1.**
  **Rejected: median + outlier flag.** It presumes a true value and discards the dissent.
  **The dissent *is* the signal.**
- **D-13. `person_id` is `user.id`.** No separate `person` table.
- **D-14. `scoring_key_version` is `form_version` + scoring method**, joined — not either alone.
- **D-15. The submit endpoint returns no dimension scores.** **Extended 08-19: the post-submit
  experience is a completion state, full stop.** A qualitative narrative regenerated per sitting
  is still a gradient a retaker can watch move.
- **D-16. Raw responses are stored per item, append-only, never overwritten.** Reconciled with
  deletion rights 2026-08-20 — see D-23. D-16 governs scoring integrity, not identity retention.
- **D-17. Person-side confidence is the Guttman error count, and it describes the score, not the
  respondent.** e ∈ {0,1,2}; **stored value = 1 − e/2**. **Semantics, binding on every consumer:
  low confidence is never read as gaming; high confidence is never read as honesty.**
  **(a)** Feedback's stored confidence stays NULL pending S-18.
  **(b)** No analysis upstream of S-18 may filter or weight by confidence.
  **(c)** e depends on rung order — a difficulty reordering is a scoring-key change.
- **D-18. Completion is a fact about an instrument, not about the user.** **The check must never
  break auth.**
- **D-19. schema.sql's company side lives IN the app schema, minimally translated.**
  **(a) One company universe** — one nullable-unique `domain` column. **⚠ That UNIQUE constraint
  is what makes v2 segmentation (D-22) a migration rather than a data change.** See S-51 OPEN 2.
  **(b) No registry tables.** **(c) Postgres enums become String + CheckConstraint.**
  **(d) schema.sql's `recommendation` is created as `match_recommendation`.**
- **D-20. Experienced outcomes train through OrderedLogistic — never a dichotomized Bernoulli.**
  The cut point is a hidden researcher degree of freedom. **The two outcomes are never pooled.**
  **Build deferred until placement data is in sight; reopen as a NEW item id.**
  **2026-09-01 relevance:** this is also why a systematic extractor bias is not automatically
  fatal — the match model's real calibration target is outcome data, not the ground-truth set, so
  a *consistent* offset can in principle be absorbed downstream. That is an argument for not
  panicking, **not** an argument that the extractor's calibration does not matter.
- **D-21. The seeds rule, enforced at the point a number is produced.** **≥3 independent draws,
  paired where arms are compared, dispersion reported** — otherwise it is a pilot and **no number
  is quoted**. **(a) Draws, not only seeds.** **(b) Enforcement is at production, not in prose.**
  **(c) Scope:** governs numbers entering a document as evidence, not deterministic production
  computation. **Violated once more on 2026-08-20 and caught:** per-arm RNGs diverged, so
  contrasts were silently unpaired while reported as paired.
- **D-22. One company = one culture score, for v1. Segmentation is a v2 feature.**
  **Rejected: excluding heterogeneous employers** — biases toward homogeneous white-collar
  employers. **Rejected: building the segment field now.** **Two consequences NOT deferred:**
  scope-label at creation time, and the `domain` UNIQUE collision. Both in S-51.
- **D-23. Account deletion de-identifies, it does not destroy research rows.** The `user` row
  becomes a tombstone; resumes/intakes/recommendations/parse-corrections are destroyed;
  `AssessmentResponse` and `PersonDimensionScore` are RETAINED against the tombstone id.
  **Rejected: keeping parse corrections de-identified** — parsed resume content is itself
  identifying. Age floor 16+, acceptance recorded with terms version, US-only launch scope.

---

## 5. Measured results worth not re-deriving

### Round 1 — the rater returns (all 2026-09-01, from the 18 returned JSONs)

- **The S-15 flag fired far harder than pre-registered: 17 REVIEW / 12 WATCH / 7 AGREE** over 36
  B-C cells. ~47% of cells ≥2 bands apart; ~19% exact agreement. **Pearson correlation between
  Carolynn's and George's 36 paired scores is −0.195** — not merely uncorrelated, faintly
  negative. The pre-registered expectation was "few flags, possibly zero" on the reasoning that
  two lawyers would correlate heavily. **They did not.**
- **Decision is the worst dimension: 0 of 6 packets in agreement.** Feedback next at 1 of 6.
- **`expert_divergence` (D-12(c)) is NOT present in round 1** — on the 7 cells where B and C
  agree, Julie is at most 1 band away.
- **Julie scores systematically lower than both blind raters:** mean band 1.83 vs Carolynn 2.31
  and George 2.22 (bands indexed 0–4). On the 7 B-C agreement cells she matches exactly on 3.
- **Recognition, from the `recognition` fields:** Julie recognised or suspected the company on
  **3 of 6** packets (P-01 Oscar "I have recruited from this company"; P-02 Best Buy, explicit and
  correct; P-03 Akuna, narrowed but unsure). **Carolynn and George recognised zero.** This is
  D-09 working as designed — recognition recorded as data, not a blindness failure.
- **NEW 2026-09-01 — band-usage distributions, all 36 cells each.** Counts at 0.1/0.3/0.5/0.7/0.9:
  **Julie 8/6/10/8/4**; **Carolynn 1/10/9/9/7**; **George 4/8/7/10/7**; **the LLM extractor
  0/10/6/16/4**. Extreme-band usage (0.1 or 0.9): Julie 12/36, George 11/36, Carolynn 8/36, **LLM
  4/36 and never once at 0.1.** **Carolynn used the bottom band exactly once in 36 opportunities**
  while using the top band seven times — a floor reluctance of her own, milder than the model's
  but in the same direction. Raw counts, no inferential claim attached; feeds S-58.
### NEW 2026-09-01b — the free S-58 analyses and the 22-call run

Pre-registered in `PREREG_S58_2026-09-01b.md` and `PREREG_COMBINED_RUN_2026-09-01b.md`.

- **Global-impression test: NULL.** Packet-effect eta-sq against a 10k permutation null (baseline
  5/35 = 0.143) — A 0.175 (p=0.31), B 0.059 (p=0.87), C 0.214 (p=0.19). **No human rater shows a
  packet effect distinguishable from chance.** LLM 0.305 (p=0.045), structural — it scores six
  dimensions in one call.
- **Passage-level construct agreement: 65% overlap against a 22.6% permutation null, p = 0.0002**
  over 34 passages cited by >=2 raters. Strong construct drift disconfirmed; 35% zero-overlap.
- **Spearman(B-C band distance, mean B/C confidence) = -0.073** over 36 cells. Mean band distance by
  dimension: decision 2.67, autonomy 1.67, collaboration/feedback/innovation 1.33, pace 0.83.
- **S-15 correlations, cluster bootstrap over packets (n=6, 20k draws):** B-C **-0.195, CI
  [-0.408, +0.069]**, perm p 0.28 — includes zero. A-C **+0.401, CI [+0.248, +0.568]**, p 0.016 —
  excludes zero. **Evidence weighting is inert here:** min(quotes_B, quotes_C) is 1 in 35 of 36 cells.
- **Citations per cell: A 3.22, B 1.03, C 3.58.** C wrote zero free-text notes in 36 cells.
- **0.1 use by dimension** (A+B+C, 18 opportunities each): autonomy 4, decision 4, innovation 2,
  feedback 2, collaboration 1, **pace 0**.
- **Extremity-flag fire rate under `ForcedChoiceBandProbe(allow_off_axis=True)`: 1/16 (6%)**, against
  2/16 under the binary probe, same cells and same saved citations. Both pre-registered predictions
  held. All five probed feedback cells returned **zero** floor matches.
- **v3 anchors move the extractor less than its own run-to-run noise.** ~6 cells moved one band;
  **9 of 36 cells carry non-zero SD across five runs of identical input.** Decision 0.000, replicating
  the morning's no-op.
- **Cross-dimension citation collisions by EXCERPT ID — humans and extractor in the same units for
  the first time** (159/159 human-cited eids exist in the model's parsed excerpts): **Julie 20/93 =
  22%, George 19/106 = 18%, Carolynn 4/33 = 12%, extractor v1 7/94 = 7%, extractor v3 6/91 = 7%.**
  The extractor separates constructs 2-3x more cleanly than any human rater. **A text-matched version
  of this metric returned 0 for the extractor and was an ARTIFACT** — the model generates spans while
  raters select from a fixed excerpt inventory. Do not use text matching for this.
- **collaboration<->feedback is the top colliding pair for Julie (4) and George (4) and is absent from
  the extractor's top pairs under both v1 and v3.** The extractor cannot validate a fix for a defect
  it does not have.
- **inno<->pace was the extractor's top v1 pair (3)** — one of only two pairs the frozen anchors guard
  in both directions. n=3; consistent with the human-side finding that guardrail presence does not
  obviously reduce collision, and not strong enough to carry alone.
- **Feedback-THIN is NOT a collection-rule artifact:** THIN in 4/4 packets where the review-source
  recency cross-check fires and 4/6 where it does not.
- **Integrity check, reusable:** `anchors.json` recomputes to `anchors_hash` **`55c4501b25c5`**,
  byte-identical to the value recorded in all 18 rater JSONs. The frozen file is provably what round 1
  was scored against. `build_rater_page.py` hashes `{k: v for k, v in cfg.items() if not
  k.startswith("_")}` with `sort_keys=True, ensure_ascii=False`, sha256, first 12 chars.

### The LLM extractor vs human consensus (2026-09-01, first execution of S-49's second purpose)

- **Mean |LLM mean − human median| across 36 cells = 0.114**, roughly half a band. Most cells fall
  at 0.0–0.2. Worst two at 0.300: P-02/autonomy (both humans agree closely at 0.7/0.5, LLM at 0.3
  — a real miss) and P-04/innovation (humans themselves split 0.9/0.3, so the "consensus" it is
  scored against is not meaningful there).
- **Mean within-model SD across 5 runs = 0.023**, max 0.098, many cells exactly 0.000.
  **Repeated sampling of one model is therefore not a fix for anything** — there is almost no
  decoding noise to average away, and the 0.114 gap is systematic, not sampling variance. This
  settles the "score it N times and average" idea empirically.
- **THE FLOOR BIAS: the extractor never assigned the 0.1 band. Not once, in 72 independent
  scoring instances across two separate runs**, while human raters used 0.1 at least five times on
  the same packets (P-01/autonomy-C, P-04/decision-C, P-05/decision-B, P-06/autonomy-C,
  P-06/innovation-C). On the three cells where it declined the floor its own citations supported,
  SD was 0.000 — it is consistently, not randomly, refusing.
- **A prompt-level calibration fix does NOT work.** Adding an explicit instruction — *"if the
  cited evidence is unanimous and clearly one-sided, use the most extreme band; do not default to
  a more moderate band as a hedge"* — moved **zero** of the three test cases. All three stayed at
  0.3, with citations if anything more unanimous on the re-run. **This is structural, not a
  prompting gap; do not spend more on prompt variants for it.**
- **The Decision-anchor rewrite is a measured NO-OP for the extractor.** Re-running all six
  packets against a copy of `anchors.json` carrying `anchors_v3_PROPOSED.json`'s rewritten
  `decision` block produced **identical means on every packet** (0.70/0.58/0.70/0.50/0.70/0.70),
  with SD 0.000 on five of six both before and after — the same deterministic call, not a
  coincidence of averaging. **An anchor rewrite can change nothing about extractor behaviour.**
  Whether it helps human raters is untested and now untestable by another blind pass.
- **What the extractor actually cites on Decision is on-axis.** All 18 Decision quotes across the
  six packets are genuinely about data-vs-judgement; none show the Autonomy-flavoured conflation
  Carolynn showed. **This rules out anchor ambiguity as the cause of the extractor's Decision gap**
  and explains the no-op above.
- **RETRACTED, same day, before it was acted on: a "leans toward the more favourable pole"
  theory.** It held 6/6 on Decision and then failed to reproduce on Autonomy (mixed in every
  direction, sometimes below both raters) or Feedback (leans toward the *lower*-scoring rater in
  4 of 6). Source-tag weighting was checked as an alternative explanation and also fails
  (P-02/autonomy cites three company-authored quotes and scores low; P-04/innovation cites three
  noncompany quotes and scores high). **The floor bias is what replicated; the directional story
  did not.**
- **Reading the five floor cells individually splits them 3/2.** Genuine floor-avoidance on
  P-06/autonomy (3 of 3 citations match the 0.1 band, zero countervailing), P-01/autonomy (2 of 3,
  one countervailing), P-06/innovation (2 of 3). **Not floor-avoidance on P-04/decision and
  P-05/decision** — on both, the two humans sat at opposite extremes and the extractor landed near
  the non-0.1 rater, so the "human used 0.1" comparison point is itself a minority read.
  **Conflating all five would have overstated the case.**

### The extremity flag and its probe (2026-09-01)

- **Two designs failed and are recorded so they are not rebuilt.** (1) Source-tag counts cannot
  work: `classify_source` encodes *authorship*, not valence. (2) A **symmetric** citation-consistency
  check ("all citations match the extreme band but the score sits inside the pole") is disproved by
  P-03/autonomy — three citations all matching the 0.9 band, score 0.7, and the human median was
  *also* 0.7. Citing vivid extreme quotes and scoring moderately is ordinary behaviour.
- **The reluctance is task-shaped, not evidence-shaped.** The same model that refuses to score a
  company 0.1 will answer **True** to "does this fragment match this description?" on the exact
  same text, with easy controls correctly rejected. This is a real dissociation and is what makes
  the workaround possible.
- **Probe comparison over 46 real quotes, four pre-registered categories** (A floor / B leaning-low
  / C off-axis fed to the wrong dimension / D opposite pole), same labels and seed for all three:
  | design | A | B | C | D |
  |---|---|---|---|---|
  | binary membership | 12/13 | 6/10 | **12/12** | 11/11 |
  | forced choice | 10/13 | **8/10** | 9/12 | 11/11 |
  | **forced choice + off-axis escape** | 9/13 | **8/10** | **12/12** | 11/11 |
  **Binary over-matches at the 0.1/0.3 boundary** (it sees one description in isolation, so partial
  resemblance earns a yes — proof case: decision/"combines systematic pricing infrastructure with
  trader judgment", which names both poles and still matched the floor). **Plain forced choice
  fixes that but cannot say "none of these"**, so it maps negative-sounding off-axis quotes onto
  the low band, including a lexical trap ("mandatory overtime is required", a pace quote, fed to
  the autonomy probe whose 0.1 text says "mandatory procedures"). **Forced choice plus the escape
  hatch keeps both fixes and is the settled default.**
- **Fire rate 2 of 16 probed cells (12%)** — measured with the *binary* probe, so this number is
  now stale; see S-59. One confirmed true positive (P-06/autonomy, human C = 0.1). One
  unadjudicated (P-06/feedback — the probe's labelling looks right, but the human scores on that
  cell are independently known to be unreliable per S-09, so it cannot be scored either way).
  **Predicted but not measured under the settled probe: P-06/autonomy still fires, P-06/feedback
  stops.**
- **A caution about the test suite:** `test_extremity_flag.py` validates flag LOGIC against hand
  labels. It does not validate the labels. A green suite is not evidence the probe is accurate —
  and in fact the boundary test showed several of those hand labels to be wrong. This is S-58
  observed inside the project's own tooling.

### Earlier results, retained

- **RETRACTION 2026-08-20 — the S-48(b) confounder-spread analysis answered a question the
  ground-truth set does not pose.** `assemble_training_data.py` draws its company universe from
  `outcome_appeal JOIN recommendation` and `outcome_experienced`; **`is_ground_truth` never enters
  it.** **Withdrawn:** the ≥6-off-mode comp requirement, "comp is the binding constraint", the
  |corr| ≤ 0.20 rule, the set-designer's premise. **The SIZE analysis is NOT withdrawn.**
- **What survives the retraction, landing on the PRODUCTION model:** **(a) Clustering/overconfidence.**
  **64× the rows improved the reported SE 8.4× and real uncertainty only 2.2×; the overconfidence
  ratio grew 1.6× → 6.2×. Effective N for a confounder weight is distinct companies, not rows.**
  Third appearance of this error. **(b) Zero spread yields a confidently wrong coefficient** —
  SD 0.000, bias equal to the entire true weight.
- **Feedback comes back THIN in 8 of the first 10 built packets** — a source-class pattern, not a
  company-selection problem. P-01/Oscar Health and P-09/Warby Parker are the only COVERED cases.
  Across 8 independent builds spanning very different industries and sizes, Feedback evidence is
  scarce almost regardless of employer. **Hudson River will very likely also come back THIN; it is
  not a fix.** **The open question: can Feedback be scored reliably, by raters or the extractor,
  from evidence that is consistently sparse?** **2026-09-01 makes this sharper — the round-1
  Feedback citations show both raters filling that scarcity with off-axis material rather than
  reporting low confidence.**
- **S-48 SIZE (simulation, 400 trials/cell).** Naive pooling says N=6 gives power ≥0.95 for a
  half-band miscalibration; **corrected for within-company correlation the naive false-positive
  rate inflates to 0.35–0.49** against nominal 0.05, and reasonable power needs **N≈15–19**.
  Simulation under stated assumptions — not a measurement.
- **Roster facts, verified 2026-08-20:** stage 5 is **58%** (11/19); the 78% figure belongs to
  **comp = 3** (15/19); comp ∈ {3,4,5} with zero below-market; **P-04 is R/GA the digital agency
  (stage 3), not RGA Reinsurance.**
- **The person side reproduces `PERSON_LATTICE` end to end** (08-19 smoke test): 0.25 / 0.75 / 0.5
  / 0.25 / 0.25 / 0.5. **The distinct values are the finding, not the row counts.**
- **The S-07 migration is equivalence-verified** on fresh Postgres 16; autogenerate shows zero
  differences; downgrade removes all 8 tables + `domain`. Suite 399 → **408**.
- **The serving path is anchored analytically and mutation-verified.** Perfect match at neutral
  priors = **0.5 exactly**; the pole-penalty fix is bitwise-verified; p_fit monotone in |gap|.
  Suite 408 → **421**.
- **The confidence measure** is implemented and mutation-verified. Suite 421 → **430**.
- **The seeds rule is enforced and mutation-verified.** Suite 430 → **442**. The mutation that
  matters leaves every headline VALUE identical and changes only dispersion.
- **STATE itself verifies clean** as of the 08-20 closing run: **31 passed / 0 failed / 1 skipped**.
  Suite 442 → **458**. **NOT re-run against this 2026-09-01 rewrite.**
- **The three-way dispersion diagnostic is mutation-verified** (08-20, re-verified at rebuild).
  12 tests; 5 planted mutations each caught.
- **The pooled 2×2's recorded CI was too narrow.** Collapsing 20 correlated cells to 5 seeds:
  point estimate **+0.005 (unchanged)**, **95% CI [−0.080, +0.091]** against [−0.049, +0.059].
  **"No detectable effect" is unchanged and better supported; the precision claim was overstated.**
- **The 2.5x rows figure is RETRACTED.** Cannot rule out a true effect below ~0.10.
- **The 5-point lattice attenuates correlations by ≈0.63** (n=200k/cell). **A latent 0.70 can never
  present above ~0.44.**
- **Both person-side analyses need N ≥ 300.** Climb 0.37/0.82/0.96 at N=100/300/500; composition
  0.26/0.55/0.79. **Simulation only — no respondent data exists.**
- **Re-identification:** 5 of 6 companies identified HIGH on 3/3 runs by `gpt-5.5-2026-04-23`.
  Only Akuna survived. **Reader-class dependent** — **confirmed by round 1: the two lawyers
  recognised nothing, Julie recognised or suspected half the set.**
- **Source-class composition:** **P-05 has ZERO non-company excerpts.** Only P-01, P-02, P-04, P-06
  can register non-company support at all. **So "this score has non-company support" will mostly
  mean "this company is large or public," not "this score is well-evidenced."**
- **Packet fidelity (qualitative).** Quotes spot-verified in real time as built; Julie's read judged
  them accurate overall with the P-02 caveat. **It addresses fabrication, not selection bias, and
  it missed one — see S-53.** **2026-09-01: all 18 extractor citations verified against the packet
  text via `scorer_pipeline.verify_result`, so the dash/quote normalisation works on that path.**
- **Test 1, blind vs. identified:** clean null. 0/36 cells beyond 1.5×SE, mean |delta| 0.0133.
- **Coarse instrument resolution is not expensive for weight recovery.** Fisher information goes as
  the predictor's *variance*, not its cardinality. **Range restriction is the expensive thing.**
- **The gate's honest limit:** it catches enumerated structural classes. Passing it is not evidence
  the ladder works.
- **Compliance audit (2026-08-20).** 20 gaps mapped with file:line evidence; Phase 0 implemented
  same day. Three structural findings: the legal layer did not exist while intake REQUIRED consent
  to it; marketing claimed "shared only with your consent" while resume text flowed to LLM
  providers undisclosed; no deletion path existed and D-16 needed D-23 before one could be built.

---

## 6. Closed — IDs retained so stale references resolve correctly

- **S-42 — `.env` held production JWT-cookie values overriding `app.py`'s dev defaults.** CLOSED
  2026-08-22. Fixed by removing both lines from the local, gitignored `.env`; necessarily
  `[UNVERIFIED]` by `check_state.py`.
- **S-55 — Land the compliance batch.** CLOSED 2026-08-20 on **31 passed / 0 failed / 1 skipped**.
  The audit gates fired on first exercise (react-router 7.14.1 vulnerable range; setuptools
  PYSEC-2026-3447), both fixed and pushed, CI green. check_state caught real drift: the batch was
  committed while STATE said otherwise, and four analysis files had never landed on disk (rebuilt
  and re-verified). **Checker lesson:** prose ABOUT commit status must keep the word "uncommitted"
  away from blocks naming files.
- **S-50 — Anonymization ruleset sign-off.** CLOSED 2026-08-20. Three tracked items were already
  decided as A1–A4 (STATE had been reading the stale subfolder `_STATE.md`); six others were
  genuinely open and Julie answered all six. **Five of six need no packet rework.**
- **S-37 — Locate the code→company map and confounder table.** CLOSED 08-19b.
- **S-16 — The ground-truth roster document.** CLOSED 08-19b; supplied 08-20. Two lessons: it
  hunted the wrong filename for four sessions, and it sat under *Blocked on people* where
  `carried:` freezes, so nobody asked — and the answer took one sentence.
- **S-28 — Build `check_state.py`.** CLOSED 08-19b. **Honest limit, four demonstrations: it cannot
  verify a claim that cites no artifact.**
- **S-04 — Seeds-rule enforcement mechanism.** CLOSED 08-19b → **D-21**.
- **S-31 — Build the confidence measure.** CLOSED 08-19b. 9 tests, 4 mutations.
- **S-06 — `OrderedLogistic` path.** CLOSED 08-19b by decision → **D-20**.
- **S-38 — Migrations run silently.** CLOSED 08-19b. `env.py` never called `fileConfig`.
- **S-43 — The assessment has no entry point.** CLOSED 08-19 — **it ships as Work Pulse.**
- **S-01 — Build the person-side form.** CLOSED 08-19.
- **S-02 — Enforce employer-visibility in the data layer.** CLOSED 08-19.
- **S-39 — Provision `SOLVERAH_FORM_TOKEN_SECRET`.** CLOSED 08-19. **Do not rotate mid-form.**
- **S-32 — Apply the migration.** CLOSED 08-19 (person-side).
- **S-36 — Which rater letter is Julie?** CLOSED 08-19: **A = Julie, B = Carolynn, C = George.**
- **S-30 — The React assessment component.** CLOSED 08-19.
- **S-29 — Locate the rater HTML generator and schema.** CLOSED 08-19 — **18 files, not 6.**
- **S-08 — Populate `scoring_key_version`.** CLOSED 08-19 for the person side.
- **S-14 — Notify George.** CLOSED 08-18.
- **Anonymization standing alarm** (old item 25). CLOSED 08-18 — collapsed to D-10.
- **The funnel question.** Decided in practice by S-43.
- **Item ratification.** `assessment_items_v2.yaml` active, rules 1–7 enforced.
- **S-35 — The `> 0.15` agreement threshold was never a real rule.** Resolved by D-12. **0.15 sits
  below one band (0.2)**, so it would have flagged as ambiguity what the real rule calls expected
  resolution.
- **S-40 — A test suite asserted an order it could not detect losing.** Resolved. Refixtured to
  `zulu, mike, alfa`. **Applied prospectively four times since**, most recently in the 09-01
  boundary test's use of objectively-labelable off-axis and opposite-pole controls.
- **S-44 — An inherited deadline outlived the condition that created it.** Resolved. **The urgency
  survived the work that removed it.** The mirror case also occurred. **The rule cuts both ways.**

---

## 7. Won't do

- **S-19 — `pace → autonomy` and `pace → feedback` as category-3 causal candidates.**
  Moved here 2026-08-19 at `carried: 6`. **Rejected alternative:** carry it once more pending pilot
  data — exactly the pattern the counter exists to stop. **If pilot data shows the correlation,
  reopen as a new ID.**
