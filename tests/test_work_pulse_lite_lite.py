"""WPLL scoring through the job pair, and unit tests for the insight engine.

Phase 3c deleted the synchronous ``POST /assessments/wpll/submissions``: it
answers 410 with a pointer at ``POST /assessments/wpll/scoring-jobs``, and
``test_the_synchronous_submit_is_a_410_tombstone`` is the test of that
deletion. The endpoint coverage drives the enqueue and the poll -- with no JWT
and no CSRF, because wpll is the anonymous pre-launch instrument. Under the
suite's eager execution the job runs inline, so the first poll is terminal.
"""

import pytest

from work_pulse.insight_engine import (
    INSIGHT_TEMPLATES,
    score_answers,
    select_template,
)

VALID_ANSWERS = [
    {"question_id": "wpll-q1", "option_id": "wpll-q1-c"},  # fragmentation = 2
    {"question_id": "wpll-q2", "option_id": "wpll-q2-d"},  # sustainability = 3
    {"question_id": "wpll-q3", "option_id": "wpll-q3-a"},  # environmental_friction = 0
    {"question_id": "wpll-q4", "option_id": "wpll-q4-b"},  # recognition_friction = 1
    {"question_id": "wpll-q5", "option_id": "wpll-q5-a"},  # work_pace = 0
]


def _queue(client, body):
    return client.post("/api/v1/assessments/wpll/scoring-jobs", json=body)


def _poll(client, job_id):
    return client.get("/api/v1/assessments/wpll/scoring-jobs/%s" % job_id)


def _score(client, answers):
    """Queue a scoring and poll it once -- terminal under eager execution."""
    queued = _queue(client, {"answers": answers})
    assert queued.status_code == 202
    return _poll(client, queued.get_json()["job_id"])


# ── Endpoint tests ──────────────────────────────────────────────────────────

def test_lite_lite_result_returns_insight_and_locked_sections(client):
    poll = _score(client, VALID_ANSWERS)

    assert poll.status_code == 200
    assert poll.get_json()["status"] == "succeeded"
    result = poll.get_json()["result"]
    assert isinstance(result["insight_text"], str) and len(result["insight_text"]) > 0
    assert isinstance(result["locked_sections"], list)
    assert len(result["locked_sections"]) == 3
    assert all(isinstance(s, str) for s in result["locked_sections"])


def test_lite_lite_result_accepts_partial_answers(client):
    poll = _score(client, VALID_ANSWERS[:3])

    assert poll.get_json()["status"] == "succeeded"
    result = poll.get_json()["result"]
    assert isinstance(result["insight_text"], str) and len(result["insight_text"]) > 0


def test_lite_lite_result_empty_answers_returns_400(client):
    """The precheck refuses at the enqueue -- a bad body is not worth a job."""
    res = _queue(client, {"answers": []})
    assert res.status_code == 400


def test_lite_lite_result_rejects_too_many_answers(client):
    too_many = VALID_ANSWERS + [{"question_id": "wpll-q1", "option_id": "wpll-q1-a"}]
    res = _queue(client, {"answers": too_many})
    assert res.status_code == 400


def test_lite_lite_result_rejects_non_list_answers(client):
    """A wrong-typed field is refused by the schema, not by the precheck.

    422 rather than 400, on the job door exactly as on the old one. Pydantic
    coerces what is coercible -- "12" becomes 12 -- but a string is not a list
    of answers under any reading, so this is a genuine rejection.
    """
    res = _queue(client, {"answers": "not a list"})
    assert res.status_code == 422
    assert "answers" in {error["field"] for error in res.get_json()["errors"]}


def test_lite_lite_result_does_not_require_auth(client):
    """The whole flow -- enqueue and poll -- with no cookies at all.

    wpll is the pre-launch teaser and has no account to attach to, so the job
    handle is the whole of the authorisation.
    """
    poll = _score(client, VALID_ANSWERS)

    assert poll.status_code == 200
    assert poll.get_json()["status"] == "succeeded"


def test_the_synchronous_submit_is_a_410_tombstone(client):
    """This is the test of the deletion.

    A 404 would lie -- the kind exists, and the operation existed until Phase
    3c deleted the synchronous half. A 200 would be worse: it would resurrect
    the blocking provider call Phase 3 removed. wpll never required auth, so
    the point here is that the anonymous caller gets the 410 and the
    forwarding address too, not a route that quietly still scores.
    """
    res = client.post(
        "/api/v1/assessments/wpll/submissions", json={"answers": VALID_ANSWERS}
    )

    assert res.status_code == 410
    assert res.mimetype == "application/problem+json"
    body = res.get_json()
    assert body["type"] == "https://solverah.com/errors/gone"
    assert body["title"] == "Gone"
    assert body["replaced_by"] == "/assessments/wpll/scoring-jobs"
    assert body["errors"][0]["code"] == "moved_to_scoring_jobs"


# ── Unit tests for the engine ───────────────────────────────────────────────

def test_score_answers_maps_options_to_scores():
    answers = [
        {"question_id": "wpll-q1", "option_id": "wpll-q1-c"},  # fragmentation = 2
        {"question_id": "wpll-q2", "option_id": "wpll-q2-d"},  # sustainability = 3
    ]
    scores = score_answers(answers)
    assert scores["fragmentation"] == 2
    assert scores["sustainability"] == 3
    assert scores["environmental_friction"] == 0  # defaulted


def test_select_template_single_dominant():
    scores = {
        "fragmentation": 3,
        "sustainability": 1,
        "environmental_friction": 0,
        "recognition_friction": 0,
        "work_pace": 1,
    }
    assert select_template(scores) == "fragmentation"


def test_select_template_dual_combo():
    scores = {
        "fragmentation": 3,
        "sustainability": 2,
        "environmental_friction": 0,
        "recognition_friction": 0,
        "work_pace": 0,
    }
    assert select_template(scores) == "fragmentation+sustainability"


def test_select_template_broad_overload():
    scores = {
        "fragmentation": 3,
        "sustainability": 3,
        "environmental_friction": 2,
        "recognition_friction": 2,
        "work_pace": 1,
    }
    assert select_template(scores) == "broad_overload"


def test_select_template_all_low():
    scores = {
        "fragmentation": 1,
        "sustainability": 1,
        "environmental_friction": 0,
        "recognition_friction": 1,
        "work_pace": 0,
    }
    assert select_template(scores) == "all_low"


def test_all_template_keys_have_text():
    for key, text in INSIGHT_TEMPLATES.items():
        assert isinstance(text, str) and len(text) > 50, f"Template '{key}' is too short"
