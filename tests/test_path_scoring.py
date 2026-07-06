"""Tests for backend.services.path_scoring.

All O*NET HTTP calls are mocked — no live API traffic in CI.

Call-count notes:
  score_paths with career_status="employed" and N skill search terms calls (no openai_client):
    search_occupations:  1 (resolve zone) + 1 (title in gather) + N (skills in gather)
    get_job_zone:        1 (current code) + 1 per unique candidate
    get_skills_profile:  1 per unique candidate
    get_tech_skills:     1 per unique candidate (hot_only=True, no fallback)
  When openai_client is provided, _generate_search_terms adds 1 LLM call before gathering.

Mocking convention: get_job_zone / get_skills_profile / get_tech_skills /
get_work_activities are mocked with code-keyed side_effect functions (see the
by_code() helper below) rather than positional side_effect lists, because
score_paths() fetches candidate data concurrently via a thread pool — the
order these are actually invoked in across candidates is not guaranteed.
search_occupations remains positional-order-sensitive (via plain side_effect
lists), since candidate gathering (_gather_candidates) and current-zone
resolution (_resolve_current_zone) both stay fully sequential.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

import backend.services.onet_client as onet_module
from backend.services.onet_client import (
    OnetAPIError,
    OnetClient,
    OnetRateLimitError,
    Occupation,
    Skill,
)
from backend.services.path_scoring import (
    ScoredPath,
    UserProfile,
    UserSkill,
    _CENTROID_MIX,
    _COVERAGE_MIX,
    _COVERAGE_TOP_K,
    _EMBED_CACHE,
    _EMBED_CACHE_MAX,
    _EMBED_THRESHOLD,
    _HOT_TECH_IMPORTANCE,
    _LLM_DEBUG_LOG,
    _MIN_MATCH_LEN,
    _ROLE_WEIGHT_BY_INTENT,
    _SKILL_LEVEL_WEIGHTS,
    _SKILLS_WEIGHT_EXPERIENCED,
    _ZONE_WEIGHT_EXPERIENCED,
    _batch_embed,
    _build_behavioral_profile,
    _build_role_profile,
    _compute_centroid_score,
    _compute_weighted_user_centroid,
    _cosine_similarity,
    _filter_candidate_pool,
    _find_matched_skills,
    _gather_candidates,
    _generate_search_terms,
    _normalize_title_for_onet,
    _resolve_current_zone,
    _role_coverage_score,
    _role_similarity_score,
    _shape_role_similarity,
    _semantic_overlap_score,
    _substring_overlap_score,
    _work_style_similarity,
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


class Seq:
    """Marks a by_code() value as a sequence consumed in order across repeated
    calls to the *same* onet_code, rather than a single fixed response.

    Needed when one occupation is legitimately looked up twice in a single
    score_paths() call with different expected results each time — e.g. the
    user's current occupation also appears in the candidate pool (stay_in_field
    doesn't exclude it), so get_job_zone(code) is called once during the
    (sequential) current-zone resolution and again later during the candidate
    loop for that same occupation. Safe to rely on call order here specifically
    because resolution always fully completes before the parallel candidate
    fetch phase starts — the nondeterminism parallelization introduces is only
    in the relative order *across different candidates*, not between the
    sequential resolve step and the candidate phase as a whole.
    """
    def __init__(self, *values):
        self.values = list(values)


def by_code(mapping: dict[str, object], *, default=None):
    """Build a side_effect function keyed on the onet_code positional arg.

    Replaces positional side_effect lists (order-dependent) for
    get_job_zone/get_skills_profile/get_tech_skills/get_work_activities:
    score_paths fetches candidate data concurrently via a thread pool, so the
    order these mocks are actually invoked in is not guaranteed to match
    submission order. Keying responses on the onet_code argument itself makes
    the mock order-independent. Raises KeyError on an unmapped code (surfaced
    as a test failure) unless *default* is given, so a missing test-data entry
    fails loudly rather than silently returning None.

    Wrap a value in Seq(...) when the same code is called more than once and
    needs different answers each time (see Seq's docstring).
    """
    queues = {code: iter(v.values) for code, v in mapping.items() if isinstance(v, Seq)}

    def _side_effect(code, *args, **kwargs):
        if code in queues:
            try:
                value = next(queues[code])
            except StopIteration:
                raise KeyError(f"by_code(): Seq exhausted for onet_code={code!r}") from None
        elif code in mapping:
            value = mapping[code]
        elif default is not None:
            value = default
        else:
            raise KeyError(f"by_code(): no mapped response for onet_code={code!r}")
        if isinstance(value, Exception):
            raise value
        return value
    return _side_effect


@pytest.fixture()
def mock_client() -> MagicMock:
    m = MagicMock(spec=OnetClient)
    m.get_job_family_occupations.return_value = []  # default: job family empty; override per test
    return m


# ---------------------------------------------------------------------------
# _zone_delta_score
# ---------------------------------------------------------------------------


class TestZoneDeltaScore:
    def test_one_zone_above_scores_maximum(self):
        assert _zone_delta_score(2, 3) == 1.0

    def test_two_zones_above(self):
        assert _zone_delta_score(2, 4) == 0.6

    def test_three_or_more_zones_above(self):
        assert _zone_delta_score(1, 4) == 0.2
        assert _zone_delta_score(1, 5) == 0.2

    def test_same_zone_is_lateral(self):
        assert _zone_delta_score(3, 3) == 0.5

    def test_regression_scores(self):
        assert _zone_delta_score(4, 3) == 0.0   # one step back
        assert _zone_delta_score(5, 2) == -0.3  # three steps back

    def test_zone_1_to_2_is_maximum(self):
        # first_job user stepping to zone 2 should be ideal
        assert _zone_delta_score(1, 2) == 1.0


# ---------------------------------------------------------------------------
# _substring_overlap_score
# ---------------------------------------------------------------------------


class TestSubstringOverlapScore:
    """Tests for the bidirectional substring fallback.

    Input format: _substring_overlap_score(user_skills, [(name, importance_0_to_100), ...])
    Denominator = sum of user proficiency weights (user-centric).
    Each match contributes: proficiency_weight * (importance / 100).
    """

    def test_full_match_advanced_scores_1(self):
        score, matched = _substring_overlap_score(
            [user_skill("Python", "advanced")],
            [("Python", 100.0)],
        )
        assert matched == ["Python"]
        assert score == pytest.approx(1.0)

    def test_no_match_returns_zero_and_empty(self):
        score, matched = _substring_overlap_score(
            [user_skill("Python")],
            [("SQL", 50.0), ("Tableau", 50.0)],
        )
        assert score == 0.0
        assert matched == []

    def test_proficiency_affects_score_across_multi_skill_users(self):
        # With 2 user skills where only Python matches, the unmatched skill
        # stays in the denominator — higher proficiency on the match → higher score.
        onet = [("Python", 100.0)]
        score_b, _ = _substring_overlap_score(
            [user_skill("Python", "beginner"), user_skill("NoMatch", "advanced")], onet
        )
        score_a, _ = _substring_overlap_score(
            [user_skill("Python", "advanced"), user_skill("NoMatch", "advanced")], onet
        )
        assert score_b < score_a

    def test_single_match_gives_full_importance_coverage(self):
        # With one skill that matches at 100% importance, score = importance fraction = 1.0.
        # (Denominator = user weight; contribution = user_weight * 1.0 → cancels out.)
        score, _ = _substring_overlap_score(
            [user_skill("Python", "beginner")],
            [("Python", 100.0)],
        )
        assert score == pytest.approx(1.0)

    def test_partial_match_normalised_correctly(self):
        # user has Python (advanced=1.0); onet has Python (50) + SQL (50)
        # contribution = 1.0 * (50/100) = 0.5; denominator = 1.0 → score = 0.5
        score, matched = _substring_overlap_score(
            [user_skill("Python", "advanced")],
            [("Python", 50.0), ("SQL", 50.0)],
        )
        assert score == pytest.approx(0.5)
        assert matched == ["Python"]

    def test_case_insensitive_matching(self):
        score, matched = _substring_overlap_score(
            [user_skill("python")],   # lowercase user input
            [("Python", 50.0)],       # titlecase from O*NET
        )
        assert score > 0.0
        assert matched == ["python"]  # returns the user's skill name as entered

    def test_empty_onet_items_returns_zero(self):
        score, matched = _substring_overlap_score([user_skill("Python")], [])
        assert score == 0.0
        assert matched == []

    def test_score_never_exceeds_one(self):
        user = [user_skill("A", "advanced"), user_skill("B", "advanced")]
        onet = [("A", 100.0), ("B", 100.0)]
        score, _ = _substring_overlap_score(user, onet)
        assert score <= 1.0

    def test_zero_importance_returns_zero(self):
        score, _ = _substring_overlap_score(
            [user_skill("Python")],
            [("Python", 0.0)],
        )
        assert score == 0.0

    def test_substring_match(self):
        score, matched = _substring_overlap_score(
            [user_skill("React", "advanced")],
            [("react native", 100.0)],
        )
        assert score > 0.0
        assert matched == ["React"]

    def test_short_token_skipped(self):
        score, matched = _substring_overlap_score(
            [user_skill("R", "advanced")],
            [("r programming", 100.0)],
        )
        assert score == 0.0
        assert matched == []

    def test_empty_user_skills_returns_zero(self):
        score, matched = _substring_overlap_score([], [("python", 100.0)])
        assert score == 0.0
        assert matched == []




# ---------------------------------------------------------------------------
# _resolve_current_zone
# ---------------------------------------------------------------------------


class TestResolveCurrentZone:
    def test_first_job_never_queries_onet(self, mock_client):
        p = profile(career_status="first_job", current_title="Barista")
        zone, code, resolved, title = _resolve_current_zone(p, mock_client)
        assert zone == 1
        assert code is None
        assert resolved is False
        assert title is None
        mock_client.search_occupations.assert_not_called()

    def test_none_title_returns_zone_1(self, mock_client):
        p = profile(career_status="between_jobs", current_title=None)
        zone, code, resolved, title = _resolve_current_zone(p, mock_client)
        assert zone == 1
        assert code is None
        assert resolved is False
        assert title is None

    def test_employed_resolves_title_to_zone(self, mock_client):
        mock_client.search_occupations.return_value = [occ("15-1252.00", "Software Devs")]
        mock_client.get_job_zone.return_value = 3
        zone, code, resolved, title = _resolve_current_zone(
            profile(career_status="employed", current_title="Software Engineer"),
            mock_client,
        )
        assert zone == 3
        assert code == "15-1252.00"
        assert resolved is True
        assert title == "Software Engineer"

    def test_between_jobs_resolves_title(self, mock_client):
        mock_client.search_occupations.return_value = [occ("11-1021.00", "General Managers")]
        mock_client.get_job_zone.return_value = 4
        zone, code, resolved, title = _resolve_current_zone(
            profile(career_status="between_jobs", current_title="General Manager"),
            mock_client,
        )
        assert zone == 4
        assert code == "11-1021.00"
        assert resolved is True
        assert title == "General Manager"

    def test_empty_search_falls_back_to_zone_1(self, mock_client):
        mock_client.search_occupations.return_value = []
        zone, code, resolved, title = _resolve_current_zone(profile(), mock_client)
        assert zone == 1
        assert code is None
        assert resolved is False
        assert title == "Software Engineer"

    def test_search_api_error_falls_back_to_zone_1(self, mock_client):
        mock_client.search_occupations.side_effect = OnetAPIError("timeout")
        zone, code, resolved, title = _resolve_current_zone(profile(), mock_client)
        assert zone == 1
        assert code is None
        assert resolved is False
        assert title == "Software Engineer"

    def test_job_zone_api_error_still_returns_code(self, mock_client):
        # The code is known even if zone fetch fails; use it to exclude from candidates.
        mock_client.search_occupations.return_value = [occ("15-1252.00")]
        mock_client.get_job_zone.side_effect = OnetAPIError("zone fail")
        zone, code, resolved, title = _resolve_current_zone(profile(), mock_client)
        assert zone == 1
        assert code == "15-1252.00"
        assert resolved is False
        assert title == "Software Engineer"


# ---------------------------------------------------------------------------
# _gather_candidates
# ---------------------------------------------------------------------------


class TestGatherCandidates:
    def test_deduplicates_across_searches(self, mock_client):
        mock_client.search_occupations.return_value = [occ("15-1252.00", "SW Dev")]
        p = profile(skills=[user_skill("Python")])
        candidates = _gather_candidates(p, mock_client, None, None)
        assert [c.code for c in candidates].count("15-1252.00") == 1

    def test_does_not_exclude_current_code(self, mock_client):
        """current_code is NOT excluded from the candidate pool.

        Zone resolution normalises "Founder & Full Stack Engineer" → "Software Developers"
        to derive a zone number.  Software Developers is still a valid recommendation, so
        it must remain eligible.  The zone-resolved code is seeding, not blocking.
        """
        mock_client.get_job_family_occupations.return_value = []
        mock_client.search_occupations.return_value = [occ("15-1252.00"), occ("15-1211.00")]
        p = profile(skills=[user_skill("Python")])
        candidates = _gather_candidates(p, mock_client, None, "15-1252.00")
        assert any(c.code == "15-1252.00" for c in candidates)

    def test_stay_in_field_uses_keyword_search(self, mock_client):
        mock_client.search_occupations.return_value = [occ("15-1211.00")]
        p = profile(skills=[user_skill("Python")], move_intent="stay_in_field")
        _gather_candidates(p, mock_client, None, None)
        mock_client.search_occupations.assert_called()
        mock_client.get_bright_outlook_occupations.assert_not_called()

    def test_fresh_start_uses_bright_outlook(self, mock_client):
        mock_client.get_bright_outlook_occupations.return_value = [occ("15-1252.00", "SW Dev")]
        p = profile(skills=[user_skill("Python")], move_intent="fresh_start")
        candidates = _gather_candidates(p, mock_client, None, None)
        mock_client.get_bright_outlook_occupations.assert_called_once()
        mock_client.search_occupations.assert_not_called()
        assert len(candidates) == 1

    def test_fresh_start_falls_back_when_bright_outlook_empty(self, mock_client):
        mock_client.get_bright_outlook_occupations.return_value = []
        mock_client.search_occupations.return_value = [occ("15-1211.00", "CS Analyst")]
        p = profile(skills=[user_skill("Python")], move_intent="fresh_start")
        candidates = _gather_candidates(p, mock_client, None, None)
        assert len(candidates) >= 1
        mock_client.search_occupations.assert_called()

    def test_api_error_on_keyword_search_skipped(self, mock_client):
        mock_client.search_occupations.side_effect = OnetAPIError("fail")
        p = profile(skills=[user_skill("Python")])
        candidates = _gather_candidates(p, mock_client, None, None)
        assert candidates == []


# ---------------------------------------------------------------------------
# _gather_candidates — job family primary architecture (Fix 5)
# ---------------------------------------------------------------------------


def test_gather_candidates_uses_job_family_as_primary_pool(mock_client):
    """Job family is used as primary pool; only first keyword result per term is added.

    current_code "15-9999.00" is used as the resolved code (not present in the family
    results) so all family members are eligible (none excluded as current occupation).
    """
    sw_dev = occ("15-1252.00", "Software Developers")
    web_dev = occ("15-1254.00", "Web Developers")
    cirs = occ("15-1221.00", "Computer and Information Research Scientists")
    data_sci = occ("15-2051.00", "Data Scientists")

    mock_client.get_job_family_occupations.return_value = [sw_dev, cirs, web_dev]
    # Keyword search: first result per term = data_sci (only it is added; second result ignored)
    mock_client.search_occupations.return_value = [data_sci, occ("15-2031.00", "Operations Research Analysts")]

    p = profile(career_status="employed", skills=[user_skill("Python")])
    candidates = _gather_candidates(p, mock_client, None, "15-9999.00")
    codes = [c.code for c in candidates]

    assert "15-1252.00" in codes    # from job family
    assert "15-1254.00" in codes    # from job family
    assert "15-2051.00" in codes    # first result from keyword search (whitelisted)
    assert "15-1221.00" not in codes  # filtered by _RESEARCH_ROLE_CODES_EXCLUDE
    assert "15-2031.00" not in codes  # filtered by _RESEARCH_SOC_PREFIX_EXCLUDE (15-2)


def test_gather_candidates_first_result_only_from_keyword_search(mock_client):
    """Keyword search contributes only result[0] per term, not all 20 results."""
    a = occ("15-1252.00", "Software Developers")
    b = occ("15-1254.00", "Web Developers")
    c_ = occ("15-1211.00", "Computer Systems Analysts")

    mock_client.get_job_family_occupations.return_value = []
    mock_client.search_occupations.return_value = [a, b, c_]  # 3 results

    p = profile(career_status="employed", skills=[user_skill("Python")])
    candidates = _gather_candidates(p, mock_client, None, "15-9999.00")
    codes = [c.code for c in candidates]

    assert "15-1252.00" in codes   # result[0] kept
    assert "15-1254.00" not in codes  # result[1] discarded
    assert "15-1211.00" not in codes  # result[2] discarded


def test_gather_candidates_skips_primary_when_no_code(mock_client):
    """When current_code is None, job family call is skipped entirely."""
    mock_client.search_occupations.return_value = [occ("15-1252.00")]
    p = profile(skills=[user_skill("Python")])
    _gather_candidates(p, mock_client, None, None)
    mock_client.get_job_family_occupations.assert_not_called()


# ---------------------------------------------------------------------------
# _zone_delta_score with seniority_intent
# ---------------------------------------------------------------------------


class TestZoneDeltaScoreWithIntent:
    def test_move_up_boosts_delta_2(self):
        assert _zone_delta_score(2, 4, "move_up") == 0.8

    def test_move_up_penalises_lateral(self):
        assert _zone_delta_score(3, 3, "move_up") == 0.0

    def test_move_up_still_favours_delta_1(self):
        assert _zone_delta_score(2, 3, "move_up") == 1.0

    def test_stay_lateral_boosts_same_zone(self):
        assert _zone_delta_score(3, 3, "stay_lateral") == 0.8

    def test_stay_lateral_reduces_forward_step(self):
        assert _zone_delta_score(2, 3, "stay_lateral") == 0.5

    def test_stay_lateral_slight_regression_tolerable(self):
        assert _zone_delta_score(3, 2, "stay_lateral") == 0.2

    def test_open_matches_none_behaviour(self):
        for delta in range(-2, 4):
            assert _zone_delta_score(3, 3 + delta, "open") == _zone_delta_score(3, 3 + delta, None)


# ---------------------------------------------------------------------------
# _gather_candidates with move_intent
# ---------------------------------------------------------------------------


class TestGenerateSearchTerms:
    """Fallback behaviour (no openai_client) matches the old _gather_candidates term logic."""

    def test_stay_in_field_includes_title_and_skills(self):
        p = profile(skills=[user_skill("Python"), user_skill("SQL")], move_intent="stay_in_field")
        terms = _generate_search_terms(p, client=None)
        assert "Software Engineer" in terms
        assert "Python" in terms

    def test_fresh_start_excludes_title(self):
        p = profile(skills=[user_skill("Python"), user_skill("SQL")], move_intent="fresh_start")
        terms = _generate_search_terms(p, client=None)
        assert "Software Engineer" not in terms
        assert "Python" in terms

    def test_adjacent_includes_title_and_skills(self):
        p = profile(skills=[user_skill("Python")], move_intent="adjacent")
        terms = _generate_search_terms(p, client=None)
        assert "Software Engineer" in terms
        assert "Python" in terms

    def test_none_intent_behaves_like_adjacent(self):
        p = profile(skills=[user_skill("Python")], move_intent=None)
        terms = _generate_search_terms(p, client=None)
        assert "Software Engineer" in terms
        assert "Python" in terms

    def test_first_job_skips_title(self):
        p = profile(career_status="first_job", current_title="Intern", skills=[user_skill("Python")])
        terms = _generate_search_terms(p, client=None)
        assert "Intern" not in terms
        assert "Python" in terms

    def test_limits_to_skill_search_count_skills(self):
        many_skills = [user_skill(f"Skill{i}") for i in range(5)]
        p = profile(skills=many_skills)
        terms = _generate_search_terms(p, client=None)
        assert "Software Engineer" in terms
        assert "Skill0" in terms
        assert "Skill1" in terms
        assert "Skill2" not in terms

    def test_empty_skills_first_job_returns_empty(self):
        p = profile(career_status="first_job", current_title=None, skills=[])
        terms = _generate_search_terms(p, client=None)
        assert terms == []


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
        # Both candidates come from job family (primary pool).
        mock_client.get_job_family_occupations.return_value = [
            occ("15-1211.00", "CS Analysts"),
            occ("11-3021.00", "IT Managers"),
        ]
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00", "SW Dev")],  # resolve: current title
            [], [],                          # keyword supplementary — nothing extra
        ]
        # get_job_zone: current=3, CS Analysts=4, IT Mgrs=5
        mock_client.get_job_zone.side_effect = by_code({
            "15-1252.00": 3, "15-1211.00": 4, "11-3021.00": 5,
        })
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.side_effect = by_code({
            "15-1211.00": [onet_skill("Python", 80.0)],
            "11-3021.00": [onet_skill("Leadership", 60.0)],
        })

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
        # Data Sci comes from job family (15-2051.00 is whitelisted in _RESEARCH_SOC_WHITELIST).
        mock_client.get_job_family_occupations.return_value = [occ("15-2051.00", "Data Sci")]
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00", "SW Dev")],  # resolve
            [], [],                          # keyword supplementary — nothing extra
        ]
        mock_client.get_job_zone.side_effect = by_code({"15-1252.00": 3, "15-2051.00": 4})   # current=3, Data Sci=4
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
        mock_client.get_skills_profile.return_value = [onet_skill("Python", 80.0)]

        results = score_paths(
            profile(
                career_status="between_jobs",
                current_title=None,
                skills=[user_skill("Python", "intermediate")],
            ),
            mock_client,
        )

        # zone unresolved → skills_w=1.0, zone_w=0.0
        # no hot tech tools; generic pool = [("Python", 80.0)]
        # substring fallback: contribution = 0.67*(80/100)/0.67 = 0.8; final = 0.8
        assert len(results) == 1
        assert results[0].score == pytest.approx(80.0 / 100.0, abs=1e-3)

    def test_between_jobs_no_title_zero_overlap_filtered(self, mock_client):
        mock_client.search_occupations.return_value = [occ("15-1211.00", "CS Analyst")]
        mock_client.get_job_zone.return_value = 3
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

        # zone is unresolved and overlap is zero for an established user → filtered out
        assert results == []

    def test_no_skill_overlap_scores_by_zone_only(self, mock_client):
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00")],                # resolve
            [occ("15-1211.00", "CS Analyst")],  # gather title
            [],                                  # gather skill
        ]
        mock_client.get_job_zone.side_effect = by_code({"15-1252.00": 2, "15-1211.00": 3})   # current=2, candidate=3 (+1)
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.return_value = [onet_skill("COBOL", 100.0)]

        results = score_paths(
            profile(skills=[user_skill("Python")]),  # no overlap with COBOL
            mock_client,
        )

        assert results[0].overlapping_skills == []
        # experienced user, zone resolved: skills_w=0.5, zone_w=0.5; no skill overlap
        assert results[0].score == pytest.approx(_ZONE_WEIGHT_EXPERIENCED * 1.0)

    def test_higher_zone_beats_same_zone_with_equal_skills(self, mock_client):
        mock_client.get_job_family_occupations.return_value = [
            occ("15-1211.00", "Same Zone"),
            occ("11-3021.00", "Higher Zone"),
        ]
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00")],  # resolve
            [], [],               # keyword supplementary — nothing extra
        ]
        # current=3, same=3, higher=4
        mock_client.get_job_zone.side_effect = by_code({
            "15-1252.00": 3, "15-1211.00": 3, "11-3021.00": 4,
        })
        mock_client.get_tech_skills.return_value = set()
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
        mock_client.get_job_zone.side_effect = by_code({"15-1252.00": 4, "43-4051.00": 2})   # current=4, candidate=2 (-2)
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
        mock_client.get_job_zone.side_effect = by_code({"15-1252.00": 3}, default=4)
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.return_value = []

        results = score_paths(profile(skills=[]), mock_client)
        assert len(results) <= 10

    def test_results_sorted_descending(self, mock_client):
        mock_client.get_job_family_occupations.return_value = [
            occ("15-0001.00", "Low"),
            occ("15-0002.00", "High"),
        ]
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00")],  # resolve
            [], [],               # keyword supplementary — nothing extra
        ]
        # current=2; both candidates at zone 3 (delta=+1)
        mock_client.get_job_zone.side_effect = by_code({
            "15-1252.00": 2, "15-0001.00": 3, "15-0002.00": 3,
        })
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.side_effect = by_code({
            "15-0001.00": [],                            # Low: no skills
            "15-0002.00": [onet_skill("Python", 100.0)], # High: skill match
        })

        results = score_paths(
            profile(skills=[user_skill("Python", "advanced")]),
            mock_client,
        )

        assert results[0].onet_code == "15-0002.00"
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

    def test_empty_candidate_pool_returns_empty_list(self, mock_client):
        mock_client.search_occupations.return_value = []
        results = score_paths(profile(skills=[]), mock_client)
        assert results == []

    def test_api_error_on_zone_fetch_skips_candidate(self, mock_client):
        # Both candidates come from job family; 15-1211 fails zone lookup, 15-2051 succeeds.
        mock_client.get_job_family_occupations.return_value = [
            occ("15-1211.00", "Fails"),
            occ("15-2051.00", "Succeeds"),
        ]
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00")],
            [], [],
        ]
        mock_client.get_job_zone.side_effect = by_code({
            "15-1252.00": 3,                          # current zone
            "15-1211.00": OnetAPIError("zone fail"),  # first candidate fails
            "15-2051.00": 4,                          # second candidate succeeds
        })
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.return_value = []

        results = score_paths(profile(skills=[]), mock_client)
        assert len(results) == 1
        assert results[0].onet_code == "15-2051.00"

    def test_rate_limit_error_on_zone_fetch_skips_candidate_during_parallel_fetch(self, mock_client):
        """A candidate hitting OnetRateLimitError during the (now-parallel) fetch
        phase must be skipped like any other fetch failure, not crash the whole
        request — parallelizing raises the odds of hitting O*NET's rate limiter
        (up to _FETCH_MAX_WORKERS candidates in flight at once), so this failure
        mode needed the same handling OnetAPIError already had.
        """
        mock_client.get_job_family_occupations.return_value = [
            occ("15-1211.00", "Fails"),
            occ("15-2051.00", "Succeeds"),
        ]
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00")],
            [], [],
        ]
        mock_client.get_job_zone.side_effect = by_code({
            "15-1252.00": 3,                                       # current zone
            "15-1211.00": OnetRateLimitError("rate limited"),      # first candidate fails
            "15-2051.00": 4,                                       # second candidate succeeds
        })
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.return_value = []

        results = score_paths(profile(skills=[]), mock_client)
        assert len(results) == 1
        assert results[0].onet_code == "15-2051.00"

    def test_api_error_on_skills_fetch_skips_candidate(self, mock_client):
        mock_client.get_job_family_occupations.return_value = [
            occ("15-1211.00", "Fails Skills"),
            occ("15-2051.00", "OK"),
        ]
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00")],
            [], [],
        ]
        mock_client.get_job_zone.side_effect = by_code({
            "15-1252.00": 3, "15-1211.00": 4, "15-2051.00": 4,
        })
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.side_effect = by_code({
            "15-1211.00": OnetAPIError("skills fail"),
            "15-2051.00": [],
        })

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
        mock_client.get_job_zone.side_effect = by_code({"15-1252.00": 2, "15-1211.00": 3})
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
        mock_client.get_job_zone.side_effect = by_code({
            "15-1252.00": 3, "15-1211.00": 4, "43-4051.00": 1,
        })
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

    def test_tech_skills_fetches_hot_only_once(self, mock_client):
        """score_paths calls get_tech_skills(hot_only=True) exactly once per candidate."""
        mock_client.search_occupations.return_value = [occ("15-1252.00", "SW Dev")]
        mock_client.get_job_zone.return_value = 3
        mock_client.get_skills_profile.return_value = []
        mock_client.get_tech_skills.return_value = {"python", "javascript"}

        score_paths(
            profile(
                career_status="between_jobs",
                current_title=None,
                skills=[user_skill("Python", "intermediate")],
            ),
            mock_client,
        )

        mock_client.get_tech_skills.assert_called_once_with("15-1252.00", hot_only=True)


# ---------------------------------------------------------------------------
# _normalize_title_for_onet
# ---------------------------------------------------------------------------


def test_normalize_title_calls_openai_and_strips_artifacts():
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Output: Software Developer"))]
    )
    result = _normalize_title_for_onet("Co-Founder & CTO", mock_openai)
    assert result == "Software Developer"
    mock_openai.chat.completions.create.assert_called_once()


def test_normalize_title_returns_none_on_api_error():
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.side_effect = Exception("API error")
    result = _normalize_title_for_onet("Some Title", mock_openai)
    assert result is None


# ---------------------------------------------------------------------------
# _batch_embed and cache
# ---------------------------------------------------------------------------


def test_batch_embed_caches_and_pre_evicts():
    import backend.services.path_scoring as ps

    ps._EMBED_CACHE.clear()
    # Fill cache to max with sentinel values.
    for i in range(ps._EMBED_CACHE_MAX):
        ps._EMBED_CACHE[f"existing_{i}"] = [0.0]

    mock_openai = MagicMock()
    mock_openai.embeddings.create.return_value = MagicMock(
        data=[
            MagicMock(index=0, embedding=[1.0]),
            MagicMock(index=1, embedding=[2.0]),
        ]
    )

    _batch_embed(["new_text_1", "new_text_2"], mock_openai)

    assert "new_text_1" in ps._EMBED_CACHE
    assert "new_text_2" in ps._EMBED_CACHE
    assert len(ps._EMBED_CACHE) == ps._EMBED_CACHE_MAX  # evicted 2, added 2
    ps._EMBED_CACHE.clear()


# ---------------------------------------------------------------------------
# _semantic_overlap_score and _semantic_score_via_embeddings
# ---------------------------------------------------------------------------


def test_semantic_overlap_above_threshold_matches():
    import backend.services.path_scoring as ps

    ps._EMBED_CACHE.clear()
    # Plant embeddings: user skill and role item pointing in the same direction.
    ps._EMBED_CACHE["python"] = [1.0, 0.0]
    ps._EMBED_CACHE["programming language"] = [0.99, 0.14]  # cos ≈ 0.99

    score, matched = _compute_centroid_score(
        [user_skill("Python", "advanced")],
        [("programming language", 80.0)],
    )

    assert score > 0.0
    assert "Python" in matched
    ps._EMBED_CACHE.clear()


def test_semantic_overlap_falls_back_to_substring_when_no_client():
    score, matched = _semantic_overlap_score(
        [user_skill("Python", "advanced")],
        [("python", 100.0)],
        None,  # no OpenAI client → substring fallback
    )
    assert score == pytest.approx(1.0)
    assert matched == ["Python"]


# ---------------------------------------------------------------------------
# _build_role_profile
# ---------------------------------------------------------------------------


def test_build_role_profile_merges_hot_tech_and_generic():
    names = {"python", "javascript"}
    skills = [
        onet_skill("Problem Solving", 70.0),
        onet_skill("Communication", 80.0),
    ]
    items = _build_role_profile(names, skills)
    names_in_items = {name for name, _ in items}
    assert "python" in names_in_items
    assert "javascript" in names_in_items
    assert "Problem Solving" in names_in_items
    assert "Communication" in names_in_items
    hot_importances = {imp for name, imp in items if name in {"python", "javascript"}}
    assert hot_importances == {_HOT_TECH_IMPORTANCE}


def test_build_role_profile_excludes_low_importance_generic():
    names: set[str] = set()
    skills = [
        onet_skill("High Skill", 75.0),
        onet_skill("Low Skill", 30.0),
    ]
    items = _build_role_profile(names, skills)
    names_in_items = {name for name, _ in items}
    assert "High Skill" in names_in_items
    assert "Low Skill" not in names_in_items


def test_build_role_profile_no_hot_tech():
    """For a non-tech role with no hot tools, profile is generic-skills only."""
    names: set[str] = set()
    skills = [onet_skill("Patient Care", 90.0)]
    items = _build_role_profile(names, skills)
    assert len(items) == 1
    assert items[0] == ("Patient Care", 90.0)


# ---------------------------------------------------------------------------
# _compute_centroid_score and _find_matched_skills
# ---------------------------------------------------------------------------


def test_compute_centroid_score_produces_single_similarity():
    import backend.services.path_scoring as ps
    ps._EMBED_CACHE.clear()
    ps._EMBED_CACHE["python"] = [1.0, 0.0]
    ps._EMBED_CACHE["programming language"] = [0.99, 0.14]  # high cosine sim

    score, matched = _compute_centroid_score(
        [user_skill("Python", "advanced")],
        [("programming language", 80.0)],
    )

    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0
    assert score > 0.5  # centroid similarity, not a fractional count
    assert "Python" in matched
    ps._EMBED_CACHE.clear()


def test_find_matched_skills_does_not_affect_score():
    """Centroid score is geometric; matched list does not influence it."""
    import backend.services.path_scoring as ps
    ps._EMBED_CACHE.clear()
    ps._EMBED_CACHE["python"] = [1.0, 0.0]   # aligned with role
    ps._EMBED_CACHE["sql"] = [0.0, 1.0]       # orthogonal to role
    ps._EMBED_CACHE["programming"] = [1.0, 0.0]

    score, matched = _compute_centroid_score(
        [user_skill("Python", "advanced"), user_skill("sql", "advanced")],
        [("programming", 80.0)],
    )

    # Only Python aligns with the role item above threshold
    assert "Python" in matched
    assert "sql" not in matched
    # Centroid is average of [1,0] and [0,1] → [0.5, 0.5]; role centroid = [1,0]
    # cos([0.5,0.5], [1,0]) = 0.5/sqrt(0.5) ≈ 0.707 — not 0.5 (1/2 matched)
    assert score == pytest.approx(0.707, abs=0.01)
    ps._EMBED_CACHE.clear()


def test_centroid_falls_back_to_substring_without_client():
    """With openai_client=None, centroid path is skipped; substring matching is used."""
    score, matched = _semantic_overlap_score(
        [user_skill("Python", "advanced")],
        [("Python", 100.0)],
        None,
    )
    assert score == pytest.approx(1.0)
    assert matched == ["Python"]


# ---------------------------------------------------------------------------
# _build_behavioral_profile
# ---------------------------------------------------------------------------


def test_build_behavioral_profile_with_all_fields():
    p = profile(
        archetype="Autonomous Strategic Contributor",
        focus_type="Deep Diver",
        manager_match="The Operator",
        work_style_tags=["Independent Worker", "Constructive Feedback Utilizer"],
    )
    result = _build_behavioral_profile(p)
    # Space-joined so that description sentences with their own punctuation
    # don't get double periods inserted between them.
    assert result == (
        "Autonomous Strategic Contributor Deep Diver The Operator "
        "Independent Worker Constructive Feedback Utilizer"
    )


def test_build_behavioral_profile_partial():
    p = profile(archetype="Deep Diver")
    result = _build_behavioral_profile(p)
    assert result == "Deep Diver"


def test_build_behavioral_profile_no_assessments():
    p = profile(archetype="", focus_type=None, manager_match=None, work_style_tags=[])
    result = _build_behavioral_profile(p)
    assert result is None


# ---------------------------------------------------------------------------
# _work_style_similarity
# ---------------------------------------------------------------------------


def test_work_style_similarity_returns_zero_without_client():
    score = _work_style_similarity(
        "Deep Diver. The Operator",
        [("Getting Information", 80.0), ("Communicating", 70.0)],
        None,
    )
    assert score == 0.0


def test_work_style_similarity_returns_zero_on_empty_activities():
    mock_openai = MagicMock()
    score = _work_style_similarity("Deep Diver", [], mock_openai)
    assert score == 0.0
    mock_openai.embeddings.create.assert_not_called()


# ---------------------------------------------------------------------------
# score_paths — behavioral profile signal
# ---------------------------------------------------------------------------


def test_score_paths_skips_work_activities_fetch_when_no_behavioral_profile(mock_client):
    """get_work_activities must not be called when behavioral_profile is None."""
    mock_client.search_occupations.side_effect = [
        [occ("15-1252.00", "SW Dev")],   # resolve
        [occ("15-1211.00", "CS Analyst")],  # gather title
        [],                               # gather skill
    ]
    mock_client.get_job_zone.side_effect = by_code({"15-1252.00": 3, "15-1211.00": 4})
    mock_client.get_tech_skills.return_value = set()
    mock_client.get_skills_profile.return_value = [onet_skill("Python", 80.0)]

    score_paths(
        profile(archetype="", focus_type=None, manager_match=None, work_style_tags=[],
                skills=[user_skill("Python", "intermediate")]),
        mock_client,
    )

    mock_client.get_work_activities.assert_not_called()


# ---------------------------------------------------------------------------
# _role_coverage_score
# ---------------------------------------------------------------------------


def test_role_coverage_full_match():
    """All top-K role items matched by user → 1.0."""
    import backend.services.path_scoring as ps
    ps._EMBED_CACHE.clear()
    # User skill and all role items aligned in the same direction.
    ps._EMBED_CACHE["python"] = [1.0, 0.0]
    for name in ["JavaScript", "React", "TypeScript", "Node.js", "REST APIs"]:
        ps._EMBED_CACHE[name] = [1.0, 0.0]  # cos(python, item) = 1.0 ≥ _EMBED_THRESHOLD

    user = [user_skill("Python", "advanced")]
    role_items = [(name, 75.0) for name in ["JavaScript", "React", "TypeScript", "Node.js", "REST APIs"]]
    score = _role_coverage_score(user, role_items)
    assert score == pytest.approx(1.0)
    ps._EMBED_CACHE.clear()


def test_role_coverage_no_match():
    """User skills orthogonal to all role items → 0.0."""
    import backend.services.path_scoring as ps
    ps._EMBED_CACHE.clear()
    ps._EMBED_CACHE["python"] = [1.0, 0.0]
    for name in ["Instructing", "Learning Strategies", "Curriculum Design"]:
        ps._EMBED_CACHE[name] = [0.0, 1.0]  # orthogonal → cos = 0.0 < _EMBED_THRESHOLD

    user = [user_skill("Python", "advanced")]
    role_items = [(name, 75.0) for name in ["Instructing", "Learning Strategies", "Curriculum Design"]]
    score = _role_coverage_score(user, role_items)
    assert score == pytest.approx(0.0)
    ps._EMBED_CACHE.clear()


def test_role_coverage_partial():
    """3 of 5 top-K role items are matched by user → coverage = 3/5."""
    import backend.services.path_scoring as ps
    ps._EMBED_CACHE.clear()
    # User: 3 tech skills all in [1,0] direction → user_centroid = [1,0].
    ps._EMBED_CACHE["skill_a"] = [1.0, 0.0]
    ps._EMBED_CACHE["skill_b"] = [1.0, 0.0]
    ps._EMBED_CACHE["skill_c"] = [1.0, 0.0]
    # Role has 5 items: 3 tech [1,0] (close to user_centroid, user matches) and
    # 2 orthogonal [0,1] (far from user_centroid, user does not match).
    # All 5 are in top-K (k=5); 3 matched → 3/5.
    ps._EMBED_CACHE["Role Tech 1"] = [1.0, 0.0]
    ps._EMBED_CACHE["Role Tech 2"] = [1.0, 0.0]
    ps._EMBED_CACHE["Role Tech 3"] = [1.0, 0.0]
    ps._EMBED_CACHE["Role Other 1"] = [0.0, 1.0]
    ps._EMBED_CACHE["Role Other 2"] = [0.0, 1.0]

    user = [user_skill("skill_a"), user_skill("skill_b"), user_skill("skill_c")]
    role_items = [
        ("Role Tech 1", 80.0), ("Role Tech 2", 80.0), ("Role Tech 3", 80.0),
        ("Role Other 1", 80.0), ("Role Other 2", 80.0),
    ]
    score = _role_coverage_score(user, role_items)
    assert score == pytest.approx(3 / 5)
    ps._EMBED_CACHE.clear()


def test_role_coverage_empty_role_items():
    """Empty role_items pool → 0.0."""
    import backend.services.path_scoring as ps
    ps._EMBED_CACHE.clear()
    ps._EMBED_CACHE["python"] = [1.0, 0.0]

    user = [user_skill("Python", "advanced")]
    score = _role_coverage_score(user, [])
    assert score == 0.0
    ps._EMBED_CACHE.clear()


def test_role_coverage_excludes_uncached_from_pool():
    """Uncached role items are excluded from top-K selection."""
    import backend.services.path_scoring as ps
    ps._EMBED_CACHE.clear()
    # User has 1 tech skill [1,0] → user_centroid = [1,0].
    # Role has 2 cached items (tech and research) plus 1 uncached item.
    # Only cached items participate in top-K; uncached item is silently ignored.
    # top-2: "Cached Tech Item" cos=1.0 → matched; "Cached Other Item" cos=0.0 → not matched.
    # coverage = 1/2 = 0.5
    ps._EMBED_CACHE["skill_tech"] = [1.0, 0.0]
    ps._EMBED_CACHE["Cached Tech Item"] = [1.0, 0.0]
    ps._EMBED_CACHE["Cached Other Item"] = [0.0, 1.0]
    # "Uncached Item" deliberately absent → excluded from available_role

    user = [user_skill("skill_tech")]
    role_items = [("Cached Tech Item", 80.0), ("Cached Other Item", 80.0), ("Uncached Item", 80.0)]
    score = _role_coverage_score(user, role_items)
    assert score == pytest.approx(0.5)
    ps._EMBED_CACHE.clear()


def test_overlap_combines_centroid_and_coverage(mock_client):
    """When openai_client provided, overlap_score = 0.5×centroid + 0.5×coverage."""
    import backend.services.path_scoring as ps
    ps._EMBED_CACHE.clear()

    # All embeddings seeded so _batch_embed makes no API calls.
    ps._EMBED_CACHE["python"] = [1.0, 0.0]         # user skill (lowercased)
    ps._EMBED_CACHE["python hot"] = [1.0, 0.0]     # hot tech tool in role_items
    ps._EMBED_CACHE["Programming"] = [1.0, 0.0]    # generic skill in role_items

    mock_client.search_occupations.side_effect = [
        [occ("15-1252.00", "SW Dev")],      # resolve current title
        [occ("15-1211.00", "CS Analyst")],  # gather title
        [],                                  # gather skill
    ]
    mock_client.get_job_zone.side_effect = by_code({"15-1252.00": 3, "15-1211.00": 3})  # current=3, candidate=3 (delta=0)
    mock_client.get_tech_skills.return_value = {"python hot"}
    mock_client.get_skills_profile.return_value = [onet_skill("Programming", 80.0)]

    mock_openai = MagicMock()
    mock_openai.embeddings.create.return_value = MagicMock(data=[])

    results = score_paths(
        profile(archetype="", skills=[user_skill("Python", "advanced")]),
        mock_client,
        mock_openai,
    )

    # centroid: user=[1,0], role_centroid = mean([1,0],[1,0])=[1,0] → cos=1.0
    # coverage (user-centroid): user_centroid=[1,0]; top-2 role items "python hot"[1,0] and
    #   "Programming"[1,0] both close to user_centroid; user "python"[1,0] matches both.
    #   coverage = 2/2 = 1.0
    # overlap = 0.5*1.0 + 0.5*1.0 = 1.0
    # zone: delta=0, seniority=None → zone_score=0.5; experienced, zone resolved
    # role: move_intent unspecified (None) → role_w=0.35; anchor title "Software Engineer"
    #   resolved but its embedding (and the candidate's) aren't seeded here, so
    #   role_score is None → contributes 0.  role_w still carves out its share of the
    #   skills/zone budget: skills_w = zone_w = 0.5*(1-0.35) = 0.325.
    # final = 0.35*0 + 0.325*overlap(1.0) + 0.325*zone(0.5) = 0.325 + 0.1625 = 0.4875
    assert len(results) == 1
    assert results[0].score == pytest.approx(0.4875)
    ps._EMBED_CACHE.clear()


# ---------------------------------------------------------------------------
# OnetClient — get_bright_outlook_occupations (cache behaviour)
# ---------------------------------------------------------------------------


@pytest.fixture()
def reset_bright_outlook_cache():
    """Reset the module-level Bright Outlook cache before and after each test."""
    onet_module._BRIGHT_OUTLOOK_CACHE = []
    onet_module._BRIGHT_OUTLOOK_CACHE_TS = 0.0
    yield
    onet_module._BRIGHT_OUTLOOK_CACHE = []
    onet_module._BRIGHT_OUTLOOK_CACHE_TS = 0.0


class TestBrightOutlookOccupations:
    def test_deduplicates_across_categories(self, reset_bright_outlook_cache):
        client = MagicMock(spec=OnetClient)
        # Two categories; second returns an occ already seen in first.
        client._get.side_effect = [
            {"bright_outlook_category": [{"code": "growing"}, {"code": "openings"}]},
            {"occupation": [{"code": "15-1252.00", "title": "SW Dev"}, {"code": "15-1211.00", "title": "CS Analyst"}]},
            {"occupation": [{"code": "15-1252.00", "title": "SW Dev"}, {"code": "11-3021.00", "title": "IT Manager"}]},
        ]
        from backend.services.onet_client import OnetClient as RealClient
        result = RealClient.get_bright_outlook_occupations(client)
        codes = [o.code for o in result]
        assert codes.count("15-1252.00") == 1
        assert len(codes) == 3

    def test_uses_cache_within_ttl(self, reset_bright_outlook_cache):
        client = MagicMock(spec=OnetClient)
        client._get.side_effect = [
            {"bright_outlook_category": [{"code": "growing"}]},
            {"occupation": [{"code": "15-1252.00", "title": "SW Dev"}]},
        ]
        from backend.services.onet_client import OnetClient as RealClient
        RealClient.get_bright_outlook_occupations(client)
        RealClient.get_bright_outlook_occupations(client)
        # _get called only twice (categories + one category); second call hit cache
        assert client._get.call_count == 2

    def test_returns_stale_cache_on_error(self, reset_bright_outlook_cache):
        client = MagicMock(spec=OnetClient)
        # Prime the cache with one successful fetch.
        client._get.side_effect = [
            {"bright_outlook_category": [{"code": "growing"}]},
            {"occupation": [{"code": "15-1252.00", "title": "SW Dev"}]},
        ]
        from backend.services.onet_client import OnetClient as RealClient, OnetAPIError as RealAPIError
        RealClient.get_bright_outlook_occupations(client)
        # Expire the cache and make the next call fail.
        onet_module._BRIGHT_OUTLOOK_CACHE_TS = 0.0
        client._get.side_effect = RealAPIError("network error")
        result = RealClient.get_bright_outlook_occupations(client)
        assert len(result) == 1
        assert result[0].code == "15-1252.00"


# ---------------------------------------------------------------------------
# _generate_search_terms — LLM path (JSON parsing)
# ---------------------------------------------------------------------------


class TestGenerateSearchTermsLLM:
    def test_parses_valid_json_array(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices[0].message.content = (
            '["Software Developers", "Data Scientists", "Information Security Analysts"]'
        )
        p = profile(skills=[user_skill("Python"), user_skill("React")])
        terms = _generate_search_terms(p, mock_client)
        assert terms == ["Software Developers", "Data Scientists", "Information Security Analysts"]

    def test_strips_markdown_fences(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices[0].message.content = (
            '```json\n["Software Developers", "Data Scientists"]\n```'
        )
        p = profile(skills=[user_skill("Python")])
        terms = _generate_search_terms(p, mock_client)
        assert "Software Developers" in terms

    def test_falls_back_on_invalid_json(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value.choices[0].message.content = (
            "here are some titles: Software Developer, Data Scientist"
        )
        p = profile(skills=[user_skill("Python")])
        terms = _generate_search_terms(p, mock_client)
        # Should return fallback list (title + skills), not raise
        assert isinstance(terms, list)
        assert len(terms) > 0

    def test_falls_back_on_api_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API down")
        p = profile(skills=[user_skill("Python")])
        terms = _generate_search_terms(p, mock_client)
        assert isinstance(terms, list)


# ---------------------------------------------------------------------------
# Priority weight adjustment
# ---------------------------------------------------------------------------


class TestPriorityWeights:
    def test_learning_growth_increases_zone_weight(self, mock_client):
        """When priority=learning_growth and zone is reliable, zone_w should be 0.65."""
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00")],         # resolve
            [occ("15-1211.00", "CS Analyst")],  # gather
            [],
        ]
        # current=2, candidate=3 (+1 → zone_score=1.0)
        mock_client.get_job_zone.side_effect = by_code({"15-1252.00": 2, "15-1211.00": 3})
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.return_value = []  # no skill overlap

        results = score_paths(
            profile(skills=[], priority="learning_growth"),
            mock_client,
        )
        # zone_w=0.65, overlap=0 → score = 0.65 × 1.0 = 0.65
        assert len(results) == 1
        assert results[0].score == pytest.approx(0.65, abs=1e-3)

    def test_no_priority_uses_balanced_weights(self, mock_client):
        """Without priority, zone_w stays at 0.50 (ZONE_WEIGHT_EXPERIENCED)."""
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00")],
            [occ("15-1211.00", "CS Analyst")],
            [],
        ]
        mock_client.get_job_zone.side_effect = by_code({"15-1252.00": 2, "15-1211.00": 3})
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.return_value = []

        results = score_paths(profile(skills=[], priority=None), mock_client)
        assert results[0].score == pytest.approx(_ZONE_WEIGHT_EXPERIENCED * 1.0, abs=1e-3)


# ---------------------------------------------------------------------------
# Zone normalization — O*NET plural form and two-attempt fallback
# ---------------------------------------------------------------------------


def test_normalize_title_uses_onet_plural_form():
    """LLM returns a plural O*NET title; _resolve_current_zone resolves zone via that title."""
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Software Developers"))]
    )
    mock_onet = MagicMock(spec=OnetClient)
    mock_onet.search_occupations.side_effect = [
        [],  # raw title → no O*NET results
        [occ("15-1252.00", "Software Developers")],  # normalized plural → found
    ]
    mock_onet.get_job_zone.return_value = 4

    zone, code, resolved, title = _resolve_current_zone(
        profile(career_status="employed", current_title="Founder & Full Stack Engineer"),
        mock_onet,
        mock_openai,
    )

    assert resolved is True
    assert zone == 4
    assert code == "15-1252.00"
    assert title == "Software Developers"
    calls = [str(c) for c in mock_onet.search_occupations.call_args_list]
    assert any("Software Developers" in c for c in calls)


def test_normalize_title_fallback_attempt_on_first_miss():
    """When first normalized title finds nothing O*NET, second fallback prompt succeeds."""
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.side_effect = [
        MagicMock(choices=[MagicMock(message=MagicMock(content="Quantum Engineer"))]),
        MagicMock(choices=[MagicMock(message=MagicMock(content="Software Developers"))]),
    ]
    mock_onet = MagicMock(spec=OnetClient)
    mock_onet.search_occupations.side_effect = [
        [],  # raw title → no results
        [],  # "Quantum Engineer" → no results
        [occ("15-1252.00", "Software Developers")],  # fallback broad category → found
    ]
    mock_onet.get_job_zone.return_value = 4

    zone, code, resolved, title = _resolve_current_zone(
        profile(career_status="employed", current_title="Quantum Computing Visionary"),
        mock_onet,
        mock_openai,
    )

    assert resolved is True
    assert zone == 4
    assert code == "15-1252.00"
    assert title == "Software Developers"
    assert mock_openai.chat.completions.create.call_count == 2


# ---------------------------------------------------------------------------
# LLM debug log written by score_paths
# ---------------------------------------------------------------------------


def _debug_log_path() -> str:
    import backend.services.path_scoring as ps
    return os.path.normpath(
        os.path.join(os.path.dirname(ps.__file__), "..", "..", "llm_debug.txt")
    )


def _make_search_terms_openai() -> MagicMock:
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='["Software Developers"]'))]
    )
    mock_openai.embeddings.create.return_value = MagicMock(data=[])
    return mock_openai


def test_llm_debug_log_written_after_score_paths(mock_client):
    """score_paths writes llm_debug.txt containing key section headers."""
    mock_client.search_occupations.return_value = []
    p = profile(career_status="between_jobs", current_title=None, skills=[user_skill("Python")])

    score_paths(p, mock_client, _make_search_terms_openai())

    path = _debug_log_path()
    assert os.path.exists(path)
    content = open(path, encoding="utf-8").read()
    assert "SEARCH TERM GENERATION" in content
    assert "BEHAVIORAL PROFILE" in content
    assert "CANDIDATE SCORES" in content


def test_llm_debug_log_cleared_between_invocations(mock_client):
    """Second score_paths call does not include entries from the first invocation."""
    mock_client.search_occupations.return_value = []
    p = profile(career_status="between_jobs", current_title=None, skills=[user_skill("Python")])
    mock_openai = _make_search_terms_openai()

    score_paths(p, mock_client, mock_openai)
    score_paths(p, mock_client, mock_openai)

    content = open(_debug_log_path(), encoding="utf-8").read()
    # Each invocation generates exactly one SEARCH TERM GENERATION — LLM Input entry.
    assert content.count("SEARCH TERM GENERATION — LLM Input") == 1


# ---------------------------------------------------------------------------
# Bug fixes: zone normalization, candidate filtering, coverage direction
# ---------------------------------------------------------------------------


def test_zone_llm_normalization_fires_on_unreliable_raw_match():
    """LLM normalization runs even when raw O*NET search finds a code but get_job_zone fails."""
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Software Developers"))]
    )
    mock_onet = MagicMock(spec=OnetClient)
    mock_onet.search_occupations.side_effect = [
        [occ("17-2199.00", "Engineers, All Other")],  # raw title → unreliable match
        [occ("15-1252.00", "Software Developers")],   # LLM-normalized → reliable
    ]
    mock_onet.get_job_zone.side_effect = [
        OnetAPIError("zone lookup failed"),  # raw match zone fails → reliable=False
        4,                                   # normalized match zone succeeds
    ]

    zone, code, resolved, title = _resolve_current_zone(
        profile(career_status="employed", current_title="Founder & Full Stack Engineer"),
        mock_onet,
        mock_openai,
    )

    assert resolved is True
    assert zone == 4
    assert code == "15-1252.00"
    assert title == "Software Developers"
    # LLM was called for normalization
    mock_openai.chat.completions.create.assert_called_once()


def test_candidate_pool_excludes_unrelated_science_roles():
    """Life/physical/social science SOC codes are removed when user has no domain skills."""
    sw_user = profile(
        career_status="employed",
        skills=[user_skill("React"), user_skill("TypeScript"), user_skill("Python")],
    )
    candidates = [
        occ("15-1252.00", "Software Developers"),
        occ("19-1029.01", "Bioinformatics Scientists"),
        occ("19-2021.00", "Atmospheric and Space Scientists"),
        occ("19-3094.00", "Political Scientists"),
        occ("15-1211.00", "Computer Systems Analysts"),
    ]
    filtered = _filter_candidate_pool(candidates, sw_user)
    codes = [o.code for o in filtered]
    assert "15-1252.00" in codes
    assert "15-1211.00" in codes
    assert "19-1029.01" not in codes
    assert "19-2021.00" not in codes
    assert "19-3094.00" not in codes


def test_candidate_pool_excludes_research_adjacent_roles_by_default():
    """15-2 Mathematical Science Occupations and CIRS are removed for a tech user.

    15-2051.00 (Data Scientists) is the sole 15-2 practitioner role and must survive
    the prefix exclusion via _RESEARCH_SOC_WHITELIST.
    """
    tech_user = profile(
        career_status="employed",
        skills=[user_skill("React"), user_skill("Python"), user_skill("SQL")],
    )
    candidates = [
        occ("15-1252.00", "Software Developers"),
        occ("15-2051.00", "Data Scientists"),            # whitelisted — must survive
        occ("15-1221.00", "Computer and Information Research Scientists"),  # excluded by code
        occ("15-2031.00", "Operations Research Analysts"),   # excluded by 15-2 prefix
        occ("15-2041.00", "Statisticians"),                  # excluded by 15-2 prefix
        occ("15-2021.00", "Mathematicians"),                 # excluded by 15-2 prefix
        occ("15-2099.01", "Bioinformatics Technicians"),     # excluded by 15-2 prefix
    ]
    filtered = _filter_candidate_pool(candidates, tech_user)
    codes = [o.code for o in filtered]
    assert "15-1252.00" in codes
    assert "15-2051.00" in codes
    assert "15-1221.00" not in codes
    assert "15-2031.00" not in codes
    assert "15-2041.00" not in codes
    assert "15-2021.00" not in codes
    assert "15-2099.01" not in codes


def test_candidate_pool_keeps_research_roles_when_unlocked_by_skills():
    """A user with explicit research-domain skills keeps CIRS / 15-2 roles in the pool."""
    research_user = profile(
        career_status="employed",
        skills=[user_skill("Python"), user_skill("bioinformatics")],
    )
    candidates = [
        occ("15-1252.00", "Software Developers"),
        occ("15-1221.00", "Computer and Information Research Scientists"),
        occ("15-2041.00", "Statisticians"),
    ]
    filtered = _filter_candidate_pool(candidates, research_user)
    codes = [o.code for o in filtered]
    assert "15-1221.00" in codes
    assert "15-2041.00" in codes


def test_coverage_user_direction_higher_for_aligned_role():
    """User's tech skills produce high coverage for Software Developers, near-zero for Atmospheric Scientists."""
    import backend.services.path_scoring as ps
    ps._EMBED_CACHE.clear()

    # User skills: all in tech direction [1, 0]
    for skill in ["react", "javascript", "python"]:
        ps._EMBED_CACHE[skill] = [1.0, 0.0]

    # Software Developers role items: tech direction [1, 0]
    sw_role_items = [(name, 75.0) for name in ["JavaScript", "React", "Python"]]
    for name in ["JavaScript", "React", "Python"]:
        ps._EMBED_CACHE[name] = [1.0, 0.0]

    # Atmospheric Scientists role items: orthogonal direction [0, 1]
    atm_role_items = [(name, 75.0) for name in ["Meteorology", "FORTRAN", "Radar Systems"]]
    for name in ["Meteorology", "FORTRAN", "Radar Systems"]:
        ps._EMBED_CACHE[name] = [0.0, 1.0]

    user = [user_skill("react"), user_skill("javascript"), user_skill("python")]
    sw_coverage = _role_coverage_score(user, sw_role_items)
    atm_coverage = _role_coverage_score(user, atm_role_items)

    assert sw_coverage > atm_coverage
    assert sw_coverage == pytest.approx(1.0)
    assert atm_coverage == pytest.approx(0.0)
    ps._EMBED_CACHE.clear()


def test_research_scientist_excluded_from_results_for_tech_user(mock_client):
    """CIRS is excluded from score_paths results even when it appears in the job family.

    CIRS enters via the job family primary pool (15-0000 family includes 15-1221.00),
    but _filter_candidate_pool removes it before it reaches the scoring loop.
    """
    import backend.services.path_scoring as ps
    ps._EMBED_CACHE.clear()

    for skill in ["react", "typescript", "python", "sql"]:
        ps._EMBED_CACHE[skill] = [1.0, 0.0]
    for item in ["JavaScript", "React", "Python", "TypeScript", "Node.js"]:
        ps._EMBED_CACHE[item] = [1.0, 0.0]

    sw_dev = occ("15-1252.00", "Software Developers")
    web_dev = occ("15-1254.00", "Web Developers")
    cirs = occ("15-1221.00", "Computer and Information Research Scientists")

    # Zone resolution: one search_occupations call
    mock_client.search_occupations.side_effect = [
        [occ("15-1253.00")],   # zone resolution for "Software Engineer"
        [sw_dev],               # supplementary: first result for "Software Developers" term
    ]
    # Job family primary includes sw_dev, web_dev, cirs; CIRS filtered before scoring
    mock_client.get_job_family_occupations.return_value = [sw_dev, cirs, web_dev]
    mock_client.get_job_zone.side_effect = by_code({
        "15-1253.00": 3, "15-1252.00": 3, "15-1254.00": 3,
    })  # current=3, sw_dev=3, web_dev=3
    mock_client.get_tech_skills.side_effect = by_code({
        "15-1252.00": {"JavaScript", "React", "Python", "TypeScript", "Node.js"},  # sw_dev
        "15-1254.00": {"HTML", "CSS", "JavaScript"},                                # web_dev
    })
    mock_client.get_skills_profile.return_value = []

    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='["Software Developers"]'))]
    )
    mock_openai.embeddings.create.return_value = MagicMock(data=[])

    results = score_paths(
        profile(
            current_title="Software Engineer",
            career_status="employed",
            skills=[
                user_skill("react"), user_skill("typescript"),
                user_skill("python"), user_skill("sql"),
            ],
        ),
        mock_client,
        mock_openai,
    )

    codes = [r.onet_code for r in results]
    assert "15-1252.00" in codes
    assert "15-1221.00" not in codes

    ps._EMBED_CACHE.clear()


