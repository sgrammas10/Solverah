"""Per-endpoint rate limits actually fire.

Context, because these tests exist for a specific defect.

Every `@limiter.limit(...)` in the pre-Phase-1 `app.py` was written above its
`@app.route(...)`:

    @limiter.limit("5 per minute")
    @app.route("/api/login", methods=["POST"])
    def login(): ...

Decorators apply bottom-up, and `Flask.route` registers the function it is given
and returns it unchanged. So Flask registered the undecorated `login`, and the
`limiter.limit` wrapper -- which is what consults the limit -- was bound to a
module-level name nothing called. The result: the 5/minute on login, the
5/minute on register, the 3/minute on password reset, and the 1/day on guest
quiz insights had no effect whatsoever. Only the blanket `default_limits`
applied.

Moving the handlers into blueprints put the decorators in the conventional order
and the limits started working, which is how this was found. These tests are the
regression cover, and they fail against the old ordering.

Rate limiting is exempted for the test client (`security._skip_when_testing`) so
the other 590-odd tests can fire more than five logins a minute. These tests turn
`TESTING` off to exercise the real path.
"""

import pytest

from security import _skip_preflight, _skip_when_testing


@pytest.fixture()
def enforcing(client):
    """A client with the TESTING exemption switched off.

    The limiter's storage is reset around the test so counts from the rest of
    the suite cannot make this pass, and this test's counts cannot leak into
    anything that runs after it.
    """
    from app import app
    from solverah.extensions import limiter

    limiter.reset()
    app.config["TESTING"] = False
    try:
        yield client
    finally:
        app.config["TESTING"] = True
        limiter.reset()


def _login_body(n=0):
    return {"email": "nobody-%d@example.com" % n, "password": "wrong-password"}


# ── The limits fire ─────────────────────────────────────────────────────────


def test_login_is_limited_to_five_per_minute(enforcing):
    """Brute-force protection on the credential endpoint.

    Six wrong-password attempts: the first five reach the handler and get 401,
    the sixth is refused by the limiter.
    """
    statuses = [
        enforcing.post("/api/v1/login", json=_login_body(i)).status_code
        for i in range(6)
    ]

    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429


def test_the_limit_is_shared_across_the_versioned_and_legacy_paths(enforcing):
    """Alternating paths must not buy a second allowance.

    This is what `register_legacy_aliases` binding one endpoint to two rules
    buys. Registering each blueprint twice under a second prefix would create
    two endpoints, and Flask-Limiter keys its storage on the endpoint name -- an
    attacker would simply alternate /api/login and /api/v1/login for 10 tries a
    minute instead of 5.
    """
    paths = ["/api/v1/login", "/api/login"] * 3
    statuses = [enforcing.post(p, json=_login_body(i)).status_code
                for i, p in enumerate(paths)]

    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429


def test_register_is_limited(enforcing, monkeypatch):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", lambda *a, **k: None)

    statuses = []
    for i in range(6):
        statuses.append(
            enforcing.post(
                "/api/v1/register",
                json={
                    "email": "rl-%d@example.com" % i,
                    "password": "Strongpass1!",
                    "name": "Rate Limited",
                    "terms_accepted": True,
                },
            ).status_code
        )

    assert statuses[5] == 429


def test_password_reset_is_limited_to_three_per_minute(enforcing):
    statuses = [
        enforcing.post(
            "/api/v1/request-password-reset", json={"email": "nobody@example.com"}
        ).status_code
        for _ in range(4)
    ]

    assert statuses[:3] == [404] * 3
    assert statuses[3] == 429


def test_a_refusal_is_json_not_html(enforcing):
    """The frontend calls res.json() on every response.

    Werkzeug's default 429 page is HTML; Phase 0's error handlers turn it into a
    problem document. A limiter that answered in HTML would surface in the UI as
    "Unexpected response from server".
    """
    for i in range(6):
        resp = enforcing.post("/api/v1/login", json=_login_body(i))

    assert resp.status_code == 429
    assert resp.get_json()["status"] == 429


# ── The exemptions are exactly what they claim to be ────────────────────────


def test_the_test_client_exemption_is_gated_only_on_testing(client):
    """If this ever returns True outside TESTING, the limits are off in production."""
    from app import app

    with app.test_request_context("/api/v1/login", method="POST"):
        app.config["TESTING"] = False
        try:
            assert _skip_when_testing() is False
        finally:
            app.config["TESTING"] = True

        assert _skip_when_testing() is True


def test_preflight_is_exempt_but_the_real_method_is_not(client):
    """A browser issues OPTIONS unprompted; counting it would halve every limit."""
    from app import app

    with app.test_request_context("/api/v1/login", method="OPTIONS"):
        assert _skip_preflight() is True

    with app.test_request_context("/api/v1/login", method="POST"):
        assert _skip_preflight() is False


def test_limits_do_not_apply_under_the_default_test_client(client):
    """The exemption the other 590 tests depend on."""
    statuses = [client.post("/api/v1/login", json=_login_body(i)).status_code
                for i in range(8)]

    assert 429 not in statuses
