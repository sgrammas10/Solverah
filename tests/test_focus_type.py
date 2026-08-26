"""Tests for FocusType scoring module and POST /api/focus-type/submit."""

import pytest
from focus_type.score import score_focus_type, DIMENSIONS, _determine_archetype


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------

# Produces clear Deep Diver winner:
#   Scene 1: big_project top → deep_focus +2
#   Scene 2: 2 items NOW (≤3) → deep_focus +2; ignore > now > later → deep_focus +1
#   Scene 3: deep_solo highest → deep_focus +2
#   Scene 4: deep_research in NOW → deep_focus +1; avg 500ms → reactivity +1
#   Scene 5: leads with deep_work → deep_focus +2; no break → deep_focus +1
# Total deep_focus = 2+2+1+2+1+2+1 = 11; others much lower.

DEEP_DIVER_PAYLOAD = {
    "scene_1": ["big_project", "planning_doc", "urgent_client", "teammate_feedback", "emails", "admin_tasks"],
    "scene_2": {
        "now":    ["email_client_important", "slack_mentioned"],
        "later":  ["slack_teammate_question"],
        "ignore": ["email_newsletter", "calendar_meeting_invite", "task_new_ticket",
                   "task_planning_doc", "slack_team_channel", "email_system_report",
                   "calendar_team_lunch"],
    },
    "scene_3": {"deep_solo": 2.5, "planning": 0.5, "social": 0.5, "breaks": 0.25, "exploring": 0.25},
    "scene_4": {
        "now":    ["deep_research"],
        "tomorrow": ["reply_teammate", "write_report_draft", "update_task_tracker",
                     "quick_call_unblock", "send_followup_email", "review_others_work",
                     "sketch_tomorrow_plan"],
        "avg_decision_time_ms": 500,
    },
    "scene_5": ["deep_work", "wind_down"],
}


def _register_and_login(client, monkeypatch, email="ft@example.com", password="Strongpass1!"):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", lambda *a, **kw: None)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", lambda *a, **kw: None)

    client.post("/api/register", json={
        "email": email, "password": password, "name": "FT User", "role": "job-seeker", "terms_accepted": True,
    })

    from app import app
    from model import User, db
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()

    resp = client.post("/api/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"]


# ---------------------------------------------------------------------------
# Pure scoring unit tests
# ---------------------------------------------------------------------------

class TestScoreFocusType:
    def test_returns_required_keys(self):
        result = score_focus_type(
            DEEP_DIVER_PAYLOAD["scene_1"],
            DEEP_DIVER_PAYLOAD["scene_2"],
            DEEP_DIVER_PAYLOAD["scene_3"],
            DEEP_DIVER_PAYLOAD["scene_4"],
            DEEP_DIVER_PAYLOAD["scene_5"],
        )
        assert "archetype" in result
        assert "dimension_scores" in result
        assert "recommendations" in result

    def test_dimension_scores_has_all_dimensions(self):
        result = score_focus_type(
            DEEP_DIVER_PAYLOAD["scene_1"],
            DEEP_DIVER_PAYLOAD["scene_2"],
            DEEP_DIVER_PAYLOAD["scene_3"],
            DEEP_DIVER_PAYLOAD["scene_4"],
            DEEP_DIVER_PAYLOAD["scene_5"],
        )
        assert set(result["dimension_scores"].keys()) == set(DIMENSIONS)

    def test_deep_diver_payload_produces_deep_diver(self):
        result = score_focus_type(
            DEEP_DIVER_PAYLOAD["scene_1"],
            DEEP_DIVER_PAYLOAD["scene_2"],
            DEEP_DIVER_PAYLOAD["scene_3"],
            DEEP_DIVER_PAYLOAD["scene_4"],
            DEEP_DIVER_PAYLOAD["scene_5"],
        )
        assert result["archetype"] == "Deep Diver"

    def test_recommendations_is_nonempty_list_of_strings(self):
        result = score_focus_type(
            DEEP_DIVER_PAYLOAD["scene_1"],
            DEEP_DIVER_PAYLOAD["scene_2"],
            DEEP_DIVER_PAYLOAD["scene_3"],
            DEEP_DIVER_PAYLOAD["scene_4"],
            DEEP_DIVER_PAYLOAD["scene_5"],
        )
        recs = result["recommendations"]
        assert isinstance(recs, list) and len(recs) > 0
        assert all(isinstance(r, str) for r in recs)

    def test_all_dimension_scores_are_non_negative(self):
        result = score_focus_type(
            DEEP_DIVER_PAYLOAD["scene_1"],
            DEEP_DIVER_PAYLOAD["scene_2"],
            DEEP_DIVER_PAYLOAD["scene_3"],
            DEEP_DIVER_PAYLOAD["scene_4"],
            DEEP_DIVER_PAYLOAD["scene_5"],
        )
        assert all(v >= 0 for v in result["dimension_scores"].values())


