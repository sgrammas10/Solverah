# assemble_training_data(db) — notes

`assemble_training_data.py` is a first implementation, not previously started. It's been
verified end-to-end against `build_model.py`'s real contract (see "What's actually verified"
below), but it makes several policy choices that were never explicitly settled anywhere in the
handoffs, and it surfaced one real gap in `build_model.py` itself. Both need your sign-off, same
pattern as the rubric anchors and the anonymization ruleset going through you before being
treated as settled.

## What's actually verified

* `assemble_training_data()` ran against an in-memory sqlite DB carrying the same columns as
  `schema.sql`, through the **real** fetch + resolve + assemble functions — no sqlite-specific
  reimplementation. This was possible because the fetch layer uses SQLAlchemy's portable `IN`
  binding instead of Postgres-only `ANY()`, and resolves "which of several rows wins" in Python
  instead of Postgres-only `DISTINCT ON`.
* Its output was fed **directly** into `build_model.build_model(person, env, conf, cfg, pri,
  outcome=...)` using the real `solverah_model_config.yaml` and `priors.yaml` — not a stub — and
  `pm.sample_prior_predictive()` ran on the resulting model without error.
* **Not verified:** behavior against a real Postgres database (none exists yet — see below), or
  against real data volume.

Run `python assemble_training_data.py` to re-run the sqlite checks.

## Real gap this surfaced: `build_model.py` has no path for `experienced` outcomes

The canonical handoff and `solverah_model_config.yaml`'s comments both describe two outcome
heads sharing one linear predictor: `appeal` (Bernoulli, `fit_yes`) and `experienced` (1–5
ordinal, `working_scale`, meant to use `OrderedLogistic`). `assemble_training_data()` correctly
assembles both — the self-test builds an `experienced` row and returns `outcome=4` as a plain
value, not a 0/1 — but `build_model.build_model()` only ever attaches
`pm.Bernoulli(outcome_name, logit_p=z, observed=...)`. There is no `OrderedLogistic` branch, and
`solverah_model_config.yaml`'s `settings.outcome` block only describes the binary head
(`type: binary`).

This means the `experienced` output of `assemble_training_data()` is real and correctly shaped,
but **nothing downstream can consume it yet.** Not a blocker for this task (scoping the glue
function was the ask), but it's the next piece of real work if experienced-fit training is meant
to happen before appeal-only — worth deciding which comes first rather than discovering the gap
mid-training-run.

## Policy decisions made, that you should confirm or override

1. **Source-priority resolution for company scores/confounders**
   (`DEFAULT_SOURCE_PRIORITY = ("declared", "researched", "scraped")`, tie-broken by most recent
   `as_of`). Nothing in `schema.sql` specifies this — it can hold multiple rows per
   `(company, dimension)` across sources and dates by design. Verified this actually matters: the
   self-test seeds company 10 with a `scraped` row from January and a `declared` row from June for
   the same dimension, and the resolver correctly keeps the June `declared` value over the
   (chronologically later-inserted, higher-magnitude) scraped one. Override via the
   `source_priority` argument — e.g. force `researched`-only during ground-truth work, so a later
   scraped row can never silently outrank a hand-scored one.

2. **`experienced` and `appeal` are never blended.** The canonical handoff's own signature —
   `assemble_training_data(db) -> (person, env, conf, outcome)` — reads as if there's a single
   `outcome`. Taken literally that violates the project's own locked "never average appeal and
   experienced" rule, so this implementation requires `outcome_type` as an argument instead and
   won't produce a merged array. Call it twice if you want both.

3. **Confidence is not used to filter rows by default.** `min_company_confidence` exists as an
   opt-in parameter but defaults to `None` (no filtering), matching the 08-10 decision that
   confidence stays informational in v1 and out of the ranking math. It would be easy to
   default this differently (e.g. drop anything below the "Low" confidence band) — flagging the
   current default explicitly rather than letting it be an implicit assumption. The self-test
   proves the filter works when turned on (a `min_company_confidence=0.9` run correctly drops the
   only candidate, since company 10's non-`declared` dimensions sit at confidence 0.7).

4. **Incomplete rows are dropped, not imputed, and every drop is recorded with a reason** (in
   `AssembleResult.dropped`) rather than silently shrinking the training set. This follows the
   project's own repeated lesson about not treating "missing" as unremarkable (the P-03/P-04
   "empty response read as absence" class of bug). No config here — this one seems clearly
   correct given the project's history, but flagging that it's a choice, not a law of nature:
   an alternative would impute a company's missing dimension from a same-industry/stage prior,
   which the model doesn't currently support and probably shouldn't until there's a reason to
   trust it.

