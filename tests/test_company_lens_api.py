"""The six-trait CompanyLens routes (C6, 2026-10-13): ``GET /me/matches``,
``GET /companies/<id>/read``, ``POST /companies/research``, ``/me/job-postings`` and
``/me/company-links``.

Against the real test database. Company evidence is written through
``company_evidence_store`` (the only door), the person side comes through the
``assessment_store`` doorway -- the six core scores are monkeypatched AT THE DOORWAY so a
test can place a person exactly, and tolerance is saved through the store -- and the
model runs for real on priors.yaml with NO ``model_run`` row and the weight source
unset, which is production's state.

The plan's Review Focus items (docs/superpowers/plans/2026-10-13-companylens-six-trait.md)
each have a test here, plus the one rule every response obeys: NO PROBABILITY ON THE
WIRE. ``_assert_no_numbers_that_look_like_scores`` walks every body for a float, a key
that looks like a score, or a percentage, and the responses of every new route go
through it.

A NOTE ON NAMES
---------------
``EvidenceItemInput`` is built positionally: its third field is the scorer's internal
copy of the text, and tests/test_company_evidence_internal.py keeps that column name out
of every file but the store and the scorer package, test files included.
"""

from __future__ import annotations

import datetime
import re

import pytest

import company_evidence_store as store
from solverah.domain.trait_preferences import TRAIT_KEYS, parse_trait_preferences
from solverah.schemas.matching import (
    CompanyLinkListResponse,
    CompanyLinkResponse,
    CompanyReadResponse,
    JobPostingResponse,
    MatchesResponse,
    ResearchRunResponse,
    ResearchRunStatus,
)
from solverah.services import company_match_content as content
from solverah.services import company_match_service as svc

PASSWORD = "Strongpass1!"
DIMS = list(TRAIT_KEYS)


@pytest.fixture(autouse=True)
def _form_token_secret(monkeypatch):
    # Read at call time in assessment_store.respondent_id_for_user, no default by
    # design (D-05); set per file, never in conftest.py.
    monkeypatch.setenv("SOLVERAH_FORM_TOKEN_SECRET", "test-secret-not-a-real-one")


@pytest.fixture(autouse=True)
def _production_weight_source(monkeypatch):
    """Production never seeds a model_run and never sets the weight source."""
    monkeypatch.delenv("SOLVERAH_MODEL_WEIGHTS_SOURCE", raising=False)


@pytest.fixture(autouse=True)
def _research_switch_on(monkeypatch):
    """The public research switch is OFF by default (C5c). The tests below exercise
    the open door unless they clear the variable themselves."""
    monkeypatch.setenv("SOLVERAH_COMPANYLENS_RESEARCH_ENABLED", "1")


def _assert_problem(resp, status, code):
    """A typed problem document: status, code slug, the problem media type."""
    body = resp.get_json()
    assert resp.status_code == status, body
    assert resp.mimetype == "application/problem+json"
    assert body["status"] == status
    assert body["type"] == "https://solverah.com/errors/%s" % code
    assert body["title"] and body["detail"]
    assert body["instance"] == resp.request.path
    return body


def _noop(*_args, **_kwargs):
    return None


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

def _register_and_login(client, monkeypatch, email="lens@example.com"):
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)
    client.post("/api/v1/auth/register", json={
        "email": email, "password": PASSWORD, "name": "Lens User", "terms_accepted": True,
    })
    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()
        user_id = user.id
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200
    return resp.get_json()["csrfToken"], user_id


def _place_person(monkeypatch, scores):
    """Every user's six core scores read as *scores* through the doorway."""
    import assessment_store

    full = {k: float(scores.get(k, 0.5)) for k in DIMS}
    monkeypatch.setattr(assessment_store, "get_dimension_scores", lambda _user_id: dict(full))


def _save_prefs(user_id, *, under=1, over=1, must=()):
    import assessment_store
    from app import app
    from model import db

    prefs = parse_trait_preferences([
        {"dimension_key": k, "under_steps": under, "over_steps": over, "must_have": k in must}
        for k in DIMS
    ])
    with app.app_context():
        assessment_store.save_trait_preferences(db, user_id, prefs)
        db.session.commit()


def _company(name, *, headcount=None):
    from app import app
    from model import Company, db

    with app.app_context():
        row = Company(
            name=name, slug=re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"),
            profile_json={"overview": {"name": name}}, headcount=headcount,
        )
        db.session.add(row)
        db.session.commit()
        return row.id


def _scorer_run(db):
    from model import ScorerRun

    run = ScorerRun(model="test-model", temperature=0, temperature_honored=True,
                    rubric_version="v3.1", packet_version="v4.11")
    db.session.add(run)
    db.session.commit()
    return run.id


