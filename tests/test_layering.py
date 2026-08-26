"""The layering in docs/ARCHITECTURE.md 2.2 holds, and is checked rather than hoped for.

    api/v1/*         HTTP only. Parse -> validate -> call service -> serialize.
        |            No business logic, no ORM queries, no external clients.
        v
    services/*       Business logic. Owns the transaction boundary.
        v
    repositories/*   All data access. Nothing else touches db.session.
        v
    domain/*         Pure functions and value objects. No Flask, no SQLAlchemy,
        v            no network.
    infra/*          Adapters: db, cache, object storage, email, LLM, queue.

A layering rule that lives only in a document is a rule that erodes one
reasonable-looking import at a time. These tests are cheap and they fail loudly,
which is the only reason the boundaries above will still mean something in six
months.

They are also what makes the rest of the roadmap tractable. Phase 2 rewrites the
schema under `repositories/`; Phase 3 moves `services/` calls onto a Celery
queue. Neither is possible if a route handler is running its own query or a
service is reading `flask.request`.
"""

import ast
import io
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SOLVERAH = REPO_ROOT / "solverah"
PACKAGES_ML = REPO_ROOT / "packages" / "ml"


def _modules(directory: Path):
    return sorted(p for p in directory.rglob("*.py") if "__pycache__" not in p.parts)


def _imported_names(path: Path) -> set[str]:
    """Every module name this file imports, at any nesting depth."""
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                names.add(node.module)
    return names


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


# ── The domain layer is pure ────────────────────────────────────────────────


@pytest.mark.parametrize("path", _modules(SOLVERAH / "domain"), ids=_rel)
def test_domain_has_no_framework_or_database_dependency(path):
    """`domain/` must be importable with no app context and no database.

    That is what makes the scoring and merge rules testable at their boundaries
    instead of through an HTTP request, and callable from a Celery worker in
    Phase 3 without dragging Flask along.
    """
    forbidden = {"flask", "sqlalchemy", "model", "requests", "boto3", "openai"}
    offenders = {
        name
        for name in _imported_names(path)
        if name.split(".")[0] in forbidden
    }

    assert offenders == set(), "%s imports %s" % (_rel(path), sorted(offenders))


@pytest.mark.parametrize("path", _modules(PACKAGES_ML), ids=_rel)
def test_packages_ml_has_no_flask_dependency(path):
    """docs/ARCHITECTURE.md 3.2 rule 2.

    `packages/ml` must be importable from the API, from a worker, and from a
    notebook. A Flask import here would make the deterministic ML -- the most
    valuable IP in the product -- reachable only through the web app.
    """
    forbidden = {"flask", "flask_sqlalchemy", "model"}
    offenders = {
        name for name in _imported_names(path) if name.split(".")[0] in forbidden
    }

    assert offenders == set(), "%s imports %s" % (_rel(path), sorted(offenders))


# ── Nothing above app.py imports it ────────────────────────────────────────


@pytest.mark.parametrize("path", _modules(SOLVERAH) + _modules(PACKAGES_ML), ids=_rel)
def test_nothing_in_the_package_imports_app(path):
    """`app.py` is the entrypoint, not a module anything depends on.

    Before Phase 1 the dependency ran both ways -- `account_lifecycle.py`
    imported `get_s3_client` from `app.py`, which imported `account_lifecycle`
    -- and the lazy in-function import that made it work was the visible symptom
    of the cycle. The one exception below is the OpenAPI CLI, which loads the
    app in order to walk its url_map; that is a tool consuming the entrypoint,
    which is the correct direction.
    """
    if path.name == "openapi.py":
        pytest.skip("the OpenAPI CLI loads the app deliberately; see its docstring")

    tree = ast.parse(io.open(path, encoding="utf-8").read())
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app":
            offenders.append(node.lineno)
        elif isinstance(node, ast.Import):
            offenders.extend(node.lineno for alias in node.names if alias.name == "app")

    assert offenders == [], "%s imports app at line(s) %s" % (_rel(path), offenders)


# ── The API layer does not query ───────────────────────────────────────────


@pytest.mark.parametrize("path", _modules(SOLVERAH / "api" / "v1"), ids=_rel)
def test_api_layer_does_not_touch_the_session(path):
    """A query in a handler is a query that cannot be reused, cached, or moved.

    Phase 2 rewrites the schema underneath `repositories/`; every query that
    escaped into a route handler is a second place that rewrite has to reach.
    """
    source = io.open(path, encoding="utf-8").read()

    assert "db.session" not in source, "%s touches db.session" % _rel(path)


@pytest.mark.parametrize("path", _modules(SOLVERAH / "api" / "v1"), ids=_rel)
def test_api_layer_does_not_build_provider_clients(path):
    """Routes call services; services call adapters. A route holding a provider
    client is a route that cannot be tested without stubbing the network."""
    source = io.open(path, encoding="utf-8").read()

    for forbidden in ("boto3.client", "OpenAI(", "resend."):
        assert forbidden not in source, "%s constructs %s" % (_rel(path), forbidden)


# ── Services stay callable from a worker ───────────────────────────────────


@pytest.mark.parametrize("path", _modules(SOLVERAH / "services"), ids=_rel)
def test_services_do_not_read_the_request(path):
    """A service that reads `flask.request` cannot run on a Celery queue.

    Phase 3 moves resume parsing, assessment scoring, path suggestions, match
    precomputation, and all email off the request path. Anything reading the
    request here is work that cannot make that move.

    `audit.py` is the documented exception: it records the client IP and user
    agent, and threading those two strings through every call site in the
    application is the change Phase 3 makes when audit writes go to the outbox.
    """
    if path.name == "audit.py":
        pytest.skip("documented exception; see solverah/services/audit.py")

    imported = _imported_names(path)
    source = io.open(path, encoding="utf-8").read()

    assert "flask" not in {n.split(".")[0] for n in imported} or "request" not in source, (
        "%s reads flask.request" % _rel(path)
    )
