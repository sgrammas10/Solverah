"""``GET``/``PUT /api/v1/me/path-wants`` -- the "what should change" panel (W-4).

Five things this file exists to prove, each of them a decision rather than an
implementation detail.

**"Fine" is the absence of a row.**  The panel's third answer is stored as
nothing at all (``model.PathWant``), so the tests that matter are the ones where
a row has to *disappear*: clearing with ``null``, clearing something already
clear, and the round trip that shows a cleared row reading back as ``verdict:
null`` rather than as a missing key.

**Partial is valid and is the expected case.**  Design doc §8.3: the panel is
skippable and must be valid half-finished.  A body naming two of twelve rows
changes those two and leaves the rest exactly where they were.

**An answer belongs to the occupation it was asked about.**  A key that is
perfectly valid for a *different* job is a 422, and a user whose current job
changes reads a new panel with none of the old answers on it -- while the old
rows stay in the table, inert.  This is the failure a client holding a stale
panel across a job change would cause, and it is the one worth a route test.

**The wants reach the scorer on BOTH paths, for all three intents.**  The cold
suggestion job and the warm feedback re-rank each call ``score_paths``, and a
`Wants` dropped on either of them is a user whose answers silently stopped
working.  The assertions are on the object handed over, not on the ranking --
`tests/test_path_scoring.py` owns the arithmetic.

**No stored wants is `wants=None`.**  Not an empty ``Wants``; the two are
equivalent to the scorer and only one of them is provably the call that existed
before this table did.

The corpus is five hand-written vectors with real sidecars written beside them in
``tmp_path``, so ``occupation_tasks`` and ``occupation_conditions`` run their own
file-loading code.  Nothing here reaches OpenAI, O*NET, S3, or
``Desktop/solverah-corpus``.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

import backend.services.occupation_conditions as conditions_mod
import backend.services.occupation_retrieval as retrieval
import backend.services.occupation_tasks as tasks_mod
import backend.services.path_narrative as pn
import backend.services.path_scoring as ps
from backend.services.occupation_conditions import ConditionsTable
from backend.services.occupation_retrieval import CorpusUnavailable, OccupationCorpus
from backend.services.occupation_tasks import OccupationTask, TasksTable
from backend.services.path_narrative import PathSuggestion
from backend.services.path_scoring import ScoredPath, Wants
from solverah.repositories import path_wants_repository as wants_repo

EMAIL = "pathwants@example.com"
OTHER_EMAIL = "pathwants-other@example.com"
PASSWORD = "Strongpass1!"

DIMS = 6

DEV_CODE = "15-1252.00"
TEACHER_CODE = "25-2021.00"
SALES_CODE = "41-3091.00"

#: The developer's eight offered statements, cut to four so a test can name them
#: all.  These are the ORIGINAL O*NET wording, which is the string that gets
#: embedded and hashed; the label beside each is the plain-words display prose
#: that must never reach either (design doc §8.7).
DEV_TASKS = [
    ("Modify existing software to correct errors or improve performance.",
     "Fix and tune existing software"),
    ("Analyze information to determine, recommend, and plan installation of a new system.",
     "Work out what a new system needs"),
    ("Confer with systems analysts, engineers and others to obtain information on limitations.",
     "Talk through limits with other teams"),
    ("Train users to operate and maintain the system.",
     "Train people to use the system"),
]
TEACHER_TASKS = [
    ("Establish and enforce rules for behavior and procedures for maintaining order.",
     "Set and hold the classroom rules"),
    ("Adapt teaching methods to meet students' varying needs and interests.",
     "Adapt lessons to different students"),
]


def unit(*values: float) -> np.ndarray:
    vec = np.zeros(DIMS, dtype=np.float32)
    vec[: len(values)] = values
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm else vec


DEV_VEC = unit(1, 0, 0, 0)
TEACHER_VEC = unit(0, 0, 1, 0)

W4_ROWS = [
    (DEV_CODE, "Software Developers", DEV_VEC),
    ("15-1251.00", "Computer Programmers", unit(0.90, 0.44, 0, 0)),
    (SALES_CODE, "Sales Engineers", unit(0, 1, 0, 0)),
    (TEACHER_CODE, "Elementary School Teachers", TEACHER_VEC),
    ("47-2111.00", "Electricians", unit(0, 0, 0, 1)),
]
W4_ZONES = {code: 4 for code, _, _ in W4_ROWS}

#: Percentiles for four of the seven axes.  The developer is design doc §8.2's
#: measured extreme -- 0.07 for `people`, 1.00 for `desk` -- because that is the
#: profile the distinctiveness rule exists for.
W4_PERCENTILES = {
    DEV_CODE: {"people": 0.07, "public": 0.10, "leading": 0.30, "desk": 1.00},
    "15-1251.00": {"people": 0.10, "public": 0.12, "leading": 0.28, "desk": 0.98},
    SALES_CODE: {"people": 0.85, "public": 0.90, "leading": 0.55, "desk": 0.60},
    TEACHER_CODE: {"people": 0.95, "public": 0.70, "leading": 0.80, "desk": 0.20},
    "47-2111.00": {"people": 0.40, "public": 0.45, "leading": 0.35, "desk": 0.05},
}

PROFILE = {
    "career_status": "employed",
    "skills": ["Python", "SQL"],
    "skill_levels": {"Python": "advanced", "SQL": "intermediate"},
    "experience": [{"position": "Software Engineer", "endDate": "Present"}],
    "path_preferences": {
        "move_intent": "adjacent",
        "seniority_intent": "open",
        "priority": "interesting_work",
    },
}


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


class FixedEmbeddings:
    """Every text embeds to one vector, so anchor resolution is a fixed point.

    Deliberately not a text->vector table: the anchor is resolved from documents
    this test does not compose (`_compose_profile_document` blends title, skills
    and assessment prose), and a table keyed on strings would silently fall
    through to the default the day one of those composers changed a word.
    """

    def __init__(self, owner: "FixedOpenAI") -> None:
        self.owner = owner

    def create(self, *, model: str, input: list[str]):
        self.owner.calls += 1
        return MagicMock(
            data=[
                MagicMock(index=i, embedding=self.owner.vector.tolist())
                for i, _ in enumerate(input)
            ]
        )


class FixedOpenAI:
    def __init__(self, vector: np.ndarray) -> None:
        self.vector = vector
        self.calls = 0
        self.embeddings = FixedEmbeddings(self)


def _tasks_table(rows: dict[str, list[tuple[str, str]]]) -> TasksTable:
    return TasksTable(
        tasks={
            code: tuple(OccupationTask(task=t, label=l) for t, l in pairs)
            for code, pairs in rows.items()
        },
        source="w4-fixture",
        built_at="2026-09-21T00:00:00+00:00",
        label_model="fixture",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch, email=EMAIL):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "name": "Wants User",
            "role": "job-seeker",
            "terms_accepted": True,
        },
    )

    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


def _set_profile(extra: dict, email: str = EMAIL):
    from app import app
    from model import User, db
    from solverah.repositories import profile_repository

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        profile_repository.update_document(
            user.id, lambda existing: {**existing, **extra}
        )
        db.session.commit()


def _user_id(email: str = EMAIL) -> int:
    from app import app
    from model import User

    with app.app_context():
        return User.query.filter_by(email=email).first().id


def _rows(email: str = EMAIL):
    from app import app
    from model import PathWant

    with app.app_context():
        return (
            PathWant.query.filter_by(user_id=_user_id(email))
            .order_by(PathWant.id.asc())
            .all()
        )


def _get(client):
    return client.get("/api/v1/me/path-wants")


def _put(client, csrf, answers):
    return client.put(
        "/api/v1/me/path-wants",
        json={"answers": answers},
        headers={"X-CSRF-TOKEN": csrf},
    )


def _task_key(statement: str) -> str:
    return wants_repo.item_key_for_task(statement)


def _keys(body) -> list[str]:
    return [row["key"] for row in body["tasks"]]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def artifact(tmp_path: Path) -> Path:
    """A matrix path the sidecars can be written beside.

    The file itself is never read -- the corpus object is handed to the code
    under test directly -- but `occupation_tasks` and `occupation_conditions`
    derive their own filenames from it and read those off disk for real, which is
    the point: a sidecar loader that stopped parsing would pass a test that
    handed it a table.
    """
    return tmp_path / "onet_corpus_w4fix.npy"


@pytest.fixture()
def corpus(monkeypatch, artifact) -> OccupationCorpus:
    matrix = np.array([vec for _, _, vec in W4_ROWS], dtype=np.float32)
    matrix.setflags(write=False)
    built = OccupationCorpus(
        version="w4fix",
        model="text-embedding-3-small",
        dimensions=DIMS,
        codes=tuple(code for code, _, _ in W4_ROWS),
        titles=tuple(title for _, title, _ in W4_ROWS),
        matrix=matrix,
        matrix_path=artifact,
        zones=dict(W4_ZONES),
    )
    monkeypatch.setattr(retrieval, "get_corpus", lambda: built)
    monkeypatch.setattr(ps, "get_corpus", lambda: built)
    return built


@pytest.fixture()
def sidecars(corpus, artifact):
    """Real ``*.tasks.json`` and ``*.experience.json`` files beside the artifact."""
    tasks_mod.write_tasks_sidecar(
        artifact, _tasks_table({DEV_CODE: DEV_TASKS, TEACHER_CODE: TEACHER_TASKS})
    )
    conditions_mod.write_conditions_sidecar(
        artifact, ConditionsTable(percentiles=W4_PERCENTILES, source="w4-fixture")
    )
    return artifact


@pytest.fixture()
def embedder(monkeypatch):
    """Anchor resolution lands on Software Developers, and can be moved."""
    fake = FixedOpenAI(DEV_VEC)
    monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: fake)
    return fake


@pytest.fixture()
def signed_in(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch)
    _set_profile(PROFILE)
    return csrf


@pytest.fixture()
def panel(signed_in, corpus, sidecars, embedder):
    """Signed in, with a resolvable anchor and both sidecars on disk."""
    return signed_in


@pytest.fixture(autouse=True)
def _clean_process_state():
    """The two sidecar memos and the embedding cache are process-wide.

    Without this a table loaded from one test's `tmp_path` answers the next
    test's request -- the memo is keyed on `corpus.version`, and every corpus
    here is version "w4fix" on purpose, so the collision is real rather than
    theoretical.
    """
    from solverah.services import path_cache

    tasks_mod.reset_tasks_cache()
    conditions_mod.reset_conditions_cache()
    ps._EMBED_CACHE.clear()
    path_cache.clear()
    yield
    tasks_mod.reset_tasks_cache()
    conditions_mod.reset_conditions_cache()
    ps._EMBED_CACHE.clear()
    path_cache.clear()


@pytest.fixture(autouse=True)
def _onet_key(monkeypatch):
    """`OnetClient()` refuses to construct without a key, and anchor resolution
    builds one before it decides it does not need it.

    CI parity: a developer with a populated `.env` gets this for free and every
    test below passes without the fixture; the runner sets five variables and has
    no `.env`, and would see a 500 in most of them.  CLAUDE.md's warning, applied.
    """
    monkeypatch.setenv("ONET_API_KEY", "test-key")


# ---------------------------------------------------------------------------
# Auth, method, shape
# ---------------------------------------------------------------------------


def test_unauthenticated_get_returns_401(client):
    assert _get(client).status_code == 401


def test_unauthenticated_put_returns_401(client):
    assert client.put("/api/v1/me/path-wants", json={"answers": []}).status_code == 401


def test_a_write_without_the_csrf_header_is_refused(client, monkeypatch, corpus):
    _register_and_login(client, monkeypatch)
    _set_profile(PROFILE)
    resp = client.put("/api/v1/me/path-wants", json={"answers": []})
    assert resp.status_code == 401
    assert _rows() == []


def test_post_is_not_served(client, monkeypatch):
    _register_and_login(client, monkeypatch)
    assert client.post("/api/v1/me/path-wants", json={}).status_code == 405


# ---------------------------------------------------------------------------
# GET -- the panel
# ---------------------------------------------------------------------------


def test_the_panel_is_the_users_own_occupation(client, panel):
    body = _get(client).get_json()

    assert body["status"] == "ok"
    assert body["anchor"] == {"onet_code": DEV_CODE, "title": "Software Developers"}
    assert [row["label"] for row in body["tasks"]] == [label for _, label in DEV_TASKS]
    assert [row["axis"] for row in body["conditions"]] == [
        "people",
        "public",
        "leading",
        "desk",
    ]


def test_every_row_starts_unanswered(client, panel):
    body = _get(client).get_json()
    assert all(row["verdict"] is None for row in body["tasks"])
    assert all(row["verdict"] is None for row in body["conditions"])


def test_the_original_statement_never_reaches_the_wire(client, panel):
    """`task` is what gets embedded and `label` is what gets read (design doc
    §8.7).  Shipping the statement would invite a client to send it back as the
    key, which is the coupling the digest exists to remove."""
    raw = _get(client).get_data(as_text=True)
    for statement, _ in DEV_TASKS:
        assert statement not in raw


def test_the_task_rows_arrive_in_sidecar_order(client, panel):
    assert _keys(_get(client).get_json()) == [_task_key(t) for t, _ in DEV_TASKS]


def test_no_current_job_is_no_anchor_not_an_error(client, monkeypatch, corpus, embedder):
    _register_and_login(client, monkeypatch)
    _set_profile({"career_status": "first_job", "skills": ["Python"]})

    resp = _get(client)

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "no_anchor"
    assert body["anchor"] is None
    assert body["tasks"] == [] and body["conditions"] == []


def test_a_profile_with_no_career_status_and_no_experience_is_no_anchor(
    client, monkeypatch, corpus, embedder
):
    _register_and_login(client, monkeypatch)
    _set_profile({"skills": ["Python"]})
    assert _get(client).get_json()["status"] == "no_anchor"


def test_a_missing_tasks_sidecar_still_offers_the_conditions(
    client, signed_in, corpus, embedder, artifact
):
    """`unavailable` is about the TASK half specifically.

    An axis is a name in code and its label is a constant, so nothing on the
    conditions half depends on a file being present -- a deployment that lost the
    tasks sidecar lets a user say "less time with the public" instead of showing
    them an empty screen.
    """
    conditions_mod.write_conditions_sidecar(
        artifact, ConditionsTable(percentiles=W4_PERCENTILES)
    )

    body = _get(client).get_json()

    assert body["status"] == "unavailable"
    assert body["anchor"]["onet_code"] == DEV_CODE
    assert body["tasks"] == []
    assert len(body["conditions"]) == 4


def test_an_occupation_with_no_statements_is_an_empty_list_not_an_error(
    client, signed_in, corpus, embedder, artifact
):
    """16 of the 939 retrievable rows publish no tasks at all (all military)."""
    tasks_mod.write_tasks_sidecar(artifact, _tasks_table({TEACHER_CODE: TEACHER_TASKS}))

    body = _get(client).get_json()

    assert body["status"] == "ok"
    assert body["tasks"] == []
    assert len(body["conditions"]) == 4


def test_no_current_job_is_no_anchor_even_during_an_outage(
    client, monkeypatch, embedder
):
    """"I have no current job" is a permanent fact about the profile.

    Answering it with the 503 an S3 outage produces would send a first-job user
    retrying something that will never work, so the anchor short-circuits before
    the corpus is loaded (`path_scoring.resolve_anchor_code`).
    """
    def _boom():
        raise CorpusUnavailable("no corpus source")

    monkeypatch.setattr(retrieval, "get_corpus", _boom)
    monkeypatch.setattr(ps, "get_corpus", _boom)
    _register_and_login(client, monkeypatch)
    _set_profile({**PROFILE, "career_status": "first_job"})

    resp = _get(client)

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "no_anchor"


def test_an_unreachable_corpus_is_the_typed_503(client, signed_in, monkeypatch):
    def _boom():
        raise CorpusUnavailable("no corpus source")

    monkeypatch.setattr(retrieval, "get_corpus", _boom)
    monkeypatch.setattr(ps, "get_corpus", _boom)

    resp = _get(client)

    assert resp.status_code == 503
    assert resp.get_json() == {"error": "corpus_unavailable"}


def test_the_panel_costs_no_onet_request(client, panel, monkeypatch):
    """Design doc §8.7's request-path discipline: the corpus answers the anchor."""
    from backend.services import onet_client as onet_module

    monkeypatch.setattr(
        onet_module.OnetClient,
        "search_occupations",
        lambda self, title: pytest.fail("the panel reached O*NET"),
    )
    assert _get(client).status_code == 200


