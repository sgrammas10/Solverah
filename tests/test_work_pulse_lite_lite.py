"""Unit tests for the WPLL rules engine, ``work_pulse/insight_engine.py``.

The teaser this engine scored is retired (2026-11-23, with ``/start``): its
endpoint tests are gone, and the retirement itself is pinned in
``test_wpll_result.py``. The engine stays because Pulse reads its
``QUESTION_DIMENSIONS``; these tests keep the rest honest while it remains.
"""

from work_pulse.insight_engine import (
    INSIGHT_TEMPLATES,
    score_answers,
    select_template,
)


def test_score_answers_skips_null_ids():
    scores = score_answers([
        {"question_id": "wpll-q1", "option_id": None},
        {"question_id": None, "option_id": "wpll-q2-d"},
        "not-an-object",
    ])
    assert all(v == 0 for v in scores.values())


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