# ---------------------------------------------------------------------------
# Scoring Fix Round 3 regression tests
# ---------------------------------------------------------------------------


def test_no_life_science_roles_for_software_user():
    """SOC 19-1/2/3/4 codes are all removed for users with no life/science skills."""
    tech_user = profile(
        career_status="employed",
        skills=[user_skill("React"), user_skill("Python"),
                user_skill("JavaScript"), user_skill("SQL")],
    )
    candidates = [
        occ("15-1252.00", "Software Developers"),
        occ("19-1029.01", "Bioinformatics Scientists"),
        occ("19-2021.00", "Atmospheric Scientists"),
        occ("19-3094.00", "Political Scientists"),
        occ("19-4099.01", "Bioinformatics Technicians"),
        occ("15-1211.00", "Computer Systems Analysts"),
    ]
    filtered = _filter_candidate_pool(candidates, tech_user)
    codes = [o.code for o in filtered]
    assert "15-1252.00" in codes
    assert "15-1211.00" in codes
    assert not any(c.startswith("19-") for c in codes)


def test_coverage_user_centroid_direction_differentiates_tech_vs_research():
    """Top-K role items closest to tech user's centroid are tech items, not genomics items."""
    import backend.services.path_scoring as ps
    ps._EMBED_CACHE.clear()

    for skill in ["react", "typescript", "python", "javascript", "sql"]:
        ps._EMBED_CACHE[skill] = [1.0, 0.0]

    sw_items = [(n, 75.0) for n in ["JavaScript SDK", "React Framework", "Python Libraries"]]
    for n in ["JavaScript SDK", "React Framework", "Python Libraries"]:
        ps._EMBED_CACHE[n] = [1.0, 0.0]

    bio_items = [(n, 75.0) for n in ["Genomics Toolkit", "Sequencing Platform", "Bioinformatics Suite"]]
    for n in ["Genomics Toolkit", "Sequencing Platform", "Bioinformatics Suite"]:
        ps._EMBED_CACHE[n] = [0.0, 1.0]

    user = [user_skill("react"), user_skill("typescript"), user_skill("python"),
            user_skill("javascript"), user_skill("sql")]
    sw_cov = _role_coverage_score(user, sw_items)
    bio_cov = _role_coverage_score(user, bio_items)

    assert sw_cov == pytest.approx(1.0)
    assert bio_cov == pytest.approx(0.0)
    ps._EMBED_CACHE.clear()


