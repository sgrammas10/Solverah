"""P0-1: two concurrent profile writers must both survive.

This is the defect Phase 2a exists to fix, and it is the only thing in the phase
that decomposition does not fix on its own.  Splitting ``experience`` into rows
stops two writers from clobbering each other's *lists*; it does nothing about
two writers touching two scalar fields, because those still land in one row --
``profiles.extra`` for the unpromoted keys, ``profiles.*`` for the promoted ones.
``profiles.version`` is what closes that, and this file is what proves it.

The interleaving being forced
-----------------------------
::

    T1  read blob         -> {"summary": "original"}
    T2  read blob         -> {"summary": "original"}          <- same snapshot
    T1  write {"summary": "original", "phone": "555"}   commit
    T2  write {"summary": "original", "linkedinUrl": ...} commit

Under a read-modify-write of one JSON column the second commit rewrites the whole
column from a snapshot taken before the first one landed, so ``phone`` is gone
and nothing anywhere reports an error.  That is a lost update, and it is silent.

The barrier is placed inside ``merge_profile`` rather than around the service
call because that is the one point guaranteed to sit *after* the read and
*before* the write.  Sleeping instead would make this a race that usually
reproduces, which is not the same thing as a test.

Each thread gates exactly once (``_local.gated``).  A retrying implementation
calls ``merge_profile`` again on its second attempt, and that call must not
block on a barrier the other thread has already left.
"""

import threading

import pytest

EMAIL = "profile-race@example.com"
PASSWORD = "Strongpass1!"

#: Generous. It bounds a hang, it does not pace the test -- both threads reach
#: the barrier in milliseconds or the interleaving never happened at all.
BARRIER_TIMEOUT_SECONDS = 30


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture()
def race_user(client, monkeypatch):
    """A registered, confirmed user with a known starting profile."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)

    client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "name": "Race User",
              "role": "job-seeker", "terms_accepted": True},
    )

    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        user.email_confirmed = True
        db.session.commit()

    from solverah.services import profile_service
    from validators import clean_profile_data

    # ``test_request_context`` rather than ``app_context``: the profile save
    # writes an AuditLog row, and ``audit.log_audit_event`` reads the client IP
    # and user agent off ``flask.request``. Stubbing the audit write instead
    # would remove an INSERT from the very transaction whose interleaving is
    # under test.
    with app.test_request_context():
        user = User.query.filter_by(email=EMAIL).first()
        profile_service.save_profile(
            user, {"summary": "original"}, clean_profile_data
        )

    return EMAIL


def _run_two_writers(payload_one, payload_two):
    """Run two profile saves whose reads both precede either write.

    Returns ``(profile_document, errors)`` -- the document as the API would
    serve it after both writers have committed, and anything either thread
    raised.
    """
    from app import app
    from model import User
    from solverah.domain import profile as domain
    from solverah.services import profile_service
    from validators import clean_profile_data

    gate = threading.Barrier(2, timeout=BARRIER_TIMEOUT_SECONDS)
    local = threading.local()
    real_merge = domain.merge_profile

    def merge_after_both_have_read(existing, incoming):
        # First call per thread only: by the time a thread reaches the merge it
        # has already read the stored profile, so releasing both threads here
        # hands each one the other's pre-write snapshot. Retries fall straight
        # through -- see the module docstring.
        if not getattr(local, "gated", False):
            local.gated = True
            gate.wait()
        return real_merge(existing, incoming)

    errors = []

    def writer(payload):
        try:
            # Its own request context, therefore its own SQLAlchemy session
            # and its own connection. Two writers sharing a session would not be
            # two writers.
            with app.test_request_context():
                user = User.query.filter_by(email=EMAIL).first()
                profile_service.save_profile(user, payload, clean_profile_data)
        except Exception as exc:  # noqa: BLE001 -- reported, not swallowed
            errors.append(exc)
            gate.abort()

    original = profile_service.domain.merge_profile
    profile_service.domain.merge_profile = merge_after_both_have_read
    try:
        threads = [
            threading.Thread(target=writer, args=(payload_one,)),
            threading.Thread(target=writer, args=(payload_two,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=BARRIER_TIMEOUT_SECONDS + 15)
            assert not thread.is_alive(), "a writer never finished"
    finally:
        profile_service.domain.merge_profile = original

    with app.test_request_context():
        user = User.query.filter_by(email=EMAIL).first()
        document = profile_service.read_profile_document(user).body["profile"]

    return document, errors


def test_concurrent_writers_to_different_fields_both_survive(race_user):
    """The P0-1 fix, stated as the thing that used to be false.

    Neither writer touches the other's field. There is no conflict to resolve
    and no ambiguity about the intended outcome: both edits are meant to be
    there afterwards, and before Phase 2a exactly one of them was.
    """
    document, errors = _run_two_writers(
        {"phone": "555-0100"},
        {"linkedinUrl": "https://example.com/in/race"},
    )

    assert errors == [], "writers raised: %r" % errors
    assert document.get("phone") == "555-0100", (
        "the phone write was lost: %r" % document
    )
    assert document.get("linkedinUrl") == "https://example.com/in/race", (
        "the linkedinUrl write was lost: %r" % document
    )


def test_concurrent_writers_do_not_lose_the_untouched_fields(race_user):
    """A field neither writer sent survives both writes."""
    document, errors = _run_two_writers(
        {"phone": "555-0101"},
        {"linkedinUrl": "https://example.com/in/race2"},
    )

    assert errors == []
    assert document.get("summary") == "original"


def test_concurrent_list_writers_both_survive(race_user):
    """The same race across two decomposed collections rather than two scalars.

    ``experience`` and ``skills`` become rows in Phase 2a, so this pair would
    pass on row-level storage alone. It is here so the two cases are covered by
    two tests rather than one -- if a later change fixes the lists and regresses
    the scalars, the pair says which.
    """
    document, errors = _run_two_writers(
        {"experience": [{"company": "Acme", "position": "Engineer"}]},
        {"skills": ["Python"]},
    )

    assert errors == []
    assert document.get("experience") == [{"company": "Acme", "position": "Engineer"}]
    assert document.get("skills") == ["Python"]
