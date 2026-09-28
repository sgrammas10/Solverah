"""Tests for backend.services.path_narrative.

All OpenAI calls are mocked — no live network traffic in CI.
"""
from __future__ import annotations

import json
import re
import threading
from unittest.mock import MagicMock

import pytest

import backend.services.path_narrative as narrative_module
from backend.services.path_narrative import (
    NarrativeGenerationError,
    PathSuggestion,
    UserContext,
    _build_prompt,
    _format_management_prefs,
    _scrub_grades,
    _validate_response,
    generate_narratives,
)
from backend.services.path_scoring import ScoredPath


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def scored_path(code: str, title: str = "A Role", score: float = 0.75) -> ScoredPath:
    return ScoredPath(
        onet_code=code,
        title=title,
        score=score,
        overlapping_skills=["Python", "SQL"],
    )


def user_ctx(**kwargs) -> UserContext:
    defaults = {
        "archetype": "Deep Diver",
        "management_preferences": {
            "archetype": "The Autonomist",
            "dimension_scores": {"autonomy": 0.75, "feedback_style": 0.30},
        },
        "career_status": "employed",
        "top_skills": ["Python", "SQL"],
    }
    defaults.update(kwargs)
    return UserContext(**defaults)


# Realistic LLM response that matches all five candidates from the default fixture.
VALID_LLM_RESPONSE = {
    "suggestions": [
        {
            "onet_code": "15-1211.00",
            "title": "Computer Systems Analysts",
            "why_text": (
                "Your Python expertise maps directly to this role, and it represents "
                "a natural forward step from where you are now."
            ),
            "profile_dimensions": [
                "Builds on your Python skills",
                "Matches your Deep Diver archetype",
                "Forward progression into zone 4",
            ],
        },
        {
            "onet_code": "15-2051.00",
            "title": "Data Scientists",
            "why_text": (
                "Combining your SQL and Python skills with data science would open new "
                "growth paths while leveraging what you already do well."
            ),
            "profile_dimensions": [
                "Leverages your SQL expertise",
                "Fits your autonomy preference",
            ],
        },
        {
            "onet_code": "11-3021.00",
            "title": "IT Managers",
            "why_text": (
                "Your technical background positions you well to lead engineering teams "
                "and drive delivery across complex projects."
            ),
            "profile_dimensions": [
                "Leadership growth opportunity",
                "Leverages your Python experience",
            ],
        },
        {
            "onet_code": "15-1299.00",
            "title": "Software Quality Analysts",
            "why_text": (
                "Your attention to detail and Python skills make quality engineering "
                "a strong lateral move with clear upward potential."
            ),
            "profile_dimensions": [
                "Builds on your Python skills",
                "Suits your analytical style",
            ],
        },
        {
            "onet_code": "13-1161.00",
            "title": "Market Research Analysts",
            "why_text": (
                "Your SQL and data skills transfer directly into market research, "
                "opening doors in a new domain."
            ),
            "profile_dimensions": [
                "Leverages your SQL expertise",
                "Broadens your career direction",
            ],
        },
    ]
}

DEFAULT_CANDIDATES = [
    scored_path("15-1211.00", "Computer Systems Analysts", score=0.82),
    scored_path("15-2051.00", "Data Scientists", score=0.77),
    scored_path("11-3021.00", "IT Managers", score=0.65),
    scored_path("15-1299.00", "Software Quality Analysts", score=0.60),
    scored_path("13-1161.00", "Market Research Analysts", score=0.45),
]


def _make_openai_response(json_data: dict) -> MagicMock:
    """Return a mock openai response object with json_data as the content."""
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(json_data)
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    return mock_resp


def _patch_client(monkeypatch, *, return_json=None, side_effects=None) -> MagicMock:
    """Patch _get_openai_client in the narrative module."""
    mock_client = MagicMock()
    if side_effects is not None:
        mock_client.chat.completions.create.side_effect = side_effects
    else:
        mock_client.chat.completions.create.return_value = _make_openai_response(
            return_json if return_json is not None else VALID_LLM_RESPONSE
        )
    monkeypatch.setattr(narrative_module, "_get_openai_client", lambda: mock_client)
    return mock_client


