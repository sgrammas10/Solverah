"""
assessment_store.py -- persistence for a scored person-side submission.

Split from assessment_form.py deliberately: that module is the instrument's doorway and has
no Flask or SQLAlchemy import, so it stays testable without an app context and cannot grow a
dependency on the product schema. This module is the only place the two meet.

WHAT IS STORED, AND WHY BOTH
----------------------------
Raw responses AND derived scores, always together, in one transaction.

The raw rows are the ones that matter long term. A score is a function of (choices, item
file, scoring method); two of those three change over time. schema.sql's own comment is
"keep them so scores can be RE-derived when the scoring key changes -- never overwrite raw
responses." Storing only scores would make every historical profile un-recomputable the
first time the ladder is revised, which is precisely the position the v1 -> v2 item change
would have put us in.

RETAKE SEMANTICS
----------------
Raw responses are append-only: a retake writes 24 new rows under a new submission_id, and
the old sitting stays readable forever. Derived scores are unique per
(user, dimension, scoring_key_version), so a retake under the same key version UPDATES the
score row in place and records which submission it now comes from.

That asymmetry is intentional. There is exactly one current score per person per dimension
per scoring key -- anything else means every consumer has to decide which row is live, and
they will not all decide the same way. The history is not lost; it is in the raw rows.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import uuid

from assessment_form import ScoredSubmission

__all__ = [
    "export_person_side",
    "get_dimension_confidences",
    "get_dimension_scores",
    "has_completed_assessment",
    "persist_submission",
    "respondent_id_for_user",
]


def respondent_id_for_user(user_id: int, secret: bytes | None = None) -> str:
    """A stable, opaque per-user id to seed the shuffle and salt the item tokens.

    Not `user.id` directly. `build_form` echoes respondent_id back in the payload, so a raw
    database id would be published to the client -- a sequential public counter, which is
    exactly what present_items' DECISION 3 rules out. HMAC of the id under the form secret is
    stable across sessions (so a resumed form does not reshuffle), opaque, and not guessable
    from another user's value.

    Derived rather than stored: a stored column would be a second source of truth that can
    drift, and this is reproducible from (user_id, secret) forever.
    """
    if secret is None:
        env = os.environ.get("SOLVERAH_FORM_TOKEN_SECRET")
        if not env:
            raise RuntimeError(
                "SOLVERAH_FORM_TOKEN_SECRET is not set. Deliberately no default (D-05)."
            )
        secret = env.encode("utf-8")
    return hmac.new(
        secret, f"respondent\x00{user_id}".encode("utf-8"), hashlib.sha256
    ).hexdigest()[:32]


def persist_submission(db, user_id: int, result: ScoredSubmission) -> str:
    """Write one sitting's raw responses and its six derived scores. Returns submission_id.

    Does NOT commit -- the caller owns the transaction boundary, so a route can roll the
    whole thing back if anything after this fails. Both writes are in the same transaction
    by construction: a scores row whose raw responses were not written is un-recomputable,
    and raw responses with no scores are invisible to every consumer.
    """
    from model import AssessmentResponse, PersonDimensionScore

    submission_id = uuid.uuid4().hex

    for item_id, choice in result.choices.items():
        db.session.add(
            AssessmentResponse(
                user_id=user_id,
                submission_id=submission_id,
                item_id=item_id,
                choice=choice,
                form_version=result.form_version,
            )
        )

    for dimension_key, score in result.scores.items():
        existing = PersonDimensionScore.query.filter_by(
            user_id=user_id,
            dimension_key=dimension_key,
            scoring_key_version=result.scoring_key_version,
        ).first()
        # D-17: confidence comes from the submission, indexed strictly -- a dimension the
        # scorer scored but did not grade for confidence is a contract violation, not a
        # default-to-NULL (D-07). None is a legitimate VALUE here for exactly one reason:
        # CONFIDENCE_PENDING_DIMENSIONS (feedback, D-17(a)).
        confidence = result.confidences[dimension_key]
        if existing is None:
            db.session.add(
                PersonDimensionScore(
                    user_id=user_id,
                    dimension_key=dimension_key,
                    score=score,
                    confidence=confidence,
                    scoring_key_version=result.scoring_key_version,
                    submission_id=submission_id,
                )
            )
        else:
            existing.score = score
            # A retake refreshes confidence with the score -- a new sitting's score carrying
            # the OLD sitting's e would attribute one submission's answer pattern to another.
            existing.confidence = confidence
            existing.submission_id = submission_id
            existing.scored_at = db.func.now()

    return submission_id


def has_completed_assessment(user_id: int) -> bool:
    """True if this user has a sitting of the CURRENT instrument on record.

    Keyed to the current scoring_key_version deliberately, not to "any submission ever".
    Completion is a fact about an instrument, not about the user: when the item file or the
    scoring method changes, every profile reverts to not-completed and the product re-prompts
    (decided with Sebastian 2026-08-19 for the v1-WorkPulse -> v2 replacement, and the same
    logic applies to any future v3). The old raw rows are not lost -- they stay append-only
    per D-16 -- but a sitting of one instrument says nothing the next instrument may consume.

    This is the read path the web layer must use for completion gating. Querying the
    person-side tables from app.py directly fails tests/test_employer_visibility.py, and
    adding app.py to that allowlist is explicitly the wrong fix (D-01).
    """
    from assessment_form import scoring_key_version
    from model import PersonDimensionScore

    return (
        PersonDimensionScore.query.filter_by(
            user_id=user_id,
            scoring_key_version=scoring_key_version(),
        ).first()
        is not None
    )


def get_dimension_scores(user_id: int) -> dict[str, float] | None:
    """The user's current dimension scores, {dimension_key: score}, or None.

    THE sanctioned read for match scoring (decided with Sebastian 2026-08-19): the match
    pipeline consumes a person's profile through this function, keeping the
    test_employer_visibility.py allowlist closed -- match_scoring.py takes plain dicts
    and never touches the person-side tables itself. What leaves this function is
    already the full D-01-sensitive object, so every caller inherits D-01's constraint:
    scores feed the model; they are never surfaced to an employer, and anything shown
    anywhere is a match RESULT.

    Keyed to the CURRENT scoring_key_version, same reasoning as
    has_completed_assessment: scores from a superseded instrument are not comparable to
    company scores calibrated against the current one. None means "no current profile"
    -- an ordinary state (new user, or instrument changed), not an error. Consumers must
    treat None as "cannot be matched yet", never as a zero/default profile (D-07);
    match_core refuses a partial dimension dict for the same reason.
    """
    from assessment_form import scoring_key_version
    from model import PersonDimensionScore

    rows = PersonDimensionScore.query.filter_by(
        user_id=user_id,
        scoring_key_version=scoring_key_version(),
    ).all()
    if not rows:
        return None
    return {r.dimension_key: r.score for r in rows}


def get_dimension_confidences(user_id: int) -> dict[str, float | None] | None:
    """The user's current stored confidences, {dimension_key: confidence_or_None}, or None
    if no current profile exists. The sanctioned read for D-17 confidence, same doorway
    logic as get_dimension_scores.

    D-17's semantics bind every caller: confidence describes how well one ladder position
    summarizes four answers -- low is never read as gaming, high is never read as honesty,
    and a None value (feedback, pending S-18 per D-17(a) -- or any pre-S-31 row) is never
    read as high. D-17(b): analyses upstream of S-18 may not filter or weight by these
    values at all.
    """
    from assessment_form import scoring_key_version
    from model import PersonDimensionScore

    rows = PersonDimensionScore.query.filter_by(
        user_id=user_id,
        scoring_key_version=scoring_key_version(),
    ).all()
    if not rows:
        return None
    return {r.dimension_key: r.confidence for r in rows}


def export_person_side(user_id: int) -> dict[str, list[dict]]:
    """Every person-side row we hold for one user, as plain dicts.

    THE doorway for account-rights requests -- GDPR/CCPA access, portability, and the
    "what survives deletion" assertions that go with them. account_lifecycle.py calls
    this instead of importing the models: an export endpoint is precisely the module
    that would otherwise widen the tests/test_employer_visibility.py allowlist, and D-01
    keeps that list closed. Adding account_lifecycle.py to ALLOWED is the wrong fix.

    Deliberately NOT keyed to the current scoring_key_version, unlike
    get_dimension_scores. Those reads answer "what can be consumed now", so a superseded
    instrument correctly drops out. A subject-access request asks a different question --
    what do you HOLD about me -- and a version filter there would silently return an
    incomplete answer to a legal request (D-07: never degrade to a quiet default).

    Returns plain dicts rather than ORM rows on purpose: the caller cannot navigate back
    to the tables through the objects it was handed, so the doorway stays a doorway.
    """
    from model import AssessmentResponse, PersonDimensionScore

    answers = (
        AssessmentResponse.query.filter_by(user_id=user_id)
        .order_by(AssessmentResponse.answered_at, AssessmentResponse.id)
        .all()
    )
    scores = (
        PersonDimensionScore.query.filter_by(user_id=user_id)
        .order_by(PersonDimensionScore.dimension_key)
        .all()
    )
    return {
        "answers": [
            {
                "submission_id": a.submission_id,
                "item_id": a.item_id,
                "choice": a.choice,
                "form_version": a.form_version,
                "answered_at": a.answered_at.isoformat() if a.answered_at else None,
            }
            for a in answers
        ],
        "dimension_scores": [
            {
                "dimension": s.dimension_key,
                "score": s.score,
                "confidence": s.confidence,
                "scoring_key_version": s.scoring_key_version,
                "submission_id": s.submission_id,
                "scored_at": s.scored_at.isoformat() if s.scored_at else None,
            }
            for s in scores
        ],
    }
