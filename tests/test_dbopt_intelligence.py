"""DB-ledger regression tests for package I: path intelligence and the agent.

Five promises, each pinned against the real Postgres tables:

* **The path preferences are one profile key.** ``PUT`` writes
  ``profiles.extra.path_preferences`` through ``update_extra_key`` and answers
  with the value it wrote, so it no longer rewrites the profile's lists or reads
  the whole document back; ``GET`` reads the one key. Same bytes on the wire.
* **A wants save costs the same for one answer as for the whole panel.** One
  upsert for every answered item, where each item was a statement of its own.
* **No network call runs inside a transaction.** The scorer, anchor
  resolution, the corpus fetch, the deep fit, the agent's provider call and the
  account deletion's R2 deletes each record the session's state from inside the
  stubbed call -- the one moment that matters.
* **Nothing reloads after a commit, and nothing reads a known answer.** The
  handlers carry the user's id across their commits, a reset does not read back
  the judgements it just deleted, and the intake read is its one column.
* **The engine carries an idle-in-transaction ceiling**, on by default and off
  at 0.

Counted requests are made with NO outer app context (see ``_statements``).
"""

from __future__ import annotations

import contextlib
import re
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa

import backend.services.occupation_retrieval as retrieval
import backend.services.path_deep_fit as pdf
import backend.services.path_narrative as pn
import backend.services.path_scoring as ps
from backend.services.path_scoring import ScoredPath
from tests.query_count import count_queries

# The W-4 panel's fixtures -- a five-row corpus with real task and condition
# sidecars, an embedder that resolves every profile to Software Developers --
# reused rather than rebuilt, so the panel measured here is the one the W-4
# tests prove correct. The two autouse fixtures reset the process-wide memos.
from tests.test_path_wants_api import (  # noqa: F401 -- fixtures
    DEV_CODE,
    DEV_TASKS,
    PROFILE,
    SALES_CODE,
    _clean_process_state,
    _onet_key,
    _register_and_login,
    _set_profile,
    _task_key,
    _user_id,
    artifact,
    corpus,
    embedder,
    panel,
    sidecars,
    signed_in,
)
from tests.test_path_fit_api import _fit

PROFILE_LIST_TABLES = ("profile_experiences", "profile_educations", "profile_skills", "resumes")

SCORED = [
    ScoredPath(onet_code=SALES_CODE, title="Sales Engineers", score=0.8,
               overlapping_skills=["SQL"]),
    ScoredPath(onet_code="15-1251.00", title="Computer Programmers", score=0.7,
               overlapping_skills=["Python"]),
]

PREFERENCES = {
    "move_intent": "fresh_start",
    "seniority_intent": "move_up",
    "priority": "learning_growth",
}


# -- Helpers -----------------------------------------------------------------


@pytest.fixture(autouse=True)
def _narration_runs_in_this_app(monkeypatch):
    """Bind this file's app to the queue adapter, as the W-16 tests do."""
    from app import app
    from solverah.infra.queue import celery_app

    monkeypatch.setitem(celery_app.conf, "solverah_flask_app", app)


@contextlib.contextmanager
def _statements():
    """``count_queries`` for requests made with NO outer app context.

    The test client reuses an app context that is already pushed, so a request
    made inside one would share this test's session and identity map instead of
    getting its own, as it does in production. The context here lives only long
    enough to resolve the engine the counter listens on.
    """
    from app import app

    with app.app_context():
        counting = count_queries()
        statements = counting.__enter__()
    try:
        yield statements
    finally:
        counting.__exit__(None, None, None)


def _reads_of(statements, table):
    """The SELECTs in *statements* whose FROM clause starts at *table*."""
    source = re.compile(r"\bFROM\s+%s\b" % re.escape(table), re.IGNORECASE)
    return [
        s for s in statements
        if s.lstrip().upper().startswith("SELECT") and source.search(s)
    ]


def _touching_profile_lists(statements):
    pattern = re.compile(r"\b(%s)\b" % "|".join(PROFILE_LIST_TABLES))
    return [s for s in statements if pattern.search(s)]


