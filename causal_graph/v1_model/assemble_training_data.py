"""
assemble_training_data.py -- the DB -> model join/pivot glue.

Turns the long-format rows in schema.sql into the exact (person, env, conf, outcome)
shape build_model.build_model() / fit_posterior() expect:
    person, env : dict {dim_key: np.array([...]), length N}   -- raw 0..1 scores
    conf        : dict {confounder_key: np.array([...]), length N}  -- RAW values
                  (preprocess_conf() in build_model.py standardizes/one-hots this;
                  this function must NOT pre-scale, or fit-time and predict-time
                  preprocessing would run twice)
    outcome     : np.array([...]), length N

Was never written before this pass. Reads schema.sql and build_model.py's actual
contract rather than inventing a new one -- see ASSEMBLE_TRAINING_DATA_NOTES.md
for the design decisions this makes and the ones still open for sign-off.

TWO SOURCES, ONE SHAPE (BUILD_PLAN E-4)
---------------------------------------
`assemble_training_data()`               (person, COMPANY) pairs: a recommendation
                                         was shown and an outcome came back. The
                                         env side is a company's scored dimensions.
`assemble_environment_training_data()`   (person, OWN JOB) pairs: the user described
                                         a job of their own through A-1's
                                         instrument -- their current one, or (since
                                         2026-10-01, `report_subject='past'`) the
                                         one before it. The env side is
                                         `environment_reports`.

Both return the same four arguments in the same raw units, so build_model does not
know or care which produced a row. The second is the one that has data at launch --
§5's "inversion paying off" -- and it reads the APPLICATION database (model.py),
where schema.sql's `person_id` is `user_id`. Every row it emits carries a
`capture_path` saying which source it came from and a funnel/collider inventory
saying what did NOT select it; see FUNNEL_FIELD_CAPTURE_NOTES.

    pip install sqlalchemy pyyaml

    python assemble_training_data.py     # runs the sqlite self-test at the bottom
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Literal, Optional, Sequence

import numpy as np
from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

OutcomeType = Literal["appeal", "experienced"]

# ---------------------------------------------------------------------------
# THE TWO OUTCOME LABELS ARE NEVER MIXED -- locked decision (canonical
# handoff: "Outcomes: two SEPARATE labels -- appeal ... vs experienced ...
# Never averaged."). The canonical handoff's own function signature reads
# assemble_training_data(db) -> (person, env, conf, outcome) as if there is
# one outcome; taken literally that violates "never average" by construction
# -- you can't return "the" outcome without choosing which of two
# incompatible labels it is. Resolved by requiring outcome_type and refusing
# to blend the two. Call this twice (once per type) for both.
# ---------------------------------------------------------------------------

# company_dimension_score / company_confounder_value allow MULTIPLE rows per
# (entity, key) -- one per (source, as_of); schema.sql's own comment
# describes the intended lifecycle ("scraped can be upgraded to declared
# in-place"). Nothing in the schema says which wins at query time -- that's
# a real policy choice, not a detail. Default: higher-trust source wins,
# then most recent as_of within a source (culture drifts -- an old read is
# a wrong read, per schema.sql's own comment on `as_of`). Override
# `source_priority` to change this -- e.g. force 'researched' only during
# ground-truth work, so a later scraped row can never silently outrank a
# hand-scored one.
DEFAULT_SOURCE_PRIORITY: Sequence[str] = ("declared", "researched", "scraped")


@dataclass
class AssembledRow:
    """One (person, company) training example, kept in the result so a row
    can be traced back to real IDs instead of just an array index."""
    person_id: int
    company_id: int
    recommendation_id: Optional[int]


@dataclass
class AssembleResult:
    person: dict
    env: dict
    conf: dict
    outcome: np.ndarray
    rows: list             # list[AssembledRow], same order/length as the arrays
    dropped: list = field(default_factory=list)  # list[dict] -- excluded + why


# ---------------------------------------------------------------------------
# Pure assembly logic -- no SQL, no dialect dependence. Deliberately
# separated from the DB-fetch functions below so it can be unit-tested
# directly and so "how a (company, dimension) row gets resolved when several
# exist" isn't buried inside a database-specific query string.
# ---------------------------------------------------------------------------
def resolve_best_by_source(rows: list[dict], priority: Sequence[str]) -> dict:
    """rows: mappings with at least entity_id, key, source, as_of (ISO date
    strings sort correctly as plain strings). Returns {(entity_id, key): row}
    keeping, per key, the highest-priority source and, within a tied source,
    the most recent as_of."""
    priority_rank = {s: i for i, s in enumerate(priority)}
    best: dict = {}
    for r in rows:
        k = (r["entity_id"], r["key"])
        rank = priority_rank.get(r["source"], len(priority))
        cur = best.get(k)
        if cur is None:
            best[k] = (rank, r["as_of"], r)
            continue
        cur_rank, cur_as_of, _ = cur
        if rank < cur_rank or (rank == cur_rank and r["as_of"] > cur_as_of):
            best[k] = (rank, r["as_of"], r)
    return {k: v[2] for k, v in best.items()}


def assemble_rows(
    candidates: list[dict],
    person_scores: dict,       # {(person_id, dim_key): score}
    company_scores: dict,      # {(company_id, dim_key): (score, confidence)}
    company_confs: dict,       # {(company_id, conf_key): value}
    dims: list[str],
    conf_keys: list[str],
    outcome_type: OutcomeType,
    min_company_confidence: Optional[float],
) -> AssembleResult:
    """candidates: rows with person_id, company_id, recommendation_id,
    outcome_value -- already resolved to ONE outcome type by the caller.
    Pure function: given fully-resolved lookups, builds the arrays and
    records every dropped candidate with a reason. This is the piece that
    matters most to get right and the piece the self-test below exercises
    directly, with no database involved at all."""
    dropped: list = []
    rows: list[AssembledRow] = []
    person_vals = {k: [] for k in dims}
    env_vals = {k: [] for k in dims}
    conf_vals = {k: [] for k in conf_keys}
    outcome_vals = []

    for c in candidates:
        pid, cid = c["person_id"], c["company_id"]
        missing = []

        p_row = {}
        for k in dims:
            v = person_scores.get((pid, k))
            if v is None:
                missing.append(f"person.{k}")
            p_row[k] = v

        e_row, min_conf_seen = {}, 1.0
        for k in dims:
            v = company_scores.get((cid, k))
            if v is None:
                missing.append(f"company.{k}")
                e_row[k] = None
            else:
                e_row[k] = v[0]
                min_conf_seen = min(min_conf_seen, v[1])

        cf_row = {}
        for k in conf_keys:
            v = company_confs.get((cid, k))
            if v is None:
                missing.append(f"confounder.{k}")
            cf_row[k] = v

        if missing:
            dropped.append({"person_id": pid, "company_id": cid, "reason": missing})
            continue
        if min_company_confidence is not None and min_conf_seen < min_company_confidence:
            dropped.append({
                "person_id": pid, "company_id": cid,
                "reason": [f"min company confidence {min_conf_seen:.2f} < {min_company_confidence}"],
            })
            continue

        for k in dims:
            person_vals[k].append(p_row[k])
            env_vals[k].append(e_row[k])
        for k in conf_keys:
            conf_vals[k].append(cf_row[k])
        outcome_vals.append(c["outcome_value"])
        rows.append(AssembledRow(person_id=pid, company_id=cid,
                                  recommendation_id=c.get("recommendation_id")))

    person_arr = {k: np.asarray(v, dtype=float) for k, v in person_vals.items()}
    env_arr = {k: np.asarray(v, dtype=float) for k, v in env_vals.items()}
    conf_arr = {k: np.asarray(v, dtype=object if any(isinstance(x, str) for x in v) else float)
                for k, v in conf_vals.items()}
    outcome_arr = np.asarray(outcome_vals, dtype=(float if outcome_type == "experienced" else int))

    return AssembleResult(person=person_arr, env=env_arr, conf=conf_arr,
                           outcome=outcome_arr, rows=rows, dropped=dropped)


# ---------------------------------------------------------------------------
# DB-fetch layer. Thin on purpose -- all decisions live in the pure functions
# above. Portable across Postgres and sqlite: uses SQLAlchemy's expanding
# IN-binding instead of Postgres-only ANY(:list), and resolves "which row
# wins" in Python (resolve_best_by_source) instead of Postgres-only
# DISTINCT ON. That's what makes the self-test below exercise the ACTUAL
# production function rather than a sqlite-flavored stand-in for it.
# ---------------------------------------------------------------------------
def _fetch_candidates(conn: Connection, outcome_type: OutcomeType) -> list[dict]:
    if outcome_type == "appeal":
        sql = text("""
            SELECT r.person_id AS person_id, r.company_id AS company_id,
                   oa.recommendation_id AS recommendation_id, oa.fit_yes AS outcome_value
            FROM outcome_appeal oa JOIN recommendation r ON r.id = oa.recommendation_id
        """)
    else:
        sql = text("""
            SELECT person_id, company_id, recommendation_id, working_scale AS outcome_value
            FROM outcome_experienced
        """)
    return [dict(r) for r in conn.execute(sql).mappings().all()]


def _fetch_person_scores(conn: Connection, person_ids: list[int],
                          scoring_key_version: Optional[str]) -> dict:
    sql = "SELECT person_id, dimension_key, score, scored_at FROM person_dimension_score WHERE person_id IN :pids"
    params = {"pids": person_ids}
    if scoring_key_version:
        sql += " AND scoring_key_version = :skv"
        params["skv"] = scoring_key_version
    stmt = text(sql).bindparams(bindparam("pids", expanding=True))
    rows = conn.execute(stmt, params).mappings().all()
    # latest scored_at wins per (person, dimension) -- "always the current
    # scoring key" per schema.sql's rationale for keeping raw responses.
    best: dict = {}
    for r in rows:
        k = (r["person_id"], r["dimension_key"])
        if k not in best or r["scored_at"] > best[k]["scored_at"]:
            best[k] = r
    return {k: v["score"] for k, v in best.items()}


def _fetch_company_scores(conn: Connection, company_ids: list[int],
                           priority: Sequence[str]) -> dict:
    stmt = text(
        "SELECT company_id, dimension_key, score, confidence, source, as_of "
        "FROM company_dimension_score WHERE company_id IN :cids"
    ).bindparams(bindparam("cids", expanding=True))
    raw = conn.execute(stmt, {"cids": company_ids}).mappings().all()
    norm = [{"entity_id": r["company_id"], "key": r["dimension_key"], "source": r["source"],
             "as_of": r["as_of"], "score": r["score"], "confidence": r["confidence"]} for r in raw]
    resolved = resolve_best_by_source(norm, priority)
    return {k: (r["score"], r["confidence"]) for k, r in resolved.items()}


def _fetch_company_confounders(conn: Connection, company_ids: list[int],
                                conf_kind: dict, priority: Sequence[str]) -> dict:
    stmt = text(
        "SELECT company_id, dimension_key AS confounder_key, value_num, value_cat, source, as_of "
        "FROM company_confounder_value WHERE company_id IN :cids"
    ).bindparams(bindparam("cids", expanding=True))
    raw = conn.execute(stmt, {"cids": company_ids}).mappings().all()
    norm = [{"entity_id": r["company_id"], "key": r["confounder_key"], "source": r["source"],
             "as_of": r["as_of"], "value_num": r["value_num"], "value_cat": r["value_cat"]}
            for r in raw if r["confounder_key"] in conf_kind]
    resolved = resolve_best_by_source(norm, priority)
    out = {}
    for k, r in resolved.items():
        out[k] = r["value_cat"] if conf_kind[k[1]] == "categorical" else r["value_num"]
    return out


def assemble_training_data(
    conn: Connection,
    cfg: dict,
    outcome_type: OutcomeType,
    *,
    scoring_key_version: Optional[str] = None,
    source_priority: Sequence[str] = DEFAULT_SOURCE_PRIORITY,
    min_company_confidence: Optional[float] = None,
) -> AssembleResult:
    """
    conn: open SQLAlchemy Connection against the schema.sql database.
    cfg:  solverah_model_config.yaml, already loaded. Read from here, not
          re-derived from the DB's dimension/confounder registry tables --
          the YAML is the documented single source of truth for structure;
          the registry tables exist only "to give FKs something to point at."
    outcome_type: 'appeal' or 'experienced'. Required -- see module docstring.
    scoring_key_version: pin an explicit person-assessment scoring version.
          Default: each person's most recent scored_at (the current key).
    min_company_confidence: opt-in row filter (default off — v1 keeps
          confidence OUT of the ranking math per the 08-10 handoff; this
          param exists but is not silently applied). See NOTES.md.

    Returns AssembleResult; person/env/conf/outcome are ready for
    build_model.build_model(person, env, conf, cfg, pri, outcome).
    `dropped` records every excluded (person, company) pair and why --
    silently shrinking N is exactly the "empty response read as absence"
    class of bug this project's handoffs keep catching after the fact;
    don't repeat it here by staying silent about exclusions.
    """
    dims = [d["key"] for d in cfg["dimensions"] if d.get("active")]
    confs = [c for c in cfg["confounders"] if c.get("active") and c.get("measurable")]
    conf_keys = [c["key"] for c in confs]
    conf_kind = {c["key"]: c.get("kind") for c in confs}

    candidates = _fetch_candidates(conn, outcome_type)
    if not candidates:
        return AssembleResult(
            person={k: np.array([], dtype=float) for k in dims},
            env={k: np.array([], dtype=float) for k in dims},
            conf={k: np.array([]) for k in conf_keys},
            outcome=np.array([]), rows=[], dropped=[],
        )

    person_ids = sorted({c["person_id"] for c in candidates})
    company_ids = sorted({c["company_id"] for c in candidates})

    person_scores = _fetch_person_scores(conn, person_ids, scoring_key_version)
    company_scores = _fetch_company_scores(conn, company_ids, source_priority)
    company_confs = _fetch_company_confounders(conn, company_ids, conf_kind, source_priority)

    return assemble_rows(candidates, person_scores, company_scores, company_confs,
                          dims, conf_keys, outcome_type, min_company_confidence)



# ===========================================================================
# THE ENVIRONMENT-REPORT SOURCE  (BUILD_PLAN E-4)
# ===========================================================================
# Everything above assembles the (person, COMPANY) pairs schema.sql was drawn
# for: a recommendation was shown, an outcome came back, and the env side is a
# company's scraped/researched/declared scores. That path stays -- it is what
# serves ranking once a scored company set exists. It is not where the training
# rows come from at launch, because at launch there are no recommendations and
# no scored companies.
#
# BUILD_PLAN §5's E-4 calls the other path "the inversion paying off": the env
# side is the USER's own description of their own job (A-1's instrument, A-2's
# `environment_reports`) -- the current one, or since 2026-10-01 at most one
# PAST job (`environment_reports.subject`, see PAST-JOB ROWS below), keyed to
# the same `user_id` their person-side rows already carry, and the outcome is that same form's one evaluative item. A
# training pair therefore exists the moment someone fills the Situation Report
# in -- no company scoring, no funnel, no placement required.
#
# THIS IS A JOIN, NOT A TRANSLATION
# ---------------------------------
# A-1's `POLE_VALUES` are the rater rubric's own five band values and A-2's
# columns were aligned to schema.sql's on purpose, so nothing here rescales,
# recodes or reinterprets anything: dimension scores come out of
# `environment_dimension_score` exactly as stored (0..1), and `stage_size` /
# `comp` / `experienced_outcome` come out raw on their 1..5 scales.
# schema.sql is explicit that raw is the contract -- "stored RAW / unscaled;
# the model standardizes via the `scale` in solverah_model_config.yaml" -- and
# `build_model.preprocess_conf` is the thing that standardizes. Scaling here
# would run that preprocessing twice at fit time and once at predict time.
#
# WHAT THIS SOURCE COSTS, STATED ONCE
# -----------------------------------
# These rows are self-reported on BOTH sides. If a person's environment score
# is partly a function of the person, the model fits a partly circular
# relationship -- work_pulse/SITUATION_ITEMS_BIAS_REVIEW.md, Finding 3's
# "Worse" paragraph names E-4 by name for exactly this. A known limitation of
# the source, not a defect in this function; the provenance carried on every
# row is what lets a later analysis see it instead of inheriting it silently.
#
# ONE OUTCOME, NOT TWO
# --------------------
# Deliberately no `outcome_type` parameter, unlike `assemble_training_data`
# above. `appeal` means "did this recommendation look like a fit", and there is
# no recommendation behind an environment report -- the user already holds (or,
# on a past row, already held) the job. The only outcome on this path is
# `experienced` (1..5 ordinal, the same shape as `outcome_experienced.working_scale`), so there is nothing for a
# caller to choose and nothing that could be blended.

#
# PAST-JOB ROWS (PRODUCT_DECISIONS.md §2, 2026-10-01)
# ---------------------------------------------------
# A user who has filed a current report may file ONE more about the job before
# it (`environment_reports.subject = 'past'`). Same instrument, same scoring,
# same outcome item -- so it assembles into the same arrays, and every row says
# which kind it is in `report_subject`. Two things about a past row are easy to
# get wrong, and both are why analysis must filter or stratify on
# `report_subject` rather than on anything else:
#   * It pairs with the SAME per-user person-side pin as the user's current
#     rows. The person side was measured around now; the job ended earlier.
#   * `career_status` is the user's status ON THE DAY THEY FILED, not a property
#     of the past job. 'employed' on a past row does not mean that job is still
#     in progress.
# The first-outcome-fit pre-registration (Amendment 1) treats past rows as
# exploratory only; its primary sample is `current_report_ordinal == 1`.

ENVIRONMENT_OUTCOME_TYPE: OutcomeType = "experienced"

#: `environment_reports.subject` values, restated from `model.ENV_REPORT_SUBJECTS`
#: (no app on sys.path here; a test asserts the two agree).
SUBJECT_CURRENT = "current"
SUBJECT_PAST = "past"
ENVIRONMENT_REPORT_SUBJECTS: tuple[str, ...] = (SUBJECT_CURRENT, SUBJECT_PAST)

#: `environment_reports` columns carrying a `confounders:` key from
#: `solverah_model_config.yaml`. The instrument asks all three active
#: measurable confounders. `industry` joined on 2026-10-01 (PRODUCT_DECISIONS.md
#: §2). It is optional, so a NULL row (pre-2026-10-01 "never asked", or "not
#: sure / prefer not to say" since) stays masked exactly as every row was before.
#:
#: This IS `work_pulse.situation_items.CONTEXT_COLUMNS` minus `experienced`
#: (the outcome, not a confounder). Restated rather than imported so this
#: module still works with no app on sys.path; a tripwire test asserts the two
#: agree rather than trusting the comment.
ENVIRONMENT_CONFOUNDER_COLUMNS: dict[str, str] = {
    "stage_size": "stage_size",
    "comp": "comp",
    "industry": "industry",
}

#: A-1's single evaluative item, "Overall, how well is this role working for
#: you?" (1..5) -- the model's outcome node on this path.
ENVIRONMENT_OUTCOME_COLUMN = "experienced_outcome"

#: `environment_reports.career_status` values that may produce a training row.
#:
#: `first_job` is absent BY DESIGN. PRODUCT_DECISIONS.md §2's environment-
#: instrument rulings (2026-09-10) say a never-employed user skips the form
#: entirely, and `situation_report_service.submit_environment_report` refuses
#: them with a 409 -- so a `first_job` row reaching here means that refusal was
#: bypassed and the row may describe a job nobody ever held. Dropped with a
#: named reason rather than asserted away: one bad row must not take a fit run
#: down, and `dropped` is where it becomes visible instead of silent.
TRAINABLE_CAREER_STATUSES: frozenset[str] = frozenset({"employed", "between_jobs"})

#: Where a respondent came from. 'app' is anyone who answered through the
#: product; 'pilot_form' is a respondent to the pre-launch pilot form
#: (`causal_graph/v1_model/pilot_form/`, pre-registration Amendment 2), whose
#: answers were imported through the app's own storage doorways under a user
#: whose email ends in PILOT_FORM_EMAIL_DOMAIN. The domain IS the label: the
#: importer is the only thing that creates such addresses (`.invalid` is
#: reserved by RFC 2606 and can never be registered or mailed), so the label
#: needs no new column and no migration, and an app row's provenance is
#: untouched -- it is 'app' because its email is anything else.
RESPONDENT_SOURCE_APP = "app"
RESPONDENT_SOURCE_PILOT_FORM = "pilot_form"
RESPONDENT_SOURCES: tuple[str, ...] = (RESPONDENT_SOURCE_APP, RESPONDENT_SOURCE_PILOT_FORM)
PILOT_FORM_EMAIL_DOMAIN = "@pilotform.solverah.invalid"

PIN_EXPLICIT = "explicit_override"
#: Renamed from `PIN_FIRST_CORE = "first_core_sitting"` on 2026-10-05, when core
#: became retakeable (6babb39) and the default stopped being the first sitting.
#: Nothing stored carried the old value (no fit output, devfit report or
#: pre-registration names it), so the label changed with the rule.
PIN_DEFAULT = "default_core_sitting"

CAPTURE_PATH = "self_report_environment"
OUTCOME_SOURCE = "environment_report"


@dataclass
class EnvironmentTrainingRow:
    """Provenance for one assembled row -- one `environment_reports` row, the
    core sitting it was paired with, and the funnel/collider inventory.

    Every field is documented in FUNNEL_FIELD_CAPTURE_NOTES below, including
    the always-NULL ones; a test asserts the two stay in step.
    """

    # --- supplied ---------------------------------------------------------
    environment_report_id: int
    user_id: int
    submitted_at: datetime
    career_status: str
    env_form_version: str
    person_submission_id: str
    person_form_version: Optional[str]
    person_scoring_key_version: Optional[str]
    pin_source: str
    report_ordinal: int
    report_count_for_user: int
    employer_name_normalized: Optional[str]
    report_subject: str
    current_report_ordinal: Optional[int]
    respondent_source: str = RESPONDENT_SOURCE_APP
    outcome_source: str = OUTCOME_SOURCE
    capture_path: str = CAPTURE_PATH

    # --- named by the handoff, not suppliable from an environment report ---
    company_id: None = None
    recommendation_id: None = None
    is_exploration: None = None
    rank: None = None
    channel: None = None
    p_fit: None = None
    p_fit_low: None = None
    p_fit_high: None = None
    model_run_id: None = None
    funnel_actions: None = None
    match_formed: None = None
    started_at: None = None


#: Every provenance field on `EnvironmentTrainingRow`, and how it was captured.
#:
#: BUILD_PLAN §5's second E-4 bullet is "funnel/collider fields carried per the
#: handoff (capture how each pair entered the data)". This is that capture, as
#: DATA rather than as prose, so a consumer can print it and a test can assert
#: no field is accounted for by silence.
#:
#: `None` on this path is a fact about how the pair formed, not a gap waiting
#: to be filled: nothing selected this pair, which is exactly why it is not
#: subject to the collider schema.sql's principle 5 exists to make visible.
#: Emitted as explicit NULL columns rather than omitted, so a later run mixing
#: both sources has one row shape and can still tell the two apart.
FUNNEL_FIELD_CAPTURE_NOTES: dict[str, str] = {
    # --- supplied by the app DB -------------------------------------------
    "environment_report_id": "environment_reports.id -- this row's identity.",
    "user_id": (
        "environment_reports.user_id -- the same key person_dimension_score carries, "
        "which is what makes the person/env join a join rather than a resolution."
    ),
    "submitted_at": "environment_reports.submitted_at -- when the env side was described.",
    "career_status": (
        "environment_reports.career_status, snapshotted at submit time: the USER's "
        "status on the day they filed. On a current row it is THE sample-definition "
        "field: 'employed' describes a job in progress and 'between_jobs' one just "
        "left, which are different populations answering the same outcome item. On a "
        "PAST row it describes the filer, NOT the job -- that job has ended whatever "
        "this says -- so analysis must split on report_subject, never infer it from "
        "here. 'first_job' cannot appear -- see TRAINABLE_CAREER_STATUSES."
    ),
    "env_form_version": (
        "environment_reports.version (situation_items.FORM_VERSION). Era separability "
        "for the ENV side -- §5's 'scoring_key_version discipline keeps eras separable'."
    ),
    "person_submission_id": (
        "The pinned core sitting, resolved exactly as A-5 does -- see "
        "_resolve_pinned_submissions. This is the join key, and WHICH sitting it names "
        "is the whole question E-4's join path has to answer."
    ),
    "person_form_version": (
        "assessment_response.form_version on the PINNED sitting: which item set the "
        "respondent actually answered. Era separability for the PERSON side."
    ),
    "person_scoring_key_version": (
        "The key the score was re-derived UNDER -- today's active item file, which is "
        "not necessarily the one the respondent saw. Both are carried because they can "
        "differ; where they differ incompatibly score_stored_choices refuses and the "
        "row is dropped rather than scored across two eras."
    ),
    "pin_source": (
        "'explicit_override' (a situation_report_pins row) or 'default_core_sitting' "
        "(⚑5's default: the sitting that was current when the user's FIRST current "
        "report was filed, fallen forward past any sitting that can no longer be "
        "scored -- see _resolve_pinned_submissions). Carried because the two say "
        "different things about what the person side describes: the default is the "
        "person side the report was built from; the override is one the user chose."
    ),
    "report_ordinal": (
        "1-based position of this report among ALL that user's reports (current and "
        "past alike), oldest first by (submitted_at, id). "
        "environment_reports is append-only, so a user contributes as many rows as they "
        "have submitted and those rows are NOT independent observations. This is what "
        "lets a fit group or weight them instead of counting one person several times."
    ),
    "report_count_for_user": (
        "How many reports that user has in total, both subjects. See report_ordinal."
    ),
    "report_subject": (
        "environment_reports.subject: 'current' (the user's current or most recent "
        "job -- every row filed before 2026-10-01) or 'past' (the one job before that, "
        "at most one per user, filed after a current report). A past row pairs with the "
        "SAME per-user person-side pin as the current rows, so its person side was "
        "measured around now while the job it describes ended earlier; and its "
        "career_status describes the user at filing, not that job. Pre-registration "
        "Amendment 1: past rows are exploratory only."
    ),
    "current_report_ordinal": (
        "1-based position of this report among that user's CURRENT reports only, "
        "oldest first by (submitted_at, id); None on a past row. Past rows interleaved "
        "in time do not shift it. 'First eligible current report' -- the "
        "pre-registered primary sample -- is current_report_ordinal == 1."
    ),
    "respondent_source": (
        "'app' or 'pilot_form'. 'pilot_form' means the respondent answered the "
        "pre-launch pilot Google Form and the answers were imported into a LOCAL "
        "research database through the app's own storage doorways "
        "(causal_graph/v1_model/pilot_form/); 'app' is every other respondent. Derived "
        "from the user's email domain, which the importer alone assigns "
        "(PILOT_FORM_EMAIL_DOMAIN, an RFC 2606 .invalid address); the email itself never "
        "leaves the query. Pre-registration Amendment 2: pilot current rows count toward "
        "the primary population, and each look is ALSO called on 'app' rows alone -- a "
        "disagreement is reported as mode-sensitive. Synthetic devfit users read 'app' "
        "here; they are excluded by their own domain (section 0.2), not by this field."
    ),
    "employer_name_normalized": (
        "environment_reports.employer_name_normalized (⚑6) -- optional, usually NULL, "
        "displayed nowhere. Carried, not joined: it is the future company-aggregation "
        "lane's key, and it is also the cheap between-vs-within-employer variance check "
        "SITUATION_ITEMS_BIAS_REVIEW.md Finding 3 asks for."
    ),
    "outcome_source": (
        "Constant 'environment_report' -- outcome_experienced.source's role ('survey | "
        "inferred(tenure) | ...'), answered honestly here: it is a survey, of the person "
        "doing the job, about the job."
    ),
    "capture_path": (
        "Constant 'self_report_environment'. THE answer to 'how did this pair enter the "
        "data': it did not come through a recommendation at all -- the user already held "
        "the job (current or past, see report_subject) and described it. Every NULL "
        "below follows from this one value."
    ),
    # --- named by the handoff, NOT suppliable from an environment report ---
    "company_id": (
        "NULL: an environment report has no company row behind it (model.py, "
        "'Environment side'). employer_name_normalized is a free-text hint, and "
        "resolving it to a company_id would be a fuzzy match presented as a fact."
    ),
    "recommendation_id": (
        "NULL: no match_recommendation preceded this pair. Nothing was shown, so there "
        "is no shown-list row to point at."
    ),
    "is_exploration": (
        "NULL, and NOT False. False would claim the pair came through the ranker on the "
        "exploit arm; it came through no ranker at all. schema.sql's exploration flag "
        "exists to break the feedback loop, and a pair that never entered the loop has "
        "no value for it."
    ),
    "rank": "NULL: no shown list, so no position in one.",
    "channel": (
        "NULL: match_recommendation.channel ('onsite'|'email') describes how a "
        "recommendation reached the user. Nothing reached them."
    ),
    "p_fit": (
        "NULL: the model's own prediction at show time. Nothing was predicted. This is "
        "the field that makes model-driven selection visible, and its absence here is "
        "the evidence that none occurred."
    ),
    "p_fit_low": "NULL: credible-interval bound on p_fit. See p_fit.",
    "p_fit_high": "NULL: credible-interval bound on p_fit. See p_fit.",
    "model_run_id": "NULL: which model produced the recommendation. There was none.",
    "funnel_actions": (
        "NULL, not []. rec_action rows hang off a recommendation_id and there is no "
        "recommendation, so the funnel is UNOBSERVED -- which is not the same claim as "
        "an empty funnel ('we watched and they did nothing'). An empty list asserts the "
        "second, and would be read as evidence."
    ),
    "match_formed": (
        "NULL: schema.sql principle 5's collider -- 'hired + accepted', the condition "
        "outcome rows are silently selected on. These rows are NOT conditioned on it "
        "(the user is describing a job they have or had, however they came by it), "
        "which is this source's real advantage over the placement path and the reason "
        "to record the absence explicitly rather than leave the column out."
    ),
    "started_at": (
        "NULL: outcome_experienced.started_at (when they joined). A-1 does not ask for "
        "tenure, so the DB cannot supply it. The one field here a future instrument "
        "question COULD fill -- flagged as such rather than as a permanent absence."
    ),
}

#: The subset of FUNNEL_FIELD_CAPTURE_NOTES that is always NULL on this path,
#: kept as data so `unsupplied_fields` need not be re-derived from prose.
UNSUPPLIED_FUNNEL_FIELDS: tuple[str, ...] = (
    "company_id",
    "recommendation_id",
    "is_exploration",
    "rank",
    "channel",
    "p_fit",
    "p_fit_low",
    "p_fit_high",
    "model_run_id",
    "funnel_actions",
    "match_formed",
    "started_at",
)


@dataclass
class EnvironmentAssembleResult:
    """`build_model.build_model(person, env, conf, cfg, pri, outcome=...)`'s
    four arguments, plus what it takes to audit them.

    `conf_missing` is not decoration. `comp` is nullable by a signed ruling
    ("not sure", PRODUCT_DECISIONS.md §2, 2026-09-10) and so is `industry`
    (asked since 2026-10-01, optional, NULL on "not sure / prefer not to say";
    NULL on every older row, which was never asked), so a confounder column
    can legitimately carry no value for a row that is otherwise complete. NaN
    carries that through a float array honestly, but NaN cannot do the same
    job for a categorical column, and no array shape distinguishes "missing" from "happened to be NaN". The mask
    does, for every kind, which is what lets the model config -- not this
    function -- decide whether to exclude the column, model the missingness, or
    impute. Imputing or dropping HERE would make that decision unrecoverable.

    FEEDABLE INTO build_model AS OF 2026-09-21 -- pass `conf_missing` along.
    The decision this docstring used to defer was made, in the model and not in
    this loader: EXCLUDE THE TERM for a masked row, for both kinds.
    `match_core.preprocess_conf(conf, cfg, conf_missing=...)` zeroes a masked
    continuous value (a "not sure" comp) and gives a masked categorical one
    (a NULL `industry`) a `<key>__present` flag that drops its per-level
    weight from the logit, while a row that names its industry keeps
    `__present` = 1 and indexes its own level. Without the mask both still
    fail loudly -- a NaN or a None raises, naming the confounder -- so a caller
    that forgets `conf_missing` cannot get a silently wrong fit. The
    OrderedLogistic head the 1-5 outcome needs landed 2026-09-17
    (`build_model.build_model(head="experienced")`). What still stands between
    this source and a fit run is data volume, nothing in code (see
    ASSEMBLE_TRAINING_DATA_NOTES.md).
    """

    person: dict[str, np.ndarray]
    env: dict[str, np.ndarray]
    conf: dict[str, np.ndarray]
    conf_missing: dict[str, np.ndarray]
    outcome: np.ndarray
    rows: list            # list[EnvironmentTrainingRow], same order as the arrays
    dropped: list[dict] = field(default_factory=list)
    unsupplied_confounders: tuple[str, ...] = ()
    outcome_type: str = ENVIRONMENT_OUTCOME_TYPE


# ---------------------------------------------------------------------------
# Pure assembly -- no SQL, no app, no clock. Same split as assemble_rows above
# and for the same reason: the decisions live here where a test can reach them
# without a database.
# ---------------------------------------------------------------------------
def _report_order_key(report: dict) -> tuple:
    """Oldest first, `id` breaking a same-instant tie -- the ascending mirror
    of `environment_report_store.latest_environment_report`'s ordering, which
    is `submitted_at DESC, id DESC`. Used only to number a user's reports."""
    return (report["submitted_at"], report["id"])