# ---------------------------------------------------------------------------
# PUT -- storing answers
# ---------------------------------------------------------------------------


def test_a_task_answer_is_stored_with_the_original_statement(client, panel):
    statement, _ = DEV_TASKS[0]
    resp = _put(client, panel, [{"kind": "task", "key": _task_key(statement), "verdict": "less"}])

    assert resp.status_code == 200
    row = _rows()[0]
    assert (row.kind, row.verdict, row.anchor_onet_code) == ("task", "less", DEV_CODE)
    # The statement, not the label: it is what the scorer embeds.
    assert row.item_text == statement


def test_a_condition_answer_stores_the_axis_and_no_text(client, panel):
    _put(client, panel, [{"kind": "condition", "key": "people", "verdict": "more"}])

    row = _rows()[0]
    assert (row.kind, row.item_key, row.verdict) == ("condition", "people", "more")
    assert row.item_text == ""


def test_the_put_returns_the_same_shape_as_the_get(client, panel):
    written = _put(
        client, panel, [{"kind": "condition", "key": "desk", "verdict": "less"}]
    ).get_json()
    read = _get(client).get_json()
    assert written == read


def test_a_partial_body_leaves_the_rest_alone(client, panel):
    """Design doc §8.3: valid half-finished."""
    first, second = _task_key(DEV_TASKS[0][0]), _task_key(DEV_TASKS[1][0])

    _put(client, panel, [{"kind": "task", "key": first, "verdict": "less"}])
    body = _put(
        client, panel, [{"kind": "task", "key": second, "verdict": "more"}]
    ).get_json()

    verdicts = {row["key"]: row["verdict"] for row in body["tasks"]}
    assert verdicts[first] == "less"
    assert verdicts[second] == "more"
    assert len(_rows()) == 2


