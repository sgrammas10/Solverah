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
    Task,
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


@pytest.fixture(autouse=True)
def _clear_bright_outlook_cache():
    """Same rationale as _clear_occ_cache, for the separate Bright Outlook cache."""
    onet_module._BRIGHT_OUTLOOK_CACHE = []
    onet_module._BRIGHT_OUTLOOK_CACHE_TS = 0.0
    yield
    onet_module._BRIGHT_OUTLOOK_CACHE = []
    onet_module._BRIGHT_OUTLOOK_CACHE_TS = 0.0


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


# ---------------------------------------------------------------------------
# get_bright_outlook_occupations
# ---------------------------------------------------------------------------


class TestGetBrightOutlookOccupations:
    """Regression coverage for a live-only bug: GET /online/bright_outlook

    returns a bare JSON array of {href, code, title} — not an object with a
    "bright_outlook_category" key. The old code called categories_data.get(...)
    on that array and crashed with AttributeError (not OnetAPIError, so the
    existing stale-cache fallback never caught it) the first time a real user
    exercised the fresh_start / new-field flow. Confirmed against the live v2
    API before fixing. These response shapes mirror what was actually observed.
    """

    _CATEGORIES = [
        {"href": "https://api-v2.onetcenter.org/online/bright_outlook/grow", "code": "grow", "title": "Rapid Growth"},
        {"href": "https://api-v2.onetcenter.org/online/bright_outlook/openings", "code": "openings", "title": "Numerous Openings"},
        # Live response also includes this meta-entry with no "code" key at all —
        # must be skipped, not looped over as a 3rd category.
        {"href": "https://api-v2.onetcenter.org/online/bright_outlook/all", "title": "All Bright Outlook Occupations"},
    ]

    @staticmethod
    def _category_response(occupations: list[dict]) -> dict:
        return {"start": 1, "end": 100, "total": len(occupations), "occupation": occupations}

    def test_parses_bare_array_category_response(self, client: OnetClient) -> None:
        """The exact shape that used to crash: a bare list, not {"bright_outlook_category": [...]}."""
        responses = [
            _mock_response(self._CATEGORIES),
            _mock_response(self._category_response([
                {"code": "13-2011.00", "title": "Accountants and Auditors"},
            ])),
            _mock_response(self._category_response([
                {"code": "15-1252.00", "title": "Software Developers"},
            ])),
        ]
        with patch.object(client._session, "get", side_effect=responses):
            result = client.get_bright_outlook_occupations()

        assert {o.code for o in result} == {"13-2011.00", "15-1252.00"}

    def test_deduplicates_across_categories(self, client: OnetClient) -> None:
        responses = [
            _mock_response(self._CATEGORIES),
            _mock_response(self._category_response([
                {"code": "13-2011.00", "title": "Accountants and Auditors"},
            ])),
            _mock_response(self._category_response([
                {"code": "13-2011.00", "title": "Accountants and Auditors"},  # same occupation, other category
            ])),
        ]
        with patch.object(client._session, "get", side_effect=responses):
            result = client.get_bright_outlook_occupations()

        assert [o.code for o in result].count("13-2011.00") == 1

    def test_requests_up_to_100_per_category(self, client: OnetClient) -> None:
        """Categories can hold 300+ occupations; the API defaults to a 20-item
        page, so each per-category call must explicitly request end=100."""
        responses = [
            _mock_response(self._CATEGORIES),
            _mock_response(self._category_response([])),
            _mock_response(self._category_response([])),
        ]
        with patch.object(client._session, "get", side_effect=responses) as mock_get:
            client.get_bright_outlook_occupations()

        category_calls = mock_get.call_args_list[1:]
        assert all(call.kwargs.get("params", {}).get("end") == 100 for call in category_calls)

    def test_api_error_falls_back_to_stale_cache(self, client: OnetClient) -> None:
        onet_module._BRIGHT_OUTLOOK_CACHE = [Occupation(code="15-1252.00", title="Software Developers")]
        onet_module._BRIGHT_OUTLOOK_CACHE_TS = 0.0  # expired, forces a re-fetch attempt

        with patch.object(client._session, "get", return_value=_mock_response({}, status_code=500)):
            result = client.get_bright_outlook_occupations()

        assert result == [Occupation(code="15-1252.00", title="Software Developers")]

    def test_cache_hit_avoids_second_fetch(self, client: OnetClient) -> None:
        responses = [
            _mock_response(self._CATEGORIES),
            _mock_response(self._category_response([{"code": "13-2011.00", "title": "Accountants"}])),
            _mock_response(self._category_response([{"code": "15-1252.00", "title": "SW Dev"}])),
        ]
        with patch.object(client._session, "get", side_effect=responses) as mock_get:
            first = client.get_bright_outlook_occupations()
            second = client.get_bright_outlook_occupations()

        assert first == second
        assert mock_get.call_count == 3  # not re-fetched on the second call