def _records(company_id, spec, *, split=None):
    """Shared company-scope records for *company_id* from *spec*:
    ``{dim: ("known", estimate) | ("mixed", low, high) | ("unknown",)}``. Traits not
    named get NO record at all. Each known trait gets three dated items at the
    estimate; each mixed trait two items per side; each unknown trait one abstention.
    Returns the research run id."""
    from app import app
    from model import EvidenceItemScore, db

    with app.app_context():
        run = store.start_research_run(
            db, company_id, trigger="on_demand", provider="anthropic",
            model="claude-test", prompt_version="r1",
        )
        scorer_id = _scorer_run(db)
        inputs = []
        for dim, shape in spec.items():
            status = shape[0]
            if status == "known":
                points = [shape[1]] * 3
            elif status == "mixed":
                points = [shape[1], shape[1], shape[2], shape[2]]
            else:
                points = [None]
            labels = (["corporate", "corporate", "sites", "sites"] if status == "mixed"
                      else [None] * len(points))
            item_ids = store.write_items(
                db, company_id,
                [
                    store.EvidenceItemInput(
                        "company" if label is None else "division",
                        "employee_review",
                        "verbatim text the scorer saw %s %d" % (dim, i),
                        "A reviewer describes %s (%s, item %d)." % (dim, status, i),
                        scope_label=label,
                        published_at=datetime.date(2026, 9, 1 + i),
                    )
                    for i, label in enumerate(labels)
                ],
                research_run_id=run.id,
            )
            store.write_item_scores(
                db,
                [
                    store.ItemScoreInput(item_id, dim, score=point, abstained=point is None)
                    for item_id, point in zip(item_ids, points)
                ],
                scorer_run_id=scorer_id,
            )
            score_ids = [
                s.id for s in EvidenceItemScore.query.filter(
                    EvidenceItemScore.evidence_item_id.in_(item_ids)
                ).all()
            ]
            if status == "known":
                inputs.append(store.TraitRecordInput(
                    dimension_key=dim, scope="company", status="known",
                    estimate=shape[1], confidence=0.7, score_ids=score_ids,
                ))
            elif status == "mixed":
                inputs.append(store.TraitRecordInput(
                    dimension_key=dim, scope="company", status="mixed",
                    low_end=shape[1], high_end=shape[2], confidence=0.5,
                    split_explained_by=split, score_ids=score_ids,
                ))
            else:
                inputs.append(store.TraitRecordInput(
                    dimension_key=dim, scope="company", status="unknown",
                    score_ids=score_ids,
                ))
        store.write_trait_records(db, company_id, inputs, aggregation_version="agg-test")
        store.finish_research_run(db, run.id, status="done", cost_usd=0.1)
        return run.id


def _posting(user_id, company_id, spec, *, title="Ops Lead"):
    """A pasted posting with private role-scope records per *spec* (same shape as
    `_records`; an empty spec is a posting that abstained everywhere, i.e. six unknown
    records)."""
    from app import app
    from model import EvidenceItemScore, db

    with app.app_context():
        posting = store.create_job_posting(
            db, user_id, posting_text="Own the regional process end to end.",
            company_id=company_id, title=title,
        )
        scorer_id = _scorer_run(db)
        (item_id,) = store.write_items(
            db, company_id,
            [store.EvidenceItemInput(
                "role", "user_pasted_posting", "Own the regional process end to end.",
                "The posting says the role owns its process end to end.",
                scope_label=title, published_at=datetime.date(2026, 10, 1),
            )],
            job_posting_id=posting.id,
        )
        inputs = []
        for dim in DIMS:
            shape = spec.get(dim, ("unknown",))
            store.write_item_scores(
                db,
                [store.ItemScoreInput(
                    item_id, dim,
                    score=None if shape[0] == "unknown" else shape[1],
                    abstained=shape[0] == "unknown",
                )],
                scorer_run_id=scorer_id,
            )
            score_id = EvidenceItemScore.query.filter_by(
                evidence_item_id=item_id, dimension_key=dim
            ).one().id
            if shape[0] == "known":
                inputs.append(store.TraitRecordInput(
                    dimension_key=dim, scope="role", scope_label=title, status="known",
                    estimate=shape[1], confidence=0.6, score_ids=[score_id],
                    job_posting_id=posting.id,
                ))
            else:
                inputs.append(store.TraitRecordInput(
                    dimension_key=dim, scope="role", scope_label=title, status="unknown",
                    score_ids=[score_id], job_posting_id=posting.id,
                ))
        store.write_trait_records(db, company_id, inputs, aggregation_version="agg-test")
        store.set_job_posting_status(db, posting.id, "scored")
        return posting.id


_FORBIDDEN_KEY = re.compile(
    r"(p_fit|prob|score|percent|pct|estimate|confidence|logit|^z$|_z$|^z_)", re.IGNORECASE
)
_PERCENT = re.compile(r"\d\s*%")


def _assert_no_numbers_that_look_like_scores(body, path="$"):
    """No float anywhere, no key that names a score, no percentage in a string."""
    if isinstance(body, dict):
        for key, value in body.items():
            assert not _FORBIDDEN_KEY.search(str(key)), "%s.%s looks like a score key" % (path, key)
            _assert_no_numbers_that_look_like_scores(value, "%s.%s" % (path, key))
    elif isinstance(body, list):
        for i, value in enumerate(body):
            _assert_no_numbers_that_look_like_scores(value, "%s[%d]" % (path, i))
    elif isinstance(body, float):
        raise AssertionError("%s carries a float (%r) -- no probability on the wire" % (path, body))
    elif isinstance(body, str):
        assert not _PERCENT.search(body), "%s carries a percentage: %r" % (path, body)


def _matches(client, **params):
    query = "&".join("%s=%s" % kv for kv in params.items())
    resp = client.get("/api/v1/me/matches" + ("?" + query if query else ""))
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    MatchesResponse.model_validate(body)
    _assert_no_numbers_that_look_like_scores(body)
    return body