def test_an_empty_body_is_a_valid_no_op(client, panel):
    assert _put(client, panel, []).status_code == 200
    assert _rows() == []


def test_a_body_with_no_answers_key_at_all_is_a_no_op(client, panel):
    resp = client.put(
        "/api/v1/me/path-wants", json={}, headers={"X-CSRF-TOKEN": panel}
    )
    assert resp.status_code == 200
    assert _rows() == []


def test_re_answering_is_a_correction_not_a_second_row(client, panel):
    key = _task_key(DEV_TASKS[0][0])
    _put(client, panel, [{"kind": "task", "key": key, "verdict": "less"}])
    created = _rows()[0].created_at

    _put(client, panel, [{"kind": "task", "key": key, "verdict": "more"}])

    rows = _rows()
    assert len(rows) == 1
    assert rows[0].verdict == "more"
    assert rows[0].created_at == created


def test_the_same_body_twice_writes_the_same_state(client, panel):
    body = [
        {"kind": "task", "key": _task_key(DEV_TASKS[0][0]), "verdict": "less"},
        {"kind": "condition", "key": "people", "verdict": "more"},
    ]
    first = _put(client, panel, body).get_json()
    second = _put(client, panel, body).get_json()

    assert first == second
    assert len(_rows()) == 2


def test_null_clears_an_answer(client, panel):
    """"Fine" is the absence of a row (`model.PathWant`), so clearing is a
    DELETE and the cleared row reads back as null rather than vanishing from the
    panel."""
    key = _task_key(DEV_TASKS[0][0])
    _put(client, panel, [{"kind": "task", "key": key, "verdict": "less"}])
    assert len(_rows()) == 1

    body = _put(client, panel, [{"kind": "task", "key": key, "verdict": None}]).get_json()

    assert _rows() == []
    assert {row["key"]: row["verdict"] for row in body["tasks"]}[key] is None


