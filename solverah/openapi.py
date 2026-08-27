"""OpenAPI 3.1 generation from pydantic v2 models.

Why this is ~300 lines of local code and not a dependency
--------------------------------------------------------
The three obvious candidates were evaluated and rejected:

* **APIFlask** subclasses ``Flask``, so it wants to *be* the app object, and it
  is marshmallow-based.  It also installs its own ``HTTPError`` handling, which
  would fight the RFC 9457 handlers in ``solverah/errors.py``.
* **flask-openapi3** is pydantic-native but is likewise a ``Flask`` subclass and
  requires its own ``APIBlueprint``, and it answers validation failures with its
  own 422 body.
* **spectree** is the closest fit -- decorator-driven, ``api.register(app)``,
  leaves the app object alone.  Two things ruled it out.  Its Flask plugin
  validates *responses* at runtime and turns a mismatch into a 500, which is a
  live grenade pointed at 38 hand-written response dicts; and its own source
  marks ``openapi_version`` as "doesn't affect anything", so the 3.1 it declares
  is not a 3.1 it generates.  Bending its error body back to the shapes this API
  already returns leaves it doing nothing but serialising a spec.

The deciding fact is that there is nothing to bridge.  Pydantic v2 emits JSON
Schema draft 2020-12, and OpenAPI 3.1's Schema Object *is* draft 2020-12 -- that
is the headline change from 3.0.  ``models_json_schema`` even takes the
``ref_template`` that points ``$ref``s at ``#/components/schemas/``.  So the
generator is a walk over ``app.url_map`` plus a dict.

Requests are enforced; responses are not
----------------------------------------
Phase 1b added ``enforce=True``.  A route carrying it has its request body
validated against ``request`` and its query string against ``query`` before the
handler runs, and a mismatch answers 422 in the Problem Details shape Part 5.1
specifies.  The enforcement does **not** live in this decorator -- see
:mod:`solverah.validation` for why a ``before_request`` hook is the only
placement that cannot be defeated by writing the decorators in the wrong order.

Responses are still not validated, and deliberately so.  That was the single
thing that ruled spectree out: turning a response mismatch into a 500 is a live
grenade pointed at every hand-written response dict.  ``tests/test_schema_conformance.py``
pushes real responses through the declared models instead, which catches drift
without being able to take an endpoint down.

The superseded Phase 1a handlers keep ``enforce`` off for as long as they exist.
Enforcing a schema on a route that is about to be deleted buys nothing and can
only break a client that has not finished moving off it.

Usage::

    @document(
        summary="Authenticate a user",
        tags=["auth"],
        request=LoginRequest,
        responses={200: LoginResponse, 401: LegacyError},
    )
    @auth_bp.post("/login")
    @limiter.limit("5 per minute")
    def login():
        ...

Regenerate the committed document with::

    python -m solverah.openapi
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Type

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

__all__ = [
    "OPENAPI_VERSION",
    "RouteSpec",
    "build_openapi",
    "document",
    "route_spec",
    "write_openapi",
]

OPENAPI_VERSION = "3.1.0"
JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

#: Where the generated document is committed.  Committing it means the frontend
#: can generate its typed client without booting the API, and CI can fail on
#: drift -- see tests/test_openapi.py.
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"

#: Attribute the decorator stashes its spec under.
_SPEC_ATTR = "__solverah_openapi__"

_ATTACHED_PREFIX = "/api/v1"

# Werkzeug converter -> (JSON Schema type, format).  Anything not listed is
# documented as a string, which is what Werkzeug's default converter accepts.
_CONVERTER_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "int": {"type": "integer"},
    "float": {"type": "number"},
    "uuid": {"type": "string", "format": "uuid"},
    "path": {"type": "string"},
    "string": {"type": "string"},
    "default": {"type": "string"},
}

_RULE_ARG = re.compile(r"<(?:(?P<conv>[a-zA-Z_][a-zA-Z0-9_]*)(?:\([^)]*\))?:)?(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)>")


@dataclass(frozen=True)
class RouteSpec:
    """Everything :func:`document` was told about one handler.

    Attributes:
        summary: One-line description; becomes the operation summary.
        description: Longer prose.  Defaults to the handler's docstring.
        tags: Grouping in the rendered document.  Defaults to the blueprint name.
        request: Model describing the JSON request body, if the route takes one.
        query: Model whose fields become ``in: query`` parameters.
        responses: Status code -> model.  ``None`` documents a body-less response.
        request_required: Whether the body is mandatory.
        security: Security scheme names; empty list means the route is public.
        deprecated: Marks the operation deprecated in the document.
        operation_id: Overrides the derived ``tag_functionname`` id.
        enforce: When True, ``solverah.validation`` validates the request body
            against *request* and the query string against *query* before the
            handler runs, answering a mismatch with a 422 problem document.
            When False the models are descriptive only -- which is what every
            Phase 1a route was, and what the superseded ones stay until they
            are deleted.
        request_for: ``(view_args, payload) -> model``, for a route whose body
            shape depends on a discriminator.  Two routes need it and they
            discriminate on different things, which is why it receives both:
            ``POST /assessments/{kind}/submissions`` keys off a path parameter,
            and ``POST /intake/claims`` keys off ``mode`` in the body.  In both
            cases *request* documents the union of the shapes and this picks
            the one that actually applies.  Enforcing the union instead would
            accept a Work Pulse body on the FocusType path -- which is most of
            the value of enforcing at all.
    """

    summary: str
    description: Optional[str] = None
    tags: Tuple[str, ...] = ()
    request: Optional[Type[BaseModel]] = None
    query: Optional[Type[BaseModel]] = None
    responses: Mapping[int, Optional[Type[BaseModel]]] = field(default_factory=dict)
    request_required: bool = True
    security: Optional[Tuple[str, ...]] = None
    deprecated: bool = False
    operation_id: Optional[str] = None
    enforce: bool = False
    request_for: Optional[Any] = None


def document(
    summary: str,
    *,
    description: Optional[str] = None,
    tags: Sequence[str] = (),
    request: Optional[Type[BaseModel]] = None,
    query: Optional[Type[BaseModel]] = None,
    responses: Optional[Mapping[int, Optional[Type[BaseModel]]]] = None,
    request_required: bool = True,
    security: Optional[Sequence[str]] = None,
    deprecated: bool = False,
    operation_id: Optional[str] = None,
    enforce: bool = False,
    request_for=None,
):
    """Attach an OpenAPI operation description to a view function.

    Purely declarative: the returned decorator stores a :class:`RouteSpec` on the
    function and hands the *same function object* back.  It wraps nothing, so it
    cannot change a status code, a body, or a header, and it composes in any
    order with ``@bp.route``, ``@jwt_required()``, and ``@limiter.limit``.

    Place it outermost.  ``@bp.route`` registers whatever function object it is
    given, so a decorator applied above it still annotates the object Flask
    registered -- but reading it back is one attribute lookup instead of walking
    ``__wrapped__`` chains.
    """

    spec = RouteSpec(
        summary=summary,
        description=description,
        tags=tuple(tags),
        request=request,
        query=query,
        responses=dict(responses or {}),
        request_required=request_required,
        security=tuple(security) if security is not None else None,
        deprecated=deprecated,
        operation_id=operation_id,
        enforce=enforce,
        request_for=request_for,
    )

    def decorator(func):
        setattr(func, _SPEC_ATTR, spec)
        return func

    return decorator


def route_spec(view_func) -> Optional[RouteSpec]:
    """Return the :class:`RouteSpec` for *view_func*, unwrapping decorators.

    ``@limiter.limit`` returns a wrapper, so a spec applied under it lands on the
    inner function.  Following ``__wrapped__`` means ``@document`` works above or
    below the rate-limit decorator rather than only above it.
    """
    seen = set()
    current = view_func
    while current is not None and id(current) not in seen:
        spec = getattr(current, _SPEC_ATTR, None)
        if spec is not None:
            return spec
        seen.add(id(current))
        current = getattr(current, "__wrapped__", None)
    return None


def _openapi_path(rule: str) -> str:
    """``/api/v1/companies/<int:company_id>`` -> ``/api/v1/companies/{company_id}``."""
    return _RULE_ARG.sub(lambda m: "{%s}" % m.group("name"), rule)


def _path_parameters(rule) -> List[Dict[str, Any]]:
    """Describe a rule's URL converters as OpenAPI path parameters."""
    parameters = []
    for match in _RULE_ARG.finditer(rule.rule):
        name = match.group("name")
        converter = match.group("conv") or "default"
        parameters.append(
            {
                "name": name,
                "in": "path",
                "required": True,
                "schema": dict(_CONVERTER_SCHEMAS.get(converter, _CONVERTER_SCHEMAS["default"])),
            }
        )
    return parameters


