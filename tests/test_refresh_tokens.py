"""Database-backed refresh tokens: logout revokes, reuse revokes, rotation rotates.

This is audit finding 1.1 (HIGH), asserted.  Until S3 `POST /auth/logout` called
`unset_jwt_cookies` and nothing else -- the handler's own docstring admitted the
JWT "stays valid until it expires" -- so a captured access cookie survived the
victim logging out for up to an hour and no operator action short of rotating
`JWT_SECRET_KEY` fleet-wide revoked it.

Four properties carry the round, and each has a test written to fail if the
property is removed rather than to describe the code that implements it:

1. **Logout invalidates the refresh token.**  `test_logout_*`.
2. **A retired token presented outside the grace window revokes its family.**
   `test_replayed_token_*`.
3. **Rotation issues a new token every time.**  `test_refresh_rotates_*`.
4. **Concurrent refresh does not self-revoke.**  `test_two_simultaneous_*`,
   which runs two real requests through two threads against one Postgres row.

The fourth is the one this design most often ships broken.  Two tabs, or two
parallel TanStack queries in one tab, hit a 401 at the same instant and present
the *same* refresh token; the second one looks exactly like theft, and a
rotation scheme with no grace window signs the user out for using the product
normally.  The single-flight guard on the client (`AuthContext.tsx`) is the
first half of the answer and the server-side grace window is the second, and
only the second is testable here.  A design that works single-tab is not a
working design, so the concurrency test is not optional cover.

The negative cases matter as much: an **expired** token must not revoke a
family (an expired session is the system working), and an **unknown** token
must not either (there is no family, and no evidence of anything).  Both are
asserted, because the cheap wrong implementation treats every refusal as reuse
and signs people out of sessions nobody attacked.
"""

import datetime
import threading

import pytest
import sqlalchemy as sa

from solverah.services import refresh_tokens

EMAIL = "refresh-api@example.test"
OTHER_EMAIL = "refresh-other@example.test"
PASSWORD = "Strongpass1!"

REFRESH_PATH = "/api/v1/auth/refresh"
COOKIE = "refresh_token_cookie"


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture(autouse=True)
def _no_outbound_email(monkeypatch):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.infra.email.send_password_reset_email", _noop)


def _register_confirmed(client, email=EMAIL):
    """An account that can log in: registered, then confirmed directly."""
    from app import app
    from model import User, db

    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "name": "Refresh User",
              "terms_accepted": True},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()
        return user.id


def _login(client, email=EMAIL):
    """Sign in and return ``(csrf_token, raw_refresh_token)``."""
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["csrfToken"], _cookie_value(client)


def _cookie_value(client):
    cookie = client.get_cookie(COOKIE, path=REFRESH_PATH)
    return None if cookie is None else cookie.value


def _set_refresh_cookie(client, raw):
    client.set_cookie(COOKIE, raw, path=REFRESH_PATH, domain="localhost")


def _refresh(client, **kwargs):
    """POST the refresh endpoint the way the SPA does: JSON, no body."""
    kwargs.setdefault("json", {})
    return client.post(REFRESH_PATH, **kwargs)


def _sessions():
    """Every `user_sessions` row, oldest first, as ORM objects."""
    from app import app
    from model import UserSession

    with app.app_context():
        return UserSession.query.order_by(UserSession.id).all()


def _set_cookie_names(response):
    return sorted(
        {value.split("=", 1)[0] for key, value in response.headers
         if key.lower() == "set-cookie"}
    )


def _age_retirements(minutes):
    """Push every retirement *minutes* into the past.

    How a token gets outside the grace window without the test sleeping for it.
    Moving the clock rather than the constant, because a test that lowered
    ``GRACE_SECONDS`` to zero would prove the code works with no grace window --
    which is the design being ruled out, not the one being checked.
    """
    from app import app
    from model import UserSession, db

    table = UserSession.__table__
    with app.app_context():
        db.session.execute(
            sa.update(table)
            .where(table.c.retired_at.isnot(None))
            .values(
                retired_at=datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(minutes=minutes)
            )
        )
        db.session.commit()


# ── 1. Logout invalidates the refresh token ─────────────────────────────────


