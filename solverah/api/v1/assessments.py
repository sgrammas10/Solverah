"""The five assessment instruments.

Paths unchanged: ``/work-pulse/lite-lite/result``, ``/work-pulse/submit``,
``/work-pulse/results``, ``/focus-type/submit``, ``/manager-match/submit``,
``/manager-match/results``, ``/assessment/form``, ``/assessment/submit``.

The two person-side culture routes at the bottom are thin on purpose.  Every
correctness requirement -- the server-authoritative shuffle (D-04), the
cross-dimension interleave, the opaque item tokens, the per-dimension arity check
(D-02) -- lives in ``assessment_form.py`` and ``present_items.py``.  A route that
reimplements any of it, or reaches past ``assessment_form`` into
``present_items`` / ``score_person_side`` directly, is a bug.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required, verify_jwt_in_request

from security import (
    DEFAULT_LIMITS,
    WPLL_ANON_GLOBAL_LIMIT,
    WPLL_ANON_PER_IP_LIMIT,
    global_rate_limit_key,
)
from solverah.errors import GoneError, NotFoundError
from solverah.extensions import limiter
from solverah.openapi import document
from solverah.repositories import user_repository
from solverah.schemas import PROBLEM_RESPONSE_MODEL, LegacyError
from solverah.schemas.assessments import (
    SUBMISSION_REQUESTS,
    AssessmentScoringJobStatus,
    AssessmentCatalogueResponse,
    AssessmentFormResponse,
    AssessmentSubmissionRequest,
    AssessmentSubmissionResponse,
    AssessmentSubmitRequest,
    AssessmentSubmitResponse,
    FocusTypeResult,
    FocusTypeSubmitRequest,
    ManagerMatchResult,
    ManagerMatchSubmitRequest,
    ScoringJobAccepted,
    TraitPreferencesDocument,
    TraitPreferencesPutRequest,
    WpllResultResponse,
    WpllSubmitRequest,
)
from solverah.schemas.manager_playbook import (
    ManagerProfileSubmitRequest,
    ManagerProfileSubmitResponse,
)
from solverah.services import assessment_service, manager_playbook_service, scoring_jobs

__all__ = ["assessments_bp"]

assessments_bp = Blueprint("assessments", __name__)

_AUTHENTICATED = ["accessTokenCookie"]
_AUTHENTICATED_WRITE = ["accessTokenCookie", "csrfHeader"]

#: Rate-limit bucket namespace for a submission, completed with the ``{kind}``.
#: Shared by the submit route and the scoring-job enqueue, so the two doors to
#: one instrument draw a single budget (A9) -- see ``_submission_scope``.
#:
#: Used with ``limiter.shared_limit``, never ``limiter.limit``.
#: ``limit(scope=...)`` keys its bucket as ``"{endpoint}:{scope}"``, which
#: sub-divides one endpoint rather than joining two, so written that way the
#: unified route and the handler it replaces would still hold two independent
#: allowances for the whole cutover. Only ``shared_limit`` drops the endpoint
#: from the key.
SUBMIT_SCOPE_PREFIX = "assessments:submit:"

DEFAULT_SUBMISSION_LIMIT = "5 per minute"

#: Rate limit for a job poll, and it is deliberately not the global default.
#:
#: A poll is a single indexed-row read that makes no provider call, so A9's
#: reasoning does not reach it: those budgets exist to bound provider spend, and
#: a poll spends nothing. Left on the defaults it inherits ``50 per hour`` --
#: measured, not assumed -- which a client polling every two seconds exhausts
#: inside one scoring, and which it shares with every other default-limited
#: route the same browser is using.
#:
#: The day cap is restated rather than dropped. ``@limiter.limit`` defaults to
#: ``override_defaults=True``, so naming only a per-minute allowance here would
#: silently remove the ``200 per day`` backstop while looking like a tightening
#: -- the same trap ``SUBMISSION_LIMITS`` documents.
#:
#: ``GET /me/resume-parse-jobs/{job_id}`` (3a) has the identical exposure and is
#: deliberately left alone: it is an existing route, changing its limit is a
#: behaviour change no contract test would catch, and it is a smaller problem
#: there because a parse finishes in seconds. It is recorded in A19 rather than
#: fixed in passing.
POLL_LIMIT = "60 per minute;2000 per day"

#: Per-instrument, per-IP limits. Four are preserved exactly as the five
#: separate handlers had them.
#:
#: ``wpll`` is the one that changed, in S1. It used to be spelled
#: ``";".join(DEFAULT_LIMITS)`` -- the global defaults, restated so that
#: decorating the route could not silently drop the 200-per-day backstop
#: (``shared_limit`` defaults to ``override_defaults=True``). Restating them was
#: right; *those numbers* were not the right numbers for the application's one
#: unauthenticated door onto a paid provider. 200/day with no burst term meant
#: the 2026-09 audit could fire 40 enqueues from one address in 49 seconds and
#: collect 40 ``202``s.
#:
#: It now carries ``WPLL_ANON_PER_IP_LIMIT``, which keeps a day term (so the
#: backstop is still not dropped) and adds the minute and hour terms the door
#: needed. The paired global ceiling lives on the routes themselves, below --
#: it cannot live in this table, because it is keyed differently.
#:
#: The retired ``work_pulse`` has no entry: every write door refuses it, and a
#: refusal draws the default bucket like any unlisted kind.
SUBMISSION_LIMITS = {
    "core": DEFAULT_SUBMISSION_LIMIT,
    "focus_type": DEFAULT_SUBMISSION_LIMIT,
    "manager_match": DEFAULT_SUBMISSION_LIMIT,
    "wpll": WPLL_ANON_PER_IP_LIMIT,
}


def _respond(result: assessment_service.AssessmentResult):
    return jsonify(result.body), result.status


def _current_user():
    return user_repository.find_by_email(get_jwt_identity())


# ---------------------------------------------------------------------------
# Person-side culture assessment (S-01)
# ---------------------------------------------------------------------------


def _kind_or_404(kind: str):
    """Resolve ``{kind}``, or raise the 404 an unknown instrument deserves."""
    resolved = assessment_service.find_kind(kind)
    if resolved is None:
        raise NotFoundError(
            detail="Unknown assessment kind %r" % kind,
            errors=[{"field": "kind", "code": "unknown_kind"}],
        )
    return resolved


def _refuse_retired(resolved) -> None:
    """Raise the 410 every write door gives a retired instrument.

    The original 12-question ``work_pulse`` (retired 2026-10-02) is the only
    one. Its own code, ``kind_retired``, rather than Phase 3c's
    ``moved_to_scoring_jobs``: that refusal carries a forwarding address for
    the same operation, and this one has none -- the operation is gone, not
    moved. Raised before auth and before the body is read, like Phase 3c's,
    because it holds for any caller sending anything. The stored result stays
    readable at ``GET /me/assessments/work_pulse/result``.
    """
    if resolved.retired:
        raise GoneError(
            detail=assessment_service.RETIRED_WORK_PULSE_MESSAGE,
            errors=[{"field": "kind", "code": "kind_retired"}],
        )


def _sync_kind_or_410(kind: str):
    """Resolve ``{kind}`` and require that it still submits synchronously.

    The mirror of :func:`_job_kind_or_404`, splitting the five instruments on
    the same predicate (``scoring_jobs.is_job_eligible``) so the two routes
    partition them identically: the three provider-scored kinds queue and are
    refused here, the two rules-scored kinds submit here and 404 there.

    410 rather than 404, because a 404 would lie twice over. The kind exists --
    an unknown one is the 404, above -- and this operation existed for it until
    Phase 3c deleted the synchronous half. Silently accepting instead would
    resurrect the blocking provider call the whole phase existed to remove. The
    problem document carries where the work went, so a client that missed the
    cutover is told the fix rather than left to guess.
    """
    resolved = _kind_or_404(kind)
    _refuse_retired(resolved)
    if scoring_jobs.is_job_eligible(resolved.key):
        raise GoneError(
            detail=(
                "%s is scored off the request path since Phase 3c. Queue the "
                "scoring at POST /assessments/%s/scoring-jobs and poll the job."
                % (resolved.key, resolved.key)
            ),
            errors=[{"field": "kind", "code": "moved_to_scoring_jobs"}],
            extra={"replaced_by": "/assessments/%s/scoring-jobs" % resolved.key},
        )
    return resolved


def _require_auth_for(kind) -> None:
    """Enforce the JWT for instruments that need one.

    ``@jwt_required()`` cannot be used here, because one of the five is
    deliberately anonymous: ``wpll`` is the pre-launch teaser and has no account
    to attach to yet. So the requirement moves inside the handler, where it can
    depend on ``{kind}``.

    ``verify_jwt_in_request()`` is the same function the decorator calls, which
    matters more than it looks: it performs the identical cookie lookup, the
    identical signature check, **and the identical CSRF check** on a
    state-changing method. Hand-rolling an "is there a cookie" test here would
    have quietly dropped CSRF protection from four instruments.
    """
    if kind.requires_auth:
        verify_jwt_in_request()


def _submission_scope(_endpoint: str) -> str:
    """Rate-limit bucket for one submission, keyed by instrument.

    This is the decision that collapsing five routes into one forces, and it is
    made deliberately rather than inherited.

    Flask-Limiter composes its storage key from the endpoint name. Five handlers
    at 5 per minute each were five independent budgets; one handler is one
    shared budget, so a user who finished Work Pulse and moved on to FocusType
    would have been spending a single allowance across two unrelated
    instruments. The two ways out were to raise the limit -- which would let any
    *one* instrument be hit five times harder than it is today -- or to key the
    bucket by kind, which preserves each instrument's budget exactly.

    Keying wins because the limit exists to bound provider spend, and provider
    spend is per call to a specific instrument. Raising it to 25 would have
    bought a 5x on the expensive ones to solve a problem that is really about
    which bucket a call lands in.

    The scope is also what keeps the superseded handlers sharing these buckets
    while both paths are live -- otherwise ``POST /work-pulse/submit`` and
    ``POST /assessments/work_pulse/submissions`` would be two endpoints, two
    buckets, and 10 per minute for the length of the cutover.
    """
    kind = (request.view_args or {}).get("kind") or "unknown"
    return "%s%s" % (SUBMIT_SCOPE_PREFIX, kind)


def _anonymous_submission_scope(_endpoint: str) -> str:
    """Bucket for the *global* spend ceiling on an anonymous instrument.

    Keyed by instrument like ``_submission_scope``, and for the same reason --
    the two anonymous doors this application has must not be able to close each
    other. It carries its own ``:global`` suffix rather than reusing that scope
    because the bucket underneath it is keyed on a constant, not on the caller;
    the same name with two key functions would be one name for two different
    counters.
    """
    kind = (request.view_args or {}).get("kind") or "unknown"
    return "%s%s:global" % (SUBMIT_SCOPE_PREFIX, kind)


def _is_authenticated_kind() -> bool:
    """Whether the instrument being submitted needs a JWT.

    Used as ``exempt_when`` on the global ceiling below, so the ceiling applies
    to the anonymous instruments and to nothing else. Derived from the registry
    rather than from a literal ``kind == "wpll"``, so a second anonymous
    instrument inherits the control instead of quietly arriving without one.

    An unknown ``{kind}`` counts as authenticated and is therefore exempt: it is
    about to be a 404 from ``_job_kind_or_404``, and spending the anonymous
    budget on requests that reach no provider would let anyone close the door
    for real visitors by typing a name that does not exist.
    """
    kind = assessment_service.find_kind((request.view_args or {}).get("kind") or "")
    return kind is None or kind.requires_auth


def _submission_limit() -> str:
    """The limit string for the instrument being submitted.

    Per-kind because the five do not have the same limit today and unifying the
    route must not unify that either.

    ``wpll`` is the one that needs stating. It carries no per-endpoint limit at
    all, so it runs on the global defaults -- and ``@limiter.limit`` defaults to
    ``override_defaults=True``, which means decorating it with a bare "5 per
    minute" would have *removed* its 200-per-day cap while appearing to tighten
    it. Naming the defaults explicitly keeps them.
    """
    kind = (request.view_args or {}).get("kind") or "unknown"
    return SUBMISSION_LIMITS.get(kind, DEFAULT_SUBMISSION_LIMIT)


@document(
    "List the assessment catalogue with this user's completion state",
    tags=["assessments"],
    responses={200: AssessmentCatalogueResponse, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
)
@assessments_bp.route("/assessments", methods=["GET"])
@jwt_required()
def assessment_catalogue():
    """GET /assessments - the five instruments and where this user stands.

    New in Phase 1b. Without it a client has to hard-code the five kind keys and
    work out completion from three unrelated places: user_intake timestamps, two
    profile_data keys, and the person-side tables.
    """
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return _respond(assessment_service.catalogue(user))


@document(
    "Fetch an assessment's items, ordered for this respondent",
    tags=["assessments"],
    responses={200: AssessmentFormResponse, 404: LegacyError, 500: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
)
@assessments_bp.route("/assessments/<kind>/form", methods=["GET"])
@jwt_required()
def assessment_kind_form(kind: str):
    """GET /assessments/{kind}/form - the items, ordered for this respondent.

    Only `core` serves a form; the other four are rendered from definitions the
    client ships with, and asking for theirs is a 404 rather than an empty
    payload that implies one might arrive.

    The payload carries `blocks`, not `dimensions`. The client renders it
    verbatim: it must not sort, group, re-shuffle, or reorder options. Ordering
    is server-authoritative because two independent PRNGs in two languages
    diverging is silent, and a divergence corrupts a resumed session's ordering
    rather than raising (D-04).
    """
    resolved = _kind_or_404(kind)
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return _respond(assessment_service.form(resolved, user, current_app.logger))


@document(
    "Submit a completed assessment",
    tags=["assessments"],
    request=AssessmentSubmissionRequest,
    request_for=lambda view_args, _body: (
        None
        if scoring_jobs.is_job_eligible(view_args.get("kind") or "")
        else SUBMISSION_REQUESTS.get(view_args.get("kind"))
    ),
    responses={
        200: AssessmentSubmissionResponse,
        400: LegacyError,
        404: LegacyError,
        409: PROBLEM_RESPONSE_MODEL,
        410: PROBLEM_RESPONSE_MODEL,
        500: LegacyError,
    },
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "Serves the two rules-scored instruments, `core` and `focus_type`, "
        "which score deterministically in-process and stay synchronous by "
        "design (A19). `{kind}` selects both the request body and the response "
        "body -- the route is shared, the payloads are not.\n\n"
        "`core` may be retaken: each sitting is stored as its own. A cooldown "
        "between sittings exists as a server setting and is off; when it is "
        "on, a retake inside it answers `409` with error code "
        "`retake_cooldown`.\n\n"
        "The two provider-scored kinds, `wpll` and `manager_match`, answer "
        "`410 Gone` here since Phase 3c: their scoring moved off the request "
        "path, and the problem document's `replaced_by` names the "
        "`POST /assessments/{kind}/scoring-jobs` operation that took it. "
        "The retired `work_pulse` (the original 12-question instrument, "
        "retired 2026-10-02) answers `410` with error code `kind_retired` and "
        "no `replaced_by`."
    ),
)
# NOTE: the anonymous *global* ceiling is deliberately NOT on this route, only
# on the enqueue below. It bounds provider spend, and this route spends nothing
# for `wpll`: `_sync_kind_or_410` refuses before auth and before the body is
# read. Counting refusals into a shared bucket would hand anyone a way to close
# the real teaser for every visitor by hammering a door that is already gone --
# 500 free hits, no provider call, no cost to the attacker. The per-IP bucket
# below still counts them, and should: it is per-caller, so it bounds only the
# caller doing it. Same distinction POLL_LIMIT makes for the same reason.
@assessments_bp.route("/assessments/<kind>/submissions", methods=["POST"])
@limiter.shared_limit(_submission_limit, scope=_submission_scope)
def assessment_kind_submit(kind: str):
    """POST /assessments/{kind}/submissions - score and persist a submission.

    Phase 3c closed this route to the three provider-scored instruments; the
    refusal is in `_sync_kind_or_410`, and it comes before auth and before the
    body is read because the operation is gone for those kinds no matter who
    asks or what they send. The rate-limit decorator stays exactly as it was:
    `_submission_scope` keys one bucket per instrument, which is what keeps
    `core` and `focus_type` on their own budgets (A9) -- and a refused call
    still draws the moved kind's shared bucket, so the closed door can never
    become a way around the enqueue's limit.

    Note what is NOT unified: the result. `core` returns a submission id and no
    dimension scores at all -- handing them back would give a retaking
    respondent a gradient to optimise against, which teaches the
    item-to-dimension mapping the shuffle and interleave exist to hide. A
    uniform result envelope with a `scores` field would have undone that
    quietly.
    """
    resolved = _sync_kind_or_410(kind)
    _require_auth_for(resolved)

    user = _current_user() if resolved.requires_auth else None
    if resolved.requires_auth and not user:
        return jsonify({"error": "User not found"}), 404

    return _respond(
        assessment_service.submit(
            resolved, user, request.get_json(silent=True) or {}, current_app.logger
        )
    )


@document(
    "Retrieve a stored assessment result",
    tags=["assessments"],
    responses={200: AssessmentSubmissionResponse, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
    description=(
        "`{kind}` selects the response shape, as on the submit route. Only "
        "`work_pulse`, `focus_type`, and `manager_match` store a re-readable "
        "result. `work_pulse` is the retired original instrument: its stored "
        "narrative stays readable here, read-only, and a sitting without one "
        "is a `404` like no sitting at all. `core` is absent by design rather "
        "than pending -- its scores are withheld from the submit response for "
        "a documented reason, and a read endpoint would be the same "
        "disclosure through another door."
    ),
)
@assessments_bp.route("/me/assessments/<kind>/result", methods=["GET"])
@jwt_required()
def assessment_kind_result(kind: str):
    """GET /me/assessments/{kind}/result - re-read a completed assessment.

    Used to rehydrate a results page in a fresh browser session where
    sessionStorage has been cleared.
    """
    resolved = _kind_or_404(kind)
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return _respond(assessment_service.result(resolved, user))


# ---------------------------------------------------------------------------
# Trait preferences: per-trait tolerance and must-have (six-trait model, 2026-10-13)
# ---------------------------------------------------------------------------


@document(
    "Read the user's per-trait tolerance and must-have flags",
    tags=["assessments"],
    responses={200: TraitPreferencesDocument, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
    description=(
        "The latest sitting of the short step that follows Work Pulse. A user who "
        "never answered, or skipped, gets `answered: false` with all six traits "
        "unanswered (steps `null`) -- matching and the Situation Report then behave "
        "exactly as they did before this step existed."
    ),
)
@assessments_bp.route("/me/trait-preferences", methods=["GET"])
@jwt_required()
def get_trait_preferences():
    """GET /me/trait-preferences - the latest sitting, or all six unanswered."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(assessment_service.read_trait_preferences(user)), 200