def test_software_developers_above_bioinformatics(mock_client):
    """Bioinformatics is filtered out for a tech-only user; Software Developers appears."""
    import backend.services.path_scoring as ps
    ps._EMBED_CACHE.clear()

    for skill in ["react", "typescript", "python", "sql"]:
        ps._EMBED_CACHE[skill] = [1.0, 0.0]
    for item in ["JavaScript", "React", "Python", "TypeScript"]:
        ps._EMBED_CACHE[item] = [1.0, 0.0]

    sw_dev = occ("15-1252.00", "Software Developers")
    bio_sci = occ("19-1029.01", "Bioinformatics Scientists")

    mock_client.search_occupations.side_effect = [
        [occ("15-1253.00")],   # resolve current title
        [sw_dev, bio_sci],      # gather: both returned by O*NET search
    ]
    mock_client.get_job_zone.side_effect = by_code({"15-1253.00": 3, "15-1252.00": 4})  # current=3, sw_dev=4
    mock_client.get_tech_skills.return_value = {"JavaScript", "React", "Python", "TypeScript"}
    mock_client.get_skills_profile.return_value = []

    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='["Software Developers"]'))]
    )
    mock_openai.embeddings.create.return_value = MagicMock(data=[])

    results = score_paths(
        profile(
            current_title="Full Stack Developer",
            career_status="employed",
            skills=[user_skill("react"), user_skill("typescript"),
                    user_skill("python"), user_skill("sql")],
        ),
        mock_client,
        mock_openai,
    )

    codes = [r.onet_code for r in results]
    assert "15-1252.00" in codes, "Software Developers should appear in results"
    assert "19-1029.01" not in codes, "Bioinformatics should be filtered for tech-only user"
    ps._EMBED_CACHE.clear()


