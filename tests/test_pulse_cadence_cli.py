"""Tests for `flask pulse send-prompts` (BUILD_PLAN B-2): due-selection, the
anti-nag auto-drop, and idempotent re-runs.

Same CLI-testing shape as `test_ops_cli.py`: a `test_cli_runner()` invocation,
JSON parsed off the last output line, and a `sent` fixture that stands in for
Resend so nothing here makes a network call.
"""

import datetime
import json

import pytest

UTC = datetime.timezone.utc


@pytest.fixture()
def ctx(client):
    """An application context with the schema built, and a clean session after."""
    from app import app

    with app.app_context():
        yield app
        from model import db

        db.session.rollback()


@pytest.fixture()
def sent(monkeypatch):
    """Capture what the publisher would send; see test_outbox.py's twin."""
    delivered = []
    monkeypatch.setattr(
        "solverah.infra.email.send_pulse_prompt_email",
        lambda to, deep_link, slowdown_notice=False: delivered.append(
            {"to": to, "deep_link": deep_link, "slowdown_notice": slowdown_notice}
        ),
    )
    return delivered


def _invoke(app, *args):
    """Run a CLI command; return (exit_code, parsed-JSON-or-None, raw result)."""
    result = app.test_cli_runner().invoke(args=list(args))
    payload = None
    for line in reversed(result.output.strip().splitlines()):
        try:
            payload = json.loads(line)
            break
        except ValueError:
            continue
    return result.exit_code, payload, result


def _confirmed_user(email, **kwargs):
    from model import User

    return User(email=email, password_hash="not-a-real-hash", email_confirmed=True, **kwargs)


def _seed(email, **kwargs):
    from model import db

    user = _confirmed_user(email, **kwargs)
    db.session.add(user)
    db.session.commit()
    return user.id


def _set_pulse_settings(user_id, **fields):
    """Write `pulse_settings` directly, bypassing the module's own writers --
    these tests need arbitrary starting states the public API cannot always
    reach in one call (e.g. an in-progress `awaiting_response` at a specific
    `consecutive_unanswered`)."""
    from solverah.repositories import profile_repository

    def _mutate(document):
        return {**document, "pulse_settings": fields}

    profile_repository.update_document(user_id, _mutate)
    from model import db

    db.session.commit()


def _ago(**kwargs):
    return (datetime.datetime.now(UTC) - datetime.timedelta(**kwargs)).isoformat()


def _ago_dt(**kwargs):
    return datetime.datetime.now(UTC) - datetime.timedelta(**kwargs)


def _seed_checkin(user_id, *, taken_at=None):
    """Complete one check-in for *user_id* via the real `pulse_store` write
    path -- the zero-check-in gate is `pulse_cadence_service._candidates`'
    DISTINCT ON read of `pulse_checkins`, not `pulse_settings`, so these tests
    need a real row, not a settings fixture. `taken_at` optionally backdates
    the server-defaulted timestamp, to control the never-prompted "one interval
    after the most recent check-in" math."""
    import pulse_store
    from model import db
    from work_pulse.pulse_items import FORM_VERSION, dimensions_for_checkin

    sequence = pulse_store.pulse_checkin_count(user_id)
    item_scores = {dim: 3 for dim in dimensions_for_checkin(user_id, sequence)}
    checkin_id = pulse_store.write_pulse_checkin(
        db,
        user_id,
        sequence=sequence,
        item_scores=item_scores,
        experienced=3,
        version=FORM_VERSION,
    )
    db.session.commit()

    if taken_at is not None:
        from model import PulseCheckin

        row = db.session.get(PulseCheckin, checkin_id)
        row.taken_at = taken_at
        db.session.commit()

    return checkin_id


# ── who gets prompted ────────────────────────────────────────────────────────


def test_zero_checkin_confirmed_user_is_never_selected(ctx, sent):
    """2026-09-11 ruling: checking in once is the opt-in. A confirmed user who
    has never completed a check-in is excluded no matter what their cadence or
    `last_prompted_at` says -- there is no such thing as an unsolicited first
    Pulse email."""
    user_id = _seed("zero-checkins@example.test")
    _set_pulse_settings(
        user_id, cadence="weekly", last_prompted_at=_ago(days=30),
        awaiting_response=False, consecutive_unanswered=0,
    )

    exit_code, payload, _ = _invoke(ctx, "pulse", "send-prompts")

    assert exit_code == 0
    assert payload["sent"] == 0
    assert sent == []


