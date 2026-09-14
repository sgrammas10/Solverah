"""API tests for the Pulse surface (BUILD_PLAN B-2):
`POST /me/pulse/checkins`, `GET /me/pulse/history`, `GET /me/pulse/next-checkin`,
`POST /me/pulse/events`, `GET|PATCH /me/pulse/settings`.

`pulse_settings`'s cadence/anti-nag state and the cadence engine's due-selection
are covered on their own in `test_pulse_settings.py` and `test_pulse_cadence_cli.py`;
this file is only what an authenticated user's own requests can do.
"""

import datetime

import pytest

from solverah.schemas.pulse import (
    PulseCadenceResponse,
    PulseCheckinResponse,
    PulseEventResponse,
    PulseHistoryResponse,
    PulseNextCheckinResponse,
)
from work_pulse.pulse_items import dimensions_for_checkin

EMAIL = "pulse-api@example.com"
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
            "email": EMAIL, "password": PASSWORD, "name": "Pulse User",
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


def _scores_for(user_id, sequence, value=3):
    return {dim: value for dim in dimensions_for_checkin(user_id, sequence)}


def _submit_checkin(client, csrf, user_id, sequence, *, value=3, experienced=4):
    return client.post(
        "/api/v1/me/pulse/checkins",
        json={"item_scores": _scores_for(user_id, sequence, value=value), "experienced": experienced},
        headers={"X-CSRF-TOKEN": csrf},
    )


# ── POST /me/pulse/checkins ─────────────────────────────────────────────────


def test_post_checkin_happy_path_and_validates(client, auth):
    csrf, user_id = auth

    resp = _submit_checkin(client, csrf, user_id, 0, value=2, experienced=5)

    assert resp.status_code == 200
    body = resp.get_json()
    PulseCheckinResponse.model_validate(body)
    assert body["sequence"] == 0
    assert body["experienced"] == 5
    assert body["item_scores"] == _scores_for(user_id, 0, value=2)
    assert body["version"]


def test_post_checkin_sequence_advances_with_completed_count(client, auth):
    csrf, user_id = auth

    first = _submit_checkin(client, csrf, user_id, 0).get_json()
    second = _submit_checkin(client, csrf, user_id, 1).get_json()

    assert first["sequence"] == 0
    assert second["sequence"] == 1


