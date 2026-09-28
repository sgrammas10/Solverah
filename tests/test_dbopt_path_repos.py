"""DB-ledger Package D2: the path repositories and the Situation Report pin store
write with one ``INSERT ... ON CONFLICT DO UPDATE`` instead of reading the row
first and then inserting or updating it.

Three promises, each against the real Postgres table:

* the first call inserts, the second updates, and neither sends a SELECT;
* a row another connection commits AFTER the old code's read and BEFORE its
  write is updated rather than tripped over -- the double-tap race, which
  select-then-insert loses with an IntegrityError on the unique key;
* ``path_wants_repository.set_answers`` sends as many statements for twelve
  answers as for two.

The race tests commit the competing row from a hook on the session's first
INSERT into the table, not before the call: a row committed before the call
would be seen by the old code's own SELECT, and the test could not fail.
"""
from __future__ import annotations

import contextlib

import pytest
import sqlalchemy as sa

CODE = "15-1252.00"
OTHER_CODE = "15-1211.00"
ANCHOR = "15-1252.00"


@pytest.fixture()
def user_id(client):
    from app import app
    from model import User, db

    with app.app_context():
        user = User(email="dbopt-d2@example.com", password_hash="x", name="D2")
        db.session.add(user)
        db.session.commit()
        return user.id


def _is_read(statement: str) -> bool:
    return statement.lstrip().upper().startswith("SELECT")


def _assert_one_upsert(statements, table):
    """Exactly one statement was sent: an INSERT ... ON CONFLICT into *table*."""
    assert [s for s in statements if _is_read(s)] == [], "read before write: %r" % statements
    assert len(statements) == 1, statements
    assert statements[0].startswith("INSERT INTO %s " % table), statements[0]
    assert "ON CONFLICT" in statements[0], statements[0]


def _backdate(sql, **params):
    """Move stored timestamps a day back, so the next write's "now" is visibly later."""
    from model import db

    db.session.execute(sa.text(sql), params)
    db.session.commit()


@contextlib.contextmanager
def _row_committed_before_first_insert(table, sql, params):
    """Commit *sql* from a second connection just before this session's first
    INSERT into *table* -- after any SELECT the code under test sent first.

    Select-then-insert has already decided "no row" when this fires, so its
    INSERT meets the committed row and raises IntegrityError. An upsert updates
    that row instead. Yields the statements the hook fired on, so a test can
    prove the competitor really was committed.

    The second connection is opened up front, so the hook itself only executes
    and commits -- no connect happens inside the statement under test.
    """
    from sqlalchemy import event

    from model import db

    engine = db.engine
    fired = []

    def _commit_competitor(conn, cursor, statement, parameters, context, executemany):
        if fired or not statement.startswith("INSERT INTO %s " % table):
            return
        fired.append(statement)  # before executing, so the competitor's own INSERT skips this
        other.execute(sa.text(sql), params)
        other.commit()

    with engine.connect() as other:
        event.listen(engine, "before_cursor_execute", _commit_competitor)
        try:
            yield fired
        finally:
            event.remove(engine, "before_cursor_execute", _commit_competitor)


# ---------------------------------------------------------------------------
# path_fit_repository.store
# ---------------------------------------------------------------------------


def test_store_inserts_then_updates_with_one_statement_and_no_read(user_id):
    from app import app
    from model import PathFit, db
    from solverah.repositories import path_fit_repository
    from tests.query_count import count_queries

    with app.app_context():
        with count_queries() as first:
            path_fit_repository.store(user_id, CODE, {"fit_score": 0.5}, "a" * 64)
        _assert_one_upsert(first, "path_fits")
        db.session.commit()
        original_id = PathFit.query.filter_by(user_id=user_id).one().id

        _backdate(
            "UPDATE path_fits SET computed_at = computed_at - interval '1 day' "
            "WHERE user_id = :u",
            u=user_id,
        )
        backdated = PathFit.query.filter_by(user_id=user_id).one().computed_at

        with count_queries() as second:
            path_fit_repository.store(user_id, CODE, {"fit_score": 0.9}, "b" * 64)
        _assert_one_upsert(second, "path_fits")
        db.session.commit()

        rows = PathFit.query.filter_by(user_id=user_id).all()
        assert len(rows) == 1
        assert rows[0].id == original_id, "updated in place, not replaced"
        assert rows[0].payload == {"fit_score": 0.9}
        assert rows[0].profile_fingerprint == "b" * 64
        assert rows[0].computed_at > backdated


