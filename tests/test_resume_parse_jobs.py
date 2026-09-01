"""Resume parsing off the request path: ``202`` + a job handle, and the poll.

Phase 3 item 3.  ``POST /me/resumes/{id}/complete`` downloads the object from R2,
writes it to a temp file, and runs pdfminer or python-docx over it *inside the
request* -- part of why ``gunicorn.conf.py`` carries a 120-second timeout.

**The old endpoint is not replaced and these tests say so.**  A client cannot
move from awaiting a 200 to polling a job in the same deploy that first gives it
a job to poll, so both exist until the frontend has moved.
``test_the_synchronous_path_still_works`` is the one that fails if somebody
"finishes the migration" by deleting it.

**What eager execution can and cannot show here.**  Under ``APP_ENV=testing`` the
parse runs inline, so a job is already terminal by the time the ``202`` is
returned -- which makes the happy path easy and makes the *interesting* states
unreachable through the endpoint. ``queued`` and ``running``, the two states a
client actually polls, and the reaper that resolves them, are therefore driven
against ``resume_jobs`` directly.

The parser itself is stubbed throughout: it reads from object storage, and what
is under test is the job lifecycle rather than pdfminer.
"""

import pytest

EMAIL = "resume-jobs@example.test"
PASSWORD = "Strongpass1!"

PARSED = {
    "experience": [{"company": "Acme", "title": "Engineer"}],
    "skills": ["Python"],
}


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture()
def auth(client, monkeypatch):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "name": "Resume Jobs",
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


@pytest.fixture()
def parser(monkeypatch):
    """Stub the parser. Returns the list of resume keys it was handed."""
    seen = []

    def _build(resume_key, resume_mime, resume_size_bytes, resume_name):
        seen.append(resume_key)
        return dict(PARSED)

    monkeypatch.setattr(
        "solverah.services.resume_service.build_profile_from_resume_key", _build
    )
    monkeypatch.setattr(
        "solverah.services.resume_service.snapshot_of",
        lambda key, updates: {"resumeKey": key},
    )
    return seen


