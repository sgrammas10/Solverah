"""POST /assessments/manager-profile and GET /me/manager-playbook (BUILD_PLAN C-3).

Both instruments score deterministically and instantly -- unlike `manager_match`, there is
no provider call and so no job/poll pair to drive. `_seed_manager_match` writes a
ManagerMatch submission the same way test_manager_match_api.py's
`test_get_results_happy_path` does: through `assessment_repository.open_current`, so a
test cannot seed a row the application could not produce itself.
"""

MP_ANSWERS = [
    {"question_id": "mp-q%d" % i, "choice": "a" if i % 2 == 0 else "b"}
    for i in range(1, 17)
]

MM_ANSWERS = [
    {"question_id": "mm-q%d" % i, "choice": "a" if i % 2 == 0 else "b"}
    for i in range(1, 16)
]


def _noop(*_args, **_kwargs):
    return None


def _register_and_login(client, monkeypatch, email="mp@example.com", password="Strongpass1!"):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)

    client.post(
        "/api/v1/auth/register",
        json={
            "email": email, "password": password, "name": "MP User",
            "role": "job-seeker", "terms_accepted": True,
        },
    )

    from app import app
    from model import User, db
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


def _seed_manager_match(email: str, answers=MM_ANSWERS) -> None:
    """Give *email* a completed ManagerMatch sitting, through the sanctioned write path."""
    from app import app
    from model import User, db
    from solverah.domain import auth as auth_domain
    from solverah.repositories import assessment_repository
    from solverah.services import assessment_service

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        submission = assessment_repository.open_current(
            user.id, "manager_match", assessment_service.CLIENT_FORM_VERSION
        )
        submission.answers = answers
        submission.result = {"archetype": "The Operator", "dimension_scores": {}}
        submission.status = "scored"
        submission.completed_at = submission.scored_at = auth_domain.utcnow()
        db.session.commit()


def _post(client, body, csrf=None):
    headers = {"X-CSRF-TOKEN": csrf} if csrf else {}
    return client.post("/api/v1/assessments/manager-profile", json=body, headers=headers)


def _get_playbook(client):
    return client.get("/api/v1/me/manager-playbook")


# ── POST /assessments/manager-profile ───────────────────────────────────────


def test_submit_without_manager_match_scores_and_stores_but_playbook_is_null(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="mp_no_mm@example.com")

    res = _post(client, {"answers": MP_ANSWERS}, csrf)

    assert res.status_code == 200
    body = res.get_json()
    assert set(body["dimension_scores"]) == {
        "autonomy", "feedback_style", "relationship", "growth_focus",
    }
    assert body["scoring_key"] == "mp-v1"
    assert body["version"] == "v1"
    assert body["playbook"] is None


def test_submit_with_manager_match_assembles_the_playbook(client, monkeypatch):
    email = "mp_with_mm@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _seed_manager_match(email)

    res = _post(client, {"answers": MP_ANSWERS}, csrf)

    assert res.status_code == 200
    playbook = res.get_json()["playbook"]
    assert playbook is not None
    assert len(playbook["dimensions"]) == 4
    assert playbook["grind_count"] + playbook["mesh_count"] == 4
    assert "privacy_notice" in playbook


def test_submit_persists_a_manager_profiles_row(client, monkeypatch):
    email = "mp_persist@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)

    _post(client, {"answers": MP_ANSWERS}, csrf)

    from app import app
    from model import ManagerProfile, User
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        row = ManagerProfile.query.filter_by(user_id=user.id).one()
        assert row.scoring_key == "mp-v1"
        assert row.version == "v1"


def test_submit_wrong_answer_count(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="mp_short@example.com")

    res = _post(client, {"answers": MP_ANSWERS[:10]}, csrf)

    assert res.status_code == 400
    assert "16" in res.get_json()["error"]


def test_submit_invalid_choice_value(client, monkeypatch):
    csrf = _register_and_login(client, monkeypatch, email="mp_bad_choice@example.com")

    bad = [dict(a) for a in MP_ANSWERS]
    bad[3]["choice"] = "x"

    res = _post(client, {"answers": bad}, csrf)

    assert res.status_code == 400
    assert "choice" in res.get_json()["error"]


def test_submit_unauthenticated(client):
    res = _post(client, {"answers": MP_ANSWERS})
    assert res.status_code == 401


# ── Authored-identity round trip (Sebastian's 2026-09-10 storage ruling) ───


