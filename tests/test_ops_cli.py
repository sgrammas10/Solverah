"""The operational CLI (`flask outbox sweep`, `flask retention run`).

These commands are how Scenario A production (one web service + Postgres,
no broker, no beat -- PROD_READINESS_2026-09_ANSWERS.md) gets its outbox
retried and its PII-bearing tables purged: a Render Cron Job service runs them
on a schedule.  What this file proves:

1. The commands exist on the app the factory builds -- a cron box with only the
   repo and env vars can run them through ``create_app()``.
2. ``outbox sweep`` delivers what is owed, reports counts, and exits 0 even
   when every row fails (provider flakiness is data, not a sweeper failure) --
   but exits non-zero when the pass itself crashes, which is the distinction
   cron alerting keys on.
3. ``retention run`` deletes exactly the rows whose windows have passed --
   delivered outbox rows, terminal scoring jobs, terminal resume-parse jobs,
   dead refresh sessions -- and provably nothing else.

The fourth is S3's, and it is the one with two conditions rather than one: a
session row is deletable when it was *retired* long enough ago **or** when it
ran past ``expires_at`` long enough ago without ever being stamped. Both halves
are seeded below, and so is the case each half must not touch -- a live session
is somebody signed in right now, and deleting one signs them out with no event
anywhere saying why.
"""

import datetime
import json

import pytest

TOPIC = "email.verification"
EMAIL = "ops-cli@example.test"


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
        "solverah.infra.email.send_confirmation_email",
        lambda to, code: delivered.append((to, code)),
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


def _ago(**kwargs):
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(**kwargs)


# ── flask outbox sweep ──────────────────────────────────────────────────────


def test_outbox_sweep_delivers_owed_rows_and_reports(ctx, sent):
    from model import db
    from solverah.services import outbox

    outbox.enqueue(TOPIC, {"to": EMAIL, "code": "111111"})
    db.session.commit()

    exit_code, payload, _ = _invoke(ctx, "outbox", "sweep")

    assert exit_code == 0
    assert payload["event"] == "outbox_sweep"
    assert payload["selected"] == 1
    assert payload[outbox.PUBLISHED] == 1
    assert payload["outbox"] == {"pending": 0, "parked": 0}
    assert sent == [(EMAIL, "111111")]


def test_outbox_sweep_exits_zero_when_rows_fail(ctx, monkeypatch):
    """Failed sends are the outbox's normal weather, not a broken sweeper.

    Cron alerting must distinguish "provider flaky" (rows failed, exit 0, rows
    retried next pass) from "sweeper broken" (non-zero).  A sweep that exited 1
    whenever Resend blipped would page someone for the exact situation the
    outbox exists to absorb.
    """
    from model import db
    from solverah.services import outbox

    monkeypatch.setattr(
        "solverah.infra.email.send_confirmation_email",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("resend is down")),
    )
    entry_id = outbox.enqueue(TOPIC, {"to": EMAIL, "code": "222222"})
    db.session.commit()

    exit_code, payload, _ = _invoke(ctx, "outbox", "sweep")

    assert exit_code == 0
    assert payload[outbox.FAILED] == 1
    assert payload["outbox"] == {"pending": 1, "parked": 0}
    state = outbox.entry_state(entry_id)
    assert state["published_at"] is None
    assert state["attempts"] == 1


def test_outbox_sweep_exits_nonzero_when_the_pass_crashes(ctx, monkeypatch):
    """The other half of the exit-code contract: a crashed pass must page."""
    monkeypatch.setattr(
        "solverah.services.outbox.drain",
        lambda **_k: (_ for _ in ()).throw(RuntimeError("database on fire")),
    )

    exit_code, _, _ = _invoke(ctx, "outbox", "sweep")

    assert exit_code != 0


# ── flask retention run ─────────────────────────────────────────────────────