def assemble_environment_rows(
    reports: list[dict],
    env_scores: dict,
    pins: dict,
    pinned_choices: dict,
    pinned_form_versions: dict,
    dims: list[str],
    conf_keys: list[str],
    conf_kind: dict[str, Optional[str]],
    score_person: Callable[[dict], dict],
    scoring_key_version: Optional[str],
    respondent_sources: Optional[dict] = None,
) -> EnvironmentAssembleResult:
    """Build the arrays from fully-resolved lookups.

    reports:              `environment_reports` rows as dicts.
    env_scores:           {(environment_report_id, dimension_key): score}.
    pins:                 {user_id: (submission_id, pin_source)}.
    pinned_choices:       {submission_id: {item_id: choice}} -- RAW responses.
    pinned_form_versions: {submission_id: form_version}.
    score_person:         {item_id: choice} -> {dimension_key: 0..1}. Injected
                          rather than imported so this function stays pure;
                          the real caller passes
                          `assessment_form.score_stored_choices`, which is the
                          ONLY sanctioned way to read a named sitting's scores
                          (A-5's load-bearing lesson: `person_dimension_score`
                          is upserted in place, so a retake silently rewrites
                          what a pinned read would have returned).
    respondent_sources:   {user_id: 'app' | 'pilot_form'}. A user it does not
                          name is 'app', so a caller that predates the pilot
                          form gets exactly the rows it always got.

    Every excluded report lands in `dropped` with a reason. Silently shrinking N
    is the "empty response read as absence" bug this project keeps catching
    after the fact; it is not going to be reintroduced by the function that
    decides how big N is.
    """
    ordered = sorted(reports, key=_report_order_key)

    per_user: dict = {}
    for report in ordered:
        per_user.setdefault(report["user_id"], []).append(report["id"])
    ordinal_of = {
        report_id: (index + 1, len(ids))
        for ids in per_user.values()
        for index, report_id in enumerate(ids)
    }
    # The same numbering over current reports alone: a past report never takes
    # (or shifts) a current report's place.
    current_ordinal_of: dict = {}
    current_seen: dict = {}
    for report in ordered:
        if report["subject"] == SUBJECT_CURRENT:
            current_seen[report["user_id"]] = current_seen.get(report["user_id"], 0) + 1
            current_ordinal_of[report["id"]] = current_seen[report["user_id"]]

    # One sitting is shared by every report a user has written (the pin is per
    # user, not per report), so score it once. The cache also means a sitting
    # that cannot be scored is reported once per report but computed once.
    person_cache: dict = {}

    def _person_scores(submission_id: str):
        if submission_id not in person_cache:
            try:
                person_cache[submission_id] = (
                    score_person(pinned_choices[submission_id]),
                    None,
                )
            except Exception as exc:  # noqa: BLE001 - any scoring refusal is a drop
                person_cache[submission_id] = (None, "%s: %s" % (type(exc).__name__, exc))
        return person_cache[submission_id]

    dropped: list = []
    rows: list = []
    person_vals = {k: [] for k in dims}
    env_vals = {k: [] for k in dims}
    conf_vals = {k: [] for k in conf_keys}
    conf_missing_vals = {k: [] for k in conf_keys}
    outcome_vals: list = []

    for report in ordered:
        report_id, user_id = report["id"], report["user_id"]
        reasons: list = []

        if report["career_status"] not in TRAINABLE_CAREER_STATUSES:
            # Not merely unusual -- A-5 refuses this submission with a 409, so a
            # row here means the refusal was bypassed. See TRAINABLE_CAREER_STATUSES.
            reasons.append("career_status=%r is not trainable" % report["career_status"])
        if report["subject"] not in ENVIRONMENT_REPORT_SUBJECTS:
            # The column's CHECK holds this vocabulary; a row here bypassed it.
            reasons.append("subject=%r is not a known subject" % report["subject"])

        e_row = {}
        for key in dims:
            value = env_scores.get((report_id, key))
            if value is None:
                reasons.append("env.%s" % key)
            e_row[key] = value

        pin = pins.get(user_id)
        p_row: dict = {}
        submission_id = form_version = pin_source = None
        if pin is None:
            # A user can describe their job before they ever take core: A-5
            # serves that as the `needs_core` state. It is a real, complete
            # environment report with no person side to pair it with.
            reasons.append("no_pinned_core_sitting")
        else:
            submission_id, pin_source = pin
            form_version = pinned_form_versions.get(submission_id)
            if not pinned_choices.get(submission_id):
                reasons.append("pinned_sitting_has_no_responses:%s" % submission_id)
            else:
                scores, failure = _person_scores(submission_id)
                if failure is not None:
                    reasons.append("person_side_unscorable:%s" % failure)
                else:
                    for key in dims:
                        value = scores.get(key)
                        if value is None:
                            reasons.append("person.%s" % key)
                        p_row[key] = value

        outcome_value = report.get(ENVIRONMENT_OUTCOME_COLUMN)
        if outcome_value is None:
            reasons.append("outcome.%s" % ENVIRONMENT_OUTCOME_COLUMN)

        cf_row: dict = {}
        cf_missing: dict = {}
        for key in conf_keys:
            column = ENVIRONMENT_CONFOUNDER_COLUMNS.get(key)
            value = None if column is None else report.get(column)
            cf_row[key] = value
            cf_missing[key] = value is None

        if reasons:
            dropped.append(
                {
                    "environment_report_id": report_id,
                    "user_id": user_id,
                    "reason": reasons,
                }
            )
            continue

        ordinal, count = ordinal_of[report_id]
        for key in dims:
            person_vals[key].append(p_row[key])
            env_vals[key].append(e_row[key])
        for key in conf_keys:
            conf_vals[key].append(cf_row[key])
            conf_missing_vals[key].append(cf_missing[key])
        outcome_vals.append(outcome_value)
        rows.append(
            EnvironmentTrainingRow(
                environment_report_id=report_id,
                user_id=user_id,
                submitted_at=report["submitted_at"],
                career_status=report["career_status"],
                env_form_version=report["version"],
                person_submission_id=submission_id,
                person_form_version=form_version,
                person_scoring_key_version=scoring_key_version,
                pin_source=pin_source,
                report_ordinal=ordinal,
                report_count_for_user=count,
                employer_name_normalized=report.get("employer_name_normalized"),
                report_subject=report["subject"],
                current_report_ordinal=current_ordinal_of.get(report_id),
                respondent_source=(respondent_sources or {}).get(
                    user_id, RESPONDENT_SOURCE_APP
                ),
            )
        )

    person_arr = {k: np.asarray(v, dtype=float) for k, v in person_vals.items()}
    env_arr = {k: np.asarray(v, dtype=float) for k, v in env_vals.items()}

    conf_arr: dict = {}
    for key in conf_keys:
        values = conf_vals[key]
        if conf_kind.get(key) == "categorical":
            # No NaN for a categorical: object array, None where absent. A
            # categorical NaN would one-hot as a level named 'nan'.
            conf_arr[key] = np.asarray(values, dtype=object)
        else:
            # None -> NaN, which is what a float array means by "no value".
            # NOT an imputation: conf_missing carries the same fact losslessly
            # for a consumer that would rather not test for NaN.
            conf_arr[key] = np.asarray(
                [np.nan if v is None else float(v) for v in values], dtype=float
            )
    conf_missing_arr = {
        k: np.asarray(v, dtype=bool) for k, v in conf_missing_vals.items()
    }

    # int, not float: `experienced` is an ordinal 1..5 whose outcome node is
    # OrderedLogistic (schema.sql's own note on working_scale), and an
    # OrderedLogistic observed vector is a category index.
    outcome_arr = np.asarray(outcome_vals, dtype=int)

    unsupplied = tuple(k for k in conf_keys if k not in ENVIRONMENT_CONFOUNDER_COLUMNS)

    return EnvironmentAssembleResult(
        person=person_arr,
        env=env_arr,
        conf=conf_arr,
        conf_missing=conf_missing_arr,
        outcome=outcome_arr,
        rows=rows,
        dropped=dropped,
        unsupplied_confounders=unsupplied,
    )


