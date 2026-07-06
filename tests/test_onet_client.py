"""Tests for backend.services.onet_client.

All HTTP calls are mocked so these tests never hit the live O*NET API.
Mock response shapes mirror the O*NET v1.9 REST API JSON format.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest
import requests

import backend.services.onet_client as onet_module
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


@pytest.fixture(autouse=True)
def _clear_occ_cache():
    """_OCC_CACHE is module-level (shared across every OnetClient instance,
    by design — see onet_client.py) so it must be cleared between tests or
    one test's mocked response leaks into the next test's assertions.
    """
    onet_module._OCC_CACHE.clear()
    yield
    onet_module._OCC_CACHE.clear()


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
    # v2 flat format: each element has a top-level "importance" int (0-100).
    # The "level" (LV) scale is not exposed by this endpoint so it is always 0.0.
    _RESPONSE = {
        "occupation": {"href": "...", "code": "15-1252.00", "title": "Software Developers"},
        "element": [
            {"id": "2.A.1.a", "name": "Reading Comprehension", "importance": 72},
            {"id": "2.A.1.b", "name": "Active Listening", "importance": 68},
        ],
    }

    def test_returns_skill_list(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response(self._RESPONSE)):
            skills = client.get_skills_profile("15-1252.00")

        assert len(skills) == 2
        assert skills[0] == Skill(
            element_id="2.A.1.a",
            name="Reading Comprehension",
            importance=72.0,
            level=0.0,
        )

    def test_scores_are_floats(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response(self._RESPONSE)):
            skills = client.get_skills_profile("15-1252.00")

        assert isinstance(skills[0].importance, float)
        assert isinstance(skills[0].level, float)

    def test_missing_importance_defaults_to_zero(self, client: OnetClient) -> None:
        no_importance = {
            "element": [{"id": "2.A.1.a", "name": "Reading Comprehension"}],
        }
        with patch.object(client._session, "get", return_value=_mock_response(no_importance)):
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
        # Distinct onet_code per iteration — get_job_zone results are now cached
        # per-code, so reusing one code across differing mocked responses would
        # just return the first cached value on every later iteration.
        for expected in (1, 2, 3, 4, 5):
            resp = {"code": expected, "title": "..."}
            with patch.object(client._session, "get", return_value=_mock_response(resp)):
                assert client.get_job_zone(f"15-125{expected}.00") == expected

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


# ---------------------------------------------------------------------------
# get_tech_skills
# ---------------------------------------------------------------------------


class TestGetTechSkills:
    _RESPONSE = {
        "occupation": {"href": "...", "code": "15-1252.00", "title": "Software Developers"},
        "category": [
            {
                "title": "Programming Languages",
                "example": [
                    {"title": "Python"},
                    {"title": "JavaScript"},
                ],
                "example_more": [],
            },
            {
                "title": "Frameworks",
                "example": [],
                "example_more": [
                    {"title": "React"},
                ],
            },
        ],
    }

    def test_returns_lowercased_set(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response(self._RESPONSE)):
            names = client.get_tech_skills("15-1252.00")

        assert names == {"python", "javascript", "react"}

    def test_returns_set_type(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response(self._RESPONSE)):
            names = client.get_tech_skills("15-1252.00")

        assert isinstance(names, set)

    def test_empty_category_returns_empty_set(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response({"category": []})):
            assert client.get_tech_skills("15-1252.00") == set()

    def test_missing_category_key_returns_empty_set(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response({})):
            assert client.get_tech_skills("15-1252.00") == set()

    def test_raises_on_rate_limit(
        self, client: OnetClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("backend.services.onet_client.time.sleep", lambda _: None)
        with patch.object(client._session, "get", return_value=_mock_response({}, status_code=429)):
            with pytest.raises(OnetRateLimitError):
                client.get_tech_skills("15-1252.00")


# ---------------------------------------------------------------------------
# Occupation-level cache (get_job_zone / get_skills_profile / get_tech_skills /
# get_work_activities) — shared module-level cache, see _OCC_CACHE.
# ---------------------------------------------------------------------------


class TestOccupationCache:
    def test_get_job_zone_cache_hit_avoids_second_fetch(self, client: OnetClient) -> None:
        with patch.object(
            client._session, "get", return_value=_mock_response({"code": 4, "title": "..."})
        ) as mock_get:
            assert client.get_job_zone("15-9001.00") == 4
            assert client.get_job_zone("15-9001.00") == 4

        assert mock_get.call_count == 1

    def test_get_skills_profile_cache_hit_avoids_second_fetch(self, client: OnetClient) -> None:
        resp = {"element": [{"id": "2.A.1.a", "name": "Reading Comprehension", "importance": 72}]}
        with patch.object(client._session, "get", return_value=_mock_response(resp)) as mock_get:
            first = client.get_skills_profile("15-9002.00")
            second = client.get_skills_profile("15-9002.00")

        assert mock_get.call_count == 1
        assert first == second

    def test_get_tech_skills_cache_hit_avoids_second_fetch(self, client: OnetClient) -> None:
        resp = {"category": [{"example": [{"title": "Python"}], "example_more": []}]}
        with patch.object(client._session, "get", return_value=_mock_response(resp)) as mock_get:
            first = client.get_tech_skills("15-9003.00")
            second = client.get_tech_skills("15-9003.00")

        assert mock_get.call_count == 1
        assert first == second == {"python"}

    def test_get_tech_skills_hot_only_variants_cached_separately(self, client: OnetClient) -> None:
        """hot_only=True/False must not share a cache entry — different results."""
        resp = {
            "category": [{
                "example": [
                    {"title": "Python", "hot_technology": True},
                    {"title": "COBOL", "hot_technology": False},
                ],
                "example_more": [],
            }]
        }
        with patch.object(client._session, "get", return_value=_mock_response(resp)) as mock_get:
            hot_only = client.get_tech_skills("15-9004.00", hot_only=True)
            all_tools = client.get_tech_skills("15-9004.00", hot_only=False)

        assert hot_only == {"python"}
        assert all_tools == {"python", "cobol"}
        assert mock_get.call_count == 2

    def test_get_work_activities_cache_hit_avoids_second_fetch(self, client: OnetClient) -> None:
        resp = {"element": [{"id": "4.A.1.a", "name": "Getting Information", "importance": 80}]}
        with patch.object(client._session, "get", return_value=_mock_response(resp)) as mock_get:
            first = client.get_work_activities("15-9005.00")
            second = client.get_work_activities("15-9005.00")

        assert mock_get.call_count == 1
        assert first == second

    def test_cached_list_and_set_values_are_not_shared_by_reference(self, client: OnetClient) -> None:
        """Mutating one caller's result must not corrupt what later callers get back."""
        skills_resp = {"element": [{"id": "2.A.1.a", "name": "Reading Comprehension", "importance": 72}]}
        with patch.object(client._session, "get", return_value=_mock_response(skills_resp)):
            first = client.get_skills_profile("15-9006.00")
            first.append(Skill(element_id="x", name="Injected", importance=1.0, level=0.0))
            second = client.get_skills_profile("15-9006.00")

        assert len(second) == 1

        tech_resp = {"category": [{"example": [{"title": "Python"}], "example_more": []}]}
        with patch.object(client._session, "get", return_value=_mock_response(tech_resp)):
            first_set = client.get_tech_skills("15-9007.00")
            first_set.add("injected")
            second_set = client.get_tech_skills("15-9007.00")

        assert second_set == {"python"}

    def test_cache_is_thread_safe_under_concurrent_access(self, client: OnetClient) -> None:
        """Many threads racing on a cold cache entry must all get the correct value,
        without corruption, and settle into a cache hit afterwards. A cold cache may
        allow a handful of duplicate live fetches (see onet_client._occ_cache_get/_set
        docstrings) — this asserts a loose upper bound, not a strict single-fetch
        guarantee, matching that documented tradeoff.
        """
        call_count = {"n": 0}

        def _slow_get(*args, **kwargs):
            call_count["n"] += 1
            time.sleep(0.01)  # widen the race window
            return _mock_response({"code": 3, "title": "..."})

        with patch.object(client._session, "get", side_effect=_slow_get):
            with ThreadPoolExecutor(max_workers=10) as executor:
                results = list(executor.map(
                    lambda _: client.get_job_zone("15-9008.00"), range(10)
                ))

            assert all(r == 3 for r in results)
            assert call_count["n"] <= 10  # bounded duplicate-fetch window, not exactly 1

            # Cache is now warm — a subsequent call must be a guaranteed hit.
            before = call_count["n"]
            assert client.get_job_zone("15-9008.00") == 3
            assert call_count["n"] == before