# ---------------------------------------------------------------------------
# _format_management_prefs
# ---------------------------------------------------------------------------


class TestFormatManagementPrefs:
    def test_empty_dict(self):
        assert _format_management_prefs({}) == "Not provided."

    def test_includes_archetype(self):
        result = _format_management_prefs({"archetype": "The Challenger"})
        assert "The Challenger" in result

    def test_includes_dimension_scores(self):
        prefs = {
            "archetype": "The Autonomist",
            "dimension_scores": {"autonomy": 0.75, "feedback_style": 0.30},
        }
        result = _format_management_prefs(prefs)
        assert "0.75" in result
        assert "0.30" in result

    def test_dimension_label_replaces_underscores(self):
        result = _format_management_prefs(
            {"dimension_scores": {"feedback_style": 0.5}}
        )
        assert "Feedback Style" in result


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def test_returns_system_and_user_messages(self):
        msgs = _build_prompt(DEFAULT_CANDIDATES, user_ctx())
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"

    def test_system_contains_candidate_only_rule(self):
        msgs = _build_prompt(DEFAULT_CANDIDATES, user_ctx())
        assert "ONLY" in msgs[0]["content"]
        assert "candidate list" in msgs[0]["content"]

    def test_user_message_contains_all_candidate_codes(self):
        msgs = _build_prompt(DEFAULT_CANDIDATES, user_ctx())
        user_msg = msgs[1]["content"]
        for c in DEFAULT_CANDIDATES:
            assert c.onet_code in user_msg

    def test_user_message_contains_context_fields(self):
        msgs = _build_prompt(DEFAULT_CANDIDATES, user_ctx())
        user_msg = msgs[1]["content"]
        assert "Deep Diver" in user_msg
        assert "employed" in user_msg
        assert "Python" in user_msg

    def test_user_message_handles_empty_top_skills(self):
        msgs = _build_prompt(DEFAULT_CANDIDATES, user_ctx(top_skills=[]))
        assert "none listed" in msgs[1]["content"]


# ---------------------------------------------------------------------------
# W-13: no score in the prompt, and no grade out of it (ruling flag 12)
# ---------------------------------------------------------------------------


class TestThePromptCarriesNoScore:
    """Ruling flag 12's first half: a model handed a number writes about it.

    The third browser test found "...making it a strong fit for your
    background." on a Database Administrators card. The prompt was handing the
    narrator ``match_score`` per candidate and calling the list "sorted by
    match_score, highest first".
    """

    def test_no_candidate_carries_a_score_field(self):
        msgs = _build_prompt(DEFAULT_CANDIDATES, user_ctx())
        assert "match_score" not in msgs[1]["content"]
        assert "match_score" not in msgs[0]["content"]

    def test_no_candidate_score_value_reaches_the_prompt(self):
        msgs = _build_prompt(DEFAULT_CANDIDATES, user_ctx())
        for candidate in DEFAULT_CANDIDATES:
            assert str(candidate.score) not in msgs[1]["content"]

    def test_the_order_is_still_stated_without_naming_a_score(self):
        # The ranking has not stopped existing -- it is just not a number the
        # narrator is shown.
        msgs = _build_prompt(DEFAULT_CANDIDATES, user_ctx())
        assert "order" in msgs[1]["content"]
        assert [c.onet_code for c in DEFAULT_CANDIDATES] == re.findall(
            r'"onet_code": "([^"]+)"', msgs[1]["content"]
        )

    def test_the_system_prompt_forbids_grading(self):
        system = _build_prompt(DEFAULT_CANDIDATES, user_ctx())[0]["content"]
        assert "NEVER rate, rank or grade the fit" in system


