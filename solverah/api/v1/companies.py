"""Company lookup, the six-trait CompanyLens read, on-demand research, pasted job
postings and "I took this job" links.

Six-trait build, C6 (2026-10-13). PRODUCT_DECISIONS.md §2, "The six-trait match model".
The read itself is `solverah.services.company_match_service`; the research pipeline is
`solverah.services.company_research.service`; the records come through
`company_evidence_store`. Nothing in this module serialises a probability, a score, an
estimate or a person-side number (D-15; tests/test_company_lens_api.py walks every
response for one).

The two legacy paths -- ``/companies/<int:company_id>`` and ``/companies`` -- are
unchanged. ``/me/matches`` keeps its path and its cursor contract but is a new body:
the interim ``culture_fit_score`` ranking it served was deleted with this build.

COST CONTROL ON RESEARCH
------------------------
``POST /companies/research`` is the one door that spends provider money. Two limits sit
on it: the house ``@limiter.limit`` burst limit per caller address, and a per-USER
budget of ``RESEARCH_DAILY_NEW_LIMIT`` on NEW runs only. The second cannot be a route
decorator: Flask-Limiter checks a decorated limit BEFORE the handler runs, so a user at
the budget could not get a cached hit either, and the spec says cached hits are free.
It is therefore charged by hand (``_charge_new_run``) on the limiter's own storage,
after the cache has answered and the providers are known to be reachable, and only
when a run is about to be queued. Like every house limit it is exempt under
``TESTING`` (``security._skip_when_testing``); tests/test_company_lens_api.py turns the
flag off to prove it fires.

THE PUBLIC SWITCH (C5c, 2026-10-14). Before any of that, ``SOLVERAH_COMPANYLENS_RESEARCH_ENABLED``
(``research_service.research_enabled``, default OFF) decides whether a NEW run may
start at all: off, the door answers a ``research_disabled`` problem document (503)
and writes nothing -- not even the company row, which is why the handler looks the
company up (``find_company``) before it creates it. Cached and in-flight runs are
served either way. A missing provider key is the sibling ``provider_unavailable``
problem document on both this door and the posting door.
"""

from __future__ import annotations

import datetime
import logging

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from limits import parse as parse_rate_limit

import company_evidence_store as store
from model import db
from solverah.errors import ApiError, RateLimitError
from solverah.extensions import limiter
from solverah.infra import llm
from solverah.infra.llm import LLMProviderUnavailable
from solverah.openapi import document
from solverah.repositories import company_repository, user_repository
from solverah.schemas import PROBLEM_RESPONSE_MODEL, LegacyError, OkResponse
from solverah.schemas.matching import (
    CompanyDetailResponse,
    CompanyLinkCreateRequest,
    CompanyLinkEndRequest,
    CompanyLinkListResponse,
    CompanyLinkResponse,
    CompanyListQuery,
    CompanyListResponse,
    CompanyReadQuery,
    CompanyReadResponse,
    JobPostingCreateRequest,
    JobPostingResponse,
    MatchesQuery,
    MatchesResponse,
    ResearchRequest,
    ResearchRunResponse,
    ResearchRunStatus,
)
from solverah.services import company_match_service, matching_service
from solverah.services.company_research import service as research_service

__all__ = ["companies_bp"]

companies_bp = Blueprint("companies", __name__)

_AUTHENTICATED = ["accessTokenCookie"]
_AUTHENTICATED_WRITE = ["accessTokenCookie", "csrfHeader"]

#: New (uncached) research runs one user may start per day. Charged by
#: ``_charge_new_run`` only when a run is about to be queued.
RESEARCH_DAILY_NEW_LIMIT = "5 per day"
_RESEARCH_DAILY_ITEM = parse_rate_limit(RESEARCH_DAILY_NEW_LIMIT)
_RESEARCH_DAILY_NAMESPACE = "companies:research:new"
#: Burst limit on the research door, per caller address, cached or not.
RESEARCH_BURST_LIMIT = "10 per minute"
#: Pasted postings go through the scorer, so they are bounded like a submission.
JOB_POSTING_SUBMIT_LIMIT = "5 per minute;20 per day"
COMPANY_LINK_LIMIT = "20 per minute"


class ResearchDisabledError(ApiError):
    """The public research switch (``SOLVERAH_COMPANYLENS_RESEARCH_ENABLED``) is off
    and the request would have started a new paid run. A 503 problem document, code
    ``research_disabled``; nothing is written. Cached research is still served."""

    status = 503
    title = "Research disabled"
    code = "research_disabled"
    # The default state until the attorney gate opens: expected traffic, not an
    # alarm (`solverah/errors.py` logs a 5xx ApiError at ERROR otherwise).
    log_level = logging.INFO


