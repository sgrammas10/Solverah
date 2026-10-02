"""Rules-based insight engine for Work Pulse Lite Lite (5-question teaser).

Scores each answered dimension on 0-3, selects the most relevant template,
and returns a fixed set of locked section titles. No LLM calls — pure lookup.
"""

QUESTION_DIMENSIONS: dict[str, str] = {
    "wpll-q1": "fragmentation",
    "wpll-q2": "sustainability",
    "wpll-q3": "environmental_friction",
    "wpll-q4": "recognition_friction",
    "wpll-q5": "work_pace",
}

OPTION_SCORES: dict[str, int] = {
    "a": 0,
    "b": 1,
    "c": 2,
    "d": 3,
}

# Lower index = higher priority; used to build combo keys and break score ties.
PRIORITY_ORDER: list[str] = [
    "fragmentation",
    "sustainability",
    "recognition_friction",
    "environmental_friction",
    "work_pace",
]

INSIGHT_TEMPLATES: dict[str, str] = {
    # ── Single dimension dominant ─────────────────────────────────────────────
    "fragmentation": (
        "Your responses suggest a high-fragmentation work environment — you're likely absorbing "
        "context-switching costs that compound throughout the day, affecting both focus quality "
        "and end-of-day energy. This pattern often runs quietly in the background, making it "
        "easy to attribute the drain to something else entirely."
    ),
    "sustainability": (
        "There are clear signs that your current work demands are exceeding what feels "
        "maintainable over time — not dramatically, but steadily. The gap between what the "
        "role requires and what feels sustainable tends to widen gradually, which makes it "
        "harder to name until the depletion is significant."
    ),
    "environmental_friction": (
        "Your environment appears to be generating meaningful background friction — the kind "
        "that rarely shows up in a job description but shapes every working hour. When the "
        "physical or process context fights against how you naturally operate, the extra effort "
        "required often goes uncounted and unacknowledged."
    ),
    "recognition_friction": (
        "Your responses point to work that isn't being fully seen or accurately evaluated — "
        "a pattern that quietly erodes motivation even when the work itself remains "
        "meaningful. Over time, the absence of calibrated feedback makes it harder to gauge "
        "whether your effort is landing where it should."
    ),
    "work_pace": (
        "There appears to be a meaningful gap between the pace your role demands and the "
        "rhythm at which you do your best thinking. Sustained pace mismatch tends to show up "
        "as a low-level restlessness or frustration that's difficult to pin on any single "
        "cause — it's systemic, not situational."
    ),

    # ── Two-dimension combos (sorted by PRIORITY_ORDER index) ────────────────
    "fragmentation+sustainability": (
        "Two patterns are showing up together: high fragmentation and signals of "
        "unsustainability. When attention is constantly interrupted and the overall load "
        "exceeds what feels recoverable, the effects amplify each other — fragmentation "
        "raises the energy cost of every task just as the reserve is already running low."
    ),
    "fragmentation+recognition_friction": (
        "Your responses show both high context-switching and a sense that your work isn't "
        "being accurately seen. Fragmented environments make deep contributions harder to "
        "produce — and when that effort goes unrecognized on top of it, the motivation to "
        "push through the friction diminishes in ways that are hard to reverse."
    ),
    "fragmentation+work_pace": (
        "You appear to be navigating both a fragmented attention environment and a pace that "
        "doesn't align with how you work best. These two patterns reinforce each other: "
        "interruptions break the rhythm that allows you to find sustainable momentum, leaving "
        "you neither fully focused nor comfortably paced."
    ),
    "fragmentation+environmental_friction": (
        "High fragmentation combined with environmental friction suggests your context is "
        "actively working against the conditions you need to focus. The result is a "
        "compounding tax — the environment interrupts, and when you do find a window of "
        "concentration, the surroundings make it harder to use it well."
    ),
    "sustainability+work_pace": (
        "There are signs that the pace your role demands isn't one you can maintain "
        "comfortably — and that this is already showing up as depletion rather than just "
        "busyness. When the rhythm feels chronically off, effort starts to cost more than "
        "it returns, even on work you find genuinely engaging."
    ),
    "sustainability+environmental_friction": (
        "The combination of sustainability concerns and environmental friction is notable — "
        "it suggests your environment is adding an invisible overhead that makes an already "
        "demanding situation harder to recover from. Friction in the context compounds the "
        "load in ways that don't appear on any task list."
    ),
    "sustainability+recognition_friction": (
        "Unsustainable demands alongside work that isn't being fully seen is a particularly "
        "draining combination. Giving more than feels sustainable is hard enough — doing it "
        "while that effort goes unacknowledged removes one of the key mechanisms that "
        "normally makes high effort feel worthwhile."
    ),
    "recognition_friction+work_pace": (
        "Your responses suggest a pace mismatch alongside a sense that your contributions "
        "aren't being fully recognized. When the role moves faster or slower than your "
        "natural rhythm and the output still doesn't land as expected, the signal you're "
        "receiving about your fit in this environment can become confusing and discouraging."
    ),

    # ── Edge cases ───────────────────────────────────────────────────────────
    "broad_overload": (
        "Your responses reflect friction across multiple dimensions simultaneously — "
        "fragmentation, sustainability, environment, recognition, and pace are all showing "
        "meaningful signals. When several of these patterns stack, the combined effect is "
        "greater than any single factor suggests; the system as a whole is working against "
        "your ability to do your best work."
    ),
    "all_low": (
        "Your responses don't show strong friction signals across the dimensions we measure "
        "— which is worth noting. Either your current environment is genuinely well-matched "
        "to how you work, or the friction present is subtle enough that a deeper assessment "
        "would be needed to surface it accurately."
    ),
}