def _read(client, company_id, posting_id=None, expect=200):
    url = "/api/v1/companies/%d/read" % company_id
    if posting_id is not None:
        url += "?posting_id=%d" % posting_id
    resp = client.get(url)
    assert resp.status_code == expect, resp.get_json()
    body = resp.get_json()
    if expect == 200:
        CompanyReadResponse.model_validate(body)
        _assert_no_numbers_that_look_like_scores(body)
    return body


def _trait(body, dim):
    return next(t for t in body["traits"] if t["dimension"] == dim)


#: Three known traits at the midpoint: enough for a rank, no gap for a person at 0.5.
_THREE_KNOWN_FLAT = {"pace": ("known", 0.5), "collaboration": ("known", 0.5),
                     "feedback": ("known", 0.5)}


# ---------------------------------------------------------------------------
# States
# ---------------------------------------------------------------------------

def test_a_user_without_core_gets_the_core_required_state_not_a_400(client, monkeypatch):
    _register_and_login(client, monkeypatch)
    _records(_company("Acme"), {"pace": ("known", 0.5)})

    body = _matches(client)
    assert body["state"] == "core_required"
    assert body["data"] == [] and body["total_companies"] == 0

    read = _read(client, 1)
    assert read["state"] == "core_required"
    assert "traits" not in read or read["traits"] == []


def test_no_researched_companies_is_an_empty_state(client, monkeypatch):
    _register_and_login(client, monkeypatch)
    _place_person(monkeypatch, {})
    _company("Acme")  # exists, never researched

    body = _matches(client)
    assert body["state"] == "no_companies" and body["data"] == []

    read = _read(client, 1)
    assert read["state"] == "not_researched"
    assert read["research"] is None


def test_matches_requires_authentication(client):
    assert client.get("/api/v1/me/matches").status_code == 401


def test_an_unknown_company_is_a_404(client, monkeypatch):
    _register_and_login(client, monkeypatch)
    _place_person(monkeypatch, {})
    assert client.get("/api/v1/companies/999/read").status_code == 404


# ---------------------------------------------------------------------------
# Review focus: all unknown, must-have break, mixed risk, hinge at the floor
# ---------------------------------------------------------------------------

def test_an_all_unknown_company_is_not_enough_evidence_with_no_crash_and_no_midpoint(
    client, monkeypatch
):
    _, user_id = _register_and_login(client, monkeypatch)
    _place_person(monkeypatch, {"autonomy": 0.9})
    _save_prefs(user_id, must=("autonomy",))
    ghost = _company("Ghost Co")
    _records(ghost, {d: ("unknown",) for d in DIMS})

    body = _matches(client)
    [entry] = body["data"]
    assert entry["state"] == "not_enough_evidence"
    assert entry["rank"] is None
    assert entry["coverage"] == {"known": 0, "mixed": 0, "unknown": 6, "total": 6}
    assert entry["missing"] == DIMS
    # The unknown must-have is an Investigate step, with questions on the read.
    assert entry["next_step"]["category"] == "investigate"
    assert entry["flags"] == {"must_have_breaks": 0, "risks": 0, "investigate": 1}

    read = _read(client, ghost)
    assert read["state"] == "not_enough_evidence"
    autonomy = _trait(read, "autonomy")
    assert autonomy["status"] == "unknown" and autonomy["flag"] == "investigate"
    assert autonomy["direction"] is None and autonomy["within_tolerance"] is None
    assert len(autonomy["questions"]) >= 2
    assert autonomy["explanation"]
    # A non-must-have unknown trait is flagged nowhere and asks nothing.
    pace = _trait(read, "pace")
    assert pace["flag"] is None and pace["questions"] == [] and pace["explanation"]
    assert not _carries_midpoint(read)


def _carries_midpoint(body) -> bool:
    """True if any VALUE in the JSON is the midpoint (0.5, or the string "0.5").

    Walks values instead of searching the serialised text: a substring search
    for "0.5" fails about once in a hundred runs on a timestamp whose seconds
    read "...:50.5..." (found 2026-10-14 in the close-out suite run)."""
    if isinstance(body, dict):
        return any(_carries_midpoint(v) for v in body.values())
    if isinstance(body, list):
        return any(_carries_midpoint(v) for v in body)
    if isinstance(body, bool):
        return False
    if isinstance(body, (int, float)):
        return body == 0.5
    if isinstance(body, str):
        return body.strip() == "0.5"
    return False


def test_the_midpoint_check_ignores_timestamps_and_still_catches_a_midpoint():
    """Regression: the old substring check failed on a timestamp like this one."""
    stamp = {"created_at": "2026-10-14T14:07:50.512345+00:00", "coverage": {"known": 0}}
    assert "0.5" in __import__("json").dumps(stamp)  # what fooled the old check
    assert not _carries_midpoint(stamp)
    assert _carries_midpoint({"traits": [{"estimate": 0.5}]})
    assert _carries_midpoint({"traits": [{"label": "0.5"}]})


