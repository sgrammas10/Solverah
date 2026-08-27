"""Tests for POST /api/work-pulse/lite-lite/result and the insight engine."""

import json
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


# ── Endpoint tests ──────────────────────────────────────────────────────────

def test_lite_lite_result_returns_insight_and_locked_sections(client):
    res = client.post(
        "/api/v1/assessments/wpll/submissions",
        data=json.dumps({"answers": VALID_ANSWERS}),
        content_type="application/json",
    )
    assert res.status_code == 200
    body = res.get_json()
    assert isinstance(body["insight_text"], str) and len(body["insight_text"]) > 0
    assert isinstance(body["locked_sections"], list)
    assert len(body["locked_sections"]) == 3
    assert all(isinstance(s, str) for s in body["locked_sections"])


def test_lite_lite_result_accepts_partial_answers(client):
    partial = VALID_ANSWERS[:3]
    res = client.post(
        "/api/v1/assessments/wpll/submissions",
        data=json.dumps({"answers": partial}),
        content_type="application/json",
    )
    assert res.status_code == 200
    body = res.get_json()
    assert isinstance(body["insight_text"], str) and len(body["insight_text"]) > 0


def test_lite_lite_result_empty_answers_returns_400(client):
    res = client.post(
        "/api/v1/assessments/wpll/submissions",
        data=json.dumps({"answers": []}),
        content_type="application/json",
    )
    assert res.status_code == 400


def test_lite_lite_result_rejects_too_many_answers(client):
    too_many = VALID_ANSWERS + [{"question_id": "wpll-q1", "option_id": "wpll-q1-a"}]
    res = client.post(
        "/api/v1/assessments/wpll/submissions",
        data=json.dumps({"answers": too_many}),
        content_type="application/json",
    )
    assert res.status_code == 400


def test_lite_lite_result_rejects_non_list_answers(client):
    """A wrong-typed field is refused by the schema, not by the handler.

    422 rather than the 400 the handler used to answer with. Pydantic coerces
    what is coercible -- "12" becomes 12 -- but a string is not a list of
    answers under any reading, so this is a genuine rejection.
    """
    res = client.post(
        "/api/v1/assessments/wpll/submissions",
        data=json.dumps({"answers": "not a list"}),
        content_type="application/json",
    )
    assert res.status_code == 422
    assert "answers" in {error["field"] for error in res.get_json()["errors"]}


def test_lite_lite_result_does_not_require_auth(client):
    res = client.post(
        "/api/v1/assessments/wpll/submissions",
        data=json.dumps({"answers": VALID_ANSWERS}),
        content_type="application/json",
    )
    assert res.status_code == 200


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