def test_post_checkin_rejects_the_wrong_dimension_set(client, auth):
    """Posting a different dimension set than the server would have served is
    refused 422 in problem+json -- not silently accepted, not a 500."""
    csrf, user_id = auth

    wrong_scores = _scores_for(user_id, 1, value=3)  # sequence 1's dims, submitted as sequence 0
    resp = client.post(
        "/api/v1/me/pulse/checkins",
        json={"item_scores": wrong_scores, "experienced": 3},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert resp.status_code == 422
    body = resp.get_json()
    assert body["status"] == 422
    assert "item_scores" in body["detail"] or body["errors"][0]["field"] == "item_scores"


def test_post_checkin_rejects_a_score_out_of_range(client, auth):
    csrf, user_id = auth

    scores = _scores_for(user_id, 0, value=6)  # legal shape, illegal value
    resp = client.post(
        "/api/v1/me/pulse/checkins",
        json={"item_scores": scores, "experienced": 3},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert resp.status_code == 422


def test_post_checkin_rejects_missing_fields(client, auth):
    csrf, _user_id = auth

    resp = client.post(
        "/api/v1/me/pulse/checkins", json={"experienced": 3}, headers={"X-CSRF-TOKEN": csrf}
    )

    assert resp.status_code == 422


def test_post_checkin_requires_authentication(client):
    resp = client.post(
        "/api/v1/me/pulse/checkins", json={"item_scores": {}, "experienced": 3}
    )

    assert resp.status_code == 401


def test_post_checkin_round_robin_is_driven_by_count_not_the_clock(client, auth):
    """A check-in taken long ago still counts as one completed check-in, and the
    next sequence is exactly what `dimensions_for_checkin` says count=1 serves --
    never re-derived from how much calendar time has passed."""
    csrf, user_id = auth

    _submit_checkin(client, csrf, user_id, 0)

    from app import app
    from model import PulseCheckin, db

    with app.app_context():
        row = PulseCheckin.query.filter_by(user_id=user_id).one()
        row.taken_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(weeks=10)
        db.session.commit()

    next_checkin = client.get("/api/v1/me/pulse/next-checkin").get_json()
    assert next_checkin["sequence"] == 1
    assert {item["dimension"] for item in next_checkin["items"]} == set(
        dimensions_for_checkin(user_id, 1)
    )


# ── GET /me/pulse/next-checkin ──────────────────────────────────────────────


def test_get_next_checkin_matches_what_a_checkin_must_submit(client, auth):
    csrf, user_id = auth

    resp = client.get("/api/v1/me/pulse/next-checkin")
    assert resp.status_code == 200
    body = resp.get_json()
    PulseNextCheckinResponse.model_validate(body)
    assert body["sequence"] == 0
    served_dims = {item["dimension"] for item in body["items"]}
    assert served_dims == set(dimensions_for_checkin(user_id, 0))
    assert body["experienced_item"]["item_id"] == "pulse-experienced"

    # The exact set GET said would be served is exactly what POST accepts.
    submit = client.post(
        "/api/v1/me/pulse/checkins",
        json={"item_scores": {d: 3 for d in served_dims}, "experienced": 3},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert submit.status_code == 200


def test_get_next_checkin_requires_authentication(client):
    assert client.get("/api/v1/me/pulse/next-checkin").status_code == 401


# ── GET /me/pulse/history ───────────────────────────────────────────────────


def test_get_history_lists_checkins_and_events_newest_first(client, auth):
    csrf, user_id = auth

    _submit_checkin(client, csrf, user_id, 0)
    _submit_checkin(client, csrf, user_id, 1)
    client.post(
        "/api/v1/me/pulse/events",
        json={"event_type": "new_manager"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    resp = client.get("/api/v1/me/pulse/history")
    assert resp.status_code == 200
    body = resp.get_json()
    PulseHistoryResponse.model_validate(body)
    assert [c["sequence"] for c in body["checkins"]] == [1, 0]
    assert len(body["events"]) == 1
    assert body["events"][0]["event_type"] == "new_manager"


def test_get_history_windows_by_since_and_until(client, auth):
    csrf, user_id = auth
    _submit_checkin(client, csrf, user_id, 0)

    from app import app
    from model import PulseCheckin, db

    with app.app_context():
        row = PulseCheckin.query.filter_by(user_id=user_id).one()
        row.taken_at = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
        db.session.commit()

    _submit_checkin(client, csrf, user_id, 1)  # taken "now"

    only_recent = client.get(
        "/api/v1/me/pulse/history?since=2025-01-01T00:00:00%2B00:00"
    ).get_json()
    assert [c["sequence"] for c in only_recent["checkins"]] == [1]

    only_old = client.get(
        "/api/v1/me/pulse/history?until=2020-06-01T00:00:00%2B00:00"
    ).get_json()
    assert [c["sequence"] for c in only_old["checkins"]] == [0]


def test_get_history_limit_clamps_and_rejects_garbage(client, auth):
    csrf, user_id = auth
    for sequence in range(3):
        _submit_checkin(client, csrf, user_id, sequence)

    limited = client.get("/api/v1/me/pulse/history?limit=1").get_json()
    assert len(limited["checkins"]) == 1

    resp = client.get("/api/v1/me/pulse/history?limit=abc")
    assert resp.status_code == 422


def test_get_history_rejects_a_malformed_since(client, auth):
    _csrf, _user_id = auth

    resp = client.get("/api/v1/me/pulse/history?since=not-a-date")

    assert resp.status_code == 422


def test_get_history_requires_authentication(client):
    assert client.get("/api/v1/me/pulse/history").status_code == 401


# ── POST /me/pulse/events ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "event_type", ["new_manager", "reorg", "remote_change", "role_change", "other"]
)
def test_post_event_accepts_every_vocabulary_entry(client, auth, event_type):
    csrf, _user_id = auth

    resp = client.post(
        "/api/v1/me/pulse/events",
        json={"event_type": event_type, "note": "context"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert resp.status_code == 200
    body = resp.get_json()
    PulseEventResponse.model_validate(body)
    assert body["event_type"] == event_type
    assert body["note"] == "context"


def test_post_event_rejects_an_unknown_event_type(client, auth):
    csrf, _user_id = auth

    resp = client.post(
        "/api/v1/me/pulse/events",
        json={"event_type": "promotion"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert resp.status_code == 422


def test_post_event_rejects_a_note_over_the_length_cap(client, auth):
    csrf, _user_id = auth

    resp = client.post(
        "/api/v1/me/pulse/events",
        json={"event_type": "other", "note": "x" * 281},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert resp.status_code == 422


def test_post_event_requires_authentication(client):
    assert client.post("/api/v1/me/pulse/events", json={"event_type": "other"}).status_code == 401


# ── GET|PATCH /me/pulse/settings ────────────────────────────────────────────


def test_get_settings_defaults_to_weekly(client, auth):
    resp = client.get("/api/v1/me/pulse/settings")

    assert resp.status_code == 200
    body = resp.get_json()
    PulseCadenceResponse.model_validate(body)
    assert body["cadence"] == "weekly"


@pytest.mark.parametrize("cadence", ["biweekly", "off", "weekly"])
def test_patch_settings_updates_cadence(client, auth, cadence):
    csrf, _user_id = auth

    resp = client.patch(
        "/api/v1/me/pulse/settings", json={"cadence": cadence}, headers={"X-CSRF-TOKEN": csrf}
    )

    assert resp.status_code == 200
    assert resp.get_json()["cadence"] == cadence
    assert client.get("/api/v1/me/pulse/settings").get_json()["cadence"] == cadence


def test_patch_settings_off_is_one_call(client, auth):
    """The product rule, checked structurally: turning Pulse off is a single
    PATCH, no confirmation step, no secondary call."""
    csrf, _user_id = auth

    resp = client.patch(
        "/api/v1/me/pulse/settings", json={"cadence": "off"}, headers={"X-CSRF-TOKEN": csrf}
    )

    assert resp.status_code == 200
    assert resp.get_json()["cadence"] == "off"


def test_patch_settings_rejects_a_cadence_the_user_cannot_set_directly(client, auth):
    csrf, _user_id = auth

    resp = client.patch(
        "/api/v1/me/pulse/settings", json={"cadence": "monthly"}, headers={"X-CSRF-TOKEN": csrf}
    )

    assert resp.status_code == 422


def test_patch_settings_rejects_an_unknown_cadence(client, auth):
    csrf, _user_id = auth

    resp = client.patch(
        "/api/v1/me/pulse/settings", json={"cadence": "daily"}, headers={"X-CSRF-TOKEN": csrf}
    )

    assert resp.status_code == 422


def test_get_settings_requires_authentication(client):
    assert client.get("/api/v1/me/pulse/settings").status_code == 401


def test_patch_settings_requires_authentication(client):
    resp = client.patch("/api/v1/me/pulse/settings", json={"cadence": "off"})

    assert resp.status_code == 401