def test_web_developers_above_survey_researchers(mock_client):
    """Survey Researchers (19-3xxx) are filtered out for a web-dev user."""
    import backend.services.path_scoring as ps
    ps._EMBED_CACHE.clear()

    for skill in ["html", "css", "javascript", "react"]:
        ps._EMBED_CACHE[skill] = [1.0, 0.0]
    for item in ["HTML5", "CSS3", "JavaScript", "React.js"]:
        ps._EMBED_CACHE[item] = [1.0, 0.0]

    web_dev = occ("15-1257.00", "Web Developers")
    survey = occ("19-3022.00", "Survey Researchers")

    mock_client.search_occupations.side_effect = [
        [occ("15-1253.00")],   # resolve current title
        [web_dev, survey],      # gather: both returned by O*NET search
    ]
    mock_client.get_job_zone.side_effect = by_code({"15-1253.00": 3, "15-1257.00": 4})  # current=3, web_dev=4
    mock_client.get_tech_skills.return_value = {"HTML5", "CSS3", "JavaScript", "React.js"}
    mock_client.get_skills_profile.return_value = []

    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='["Web Developers"]'))]
    )
    mock_openai.embeddings.create.return_value = MagicMock(data=[])

    results = score_paths(
        profile(
            current_title="Frontend Developer",
            career_status="employed",
            skills=[user_skill("html"), user_skill("css"),
                    user_skill("javascript"), user_skill("react")],
        ),
        mock_client,
        mock_openai,
    )

    codes = [r.onet_code for r in results]
    assert "15-1257.00" in codes, "Web Developers should appear in results"
    assert "19-3022.00" not in codes, "Survey Researchers should be filtered for web-dev user"
    ps._EMBED_CACHE.clear()