def _ticket(client, csrf):
    """Presign an upload and return its resume_id."""
    resp = client.post(
        "/api/v1/me/resumes",
        json={"mime": "application/pdf", "size": 2048},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200
    return resp.get_json()["resume_id"]


@pytest.fixture()
def storage(monkeypatch):
    """Stub object storage for the presign step.

    Patched on ``resume_service`` as well as on ``infra.storage``, because
    ``resume_service`` does ``from solverah.infra.storage import get_s3_client``
    -- a name bound at import, which a patch on the source module does not reach.
    Without both, `S3_ENDPOINT_URL` is read for real, and CI (five variables, no
    `.env`) does not have it: green locally, 500 on the runner. Exactly the
    asymmetry CLAUDE.md names.
    """
    class _FakeS3:
        def generate_presigned_url(self, **_kwargs):
            return "https://example.invalid/put"

    monkeypatch.setattr("solverah.infra.storage.get_s3_client", lambda: _FakeS3())
    monkeypatch.setattr(
        "solverah.services.resume_service.get_s3_client", lambda: _FakeS3()
    )
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bucket")


# ── The contract addition ───────────────────────────────────────────────────


def test_queueing_a_parse_answers_202_with_a_handle(client, auth, storage, parser):
    resume_id = _ticket(client, auth)

    resp = client.post(
        "/api/v1/me/resumes/%s/parse-jobs" % resume_id,
        json={"mime": "application/pdf", "size": 2048, "name": "cv.pdf"},
        headers={"X-CSRF-TOKEN": auth},
    )

    assert resp.status_code == 202
    body = resp.get_json()
    from solverah.schemas.profile import ResumeParseJobAccepted

    ResumeParseJobAccepted.model_validate(body)
    assert body["status_url"] == "/me/resume-parse-jobs/%s" % body["job_id"]


def test_polling_reports_success_and_hands_back_the_profile(
    client, auth, storage, parser
):
    """The succeeded payload carries what ``/complete`` would have returned.

    Same document from both paths, so a client's merge logic does not fork on
    which endpoint it used.
    """
    resume_id = _ticket(client, auth)
    job_id = client.post(
        "/api/v1/me/resumes/%s/parse-jobs" % resume_id,
        json={"mime": "application/pdf", "size": 2048},
        headers={"X-CSRF-TOKEN": auth},
    ).get_json()["job_id"]

    resp = client.get("/api/v1/me/resume-parse-jobs/%s" % job_id)

    assert resp.status_code == 200
    body = resp.get_json()
    from solverah.schemas.profile import ResumeParseJobStatus

    ResumeParseJobStatus.model_validate(body)
    assert body["status"] == "succeeded"
    assert body["error"] is None
    assert body["profile"]["skills"] == ["Python"]


def test_the_synchronous_path_still_works(client, auth, storage, parser):
    """This is an addition, not a replacement.

    Delete `/complete` and this fails -- which is the point, because the frontend
    is still on it.
    """
    resume_id = _ticket(client, auth)

    resp = client.post(
        "/api/v1/me/resumes/%s/complete" % resume_id,
        json={"mime": "application/pdf", "size": 2048},
        headers={"X-CSRF-TOKEN": auth},
    )

    assert resp.status_code == 200
    assert resp.get_json()["profile"]["skills"] == ["Python"]


# ── Ownership ───────────────────────────────────────────────────────────────


def test_a_job_handle_is_scoped_to_its_owner(client, auth, storage, parser):
    """404, not 403: distinguishing them would confirm the handle exists, and the
    handle is the only thing protecting the job."""
    from app import app
    from model import ResumeParseJob, User, db
    from solverah.services import resume_jobs

    with app.app_context():
        stranger = User(email="stranger@example.test", password_hash="not-a-real-hash")
        db.session.add(stranger)
        db.session.commit()
        job = ResumeParseJob(
            user_id=stranger.id,
            object_key="profile/%s/x/resume.pdf" % stranger.id,
            mime="application/pdf",
            size_bytes=10,
        )
        db.session.add(job)
        db.session.commit()
        stolen = job.public_id.hex

        owner = User.query.filter_by(email=EMAIL).first()
        assert resume_jobs.find_for_user(owner.id, stolen) is None

    assert client.get("/api/v1/me/resume-parse-jobs/%s" % stolen).status_code == 404


def test_a_malformed_handle_is_a_404_not_a_500(client, auth):
    """A handle that is not a UUID must not reach the driver as one."""
    assert client.get("/api/v1/me/resume-parse-jobs/not-a-uuid").status_code == 404


def test_queueing_against_an_unknown_resume_is_a_404(client, auth, storage):
    assert (
        client.post(
            "/api/v1/me/resumes/current/parse-jobs",
            json={"mime": "application/pdf", "size": 2048},
            headers={"X-CSRF-TOKEN": auth},
        ).status_code
        == 404
    )


# ── The lifecycle, driven directly ──────────────────────────────────────────


@pytest.fixture()
def job(client, auth):
    """A queued job for the signed-in user, created without running it."""
    from app import app
    from model import ResumeParseJob, User, db

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        row = ResumeParseJob(
            user_id=user.id,
            object_key="profile/%s/abc/resume.pdf" % user.id,
            mime="application/pdf",
            size_bytes=2048,
        )
        db.session.add(row)
        db.session.commit()
        return {"id": row.id, "public_id": row.public_id.hex, "user_id": user.id}


def test_a_queued_job_polls_as_queued_and_carries_no_profile(client, auth, job):
    resp = client.get("/api/v1/me/resume-parse-jobs/%s" % job["public_id"])

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "queued"
    assert body.get("profile") is None


def test_a_second_worker_cannot_claim_a_running_job(client, auth, job, parser):
    """``task_acks_late`` redelivers on a worker death, so the claim is the guard.

    Zero parses on the second call is the assertion: a redelivered message must
    not run the parse a second time and merge it again.
    """
    from app import app
    from solverah.services import resume_jobs

    with app.app_context():
        assert resume_jobs.run(job["id"]) == resume_jobs.SUCCEEDED
        assert len(parser) == 1

        assert resume_jobs.run(job["id"]) == "skipped"
        assert len(parser) == 1


def test_a_parse_failure_is_reported_without_leaking_storage_detail(
    client, auth, job, monkeypatch
):
    """Parser and botocore messages carry bucket names and object keys.

    The job row records a fixed reason; the real exception goes to the logs.
    """
    from app import app
    from solverah.services import resume_jobs

    def _boom(**_kwargs):
        raise RuntimeError("NoSuchKey: solverah-resumes/profile/9/abc/resume.pdf")

    monkeypatch.setattr(
        "solverah.services.resume_service.build_profile_from_resume_key", _boom
    )

    with app.app_context():
        assert resume_jobs.run(job["id"]) == resume_jobs.FAILED

    body = client.get("/api/v1/me/resume-parse-jobs/%s" % job["public_id"]).get_json()

    assert body["status"] == "failed"
    assert body["error"] == resume_jobs.GENERIC_FAILURE
    assert "solverah-resumes" not in body["error"]
    assert body.get("profile") is None


def test_a_stalled_job_is_failed_rather_than_polled_forever(client, auth, job):
    """A worker killed mid-parse leaves a row nothing will ever move.

    A client holding a spinner needs an answer more than it needs an optimistic
    status, so past the deadline the sweep fails it.
    """
    import sqlalchemy as sa

    from app import app
    from model import ResumeParseJob, db
    from solverah.services import resume_jobs

    with app.app_context():
        with db.engine.begin() as connection:
            connection.execute(
                sa.update(ResumeParseJob.__table__)
                .where(ResumeParseJob.__table__.c.id == job["id"])
                .values(
                    status="running",
                    created_at=sa.text("now() - interval '2 hours'"),
                )
            )

        assert resume_jobs.reap_stalled() == 1

    body = client.get("/api/v1/me/resume-parse-jobs/%s" % job["public_id"]).get_json()
    assert body["status"] == "failed"


def test_a_recent_job_is_not_reaped(client, auth, job):
    """A queue backed up behind a deploy is a slow job, not a stalled one."""
    from app import app
    from solverah.services import resume_jobs

    with app.app_context():
        assert resume_jobs.reap_stalled() == 0

    body = client.get("/api/v1/me/resume-parse-jobs/%s" % job["public_id"]).get_json()
    assert body["status"] == "queued"


def test_the_sweep_runs_jobs_whose_enqueue_was_lost(client, auth, job, parser):
    """``queue.enqueue`` swallows a broker failure, so something has to find the row.

    That is the whole reason a job is a table row before it is a message.
    """
    from app import app
    from solverah.services import resume_jobs
    from solverah.tasks.resume_tasks import sweep_resume_jobs

    with app.app_context():
        assert job["id"] in resume_jobs.pending_ids()

        result = sweep_resume_jobs()

    assert result["requeued"] == 1
    assert len(parser) == 1

    body = client.get("/api/v1/me/resume-parse-jobs/%s" % job["public_id"]).get_json()
    assert body["status"] == "succeeded"
