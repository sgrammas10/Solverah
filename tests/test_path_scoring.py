"""Tests for backend.services.path_scoring.

All O*NET HTTP calls are mocked — no live API traffic in CI.

Call-sequence notes (important for side_effect list ordering):
  score_paths with career_status="employed" and N skill search terms calls:
    search_occupations:  1 (resolve zone) + 1 (title in gather) + N (skills in gather)
    get_job_zone:        1 (current code) + 1 per unique candidate
    get_tech_skills:     1 per unique candidate
    get_skills_profile:  1 per unique candidate
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.services.onet_client import OnetAPIError, OnetClient, Occupation, Skill
from backend.services.path_scoring import (
    ScoredPath,
    UserProfile,
    UserSkill,
    _MIN_MATCH_LEN,
    _SKILL_LEVEL_WEIGHTS,
    _SKILLS_WEIGHT,
    _ZONE_WEIGHT,
    _gather_candidates,
    _generic_skills_overlap_score,
    _resolve_current_zone,
    _tech_skills_overlap_score,
    _zone_delta_score,
    score_paths,
)


# ---------------------------------------------------------------------------
# Tiny constructors
# ---------------------------------------------------------------------------


def occ(code: str, title: str = "A Role") -> Occupation:
    return Occupation(code=code, title=title)


def onet_skill(name: str, importance: float = 50.0, level: float = 3.0) -> Skill:
    return Skill(element_id="2.A.1.a", name=name, importance=importance, level=level)


def user_skill(name: str, level: str = "intermediate") -> UserSkill:
    return UserSkill(name=name, level=level)


def profile(**kwargs) -> UserProfile:
    defaults: dict = {
        "current_title": "Software Engineer",
        "career_status": "employed",
        "skills": [],
        "archetype": "Deep Diver",
    }
    defaults.update(kwargs)
    return UserProfile(**defaults)


@pytest.fixture()
def mock_client() -> MagicMock:
    return MagicMock(spec=OnetClient)


# ---------------------------------------------------------------------------
# _zone_delta_score
# ---------------------------------------------------------------------------


class TestZoneDeltaScore:
    def test_one_zone_above_scores_maximum(self):
        assert _zone_delta_score(2, 3) == 1.0

    def test_two_zones_above(self):
        assert _zone_delta_score(2, 4) == 0.7

    def test_three_or_more_zones_above(self):
        assert _zone_delta_score(1, 4) == 0.3
        assert _zone_delta_score(1, 5) == 0.3

    def test_same_zone_is_negative(self):
        assert _zone_delta_score(3, 3) == -0.2

    def test_regression_is_most_negative(self):
        assert _zone_delta_score(4, 3) == -0.5
        assert _zone_delta_score(5, 2) == -0.5

    def test_zone_1_to_2_is_maximum(self):
        # first_job user stepping to zone 2 should be ideal
        assert _zone_delta_score(1, 2) == 1.0


# ---------------------------------------------------------------------------
# _generic_skills_overlap_score
# ---------------------------------------------------------------------------


class TestGenericSkillsOverlapScore:
    def test_full_match_advanced_scores_1(self):
        score, matched = _generic_skills_overlap_score(
            [user_skill("Python", "advanced")],
            [onet_skill("Python", importance=100.0)],
        )
        assert matched == ["Python"]
        assert score == pytest.approx(1.0)

    def test_no_match_returns_zero_and_empty(self):
        score, matched = _generic_skills_overlap_score(
            [user_skill("Python")],
            [onet_skill("SQL"), onet_skill("Tableau")],
        )
        assert score == 0.0
        assert matched == []

    def test_advanced_scores_higher_than_beginner(self):
        onet = [onet_skill("Python", importance=100.0)]
        score_b, _ = _generic_skills_overlap_score([user_skill("Python", "beginner")], onet)
        score_a, _ = _generic_skills_overlap_score([user_skill("Python", "advanced")], onet)
        assert score_b < score_a

    def test_beginner_weight_is_correct(self):
        # beginner weight = 0.33; only skill; importance 100 / total 100 → 0.33
        score, _ = _generic_skills_overlap_score(
            [user_skill("Python", "beginner")],
            [onet_skill("Python", importance=100.0)],
        )
        assert score == pytest.approx(_SKILL_LEVEL_WEIGHTS["beginner"])

    def test_partial_match_normalised_correctly(self):
        # user has Python (advanced=1.0); onet has Python (50) + SQL (50)
        # overlap = 1.0 * 50 / 100 = 0.5
        score, matched = _generic_skills_overlap_score(
            [user_skill("Python", "advanced")],
            [onet_skill("Python", importance=50.0), onet_skill("SQL", importance=50.0)],
        )
        assert score == pytest.approx(0.5)
        assert matched == ["Python"]

    def test_case_insensitive_matching(self):
        score, matched = _generic_skills_overlap_score(
            [user_skill("python")],  # lowercase user input
            [onet_skill("Python")],  # titlecase from O*NET
        )
        assert score > 0.0
        assert matched == ["python"]  # returns the user's skill name as entered

    def test_empty_onet_skills_returns_zero(self):
        score, matched = _generic_skills_overlap_score([user_skill("Python")], [])
        assert score == 0.0
        assert matched == []

    def test_score_never_exceeds_one(self):
        user = [user_skill("A", "advanced"), user_skill("B", "advanced")]
        onet = [onet_skill("A", importance=100.0), onet_skill("B", importance=100.0)]
        score, _ = _generic_skills_overlap_score(user, onet)
        assert score <= 1.0

    def test_zero_total_importance_returns_zero(self):
        score, _ = _generic_skills_overlap_score(
            [user_skill("Python")],
            [onet_skill("Python", importance=0.0)],
        )
        assert score == 0.0


# ---------------------------------------------------------------------------
# _tech_skills_overlap_score
# ---------------------------------------------------------------------------


class TestTechSkillsOverlapScore:
    def test_exact_match_advanced_scores_1(self):
        score, matched = _tech_skills_overlap_score(
            [user_skill("Python", "advanced")],
            {"python"},
        )
        assert score == pytest.approx(1.0)
        assert matched == ["Python"]

    def test_no_match_returns_zero_and_empty(self):
        score, matched = _tech_skills_overlap_score(
            [user_skill("Python")],
            {"tableau", "powerbi"},
        )
        assert score == 0.0
        assert matched == []

    def test_empty_tech_names_returns_zero(self):
        score, matched = _tech_skills_overlap_score([user_skill("Python")], set())
        assert score == 0.0
        assert matched == []

    def test_empty_user_skills_returns_zero(self):
        score, matched = _tech_skills_overlap_score([], {"python"})
        assert score == 0.0
        assert matched == []

    def test_advanced_scores_higher_than_beginner(self):
        # Two skills, only Python matches — so level weight is divided by total of both,
        # making the ratio differ between beginner and advanced.
        score_b, _ = _tech_skills_overlap_score(
            [user_skill("Python", "beginner"), user_skill("SQL", "beginner")], {"python"}
        )
        score_a, _ = _tech_skills_overlap_score(
            [user_skill("Python", "advanced"), user_skill("SQL", "beginner")], {"python"}
        )
        assert score_b < score_a

    def test_substring_match(self):
        score, matched = _tech_skills_overlap_score(
            [user_skill("React", "advanced")],
            {"react native"},
        )
        assert score > 0.0
        assert matched == ["React"]

    def test_short_token_skipped(self):
        score, matched = _tech_skills_overlap_score(
            [user_skill("R", "advanced")],
            {"r programming"},
        )
        assert score == 0.0
        assert matched == []

    def test_score_capped_at_one(self):
        score, _ = _tech_skills_overlap_score(
            [user_skill("Python", "advanced"), user_skill("SQL", "advanced")],
            {"python", "sql"},
        )
        assert score <= 1.0


# ---------------------------------------------------------------------------
# _resolve_current_zone
# ---------------------------------------------------------------------------


class TestResolveCurrentZone:
    def test_first_job_never_queries_onet(self, mock_client):
        p = profile(career_status="first_job", current_title="Barista")
        zone, code = _resolve_current_zone(p, mock_client)
        assert zone == 1
        assert code is None
        mock_client.search_occupations.assert_not_called()

    def test_none_title_returns_zone_1(self, mock_client):
        p = profile(career_status="between_jobs", current_title=None)
        zone, code = _resolve_current_zone(p, mock_client)
        assert zone == 1
        assert code is None

    def test_employed_resolves_title_to_zone(self, mock_client):
        mock_client.search_occupations.return_value = [occ("15-1252.00", "Software Devs")]
        mock_client.get_job_zone.return_value = 3
        zone, code = _resolve_current_zone(
            profile(career_status="employed", current_title="Software Engineer"),
            mock_client,
        )
        assert zone == 3
        assert code == "15-1252.00"

    def test_between_jobs_resolves_title(self, mock_client):
        mock_client.search_occupations.return_value = [occ("11-1021.00", "General Managers")]
        mock_client.get_job_zone.return_value = 4
        zone, code = _resolve_current_zone(
            profile(career_status="between_jobs", current_title="General Manager"),
            mock_client,
        )
        assert zone == 4
        assert code == "11-1021.00"

    def test_empty_search_falls_back_to_zone_1(self, mock_client):
        mock_client.search_occupations.return_value = []
        zone, code = _resolve_current_zone(profile(), mock_client)
        assert zone == 1
        assert code is None

    def test_search_api_error_falls_back_to_zone_1(self, mock_client):
        mock_client.search_occupations.side_effect = OnetAPIError("timeout")
        zone, code = _resolve_current_zone(profile(), mock_client)
        assert zone == 1
        assert code is None

    def test_job_zone_api_error_still_returns_code(self, mock_client):
        # The code is known even if zone fetch fails; use it to exclude from candidates.
        mock_client.search_occupations.return_value = [occ("15-1252.00")]
        mock_client.get_job_zone.side_effect = OnetAPIError("zone fail")
        zone, code = _resolve_current_zone(profile(), mock_client)
        assert zone == 1
        assert code == "15-1252.00"


# ---------------------------------------------------------------------------
# _gather_candidates
# ---------------------------------------------------------------------------


class TestGatherCandidates:
    def test_deduplicates_across_searches(self, mock_client):
        # Same occupation returned by both the title and the skill search.
        mock_client.search_occupations.return_value = [occ("15-1252.00", "SW Dev")]
        p = profile(skills=[user_skill("Python")])
        candidates = _gather_candidates(p, mock_client, exclude_code=None)
        assert [c.code for c in candidates].count("15-1252.00") == 1

    def test_excludes_current_code(self, mock_client):
        mock_client.search_occupations.return_value = [
            occ("15-1252.00"),
            occ("15-1211.00"),
        ]
        candidates = _gather_candidates(profile(skills=[]), mock_client, exclude_code="15-1252.00")
        assert all(c.code != "15-1252.00" for c in candidates)

    def test_first_job_skips_title_search(self, mock_client):
        mock_client.search_occupations.return_value = []
        p = profile(career_status="first_job", current_title="Intern", skills=[])
        _gather_candidates(p, mock_client, exclude_code=None)
        # No current_title search term for first_job — only skills, which are empty here.
        mock_client.search_occupations.assert_not_called()

    def test_first_job_with_skills_searches_skills(self, mock_client):
        mock_client.search_occupations.return_value = [occ("43-4051.00", "Customer Rep")]
        p = profile(career_status="first_job", current_title=None, skills=[user_skill("Communication")])
        candidates = _gather_candidates(p, mock_client, exclude_code=None)
        mock_client.search_occupations.assert_called_once_with("Communication")
        assert len(candidates) == 1

    def test_api_error_on_one_term_is_skipped(self, mock_client):
        mock_client.search_occupations.side_effect = OnetAPIError("fail")
        p = profile(skills=[user_skill("Python")])
        candidates = _gather_candidates(p, mock_client, exclude_code=None)
        assert candidates == []

    def test_uses_at_most_skill_search_count_skills(self, mock_client):
        mock_client.search_occupations.return_value = []
        # 5 skills; only top 2 should be searched (plus the title)
        many_skills = [user_skill(f"Skill{i}") for i in range(5)]
        p = profile(skills=many_skills)
        _gather_candidates(p, mock_client, exclude_code=None)
        call_args = [c.args[0] for c in mock_client.search_occupations.call_args_list]
        # title + 2 skill names = 3 calls total
        assert len(call_args) == 3
        assert "Software Engineer" in call_args   # current_title
        assert "Skill0" in call_args
        assert "Skill1" in call_args
        assert "Skill2" not in call_args


# ---------------------------------------------------------------------------
# score_paths — integration-level tests with a fully mocked OnetClient
# ---------------------------------------------------------------------------


class TestScorePaths:
    """
    Call sequences for an "employed" user with 1 skill (N=1):
      search_occupations calls:
        [0] resolve: current_title  → [occ(current)]
        [1] gather:  current_title  → [candidates...]
        [2] gather:  skill name     → [candidates...]
      get_job_zone calls:
        [0] resolve: current_code → current_zone
        [1..] score: one per unique candidate
      get_skills_profile calls:
        [0..] score: one per unique candidate
    """

    def test_employed_returns_scored_paths(self, mock_client):
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00", "SW Dev")],        # resolve: current title
            [occ("15-1211.00", "CS Analysts"),    # gather: title search
             occ("11-3021.00", "IT Managers")],
            [],                                    # gather: skill search (Python)
        ]
        # get_job_zone: current=3, CS Analysts=4, IT Mgrs=5
        mock_client.get_job_zone.side_effect = [3, 4, 5]
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.side_effect = [
            [onet_skill("Python", 80.0)],
            [onet_skill("Leadership", 60.0)],
        ]

        results = score_paths(
            profile(career_status="employed", skills=[user_skill("Python", "advanced")]),
            mock_client,
        )

        assert len(results) == 2
        assert all(isinstance(r, ScoredPath) for r in results)
        assert results[0].score >= results[1].score  # sorted descending

    def test_first_job_uses_zone_1_and_favours_zone_2(self, mock_client):
        # first_job: no resolve call → only skill search
        mock_client.search_occupations.return_value = [occ("43-4051.00", "Customer Rep")]
        mock_client.get_job_zone.return_value = 2   # one step above zone 1
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.return_value = [onet_skill("Communication", 80.0)]

        results = score_paths(
            profile(
                current_title=None,
                career_status="first_job",
                skills=[user_skill("Communication", "intermediate")],
            ),
            mock_client,
        )

        assert len(results) == 1
        assert results[0].score > 0.5
        mock_client.search_occupations.assert_called_once_with("Communication")

    def test_between_jobs_resolves_title_and_scores(self, mock_client):
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00", "SW Dev")],   # resolve
            [occ("15-1252.00", "SW Dev"),    # gather (current excluded)
             occ("15-2051.00", "Data Sci")],
            [],                               # skill search
        ]
        mock_client.get_job_zone.side_effect = [3, 4]   # current=3, Data Sci=4
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.return_value = [onet_skill("Statistics", 70.0)]

        results = score_paths(
            profile(
                career_status="between_jobs",
                current_title="Software Developer",
                skills=[user_skill("Statistics", "beginner")],
            ),
            mock_client,
        )

        assert len(results) == 1
        assert results[0].onet_code == "15-2051.00"

    def test_between_jobs_no_title_uses_skill_search_only(self, mock_client):
        mock_client.search_occupations.return_value = [occ("15-1211.00", "CS Analyst")]
        mock_client.get_job_zone.return_value = 3   # candidate zone
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.return_value = []

        results = score_paths(
            profile(
                career_status="between_jobs",
                current_title=None,
                skills=[user_skill("Python")],
            ),
            mock_client,
        )

        # zone delta: 3 - 1 (default) = +2 → 0.7; no skills overlap
        assert len(results) == 1
        assert results[0].score == pytest.approx(_ZONE_WEIGHT * 0.7, abs=1e-3)

    def test_no_skill_overlap_scores_by_zone_only(self, mock_client):
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00")],                # resolve
            [occ("15-1211.00", "CS Analyst")],  # gather title
            [],                                  # gather skill
        ]
        mock_client.get_job_zone.side_effect = [2, 3]   # current=2, candidate=3 (+1)
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.return_value = [onet_skill("COBOL", 100.0)]

        results = score_paths(
            profile(skills=[user_skill("Python")]),  # no overlap with COBOL
            mock_client,
        )

        assert results[0].overlapping_skills == []
        # score = _SKILLS_WEIGHT*0.0 + _ZONE_WEIGHT*1.0
        assert results[0].score == pytest.approx(_ZONE_WEIGHT * 1.0)

    def test_higher_zone_beats_same_zone_with_equal_skills(self, mock_client):
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00")],                         # resolve
            [occ("15-1211.00", "Same Zone"),             # gather
             occ("11-3021.00", "Higher Zone")],
            [],
        ]
        # current=3, same=3, higher=4
        mock_client.get_job_zone.side_effect = [3, 3, 4]
        mock_client.get_tech_skills.return_value = set()
        # Identical skill overlap for both candidates
        mock_client.get_skills_profile.return_value = [onet_skill("Python", 100.0)]

        results = score_paths(
            profile(skills=[user_skill("Python", "intermediate")]),
            mock_client,
        )

        same_zone = next(r for r in results if r.onet_code == "15-1211.00")
        higher_zone = next(r for r in results if r.onet_code == "11-3021.00")
        assert higher_zone.score > same_zone.score

    def test_regression_below_current_zone_scores_near_zero(self, mock_client):
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00")],
            [occ("43-4051.00", "Entry Role")],
            [],
        ]
        mock_client.get_job_zone.side_effect = [4, 2]   # current=4, candidate=2 (-2)
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.return_value = []

        results = score_paths(profile(skills=[]), mock_client)

        # regression penalty: -0.5 zone score, 0 skills → clamp to 0
        assert results[0].score == 0.0

    def test_returns_at_most_top_n_results(self, mock_client):
        many = [occ(f"15-{i:04d}.00", f"Role {i}") for i in range(20)]
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00")],  # resolve
            many,                  # gather title
            [],                    # gather skill
        ]
        mock_client.get_job_zone.side_effect = [3] + [4] * 20
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.return_value = []

        results = score_paths(profile(skills=[]), mock_client)
        assert len(results) <= 10

    def test_results_sorted_descending(self, mock_client):
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00")],
            [occ("A-0001.00", "Low"), occ("A-0002.00", "High")],
            [],
        ]
        # current=2; both candidates at zone 3 (delta=+1)
        mock_client.get_job_zone.side_effect = [2, 3, 3]
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.side_effect = [
            [],                            # Low: no skills
            [onet_skill("Python", 100.0)], # High: skill match
        ]

        results = score_paths(
            profile(skills=[user_skill("Python", "advanced")]),
            mock_client,
        )

        assert results[0].onet_code == "A-0002.00"
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

    def test_empty_candidate_pool_returns_empty_list(self, mock_client):
        mock_client.search_occupations.return_value = []
        results = score_paths(profile(skills=[]), mock_client)
        assert results == []

    def test_api_error_on_zone_fetch_skips_candidate(self, mock_client):
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00")],
            [occ("15-1211.00", "Fails"), occ("15-2051.00", "Succeeds")],
            [],
        ]
        mock_client.get_job_zone.side_effect = [
            3,                         # current zone
            OnetAPIError("zone fail"), # first candidate fails
            4,                         # second candidate succeeds
        ]
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.return_value = []

        results = score_paths(profile(skills=[]), mock_client)
        assert len(results) == 1
        assert results[0].onet_code == "15-2051.00"

    def test_api_error_on_skills_fetch_skips_candidate(self, mock_client):
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00")],
            [occ("15-1211.00", "Fails Skills"), occ("15-2051.00", "OK")],
            [],
        ]
        mock_client.get_job_zone.side_effect = [3, 4, 4]
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.side_effect = [
            OnetAPIError("skills fail"),
            [],
        ]

        results = score_paths(profile(skills=[]), mock_client)
        assert len(results) == 1
        assert results[0].onet_code == "15-2051.00"

    def test_overlapping_skill_names_are_returned(self, mock_client):
        # resolve(title) + gather(title) + gather(Python) + gather(SQL) = 4 calls
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00")],
            [occ("15-1211.00", "CS Analyst")],
            [],  # Python skill search
            [],  # SQL skill search
        ]
        mock_client.get_job_zone.side_effect = [2, 3]
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.return_value = [
            onet_skill("Python", 80.0),
            onet_skill("SQL", 60.0),
            onet_skill("Tableau", 40.0),
        ]

        results = score_paths(
            profile(skills=[
                user_skill("Python", "advanced"),
                user_skill("SQL", "intermediate"),
            ]),
            mock_client,
        )

        assert set(results[0].overlapping_skills) == {"Python", "SQL"}

    def test_score_is_float_in_unit_interval(self, mock_client):
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00")],
            [occ("15-1211.00", "CS Analyst"), occ("43-4051.00", "Customer Rep")],
            [],
        ]
        # Candidates at zones 4 (+1) and 1 (regression)
        mock_client.get_job_zone.side_effect = [3, 4, 1]
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.return_value = [onet_skill("Python", 100.0)]

        results = score_paths(
            profile(skills=[user_skill("Python", "advanced")]),
            mock_client,
        )

        for r in results:
            assert isinstance(r.score, float)
            assert 0.0 <= r.score <= 1.0

    def test_first_job_no_skills_returns_empty(self, mock_client):
        results = score_paths(
            profile(career_status="first_job", current_title=None, skills=[]),
            mock_client,
        )
        assert results == []
        mock_client.search_occupations.assert_not_called()