# ---------------------------------------------------------------------------
# DB-fetch layer for the environment source.
#
# Reads the APPLICATION database (model.py's tables), not schema.sql's own --
# `environment_reports` exists only there, and `person_id` is `user_id` there
# (model.py: "schema.sql's separate `person` table buys an indirection whose
# only justification is..."). Same portability discipline as the fetch layer
# above: expanding IN bindings, and every "which row wins" decision resolved in
# Python rather than in DISTINCT ON, so the logic is testable and legible.
# ---------------------------------------------------------------------------
def _fetch_environment_reports(conn: Connection) -> list[dict]:
    sql = text(
        "SELECT id, user_id, submitted_at, stage_size, comp, industry, experienced_outcome, "
        "career_status, employer_name_normalized, version, subject "
        "FROM environment_reports"
    )
    return [dict(r) for r in conn.execute(sql).mappings().all()]


def _fetch_environment_dimension_scores(conn: Connection, report_ids: list[int]) -> dict:
    stmt = text(
        "SELECT environment_report_id, dimension_key, score "
        "FROM environment_dimension_score WHERE environment_report_id IN :rids"
    ).bindparams(bindparam("rids", expanding=True))
    rows = conn.execute(stmt, {"rids": report_ids}).mappings().all()
    # No resolution step, deliberately: uq_edscore_report_dim already makes
    # (report, dimension) unique, so unlike company_dimension_score there is
    # never more than one row to choose between.
    return {(r["environment_report_id"], r["dimension_key"]): r["score"] for r in rows}