WP_QUESTIONS: dict[str, dict] = {
    "wpll-q1": {
        "dimension": "Fragmentation",
        "text": "How often do you find yourself switching between unrelated tasks throughout a typical workday?",
        "options": {
            "a": "Rarely — I can usually stay focused on one thing",
            "b": "Sometimes — a few times a day",
            "c": "Often — it feels constant",
            "d": "Almost always — I rarely finish anything in one sitting",
        },
    },
    "wpll-q2": {
        "dimension": "Sustainability",
        "text": "How would you describe your energy level at the end of a typical workday?",
        "options": {
            "a": "Strong — I often have energy left over",
            "b": "Okay — a little tired but fine",
            "c": "Drained — I need significant recovery time",
            "d": "Depleted — running on empty by the end",
        },
    },
    "wpll-q3": {
        "dimension": "Environmental Friction",
        "text": "When your environment is noisy or disorganized around you, how does it affect your output?",
        "options": {
            "a": "Barely at all — I can tune it out",
            "b": "Somewhat — it slows me down a little",
            "c": "Noticeably — it takes real effort to push through",
            "d": "Significantly — I can't do my best work in chaos",
        },
    },
    "wpll-q4": {
        "dimension": "Recognition Friction",
        "text": "How often do you feel your best work goes unnoticed or isn't fully understood by the people around you?",
        "options": {
            "a": "Rarely — I usually feel seen and recognized",
            "b": "Sometimes — it happens but doesn't bother me much",
            "c": "Often — it's a real source of frustration",
            "d": "Almost always — it feels like a persistent gap",
        },
    },
    "wpll-q5": {
        "dimension": "Work Pace",
        "text": "When you think about the overall pace of your current work, it feels…",
        "options": {
            "a": "Just right — energizing without being overwhelming",
            "b": "A bit slow — I could handle more",
            "c": "Too fast — I'm struggling to keep up",
            "d": "Unsustainable — I'm burning through my reserves",
        },
    },
}

LOCKED_SECTION_TITLES: list[str] = [
    "Environmental Friction Score",
    "Work Rhythm Pattern",
    "Emerging Archetype Signals",
]


def score_answers(answers: list[dict]) -> dict[str, int]:
    """Map a list of question/option answers to per-dimension scores (0–3).

    Unknown question IDs and option suffixes are silently ignored; missing
    dimensions default to 0 so partial answer sets are always safe.
    """
    scores = {dim: 0 for dim in QUESTION_DIMENSIONS.values()}
    for answer in answers:
        if not isinstance(answer, dict):
            continue
        q_id = answer.get("question_id")
        o_id = answer.get("option_id")
        # A null or non-string id is skipped like an unknown one. The service
        # refuses such bodies with a 400 before they get here; this keeps the
        # engine itself from raising on one.
        if not isinstance(q_id, str) or not isinstance(o_id, str):
            continue
        dim = QUESTION_DIMENSIONS.get(q_id)
        if not dim:
            continue
        suffix = o_id.split("-")[-1]  # "wpll-q1-c" → "c"
        scores[dim] = OPTION_SCORES.get(suffix, 0)
    return scores


def select_template(scores: dict[str, int]) -> str:
    """Return the template key that best matches the scored dimension pattern.

    Combo keys are built by sorting the two dimension names according to
    PRIORITY_ORDER (lower index first), matching the keys in INSIGHT_TEMPLATES.
    """
    priority_map = {dim: i for i, dim in enumerate(PRIORITY_ORDER)}

    significant = [(dim, score) for dim, score in scores.items() if score >= 2]
    if not significant:
        return "all_low"

    # Sort: higher score first; ties broken by PRIORITY_ORDER position.
    significant.sort(key=lambda x: (-x[1], priority_map.get(x[0], 999)))

    if len(significant) >= 3:
        return "broad_overload"

    if len(significant) == 2:
        dim1, dim2 = significant[0][0], significant[1][0]
        # Order by priority index so the key matches INSIGHT_TEMPLATES.
        ordered = sorted([dim1, dim2], key=lambda d: priority_map.get(d, 999))
        combo_key = "+".join(ordered)
        if combo_key in INSIGHT_TEMPLATES:
            return combo_key
        # Fall back to the single dominant dimension.
        return significant[0][0]

    return significant[0][0]


def generate_result(answers: list[dict]) -> dict:
    """Score answers and return the insight text plus locked section titles."""
    scores = score_answers(answers)
    template_key = select_template(scores)
    return {
        "insight_text": INSIGHT_TEMPLATES[template_key],
        "locked_sections": LOCKED_SECTION_TITLES,
    }