@document(
    "Save a new sitting of per-trait tolerance and must-have flags",
    tags=["assessments"],
    request=TraitPreferencesPutRequest,
    responses={
        200: TraitPreferencesDocument,
        400: PROBLEM_RESPONSE_MODEL,
        404: LegacyError,
    },
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "Carries all six traits. Each save is a new sitting; earlier sittings are "
        "kept and the newest is current. Answers `200` with the saved document.\n\n"
        "`400` (`invalid_trait_preferences`) when the body breaks a rule; each "
        "`errors` entry names it: `missing_trait`, `unknown_trait`, "
        "`duplicate_trait`, `steps_out_of_range` (steps must be 0, 1 or 2), "
        "`invalid_type`, or `too_many_must_haves` (at most two). A body that does "
        "not match the request schema at all is `422`."
    ),
)
@assessments_bp.route("/me/trait-preferences", methods=["PUT"])
@limiter.limit(DEFAULT_SUBMISSION_LIMIT)
@jwt_required()
def put_trait_preferences():
    """PUT /me/trait-preferences - append a sitting of all six traits."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return (
        jsonify(
            assessment_service.save_trait_preferences(
                user, request.get_json(silent=True) or {}
            )
        ),
        200,
    )


# ---------------------------------------------------------------------------
# Manager Decoder: the observed-manager instrument (BUILD_PLAN C-3)
# ---------------------------------------------------------------------------
#
# Deliberately not a sixth `{kind}` in the unified registry above. ⚑4 makes
# `manager_profiles` its own shared store, read by the Decoder's playbook today and
# the Situation Report's manager section later -- folding it into `assessment_submissions`
# would put it behind that table's single-current-row-per-kind constraint, which is wrong
# for an append-only instrument, and behind `{kind}`'s job/sync split, which is wrong for
# an instrument that scores deterministically and instantly like `focus_type`.
#
# `GET /me/manager-playbook` lives in `solverah/api/v1/me.py` -- it is a read about the
# authenticated principal, the same reason `GET /me/assessments/{kind}/result` lives there
# and not here.


@document(
    "Submit a manager-profile sitting; score, store, and assemble the playbook",
    tags=["assessments"],
    request=ManagerProfileSubmitRequest,
    responses={
        200: ManagerProfileSubmitResponse,
        400: LegacyError,
        404: LegacyError,
    },
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "Scores deterministically and instantly, like `focus_type` -- no provider call, "
        "no job, no polling. Stores an append-only `manager_profiles` row (D-16 "
        "tradition: a retake is a new row, never an update) and, when this user already "
        "has a completed ManagerMatch sitting, assembles the diff playbook in the same "
        "response. `playbook` is `null` when there is no ManagerMatch yet -- that is not "
        "an error here; `GET /me/manager-playbook` is where a missing ManagerMatch "
        "answers `409`."
    ),
)
@assessments_bp.route("/assessments/manager-profile", methods=["POST"])
@limiter.limit(DEFAULT_SUBMISSION_LIMIT)
@jwt_required()
def submit_manager_profile():
    """POST /assessments/manager-profile - score, persist, and diff against ManagerMatch."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    result = manager_playbook_service.submit_manager_profile(user, data.get("answers"))
    return jsonify(result.body), result.status


