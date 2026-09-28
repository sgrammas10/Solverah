"""``GET /me/dashboard``'s Recent Activity and Recommendations are real.

Until 2026-09-28 every account received the same static placeholders --
"Complete your leadership assessment, 1 day ago" and "Boost visibility" --
whatever it had actually done. These tests pin the replacement: one activity
item per real source, newest first; one recommendation per unfinished step,
each pointing at a route the SPA actually mounts; and a cached dashboard that
is dropped when a new activity row commits, not five minutes later.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

import pytest

from solverah.repositories.dashboard_repository import ActivityRow
from solverah.schemas.profile import DashboardResponse
from solverah.services import dashboard_feed

REPO = Path(__file__).resolve().parents[1]
EMAIL = "dash-feed@example.com"
PASSWORD = "Strongpass1!"
NOW = datetime.datetime(2026, 9, 28, 12, 0, tzinfo=datetime.timezone.utc)
PLACEHOLDER_STRINGS = (
    "Complete your leadership assessment",
    "1 day ago",
    "Boost visibility",
    "Complete Psychometric Assessment",
    "Add Recent Experience",
)


@pytest.fixture(autouse=True)
def _form_token_secret(monkeypatch):
    # Read at call time in assessment_store.respondent_id_for_user, with no
    # default by design (D-05). Deliberately not in tests/conftest.py.
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")


def _noop(*_args, **_kwargs):
    return None


@pytest.fixture()
def auth(client, monkeypatch):
    """A registered, confirmed, logged-in user. Returns (csrf, user_id)."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    client.post(
        "/api/v1/auth/register",
        json={"email": EMAIL, "password": PASSWORD, "name": "Dash User",
              "role": "job-seeker", "terms_accepted": True},
    )
    from model import User, db

    with client.application.app_context():
        user = User.query.filter_by(email=EMAIL).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()
        user_id = user.id

    resp = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"], user_id


def _dashboard(client) -> dict:
    resp = client.get("/api/v1/me/dashboard")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    DashboardResponse.model_validate(body)
    return body


def _ago(**delta) -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(**delta)


def _add(client, *rows) -> None:
    from model import AssessmentForm, AssessmentSubmission, db

    with client.application.app_context():
        for row in rows:
            if isinstance(row, AssessmentSubmission):
                AssessmentForm.register(row.kind, row.form_version)
            db.session.add(row)
        db.session.commit()


def _submission(user_id, kind, at):
    from model import AssessmentSubmission

    return AssessmentSubmission(user_id=user_id, kind=kind, form_version="dash-test",
                                status="complete", completed_at=at)


def _env_report(user_id, at):
    from model import EnvironmentReport

    return EnvironmentReport(user_id=user_id, raw_answers={}, stage_size=3,
                             experienced_outcome=3, career_status="employed",
                             version="dash-test", submitted_at=at)


def _checkin(user_id, at):
    from model import PulseCheckin

    return PulseCheckin(user_id=user_id, sequence=0, item_scores={}, experienced=3,
                        version="dash-test", taken_at=at)


def _manager_profile(user_id, at):
    from model import ManagerProfile

    return ManagerProfile(user_id=user_id, answers={}, dimension_scores={},
                          scoring_key="dash-test", version="dash-test", created_at=at)


def _resume(user_id, at):
    from model import Resume

    return Resume(user_id=user_id, object_key="profile/%s/x/resume.pdf" % user_id,
                  created_at=at)


def _complete_core(client, csrf):
    """The real 24-item Work Pulse, through the real route."""
    form = client.get("/api/v1/assessments/core/form")
    assert form.status_code == 200
    responses = {
        item["token"]: item["options"][0]["key"]
        for block in form.get_json()["blocks"]
        for item in block["items"]
    }
    resp = client.post("/api/v1/assessments/core/submissions",
                       json={"responses": responses}, headers={"X-CSRF-TOKEN": csrf})
    assert resp.status_code == 200, resp.get_json()


