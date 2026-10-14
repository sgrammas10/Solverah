"""API tests for condition experiments (BUILD_PLAN B-5):
`POST /me/experiments`, `GET /me/experiments`, `POST /me/experiments/{id}/abandon`.
"""
import datetime

import pytest

from solverah.schemas.experiments import (
    ExperimentAbandonResponse,
    ExperimentListResponse,
    ExperimentStartResponse,
)

EMAIL = "experiments-api@example.com"
PASSWORD = "Strongpass1!"


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture()
def auth(client, monkeypatch):
    """A registered, confirmed, logged-in user. Returns (csrf_token, user_id)."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)

    client.post(
        "/api/v1/auth/register",
        json={
            "email": EMAIL, "password": PASSWORD, "name": "Experiments User",
            "role": "job-seeker", "terms_accepted": True,
        },
    )

    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()
        user_id = user.id

    resp = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"], user_id


def _start(client, csrf, *, dimension="autonomy", direction="under"):
    return client.post(
        "/api/v1/me/experiments",
        json={"dimension": dimension, "direction": direction},
        headers={"X-CSRF-TOKEN": csrf},
    )


# ── POST /me/experiments ────────────────────────────────────────────────────


def test_post_experiment_happy_path(client, auth):
    csrf, _user_id = auth

    resp = _start(client, csrf, dimension="pace", direction="over")

    assert resp.status_code == 201
    body = resp.get_json()
    ExperimentStartResponse.model_validate(body)
    assert body["dimension"] == "pace"
    assert body["direction"] == "over"
    assert body["status"] == "active"
    assert body["phase"] == "running"
    assert body["abandoned_at"] is None
    assert body["readout"] == {
        "verdict": "not_enough_data", "before_count": 0, "after_count": 0,
    }
    # The cell's own name, resolved server-side from situation_content --
    # not something the client sent or could have guessed.
    assert body["experiment_name"] == "Defend one block, for two weeks"


def test_post_experiment_rejects_an_unknown_dimension(client, auth):
    csrf, _user_id = auth

    resp = _start(client, csrf, dimension="nonexistent", direction="under")

    assert resp.status_code == 422
    body = resp.get_json()
    assert body["status"] == 422
    assert body["errors"][0]["code"] == "not_a_change_in_place_cell"


def test_post_experiment_rejects_an_unknown_direction(client, auth):
    csrf, _user_id = auth

    resp = _start(client, csrf, dimension="autonomy", direction="sideways")

    assert resp.status_code == 422
    assert resp.get_json()["errors"][0]["code"] == "not_a_change_in_place_cell"


def test_post_experiment_rejects_missing_fields(client, auth):
    csrf, _user_id = auth

    resp = client.post(
        "/api/v1/me/experiments", json={"dimension": "autonomy"}, headers={"X-CSRF-TOKEN": csrf}
    )

    assert resp.status_code == 422


def test_post_experiment_refuses_a_second_one_while_active(client, auth):
    csrf, _user_id = auth
    first = _start(client, csrf, dimension="autonomy", direction="under")
    assert first.status_code == 201

    resp = _start(client, csrf, dimension="pace", direction="over")

    assert resp.status_code == 409
    assert resp.get_json()["errors"][0]["code"] == "experiment_already_active"


def test_post_experiment_allows_a_new_one_after_the_first_is_abandoned(client, auth):
    csrf, _user_id = auth
    first = _start(client, csrf, dimension="autonomy", direction="under").get_json()

    client.post(
        "/api/v1/me/experiments/%d/abandon" % first["id"], headers={"X-CSRF-TOKEN": csrf}
    )

    resp = _start(client, csrf, dimension="pace", direction="over")
    assert resp.status_code == 201


def _end_now(experiment_id, *, days_ago=1):
    """Backdate one experiment so its two weeks are already over."""
    from app import app
    from model import Experiment, db

    with app.app_context():
        row = db.session.get(Experiment, experiment_id)
        row.ends_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)
        row.started_at = row.ends_at - datetime.timedelta(days=14)
        db.session.commit()


def test_post_experiment_allows_a_new_one_after_the_first_ends_naturally(client, auth):
    """The 2026-10-02 blocker: an experiment that ran its two weeks kept
    `status = 'active'`, so every later start 409'd forever. Now the ended row
    is closed (`completed`) before the one-active check, and the next start
    is a 201 -- on the same cell or another."""
    csrf, _user_id = auth
    first = _start(client, csrf, dimension="autonomy", direction="under").get_json()
    _end_now(first["id"])

    resp = _start(client, csrf, dimension="autonomy", direction="under")

    assert resp.status_code == 201, resp.get_json()
    assert resp.get_json()["phase"] == "running"

    listed = client.get("/api/v1/me/experiments").get_json()["experiments"]
    assert [(row["id"], row["status"], row["phase"]) for row in listed] == [
        (resp.get_json()["id"], "active", "running"),
        (first["id"], "completed", "ended"),
    ]


def test_get_experiments_closes_an_ended_row_on_read(client, auth):
    """`status` on the wire never pairs `active` with `ended`: the list read
    itself moves an ended row to `completed`."""
    csrf, _user_id = auth
    started = _start(client, csrf).get_json()
    _end_now(started["id"])

    body = client.get("/api/v1/me/experiments").get_json()["experiments"][0]

    assert body["status"] == "completed"
    assert body["phase"] == "ended"
    ExperimentListResponse.model_validate({"experiments": [body]})


def test_post_abandon_on_an_ended_experiment_keeps_it_completed(client, auth):
    """Abandoning after the two weeks are up is a no-op, not a relabel: the
    readout stays, the status reads `completed`, and the call is still a 200."""
    csrf, _user_id = auth
    started = _start(client, csrf).get_json()
    _end_now(started["id"])

    resp = client.post(
        "/api/v1/me/experiments/%d/abandon" % started["id"], headers={"X-CSRF-TOKEN": csrf}
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "completed"
    assert body["phase"] == "ended"
    assert body["abandoned_at"] is None


def test_post_experiment_requires_authentication(client):
    resp = client.post(
        "/api/v1/me/experiments", json={"dimension": "autonomy", "direction": "under"}
    )
    assert resp.status_code == 401


# ── GET /me/experiments ─────────────────────────────────────────────────────


def test_get_experiments_lists_newest_first_with_phase_and_readout(client, auth):
    csrf, _user_id = auth
    first = _start(client, csrf, dimension="autonomy", direction="under").get_json()
    client.post(
        "/api/v1/me/experiments/%d/abandon" % first["id"], headers={"X-CSRF-TOKEN": csrf}
    )
    second = _start(client, csrf, dimension="pace", direction="over").get_json()

    resp = client.get("/api/v1/me/experiments")

    assert resp.status_code == 200
    body = resp.get_json()
    ExperimentListResponse.model_validate(body)
    assert [row["id"] for row in body["experiments"]] == [second["id"], first["id"]]
    assert body["experiments"][0]["phase"] == "running"
    assert body["experiments"][1]["phase"] == "abandoned"


def test_get_experiments_empty_before_any_are_started(client, auth):
    resp = client.get("/api/v1/me/experiments")

    assert resp.status_code == 200
    assert resp.get_json()["experiments"] == []


def test_get_experiments_readout_reflects_real_checkins(client, auth):
    """An end-to-end slice: start an experiment, back-date it, log a real
    check-in on each side of the boundary, and read the word back."""
    csrf, user_id = auth
    started = _start(client, csrf, dimension="autonomy", direction="under").get_json()

    from app import app
    from model import Experiment, db
    from pulse_store import write_pulse_checkin
    from work_pulse.pulse_items import FORM_VERSION, dimensions_for_checkin

    with app.app_context():
        row = db.session.get(Experiment, started["id"])
        started_at = datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)
        row.started_at = started_at
        row.ends_at = started_at + datetime.timedelta(days=14)
        db.session.commit()

        # Before: experienced 2. After: experienced 5. A real move up.
        write_pulse_checkin(
            db, user_id, sequence=0,
            item_scores={d: 3 for d in dimensions_for_checkin(user_id, 0)},
            experienced=2, version=FORM_VERSION,
        )
        db.session.commit()
        from model import PulseCheckin

        checkin = PulseCheckin.query.filter_by(user_id=user_id, sequence=0).one()
        checkin.taken_at = started_at - datetime.timedelta(days=3)
        db.session.commit()

        write_pulse_checkin(
            db, user_id, sequence=1,
            item_scores={d: 3 for d in dimensions_for_checkin(user_id, 1)},
            experienced=5, version=FORM_VERSION,
        )
        db.session.commit()
        checkin2 = PulseCheckin.query.filter_by(user_id=user_id, sequence=1).one()
        checkin2.taken_at = started_at + datetime.timedelta(days=3)
        db.session.commit()

    resp = client.get("/api/v1/me/experiments")
    body = resp.get_json()["experiments"][0]
    assert body["readout"] == {
        "verdict": "moved_up", "before_count": 1, "after_count": 1,
    }


def test_get_experiments_requires_authentication(client):
    assert client.get("/api/v1/me/experiments").status_code == 401


# ── POST /me/experiments/{id}/abandon ───────────────────────────────────────


def test_post_abandon_marks_the_experiment_abandoned(client, auth):
    csrf, _user_id = auth
    started = _start(client, csrf).get_json()

    resp = client.post(
        "/api/v1/me/experiments/%d/abandon" % started["id"], headers={"X-CSRF-TOKEN": csrf}
    )

    assert resp.status_code == 200
    body = resp.get_json()
    ExperimentAbandonResponse.model_validate(body)
    assert body["status"] == "abandoned"
    assert body["phase"] == "abandoned"
    assert body["abandoned_at"] is not None


def test_post_abandon_is_idempotent(client, auth):
    csrf, _user_id = auth
    started = _start(client, csrf).get_json()

    first = client.post(
        "/api/v1/me/experiments/%d/abandon" % started["id"], headers={"X-CSRF-TOKEN": csrf}
    ).get_json()
    second = client.post(
        "/api/v1/me/experiments/%d/abandon" % started["id"], headers={"X-CSRF-TOKEN": csrf}
    ).get_json()

    assert second["abandoned_at"] == first["abandoned_at"]


def test_post_abandon_404s_for_a_nonexistent_id(client, auth):
    csrf, _user_id = auth

    resp = client.post(
        "/api/v1/me/experiments/999999/abandon", headers={"X-CSRF-TOKEN": csrf}
    )

    assert resp.status_code == 404


def test_post_abandon_404s_for_someone_elses_experiment(client, monkeypatch):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)

    def _register_and_login(email):
        client.post(
            "/api/v1/auth/register",
            json={
                "email": email, "password": PASSWORD, "name": "User",
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
        resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        return resp.get_json()["csrfToken"]

    owner_csrf = _register_and_login("experiments-owner@example.com")
    owned = _start(client, owner_csrf).get_json()

    other_csrf = _register_and_login("experiments-other@example.com")
    resp = client.post(
        "/api/v1/me/experiments/%d/abandon" % owned["id"], headers={"X-CSRF-TOKEN": other_csrf}
    )

    assert resp.status_code == 404


def test_post_abandon_requires_authentication(client):
    assert client.post("/api/v1/me/experiments/1/abandon").status_code == 401