# ---------------------------------------------------------------------------
# get_occupation_description  (corpus builder, BUILD_PLAN F-1)
# ---------------------------------------------------------------------------


class TestGetOccupationDescription:
    _RESPONSE = {
        "code": "15-2051.00",
        "title": "Data Scientists",
        "description": (
            "Develop and implement a set of techniques or analytics applications to "
            "transform raw data into meaningful information."
        ),
        "tags": {"bright_outlook": True},
    }

    def test_returns_description_text(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response(self._RESPONSE)):
            description = client.get_occupation_description("15-2051.00")

        assert description.startswith("Develop and implement a set of techniques")

    def test_hits_the_occupation_root_endpoint(self, client: OnetClient) -> None:
        with patch.object(
            client._session, "get", return_value=_mock_response(self._RESPONSE)
        ) as mock_get:
            client.get_occupation_description("15-2051.00")

        assert mock_get.call_args[0][0].endswith("/online/occupations/15-2051.00")

    def test_missing_description_returns_empty_string(self, client: OnetClient) -> None:
        """A blank field degrades a role document; it must not raise and lose
        the occupation from the corpus entirely."""
        with patch.object(
            client._session,
            "get",
            return_value=_mock_response({"code": "55-1011.00", "title": "Air Crew Officers"}),
        ):
            assert client.get_occupation_description("55-1011.00") == ""

    def test_result_is_cached(self, client: OnetClient) -> None:
        with patch.object(
            client._session, "get", return_value=_mock_response(self._RESPONSE)
        ) as mock_get:
            first = client.get_occupation_description("15-2051.00")
            second = client.get_occupation_description("15-2051.00")

        assert first == second
        assert mock_get.call_count == 1

    def test_raises_on_api_error(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response({}, status_code=500)):
            with pytest.raises(OnetAPIError):
                client.get_occupation_description("15-2051.00")

    def test_raises_on_rate_limit(
        self, client: OnetClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("backend.services.onet_client.time.sleep", lambda _: None)
        with patch.object(client._session, "get", return_value=_mock_response({}, status_code=429)):
            with pytest.raises(OnetRateLimitError):
                client.get_occupation_description("15-2051.00")


# ---------------------------------------------------------------------------
# get_tasks  (corpus builder, BUILD_PLAN F-1)
# ---------------------------------------------------------------------------


class TestGetTasks:
    _RESPONSE = {
        "start": 1,
        "end": 3,
        "total": 3,
        "task": [
            {
                "id": "21828",
                "title": "Create graphs, charts, or other visualizations.",
                "importance": 71,
                "category": "Core",
            },
            {
                "id": "21823",
                "title": "Analyze, manipulate, or process large sets of data.",
                "importance": 83,
                "category": "Core",
            },
            {
                "id": "21840",
                "title": "Read scientific articles.",
                "importance": 42,
                "category": "Supplemental",
            },
        ],
    }

    def test_returns_tasks_sorted_by_importance_descending(self, client: OnetClient) -> None:
        """O*NET happens to return them ranked, but that is its choice, not a
        contract -- "top N tasks" must mean the same thing regardless."""
        with patch.object(client._session, "get", return_value=_mock_response(self._RESPONSE)):
            tasks = client.get_tasks("15-2051.00")

        assert [t.importance for t in tasks] == [83.0, 71.0, 42.0]
        assert tasks[0] == Task(
            task_id="21823",
            title="Analyze, manipulate, or process large sets of data.",
            importance=83.0,
            category="Core",
        )

    def test_uses_details_endpoint_for_importance_and_category(self, client: OnetClient) -> None:
        """/summary/tasks costs the same one request but omits both fields."""
        with patch.object(
            client._session, "get", return_value=_mock_response(self._RESPONSE)
        ) as mock_get:
            tasks = client.get_tasks("15-2051.00")

        assert mock_get.call_args[0][0].endswith("/details/tasks")
        assert mock_get.call_args.kwargs.get("params", {}).get("end") == 100
        assert tasks[2].category == "Supplemental"

    def test_falls_back_to_sub_code_when_umbrella_is_empty(self, client: OnetClient) -> None:
        responses = [
            _mock_response({"task": []}),
            _mock_response(self._RESPONSE),
        ]
        with patch.object(client._session, "get", side_effect=responses) as mock_get:
            tasks = client.get_tasks("15-2051.00")

        assert len(tasks) == 3
        assert mock_get.call_args_list[1][0][0].endswith(
            "/online/occupations/15-2051.01/details/tasks"
        )

    def test_missing_sub_code_returns_empty_instead_of_raising(self, client: OnetClient) -> None:
        """Regression: 74 of the catalog's 1,016 occupations have no task data
        -- all 19 of the 55-0000 Military Specific family plus the "..., All
        Other" residual codes -- and many of those have no .01 sub-code, so the
        fallback 404s.  A task-less occupation is a thinner role document, not a
        failed fetch; letting the 404 propagate would drop all 74 occupations
        from the corpus."""
        responses = [
            _mock_response({"task": []}),
            _mock_response({}, status_code=404),
        ]
        with patch.object(client._session, "get", side_effect=responses):
            assert client.get_tasks("55-1011.00") == []

    def test_missing_fields_default_safely(self, client: OnetClient) -> None:
        with patch.object(
            client._session,
            "get",
            return_value=_mock_response({"task": [{"title": "Do the thing."}]}),
        ):
            tasks = client.get_tasks("15-2051.00")

        assert tasks[0] == Task(task_id="", title="Do the thing.", importance=0.0, category="")

    def test_result_is_cached(self, client: OnetClient) -> None:
        with patch.object(
            client._session, "get", return_value=_mock_response(self._RESPONSE)
        ) as mock_get:
            client.get_tasks("15-2051.00")
            client.get_tasks("15-2051.00")

        assert mock_get.call_count == 1

    def test_cached_list_is_copied(self, client: OnetClient) -> None:
        """Callers must not be able to corrupt every later cache hit."""
        with patch.object(client._session, "get", return_value=_mock_response(self._RESPONSE)):
            first = client.get_tasks("15-2051.00")
            first.clear()
            second = client.get_tasks("15-2051.00")

        assert len(second) == 3

    def test_raises_on_rate_limit(
        self, client: OnetClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("backend.services.onet_client.time.sleep", lambda _: None)
        with patch.object(client._session, "get", return_value=_mock_response({}, status_code=429)):
            with pytest.raises(OnetRateLimitError):
                client.get_tasks("15-2051.00")


# ---------------------------------------------------------------------------
# get_hot_technologies  (corpus builder, BUILD_PLAN F-1)
# ---------------------------------------------------------------------------


class TestGetHotTechnologies:
    _RESPONSE = {
        "start": 1,
        "end": 3,
        "total": 3,
        "example": [
            {"title": "Python", "hot_technology": True, "in_demand": True, "percentage": 66},
            {
                "title": "Structured query language SQL",
                "hot_technology": True,
                "in_demand": True,
                "percentage": 51,
            },
            {"title": "R", "hot_technology": True, "in_demand": True, "percentage": 34},
        ],
    }

    def test_preserves_demand_order_and_capitalisation(self, client: OnetClient) -> None:
        """The whole reason this exists rather than get_tech_skills(hot_only=True),
        which returns an unordered set of lower-cased names."""
        with patch.object(client._session, "get", return_value=_mock_response(self._RESPONSE)):
            names = client.get_hot_technologies("15-2051.00")

        assert names == ["Python", "Structured query language SQL", "R"]

    def test_hits_the_hot_technology_endpoint(self, client: OnetClient) -> None:
        with patch.object(
            client._session, "get", return_value=_mock_response(self._RESPONSE)
        ) as mock_get:
            client.get_hot_technologies("15-2051.00")

        assert mock_get.call_args[0][0].endswith("/online/occupations/15-2051.00/hot_technology")
        assert mock_get.call_args.kwargs.get("params", {}).get("end") == 100

    def test_no_hot_technologies_returns_empty_list(self, client: OnetClient) -> None:
        """The endpoint answers 200 with total:0 for these, not 404 -- measured
        against the 55-0000 Military Specific family."""
        with patch.object(
            client._session,
            "get",
            return_value=_mock_response({"start": 1, "end": 0, "total": 0, "example": []}),
        ):
            assert client.get_hot_technologies("55-1011.00") == []

    def test_entries_without_a_title_are_skipped(self, client: OnetClient) -> None:
        with patch.object(
            client._session,
            "get",
            return_value=_mock_response({"example": [{"percentage": 5}, {"title": "Python"}]}),
        ):
            assert client.get_hot_technologies("15-2051.00") == ["Python"]

    def test_result_is_cached(self, client: OnetClient) -> None:
        with patch.object(
            client._session, "get", return_value=_mock_response(self._RESPONSE)
        ) as mock_get:
            client.get_hot_technologies("15-2051.00")
            client.get_hot_technologies("15-2051.00")

        assert mock_get.call_count == 1

    def test_raises_on_api_error(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response({}, status_code=500)):
            with pytest.raises(OnetAPIError):
                client.get_hot_technologies("15-2051.00")


# ---------------------------------------------------------------------------
# get_job_families / get_job_family_occupations  (catalog enumeration)
# ---------------------------------------------------------------------------


class TestGetJobFamilies:
    #: The live v2 shape: a BARE ARRAY, plus a trailing meta-entry with a title
    #: and href but no code.  Confirmed against api-v2.onetcenter.org 2026-09-16.
    _BARE_ARRAY = [
        {
            "href": "https://example.com/17-0000",
            "code": "17-0000",
            "title": "Architecture and Engineering",
        },
        {
            "href": "https://example.com/15-0000",
            "code": "15-0000",
            "title": "Computer and Mathematical",
        },
        {"href": "https://example.com/all", "title": "All Job Families"},
    ]

    def test_parses_the_bare_array_the_live_api_returns(self, client: OnetClient) -> None:
        """Regression: this endpoint returns a top-level JSON array, like
        /online/bright_outlook.  The previous ``data.get("job_family")`` raised
        AttributeError: 'list' object has no attribute 'get' on every live call,
        which made whole-catalog enumeration impossible."""
        with patch.object(client._session, "get", return_value=_mock_response(self._BARE_ARRAY)):
            families = client.get_job_families()

        assert {f["code"] for f in families} == {"17-0000", "15-0000"}

    def test_skips_the_meta_entry_that_has_no_code(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response(self._BARE_ARRAY)):
            families = client.get_job_families()

        assert all(f["code"] for f in families)
        assert "All Job Families" not in {f["title"] for f in families}

    def test_still_parses_the_wrapped_shape(self, client: OnetClient) -> None:
        """Accepted so a future re-wrap cannot break enumeration a second time."""
        wrapped = {"job_family": [{"code": "15-0000", "title": "Computer and Mathematical"}]}
        with patch.object(client._session, "get", return_value=_mock_response(wrapped)):
            assert client.get_job_families() == [
                {"code": "15-0000", "title": "Computer and Mathematical"}
            ]

    def test_empty_response_returns_empty_list(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response([])):
            assert client.get_job_families() == []


class TestGetJobFamilyOccupations:
    _RESPONSE = {
        "start": 1,
        "end": 2,
        "total": 114,
        "occupation": [
            {"code": "51-2011.00", "title": "Aircraft Structure Assemblers"},
            {"code": "51-2021.00", "title": "Coil Winders"},
        ],
    }

    def test_returns_occupations(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response(self._RESPONSE)):
            result = client.get_job_family_occupations("51-0000")

        assert result == [
            Occupation(code="51-2011.00", title="Aircraft Structure Assemblers"),
            Occupation(code="51-2021.00", title="Coil Winders"),
        ]

    def test_defaults_to_the_first_hundred(self, client: OnetClient) -> None:
        """The pre-existing contract, which path_scoring's candidate funnel
        relies on: adding paging must not widen anybody else's pool."""
        with patch.object(
            client._session, "get", return_value=_mock_response(self._RESPONSE)
        ) as mock_get:
            client.get_job_family_occupations("51-0000")

        assert mock_get.call_args.kwargs.get("params", {}) == {"start": 1, "end": 100}

    def test_passes_explicit_page_bounds_through(self, client: OnetClient) -> None:
        """51-0000 (Production) holds 114 occupations, so a caller that needs
        the whole family -- the corpus builder does -- must be able to ask for
        the second page."""
        with patch.object(
            client._session, "get", return_value=_mock_response(self._RESPONSE)
        ) as mock_get:
            client.get_job_family_occupations("51-0000", start=101, end=200)

        assert mock_get.call_args.kwargs.get("params", {}) == {"start": 101, "end": 200}

    def test_raises_on_api_error(self, client: OnetClient) -> None:
        with patch.object(client._session, "get", return_value=_mock_response({}, status_code=500)):
            with pytest.raises(OnetAPIError):
                client.get_job_family_occupations("51-0000")
