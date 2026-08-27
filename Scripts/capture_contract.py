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

Both need `DATABASE_URL` pointing at a throwaway database. Both **destroy every
object in it** -- the same `DROP SCHEMA public CASCADE` a fresh start requires --
so the guard `tests/conftest.py` uses is imported and applied here rather than
re-implemented, because a second copy of a safety check is a copy that drifts.

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

# Order matters: CSRF tokens hold no timestamp, but masking timestamps first would
# not touch them either. Doing CSRF first keeps each pattern responsible for one thing.
_CSRF_VALUE = re.compile(r'("csrf_?[Tt]oken"\s*:\s*)"[^"]*"')
_ISO_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)


def _mask(text: str) -> str:
    """Replace the two values that legitimately differ between runs."""
    text = _CSRF_VALUE.sub(r'\1"<CSRF>"', text)
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
    _load_conftest_guard()

    from app import app
    from model import User, db

    app.config["TESTING"] = True
    _silence_outbound_email()

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
