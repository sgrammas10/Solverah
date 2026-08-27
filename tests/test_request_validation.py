"""``@document(enforce=True)`` -- what enforcement rejects, and where it runs.

Phase 1b turned the schemas from descriptive into enforced, which is a live
behaviour change on every route that carries it. These are the tests for the
three decisions that made it safe to flip, plus the two structural properties
the mechanism depends on.

The structural ones matter most, because both are things that were *declared*
correctly in this codebase before and did nothing:

* enforcement cannot be defeated by decorator order -- the failure that made
  every `@limiter.limit` in the pre-Phase-1 `app.py` inert;
* a request rejected here is not charged to its endpoint's rate-limit bucket,
  which is deliberate and is not something a different hook placement could
  change.
"""

import pytest

from solverah.openapi import document, route_spec

EMAIL = "validation@example.com"
PASSWORD = "Strongpass1!"


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture()
def auth(client, monkeypatch):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "name": "Validation User",
              "role": "job-seeker", "terms_accepted": True},
    )

    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


# ── The three decisions from the pre-flip audit ─────────────────────────────


def test_a_missing_required_field_is_a_422(client):
    """The part that is genuinely new, and the point of enforcing.

    An empty login body used to travel as far as a password comparison against
    the empty string.
    """
    resp = client.post("/api/v1/auth/login", json={})

    assert resp.status_code == 422
    fields = {error["field"] for error in resp.get_json()["errors"]}
    assert fields == {"email", "password"}


def test_an_unknown_key_is_dropped_rather_than_rejected(client, monkeypatch):
    """The decision that stops the flip being an incident.

    Every handler reads its fields with `data.get(...)` and ignores the rest,
    and live call sites send more than the schemas name -- `role` on register is
    the one that would have broken. A 422 on a key the server was going to
    ignore is exactly the "worked yesterday, 422 today" failure.
    """
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)

    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "extra-keys@example.com", "password": PASSWORD,
              "name": "Extra", "terms_accepted": True,
              "role": "job-seeker", "utm_source": "newsletter"},
    )

    assert resp.status_code == 201


def test_a_coercible_type_is_coerced_not_policed(client, auth, monkeypatch):
    """`int(data.get("size") or 0)` accepted a numeric string; so does the model."""
    monkeypatch.setattr(
        "solverah.services.resume_service.presign_upload",
        lambda key, mime, size: "https://example.invalid/put",
    )

    resp = client.post(
        "/api/v1/me/resumes",
        json={"mime": "application/pdf", "size": "1024"},
        headers={"X-CSRF-TOKEN": auth},
    )

    assert resp.status_code == 200


def test_an_absent_body_is_treated_as_an_empty_one(client):
    """"No body" and "empty body" get one answer rather than two."""
    resp = client.post("/api/v1/auth/login")

    assert resp.status_code == 422
    assert {e["field"] for e in resp.get_json()["errors"]} == {"email", "password"}


# ── The error body ──────────────────────────────────────────────────────────


def test_a_rejection_is_a_problem_document(client):
    """Part 5.1: one error shape everywhere, in application/problem+json."""
    resp = client.post("/api/v1/auth/login", json={})
    body = resp.get_json()

    assert resp.mimetype == "application/problem+json"
    assert body["type"].endswith("/validation")
    assert body["status"] == 422
    assert body["instance"] == "/api/v1/auth/login"
    assert body["request_id"]


def test_errors_carry_a_machine_readable_code(client):
    """A client should branch on `code`, not match prose."""
    resp = client.post("/api/v1/auth/login", json={"email": "a@b.c"})

    error = resp.get_json()["errors"][0]
    assert error["field"] == "password"
    assert error["code"] == "missing"


def test_the_rejected_value_is_never_echoed_back(client):
    """The one endpoint where echoing the input puts a password in a log."""
    resp = client.post(
        "/api/v1/auth/login", json={"email": "a@b.c", "password": {"not": "a string"}}
    )
    body = resp.get_text() if hasattr(resp, "get_text") else resp.get_data(as_text=True)

    assert resp.status_code == 422
    assert "not a string" not in body
    assert "hunter2" not in body


# ── Structural: order-independence ──────────────────────────────────────────


