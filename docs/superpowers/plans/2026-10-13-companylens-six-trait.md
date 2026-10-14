# CompanyLens six-trait build: orchestration plan

> **For the orchestrator:** this is a multi-lane plan (`.claude/CLAUDE.md`, Orchestration).
> Each chunk is dispatched to a lane agent with a brief built from its section here.
> Lane agents do their own test-first steps inside a chunk. The orchestrator owns the
> waves, the joins, the reviews, and the single full suite run at the end.

**Goal:** CompanyLens shows a person-vs-company read on the six traits, using the
causal Bayesian model. It carries tolerance, must-haves, per-trait evidence records
(known/mixed/unknown), coverage and investigate steps, and never shows a probability.
The Situation Report adopts the same tolerance.

**Spec:** `docs/PRODUCT_DECISIONS.md` §2, "The six-trait match model" (2026-10-13). It
answers Julie's *Product & Match Model Alignment* brief (PDF, not in the repo).

**Architecture:** Person-side preferences (tolerance and must-have) sit behind the
D-01 doorway. A production research → per-item score → aggregate pipeline writes
per-trait evidence records for each company and scope. A match service combines the
two through `match_core`, with a hinge at the user's flat zone, plus a gate layer for
must-have, unknown and mixed. `/me/matches` is rewritten on top of it and CompanyLens
renders it. `culture_fit_score` is deleted.

**Approved 2026-10-13** with Q1 on-demand + batch prefill, Q2 Anthropic research /
gpt-5.5 scoring, Q3 unanswered = today's behaviour, Q4 build now / attorney before public.
Migration stubs `20261013_trait_prefs` → `20261013_company_evidence` pre-created by the
orchestrator. Later ids: C4 `20261013_envreport_outcomes`, C6 `20261013_user_company_link`,
C8 `20261013_pulse_company_link`, chained in that order.

## Global Constraints

- No probability, percentage or `p_fit` value in any user-facing response or page.
  Ranking uses the model's z internally only.
- No verbatim third-party quote reaches any route or page (GAP-14,
  `Solverah_IP/compliance/AI_GOVERNANCE_AND_CLAIMS.md:26`). Paraphrase plus source type plus date only.
- Tolerance is measured in person-lattice steps of 0.25 (0, 1 or 2), separately for
  under and over. The flat zone per direction is `max(0.15, steps * 0.25)`.
- At most 2 must-haves per user, enforced server-side.
- **A user with no tolerance answers must get exactly today's behaviour**, in both
  the Situation Report and the model. This adjusts the "1-step default" (see open
  question Q3).
- Coverage is always reported. Below 3 of 6 known traits the response is "not enough
  evidence", not a match.
- A company is never hidden. A must-have broken on a known trait means flagged and
  sorted last.
- The primary outcome is unchanged (`experienced` >= 4). New outcomes are exploratory.
  The prereg is append-only.
- Two gap sign conventions exist. In `work_pulse/situation.py`, gap = env - person.
  In `match_core.fit_gap`, gap = person - env. Every brief restates which one it uses.
- A new user-keyed table must be in `test_export_delete_coverage` COVERED. Person-side
  tables go through `assessment_store.py` (D-01 guard, `test_employer_visibility`).
- Migrations are chained in the order given below, with revision ids pre-assigned in
  each brief, so parallel lanes never produce two Alembic heads.
- Copy is best-guess-and-ship (Julie revises). Workers never commit.

## Review Focus

1. A user who never answered tolerance. Situation Report output must be bit-identical
   to today (pin test against a frozen copy of `classify_gap` behaviour).
2. All six traits unknown, or a company with zero evidence. Expect "not enough
   evidence", no crash and no 0.5 anywhere.
3. Mixed with a worst case that breaks a must-have, but a best case that is fine.
   Expect a risk flag, not a disqualification, and no averaging.
4. A pasted job posting with no trait evidence (pure requirements list). Every trait
   abstains, the role-level record is unknown, and there's no disagreement flag.
5. A user who tries to set three must-haves, or tolerance 3, through the API. Expect
   a 400 with a typed error.

