"""Contract tests for the generated OpenAPI document and the v1/legacy aliasing.

These are the tests that stop the Phase 1 restructure from rotting:

  * Every ``/api/v1`` route is documented -- an undocumented route fails the
    build, so a handler cannot be added without a schema.
  * No ``/api/v1`` route is served unversioned any more.  Phase 1a bound each
    one to an ``/api/...`` alias so the deployed frontend kept working; Phase 1b
    cut the frontend over and removed them, and a survivor would be an
    undocumented URL supported forever by accident.
  * The committed ``docs/openapi.json`` matches what the app generates, so the
    frontend can generate a typed client from the file in the repo without
    booting the API and without silently working from a stale contract.
"""

import io
import json
import re

import pytest

from solverah.factory import LEGACY_PREFIX, V1_PREFIX
from solverah.openapi import (
    DEFAULT_DESCRIPTION,
    DEFAULT_OUTPUT,
    build_openapi,
    route_spec,
    write_openapi,
)


@pytest.fixture()
def flask_app():
    from app import app

    return app


def _v1_rules(flask_app):
    return [r for r in flask_app.url_map.iter_rules() if r.rule.startswith(V1_PREFIX + "/")]


# ── Coverage ────────────────────────────────────────────────────────────────


def test_there_is_at_least_one_v1_route(flask_app):
    """Guards the tests below from passing vacuously on an empty registry."""
    assert _v1_rules(flask_app)


def test_every_v1_route_is_documented(flask_app):
    """A route with no @document spec is missing from the client's contract."""
    undocumented = [
        rule.rule
        for rule in _v1_rules(flask_app)
        if route_spec(flask_app.view_functions[rule.endpoint]) is None
    ]

    assert undocumented == []


def test_build_raises_rather_than_emitting_a_partial_document(flask_app, monkeypatch):
    """Silently dropping an undocumented route is how a contract goes stale."""
    rule = _v1_rules(flask_app)[0]
    view = flask_app.view_functions[rule.endpoint]
    monkeypatch.setattr("solverah.openapi.route_spec", lambda _fn: None)

    with pytest.raises(RuntimeError, match="no @document"):
        build_openapi(flask_app)

    assert view is flask_app.view_functions[rule.endpoint]  # nothing was mutated


# ── The aliases are gone ────────────────────────────────────────────────────
#
# Through Phase 1a this section asserted the opposite: that every /api/v1 rule
# was also served unversioned, on the same endpoint, so that one Flask-Limiter
# bucket covered both and a preflighted cross-origin POST never met a redirect.
# Phase 1b moved the frontend onto the versioned paths and removed the aliases,
# so the invariant flipped -- an unversioned rule surviving would be an
# undocumented URL supported forever by accident.
#
# tests/test_v1_aliasing.py checks the same thing over the wire. This is the
# url_map half.


def test_no_v1_route_has_an_unversioned_alias(flask_app):
    rules = {r.rule for r in flask_app.url_map.iter_rules()}
    surviving = sorted(
        LEGACY_PREFIX + r.rule[len(V1_PREFIX):]
        for r in _v1_rules(flask_app)
        if LEGACY_PREFIX + r.rule[len(V1_PREFIX):] in rules
    )

    assert surviving == []


def test_the_document_records_no_legacy_paths(flask_app):
    """`x-legacy-path` was the cutover's measurement, and the cutover is done.

    Leaving it in the document would advertise URLs that 404, which is worse
    than not mentioning them: a generated client could be built against one.
    """
    doc = build_openapi(flask_app)

    carrying = sorted(p for p, ops in doc["paths"].items() if "x-legacy-path" in ops)

    assert carrying == []


def _methods(rule):
    return frozenset(rule.methods - {"HEAD", "OPTIONS"})


# ── Operation-level coverage ────────────────────────────────────────────────
#
# Rule-level coverage is not enough, and these two tests exist because it wasn't:
# the first generator keyed paths by URL alone, which silently dropped POST
# /recommendations (a GET and a POST share that path), and it never converted
# Werkzeug's <int:company_id> into OpenAPI's {company_id}. Both passed every
# rule-level check.


def _openapi_path(rule_string):
    """Werkzeug rule syntax -> OpenAPI path template."""
    return re.sub(r"<(?:[^:>]+:)?([^>]+)>", "{" + chr(92) + "1}", rule_string)


def _url_map_operations(flask_app):
    return {
        (_openapi_path(rule.rule), method.lower())
        for rule in _v1_rules(flask_app)
        for method in _methods(rule)
    }


def _document_operations(doc):
    return {
        (path, method)
        for path, operations in doc["paths"].items()
        for method in operations
        if not method.startswith("x-")
    }


def test_every_operation_is_documented_not_just_every_rule(flask_app):
    """One path can carry two methods on two handlers; both must appear."""
    missing = _url_map_operations(flask_app) - _document_operations(build_openapi(flask_app))

    assert missing == set(), "operations served but undocumented: %s" % sorted(missing)