def _in_transaction() -> bool:
    from model import db

    return db.session().in_transaction()


def _recording(seen, label, result=None, *, call=None):
    """A stand-in for a network call that records the session state first."""

    def _stub(*args, **kwargs):
        seen.append((label, _in_transaction()))
        if call is not None:
            return call(*args, **kwargs)
        return result

    return _stub


def _record_corpus(monkeypatch, corpus_obj, seen):
    stub = _recording(seen, "get_corpus", corpus_obj)
    monkeypatch.setattr(retrieval, "get_corpus", stub)
    monkeypatch.setattr(ps, "get_corpus", stub)


def _record_scorer(monkeypatch, seen):
    monkeypatch.setattr(ps, "score_paths", _recording(seen, "score_paths", list(SCORED)))
    monkeypatch.setattr(pn, "generate_narratives", MagicMock(return_value=[]))


def _store_a_want():
    """One stored answer, so the scoring paths resolve the anchor."""
    from app import app
    from model import db
    from solverah.repositories import path_wants_repository

    with app.app_context():
        path_wants_repository.set_answers(
            _user_id(), DEV_CODE, [("condition", "people", "more", "")]
        )
        db.session.commit()


def _labels_open(seen):
    return [label for label, open_ in seen if open_]


# -- 1. Path preferences: one key, same bytes ---------------------------------


def test_path_preference_reads_and_writes_touch_one_key_and_answer_the_same_bytes(
    client, signed_in
):
    """Before: the PUT ran the whole-document write (the profile's four lists
    re-read and re-written), reloaded the expired user after its commit, then
    read the whole document back; the GET read the whole document too."""
    csrf = signed_in
    headers = {"X-CSRF-TOKEN": csrf}

    with _statements() as put_statements:
        put = client.put("/api/v1/me/path-preferences", json=PREFERENCES, headers=headers)
    assert put.status_code == 200
    assert put.get_json() == PREFERENCES

    with _statements() as get_statements:
        got = client.get("/api/v1/me/path-preferences")
    assert got.status_code == 200
    assert got.data == put.data

    # The write: user lookup, row guarantee, value read, swap, fit invalidation.
    assert _touching_profile_lists(put_statements) == []
    assert len(_reads_of(put_statements, "users")) == 1
    assert len(put_statements) <= 6, put_statements
    # The read: user lookup and the one key.
    assert _touching_profile_lists(get_statements) == []
    assert len(_reads_of(get_statements, "profiles")) == 1
    assert len(get_statements) <= 2, get_statements

    from app import app
    from solverah.repositories import profile_repository

    with app.app_context():
        document = profile_repository.load_document(_user_id())
    assert document["path_preferences"] == PREFERENCES
    # The rest of the document is untouched.
    assert document["experience"] == PROFILE["experience"]
    assert document["skills"] == PROFILE["skills"]


def test_an_invalid_preference_is_still_a_400_and_writes_nothing(client, signed_in):
    before = client.get("/api/v1/me/path-preferences")
    bad = client.put(
        "/api/v1/me/path-preferences",
        json={**PREFERENCES, "priority": "money"},
        headers={"X-CSRF-TOKEN": signed_in},
    )
    assert bad.status_code == 400
    assert bad.get_json() == {"error": "Invalid priority"}
    assert client.get("/api/v1/me/path-preferences").data == before.data


# -- 2. Wants: flat in the number of items -----------------------------------


def _answers_for_the_whole_panel():
    tasks = [
        {"kind": "task", "key": _task_key(statement), "verdict": "more"}
        for statement, _label in DEV_TASKS
    ]
    conditions = [
        {"kind": "condition", "key": axis, "verdict": "less"}
        for axis in ("people", "public", "leading", "desk")
    ]
    return tasks + conditions


