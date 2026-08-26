"""Tests for the LLM-backed POST /api/work-pulse/lite-lite/result endpoint."""

import json
import pytest
from unittest.mock import MagicMock, patch

VALID_ANSWERS = [
    {"question_id": "wpll-q1", "option_id": "wpll-q1-c"},
    {"question_id": "wpll-q2", "option_id": "wpll-q2-d"},
    {"question_id": "wpll-q3", "option_id": "wpll-q3-a"},
    {"question_id": "wpll-q4", "option_id": "wpll-q4-b"},
    {"question_id": "wpll-q5", "option_id": "wpll-q5-a"},
]

_ENDPOINT = "/api/work-pulse/lite-lite/result"


def _mock_openai_completion(insight_text: str):
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({"insight_text": insight_text})
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    return mock_completion


def test_wpll_result_llm_happy_path(client):
    expected = "Your responses show a fragmented work pattern with real sustainability costs. You're carrying more than the role probably acknowledges."
    completion = _mock_openai_completion(expected)

    with patch("solverah.infra.llm.get_openai_client") as mock_factory:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = completion
        mock_factory.return_value = mock_client

        res = client.post(
            _ENDPOINT,
            data=json.dumps({"answers": VALID_ANSWERS}),
            content_type="application/json",
        )

    assert res.status_code == 200
    body = res.get_json()
    assert body["insight_text"] == expected
    assert isinstance(body["locked_sections"], list)
    assert len(body["locked_sections"]) == 3


def test_wpll_result_llm_exception_falls_back_to_rules(client):
    with patch("solverah.infra.llm.get_openai_client") as mock_factory:
        mock_factory.side_effect = RuntimeError("simulated API outage")

        res = client.post(
            _ENDPOINT,
            data=json.dumps({"answers": VALID_ANSWERS}),
            content_type="application/json",
        )

    assert res.status_code == 200
    body = res.get_json()
    assert isinstance(body["insight_text"], str) and len(body["insight_text"]) > 0
    assert isinstance(body["locked_sections"], list)


def test_wpll_result_malformed_llm_response_falls_back_to_rules(client):
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({"summary": "wrong key"})
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    with patch("solverah.infra.llm.get_openai_client") as mock_factory:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        mock_factory.return_value = mock_client

        res = client.post(
            _ENDPOINT,
            data=json.dumps({"answers": VALID_ANSWERS}),
            content_type="application/json",
        )

    assert res.status_code == 200
    body = res.get_json()
    assert isinstance(body["insight_text"], str) and len(body["insight_text"]) > 0


def test_wpll_result_missing_answers_returns_400(client):
    res = client.post(
        _ENDPOINT,
        data=json.dumps({}),
        content_type="application/json",
    )
    assert res.status_code == 400


def test_wpll_result_empty_answers_returns_400(client):
    res = client.post(
        _ENDPOINT,
        data=json.dumps({"answers": []}),
        content_type="application/json",
    )
    assert res.status_code == 400