# ---------------------------------------------------------------------------
# Proficiency-weighted centroid
# ---------------------------------------------------------------------------


def test_proficiency_weights_shift_centroid_toward_advanced_skills():
    """Weighted centroid leans toward the advanced-skill direction."""
    import backend.services.path_scoring as ps
    ps._EMBED_CACHE.clear()
    ps._EMBED_CACHE["react"] = [1.0, 0.0]
    ps._EMBED_CACHE["arima"] = [0.0, 1.0]

    user = [
        UserSkill(name="react", level="advanced"),
        UserSkill(name="arima", level="beginner"),
    ]
    centroid, _ = _compute_weighted_user_centroid(user)
    assert centroid is not None

    sim_to_react = _cosine_similarity(centroid, [1.0, 0.0])
    sim_to_arima = _cosine_similarity(centroid, [0.0, 1.0])
    assert sim_to_react > sim_to_arima
    ps._EMBED_CACHE.clear()


def test_proficiency_weights_applied_in_score_paths(mock_client):
    """React=Advanced user scores a React-heavy role higher than an ARIMA-heavy role."""
    import backend.services.path_scoring as ps
    ps._EMBED_CACHE.clear()

    ps._EMBED_CACHE["react"] = [1.0, 0.0]
    ps._EMBED_CACHE["arima"] = [0.0, 1.0]
    ps._EMBED_CACHE["React"] = [1.0, 0.0]
    ps._EMBED_CACHE["JavaScript"] = [1.0, 0.0]
    ps._EMBED_CACHE["TypeScript"] = [1.0, 0.0]
    ps._EMBED_CACHE["ARIMA"] = [0.0, 1.0]
    ps._EMBED_CACHE["Time Series"] = [0.0, 1.0]
    ps._EMBED_CACHE["Forecasting"] = [0.0, 1.0]

    role_a = occ("15-1257.00", "Web Developers")
    role_b = occ("13-1041.00", "Compliance Officers")  # 13- prefix (Business), not in 15-2 exclusion

    mock_client.search_occupations.side_effect = [
        [occ("15-1253.00")],    # zone resolution for "Frontend Developer"
        [role_a],                # keyword first result: "Web Developers"
        [role_b],                # keyword first result: "Compliance Officers"
    ]
    mock_client.get_job_zone.side_effect = by_code({
        "15-1253.00": 3, "15-1257.00": 4, "13-1041.00": 3,
    })  # current, role_a, role_b
    mock_client.get_tech_skills.side_effect = by_code({
        "15-1257.00": {"React", "JavaScript", "TypeScript"},  # role_a
        "13-1041.00": {"ARIMA", "Time Series", "Forecasting"},  # role_b (orthogonal to React)
    })
    mock_client.get_skills_profile.return_value = []

    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='["Web Developers", "Compliance Officers"]'))]
    )
    mock_openai.embeddings.create.return_value = MagicMock(data=[])

    results = score_paths(
        profile(
            current_title="Frontend Developer",
            career_status="employed",
            archetype="",
            skills=[
                UserSkill(name="react", level="advanced"),
                UserSkill(name="arima", level="beginner"),
            ],
        ),
        mock_client,
        mock_openai,
    )

    score_map = {r.onet_code: r.score for r in results}
    assert "15-1257.00" in score_map, "Web Developers should appear"
    assert "13-1041.00" in score_map, "Compliance Officers should appear"
    assert score_map["15-1257.00"] > score_map["13-1041.00"]
    ps._EMBED_CACHE.clear()