5. **`scoring_key_version` defaults to each person's most recent `scored_at`.** Matches
   `schema.sql`'s own stated rationale for keeping raw assessment responses ("so scores can be
   re-derived when the scoring key changes") — always the current key unless one is pinned
   explicitly for reproducing an older run.

## Not yet true, worth naming

`schema.sql` has never been migrated into the app's actual Postgres database — there's no
migration under `migrations/versions/` for `dimension`, `person_dimension_score`,
`company_dimension_score`, `recommendation`, `outcome_appeal`, `outcome_experienced`, or any of
the other tables it defines. The Flask app's existing DB access is all
Flask-SQLAlchemy/Flask-Migrate against a separate, already-migrated schema (`model.py`). Wiring
this in for real means either migrating `schema.sql` into that same database or standing up a
second one — a decision this task didn't make for you, since it's a real architectural choice,
not a detail of the join logic.

---

## ADDENDUM 2026-09-11 — E-4 landed, and two things above are now out of date

`assemble_environment_training_data()` was added alongside the function this document
describes. Everything above still describes `assemble_training_data()` accurately; what
follows is what changed around it.

### "Not yet true, worth naming" is no longer true

The last section says `schema.sql` "has never been migrated into the app's actual Postgres
database" and leaves the migrate-vs-second-database choice open. That choice was made and
executed on 2026-08-19 (S-07): `schema.sql` was migrated INTO the app's database, with
`person_id` becoming `user_id` and `schema.sql`'s `company` reconciled into the existing
`Company` rather than standing up a parallel table. `migrations/versions/` now carries
`20260819_person_assessment` and `20260819_company_model`, and `model.py` holds the ORM
definitions with the reconciliation reasoning in its section comments. There is one
database, and it is the app's.

### The training rows do not come from where this document assumes

This document assumes the training pair is (person, company) with an
`outcome_appeal`/`outcome_experienced` row behind it. BUILD_PLAN §5's E-4 says the rows that
exist AT LAUNCH come from somewhere else entirely — A-2's `environment_reports`, where the
env side is the user's own description of their own job and the outcome is that form's one
evaluative item. No company scoring, no recommendation, no placement required. That is what
`assemble_environment_training_data()` assembles, and why it is a second entry point rather
than a parameter on the first: the two sources differ in what selected the pair, not merely
in where the numbers are stored.

Three consequences worth naming rather than discovering:

1. **The source-priority machinery does not apply.** `resolve_best_by_source` exists because
   `company_dimension_score` can hold several rows per (company, dimension). An
   environment report holds exactly one score per dimension
   (`uq_edscore_report_dim`), so there is nothing to resolve and no policy to sign off.
2. **`min_company_confidence` has no analogue.** There is no confidence on a self-report and
   no source axis to trade off. Decision 3 above is silent here because the question does
   not arise.
3. **Incomplete rows are still dropped with a reason, never imputed** (decision 4 above,
   unchanged) — but `comp` is now a documented, expected NULL rather than an incomplete row.
   The "not sure" option is a signed ruling (PRODUCT_DECISIONS.md §2, 2026-09-10), so the
   row carries NaN plus an explicit `conf_missing` mask and stays in the training set. What
   to do about it — exclude the term, model the missingness — is the model config's call,
   and the row shape is built to let it still be made.

### The gap this document found is now the blocking one

"`build_model.py` has no path for `experienced` outcomes" was filed above as *not a blocker
for this task*. It is a blocker now. `experienced` is the ONLY outcome the environment
source produces — `appeal` means "did this recommendation look like a fit" and there is no
recommendation — so `build_model.build_model()` attaching `pm.Bernoulli` unconditionally is
the one thing standing between these rows and a fit run. `solverah_model_config.yaml`'s
`settings.outcome` block still describes only the binary head (`type: binary`). E-5 cannot
start on this source until an `OrderedLogistic` branch exists.

### Pointer: condition experiments (BUILD_PLAN B-5)

The `experiments` table (`model.Experiment`) holds one row per user per two-week
change-in-place attempt, with a before/after `experienced` readout served to the user as a
word, never a delta. The per-user word is not this lane's food; the aggregate pattern across
many users' attempts on the same `(dimension, direction)` cell is, whenever this source gets
built out. Nothing here assembles it yet.
