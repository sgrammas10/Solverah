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

__all__ = ["persist_submission", "respondent_id_for_user"]


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
        if existing is None:
            db.session.add(
                PersonDimensionScore(
                    user_id=user_id,
                    dimension_key=dimension_key,
                    score=score,
                    confidence=None,  # not measured yet; a placeholder would read as real
                    scoring_key_version=result.scoring_key_version,
                    submission_id=submission_id,
                )
            )
        else:
            existing.score = score
            existing.submission_id = submission_id
            existing.scored_at = db.func.now()

    return submission_id
