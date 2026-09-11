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


# ── who gets prompted ────────────────────────────────────────────────────────


def test_never_prompted_confirmed_user_is_prompted(ctx, sent):
    user_id = _seed("never-prompted@example.test")

    exit_code, payload, _ = _invoke(ctx, "pulse", "send-prompts", "--base-url", "https://app.test")

    assert exit_code == 0
    assert payload["event"] == "pulse_send_prompts"
    assert payload["sent"] == 1
    assert sent == [
        {"to": "never-prompted@example.test", "deep_link": "https://app.test/pulse", "slowdown_notice": False}
    ]

    from solverah.services import pulse_settings

    settings = pulse_settings.read_settings(user_id)
    assert settings["awaiting_response"] is True
    assert settings["consecutive_unanswered"] == 0
    assert settings["last_prompted_at"] is not None


def test_off_users_are_excluded(ctx, sent):
    user_id = _seed("off@example.test")
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
    _set_pulse_settings(
        not_yet, cadence="biweekly", last_prompted_at=_ago(days=10),
        awaiting_response=False, consecutive_unanswered=0,
    )
    due = _seed("biweekly-due@example.test")
    _set_pulse_settings(
        due, cadence="biweekly", last_prompted_at=_ago(days=15),
        awaiting_response=False, consecutive_unanswered=0,
    )

    exit_code, payload, _ = _invoke(ctx, "pulse", "send-prompts")

    assert exit_code == 0
    assert payload["sent"] == 1
    assert [row["to"] for row in sent] == ["biweekly-due@example.test"]


# ── idempotency ──────────────────────────────────────────────────────────────


def test_rerun_within_the_same_window_does_not_double_send(ctx, sent):
    _seed("once-only@example.test")

    first_exit, first_payload, _ = _invoke(ctx, "pulse", "send-prompts")
    second_exit, second_payload, _ = _invoke(ctx, "pulse", "send-prompts")

    assert first_exit == 0 and second_exit == 0
    assert first_payload["sent"] == 1
    assert second_payload["sent"] == 0, "a re-run inside the cadence window re-sent the prompt"
    assert len(sent) == 1


# ── anti-nag auto-drop ───────────────────────────────────────────────────────


def test_three_consecutive_unanswered_drops_to_monthly_with_a_slowdown_note(ctx, sent):
    user_id = _seed("quiet@example.test")
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


def test_answering_before_the_next_due_date_resets_the_unanswered_count(ctx, sent):
    """A user who checks in resets the counter -- no streak survives an answer."""
    user_id = _seed("answers@example.test")
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