def test_authored_identity_round_trips_into_storage(client, monkeypatch):
    """`answers[i]["choice"]` is stored exactly as sent -- "a"/"b" as authored in
    manager_match/manager_profile.py, never a screen position -- so a frontend is free to
    reorder how options render without storage ever knowing."""
    email = "mp_identity@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)

    answers = [{"question_id": "mp-q%d" % i, "choice": "b" if i == 1 else "a"} for i in range(1, 17)]
    _post(client, {"answers": answers}, csrf)

    from app import app
    from model import ManagerProfile, User
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        row = ManagerProfile.query.filter_by(user_id=user.id).one()
        stored = {a["question_id"]: a["choice"] for a in row.answers}
        assert stored["mp-q1"] == "b"
        assert stored["mp-q2"] == "a"


# ── Retake versioning ────────────────────────────────────────────────────────


def test_retake_adds_a_row_rather_than_updating(client, monkeypatch):
    email = "mp_retake@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)

    first = _post(client, {"answers": MP_ANSWERS}, csrf)
    flipped = [dict(a, choice=("b" if a["choice"] == "a" else "a")) for a in MP_ANSWERS]
    second = _post(client, {"answers": flipped}, csrf)

    assert first.get_json()["dimension_scores"] != second.get_json()["dimension_scores"]

    from app import app
    from model import ManagerProfile, User
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        assert ManagerProfile.query.filter_by(user_id=user.id).count() == 2


# ── GET /me/manager-playbook ────────────────────────────────────────────────


def test_playbook_before_manager_match_is_409_no_manager_match(client, monkeypatch):
    _register_and_login(client, monkeypatch, email="pb_no_mm@example.com")

    res = _get_playbook(client)

    assert res.status_code == 409
    assert res.mimetype == "application/problem+json"
    body = res.get_json()
    assert body["errors"][0]["code"] == "no_manager_match"


def test_playbook_before_manager_profile_is_a_distinguishable_409(client, monkeypatch):
    email = "pb_no_mp@example.com"
    _register_and_login(client, monkeypatch, email=email)
    _seed_manager_match(email)

    res = _get_playbook(client)

    assert res.status_code == 409
    body = res.get_json()
    assert body["errors"][0]["code"] == "no_manager_profile"


def test_playbook_happy_path(client, monkeypatch):
    email = "pb_happy@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _seed_manager_match(email)
    _post(client, {"answers": MP_ANSWERS}, csrf)

    res = _get_playbook(client)

    assert res.status_code == 200
    body = res.get_json()
    assert set(body["dimension_scores"]) == {
        "autonomy", "feedback_style", "relationship", "growth_focus",
    }
    assert body["scoring_key"] == "mp-v1"
    assert len(body["playbook"]["dimensions"]) == 4


def test_playbook_serves_the_latest_sitting_after_a_retake(client, monkeypatch):
    email = "pb_retake@example.com"
    csrf = _register_and_login(client, monkeypatch, email=email)
    _seed_manager_match(email)
    _post(client, {"answers": MP_ANSWERS}, csrf)

    all_b = [{"question_id": "mp-q%d" % i, "choice": "b"} for i in range(1, 17)]
    _post(client, {"answers": all_b}, csrf)

    res = _get_playbook(client)
    assert res.status_code == 200

    from app import app
    from manager_profile_store import latest_manager_profile
    from model import User
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        latest = latest_manager_profile(user.id)
        assert latest["answers"] == all_b


def test_playbook_unauthenticated(client):
    res = _get_playbook(client)
    assert res.status_code == 401


# ── Rate limit shape ─────────────────────────────────────────────────────────


def test_submit_is_limited_to_five_per_minute(client, monkeypatch):
    """Matches the sibling assessment routes' submission budget
    (`solverah/api/v1/assessments.py`'s `DEFAULT_SUBMISSION_LIMIT`)."""
    from app import app
    from solverah.extensions import limiter

    csrf = _register_and_login(client, monkeypatch, email="mp_rate@example.com")

    limiter.reset()
    app.config["TESTING"] = False
    try:
        statuses = [
            _post(client, {"answers": MP_ANSWERS}, csrf).status_code for _ in range(6)
        ]
    finally:
        app.config["TESTING"] = True
        limiter.reset()

    assert statuses[:5] == [200] * 5
    assert statuses[5] == 429
