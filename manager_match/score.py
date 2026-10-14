from __future__ import annotations

from .questions import QUESTIONS

#: Which scoring key produced a result. Returned with every score and stored on
#: the submission as ``result["scoring_key"]``, so a `relationship` number on a
#: row says which era it belongs to instead of being read under whatever key
#: happens to be current.
#:
#: **"mm-v1" is never written anywhere.** It is the *absence* of this field, on
#: every row scored before `mm-q11` was corrected on 2026-09-10 (bias review,
#: Finding 7). ``Scripts/backfill_manager_match_scoring_key.py`` re-derives those
#: rows from their stored answers and stamps them.
#:
#: Bump this whenever an item's anchors or dimension change.
#: ``assessment_submissions.form_version`` cannot serve: it is one shared
#: placeholder constant across all four client-rendered instruments and answers
#: "which form shape did the client render", not "which key scored this".
SCORING_KEY = "mm-v2"

_SCORE_LOOKUP: dict[str, dict[str, float]] = {
    q["question_id"]: {"a": q["score_a"], "b": q["score_b"]}
    for q in QUESTIONS
}

_DIMENSION_QUESTIONS: dict[str, list[str]] = {}
for _q in QUESTIONS:
    _DIMENSION_QUESTIONS.setdefault(_q["dimension"], []).append(_q["question_id"])

_VALID_CHOICES = {"a", "b"}


def score_manager_match(answers: list[dict]) -> dict:
    if len(answers) != 15:
        raise ValueError(f"Expected 15 answers, got {len(answers)}")

    # The same three checks as `manager_profile._validate`, in the same order.
    # Without the first two an unknown id was a KeyError out of the lookup
    # below and a duplicate silently left another question unanswered (and
    # then a KeyError in the dimension means) -- either way an unhandled
    # exception rather than the ValueError every caller turns into a 400.
    seen: set[str] = set()
    for ans in answers:
        if not isinstance(ans, dict):
            raise ValueError("Each answer must be an object with question_id and choice")
        qid = ans.get("question_id")
        if not isinstance(qid, str) or qid not in _SCORE_LOOKUP:
            raise ValueError(f"Unknown question_id '{qid}'")
        if qid in seen:
            raise ValueError(f"Duplicate answer for question '{qid}'")
        seen.add(qid)
        if ans.get("choice") not in _VALID_CHOICES:
            raise ValueError(
                f"Invalid choice '{ans.get('choice')}' for question '{qid}'; must be 'a' or 'b'"
            )
    # Fifteen unique, known ids cover every question, so a missing answer is
    # already impossible by the time we get here.

    scores_by_question: dict[str, float] = {
        ans["question_id"]: _SCORE_LOOKUP[ans["question_id"]][ans["choice"]]
        for ans in answers
    }

    dimension_scores: dict[str, float] = {}
    for dim, qids in _DIMENSION_QUESTIONS.items():
        dimension_scores[dim] = sum(scores_by_question[qid] for qid in qids) / len(qids)

    autonomy = dimension_scores["autonomy"]
    feedback = dimension_scores["feedback_style"]
    relationship = dimension_scores["relationship"]
    growth = dimension_scores["growth_focus"]

    if autonomy > 0.65 and feedback < 0.45:
        archetype = "The Autonomist"
    elif autonomy < 0.45 and feedback > 0.60:
        archetype = "The Operator"
    elif growth > 0.65 and autonomy > 0.55:
        archetype = "The Challenger"
    elif growth > 0.65 and relationship > 0.60:
        archetype = "The Nurtured"
    elif relationship > 0.65:
        archetype = "The Collaborator"
    else:
        archetype = "The Operator"

    return {
        "archetype": archetype,
        "dimension_scores": dimension_scores,
        "scoring_key": SCORING_KEY,
    }
