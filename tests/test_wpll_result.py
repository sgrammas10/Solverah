"""The LLM-backed wpll scoring, driven through the job pair.

Phase 3c deleted the synchronous ``POST /assessments/wpll/submissions``. The
LLM behaviour this file exercises -- the stubbed insight on success, the
rules-based fallback on a provider failure or a malformed reply -- is service
behaviour and is unchanged; it is now asserted through ``POST
/assessments/wpll/scoring-jobs`` and its poll. Under the suite's eager
execution the job runs inline, so the ``patch`` must wrap the enqueue (that is
where the provider call happens) and the first poll is terminal.
"""

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

_ENDPOINT = "/api/v1/assessments/wpll/scoring-jobs"


def _poll(client, job_id):
    return client.get("%s/%s" % (_ENDPOINT, job_id))


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

        queued = client.post(
            _ENDPOINT,
            data=json.dumps({"answers": VALID_ANSWERS}),
            content_type="application/json",
        )

    assert queued.status_code == 202
    res = _poll(client, queued.get_json()["job_id"])

    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "succeeded"
    result = body["result"]
    assert result["insight_text"] == expected
    assert isinstance(result["locked_sections"], list)
    assert len(result["locked_sections"]) == 3


def test_wpll_result_llm_exception_falls_back_to_rules(client):
    """A provider outage does not fail the job: the fallback is service behaviour.

    wpll's scorer swallows the exception and answers the rules-based insight,
    exactly as it did on the request path. A `failed` status here would mean
    the fallback was lost in the move to the queue.
    """
    with patch("solverah.infra.llm.get_openai_client") as mock_factory:
        mock_factory.side_effect = RuntimeError("simulated API outage")

        queued = client.post(
            _ENDPOINT,
            data=json.dumps({"answers": VALID_ANSWERS}),
            content_type="application/json",
        )

    assert queued.status_code == 202
    res = _poll(client, queued.get_json()["job_id"])

    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "succeeded"
    result = body["result"]
    assert isinstance(result["insight_text"], str) and len(result["insight_text"]) > 0
    assert isinstance(result["locked_sections"], list)


def test_wpll_result_malformed_llm_response_falls_back_to_rules(client):
    """A reply without `insight_text` is discarded, not served and not fatal.

    Same fallback as the outage case: the job succeeds with the rules-based
    result rather than failing on a key the model forgot.
    """
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({"summary": "wrong key"})
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    with patch("solverah.infra.llm.get_openai_client") as mock_factory:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_completion
        mock_factory.return_value = mock_client

        queued = client.post(
            _ENDPOINT,
            data=json.dumps({"answers": VALID_ANSWERS}),
            content_type="application/json",
        )

    assert queued.status_code == 202
    res = _poll(client, queued.get_json()["job_id"])

    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "succeeded"
    assert isinstance(body["result"]["insight_text"], str)
    assert len(body["result"]["insight_text"]) > 0


def test_wpll_result_missing_answers_returns_422(client):
    res = client.post(
        _ENDPOINT,
        data=json.dumps({}),
        content_type="application/json",
    )
    # `answers` is a required field of the declared schema, so this is refused
    # before the precheck runs -- 422 with the field named, not a bare 400.
    assert res.status_code == 422
    assert "answers" in {e["field"] for e in res.get_json()["errors"]}


def test_wpll_result_empty_answers_returns_400(client):
    # The precheck refuses at the enqueue; an empty sitting is not worth a job.
    res = client.post(
        _ENDPOINT,
        data=json.dumps({"answers": []}),
        content_type="application/json",
    )
    assert res.status_code == 400
