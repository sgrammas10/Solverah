"""``POST /intake/claims`` -- the four account-attachment endpoints, collapsed.

The four were `/intake/create-account`, `/intake/sign-in`, `/intake/link-account`
and `/intake/save-to-account`. What has to survive the collapse:

* each mode still does what its endpoint did, and returns what it returned;
* two modes stay public and two stay authenticated, since `@jwt_required()` had
  to come off the route to allow the first pair -- exactly the kind of change
  that drops CSRF protection silently;
* the four rate-limit buckets stay four, and keep their two different numbers.

The security property worth stating out loud: a submission id is the *only*
thing protecting an anonymous submission, so the modes that consume one must not
let the claim body redirect where it lands.
"""

import re
import uuid

import pytest

PASSWORD = "Strongpass1!"
SUBMITTER = "claimed-submission@example.com"


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture(autouse=True)
def _no_mail(monkeypatch):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)


def _seed_submission(email=SUBMITTER, first="Claim", last="Tester"):
    """An anonymous submission sitting in the funnel, waiting to be claimed."""
    from app import app
    from model import IntakeSubmission, db

    submission_id = str(uuid.uuid4())
    with app.app_context():
        db.session.add(IntakeSubmission(
            id=submission_id, first_name=first, last_name=last, email=email,
            state="NY", resume_key="intake/%s/resume.pdf" % submission_id,
            resume_mime="application/pdf", resume_size_bytes=1024,
        ))
        db.session.commit()
    return submission_id


def _register_and_login(client, email, name="Existing User"):
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "name": name,
              "role": "job-seeker", "terms_accepted": True},
    )

    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


def _claim(client, body, csrf=None):
    headers = {"X-CSRF-TOKEN": csrf} if csrf else {}
    return client.post("/api/v1/intake/claims", json=body, headers=headers)


# ── mode: register ──────────────────────────────────────────────────────────


def test_register_creates_an_account_from_a_submission(client):
    submission_id = _seed_submission()

    resp = _claim(client, {
        "mode": "register", "submission_id": submission_id, "password": PASSWORD,
    })

    assert resp.status_code == 201
    assert resp.get_json()["user"]["email"] == SUBMITTER


def test_register_takes_the_email_from_the_submission_not_the_body(client):
    """A guessed submission id must not become an account under any address."""
    submission_id = _seed_submission()

    _claim(client, {
        "mode": "register", "submission_id": submission_id, "password": PASSWORD,
        "email": "attacker@example.com",
    })

    from app import app
    from model import User

    with app.app_context():
        assert User.query.filter_by(email="attacker@example.com").first() is None
        assert User.query.filter_by(email=SUBMITTER).first() is not None


def test_register_refuses_a_submission_that_already_has_an_account(client):
    submission_id = _seed_submission()
    _register_and_login(client, SUBMITTER)

    resp = _claim(client, {
        "mode": "register", "submission_id": submission_id, "password": PASSWORD,
    })

    assert resp.status_code == 400


def test_register_refuses_an_unknown_submission(client):
    resp = _claim(client, {
        "mode": "register", "submission_id": str(uuid.uuid4()), "password": PASSWORD,
    })

    assert resp.status_code == 404


def test_register_needs_no_jwt(client):
    """It is how a visitor gets one; requiring one would be circular."""
    submission_id = _seed_submission()

    assert _claim(client, {
        "mode": "register", "submission_id": submission_id, "password": PASSWORD,
    }).status_code == 201


# ── mode: register -- the verification code it issues (G9) ──────────────────
#
# Walked live on production 2026-09-15: this path minted `uuid.uuid4().hex`
# while /register minted a 6-digit code, and the difference was invisible at
# the API layer -- `/auth/email/verify` compares `confirmation_token` as text,
# so both "worked". What did not work was the human in the middle: the email
# template labels the value a "6-digit code" and carries no link, and
# /verify-email strips non-digits and caps the field at six characters, so a
# 32-hex token could not be entered at all. The format is the contract here,
# and these tests pin it: the shape that is mailed, that the shape mailed is
# the shape the endpoint accepts, and that it ages out on /register's clock.


def _confirmation_token(email=SUBMITTER):
    """The code sitting on the account, read straight from the row."""
    from app import app
    from model import User

    with app.app_context():
        return User.query.filter_by(email=email).first().confirmation_token