def test_a_must_have_break_on_a_known_trait_flags_and_sorts_last_never_hides(client, monkeypatch):
    """Person wants a lot of autonomy (0.9), must-have, one step of tolerance (0.25).
    Match Co offers 0.9; Break Co offers 0.3 (gap 0.6, outside); Flat Co is a close but
    not exact fit. Break Co ranks last of the three and is still listed."""
    _, user_id = _register_and_login(client, monkeypatch)
    _place_person(monkeypatch, {"autonomy": 0.9})
    _save_prefs(user_id, must=("autonomy",))
    match = _company("Match Co")
    flat = _company("Flat Co")
    broken = _company("Break Co")
    _records(match, {**_THREE_KNOWN_FLAT, "autonomy": ("known", 0.9)})
    _records(flat, {**_THREE_KNOWN_FLAT, "autonomy": ("known", 0.7)})
    _records(broken, {**_THREE_KNOWN_FLAT, "autonomy": ("known", 0.3)})

    body = _matches(client)
    names = [e["name"] for e in body["data"]]
    assert names == ["Match Co", "Flat Co", "Break Co"]
    assert [e["rank"] for e in body["data"]] == [1, 2, 3]
    last = body["data"][-1]
    assert last["flags"]["must_have_breaks"] == 1
    assert last["state"] == "ranked"
    [read] = last["must_have_reads"]
    assert read == {
        "dimension": "autonomy", "label": "Autonomy", "low_pole": "directed",
        "high_pole": "self-directed", "status": "known", "must_have": True,
        "direction": "less", "within_tolerance": False, "flag": "must_have_break",
    }
    assert last["next_step"]["category"] == "decide"
    assert body["data"][0]["must_have_reads"][0]["within_tolerance"] is True
    assert body["data"][0]["must_have_reads"][0]["direction"] == "even"
    # Flat Co: 0.2 under, inside the one-step zone, so "less" but within tolerance.
    assert body["data"][1]["must_have_reads"][0]["direction"] == "less"
    assert body["data"][1]["must_have_reads"][0]["within_tolerance"] is True


def test_a_mixed_worst_case_that_breaks_a_must_have_is_a_risk_not_a_disqualification(
    client, monkeypatch
):
    """Daniel's company: autonomy mixed, corporate (0.8) fine for him, sites (0.3) not.
    Risk flag, still ranked, both ends shown with their own evidence, nothing averaged."""
    _, user_id = _register_and_login(client, monkeypatch)
    _place_person(monkeypatch, {"autonomy": 0.9})
    _save_prefs(user_id, must=("autonomy",))
    logistics = _company("Regional Logistics", headcount=2000)
    _records(logistics, {**_THREE_KNOWN_FLAT, "autonomy": ("mixed", 0.3, 0.8)}, split="scope")

    body = _matches(client)
    [entry] = body["data"]
    assert entry["state"] == "ranked" and entry["rank"] == 1
    assert entry["flags"] == {"must_have_breaks": 0, "risks": 1, "investigate": 0}
    assert entry["coverage"] == {"known": 3, "mixed": 1, "unknown": 2, "total": 6}
    assert entry["next_step"]["category"] == "investigate"
    assert entry["size_note"].startswith("Thousands of people")

    read = _read(client, logistics)
    autonomy = _trait(read, "autonomy")
    assert autonomy["status"] == "mixed" and autonomy["flag"] == "risk"
    assert autonomy["direction"] is None and autonomy["within_tolerance"] is None
    mixed = autonomy["mixed"]
    assert mixed["low_end"]["direction"] == "less" and mixed["low_end"]["within_tolerance"] is False
    assert mixed["high_end"]["direction"] == "less" and mixed["high_end"]["within_tolerance"] is True
    assert len(mixed["low_end"]["evidence"]) == 2 and len(mixed["high_end"]["evidence"]) == 2
    assert {e["scope_label"] for e in mixed["low_end"]["evidence"]} == {"corporate"}
    assert {e["scope_label"] for e in mixed["high_end"]["evidence"]} == {"sites"}
    assert "scope" in mixed["explanation"] or "parts of the company" in mixed["explanation"]
    assert autonomy["paraphrases"] == []            # never one blended read
    assert autonomy["questions"] == content.interview_questions("autonomy", "mixed", "prefers_more")
    assert read["company"]["size_band"] == 4


def test_an_unanswered_user_gets_the_hinge_at_the_floor_and_an_answered_one_their_zone(
    client, monkeypatch
):
    """Person at 0.5 on autonomy. Near Co offers 0.6 (gap 0.1 < 0.15: inside the floor);
    Far Co offers 0.8 (gap 0.3: outside the floor, inside a two-step zone of 0.5)."""
    _, user_id = _register_and_login(client, monkeypatch)
    _place_person(monkeypatch, {})
    near = _company("Near Co")
    far = _company("Far Co")
    _records(near, {**_THREE_KNOWN_FLAT, "autonomy": ("known", 0.6)})
    _records(far, {**_THREE_KNOWN_FLAT, "autonomy": ("known", 0.8)})

    body = _matches(client)
    assert body["preferences_answered"] is False
    assert body["data"][0]["must_have_reads"] == []    # no must-haves without answers
    near_read = _trait(_read(client, near), "autonomy")
    far_read = _trait(_read(client, far), "autonomy")
    assert near_read["direction"] == "more" and near_read["within_tolerance"] is True
    assert far_read["direction"] == "more" and far_read["within_tolerance"] is False
    assert [e["name"] for e in body["data"]] == ["Near Co", "Far Co"]

    _save_prefs(user_id, under=0, over=2)
    body = _matches(client)
    assert body["preferences_answered"] is True
    assert _trait(_read(client, far), "autonomy")["within_tolerance"] is True