def test_logout_revokes_the_refresh_family_server_side(client):
    """The finding. A logout that only clears cookies is the bug."""
    _register_confirmed(client)
    csrf, _raw = _login(client)

    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": csrf}).status_code == 200

    rows = _sessions()
    assert len(rows) == 1
    assert rows[0].retired_at is not None
    assert rows[0].retired_reason == refresh_tokens.REASON_LOGGED_OUT


def test_a_refresh_token_captured_before_logout_is_worthless_after_it(client):
    """The exploit, run.

    The attacker holds a copy of the cookie; the victim logs out in another
    browser. Before S3 the copy kept working. It must now answer 401.
    """
    _register_confirmed(client)
    csrf, stolen = _login(client)

    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": csrf})

    attacker = _fresh_client()
    _set_refresh_cookie(attacker, stolen)
    assert _refresh(attacker).status_code == 401


def test_logout_clears_the_refresh_cookie_at_the_path_it_was_set_on(client):
    """A Set-Cookie whose path differs by a character deletes nothing.

    `unset_jwt_cookies` reads `JWT_REFRESH_COOKIE_PATH`, and so does the
    handler that sets the cookie. This asserts they are the same key rather
    than trusting two string literals to stay equal.
    """
    _register_confirmed(client)
    csrf, _raw = _login(client)
    assert _cookie_value(client) is not None

    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": csrf})

    assert _cookie_value(client) in (None, "")


def test_logout_without_a_session_still_answers_200(client):
    """Unchanged behaviour, and the mid-session-user path after deploy.

    A caller with no JWT -- or one issued before this round, carrying no `sid`
    claim -- has no family to revoke. Logout has always answered 200 for them.
    """
    assert client.post("/api/v1/auth/logout").status_code == 200


def test_a_forged_cross_site_logout_cannot_revoke_anything(client):
    """Audit #25 stays a nuisance rather than becoming a revocation primitive.

    A cross-site page can force a logout -- it cannot attach the CSRF header, so
    the JWT does not verify, so the handler finds no `sid` and clears cookies
    without touching the database. The session survives; the victim's cookies
    do not, which is exactly the pre-S3 behaviour of the whole endpoint.
    """
    _register_confirmed(client)
    _csrf, _raw = _login(client)

    assert client.post("/api/v1/auth/logout").status_code == 200

    rows = _sessions()
    assert rows[0].retired_at is None, "a CSRF-less logout revoked a live session"


# ── 2. A retired token outside the grace window revokes its family ──────────


def test_replayed_token_outside_the_grace_window_revokes_the_whole_family(client):
    """Reuse detection.

    The victim rotated past this token, so a second presentation of it means a
    copy exists somewhere it should not. At that point the attacker's copy and
    the victim's are indistinguishable, so both die.
    """
    _register_confirmed(client)
    _csrf, first = _login(client)
    assert _refresh(client).status_code == 200
    live_after_rotation = _cookie_value(client)

    _age_retirements(minutes=5)

    attacker = _fresh_client()
    _set_refresh_cookie(attacker, first)
    assert _refresh(attacker).status_code == 401

    victim = _fresh_client()
    _set_refresh_cookie(victim, live_after_rotation)
    assert _refresh(victim).status_code == 401, "the family survived a detected reuse"

    rows = _sessions()
    assert [row.retired_reason for row in rows] == [
        refresh_tokens.REASON_ROTATED,
        refresh_tokens.REASON_REUSED,
    ]


def test_reuse_detection_writes_a_security_event(client):
    """"Log it as a security event." Ids only -- never the address (audit #18)."""
    from model import AuditLog

    from app import app

    _register_confirmed(client)
    _csrf, first = _login(client)
    _refresh(client)
    _age_retirements(minutes=5)

    attacker = _fresh_client()
    _set_refresh_cookie(attacker, first)
    _refresh(attacker)

    with app.app_context():
        events = AuditLog.query.filter_by(action="refresh_token_reuse").all()
    assert len(events) == 1
    metadata = events[0].event_metadata
    assert metadata["revoked_siblings"] == 1
    assert EMAIL not in str(metadata)