class TestScrubGrades:
    """The deterministic half. A prompt is a request; this is the guarantee."""

    def test_a_trailing_graded_clause_is_dropped(self):
        assert _scrub_grades(
            "Database administrators keep an organisation's data available and "
            "secure, making it a strong fit for your background."
        ) == "Database administrators keep an organisation's data available and secure."

    def test_a_sentence_that_is_only_a_grade_is_dropped_whole(self):
        assert _scrub_grades("A great fit.") == ""

    def test_a_leading_graded_clause_is_cut_off_the_front(self):
        assert _scrub_grades("Strong match: uses your Python.") == "Uses your Python."

    def test_a_clean_sentence_is_untouched(self):
        clean = (
            "You would design and maintain the databases an organisation runs "
            "on, using your SQL every day."
        )
        assert _scrub_grades(clean) == clean

    def test_matches_as_a_verb_about_an_archetype_is_not_a_grade(self):
        # Rule 4's own example tag. A word list that caught "matches" would
        # empty the tags of every card on the page.
        assert (
            _scrub_grades("Matches your Deep Diver archetype")
            == "Matches your Deep Diver archetype"
        )

    def test_a_clean_tag_keeps_its_exact_text_and_gains_no_full_stop(self):
        assert _scrub_grades("Builds on your Python skills") == "Builds on your Python skills"

    def test_a_percentage_is_scrubbed(self):
        assert _scrub_grades("95% overlap with your skills") == ""

    def test_an_explicit_score_is_scrubbed_decimal_point_and_all(self):
        # The decimal point is not a sentence boundary: splitting on it would
        # keep "82 for this path."
        assert _scrub_grades("Your fit score is 0.82 for this path.") == ""

    def test_only_the_graded_sentence_of_two_is_dropped(self):
        assert (
            _scrub_grades("You would lead a team of analysts. It is the top choice for you.")
            == "You would lead a team of analysts."
        )

    def test_a_graded_tail_after_and_is_cut(self):
        assert (
            _scrub_grades(
                "Network engineers keep traffic moving between sites, and it is "
                "highly suitable for you."
            )
            == "Network engineers keep traffic moving between sites."
        )

    def test_an_excellent_match_sentence_is_dropped(self):
        assert (
            _scrub_grades("This role is an excellent match for someone with your experience.")
            == ""
        )

    def test_prose_with_no_grading_survives_verbatim(self):
        assert (
            _scrub_grades("You would write and review code all day.")
            == "You would write and review code all day."
        )

    def test_empty_input_is_empty_output(self):
        assert _scrub_grades("") == ""
        assert _scrub_grades("   ") == ""


class TestFourthUserTestPhrasings:
    """W-15: three phrasings the fourth user test found on real narrator output.

    The list had "well aligned" but not the verb the other way round, and it
    had no family for praising the MOVE ("a great opportunity") rather than the
    fit. The tester's words are embedded verbatim; the prose around each is the
    shape the narrator writes.
    """

    def test_aligning_well_with_your_technical_skills_is_cut(self):
        assert (
            _scrub_grades(
                "Data engineers build the pipelines that move data between "
                "systems, aligning well with your technical skills."
            )
            == "Data engineers build the pipelines that move data between systems."
        )

    def test_its_a_great_opportunity_is_dropped(self):
        assert (
            _scrub_grades(
                "You would design cloud infrastructure for product teams. "
                "It's a great opportunity to use your AWS experience."
            )
            == "You would design cloud infrastructure for product teams."
        )

    def test_its_an_excellent_way_to_grow_is_dropped(self):
        assert (
            _scrub_grades(
                "You would plan and track releases across several teams. "
                "It's an excellent way to grow your leadership skills."
            )
            == "You would plan and track releases across several teams."
        )

    @pytest.mark.parametrize(
        "sentence",
        [
            "It aligns closely with your SQL work.",
            "Your background aligned perfectly with this.",
            "This aligns strongly with your experience.",
            "A perfect step for you.",
            "A fantastic move for someone like you.",
            "An ideal path forward.",
            "A wonderful chance to lead.",
            "An amazing option for you.",
            "You are well positioned for this.",
            "You are perfectly placed to do it.",
            "You are ideally equipped for the work.",
        ],
    )
    def test_the_rest_of_each_new_family_is_scrubbed(self, sentence):
        assert _scrub_grades(sentence) == ""

    @pytest.mark.parametrize(
        "tag", ["Fits your AWS experience", "Matches your Deep Diver archetype"]
    )
    def test_tags_that_name_a_skill_or_trait_survive(self, tag):
        assert _scrub_grades(tag) == tag

    def test_the_prompt_no_longer_asks_for_encouraging_prose(self):
        system = _build_prompt(DEFAULT_CANDIDATES, user_ctx())[0]["content"]
        assert "encouraging" not in system.lower()
        assert (
            "concrete: what the work involves and which of their skills it uses"
            in system
        )