def test_a_wants_save_sends_as_many_statements_for_one_answer_as_for_the_whole_panel(
    client, panel
):
    """Before: one upsert per answered item, so eight answers cost seven more
    statements than one."""
    headers = {"X-CSRF-TOKEN": panel}
    everything = _answers_for_the_whole_panel()
    assert len(everything) == 8

    with _statements() as one:
        first = client.put("/api/v1/me/path-wants", json={"answers": everything[:1]},
                           headers=headers)
    with _statements() as eight:
        second = client.put("/api/v1/me/path-wants", json={"answers": everything},
                            headers=headers)

    assert first.status_code == 200 and second.status_code == 200
    assert len(eight) == len(one), (one, eight)
    # Nothing reloads the user after the commit.
    assert len(_reads_of(eight, "users")) == 1
    body = second.get_json()
    assert {row["verdict"] for row in body["tasks"]} == {"more"}
    assert {row["verdict"] for row in body["conditions"]} == {"less"}


def test_a_duplicate_answer_is_still_the_422_and_writes_nothing(client, panel):
    answer = {"kind": "condition", "key": "people", "verdict": "more"}
    resp = client.put("/api/v1/me/path-wants", json={"answers": [answer, answer]},
                      headers={"X-CSRF-TOKEN": panel})
    assert resp.status_code == 422
    assert resp.get_json()["errors"][0]["code"] == "duplicate"
    body = client.get("/api/v1/me/path-wants").get_json()
    assert all(row["verdict"] is None for row in body["conditions"])


# -- 3. No transaction open during a network call ----------------------------


def test_the_scoring_job_holds_no_transaction_across_its_network_calls(
    client, panel, corpus, monkeypatch
):
    """Before: the profile, intake, judgement and wants reads left the job's
    transaction open through anchor resolution, the scorer and the summary
    lookup's corpus load."""
    _store_a_want()
    seen = []
    _record_corpus(monkeypatch, corpus, seen)
    _record_scorer(monkeypatch, seen)
    monkeypatch.setattr(ps, "resolve_anchor_code",
                        _recording(seen, "resolve_anchor_code", DEV_CODE))

    resp = client.post("/api/v1/me/path-suggestion-jobs", headers={"X-CSRF-TOKEN": panel})
    assert resp.status_code == 202
    job = client.get("/api/v1" + resp.get_json()["status_url"]).get_json()
    assert job["status"] == "succeeded", job

    labels = {label for label, _ in seen}
    assert {"resolve_anchor_code", "score_paths", "get_corpus"} <= labels
    assert _labels_open(seen) == []


def test_a_tap_holds_no_transaction_and_never_reloads_the_user(
    client, panel, corpus, monkeypatch
):
    """Before: the corpus load, anchor resolution and the scorer all ran inside
    the transaction the user lookup opened, and the re-rank reloaded the user
    its commit had expired."""
    _store_a_want()
    seen = []
    _record_corpus(monkeypatch, corpus, seen)
    _record_scorer(monkeypatch, seen)
    monkeypatch.setattr(ps, "resolve_anchor_code",
                        _recording(seen, "resolve_anchor_code", DEV_CODE))

    with _statements() as statements:
        resp = client.post(
            "/api/v1/me/path-feedback",
            json={"onet_code": SALES_CODE, "verdict": "interesting"},
            headers={"X-CSRF-TOKEN": panel},
        )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["feedback"] == {SALES_CODE: "interesting"}

    assert {"resolve_anchor_code", "score_paths", "get_corpus"} <= {l for l, _ in seen}
    assert _labels_open(seen) == []
    assert len(_reads_of(statements, "users")) == 1


def test_a_reset_reads_no_judgements_back_and_holds_no_transaction(
    client, panel, corpus, monkeypatch
):
    """Before: the reset deleted every judgement, committed, reloaded the user
    and then SELECTed the judgements it had just deleted."""
    seen = []
    _record_corpus(monkeypatch, corpus, seen)
    _record_scorer(monkeypatch, seen)
    tap = client.post(
        "/api/v1/me/path-feedback",
        json={"onet_code": SALES_CODE, "verdict": "not_for_me"},
        headers={"X-CSRF-TOKEN": panel},
    )
    assert tap.status_code == 200
    seen.clear()

    with _statements() as statements:
        resp = client.delete("/api/v1/me/path-feedback", headers={"X-CSRF-TOKEN": panel})
    assert resp.status_code == 200
    assert resp.get_json()["feedback"] == {}

    assert _reads_of(statements, "path_feedback") == []
    assert len(_reads_of(statements, "users")) == 1
    assert "score_paths" in {l for l, _ in seen}
    assert _labels_open(seen) == []