def test_first_prompt_waits_a_full_interval_after_the_first_checkin(ctx, sent):
    """Not due before the interval elapses, even though the user has never
    been prompted -- the clock starts at the check-in, not at signup or at
    cron-discovery time."""
    user_id = _seed("fresh-checkin@example.test")
    _seed_checkin(user_id, taken_at=_ago_dt(days=3))  # weekly default: not due yet

    exit_code, payload, _ = _invoke(ctx, "pulse", "send-prompts")

    assert exit_code == 0
    assert payload["sent"] == 0
    assert sent == []

    from solverah.services import pulse_settings

    settings = pulse_settings.read_settings(user_id)
    assert settings["last_prompted_at"] is None


def test_never_prompted_user_is_prompted_one_interval_after_first_checkin_with_clean_counters(ctx, sent):
    """A user whose first-ever action is a check-in enters the loop with clean
    counters: once their check-in is old enough to clear the cadence interval,
    they are prompted exactly like any other due user."""
    user_id = _seed("earned-prompt@example.test")
    _seed_checkin(user_id, taken_at=_ago_dt(days=8))  # weekly default: past due

    exit_code, payload, _ = _invoke(ctx, "pulse", "send-prompts", "--base-url", "https://app.test")

    assert exit_code == 0
    assert payload["event"] == "pulse_send_prompts"
    assert payload["sent"] == 1
    assert sent == [
        {"to": "earned-prompt@example.test", "deep_link": "https://app.test/pulse", "slowdown_notice": False}
    ]

    from solverah.services import pulse_settings

    settings = pulse_settings.read_settings(user_id)
    assert settings["awaiting_response"] is True
    assert settings["consecutive_unanswered"] == 0
    assert settings["last_prompted_at"] is not None


def test_off_users_are_excluded(ctx, sent):
    user_id = _seed("off@example.test")
    _seed_checkin(user_id, taken_at=_ago_dt(days=30))
    _set_pulse_settings(
        user_id, cadence="off", last_prompted_at=None, awaiting_response=False,
        consecutive_unanswered=0,
    )

    exit_code, payload, _ = _invoke(ctx, "pulse", "send-prompts")

    assert exit_code == 0
    assert payload["sent"] == 0
    assert sent == []


def test_unconfirmed_users_are_excluded(ctx, sent):
    from model import User, db

    db.session.add(User(email="unconfirmed@example.test", password_hash="not-a-real-hash"))
    db.session.commit()

    exit_code, payload, _ = _invoke(ctx, "pulse", "send-prompts")

    assert exit_code == 0
    assert payload["sent"] == 0
    assert sent == []


def test_biweekly_is_honored(ctx, sent):
    not_yet = _seed("biweekly-not-due@example.test")
    _seed_checkin(not_yet, taken_at=_ago_dt(days=60))
    _set_pulse_settings(
        not_yet, cadence="biweekly", last_prompted_at=_ago(days=10),
        awaiting_response=False, consecutive_unanswered=0,
    )
    due = _seed("biweekly-due@example.test")
    _seed_checkin(due, taken_at=_ago_dt(days=60))
    _set_pulse_settings(
        due, cadence="biweekly", last_prompted_at=_ago(days=15),
        awaiting_response=False, consecutive_unanswered=0,
    )

    exit_code, payload, _ = _invoke(ctx, "pulse", "send-prompts")

    assert exit_code == 0
    assert payload["sent"] == 1
    assert [row["to"] for row in sent] == ["biweekly-due@example.test"]


def test_a_checkin_after_the_last_prompt_defers_the_next_one(ctx, sent):
    """F4 (2026-10-02): the clock runs from the LATER of the last prompt and
    the last check-in. A user prompted 8 days ago who checked in on their own
    2 days ago is not due -- before this fix they were emailed "time to check
    in" six days after checking in."""
    user_id = _seed("just-checked-in@example.test")
    _seed_checkin(user_id, taken_at=_ago_dt(days=2))
    _set_pulse_settings(
        user_id, cadence="weekly", last_prompted_at=_ago(days=8),
        awaiting_response=False, consecutive_unanswered=0,
    )

    exit_code, payload, _ = _invoke(ctx, "pulse", "send-prompts")

    assert exit_code == 0
    assert payload["sent"] == 0
    assert sent == []


