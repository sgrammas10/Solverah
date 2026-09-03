"""A login against an address that has no account costs what a real one costs.

**The finding (2026-09 audit, MED, probed live).** `auth_service.login` reads

    if not user or not check_password(user.password_hash, password):

and Python short-circuits `or`. An address with no account therefore answered
`401 Invalid credentials` without bcrypt ever running; an address with an account
and the wrong password answered the *same* 401, several tens of milliseconds
later, because bcrypt at cost 12 is deliberately slow. The bodies matched. The
clock did not, and the clock is enough: enumerating a mailing list off a timing
difference is slower than off a status code, not harder. It is the same oracle
`tests/test_user_enumeration.py` closes on forgot/resend, arriving by a different
channel.

**Why this file asserts the code path and not the clock.** A wall-clock
assertion -- "the miss took at least 80% as long as the hit" -- would be
measuring a bcrypt round on a machine that is also running Postgres, a test
suite, and whatever else. It flakes, and a flaky security test gets marked xfail
and then deleted. The property that actually matters is discrete and exactly
observable: *did the unknown-account branch perform a bcrypt verification?* So
`check_password` is replaced with a recorder and the calls are counted.

The equaliser hashes a fixed dummy digest rather than the submitted password,
which is what makes the cost constant: bcrypt's work factor is carried by the
*digest*, not by the candidate, so an attacker cannot vary the cost by varying
what they send.
"""

import pytest

from solverah.domain import auth as domain
from solverah.services import auth_service

_PASSWORD = "Str0ng-Passw0rd!"


def _noop(*_a, **_k):
    return None


class _Recorder:
    """Stands in for `bcrypt.check_password_hash`, remembering what it was asked.

    Answers True only for the exact (hash, password) pair it was seeded with, so
    it is a working password checker and not merely a spy -- a login that should
    succeed still succeeds through it.
    """

    def __init__(self, real_hash=None, real_password=None):
        self.calls = []
        self._real = (real_hash, real_password)

    def __call__(self, pw_hash, password):
        self.calls.append((pw_hash, password))
        return (pw_hash, password) == self._real and pw_hash is not None

    @property
    def hashes_seen(self):
        return [h for h, _ in self.calls]


@pytest.fixture(autouse=True)
def _no_side_effects(monkeypatch):
    monkeypatch.setattr("solverah.infra.email.send_verification_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)


@pytest.fixture()
def app_ctx(client):
    """An application context over the `client` fixture's schema.

    These tests call `auth_service.login` directly rather than through the
    route, because the route supplies the real `bcrypt.check_password_hash` and
    the whole method here is to substitute it. Calling the service still needs
    a context (it reads the session) and a database (it looks the user up), and
    `client` is what builds and tears down the schema -- so this depends on it
    rather than re-implementing that.
    """
    from app import app

    with app.app_context():
        yield app


def _register(client, email):
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": _PASSWORD,
            "name": "Timing Probe",
            "terms_accepted": True,
        },
    )
    assert res.status_code == 201, res.get_data(as_text=True)


def _login(email, password, check_password):
    """Call the service directly -- the route would supply the real bcrypt."""
    return auth_service.login(
        email=email,
        password=password,
        check_password=check_password,
        wp_v2_completed=lambda _uid: False,
    )


def test_an_unknown_account_still_verifies_a_password_hash(app_ctx):
    """The finding, stated as the thing that was missing.

    Fails against the pre-S1 short-circuit, where `check_password` was never
    called at all on this branch and `calls` comes back empty.
    """
    recorder = _Recorder()

    result = _login("no-such-person@example.com", _PASSWORD, recorder)

    assert result.status == 401
    assert len(recorder.calls) == 1


def test_the_hash_it_verifies_is_the_dummy_and_not_a_real_one(app_ctx):
    """Which digest is used is the whole safety argument.

    `TIMING_EQUALISER_HASH` has no known plaintext, so no candidate can match
    it: the branch spends the time without ever being able to authenticate
    anyone. Verifying some *real* user's hash here would equalise the clock and
    open a far worse hole.
    """
    recorder = _Recorder()

    _login("no-such-person@example.com", _PASSWORD, recorder)

    assert recorder.hashes_seen == [domain.TIMING_EQUALISER_HASH]


def test_the_dummy_hash_can_never_match(app_ctx):
    """Not a weak password -- not a password. Checked against real bcrypt."""
    from solverah.extensions import bcrypt

    for candidate in ("", _PASSWORD, domain.TIMING_EQUALISER_HASH, "password"):
        assert bcrypt.check_password_hash(domain.TIMING_EQUALISER_HASH, candidate) is False


def test_the_dummy_hash_carries_the_cost_the_real_ones_carry(app_ctx):
    """Equal work means equal *cost factor*; a cheaper dummy re-opens the gap.

    Read off a freshly minted hash rather than hard-coded, so overriding
    `BCRYPT_LOG_ROUNDS` fails this test instead of silently reintroducing the
    oracle.
    """
    from solverah.extensions import bcrypt

    minted = bcrypt.generate_password_hash(_PASSWORD).decode()

    assert domain.TIMING_EQUALISER_HASH.split("$")[:3] == minted.split("$")[:3]


def test_a_known_account_with_a_wrong_password_does_the_same_amount_of_work(client, app_ctx):
    """One bcrypt verification on each branch -- the equality being bought."""
    _register(client, "timing-known@example.com")

    miss = _Recorder()
    _login("nobody-at-all@example.com", "whatever", miss)

    wrong = _Recorder()
    result = _login("timing-known@example.com", "wrong-password", wrong)

    assert result.status == 401
    assert len(miss.calls) == len(wrong.calls) == 1


def test_a_correct_password_still_logs_in(client, app_ctx):
    """The equaliser must not have cost the feature.

    It runs only on the `user is None` branch, so a real login sees exactly one
    verification -- against its own hash, not the dummy.
    """
    from app import app
    from model import User, db

    _register(client, "timing-works@example.com")
    with app.app_context():
        user = User.query.filter_by(email="timing-works@example.com").first()
        user.email_confirmed = True
        real_hash = user.password_hash
        db.session.commit()

    recorder = _Recorder(real_hash, _PASSWORD)
    result = _login("timing-works@example.com", _PASSWORD, recorder)

    assert result.status == 200
    assert recorder.hashes_seen == [real_hash]
    assert domain.TIMING_EQUALISER_HASH not in recorder.hashes_seen
