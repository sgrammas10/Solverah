"""Record the exact bytes the identity and profile endpoints return.

Phase 2c moves the user row: `user` becomes `users`, `email_confirmed` becomes a
nullable `email_confirmed_at`, `password` becomes `password_hash`, the primary key
becomes an identity column, and a `public_id` appears alongside the integer `id`.
None of that is allowed to reach the wire. This script and its pair,
`verify_contract.py`, are the evidence.

    # on the commit before the change
    python -m Scripts.capture_contract

    # after it
    python -m Scripts.verify_contract

Both **destroy every object** in the database they run against -- the same
`DROP SCHEMA public CASCADE` a fresh start requires -- so the guard
`tests/conftest.py` uses is imported and applied here rather than re-implemented,
because a second copy of a safety check is a copy that drifts. Left alone they
use `solverah_contract`, which is theirs alone; `DATABASE_URL` overrides it, and
pointing that at the database another tool is using is the one way to get the
2026-08-27 failure back.

**Why raw text and not parsed JSON.** `json.loads(a) == json.loads(b)` is blind to
key order, to `1` versus `1.0`, and to the whitespace a serializer emits. "Byte-identical"
has to mean bytes, so the comparison is on the response body as a string.

**What is masked, and why that is safe.** Two classes of value change on every run
and would drown the diff: the CSRF token, and timestamps. Each is replaced with a
sentinel (`<CSRF>`, `<TS>`) rather than deleted. Replacement rather than deletion is
what keeps the mask honest: a boolean `true` that regressed into a timestamp string
still diffs, because `true` and `"<TS>"` are not the same text. Nothing else is
masked -- `id` in particular is recorded verbatim, since "the id on the wire is
still the integer" is one of the things being proved.

The scenario deliberately includes the failure paths. `403 Email not confirmed`
exercises the `email_confirmed_at IS NOT NULL` derivation from the side where it
returns false, which the happy path never reaches.

**Extended for Phase 2d (assessment storage unification).** The 2c scenario never
touched an assessment, so every `session` capture in it had `wpl_completed`,
`wpll_completed` and `wp_v2_completed` false -- three booleans that are trivially
byte-identical when nothing ever sets them. 2d moves all five instruments onto
`assessment_forms` + `assessment_submissions`, so the scenario now submits all
five, re-reads the three that store a result, claims an anonymous WPLL session
onto the account (the path that actually writes the `wpll_*` state), and captures
the catalogue and the session with the flags **true**. `export` and
`me-profile-after-write` are captured after all of that rather than before, so the
`legacy_quiz` block and the two profile-document result keys are in the diff too.

**The LLM is stubbed, and the prompt builders with it.** Three instruments call a
provider; a fixture that depended on one could not produce stable bytes, and the
narrative text is the whole payload for two of them. `_chat_json` is replaced by a
lookup keyed off a marker the stubbed prompt builders emit, so Work Pulse and
ManagerMatch -- which share `OPENAI_WP_MODEL` -- stay distinguishable. The
builders are still *called* with whatever the handler passes them, so a handler
that stopped being able to read its inputs still fails here; what those inputs
contain is not on the wire and is asserted in `tests/test_assessment_storage.py`
instead.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / "docs" / "contract_baseline.json"

EMAIL = "contract-primary@example.test"
UNCONFIRMED_EMAIL = "contract-unconfirmed@example.test"
PASSWORD = "Strongpass1!"

#: Same literal every person-side test uses. `respondent_id_for_user` has no
#: default by design (D-05) and this script runs with SOLVERAH_IGNORE_DOTENV=1,
#: so without it `/assessments/core/form` is a 500 on both sides of the diff --
#: identical bytes proving nothing.
FORM_TOKEN_SECRET = "test-secret-not-a-real-one"

#: This script's own database -- not the suite's `solverah_test`, and not the
#: `solverah` that `make dev` uses.
#:
#: `_reset_schema` below runs DROP SCHEMA public CASCADE. Until 2026-08-27 this
#: script inherited its URL from `tests/conftest.py`'s setdefault, which was the
#: dev database, which `make test-pg` also used: running a capture while a suite
#: was in flight dropped the schema out from under it, and vice versa. What that
#: produced was 132 collection errors naming `user_role` -- the first enum
#: create_all emits, so the first object two racing processes collide on, and
#: nothing at all to do with the phase it was blamed on for hours.
#:
#: setdefault, not a hard assignment: capturing against a scratch database is a
#: reasonable thing to want, and DATABASE_URL is how you ask for it. The guard
#: borrowed from conftest still refuses anything non-local either way.
#:
#: Created by infra/docker/initdb/02-lane-databases.sql on the stack's first
#: start, on port 5433 -- see infra/docker/compose.yml for why not 5432.
CONTRACT_DATABASE_URL = "postgresql://solverah:solverah@localhost:5433/solverah_contract"

WPLL_ANSWERS = [
    {"question_id": "wpll-q%d" % i, "option_id": "wpll-q%d-c" % i} for i in range(1, 6)
]
WP_ANSWERS = [
    {"question_id": "wp-q%d" % i, "option_id": "wp-q%d-b" % i} for i in range(1, 13)
]
MM_ANSWERS = [{"question_id": "mm-q%d" % i, "choice": "a"} for i in range(1, 16)]

FOCUS_TYPE_PAYLOAD = {
    "scene_1": ["big_project", "planning_doc", "urgent_client", "teammate_feedback",
                "emails", "admin_tasks"],
    "scene_2": {
        "now": ["email_client_important", "slack_mentioned"],
        "later": ["slack_teammate_question"],
        "ignore": ["email_newsletter", "calendar_meeting_invite", "task_new_ticket",
                   "task_planning_doc", "slack_team_channel", "email_system_report",
                   "calendar_team_lunch"],
    },
    "scene_3": {"deep_solo": 2.5, "planning": 0.5, "social": 0.5, "breaks": 0.25,
                "exploring": 0.25},
    "scene_4": {
        "now": ["deep_research"],
        "tomorrow": ["reply_teammate", "write_report_draft", "update_task_tracker",
                     "quick_call_unblock", "send_followup_email", "review_others_work",
                     "sketch_tomorrow_plan"],
        "avg_decision_time_ms": 500,
    },
    "scene_5": ["deep_work", "wind_down"],
}

#: Canned provider replies, keyed by the marker the stubbed prompt builders emit.
#: Work Pulse and ManagerMatch both run on `OPENAI_WP_MODEL`, so the model
#: environment variable cannot tell them apart and the marker is what does.
_LLM_REPLIES = {
    "WP": {
        "narrative": "You do your best work in long uninterrupted stretches.",
        "emerging_signals": ["depth over breadth", "low tolerance for context switching"],
        "archetype": "The Deep Worker",
        "archetype_description": "Sustained focus is where your output comes from.",
    },
    "MM": {
        "narrative": "You want a manager who sets direction and then gets out of the way.",
        "what_to_look_for": ["clear written goals", "few standing meetings"],
        "red_flags": ["decisions that only happen in the room"],
        "archetype_description": "Autonomy with an explicit target.",
    },
    "WPLL": {"insight_text": "You are drawn to work with a visible finish line."},
}

# Order matters: CSRF tokens hold no timestamp, but masking timestamps first would
# not touch them either. Doing CSRF first keeps each pattern responsible for one thing.
_CSRF_VALUE = re.compile(r'("csrf_?[Tt]oken"\s*:\s*)"[^"]*"')
_ISO_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)
#: A sitting's id is random per run and cannot be compared literally. The
#: character class is the assertion: 32 lowercase hex, no dashes, which is what
#: `uuid4().hex` produced before 2d and what `assessment_submissions.public_id`
#: (a uuidv7 -- same 128 bits, same `.hex`) produces after it. If the format ever
#: moves -- a dashed UUID, a bare integer, a longer token -- this pattern stops
#: matching and the raw value lands in the diff as a difference. That is the
#: whole reason the masks replace rather than delete.
_SUBMISSION_ID = re.compile(r'("submission_id"\s*:\s*)"[0-9a-f]{32}"')
#: Every RFC 7807 problem body carries the request id that produced it, so it
#: joins to the logs. It is new to this baseline only because the 2c scenario
#: never reached a route that answers with one -- the errors it captured are the
#: legacy `{"error": "..."}` shape, which carries no id.
_REQUEST_ID = re.compile(r'("request_id"\s*:\s*)"[0-9a-f]{32}"')


def _mask(text: str) -> str:
    """Replace the four values that legitimately differ between runs."""
    text = _CSRF_VALUE.sub(r'\1"<CSRF>"', text)
    text = _SUBMISSION_ID.sub(r'\1"<SID>"', text)
    text = _REQUEST_ID.sub(r'\1"<RID>"', text)
    return _ISO_TIMESTAMP.sub("<TS>", text)


def _load_conftest_guard():
    """Borrow `tests/conftest.py`'s non-local-database guard.

    Imported rather than copied. This script calls `DROP SCHEMA public CASCADE`,
    which is strictly more destructive than the `db.drop_all()` that guard was
    written for, so it must not be possible for the two to disagree about which
    hosts are safe. Importing the module also applies conftest's `setdefault`
    environment, which is the same environment the suite runs under.
    """
    spec = importlib.util.spec_from_file_location(
        "_solverah_conftest", REPO_ROOT / "tests" / "conftest.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # runs the guard against DATABASE_URL
    return module


def _reset_schema(db) -> None:
    """Return the database to the state a first-ever run would find.

    `db.drop_all()` only drops what the *current* metadata declares, and the two
    sides of this diff have different metadata -- Phase 2c adds two enum types and
    a trigger function that the pre-change side has never heard of. A leftover
    `user_role` type would make the second run's `create_all` fail on a name
    collision, and a leftover row would make its ids start somewhere else. The
    schema goes, and the extensions Part 4 depends on come back.
    """
    from sqlalchemy import text

    db.session.remove()
    with db.engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        for extension in ("citext", "pg_trgm", "vector"):
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS %s" % extension))
    db.create_all()


def _silence_outbound_email() -> None:
    """No scenario step may depend on an SMTP server being reachable."""
    from solverah.infra import email as email_infra

    for name in dir(email_infra):
        if name.startswith("send_"):
            setattr(email_infra, name, lambda *_a, **_k: None)


def _stub_llm() -> None:
    """Make the three provider-backed instruments deterministic.

    Two things are replaced, and the split matters.

    The **prompt builders** become markers. That is what lets one `_chat_json`
    stub serve Work Pulse and ManagerMatch, which share `OPENAI_WP_MODEL` and are
    therefore indistinguishable by the argument the real function dispatches on.
    Replacing them here does *not* stop the handlers reading their inputs -- the
    call site still evaluates `intake.wpll_answers` and
    `intake.selected_statement_ids` before handing them over, so a handler that
    lost access to them still fails this script.

    `_chat_json` itself becomes a dict lookup. It is patched on the service
    module rather than on the OpenAI client because the client is constructed
    lazily inside it, and a stub at the client layer would have to imitate the
    SDK's response object to reach the same three lines.
    """
    from solverah.services import assessment_prompts, assessment_service

    assessment_prompts.build_wp_narrative_prompt = (
        lambda *_a, **_k: [{"role": "system", "content": "WP"}]
    )
    assessment_prompts.build_mm_narrative_prompt = (
        lambda *_a, **_k: [{"role": "system", "content": "MM"}]
    )
    assessment_prompts.build_wpll_insight_prompt = lambda *_a, **_k: ("WPLL", "WPLL")

    def _canned(messages, _model_env, _default_model):
        marker = messages[0]["content"] if isinstance(messages, list) else "WPLL"
        return dict(_LLM_REPLIES[marker])

    assessment_service._chat_json = _canned


def run_scenario() -> List[Dict[str, Any]]:
    """Drive the endpoints and return one masked record per request.

    Returns:
        A list of ``{step, method, path, status, mimetype, cookies_set, body}``
        dicts, in execution order. ``cookies_set`` is the cookie *names* the
        response sets: the names are contract, the values are secrets that differ
        every run.
    """
    os.environ.setdefault("APP_ENV", "testing")
    os.environ.setdefault("SOLVERAH_IGNORE_DOTENV", "1")
    # Before `_load_conftest_guard()`, which setdefaults the *suite's* database.
    # Whichever runs first wins, and this script must not be the one that ends up
    # dropping the schema the suite is using.
    os.environ.setdefault("DATABASE_URL", CONTRACT_DATABASE_URL)
    # Set, not setdefault: the value seeds the shuffle and salts the item tokens,
    # so a different one in the shell would reorder `/assessments/core/form` and
    # make the two sides of the diff disagree for a reason that is not a change.
    os.environ["SOLVERAH_FORM_TOKEN_SECRET"] = FORM_TOKEN_SECRET
    _load_conftest_guard()

    from app import app
    from model import User, db

    app.config["TESTING"] = True
    _silence_outbound_email()
    _stub_llm()

    records: List[Dict[str, Any]] = []

    def record(step: str, resp, method: str, path: str) -> None:
        records.append(
            {
                "step": step,
                "method": method,
                "path": path,
                "status": resp.status_code,
                "mimetype": resp.mimetype,
                "cookies_set": sorted(
                    {
                        value.split("=", 1)[0]
                        for key, value in resp.headers
                        if key.lower() == "set-cookie"
                    }
                ),
                "body": _mask(resp.get_data(as_text=True)),
            }
        )

    with app.app_context():
        _reset_schema(db)

    client = app.test_client()

    def call(step, method, path, **kwargs):
        resp = getattr(client, method.lower())(path, **kwargs)
        record(step, resp, method, path)
        return resp

    # -- registration and confirmation -------------------------------------
    call(
        "register",
        "POST",
        "/api/v1/auth/register",
        json={
            "email": EMAIL,
            "password": PASSWORD,
            "name": "Contract User",
            "role": "job-seeker",
            "terms_accepted": True,
        },
    )
    call(
        "register-duplicate",
        "POST",
        "/api/v1/auth/register",
        json={
            "email": EMAIL,
            "password": PASSWORD,
            "name": "Contract User",
            "role": "job-seeker",
            "terms_accepted": True,
        },
    )
    # A second account that is never confirmed, so the 403 branch below has a
    # subject. Its login attempt is the only step that reads
    # `email_confirmed` while it is false.
    call(
        "register-second",
        "POST",
        "/api/v1/auth/register",
        json={
            "email": UNCONFIRMED_EMAIL,
            "password": PASSWORD,
            "name": "Unconfirmed User",
            "role": "job-seeker",
            "terms_accepted": True,
        },
    )
    call(
        "login-before-confirmation",
        "POST",
        "/api/v1/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
    )

    with app.app_context():
        code = User.query.filter_by(email=EMAIL).first().confirmation_token

    call(
        "verify-email-wrong-code",
        "POST",
        "/api/v1/auth/email/verify",
        json={"email": EMAIL, "code": "000000"},
    )
    call(
        "verify-email",
        "POST",
        "/api/v1/auth/email/verify",
        json={"email": EMAIL, "code": code},
    )

    # -- login and the three endpoints under the governing rule ------------
    call(
        "login-wrong-password",
        "POST",
        "/api/v1/auth/login",
        json={"email": EMAIL, "password": "Wrongpass1!"},
    )
    login = call(
        "login", "POST", "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    csrf = {"X-CSRF-TOKEN": login.get_json()["csrfToken"]}

    call("session", "GET", "/api/v1/auth/session")
    call("me", "GET", "/api/v1/me")
    call("me-profile-empty", "GET", "/api/v1/me/profile")

    # -- writes, then the same three again ---------------------------------
    call("patch-me", "PATCH", "/api/v1/me", json={"name": "Renamed User"}, headers=csrf)
    call(
        "patch-me-profile",
        "PATCH",
        "/api/v1/me/profile",
        json={
            "profile": {
                "firstName": "Contract",
                "lastName": "User",
                "summary": "A profile that exercises every promoted column.",
                "phone": "",
                "linkedinUrl": "https://example.test/in/contract",
                "location": "Austin, TX",
                "career_status": "employed",
                "experience": [
                    {
                        "id": 1,
                        "company": "Acme",
                        "title": "Engineer",
                        "startDate": "2019-01-01",
                        "endDate": "Present",
                        "description": "Built things.",
                    }
                ],
                "education": [
                    {
                        "id": 2,
                        "school": "State University",
                        "degree": "BS",
                        "field": "Computer Science",
                        "endDate": "2018",
                        "gpa": "3.8",
                    }
                ],
                "skills": ["Python", "Node.js", "C++"],
                "certifications": ["AWS SAA"],
            }
        },
        headers=csrf,
    )
    call(
        "patch-career-status",
        "PATCH",
        "/api/v1/me/career-status",
        json={"status": "employed"},
        headers=csrf,
    )
    call("get-skills-before-rating", "GET", "/api/v1/me/skills")
    call(
        "put-skills",
        "PUT",
        "/api/v1/me/skills",
        json={
            "skills": [
                {"name": "Python", "proficiency": "advanced"},
                {"name": "Node.js", "proficiency": "intermediate"},
            ]
        },
        headers=csrf,
    )
    call("get-skills", "GET", "/api/v1/me/skills")

    # -- the five assessments (Phase 2d) -----------------------------------
    #
    # Ordered so the not-yet-completed answers are recorded before the
    # completed ones. A 404 from `/me/assessments/work_pulse/result` is as much
    # a part of the contract as the 200 that follows it, and it is the one an
    # unmigrated read path would turn into a 500.
    call("assessments-catalogue-before", "GET", "/api/v1/assessments")
    call("assessment-form-unknown-kind", "GET", "/api/v1/assessments/nope/form")
    call("assessment-form-no-server-form", "GET", "/api/v1/assessments/work_pulse/form")
    core_form = call("assessment-form-core", "GET", "/api/v1/assessments/core/form")
    call("result-work-pulse-before", "GET", "/api/v1/me/assessments/work_pulse/result")
    call("result-focus-type-before", "GET", "/api/v1/me/assessments/focus_type/result")
    call("result-core-absent-by-design", "GET", "/api/v1/me/assessments/core/result")

    # `wpll` is the one instrument whose submit route persists nothing: the
    # stored state arrives from the anonymous session being claimed onto the
    # account, which is the write path 2d moves off `user_intake`.
    call(
        "claim-wpll-session",
        "POST",
        "/api/v1/intake/claims",
        json={
            "mode": "session",
            "selected_statement_ids": ["dir-1", "sus-2"],
            "wpll_answers": WPLL_ANSWERS,
            "wpll_insight_text": "Claimed from the anonymous session.",
        },
        headers=csrf,
    )

    call(
        "submit-wpll",
        "POST",
        "/api/v1/assessments/wpll/submissions",
        json={"answers": WPLL_ANSWERS},
    )
    call(
        "submit-work-pulse-too-few-answers",
        "POST",
        "/api/v1/assessments/work_pulse/submissions",
        json={"answers": WP_ANSWERS[:3]},
        headers=csrf,
    )
    call(
        "submit-work-pulse",
        "POST",
        "/api/v1/assessments/work_pulse/submissions",
        json={"answers": WP_ANSWERS},
        headers=csrf,
    )
    call(
        "submit-focus-type",
        "POST",
        "/api/v1/assessments/focus_type/submissions",
        json=FOCUS_TYPE_PAYLOAD,
        headers=csrf,
    )
    call(
        "submit-manager-match",
        "POST",
        "/api/v1/assessments/manager_match/submissions",
        json={"answers": MM_ANSWERS},
        headers=csrf,
    )

    # `core` answers the form it was just served: the tokens are salted per
    # respondent, so they cannot be hard-coded here.
    core_responses = {
        item["token"]: item["options"][0]["key"]
        for block in (core_form.get_json() or {}).get("blocks", [])
        for item in block["items"]
    }
    call(
        "submit-core",
        "POST",
        "/api/v1/assessments/core/submissions",
        json={"responses": core_responses},
        headers=csrf,
    )

    call("result-work-pulse", "GET", "/api/v1/me/assessments/work_pulse/result")
    call("result-focus-type", "GET", "/api/v1/me/assessments/focus_type/result")
    call("result-manager-match", "GET", "/api/v1/me/assessments/manager_match/result")
    call("result-wpll-not-stored", "GET", "/api/v1/me/assessments/wpll/result")
    call("assessments-catalogue-after", "GET", "/api/v1/assessments")

    call("me-after-write", "GET", "/api/v1/me")
    call("me-profile-after-write", "GET", "/api/v1/me/profile")
    call("session-after-write", "GET", "/api/v1/auth/session")
    call("dashboard", "GET", "/api/v1/me/dashboard")
    call("export", "GET", "/api/v1/me/export")

    # -- the unconfirmed account, and logout -------------------------------
    call(
        "login-unconfirmed",
        "POST",
        "/api/v1/auth/login",
        json={"email": UNCONFIRMED_EMAIL, "password": PASSWORD},
    )
    call("logout", "POST", "/api/v1/auth/logout", headers=csrf)
    call("session-after-logout", "GET", "/api/v1/auth/session")

    return records


def main(argv: List[str]) -> int:
    target = Path(argv[1]) if len(argv) > 1 else BASELINE
    records = run_scenario()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("captured %d responses -> %s" % (len(records), target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