def _fetch_respondent_sources(conn: Connection, user_ids: list[int]) -> dict:
    """{user_id: 'pilot_form'} for the pilot-form respondents among `user_ids`;
    everyone absent is 'app'. The match runs in the database and only ids come
    back, so no email address ever reaches the assembler."""
    if not user_ids:
        return {}
    stmt = text(
        "SELECT id FROM users WHERE id IN :uids AND LOWER(email) LIKE :pattern"
    ).bindparams(bindparam("uids", expanding=True))
    rows = conn.execute(
        stmt, {"uids": user_ids, "pattern": "%" + PILOT_FORM_EMAIL_DOMAIN}
    ).all()
    return {r[0]: RESPONDENT_SOURCE_PILOT_FORM for r in rows}


def _default_pin_start(sittings: list[dict], anchor_at) -> int:
    """Index into `sittings` (oldest first) of the sitting that was current when
    the user's first current Environment Report was filed -- the anchor
    `situation_report_service._default_pin` starts from. Pure, so the rule is
    testable without a database.

    One sitting: it, whatever the anchor. No anchor (no current report yet):
    the latest. Otherwise the last sitting completed at or before the anchor,
    or the first one after it when every sitting is newer than the report.
    """
    if len(sittings) <= 1 or anchor_at is None:
        return len(sittings) - 1
    at_or_before = [
        i for i, row in enumerate(sittings) if row["completed_at"] <= anchor_at
    ]
    return at_or_before[-1] if at_or_before else 0