# ---------------------------------------------------------------------------
# Phase 3b/3c -- scoring off the request path
# ---------------------------------------------------------------------------
#
# `202` + a job handle for the three instruments that call a provider. 3b added
# these alongside the synchronous submit; 3c closed the synchronous half once
# the frontend had moved (43a2024), so this is now the only way those three
# score. The submit route above answers their callers 410 with a pointer here.
#
# `core` and `focus_type` have no job endpoint and answer 404 here. They score
# from deterministic tables without opening a socket, and a job for work that
# finishes before the poll could be issued costs two round trips and a row to
# reap to deliver a slower answer. The reasoning is in `scoring_jobs`.


def _job_kind_or_404(kind: str):
    """Resolve ``{kind}`` and require that it scores off the request path.

    A 404 for `core` and `focus_type` rather than a 400: the truthful statement
    is that this operation does not exist for those instruments, not that the
    caller asked for it wrongly. It is the same answer `GET
    /assessments/{kind}/form` gives for the four instruments that serve no form.

    A 410 for the retired `work_pulse`, on the enqueue and the poll alike: it
    had this operation until 2026-10-02 and has none now.
    """
    resolved = _kind_or_404(kind)
    _refuse_retired(resolved)
    if not scoring_jobs.is_job_eligible(resolved.key):
        raise NotFoundError(
            detail="%s is scored synchronously and has no scoring job" % resolved.key,
            errors=[{"field": "kind", "code": "not_job_scored"}],
        )
    return resolved