# ── idempotency ──────────────────────────────────────────────────────────────


def test_rerun_within_the_same_window_does_not_double_send(ctx, sent):
    user_id = _seed("once-only@example.test")
    _seed_checkin(user_id, taken_at=_ago_dt(days=8))  # weekly default: past due

    first_exit, first_payload, _ = _invoke(ctx, "pulse", "send-prompts")
    second_exit, second_payload, _ = _invoke(ctx, "pulse", "send-prompts")

    assert first_exit == 0 and second_exit == 0
    assert first_payload["sent"] == 1
    assert second_payload["sent"] == 0, "a re-run inside the cadence window re-sent the prompt"
    assert len(sent) == 1


# ── anti-nag auto-drop ───────────────────────────────────────────────────────


def test_three_consecutive_unanswered_drops_to_monthly_with_a_slowdown_note(ctx, sent):
    user_id = _seed("quiet@example.test")
    _seed_checkin(user_id, taken_at=_ago_dt(days=60))
    _set_pulse_settings(
        user_id, cadence="weekly", last_prompted_at=_ago(days=8),
        awaiting_response=True, consecutive_unanswered=2,
    )

    exit_code, payload, _ = _invoke(ctx, "pulse", "send-prompts")

    assert exit_code == 0
    assert payload["sent"] == 1
    assert payload["dropped_to_monthly"] == 1
    assert sent[0]["slowdown_notice"] is True

    from solverah.services import pulse_settings

    settings = pulse_settings.read_settings(user_id)
    assert settings["cadence"] == "monthly"
    assert settings["consecutive_unanswered"] == 0
    assert settings["auto_slowed"] is True


def test_already_monthly_user_is_not_dropped_again_and_gets_no_second_slowdown_note(ctx, sent):
    """The drop is a one-way door, not a recurring event. A user the engine
    already slowed to monthly who stays quiet for three more prompts has
    nowhere slower to go, so re-running the drop writes the same cadence back
    and -- before G21, 2026-09-14 -- re-sent the "we've slowed these down"
    paragraph every third prompt, forever, and over-counted `dropped_to_monthly`
    in the cron's log line. The unanswered counter still resets: three prompts
    have been accounted for either way."""
    user_id = _seed("still-quiet@example.test")
    _seed_checkin(user_id, taken_at=_ago_dt(days=60))
    _set_pulse_settings(
        user_id, cadence="monthly", last_prompted_at=_ago(days=31),
        awaiting_response=True, consecutive_unanswered=2, auto_slowed=True,
    )

    exit_code, payload, _ = _invoke(ctx, "pulse", "send-prompts")

    assert exit_code == 0
    assert payload["sent"] == 1
    assert payload["dropped_to_monthly"] == 0, "re-dropped a user already on monthly"
    assert len(sent) == 1
    assert sent[0]["slowdown_notice"] is False, "sent the slowdown paragraph a second time"

    from solverah.services import pulse_settings

    settings = pulse_settings.read_settings(user_id)
    assert settings["cadence"] == "monthly"
    assert settings["consecutive_unanswered"] == 0
    assert settings["auto_slowed"] is True


def test_user_who_chose_monthly_is_prompted_without_a_slowdown_note(ctx, sent):
    """G21: monthly is a cadence a user can pick. Being on it is not evidence
    the engine put them there, so their prompt carries no slowdown note and
    `auto_slowed` stays False -- which is what the trend page reads to decide
    whether that paragraph is true of this user."""
    user_id = _seed("chose-monthly@example.test")
    _seed_checkin(user_id, taken_at=_ago_dt(days=60))
    # Reached the way a user reaches it -- `set_cadence` is what PATCH calls,
    # and it rejected "monthly" outright before G21. Seeding the state directly
    # would let this test pass against code that still refuses the choice.
    _set_pulse_settings(
        user_id, cadence="weekly", last_prompted_at=_ago(days=31),
        awaiting_response=True, consecutive_unanswered=1,
    )

    from model import db
    from solverah.services import pulse_settings

    pulse_settings.set_cadence(user_id, "monthly")
    db.session.commit()
    assert pulse_settings.read_settings(user_id)["auto_slowed"] is False

    exit_code, payload, _ = _invoke(ctx, "pulse", "send-prompts")

    assert exit_code == 0
    assert payload["sent"] == 1
    assert payload["dropped_to_monthly"] == 0
    assert sent[0]["slowdown_notice"] is False

    settings = pulse_settings.read_settings(user_id)
    assert settings["cadence"] == "monthly"
    assert settings["auto_slowed"] is False