class TestTiebreaker:
    def test_deep_focus_structure_need_tie_picks_structured_builder(self):
        # Inject synthetic scores where deep_focus == structure_need > everything else
        scores = {d: 0 for d in DIMENSIONS}
        scores["deep_focus"] = 5
        scores["structure_need"] = 5
        assert _determine_archetype(scores) == "Structured Builder"

    def test_deep_focus_burst_energy_tie_picks_deep_diver(self):
        scores = {d: 0 for d in DIMENSIONS}
        scores["deep_focus"] = 4
        scores["burst_energy"] = 4
        assert _determine_archetype(scores) == "Deep Diver"

    def test_reactivity_social_fuel_tie_picks_collaborative_charger(self):
        scores = {d: 0 for d in DIMENSIONS}
        scores["reactivity"] = 6
        scores["social_fuel"] = 6
        assert _determine_archetype(scores) == "Collaborative Charger"

    def test_urgency_drive_reactivity_tie_picks_pressure_igniter(self):
        scores = {d: 0 for d in DIMENSIONS}
        scores["urgency_drive"] = 3
        scores["reactivity"] = 3
        assert _determine_archetype(scores) == "Pressure Igniter"

    def test_burst_energy_urgency_drive_tie_picks_sprint_and_reset(self):
        scores = {d: 0 for d in DIMENSIONS}
        scores["burst_energy"] = 7
        scores["urgency_drive"] = 7
        assert _determine_archetype(scores) == "Sprint & Reset"

    def test_unlisted_tie_falls_back_alphabetically(self):
        # deep_focus vs social_fuel tie — no explicit tiebreaker rule
        scores = {d: 0 for d in DIMENSIONS}
        scores["deep_focus"] = 5
        scores["social_fuel"] = 5
        # alphabetically "deep_focus" < "social_fuel"
        assert _determine_archetype(scores) == "Deep Diver"


# ---------------------------------------------------------------------------
# Scene-level scoring
# ---------------------------------------------------------------------------

class TestScene1:
    def test_big_project_top_scores_deep_focus(self):
        from focus_type.score import _score_scene_1
        s = _score_scene_1(["big_project", "emails"])
        assert s["deep_focus"] == 2

    def test_double_deep_focus_capped_at_2(self):
        # Both top-2 cards contribute to deep_focus — should not exceed 2
        from focus_type.score import _score_scene_1
        # Only big_project gives deep_focus; emails gives structure_need+reactivity
        # We test with two planning cards conceptually — use big_project twice
        # (edge case: same card in both slots)
        s = _score_scene_1(["big_project", "big_project"])
        assert s["deep_focus"] == 2

    def test_email_and_admin_tasks_split_between_structure_and_reactivity(self):
        from focus_type.score import _score_scene_1
        s = _score_scene_1(["emails", "admin_tasks"])
        # Each gives structure_need+1 but capped at 2, and reactivity+1 capped at 2
        assert s["structure_need"] == 2
        assert s["reactivity"] == 2


class TestScene2:
    def test_five_or_more_now_scores_reactivity(self):
        from focus_type.score import _score_scene_2
        s = _score_scene_2({
            "now": ["a", "b", "c", "d", "e"],
            "later": [], "ignore": [],
        })
        assert s["reactivity"] == 2

    def test_three_or_fewer_now_scores_deep_focus(self):
        from focus_type.score import _score_scene_2
        s = _score_scene_2({
            "now": ["x", "y"],
            "later": [], "ignore": [],
        })
        assert s["deep_focus"] == 2

    def test_most_in_ignore_scores_deep_focus_plus_1(self):
        from focus_type.score import _score_scene_2
        s = _score_scene_2({
            "now": ["a"],
            "later": ["b"],
            "ignore": ["c", "d", "e"],
        })
        assert s["deep_focus"] >= 1  # +1 from ignore and may have +2 from ≤3 now

    def test_client_card_in_now_scores_urgency(self):
        from focus_type.score import _score_scene_2
        s = _score_scene_2({
            "now": ["email_client_important"],
            "later": [], "ignore": [],
        })
        assert s["urgency_drive"] == 1


class TestScene3:
    def test_highest_allocation_gets_plus_2(self):
        from focus_type.score import _score_scene_3
        s = _score_scene_3({"deep_solo": 2.0, "planning": 1.0, "social": 0.5, "breaks": 0.3, "exploring": 0.2})
        assert s["deep_focus"] == 2

    def test_second_highest_gets_plus_1(self):
        from focus_type.score import _score_scene_3
        s = _score_scene_3({"deep_solo": 2.0, "planning": 1.0, "social": 0.5, "breaks": 0.3, "exploring": 0.2})
        assert s["structure_need"] == 1

    def test_breaks_highest_scores_burst_energy(self):
        from focus_type.score import _score_scene_3
        s = _score_scene_3({"deep_solo": 0.5, "planning": 0.5, "social": 0.5, "breaks": 2.0, "exploring": 0.5})
        assert s["burst_energy"] == 2