@document(
    "Queue an assessment scoring and return a job handle",
    tags=["assessments"],
    request=AssessmentSubmissionRequest,
    request_for=lambda view_args, _body: (
        SUBMISSION_REQUESTS.get(view_args.get("kind"))
        if scoring_jobs.is_job_eligible(view_args.get("kind") or "")
        else None
    ),
    responses={
        202: ScoringJobAccepted,
        400: LegacyError,
        404: LegacyError,
        410: PROBLEM_RESPONSE_MODEL,
    },
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "The only way the provider-scored instruments score since Phase 3c. "
        "Takes the body `POST /assessments/{kind}/submissions` used to take "
        "for these kinds; answers `202` with a job handle instead of blocking "
        "on the provider. Poll "
        "`GET /assessments/{kind}/scoring-jobs/{job_id}` until `status` is "
        "`succeeded` or `failed`.\n\n"
        "Only the two provider-scored instruments have this operation: "
        "`wpll` and `manager_match`. `core` and `focus_type` score "
        "deterministically in-process and answer `404` here -- they are served "
        "by the synchronous submit route, which since Phase 3c serves only "
        "them. The retired `work_pulse` answers `410` with error code "
        "`kind_retired`: it accepts no submissions and calls no provider.\n\n"
        "**This shares one rate-limit budget with the synchronous submit for "
        "the same instrument.** The limit bounds provider spend, and spend does "
        "not move when the call moves to a worker (A9), so queueing and "
        "submitting draw on the same allowance rather than two."
    ),
)
@assessments_bp.route("/assessments/<kind>/scoring-jobs", methods=["POST"])
@limiter.shared_limit(WPLL_ANON_GLOBAL_LIMIT, scope=_anonymous_submission_scope,
                      key_func=global_rate_limit_key, exempt_when=_is_authenticated_kind)
