"""Tests for backend.services.onet_client.

All HTTP calls are mocked so these tests never hit the live O*NET API.
Mock response shapes mirror the O*NET v1.9 REST API JSON format.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from backend.services.onet_client import (
    Occupation,
    OnetAPIError,
    OnetClient,
    OnetRateLimitError,
    Skill,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Return a mock requests.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    if status_code >= 400:
        mock.raise_for_status.side_effect = requests.HTTPError(
            response=mock
        )
    else:
        mock.raise_for_status.return_value = None
    return mock


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> OnetClient:
    monkeypatch.setenv("ONET_API_KEY", "test-key")
    return OnetClient()


# ---------------------------------------------------------------------------
# OnetClient initialisation
# ---------------------------------------------------------------------------


class TestOnetClientInit:
    def test_raises_when_api_key_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ONET_API_KEY", raising=False)
        with pytest.raises(ValueError, match="ONET_API_KEY"):
            OnetClient()

    def test_accepts_explicit_api_key(self) -> None:
        c = OnetClient(api_key="explicit-key")
        assert c._session.headers["X-API-Key"] == "explicit-key"


# ---------------------------------------------------------------------------
# search_occupations
# ---------------------------------------------------------------------------


class TestSearchOccupations:
    _RESPONSE = {
        "keyword": "software developer",
        "start": 1,
        "end": 2,
        "total": 2,
        "occupation": [
            {"href": "https://example.com/1", "code": "15-1252.00", "title": "Software Developers"},
            {"href": "https://example.com/2", "code": "15-1253.00", "title": "Software Quality Assurance Analysts and Testers"},
        ],
    }

    def test_returns_occupation_list(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response(self._RESPONSE)):
            results = client.search_occupations("software developer")

        assert len(results) == 2
        assert results[0] == Occupation(code="15-1252.00", title="Software Developers")
        assert results[1] == Occupation(code="15-1253.00", title="Software Quality Assurance Analysts and Testers")

    def test_passes_keyword_param(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response(self._RESPONSE)) as mock_get:
            client.search_occupations("nurse")

        _url, kwargs = mock_get.call_args[0], mock_get.call_args[1]
        assert mock_get.call_args.kwargs.get("params", {}).get("keyword") == "nurse" or \
               mock_get.call_args[1].get("params", {}).get("keyword") == "nurse"

    def test_returns_empty_list_when_no_results(self, client: OnetClient) -> None:
        empty = {"keyword": "xyznonexistent", "start": 1, "end": 0, "total": 0}
        with patch.object(client._session, "get", return_value=_mock_response(empty)):
            results = client.search_occupations("xyznonexistent")

        assert results == []

    def test_raises_on_rate_limit_after_all_retries(
        self, client: OnetClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("backend.services.onet_client.time.sleep", lambda _: None)
        with patch.object(client._session, "get", return_value=_mock_response({}, status_code=429)):
            with pytest.raises(OnetRateLimitError):
                client.search_occupations("anything")

    def test_retries_on_rate_limit_then_succeeds(
        self, client: OnetClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("backend.services.onet_client.time.sleep", lambda _: None)
        rate_limited = _mock_response({}, status_code=429)
        ok = _mock_response(self._RESPONSE)

        with patch.object(client._session, "get", side_effect=[rate_limited, ok]):
            results = client.search_occupations("software developer")

        assert len(results) == 2

    def test_raises_onet_api_error_on_http_error(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response({}, status_code=500)):
            with pytest.raises(OnetAPIError):
                client.search_occupations("software developer")


# ---------------------------------------------------------------------------
# get_skills_profile
# ---------------------------------------------------------------------------


class TestGetSkillsProfile:
    _RESPONSE = {
        "occupation": {"href": "...", "code": "15-1252.00", "title": "Software Developers"},
        "element": [
            {
                "id": "2.A.1.a",
                "name": "Reading Comprehension",
                "score": {
                    "importance": {"value": 72.22},
                    "level": {"value": 4.25},
                },
            },
            {
                "id": "2.A.1.b",
                "name": "Active Listening",
                "score": {
                    "importance": {"value": 68.0},
                    "level": {"value": 3.75},
                },
            },
        ],
    }

    def test_returns_skill_list(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response(self._RESPONSE)):
            skills = client.get_skills_profile("15-1252.00")

        assert len(skills) == 2
        assert skills[0] == Skill(
            element_id="2.A.1.a",
            name="Reading Comprehension",
            importance=72.22,
            level=4.25,
        )

    def test_scores_are_floats(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response(self._RESPONSE)):
            skills = client.get_skills_profile("15-1252.00")

        assert isinstance(skills[0].importance, float)
        assert isinstance(skills[0].level, float)

    def test_missing_scores_default_to_zero(self, client: OnetClient) -> None:
        no_scores = {
            "occupation": {"code": "15-1252.00", "title": "Software Developers"},
            "element": [{"id": "2.A.1.a", "name": "Reading Comprehension", "score": {}}],
        }
        with patch.object(client._session, "get", return_value=_mock_response(no_scores)):
            skills = client.get_skills_profile("15-1252.00")

        assert skills[0].importance == 0.0
        assert skills[0].level == 0.0

    def test_empty_occupation_returns_empty_list(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response({"element": []})):
            assert client.get_skills_profile("15-1252.00") == []

    def test_raises_on_rate_limit(
        self, client: OnetClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("backend.services.onet_client.time.sleep", lambda _: None)
        with patch.object(client._session, "get", return_value=_mock_response({}, status_code=429)):
            with pytest.raises(OnetRateLimitError):
                client.get_skills_profile("15-1252.00")


# ---------------------------------------------------------------------------
# get_job_zone
# ---------------------------------------------------------------------------


class TestGetJobZone:
    _RESPONSE = {
        "code": 4,
        "title": "Job Zone Four: Considerable Preparation Needed",
    }

    def test_returns_integer_job_zone(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response(self._RESPONSE)):
            zone = client.get_job_zone("15-1252.00")

        assert zone == 4
        assert isinstance(zone, int)

    def test_job_zone_boundaries(self, client: OnetClient) -> None:
        for expected in (1, 2, 3, 4, 5):
            resp = {"code": expected, "title": "..."}
            with patch.object(client._session, "get", return_value=_mock_response(resp)):
                assert client.get_job_zone("15-1252.00") == expected

    def test_raises_on_rate_limit(
        self, client: OnetClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("backend.services.onet_client.time.sleep", lambda _: None)
        with patch.object(client._session, "get", return_value=_mock_response({}, status_code=429)):
            with pytest.raises(OnetRateLimitError):
                client.get_job_zone("15-1252.00")

    def test_raises_onet_api_error_on_404(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response({}, status_code=404)):
            with pytest.raises(OnetAPIError):
                client.get_job_zone("00-0000.00")