def test_register_issues_a_six_digit_numeric_code(client) -> None:
    """Not `uuid4().hex`: the inbox and the code-entry screen both assume six digits."""
    submission_id = _seed_submission()

    assert _claim(client, {
        "mode": "register", "submission_id": submission_id, "password": PASSWORD,
    }).status_code == 201

    code = _confirmation_token()
    assert re.fullmatch(r"\d{6}", code), (
        "confirmation_token is %r; /verify-email accepts only six digits" % (code,)
    )


#: What `ConfirmEmail`'s input does to whatever is typed into it:
#: `e.target.value.replace(/\D/g, '').slice(0, 6)` (ConfirmEmail.tsx:126),
#: behind a `maxLength={6}`. Mirrored here rather than described, because the
#: whole of G9 lives in the gap between what the endpoint accepts and what this
#: field can deliver to it -- a round trip that posts the raw column value
#: passes against the defect and proves nothing.
def _as_the_verification_field_would_send_it(typed: str) -> str:
    return re.sub(r"\D", "", typed)[:6]


def test_register_code_verifies_through_the_email_verify_endpoint(client) -> None:
    """The whole round trip, through the only field a user can type it into.

    Not the raw column: `/auth/email/verify` compares `confirmation_token` as
    text and accepted the 32-hex value happily, which is exactly why the defect
    survived to production. The code is put through the SPA's own sanitiser
    first, so this asserts the property that actually failed -- that what was
    mailed can be entered and confirms the account.
    """
    submission_id = _seed_submission()
    _claim(client, {
        "mode": "register", "submission_id": submission_id, "password": PASSWORD,
    })
    code = _as_the_verification_field_would_send_it(_confirmation_token())

    resp = client.post(
        "/api/v1/auth/email/verify", json={"email": SUBMITTER, "code": code}
    )

    assert resp.status_code == 200, resp.get_json()

    from app import app
    from model import User

    with app.app_context():
        user = User.query.filter_by(email=SUBMITTER).first()
        assert user.email_confirmed is True
        assert user.confirmation_token is None