def _seed_retention_matrix(app):
    """Every row class retention must and must not delete, in one database.

    Returns a dict of ids keyed by what the row is, so assertions read as the
    policy they check.
    """
    import sqlalchemy as sa

    from model import Outbox, ResumeParseJob, ScoringJob, User, UserSession, db
    from solverah.services import outbox

    ids = {}

    user = User(email=EMAIL, password_hash="not-a-real-hash")
    db.session.add(user)
    db.session.commit()

    # Outbox: delivered-old dies; delivered-fresh, pending-old, parked-old live.
    for name, code in (
        ("outbox_delivered_old", "111111"),
        ("outbox_delivered_fresh", "222222"),
        ("outbox_pending_old", "333333"),
        ("outbox_parked_old", "444444"),
    ):
        ids[name] = outbox.enqueue(TOPIC, {"to": EMAIL, "code": code})
    db.session.commit()
    outbox.publish(ids["outbox_delivered_old"])
    outbox.publish(ids["outbox_delivered_fresh"])

    with db.engine.begin() as conn:
        ob = Outbox.__table__
        conn.execute(
            sa.update(ob)
            .where(ob.c.id == ids["outbox_delivered_old"])
            .values(published_at=_ago(hours=100))
        )
        conn.execute(
            sa.update(ob)
            .where(ob.c.id == ids["outbox_pending_old"])
            .values(created_at=_ago(days=30))
        )
        conn.execute(
            sa.update(ob)
            .where(ob.c.id == ids["outbox_parked_old"])
            .values(created_at=_ago(days=30), attempts=outbox.MAX_ATTEMPTS)
        )

        # Scoring jobs: terminal-old dies; terminal-fresh and queued-old live.
        sj = ScoringJob.__table__
        for name, status, created in (
            ("scoring_terminal_old", "succeeded", _ago(days=10)),
            ("scoring_terminal_fresh", "failed", _ago(days=1)),
            ("scoring_queued_old", "queued", _ago(days=10)),
        ):
            ids[name] = conn.execute(
                sa.insert(sj)
                .values(
                    user_id=user.id,
                    job_type="assessment_scoring",
                    kind="work_pulse",
                    payload={},
                    status=status,
                    created_at=created,
                )
                .returning(sj.c.id)
            ).scalar_one()

        # Resume jobs: terminal-old dies; terminal-fresh and queued-old live.
        rj = ResumeParseJob.__table__
        for name, status, created in (
            ("resume_terminal_old", "succeeded", _ago(days=40)),
            ("resume_terminal_fresh", "failed", _ago(days=5)),
            ("resume_queued_old", "queued", _ago(days=40)),
        ):
            ids[name] = conn.execute(
                sa.insert(rj)
                .values(
                    user_id=user.id,
                    object_key="intake/%s.pdf" % name,
                    mime="application/pdf",
                    size_bytes=1,
                    status=status,
                    created_at=created,
                )
                .returning(rj.c.id)
            ).scalar_one()

        # Refresh sessions (S3). Two ways to be deletable and two ways not to
        # be, which is why this block has four rows rather than three:
        #
        #   retired_old   -- retired 40 days ago: dies on the `retired_at` half.
        #   expired_old   -- never retired, expired 40 days ago: dies on the
        #                    `expires_at` half. Dropping that half would mean
        #                    one skipped cron run leaves rows no later run
        #                    reaches, so this row is the only thing standing
        #                    between the OR and being quietly halved.
        #   retired_fresh -- retired yesterday: inside the window, lives.
        #   live          -- not retired, expires in 30 days: SOMEBODY'S CURRENT
        #                    SESSION. The one row here whose deletion would be
        #                    visible to a user.
        #
        # `expired_old` is stamped by `expire_stale` in the same pass before it
        # is deleted, which is why the run reports one expiry and two deletes.
        us = UserSession.__table__
        for name, retired_at, reason, expires_at in (
            ("session_retired_old", _ago(days=40), "logged_out", _ago(days=10)),
            ("session_expired_old", None, None, _ago(days=40)),
            ("session_retired_fresh", _ago(days=1), "rotated", _ago(days=1)),
            ("session_live", None, None, _ago(days=-30)),
        ):
            ids[name] = conn.execute(
                sa.insert(us)
                .values(
                    user_id=user.id,
                    token_hash="hash-%s" % name,
                    expires_at=expires_at,
                    retired_at=retired_at,
                    retired_reason=reason,
                )
                .returning(us.c.id)
            ).scalar_one()

    return ids