def test_the_intake_is_read_as_its_one_column(client, panel, corpus, monkeypatch):
    """Before: ``user.intake`` lazily loaded the whole row, the dead quiz JSON
    columns included."""
    from app import app
    from model import UserIntake, db

    with app.app_context():
        db.session.add(UserIntake(user_id=_user_id(), wpl_result={"archetype": "Builder"}))
        db.session.commit()

    seen = []
    _record_corpus(monkeypatch, corpus, seen)
    _record_scorer(monkeypatch, seen)
    with _statements() as statements:
        resp = client.post(
            "/api/v1/me/path-feedback",
            json={"onet_code": SALES_CODE, "verdict": "interesting"},
            headers={"X-CSRF-TOKEN": panel},
        )
    assert resp.status_code == 200

    intake_reads = _reads_of(statements, "user_intake")
    assert len(intake_reads) == 1
    assert "wpl_result" in intake_reads[0]
    assert "wpll_answers" not in intake_reads[0]


def test_the_archetype_still_reaches_the_scorer(client, panel, corpus, monkeypatch):
    from app import app
    from model import UserIntake, db

    with app.app_context():
        db.session.add(UserIntake(user_id=_user_id(), wpl_result={"archetype": "Builder"}))
        db.session.commit()

    _record_corpus(monkeypatch, corpus, [])
    scorer = MagicMock(return_value=list(SCORED))
    monkeypatch.setattr(ps, "score_paths", scorer)
    monkeypatch.setattr(pn, "generate_narratives", MagicMock(return_value=[]))

    resp = client.post(
        "/api/v1/me/path-feedback",
        json={"onet_code": SALES_CODE, "verdict": "interesting"},
        headers={"X-CSRF-TOKEN": panel},
    )
    assert resp.status_code == 200
    assert scorer.call_args.args[0].archetype == "Builder"


def test_a_deep_fit_miss_holds_no_transaction(client, panel, monkeypatch):
    """Before: the profile, intake and stored-fit reads left the transaction the
    user lookup opened sitting idle through the deep fit."""
    seen = []
    monkeypatch.setattr(pdf, "deep_fit", _recording(seen, "deep_fit", _fit(onet_code=SALES_CODE)))

    resp = client.post("/api/v1/me/path-fit/%s" % SALES_CODE, headers={"X-CSRF-TOKEN": panel})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["cached"] is False
    assert seen == [("deep_fit", False)]

    again = client.post("/api/v1/me/path-fit/%s" % SALES_CODE, headers={"X-CSRF-TOKEN": panel})
    assert again.get_json()["cached"] is True
    assert len(seen) == 1


def test_the_wants_panel_resolves_its_anchor_with_no_transaction_open(
    client, panel, corpus, monkeypatch
):
    """Before: the profile and intake reads' transaction stayed open through
    anchor resolution and the corpus load, on the GET and on the PUT."""
    seen = []
    _record_corpus(monkeypatch, corpus, seen)
    real_resolve = ps.resolve_anchor_code
    monkeypatch.setattr(ps, "resolve_anchor_code",
                        _recording(seen, "resolve_anchor_code", call=real_resolve))

    assert client.get("/api/v1/me/path-wants").status_code == 200
    put = client.put(
        "/api/v1/me/path-wants",
        json={"answers": [{"kind": "condition", "key": "desk", "verdict": "less"}]},
        headers={"X-CSRF-TOKEN": panel},
    )
    assert put.status_code == 200

    assert [l for l, _ in seen].count("resolve_anchor_code") == 2
    assert _labels_open(seen) == []