def test_clearing_something_already_clear_is_a_200(client, panel):
    resp = _put(
        client,
        panel,
        [{"kind": "condition", "key": "leading", "verdict": None}],
    )
    assert resp.status_code == 200
    assert _rows() == []


# ---------------------------------------------------------------------------
# PUT -- the business-rule 422, and nothing written
# ---------------------------------------------------------------------------


def test_an_unknown_task_key_is_422_and_writes_nothing(client, panel):
    resp = _put(client, panel, [{"kind": "task", "key": "t_deadbeef1234", "verdict": "more"}])

    assert resp.status_code == 422
    # RFC 9457, not the sibling routes' `{"error": ...}`: this one names a field,
    # which is B-5's reason for the same choice on its malformed-cell 422.
    assert resp.get_json()["errors"] == [
        {"field": "answers.0.key", "code": "not_offered"}
    ]
    assert _rows() == []


def test_an_unknown_axis_is_422(client, panel):
    resp = _put(client, panel, [{"kind": "condition", "key": "pace", "verdict": "more"}])
    assert resp.status_code == 422
    assert _rows() == []


def test_a_key_from_a_different_occupation_is_422(client, panel):
    """The stale-panel-across-a-job-change case, which is the reason keys are
    validated against what a GET would offer rather than against a vocabulary."""
    foreign = _task_key(TEACHER_TASKS[0][0])
    resp = _put(client, panel, [{"kind": "task", "key": foreign, "verdict": "more"}])

    assert resp.status_code == 422
    assert _rows() == []


