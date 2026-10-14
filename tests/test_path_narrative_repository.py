"""``path_narratives`` -- the narrator's sentences, stored by input fingerprint (W-16).

The repository's four promises, each against the real Postgres table:

* a read is a hit only for the SAME fingerprint and only inside ``MAX_AGE``;
* a write upserts on (user, code, fingerprint), so two narrations converge;
* the purge removes exactly what the read rule already refuses to serve;
* account deletion destroys every row (D-7b), and a narration still in flight
  when the account is deleted writes none back.

The API-level behaviour -- that a re-sort reads these instead of calling the
narrator -- lives in ``tests/test_path_suggestions_api.py``.
"""
from __future__ import annotations

import datetime

import pytest


@pytest.fixture()
def user_id(client):
    from app import app
    from model import User, db

    with app.app_context():
        user = User(email="narratives@example.com", password_hash="x", name="N")
        db.session.add(user)
        db.session.commit()
        return user.id


def _store(user_id, rows):
    from app import app
    from model import db
    from solverah.repositories import path_narrative_repository

    with app.app_context():
        path_narrative_repository.store_many(user_id, rows)
        db.session.commit()


def _read(user_id, fingerprints):
    from app import app
    from solverah.repositories import path_narrative_repository

    with app.app_context():
        return path_narrative_repository.read_many(user_id, fingerprints)


def test_a_read_is_a_hit_only_for_the_same_fingerprint(user_id):
    _store(user_id, {"15-1252.00": ("fp-a", "Uses your Python.", ["Builds on Python", "Fits"])})

    assert _read(user_id, {"15-1252.00": "fp-a"}) == {
        "15-1252.00": {
            "why_text": "Uses your Python.",
            "profile_dimensions": ["Builds on Python", "Fits"],
        }
    }
    assert _read(user_id, {"15-1252.00": "fp-b"}) == {}, "a moved input is a miss"
    assert _read(user_id, {"15-1211.00": "fp-a"}) == {}
    assert _read(user_id, {}) == {}


def test_a_new_fingerprint_is_a_new_row_and_the_old_one_is_found_again(user_id):
    """Going back to an earlier profile finds its sentence again -- unlike
    path_fits, a new key does not overwrite the old one."""
    _store(user_id, {"15-1252.00": ("fp-a", "First.", ["a", "b"])})
    _store(user_id, {"15-1252.00": ("fp-b", "Second.", ["c", "d"])})

    assert _read(user_id, {"15-1252.00": "fp-a"})["15-1252.00"]["why_text"] == "First."
    assert _read(user_id, {"15-1252.00": "fp-b"})["15-1252.00"]["why_text"] == "Second."


def test_the_same_key_twice_upserts_rather_than_failing(user_id):
    """Two overlapping narrations of one user converge on one row."""
    from app import app
    from solverah.repositories import path_narrative_repository

    _store(user_id, {"15-1252.00": ("fp-a", "First.", ["a", "b"])})
    _store(user_id, {"15-1252.00": ("fp-a", "Rewritten.", ["c", "d"])})

    with app.app_context():
        rows = path_narrative_repository.list_for_user(user_id)
    assert [(r.why_text, r.profile_dimensions) for r in rows] == [("Rewritten.", ["c", "d"])]


def _age_all_rows(user_id, days):
    from app import app
    from model import PathNarrative, db

    with app.app_context():
        for row in PathNarrative.query.filter_by(user_id=user_id).all():
            row.created_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
                days=days
            )
        db.session.commit()


def test_a_row_past_max_age_is_a_miss_and_the_purge_removes_it(user_id):
    from app import app
    from model import db
    from solverah.repositories import path_narrative_repository

    _store(user_id, {
        "15-1252.00": ("fp-a", "Old.", ["a", "b"]),
    })
    _age_all_rows(user_id, 31)
    _store(user_id, {"15-1211.00": ("fp-b", "New.", ["c", "d"])})

    assert _read(user_id, {"15-1252.00": "fp-a", "15-1211.00": "fp-b"}) == {
        "15-1211.00": {"why_text": "New.", "profile_dimensions": ["c", "d"]}
    }

    with app.app_context():
        purged = path_narrative_repository.purge_older_than()
        db.session.commit()
        left = [r.onet_code for r in path_narrative_repository.list_for_user(user_id)]
    assert purged == 1
    assert left == ["15-1211.00"]