class TestGradesNeverReachTheWire:
    """End to end through the fake client: what `generate_narratives` returns."""

    GRADED = {
        "suggestions": [
            {
                "onet_code": "15-1211.00",
                "title": "Database Administrators",
                "why_text": (
                    "Database administrators keep systems reliable, making it a "
                    "strong fit for your background."
                ),
                "profile_dimensions": [
                    "Builds on your Python skills",
                    "95% overlap with your skills",
                ],
            }
        ]
    }
    ONLY_A_GRADE = {
        "suggestions": [
            {
                "onet_code": "15-1211.00",
                "title": "Database Administrators",
                "why_text": "A great fit.",
                "profile_dimensions": ["Matches your Deep Diver archetype", "A perfect match"],
            }
        ]
    }

    def test_a_graded_narrative_lands_scrubbed(self, monkeypatch):
        _patch_client(monkeypatch, return_json=self.GRADED)
        [result] = generate_narratives([scored_path("15-1211.00")], user_ctx())

        assert result.why_text == "Database administrators keep systems reliable."
        assert result.profile_dimensions == ["Builds on your Python skills"]

    def test_a_narrative_that_was_all_grade_falls_back_to_the_overlap_sentence(
        self, monkeypatch
    ):
        # The same sentence `intelligence_service._describe` writes for a card
        # the re-rank surfaced with no narrative -- imported, not copied.
        from solverah.services.intelligence_service import _overlap_sentence

        _patch_client(monkeypatch, return_json=self.ONLY_A_GRADE)
        [result] = generate_narratives([scored_path("15-1211.00")], user_ctx())

        assert result.why_text == _overlap_sentence(["Python", "SQL"])
        assert result.why_text == "Uses your Python and SQL."
        assert result.profile_dimensions == ["Matches your Deep Diver archetype"]

    def test_the_scrub_is_logged_once_with_the_codes(self, monkeypatch, caplog):
        _patch_client(monkeypatch, return_json=self.GRADED)
        with caplog.at_level("WARNING", logger="backend.services.path_narrative"):
            generate_narratives([scored_path("15-1211.00")], user_ctx())

        scrubbed = [r for r in caplog.records if r.message == "path_narrative_grade_scrubbed"]
        assert len(scrubbed) == 1
        assert scrubbed[0].codes == ["15-1211.00"]

    def test_a_clean_batch_logs_nothing(self, monkeypatch, caplog):
        _patch_client(monkeypatch)
        with caplog.at_level("WARNING", logger="backend.services.path_narrative"):
            generate_narratives(DEFAULT_CANDIDATES, user_ctx())

        assert [r for r in caplog.records if r.message == "path_narrative_grade_scrubbed"] == []


# ---------------------------------------------------------------------------
# _validate_response
# ---------------------------------------------------------------------------