def test_a_bad_verdict_is_422(client, panel):
    key = _task_key(DEV_TASKS[0][0])
    resp = _put(client, panel, [{"kind": "task", "key": key, "verdict": "sort-of"}])
    assert resp.status_code == 422
    assert _rows() == []


def test_an_unknown_kind_is_422(client, panel):
    resp = _put(client, panel, [{"kind": "mood", "key": "people", "verdict": "more"}])
    assert resp.status_code == 422
    assert _rows() == []


def test_one_bad_answer_rejects_the_whole_body(client, panel):
    """Half acceptable is not half applied: the good answer is not written."""
    good = _task_key(DEV_TASKS[0][0])
    resp = _put(
        client,
        panel,
        [
            {"kind": "task", "key": good, "verdict": "less"},
            {"kind": "task", "key": "t_000000000000", "verdict": "more"},
        ],
    )
    assert resp.status_code == 422
    assert _rows() == []


def test_the_same_item_answered_twice_in_one_body_is_422(client, panel):
    key = _task_key(DEV_TASKS[0][0])
    resp = _put(
        client,
        panel,
        [
            {"kind": "task", "key": key, "verdict": "less"},
            {"kind": "task", "key": key, "verdict": "more"},
        ],
    )
    assert resp.status_code == 422
    assert _rows() == []


