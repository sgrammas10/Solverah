"""Pilot form, end to end against the test database: CSV -> the app's own doorways ->
training rows labelled 'pilot_form'; idempotency; respondent emails never reach the
database; the report-back text carries words and no numbers.

The importer is driven both as a function (import_parsed) and through its CLI (main),
because the guard's database-name rule admits this lane's `solverah_pilot_test`.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from causal_graph.v1_model.pilot_form import (  # noqa: E402
    import_responses,
    report_back,
    responses,
    sample_csv,
    spec,
)

import assemble_training_data as atd  # noqa: E402  -- on sys.path via the package

_CFG_PATH = REPO_ROOT / "causal_graph" / "v1_model" / "solverah_model_config.yaml"

REAL_EMAIL = "real.person.do.not.store@example.org"


@pytest.fixture(scope="module")
def mapping():
    return responses.load_mapping()


def _cfg():
    return yaml.safe_load(_CFG_PATH.read_text(encoding="utf-8"))


def _rows(mapping):
    """A employed + previous job + email; B between jobs, not-sure comp and industry;
    C first job; D employed, no previous job."""
    return [
        sample_csv.respondent(
            mapping, status="employed", timestamp="10/2/2026 9:00:00", previous=True,
            email=REAL_EMAIL, followup=spec.FOLLOWUP_YES, env_keys={"env-autonomy-1": "e", "env-autonomy-2": "a"},
            stage_size=4, comp=4, industry="tech", experienced=5),
        sample_csv.respondent(
            mapping, status="between_jobs", timestamp="10/2/2026 9:05:00",
            comp=None, industry=None, experienced=2, env_key="b"),
        sample_csv.respondent(mapping, status="first_job", timestamp="10/2/2026 9:10:00",
                              email="first.job@example.org"),
        sample_csv.respondent(mapping, status="employed", timestamp="10/2/2026 9:15:00",
                              core_pattern="BA", env_key="d", experienced=3),
    ]


def _parsed(mapping):
    return responses.parse_csv(sample_csv.to_csv(mapping, _rows(mapping)), mapping)


def _import(parsed):
    from app import app
    from model import db

    with app.app_context():
        return import_responses.import_parsed(db, parsed)


def _assemble():
    from app import app
    from model import db

    with app.app_context():
        with db.engine.connect() as conn:
            return atd.assemble_environment_training_data(conn, _cfg())


def _user_id(pilot_id):
    from app import app
    from model import User

    with app.app_context():
        user = User.query.filter_by(email=import_responses.pilot_email(pilot_id)).first()
        return None if user is None else user.id


# ---------------------------------------------------------------------------
# The import produces training rows, labelled
# ---------------------------------------------------------------------------
def test_a_fixture_csv_becomes_pilot_form_training_rows(client, mapping):
    import assessment_form
    from work_pulse import situation, situation_items

    parsed = _parsed(mapping)
    a, b, c, d = parsed
    summary = _import(parsed)

    assert summary.failed == [] and summary.skipped == []
    assert (summary.imported, summary.current_reports, summary.past_reports,
            summary.first_job) == (4, 3, 1, 1)

    result = _assemble()
    assert result.dropped == []
    assert len(result.rows) == 4
    assert {r.respondent_source for r in result.rows} == {"pilot_form"}

    by_user = {}
    for index, row in enumerate(result.rows):
        by_user.setdefault(row.user_id, []).append((index, row))

    # A: one current row, one past row, same person side.
    rows_a = by_user[_user_id(a.pilot_id)]
    assert [r.report_subject for _, r in rows_a] == ["current", "past"]
    (ia, cur), (ip, past) = rows_a
    assert cur.career_status == "employed" and cur.current_report_ordinal == 1
    assert past.current_report_ordinal is None
    assert int(result.outcome[ia]) == 5 and int(result.outcome[ip]) == 2
    expected_env = situation.score_environment(
        a.current.answers, situation_items.item_spec("employed"))
    for dim, value in expected_env.items():
        assert result.env[dim][ia] == pytest.approx(value)
    expected_person = assessment_form.score_stored_choices(a.core_choices)
    for dim, value in expected_person.items():
        assert result.person[dim][ia] == pytest.approx(value)
        assert result.person[dim][ip] == pytest.approx(value)
    assert result.conf["stage_size"][ia] == 4.0
    assert result.conf["industry"][ia] == "tech"
    # The previous job's "not sure" comp and industry are masked, not guessed.
    assert np.isnan(result.conf["comp"][ip]) and result.conf_missing["comp"][ip]
    assert result.conf["industry"][ip] is None and result.conf_missing["industry"][ip]

    # B: between jobs, a current row in the past-tense section, not-sure masked.
    [(ib, row_b)] = by_user[_user_id(b.pilot_id)]
    assert row_b.career_status == "between_jobs" and row_b.report_subject == "current"
    assert result.conf_missing["comp"][ib] and result.conf_missing["industry"][ib]
    assert int(result.outcome[ib]) == 2

    # C: first job -- a user and a core sitting, no environment report, no row.
    assert _user_id(c.pilot_id) is not None
    assert _user_id(c.pilot_id) not in by_user

    # D: employed, no previous job -> exactly one current row.
    assert [r.report_subject for _, r in by_user[_user_id(d.pilot_id)]] == ["current"]


def test_the_rows_are_stamped_with_the_apps_own_versions(client, mapping):
    from work_pulse import situation_items

    _import(_parsed(mapping))
    result = _assemble()
    assert {r.env_form_version for r in result.rows} == {situation_items.FORM_VERSION}
    assert {r.person_form_version for r in result.rows} == {mapping["core_form_version"]}


def test_app_users_stay_app_beside_pilot_respondents(client, mapping):
    import assessment_store
    import environment_report_store
    from app import app
    from model import User, db
    from work_pulse import situation, situation_items

    _import(_parsed(mapping)[:1])
    answers = {i["item_id"]: "c" for i in situation_items.ENVIRONMENT_ITEMS}
    with app.app_context():
        from causal_graph.v1_model.devfit.seed_synthetic import UNUSABLE_PASSWORD_HASH

        user = User(email="an.app.user@example.com", password_hash=UNUSABLE_PASSWORD_HASH)
        db.session.add(user)
        db.session.flush()
        assessment_store.persist_submission(
            db, user.id, import_responses.scored_submission(
                {c["item_id"]: "A" for c in mapping["columns"] if c["role"] == "core"}))
        environment_report_store.write_environment_report(
            db, user.id, raw_answers=answers,
            dimension_scores=situation.score_environment(
                answers, situation_items.item_spec("employed")),
            stage_size=3, comp=3, experienced_outcome=4, career_status="employed",
            version=situation_items.FORM_VERSION)
        db.session.commit()
        app_id = user.id

    result = _assemble()
    sources = {r.user_id: r.respondent_source for r in result.rows}
    assert sources[app_id] == "app"
    assert sorted(set(sources.values())) == ["app", "pilot_form"]


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------
def test_importing_the_same_csv_twice_adds_nothing(client, mapping):
    from app import app
    from model import EnvironmentReport, User

    first = _import(_parsed(mapping))
    before = _assemble()
    with app.app_context():
        users = User.query.count()
        reports = EnvironmentReport.query.count()

    second = _import(_parsed(mapping))
    assert first.imported == 4
    assert (second.imported, second.already_imported, second.failed) == (0, 4, [])

    after = _assemble()
    with app.app_context():
        assert User.query.count() == users
        assert EnvironmentReport.query.count() == reports
    assert [r.environment_report_id for r in after.rows] == [
        r.environment_report_id for r in before.rows]


def test_a_later_export_imports_only_the_new_rows(client, mapping):
    rows = _rows(mapping)
    _import(responses.parse_csv(sample_csv.to_csv(mapping, rows[:2]), mapping))
    summary = _import(responses.parse_csv(sample_csv.to_csv(mapping, rows), mapping))
    assert (summary.imported, summary.already_imported) == (2, 2)


# ---------------------------------------------------------------------------
# Respondent emails
# ---------------------------------------------------------------------------
def test_respondent_emails_never_reach_the_database(client, mapping, tmp_path):
    from sqlalchemy import select

    from app import app
    from model import db

    parsed = _parsed(mapping)
    summary = _import(parsed)
    written = import_responses.write_emails(tmp_path / "emails.csv", parsed, summary.present)
    assert written == 2
    emails_text = (tmp_path / "emails.csv").read_text(encoding="utf-8")
    assert "%s,%s,yes" % (parsed[0].pilot_id, REAL_EMAIL) in emails_text
    assert "first.job@example.org,no" in emails_text

    with app.app_context():
        with db.engine.connect() as conn:
            for table in db.metadata.sorted_tables:
                for row in conn.execute(select(table)).all():
                    flat = repr(tuple(row))
                    assert REAL_EMAIL not in flat, table.name
                    assert "first.job@example.org" not in flat, table.name
                    # The consent travels with the email only, never into the DB.
                    assert spec.FOLLOWUP_CHOICES[0][0] not in flat, table.name
                    assert "followup" not in flat, table.name
    assert all(p.email is None or "@" in p.email for p in parsed)


def test_a_respondent_that_fails_is_rolled_back_whole(client, mapping, monkeypatch):
    from solverah.services import situation_report_service

    def refuse(user, payload):
        return situation_report_service.SituationReportResult(400, {"error": "nope"})

    monkeypatch.setattr(situation_report_service, "submit_environment_report", refuse)
    parsed = _parsed(mapping)
    summary = _import(parsed[:1])
    assert len(summary.failed) == 1 and "nope" in summary.failed[0][2]
    assert _user_id(parsed[0].pilot_id) is None  # no orphan user, profile or sitting


# ---------------------------------------------------------------------------
# The CLI, end to end on this lane's database
# ---------------------------------------------------------------------------
def test_the_import_cli_runs_against_a_guarded_local_database(client, mapping, tmp_path,
                                                              monkeypatch, capsys):
    url = os.environ["DATABASE_URL"]
    if not url.rsplit("/", 1)[-1].startswith("solverah_pilot"):
        pytest.skip("this lane's database is not a solverah_pilot* database")
    monkeypatch.setenv("SOLVERAH_IGNORE_DOTENV", "1")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("APP_ENV", "testing")

    csv_path = tmp_path / "responses.csv"
    csv_path.write_text(sample_csv.to_csv(mapping, _rows(mapping)), encoding="utf-8")
    emails = tmp_path / "private" / "emails.csv"
    assert import_responses.main([str(csv_path), "--emails-out", str(emails)]) == 0
    out = capsys.readouterr().out
    out.encode("ascii")
    assert "imported now:          4" in out
    assert REAL_EMAIL not in out
    assert emails.exists()

    assert import_responses.main([str(csv_path), "--emails-out", str(emails)]) == 0
    assert "already imported:      4" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Report back: words, no numbers
# ---------------------------------------------------------------------------
def _report(pilot_id):
    from app import app

    with app.app_context():
        return report_back.report_for_pilot_id(pilot_id)


def _payload_numbers(pilot_id):
    from app import app
    from model import User
    from solverah.services import situation_report_service

    with app.app_context():
        user = User.query.filter_by(email=import_responses.pilot_email(pilot_id)).first()
        body = situation_report_service.get_situation_report(user).body
    return body, [d.get("env_score") for d in body.get("dimensions", [])]


def test_the_report_is_the_apps_content_in_words_only(client, mapping):
    a, b, c, _d = _parsed(mapping)
    _import([a, b, c])

    text = _report(a.pilot_id)
    body, scores = _payload_numbers(a.pilot_id)
    assert body["state"] == "complete" and scores
    assert text.startswith("You, and this job")
    assert not re.search(r"\d", text)
    for score in scores:
        assert repr(score) not in text
    labels = set(report_back.BUCKET_LABELS.values())
    assert any(label in text for label in labels)
    for entry in body["dimensions"]:
        assert report_back.DIMENSION_LABELS[entry["dimension"]] in text
        if entry["bucket"] != "aligned":
            assert entry["diagnosis"]["headline"].split()[0] in text
    # The list is in the service's order -- the ranking -- and nothing else orders it.
    order = [report_back.DIMENSION_LABELS[e["dimension"]] for e in body["dimensions"]]
    positions = [text.index("\n%s -- " % name) for name in order]
    assert positions == sorted(positions)
    assert body["guidance_notice"].split()[0] in text


def test_a_between_jobs_report_faces_forward(client, mapping):
    _a, b, _c, _d = _parsed(mapping)
    _import([b])
    text = _report(b.pilot_id)
    assert text.startswith("What to look for next")
    assert "Less than you need " not in text and "More than you need " not in text
    assert not re.search(r"\d", text)


def test_first_job_and_unknown_ids_get_no_report(client, mapping):
    _a, _b, c, _d = _parsed(mapping)
    _import([c])
    assert _report(c.pilot_id).startswith("No report for this respondent")
    assert _report("0123456789abcdef") is None


def test_a_digit_in_the_rendered_text_is_refused():
    body = {
        "state": "complete", "needs_forward": False, "guidance_notice": "notice",
        "dimensions": [{"dimension": "pace", "bucket": "aligned", "env_score": 0.7,
                        "rank": 1, "aligned_note": "Fits at 0.7."}],
    }
    with pytest.raises(report_back.ReportLeak):
        report_back.render_report(body)
    body["dimensions"][0]["aligned_note"] = "Fits."
    text = report_back.render_report(body)
    assert "0.7" not in text and "Pace -- Aligned" in text


def test_the_report_cli_writes_outside_the_repo_only(client, mapping, tmp_path,
                                                     monkeypatch, capsys):
    url = os.environ["DATABASE_URL"]
    if not url.rsplit("/", 1)[-1].startswith("solverah_pilot"):
        pytest.skip("this lane's database is not a solverah_pilot* database")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("APP_ENV", "testing")
    a, *_rest = _parsed(mapping)
    _import([a])

    with pytest.raises(import_responses.UnsafeOutputPath):
        report_back.main([a.pilot_id, "--out", str(REPO_ROOT / "report.txt")])
    out_file = tmp_path / "reports" / "a.txt"
    assert report_back.main([a.pilot_id, "--out", str(out_file)]) == 0
    capsys.readouterr().out.encode("ascii")
    text = out_file.read_text(encoding="utf-8")
    assert text.startswith("You, and this job") and not re.search(r"\d", text)