@limiter.shared_limit(_submission_limit, scope=_submission_scope)
def assessment_kind_scoring_job(kind: str):
    """POST /assessments/{kind}/scoring-jobs - queue the scoring, return 202.

    The rate-limit decorator is the same expression the synchronous submit
    carries, and that is the whole of A9 on this route. `_submission_scope`
    keys the bucket on `{kind}` and `shared_limit` drops the endpoint from the
    key, so this operation and `POST /assessments/{kind}/submissions` count into
    one per-instrument budget. Written as `@limiter.limit(scope=...)` it would
    key as "{endpoint}:{scope}" and hand every instrument a second, independent
    allowance reachable by queueing instead of submitting -- which is A9 undone
    by the same mistake the Phase 1b cutover made and caught.

    The body is validated before anything is enqueued. A malformed submission is
    a 400 here exactly as it is on the synchronous route; letting it through
    would convert an immediate, actionable error into a 202, a poll, and a
    failed job several seconds later.

    **The second decorator is S1's, and it does a different job.** For `wpll` --
    the one instrument with `requires_auth=False` -- this is an unauthenticated
    route that commits a row and makes a paid provider call. A per-IP limit
    cannot bound that, because the quantity an abuser controls freely is the
    number of distinct addresses: N addresses buy N times the budget. The
    `global_rate_limit_key` bucket is keyed on a constant, so it is one counter
    for the whole deployment and it is the control that actually caps the bill.
    `exempt_when=_is_authenticated_kind` keeps it off the other four, which have
    an account behind them and are bounded by that instead.

    This is the same two-limit shape `POST /intake/quiz-preview/insights`
    already used; see `security.WPLL_ANON_GLOBAL_LIMIT` for what is shared with
    it, what is not, and why.
    """
    resolved = _job_kind_or_404(kind)
    _require_auth_for(resolved)

    user = _current_user() if resolved.requires_auth else None
    if resolved.requires_auth and not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    refusal = assessment_service.precheck(resolved, data)
    if refusal is not None:
        return _respond(refusal)

    job = scoring_jobs.create_assessment(resolved.key, user, data)
    job_id = job.public_id.hex
    return (
        jsonify(
            {
                "job_id": job_id,
                "status": job.status,
                "status_url": "/assessments/%s/scoring-jobs/%s" % (resolved.key, job_id),
            }
        ),
        202,
    )