def _resolve_pinned_submissions(
    conn: Connection,
    user_ids: list[int],
    score_person: Optional[Callable[[dict], dict]] = None,
) -> dict:
    """{user_id: (submission_id, pin_source)} -- the D-15 pin, resolved the way
    `solverah.services.situation_report_service._pinned_submission_id` resolves
    it (the rule since core became retakeable, 6babb39 / 2026-10-05):

    1. An explicit recalibrate override (`situation_report_pins`) wins outright
       and is never fallen forward from -- the user chose it.
    2. Otherwise the DEFAULT: of the user's completed core sittings, oldest
       first by (completed_at, id), the latest one completed at or before the
       user's FIRST current Environment Report (MIN(submitted_at) over
       subject='current'); the first sitting after that report if every sitting
       is newer; the latest sitting if no current report exists yet.
    3. FALL-FORWARD from that anchor: the first sitting, anchor included, whose
       responses exist and that `score_person` scores without raising. If none
       is readable, the anchor itself -- the row then drops downstream with
       `person_side_unscorable`, by name.

    The service's halves are `situation_report_pin_store.explicit_pin`,
    `assessment_store.completed_core_sittings`,
    `environment_report_store.first_environment_report_submitted_at` and
    `assessment_store.dimension_scores_for_submission`. Restated in SQL here
    rather than called, so the model lane needs no Flask application context
    to assemble a training set -- a fit run is offline, and giving it a hard
    dependency on the web app's session would be the wrong trade. The
    restatement is the risk, so a tripwire test asserts this function agrees
    with the service's own resolver on every seeded case rather than trusting
    that the two descriptions match.

    Why that sitting and not simply the first or the latest: the pin protects a
    report the user has SEEN. Every input is append-only, so the anchor never
    moves once the first report exists -- a retake after filing, or a re-filed
    report, leaves the training row's person side where it was until the user
    recalibrates. A retake BEFORE the first filing is the sitting they built
    the report on, so it is the one used; the old first-sitting rule would have
    paired the report with a sitting the user had already replaced. Falling
    forward past an unreadable anchor protects nothing the user saw (the report
    renders no person side for it) and is still deterministic: the first
    readable sitting after a fixed anchor does not change on a later retake.

    score_person: {item_id: choice} -> scores, raising on a sitting the current
    item file cannot score. Default `assessment_form.score_stored_choices`, the
    same scorer the service's readability check uses.
    """
    if not user_ids:
        return {}

    overrides = conn.execute(
        text(
            "SELECT user_id, submission_id FROM situation_report_pins "
            "WHERE user_id IN :uids"
        ).bindparams(bindparam("uids", expanding=True)),
        {"uids": user_ids},
    ).mappings().all()
    resolved = {r["user_id"]: (r["submission_id"], PIN_EXPLICIT) for r in overrides}

    remaining = [uid for uid in user_ids if uid not in resolved]
    if not remaining:
        return resolved

    # `public_id` is a uuid; assessment_store hands out `public_id.hex`, which
    # is the 32 characters with no dashes, and that is what the pin table and
    # assessment_response.submission_id both hold. `completed_at IS NOT NULL`
    # as in `completed_core_sittings`: a core row is always written complete,
    # and a sitting with no completion time cannot be placed in time.
    rows = conn.execute(
        text(
            "SELECT id, user_id, completed_at, "
            "REPLACE(CAST(public_id AS VARCHAR), '-', '') AS submission_id "
            "FROM assessment_submissions "
            "WHERE kind = 'core' AND completed_at IS NOT NULL AND user_id IN :uids"
        ).bindparams(bindparam("uids", expanding=True)),
        {"uids": remaining},
    ).mappings().all()
    sittings_of: dict = {}
    for row in sorted(rows, key=lambda r: (r["completed_at"], r["id"])):
        sittings_of.setdefault(row["user_id"], []).append(row)
    if not sittings_of:
        return resolved

    anchors = conn.execute(
        text(
            "SELECT user_id, MIN(submitted_at) AS anchor_at FROM environment_reports "
            "WHERE subject = :current AND user_id IN :uids GROUP BY user_id"
        ).bindparams(bindparam("uids", expanding=True)),
        {"uids": list(sittings_of), "current": SUBJECT_CURRENT},
    ).mappings().all()
    anchor_of = {r["user_id"]: r["anchor_at"] for r in anchors}

    candidates_of = {
        user_id: sittings[_default_pin_start(sittings, anchor_of.get(user_id)):]
        for user_id, sittings in sittings_of.items()
    }
    choices_of, _versions = _fetch_pinned_responses(
        conn,
        sorted({row["submission_id"] for rows_ in candidates_of.values() for row in rows_}),
    )
    if score_person is None:
        score_person = _app_assessment_form().score_stored_choices

    for user_id, candidates in candidates_of.items():
        chosen = candidates[0]["submission_id"]
        for row in candidates:
            choices = choices_of.get(row["submission_id"])
            if not choices:
                continue
            try:
                score_person(choices)
            except Exception:  # noqa: BLE001 - any scoring refusal is "unreadable"
                continue
            chosen = row["submission_id"]
            break
        resolved[user_id] = (chosen, PIN_DEFAULT)
    return resolved


