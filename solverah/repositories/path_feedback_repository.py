"""Queries against ``path_feedback`` -- inline card judgements (BUILD_PLAN F-6).

The user taps "too similar" or "interesting" on a suggestion card; a row lands
here; the next Tier-1 retrieval reads them back and rebuilds its query.  That is
the whole lifecycle, and the shape of it is the design decision worth naming.

**Judgements, not vectors.**  ``model.PathFeedback``'s docstring has the four
reasons; the consequence for this module is that it stores no numbers at all.
:func:`verdicts_for_user` returns ``{onet_code: verdict}`` and
``backend.services.path_scoring`` turns that into arithmetic with the corpus it
has already loaded.  A repository that returned vectors would have to know which
corpus build produced them, and would be wrong the first time one was rebuilt.

**This is not a cache, so it is not invalidated.**  ``path_cache`` and
``path_fits`` are both derived from the profile and are dropped whenever the
profile moves.  A judgement is not derived from anything -- it is something a
person said -- so a profile edit leaves it standing, and
``tests/test_path_preferences_api.py``'s enumeration rule (every
``path_cache.invalidate`` is matched by a ``path_fit_repository.invalidate``)
deliberately does not extend to this table.  The only things that remove a row
are the user asking (:func:`clear_for_user`, behind ``DELETE
/me/path-feedback``) and account deletion (:func:`delete_for_user`).

**What a stale code does.**  ``onet_code`` has no foreign key -- occupations live
in the corpus artifact -- so a quarterly corpus rebuild (F-8) can retire a code
somebody has judged.  Nothing breaks: ``path_scoring`` looks each code up and
skips the ones the corpus does not carry, so a retired judgement stops
contributing instead of raising.  Rows are not swept, because a code that
vanished from one build can come back in the next and the row is ~60 bytes.
"""

from __future__ import annotations

import datetime
from typing import Dict, List

from model import PathFeedback, db

__all__ = [
    "VERDICTS",
    "clear_for_user",
    "count_for_user",
    "delete_for_user",
    "list_for_user",
    "record",
    "verdicts_for_user",
]

#: The closed verdict vocabulary.  Three, and the third one earned its place on
#: the F-2 harness rather than by symmetry with the other two -- see
#: ``backend/services/path_scoring._rocchio_query`` for the measurement.
#:
#: ``too_similar``  a RADIUS signal: exclude everything at least this close to
#:                  the user's own occupation.
#: ``interesting``  a DIRECTION signal: rotate the query toward it.
#: ``not_for_me``   the directional negative: rotate the query away from it.
#:
#: The first two are genuinely different kinds of answer, which is the reason
#: design doc §3.2 insists on both: two occupations equidistant from the anchor
#: can lie in opposite directions, so a radius alone cannot express "not that
#: way".  ``not_for_me`` is what makes Rocchio's third term reachable at all --
#: ``too_similar`` cannot serve as the negative, because subtracting something
#: that sits *next to the anchor* subtracts the anchor, and the user asking for
#: a less similar job has not asked to stop being themselves.
VERDICTS: frozenset[str] = frozenset({"too_similar", "interesting", "not_for_me"})


def record(user_id: int, onet_code: str, verdict: str) -> PathFeedback:
    """Upsert this user's judgement of one occupation.

    Re-tapping a card is a **correction**, not a second opinion: the row is
    updated in place and ``updated_at`` moves, while ``created_at`` keeps the
    first time they said anything about this card.  An append-only history would
    need a "which one counts" rule at every read and has no reader asking for
    one.

    Does not commit -- the service owns the transaction boundary, as everywhere
    else in this package.

    Raises:
        ValueError: *verdict* is not in :data:`VERDICTS`.  The route answers
            ``400 invalid_verdict`` before reaching here, so this is the
            belt-and-braces half: the vocabulary is not enforced by the column
            (see the migration for why), which makes it this function's job.
    """
    if verdict not in VERDICTS:
        raise ValueError("unknown verdict %r" % (verdict,))

    row = PathFeedback.query.filter_by(user_id=user_id, onet_code=onet_code).first()
    now = datetime.datetime.now(datetime.timezone.utc)
    if row is None:
        row = PathFeedback(
            user_id=user_id,
            onet_code=onet_code,
            verdict=verdict,
            created_at=now,
            updated_at=now,
        )
        db.session.add(row)
        return row
    row.verdict = verdict
    row.updated_at = now
    return row


def verdicts_for_user(user_id: int) -> Dict[str, str]:
    """``{onet_code: verdict}`` for every judgement this user has made.

    The exact shape ``path_scoring.score_paths`` takes: a plain mapping, with no
    model objects in it, so the scorer stays importable without the app context
    and the two halves can be tested apart.
    """
    return {
        row.onet_code: row.verdict
        for row in PathFeedback.query.filter_by(user_id=user_id).all()
    }


def list_for_user(user_id: int) -> List[PathFeedback]:
    """Every judgement for *user_id*, most recently touched first."""
    return (
        PathFeedback.query.filter_by(user_id=user_id)
        .order_by(PathFeedback.updated_at.desc())
        .all()
    )


def count_for_user(user_id: int) -> int:
    """How many judgements this user has standing."""
    return PathFeedback.query.filter_by(user_id=user_id).count()


def clear_for_user(user_id: int) -> int:
    """Delete every judgement for *user_id* and return how many there were.

    The "reset" button.  A DELETE and not a soft flag, because the whole point of
    storing judgements rather than a rotated query is that reset is this
    statement -- see the module docstring.  Does not commit.
    """
    return PathFeedback.query.filter_by(user_id=user_id).delete()


def delete_for_user(user_id: int) -> None:
    """Destroy this user's judgements on account deletion (D-7).

    Separate from :func:`clear_for_user` despite the identical statement, for the
    reason ``path_fit_repository`` gives for the same pair: one is a user action
    with a return value the route reports, the other is a promise, and only one
    of them may ever grow a "keep the row, anonymise it" variant.  Neither may
    ever call the other.
    """
    PathFeedback.query.filter_by(user_id=user_id).delete()