---

## Wave 1: three chunks in parallel, disjoint files

### C1 Person-side tolerance and must-have (core-assessments; opus)
**Files:** `model.py` (person section: new `PersonTraitPreference`), migration
`20261013_person_trait_preference`, `assessment_store.py`
(`get_trait_preferences`, `save_trait_preferences`), `api/v1/assessments.py` or `me.py`
route for GET/PUT `/me/trait-preferences`, the schema, a new
`src/features/assessments/components/TraitPreferencesStep.tsx` mounted in
`WorkPulsePage.tsx` after submit and before navigation, plus a retake entry point.
`test_employer_visibility` ALLOWED entries, if needed, each with a stated reason.
**Produces:**
`assessment_store.get_trait_preferences(db, user_id) -> dict[str, TraitPreference]`,
where `TraitPreference(dimension_key, under_steps: int|None, over_steps: int|None,
must_have: bool, answered: bool)`. Unanswered gives `None` steps (= today's
behaviour), not 1.
**Hand-offs:** auth-accounts adds export and delete. schema-steward reviews the
migration. backend-platform reviews the openapi regen.

### C2 Model: hinge, tolerance and penalty table (matching-model; fable)
**Files:** `causal_graph/v1_model/match_core.py`, `priors.yaml` (additive `why` and
`date` per entry), `match_scoring.py` passthrough, tests, plus Amendment 3 appended to
`Solverah_IP/PREREGISTRATION_2026-10-01_FIRST_OUTCOME_FIT.md`. Amendment 3 covers:
exploratory outcomes, the hinge as the serving default with linear as the comparison,
and tolerance as a person feature. The primary analysis is unchanged.
**Produces:**
`match_core.excess_gap(gap, flat_under, flat_over) -> float`, and
`point_p_fit(..., flat_zones: dict[str, tuple[float, float]] | None = None)` /
`score_pairs(...)` / `outcome_z(...)`. With `flat_zones=None`, output is bit-identical
to HEAD (pin test against a verbatim copy). At a pole gap of 0.8 the cost equals
Julie's elicited cost whatever the flat zone, so her twelve answers still reproduce.
**Judgment left to the agent:** the rescaling form; how the zone interacts with
`COMPANY_LATTICE` snapping.

### C3 Company evidence schema (matching-model, a second dispatch with disjoint files; fable)
**Files:** `model.py` (company section): `CompanyEvidenceItem` (company_id, scope
∈ company/division/location/role, scope_label, source_type, source_url, published_at,
retrieved_at, `excerpt_internal` never serialized, paraphrase, research_run_id),
`EvidenceItemScore` (item, dimension_key, score NULL when abstained, abstained,
scorer_run_id), `CompanyTraitRecord` (company_id, dimension_key, scope, scope_label,
status known/mixed/unknown, estimate, low_end, high_end, confidence, evidence_count,
first_dated, last_dated, split_explained_by ∈ scope/time/NULL, aggregation_version,
computed_at), `JobPostingSubmission` (user-keyed), and a numeric `headcount` plus the
`stage_size` confounder write path. Migration `20261013b_company_evidence`, with
down_revision = C1's revision. Also a store module `company_evidence_store.py`, and a
guard test that no route serializes `excerpt_internal`.
**Produces:** `company_evidence_store.trait_records(db, company_id, scope=None) ->
list[TraitRecordView]` and `write_items/write_item_scores/write_trait_records`.
**Hand-offs:** schema-steward reviews. auth-accounts handles export and delete of
`JobPostingSubmission`.