def test_enforcement_does_not_depend_on_decorator_order(client):
    """The failure this mechanism is shaped to avoid.

    `@document` is written above `@bp.route`, and `Blueprint.route` registers
    the function it is handed and returns it unchanged -- so a decorator applied
    above it annotates an object Flask has already registered. Fine for stashing
    an attribute, useless for wrapping. Every `@limiter.limit` in the
    pre-Phase-1 `app.py` was written that way and enforced nothing.

    Enforcement therefore resolves the spec from `request.endpoint` at request
    time. This asserts the property directly: the view function registered for
    an enforced route is NOT a validation wrapper, and the route enforces anyway.
    """
    from app import app

    view = app.view_functions["auth.login"]
    assert route_spec(view).enforce is True
    assert "valid" not in view.__qualname__.lower()

    assert client.post("/api/v1/auth/login", json={}).status_code == 422


def test_a_handlers_own_refusal_still_reaches_the_client(client, monkeypatch):
    """Enforcement checks the shape; it does not take over the business rules.

    A body that satisfies the schema still goes to the handler, and the handler
    can still refuse it on grounds no schema can express. `terms_accepted: false`
    is a valid boolean and a valid `RegisterRequest`; it is the *consent* that is
    missing, which is a rule about what the value means. That answer must not be
    swallowed or reshaped by the layer in front of it.
    """
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)

    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "noconsent@example.com", "password": PASSWORD,
              "name": "No Consent", "terms_accepted": False},
    )

    assert resp.status_code == 400
    assert "Terms" in resp.get_json()["error"]


def test_the_decorator_still_wraps_nothing(client):
    """`@document` stores a spec and hands the same object back.

    If it ever started returning a wrapper it would silently stop working
    wherever it is written above `@bp.route`, which is everywhere.
    """
    def view():
        return "ok"

    decorated = document("x", enforce=True)(view)

    assert decorated is view


# ── Structural: what a rejection costs ──────────────────────────────────────


def test_a_rejected_request_is_not_charged_to_the_rate_limit_bucket(client):
    """Deliberate, and not something a different hook placement could change.

    Flask-Limiter evaluates `default_limits` in `before_request` but evaluates
    *decorated* limits inside the wrapper around the view function, so a request
    refused before the view never reaches its bucket.

    It is also the behaviour to want. A rate limit bounds expensive work; a 422
    is a parse of a body already capped at MAX_CONTENT_LENGTH. Charging for it
    would let a broken client -- or a stranger behind the same NAT gateway --
    spend a real user's login allowance with nothing but garbage.
    """
    from app import app
    from solverah.extensions import limiter

    limiter.reset()
    app.config["TESTING"] = False
    try:
        # Well past the 5-per-minute the endpoint carries.
        malformed = [client.post("/api/v1/auth/login", json={}).status_code
                     for _ in range(8)]
        # The budget is still intact for a real attempt.
        real = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "wrong-password"},
        ).status_code
    finally:
        app.config["TESTING"] = True
        limiter.reset()

    assert malformed == [422] * 8
    assert real == 401


def test_validation_runs_before_authentication(client):
    """Consequence of the hook placement, and harmless.

    An anonymous caller with a malformed body gets 422 rather than 401. Every
    enforced schema is published in docs/openapi.json, so the 422 discloses
    nothing the contract does not already hand out.
    """
    resp = client.patch("/api/v1/me/profile", json={})

    assert resp.status_code == 422


def test_a_valid_body_still_reaches_the_auth_check(client):
    """The corollary: validation must not become a way past `@jwt_required()`."""
    resp = client.patch("/api/v1/me/profile", json={"profile": {"phone": "555"}})

    assert resp.status_code == 401


# ── Coverage: the new surface is enforced, the old is not ───────────────────


def test_every_route_enforces_its_schema(client):
    """The Phase 1b exit criterion, asserted rather than assumed.

    There is no allowlist. While the superseded Phase 1a handlers were still
    live this test carried a set of endpoints exempted from enforcement --
    turning a schema on for a route about to be deleted could only break a
    client that had not finished moving off it. Those handlers are gone, so the
    exemption set is gone with them, and the invariant is unconditional.
    """
    from app import app
    from solverah.factory import V1_PREFIX

    unenforced = sorted(
        rule.rule
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith(V1_PREFIX + "/")
        and route_spec(app.view_functions[rule.endpoint]) is not None
        and not route_spec(app.view_functions[rule.endpoint]).enforce
    )

    assert unenforced == []