class TestValidateResponse:
    VALID_CODES = {"15-1211.00", "15-2051.00", "11-3021.00", "15-1299.00", "13-1161.00"}

    def test_valid_response_returns_suggestions(self):
        result = _validate_response(VALID_LLM_RESPONSE, self.VALID_CODES)
        assert len(result) == 5
        assert all(isinstance(s, PathSuggestion) for s in result)

    def test_maps_fields_correctly(self):
        result = _validate_response(VALID_LLM_RESPONSE, self.VALID_CODES)
        first = result[0]
        assert first.onet_code == "15-1211.00"
        assert first.title == "Computer Systems Analysts"
        assert len(first.why_text) > 0
        assert isinstance(first.profile_dimensions, list)

    def test_raises_if_suggestions_missing(self):
        with pytest.raises(ValueError, match="suggestions"):
            _validate_response({}, self.VALID_CODES)

    def test_raises_if_suggestions_not_a_list(self):
        with pytest.raises(ValueError, match="list"):
            _validate_response({"suggestions": "bad"}, self.VALID_CODES)

    def test_raises_if_suggestions_empty(self):
        with pytest.raises(ValueError, match="empty"):
            _validate_response({"suggestions": []}, self.VALID_CODES)

    def test_raises_if_count_mismatches(self):
        # Fewer suggestions than valid_codes → rejected
        data = {"suggestions": VALID_LLM_RESPONSE["suggestions"][:3]}
        with pytest.raises(ValueError, match="expected 5 suggestions, got 3"):
            _validate_response(data, self.VALID_CODES)

    def test_raises_if_duplicate_code(self):
        duped = [*VALID_LLM_RESPONSE["suggestions"]]
        duped[1] = {**duped[0]}  # duplicate of index 0
        with pytest.raises(ValueError, match="more than once"):
            _validate_response({"suggestions": duped}, self.VALID_CODES)

    def test_raises_if_code_not_in_candidates(self):
        # Use a 3-item valid_codes (without the bad code) so length check passes
        three_codes = {"15-1211.00", "15-2051.00", "11-3021.00"}
        data = {
            "suggestions": [
                {**VALID_LLM_RESPONSE["suggestions"][0], "onet_code": "99-9999.00"},
                VALID_LLM_RESPONSE["suggestions"][1],
                VALID_LLM_RESPONSE["suggestions"][2],
            ]
        }
        with pytest.raises(ValueError, match="99-9999.00"):
            _validate_response(data, three_codes)

    def test_raises_if_required_key_missing(self):
        three_codes = {"15-1211.00", "15-2051.00", "11-3021.00"}
        bad = {"onet_code": "15-1211.00", "title": "CS Analysts"}  # missing why_text etc.
        data = {"suggestions": [bad, VALID_LLM_RESPONSE["suggestions"][1], VALID_LLM_RESPONSE["suggestions"][2]]}
        with pytest.raises(ValueError, match="why_text"):
            _validate_response(data, three_codes)

    def test_raises_if_profile_dimensions_too_short(self):
        three_codes = {"15-1211.00", "15-2051.00", "11-3021.00"}
        bad = {**VALID_LLM_RESPONSE["suggestions"][0], "profile_dimensions": ["only one"]}
        data = {"suggestions": [bad, VALID_LLM_RESPONSE["suggestions"][1], VALID_LLM_RESPONSE["suggestions"][2]]}
        with pytest.raises(ValueError, match="profile_dimensions"):
            _validate_response(data, three_codes)


# ---------------------------------------------------------------------------
# generate_narratives — integration tests
# ---------------------------------------------------------------------------


