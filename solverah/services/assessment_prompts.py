"""Prompt construction for the LLM-backed assessment narratives.

One since 2026-11-23: ManagerMatch. The original Work Pulse's narrative
prompt was deleted when that instrument was retired (2026-10-02), and the WPLL
teaser's when the anonymous teaser was (2026-11-23).

Moved verbatim from ``app.py``.  These are pure string builders -- they take
answers and return the messages to send -- so they are unit-testable without a
network, an app context, or an API key, which they were not while they sat
between route handlers.

They stay in ``services/`` rather than ``domain/`` because a prompt is a
provider-shaped artefact: the message-role structure and the
``response_format={"type": "json_object"}`` contract they are written against
belong to a specific vendor API, not to the business rules.
"""

from __future__ import annotations

import json


def build_mm_narrative_prompt(
    answers: list[dict],
    archetype: str,
    dimension_scores: dict[str, float],
) -> list[dict]:
    """Construct system + user messages for the ManagerMatch narrative OpenAI call.

    Maps each answer's question_id to human-readable option text so the model
    sees real sentences rather than IDs.

    Args:
        answers:          15 ManagerMatch answers, each {question_id, choice}.
        archetype:        The classified archetype string.
        dimension_scores: Four dimension floats from score_manager_match.

    Returns:
        Two-element list of OpenAI chat message dicts (system, user).
    """
    from manager_match.questions import QUESTIONS

    q_lookup = {q["question_id"]: q for q in QUESTIONS}

    formatted_answers = []
    for ans in answers:
        q_id = ans.get("question_id", "")
        choice = ans.get("choice", "")
        q = q_lookup.get(q_id)
        if not q:
            continue
        option_text = q["option_a_text"] if choice == "a" else q["option_b_text"]
        formatted_answers.append({
            "question_id": q_id,
            "dimension": q["dimension"],
            "selected": option_text,
        })

    system = (
        "You are Solverah's ManagerMatch engine. Based on a user's forced-choice "
        "assessment responses, generate a personalised management style analysis. "
        "Write in second person (\"you\"). Be specific — never generic. Reference "
        "patterns from their actual answers. Return a JSON object with exactly these "
        "four keys: narrative (2–3 paragraphs describing the user's management "
        "preferences and why they work that way — do not open with the archetype "
        "name), what_to_look_for (list of 3–4 concrete strings the user can probe "
        "for in interviews), red_flags (list of 2–3 management behaviours that will "
        "create friction for this person), archetype_description (2 sentences — what "
        "this archetype means in practice for this user)."
    )

    user_payload = {
        "archetype": archetype,
        "dimension_scores": {
            f"{k} (0.0–1.0)": round(v, 3) for k, v in dimension_scores.items()
        },
        "answers": formatted_answers,
    }

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload)},
    ]