def test_companies_are_ordered_by_the_model_and_coverage_is_counted(client, monkeypatch):
    _register_and_login(client, monkeypatch)
    _place_person(monkeypatch, {d: 0.9 for d in DIMS})
    best = _company("Best Fit")
    worst = _company("Worst Fit")
    partial = _company("Partial")
    _records(worst, {d: ("known", 0.1) for d in DIMS})
    _records(best, {d: ("known", 0.9) for d in DIMS})
    _records(partial, {"pace": ("known", 0.9), "autonomy": ("known", 0.9)})   # 2 of 6

    body = _matches(client)
    assert [e["name"] for e in body["data"]] == ["Best Fit", "Worst Fit", "Partial"]
    assert [e["rank"] for e in body["data"]] == [1, 2, None]
    assert body["data"][0]["coverage"]["known"] == 6
    assert body["data"][2]["coverage"] == {"known": 2, "mixed": 0, "unknown": 4, "total": 6}
    assert body["data"][2]["next_step"]["category"] == "explore"
    assert body["total_companies"] == 3


def test_the_ranking_pages_with_a_cursor_that_carries_no_score(client, monkeypatch):
    _register_and_login(client, monkeypatch)
    _place_person(monkeypatch, {})
    for i in range(5):
        _records(_company("Co %d" % i), {**_THREE_KNOWN_FLAT, "autonomy": ("known", 0.1 * i + 0.3)})

    seen, cursor, pages = [], None, 0
    while True:
        pages += 1
        body = _matches(client, limit=2, **({"cursor": cursor} if cursor else {}))
        seen.extend(e["id"] for e in body["data"])
        cursor = body["next_cursor"]
        if cursor is None:
            break
        import base64
        import json

        decoded = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        assert set(decoded) == {"id", "pos"} and all(isinstance(v, int) for v in decoded.values())
    assert pages == 3 and len(seen) == 5 and len(set(seen)) == 5


def test_works_with_no_model_run_and_the_weight_source_unset(client, monkeypatch):
    from app import app
    from model import ModelRun

    _register_and_login(client, monkeypatch)
    _place_person(monkeypatch, {})
    _records(_company("Acme"), _THREE_KNOWN_FLAT)
    with app.app_context():
        assert ModelRun.query.count() == 0
    assert _matches(client)["data"][0]["rank"] == 1


def test_the_run_weight_source_without_a_run_fails_loudly_not_quietly(client, monkeypatch):
    """D-07: asked to serve a fitted run that is not there, say so."""
    import match_scoring

    _register_and_login(client, monkeypatch)
    _place_person(monkeypatch, {})
    _records(_company("Acme"), _THREE_KNOWN_FLAT)
    monkeypatch.setenv("SOLVERAH_MODEL_WEIGHTS_SOURCE", "run")
    from app import app
    from model import User

    with app.app_context():
        user = User.query.first()
        with pytest.raises(match_scoring.MatchModelError):
            svc.matches(user, cursor=None, limit=None)


# ---------------------------------------------------------------------------
# Postings: owner-only, no evidence = all unknown, disagreement
# ---------------------------------------------------------------------------

def test_a_posting_with_no_trait_evidence_reads_unknown_everywhere_with_no_disagreement(
    client, monkeypatch
):
    _, user_id = _register_and_login(client, monkeypatch)
    _place_person(monkeypatch, {"autonomy": 0.9})
    _save_prefs(user_id, must=("autonomy",))
    acme = _company("Acme")
    _records(acme, {**_THREE_KNOWN_FLAT, "autonomy": ("known", 0.9)})
    posting_id = _posting(user_id, acme, {})

    read = _read(client, acme, posting_id)
    posting = read["posting"]
    JobPostingResponse.model_validate({"posting": {k: posting[k] for k in (
        "id", "company_id", "title", "status", "created_at", "has_read")}})
    assert posting["has_read"] is True and posting["status"] == "scored"
    assert all(t["status"] == "unknown" for t in posting["traits"])
    assert all(t["disagrees"] is False for t in posting["traits"])
    assert posting["disagreements"] == []
    assert read["next_step"]["category"] == "decide"

    status = client.get("/api/v1/me/job-postings/%d" % posting_id)
    assert status.status_code == 200
    JobPostingResponse.model_validate(status.get_json())
    _assert_no_numbers_that_look_like_scores(status.get_json())


def test_a_posting_that_disagrees_with_the_company_on_a_must_have_is_shown_and_investigated(
    client, monkeypatch
):
    _, user_id = _register_and_login(client, monkeypatch)
    _place_person(monkeypatch, {"autonomy": 0.9})
    _save_prefs(user_id, must=("autonomy",))
    acme = _company("Acme")
    _records(acme, {**_THREE_KNOWN_FLAT, "autonomy": ("known", 0.9)})
    posting_id = _posting(user_id, acme, {"autonomy": ("known", 0.2), "pace": ("known", 0.5)})

    read = _read(client, acme, posting_id)
    posting = read["posting"]
    assert posting["disagreements"] == ["autonomy"]
    autonomy = next(t for t in posting["traits"] if t["dimension"] == "autonomy")
    assert autonomy["disagrees"] is True and autonomy["direction"] == "less"
    assert len(autonomy["paraphrases"]) == 1
    pace = next(t for t in posting["traits"] if t["dimension"] == "pace")
    assert pace["disagrees"] is False      # same side, 0.0 apart
    assert read["next_step"]["category"] == "investigate"
    assert "posting" in read["next_step"]["reason"]