def test_register_code_expires_on_the_same_clock_as_register(client) -> None:
    """Expiry parity with /register, which is what `confirmation_sent_at` buys.

    `confirm_email` reads that column through `is_code_expired` and never looks
    at the token's format, so the two paths were already identical here -- this
    holds that true now that they also share a generator.
    """
    import datetime

    submission_id = _seed_submission()
    _claim(client, {
        "mode": "register", "submission_id": submission_id, "password": PASSWORD,
    })

    from app import app
    from model import User, db
    from solverah.domain import auth as auth_domain

    with app.app_context():
        user = User.query.filter_by(email=SUBMITTER).first()
        code = user.confirmation_token
        user.confirmation_sent_at = auth_domain.utcnow() - datetime.timedelta(
            minutes=auth_domain.code_expiry_minutes() + 1
        )
        db.session.commit()

    resp = client.post(
        "/api/v1/auth/email/verify", json={"email": SUBMITTER, "code": code}
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"] == "code expired"


# ── mode: sign_in ───────────────────────────────────────────────────────────


def test_sign_in_attaches_a_submission_and_issues_a_session(client):
    submission_id = _seed_submission()
    _register_and_login(client, SUBMITTER)

    resp = _claim(client, {
        "mode": "sign_in", "submission_id": submission_id,
        "email": SUBMITTER, "password": PASSWORD,
    })

    assert resp.status_code == 200
    assert resp.get_json()["csrfToken"]


def test_sign_in_refuses_an_email_that_does_not_match_the_submission(client):
    """Otherwise a guessed id attaches someone else's resume to your account."""
    submission_id = _seed_submission()
    _register_and_login(client, "someone-else@example.com")

    resp = _claim(client, {
        "mode": "sign_in", "submission_id": submission_id,
        "email": "someone-else@example.com", "password": PASSWORD,
    })

    assert resp.status_code == 400


def test_sign_in_refuses_a_wrong_password(client):
    submission_id = _seed_submission()
    _register_and_login(client, SUBMITTER)

    resp = _claim(client, {
        "mode": "sign_in", "submission_id": submission_id,
        "email": SUBMITTER, "password": "WrongPassword1!",
    })

    assert resp.status_code == 401


# ── mode: session ───────────────────────────────────────────────────────────


SESSION_BODY = {
    "mode": "session",
    "selected_statement_ids": ["dir-1", "sus-2"],
    "wpll_answers": [
        {"question_id": "wpll-q%d" % i, "option_id": "wpll-q%d-c" % i}
        for i in range(1, 6)
    ],
    "wpll_insight_text": "Test insight text.",
}


def test_session_adopts_an_anonymous_quiz_session(client):
    """The mode with no submission behind it at all."""
    csrf = _register_and_login(client, "session-claim@example.com")

    resp = _claim(client, SESSION_BODY, csrf)

    assert resp.status_code == 200
    assert resp.get_json()["wpll_completed"] is True


def test_session_requires_a_jwt(client):
    assert _claim(client, SESSION_BODY).status_code == 401


def test_session_requires_csrf(client):
    """`verify_jwt_in_request()` does the check `@jwt_required()` used to."""
    _register_and_login(client, "session-csrf@example.com")

    assert _claim(client, SESSION_BODY).status_code == 401


def test_session_caps_the_number_of_answers(client):
    csrf = _register_and_login(client, "session-cap@example.com")
    body = dict(SESSION_BODY)
    body["wpll_answers"] = [
        {"question_id": "q%d" % i, "option_id": "a"} for i in range(9)
    ]

    assert _claim(client, body, csrf).status_code == 400


# ── The discriminator ───────────────────────────────────────────────────────


def test_a_missing_mode_names_the_field_it_is_missing(client):
    resp = _claim(client, {"submission_id": str(uuid.uuid4())})

    assert resp.status_code == 422
    assert resp.get_json()["errors"][0]["field"] == "mode"


def test_an_unrecognised_mode_names_the_alternatives(client):
    """The reason an envelope model is the fallback rather than one of the four.

    Validating an unknown mode against a concrete mode's model would report
    every field of an arbitrarily chosen shape as missing, which tells the
    client nothing about what actually went wrong.
    """
    resp = _claim(client, {"mode": "teleport"})

    assert resp.status_code == 422
    error = resp.get_json()["errors"][0]
    assert error["field"] == "mode"
    assert error["code"] == "literal_error"


def test_the_body_is_enforced_against_the_mode_not_the_union(client):
    """A sign-in body must not be accepted as a registration."""
    resp = _claim(client, {"mode": "register", "email": SUBMITTER, "password": PASSWORD})

    assert resp.status_code == 422
    assert "submission_id" in {e["field"] for e in resp.get_json()["errors"]}


# ── Rate limiting: one route, still four budgets ────────────────────────────


@pytest.fixture()
def enforcing(client):
    from app import app
    from solverah.extensions import limiter

    limiter.reset()
    app.config["TESTING"] = False
    try:
        yield client
    finally:
        app.config["TESTING"] = True
        limiter.reset()


def test_each_mode_gets_its_own_rate_limit_bucket(enforcing):
    """Four handlers were four buckets; one handler is one unless the mode is keyed.

    Without this, an attacker probing `sign_in` would consume the budget of the
    mode that creates accounts.
    """
    for _ in range(6):
        spent = _claim(enforcing, {
            "mode": "sign_in", "submission_id": str(uuid.uuid4()),
            "email": "nobody@example.com", "password": PASSWORD,
        })
    assert spent.status_code == 429

    other = _claim(enforcing, {
        "mode": "register", "submission_id": str(uuid.uuid4()), "password": PASSWORD,
    })

    assert other.status_code != 429


def test_an_unrecognised_mode_declares_the_strictest_limit(enforcing):
    """The limit a bad mode would be charged, if it ever reached the bucket.

    It does not, and that is deliberate rather than a gap -- see
    tests/test_request_validation.py. A request refused for being malformed is
    never charged to its endpoint's bucket, because charging it would let a
    stranger on a shared NAT gateway spend a real user's allowance with garbage.

    What is asserted here is the fallback itself: a mode nobody recognises is
    mapped to the strictest of the four rather than to no limit at all, so the
    day a malformed request does reach the bucket it lands in the tightest one.
    """
    from solverah.api.v1.intake import _claim_limit
    from solverah.schemas.intake import CLAIM_LIMITS, STRICTEST_CLAIM_LIMIT
    from app import app

    with app.test_request_context("/api/v1/intake/claims", method="POST",
                                  json={"mode": "teleport"}):
        assert _claim_limit() == STRICTEST_CLAIM_LIMIT

    assert STRICTEST_CLAIM_LIMIT == min(CLAIM_LIMITS.values(), key=_per_minute)


def _per_minute(limit_string):
    """Requests-per-minute in a "N per minute" string, for comparing limits."""
    return int(limit_string.split(" ", 1)[0])