class ProviderUnavailableError(ApiError):
    """A provider the request needs has no key configured. A 503 problem document,
    code ``provider_unavailable``; nothing is written or spent."""

    status = 503
    title = "Provider unavailable"
    code = "provider_unavailable"


def _respond(result: matching_service.MatchingResult):
    return jsonify(result.body), result.status


def _current_user():
    return user_repository.find_by_email(get_jwt_identity())


def _charge_new_run(user_id: int) -> None:
    """Spend one of the user's daily new-run allowances, or raise ``RateLimitError``
    (a 429 problem document). Uses the limiter's own storage and strategy, so it is
    shared across workers exactly as the decorated limits are. Exempt under TESTING,
    like every house limit."""
    if current_app.config.get("TESTING"):
        return
    if not limiter.limiter.hit(_RESEARCH_DAILY_ITEM, _RESEARCH_DAILY_NAMESPACE, "user:%d" % user_id):
        raise RateLimitError(
            detail="You can start research on up to five new companies a day; companies "
                   "already researched are always free.",
            errors=[{"field": "name", "code": "research_daily_limit"}],
        )


# ---------------------------------------------------------------------------
# Legacy company lookup (unchanged)
# ---------------------------------------------------------------------------

@document(
    "Fetch a company's full research profile",
    tags=["companies"],
    responses={200: CompanyDetailResponse, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
)
@companies_bp.route("/companies/<int:company_id>", methods=["GET"])
@jwt_required()
def company_detail(company_id: int):
    """GET /companies/<company_id> - Return a company's full profile."""
    return _respond(matching_service.company_detail(company_id))


@document(
    "List companies, filtered and paginated",
    tags=["companies"],
    query=CompanyListQuery,
    responses={200: CompanyListResponse, 422: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
)
@companies_bp.route("/companies", methods=["GET"])
@jwt_required()
def company_list():
    """GET /companies - one page of companies, keyset-paginated (A5)."""
    return _respond(
        matching_service.list_companies(
            cursor=request.args.get("cursor"),
            limit=request.args.get("limit"),
            q=request.args.get("q"),
            industry=request.args.get("industry"),
        )
    )


# ---------------------------------------------------------------------------
# The six-trait read
# ---------------------------------------------------------------------------

@document(
    "Rank researched companies for the authenticated user on the six traits",
    tags=["companies"],
    query=MatchesQuery,
    responses={200: MatchesResponse, 404: LegacyError, 422: PROBLEM_RESPONSE_MODEL},
    security=_AUTHENTICATED,
    enforce=True,
    description=(
        "Every company with shared research records, ordered by the causal model's "
        "ranking for this user with the gate layer on top: a company with a must-have "
        "broken on a known trait is flagged and sorted last, never hidden; a company "
        "read on fewer than 3 of 6 traits is `not_enough_evidence`, has no rank and is "
        "listed after the ranked ones. No probability, score or percentage is carried: "
        "the order is the output.\n\n"
        "`state` is `core_required` when the user has no current core sitting and "
        "`no_companies` when nothing has been researched yet; both are 200s."
    ),
)
@companies_bp.route("/me/matches", methods=["GET"])
@jwt_required()
def my_matches():
    """GET /me/matches - the six-trait ranking, one page at a time."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return _respond(
        company_match_service.matches(
            user, cursor=request.args.get("cursor"), limit=request.args.get("limit")
        )
    )


@document(
    "The full per-trait read of one company for the authenticated user",
    tags=["companies"],
    query=CompanyReadQuery,
    responses={200: CompanyReadResponse, 404: LegacyError, 422: PROBLEM_RESPONSE_MODEL},
    security=_AUTHENTICATED,
    enforce=True,
    description=(
        "Six trait reads: status (known / mixed / unknown), direction versus the user's "
        "preference, inside or outside their tolerance, must-have, paraphrased evidence "
        "(both sides for a mixed trait, with the scope or time explanation when there is "
        "one), interview questions for a must-have that is unknown or mixed, and the "
        "company-size confidence note. With `?posting_id=` (one of the caller's own "
        "pastes for this company) the posting's role-level read sits beside the "
        "company's, with disagreements named. Another user's posting is a 404."
    ),
)
@companies_bp.route("/companies/<int:company_id>/read", methods=["GET"])
@jwt_required()
def company_read(company_id: int):
    """GET /companies/<company_id>/read - the six-trait read for this user."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    # `CompanyReadQuery` enforcement has already answered 422 for a non-integer
    # posting_id, so this cast cannot fail.
    raw = request.args.get("posting_id")
    posting_id = int(raw) if raw not in (None, "") else None
    return _respond(company_match_service.company_read(user, company_id, posting_id=posting_id))


# ---------------------------------------------------------------------------
# On-demand research
# ---------------------------------------------------------------------------

@document(
    "Research a company by name, on demand",
    tags=["companies"],
    request=ResearchRequest,
    responses={
        202: ResearchRunResponse,
        400: LegacyError,
        404: LegacyError,
        422: PROBLEM_RESPONSE_MODEL,
        429: PROBLEM_RESPONSE_MODEL,
        503: PROBLEM_RESPONSE_MODEL,
    },
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "Finds or creates the company and answers `202` with the run to poll. A `done` "
        "run younger than the cache window is returned as is (`cached: true`) and costs "
        "nothing; an in-flight run is returned as is. Otherwise a new run is queued. "
        "Each user may start at most five new runs a day (`429` beyond that); cached "
        "hits do not count. `503` is a problem document: `research_disabled` when "
        "on-demand research is switched off on this server (cached runs are still "
        "returned), or `provider_unavailable` when no research provider is configured. "
        "A refused request writes nothing."
    ),
)
@companies_bp.route("/companies/research", methods=["POST"])
@limiter.limit(RESEARCH_BURST_LIMIT)
@jwt_required()
def research_company():
    """POST /companies/research - queue (or return the cached) research for a name."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    try:
        # Look the company up WITHOUT creating it: a refused request writes nothing.
        company = research_service.find_company(db, name)
        existing = research_service.existing_run(db, company.id) if company else None
        if existing is None:
            # The switch first (reading cached research is never gated); then the
            # providers, so a 503 spends none of the budget; then the budget, so a
            # refused request writes no row; only then the company row.
            if not research_service.research_enabled():
                raise research_service.ResearchDisabled(research_service.RESEARCH_ENABLED_VAR)
            llm.get_research_client()
            llm.get_scorer_client()
            _charge_new_run(user.id)
            company = research_service.resolve_company(db, company_name=name)
        run = research_service.request_research(
            db, company_id=company.id, trigger="on_demand"
        )
    except research_service.ResearchDisabled:
        current_app.logger.info("company_research_disabled", extra={"user_id": user.id})
        raise ResearchDisabledError(
            detail="Company research is switched off on this server. Companies already "
                   "researched can still be read."
        )
    except LLMProviderUnavailable as exc:
        current_app.logger.warning("company_research_unavailable", extra={"reason": str(exc)})
        raise ProviderUnavailableError(detail="Company research is not available right now.")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    # The run row may have moved on already (eager/inline dispatch): report what it is now.
    current = store.research_run(db, run.id) or run
    return (
        jsonify({
            "run": company_match_service.research_status(current, company),
            "cached": existing is not None and existing.status == "done",
        }),
        202,
    )


@document(
    "Poll a research run",
    tags=["companies"],
    responses={200: ResearchRunStatus, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
)
@companies_bp.route("/companies/research/<int:run_id>", methods=["GET"])
@jwt_required()
def research_run_status(run_id: int):
    """GET /companies/research/<run_id> - the run's status."""
    run = store.research_run(db, run_id)
    if run is None:
        return jsonify({"error": "Research run not found"}), 404
    company = company_repository.get_by_id(run.company_id)
    return jsonify(company_match_service.research_status(run, company)), 200


# ---------------------------------------------------------------------------
# Pasted job postings (owner-only)
# ---------------------------------------------------------------------------

@document(
    "Paste a job posting to be read at role level",
    tags=["companies"],
    request=JobPostingCreateRequest,
    responses={
        202: JobPostingResponse,
        400: LegacyError,
        404: LegacyError,
        422: PROBLEM_RESPONSE_MODEL,
        429: PROBLEM_RESPONSE_MODEL,
        503: PROBLEM_RESPONSE_MODEL,
    },
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "The text is the user's own paste; nothing is fetched. It is scored against the "
        "same rubric as the company evidence and its records are private to the caller "
        "-- pass the posting's id as `?posting_id=` on `GET /companies/{id}/read`. "
        "`503` is a `provider_unavailable` problem document when the scorer has no key; "
        "nothing is written. Postings are not gated by the research switch."
    ),
)
@companies_bp.route("/me/job-postings", methods=["POST"])
@limiter.limit(JOB_POSTING_SUBMIT_LIMIT)
@jwt_required()
def post_job_posting():
    """POST /me/job-postings - store a paste and queue its scoring."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    body = request.get_json(silent=True) or {}
    try:
        posting = research_service.submit_job_posting(
            db, user.id,
            company_id=body.get("company_id"),
            text=body.get("text") or "",
            title=body.get("title"),
        )
    except LLMProviderUnavailable:
        raise ProviderUnavailableError(detail="Posting scoring is not available right now.")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"posting": _posting_body(user.id, posting.id)}), 202


def _posting_body(user_id: int, posting_id: int):
    posting = company_match_service._owned_posting(user_id, posting_id)
    if posting is None:
        return None
    has_read = bool(store.posting_trait_records(db, posting.id))
    return company_match_service.posting_status(posting, has_read=has_read)


@document(
    "Poll one of the caller's pasted postings",
    tags=["companies"],
    responses={200: JobPostingResponse, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
    description="Owner-only: another user's posting is a 404, not a 403.",
)
@companies_bp.route("/me/job-postings/<int:posting_id>", methods=["GET"])
@jwt_required()
def get_job_posting(posting_id: int):
    """GET /me/job-postings/<posting_id> - status and whether it has a read."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    body = _posting_body(user.id, posting_id)
    if body is None:
        return jsonify({"error": "Job posting not found"}), 404
    return jsonify({"posting": body}), 200


