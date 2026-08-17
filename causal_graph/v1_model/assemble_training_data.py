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

    pip install sqlalchemy pyyaml

    python assemble_training_data.py     # runs the sqlite self-test at the bottom
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, Sequence

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
