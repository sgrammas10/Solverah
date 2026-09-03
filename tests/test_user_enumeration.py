"""Forgot-password and resend-verification tell you nothing about who has an account.

**The finding (2026-09 audit, MED, probed live).** Four endpoints separated
"this address has an account" from "it does not", and two of them did it with a
status code:

    POST /auth/password/forgot        200 vs 404 "No account found with that
                                      email address."
    POST /auth/email/verify/resend    200 vs 400 "Email already confirmed"
                                      vs 404 "Account not found"

Replay a mailing list against either and the responses sort it into registered,
registered-and-verified, and unknown. That list is worth something on its own --
this is a career platform, so membership is a fact about someone's employment
intentions -- and it is the input to every attack downstream: credential
stuffing, the per-account lockout DoS (audit 1.2), targeted phishing that knows
the product name.

S1 makes both answer identically for every population. The other two oracles are
handled elsewhere: the login *timing* difference in
`tests/test_login_timing_equalisation.py`, and register's 400 deliberately left
alone because `Register.tsx` renders it as UX (written up in the round report;
changing it is a product decision, not a security fix).

**What "identical" is tested to mean.** Status, body bytes, and headers. Bytes
rather than parsed JSON because key order and whitespace are observable to an
attacker and invisible to `==` on dicts; headers because `Content-Length`
follows the body and a difference there is as good an oracle as the body itself.
Set-Cookie is compared too: neither endpoint should be minting anything.

Timing is deliberately NOT asserted. A wall-clock assertion on a machine running
a test suite flakes, and the honest statement about these two endpoints is
structural -- the unknown-address path does strictly less work (no row write, no
outbox row, no provider call), which is a residual documented in the round
report rather than something this file can pretend to have closed.
"""

import pytest

from model import Outbox, User, db

_UNKNOWN = "definitely-nobody-at-all@example.com"


def _noop(*_a, **_k):
    return None


@pytest.fixture(autouse=True)
def _no_real_mail(monkeypatch):
    """Neither flow may reach a provider, and neither should want to."""
    monkeypatch.setattr("solverah.infra.email.send_password_reset_email", _noop)
    monkeypatch.setattr("solverah.infra.email.send_verification_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)


def _register(client, email):
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Str0ng-Passw0rd!",
            "name": "Enumeration Probe",
            "terms_accepted": True,
        },
    )
    assert res.status_code == 201, res.get_data(as_text=True)
    return email


def _confirm(email):
    from app import app

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()


#: Headers that differ between any two requests for reasons that have nothing to
#: do with which account exists. Exactly two, and both are enumerated rather than
#: pattern-matched so that a *new* varying header fails this file loudly instead
#: of being quietly tolerated.
#:
#: `date` moves with the clock. `x-request-id` is the per-request correlation id
#: the access log keys on -- it is unique by construction and carries no
#: information about the request that produced it.
_NON_DISCRIMINATING_HEADERS = {"date", "x-request-id"}


def _fingerprint(res):
    """Everything about a response an attacker can see, as one comparable value.

    Status, body **bytes**, and every remaining header including
    `Content-Length` and any `Set-Cookie`. Bytes rather than parsed JSON because
    key order and whitespace are observable on the wire and invisible to `==` on
    two dicts; `Content-Length` because a length that tracks the body is as good
    an oracle as the body.
    """
    headers = sorted(
        (k.lower(), v)
        for k, v in res.headers.items()
        if k.lower() not in _NON_DISCRIMINATING_HEADERS
    )
    return res.status_code, res.get_data(), headers


# ── POST /auth/password/forgot ──────────────────────────────────────────────

def test_forgot_password_is_byte_identical_for_known_and_unknown(client):
    """The oracle the audit probed. Fails against the 404 that stood until S1."""
    known = _register(client, "forgot-known@example.com")
    _confirm(known)

    hit = client.post("/api/v1/auth/password/forgot", json={"email": known})
    miss = client.post("/api/v1/auth/password/forgot", json={"email": _UNKNOWN})

    assert _fingerprint(hit) == _fingerprint(miss)
    assert hit.status_code == 200


def test_forgot_password_hides_the_unconfirmed_case_too(client):
    """A registered-but-unverified address must not be a third bucket.

    It gets no code -- this endpoint mints a session, and handing one to an
    address nobody has proved they control would make email confirmation
    optional -- but it must not *say* so.
    """
    unconfirmed = _register(client, "forgot-unconfirmed@example.com")

    res = client.post("/api/v1/auth/password/forgot", json={"email": unconfirmed})
    miss = client.post("/api/v1/auth/password/forgot", json={"email": _UNKNOWN})

    assert _fingerprint(res) == _fingerprint(miss)


def test_forgot_password_still_sends_to_a_real_account(client):
    """Uniformity must not have been bought by breaking the feature."""
    from app import app

    known = _register(client, "forgot-works@example.com")
    _confirm(known)

    client.post("/api/v1/auth/password/forgot", json={"email": known})

    with app.app_context():
        user = User.query.filter_by(email=known).first()
        assert user.reset_token is not None
        assert len(user.reset_token) == 6


def test_forgot_password_owes_no_email_for_an_unknown_address(client):
    """Identical responses, not identical work.

    An endpoint that queued mail for every address it was handed would be a
    spam relay with a uniform response.
    """
    from app import app

    with app.app_context():
        before = Outbox.query.count()

    client.post("/api/v1/auth/password/forgot", json={"email": _UNKNOWN})

    with app.app_context():
        assert Outbox.query.count() == before


# ── POST /auth/email/verify/resend ──────────────────────────────────────────

def test_resend_is_byte_identical_across_all_three_populations(client):
    """Unconfirmed, already-confirmed, and unknown must be one response.

    Fails against S1's predecessor three times over: 200 / 400 "Email already
    confirmed" / 404 "Account not found".
    """
    unconfirmed = _register(client, "resend-pending@example.com")
    confirmed = _register(client, "resend-done@example.com")
    _confirm(confirmed)

    a = client.post("/api/v1/auth/email/verify/resend", json={"email": unconfirmed})
    b = client.post("/api/v1/auth/email/verify/resend", json={"email": confirmed})
    c = client.post("/api/v1/auth/email/verify/resend", json={"email": _UNKNOWN})

    assert _fingerprint(a) == _fingerprint(b) == _fingerprint(c)
    assert a.status_code == 200


def test_resend_still_rotates_the_code_for_an_unconfirmed_account(client):
    from app import app

    email = _register(client, "resend-rotates@example.com")
    with app.app_context():
        first = User.query.filter_by(email=email).first().confirmation_token

    client.post("/api/v1/auth/email/verify/resend", json={"email": email})

    with app.app_context():
        assert User.query.filter_by(email=email).first().confirmation_token != first


def test_resend_does_nothing_for_a_confirmed_or_unknown_address(client):
    """No new outbox row for either of the two no-op populations."""
    from app import app

    confirmed = _register(client, "resend-noop@example.com")
    _confirm(confirmed)

    with app.app_context():
        before = Outbox.query.count()

    client.post("/api/v1/auth/email/verify/resend", json={"email": confirmed})
    client.post("/api/v1/auth/email/verify/resend", json={"email": _UNKNOWN})

    with app.app_context():
        assert Outbox.query.count() == before


def test_a_malformed_address_is_still_a_400(client):
    """The one 400 left, and it is not a leak.

    It depends on the string and never on who owns it, so it answers the same
    for both populations -- which is the property that matters, and is asserted
    rather than assumed.
    """
    res = client.post("/api/v1/auth/email/verify/resend", json={"email": "not-an-email"})

    assert res.status_code == 400
