"""Runtime request validation for routes declared with ``@document(enforce=True)``.

Why this is a ``before_request`` hook and not part of the decorator
------------------------------------------------------------------
The obvious implementation is for :func:`solverah.openapi.document` to return a
wrapper when ``enforce=True``.  That implementation is wrong here, and Phase 1a
already paid for the lesson.

``@document`` is written **above** ``@bp.route`` throughout this codebase, and
``Blueprint.route`` registers the function object it is handed and returns it
unchanged.  A decorator applied above it therefore annotates an object Flask has
already registered -- fine for stashing an attribute, useless for wrapping.  A
wrapper written there would simply never run.  That is precisely how every
``@limiter.limit`` in the pre-Phase-1 ``app.py`` came to be inert: the limits
were declared, they read correctly, and they enforced nothing.

So enforcement is not allowed to depend on where a decorator sits.  This hook
resolves the spec from ``request.endpoint`` at request time, which makes the
declaration order irrelevant and means a handler cannot accidentally opt itself
out by being written in a reasonable-looking but wrong order.
``tests/test_request_validation.py`` asserts that directly.

Ordering inside the request, and what it costs
---------------------------------------------
This hook runs **before the handler**, which puts it before two things worth
being explicit about.

**Before ``@jwt_required()``.**  An unauthenticated caller with a malformed body
gets 422 rather than 401.  That orders the two disclosures the "wrong" way round
by the usual instinct, and it is fine: every enforced schema is published in
``docs/openapi.json``, so a 422 tells an anonymous caller nothing the contract
does not already hand them.

**Before the per-endpoint rate limit** -- which is the surprising one, and it is
not an accident of ordering that could be corrected by moving this hook.
Flask-Limiter evaluates ``default_limits`` in ``before_request`` but evaluates
**decorated** limits inside the wrapper it puts around the view function
(``_manager.resolve_limits``: ``if not in_middleware: decorated_limits.extend(...)``).
A request refused here therefore never reaches the view and is never charged to
its endpoint's bucket, and no ``before_request`` placement changes that.

That is the behaviour to want, and the reason is the same one that got
``1 per day`` removed from the guest quiz endpoint in this phase.  A rate limit
exists to bound *expensive* work; a 422 is a JSON parse against a body already
capped at ``MAX_CONTENT_LENGTH``, which is strictly cheaper than the handler it
prevents from running.  Charging for it would mean a broken client -- or a
stranger sharing a NAT gateway -- could spend a real user's login allowance with
nothing but garbage.  ``tests/test_request_validation.py`` pins this.

The residual is that a flood of *malformed* bodies is not bounded per endpoint,
only by whatever the edge applies.  That is the correct place for it: an
application rate limit keyed on IP cannot tell a flood from an office, which is
precisely the failure this phase removed from the quiz endpoint.

What "enforced" means, precisely
--------------------------------
The three decisions below were made per endpoint against what the handlers
actually tolerate today (Phase 1b, "audit before flipping enforce"):

* **Unknown keys are dropped, not rejected.**  Request models used on enforced
  routes set ``extra="ignore"``.  Every handler today reads its fields with
  ``data.get(...)`` and ignores the rest, and several live call sites send more
  than the schema names -- ``role`` on register is the one that would have
  broken.  A 422 on a key the server was going to ignore anyway is the exact
  "worked yesterday, 422 today" incident this is supposed to prevent.
* **Types are coerced, not policed.**  Pydantic's default lax mode turns
  ``"1024"`` into ``1024``, which is what ``int(data.get("size") or 0)`` did.
* **Missing required fields are rejected.**  This is the part that is genuinely
  new, and it is the whole point: a body with no ``email`` used to travel as far
  as a password comparison against the empty string.

A missing or unparseable body is validated as ``{}`` rather than special-cased,
so "no body" and "empty body" get the same answer instead of two.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, ValidationError as PydanticValidationError

from .errors import ValidationError
from .openapi import route_spec

__all__ = ["install_request_validation", "problem_errors"]


def problem_errors(exc: PydanticValidationError) -> List[Dict[str, Any]]:
    """Render a pydantic error list as RFC 9457 ``errors`` entries.

    ``loc`` is a tuple that may nest (``("answers", 3, "option_id")``); it is
    joined with dots so the client gets one addressable field name.  Pydantic's
    ``type`` is carried through as ``code`` because it is stable and
    machine-readable -- ``missing``, ``string_type``, ``int_parsing`` -- which is
    what makes a client able to branch on the failure instead of matching prose.

    ``input`` is deliberately **not** included.  Echoing the rejected value back
    would put a password into an error body on the one endpoint where that is
    most likely to be logged.
    """
    entries: List[Dict[str, Any]] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()))
        entries.append(
            {
                "field": location or None,
                "code": error.get("type"),
                "detail": error.get("msg"),
            }
        )
    return entries


def _validate(model: Type[BaseModel], payload: Any, source: str) -> None:
    """Validate *payload* against *model*, or raise :class:`ValidationError`."""
    try:
        model.model_validate(payload)
    except PydanticValidationError as exc:
        errors = problem_errors(exc)
        # The first failure is the one a human reads; the rest are in `errors`.
        first = errors[0] if errors else {}
        detail = "%s is invalid" % source
        if first.get("field"):
            detail = "%s: %s" % (first["field"], first.get("detail") or "is invalid")
        raise ValidationError(detail=detail, errors=errors) from exc


def _body_payload(request) -> Dict[str, Any]:
    """The JSON body as a dict, treating absent/unparseable/null as ``{}``.

    A non-object body (a bare list or string) is a client error the model itself
    should report, so it is passed through untouched rather than coerced -- the
    resulting pydantic message names the actual problem.
    """
    payload = request.get_json(silent=True)
    if payload is None:
        return {}
    return payload


def _query_payload(request) -> Dict[str, Any]:
    """Flat query parameters as a dict.

    ``request.args`` is a MultiDict; the last value wins for a repeated key,
    matching ``request.args.get``.  Query models are flat by construction (see
    ``solverah.openapi._query_parameters``), so nothing is lost.
    """
    return {key: request.args.get(key) for key in request.args}


#: Methods with no defined request-body semantics.
#:
#: HEAD is here as well as GET because Flask synthesises it for every GET rule;
#: a HEAD carries no body, so validating one would reject it the same way the
#: preflight was being rejected.
_BODYLESS_METHODS = frozenset({"GET", "HEAD"})


def install_request_validation(app) -> None:
    """Install the ``before_request`` hook that enforces declared schemas.

    Idempotent: a second call on the same app is ignored, so building two apps
    in one process (which the tests do) cannot stack two hooks that would report
    the same failure twice.
    """
    if app.extensions.get("solverah_request_validation"):
        return
    app.extensions["solverah_request_validation"] = True

    from flask import request

    @app.before_request
    def _enforce_declared_schemas():  # pragma: no cover - exercised via routes
        # A CORS preflight carries no body by definition, is issued by the
        # browser rather than the application, and never reaches the handler --
        # Flask answers it from the url_map. Validating it means every enforced
        # POST is rejected at 422 before the real request is ever sent, which
        # does not look like a validation error to the client: it looks like the
        # endpoint does not exist cross-origin. Login broke exactly this way.
        #
        # security.py exempts OPTIONS from rate limiting for the same reason;
        # this is that exemption's other half.
        if request.method == "OPTIONS":
            return None

        spec = _spec_for(app, request.endpoint)
        if spec is None or not spec.enforce:
            return None

        if spec.query is not None:
            _validate(spec.query, _query_payload(request), "query string")

        # GET and HEAD have no defined body semantics; everything else that
        # declares one gets it checked, DELETE included -- `DELETE /me` carries
        # the confirmation string that makes the deletion deliberate.
        if request.method not in _BODYLESS_METHODS:
            payload = _body_payload(request)
            model = _request_model(spec, request.view_args or {}, payload)
            if model is not None:
                _validate(model, payload, "request body")

        return None


def _request_model(
    spec, view_args: Dict[str, Any], payload: Any
) -> Optional[Type[BaseModel]]:
    """The model this particular request must satisfy.

    ``spec.request`` is the documented shape and is usually the answer.  A route
    whose body depends on a discriminator declares ``request_for`` instead, and
    it wins.  Two routes do, and they discriminate on different things -- which
    is why the resolver is handed both the path parameters and the parsed body:

    * ``POST /assessments/{kind}/submissions`` keys off ``{kind}`` in the path.
    * ``POST /intake/claims`` keys off ``mode`` in the body.

    Both document the union of their shapes and enforce exactly one member.
    Enforcing the union instead would let a Work Pulse payload through on the
    FocusType path, or a sign-in body through as a registration.

    A resolver returning None means "nothing declared for this value" -- the
    handler answers it, typically with a 404 for an unknown ``kind``, which is a
    better answer than a validation error against a schema that does not exist.
    """
    if spec.request_for is not None:
        return spec.request_for(view_args, payload)
    return spec.request


def _spec_for(app, endpoint: Optional[str]):
    """The :class:`~solverah.openapi.RouteSpec` for *endpoint*, or None.

    ``endpoint`` is None for a request that matched no rule -- the 404 handler
    answers those, and there is nothing to validate against.
    """
    if not endpoint:
        return None
    view = app.view_functions.get(endpoint)
    if view is None:
        return None
    return route_spec(view)
