"""Per-endpoint rate limits actually fire.

Context, because these tests exist for a specific defect.

Every `@limiter.limit(...)` in the pre-Phase-1 `app.py` was written above its
`@app.route(...)`:

    @limiter.limit("5 per minute")
    @app.route("/api/v1/auth/login", methods=["POST"])
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
        enforcing.post("/api/v1/auth/login", json=_login_body(i)).status_code
        for i in range(6)
    ]

    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429


def test_there_is_no_second_path_to_spend_a_second_allowance_on(enforcing):
    """What replaced the alias-sharing test, and why it is not simply deleted.

    Through Phase 1a the risk was two *paths* on one operation: Flask-Limiter
    keys its storage on the endpoint, so registering each blueprint again under
    a second prefix would have given `POST /api/login` and `POST /api/v1/login`
    separate 5-per-minute allowances and an attacker would have alternated them
    for 10. Binding one endpoint to two rules is what avoided that.

    Phase 1b removed the second path entirely, which makes the sharing assertion
    unwritable -- with both URLs collapsed to one, the old test passed no matter
    what the limiter did. The risk it guarded against is now the *reappearance*
    of an unversioned rule, so that is what is asserted.
    """
    assert enforcing.post("/api/login", json=_login_body(0)).status_code == 404


def test_register_is_limited(enforcing, monkeypatch):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", lambda *a, **k: None)

    statuses = []
    for i in range(6):
        statuses.append(
            enforcing.post(
                "/api/v1/auth/register",
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
            "/api/v1/auth/password/forgot", json={"email": "nobody@example.com"}
        ).status_code
        for _ in range(4)
    ]

    # 200, not 404: since S1 this endpoint answers the same for an address that
    # names no account as for one that does (tests/test_user_enumeration.py).
    # What is under test here is the fourth call, and it is unaffected -- the
    # limiter counts requests, not outcomes.
    assert statuses[:3] == [200] * 3
    assert statuses[3] == 429


def test_a_refusal_is_json_not_html(enforcing):
    """The frontend calls res.json() on every response.

    Werkzeug's default 429 page is HTML; Phase 0's error handlers turn it into a
    problem document. A limiter that answered in HTML would surface in the UI as
    "Unexpected response from server".
    """
    for i in range(6):
        resp = enforcing.post("/api/v1/auth/login", json=_login_body(i))

    assert resp.status_code == 429
    assert resp.get_json()["status"] == 429


# ── The exemptions are exactly what they claim to be ────────────────────────


def test_the_test_client_exemption_is_gated_only_on_testing(client):
    """If this ever returns True outside TESTING, the limits are off in production."""
    from app import app

    with app.test_request_context("/api/v1/auth/login", method="POST"):
        app.config["TESTING"] = False
        try:
            assert _skip_when_testing() is False
        finally:
            app.config["TESTING"] = True

        assert _skip_when_testing() is True


def test_preflight_is_exempt_but_the_real_method_is_not(client):
    """A browser issues OPTIONS unprompted; counting it would halve every limit."""
    from app import app

    with app.test_request_context("/api/v1/auth/login", method="OPTIONS"):
        assert _skip_preflight() is True

    with app.test_request_context("/api/v1/auth/login", method="POST"):
        assert _skip_preflight() is False


def test_limits_do_not_apply_under_the_default_test_client(client):
    """The exemption the other 590 tests depend on."""
    statuses = [client.post("/api/v1/auth/login", json=_login_body(i)).status_code
                for i in range(8)]

    assert 429 not in statuses


# ── One operation, two live paths, one bucket (Phase 1b) ────────────────────
#
# During the Phase 1b cutover each of these operations was served at two paths
# at once -- POST /auth/login beside POST /login -- and a second path means a
# second endpoint, which Flask-Limiter would ordinarily give a second
# independent bucket. `scope=` on `limiter.shared_limit` is what joined them.
#
# Two mistakes were possible and both were made and caught:
#
#   1. Using `limiter.limit(scope=...)` instead of `limiter.shared_limit(...)`.
#      The former keys its bucket as "{endpoint}:{scope}", which sub-divides one
#      endpoint rather than joining two, so the scope read correctly and did
#      nothing.
#   2. Writing the new view as `return login()`. At module scope `login` is the
#      limiter wrapper, not the handler, so that charged the shared bucket twice
#      per request and the new path silently ran at half its stated allowance.
#
# The second mistake outlives the cutover: any view that calls another view
# re-enters its decorators. The last two tests here are what keep it caught.


def test_one_request_costs_exactly_one_hit(enforcing):
    """The `return login()` bug, as a number.

    With the double charge this breached on the fourth request instead of the
    sixth -- a 5-per-minute limit behaving as 2.5.
    """
    statuses = [enforcing.post("/api/v1/auth/login", json=_login_body(i)).status_code
                for i in range(6)]

    assert statuses[:5] == [401] * 5
    assert statuses[5] == 429


def test_no_view_delegates_to_another_view(enforcing):
    """Structural cover for the same bug on the handlers this file cannot reach.

    A view whose body calls another *view* re-enters that view's decorators, so
    any limit on the callee is charged a second time for one request. Every
    Phase 1b handler that reuses a superseded body calls an undecorated `_do_*`
    helper instead; this asserts none of them regressed to calling the view.

    Checked by source rather than by counting hits because the failure is silent
    on every handler that happens to be unlimited today -- and the point is to
    catch it on the day a limit is added, not after.
    """
    import inspect
    import re

    from app import app
    from solverah.factory import V1_PREFIX

    view_names = {
        app.view_functions[rule.endpoint].__name__
        for rule in app.url_map.iter_rules()
    }

    offenders = []
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith(V1_PREFIX + "/"):
            continue
        view = app.view_functions[rule.endpoint]
        target = getattr(view, "__wrapped__", view)
        try:
            source = inspect.getsource(target)
        except (OSError, TypeError):
            continue
        for called in re.findall(r"return (\w+)\(\)", source):
            if called in view_names and called != target.__name__:
                offenders.append("%s -> %s()" % (rule.endpoint, called))

    assert sorted(set(offenders)) == []