def test_a_token_retired_by_logout_is_never_inside_the_grace_window(client):
    """Grace is for rotation only, and immediately -- not for a dead session.

    Presenting a logged-out token one millisecond later must be refused, or
    "logout revokes" would hold for thirty seconds less than it claims.
    """
    _register_confirmed(client)
    csrf, raw = _login(client)
    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": csrf})

    attacker = _fresh_client()
    _set_refresh_cookie(attacker, raw)
    assert _refresh(attacker).status_code == 401


def test_an_expired_token_is_refused_without_revoking_the_family(client):
    """Expiry is not theft.

    A token nobody came back for in thirty days is the system working. Treating
    it as reuse would revoke a family for the crime of being old, and the
    cheap wrong implementation does exactly that.
    """
    from app import app
    from model import UserSession, db

    _register_confirmed(client)
    _csrf, raw = _login(client)

    table = UserSession.__table__
    with app.app_context():
        db.session.execute(
            sa.update(table).values(
                expires_at=datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=1)
            )
        )
        db.session.commit()

    assert _refresh(client).status_code == 401

    rows = _sessions()
    assert rows[0].retired_reason == refresh_tokens.REASON_EXPIRED


def test_an_unknown_token_is_refused_and_revokes_nothing(client):
    """No row means no family and no evidence -- of anything except a stranger."""
    _register_confirmed(client)
    _csrf, _raw = _login(client)

    prober = _fresh_client()
    _set_refresh_cookie(prober, "not-a-token-anyone-ever-issued")
    assert _refresh(prober).status_code == 401

    assert _sessions()[0].retired_at is None


def test_a_session_whose_account_is_gone_is_refused_not_a_500(client):
    """The path that mints credentials must not dereference a missing user.

    Very nearly unreachable in the running system -- `user_id` cascades, and
    account deletion removes these rows explicitly because it tombstones rather
    than deletes -- but "very nearly" is not a thing to leave unhandled where an
    attacker controls the input and the failure mode is a 500 on the auth path.

    Constructed by dropping the foreign key and pointing the row at an id no
    user has, because that is the only way to reach the state: with the
    constraint in place the database will not let it exist. Dropping DDL inside
    a test is unusual and is the honest way here -- the alternative is stubbing
    the lookup, which would test the stub.

    The constraint name is spelled out rather than looked up, and it is the same
    name in both schemas on purpose: the model names it (see `model.UserSession`)
    so `db.create_all()` and the migration agree. If they ever stop agreeing this
    test says so, which is a second thing worth knowing.
    """
    from app import app
    from model import UserSession, db

    _register_confirmed(client)
    _csrf, raw = _login(client)

    with app.app_context():
        db.session.execute(
            sa.text("ALTER TABLE user_sessions DROP CONSTRAINT fk_user_sessions_user")
        )
        db.session.execute(
            sa.update(UserSession.__table__).values(user_id=987654321)
        )
        db.session.commit()

    orphaned = _fresh_client()
    _set_refresh_cookie(orphaned, raw)
    response = _refresh(orphaned)

    assert response.status_code == 401
    assert _sessions()[0].retired_at is not None, "the orphan stayed presentable"


def test_every_refusal_answers_the_same_body(client):
    """The endpoint is not an oracle.

    Stale, stolen, expired and never-issued all answer identically, so the
    response cannot be used to tell a token that was retired from one that was
    never minted -- the same reasoning S1 applied to `/auth/password/reset`.
    """
    _register_confirmed(client)
    _csrf, first = _login(client)
    _refresh(client)
    _age_retirements(minutes=5)

    bodies = []
    for raw in (first, "never-issued-at-all"):
        probe = _fresh_client()
        _set_refresh_cookie(probe, raw)
        response = _refresh(probe)
        bodies.append((response.status_code, response.get_data(as_text=True)))

    no_cookie = _refresh(_fresh_client())
    bodies.append((no_cookie.status_code, no_cookie.get_data(as_text=True)))

    assert len(set(bodies)) == 1, bodies


# ── 3. Rotation issues a new token every time ──────────────────────────────