class TestGenerateNarratives:
    def test_returns_path_suggestions_with_correct_shape(self, monkeypatch):
        _patch_client(monkeypatch)
        results = generate_narratives(DEFAULT_CANDIDATES, user_ctx())

        assert len(results) == len(DEFAULT_CANDIDATES)
        for s in results:
            assert isinstance(s, PathSuggestion)
            assert s.onet_code
            assert s.title
            assert len(s.why_text) > 0
            assert isinstance(s.profile_dimensions, list)
            assert len(s.profile_dimensions) >= 2

    def test_all_returned_codes_exist_in_input_candidates(self, monkeypatch):
        _patch_client(monkeypatch)
        results = generate_narratives(DEFAULT_CANDIDATES, user_ctx())

        input_codes = {c.onet_code for c in DEFAULT_CANDIDATES}
        for suggestion in results:
            assert suggestion.onet_code in input_codes, (
                f"Returned code {suggestion.onet_code!r} not in input candidates"
            )

    def test_uses_json_object_response_format(self, monkeypatch):
        mock_client = _patch_client(monkeypatch)
        generate_narratives(DEFAULT_CANDIDATES, user_ctx())

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs.get("response_format") == {"type": "json_object"}

    def test_retries_once_on_malformed_first_response(self, monkeypatch):
        malformed_response = _make_openai_response({"wrong_key": []})
        valid_response = _make_openai_response(VALID_LLM_RESPONSE)
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [malformed_response, valid_response]
        monkeypatch.setattr(narrative_module, "_get_openai_client", lambda: mock_client)

        results = generate_narratives(DEFAULT_CANDIDATES, user_ctx())

        assert mock_client.chat.completions.create.call_count == 2
        assert len(results) == len(DEFAULT_CANDIDATES)

    def test_retries_once_on_invalid_json_first_response(self, monkeypatch):
        # First response returns raw non-JSON text
        bad_choice = MagicMock()
        bad_choice.message.content = "not valid json {"
        bad_resp = MagicMock()
        bad_resp.choices = [bad_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            bad_resp,
            _make_openai_response(VALID_LLM_RESPONSE),
        ]
        monkeypatch.setattr(narrative_module, "_get_openai_client", lambda: mock_client)

        results = generate_narratives(DEFAULT_CANDIDATES, user_ctx())
        assert len(results) == len(DEFAULT_CANDIDATES)

    def test_raises_narrative_error_when_both_attempts_fail(self, monkeypatch):
        malformed = _make_openai_response({"bad": "response"})
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = malformed
        monkeypatch.setattr(narrative_module, "_get_openai_client", lambda: mock_client)

        with pytest.raises(NarrativeGenerationError, match="malformed"):
            generate_narratives(DEFAULT_CANDIDATES, user_ctx())

        assert mock_client.chat.completions.create.call_count == 2

    def test_raises_immediately_on_empty_candidates(self, monkeypatch):
        _patch_client(monkeypatch)
        with pytest.raises(NarrativeGenerationError, match="empty"):
            generate_narratives([], user_ctx())

    def test_error_message_includes_last_failure_reason(self, monkeypatch):
        malformed = _make_openai_response({"suggestions": "not a list"})
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = malformed
        monkeypatch.setattr(narrative_module, "_get_openai_client", lambda: mock_client)

        with pytest.raises(NarrativeGenerationError) as exc_info:
            generate_narratives(DEFAULT_CANDIDATES, user_ctx())

        assert str(exc_info.value)  # non-empty error message

    def test_respects_openai_narrative_model_env_var(self, monkeypatch):
        monkeypatch.setenv("OPENAI_NARRATIVE_MODEL", "gpt-4o")
        mock_client = _patch_client(monkeypatch)

        generate_narratives(DEFAULT_CANDIDATES, user_ctx())

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs.get("model") == "gpt-4o"

    def test_works_with_first_job_career_status(self, monkeypatch):
        _patch_client(monkeypatch)
        ctx = user_ctx(career_status="first_job")
        results = generate_narratives(DEFAULT_CANDIDATES, ctx)
        assert len(results) >= 2

    def test_works_with_empty_management_preferences(self, monkeypatch):
        _patch_client(monkeypatch)
        ctx = user_ctx(management_preferences={})
        results = generate_narratives(DEFAULT_CANDIDATES, ctx)
        assert len(results) >= 2

    def test_llm_called_exactly_once_on_success(self, monkeypatch):
        mock_client = _patch_client(monkeypatch)
        generate_narratives(DEFAULT_CANDIDATES, user_ctx())
        assert mock_client.chat.completions.create.call_count == 1

    def test_profile_dimensions_are_strings(self, monkeypatch):
        _patch_client(monkeypatch)
        results = generate_narratives(DEFAULT_CANDIDATES, user_ctx())
        for s in results:
            assert all(isinstance(d, str) for d in s.profile_dimensions)


# ---------------------------------------------------------------------------
# _build_prompt — preferences section
# ---------------------------------------------------------------------------


