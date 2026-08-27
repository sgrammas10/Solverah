"""Prompt construction for the three LLM-backed assessment narratives.

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

def build_wp_narrative_prompt(
    answers: list[dict],
    wpll_answers: list[dict] | None = None,
    selected_statement_ids: list[str] | None = None,
) -> list[dict]:
    """Construct system + user messages for the Work Pulse narrative OpenAI call.

    Resolves each answer's question_id / option_id to human-readable text so the
    model receives meaningful context rather than opaque identifiers.

    Args:
        answers:                 12 WP answers, each {question_id, option_id}.
        wpll_answers:            Optional 5 earlier WPLL answers for richer context.
        selected_statement_ids:  Optional intake statement IDs for richer context.

    Returns:
        Two-element list of OpenAI chat message dicts (system, user).
    """
    # Inline question registry: id -> (dimension, question_text, {suffix -> option_text})
    _Q: dict[str, tuple[str, str, dict[str, str]]] = {
        "wp-q1": ("Fragmentation", "When you're pulled off a task mid-way through, how long does it typically take you to rebuild your focus?", {
            "a": "A few minutes — I pick back up pretty quickly",
            "b": "10–20 minutes — it takes real effort to re-orient",
            "c": "30+ minutes — I often never quite get back into flow",
            "d": "I've mostly stopped expecting deep focus — it rarely happens",
        }),
        "wp-q2": ("Sustainability", "After a tough stretch — a demanding week, a big push — how do you typically recover?", {
            "a": "A good night's sleep or a weekend usually restores me",
            "b": "It takes a few lighter days before I feel like myself",
            "c": "I struggle to fully recover before the next demand hits",
            "d": "I don't really recover — I just keep pushing through",
        }),
        "wp-q3": ("Environmental Friction", "How much of your workday feels like it exists to support other people's processes rather than your own actual work?", {
            "a": "Not much — most of my time is on real output",
            "b": "Some — maybe 20–30% feels like overhead",
            "c": "A lot — I feel like I work for the calendar, not my work",
            "d": "Almost all of it — I can barely find time to do the work itself",
        }),
        "wp-q4": ("Recognition Friction", "When your contribution feeds into a team outcome, how often does your specific role in that result get acknowledged?", {
            "a": "Usually — people know what I brought to it",
            "b": "Sometimes — depends on who's paying attention",
            "c": "Rarely — team results tend to flatten individual contributions",
            "d": "Almost never — I feel largely invisible in group work",
        }),
        "wp-q5": ("Work Pace", "How often do you find yourself working urgently toward a deadline that, in retrospect, wasn't actually urgent?", {
            "a": "Rarely — urgency in my environment is usually real",
            "b": "Sometimes — maybe once or twice a month",
            "c": "Regularly — manufactured urgency is part of the culture",
            "d": "Constantly — everything is treated as high priority",
        }),
        "wp-q6": ("Autonomy", "When you're given a clear goal, how much say do you have in how you actually get there?", {
            "a": "Full autonomy — I define the approach and execute it",
            "b": "Significant input — my preferences shape the method",
            "c": "Limited — I work within a fairly defined playbook",
            "d": "Very little — the process is usually dictated to me",
        }),
        "wp-q7": ("Autonomy", "How much control do you have over when and where you do your most focused work?", {
            "a": "A lot — I structure my day around how I work best",
            "b": "Some — I have flexibility but within real constraints",
            "c": "Not much — my schedule is largely set by others",
            "d": "None — I have no real say in my work structure",
        }),
        "wp-q8": ("Collaboration Style", "When it comes to doing your best work, you tend to…", {
            "a": "Work alone for most of it, then share when it's ready",
            "b": "Collaborate closely throughout — input at every stage",
            "c": "Start solo, then bring others in at key decision points",
            "d": "Think out loud with others — real-time collaboration is where I do my best thinking",
        }),
        "wp-q9": ("Feedback Orientation", "When someone gives you critical feedback on your work, your first instinct is…", {
            "a": "To listen and adapt — I find it genuinely useful",
            "b": "To understand their perspective before deciding what to do with it",
            "c": "To evaluate whether the source is credible before I weight it",
            "d": "To feel it first, then process it over time",
        }),
        "wp-q10": ("Role Clarity", "How clearly do you understand what success looks like in your current role?", {
            "a": "Very clearly — I know exactly what good looks like",
            "b": "Mostly — there are a few areas that feel ambiguous",
            "c": "Not very — success seems to shift depending on who's asking",
            "d": "Not at all — I'm often uncertain whether I'm doing well",
        }),
        "wp-q11": ("Growth Alignment", "How closely does your day-to-day work align with the skills or direction you actually want to grow in?", {
            "a": "Closely — I'm building the things I care about",
            "b": "Partially — some of it tracks, some of it doesn't",
            "c": "Not much — I'm developing skills I don't particularly want",
            "d": "Barely — my growth is almost entirely incidental",
        }),
        "wp-q12": ("Growth Alignment", "When you picture yourself two years from now, does your current work feel like it's moving you there?", {
            "a": "Yes — I can draw a clear line from here to there",
            "b": "Somewhat — I can see a path but it's indirect",
            "c": "Not really — I'm not sure this trajectory leads where I want",
            "d": "No — I feel like I'm moving in a different or unclear direction",
        }),
    }

    formatted_answers = []
    for ans in answers:
        q_id = ans.get("question_id", "")
        o_id = ans.get("option_id", "")
        if q_id not in _Q:
            continue
        dimension, question_text, option_map = _Q[q_id]
        suffix = o_id.split("-")[-1]  # "wp-q1-b" → "b"
        option_text = option_map.get(suffix, o_id)
        formatted_answers.append({
            "dimension": dimension,
            "question": question_text,
            "selected": option_text,
        })

    system = (
        "You are a work psychology analyst. Your task is to read a person's responses to a "
        "12-question Work Pulse assessment and produce a personalised, evidence-based narrative "
        "about how they work.\n\n"

        "STRICT OUTPUT RULES:\n"
        "- Return VALID JSON only. No markdown, no commentary, no extra keys.\n"
        "- The response MUST contain exactly these four keys: narrative, emerging_signals, archetype, archetype_description.\n"
        "- narrative: A multi-paragraph string (3–4 paragraphs). Write in second person ('you'). "
        "Tone: warm, direct, and specific — never generic. Each paragraph should illuminate a "
        "different aspect of how this person works. Separate paragraphs with \\n\\n.\n"
        "- emerging_signals: A list of 2–4 objects, each with 'title' (a short named pattern, "
        "3–6 words) and 'description' (1–2 sentences explaining what the signal means for this "
        "person). Ground each signal in specific answer patterns.\n"
        "- archetype: A 2–5 word label capturing this person's dominant work style, e.g. "
        "'Structured Deep Thinker' or 'Collaborative Momentum Builder'. Be specific, not generic.\n"
        "- archetype_description: A 2–3 sentence explanation of what this archetype means in "
        "practice — how this person naturally creates momentum, what environments tend to suit "
        "them, and where friction commonly emerges for someone with this pattern. Write in second "
        "person. Do not repeat the archetype label verbatim.\n\n"

        "QUALITY GUIDELINES:\n"
        "- Do not invent traits not supported by the answers.\n"
        "- Avoid hollow phrases like 'you thrive in dynamic environments'.\n"
        "- Where two dimensions interact (e.g. low autonomy + high fragmentation), name that tension.\n"
        "- The narrative should feel like it was written by someone who actually read every answer.\n"
        "- Do not provide medical, psychological, or legal advice.\n"
    )

    user_payload: dict = {"work_pulse_answers": formatted_answers}

    if wpll_answers:
        user_payload["earlier_work_pulse_lite_signals"] = wpll_answers

    if selected_statement_ids:
        user_payload["intake_statements_selected"] = selected_statement_ids

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload)},
    ]


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


def build_wpll_insight_prompt(answers: list[dict]) -> tuple[str, str]:
    """Construct system + user messages for the Work Pulse Lite Lite insight call.

    Resolves each answer's question_id / option_id to human-readable text so the
    model receives meaningful context rather than opaque identifiers.

    Args:
        answers: Up to 5 WPLL answers, each {question_id, option_id}.

    Returns:
        (system_message, user_message) tuple of strings.
    """
    from work_pulse.insight_engine import WP_QUESTIONS

    formatted = []
    for ans in answers:
        q_id = ans.get("question_id", "")
        o_id = ans.get("option_id", "")
        q_data = WP_QUESTIONS.get(q_id)
        if not q_data:
            continue
        suffix = o_id.split("-")[-1]  # "wpll-q1-c" → "c"
        option_text = q_data["options"].get(suffix, o_id)
        formatted.append({
            "dimension": q_data["dimension"],
            "question": q_data["text"],
            "selected": option_text,
        })

    system = (
        "You are a work psychology analyst. A person just completed a 5-question "
        "assessment about how they work. Generate a brief, personal insight based on "
        "their responses.\n\n"
        "STRICT OUTPUT RULES:\n"
        "- Return VALID JSON only. No markdown, no commentary, no extra text.\n"
        "- The response must contain exactly one key: insight_text.\n"
        "- insight_text: 2–3 sentences, written in second person ('you'). "
        "Tone: warm, direct, and specific — no generic filler, no bullet points. "
        "Name the specific patterns visible in their answers.\n\n"
        "QUALITY GUIDELINES:\n"
        "- Do not invent traits not supported by the answers.\n"
        "- Avoid hollow phrases like 'you thrive in dynamic environments'.\n"
        "- The insight should feel like it was written by someone who actually read "
        "every answer — not a template.\n"
        "- Do not provide medical, psychological, or legal advice.\n"
    )

    user = json.dumps({"answers": formatted})
    return system, user
