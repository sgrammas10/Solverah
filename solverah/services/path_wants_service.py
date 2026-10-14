"""The "what should change" panel: build it, store it, and feed it to the scorer.

``GET /me/path-wants`` builds one panel out of the user's *own* occupation --
about eight of its O*NET tasks in plain words, plus four measured work conditions
-- and ``PUT`` stores what they answered.  ``backend/services/path_scoring`` then
rotates every intent's query with it (design doc §8.3, measured in W-3: nDCG@10
0.300 -> 0.444 on the fifteen profiles that state wants).

Three things here are decisions rather than plumbing.

**The panel is server-built, and the anchor is resolved the way the scorer
resolves it.**  The questions ARE the user's own occupation's task statements, so
only the server knows them -- but more importantly, a panel that resolved the
anchor differently from the scorer would ask about one job and steer another.
:func:`~backend.services.path_scoring.resolve_anchor_code` is therefore shared
rather than reimplemented, and it makes no O*NET call on the normal path.

**Answers are validated against what a GET would offer, not against a
vocabulary.**  A task key the current anchor does not carry is a ``422`` and
nothing is written -- not because the string is malformed, but because storing an
answer to a question this user was never asked would put a row in the table that
no panel can ever show them or let them clear.  That includes a key that is
perfectly valid for a *different* occupation, which is exactly what a client
holding a stale panel across a job change would send.

**A write invalidates the Tier-1 cache and the stored Tier-2 fits.**  Unlike a
card judgement (F-6), a want changes the ranking every subsequent request
computes, so the cached shortlist is wrong the moment one lands.  The stored deep
fits go with it: not because a fit's own numbers move -- they do not, wants are
not in ``path_fit_repository.fingerprint`` -- but because
``tests/test_path_preferences_api.py``'s rule is that the two invalidations
travel together at every site, and a site that drops one and not the other is
how the next one drops neither.  It costs a recomputation and never a wrong
answer.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from model import User, db
from solverah.errors import ValidationError
from solverah.infra import llm
from solverah.repositories import (
    path_fit_repository,
    path_wants_repository,
    profile_repository,
)
from solverah.services import path_cache
from solverah.services.intelligence_service import (
    IntelligenceResult,
    build_user_profile,
    derive_career_status,
    end_read_transaction,
    read_scoring_intake,
)

__all__ = [
    "CONDITION_AXES",
    "CONDITION_LABELS",
    "read_path_wants",
    "save_path_wants",
    "wants_for_scoring",
    "wants_for_scoring_by_id",
]

#: The four axes the panel asks about, in the order it shows them.
#:
#: Four of the seven the sidecar carries, and the other three are left out on
#: purpose.  ``pace`` is weak (W-3a: Air Traffic Controllers rate as less
#: time-pressured than nurses -- the single Time Pressure element measures
#: deadlines, not stress).  ``outdoors`` and ``autonomy`` are real and are used
#: on the card reason line, but they are not asked: design doc §8.3 budgets
#: "three or four conditions" next to eight tasks, and a panel that asks about
#: everything measurable is the step-before-any-value friction ⚑7 is about.
CONDITION_AXES: Tuple[str, ...] = ("people", "public", "leading", "desk")

#: Plain words for each axis, phrased as the thing being asked about rather than
#: as a question, because the control beside it is *more / fine / less* and the
#: two together already read as one.  Copy is a best guess; Julie revises on the
#: built product and this is never a reason to block a chunk.
CONDITION_LABELS: Dict[str, str] = {
    "people": "Time working with other people",
    "public": "Dealing with customers or the public",
    "leading": "Leading or directing other people",
    "desk": "At a desk, rather than on your feet",
}

_TASK = path_wants_repository.KIND_TASK
_CONDITION = path_wants_repository.KIND_CONDITION

_STATUS_OK = "ok"
_STATUS_NO_ANCHOR = "no_anchor"
_STATUS_UNAVAILABLE = "unavailable"


def _error(status: int, message: str) -> IntelligenceResult:
    """The sibling routes' failure shape, verbatim.

    ``{"error": "..."}`` and not a problem document, because the SPA's
    ``stateForFailure()`` branches on these strings for every other path route
    and one endpoint answering a different shape for the same condition is a
    client bug waiting to happen.  The *business-rule* 422 below is the
    exception, and it is RFC 7807 for the reason B-5's malformed-cell 422 is: it
    names a field.
    """
    return IntelligenceResult(status=status, body={"error": message})


# ---------------------------------------------------------------------------
# Resolving the anchor
# ---------------------------------------------------------------------------


def _user_profile_for(user_id: int):
    """The scorer's ``UserProfile`` for *user_id*, or None when it cannot be built.

    None means "no current job as far as retrieval is concerned", which is the
    panel's ``no_anchor`` and not an error: a first-job user has no occupation to
    ask about, and design doc §8.3 says so explicitly -- no current job, no
    panel, taps alone.
    """
    profile = profile_repository.load_document(user_id)
    career_status = profile.get("career_status") or derive_career_status(profile)
    if not career_status:
        return None
    return build_user_profile(
        {**profile, "career_status": career_status},
        read_scoring_intake(user_id),
        career_status,
    )


def _resolve_anchor(user_id: int) -> Optional[str]:
    """The O*NET code of the user's current job, or None.

    Raises ``CorpusUnavailable`` upward: the caller turns it into the same typed
    503 every sibling route answers, because the corpus is a build artifact
    fetched from S3 and unreachable is an outage the client retries.

    Ends the session's read transaction before resolving (DB ledger I): the
    resolution can embed the profile and, on a cold worker, fetch the corpus,
    and a connection must not sit idle in transaction across either. Only
    reads precede it in both callers, so the rollback discards nothing.
    """
    from backend.services.onet_client import OnetClient
    from backend.services.path_scoring import resolve_anchor_code

    user_profile = _user_profile_for(user_id)
    end_read_transaction()
    if user_profile is None:
        return None
    try:
        openai_client = llm.get_openai_client()
    except RuntimeError:
        # No API key: resolution degrades to O*NET's title search, the same
        # promise `score_paths` makes.  A panel built on a worse anchor is still
        # a panel; refusing would be a harder failure than the degrade.
        openai_client = None
    # A profile with no usable title resolves to None rather than raising: the
    # panel treats it as `no_anchor`, which is design doc §8.3's "no current job,
    # no panel" and not a failure the user can act on.
    return resolve_anchor_code(user_profile, OnetClient(), openai_client)


# ---------------------------------------------------------------------------
# Building the panel
# ---------------------------------------------------------------------------


def _panel_body(
    status: str,
    anchor_code: Optional[str],
    anchor_title: str,
    tasks: List[Dict[str, Any]],
    conditions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "status": status,
        "anchor": (
            {"onet_code": anchor_code, "title": anchor_title}
            if anchor_code is not None
            else None
        ),
        "tasks": tasks,
        "conditions": conditions,
    }


def _no_anchor() -> IntelligenceResult:
    return IntelligenceResult(
        status=200, body=_panel_body(_STATUS_NO_ANCHOR, None, "", [], [])
    )


def _corpus_title(corpus, code: str) -> str:
    row = corpus.index_of(code)
    return corpus.titles[row] if row is not None else code


def _build_panel(user_id: int, anchor_code: str, corpus) -> IntelligenceResult:
    """The panel body for a resolved anchor, with the user's answers filled in.

    ``status`` reports the TASK half specifically.  The conditions are offered
    either way, because an axis is a name in code and its label is a constant:
    nothing on that half depends on a file being present, so a deployment that
    lost the tasks sidecar still lets a user say "less time with the public"
    rather than showing them an empty screen.
    """
    from backend.services import occupation_tasks

    answers = path_wants_repository.answers_for_anchor(user_id, anchor_code)

    conditions = [
        {
            "axis": axis,
            "label": CONDITION_LABELS[axis],
            "verdict": answers.get((_CONDITION, axis)),
        }
        for axis in CONDITION_AXES
    ]

    table = occupation_tasks.get_tasks(corpus)
    if table is None:
        return IntelligenceResult(
            status=200,
            body=_panel_body(
                _STATUS_UNAVAILABLE,
                anchor_code,
                _corpus_title(corpus, anchor_code),
                [],
                conditions,
            ),
        )

    tasks = [
        {"key": key, "label": label, "verdict": answers.get((_TASK, key))}
        # Sidecar order, which is O*NET's own statement order for the rows that
        # were selected -- not score order and not alphabetical.  A panel that
        # reordered itself between two reads is a panel a user cannot answer.
        for key, label in (
            (path_wants_repository.item_key_for_task(row.task), row.label)
            for row in table.for_code(anchor_code)
        )
    ]

    return IntelligenceResult(
        status=200,
        body=_panel_body(
            _STATUS_OK,
            anchor_code,
            _corpus_title(corpus, anchor_code),
            tasks,
            conditions,
        ),
    )


def read_path_wants(user: User, logger) -> IntelligenceResult:
    """``GET /me/path-wants`` -- the panel, plus whatever the user has answered.

    ``200`` in every case a user can be in, with ``status`` saying which:

    ``ok``            there is an anchor and the task rows were loaded
    ``no_anchor``     no current job, or a title that resolves to nothing usable
    ``unavailable``   the task sidecar is missing; the conditions half still works

    ``503 corpus_unavailable`` is the one failure, and it is the sibling routes'
    exactly: the corpus is a build artifact fetched from S3, so unreachable is an
    outage the client retries rather than a message the user can act on.
    """
    from backend.services.occupation_retrieval import CorpusUnavailable, get_corpus

    # The id, never the row, past the transaction `_resolve_anchor` ends.
    user_id = user.id
    try:
        anchor_code = _resolve_anchor(user_id)
        if anchor_code is None:
            return _no_anchor()
        corpus = get_corpus()
    except CorpusUnavailable:
        logger.warning("Corpus unavailable for path wants, user %s", user_id)
        return _error(503, "corpus_unavailable")

    return _build_panel(user_id, anchor_code, corpus)


# ---------------------------------------------------------------------------
# Writing answers
# ---------------------------------------------------------------------------


def _reject(field: str, code: str, detail: str) -> None:
    raise ValidationError(detail=detail, errors=[{"field": field, "code": code}])


def _offered_items(corpus, anchor_code: str) -> Dict[Tuple[str, str], str]:
    """``{(kind, key): item_text}`` for everything this anchor's panel asks.

    The text is what makes this more than a membership set: a stored task row
    keeps the ORIGINAL O*NET statement, because that is what the scorer embeds
    (design doc §8.7) and the client never sees it.  A condition's text is empty,
    because an axis has none.

    Read from the same two sources :func:`_build_panel` reads, so a key a GET
    would have offered can never be refused here.  The statement is looked up
    again rather than threaded through the response body, which keeps the wire
    shape honest: nothing a client is handed can be mistaken for something the
    scorer embeds.
    """
    from backend.services import occupation_tasks

    offered: Dict[Tuple[str, str], str] = {
        (_CONDITION, axis): "" for axis in CONDITION_AXES
    }
    table = occupation_tasks.get_tasks(corpus)
    if table is not None:
        for row in table.for_code(anchor_code):
            key = path_wants_repository.item_key_for_task(row.task)
            offered[(_TASK, key)] = row.task
    return offered


def _validated_answers(
    data: Dict[str, Any], offered: Dict[Tuple[str, str], str]
) -> List[Tuple[str, str, Optional[str], str]]:
    """``[(kind, key, verdict, item_text)]``, or a ``422`` and nothing written.

    Validated as a whole before a single row is touched, which is what makes a
    rejected PUT leave the stored panel exactly as it was.  A body that is half
    acceptable is not half applied: a client that sent one bad key has a bug, and
    applying the rest of its intent would leave the user with a panel neither
    side believes in.
    """
    answers = (data or {}).get("answers")
    if answers is None:
        answers = []
    if not isinstance(answers, list):
        _reject("answers", "not_a_list", "answers must be a list.")

    out: List[Tuple[str, str, Optional[str], str]] = []
    seen: set[Tuple[str, str]] = set()
    for index, answer in enumerate(answers):
        if not isinstance(answer, dict):
            _reject("answers.%d" % index, "not_an_object", "each answer must be an object.")
        kind = answer.get("kind")
        key = answer.get("key")
        verdict = answer.get("verdict")

        if kind not in path_wants_repository.KINDS:
            _reject(
                "answers.%d.kind" % index,
                "unknown_kind",
                'kind must be "task" or "condition".',
            )
        if verdict is not None and verdict not in path_wants_repository.VERDICTS:
            _reject(
                "answers.%d.verdict" % index,
                "unknown_verdict",
                'verdict must be "more", "less", or null to clear it.',
            )
        if not isinstance(key, str) or (kind, key) not in offered:
            _reject(
                "answers.%d.key" % index,
                "not_offered",
                (
                    "key must name a row this user's current occupation offers. "
                    "Re-read GET /me/path-wants: the panel is rebuilt from the "
                    "job they hold now, and a key from a different one is not "
                    "answerable."
                ),
            )
        if (kind, key) in seen:
            _reject(
                "answers.%d.key" % index,
                "duplicate",
                "the same item was answered twice in one body.",
            )
        seen.add((kind, key))
        out.append((kind, key, verdict, offered[(kind, key)]))
    return out


def save_path_wants(user: User, data: Dict[str, Any], logger) -> IntelligenceResult:
    """``PUT /me/path-wants`` -- store the named answers, return the whole panel.

    Idempotent, and partial by design: the body names the rows it is changing and
    everything it does not name is left alone, so an abandoned panel is a valid
    panel (design doc §8.3).  ``verdict: null`` clears a row, and clearing
    something already clear is a ``200`` rather than a ``404`` -- the client is
    asking for a state, not deleting a row it named, which is
    ``DELETE /me/path-feedback``'s argument applied one level down.

    Same error vocabulary as the GET, plus the business-rule ``422`` for a key
    the user's current anchor does not offer.
    """
    from backend.services.occupation_retrieval import CorpusUnavailable, get_corpus

    # The id, never the row: `_resolve_anchor` ends a transaction and the write
    # below commits one, and either would expire it (DB ledger I).
    user_id = user.id
    try:
        anchor_code = _resolve_anchor(user_id)
        if anchor_code is None:
            # Nothing to key an answer to.  Not a 422: the client is not wrong
            # about the body, it is out of date about the user, and a GET says so.
            return _no_anchor()
        corpus = get_corpus()
    except CorpusUnavailable:
        logger.warning("Corpus unavailable for path wants write, user %s", user_id)
        return _error(503, "corpus_unavailable")

    # The whole body is refused with a 422 here -- duplicates included -- before
    # anything is sent, so `set_answers`' own ValueError is unreachable from a
    # request.
    validated = _validated_answers(data, _offered_items(corpus, anchor_code))

    # One upsert and at most one delete for the whole panel, however many
    # items it answers (DB ledger I), where each item was a statement of its own.
    path_wants_repository.set_answers(user_id, anchor_code, validated)
    path_fit_repository.invalidate(user_id)  # with the Tier-1 cache below
    db.session.commit()
    path_cache.invalidate(user_id)

    return _build_panel(user_id, anchor_code, corpus)


# ---------------------------------------------------------------------------
# Feeding the scorer
# ---------------------------------------------------------------------------


def wants_for_scoring(user: User, user_profile, onet_client, openai_client):
    """:func:`wants_for_scoring_by_id` for a ``User``."""
    return wants_for_scoring_by_id(user.id, user_profile, onet_client, openai_client)


def wants_for_scoring_by_id(user_id: int, user_profile, onet_client, openai_client):
    """The stored ``Wants`` for this user's CURRENT anchor, or None.

    Called from every site that scores paths for a signed-in user -- the cold
    suggestion job and the warm feedback re-rank -- so that all three move
    intents read them, which is design doc §8.3's rule and the one place this
    differs from F-6's card feedback.

    **Returns None, not an empty ``Wants``, when the user has stated nothing**,
    and takes the existence check FIRST so that a user who has never opened the
    panel pays nothing at all: no anchor resolution, no embedding, no sidecar
    read.  That is not an optimisation, it is how "no stored wants is
    byte-identical to the scorer that existed before W-4" is made true by
    construction rather than by argument.

    Never raises: a resolution failure loses the wants for one request and
    degrades to today's ranking, which is strictly better than losing the page.
    ``CorpusUnavailable`` is the one exception worth naming, and it cannot escape
    here either -- the caller is about to call ``score_paths``, which loads the
    same corpus and answers it properly.

    Takes the id (DB ledger I) because a caller past a commit holds an expired
    row, and reading its id would reload it. When the user HAS stated wants it
    ends the session's transaction before resolving the anchor -- an embedding
    and, on a cold worker, a corpus fetch -- so call it with nothing unwritten;
    both callers have only read since their last commit.
    """
    from backend.services.path_scoring import resolve_anchor_code

    if not path_wants_repository.any_for_user(user_id):
        return None
    end_read_transaction()
    try:
        anchor_code = resolve_anchor_code(user_profile, onet_client, openai_client)
    except Exception:  # noqa: BLE001 -- a lost rotation is not a lost page
        return None
    if anchor_code is None:
        return None
    return path_wants_repository.wants_for_anchor(user_id, anchor_code)
