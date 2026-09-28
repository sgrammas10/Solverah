"""DB-ledger package E: the Pulse, its cadence cron, and condition experiments.

Each test pins one ledger fix, and the ones that assert a fix failed on the code
before it (see each docstring). The rest are characterisation: they passed before
the change and prove it changed nothing a caller can see.

- ``pulse_settings`` reads and writes its one ``profiles.extra`` key through the
  narrow profile helpers instead of the whole document, and stores exactly what
  the document path stored.
- A check-in's sequence is claimed under a per-user lock, so two interleaved
  submits cannot both take the same one; the check-in and event responses no
  longer re-read their own row after the commit.
- ``flask pulse send-prompts`` reads its candidates and their settings in a
  constant number of statements, and holds no ORM row a per-user commit can
  expire.
- ``GET /me/experiments`` reads check-ins once for the whole list; a start that
  loses the race to the one-active index is the documented 409, not a 500.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import re
import threading
import time

import pytest
import sqlalchemy as sa

from tests.query_count import count_queries

UTC = datetime.timezone.utc
PASSWORD = "Strongpass1!"
NOW = datetime.datetime(2026, 9, 28, 12, 0, tzinfo=UTC)

#: The profile tables a whole-document read or write touches besides ``profiles``.
PROFILE_CHILD_TABLES = ("profile_experiences", "profile_educations", "profile_skills", "resumes")


def _noop(*_args, **_kwargs):
    return None


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def ctx(client):
    """An application context over the ``client`` fixture's schema, left with no
    open transaction (``client``'s teardown drops every table and would wait on it)."""
    from app import app
    from model import db

    with app.app_context():
        yield app
        db.session.rollback()
        db.session.remove()


@pytest.fixture()
def sent(monkeypatch):
    """The addresses a Pulse prompt went to; stands in for Resend."""
    delivered = []
    monkeypatch.setattr(
        "solverah.infra.email.send_pulse_prompt_email",
        lambda to, deep_link, slowdown_notice=False: delivered.append(to),
    )
    return delivered


@contextlib.contextmanager
def _statements():
    """``count_queries()`` around test-client requests.

    Entered in an app context of its own and left open outside it, so every
    request inside pushes its own context and session. A request made inside an
    outer app context shares that context's session, and anything the test held
    there would answer a query from the identity map (the wave-1 pitfall).
    """
    from app import app

    with contextlib.ExitStack() as stack:
        with app.app_context():
            statements = stack.enter_context(count_queries())
        yield statements


def _reads_of(statements, table):
    """The SELECTs in *statements* whose FROM clause starts at *table*."""
    source = re.compile(r"\bFROM\s+%s\b" % re.escape(table), re.IGNORECASE)
    return [s for s in statements if s.lstrip().upper().startswith("SELECT") and source.search(s)]


def _mentioning(statements, *tables):
    pattern = re.compile(r"\b(%s)\b" % "|".join(re.escape(t) for t in tables), re.IGNORECASE)
    return [s for s in statements if pattern.search(s)]


def _index_of(statements, pattern):
    compiled = re.compile(pattern, re.IGNORECASE)
    for position, statement in enumerate(statements):
        if compiled.search(statement):
            return position
    raise AssertionError("no statement matches %r in %r" % (pattern, statements))


def _sign_in(client, monkeypatch, email):
    """Register, confirm and log in through the API. Returns (csrf, user_id)."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "name": "Ledger E", "terms_accepted": True},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)

    from app import app
    from model import User, db

    with app.app_context():
        user = User.query.filter_by(email=email).one()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()
        user_id = user.id

    resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["csrfToken"], user_id


def _user(email, *, confirmed=True):
    from app import app
    from model import User, db

    with app.app_context():
        user = User(email=email, password_hash="not-a-real-hash", email_confirmed=confirmed)
        db.session.add(user)
        db.session.commit()
        return user.id


def _served(user_id, sequence, value=3):
    from work_pulse.pulse_items import dimensions_for_checkin

    return {dim: value for dim in dimensions_for_checkin(user_id, sequence)}


def _checkin(user_id, taken_at, *, sequence=0, experienced=3):
    """One check-in row with an explicit ``taken_at``."""
    from app import app
    from model import PulseCheckin, db

    with app.app_context():
        row = PulseCheckin(
            user_id=user_id,
            sequence=sequence,
            item_scores=_served(user_id, sequence),
            experienced=experienced,
            version="pulse-v1-test",
            taken_at=taken_at,
        )
        db.session.add(row)
        db.session.commit()
        return row.id


def _save_document(user_id, **fields):
    """Merge *fields* into the profile document through the whole-document writer."""
    from app import app
    from model import db
    from solverah.repositories import profile_repository

    with app.app_context():
        profile_repository.update_document(user_id, lambda document: {**document, **fields})
        db.session.commit()


def _profile_row(user_id):
    """``(extra as sorted JSON, completeness, version)``, or None with no profiles row."""
    from app import app
    from model import Profile, db

    with app.app_context():
        row = db.session.execute(
            sa.select(Profile.extra, Profile.completeness, Profile.version).where(
                Profile.user_id == user_id
            )
        ).one_or_none()
        db.session.remove()
    if row is None:
        return None
    return json.dumps(row.extra, sort_keys=True), row.completeness, row.version


def _in_another_transaction(work):
    """Run *work* to completion on its own thread, app context, session and connection."""
    from app import app

    errors = []

    def target():
        try:
            with app.app_context():
                work()
        except Exception as exc:  # noqa: BLE001 -- re-raised below
            errors.append(exc)

    thread = threading.Thread(target=target)
    thread.start()
    thread.join(timeout=30)
    assert not thread.is_alive(), "the competing transaction never finished"
    if errors:
        raise errors[0]


# ---------------------------------------------------------------------------
# pulse_settings: the reference is the document path as it stood before
# ---------------------------------------------------------------------------

_OLD_DEFAULTS = {
    "cadence": "weekly",
    "last_prompted_at": None,
    "awaiting_response": False,
    "consecutive_unanswered": 0,
    "auto_slowed": False,
}


def _old_with_defaults(raw):
    raw = raw if isinstance(raw, dict) else {}
    return {**_OLD_DEFAULTS, **raw}


def _old_read_settings(user_id):
    from solverah.repositories import profile_repository

    return _old_with_defaults(profile_repository.load_document(user_id).get("pulse_settings"))


def _old_set_cadence(user_id, cadence):
    from solverah.repositories import profile_repository

    def _mutate(document):
        current = _old_with_defaults(document.get("pulse_settings"))
        updated = {
            **current,
            "cadence": cadence,
            "awaiting_response": False,
            "consecutive_unanswered": 0,
            "auto_slowed": False,
        }
        return {**document, "pulse_settings": updated}

    return profile_repository.update_document(user_id, _mutate)["pulse_settings"]


def _old_mark_answered(user_id):
    from solverah.repositories import profile_repository

    if not _old_read_settings(user_id)["awaiting_response"]:
        return None

    def _mutate(document):
        settings = _old_with_defaults(document.get("pulse_settings"))
        settings["awaiting_response"] = False
        return {**document, "pulse_settings": settings}

    profile_repository.update_document(user_id, _mutate)
    return None


def _old_record_prompt(user_id, *, cadence, consecutive_unanswered, prompted_at, auto_slowed=False):
    from solverah.repositories import profile_repository

    def _mutate(document):
        settings = _old_with_defaults(document.get("pulse_settings"))
        settings.update(
            cadence=cadence,
            last_prompted_at=prompted_at.isoformat(),
            awaiting_response=True,
            consecutive_unanswered=consecutive_unanswered,
            auto_slowed=auto_slowed,
        )
        return {**document, "pulse_settings": settings}

    profile_repository.update_document(user_id, _mutate)
    return None


_ABSENT = object()

#: Starting states, each a stored ``pulse_settings`` value (or no profile row at all).
PULSE_STATES = {
    "no_profile_row": None,
    "key_absent": _ABSENT,
    "pre_g21_four_keys": {
        "cadence": "monthly",
        "last_prompted_at": "2026-01-01T00:00:00+00:00",
        "awaiting_response": True,
        "consecutive_unanswered": 2,
    },
    "all_five_keys": {
        "cadence": "biweekly",
        "last_prompted_at": "2026-02-01T09:30:00+00:00",
        "awaiting_response": True,
        "consecutive_unanswered": 1,
        "auto_slowed": True,
    },
    "an_unknown_key_rides_along": {"cadence": "off", "future_key": [1, "two"]},
    "not_a_dict": "weekly",
    "json_null": "json-null",
}

#: (label, old writer, new writer name, kwargs) -- every writer the module has.
PULSE_WRITERS = [
    ("set_cadence_off", _old_set_cadence, "set_cadence", {"cadence": "off"}),
    ("set_cadence_monthly", _old_set_cadence, "set_cadence", {"cadence": "monthly"}),
    ("mark_answered", _old_mark_answered, "mark_answered", {}),
    (
        "record_prompt_drop",
        _old_record_prompt,
        "record_prompt",
        {
            "cadence": "monthly",
            "consecutive_unanswered": 0,
            "prompted_at": datetime.datetime(2026, 9, 1, 8, 15, 30, 123456, tzinfo=UTC),
            "auto_slowed": True,
        },
    ),
    (
        "record_prompt_plain",
        _old_record_prompt,
        "record_prompt",
        {
            "cadence": "weekly",
            "consecutive_unanswered": 2,
            "prompted_at": datetime.datetime(2026, 9, 2, tzinfo=UTC),
        },
    ),
]


def _seed_state(user_id, state):
    if state == "no_profile_row":
        return
    fields = {"headline": "Engineer", "quizInsights": {"kept": True, "n": 1}}
    stored = PULSE_STATES[state]
    if stored is not _ABSENT:
        fields["pulse_settings"] = None if stored == "json-null" else stored
    _save_document(user_id, **fields)


@pytest.mark.parametrize("state", sorted(PULSE_STATES))
def test_every_writer_stores_exactly_what_the_document_path_stored(client, seed_user, state):
    """Ledger ``pulse_settings``:180/197/205/241, the equivalence the switch rests on.

    For each starting state, one user is written through the document path as it
    stood before (the closures above, verbatim) and a twin through the module's
    own writer. The stored ``extra`` (type-strict JSON), ``completeness`` and
    ``version`` must come out identical, and ``set_cadence`` must return the same
    settings. Characterisation: this passed before the switch as well.
    """
    from app import app
    from model import db
    from solverah.services import pulse_settings

    for number, (label, old_writer, new_name, kwargs) in enumerate(PULSE_WRITERS):
        old_user, new_user = 100 + 2 * number, 101 + 2 * number
        seed_user(old_user, new_user)
        _seed_state(old_user, state)
        _seed_state(new_user, state)
        assert _profile_row(old_user) == _profile_row(new_user)

        with app.app_context():
            old_result = old_writer(old_user, **kwargs)
            new_result = getattr(pulse_settings, new_name)(new_user, **kwargs)
            db.session.commit()

        assert new_result == old_result, label
        assert _profile_row(new_user) == _profile_row(old_user), label


def test_each_settings_call_reads_and_writes_only_its_key(ctx, seed_user):
    """Ledger ``pulse_settings``:108/180/197/205/241 and ``pulse_service``:209/219.

    Before: every read was the whole document (6 statements) and every write a
    document rewrite (7). Now a read is one SELECT of the key, a write is the
    narrow compare-and-swap (3), and ``mark_answered`` reads once: one statement
    when nothing is outstanding. No child table is touched by any of them.
    """
    from model import db
    from solverah.services import pulse_settings

    seed_user(1)
    _save_document(
        1,
        headline="Engineer",
        experience=[{"company": "Acme", "title": "Dev", "startDate": "2020-01", "endDate": "Present"}],
        skills=["Python", "SQL"],
    )

    with count_queries() as read:
        pulse_settings.read_settings(1)
    with count_queries() as quiet:
        pulse_settings.mark_answered(1)
    with count_queries() as prompt:
        pulse_settings.record_prompt(1, cadence="weekly", consecutive_unanswered=1, prompted_at=NOW)
    db.session.commit()
    with count_queries() as answered:
        pulse_settings.mark_answered(1)
    db.session.commit()
    with count_queries() as chosen:
        pulse_settings.set_cadence(1, "biweekly")
    db.session.commit()

    assert len(read) == 1, read
    assert len(quiet) == 1, quiet
    assert len(prompt) == 3, prompt
    assert len(answered) == 4, answered
    assert len(chosen) == 3, chosen
    for statements in (read, quiet, prompt, answered, chosen):
        assert _mentioning(statements, *PROFILE_CHILD_TABLES) == [], statements

    settings = pulse_settings.read_settings(1)
    assert settings["cadence"] == "biweekly"
    assert settings["awaiting_response"] is False
    assert settings["last_prompted_at"] == NOW.isoformat()


def test_the_settings_routes_read_and_write_only_the_pulse_key(client, monkeypatch):
    """Ledger ``pulse_service``:209/219: GET and PATCH /me/pulse/settings no longer
    assemble the profile document."""
    csrf, user_id = _sign_in(client, monkeypatch, "settings-routes@example.test")
    _save_document(user_id, headline="Engineer", skills=["Python"])

    with _statements() as got:
        read = client.get("/api/v1/me/pulse/settings")
    with _statements() as patched:
        written = client.patch(
            "/api/v1/me/pulse/settings", json={"cadence": "monthly"}, headers={"X-CSRF-TOKEN": csrf}
        )

    assert read.status_code == 200 and read.get_json() == {"cadence": "weekly", "auto_slowed": False}
    assert written.status_code == 200
    assert written.get_json() == {"cadence": "monthly", "auto_slowed": False}
    for statements in (got, patched):
        assert _mentioning(statements, *PROFILE_CHILD_TABLES, "assessment_submissions") == [], statements
    assert len(_reads_of(got, "profiles")) == 1, got


# ---------------------------------------------------------------------------
# Check-ins and events
# ---------------------------------------------------------------------------


def test_checkin_and_event_answer_their_timestamps_without_rereading_their_row(client, monkeypatch):
    """Ledger ``pulse_service``:121/182/191, ``pulse_store``:205/238.

    Before: the commit expired the new row and the response re-SELECTed it to
    read the server-default timestamp. Now the value comes back with the INSERT
    and is read before the commit, and it is still the stored value.
    """
    from app import app
    from model import PulseCheckin, PulseEvent, db

    csrf, user_id = _sign_in(client, monkeypatch, "timestamps@example.test")

    with _statements() as checkin_statements:
        checkin = client.post(
            "/api/v1/me/pulse/checkins",
            json={"item_scores": _served(user_id, 0), "experienced": 4},
            headers={"X-CSRF-TOKEN": csrf},
        )
    with _statements() as event_statements:
        event = client.post(
            "/api/v1/me/pulse/events",
            json={"event_type": "reorg", "note": "new team"},
            headers={"X-CSRF-TOKEN": csrf},
        )

    assert checkin.status_code == 200, checkin.get_json()
    assert event.status_code == 200, event.get_json()

    inserted = _index_of(checkin_statements, r"^\s*INSERT INTO pulse_checkins\b")
    assert _reads_of(checkin_statements[inserted + 1:], "pulse_checkins") == [], checkin_statements
    inserted = _index_of(event_statements, r"^\s*INSERT INTO pulse_events\b")
    assert _reads_of(event_statements[inserted + 1:], "pulse_events") == [], event_statements

    with app.app_context():
        stored_taken_at = db.session.get(PulseCheckin, checkin.get_json()["id"]).taken_at
        stored_at = db.session.get(PulseEvent, event.get_json()["id"]).at
    assert checkin.get_json()["taken_at"] == stored_taken_at.isoformat()
    assert checkin.get_json()["sequence"] == 0
    assert event.get_json()["at"] == stored_at.isoformat()


def _someone_waits_on_an_advisory_lock(engine):
    with engine.connect() as connection:
        return (
            connection.execute(
                sa.text(
                    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted "
                    "AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"
                )
            ).scalar()
            > 0
        )


def test_two_interleaved_checkins_get_distinct_sequences(client, monkeypatch):
    """Ledger ``pulse_service``:101, ``pulse_store``:205/293 (decision 4: a lock, no
    unique constraint).

    Two real ``submit_checkin`` calls for one user, each on its own session and
    connection. The first is held open after its INSERT, inside
    ``mark_answered``, before its commit; the second then runs while it is open.
    Before the fix the second counted the same completed check-ins, wrote the
    same sequence and committed (sequences [0, 0]). Now the second waits at the
    per-user lock until the first commits, then counts it. The interleaving is
    driven, not raced: the first is released only once the second has either
    finished or is seen waiting on an advisory lock in ``pg_locks``.
    """
    import pulse_store
    from app import app
    from model import PulseCheckin, User, db
    from solverah.services import pulse_service, pulse_settings

    user_id = _user("interleaved@example.test")
    with app.app_context():
        engine = db.engine

    # Every sequence serves the same three dimensions here, so both submits are
    # valid whichever sequence each is handed: the assertion is about sequences.
    served = ("fragmentation", "sustainability", "work_pace")
    monkeypatch.setattr(pulse_store, "dimensions_for_checkin", lambda _uid, _sequence: served)

    real_mark_answered = pulse_settings.mark_answered
    first_wrote = threading.Event()
    release_first = threading.Event()

    def mark_answered_then_hold_the_first(uid):
        real_mark_answered(uid)
        if threading.current_thread().name == "first":
            first_wrote.set()
            release_first.wait(30)

    monkeypatch.setattr(pulse_settings, "mark_answered", mark_answered_then_hold_the_first)

    results, errors = {}, []

    def submit():
        name = threading.current_thread().name
        try:
            with app.app_context():
                user = db.session.get(User, user_id)
                results[name] = pulse_service.submit_checkin(
                    user, {"item_scores": {dim: 3 for dim in served}, "experienced": 4}
                )
        except Exception as exc:  # noqa: BLE001 -- asserted below
            errors.append(exc)

    first = threading.Thread(target=submit, name="first")
    second = threading.Thread(target=submit, name="second")
    first.start()
    try:
        assert first_wrote.wait(30), "the first check-in never reached its commit"
        second.start()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if "second" in results or errors or _someone_waits_on_an_advisory_lock(engine):
                break
            time.sleep(0.02)
    finally:
        release_first.set()
        first.join(30)
        if second.ident is not None:
            second.join(30)

    assert not errors, errors
    with app.app_context():
        sequences = sorted(
            db.session.execute(
                sa.select(PulseCheckin.sequence).where(PulseCheckin.user_id == user_id)
            ).scalars()
        )
    assert sequences == [0, 1], "two interleaved check-ins took the same sequence"
    assert sorted(result["sequence"] for result in results.values()) == [0, 1]


# ---------------------------------------------------------------------------
# pulse_store: the narrow reads the fixes use, with existing callers unchanged
# ---------------------------------------------------------------------------


def test_events_can_be_read_after_an_exclusive_bound_projecting_only_named_columns(ctx, seed_user):
    """Ledger ``pulse_store``:341: an exclusive lower bound in SQL and a projection,
    both keyword-only, so the situation report never ships the note or filters in
    Python. The call every existing caller makes returns what it always did."""
    import pulse_store
    from model import PulseEvent, db

    seed_user(1)
    bound = datetime.datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    for offset, kind in ((-1, "reorg"), (0, "new_manager"), (1, "other")):
        db.session.add(
            PulseEvent(
                user_id=1, event_type=kind, note="private %s" % kind,
                at=bound + datetime.timedelta(microseconds=offset),
            )
        )
    db.session.commit()

    with count_queries() as statements:
        after = pulse_store.pulse_events_in_range(1, after=bound, columns=("event_type", "at"))

    later = bound + datetime.timedelta(microseconds=1)
    assert after == [{"event_type": "other", "at": later.isoformat()}]
    assert len(statements) == 1
    assert "note" not in statements[0]
    assert re.search(r"pulse_events\.at > ", statements[0]), statements[0]

    inclusive = pulse_store.pulse_events_in_range(1, since=bound)
    assert [e["event_type"] for e in inclusive] == ["other", "new_manager"]
    assert set(inclusive[0]) == {"id", "user_id", "at", "event_type", "note"}
    assert inclusive[0]["note"] == "private other"


def test_checkin_history_offers_the_ranged_projection_experiments_use(ctx, seed_user):
    """Ledger ``experiment_store``:342: the ranged read selects ``taken_at`` and
    ``experienced`` only, never the ``item_scores`` JSONB, in the same order and
    with the same inclusive bounds as the full read."""
    import pulse_store

    seed_user(1)
    start = datetime.datetime(2026, 8, 1, tzinfo=UTC)
    for day, experienced in ((0, 2), (3, 4), (9, 5)):
        _checkin(1, start + datetime.timedelta(days=day), sequence=day, experienced=experienced)

    since, until = start, start + datetime.timedelta(days=3)
    with count_queries() as statements:
        ranged = pulse_store.pulse_checkin_history(
            1, since=since, until=until, columns=("taken_at", "experienced")
        )
    full = pulse_store.pulse_checkin_history(1, since=since, until=until)

    assert ranged == [{"taken_at": row["taken_at"], "experienced": row["experienced"]} for row in full]
    assert [row["experienced"] for row in ranged] == [4, 2]
    assert len(statements) == 1 and "item_scores" not in statements[0], statements

    with pytest.raises(ValueError):
        pulse_store.pulse_checkin_history(1, columns=("taken_at", "no_such_column"))


# ---------------------------------------------------------------------------
# The cadence cron (flask pulse send-prompts)
# ---------------------------------------------------------------------------


def _run_cron(now=NOW):
    from app import app
    from solverah.services import pulse_cadence_service

    with app.app_context():
        with count_queries() as statements:
            summary = pulse_cadence_service.send_due_prompts(base_url="https://app.test", now=now)
    return summary, statements


def test_the_cron_sends_a_constant_number_of_statements_however_many_users_it_checks(client, sent):
    """Ledger ``cli``:334, ``pulse_cadence_service``:86/88/92, ``pulse_store``:276.

    Before: one users SELECT, then per confirmed user a latest-check-in query and
    a whole-document settings read (7 statements each). Now the candidates come
    back from one DISTINCT ON query and their settings from one batched read, so
    four users cost what one does. ``checked`` still counts every confirmed user.
    """
    _user("never-checked-in@example.test")
    unconfirmed = _user("unconfirmed@example.test", confirmed=False)
    _checkin(unconfirmed, NOW - datetime.timedelta(days=30))
    _checkin(_user("recent-0@example.test"), NOW - datetime.timedelta(days=1))

    one_summary, one = _run_cron()

    for number in range(1, 4):
        _checkin(_user("recent-%d@example.test" % number), NOW - datetime.timedelta(days=1))

    four_summary, four = _run_cron()

    assert one_summary == {"checked": 2, "sent": 0, "dropped_to_monthly": 0}
    assert four_summary == {"checked": 5, "sent": 0, "dropped_to_monthly": 0}
    assert sent == []
    assert len(four) == len(one), (one, four)


def test_the_cron_prompts_each_due_user_at_a_constant_cost_and_never_reloads_a_user(client, sent):
    """Ledger ``pulse_cadence_service``:88 (lazy load), :121, :136.

    The per-user commit stays -- it is the documented idempotency -- but the
    users are tuples now, so a commit expires nothing the loop touches next:
    ``users`` is read once per run (the ``checked`` count), never per user. Each
    due user costs the same, and no whole-document read or write is left in it.
    """
    counts = []
    for batch in (1, 2, 3):
        for number in range(batch):
            uid = _user("due-%d-%d@example.test" % (batch, number))
            _checkin(uid, NOW - datetime.timedelta(days=8))

        summary, statements = _run_cron()

        assert summary["sent"] == batch, summary
        assert len(_reads_of(statements, "users")) == 1, statements
        assert _mentioning(statements, *PROFILE_CHILD_TABLES) == [], statements
        counts.append(len(statements))

    assert counts[1] - counts[0] == counts[2] - counts[1], counts
    assert len(sent) == 6


def test_a_user_who_turns_pulse_off_while_the_cron_runs_is_neither_prompted_nor_overwritten(
    client, sent, monkeypatch
):
    """The batched settings read only rules users out. A user it rules in is
    re-read just before the write, as the old loop read every user -- otherwise
    a cadence change that lands while earlier users are being prompted would be
    overwritten by the cron's stale copy and the user emailed anyway.
    Characterisation: the old per-user loop passed this too.
    """
    from model import db
    from solverah.services import outbox, pulse_settings

    first = _user("first-due@example.test")
    _checkin(first, NOW - datetime.timedelta(days=8))
    second = _user("turns-off@example.test")
    _checkin(second, NOW - datetime.timedelta(days=8))

    real_enqueue = outbox.enqueue

    def enqueue_then_the_second_user_turns_pulse_off(topic, payload):
        entry_id = real_enqueue(topic, payload)
        if payload["to"] == "first-due@example.test":

            def turn_off():
                pulse_settings.set_cadence(second, "off")
                db.session.commit()

            _in_another_transaction(turn_off)
        return entry_id

    monkeypatch.setattr(outbox, "enqueue", enqueue_then_the_second_user_turns_pulse_off)

    summary, _statements_sent = _run_cron()

    assert summary["sent"] == 1
    assert sent == ["first-due@example.test"]
    from app import app

    with app.app_context():
        assert pulse_settings.read_settings(second)["cadence"] == "off"


# ---------------------------------------------------------------------------
# Condition experiments
# ---------------------------------------------------------------------------


def _experiments(user_id, starts):
    """One experiment per start (oldest first); all but the newest abandoned."""
    import experiment_store
    from app import app
    from model import Experiment, db

    ids = []
    with app.app_context():
        for position, started_at in enumerate(starts):
            row = experiment_store.start_experiment(
                db, user_id, dimension="autonomy", direction="under"
            )
            experiment = db.session.get(Experiment, row["id"])
            experiment.started_at = started_at
            experiment.ends_at = started_at + experiment_store.EXPERIMENT_WINDOW
            experiment.created_at = started_at
            db.session.flush()
            if position < len(starts) - 1:
                experiment_store.abandon_experiment(db, user_id, row["id"])
            db.session.commit()
            ids.append(row["id"])
    return ids


def test_the_experiment_list_reads_checkins_once_however_many_experiments(client, monkeypatch):
    """Ledger ``experiment_service``:88/135/136, ``experiment_store``:342/345.

    Before: each listed experiment ran its own two check-in queries (1 + 2N).
    Now one ranged query covers every experiment in the list.
    """
    base = datetime.datetime(2026, 6, 1, tzinfo=UTC)

    _csrf, one_user = _sign_in(client, monkeypatch, "one-experiment@example.test")
    _experiments(one_user, [base])
    _checkin(one_user, base + datetime.timedelta(days=2))
    with _statements() as one:
        one_body = client.get("/api/v1/me/experiments")

    _csrf, four_user = _sign_in(client, monkeypatch, "four-experiments@example.test")
    _experiments(four_user, [base + datetime.timedelta(days=30 * n) for n in range(4)])
    _checkin(four_user, base + datetime.timedelta(days=2))
    with _statements() as four:
        four_body = client.get("/api/v1/me/experiments")

    assert one_body.status_code == 200 and len(one_body.get_json()["experiments"]) == 1
    assert four_body.status_code == 200 and len(four_body.get_json()["experiments"]) == 4
    assert len(four) == len(one), (one, four)
    assert len(_reads_of(four, "pulse_checkins")) == 1, four


def _old_readout(user_id, started_at, ends_at):
    """``checkin_experienced_values`` as it stood: two history reads, boundary in Python."""
    import pulse_store
    from work_pulse import experiments as experiment_engine

    window = datetime.timedelta(days=14)
    before = pulse_store.pulse_checkin_history(user_id, since=started_at - window, until=started_at)
    after = pulse_store.pulse_checkin_history(user_id, since=started_at, until=ends_at)
    before_values = [
        c["experienced"]
        for c in before
        if c["taken_at"] is not None and datetime.datetime.fromisoformat(c["taken_at"]) < started_at
    ]
    after_values = [c["experienced"] for c in after]
    return before_values, after_values, experiment_engine.compute_readout(before_values, after_values)


def test_experiment_readouts_are_unchanged_by_the_single_read(client, monkeypatch):
    """Characterisation for the batched ``_enrich``: every boundary the two
    per-experiment windows drew -- [start - 14d, start) before, [start, end]
    after -- lands the same check-in in the same bucket, for overlapping and
    separate experiments alike."""
    import experiment_store
    from app import app

    csrf, user_id = _sign_in(client, monkeypatch, "readouts@example.test")
    first = datetime.datetime(2026, 5, 1, tzinfo=UTC)
    second = first + datetime.timedelta(days=20)  # its before-window overlaps the first's after
    third = first + datetime.timedelta(days=90)
    _experiments(user_id, [first, second, third])

    tick = datetime.timedelta(microseconds=1)
    window = datetime.timedelta(days=14)
    moments = [
        first - window - tick, first - window, first - tick, first, first + window,
        first + window + tick, second - tick, second, second + window, third - window,
        third + datetime.timedelta(days=1),
    ]
    for sequence, moment in enumerate(moments):
        _checkin(user_id, moment, sequence=sequence, experienced=1 + sequence % 5)

    body = client.get("/api/v1/me/experiments").get_json()["experiments"]

    with app.app_context():
        for entry in body:
            started_at = datetime.datetime.fromisoformat(entry["started_at"])
            ends_at = datetime.datetime.fromisoformat(entry["ends_at"])
            before_values, after_values, readout = _old_readout(user_id, started_at, ends_at)
            assert entry["readout"] == readout, entry
            assert experiment_store.checkin_experienced_values(
                user_id, started_at=started_at, ends_at=ends_at
            ) == (before_values, after_values)

    # Newest first. Third: [T-14d] before, [T+1d] after. Second: [F+14d, F+14d+1us,
    # S-1us] before, [S, S+14d] after. First: [F-14d, F-1us] before, [F, F+14d] after.
    counts = [(e["readout"]["before_count"], e["readout"]["after_count"]) for e in body]
    assert counts == [(1, 1), (3, 2), (2, 2)], counts


def test_a_start_that_loses_the_race_is_the_409_not_a_500(client, monkeypatch):
    """Ledger ``experiment_service``:119, ``experiment_store``:277.

    The pre-check passes, then a competing start commits before this one's
    INSERT, and the partial unique index refuses it. Before: the IntegrityError
    escaped as a 500. Now it is the same 409 the pre-check gives.
    """
    import experiment_store
    from app import app
    from model import Experiment, db

    csrf, user_id = _sign_in(client, monkeypatch, "start-race@example.test")
    real_check = experiment_store.active_experiment

    def check_then_lose_the_race(uid):
        found = real_check(uid)

        def competitor():
            experiment_store.start_experiment(db, uid, dimension="pace", direction="over")
            db.session.commit()

        _in_another_transaction(competitor)
        return found

    monkeypatch.setattr(experiment_store, "active_experiment", check_then_lose_the_race)
    raced = client.post(
        "/api/v1/me/experiments",
        json={"dimension": "autonomy", "direction": "under"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    monkeypatch.setattr(experiment_store, "active_experiment", real_check)
    refused = client.post(
        "/api/v1/me/experiments",
        json={"dimension": "autonomy", "direction": "under"},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert raced.status_code == 409, raced.get_data(as_text=True)
    assert refused.status_code == 409

    def _stable(body):
        return {key: value for key, value in body.items() if key != "request_id"}

    assert raced.mimetype == refused.mimetype == "application/problem+json"
    assert _stable(raced.get_json()) == _stable(refused.get_json())
    assert raced.get_json()["errors"][0]["code"] == "experiment_already_active"

    with app.app_context():
        active = Experiment.query.filter_by(user_id=user_id, status="active").all()
        assert [(row.dimension, row.direction) for row in active] == [("pace", "over")]
