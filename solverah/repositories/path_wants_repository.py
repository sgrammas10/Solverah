"""Queries against ``path_wants`` -- what should change about the user's own job (W-4).

The user answers a panel built from their *own* occupation; a row lands here per
answer; the next Tier-1 retrieval reads them back as a
``backend.services.path_scoring.Wants`` and rotates its query with them.  That is
the whole lifecycle, and three things about its shape are decisions rather than
implementation details.

**"Fine" is the absence of a row.**  The panel offers *more*, *fine* and *less*
and only two of them are stored -- see ``model.PathWant``'s section comment for
why a third value would be two representations of one state.  The consequence
here is that :func:`set_answer` with ``verdict=None`` is a DELETE, and that
``answers_for_anchor`` returns a partial mapping rather than one entry per
offered item.

**Answers belong to the occupation they were asked about.**  Every read is keyed
by ``(user_id, anchor_onet_code)``, so a user whose current job resolves
somewhere new reads none of their old answers -- the rows are inert, not stale
(``model.PathWant`` again).  Nothing here sweeps them and nothing here is keyed
by user alone except :func:`any_for_user`, whose only job is to let a caller skip
the anchor resolution entirely when the user has never answered anything.

**This is not a cache, so it is not invalidated.**  ``path_feedback_repository``
makes the same point about the same distinction: a want is not derived from the
profile, it is something a person said, so a profile edit leaves it standing.
What a wants *write* does invalidate is the other direction -- the Tier-1
suggestion cache and the stored Tier-2 fits, because the ranking they hold was
computed without this answer.  That happens in the service, where every other
invalidation pair lives.

**What a stale key does.**  ``item_key`` is a digest of the O*NET task statement,
so a quarterly sidecar rebuild that drops or rewords a task leaves a row nobody
offers any more.  Nothing breaks: the panel lists what the sidecar carries today
and :func:`wants_for_anchor` still hands the stored ``item_text`` to the scorer,
which embeds it like any other sentence.  Rows are not swept, for
``path_feedback_repository``'s reason -- a statement that vanished from one build
can come back in the next, and the row is ~200 bytes.
"""

from __future__ import annotations

import datetime
import hashlib
import re
from typing import Dict, List, Optional, Tuple

from model import PathWant, db

__all__ = [
    "KINDS",
    "KIND_CONDITION",
    "KIND_TASK",
    "VERDICTS",
    "answers_for_anchor",
    "any_for_user",
    "clear_for_user",
    "count_for_user",
    "delete_for_user",
    "item_key_for_task",
    "list_for_anchor",
    "set_answer",
    "wants_for_anchor",
]

KIND_TASK = "task"
KIND_CONDITION = "condition"

#: The two kinds of question the panel asks.  Two and not three: the tasks come
#: from the anchor's own O*NET statements and the conditions from the measured
#: work-context axes, and design doc §8.2 measured those as different signals
#: (tasks carry the user's examples, conditions cannot rank alone).  A third kind
#: would need its own storage meaning, not just another string.
KINDS: frozenset[str] = frozenset({KIND_TASK, KIND_CONDITION})

#: The closed verdict vocabulary.  Two, and the missing third is the point:
#: *fine* is stored as no row at all (module docstring).
VERDICTS: frozenset[str] = frozenset({"more", "less"})

#: Length of the hex digest kept for a task key.  48 bits of sha256 over the
#: normalised statement: the whole O*NET catalogue is ~20,000 statements, so the
#: birthday probability of any collision across it is under 10^-6, and a
#: collision would at worst mis-key one answer inside one occupation's eight
#: offered rows rather than across the catalogue -- the uniqueness that matters
#: is within a single ``(user, anchor)``, where there are eight of them.
#:
#: Short because it travels on the wire and into a client's form state, and a
#: 64-character key buys nothing a 12-character one does not.
_KEY_HEX_LENGTH = 12