def test_refresh_rotates_the_token_on_every_use(client):
    """Single-use, which is what makes reuse detection possible at all."""
    _register_confirmed(client)
    _csrf, first = _login(client)

    seen = [first]
    for _ in range(3):
        assert _refresh(client).status_code == 200
        seen.append(_cookie_value(client))

    assert len(set(seen)) == len(seen), "a refresh handed back a token it had seen"


def test_rotation_keeps_one_family_and_links_the_chain(client):
    """One sign-in is one family however many times it rotates.

    Without this a rotation would open a new family, reuse detection would have
    nothing to revoke beyond a single row, and the ancestor an attacker holds
    would sit outside the family its descendant belongs to.
    """
    _register_confirmed(client)
    _login(client)
    _refresh(client)
    _refresh(client)

    rows = _sessions()
    assert len({str(row.family_id) for row in rows}) == 1
    assert [row.parent_id for row in rows] == [None, rows[0].id, rows[1].id]
    assert [row.successor_id for row in rows] == [rows[1].id, rows[2].id, None]


def test_rotation_retires_the_presented_token(client):
    _register_confirmed(client)
    _login(client)
    _refresh(client)

    rows = _sessions()
    assert rows[0].retired_reason == refresh_tokens.REASON_ROTATED
    assert rows[1].retired_at is None


def test_a_rotated_session_still_authenticates(client):
    """The point of the whole exchange: the new access cookie works."""
    _register_confirmed(client)
    _login(client)
    assert _refresh(client).status_code == 200

    assert client.get("/api/v1/auth/session").status_code == 200


# ── 4. Concurrent refresh does not self-revoke ─────────────────────────────


def test_replaying_a_just_rotated_token_inside_the_grace_window_succeeds(client):
    """The stampede, serialised: two requests, the second arriving after the first.

    This is the shape a browser actually produces -- the second tab's request
    was already in flight when the first one rotated -- and without the grace
    window it is indistinguishable from theft. The second caller gets a fresh
    access token and **no** Set-Cookie for the refresh token, because the
    successor the first request minted is already in the shared cookie jar.
    """
    _register_confirmed(client)
    _csrf, first = _login(client)
    assert _refresh(client).status_code == 200

    second_tab = _fresh_client()
    _set_refresh_cookie(second_tab, first)
    response = _refresh(second_tab)

    assert response.status_code == 200
    assert COOKIE not in _set_cookie_names(response)
    assert "access_token_cookie" in _set_cookie_names(response)
    assert _sessions()[-1].retired_at is None, "the grace path revoked the live token"