def _fetch_pinned_responses(conn: Connection, submission_ids: list[str]) -> tuple[dict, dict]:
    """({submission_id: {item_id: choice}}, {submission_id: form_version}).

    `assessment_response` rows, NOT `person_dimension_score`. That table is
    upserted in place per (user, dimension, scoring_key_version), so after a
    retake it describes the LATEST sitting while still being the obvious thing
    to read for the pinned one -- it would answer, plausibly, about the wrong
    sitting. Raw responses are append-only and a retake never touches them.
    """
    if not submission_ids:
        return {}, {}
    stmt = text(
        "SELECT submission_id, item_id, choice, form_version "
        "FROM assessment_response WHERE submission_id IN :sids"
    ).bindparams(bindparam("sids", expanding=True))
    rows = conn.execute(stmt, {"sids": submission_ids}).mappings().all()

    choices: dict = {}
    versions: dict = {}
    for r in rows:
        choices.setdefault(r["submission_id"], {})[r["item_id"]] = r["choice"]
        versions.setdefault(r["submission_id"], set()).add(r["form_version"])
    # One sitting is submitted once, so one form_version; joined rather than
    # picked arbitrarily so a mixed sitting is visible in the row instead of
    # being resolved away by whichever row the database returned first.
    return choices, {k: "|".join(sorted(v)) for k, v in versions.items()}