def test_store_refreshes_the_row_read_already_loaded(user_id):
    """``path_fit``'s own sequence in one session: ``read()`` loads the stale row,
    ``store()`` replaces it, and the session must not keep serving the old fit."""
    from app import app
    from model import db
    from solverah.repositories import path_fit_repository

    with app.app_context():
        path_fit_repository.store(user_id, CODE, {"fit_score": 0.5}, "a" * 64)
        db.session.commit()

    with app.app_context():
        assert path_fit_repository.read(user_id, CODE, "b" * 64) is None  # stale
        path_fit_repository.store(user_id, CODE, {"fit_score": 0.9}, "b" * 64)
        assert path_fit_repository.read(user_id, CODE, "b" * 64) == {"fit_score": 0.9}
        db.session.rollback()


def test_store_survives_a_fit_committed_between_read_and_write(user_id):
    from app import app
    from model import PathFit, db
    from solverah.repositories import path_fit_repository

    with app.app_context():
        with _row_committed_before_first_insert(
            "path_fits",
            "INSERT INTO path_fits "
            "(user_id, onet_code, payload, profile_fingerprint, computed_at) "
            "VALUES (:u, :c, CAST(:p AS jsonb), :f, now())",
            {"u": user_id, "c": CODE, "p": '{"fit_score": 0.1}', "f": "c" * 64},
        ) as fired:
            path_fit_repository.store(user_id, CODE, {"fit_score": 0.9}, "d" * 64)
            db.session.commit()
        assert fired, "the competing row was never committed; the test proved nothing"

    with app.app_context():
        rows = PathFit.query.filter_by(user_id=user_id).all()
        assert [(r.payload, r.profile_fingerprint) for r in rows] == [
            ({"fit_score": 0.9}, "d" * 64)
        ]


# ---------------------------------------------------------------------------
# path_feedback_repository.record / verdicts_for_user
# ---------------------------------------------------------------------------


def test_record_inserts_then_updates_with_one_statement_and_no_read(user_id):
    from app import app
    from model import PathFeedback, db
    from solverah.repositories import path_feedback_repository
    from tests.query_count import count_queries

    with app.app_context():
        with count_queries() as first:
            row = path_feedback_repository.record(user_id, CODE, "interesting")
        _assert_one_upsert(first, "path_feedback")
        assert isinstance(row, PathFeedback)
        assert (row.user_id, row.onet_code, row.verdict) == (user_id, CODE, "interesting")
        db.session.commit()
        original_id = PathFeedback.query.filter_by(user_id=user_id).one().id

        _backdate(
            "UPDATE path_feedback SET created_at = created_at - interval '1 day', "
            "updated_at = updated_at - interval '1 day' WHERE user_id = :u",
            u=user_id,
        )
        before = PathFeedback.query.filter_by(user_id=user_id).one()
        created, updated = before.created_at, before.updated_at

        with count_queries() as second:
            row = path_feedback_repository.record(user_id, CODE, "too_similar")
        _assert_one_upsert(second, "path_feedback")
        assert row.verdict == "too_similar"
        db.session.commit()

        rows = PathFeedback.query.filter_by(user_id=user_id).all()
        assert len(rows) == 1
        assert rows[0].id == original_id, "a re-tap corrects the row, not a second one"
        assert rows[0].verdict == "too_similar"
        assert rows[0].created_at == created, "created_at keeps the first tap"
        assert rows[0].updated_at > updated, "updated_at moves on a correction"