@document(
    "Report the state of a queued assessment scoring",
    tags=["assessments"],
    responses={200: AssessmentScoringJobStatus, 404: LegacyError, 410: PROBLEM_RESPONSE_MODEL},
    security=_AUTHENTICATED,
    enforce=True,
    description=(
        "`{kind}` selects the response shape, as it does on the submit route: "
        "`result` is that instrument's own result model and nothing else, and "
        "it is present only once `status` is `succeeded`. There is no shared "
        "result envelope here for the same reason there is none there (A12).\n\n"
        "`wpll` needs no JWT, because the instrument does not: it is the "
        "anonymous teaser, its job has no owner, and the handle is what "
        "authorises the poll. `manager_match` scopes the handle to the "
        "authenticated user. The retired `work_pulse` answers `410`."
    ),
)
@assessments_bp.route("/assessments/<kind>/scoring-jobs/<job_id>", methods=["GET"])
@limiter.limit(POLL_LIMIT)
def assessment_kind_scoring_job_status(kind: str, job_id: str):
    """GET /assessments/{kind}/scoring-jobs/{job_id} - poll a queued scoring.

    404 covers four cases deliberately: no such job, a malformed handle, a job
    belonging to somebody else, and a handle for a job of a different
    instrument. The first three are the rule `resume_jobs` follows -- confirming
    a handle exists is the only thing a handle has to protect. The fourth is
    A12's promise read from the other end: a Work Pulse job served at the
    ManagerMatch path would answer under ManagerMatch's response model with a
    Work Pulse body.
    """
    resolved = _job_kind_or_404(kind)
    _require_auth_for(resolved)

    if resolved.requires_auth:
        user = _current_user()
        if not user:
            return jsonify({"error": "User not found"}), 404
        job = scoring_jobs.find_for_user(
            user.id,
            job_id,
            job_type=scoring_jobs.ASSESSMENT,
            kind=resolved.key,
        )
    else:
        job = scoring_jobs.find_anonymous(job_id, kind=resolved.key)

    if job is None:
        return jsonify({"error": "Job not found"}), 404

    return jsonify(scoring_jobs.status_for(job)), 200