class TestBuildPromptPreferences:
    def test_preferences_section_included_when_set(self):
        ctx = user_ctx(move_intent="fresh_start", seniority_intent="move_up", priority="learning_growth")
        msgs = _build_prompt([scored_path("15-1252.00")], ctx)
        user_content = msgs[1]["content"]
        assert "Fresh direction" in user_content
        assert "Looking to move up" in user_content
        assert "Learning & growth" in user_content
        assert "Preferences" in user_content

    def test_preferences_section_omitted_when_none(self):
        ctx = user_ctx()  # all None by default
        msgs = _build_prompt([scored_path("15-1252.00")], ctx)
        user_content = msgs[1]["content"]
        assert "Preferences" not in user_content

    def test_partial_preferences_still_included(self):
        ctx = user_ctx(move_intent="stay_in_field")
        msgs = _build_prompt([scored_path("15-1252.00")], ctx)
        user_content = msgs[1]["content"]
        assert "Stay in my field" in user_content
        assert "Preferences" in user_content

    def test_all_label_mappings_render(self):
        cases = [
            ("stay_in_field", "Stay in my field"),
            ("adjacent", "Something adjacent"),
            ("fresh_start", "Fresh direction"),
        ]
        for value, expected_label in cases:
            ctx = user_ctx(move_intent=value)
            msgs = _build_prompt([scored_path("15-1252.00")], ctx)
            assert expected_label in msgs[1]["content"]


# ---------------------------------------------------------------------------
# generate_narratives_batched (W-12)
# ---------------------------------------------------------------------------


def _deep_candidates(n: int = 20) -> list[ScoredPath]:
    return [scored_path("15-00%02d.00" % i, "Role %d" % i) for i in range(n)]


def _codes_in(messages) -> list[str]:
    """The candidate codes a narrator call was asked about, in prompt order."""
    return re.findall(r'"onet_code": "([^"]+)"', messages[1]["content"])


def _batching_client(monkeypatch, *, fail_when=None, barrier=None):
    """A narrator double that answers whatever codes it is handed.

    Returns the list of per-call code lists, which is what the batching
    assertions are about.  Failure is keyed on CONTENT and not on call order,
    because the batches run on threads and arrive in whichever order the
    provider answers.
    """
    calls: list[list[str]] = []
    guard = threading.Lock()

    def create(*, model, messages, response_format, **_):
        codes = _codes_in(messages)
        with guard:
            calls.append(codes)
        if barrier is not None:
            barrier.wait()
        if fail_when is not None and fail_when(codes):
            raise RuntimeError("the provider is down")
        return _make_openai_response(
            {
                "suggestions": [
                    {
                        "onet_code": code,
                        "title": "Role %s" % code,
                        "why_text": "Written for %s." % code,
                        "profile_dimensions": [
                            "Builds on your Python skills",
                            "Fits your autonomy preference",
                        ],
                    }
                    for code in codes
                ]
            }
        )

    client = MagicMock()
    client.chat.completions.create.side_effect = create
    monkeypatch.setattr(narrative_module, "_get_openai_client", lambda: client)
    return calls