def test_answers_that_is_not_a_list_is_422(client, panel):
    resp = client.put(
        "/api/v1/me/path-wants",
        json={"answers": {"kind": "task"}},
        headers={"X-CSRF-TOKEN": panel},
    )
    assert resp.status_code == 422


def test_a_put_with_no_anchor_writes_nothing_and_says_so(
    client, monkeypatch, corpus, sidecars, embedder
):
    csrf = _register_and_login(client, monkeypatch)
    _set_profile({"career_status": "first_job", "skills": ["Python"]})

    resp = _put(
        client, csrf, [{"kind": "condition", "key": "people", "verdict": "more"}]
    )

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "no_anchor"
    assert _rows() == []


def test_a_put_with_an_unreachable_corpus_is_the_typed_503(
    client, signed_in, monkeypatch
):
    def _boom():
        raise CorpusUnavailable("no corpus source")

    monkeypatch.setattr(retrieval, "get_corpus", _boom)
    monkeypatch.setattr(ps, "get_corpus", _boom)

    resp = _put(client, signed_in, [{"kind": "condition", "key": "desk", "verdict": "more"}])

    assert resp.status_code == 503
    assert resp.get_json() == {"error": "corpus_unavailable"}
    assert _rows() == []


# ---------------------------------------------------------------------------
# A job change
# ---------------------------------------------------------------------------


def test_a_job_change_leaves_the_old_answers_inert(client, panel, embedder):
    """The rows survive and stop being read.  Not stale -- a true answer to a
    question about a job the user no longer holds (`model.PathWant`)."""
    _put(
        client,
        panel,
        [
            {"kind": "task", "key": _task_key(DEV_TASKS[0][0]), "verdict": "less"},
            {"kind": "condition", "key": "people", "verdict": "more"},
        ],
    )
    assert len(_rows()) == 2

    _set_profile(
        {**PROFILE, "experience": [{"position": "Teacher", "endDate": "Present"}]}
    )
    embedder.vector = TEACHER_VEC
    ps._EMBED_CACHE.clear()

    body = _get(client).get_json()

    assert body["anchor"]["onet_code"] == TEACHER_CODE
    assert [row["label"] for row in body["tasks"]] == [l for _, l in TEACHER_TASKS]
    assert all(row["verdict"] is None for row in body["tasks"])
    assert all(row["verdict"] is None for row in body["conditions"])
    # Still in the table, under the old anchor.
    assert {row.anchor_onet_code for row in _rows()} == {DEV_CODE}


def test_going_back_to_the_old_job_finds_the_old_answers(client, panel, embedder):
    key = _task_key(DEV_TASKS[0][0])
    _put(client, panel, [{"kind": "task", "key": key, "verdict": "less"}])

    _set_profile(
        {**PROFILE, "experience": [{"position": "Teacher", "endDate": "Present"}]}
    )
    embedder.vector = TEACHER_VEC
    ps._EMBED_CACHE.clear()
    assert _get(client).get_json()["anchor"]["onet_code"] == TEACHER_CODE

    _set_profile(PROFILE)
    embedder.vector = DEV_VEC
    ps._EMBED_CACHE.clear()

    body = _get(client).get_json()
    assert {row["key"]: row["verdict"] for row in body["tasks"]}[key] == "less"


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


def test_another_users_answers_are_never_visible(client, panel, monkeypatch):
    key = _task_key(DEV_TASKS[0][0])
    _put(client, panel, [{"kind": "task", "key": key, "verdict": "less"}])

    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": panel})
    _register_and_login(client, monkeypatch, email=OTHER_EMAIL)
    _set_profile(PROFILE, email=OTHER_EMAIL)

    body = _get(client).get_json()

    assert all(row["verdict"] is None for row in body["tasks"])
    assert _rows(OTHER_EMAIL) == []


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------