def _app_assessment_form():
    """The app's person-side doorway, imported lazily.

    `assessment_form` has no Flask and no SQLAlchemy import by design (its own
    module docstring), so this costs the model lane an sys.path entry and
    nothing else -- no app context, no database session. Lazy so that
    `python assemble_training_data.py` still runs its sqlite self-test with the
    repo's root nowhere near sys.path.
    """
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    import assessment_form

    return assessment_form


def assemble_environment_training_data(
    conn: Connection,
    cfg: dict,
    *,
    score_person: Optional[Callable[[dict], dict]] = None,
    scoring_key_version: Optional[str] = None,
) -> EnvironmentAssembleResult:
    """One training row per `environment_reports` row: (person, env, conf, outcome).

    conn: open SQLAlchemy Connection against the APPLICATION database.
    cfg:  solverah_model_config.yaml, already loaded -- the documented single
          source of truth for which dimensions and confounders exist, same as
          `assemble_training_data` above. A dimension activated there that A-1
          does not ask about produces no environment score, so every row drops
          naming it; that is the correct loud failure, not a case to paper over.
    score_person: override the person-side scorer (tests, or reproducing an
          older key). Default `assessment_form.score_stored_choices`.
    scoring_key_version: the key stamped on every row. Default
          `assessment_form.scoring_key_version()` -- the CURRENT key, because
          that is the one the default scorer re-derives under.

    ALL of a user's reports are assembled, not just the latest -- current and
    past alike; `report_subject` says which, and `current_report_ordinal == 1`
    selects each user's first current report.
    `environment_reports` is append-only and its history is the point (A-2's
    module docstring says so, and names this function). Repeated reports from
    one person are not independent observations, so `report_ordinal` and
    `report_count_for_user` ride on every row -- the fit needs to know, and
    dropping the history to avoid the problem would throw away the within-person
    variation that is the most informative thing this source has.

    THE JOIN PATH, IN ONE SENTENCE: every report a user has written pairs with
    the SAME core sitting -- their pin -- because the pin is per user, which is
    precisely what makes the person side sealed while the environment side
    varies. That includes a past-job report: its person side is the same pin,
    measured around now, not at the time of the job it describes.
    """
    form = None
    if score_person is None or scoring_key_version is None:
        form = _app_assessment_form()
    if score_person is None:
        score_person = form.score_stored_choices
    if scoring_key_version is None:
        scoring_key_version = form.scoring_key_version()

    dims = [d["key"] for d in cfg["dimensions"] if d.get("active")]
    confs = [c for c in cfg["confounders"] if c.get("active") and c.get("measurable")]
    conf_keys = [c["key"] for c in confs]
    conf_kind = {c["key"]: c.get("kind") for c in confs}

    reports = _fetch_environment_reports(conn)
    if not reports:
        return EnvironmentAssembleResult(
            person={k: np.array([], dtype=float) for k in dims},
            env={k: np.array([], dtype=float) for k in dims},
            conf={
                k: np.array([], dtype=object if conf_kind.get(k) == "categorical" else float)
                for k in conf_keys
            },
            conf_missing={k: np.array([], dtype=bool) for k in conf_keys},
            outcome=np.array([], dtype=int),
            rows=[],
            dropped=[],
            unsupplied_confounders=tuple(
                k for k in conf_keys if k not in ENVIRONMENT_CONFOUNDER_COLUMNS
            ),
        )

    report_ids = sorted({r["id"] for r in reports})
    user_ids = sorted({r["user_id"] for r in reports})

    env_scores = _fetch_environment_dimension_scores(conn, report_ids)
    pins = _resolve_pinned_submissions(conn, user_ids, score_person)
    pinned_choices, pinned_form_versions = _fetch_pinned_responses(
        conn, sorted({sid for sid, _ in pins.values()})
    )

    return assemble_environment_rows(
        reports,
        env_scores,
        pins,
        pinned_choices,
        pinned_form_versions,
        dims,
        conf_keys,
        conf_kind,
        score_person,
        scoring_key_version,
        respondent_sources=_fetch_respondent_sources(conn, user_ids),
    )


