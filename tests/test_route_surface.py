"""Every registered route is actually wired up, and the public intake funnel works.

This file exists because of a specific bug and the gap that let it through.

Phase 1b deleted the superseded Phase 1a handlers. One of them,
``early_access_request``, had been factored into a shared ``_do_early_access``
helper during the cutover, and the deletion took the helper with it -- leaving
``POST /intake/early-access`` calling a name that no longer existed. Every test
passed. The endpoint would have raised ``NameError`` and returned 500 on the
first real request, because **nothing in the suite called it**.

Two things here address that, and it is worth being precise about which one does
what, because the obvious answer is the weaker one.

``test_no_undefined_names_in_the_route_modules`` is what would have caught this
bug. It parses each route module and asserts every name it loads is one it
defines or imports -- which is exactly the shape of the failure: a call to a
helper that was deleted underneath it. It runs in milliseconds and needs no app.

``test_no_route_answers_with_a_server_error`` is the broader sweep, and it would
**not** have caught this one. It calls every route with an empty body, and an
empty body is refused by the enforced schema before the handler runs -- so it
never reached the dead call. What it does catch is a 5xx on any route whose
schema lets an empty body through, which is a real and different class of bug.
Both are cheap; neither subsumes the other.

The rest of the file is the coverage that was actually missing: the public
intake funnel, which is the most exposed surface in the application and had two
endpoints nobody exercised. That is what turned the bug from invisible into a
failing test.
"""

import ast
import builtins
import io
from pathlib import Path

import pytest

from solverah.factory import V1_PREFIX

REPO_ROOT = Path(__file__).resolve().parents[1]
ROUTE_MODULES = sorted((REPO_ROOT / "solverah" / "api" / "v1").glob("*.py"))


def _unresolved_names(path: Path) -> list:
    """Names *path* reads that it neither defines nor imports.

    A deliberately simple scope model -- every binding anywhere in the module
    counts as defined -- because the failure being caught is not subtle. A call
    to something that does not exist at all reads as a name bound nowhere, and
    that is what a deleted helper leaves behind.
    """
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    defined = set(dir(builtins))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                defined.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            defined.add(node.id)
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
    used = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    return sorted(used - defined)


def test_the_route_modules_are_found():
    """Guards the test below from passing over an empty list."""
    assert len(ROUTE_MODULES) >= 6


@pytest.mark.parametrize("module", ROUTE_MODULES, ids=lambda p: p.name)
def test_no_undefined_names_in_the_route_modules(module):
    """The check that would have caught the bug in this file's docstring.

    A handler calling a helper that was deleted underneath it is invisible until
    the route is requested, and a route with no test is never requested. This
    finds it without running anything.
    """
    assert _unresolved_names(module) == []

#: Routes the sweep does not call, with the reason for each.
#:
#: Deliberately empty. An exclusion is a route the sweep stops protecting, and
#: the one candidate -- `POST /agent/messages`, which streams Server-Sent Events
#: from a live provider client -- turned out not to need it: its schema requires
#: a non-empty message list, so an empty body is refused before any of the
#: streaming machinery is reached. Add to this only with a reason written down.
_SKIP: set = set()


def _v1_routes(app):
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith(V1_PREFIX + "/"):
            continue
        if rule.endpoint in _SKIP:
            continue
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            # Fill path converters with something well-formed for their type.
            path = rule.rule
            for argument in rule.arguments:
                converter = rule._converters[argument].__class__.__name__.lower()
                value = "1" if "integer" in converter else "core"
                path = path.replace("<%s>" % argument, value)
                path = path.replace("<int:%s>" % argument, value)
            yield rule.endpoint, method, path


def test_the_sweep_covers_the_whole_surface(client):
    """Guards the test below from passing because the route scan found nothing."""
    from app import app

    assert len(list(_v1_routes(app))) >= 25


def test_no_route_answers_with_a_server_error(client):
    """The wiring check. A 500 here is a bug in the route, not in the request.

    Every route is called unauthenticated with an empty body, so the expected
    answers are 401 (needs a JWT), 422 (enforced schema rejects the empty body),
    400, 404, or 405. Anything 5xx means the handler could not run at all --
    which is exactly what a deleted helper, a stale import, or a typo produces.
    """
    from app import app

    failures = []
    for endpoint, method, path in _v1_routes(app):
        resp = client.open(path, method=method, json={})
        if resp.status_code >= 500:
            failures.append("%s %s -> %d (%s)" % (method, path, resp.status_code, endpoint))

    assert failures == [], "routes that could not run:\n  " + "\n  ".join(failures)