def test_another_users_posting_is_a_404_on_both_doors(client, monkeypatch):
    _, owner_id = _register_and_login(client, monkeypatch, email="owner@example.com")
    acme = _company("Acme")
    _records(acme, _THREE_KNOWN_FLAT)
    posting_id = _posting(owner_id, acme, {})

    client.post("/api/v1/auth/logout")
    _register_and_login(client, monkeypatch, email="other@example.com")
    _place_person(monkeypatch, {})

    assert client.get("/api/v1/me/job-postings/%d" % posting_id).status_code == 404
    assert _read(client, acme, posting_id, expect=404)
    # The posting is still there for its owner.
    client.post("/api/v1/auth/logout")
    _register_and_login(client, monkeypatch, email="owner@example.com")
    assert client.get("/api/v1/me/job-postings/%d" % posting_id).status_code == 200


def test_submitting_a_posting_needs_the_scorer_and_a_real_company(client, monkeypatch):
    csrf, _ = _register_and_login(client, monkeypatch)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    acme = _company("Acme")
    headers = {"X-CSRF-TOKEN": csrf}

    resp = client.post("/api/v1/me/job-postings",
                       json={"company_id": acme, "text": "Own it."}, headers=headers)
    body = _assert_problem(resp, 503, "provider_unavailable")
    assert body["detail"] == "Posting scoring is not available right now."
    # The research switch does not gate postings: still the scorer's 503, not research_disabled.
    monkeypatch.delenv("SOLVERAH_COMPANYLENS_RESEARCH_ENABLED")
    resp = client.post("/api/v1/me/job-postings",
                       json={"company_id": acme, "text": "Own it."}, headers=headers)
    _assert_problem(resp, 503, "provider_unavailable")
    resp = client.post("/api/v1/me/job-postings",
                       json={"company_id": 999, "text": "Own it."}, headers=headers)
    assert resp.status_code in (400, 503)
    resp = client.post("/api/v1/me/job-postings",
                       json={"company_id": acme, "text": ""}, headers=headers)
    assert resp.status_code == 422