def test_account_deletion_destroys_every_stored_sentence(user_id):
    """D-7b: `why_text` is prose about the person."""
    from app import app
    from model import db
    from solverah.repositories import account_repository, path_narrative_repository

    _store(user_id, {
        "15-1252.00": ("fp-a", "Uses your Python.", ["a", "b"]),
        "15-1211.00": ("fp-a", "Uses your SQL.", ["c", "d"]),
    })

    with app.app_context():
        account_repository.delete_personal_rows(user_id, [])
        db.session.commit()
        assert path_narrative_repository.list_for_user(user_id) == []


def test_a_narration_that_lands_after_deletion_stores_nothing(user_id, monkeypatch):
    """The narration was already out when the account was deleted; its rows must
    not be written back a second after the deletion destroyed them."""
    import backend.services.path_narrative as pn
    from app import app
    from backend.services.path_narrative import PathSuggestion, UserContext
    from backend.services.path_scoring import ScoredPath
    from model import db
    from solverah.repositories import path_narrative_repository, profile_repository
    from solverah.services import intelligence_service

    monkeypatch.setattr(
        pn,
        "generate_narratives",
        lambda cands, _ctx: [
            PathSuggestion(onet_code=c.onet_code, title=c.title, why_text="Written.",
                           profile_dimensions=["a", "b"])
            for c in cands
        ],
    )
    card = ScoredPath(onet_code="15-1252.00", title="Devs", score=0.5, overlapping_skills=["SQL"])
    ctx = UserContext(archetype="", management_preferences={}, career_status="employed",
                      top_skills=["SQL"])
    payload = {"suggestions": [intelligence_service._card(card, None)], "narration_pending": True}

    with app.app_context():
        narration = intelligence_service._narration_phase(
            user_id=user_id, token="t", context=ctx, payload=payload, misses=[card],
            stored={}, fingerprints={"15-1252.00": "fp"}, logger=app.logger,
        )
        profile_repository.update_document(user_id, lambda _e: {"deleted_at": "2026-09-28T00:00:00Z"})
        db.session.commit()
        final = narration()
        assert path_narrative_repository.list_for_user(user_id) == []

    assert final["suggestions"][0]["why_text"] == "Written.", "still shown to the page"


def test_a_waiting_narration_holds_no_database_connection(user_id, monkeypatch):
    """W-17: the narration ends its read transaction before it waits.

    A session holds its pooled connection until its transaction ends. Since W-17
    up to `NARRATION_WORKERS` (16) narrations wait on the narrator at once, and
    the pool is 10 + 5 overflow shared with the 8 request threads -- so a
    narration that waited inside its read transaction could starve the requests.
    Checked on the orchestrating thread, at the moment it starts waiting.
    """
    import backend.services.path_narrative as pn
    from app import app
    from backend.services.path_narrative import UserContext
    from backend.services.path_scoring import ScoredPath
    from model import db
    from solverah.services import intelligence_service

    seen = []

    def narrate_page_first(head, tail, ctx, on_landed=None):
        seen.append(db.session().in_transaction())
        return []

    monkeypatch.setattr(pn, "narrate_page_first", narrate_page_first)
    card = ScoredPath(onet_code="15-1252.00", title="Devs", score=0.5, overlapping_skills=["SQL"])
    ctx = UserContext(archetype="", management_preferences={}, career_status="employed",
                      top_skills=["SQL"])
    payload = {"suggestions": [intelligence_service._card(card, None)], "narration_pending": True}

    with app.app_context():
        narration = intelligence_service._narration_phase(
            user_id=user_id, token="t", context=ctx, payload=payload, misses=[card],
            stored={}, fingerprints={"15-1252.00": "fp"}, logger=app.logger,
        )
        narration()

    assert seen == [False]