#: Prefix on a task key, so an eyeballed row says which vocabulary its
#: ``item_key`` is drawn from without a join to ``kind``.
_TASK_KEY_PREFIX = "t_"

_WHITESPACE = re.compile(r"\s+")


def item_key_for_task(statement: str) -> str:
    """A stable short key for one O*NET task statement.

    **Derived from the statement, not from its position and not from its display
    label**, which is the property the whole key exists for.  The tasks sidecar
    is rebuilt with the corpus every quarter and its plain-words labels are
    rewritten by an offline LLM pass, so:

    * a positional key ("the third row") would silently re-point a stored answer
      at a different task the first time O*NET reordered or dropped one;
    * a label key would lose every answer the first time the labels were
      regenerated, which is a thing that happens on purpose.

    Normalised on whitespace and case before hashing, so a statement that comes
    back from a rebuild with a collapsed double space or a capitalisation fix is
    still the same question.  Nothing else is stripped: O*NET's punctuation is
    part of the sentence, and normalising more would start merging statements
    that differ only in a qualifier.
    """
    normalised = _WHITESPACE.sub(" ", (statement or "").strip()).lower()
    digest = hashlib.sha256(normalised.encode("utf-8")).hexdigest()
    return _TASK_KEY_PREFIX + digest[:_KEY_HEX_LENGTH]


def list_for_anchor(user_id: int, anchor_onet_code: str) -> List[PathWant]:
    """Every standing answer this user has given about *anchor_onet_code*.

    Ordered by ``(kind, item_key)`` rather than by time: two identical requests
    must produce the same list, and the scorer means the same thing whichever
    order the rows arrive in, so a stable one costs nothing and makes a response
    diffable.
    """
    return (
        PathWant.query.filter_by(user_id=user_id, anchor_onet_code=anchor_onet_code)
        .order_by(PathWant.kind.asc(), PathWant.item_key.asc())
        .all()
    )


def answers_for_anchor(
    user_id: int, anchor_onet_code: str
) -> Dict[Tuple[str, str], str]:
    """``{(kind, item_key): verdict}`` for one user and one anchor.

    What the panel renders from: a plain mapping with no model objects in it, so
    the service can answer "what did they say about this row" with a lookup and
    ``None`` is the *fine* case by construction.
    """
    return {
        (row.kind, row.item_key): row.verdict
        for row in list_for_anchor(user_id, anchor_onet_code)
    }


def wants_for_anchor(user_id: int, anchor_onet_code: str):
    """The stored answers as a scorer ``Wants``, or None when there are none.

    The one function that crosses into ``backend.services.path_scoring``'s
    vocabulary, and it converts rather than leaking rows: tasks become the
    ORIGINAL statements (``item_text``, never a display label -- design doc §8.7)
    and conditions become ``{axis: verdict}``.

    Returns ``None`` rather than an empty ``Wants`` when nothing is stored, so
    the caller hands the scorer the same ``None`` it handed before this table
    existed.  The two are equivalent to ``score_paths`` -- ``Wants().is_empty``
    is the identity case it pins -- but only one of them is provably the old
    call.

    Imported inside the function for the reason every repository that touches the
    scorer gives: ``path_scoring`` pulls in numpy and the corpus seam, and a
    module-level import would drag both into anything that imports a repository.
    """
    from backend.services.path_scoring import Wants

    more: List[str] = []
    less: List[str] = []
    conditions: Dict[str, str] = {}
    for row in list_for_anchor(user_id, anchor_onet_code):
        if row.kind == KIND_TASK:
            if not row.item_text:
                # A task row with no statement cannot be embedded and must not
                # become an empty string in the rotation.  Unreachable through
                # the API, which refuses a task answer whose text it cannot find.
                continue
            (more if row.verdict == "more" else less).append(row.item_text)
        elif row.kind == KIND_CONDITION:
            conditions[row.item_key] = row.verdict

    if not (more or less or conditions):
        return None
    return Wants(tasks_more=tuple(more), tasks_less=tuple(less), conditions=conditions)