class TestScene4:
    def test_social_cards_in_now_score_social_fuel(self):
        from focus_type.score import _score_scene_4
        s = _score_scene_4({"now": ["reply_teammate"], "tomorrow": [], "avg_decision_time_ms": 1500})
        assert s["social_fuel"] == 2

    def test_almost_everything_tomorrow_scores_burst_energy(self):
        from focus_type.score import _score_scene_4
        s = _score_scene_4({
            "now": ["reply_teammate"],
            "tomorrow": ["write_report_draft", "update_task_tracker", "quick_call_unblock",
                         "deep_research", "send_followup_email", "review_others_work"],
            "avg_decision_time_ms": 1500,
        })
        assert s["burst_energy"] == 2

    def test_quick_decisions_score_reactivity(self):
        from focus_type.score import _score_scene_4
        s = _score_scene_4({"now": [], "tomorrow": [], "avg_decision_time_ms": 900})
        assert s["reactivity"] == 1

    def test_slow_decisions_score_deep_focus(self):
        from focus_type.score import _score_scene_4
        s = _score_scene_4({"now": [], "tomorrow": [], "avg_decision_time_ms": 3000})
        assert s["deep_focus"] == 1


class TestScene5:
    def test_leads_with_deep_work_scores_deep_focus(self):
        from focus_type.score import _score_scene_5
        s = _score_scene_5(["deep_work", "break", "wind_down"])
        assert s["deep_focus"] == 2

    def test_plan_organize_first_scores_structure_need(self):
        from focus_type.score import _score_scene_5
        s = _score_scene_5(["planning", "focused_sprint", "break"])
        assert s["structure_need"] == 2

    def test_teammate_checkin_scores_social_fuel(self):
        from focus_type.score import _score_scene_5
        s = _score_scene_5(["deep_work", "teammate_checkin", "wind_down"])
        assert s["social_fuel"] == 2

    def test_sprint_break_second_sprint_order_scores_burst_energy(self):
        from focus_type.score import _score_scene_5
        # Leading with focused_sprint also fires the +1 "leads with sprint" rule,
        # so total burst_energy = +2 (ordered sprints) + +1 (leads) = 3.
        s = _score_scene_5(["focused_sprint", "break", "second_sprint"])
        assert s["burst_energy"] == 3

    def test_no_break_scores_urgency_and_deep(self):
        from focus_type.score import _score_scene_5
        s = _score_scene_5(["deep_work", "wind_down"])
        assert s["urgency_drive"] == 1
        assert s["deep_focus"] >= 1  # +2 from leading + +1 from no break

    def test_leads_with_sprint_not_deep_work_scores_burst_energy_plus_1(self):
        from focus_type.score import _score_scene_5
        s = _score_scene_5(["focused_sprint", "wind_down"])
        assert s["burst_energy"] == 1


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class TestFocusTypeEndpoint:
    def test_valid_payload_returns_200_with_all_keys(self, client, monkeypatch):
        csrf = _register_and_login(client, monkeypatch)
        res = client.post(
            "/api/focus-type/submit",
            json=DEEP_DIVER_PAYLOAD,
            headers={"X-CSRF-TOKEN": csrf},
        )
        assert res.status_code == 200
        body = res.get_json()
        assert "archetype" in body
        assert "dimension_scores" in body
        assert "recommendations" in body
        assert isinstance(body["archetype"], str) and body["archetype"]
        assert isinstance(body["recommendations"], list) and body["recommendations"]

    def test_result_persisted_to_profile_data(self, client, monkeypatch):
        csrf = _register_and_login(client, monkeypatch, email="persist@example.com")
        client.post(
            "/api/focus-type/submit",
            json=DEEP_DIVER_PAYLOAD,
            headers={"X-CSRF-TOKEN": csrf},
        )

        from app import app
        from model import User
        with app.app_context():
            user = User.query.filter_by(email="persist@example.com").first()
            assert "focus_type_result" in (user.profile_data or {})
            saved = user.profile_data["focus_type_result"]
            assert "archetype" in saved
            assert "dimension_scores" in saved

    def test_missing_scene_returns_400(self, client, monkeypatch):
        csrf = _register_and_login(client, monkeypatch, email="missing@example.com")
        payload = {k: v for k, v in DEEP_DIVER_PAYLOAD.items() if k != "scene_3"}
        res = client.post(
            "/api/focus-type/submit",
            json=payload,
            headers={"X-CSRF-TOKEN": csrf},
        )
        assert res.status_code == 400
        assert "scene_3" in res.get_json()["error"]

    def test_unauthenticated_returns_401(self, client):
        res = client.post("/api/focus-type/submit", json=DEEP_DIVER_PAYLOAD)
        assert res.status_code == 401

    def test_all_scenes_missing_returns_400(self, client, monkeypatch):
        csrf = _register_and_login(client, monkeypatch, email="empty@example.com")
        res = client.post(
            "/api/focus-type/submit",
            json={},
            headers={"X-CSRF-TOKEN": csrf},
        )
        assert res.status_code == 400