def test_beginner_proficiency_defaults_to_weight_1():
    """Unrecognized proficiency level falls back to beginner weight without error."""
    import backend.services.path_scoring as ps
    ps._EMBED_CACHE.clear()
    ps._EMBED_CACHE["skill_x"] = [1.0, 0.0]

    user = [UserSkill(name="skill_x", level="unknown")]  # type: ignore[arg-type]
    centroid, available = _compute_weighted_user_centroid(user)

    assert centroid is not None, "should not fail for unknown level"
    assert available is not None
    _, weight = available[0]
    assert weight == pytest.approx(_SKILL_LEVEL_WEIGHTS["beginner"])
    ps._EMBED_CACHE.clear()


# ---------------------------------------------------------------------------
# _role_similarity_score and role-identity anchor weighting (scoring_fix_6)
# ---------------------------------------------------------------------------


def test_role_similarity_exact_code_match_skips_embedding():
    """Exact O*NET code match returns 1.0 immediately — no embedding call needed."""
    mock_openai = MagicMock()
    score = _role_similarity_score(
        "Software Engineer", "Software Developers", "15-1252.00", "15-1252.00", mock_openai
    )
    assert score == 1.0
    mock_openai.embeddings.create.assert_not_called()


def test_stay_in_field_boosts_title_matching_candidate(mock_client):
    """stay_in_field reserves role_w=0.50.  Two candidates share identical skills/zone
    signal (overlap_score=0.0, zone_score=1.0 for both); the one that IS the user's
    own occupation (exact O*NET code match) must score materially higher than the
    other, and higher than the pre-change skills+zone-only formula would give either.
    """
    import backend.services.path_scoring as ps
    ps._EMBED_CACHE.clear()

    sw_dev = occ("15-1252.00", "Software Developers")   # matches the resolved current code
    web_dev = occ("15-1257.00", "Web Developers")        # does not match

    mock_client.get_job_family_occupations.return_value = [sw_dev, web_dev]
    mock_client.search_occupations.side_effect = [
        [occ("15-1252.00", "Software Developers")],  # resolve: current title
        [],                                            # keyword supplementary — nothing extra
    ]
    # sw_dev shares the current-resolved code, so get_job_zone("15-1252.00") is called
    # twice: once resolving the current zone (3), once scoring sw_dev as a candidate (4).
    mock_client.get_job_zone.side_effect = by_code({
        "15-1252.00": Seq(3, 4), "15-1257.00": 4,
    })  # current=3, sw_dev=4, web_dev=4
    mock_client.get_tech_skills.return_value = set()
    mock_client.get_skills_profile.return_value = []  # empty role_items → overlap_score=0.0 for both

    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='["Software Developers"]'))]
    )
    mock_openai.embeddings.create.return_value = MagicMock(data=[])  # no embeddings available

    results = score_paths(
        profile(
            current_title="Software Engineer",
            career_status="employed",
            archetype="",  # no behavioral profile — isolates the role/skills/zone terms
            move_intent="stay_in_field",
            skills=[user_skill("python", "advanced")],
        ),
        mock_client,
        mock_openai,
    )

    score_map = {r.onet_code: r.score for r in results}
    # Pre-change formula (no role term) would give 0.5*0.0 + 0.5*1.0 = 0.5 for BOTH candidates.
    assert score_map["15-1252.00"] == pytest.approx(0.75)
    assert score_map["15-1252.00"] > 0.5
    assert score_map["15-1257.00"] == pytest.approx(0.25)
    ps._EMBED_CACHE.clear()