def _texts(items):
    return [item["text"] for item in items]


def _ids(recs):
    return [rec["id"] for rec in recs]


# ── A brand-new account ─────────────────────────────────────────────────────


def test_a_new_account_has_no_activity_and_the_first_three_steps(client, auth):
    body = _dashboard(client)

    assert body["recentActivity"] == []
    assert _ids(body["recommendations"]) == ["career_status", "work_pulse", "skills"]


def test_the_old_placeholder_strings_never_appear(client, auth):
    """Regression: every account used to receive the same static items."""
    csrf, user_id = auth
    _add(client, _checkin(user_id, _ago(days=1)))

    raw = client.get("/api/v1/me/dashboard").get_data(as_text=True)

    for placeholder in PLACEHOLDER_STRINGS:
        assert placeholder not in raw
    assert "/job-seeker/profile#assessments" not in raw


# ── One test per activity source ────────────────────────────────────────────


@pytest.mark.parametrize(
    "build, text, icon",
    [
        (lambda uid, at: _submission(uid, "focus_type", at), "You took FocusType", "Brain"),
        (lambda uid, at: _submission(uid, "manager_match", at), "You took ManagerMatch", "Brain"),
        (lambda uid, at: _submission(uid, "work_pulse", at),
         "You took the original Work Pulse quiz", "Brain"),
        (_env_report, "You described your current job", "FileText"),
        (_manager_profile, "You described your manager", "Briefcase"),
        (_checkin, "You checked in on your week", "TrendingUp"),
        (_resume, "You uploaded your resume", "FileText"),
    ],
)
def test_each_activity_source_appears_with_its_timestamp(client, auth, build, text, icon):
    _csrf, user_id = auth
    at = _ago(hours=3)
    _add(client, build(user_id, at))

    [item] = _dashboard(client)["recentActivity"]

    assert item["text"] == text
    assert item["icon"] == icon
    assert datetime.datetime.fromisoformat(item["time"]) == at


def test_a_work_pulse_sitting_appears(client, auth):
    csrf, _user_id = auth
    _complete_core(client, csrf)

    assert "You took Work Pulse" in _texts(_dashboard(client)["recentActivity"])


def test_quiz_insights_appear_from_the_profile_document(client, auth):
    from model import db
    from solverah.repositories import profile_repository

    _csrf, user_id = auth
    stamp = _ago(hours=2).isoformat()
    with client.application.app_context():
        profile_repository.update_document(user_id, lambda doc: {
            **doc, "quizInsights": {"careerQuizzes": {"_generatedAt": stamp}}})
        db.session.commit()

    [item] = _dashboard(client)["recentActivity"]
    assert item["text"] == "You got insights from your career quizzes"
    assert item["time"] == datetime.datetime.fromisoformat(stamp).isoformat()


def test_the_claimed_anonymous_session_is_not_activity(client, auth):
    _csrf, user_id = auth
    _add(client, _submission(user_id, "wpll", _ago(hours=1)))

    assert _dashboard(client)["recentActivity"] == []


def test_activity_is_newest_first_one_per_source_and_at_most_five(client, auth):
    _csrf, user_id = auth
    _add(
        client,
        _checkin(user_id, _ago(days=9)),
        _checkin(user_id, _ago(days=2)),          # only the newest check-in shows
        _resume(user_id, _ago(days=5)),
        _env_report(user_id, _ago(days=1)),
        _manager_profile(user_id, _ago(days=3)),
        _submission(user_id, "focus_type", _ago(days=4)),
        _submission(user_id, "manager_match", _ago(days=6)),  # sixth: cut
    )

    items = _dashboard(client)["recentActivity"]

    assert _texts(items) == [
        "You described your current job",
        "You checked in on your week",
        "You described your manager",
        "You took FocusType",
        "You uploaded your resume",
    ]
    times = [item["time"] for item in items]
    assert times == sorted(times, reverse=True)