def _surviving(table, row_ids):
    import sqlalchemy as sa

    from model import db

    with db.engine.connect() as conn:
        return {
            row.id
            for row in conn.execute(
                sa.select(table.c.id).where(table.c.id.in_(row_ids))
            )
        }


def test_retention_run_deletes_exactly_the_expired_delivered_and_terminal_rows(
    ctx, sent
):
    from model import Outbox, ResumeParseJob, ScoringJob, UserSession

    ids = _seed_retention_matrix(ctx)

    exit_code, payload, _ = _invoke(ctx, "retention", "run")

    assert exit_code == 0
    assert payload["event"] == "retention_run"
    assert payload["outbox_deleted"] == 1
    assert payload["scoring_jobs_deleted"] == 1
    assert payload["resume_jobs_deleted"] == 1
    # One stamp (`session_expired_old`), two deletes (it, and the row that was
    # retired 40 days ago). The live session and the freshly retired one stay.
    assert payload["sessions_expired"] == 1
    assert payload["sessions_deleted"] == 2

    sessions_alive = _surviving(
        UserSession.__table__,
        [v for k, v in ids.items() if k.startswith("session_")],
    )
    assert ids["session_retired_old"] not in sessions_alive
    assert ids["session_expired_old"] not in sessions_alive, (
        "the expires_at half of the condition did nothing"
    )
    assert ids["session_retired_fresh"] in sessions_alive
    assert ids["session_live"] in sessions_alive, "retention signed a user out"

    outbox_alive = _surviving(
        Outbox.__table__, [v for k, v in ids.items() if k.startswith("outbox_")]
    )
    assert ids["outbox_delivered_old"] not in outbox_alive
    assert ids["outbox_delivered_fresh"] in outbox_alive
    assert ids["outbox_pending_old"] in outbox_alive, "retention deleted an owed email"
    assert ids["outbox_parked_old"] in outbox_alive, "retention deleted a parked row"

    scoring_alive = _surviving(
        ScoringJob.__table__, [v for k, v in ids.items() if k.startswith("scoring_")]
    )
    assert ids["scoring_terminal_old"] not in scoring_alive
    assert ids["scoring_terminal_fresh"] in scoring_alive
    assert ids["scoring_queued_old"] in scoring_alive, "purge took a non-terminal job"

    resume_alive = _surviving(
        ResumeParseJob.__table__,
        [v for k, v in ids.items() if k.startswith("resume_")],
    )
    assert ids["resume_terminal_old"] not in resume_alive
    assert ids["resume_terminal_fresh"] in resume_alive
    assert ids["resume_queued_old"] in resume_alive, "purge took a non-terminal job"


def test_retention_run_on_an_empty_database_deletes_nothing_and_exits_zero(ctx, sent):
    exit_code, payload, _ = _invoke(ctx, "retention", "run")

    assert exit_code == 0
    assert payload["outbox_deleted"] == 0
    assert payload["scoring_jobs_deleted"] == 0
    assert payload["resume_jobs_deleted"] == 0
    assert payload["sessions_expired"] == 0
    assert payload["sessions_deleted"] == 0


def test_retention_run_leaves_a_live_session_alone_at_any_window(ctx, sent):
    """The window is a floor on deletion, never a licence to reach a live row.

    Run with `--session-days 0`, which makes every *dead* row deletable
    immediately. A live session must still survive it, because what protects it
    is `retired_at IS NULL AND expires_at > now()` and not the size of the
    window -- and an implementation that filtered on age alone would pass the
    default-window test above and fail here.
    """
    import sqlalchemy as sa

    from model import UserSession, db

    ids = _seed_retention_matrix(ctx)
    db.session.commit()

    exit_code, payload, _ = _invoke(ctx, "retention", "run", "--session-days", "0")

    assert exit_code == 0
    assert payload["sessions_deleted"] == 3, "expected every dead row, and only those"

    with db.engine.connect() as conn:
        alive = {
            row.id
            for row in conn.execute(
                sa.select(UserSession.__table__.c.id).where(
                    UserSession.__table__.c.id.in_(
                        [v for k, v in ids.items() if k.startswith("session_")]
                    )
                )
            )
        }
    assert alive == {ids["session_live"]}
