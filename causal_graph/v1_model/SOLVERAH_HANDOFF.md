# Solverah — Project State & Decisions (handoff)

Paste this into a new chat (or add to project knowledge) to restore context. Custom instruction to honor: be logical and future-thinking, do not be agreeable — push back.

_Last updated: 2026-07-23 (merged the comp-confounder redefinition + the ground-truth two-rater calibration exercise into the canonical doc)._

## What Solverah is
A candidate ↔ company work-culture fit matcher. v1 matches a person to a company (role/team matching is later, once companies input their own data). Company-first because company culture can be inferred from scraping; role/team data can't yet.

## The model (built + validated)
* Causal Bayesian model in PyMC. Files live in `causal_graph/v1_model/`.
* Each dimension: `Person score` + `Company score` → deterministic Fit node = signed gap (`person − company`). Signed, not absolute (direction matters).
* Outcome = logistic on a linear predictor: `logit(P) = intercept + Σ (mag·|gap| + dir·gap) over dims + Σ (weight · confounder)`.
   * `mag` = symmetric penalty (any mismatch hurts). `dir` = directional asymmetry.
   * Two features per dim because a signed gap can't enter a logit as one linear term.
* Experienced-fit outcome is a 1–5 scale → that training run uses OrderedLogistic, NOT Bernoulli. The fast "appeal" yes/no outcome stays Bernoulli. Same linear predictor, two outcome heads.
* Config-driven: `solverah_model_config.yaml` = structure (dims, confounders, kinds). `priors.yaml` = numbers (every weight is `{mean, sd}`, separate file so real priors are a file swap). Adding a dimension/confounder = edit YAML, no code change.
* Confounders enter as raw covariate terms (continuous standardized via fixed `scale`; categorical one-hot via `levels`), and also point into the company-side scores in the DAG.
* Validated: synthetic recovery curve shows the posterior moving from prior toward a planted truth as data grows (updating works). Known limit: a very strong coefficient shrinks slightly (logistic saturation) — fine for ranking. **Framing caveat (see below): "validated" means the MACHINERY updates correctly; the priors themselves are still unvalidated expert opinion until outcome data arrives.**

## Dimensions (6 active, 2 on-deck)
Active: autonomy, pace, collaboration, feedback, innovation, decision. On-deck (inactive): structure, orientation. Each is bilateral, both poles legitimate, non-overlapping. Scale is 0–1: 0 = low pole, 1 = high pole, identical on the person and company sides (so the signed gap is meaningful).

## Confounders
Active + measurable: stage_size (biggest — common cause of all dims), comp, industry. Inactive: prestige. Unmeasurable (documented, excluded): manager_quality. Rule: confounders go IN the model (not just filters); adjust for common causes, NOT mediators or colliders.

* **stage_size** — company stage/size as an ordered index 1–5 (1 pre-seed/seed <20 · 2 Series A–B 20–100 · 3 growth 100–1,000 · 4 large 1k–10k · 5 enterprise 10k+). Record raw headcount too. Config key `stage_size`; workbook/label `stage_index`. `kind: continuous`, `scale {mean 3.0, sd 1.5}` placeholder.
* **comp — REDEFINED 2026-07 to market-relative pay POSTURE, not dollars.** Absolute dollars aren't a company-level property (they vary within a company by role/level/geo more than across peers) and are mostly explained by industry+geo, so they double-count `industry` and don't isolate the causal signal. What biases pace/autonomy is the pay posture vs. the talent market. Encoding: ordered band 1–5 (1 well below … 3 at market … 5 well above), vs. talent-market peers (same industry/stage/geo) for COMPARABLE roles. `kind` stays `continuous` (one ordered weight, NO code change); `scale {mean 3.0, sd 1.0}` placeholder. Self-centering, so far less collinear with `industry` than raw dollars. Config/DB key stays `comp`; `comp_vs_market` is the human label. Make role-conditioned when role/team matching lands.
* **industry** — categorical, one-hot via `levels` [tech, finance, healthcare, retail, other].

## Company scoring = an LLM (not "the model")
The causal Bayesian thing is *the model*. Company scores are produced by *an LLM* that reads scraped text and emits 0–1 per dimension (+ confidence + source flag). Keep the terms distinct: the ground-truth exercise below validates the LLM extractor, not the model.

## Key decisions locked
* Measurement (person side): single-axis, behavioral forced-choice items (normative, comparable to company scores). No "professionally correct" answer. Past-behavior framed. 24 draft items in `assessment_items.yaml` / `Solverah_Assessment_Items.docx` — need bias-testing.
* Company scoring: scraped/researched → 0–1 per dim + confidence + source flag (scraped→declared upgrade path). THE #1 unsolved pipeline. A ground-truth company set (below) calibrates it. Confounder `scale` stats are placeholders — replace with real distributions once the ground-truth set is scored.
* Outcomes: two SEPARATE labels — `appeal` (fast, biased toward "looks like a fit") vs `experienced` (slow, true, 1–5). Never averaged. Collect appeal on recommendations (incl. non-pursued) + add exploration to break the feedback loop.
* Collider trap: data is conditioned on "a match formed"; capture the full funnel so it's visible. Outcome data is a known deferred problem — v1 = expert priors, instrument now, train later.
* Predictions vs outcomes: predict for everyone (rank against all companies); TRAIN only on the few pairs that have a real outcome.
* Priors: expert-elicited via `Solverah_Priors_Form.docx` (partner answers plain-English multiple-choice; an internal appendix maps her answers → priors.yaml numbers). DELETE the appendix from her copy before sharing. "Wisdom of crowds" only works for OBSERVABLE quantities (e.g., scoring companies), NOT for the causal weights — don't crowd-source the priors.
* **Company scoring is validated by two blind human raters (2026-07).** One rater can't be validated — a single expert's scores are indistinguishable from that expert's lens. Company scoring is an OBSERVABLE quantity, so wisdom-of-crowds belongs here (unlike the priors). On rater disagreement >0.15 on a dimension: reword the ambiguous rubric anchor — do NOT average.