def test_the_agent_turn_holds_no_transaction_during_the_provider_call(client, monkeypatch):
    """Before: the user lookup's transaction stayed open through the provider
    call and every token of the stream."""
    csrf = _register_and_login(client, monkeypatch, email="ledger-i-agent@example.com")
    seen = []
    chunk = MagicMock()
    chunk.choices[0].delta.content = "Hello"

    def _create(**_kwargs):
        seen.append(("agent", _in_transaction()))
        return iter([chunk])

    fake = MagicMock()
    fake.chat.completions.create.side_effect = _create
    monkeypatch.setattr("solverah.infra.llm.get_agent_client", lambda: fake)

    resp = client.post(
        "/api/v1/agent/messages",
        json={"messages": [{"role": "user", "content": "Hi"}], "model": "test-model"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200
    assert b"Hello" in resp.data
    assert seen == [("agent", False)]


class _RecordingR2:
    def __init__(self):
        self.calls = []

    def delete_object(self, Bucket, Key):
        self.calls.append((Key, _in_transaction()))


def test_account_deletion_holds_no_transaction_across_its_r2_deletes(client, monkeypatch):
    """Before: the user lookup and the intake and resume reads left the
    transaction open through every R2 delete. The order is kept: storage first,
    then the rows."""
    email = "ledger-i-delete@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    user_id = _user_id(email)
    key = "users/%d/resume.pdf" % user_id
    _set_profile({"resumeKey": key, "uploadedResume": {"type": "application/pdf"}},
                 email=email)
    r2 = _RecordingR2()
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")
    monkeypatch.setattr("solverah.infra.storage.get_s3_client", lambda: r2)

    resp = client.delete("/api/v1/me", json={"confirm": "DELETE"},
                         headers={"X-CSRF-TOKEN": csrf})

    assert resp.status_code == 200
    assert resp.get_json()["r2_delete_failures"] == []
    assert r2.calls == [(key, False)]

    from app import app
    from model import User, db
    from solverah.repositories import profile_repository

    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.status == "deleted"
        assert user.email == "deleted-%d@tombstone.invalid" % user_id
        assert set(profile_repository.load_document(user_id)) == {"deleted_at"}


# -- 4. The engine's idle-in-transaction ceiling -----------------------------


def test_the_engine_ends_sessions_idle_in_transaction_by_default():
    from solverah.config import Settings
    from tests.test_config import BASE_ENV

    options = Settings.from_env(dict(BASE_ENV)).engine_options()["connect_args"]["options"]

    assert "-c idle_in_transaction_session_timeout=300000" in options
    assert "-c statement_timeout=15000" in options


def test_the_idle_in_transaction_ceiling_is_configurable_and_off_at_zero():
    from solverah.config import Settings
    from tests.test_config import BASE_ENV

    tuned = Settings.from_env(dict(BASE_ENV, DB_IDLE_IN_TRANSACTION_TIMEOUT_MS="120000"))
    off = Settings.from_env(dict(BASE_ENV, DB_IDLE_IN_TRANSACTION_TIMEOUT_MS="0"))

    assert "idle_in_transaction_session_timeout=120000" in (
        tuned.engine_options()["connect_args"]["options"]
    )
    assert "idle_in_transaction_session_timeout=0" in (
        off.engine_options()["connect_args"]["options"]
    )


def test_a_negative_idle_in_transaction_ceiling_is_rejected():
    from solverah.config import ConfigError, Settings
    from tests.test_config import BASE_ENV

    with pytest.raises(ConfigError) as exc:
        Settings.from_env(dict(BASE_ENV, DB_IDLE_IN_TRANSACTION_TIMEOUT_MS="-1"))
    assert "DB_IDLE_IN_TRANSACTION_TIMEOUT_MS" in str(exc.value)


def test_the_engine_accepts_the_options_it_builds(client):
    """The server takes the setting the options string sends (a typo in a
    ``-c`` option fails the connection, not a test)."""
    from app import app
    from model import db

    with app.app_context():
        value = db.session.execute(
            sa.text("SHOW idle_in_transaction_session_timeout")
        ).scalar_one()
    assert value == "5min"