def test_record_survives_a_tap_committed_between_read_and_write(user_id):
    from app import app
    from model import PathFeedback, db
    from solverah.repositories import path_feedback_repository

    with app.app_context():
        with _row_committed_before_first_insert(
            "path_feedback",
            "INSERT INTO path_feedback (user_id, onet_code, verdict, created_at, updated_at) "
            "VALUES (:u, :c, 'interesting', now(), now())",
            {"u": user_id, "c": CODE},
        ) as fired:
            path_feedback_repository.record(user_id, CODE, "too_similar")
            db.session.commit()
        assert fired, "the competing row was never committed; the test proved nothing"

    with app.app_context():
        rows = PathFeedback.query.filter_by(user_id=user_id).all()
        assert [(r.onet_code, r.verdict) for r in rows] == [(CODE, "too_similar")]


def test_verdicts_for_user_selects_only_the_two_columns(user_id):
    from app import app
    from model import db
    from solverah.repositories import path_feedback_repository
    from tests.query_count import count_queries

    with app.app_context():
        path_feedback_repository.record(user_id, CODE, "interesting")
        path_feedback_repository.record(user_id, OTHER_CODE, "not_for_me")
        db.session.commit()

    with app.app_context():
        with count_queries() as statements:
            verdicts = path_feedback_repository.verdicts_for_user(user_id)

    assert verdicts == {CODE: "interesting", OTHER_CODE: "not_for_me"}
    assert len(statements) == 1, statements
    select_list = statements[0].split("FROM", 1)[0]
    assert "path_feedback.onet_code" in select_list
    assert "path_feedback.verdict" in select_list
    for column in ("id", "user_id", "created_at", "updated_at"):
        assert "path_feedback.%s " % column not in select_list, select_list


# ---------------------------------------------------------------------------
# situation_report_pin_store.set_pin
# ---------------------------------------------------------------------------


def test_set_pin_inserts_then_moves_with_one_statement_and_no_read(user_id):
    import situation_report_pin_store as pins
    from app import app
    from model import SituationReportPin, db
    from tests.query_count import count_queries

    with app.app_context():
        with count_queries() as first:
            placed = pins.set_pin(db, user_id, "a" * 32)
        _assert_one_upsert(first, "situation_report_pins")
        db.session.commit()
        stored = SituationReportPin.query.filter_by(user_id=user_id).one()
        assert placed == {
            "user_id": user_id,
            "submission_id": "a" * 32,
            "pinned_at": stored.pinned_at.isoformat(),
        }
        original_id = stored.id

        _backdate(
            "UPDATE situation_report_pins SET pinned_at = pinned_at - interval '1 day' "
            "WHERE user_id = :u",
            u=user_id,
        )
        backdated = SituationReportPin.query.filter_by(user_id=user_id).one().pinned_at

        with count_queries() as second:
            moved = pins.set_pin(db, user_id, "b" * 32)
        _assert_one_upsert(second, "situation_report_pins")
        db.session.commit()

        rows = SituationReportPin.query.filter_by(user_id=user_id).all()
        assert len(rows) == 1
        assert rows[0].id == original_id, "moved in place, not a second row"
        assert moved == {
            "user_id": user_id,
            "submission_id": "b" * 32,
            "pinned_at": rows[0].pinned_at.isoformat(),
        }
        assert rows[0].pinned_at > backdated


def test_set_pin_refreshes_the_pin_explicit_pin_already_loaded(user_id):
    """``recalibrate``'s own sequence: ``explicit_pin()`` loads the row, ``set_pin()``
    moves it, and a read later in the same session sees where it moved to."""
    import situation_report_pin_store as pins
    from app import app
    from model import db

    with app.app_context():
        pins.set_pin(db, user_id, "a" * 32)
        db.session.commit()

    with app.app_context():
        assert pins.explicit_pin(user_id)["submission_id"] == "a" * 32
        pins.set_pin(db, user_id, "b" * 32)
        assert pins.explicit_pin(user_id)["submission_id"] == "b" * 32
        db.session.rollback()