def _query_parameters(model: Type[BaseModel], schemas: Mapping[Any, Any]) -> List[Dict[str, Any]]:
    """Flatten a model's fields into ``in: query`` parameters.

    Query strings are flat, so a nested model cannot be represented faithfully;
    the field's own schema is inlined and a nested one would emit a ``$ref`` that
    no client could serialise into a query string.  Keep query models flat.
    """
    schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
    required = set(schema.get("required", []))
    parameters = []
    for name, prop in (schema.get("properties") or {}).items():
        prop = dict(prop)
        description = prop.pop("description", None)
        parameter = {
            "name": name,
            "in": "query",
            "required": name in required,
            "schema": prop,
        }
        if description:
            parameter["description"] = description
        parameters.append(parameter)
    return parameters


def _json_content(ref: Mapping[str, Any]) -> Dict[str, Any]:
    return {"application/json": {"schema": dict(ref)}}


def _collect_models(specs: Iterable[RouteSpec]) -> List[Tuple[Type[BaseModel], str]]:
    """Every model referenced by any spec, paired with the mode it is used in.

    Request and query models are generated in ``validation`` mode and response
    models in ``serialization`` mode.  For a model with no aliases or computed
    fields the two are identical, but the distinction is free and it is the
    difference between documenting what a client may send and what it will
    receive.
    """
    seen: Dict[Tuple[int, str], Tuple[Type[BaseModel], str]] = {}

    def add(model: Optional[Type[BaseModel]], mode: str) -> None:
        if model is None:
            return
        seen.setdefault((id(model), mode), (model, mode))

    for spec in specs:
        add(spec.request, "validation")
        add(spec.query, "validation")
        for model in spec.responses.values():
            add(model, "serialization")
    return list(seen.values())