def test_a_write_drops_the_suggestion_cache_and_the_stored_fits(client, panel):
    """A want changes the ranking every later request computes, so the cached
    shortlist is wrong the moment one lands -- unlike a card judgement (F-6),
    which the re-rank writes straight back into the cache."""
    from model import PathFit, db
    from solverah.services import path_cache
    from app import app

    user_id = _user_id()
    path_cache.store(user_id, {"suggestions": []})
    with app.app_context():
        db.session.add(
            PathFit(
                user_id=user_id,
                onet_code=SALES_CODE,
                payload={},
                profile_fingerprint="x" * 64,
            )
        )
        db.session.commit()

    _put(client, panel, [{"kind": "condition", "key": "people", "verdict": "more"}])

    assert path_cache.get(user_id) is None
    with app.app_context():
        assert PathFit.query.filter_by(user_id=user_id).count() == 0


def test_a_rejected_write_invalidates_nothing(client, panel):
    from solverah.services import path_cache

    user_id = _user_id()
    path_cache.store(user_id, {"suggestions": []})

    _put(client, panel, [{"kind": "task", "key": "t_nope00000000", "verdict": "more"}])

    assert path_cache.get(user_id) == {"suggestions": []}


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------


def test_account_deletion_destroys_the_answers(client, panel):
    """D-7. Destroyed rather than retained de-identified -- see
    `tests/test_export_delete_coverage.py`'s entry for why the spelling rule and
    the meaning rule point different ways here."""
    from app import app
    from model import PathWant, db
    from solverah.repositories import account_repository

    _put(client, panel, [{"kind": "condition", "key": "desk", "verdict": "less"}])
    user_id = _user_id()

    with app.app_context():
        account_repository.delete_personal_rows(user_id, [])
        db.session.commit()
        assert PathWant.query.filter_by(user_id=user_id).count() == 0


# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------


def test_twenty_per_minute_shared_across_both_methods(client, panel):
    """A9, with `POST /me/path-feedback`'s interaction argument: the panel is
    twelve controls and a client that writes per control sends twelve requests,
    so ten would 429 the feature it is protecting.  One bucket for the pair,
    because read-answer-read is one user doing one thing."""
    from app import app
    from solverah.extensions import limiter

    limiter.reset()
    app.config["TESTING"] = False
    try:
        statuses = [_get(client).status_code for _ in range(19)]
        statuses.append(_put(client, panel, []).status_code)
        statuses.append(_put(client, panel, []).status_code)
    finally:
        app.config["TESTING"] = True
        limiter.reset()

    assert statuses[:20] == [200] * 20
    assert statuses[20] == 429


# ---------------------------------------------------------------------------
# The key itself
# ---------------------------------------------------------------------------


class TestItemKey:
    """The property the whole key exists for: an answer outlives a rebuild."""

    def test_the_same_statement_is_the_same_key(self) -> None:
        statement = DEV_TASKS[0][0]
        assert _task_key(statement) == _task_key(statement)

    def test_two_statements_are_two_keys(self) -> None:
        assert _task_key(DEV_TASKS[0][0]) != _task_key(DEV_TASKS[1][0])

    def test_whitespace_and_case_do_not_move_it(self) -> None:
        """A rebuild that collapses a double space or fixes a capital is the
        same question, and an answer must not be lost to it."""
        statement = DEV_TASKS[0][0]
        assert _task_key("  " + statement.upper().replace(" ", "  ") + " ") == _task_key(
            statement
        )

    def test_the_label_is_not_the_key(self) -> None:
        """Relabelling is a thing that happens on purpose: the labels come from
        an offline LLM pass and are rewritten with the sidecar."""
        statement, label = DEV_TASKS[0]
        assert _task_key(label) != _task_key(statement)

    def test_a_relabelled_sidecar_keeps_the_answer(
        self, client, panel, artifact
    ) -> None:
        key = _task_key(DEV_TASKS[0][0])
        _put(client, panel, [{"kind": "task", "key": key, "verdict": "less"}])

        relabelled = [(t, "Completely different wording") for t, _ in DEV_TASKS]
        tasks_mod.reset_tasks_cache()
        tasks_mod.write_tasks_sidecar(artifact, _tasks_table({DEV_CODE: relabelled}))

        body = _get(client).get_json()
        assert {row["key"]: row["verdict"] for row in body["tasks"]}[key] == "less"