# ---------------------------------------------------------------------------
# "I took this job"
# ---------------------------------------------------------------------------

def _link_body(link: store.CompanyLinkView, company_row=None):
    body = {
        "id": link.id,
        "company_id": link.company_id,
        "started_on": link.started_on.isoformat(),
        "ended_on": None if link.ended_on is None else link.ended_on.isoformat(),
        "created_at": link.created_at.isoformat() if link.created_at else None,
        "company": None,
    }
    if company_row is not None:
        body["company"] = {
            "id": company_row.id, "name": company_row.name, "slug": company_row.slug,
            "industry": getattr(company_row, "industry", None),
        }
    return body


@document(
    "Record that the user took a job at a company",
    tags=["companies"],
    request=CompanyLinkCreateRequest,
    responses={201: CompanyLinkResponse, 404: LegacyError, 422: PROBLEM_RESPONSE_MODEL},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description=(
        "\"I took this job\": links later Pulse check-ins to the CompanyLens read "
        "(PRODUCT_DECISIONS.md section 2, what changes the weights, item 4)."
    ),
)
@companies_bp.route("/me/company-links", methods=["POST"])
@limiter.limit(COMPANY_LINK_LIMIT)
@jwt_required()
def post_company_link():
    """POST /me/company-links - create a link."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    body = request.get_json(silent=True) or {}
    company_id = body.get("company_id")
    try:
        started_on = datetime.date.fromisoformat(str(body.get("started_on")))
    except (TypeError, ValueError):
        return jsonify({"error": "started_on must be an ISO date"}), 422
    if company_repository.get_by_id(company_id) is None:
        return jsonify({"error": "Company not found"}), 404
    link = store.create_company_link(db, user.id, company_id=company_id, started_on=started_on)
    summaries = company_repository.summaries([link.company_id])
    return jsonify({"link": _link_body(link, summaries.get(link.company_id))}), 201


@document(
    "List the user's company links",
    tags=["companies"],
    responses={200: CompanyLinkListResponse, 404: LegacyError},
    security=_AUTHENTICATED,
    enforce=True,
)
@companies_bp.route("/me/company-links", methods=["GET"])
@jwt_required()
def list_company_links():
    """GET /me/company-links - every link, newest start first."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    links = store.company_links_for_user(db, user.id)
    summaries = company_repository.summaries(link.company_id for link in links)
    return jsonify({
        "data": [_link_body(link, summaries.get(link.company_id)) for link in links]
    }), 200


