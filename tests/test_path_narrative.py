"""Tests for backend.services.path_narrative.

All OpenAI calls are mocked — no live network traffic in CI.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

import backend.services.path_narrative as narrative_module
from backend.services.path_narrative import (
    NarrativeGenerationError,
    PathSuggestion,
    UserContext,
    _build_prompt,
    _format_management_prefs,
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