def test_another_users_activity_is_not_shown(client, auth):
    from model import User, db

    with client.application.app_context():
        other = User(email="someone-else@example.test", password_hash="x")
        db.session.add(other)
        db.session.commit()
        other_id = other.id
    _add(client, _checkin(other_id, _ago(hours=1)))

    assert _dashboard(client)["recentActivity"] == []


# ── Recommendation rules (pure) ─────────────────────────────────────────────


def _recs(profile=None, rows=(), has_work_pulse=False):
    return dashboard_feed.build_recommendations(
        profile or {}, list(rows), has_work_pulse=has_work_pulse, now=NOW)


def _row(source, days_ago):
    return ActivityRow(source=source, kind=None, at=NOW - datetime.timedelta(days=days_ago))


@pytest.fixture()
def _uncapped(monkeypatch):
    monkeypatch.setattr(dashboard_feed, "RECOMMENDATION_LIMIT", 99)


def _all_rules(profile=None, rows=(), has_work_pulse=False):
    """Every rule that fires. Callers use the ``_uncapped`` fixture."""
    return _ids(_recs(profile, rows, has_work_pulse))


@pytest.mark.usefixtures("_uncapped")
def test_career_status_is_recommended_only_when_unset_and_underivable():
    assert "career_status" in _all_rules({})
    assert "career_status" not in _all_rules({"career_status": "between_jobs"})
    derived = {"experience": [{"title": "Dev", "endDate": "Present"}]}
    assert "career_status" not in _all_rules(derived)


@pytest.mark.usefixtures("_uncapped")
def test_work_pulse_is_recommended_until_taken():
    assert "work_pulse" in _all_rules()
    assert "work_pulse" not in _all_rules(has_work_pulse=True)


@pytest.mark.usefixtures("_uncapped")
def test_environment_report_follows_work_pulse_and_skips_first_jobs():
    employed = {"career_status": "employed"}
    assert "environment_report" not in _all_rules(employed)
    assert "environment_report" in _all_rules(employed, has_work_pulse=True)
    assert "environment_report" not in _all_rules({"career_status": "first_job"},
                                                  has_work_pulse=True)
    done = [_row("environment_report", 1)]
    assert "environment_report" not in _all_rules(employed, done, has_work_pulse=True)


@pytest.mark.usefixtures("_uncapped")
def test_situation_report_needs_both_prerequisites():
    env = [_row("environment_report", 1)]
    assert "situation_report" not in _all_rules(has_work_pulse=True)
    assert "situation_report" not in _all_rules({}, env)
    assert "situation_report" in _all_rules({}, env, has_work_pulse=True)


@pytest.mark.usefixtures("_uncapped")
def test_skills_are_recommended_only_when_there_are_none():
    assert "skills" in _all_rules({"skills": []})
    assert "skills" not in _all_rules({"skills": ["Python"]})


@pytest.mark.usefixtures("_uncapped")
def test_pulse_is_recommended_when_never_taken_or_older_than_the_cadence():
    assert "pulse" in _all_rules()
    assert "pulse" not in _all_rules({}, [_row("pulse_checkin", 2)])
    assert "pulse" in _all_rules({}, [_row("pulse_checkin", 8)])
    biweekly = {"pulse_settings": {"cadence": "biweekly"}}
    assert "pulse" not in _all_rules(biweekly, [_row("pulse_checkin", 8)])
    assert "pulse" not in _all_rules({"pulse_settings": {"cadence": "off"}})


def test_recommendations_are_capped_at_three_in_priority_order():
    assert _ids(_recs()) == ["career_status", "work_pulse", "skills"]
    settled = {"career_status": "employed", "skills": ["Python"]}
    assert _ids(_recs(settled, [_row("environment_report", 1)], has_work_pulse=True)) == [
        "situation_report", "pulse"]


def test_the_endpoint_applies_the_rules_to_real_rows(client, auth):
    csrf, user_id = auth
    client.patch("/api/v1/me/career-status", json={"status": "employed"},
                 headers={"X-CSRF-TOKEN": csrf})
    _complete_core(client, csrf)

    assert _ids(_dashboard(client)["recommendations"]) == [
        "environment_report", "skills", "pulse"]