@document(
    "Remove one of the user's company links",
    tags=["companies"],
    responses={200: OkResponse, 404: LegacyError},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description="Owner-only: another user's link is a 404.",
)
@companies_bp.route("/me/company-links/<int:link_id>", methods=["DELETE"])
@jwt_required()
def delete_company_link(link_id: int):
    """DELETE /me/company-links/<link_id>."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if not store.delete_company_link(db, user.id, link_id):
        return jsonify({"error": "Company link not found"}), 404
    return jsonify({"ok": True}), 200


@document(
    "\"I left\": close one of the user's company links",
    tags=["companies"],
    request=CompanyLinkEndRequest,
    responses={200: CompanyLinkResponse, 404: LegacyError, 422: PROBLEM_RESPONSE_MODEL},
    security=_AUTHENTICATED_WRITE,
    enforce=True,
    description="Owner-only: another user's link is a 404. ended_on must be on or after started_on.",
)
@companies_bp.route("/me/company-links/<int:link_id>", methods=["PATCH"])
@jwt_required()
def patch_company_link(link_id: int):
    """PATCH /me/company-links/<link_id> - set ended_on."""
    user = _current_user()
    if not user:
        return jsonify({"error": "User not found"}), 404
    body = request.get_json(silent=True) or {}
    try:
        ended_on = datetime.date.fromisoformat(str(body.get("ended_on")))
    except (TypeError, ValueError):
        return jsonify({"error": "ended_on must be an ISO date"}), 422
    try:
        link = store.end_company_link(db, user.id, link_id, ended_on=ended_on)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 422
    if link is None:
        return jsonify({"error": "Company link not found"}), 404
    summaries = company_repository.summaries([link.company_id])
    return jsonify({"link": _link_body(link, summaries.get(link.company_id))}), 200