## Ground-truth calibration exercise (2026-07 build)
Purpose: produce a small set of hand-scored companies to (a) calibrate the person↔company scale, (b) validate the LLM extractor, (c) replace the confounder `scale` placeholders with real distributions.

* **Two human raters, blind + independent.** Each gets their own copy; neither sees the other's numbers. Merge both into the master workbook; the Agreement tab flags per-dimension gaps > 0.15.
* **Packet = frozen, anonymized scraped text**, identical for both raters (and later the LLM). Same input the LLM sees → clean test of extraction. Fixed source-mix per company (careers page + latest 15 reviews + 2–3 job posts + culture/eng blog + recent news). Confounders are NOT in the packet (they'd re-identify; they live in the roster).
* **No-priors control = anonymize (primary) + low-profile companies (insurance) + a recognition Y/N flag.** Refined rule: avoid companies famous FOR their culture — their distinctive way of working is their fingerprint and can't be scrubbed without deleting the signal. Ordinary, merely-known companies are fine once anonymized.
* **Roster v2:** 18 ordinary companies chosen by archetype for pole spread; culture-legends excluded. Known gaps: skews stage 5 (ordinary known cos are big); "blunt feedback" pole under-anchored (bluntness lives in the legends we avoid); confounders are estimates to verify during packet build; add 1–2 genuinely small cos from Sebastian's own reach for stage 1–2.
* **LLM as a 3rd scorer: DEFERRED** until the two humans validate the rubric first. Then run the LLM on the same packets and compare human consensus vs LLM.

## Files that exist (in the repo / outputs)
* `build_model.py`, `solverah_model_config.yaml`, `priors.yaml` (the model)
* `schema.sql` (Postgres: person/company dim scores, confounders, recommendations, funnel, outcome_appeal, outcome_experienced, model_run, weight_posterior — long format, versioned). NOTE: `comp`/`stage` are 1–5 in `value_num`; a doc-comment documents the encoding; the DB does NOT range-check (loader + workbook dropdowns are the guardrail). No DDL change was needed for the comp redefinition.
* `assessment_items.yaml` + `Solverah_Assessment_Items.docx`
* `Solverah_Priors_Form.docx` (partner priors elicitation + internal answer key)
* `SOLVERAH_HANDOFF.md` (this file)
* **Ground-truth exercise (2026-07):**
   * `Solverah_Company_Rating_Rubric_v2.docx` — anchored 0–1 rubric, 6 dims + comp band + talent-market reference class + anti-bias gates
   * `Solverah_Company_Scoring_Workbook_v2.xlsx` — long-format; Companies/Scores/Agreement tabs; `comp_vs_market` column; auto flags gaps >0.15
   * `Solverah_Evidence_Packet_Protocol.md` — packet rules, anonymization protocol, leakage check, workflow, per-company template
   * `Solverah_Ground_Truth_Roster_v2.md` — the 18 companies + coverage check + gaps
   * `Solverah_Packet_Prep_Checklist.md` — day plan for building packets

## Data flow (storage → training)
Tables store person & company dim scores separately (long format). A training row = a (person, company) pair WITH an `outcome_experienced`. A join+pivot assembles per-dim arrays → `fit_posterior(person, env, conf, outcome, ...)` → posterior → snapshot into `weight_posterior`. This join-and-pivot glue is not written yet.

## Toolchain notes
* Windows, python.org Python 3.10, pip. PyMC 5.25 installed.
* pytensor C-compile is FRAGILE (MSYS2 g++ 16 + MSVC-Python mismatch → CompileError). Workaround: `os.environ["PYTENSOR_FLAGS"] = "cxx="` at top of build_model.py forces Python mode (works, slow). Real fix for speed = conda-forge PyMC. Sampling at n=5000×4chains ~hours in Python mode.

## Framings that survived pushback (keep these honest)
* "Validated" = the machinery updates correctly; the priors are unvalidated expert opinion until outcomes arrive.
* Person↔company SCALE calibration is load-bearing — same latent 0–1 scale both sides, or the signed gap is meaningless. Treat it as higher-priority than its old "page-1 risk" billing.
* Inputs (the company-scoring pipeline) are the long pole; don't polish coefficients while inputs are unbuilt.
* Confounders go IN the model; adjust common causes, not mediators/colliders.

## Open / next
1. **Company-scoring pipeline** (long pole; where crowd-sourcing DOES belong). IN PROGRESS: ground-truth two-rater exercise — build packets → both raters score blind → merge → Agreement → reword ambiguous anchors → then add LLM as 3rd scorer.
2. Replace confounder `scale` placeholders (`comp`, `stage_size`) with real distributions once ~15 companies are scored.
3. DB → model glue: `assemble_training_data(db) -> (person, env, conf, outcome)`.
4. Expert priors: partner fills the form → convert to `priors.yaml`.
5. Assessment: bias-test items, build survey, write scoring (yaml → 0–1 + consistency).
6. Person↔company scale calibration check (load-bearing) before trusting live rankings.
7. App/serving integration (Flask) + instrumentation logging.