def test_choosing_a_cadence_after_an_auto_drop_ends_the_auto_slowed_state(ctx, sent):
    """The user takes the wheel back. `set_cadence` -- what `PATCH
    /me/pulse/settings` calls -- clears `auto_slowed`, so the next prompt the
    engine sends passes the cleared value through instead of resurrecting the
    note, and the trend page stops explaining a slowdown that no longer
    describes anything."""
    user_id = _seed("took-the-wheel@example.test")
    _seed_checkin(user_id, taken_at=_ago_dt(days=60))
    _set_pulse_settings(
        user_id, cadence="monthly", last_prompted_at=_ago(days=31),
        awaiting_response=True, consecutive_unanswered=2, auto_slowed=True,
    )

    from model import db
    from solverah.services import pulse_settings

    pulse_settings.set_cadence(user_id, "weekly")
    db.session.commit()
    assert pulse_settings.read_settings(user_id)["auto_slowed"] is False

    exit_code, payload, _ = _invoke(ctx, "pulse", "send-prompts")

    assert exit_code == 0
    assert payload["sent"] == 1
    assert payload["dropped_to_monthly"] == 0
    assert sent[0]["slowdown_notice"] is False

    settings = pulse_settings.read_settings(user_id)
    assert settings["cadence"] == "weekly"
    assert settings["auto_slowed"] is False


def test_answering_before_the_next_due_date_resets_the_unanswered_count(ctx, sent):
    """A user who checks in resets the counter -- no streak survives an answer."""
    user_id = _seed("answers@example.test")
    _seed_checkin(user_id, taken_at=_ago_dt(days=60))
    _set_pulse_settings(
        user_id, cadence="weekly", last_prompted_at=_ago(days=8),
        awaiting_response=False,  # they answered -- pulse_service.submit_checkin's job
        consecutive_unanswered=2,
    )

    exit_code, payload, _ = _invoke(ctx, "pulse", "send-prompts")

    assert exit_code == 0
    assert payload["dropped_to_monthly"] == 0
    assert sent[0]["slowdown_notice"] is False

    from solverah.services import pulse_settings

    settings = pulse_settings.read_settings(user_id)
    assert settings["cadence"] == "weekly"
    assert settings["consecutive_unanswered"] == 0


def test_no_guilt_copy_or_streak_language_anywhere_in_the_email(monkeypatch):
    """PRODUCT_DECISIONS.md §2: silence is data, never a guilt trip. Checked
    against the real HTML this time -- not the `sent` fixture's stand-in --
    so a copy change cannot slip a banned phrase past the mock."""
    import sys

    from solverah.infra import email as email_module

    # `RESEND_API_KEY`/`EMAIL_FROM` are read once into module globals at import
    # time (solverah/infra/email.py's own docstring notes this), so
    # `monkeypatch.setenv` -- which only touches `os.environ` -- would not
    # reach them; the already-bound attributes are what needs patching.
    monkeypatch.setattr(email_module, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(email_module, "EMAIL_FROM", "no-reply@solverah.test")

    captured = {}

    class _FakeEmails:
        @staticmethod
        def send(params):
            captured.update(params)

    class _FakeResend:
        api_key = None
        Emails = _FakeEmails

    monkeypatch.setitem(sys.modules, "resend", _FakeResend)

    email_module.send_pulse_prompt_email(
        "someone@example.test", "https://app.test/pulse", slowdown_notice=True
    )

    html = captured["html"].lower()
    for banned in ("streak", "miss", "haven't", "you didn't", "still waiting", "come back"):
        assert banned not in html, "banned guilt/streak phrase %r found in the email" % banned
    assert "slowed" in html  # the one line the drop is allowed to add
