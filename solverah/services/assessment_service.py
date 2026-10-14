"""The five assessment instruments: Work Pulse, WPLL, FocusType, ManagerMatch,
and the current 24-item person-side culture assessment.

Phase 1b collapsed the five near-identical submit handlers into one
``POST /assessments/{kind}/submissions``.  Phase 2d finished the other half:
the five now write one storage shape, ``assessment_submissions``, instead of the
four places they used to live in -- two column families on ``user_intake``, two
keys inside the profile document, and the person-side tables.

The original 12-question ``work_pulse`` was retired on 2026-10-02: its scorer
and its two-commit write are gone, every write door answers 410, and only its
stored result stays readable (see the RETIRED section below).

Deliberately unchanged:

* Scoring the person-side assessment returns the submission id and the key
  version but **not the six dimension scores**.  Handing them back gives a
  retaking respondent a gradient to optimise against, which teaches the
  item-to-dimension mapping the shuffle and interleave exist to hide.
* Persistence for ``core`` still goes through ``assessment_store`` and nothing
  else (D-01).  Its submission row is written there, in the same transaction as
  the raw responses, and carries no result and no answers.  Unifying where a
  sitting is *recorded* was not licence to widen what a sitting *exposes*.

No provider call runs inside a transaction.  The caller's user lookup opens
one -- the worker's ``find_by_id`` before it scores -- and the retired Work
Pulse scorer used to open and flush its submission row before narrating as
well, so a connection sat idle in transaction for the whole paid round trip,
which is seconds and can be minutes when the SDK retries.  The provider-scored
submit with an account (ManagerMatch) reads what it needs, copy it out as values (a commit expires every
instance in the session), end that transaction, and write only once the reply
is in.  The same goes for ``user.id``: every submit takes it once, before its
first commit, so no commit is followed by a reload of the user row.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, List, Optional

from model import User, db
from solverah.domain import auth as auth_domain
from solverah.errors import ValidationError
from solverah.infra import llm
from solverah.repositories import assessment_repository, path_fit_repository
from solverah.services import assessment_prompts, path_cache

__all__ = [
    "ASSESSMENT_KINDS",
    "AssessmentKind",
    "CORE_RETAKE_COOLDOWN",
    "RETIRED_WORK_PULSE_MESSAGE",
    "precheck",
    "AssessmentResult",
    "TraitPreferencesInvalid",
    "read_trait_preferences",
    "save_trait_preferences",
    "KINDS_BY_KEY",
    "catalogue",
    "find_kind",
    "form",
    "result",
    "submit",
    "MANAGER_MATCH_ANSWER_COUNT",
    "WPLL_MAX_ANSWERS",
    "completed_kinds",
    "get_manager_match_result",
    "get_work_pulse_result",
    "submit_focus_type",
    "submit_manager_match",
    "wpll_insight",
]

MANAGER_MATCH_ANSWER_COUNT = 15
WPLL_MAX_ANSWERS = 5

#: The form version the four client-rendered instruments submit against.
#:
#: A placeholder, and named as one. Their questions ship in the client bundle,
#: so there is no server-side definition to version and nothing that could
#: disagree about which one a respondent saw. It exists because
#: ``assessment_submissions.form_version`` is part of the composite foreign key
#: into ``assessment_forms`` -- the constraint that stops the version string
#: being free text -- and a nullable column there would make the constraint
#: unenforceable for four instruments out of five. It becomes a real version the
#: moment those definitions move server-side, which is Phase 4.
#:
#: ``core`` does not use this. Its version is the item file's own
#: ``form_version``, which is a real one.
CLIENT_FORM_VERSION = "v1"


@dataclass
class AssessmentResult:
    """A service outcome the API layer turns into a response."""

    status: int
    body: Any = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status < 400


def _error(status: int, message: str) -> AssessmentResult:
    return AssessmentResult(status=status, body={"error": message})


def _chat_json(messages: List[Dict[str, Any]], model_env: str, default_model: str) -> dict:
    """One JSON-mode chat completion, parsed.

    Raises whatever the SDK raises -- callers decide what a provider failure
    means for their endpoint, and they do not all agree (WPLL falls back to the
    rules engine, Work Pulse returns 500).
    """
    client = llm.get_openai_client()
    response = client.chat.completions.create(
        model=os.environ.get(model_env, default_model),
        messages=messages,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content or "{}")


# ---------------------------------------------------------------------------
# Work Pulse Lite-Lite (anonymous teaser)
# ---------------------------------------------------------------------------

def _wpll_answers_error(answers: Any) -> Optional[str]:
    """Why a WPLL answers list cannot be scored, or None when it can.

    Shared by :func:`wpll_insight` and :func:`precheck` so the enqueue and the
    worker refuse the same bodies. The request schema lets ``question_id`` and
    ``option_id`` be null; the rules engine cannot read a null, so an answer
    without both strings is a 400 at the door, not a failed job later.
    """
    if not isinstance(answers, list):
        return "answers must be a list"
    if len(answers) == 0:
        return "answers is required"
    if len(answers) > WPLL_MAX_ANSWERS:
        return "Too many answers"
    for answer in answers:
        if not isinstance(answer, dict):
            return "each answer must be an object"
        if not isinstance(answer.get("question_id"), str) or not isinstance(
            answer.get("option_id"), str
        ):
            return "each answer needs a question_id and an option_id"
    return None


def wpll_insight(answers: Any) -> AssessmentResult:
    """Generate the anonymous WPLL teaser insight.

    Falls back silently to the deterministic rules engine when the LLM call
    fails or returns something unusable. That fallback is the right call here
    and only here: this is an unauthenticated teaser with no persistence, so a
    slightly less personal sentence beats an error page. The authenticated
    instruments return 500 instead, because a narrative they cannot generate is
    a result they cannot store.
    """
    from work_pulse.insight_engine import LOCKED_SECTION_TITLES, generate_result

    refusal = _wpll_answers_error(answers)
    if refusal is not None:
        return _error(400, refusal)

    insight_text = None
    try:
        system_msg, user_msg = assessment_prompts.build_wpll_insight_prompt(answers)
        parsed = _chat_json(
            [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "OPENAI_WPLL_MODEL",
            "gpt-4o-mini",
        )
        candidate = parsed.get("insight_text")
        if isinstance(candidate, str) and candidate.strip():
            insight_text = candidate
    except Exception:  # noqa: BLE001 -- see docstring; fall back, do not fail
        pass

    if insight_text is None:
        return AssessmentResult(status=200, body=generate_result(answers))

    return AssessmentResult(
        status=200,
        body={"insight_text": insight_text, "locked_sections": LOCKED_SECTION_TITLES},
    )


# ---------------------------------------------------------------------------
# Work Pulse, the original 12-question instrument (RETIRED 2026-10-02)
# ---------------------------------------------------------------------------
#
# Retired by Sebastian's ruling of 2026-10-02. Nothing in the client could start
# a sitting any more (the 24-item ``core`` instrument replaced it at /work-pulse
# on 2026-08-19), yet its scorer still accepted twelve answers and paid for an
# OpenAI narrative. The scorer is deleted rather than guarded: every door to it
# answers 410 (``solverah/api/v1/assessments.py``), and :func:`submit` refuses
# the kind as well, so a job queued before the deploy fails without a provider
# call when a worker picks it up.
#
# What stays is the READ side. A user who finished the old quiz keeps their
# stored narrative at ``GET /me/assessments/work_pulse/result``, and their rows
# stay in ``assessment_submissions`` for export and deletion like any other.

#: The problem text every write door gives the retired kind. Shared so the
#: route refusal and a pre-deploy job's failure say the same thing.
RETIRED_WORK_PULSE_MESSAGE = (
    "The original 12-question Work Pulse was retired on 2026-10-02 and no longer "
    "accepts submissions. The current Work Pulse is the core instrument: "
    "GET /assessments/core/form."
)


def get_work_pulse_result(user: User) -> AssessmentResult:
    """Return the stored narrative of a retired-instrument sitting, read-only.

    404 for "nothing to show", whichever way it arose: never taken, or taken
    with the narrative write failing. That second case used to be a 422 telling
    the client to resubmit; with the scorer retired there is nothing to resubmit
    to, so the honest answer is the same absence a never-taken user gets.
    """
    submission = assessment_repository.current_result(user.id, "work_pulse")
    if submission is None or submission.completed_at is None or not submission.result:
        return _error(404, "No Work Pulse results found")
    return AssessmentResult(status=200, body=submission.result)


def _store(user_id: int, kind: str, *, answers, result, narrative=None) -> None:
    """Record a completed, scored sitting of one of the deterministic-or-narrated
    instruments. Does not commit -- the caller owns the transaction.

    Only for the instruments whose whole result arrives in one request.
    ``core`` does not, because its persistence is behind
    ``assessment_store``; ``wpll`` does not, because its stored state arrives from
    an anonymous session being claimed rather than from a submission.

    Takes the id rather than the user: ``submit_manager_match`` has already
    committed once by the time it gets here, and that commit expired the row.
    """
    now = auth_domain.utcnow()
    submission = assessment_repository.open_current(user_id, kind, CLIENT_FORM_VERSION)
    submission.answers = answers
    submission.result = result
    submission.narrative = narrative
    submission.status = "scored"
    submission.completed_at = now
    submission.scored_at = now


# ---------------------------------------------------------------------------
# FocusType (authenticated, 5 scenes, deterministic)
# ---------------------------------------------------------------------------

def submit_focus_type(user: User, data: Dict[str, Any]) -> AssessmentResult:
    """Score and persist a FocusType result.

    Entirely deterministic -- no LLM, so no failure mode beyond a bad payload,
    and a bad payload is a 400: the request schema admits any object or list
    per scene, so the shape checks live with the scorer that reads them.
    """
    from focus_type.score import FocusTypePayloadError, score_focus_type

    missing = ["scene_%d" % i for i in range(1, 6) if "scene_%d" % i not in data]
    if missing:
        return _error(400, "Missing scene payloads: %s" % ", ".join(missing))

    try:
        result = score_focus_type(
            data["scene_1"],
            data["scene_2"],
            data["scene_3"],
            data["scene_4"],
            data["scene_5"],
        )
    except FocusTypePayloadError as exc:
        return _error(400, str(exc))

    user_id = user.id  # a value: the commit below expires the user row
    _store(user_id, "focus_type", answers=data, result=result)
    path_fit_repository.invalidate(user_id)  # F-5, with the Tier-1 cache below
    db.session.commit()
    path_cache.invalidate(user_id)

    return AssessmentResult(status=200, body=result)


# ---------------------------------------------------------------------------
# ManagerMatch (authenticated, 15 forced-choice items)
# ---------------------------------------------------------------------------

def submit_manager_match(user: User, answers: Any, logger) -> AssessmentResult:
    """Score deterministically, narrate with the LLM, then persist both."""
    from manager_match.score import score_manager_match

    if not isinstance(answers, list) or len(answers) != MANAGER_MATCH_ANSWER_COUNT:
        return _error(400, "answers must be a list of exactly 15 items")

    try:
        scoring = score_manager_match(answers)
    except ValueError as exc:
        return _error(400, str(exc))

    # The caller's user lookup began a transaction; it ends here rather than
    # idling through the provider call (see the module docstring). The id is
    # kept as a value because that commit expires the user row.
    user_id = user.id
    db.session.commit()

    try:
        llm_result = _chat_json(
            assessment_prompts.build_mm_narrative_prompt(
                answers, scoring["archetype"], scoring["dimension_scores"]
            ),
            "OPENAI_WP_MODEL",
            "gpt-4o-mini",
        )
    except Exception:  # noqa: BLE001 -- logged with a traceback below
        logger.exception("ManagerMatch narrative generation failed")
        return _error(500, "Unable to generate ManagerMatch results")

    required = ("narrative", "what_to_look_for", "red_flags", "archetype_description")
    if not all(key in llm_result for key in required):
        return _error(500, "Malformed response from model")

    # Scoring wins over the model's reply, not the other way round. The three
    # deterministic keys -- `archetype`, `dimension_scores`, and the
    # `scoring_key` saying which era the numbers belong to -- must not be
    # shadowed by a reply that happens to carry one of them. A marker a model
    # could overwrite would not be a marker, and the backfill that re-derives
    # unmarked rows takes this field at its word.
    result = {**llm_result, **scoring}

    _store(
        user_id,
        "manager_match",
        answers=answers,
        result=result,
        narrative=llm_result["narrative"],
    )
    path_fit_repository.invalidate(user_id)  # F-5, with the Tier-1 cache below
    db.session.commit()
    path_cache.invalidate(user_id)

    return AssessmentResult(status=200, body=result)


def get_manager_match_result(user: User) -> AssessmentResult:
    """Return the stored ManagerMatch result."""
    submission = assessment_repository.current_result(user.id, "manager_match")
    if submission is None or submission.result is None:
        return _error(404, "No ManagerMatch result found")
    return AssessmentResult(status=200, body=submission.result)


#: The minimum gap between two completed ``core`` sittings, or None for no
#: cooldown at all.
#:
#: None by Sebastian's ruling of 2026-10-02: Work Pulse is retakeable, with no
#: cooldown "for now". This constant is the whole server-side switch -- set it
#: to e.g. ``timedelta(days=90)`` and :func:`submit_person_side` refuses a
#: retake inside the window with a 409 whose error code is
#: ``retake_cooldown``. Nothing tells the client about the window yet, so
#: turning it on should come with a way for /work-pulse to hide its Retake
#: action; otherwise a user answers 24 questions and is refused at Finish.
CORE_RETAKE_COOLDOWN: Optional[timedelta] = None


def _refuse_core_retake_inside_cooldown(user_id: int) -> None:
    """Raise the 409 for a retake inside :data:`CORE_RETAKE_COOLDOWN`, if one is set.

    A first sitting is never refused: the window runs from the user's latest
    completed sitting, and a user with none has nothing to count from.
    """
    if CORE_RETAKE_COOLDOWN is None:
        return
    from assessment_store import latest_core_completed_at

    last = latest_core_completed_at(user_id)
    if last is not None and auth_domain.utcnow() - last < CORE_RETAKE_COOLDOWN:
        from solverah.errors import ConflictError

        raise ConflictError(
            detail="Work Pulse was taken recently. A retake opens once the cooldown has passed.",
            errors=[{"field": "core", "code": "retake_cooldown"}],
            extra={"retake_available_at": (last + CORE_RETAKE_COOLDOWN).isoformat()},
        )


def submit_person_side(user: User, responses: Any) -> AssessmentResult:
    """Score and persist a completed person-side assessment.

    A retake is an ordinary call. Each sitting appends its own submission row
    and raw responses; the current scores move to the newest sitting, and the
    Situation Report stays pinned to the sitting it was built from until the
    user recalibrates (``assessment_store``'s RETAKE SEMANTICS). The only
    retake-specific rule is :data:`CORE_RETAKE_COOLDOWN`, which is off.

    Everything correctness-critical -- the server-authoritative shuffle (D-04),
    the cross-dimension interleave, the opaque item tokens, the per-dimension
    arity check (D-02) -- lives in ``assessment_form``, and persistence goes
    through ``assessment_store``, the single sanctioned doorway to the
    person-side tables (D-01).  This function orchestrates the two and owns the
    transaction; it must not reach past either.

    The six dimension scores are deliberately absent from the result -- see the
    module docstring.
    """
    from assessment_form import AssessmentError, submit_form
    from assessment_store import persist_submission, respondent_id_for_user

    _refuse_core_retake_inside_cooldown(user.id)

    try:
        result = submit_form(respondent_id_for_user(user.id), responses)
    except AssessmentError as exc:
        return _error(400, str(exc))

    try:
        submission_id = persist_submission(db, user.id, result)
        db.session.commit()
    except Exception:
        # Re-raised, not swallowed: a failure to persist a completed assessment
        # is a 500 the operator must see. Rolling back first keeps the session
        # usable for the error handler.
        db.session.rollback()
        raise

    return AssessmentResult(
        status=200,
        body={
            "submission_id": submission_id,
            "scoring_key_version": result.scoring_key_version,
            "dimensions_scored": len(result.scores),
        },
    )


def person_side_form(user: User, logger) -> AssessmentResult:
    """The person-side items, ordered for this respondent.

    Ordering is server-authoritative: two independent PRNGs in two languages
    diverging is silent, and a divergence corrupts a resumed session's ordering
    rather than raising.
    """
    from assessment_form import PresentationContractError, get_form
    from assessment_store import respondent_id_for_user

    try:
        return AssessmentResult(status=200, body=get_form(respondent_id_for_user(user.id)))
    except PresentationContractError as exc:
        # Do not degrade to an unshuffled form. A form that silently renders in
        # difficulty order produces data that looks fine and is not (D-07).
        logger.error("assessment form unservable: %s", exc)
        return _error(500, "Assessment is temporarily unavailable")


# ===========================================================================
# Phase 1b -- one route, five instruments
# ===========================================================================
#
# Part 5.2 collapses five near-identical submit handlers into
# ``POST /assessments/{kind}/submissions``.  The registry below is what the
# ``{kind}`` discriminator resolves against, and the shape of it is the point:
# the five differ in a scorer, a prompt, a storage key, and whether they need a
# JWT, and nothing else.  Adding assessment #6 is an entry here.
#
# What is emphatically **not** unified is the result.  The five produce
# genuinely different payloads -- a narrative and an archetype, six dimension
# scores, a teaser sentence with locked section titles, a submission id with no
# scores at all -- and flattening them into a lowest-common-denominator envelope
# would throw away the part each instrument exists to produce.  Each kind keeps
# its own response model; the route is what is shared, not the shape.
#
# ``core``'s response is the sharpest example of why. It deliberately withholds
# the six dimension scores, because handing them back gives a retaking
# respondent a gradient to optimise against and teaches the item-to-dimension
# mapping the shuffle and interleave exist to hide. A "uniform" result envelope
# with a ``scores`` field would have quietly undone that.

@dataclass(frozen=True)
class AssessmentKind:
    """One instrument, and everything the unified route needs to know about it.

    Attributes:
        key: The ``{kind}`` path segment.
        title: Human-readable name, for the catalogue.
        requires_auth: Whether a JWT is required. ``wpll`` is the only one that
            does not: it is the anonymous teaser on the pre-launch funnel and
            has no account to attach to yet.
        scored_by: ``"rules"`` or ``"llm"``. Carried because it is what decides
            whether a provider outage makes the instrument unavailable, and the
            catalogue is the honest place to say so.
        has_form: Whether the server serves the items. Only ``core`` does; the
            other four are rendered from definitions the client already holds.
        has_result: Whether a completed submission can be re-read later.
        retired: The instrument no longer accepts submissions. Its stored
            results stay readable; every write door answers 410. Only the
            original 12-question ``work_pulse`` (retired 2026-10-02).
    """

    key: str
    title: str
    requires_auth: bool
    scored_by: str
    has_form: bool
    has_result: bool
    retired: bool = False


ASSESSMENT_KINDS = (
    AssessmentKind("core", "Culture Assessment", True, "rules", True, False),
    AssessmentKind("work_pulse", "Work Pulse", True, "llm", False, True, retired=True),
    AssessmentKind("wpll", "Work Pulse Lite-Lite", False, "llm", False, False),
    AssessmentKind("focus_type", "FocusType", True, "rules", False, True),
    AssessmentKind("manager_match", "ManagerMatch", True, "llm", False, True),
)

KINDS_BY_KEY = {kind.key: kind for kind in ASSESSMENT_KINDS}


def find_kind(key: str) -> Optional[AssessmentKind]:
    """The instrument named *key*, or None when nothing is."""
    return KINDS_BY_KEY.get(key)


def submit(kind: AssessmentKind, user: Optional[User], data: Dict[str, Any], logger) -> AssessmentResult:
    """Route a submission to the instrument that scores it.

    Dispatch is explicit rather than a callable stashed on the registry entry,
    because the signatures genuinely differ -- two take a bare answers
    list, one takes the whole payload, one takes no user -- and a uniform
    adapter would be five wrappers pretending to be one.

    Two callers since 3c, and the split is by ``scored_by``: the synchronous
    submit route reaches this only for ``core`` and ``focus_type`` (it answers
    the others 410), and the scoring-job worker reaches it only for ``wpll``
    and ``manager_match``. One dispatcher for both is what guarantees a queued
    scoring and the synchronous one it replaced produce the same body.

    A retired kind is refused here too, not only at the routes: a job queued
    before the retirement deployed still reaches this from the worker, and it
    must fail without a provider call.
    """
    if kind.retired:
        return _error(410, RETIRED_WORK_PULSE_MESSAGE)
    if kind.key == "core":
        return submit_person_side(user, data.get("responses"))
    if kind.key == "wpll":
        return wpll_insight(data.get("answers", []))
    if kind.key == "focus_type":
        return submit_focus_type(user, data)
    if kind.key == "manager_match":
        return submit_manager_match(user, data.get("answers"), logger)
    return _error(404, "Unknown assessment")


def precheck(kind: AssessmentKind, data: Dict[str, Any]) -> Optional[AssessmentResult]:
    """The 400 a submission would earn, decided without calling a provider.

    Exists for the asynchronous path and only for it.  ``POST
    /assessments/{kind}/scoring-jobs`` answers 202 and hands back a handle, so
    anything it does not check up front becomes a job that is accepted, queued,
    picked up by a worker and *then* failed -- turning what the synchronous
    route answers immediately as a 400 into a poll, a spinner, and an error
    delivered several seconds later.  A malformed body is not worth a round
    trip through the broker.

    **This deliberately duplicates the guards at the top of the three submit
    functions rather than being factored out of them.**  The guards still run
    -- a worker reaches them through :func:`submit` -- so extracting them would
    refactor the scorers to serve a check that already exists.  The duplication
    is held honest by ``tests/test_scoring_jobs.py``, which sends the same
    malformed body through the enqueue's precheck and through a directly-run
    job and asserts the two report the same error -- so the copy cannot drift
    without a test failing. (Two since the retired ``work_pulse`` lost its
    scorer.) WPLL's guard is the exception: its per-answer
    check grew past a length test, so both callers share
    :func:`_wpll_answers_error` rather than carry two copies of it.

    Returns None when there is nothing to object to.  A None here is not a
    promise the scoring will succeed: the provider can still fail, and that is
    a failed job rather than a 400, because by then the client has a handle.
    """
    if kind.key == "manager_match":
        answers = data.get("answers")
        if not isinstance(answers, list) or len(answers) != MANAGER_MATCH_ANSWER_COUNT:
            return _error(400, "answers must be a list of exactly 15 items")
        # The scorer is pure and calls no provider, so running it here costs
        # nothing and turns a bad question_id or choice into a 400 at the door
        # rather than a failed job. Its error text is the worker's, word for word.
        from manager_match.score import score_manager_match

        try:
            score_manager_match(answers)
        except ValueError as exc:
            return _error(400, str(exc))
        return None

    if kind.key == "wpll":
        refusal = _wpll_answers_error(data.get("answers", []))
        return None if refusal is None else _error(400, refusal)

    return None


def form(kind: AssessmentKind, user: User, logger) -> AssessmentResult:
    """The server-ordered items for *kind*.

    Only ``core`` has them. The other four are rendered from question
    definitions that ship with the client, and a 404 is the truthful answer for
    a form that does not exist rather than an empty one that implies it might.
    """
    if kind.key == "core":
        return person_side_form(user, logger)
    return _error(404, "%s has no server-served form" % kind.key)


def result(kind: AssessmentKind, user: User) -> AssessmentResult:
    """The stored result for *kind*, or a 404.

    ``core`` is absent on purpose, not pending. Its scores are withheld from the
    submit response for a documented reason -- an aspirational respondent
    optimising against a visible gradient -- and a read endpoint that handed
    them back would be the same disclosure through a different door.
    """
    if kind.key == "work_pulse":
        return get_work_pulse_result(user)
    if kind.key == "manager_match":
        return get_manager_match_result(user)
    if kind.key == "focus_type":
        submission = assessment_repository.current_result(user.id, "focus_type")
        if submission is None or submission.result is None:
            return _error(404, "No FocusType result found")
        return AssessmentResult(status=200, body=submission.result)
    return _error(404, "%s does not store a retrievable result" % kind.key)


def catalogue(user: User) -> AssessmentResult:
    """Every instrument, with this user's completion state against each.

    New in Phase 1b, and the thing that makes ``{kind}`` discoverable: without
    it a client has to hard-code the five keys and work out completion from
    three unrelated places -- ``user_intake`` timestamps, two blob keys, and the
    person-side tables.
    """
    finished = completed_kinds(user)
    return AssessmentResult(
        status=200,
        body={
            "data": [
                {
                    "kind": kind.key,
                    "title": kind.title,
                    "requires_auth": kind.requires_auth,
                    "scored_by": kind.scored_by,
                    "has_form": kind.has_form,
                    "has_result": kind.has_result,
                    "completed": kind.key in finished,
                }
                for kind in ASSESSMENT_KINDS
            ]
        },
    )


def completed_kinds(user: User) -> set:
    """Every instrument key *user* has finished.

    Phase 1b's version of this read four storage locations, one instrument at a
    time, and the docstring said so. It is two reads now and they are the two
    that genuinely differ:

    * ``core``'s completion is keyed to the *current* ``scoring_key_version``, so
      a sitting of a superseded instrument is correctly not completion. That rule
      lives in ``assessment_store`` behind D-01's doorway and cannot be answered
      by a query here.
    * Everything else is one ``SELECT DISTINCT kind`` over the shared table.

    Neither read is allowed to fail a page load. ``core``'s is wrapped for the
    same reason it always was: the flag gates a banner, and a wrong ``False``
    re-shows a prompt to someone who already finished -- visible and recoverable
    -- while an exception is a broken dashboard.
    """
    from assessment_store import has_completed_assessment

    finished = assessment_repository.completed_kinds(user.id)
    try:
        if has_completed_assessment(user.id):
            finished.add("core")
    except Exception:  # noqa: BLE001 -- a catalogue must not fail a page load
        pass
    return finished


# ---------------------------------------------------------------------------
# Trait preferences: per-trait tolerance and must-have (six-trait model, 2026-10-13)
# ---------------------------------------------------------------------------
#
# A short, skippable step after core, retakeable any time. Core itself -- its items,
# its scoring, its D-01 path -- is untouched: these are a separate person-side record
# behind `assessment_store`, and the rules live in `solverah.domain.trait_preferences`.


class TraitPreferencesInvalid(ValidationError):
    """A PUT /me/trait-preferences body that breaks a rule: a missing, unknown or
    repeated trait, a step count outside 0..2, or more than two must-haves.

    400 rather than ValidationError's 422, by ruling (2026-10-13 build plan, review
    focus 5): these are the product's rules, not the body's shape. A body that does
    not even match the request schema is still the house 422 from the enforcement
    hook. The `errors` entries carry the specific `code` a client can branch on.
    """

    status = 400
    title = "Invalid trait preferences"
    code = "invalid_trait_preferences"


def _trait_preferences_body(prefs) -> Dict[str, Any]:
    from solverah.domain.trait_preferences import MAX_MUST_HAVES, TRAIT_KEYS

    return {
        "answered": all(prefs[key].answered for key in TRAIT_KEYS),
        "max_must_haves": MAX_MUST_HAVES,
        "traits": [
            {
                "dimension_key": key,
                "under_steps": prefs[key].under_steps,
                "over_steps": prefs[key].over_steps,
                "must_have": prefs[key].must_have,
                "answered": prefs[key].answered,
            }
            for key in TRAIT_KEYS
        ],
    }


def read_trait_preferences(user: User) -> Dict[str, Any]:
    """GET /me/trait-preferences: the latest sitting, or all six unanswered."""
    from assessment_store import get_trait_preferences

    return _trait_preferences_body(get_trait_preferences(db, user.id))


def save_trait_preferences(user: User, payload: Any) -> Dict[str, Any]:
    """PUT /me/trait-preferences: append a sitting of all six traits and echo it back.

    Raises TraitPreferencesInvalid (400) for a rule violation. The echo is built from
    what was written, so there is no read-back after the commit.
    """
    from assessment_store import save_trait_preferences as store_save
    from solverah.domain.trait_preferences import (
        TraitPreferenceError,
        parse_trait_preferences,
    )

    raw = payload.get("traits") if isinstance(payload, dict) else None
    try:
        prefs = parse_trait_preferences(raw)
    except TraitPreferenceError as exc:
        raise TraitPreferencesInvalid(detail=str(exc), errors=exc.errors) from exc

    store_save(db, user.id, prefs)
    db.session.commit()
    return _trait_preferences_body(prefs)
