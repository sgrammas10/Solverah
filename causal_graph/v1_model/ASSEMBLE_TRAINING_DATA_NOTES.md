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

#### Both blockers cleared, 2026-09-17

The `OrderedLogistic` branch exists. `build_model.build_model(..., head="experienced")`
attaches it; `head="appeal"` is the default and is the unchanged binary model. The two
heads are declared side by side in `solverah_model_config.yaml`'s new `settings.heads`
block, and `settings.outcome` stays as the legacy alias of `heads.appeal` so every
existing reader (`recovery_multiseed.py`) keeps working. Nothing dichotomizes an
`experienced` rating anywhere on the path -- that is D-20, and a rating that is not an
integer in 1..5 now raises rather than being rounded or clipped into one.

**The mapping, which is the part worth knowing.** `priors.yaml`'s weights were elicited
on a BINARY scale: `sigmoid(z) = P(still doing well after a year)`, "doing well" being a
rating of 4 or 5. PyMC parameterizes `OrderedLogistic` as `P(Y <= k) = sigmoid(c_k -
eta)` (verified against pymc 5.25.1's `OrderedLogistic.compute_p`). So with

* `eta = z`, the FULL linear predictor, intercept included, and
* `c_3` -- the boundary between ratings 3 and 4 -- PINNED at 0, a constant,

`P(Y >= 4) = 1 - sigmoid(0 - z) = sigmoid(z)` *identically*. The expert's numbers keep
their meaning on the ordinal head with no rescaling, and `sigmoid(z)` in the serving path
(`match_core.point_p_fit` / `score_pairs`) goes on meaning exactly what it meant.

The pin is load-bearing, and its absence would be silent. An intercept and a free
cutpoint vector are jointly unidentified: shift every cutpoint by d and the intercept by
d and the likelihood is unchanged. Leave `c_3` free and the sampler still runs and
nothing fails -- the intercept just quietly stops meaning "8 in 10 still doing well". The
remaining three cutpoints are free, built from positive `LogNormal` spacings
(`cut_spacing`) so ordering holds by construction; their priors live in `priors.yaml` (and
identically in `priors_placeholder.yaml`) under `cutpoints:`, flagged as NOT
expert-elicited. The pin's position is derived from `heads.experienced.doing_well_at`,
not hardcoded, so moving the threshold moves the pin with it.

**NULL `comp`: the term is excluded.** `match_core.preprocess_conf` takes an optional
`conf_missing` mask -- exactly the one `EnvironmentAssembleResult.conf_missing` carries.
Where the mask is True a continuous confounder's standardized value becomes exactly
`0.0`, and since it enters the logit as `w * value`, that row's term drops out of `z`.
Deliberately NOT a missingness-indicator weight: that would be a 21st weight, and the
flat weight naming is a database interface pinned at 20 rows. Modelling the missingness
stays available as a later config change with its own sign-off. Without a mask, a NaN now
RAISES and names the confounder -- before this it standardized into a NaN and propagated
through the whole linear predictor into `p_fit`, unflagged.

**What still stands between these rows and a fit.** Three things, none of them this
file's two:

1. **`industry` is still unfeedable from this source.** The instrument does not ask it,
   so every row carries `None` for it, and a categorical confounder goes through
   `levels.index(v)`, which raises. The continuous ruling does not transfer: `0.0` is a
   neutral standardized value, but there is no neutral level index to stand in for one
   weight out of a per-level vector. That is a config decision -- add an `unknown` level,
   or deactivate the confounder for runs off this source -- and it is unmade.
   *(Made on 2026-09-21 -- see the next section. Item 1 is closed; 2 and 3 stand.)*
2. **There is no volume yet.** `assemble_environment_training_data` is verified against
   sqlite and against `build_model`'s real contract, not against a populated production
   database.
3. **The head is verified on data it generated itself.** `ordinal_recovery.py` +
   `results/ordinal_recovery.md` show the head recovering known weights and known
   cutpoints at the resolution the real instruments emit. That is an inference check, not
   evidence that the expert's weights describe real placements. Only outcome data can say
   that, which is why BUILD_PLAN's "First real-priors fit" box stays unchecked.

## 2026-09-21 — the third blocker is closed: a masked `industry` excludes its term

The ruling above ("that is a config decision, and it is unmade") is made. **Exclude the
term**, exactly as for a missing `comp` — carried by the mask that
`EnvironmentAssembleResult.conf_missing` already supplies, not by a config edit. With
that, **nothing in code** stands between the environment rows and a fit. What remains is
items 2 and 3 above: **data volume**, and the fact that the head has so far only been
checked against data it generated itself. Neither is a code change.

**The mechanism, in two sentences.** `preprocess_conf` gives a masked categorical row
level index 0 as a *placeholder* and returns a second array, `{key}__present`, that is
`1.0` where the value is present and `0.0` where it is masked; `outcome_logit` then adds
`w[level] * present`, so a masked row contributes exactly nothing and the placeholder
weight is never read. With no mask — or an all-False one — the code takes the literal
old expression and returns the old keys, because `point_p_fit`/`score_pairs` run it on
every request and bit-identity there is the requirement, not closeness.

**Two rejected alternatives, recorded so they are not re-proposed.**

* **An `unknown` LEVEL.** When every row off a source shares it, it is perfectly
  collinear with the intercept: unidentified, pure prior, and it would bleed into the
  intercept — the one that currently means "8 in 10 still doing well", the elicited
  baseline the cutpoint pin exists to preserve. A sixth level that only ever appears
  alone is not a category, it is a second intercept.
* **Deactivating `industry` in the config.** That removes the confounder from the
  company-side path too, where it *is* supplied, and it changes the flat weight set,
  which `tests/test_match_scoring.py` pins at 20 rows. A fix for one source must not
  silently re-specify the model for the other.

**The mask is self-reversing.** Nothing about this is a permanent exclusion of
`industry`. When a source starts supplying it, those rows stop being masked, `present`
goes to `1.0`, and the term returns — no code change, no config change, no migration.
That is the property the level-and-config alternatives lacked.

**Follow-up, NOT done and not in scope here.** `industry` could be derived product-side
from the user's resolved occupation code rather than asked. Worth doing only if early
fits show unexplained sector differences; until then a derived confounder is an
unvalidated one.

**Parked, and not the same variable.** The expert's note on industry is about *switching*
industries — a transition, whose cost depends on where you come from as well as where you
land. A per-level weight cannot express that: it scores the destination only. It is a
different variable with a different shape, and it sits with her other structural notes
rather than being approximated by this one.

Unmasked, a `None` or an unrecognized level still raises — now naming the confounder, the
offending values and the rows, instead of `list.index`'s bare `None is not in list`.
Masking is a claim the caller makes explicitly; it is not a way for an unasked value to
reach a fit quietly.

*Tests:* `tests/test_ordinal_head.py` section 7 (numpy, runs in CI, including an
end-to-end pass from three real assembled environment rows to a finite `z` under the live
priors) and `causal_graph/v1_model/test_ordinal_head.py` sections 6–7 (PyMC: pytensor
accepts the masked expression, the unmasked model's `pm.Data` names and free RVs are
unchanged on both heads, and a short NUTS fit with `industry` masked on every row leaves
`w_industry` sitting on its `Normal(0, 1)` prior).

*Note for whoever edits `assemble_training_data.py` next:* the docstring on
`EnvironmentAssembleResult` still says the output "IS NOT YET FEEDABLE STRAIGHT INTO
build_model" because `preprocess_conf` handles neither case. Both halves of that are now
false. That file was outside this change's ownership, so the correction is recorded here
rather than made there.

### Pointer: condition experiments (BUILD_PLAN B-5)

The `experiments` table (`model.Experiment`) holds one row per user per two-week
change-in-place attempt, with a before/after `experienced` readout served to the user as a
word, never a delta. The per-user word is not this lane's food; the aggregate pattern across
many users' attempts on the same `(dimension, direction)` cell is, whenever this source gets
built out. Nothing here assembles it yet.