# ---------------------------------------------------------------------------
# Self-test. No live database exists yet to test against for real --
# schema.sql has never been migrated into the app's actual Postgres DB (see
# NOTES.md) -- so this runs the REAL functions above (not a re-implementation)
# against an in-memory sqlite DB with the same columns as schema.sql. Because
# the fetch layer avoids Postgres-only syntax (ANY, DISTINCT ON), this is the
# actual production code path, not an approximation of it.
# ---------------------------------------------------------------------------
def _build_test_db():
    import sqlalchemy as sa
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE recommendation (id INTEGER PRIMARY KEY, person_id INT, company_id INT)"))
        conn.execute(text("CREATE TABLE outcome_appeal (recommendation_id INT, fit_yes INT)"))
        conn.execute(text("CREATE TABLE outcome_experienced (person_id INT, company_id INT, recommendation_id INT, working_scale INT)"))
        conn.execute(text("CREATE TABLE person_dimension_score (person_id INT, dimension_key TEXT, score REAL, scoring_key_version TEXT, scored_at TEXT)"))
        conn.execute(text("CREATE TABLE company_dimension_score (company_id INT, dimension_key TEXT, score REAL, confidence REAL, source TEXT, as_of TEXT)"))
        conn.execute(text("CREATE TABLE company_confounder_value (company_id INT, dimension_key TEXT, value_num REAL, value_cat TEXT, confidence REAL, source TEXT, as_of TEXT)"))

        dims = ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]

        # Person 1: complete on all 6 dims. Person 2: missing 'decision' on purpose.
        for pid, complete in [(1, True), (2, False)]:
            for k in dims:
                if k == "decision" and not complete:
                    continue
                conn.execute(text("INSERT INTO person_dimension_score VALUES (:p,:k,0.5,'v1','2026-08-01')"),
                             {"p": pid, "k": k})

        # Company 10: BOTH a 'scraped' row (earlier as_of) and a 'declared'
        # row (later as_of) for autonomy -- proves priority beats mere
        # recency, and that scraped doesn't win just by being inserted first.
        conn.execute(text("INSERT INTO company_dimension_score VALUES (10,'autonomy',0.9,0.3,'scraped','2026-01-01')"))
        conn.execute(text("INSERT INTO company_dimension_score VALUES (10,'autonomy',0.6,0.95,'declared','2026-06-01')"))
        for k in dims:
            if k != "autonomy":
                conn.execute(text("INSERT INTO company_dimension_score VALUES (10,:k,0.4,0.7,'researched','2026-07-01')"), {"k": k})
        conn.execute(text("INSERT INTO company_confounder_value VALUES (10,'stage_size',3,NULL,0.8,'researched','2026-07-01')"))
        conn.execute(text("INSERT INTO company_confounder_value VALUES (10,'comp',3,NULL,0.8,'researched','2026-07-01')"))
        conn.execute(text("INSERT INTO company_confounder_value VALUES (10,'industry',NULL,'tech',0.8,'researched','2026-07-01')"))

        # Company 11: fully scored, used only by person 2 (who is incomplete
        # on the PERSON side) -- proves an incomplete candidate gets dropped
        # and recorded, not silently skipped.
        for k in dims:
            conn.execute(text("INSERT INTO company_dimension_score VALUES (11,:k,0.5,0.6,'researched','2026-07-01')"), {"k": k})
        conn.execute(text("INSERT INTO company_confounder_value VALUES (11,'stage_size',2,NULL,0.8,'researched','2026-07-01')"))
        conn.execute(text("INSERT INTO company_confounder_value VALUES (11,'comp',2,NULL,0.8,'researched','2026-07-01')"))
        conn.execute(text("INSERT INTO company_confounder_value VALUES (11,'industry',NULL,'finance',0.8,'researched','2026-07-01')"))

        conn.execute(text("INSERT INTO recommendation VALUES (100,1,10)"))
        conn.execute(text("INSERT INTO recommendation VALUES (101,2,11)"))
        conn.execute(text("INSERT INTO outcome_appeal VALUES (100,1)"))
        conn.execute(text("INSERT INTO outcome_appeal VALUES (101,0)"))
        conn.execute(text("INSERT INTO outcome_experienced VALUES (1,10,100,4)"))
    return engine


def _cfg_for_test():
    return {
        "dimensions": [{"key": k, "active": True} for k in
                       ["autonomy", "pace", "collaboration", "feedback", "innovation", "decision"]],
        "confounders": [
            {"key": "stage_size", "active": True, "measurable": True, "kind": "continuous"},
            {"key": "comp", "active": True, "measurable": True, "kind": "continuous"},
            {"key": "industry", "active": True, "measurable": True, "kind": "categorical",
             "levels": ["tech", "finance", "healthcare", "retail", "other"]},
        ],
    }


def _check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"  {status}  {name}" + (f"   [{detail}]" if detail and not cond else ""))
    assert cond, f"{name}: {detail}"


if __name__ == "__main__":
    engine = _build_test_db()
    cfg = _cfg_for_test()

    with engine.connect() as conn:
        result = assemble_training_data(conn, cfg, "appeal")

    print("APPEAL outcome:")
    _check("1 row assembled (person1 x company10), 1 dropped (person2 x company11)",
           len(result.rows) == 1 and len(result.dropped) == 1,
           f"rows={len(result.rows)} dropped={len(result.dropped)}")
    _check("surviving row is person 1, company 10",
           result.rows[0].person_id == 1 and result.rows[0].company_id == 10)
    _check("dropped row correctly attributes the missing field",
           result.dropped[0]["reason"] == ["person.decision"], result.dropped[0])
    _check("source-priority resolution: declared (0.6) beat scraped (0.9) for company 10 autonomy",
           result.env["autonomy"][0] == 0.6, result.env["autonomy"])
    _check("categorical confounder passed through RAW ('tech', not one-hot/index)",
           result.conf["industry"][0] == "tech", result.conf["industry"])
    _check("continuous confounder passed through RAW (3.0, not standardized)",
           result.conf["stage_size"][0] == 3.0, result.conf["stage_size"])
    _check("outcome array is the appeal value (fit_yes=1)", result.outcome[0] == 1)
    _check("all 6 dimensions present as arrays of length 1",
           all(len(result.person[k]) == 1 for k in result.person))

    with engine.connect() as conn:
        exp_result = assemble_training_data(conn, cfg, "experienced")
    print("\nEXPERIENCED outcome:")
    _check("1 row assembled (only person1 x company10 has an experienced outcome)",
           len(exp_result.rows) == 1, len(exp_result.rows))
    _check("outcome value is the 1-5 working_scale rating (4), not a 0/1",
           exp_result.outcome[0] == 4, exp_result.outcome)

    with engine.connect() as conn:
        result_min_conf = assemble_training_data(conn, cfg, "appeal", min_company_confidence=0.9)
    print("\nmin_company_confidence filter:")
    _check("company 10's other dims sit at confidence 0.7, below a 0.9 floor -> row dropped",
           len(result_min_conf.rows) == 0 and len(result_min_conf.dropped) == 2,
           f"rows={len(result_min_conf.rows)} dropped={len(result_min_conf.dropped)}")

    print("\nAll checks passed. This exercised the real production functions above")
    print("(fetch + resolve_best_by_source + assemble_rows) against sqlite -- the only")
    print("adaptation is the database engine itself; the code path is unchanged.")
    print("Still unverified: behavior against actual Postgres, and against real data volume.")