def test_set_pin_survives_a_pin_committed_between_read_and_write(user_id):
    import situation_report_pin_store as pins
    from app import app
    from model import SituationReportPin, db

    with app.app_context():
        with _row_committed_before_first_insert(
            "situation_report_pins",
            "INSERT INTO situation_report_pins (user_id, submission_id, pinned_at) "
            "VALUES (:u, :s, now())",
            {"u": user_id, "s": "b" * 32},
        ) as fired:
            pins.set_pin(db, user_id, "c" * 32)
            db.session.commit()
        assert fired, "the competing row was never committed; the test proved nothing"

    with app.app_context():
        rows = SituationReportPin.query.filter_by(user_id=user_id).all()
        assert [r.submission_id for r in rows] == ["c" * 32]


# ---------------------------------------------------------------------------
# path_wants_repository.set_answer / set_answers
# ---------------------------------------------------------------------------

#: One O*NET-style statement and a rewording with the same normalised digest --
#: the sidecar-rebuild case ``set_answer`` rewrites ``item_text`` for.
STATEMENT = "Write  and review CODE."
REWORDED = "Write and review code."


def test_set_answer_inserts_updates_and_clears_with_one_statement_and_no_read(user_id):
    from app import app
    from model import PathWant, db
    from solverah.repositories import path_wants_repository as wants
    from tests.query_count import count_queries

    key = wants.item_key_for_task(STATEMENT)
    assert wants.item_key_for_task(REWORDED) == key

    with app.app_context():
        with count_queries() as inserted:
            row = wants.set_answer(user_id, ANCHOR, wants.KIND_TASK, key, "more", STATEMENT)
        _assert_one_upsert(inserted, "path_wants")
        assert isinstance(row, PathWant)
        assert (row.kind, row.item_key, row.verdict, row.item_text) == (
            "task", key, "more", STATEMENT
        )
        db.session.commit()
        original_id = PathWant.query.filter_by(user_id=user_id).one().id

        _backdate(
            "UPDATE path_wants SET created_at = created_at - interval '1 day', "
            "updated_at = updated_at - interval '1 day' WHERE user_id = :u",
            u=user_id,
        )
        before = PathWant.query.filter_by(user_id=user_id).one()
        created, updated = before.created_at, before.updated_at

        with count_queries() as corrected:
            row = wants.set_answer(user_id, ANCHOR, wants.KIND_TASK, key, "less", REWORDED)
        _assert_one_upsert(corrected, "path_wants")
        db.session.commit()

        after = PathWant.query.filter_by(user_id=user_id).one()
        assert after.id == original_id, "a changed mind corrects the row"
        assert (after.verdict, after.item_text) == ("less", REWORDED)
        assert after.created_at == created, "created_at keeps the first answer"
        assert after.updated_at > updated, "updated_at moves on a correction"

        with count_queries() as cleared:
            assert wants.set_answer(user_id, ANCHOR, wants.KIND_TASK, key, None) is None
        assert [s for s in cleared if _is_read(s)] == [], cleared
        assert len(cleared) == 1 and cleared[0].startswith("DELETE FROM path_wants"), cleared
        db.session.commit()
        assert PathWant.query.filter_by(user_id=user_id).count() == 0

        # Clearing what is already clear is a no-op, not an error.
        assert wants.set_answer(user_id, ANCHOR, wants.KIND_TASK, key, None) is None
        db.session.commit()
        assert PathWant.query.filter_by(user_id=user_id).count() == 0


def test_set_answer_survives_an_answer_committed_between_read_and_write(user_id):
    from app import app
    from model import db
    from solverah.repositories import path_wants_repository as wants

    with app.app_context():
        with _row_committed_before_first_insert(
            "path_wants",
            "INSERT INTO path_wants (user_id, anchor_onet_code, kind, item_key, "
            "item_text, verdict, created_at, updated_at) "
            "VALUES (:u, :a, 'condition', 'pace', '', 'less', now(), now())",
            {"u": user_id, "a": ANCHOR},
        ) as fired:
            wants.set_answer(user_id, ANCHOR, wants.KIND_CONDITION, "pace", "more")
            db.session.commit()
        assert fired, "the competing row was never committed; the test proved nothing"

    with app.app_context():
        assert wants.answers_for_anchor(user_id, ANCHOR) == {("condition", "pace"): "more"}