# ---------------------------------------------------------------------------
# What the scorer is handed -- both sites, all three intents
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_scorer(monkeypatch):
    mock = MagicMock(
        return_value=[
            ScoredPath(onet_code=SALES_CODE, title="Sales Engineers", score=0.9),
            ScoredPath(onet_code=TEACHER_CODE, title="Teachers", score=0.8),
        ]
    )
    monkeypatch.setattr(ps, "score_paths", mock)
    return mock


@pytest.fixture()
def mock_narrator(monkeypatch):
    def _generate(candidates, _ctx):
        return [
            PathSuggestion(
                onet_code=c.onet_code,
                title=c.title,
                why_text="Because %s." % c.onet_code,
                profile_dimensions=[],
            )
            for c in candidates
        ]

    monkeypatch.setattr(pn, "generate_narratives", MagicMock(side_effect=_generate))


def _handed_wants(mock) -> Wants | None:
    assert mock.call_count == 1, "the scorer was called %d times" % mock.call_count
    return mock.call_args.kwargs["wants"]


def _run_cold_job(email: str = EMAIL):
    from app import app
    from model import User
    from solverah.services import intelligence_service

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        return intelligence_service.path_suggestions(user, app.logger)


@pytest.mark.parametrize("intent", ["stay_in_field", "adjacent", "fresh_start"])
def test_stored_wants_reach_the_cold_job_for_every_intent(
    client, panel, mock_scorer, mock_narrator, intent
):
    """All three, unlike F-6's judgements.  A want is the user's own statement
    about their own day, not a judgement about a card the scorer chose."""
    _put(
        client,
        panel,
        [
            {"kind": "task", "key": _task_key(DEV_TASKS[0][0]), "verdict": "less"},
            {"kind": "condition", "key": "people", "verdict": "more"},
        ],
    )
    _set_profile({**PROFILE, "path_preferences": {**PROFILE["path_preferences"], "move_intent": intent}})

    result = _run_cold_job()

    assert result.status == 200
    wants = _handed_wants(mock_scorer)
    assert wants.tasks_less == (DEV_TASKS[0][0],)
    assert wants.tasks_more == ()
    assert dict(wants.conditions) == {"people": "more"}


def test_stored_wants_reach_the_feedback_rerank(
    client, panel, mock_scorer, mock_narrator
):
    _put(client, panel, [{"kind": "condition", "key": "desk", "verdict": "less"}])
    mock_scorer.reset_mock()

    resp = client.post(
        "/api/v1/me/path-feedback",
        json={"onet_code": SALES_CODE, "verdict": "interesting"},
        headers={"X-CSRF-TOKEN": panel},
    )

    assert resp.status_code == 200
    assert dict(_handed_wants(mock_scorer).conditions) == {"desk": "less"}


def test_no_stored_wants_is_none_not_an_empty_wants(
    client, panel, mock_scorer, mock_narrator
):
    """Equivalent to the scorer -- `Wants().is_empty` is the identity case it
    pins -- but only one of the two is provably the call that existed before
    this table did."""
    assert _run_cold_job().status == 200
    assert _handed_wants(mock_scorer) is None


def test_a_user_who_has_answered_nothing_never_resolves_an_anchor(
    client, panel, mock_scorer, mock_narrator, embedder
):
    """The existence check comes first, so the common case pays nothing: no
    anchor resolution, no embedding, no sidecar read."""
    before = embedder.calls
    _run_cold_job()
    # The scorer is a double here, so every embedding request the service makes
    # is one the wants lookup asked for.
    assert embedder.calls == before


def test_only_the_current_anchors_answers_are_handed_over(
    client, panel, mock_scorer, mock_narrator, embedder
):
    _put(client, panel, [{"kind": "condition", "key": "people", "verdict": "more"}])

    _set_profile(
        {**PROFILE, "experience": [{"position": "Teacher", "endDate": "Present"}]}
    )
    embedder.vector = TEACHER_VEC
    ps._EMBED_CACHE.clear()

    _run_cold_job()

    assert _handed_wants(mock_scorer) is None


def test_the_cold_payload_carries_the_reasons_field(
    client, panel, mock_scorer, mock_narrator
):
    """Additive on the wire, present whether or not it has content."""
    body = _run_cold_job().body
    assert all("reasons" in card for card in body["suggestions"])


def test_the_rerank_payload_carries_the_reasons_field(
    client, panel, mock_scorer, mock_narrator
):
    resp = client.post(
        "/api/v1/me/path-feedback",
        json={"onet_code": SALES_CODE, "verdict": "interesting"},
        headers={"X-CSRF-TOKEN": panel},
    )
    assert all("reasons" in card for card in resp.get_json()["suggestions"])