def _canonical_rules(app) -> List[Tuple[Any, str]]:
    """Every versioned rule, paired with its templated OpenAPI path.

    Through the Phase 1 cutover this also resolved each rule's unversioned alias
    and recorded it as ``x-legacy-path``, so the document said out loud which
    URLs were on their way out and the frontend migration had something to diff
    against.  Phase 1b finished that migration and removed the aliases, so there
    is nothing left to record: every path the API serves is a supported one.

    Rules are keyed by ``(path, endpoint)``, not by path alone.  One path can
    carry two endpoints -- ``/me`` has a GET, a PATCH, and a DELETE bound to
    three handlers -- and keying on the path dropped whichever came second, an
    operation silently missing from the contract.
    """
    versioned: Dict[Tuple[str, str], Any] = {}

    for rule in app.url_map.iter_rules():
        if rule.rule.startswith(_ATTACHED_PREFIX + "/"):
            versioned.setdefault((rule.rule, rule.endpoint), rule)

    results = [
        # Werkzeug writes converters as <int:company_id>; OpenAPI wants
        # {company_id}, with the type carried by the parameter object.
        (rule, _openapi_path(rule.rule))
        for (_raw_path, _endpoint), rule in versioned.items()
    ]
    results.sort(key=lambda item: item[1])
    return results


def _operation_id(spec: RouteSpec, rule, method: str) -> str:
    if spec.operation_id:
        return spec.operation_id
    endpoint = rule.endpoint.replace(".", "_")
    return "%s_%s" % (method.lower(), endpoint)