def set_answer(
    user_id: int,
    anchor_onet_code: str,
    kind: str,
    item_key: str,
    verdict: Optional[str],
    item_text: str = "",
) -> Optional[PathWant]:
    """Upsert one answer, or delete it when *verdict* is None.

    ``verdict=None`` is *fine*, and *fine* is the absence of a row (module
    docstring), so clearing is a DELETE and re-clearing something already absent
    is a no-op rather than an error -- which is what makes the whole PUT
    idempotent.

    Re-answering is a **correction**: the row is updated in place and
    ``updated_at`` moves, while ``created_at`` keeps the first time they said
    anything about this item.  ``PathFeedback``'s shape and ``PathFeedback``'s
    reason -- a history of changed minds has no reader.

    ``item_text`` is only meaningful for a task, and is rewritten on every upsert
    rather than only on insert: a sidecar rebuild that rewords a statement
    without changing its normalised digest should leave the newer text stored.

    Does not commit -- the service owns the transaction boundary.

    Raises:
        ValueError: *kind* is not in :data:`KINDS`, or *verdict* is neither None
            nor in :data:`VERDICTS`.  The route answers a typed 422 before
            reaching here, so this is the belt-and-braces half: the vocabulary is
            not enforced by the column (see the migration for why), which makes
            it this function's job.
    """
    if kind not in KINDS:
        raise ValueError("unknown want kind %r" % (kind,))
    if verdict is not None and verdict not in VERDICTS:
        raise ValueError("unknown want verdict %r" % (verdict,))

    row = PathWant.query.filter_by(
        user_id=user_id,
        anchor_onet_code=anchor_onet_code,
        kind=kind,
        item_key=item_key,
    ).first()

    if verdict is None:
        if row is not None:
            db.session.delete(row)
        return None

    now = datetime.datetime.now(datetime.timezone.utc)
    if row is None:
        row = PathWant(
            user_id=user_id,
            anchor_onet_code=anchor_onet_code,
            kind=kind,
            item_key=item_key,
            item_text=item_text or "",
            verdict=verdict,
            created_at=now,
            updated_at=now,
        )
        db.session.add(row)
        return row

    row.verdict = verdict
    row.item_text = item_text or ""
    row.updated_at = now
    return row


def any_for_user(user_id: int) -> bool:
    """True when this user has answered anything, about any occupation.

    The cheap guard on the scoring path.  Reading stored wants needs the user's
    anchor, and resolving the anchor costs an embedding of their profile document
    -- so a user who has never opened the panel, which is every user today, must
    not pay for it.  One indexed existence check instead.
    """
    return (
        db.session.query(PathWant.id).filter_by(user_id=user_id).first() is not None
    )


def count_for_user(user_id: int) -> int:
    """How many answers this user has standing, across every anchor."""
    return PathWant.query.filter_by(user_id=user_id).count()


def clear_for_user(user_id: int, anchor_onet_code: Optional[str] = None) -> int:
    """Delete this user's answers and return how many there were.

    With *anchor_onet_code* it clears one job's panel; without it, everything.
    The user action, not the deletion promise -- see :func:`delete_for_user` for
    why the two are separate despite the statement being the same.  Does not
    commit.
    """
    query = PathWant.query.filter_by(user_id=user_id)
    if anchor_onet_code is not None:
        query = query.filter_by(anchor_onet_code=anchor_onet_code)
    return query.delete()


def delete_for_user(user_id: int) -> None:
    """Destroy this user's answers on account deletion (D-7).

    Separate from :func:`clear_for_user` despite the overlapping statement, for
    the reason ``path_feedback_repository`` and ``path_fit_repository`` both
    give: one is a user action with a return value a route reports, the other is
    a promise, and only one of them may ever grow a "keep the row, anonymise it"
    variant.  Neither may ever call the other.
    """
    PathWant.query.filter_by(user_id=user_id).delete()