# ── The public intake funnel ────────────────────────────────────────────────
#
# Unauthenticated, and the most exposed surface in the application. Two of these
# endpoints had no test of their own before Phase 1b.


def test_early_access_forwards_the_lead(client, monkeypatch):
    sent = {}

    def _capture(**kwargs):
        sent.update(kwargs)

    monkeypatch.setattr(
        "solverah.infra.email.send_early_access_modal_notification", _capture
    )

    resp = client.post(
        "/api/v1/intake/early-access",
        json={"firstName": "Ada", "lastName": "Lovelace",
              "email": "ada@example.com", "phone": "555-0100"},
    )

    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}
    assert sent["email"] == "ada@example.com"


def test_early_access_requires_a_name_and_an_email(client):
    resp = client.post("/api/v1/intake/early-access", json={"email": "ada@example.com"})

    assert resp.status_code == 422
    missing = {error["field"] for error in resp.get_json()["errors"]}
    assert missing == {"firstName", "lastName"}


def test_early_access_reports_a_delivery_failure(client, monkeypatch):
    """The one intake endpoint that returns 500 rather than swallowing the error.

    Nothing is persisted -- the submission exists only as an email -- so a
    silent failure loses the lead entirely.
    """
    def _boom(**_kwargs):
        raise RuntimeError("resend is down")

    monkeypatch.setattr(
        "solverah.infra.email.send_early_access_modal_notification", _boom
    )

    resp = client.post(
        "/api/v1/intake/early-access",
        json={"firstName": "Ada", "lastName": "Lovelace", "email": "ada@example.com"},
    )

    assert resp.status_code == 500


def test_a_resume_ticket_mints_a_submission_id_and_an_upload_url(client, monkeypatch):
    """Step 1 of the anonymous funnel.

    The id is server-minted and is the *only* thing protecting an anonymous
    submission -- there is no account to authorise against -- which is why this
    endpoint is not `POST /intake/submissions/{id}/resume-ticket` as Part 5.2
    sketches it. The id does not exist until this call creates it.
    """
    class _FakeS3:
        def generate_presigned_url(self, **_kwargs):
            return "https://example.invalid/put"

    monkeypatch.setattr("solverah.infra.storage.get_s3_client", lambda: _FakeS3())
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")

    resp = client.post(
        "/api/v1/intake/resume-tickets",
        json={"mime": "application/pdf", "size": 1024},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["submission_id"]
    assert body["object_key"].startswith("intake/%s/" % body["submission_id"])
    assert body["upload_url"]


def test_a_resume_ticket_refuses_an_unsupported_type(client):
    resp = client.post(
        "/api/v1/intake/resume-tickets", json={"mime": "image/png", "size": 1024}
    )

    assert resp.status_code == 400


def test_a_resume_ticket_enforces_its_schema(client):
    resp = client.post("/api/v1/intake/resume-tickets", json={"mime": "application/pdf"})

    assert resp.status_code == 422
    assert {e["field"] for e in resp.get_json()["errors"]} == {"size"}


def test_a_submission_will_not_commit_without_a_verified_upload(client, monkeypatch):
    """The HEAD check is what makes the row mean something.

    The ticket signs a ContentLength, so R2 rejects a body of a different size --
    but nothing stops a client skipping the upload entirely and calling this
    anyway. Without the check the submission would point at a key holding
    nothing.
    """
    class _EmptyBucket:
        def head_object(self, **_kwargs):
            raise RuntimeError("NoSuchKey")

    monkeypatch.setattr("solverah.infra.storage.get_s3_client", lambda: _EmptyBucket())
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")

    resp = client.post(
        "/api/v1/intake/submissions",
        json={
            "submission_id": "3f1a5b2c-0000-4000-8000-000000000000",
            "object_key": "intake/3f1a5b2c-0000-4000-8000-000000000000/resume.pdf",
            "mime": "application/pdf", "size": 1024,
            "first_name": "Ada", "last_name": "Lovelace",
            "email": "ada@example.com", "state": "NY", "privacy_consent": True,
        },
    )

    assert resp.status_code == 400
    assert "upload" in resp.get_json()["error"].lower()


def test_a_submission_enforces_its_schema(client):
    resp = client.post("/api/v1/intake/submissions", json={"first_name": "Ada"})

    assert resp.status_code == 422
    missing = {error["field"] for error in resp.get_json()["errors"]}
    assert "submission_id" in missing
    assert "privacy_consent" in missing
