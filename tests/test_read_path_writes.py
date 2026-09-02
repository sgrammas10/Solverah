"""``GET`` handlers do not commit. P0-3's server half, asserted rather than hoped for.

The defect: ``GET /api/profile`` appended an ``AuditLog`` row and called
``db.session.commit()`` on every read, and ``GET /company-lens/matches`` committed
a profile backfill mid-read.  Both take a write lock on a request that ought to
be servable from a replica, and the first sat on the app-boot path.

Phase 1b moved session restore off that endpoint; Phase 3 removes the writes.

**Why this file exists separately from the endpoint tests.**  A test that asserts
a response body cannot see a commit, and a test that counts rows afterwards
cannot tell *which transaction* wrote them -- the audit row still appears after
``GET /me/profile``, it is just written by a worker.  So these two questions need
two different instruments, and only the second one is here:

* "Did the row eventually appear?" -- ``tests/test_me_api.py``, by counting.
* "Did *this request* write it?" -- here, by counting commits on the request's
  own session.

**Eager mode does not weaken this.**  Queued work runs inline under
``APP_ENV=testing``, so the audit task really does execute during the request --
which is exactly why the check is on ``db.session`` and not on the table.  The
task writes through ``db.engine.begin()``, its own connection and its own
transaction, so a commit it makes is not a commit on the session under test.  If
someone rewrites the task to use ``db.session``, the two become one and these
tests fail.  That is the point of them.

**The regression this guards against is silent.**  A write that reappears on a
read path costs latency and replica-routing, not correctness, so nothing else in
the suite would ever go red.
"""

import pytest

EMAIL = "read-path@example.test"
PASSWORD = "Strongpass1!"


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture()
def auth(client, monkeypatch):
    """A confirmed, logged-in account. Returns its CSRF token."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "name": "Read Path",
              "role": "job-seeker", "terms_accepted": True},
    )

    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


@pytest.fixture()
def commits():
    """Count commits on the request's scoped session, and only that session.

    Patched on the ``scoped_session`` object rather than on the ``Session``
    class, so a task opening its own connection through ``db.engine.begin()`` is
    invisible here -- which is the distinction being measured.
    """
    from model import db

    counter = {"n": 0}
    original = db.session.commit

    def _counted(*args, **kwargs):
        counter["n"] += 1
        return original(*args, **kwargs)

    db.session.commit = _counted
    try:
        yield counter
    finally:
        db.session.commit = original


#: Every ``GET`` a signed-in client can reach that used to, or could plausibly,
#: write. ``/me/matches`` answers 400 here (no culture preferences) and
#: ``/me/path-suggestions`` a 404 (an unwarmed cache, since 3c) and that is
#: fine -- the question is whether they committed on the way to the answer,
#: and the branch that used to commit is the one an error passes through.
READ_PATHS = [
    "/api/v1/me",
    "/api/v1/me/profile",
    "/api/v1/me/dashboard",
    "/api/v1/me/skills",
    "/api/v1/me/export",
    "/api/v1/auth/session",
    "/api/v1/assessments",
    "/api/v1/companies",
    "/api/v1/me/matches",
    "/api/v1/me/path-preferences",
    "/api/v1/me/path-suggestions",
    "/api/v1/me/recommendations",
]


@pytest.mark.parametrize("path", READ_PATHS)
def test_a_get_does_not_commit(client, auth, commits, path):
    """The whole file in one assertion, once per read path."""
    resp = client.get(path)

    assert resp.status_code < 500, "%s could not run at all" % path
    assert commits["n"] == 0, "%s committed %d time(s)" % (path, commits["n"])


def test_the_commit_counter_actually_counts(client, auth, commits):
    """Guards the test above from passing because the instrument is broken.

    Without this, a ``commits`` fixture that patched the wrong object would make
    every case above pass unconditionally.
    """
    resp = client.patch(
        "/api/v1/me", json={"name": "Renamed"}, headers={"X-CSRF-TOKEN": auth}
    )

    assert resp.status_code == 200
    assert commits["n"] >= 1


def test_reading_the_profile_document_still_records_the_read(client, auth):
    """Removing the write must not remove the audit trail.

    The row is written by a worker now -- inline under eager execution, on the
    ``maintenance`` queue in production -- so it still lands. What changed is the
    transaction it lands in, which is what the parametrised test above measures.
    """
    from app import app
    from model import AuditLog

    def _reads():
        with app.app_context():
            return (
                AuditLog.query.filter_by(action="read", resource="profile")
                .order_by(AuditLog.id)
                .all()
            )

    before = len(_reads())
    client.get(
        "/api/v1/me/profile", headers={"User-Agent": "read-path-probe/1.0"}
    )
    rows = _reads()

    assert len(rows) == before + 1

    # The whole row, not just its existence. The worker writes through a Core
    # INSERT rather than the ORM, so a column that stopped being populated -- the
    # request-scoped ones especially, which the worker cannot re-derive and has to
    # be handed -- would leave a row that counts and says nothing.
    written = rows[-1]
    assert written.user_agent == "read-path-probe/1.0"
    assert written.ip_address == "127.0.0.1"
    assert written.actor_user_id is not None
    assert written.event_metadata == {"target_user_id": written.actor_user_id}


def test_the_matches_read_derives_culture_preferences_without_persisting(client, auth):
    """``resolve_culture_preferences`` committed a backfill inside a GET.

    It still derives the vector -- the response is unchanged and a user with Work
    Pulse answers still gets matches -- but the profile document is not written.
    Persisting is ``matching_service.backfill_culture_preferences``, on the
    maintenance queue.
    """
    from app import app
    from model import User, db
    from solverah.domain import auth as auth_domain
    from solverah.repositories import assessment_repository, profile_repository
    from solverah.services import assessment_service, matching_service

    answers = [
        {"question_id": "wp-q%d" % i, "option_id": "wp-q%d-b" % i} for i in range(1, 13)
    ]

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        # Through the repository rather than by constructing the row:
        # `open_current` is the write doorway, and it registers the form version
        # the foreign key needs on the way in.
        submission = assessment_repository.open_current(
            user.id, "work_pulse", assessment_service.CLIENT_FORM_VERSION
        )
        submission.answers = answers
        submission.status = "scored"
        submission.completed_at = submission.scored_at = auth_domain.utcnow()
        db.session.commit()
        user_id = user.id

        assert "culture_preferences" not in profile_repository.load_document(user_id)

        derived = matching_service.resolve_culture_preferences(user)

        assert derived, "the derivation stopped working, not just the write"
        assert "culture_preferences" not in profile_repository.load_document(user_id), (
            "resolve_culture_preferences persisted on a read path again"
        )

        # And the backfill is where the write went.
        counts = matching_service.backfill_culture_preferences()
        assert counts["written"] == 1
        assert profile_repository.load_document(user_id)["culture_preferences"] == derived