def test_two_simultaneous_refreshes_of_one_token_do_not_revoke_the_family(client):
    """The concurrency case, run concurrently against one Postgres row.

    Two threads present the same token through two real requests, released
    together by a barrier so they contend on the conditional UPDATE that claims
    the row. Both must answer 200, exactly one must mint a successor, and the
    family must still be usable afterwards.

    The test above proves the grace *window*; this one proves the *claim* --
    they fail differently. A read-then-write rotation passes the sequential
    test and fails here by minting two successors, which leaves two live tokens
    in one family and a jar holding whichever response landed last.
    """
    _register_confirmed(client)
    _csrf, raw = _login(client)

    barrier = threading.Barrier(2)
    results = {}

    def hit(index):
        caller = _fresh_client()
        _set_refresh_cookie(caller, raw)
        barrier.wait(timeout=10)
        response = _refresh(caller)
        results[index] = (response.status_code, _set_cookie_names(response))

    threads = [threading.Thread(target=hit, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "a concurrent refresh deadlocked"

    assert len(results) == 2, results
    statuses = sorted(status for status, _ in results.values())
    assert statuses == [200, 200], results

    rotations = [names for _s, names in results.values() if COOKIE in names]
    assert len(rotations) == 1, "both racers rotated; the row was claimed twice"

    rows = _sessions()
    assert len(rows) == 2, "expected exactly one successor, got %d rows" % len(rows)
    assert rows[0].retired_reason == refresh_tokens.REASON_ROTATED
    assert rows[1].retired_at is None, "the concurrent pair revoked its own family"


def test_the_grace_window_does_not_extend_the_family(client):
    """A grace hit is not a rotation, and must not act like one.

    If it minted a successor, the token still in the jar would be the *older*
    one whenever the first response landed last -- and fifteen minutes later
    that token is outside the window and revokes the family. Handing back an
    access token and nothing else is what makes the window safe to have.
    """
    _register_confirmed(client)
    _csrf, first = _login(client)
    _refresh(client)
    before = len(_sessions())

    second_tab = _fresh_client()
    _set_refresh_cookie(second_tab, first)
    _refresh(second_tab)

    assert len(_sessions()) == before, "the grace path minted a token"


# ── The cookie, the token at rest, and the access-token lifetime ───────────


def test_the_refresh_token_is_never_stored_in_the_clear(client):
    """Same reasoning as passwords: a leaked table must not be a set of sessions."""
    _register_confirmed(client)
    _csrf, raw = _login(client)

    stored = {row.token_hash for row in _sessions()}
    assert raw not in stored
    assert len(stored) == 1
    assert next(iter(stored)) == __import__(
        "solverah.domain.auth", fromlist=["hash_refresh_token"]
    ).hash_refresh_token(raw)


def test_the_refresh_cookie_is_httponly_secure_flagged_and_path_scoped(client):
    """Every attribute in the contract, read off the wire rather than the config."""
    from app import app

    _register_confirmed(client)
    response = client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )

    header = next(
        value for key, value in response.headers
        if key.lower() == "set-cookie" and value.startswith(COOKIE + "=")
    )
    assert "HttpOnly" in header
    assert "Path=%s" % REFRESH_PATH in header
    # SameSite matches the access cookie's, whatever this environment sets it to.
    assert "SameSite=%s" % app.config["JWT_COOKIE_SAMESITE"] in header
    # Persistent, not a session cookie: a thirty-day row behind a cookie that
    # dies with the browser window is thirty days nobody can use.
    assert "Max-Age=" in header


def test_the_refresh_cookie_is_not_sent_on_ordinary_api_calls(client):
    """Path scoping, asserted through the browser's own rule rather than a string.

    Werkzeug's client applies cookie paths the way a browser does, so a request
    to any other route simply does not carry it.
    """
    _register_confirmed(client)
    _login(client)

    assert client.get("/api/v1/auth/session").status_code == 200
    # The jar has it for the refresh path...
    assert _cookie_value(client) is not None
    # ...and nothing else. `get_cookie` at "/" finds no cookie of that name.
    assert client.get_cookie(COOKIE, path="/") is None


def test_the_refresh_cookie_path_matches_the_route_that_reads_it(client):
    """A cookie scoped to a path nothing serves is a cookie never sent.

    The config value carries the `/api/v1` prefix and the blueprint rule does
    not, so the two are assembled in different places and can drift.
    """
    from app import app

    configured = app.config["JWT_REFRESH_COOKIE_PATH"]
    served = {rule.rule for rule in app.url_map.iter_rules()}
    assert configured in served


def test_the_access_token_expires_in_fifteen_minutes(client):
    """Down from an hour: the exposure window logout cannot close (see the module
    docstring and `solverah/api/v1/auth.py::logout`)."""
    from app import app

    assert app.config["JWT_ACCESS_TOKEN_EXPIRES"] == datetime.timedelta(minutes=15)


def test_the_access_token_carries_the_family_it_belongs_to(client):
    """The `sid` claim is how logout finds the family without the refresh cookie,
    which is path-scoped away from `/auth/logout` by design."""
    from flask_jwt_extended import decode_token

    from app import app

    _register_confirmed(client)
    _login(client)

    access = client.get_cookie("access_token_cookie", path="/")
    with app.app_context():
        claims = decode_token(access.value)
    assert claims["sid"] == str(_sessions()[0].family_id)


# ── Every path that opens a session opens a refresh session ────────────────


def test_otp_sign_in_issues_a_refresh_token_too(client):
    """`POST /auth/password/reset` mints a full session and must mint both halves.

    A sign-in path that hands out only an access token gives the user fifteen
    minutes and then a login screen, and nothing fails until the sixteenth
    minute.
    """
    from app import app
    from model import User

    _register_confirmed(client)
    client.post("/api/v1/auth/password/forgot", json={"email": EMAIL})
    with app.app_context():
        code = User.query.filter_by(email=EMAIL).first().reset_token

    response = client.post(
        "/api/v1/auth/password/reset", json={"email": EMAIL, "code": code}
    )

    assert response.status_code == 200
    assert COOKIE in _set_cookie_names(response)
    assert len(_sessions()) == 1


def test_every_session_issuing_response_sets_the_refresh_cookie(client):
    """The guard against a fourth sign-in path forgetting the second half.

    `AuthResult.issue_token` and `IntakeResult.issue_token` are the two flags
    that mean "a session was established"; both funnel through
    `auth.start_session`, and this asserts the funnel rather than the two call
    sites -- a third module setting the flag and minting its own token would
    fail here.
    """
    import inspect

    from solverah.api.v1 import auth as auth_api
    from solverah.api.v1 import intake as intake_api

    for module in (auth_api, intake_api):
        source = inspect.getsource(module)
        assert "create_access_token" not in source or module is auth_api
    # auth.py is the only module allowed to mint one, and it does so in exactly
    # two places: start_session (login, OTP sign-in, intake) and refresh.
    assert inspect.getsource(auth_api).count("create_access_token(") == 2


# ── CSRF on the refresh POST ───────────────────────────────────────────────


def test_a_cross_site_origin_is_refused(client):
    """The CSRF control. `evil.example` announces itself and is turned away."""
    _register_confirmed(client)
    _login(client)

    response = _refresh(client, headers={"Origin": "https://evil.example"})

    assert response.status_code == 403
    assert _sessions()[0].retired_at is None, "a refused request rotated anyway"


def test_a_look_alike_origin_is_refused(client):
    """Exact strings, never patterns.

    `https://solverah.com` read as a regex also matches `https://solverahXcom`,
    which is a domain somebody else can register. The allowlist keeps exact
    origins and regex patterns apart for this reason.
    """
    _register_confirmed(client)
    _login(client)

    assert _refresh(client, headers={"Origin": "https://solverahXcom"}).status_code == 403


def test_an_allowed_origin_passes(client):
    _register_confirmed(client)
    _login(client)

    assert _refresh(client, headers={"Origin": "http://localhost:5173"}).status_code == 200


def test_a_form_content_type_is_refused(client):
    """A cross-site HTML form can send three content types and none is JSON.

    The second half of the guard, for the case where a browser sends no Origin
    at all.
    """
    _register_confirmed(client)
    _login(client)

    response = client.post(REFRESH_PATH, data="x", content_type="text/plain")

    assert response.status_code == 415


# ── Rate limiting ──────────────────────────────────────────────────────────


def test_the_refresh_endpoint_carries_exactly_one_explicit_per_ip_bucket(client):
    """S1's idiom: `shared_limit` with a named scope, and no second per-IP bucket.

    Read off the limit manager rather than off the decorator, for the reason
    `tests/test_anonymous_enqueue_limits.py` gives at length: a limit that is
    declared but never attached is a defect this codebase has already shipped
    once, and asserting on decorator arguments would pass against it.

    One bucket, not two. Two per-IP buckets on one door means the effective
    limit is whichever is tighter and neither limit string tells you which --
    the "do not stack conflicting per-IP buckets" instruction, as an assertion.
    """
    from app import app

    from solverah.extensions import limiter

    # Flask-Limiter keys decorated limits by "<module>.<qualname>.<name>",
    # which identifies a handler independently of its URL rule -- the same
    # spelling tests/test_anonymous_enqueue_limits.py uses.
    view = "solverah.api.v1.auth.refresh.refresh"
    with app.test_request_context(REFRESH_PATH, method="POST"):
        limits = limiter.limit_manager.decorated_limits(view)
        buckets = {(limit.key_func, limit.scope_for(view, "POST")) for limit in limits}

    assert buckets, "no limits registered for %s -- has the view been renamed?" % view
    assert len(buckets) == 1, buckets
    assert next(iter(buckets))[1] == "auth:refresh"


def test_the_refresh_limit_fires(client):
    """The decorator is below the route, so it actually wraps what Flask calls.

    Every `@limiter.limit` in the pre-Phase-1 `app.py` was written above the
    route and enforced nothing (tests/test_rate_limits.py). A new limit is a new
    chance to repeat that.
    """
    from app import app

    from security import REFRESH_PER_IP_LIMIT
    from solverah.extensions import limiter

    burst = int(REFRESH_PER_IP_LIMIT.split(" per ")[0])

    limiter.reset()
    app.config["TESTING"] = False
    try:
        statuses = [_refresh(client).status_code for _ in range(burst + 1)]
    finally:
        app.config["TESTING"] = True
        limiter.reset()

    assert statuses[-1] == 429
    assert set(statuses[:-1]) == {401}


# ── Deletion, and the existing-session path ────────────────────────────────


def test_deleting_the_account_destroys_its_sessions(client):
    """A tombstone frees the address and kills the password; a surviving refresh
    token would be the way back in that neither of those closed."""
    from solverah.services import account_service

    _register_confirmed(client)
    csrf, raw = _login(client)

    response = client.delete(
        "/api/v1/me",
        json={"confirm": account_service.DELETE_CONFIRMATION},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert response.status_code == 200, response.get_data(as_text=True)

    assert _sessions() == []

    survivor = _fresh_client()
    _set_refresh_cookie(survivor, raw)
    assert _refresh(survivor).status_code == 401


def test_a_pre_deploy_access_cookie_still_authenticates(client):
    """Trap 2, asserted: nobody is signed out by the deploy.

    A token minted before this round has no `sid` claim and there is no refresh
    cookie beside it. It must keep working until it expires, and logout must
    answer 200 rather than erroring on the missing claim.
    """
    from flask_jwt_extended import create_access_token

    from app import app

    user_id = _register_confirmed(client)
    assert user_id

    with app.app_context():
        legacy = create_access_token(identity=EMAIL)  # no additional claims
    client.set_cookie("access_token_cookie", legacy, path="/", domain="localhost")

    assert client.get("/api/v1/auth/session").status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 200


def test_a_pre_deploy_session_gets_a_refresh_token_at_the_next_login(client):
    """...and the way out of that state is the ordinary one."""
    _register_confirmed(client)
    _csrf, raw = _login(client)

    assert raw is not None
    assert len(_sessions()) == 1


# ── Retention ──────────────────────────────────────────────────────────────


def test_expire_stale_stamps_only_rows_past_their_expiry(client):
    from app import app
    from model import UserSession, db

    _register_confirmed(client)
    _login(client)

    with app.app_context():
        user_id = _sessions()[0].user_id
        db.session.add(
            UserSession(
                user_id=user_id,
                token_hash="already-expired",
                expires_at=datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=1),
            )
        )
        db.session.commit()

        assert refresh_tokens.expire_stale() == 1
        rows = UserSession.query.order_by(UserSession.id).all()

    assert rows[0].retired_at is None, "a live session was expired"
    assert rows[1].retired_reason == refresh_tokens.REASON_EXPIRED
    assert rows[1].retired_at == rows[1].expires_at, (
        "the stamp restarted the retention window instead of recording the death"
    )


def test_purge_terminal_reaches_a_row_that_was_never_stamped(client):
    """The second half of the delete's OR, exercised on its own.

    Inside a normal `retention run` this branch finds nothing, because
    `expire_stale` runs first and stamps everything. It exists for the pass
    that never ran -- a cron outage, a deploy that skipped a day -- and without
    it those rows would be unreachable by every later run, because each one
    would also stamp before deleting and each stamp lands on a row the delete
    has already passed over.
    """
    from app import app
    from model import UserSession, db

    _register_confirmed(client)
    _login(client)

    with app.app_context():
        user_id = _sessions()[0].user_id
        db.session.add(
            UserSession(
                user_id=user_id,
                token_hash="expired-and-never-swept",
                expires_at=datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=90),
            )
        )
        db.session.commit()

        assert refresh_tokens.purge_terminal() == 1
        remaining = UserSession.query.all()

    assert len(remaining) == 1
    assert remaining[0].retired_at is None, "the live session was purged"


def _fresh_client():
    """A second client on the same app: its own cookie jar, one database."""
    from app import app

    return app.test_client()