# ── Every href and icon resolves on the frontend ────────────────────────────


def _app_routes() -> set:
    source = (REPO / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
    return set(re.findall(r'<Route path="([^"]+)"', source))


def test_every_recommendation_href_is_a_mounted_route(monkeypatch):
    monkeypatch.setattr(dashboard_feed, "RECOMMENDATION_LIMIT", 99)
    fired = (
        _recs({})  # career_status, work_pulse, skills, pulse
        + _recs({"career_status": "employed"}, [], has_work_pulse=True)
        + _recs({}, [_row("environment_report", 1)], has_work_pulse=True)
    )
    recs = {rec["id"]: rec for rec in fired}
    assert set(recs) == {"career_status", "work_pulse", "environment_report",
                         "situation_report", "skills", "pulse"}
    routes = _app_routes()
    for rec in recs.values():
        path = re.split(r"[#?]", rec["href"])[0]
        assert path in routes, rec


def test_every_activity_icon_is_one_the_dashboard_maps():
    source = (REPO / "src" / "features" / "profile" / "components"
              / "JobSeekerDashboard.tsx").read_text(encoding="utf-8")
    mapped = set(re.search(r"iconMap[^{]*\{([^}]*)\}", source).group(1).replace(" ", "").split(","))
    icons = {icon for _t, icon in dashboard_feed._ASSESSMENT_COPY.values()}
    icons |= {icon for _k, _t, icon in dashboard_feed._SOURCE_COPY.values()}
    icons.add("Brain")  # quiz insights
    assert icons <= mapped


# ── Invalidation ────────────────────────────────────────────────────────────


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def ping(self):
        return True

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, _ttl, value):
        self.store[key] = value

    def delete(self, *keys):
        for key in keys:
            self.store.pop(key, None)


@pytest.fixture()
def fake_cache(monkeypatch):
    from solverah.infra import cache

    fake = _FakeRedis()
    cache.clear_client()
    monkeypatch.setattr(cache, "_url", "redis://fake")
    monkeypatch.setattr(cache, "_client", fake)
    monkeypatch.setattr(cache, "_client_resolved", True)
    yield fake
    cache.clear_client()


@pytest.mark.parametrize(
    "build",
    [_checkin, _env_report, _manager_profile, _resume,
     lambda uid, at: _submission(uid, "focus_type", at)],
)
def test_a_new_activity_row_drops_the_cached_dashboard(client, fake_cache, build):
    """Regression: only profile-document writes used to invalidate, so a
    check-in or assessment left the cached card stale for the whole TTL."""
    from model import AssessmentForm, AssessmentSubmission, User, db
    from solverah.infra import cache
    from solverah.services import profile_service

    with client.application.app_context():
        user = User(email="dash-cache@example.test", password_hash="x")
        db.session.add(user)
        db.session.commit()
        key = cache.dashboard_key(user.id)

        profile_service.dashboard_data(user, user.email)
        assert key in fake_cache.store

        row = build(user.id, _ago(minutes=1))
        if isinstance(row, AssessmentSubmission):
            AssessmentForm.register(row.kind, row.form_version)
            db.session.commit()
        db.session.add(row)
        db.session.flush()
        assert key in fake_cache.store, "dropped before the commit"
        db.session.commit()
        assert key not in fake_cache.store


def test_a_rolled_back_activity_row_keeps_the_cache(client, fake_cache):
    from model import User, db
    from solverah.infra import cache
    from solverah.services import profile_service

    with client.application.app_context():
        user = User(email="dash-rollback@example.test", password_hash="x")
        db.session.add(user)
        db.session.commit()
        key = cache.dashboard_key(user.id)
        profile_service.dashboard_data(user, user.email)

        db.session.add(_checkin(user.id, _ago(minutes=1)))
        db.session.flush()
        db.session.rollback()
        assert key in fake_cache.store