def test_set_answers_sends_as_many_statements_for_twelve_items_as_for_two(user_id):
    from app import app
    from model import PathWant, db
    from solverah.repositories import path_wants_repository as wants
    from tests.query_count import count_queries

    tasks = ["Task statement number %d." % n for n in range(8)]
    key = wants.item_key_for_task

    with app.app_context():
        # Stored before either call: three rows the twelve-item call clears.
        for kind, item_key, text in (
            ("task", key(tasks[6]), tasks[6]),
            ("task", key(tasks[7]), tasks[7]),
            ("condition", "travel", ""),
        ):
            db.session.add(
                PathWant(
                    user_id=user_id,
                    anchor_onet_code=ANCHOR,
                    kind=kind,
                    item_key=item_key,
                    item_text=text,
                    verdict="less",
                )
            )
        db.session.commit()

        two = [
            ("task", key(tasks[0]), "more", tasks[0]),
            ("condition", "pace", None, ""),  # clearing what is already clear
        ]
        with count_queries() as for_two:
            wants.set_answers(user_id, ANCHOR, two)
        db.session.commit()

        twelve = (
            # tasks[0] is a correction of the call above; 1-5 are new.
            [("task", key(t), "less" if n == 0 else "more", t) for n, t in enumerate(tasks[:6])]
            + [("condition", "autonomy", "more", ""), ("condition", "hours", "less", "")]
            # Three stored rows cleared, and one that was never there.
            + [
                ("task", key(tasks[6]), None, tasks[6]),
                ("task", key(tasks[7]), None, tasks[7]),
                ("condition", "travel", None, ""),
                ("condition", "pace", None, ""),
            ]
        )
        assert len(twelve) == 12
        with count_queries() as for_twelve:
            written = wants.set_answers(user_id, ANCHOR, twelve)
        db.session.commit()

        expected = {("task", key(tasks[0])): "less"}
        expected.update({("task", key(t)): "more" for t in tasks[1:6]})
        expected.update({("condition", "autonomy"): "more", ("condition", "hours"): "less"})
        assert {k: row.verdict for k, row in written.items()} == expected
        assert wants.answers_for_anchor(user_id, ANCHOR) == expected
        assert {
            row.item_key: row.item_text
            for row in PathWant.query.filter_by(user_id=user_id, kind="task")
        } == {key(t): t for t in tasks[:6]}

    for statements in (for_two, for_twelve):
        assert [s for s in statements if _is_read(s)] == [], statements
    assert len(for_twelve) == len(for_two), (for_two, for_twelve)
    assert sorted(s.split()[0] for s in for_twelve) == ["DELETE", "INSERT"], for_twelve


def test_set_answers_with_nothing_to_write_sends_nothing(user_id):
    from app import app
    from solverah.repositories import path_wants_repository as wants
    from tests.query_count import count_queries

    with app.app_context():
        with count_queries() as statements:
            assert wants.set_answers(user_id, ANCHOR, []) == {}
    assert statements == []


@pytest.mark.parametrize(
    "bad, message",
    [
        (("chore", "t_x", "more", ""), "unknown want kind"),
        (("task", "t_x", "fine", ""), "unknown want verdict"),
        (("condition", "pace", None, ""), "twice"),  # the first good answer again
    ],
)
def test_set_answers_refuses_a_bad_body_before_writing_anything(user_id, bad, message):
    from app import app
    from model import db
    from solverah.repositories import path_wants_repository as wants
    from tests.query_count import count_queries

    good = [("condition", "pace", "more", ""), ("task", "t_y", "less", "A statement.")]
    with app.app_context():
        with count_queries() as statements:
            with pytest.raises(ValueError, match=message):
                wants.set_answers(user_id, ANCHOR, good + [bad])
        assert statements == [], "a refused body must not send a statement"
        db.session.rollback()

    with app.app_context():
        assert wants.answers_for_anchor(user_id, ANCHOR) == {}
