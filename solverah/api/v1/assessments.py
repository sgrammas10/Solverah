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

from security import DEFAULT_LIMITS
from solverah.errors import NotFoundError
from solverah.extensions import limiter
from solverah.openapi import document
from solverah.repositories import user_repository
from solverah.schemas import LegacyError
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
    WorkPulseResult,
    WorkPulseSubmitRequest,
    WpllResultResponse,
    WpllSubmitRequest,
)
from solverah.services import assessment_service, scoring_jobs

__all__ = ["assessments_bp"]

assessments_bp = Blueprint("assessments", __name__)

_AUTHENTICATED = ["accessTokenCookie"]
_AUTHENTICATED_WRITE = ["accessTokenCookie", "csrfHeader"]

#: Rate-limit bucket namespace for a submission, completed with the ``{kind}``.
#: Named here so the superseded handlers below can opt into the same bucket as
#: the unified route -- see ``_submission_scope`` for why that matters.
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

#: Per-instrument limits, preserved exactly as the five separate handlers had
#: them. ``wpll`` carries no per-endpoint limit today and therefore runs on the
#: global defaults; they are spelled out because ``@limiter.limit`` defaults to
#: ``override_defaults=True``, so a bare "5 per minute" there would have removed
#: its 200-per-day cap while looking like a tightening.
SUBMISSION_LIMITS = {
    "core": DEFAULT_SUBMISSION_LIMIT,
    "work_pulse": DEFAULT_SUBMISSION_LIMIT,
    "focus_type": DEFAULT_SUBMISSION_LIMIT,
    "manager_match": DEFAULT_SUBMISSION_LIMIT,
    "wpll": ";".join(DEFAULT_LIMITS),
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
    request_for=lambda view_args, _body: SUBMISSION_REQUESTS.get(view_args.get("kind")),
    responses={
        200: AssessmentSubmissionResponse,
        400: LegacyError,
        404: LegacyError,
        500: LegacyError,
    },
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "Replaces the five submit handlers Phase 1a inherited. `{kind}` is one "
        "of `core`, `work_pulse`, `wpll`, `focus_type`, `manager_match`, and it "
        "selects both the request body and the response body -- the route is "
        "shared, the payloads are not. The `anyOf` on each is the union of the "
        "five real schemas; the path parameter says which member applies, which "
        "is why this cannot be an OpenAPI discriminated union (3.1 keys a "
        "discriminator off a property of the payload, not off the URL).\n\n"
        "`wpll` is the one kind that needs no JWT: it is the anonymous teaser "
        "on the pre-launch funnel. The other four require one, and CSRF with it."
    ),
)
@assessments_bp.route("/assessments/<kind>/submissions", methods=["POST"])
@limiter.shared_limit(_submission_limit, scope=_submission_scope)
def assessment_kind_submit(kind: str):
    """POST /assessments/{kind}/submissions - score and persist a submission.

    The five instruments differ in a scorer, a prompt, a storage key, and
    whether they need a JWT. Everything else about them was five copies of the
    same handler, and this is the one that is left.

    Note what is NOT unified: the result. `core` returns a submission id and no
    dimension scores at all -- handing them back would give a retaking
    respondent a gradient to optimise against, which teaches the
    item-to-dimension mapping the shuffle and interleave exist to hide. A
    uniform result envelope with a `scores` field would have undone that
    quietly.
    """
    resolved = _kind_or_404(kind)
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
    responses={200: AssessmentSubmissionResponse, 404: LegacyError, 422: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
    description=(
        "`{kind}` selects the response shape, as on the submit route. Only "
        "`work_pulse`, `focus_type`, and `manager_match` store a re-readable "
        "result. `core` is absent by design rather than pending -- its scores "
        "are withheld from the submit response for a documented reason, and a "
        "read endpoint would be the same disclosure through another door."
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
# Phase 3b -- scoring off the request path
# ---------------------------------------------------------------------------
#
# `202` + a job handle for the three instruments that call a provider, added
# alongside `POST /assessments/{kind}/submissions` rather than replacing it.
# The synchronous route above is untouched and byte-identical; a client cannot
# move from awaiting a 200 to polling a job in the same deploy that first gives
# it something to poll. 3c is where the synchronous half dies.
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
    """
    resolved = _kind_or_404(kind)
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
    },
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "Asynchronous counterpart to `POST /assessments/{kind}/submissions`. "
        "Identical request body; answers `202` with a job handle instead of "
        "blocking on the provider. Poll "
        "`GET /assessments/{kind}/scoring-jobs/{job_id}` until `status` is "
        "`succeeded` or `failed`.\n\n"
        "Only the three provider-scored instruments have this operation: "
        "`work_pulse`, `wpll`, `manager_match`. `core` and `focus_type` score "
        "deterministically in-process and answer `404` here -- they are served "
        "by the synchronous route, which remains available for all five.\n\n"
        "**This shares one rate-limit budget with the synchronous submit for "
        "the same instrument.** The limit bounds provider spend, and spend does "
        "not move when the call moves to a worker (A9), so queueing and "
        "submitting draw on the same allowance rather than two."
    ),
)
@assessments_bp.route("/assessments/<kind>/scoring-jobs", methods=["POST"])
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
    responses={200: AssessmentScoringJobStatus, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
    description=(
        "`{kind}` selects the response shape, as it does on the submit route: "
        "`result` is that instrument's own result model and nothing else, and "
        "it is present only once `status` is `succeeded`. There is no shared "
        "result envelope here for the same reason there is none there (A12).\n\n"
        "`wpll` needs no JWT, because the instrument does not: it is the "
        "anonymous teaser, its job has no owner, and the handle is what "
        "authorises the poll. The other two scope the handle to the "
        "authenticated user."
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