def test_fresh_start_leaves_score_unchanged(mock_client):
    """fresh_start forces role_w=0 regardless of current_title/openai_client — regression
    guard: final score must equal the pre-change skills+zone formula exactly."""
    import backend.services.path_scoring as ps
    ps._EMBED_CACHE.clear()

    candidate = occ("15-1252.00", "Software Developers")

    mock_client.search_occupations.return_value = [occ("11-9999.00", "Some Current Role")]
    mock_client.get_bright_outlook_occupations.return_value = [candidate]
    mock_client.get_job_zone.side_effect = by_code({"11-9999.00": 3, "15-1252.00": 4})  # current=3, candidate=4
    mock_client.get_tech_skills.return_value = set()
    mock_client.get_skills_profile.return_value = []

    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='["Some Role"]'))]
    )
    mock_openai.embeddings.create.return_value = MagicMock(data=[])

    results = score_paths(
        profile(
            current_title="Product Manager",
            career_status="employed",
            archetype="",
            move_intent="fresh_start",
            skills=[],
        ),
        mock_client,
        mock_openai,
    )

    assert len(results) == 1
    # skills_w=0.5 * overlap(0.0) + zone_w=0.5 * zone_delta(+1 → 1.0), role_w forced to 0.
    assert results[0].score == pytest.approx(0.5)
    ps._EMBED_CACHE.clear()