### C0 Julie's deliverables (research-ground-truth; opus), runs alongside
These are the brief's §6 items, as docs in `Solverah_IP/`: a one-page architecture map
(evidence → uncertainty → interpretation → match signals → guidance), outcome
definitions (how each is observed), the six-trait boundary statement, the validation
roadmap (expert hypotheses / internal tests / predictive evidence), three fictional
journeys (including one where strong performance doesn't mean sustainable fit), and
the compounding-pairs draft from her notes. Best-guess, Julie revises.

## Wave 2: after Wave 1 lands and is reviewed

### C4 Situation Report: tolerance plus exploratory outcomes (situation-report; opus)
**Files:** `work_pulse/situation.py` (sign-aware `classify_gap` with per-user,
per-direction zones; aligned < zone, notable < zone + 0.10, straining beyond;
must-have dimensions first within their tier), `situation_report_service.py` (fetch
C1 prefs), `situation_items.py` and `envQuestions.ts` (exploratory outcome items AFTER
`experienced`, all optional: satisfaction, performance, engagement, sustainability,
retention, each 1–5 mapped to 0–1), `FORM_VERSION` env-v3, an `environment_reports`
migration (down_revision = C3's) with nullable columns, `environment_report_store.py`.
**Consumes:** C1 `get_trait_preferences`.
**Hand-off:** matching-model adds the new columns to
`assemble_training_data._fetch_environment_reports` (a small follow-up inside C6).

### C5 Production research, scoring and aggregation pipeline (matching-model; fable)
**Files:** a new `solverah/services/company_research/` (`research.py`: web-research LLM
→ evidence items, prompt derived from rubric v4.11's source sections and scope
declaration; `score_items.py`: per-item, per-dimension scoring on the v3.1 anchors with
the `insufficient_evidence` abstain, through structured output; `aggregate.py`: items →
`CompanyTraitRecord`; `job_posting.py`: pasted text → role-scope items → the same
scorer), an async job through the existing queue and scoring-job runner pattern, and a
`flask companies research <name>` CLI for batch runs. If a new provider is needed:
`infra/llm` provider function (llm-features writes it, a separate small dispatch).
**Aggregation rules (provisional, versioned):** a trait is **unknown** with fewer than 3
non-abstaining items, or with none dated in the last 24 months. Otherwise, split the
items at 0.5 into a low side and a high side.

A trait is **mixed** only when both sides have real support: at least 2 items on each
side, with the smaller side making up 25% or more of the items. Before recording it as
mixed, check whether scope (group by scope_label) or time (last 24 months vs older)
explains the split. If one does, record that explanation; if not, keep low_end and
high_end.

Every other case is **known**: one side predominates, and the spread lowers the
confidence instead of producing "mixed". This follows Julie's anchors ruling 5:
strength, recency and amount still decide whether one pole predominates, so
contradiction does not automatically mean mixed. For example, five items at 0.9 and
one at 0.1 come out known (high), with lower confidence.

**Size discount:** the larger the company, the lower the confidence that the
company-wide read describes the user's team. Use buckets from `stage_size`/headcount.
**Consumes:** C3 store. **Reviewer:** research-ground-truth checks the prompts'
fidelity to rubric v4.11 and anchors v3.1.
**Cost:** measure per-company cost on 3 companies and report it before any batch run.

## Wave 3

### C6 Match service and the `/me/matches` rewrite (matching-model; fable)
**Files:** a new `solverah/services/company_match_service.py`; `api/v1/companies.py`
(`/me/matches`, `/companies/<id>/read`, `POST /me/job-postings`, `POST /me/company-links`
for "I took this job"); deletion of `matching_service`'s `culture_fit_score` path and
`packages/ml/culture/scoring.py`; an interview-question bank as a content file (trait
× status × direction, best-guess); the training-assembler columns from C4; and an
openapi + `schema.ts` regen plus a contract re-baseline (A33).
**Response shape per company:** coverage `{known, total: 6}`; for each trait, status,
direction vs the user, inside/outside tolerance, `must_have`, paraphrased evidence for
mixed (both sides), scope/time explanation, size-confidence note; flags (must-have
break → sorted last; mixed worst case → risk; unknown must-have → investigate step
with questions); posting-vs-company disagreements when a posting is attached. No
probability field.
**Orchestrator ruling (2026-10-13, from C2's join question):** "unanswered = today's
behaviour" applies to the Situation Report, the only surface that has a "today". In
CompanyLens, a user who hasn't answered gets the hinge at the floor: `{d: (0.15, 0.15)}`
for all six traits. They never get `None`, which means the linear model. This follows the
decision "the flat zone is the larger of tolerance and the 0.15 band" and "hinge is the
serving default". Unknown traits use `env_missing`. Mixed traits call `point_z` twice,
once at low_end and once at high_end. Rank with `z_with_current_run`; z and p never go on
the wire. C6 also adds the C4 outcome columns and the trait-preference columns to the
training assembler.
**Consumes:** C1, C2, C3, C5. **Reviewers:** backend-platform (contract),
schema-steward (`UserCompanyLink` migration, down_revision = C4's), auth-accounts
(export and delete of the link).

## Wave 4: two chunks in parallel

### C7 CompanyLens frontend (matching-model; opus)
**Files:** `src/features/matching/components/CompanyLensPage.tsx` and new trait-read
components, `CompanyDetailPage.tsx` read section, a paste-a-posting panel, the "I took
this job" action, and a no-percentage test (every rendered string is checked for `%`
next to a fit word). App.tsx route lines get a frontend-shell review.
### C8 Pulse attaches to the company link (pulse-experiments; sonnet)
**Files:** `PulseCheckin.company_link_id` (nullable), `pulse_store.py`, a migration
(down_revision = C6's).

## Wave 5: validation and close-out

### C9 Sensitivity test plus first real run (matching-model; fable)
Also add the one-argument `flat_zones` passthrough in `build_model.py` so the Look 2 hinge
fit can run (C2's algebra already works on tensors). Note that the `priors.yaml` hash
changed, so devfit DBs will show a second priors run. Then run C5 on the round-2 company
set. Script `causal_graph/v1_model/sensitivity.py`
nudges each penalty weight ±50% across synthetic people × those companies, and reports
top-5 overlap and Kendall tau per weight. A weight "matters" if overlap < 4/5 or tau <
0.8. Output goes to a `Solverah_IP/` doc.
### C10 Blind-rater pair task (research-ground-truth; opus)
Person/company scenario pages for raters who didn't set the weights: round-2 raters
other than Julie and Sebastian.
### Open joins (tracked by the orchestrator)
- ~~C5 commit flag + auth-accounts wrapper removal~~: DONE (C5 added `commit=`; the
  orchestrator removed the wrapper; 31 account tests pass).
- **ops-crons** (close-out): production has no worker; C5's jobs run on a 2-thread pool.
  `service.sweep_research_runs` (fails runs stuck past 1560 s, re-dispatches queued runs
  older than 5 min) needs a schedule: a `flask companies sweep` command plus a Render
  cron (render.yaml is doc-only).
- DONE: schema-steward approved all five 20261013 revisions. The orchestrator added
  `ix_pulse_checkins_company_link` (F2, migration edited in place + ORM; 77 tests pass).
  auth-accounts made `user_company_link` exported and RETAINED on deletion (precedent:
  `employer_name_normalized`), and fixed `ExportedPulseCheckin.company_link_id`.
  **Sebastian question:** `employer_name_normalized` is free text that is retained, which
  conflicts with D-7b. If he rules it must go, the links flip to destroy (one line).
- DONE: one-open-link rule (partial unique index edited into the migration in place)
  + PATCH "I left" + docstring fixes. The final suite will catch any test that builds
  two open links by hand.
- (historical) RUNNING: one-open-link rule + `PATCH /me/company-links/<id>` ("I left") +
  docstring fixes (matching-model, small; DB c5). Orchestrator default: one current job.
- Close-out must also run `flask db upgrade` from empty and a downgrade round trip on a
  throwaway DB, since migrations were edited in place after review (F2, the one-open
  index).
- (historical) **auth-accounts** (after C8): export/delete for `user_company_link`, using
  `company_links_for_user` and `delete_company_links_for_user(..., commit=False)`. C8
  makes `pulse_checkins.company_link_id` ON DELETE SET NULL, so ordering is safe.
- **backend-platform** (A33): `Scripts/capture_contract.py` still seeds the deleted
  interim matches path. Re-point it to capture `core_required` / `no_companies` /
  `ranked` with seeded records. After that, **core-assessments** deletes the dead
  `work_pulse/derive_preferences.py` and `assessment_repository.work_pulse_answers_for_users`.
- **ops-crons/backend-platform**: two comment references to the deleted
  `maintenance_tasks.py` (`.claude/agents/ops-crons.md`, `solverah/worker.py`).
- **profile-hub**: the Intelligence/dashboard CompanyLens cards still say "coming soon"
  (C7 will list where).
- C6 rulings (orchestrator): mixed does NOT count toward the 3-known minimum (decision
  text); Investigate wins over Explore. C6's `git rm` deletions are staged in the index;
  handle them in the commit pass.
- **C5b** (running): research-ground-truth's fidelity review, F1–F10, F13 and F14, all gate
  the first live run. Julie's five provisional rulings are marked PROVISIONAL in
  `constants.py`. **research-ground-truth** (C10 time) writes them up as an async ask
  for Julie: where mixed starts (6v2, 5v2+3, 4v2, 3v3, 2v2+4), strength/recency
  weighting, company-only evidence, recent-vs-old splits, single item vs company bands.
- DONE C10: fit-pair task (50 pairs + 4 repeats in 10 blocks, contrasts K1–K11,
  prereg `Solverah_IP/ground_truth/fit_pairs/PREREG_FIT_PAIRS_2026-10-13.md`), plus
  Julie ask 08 (six one-tap questions, including innovation direction). **Blocker for
  Sebastian:** zero eligible raters. A=Julie and D=Sebastian set the weights; B and C
  are unavailable. He must recruit raters E+ and needs a recruit covering note. The
  model scores for the pairs are running (matching-model). `pair_specs.json` must be
  committed with the prereg before any page goes out.
- DONE C9: sensitivity on the six round-1 packets plus 30 labelled synthetic companies,
  200 people. MATTER: pace.mag, innovation.mag, innovation.dir, feedback.mag
  (borderline). INERT: the other direction weights, autonomy, collaboration, decision.
  `build_model`/`fit_posterior`/`prior_predictive` gained `flat_zones` (accepted).
  Citations are matched by URL. The 10% share threshold is C9's choice. Results:
  `Solverah_IP/match_model_alignment/07_SENSITIVITY_RESULTS.md`.
- (historical) **C9 (matching-model)**: switch `company_research/research.py::_citations_for` to match
  `char_location` citations by the new `ResearchCitation.url`, which comes from
  `document_index` (llm-features fix). Today it matches by title. The live run also
  checks the assumption that `document_index` counts successful fetches in order.
- Cleanup: drop the scratch DB `solverah_c5llm`.
- **Concordance study** (F11: per-item vs packet scoring on the round-1/2 packets) needs
  Sebastian's cost go. Per-item scoring hasn't been validated; no user-facing claim
  until it is.
- Pilot form: done (98 pass). Minor: `submit_environment_report` stamps the current
  FORM_VERSION, so the DB can't tell "outcomes not offered" (v2 pilot form) from
  "skipped". Provenance lives only in import-time bookkeeping. Fine for exploratory
  use; revisit if ever needed.
- **backend-platform** (close-out): consider excluding `Solverah_IP` from the Docker
  image once C5b ships the frozen anchors copy (F14). Check nothing else in prod reads it.
- **Sebastian** (live): the first 3-company cost run is the acceptance test for
  citations under JSON output (100% `dropped_unverified` = the prompt shape is wrong).
  Command: `flask companies research "A" "B" "C"` with keys set, against a LOCAL 5433 DB.
- (historical) C5: add `commit: bool = True` to `company_evidence_store.delete_job_postings_for_user`
  (and any other store write account deletion needs). Then **auth-accounts** deletes its
  `_InCallersTransaction` / `_FlushInsteadOfCommit` wrapper in `account_repository` and
  calls the store directly.
- ~~After C4 lands: five outcome fields on `ExportedEnvironmentReport`~~. DONE by the
  orchestrator (2026-10-13); 111 export and situation tests pass; openapi and schema.ts
  regenerated.
- **schema-steward** reviews `20261013_envreport_outcomes`, together with C6's
  `user_company_link` migration.
- Pilot form: artifacts regenerated to env-v3, and the importer accepts v2 rows with
  their own version recorded (small matching-model dispatch, running).
- **After C6:** backend-platform reviews the openapi and `schema.ts` regenerations by C1,
  auth-accounts, C4 and C6, including the `info.description` generator quirk. Then one
  contract re-baseline (A33), covering export (now with `job_postings` and
  `trait_preferences`), the situation report, `/me/trait-preferences` and `/me/matches`.
- **frontend-shell** reviews all App.tsx route lines together after C7. C1's line has
  already been checked by the orchestrator.
- **schema-steward** ownership table: add PersonTraitPreference → core-assessments and the
  six evidence classes → matching-model (schema-steward edits its own file at the next
  review).

### Late joins (2026-10-14)
- DONE ops-crons: `flask companies sweep`, a doc-only render.yaml cron (every 10 min),
  the runbook "CompanyLens six-trait" section, and rollback §8. **The next merge applies
  10 migrations** (prod head `20260921_path_wants`; check `flask db current` first).
- RUNNING C5c (matching-model): atomic run claim (no double paid run), finish only from
  `running` (no overwrite of a reaped row), `SOLVERAH_COMPANYLENS_RESEARCH_ENABLED`
  (default OFF → 503 `research_disabled`; the CLI needs `--allow-when-disabled`), and
  `SOLVERAH_RESEARCH_BLOCKED_DOMAINS` plumbing.
- AFTER C5c: backend-platform captures the research POST step in A33. The orchestrator
  adds the switch variable to the render.yaml env docs and the runbook (the switch, not
  the key, is the public gate).

- DONE frontend-shell: App.tsx and the MSW file approved; full vitest 1449/1449;
  type/lint/build clean; size 99.87/101 kB JS, 10.51/11 kB CSS (tight); e2e smoke,
  real_stack and feature_tour ALL PASS against a real stack (solverah_e2e migrated to
  head; Flask on 5055). RUNNING: no-probability guard tightened (decimals/ratings) + MSW
  conventions (matching-model, small).

- DONE backend-platform A33: 116 → 152 steps, 0 differences after recapture; the
  pre-change diff was additive only. Fixes: `info.description` (a shadowed variable in
  `build_openapi`), anthropic redaction in config, `test_schema_conformance` rewritten
  for six-trait `/me/matches`. PENDING: research POST steps (+ the typed posting 503)
  after C5c, then recapture. **Sebastian:** exclude `Solverah_IP` (37 MB) from the
  Docker image? backend-platform verified nothing at runtime reads it.
- RUNNING: core-assessments deletes `derive_preferences.py`, its test, and
  `work_pulse_answers_for_users`.

### Backlog after this build
- manager-match (pre-existing, from the e2e tour): `/me/manager-playbook` 409 logs a
  console error before ManagerMatch is taken; `/manager-match/results` hits a 404
  before redirecting. (C7's API notes; each would need a new contract re-baseline, so not now)
- `GET /me/job-postings` (a list). Today a posting can only be found again through `?posting=` in the URL.
- An empty research name returns 400, not 422. Align it with the house validation split.
- Posting-vs-company disagreements carry no direction. Add the posting's pole so the UI
  can say which way it leans.
- `/companies/<id>/read` has no handle on an in-flight run without a new POST.
  Include the run status.
- `GET /companies/research/<run_id>` is not owner-scoped. Acceptable for shared
  research; revisit if runs ever carry user data.
- C7 rulings (orchestrator): "Based on N of 6" counts known + mixed (traits with
  evidence); the ranking minimum stays 3 known. Glassdoor x/5 grid and old
  8-dimension bars dropped from the legacy profile (no-score rule).

### Orchestrator close-out
Read each diff. One CI-style full suite run
(`SOLVERAH_IGNORE_DOTENV=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, lane DB on 5433,
verification venv). Frontend type-check, lint, test, build and size gates. Browser
click-through of CompanyLens and the Situation Report. Ask Sebastian before any commit.