class TestBatchedNarratives:
    """W-12: twenty cards narrated as two parallel tens, best-effort per batch.

    Measured before it was built (three F-2 profiles, the real API): ten cards
    10.35 / 11.09 / 10.35 s, two batches of ten on threads 11.87 / 9.37 / 9.96 s
    -- a mean difference of -0.20 s -- and twenty in ONE completion 17.72 /
    18.58 / 18.87 s.  The parallelism is the whole saving, which is why it is
    pinned here rather than assumed.
    """

    def test_twenty_candidates_go_out_as_two_batches_of_ten(self, monkeypatch):
        calls = _batching_client(monkeypatch)
        candidates = _deep_candidates(20)

        result = narrative_module.generate_narratives_batched(candidates, user_ctx())

        assert len(calls) == 2, "one completion per batch, and no more"
        assert sorted(len(codes) for codes in calls) == [10, 10]
        assert sorted(calls, key=lambda codes: codes[0]) == [
            [c.onet_code for c in candidates[:10]],
            [c.onet_code for c in candidates[10:]],
        ]
        assert [s.onet_code for s in result] == [
            c.onet_code for c in candidates
        ], "the caller slices the page off the front, so order survives the fan-out"

    def test_the_batches_actually_run_at_the_same_time(self, monkeypatch):
        """A barrier rather than a stopwatch.

        Both calls must be in flight together for the barrier to release; if the
        second only started after the first returned, it times out and this test
        fails instead of passing slowly.
        """
        barrier = threading.Barrier(2, timeout=10)
        _batching_client(monkeypatch, barrier=barrier)

        result = narrative_module.generate_narratives_batched(
            _deep_candidates(20), user_ctx()
        )

        assert len(result) == 20
        assert not barrier.broken

    def test_a_failing_second_batch_still_lands_the_first_ten(self, monkeypatch):
        """The reserve is a nice-to-have; the page is the product."""
        candidates = _deep_candidates(20)
        second = {c.onet_code for c in candidates[10:]}
        _batching_client(monkeypatch, fail_when=lambda codes: codes[0] in second)

        result = narrative_module.generate_narratives_batched(candidates, user_ctx())

        assert [s.onet_code for s in result] == [c.onet_code for c in candidates[:10]]

    def test_a_failing_first_batch_still_lands_the_second_ten(self, monkeypatch):
        """This function privileges no batch -- `path_suggestions` is what decides
        that the missing one was the page and answers 500.  Keeping that judgement
        in one place is why this one is symmetric.
        """
        candidates = _deep_candidates(20)
        first = {c.onet_code for c in candidates[:10]}
        _batching_client(monkeypatch, fail_when=lambda codes: codes[0] in first)

        result = narrative_module.generate_narratives_batched(candidates, user_ctx())

        assert [s.onet_code for s in result] == [c.onet_code for c in candidates[10:]]

    def test_a_malformed_batch_is_dropped_rather_than_raised(self, monkeypatch):
        """The narrator's own retry runs first; what reaches the pool is the
        second failure, and it must not take the other batch down with it.
        """
        mock_client = MagicMock()
        candidates = _deep_candidates(20)
        second = {c.onet_code for c in candidates[10:]}

        def create(*, model, messages, response_format, **_):
            codes = _codes_in(messages)
            if codes[0] in second:
                return _make_openai_response({"suggestions": "not a list"})
            return _make_openai_response(
                {
                    "suggestions": [
                        {
                            "onet_code": code,
                            "title": "Role",
                            "why_text": "Because.",
                            "profile_dimensions": ["One", "Two"],
                        }
                        for code in codes
                    ]
                }
            )

        mock_client.chat.completions.create.side_effect = create
        monkeypatch.setattr(narrative_module, "_get_openai_client", lambda: mock_client)

        result = narrative_module.generate_narratives_batched(candidates, user_ctx())

        assert len(result) == 10

    def test_ten_candidates_are_the_same_single_call_as_before(self, monkeypatch):
        """A job that scores fewer than eleven must be unchanged, not equivalent:
        no pool, no thread, the one completion `generate_narratives` always made.
        """
        calls = _batching_client(monkeypatch)

        result = narrative_module.generate_narratives_batched(
            _deep_candidates(10), user_ctx()
        )

        assert len(calls) == 1
        assert len(result) == 10

    def test_an_uneven_tail_is_its_own_batch(self, monkeypatch):
        calls = _batching_client(monkeypatch)

        narrative_module.generate_narratives_batched(_deep_candidates(13), user_ctx())

        assert sorted(len(codes) for codes in calls) == [3, 10]

    def test_nothing_to_narrate_is_empty_rather_than_an_error(self, monkeypatch):
        """Unlike `generate_narratives`: here the batches are derived from what
        the scorer returned, so "none" is a state rather than a caller mistake.
        """
        calls = _batching_client(monkeypatch)

        assert narrative_module.generate_narratives_batched([], user_ctx()) == []
        assert calls == []