def test_the_document_invents_no_operations(flask_app):
    extra = _document_operations(build_openapi(flask_app)) - _url_map_operations(flask_app)

    assert extra == set(), "operations documented but not served: %s" % sorted(extra)


def test_path_parameters_use_openapi_templating(flask_app):
    """`<int:company_id>` is Werkzeug syntax and is not a valid OpenAPI path."""
    doc = build_openapi(flask_app)

    assert not [p for p in doc["paths"] if "<" in p or ">" in p]


def test_every_path_parameter_is_declared_with_a_type(flask_app):
    """A templated segment with no matching parameter object is an invalid document."""
    doc = build_openapi(flask_app)

    for path, operations in doc["paths"].items():
        templated = set(re.findall(r"{([^}]+)}", path))
        if not templated:
            continue
        for method, operation in operations.items():
            if method.startswith("x-"):
                continue
            declared = {
                p["name"] for p in operation.get("parameters", []) if p["in"] == "path"
            }
            assert templated <= declared, "%s %s missing %s" % (
                method,
                path,
                templated - declared,
            )
            for param in operation.get("parameters", []):
                if param["in"] == "path":
                    assert param["schema"].get("type"), param["name"]
                    assert param["required"] is True


# ── Document shape ──────────────────────────────────────────────────────────


def test_document_declares_openapi_31_and_the_2020_12_dialect(flask_app):
    """3.1 is the version whose Schema Object *is* JSON Schema 2020-12.

    That equivalence is the reason pydantic v2's output can be dropped into
    components/schemas untranslated, so the version is load-bearing, not cosmetic.
    """
    doc = build_openapi(flask_app)

    assert doc["openapi"].startswith("3.1")
    assert doc["jsonSchemaDialect"] == "https://json-schema.org/draft/2020-12/schema"


def test_every_operation_has_an_operation_id_and_a_response(flask_app):
    doc = build_openapi(flask_app)

    for path, operations in doc["paths"].items():
        for method, operation in operations.items():
            if method.startswith("x-"):
                continue
            assert operation.get("operationId"), "%s %s" % (method, path)
            assert operation.get("responses"), "%s %s" % (method, path)


def test_operation_ids_are_unique(flask_app):
    """A duplicate id makes a generated client emit two methods with one name."""
    ids = [
        operation["operationId"]
        for operations in build_openapi(flask_app)["paths"].values()
        for method, operation in operations.items()
        if not method.startswith("x-")
    ]

    assert len(ids) == len(set(ids)), sorted(ids)


def test_every_operation_documents_the_problem_details_fallback(flask_app):
    """Phase 0 made every unhandled failure problem+json; the contract says so."""
    doc = build_openapi(flask_app)

    for path, operations in doc["paths"].items():
        for method, operation in operations.items():
            if method.startswith("x-"):
                continue
            default = operation["responses"]["default"]
            assert "application/problem+json" in default["content"], "%s %s" % (method, path)


def test_every_schema_reference_resolves(flask_app):
    """A dangling $ref generates a client that will not compile."""
    doc = build_openapi(flask_app)
    declared = set(doc["components"]["schemas"])

    refs = set()

    def walk(node):
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                refs.add(ref.rsplit("/", 1)[-1])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(doc)

    assert refs - declared == set()


def test_documented_paths_are_only_the_versioned_ones(flask_app):
    """The unversioned paths are a migration affordance, not a supported contract."""
    doc = build_openapi(flask_app)

    assert all(path.startswith(V1_PREFIX + "/") for path in doc["paths"])



# ── Committed artefact ──────────────────────────────────────────────────────


def test_committed_document_is_not_stale(flask_app):
    """docs/openapi.json is what the frontend generates its client from.

    Regenerate with `python -m solverah.openapi`.
    """
    assert DEFAULT_OUTPUT.exists(), "run: python -m solverah.openapi"
    committed = io.open(DEFAULT_OUTPUT, encoding="utf-8").read()
    generated = json.dumps(build_openapi(flask_app), indent=2, sort_keys=True) + "\n"

    assert committed == generated, "docs/openapi.json is stale: python -m solverah.openapi"


def test_info_description_is_fixed_and_not_an_operations(flask_app):
    """`info.description` belongs to the document, not to whichever route sorts last.

    The generator's loop variable used to shadow the `description` parameter,
    so the document's description silently became the last operation's --
    `PUT /me/skills`' docstring, then `PUT /me/trait-preferences`' once a route
    sorted after it was added. A route addition at the end of the sort order
    moved the committed document's description with no route having changed.
    """
    doc = build_openapi(flask_app)

    assert doc["info"]["description"] == DEFAULT_DESCRIPTION
    operation_descriptions = {
        operation.get("description")
        for operations in doc["paths"].values()
        for operation in operations.values()
    }
    assert doc["info"]["description"] not in operation_descriptions
    assert build_openapi(flask_app, description="custom")["info"]["description"] == "custom"


def test_write_openapi_round_trips(tmp_path, flask_app):
    target = write_openapi(tmp_path / "openapi.json", app=flask_app)

    assert json.loads(io.open(target, encoding="utf-8").read())["openapi"] == "3.1.0"