def build_openapi(
    app,
    *,
    title: str = "Solverah API",
    version: str = "1.0.0",
    description: Optional[str] = None,
    servers: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Generate the OpenAPI 3.1 document for *app*.

    Only ``/api/v1`` rules are documented.  Health probes are intentionally
    absent: Part 5.2 lists them as unversioned platform endpoints, they are bound
    to the internal interface, and putting them in the public contract invites a
    generated client to call them.

    Raises:
        RuntimeError: If a ``/api/v1`` rule has no :func:`document` spec.  A
            silently undocumented route is how a contract rots, so this is loud.
    """
    from solverah.schemas import PROBLEM_RESPONSE_MODEL

    rules = _canonical_rules(app)

    undocumented = []
    entries = []
    for rule, path in rules:
        spec = route_spec(app.view_functions[rule.endpoint])
        if spec is None:
            undocumented.append("%s (%s)" % (path, rule.endpoint))
            continue
        entries.append((rule, path, spec))

    if undocumented:
        raise RuntimeError(
            "These /api/v1 routes have no @document(...) spec, so they would be "
            "missing from the contract: %s" % ", ".join(sorted(undocumented))
        )

    specs = [entry[2] for entry in entries]
    models = _collect_models(specs)
    models.append((PROBLEM_RESPONSE_MODEL, "serialization"))

    key_map, definitions = models_json_schema(
        models,
        ref_template="#/components/schemas/{model}",
        title=None,
    )
    schemas = definitions.get("$defs", {})

    paths: Dict[str, Dict[str, Any]] = {}
    for rule, path, spec in entries:
        operations = paths.setdefault(path, {})

        parameters = _path_parameters(rule)
        if spec.query is not None:
            parameters.extend(_query_parameters(spec.query, schemas))

        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            operation: Dict[str, Any] = {
                "summary": spec.summary,
                "operationId": _operation_id(spec, rule, method),
                "tags": list(spec.tags) or [rule.endpoint.split(".")[0]],
                "responses": _build_responses(spec, key_map, PROBLEM_RESPONSE_MODEL),
            }
            description = spec.description or _docstring(app.view_functions[rule.endpoint])
            if description:
                operation["description"] = description
            if parameters:
                operation["parameters"] = parameters
            # OpenAPI 3.1 permits a body on DELETE, and ``DELETE /me`` needs
            # one: the confirmation string is what stops a stray click or a
            # replayed request destroying an account. Only GET is excluded,
            # where a body has no defined semantics.
            if spec.request is not None and method != "GET":
                operation["requestBody"] = {
                    "required": spec.request_required,
                    "content": _json_content(key_map[(spec.request, "validation")]),
                }
            if spec.security is not None:
                operation["security"] = [{name: []} for name in spec.security]
            if spec.deprecated:
                operation["deprecated"] = True
            operations[method.lower()] = operation

    document_: Dict[str, Any] = {
        "openapi": OPENAPI_VERSION,
        "jsonSchemaDialect": JSON_SCHEMA_DIALECT,
        "info": {
            "title": title,
            "version": version,
            "description": description
            or (
                "Generated from the pydantic models on each handler. "
                "Every operation below is also served at the unversioned path "
                "recorded in its `x-legacy-path`, for the duration of the "
                "frontend cutover; the unversioned paths are not part of the "
                "supported contract."
            ),
        },
        "paths": dict(sorted(paths.items())),
        "components": {
            "schemas": dict(sorted(schemas.items())),
            "securitySchemes": _security_schemes(),
        },
    }
    if servers:
        document_["servers"] = list(servers)
    return document_


def _docstring(view_func) -> Optional[str]:
    doc = getattr(view_func, "__doc__", None)
    if not doc:
        return None
    return "\n".join(line.strip() for line in doc.strip().splitlines()).strip() or None


def _build_responses(
    spec: RouteSpec,
    key_map: Mapping[Any, Any],
    problem_model: Type[BaseModel],
) -> Dict[str, Any]:
    """Render a spec's declared responses, plus the catch-all problem document."""
    responses: Dict[str, Any] = {}
    for status, model in sorted(spec.responses.items()):
        entry: Dict[str, Any] = {"description": _STATUS_TEXT.get(status, "Response")}
        if model is not None:
            entry["content"] = _json_content(key_map[(model, "serialization")])
        responses[str(status)] = entry

    # Phase 0 gave every unhandled failure an RFC 9457 body. Declaring it once as
    # the default rather than repeating it on every operation keeps the document
    # honest without 38 copies of the same block.
    responses.setdefault(
        "default",
        {
            "description": "Unexpected error (RFC 9457 problem document)",
            "content": {
                "application/problem+json": {
                    "schema": dict(key_map[(problem_model, "serialization")])
                }
            },
        },
    )
    return responses


def _security_schemes() -> Dict[str, Any]:
    """The scheme Appendix B calls out as correct and not to be changed.

    An HttpOnly access-token cookie plus a CSRF token echoed in a header.  Both
    are needed for a state-changing call, which is why they are two schemes and
    why an authenticated write lists both.
    """
    return {
        "accessTokenCookie": {
            "type": "apiKey",
            "in": "cookie",
            "name": "access_token_cookie",
            "description": (
                "HttpOnly JWT set by POST /api/v1/login. Not readable by "
                "JavaScript, so it is paired with the CSRF header below on every "
                "state-changing method."
            ),
        },
        "csrfHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-CSRF-TOKEN",
            "description": (
                "Value of the csrf_access_token cookie, echoed by the client. "
                "Required on POST, PUT, PATCH, and DELETE."
            ),
        },
    }


_STATUS_TEXT = {
    200: "OK",
    201: "Created",
    202: "Accepted",
    204: "No content",
    400: "Bad request",
    401: "Authentication required",
    403: "Forbidden",
    404: "Not found",
    409: "Conflict",
    413: "Payload too large",
    422: "Validation failed",
    429: "Too many requests",
    500: "Internal server error",
    502: "Upstream error",
    503: "Service unavailable",
}


def write_openapi(path: Optional[Path] = None, app=None) -> Path:
    """Generate the document and write it to *path*.

    Returns:
        The path written.
    """
    if app is None:
        from app import app as flask_app

        app = flask_app
    target = Path(path or DEFAULT_OUTPUT)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Trailing newline and sorted keys so the committed file diffs cleanly and
    # the drift test compares text, not dict ordering.
    target.write_text(
        json.dumps(build_openapi(app), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


if __name__ == "__main__":  # pragma: no cover - CLI
    written = write_openapi()
    print("wrote %s" % written)