def test_submitting_a_posting_queues_its_scoring(client, monkeypatch):
    from tests.test_company_research_pipeline import FakeScorerClient
    from solverah.infra import llm

    csrf, _ = _register_and_login(client, monkeypatch)
    _place_person(monkeypatch, {})
    acme = _company("Acme")
    monkeypatch.setattr(llm, "get_scorer_client", lambda: FakeScorerClient(
        extraction_items=[], scores=[],
    ))
    resp = client.post(
        "/api/v1/me/job-postings",
        json={"company_id": acme, "text": "Requirements: 5 years of SQL.", "title": "Analyst"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 202, resp.get_json()
    body = resp.get_json()
    JobPostingResponse.model_validate(body)
    _assert_no_numbers_that_look_like_scores(body)
    assert body["posting"]["company_id"] == acme
    assert body["posting"]["status"] in ("pending", "scored")


# ---------------------------------------------------------------------------
# Research: 202, cached hits, the per-user limit, 503 without a provider
# ---------------------------------------------------------------------------

def test_research_without_a_provider_is_a_503_and_nothing_is_written(client, monkeypatch):
    csrf, _ = _register_and_login(client, monkeypatch)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    resp = client.post("/api/v1/companies/research", json={"name": "Acme"},
                       headers={"X-CSRF-TOKEN": csrf})
    body = _assert_problem(resp, 503, "provider_unavailable")
    assert body["detail"] == "Company research is not available right now."
    from app import app
    from model import Company, CompanyResearchRun

    with app.app_context():
        assert CompanyResearchRun.query.count() == 0
        assert Company.query.filter_by(slug="acme").count() == 0  # not even the company

    resp = client.post("/api/v1/companies/research", json={"name": ""},
                       headers={"X-CSRF-TOKEN": csrf})
    assert resp.status_code == 422
    assert client.get("/api/v1/companies/research/999").status_code == 404


def test_research_switched_off_is_a_503_problem_and_cached_runs_are_still_served(client, monkeypatch):
    """`SOLVERAH_COMPANYLENS_RESEARCH_ENABLED` is the public switch (C5c): off, a new
    run is refused with `research_disabled` and nothing is written -- even with both
    provider keys present; a company with a done run is still answered, cached."""
    csrf, _ = _register_and_login(client, monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-real")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    _install_fakes(monkeypatch)
    monkeypatch.delenv("SOLVERAH_COMPANYLENS_RESEARCH_ENABLED")
    headers = {"X-CSRF-TOKEN": csrf}

    resp = client.post("/api/v1/companies/research", json={"name": "Fresh Co"}, headers=headers)
    body = _assert_problem(resp, 503, "research_disabled")
    assert body["title"] == "Research disabled"
    assert body["detail"] == (
        "Company research is switched off on this server. Companies already "
        "researched can still be read."
    )
    assert "request_id" in body
    from app import app
    from model import Company, CompanyResearchRun

    with app.app_context():
        assert CompanyResearchRun.query.count() == 0
        assert Company.query.filter_by(slug="fresh-co").count() == 0

    # A cached done run is read, not gated.
    cached = _company("Cached Co")
    run_id = _records(cached, {"pace": ("known", 0.8)})
    resp = client.post("/api/v1/companies/research", json={"name": "Cached Co"}, headers=headers)
    assert resp.status_code == 202, resp.get_json()
    assert resp.get_json()["cached"] is True
    assert resp.get_json()["run"]["run_id"] == run_id
    assert resp.get_json()["run"]["status"] == "done"
    # An in-flight run is read as is too.
    with app.app_context():
        import company_evidence_store as store
        from model import db

        flight = _company("In Flight Co")
        queued = store.start_research_run(
            db, flight, trigger="on_demand", provider="anthropic", model="m",
            prompt_version="v", status="queued",
        ).id
    resp = client.post("/api/v1/companies/research", json={"name": "In Flight Co"}, headers=headers)
    assert resp.status_code == 202 and resp.get_json()["cached"] is False
    assert resp.get_json()["run"]["run_id"] == queued
    assert resp.get_json()["run"]["status"] == "queued"
    # Polling never needed the switch.
    assert client.get("/api/v1/companies/research/%d" % run_id).status_code == 200

    # Switch on: the same request starts a run.
    monkeypatch.setenv("SOLVERAH_COMPANYLENS_RESEARCH_ENABLED", "true")
    resp = client.post("/api/v1/companies/research", json={"name": "Fresh Co"}, headers=headers)
    assert resp.status_code == 202, resp.get_json()
    assert resp.get_json()["cached"] is False
    assert resp.get_json()["run"]["status"] == "done"


def _install_fakes(monkeypatch):
    from tests.test_company_research_pipeline import (
        FakeResearchClient, FakeScorerClient, _research_message,
    )
    from solverah.infra import llm

    research = FakeResearchClient(*[_research_message() for _ in range(20)])
    scorer = FakeScorerClient(scores=[{"pace": 0.9}] * 60)
    monkeypatch.setattr(llm, "get_research_client", lambda: research)
    monkeypatch.setattr(llm, "get_scorer_client", lambda: scorer)


def test_research_answers_202_runs_inline_and_a_repeat_is_a_free_cached_hit(client, monkeypatch):
    csrf, _ = _register_and_login(client, monkeypatch)
    _install_fakes(monkeypatch)

    resp = client.post("/api/v1/companies/research", json={"name": "Acme Corp"},
                       headers={"X-CSRF-TOKEN": csrf})
    assert resp.status_code == 202, resp.get_json()
    body = resp.get_json()
    ResearchRunResponse.model_validate(body)
    _assert_no_numbers_that_look_like_scores(body)
    assert body["cached"] is False
    assert body["run"]["status"] == "done"          # eager + TESTING: ran inline
    assert body["run"]["company"]["name"] == "Acme Corp"
    run_id = body["run"]["run_id"]

    poll = client.get("/api/v1/companies/research/%d" % run_id)
    assert poll.status_code == 200
    ResearchRunStatus.model_validate(poll.get_json())
    _assert_no_numbers_that_look_like_scores(poll.get_json())

    again = client.post("/api/v1/companies/research", json={"name": "Acme Corp"},
                        headers={"X-CSRF-TOKEN": csrf})
    assert again.status_code == 202
    assert again.get_json()["cached"] is True
    assert again.get_json()["run"]["run_id"] == run_id


@pytest.fixture()
def enforcing(client):
    """A client with the TESTING rate-limit exemption switched off, research still
    inline."""
    from app import app
    from solverah.extensions import limiter

    limiter.reset()
    app.config["TESTING"] = False
    app.config["COMPANY_RESEARCH_INLINE"] = True
    try:
        yield client
    finally:
        app.config["TESTING"] = True
        app.config.pop("COMPANY_RESEARCH_INLINE", None)
        limiter.reset()


def test_each_user_may_start_five_new_research_runs_a_day_and_cached_hits_are_free(
    enforcing, monkeypatch
):
    client = enforcing
    csrf, _ = _register_and_login(client, monkeypatch)
    _install_fakes(monkeypatch)
    headers = {"X-CSRF-TOKEN": csrf}

    for i in range(5):
        resp = client.post("/api/v1/companies/research", json={"name": "Fresh %d" % i},
                           headers=headers)
        assert resp.status_code == 202, (i, resp.get_json())
    # A sixth cached hit is free...
    resp = client.post("/api/v1/companies/research", json={"name": "Fresh 0"}, headers=headers)
    assert resp.status_code == 202 and resp.get_json()["cached"] is True
    # ...a sixth NEW run is not.
    resp = client.post("/api/v1/companies/research", json={"name": "Fresh 5"}, headers=headers)
    assert resp.status_code == 429
    from app import app
    from model import CompanyResearchRun

    with app.app_context():
        assert CompanyResearchRun.query.count() == 5

    # Another user has their own budget.
    client.post("/api/v1/auth/logout")
    csrf2, _ = _register_and_login(client, monkeypatch, email="second@example.com")
    resp = client.post("/api/v1/companies/research", json={"name": "Fresh 5"},
                       headers={"X-CSRF-TOKEN": csrf2})
    assert resp.status_code == 202


# ---------------------------------------------------------------------------
# "I took this job"
# ---------------------------------------------------------------------------

def test_company_links_round_trip_and_are_owner_only(client, monkeypatch):
    csrf, _ = _register_and_login(client, monkeypatch)
    acme = _company("Acme")
    headers = {"X-CSRF-TOKEN": csrf}

    resp = client.post("/api/v1/me/company-links",
                       json={"company_id": acme, "started_on": "2026-11-02"}, headers=headers)
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    CompanyLinkResponse.model_validate(body)
    _assert_no_numbers_that_look_like_scores(body)
    link_id = body["link"]["id"]
    assert body["link"]["started_on"] == "2026-11-02" and body["link"]["ended_on"] is None
    assert body["link"]["company"]["name"] == "Acme"

    listing = client.get("/api/v1/me/company-links")
    assert listing.status_code == 200
    CompanyLinkListResponse.model_validate(listing.get_json())
    assert [l["id"] for l in listing.get_json()["data"]] == [link_id]

    assert client.post("/api/v1/me/company-links",
                       json={"company_id": 999, "started_on": "2026-11-02"},
                       headers=headers).status_code == 404
    assert client.post("/api/v1/me/company-links",
                       json={"company_id": acme, "started_on": "not-a-date"},
                       headers=headers).status_code == 422

    client.post("/api/v1/auth/logout")
    csrf2, _ = _register_and_login(client, monkeypatch, email="other@example.com")
    assert client.get("/api/v1/me/company-links").get_json()["data"] == []
    assert client.delete("/api/v1/me/company-links/%d" % link_id,
                         headers={"X-CSRF-TOKEN": csrf2}).status_code == 404

    client.post("/api/v1/auth/logout")
    csrf, _ = _register_and_login(client, monkeypatch)
    assert client.delete("/api/v1/me/company-links/%d" % link_id,
                         headers={"X-CSRF-TOKEN": csrf}).status_code == 200
    assert client.get("/api/v1/me/company-links").get_json()["data"] == []


# ---------------------------------------------------------------------------
# The content bank and the next-step rule
# ---------------------------------------------------------------------------

def test_the_question_bank_covers_every_cell_with_two_to_three_questions():
    for trait in DIMS:
        for status in (content.STATUS_UNKNOWN, content.STATUS_MIXED):
            for direction in (content.PREFERS_MORE, content.PREFERS_LESS):
                questions = content.interview_questions(trait, status, direction)
                assert 2 <= len(questions) <= 3 and all(q.strip() for q in questions)
                assert content.explanation(trait, status, direction).strip()
    assert content.direction_for_person(0.5) == content.PREFERS_MORE
    assert content.direction_for_person(0.49) == content.PREFERS_LESS
    assert set(content.NEXT_STEPS) == {"decide", "investigate", "prepare", "explore", "act",
                                       "dont_act_yet"}
    for band in (None, 1, 2, 3, 4, 5):
        assert content.size_note(band)


def test_the_worst_case_over_mixed_traits_is_the_worse_end_never_the_average(client, monkeypatch):
    """Two companies identical except autonomy: Mixed Co is mixed (0.1, 0.9) and Low Co
    is known at 0.1. For a person who wants 0.9, Mixed Co's worst case IS Low Co, so
    the two tie on z and Low Co (the lower id) comes first -- an average (0.5) would
    have put Mixed Co clearly ahead."""
    _register_and_login(client, monkeypatch)
    _place_person(monkeypatch, {"autonomy": 0.9})
    low = _company("Low Co")
    mixed = _company("Mixed Co")
    _records(low, {**_THREE_KNOWN_FLAT, "autonomy": ("known", 0.1)})
    _records(mixed, {**_THREE_KNOWN_FLAT, "autonomy": ("mixed", 0.1, 0.9)})

    from app import app
    from model import User

    with app.app_context():
        user = User.query.first()
        person = svc._person_side(user.id)
        evals = svc._evaluate([low, mixed], person)
    by_name = {ev.name: ev for ev in evals}
    assert by_name["Mixed Co"].z == pytest.approx(by_name["Low Co"].z)
    assert [e["name"] for e in _matches(client)["data"]] == ["Low Co", "Mixed Co"]


def test_patch_company_link_sets_ended_on(client, monkeypatch):
    csrf, _ = _register_and_login(client, monkeypatch)
    acme = _company("Acme")
    headers = {"X-CSRF-TOKEN": csrf}
    link_id = client.post("/api/v1/me/company-links",
                          json={"company_id": acme, "started_on": "2026-11-02"},
                          headers=headers).get_json()["link"]["id"]
    url = "/api/v1/me/company-links/%d" % link_id

    assert client.patch(url, json={"ended_on": "2026-10-01"},
                        headers=headers).status_code == 422
    assert client.patch(url, json={"ended_on": "soon"}, headers=headers).status_code == 422
    resp = client.patch(url, json={"ended_on": "2026-12-01"}, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    CompanyLinkResponse.model_validate(resp.get_json())
    assert resp.get_json()["link"]["ended_on"] == "2026-12-01"

    client.post("/api/v1/auth/logout")
    csrf2, _ = _register_and_login(client, monkeypatch, email="other2@example.com")
    assert client.patch(url, json={"ended_on": "2026-12-05"},
                        headers={"X-CSRF-TOKEN": csrf2}).status_code == 404