def test_first_job_score_unaffected_by_move_intent(mock_client):
    """current_title=None (first-job) forces role_w=0 no matter what move_intent is set —
    regression guard for the path most likely to break silently."""
    import backend.services.path_scoring as ps

    def run(move_intent):
        ps._EMBED_CACHE.clear()
        m = MagicMock(spec=OnetClient)
        m.get_job_family_occupations.return_value = []
        m.get_bright_outlook_occupations.return_value = []
        m.search_occupations.return_value = [occ("43-4051.00", "Customer Rep")]
        m.get_job_zone.return_value = 2
        m.get_tech_skills.return_value = set()
        m.get_skills_profile.return_value = [onet_skill("Communication", 80.0)]

        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='["Communication"]'))]
        )
        mock_openai.embeddings.create.return_value = MagicMock(data=[])

        results = score_paths(
            profile(
                current_title=None,
                career_status="first_job",
                archetype="",
                move_intent=move_intent,
                skills=[user_skill("Communication", "intermediate")],
            ),
            m,
            mock_openai,
        )
        assert len(results) == 1
        return results[0].score

    score_stay = run("stay_in_field")
    score_none = run(None)
    score_fresh = run("fresh_start")
    assert score_stay == score_none == score_fresh
    ps._EMBED_CACHE.clear()


def test_no_openai_client_leaves_score_unchanged(mock_client):
    """openai_client=None forces role_w=0 via the same guard as fresh_start — even a
    candidate that exactly matches the resolved current O*NET code must not get a role
    boost, so substring-fallback scoring is byte-for-byte unchanged from pre-change."""
    mock_client.get_job_family_occupations.return_value = [occ("15-1252.00", "Software Developers")]
    mock_client.search_occupations.return_value = [occ("15-1252.00", "Software Developers")]
    mock_client.get_job_zone.return_value = 4  # current == candidate zone → same-zone delta
    mock_client.get_tech_skills.return_value = set()
    mock_client.get_skills_profile.return_value = [onet_skill("Python", 80.0)]

    results = score_paths(
        profile(
            current_title="Software Developer",
            career_status="employed",
            archetype="",
            move_intent="stay_in_field",
            skills=[user_skill("Python", "advanced")],
        ),
        mock_client,
        None,
    )

    assert len(results) == 1
    # substring overlap: "python" ⊂ "Python"(80) → 0.8; zone delta 0 (open/None) → 0.5.
    expected = 0.5 * 0.8 + 0.5 * 0.5
    assert results[0].score == pytest.approx(expected)


# ---------------------------------------------------------------------------
# _shape_role_similarity — concave reshape for adjacent move_intent
# ---------------------------------------------------------------------------


def test_shape_role_similarity_passthrough_for_stay_in_field_and_none():
    """stay_in_field and unspecified (None) intent keep the raw linear score —
    the sharp discrimination there is already validated and must not change."""
    assert _shape_role_similarity(0.42, "stay_in_field") == 0.42
    assert _shape_role_similarity(0.42, None) == 0.42


def test_shape_role_similarity_sqrt_for_adjacent():
    """adjacent applies sqrt: mid-range values get lifted, boundaries are fixed points."""
    assert _shape_role_similarity(0.30, "adjacent") == pytest.approx(0.30 ** 0.5)
    assert _shape_role_similarity(0.0, "adjacent") == 0.0
    assert _shape_role_similarity(1.0, "adjacent") == pytest.approx(1.0)


def test_shape_role_similarity_none_passthrough():
    """role_score=None (no anchor / embeddings unavailable) passes through unchanged
    for every intent, so the existing role_w-collapses-to-0 guard is untouched."""
    assert _shape_role_similarity(None, "adjacent") is None
    assert _shape_role_similarity(None, "stay_in_field") is None
    assert _shape_role_similarity(None, None) is None


def test_adjacent_mid_range_role_score_beats_stay_in_field_linear_treatment():
    """A mid-range role_similarity (0.2-0.4 band) must contribute more to the final
    score under adjacent's role_w×reshape than the same raw score would contribute
    under stay_in_field's role_w×raw — confirms the reshape actually broadens
    mid-range credit rather than just being a relabelled weight cut."""
    raw_role_score = 0.30

    stay_contribution = _ROLE_WEIGHT_BY_INTENT["stay_in_field"] * _shape_role_similarity(
        raw_role_score, "stay_in_field"
    )
    adjacent_contribution = _ROLE_WEIGHT_BY_INTENT["adjacent"] * _shape_role_similarity(
        raw_role_score, "adjacent"
    )

    assert adjacent_contribution > stay_contribution


def test_adjacent_near_ceiling_role_score_close_to_stay_in_field(mock_client):
    """Regression guard for the exact bug this spec fixes: a candidate with
    role_score≈1.0 (exact O*NET code match to the resolved current title) must not
    crater just because move_intent switched from stay_in_field to adjacent.
    sqrt(1.0)=1.0 keeps the reshaped value at the ceiling, and role_w only drops
    modestly (0.50→0.45), so the adjacent score must sit close to — not a
    double-digit-point crater below — the stay_in_field score."""
    import backend.services.path_scoring as ps

    def run(move_intent):
        ps._EMBED_CACHE.clear()
        sw_dev = occ("15-1252.00", "Software Developers")   # matches resolved current code
        web_dev = occ("15-1257.00", "Web Developers")        # does not match

        mock_client.get_job_family_occupations.return_value = [sw_dev, web_dev]
        mock_client.search_occupations.side_effect = [
            [occ("15-1252.00", "Software Developers")],  # resolve: current title
            [],                                            # keyword supplementary — nothing extra
        ]
        # sw_dev shares the current-resolved code — see the analogous comment in
        # test_stay_in_field_boosts_title_matching_candidate above.
        mock_client.get_job_zone.side_effect = by_code({
            "15-1252.00": Seq(3, 4), "15-1257.00": 4,
        })  # current=3, sw_dev=4, web_dev=4
        mock_client.get_tech_skills.return_value = set()
        mock_client.get_skills_profile.return_value = []  # empty role_items → overlap_score=0.0

        mock_openai = MagicMock()
        mock_openai.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='["Software Developers"]'))]
        )
        mock_openai.embeddings.create.return_value = MagicMock(data=[])

        results = score_paths(
            profile(
                current_title="Software Engineer",
                career_status="employed",
                archetype="",
                move_intent=move_intent,
                skills=[user_skill("python", "advanced")],
            ),
            mock_client,
            mock_openai,
        )
        return {r.onet_code: r.score for r in results}["15-1252.00"]

    stay_score = run("stay_in_field")
    adjacent_score = run("adjacent")

    assert stay_score == pytest.approx(0.75)
    assert adjacent_score == pytest.approx(0.725)
    assert abs(adjacent_score - stay_score) <= 0.05
    ps._EMBED_CACHE.clear()
