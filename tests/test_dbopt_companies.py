"""DB ledger, Package F: the company list, culture matching and the agent chat.

The headline finding: ``GET /me/matches`` and ``GET /companies`` both loaded the
whole ``company`` table -- ``profile_json``, the entire research document,
included -- on every page request, and paged the result in Python.

The first half of this file is characterisation, recorded from the code before
the change and required to hold after it: every page of both lists, byte for
byte, through the edge cases a keyset gets wrong -- the last page, an empty
filter result, a cursor from an earlier page, and a cursor whose row has since
gone or no longer matches the filter. The recording holds a SHA-256 of each
response body next to a readable summary of it; a mismatch prints both records.

The second half is regression tests, each run against the code before its fix
to watch it fail:

* a ``/companies`` page read every row, with ``profile_json``;
* ``/me/matches`` read ``profile_json`` for every company, not just the page;
* ``resolve_culture_preferences`` assembled the whole profile document (six
  statements) to read one key, and read the Work Pulse row's narrative too;
* ``backfill_culture_preferences`` loaded and rewrote the whole document, read
  the Work Pulse row, and committed -- once per user -- and overwrote a value
  that landed between its emptiness check and its write;
* an agent chat turn loaded the profile document twice and sampled ten whole
  company rows in no particular order.
"""

import contextlib
import hashlib
import json
import re

import pytest
import sqlalchemy as sa
from sqlalchemy import event

from tests.query_count import count_queries

EMAIL = "dbopt-f@example.test"
DERIVED_EMAIL = "dbopt-f-derived@example.test"
PASSWORD = "Strongpass1!"

#: The stored culture preferences the matches walks score against.
PREFS = {
    "empathy": 0.8, "creative_drive": 0.6, "adaptability": 0.4, "futuristic": 0.7,
    "harmony": 0.5, "data_orientation": 0.3, "pace": "fast",
    "work_environment": "collaborative, remote",
}

#: A second preference vector, for the page walk whose scores change mid-walk.
OTHER_PREFS = {
    "empathy": 0.2, "creative_drive": 0.9, "adaptability": 0.8, "futuristic": 0.9,
    "harmony": 0.2, "data_orientation": 0.7, "pace": "very-fast",
    "work_environment": "startup, remote",
}

#: Twelve Work Pulse answers the derivation turns into a preference vector.
WORK_PULSE_ANSWERS = [
    {"question_id": "wp-q%d" % i, "option_id": "wp-q%d-b" % i} for i in range(1, 13)
]

_NO_KEY = "<overview has no industry key>"
_NO_OVERVIEW = "<profile_json has no overview>"

#: ``(id, name, industry, pace, work_environment, empathy, creative_drive,
#: adaptability, futuristic, harmony, data_orientation)``.
#:
#: Ids run in a different order from names, so a cursor's id and its position
#: disagree. Names repeat prefixes, mix case, spaces and punctuation -- the
#: database orders them by its collation, Python compares them by code point,
#: and the two disagree about ``eBay`` and ``iRobot`` in particular. Three rows
#: have no ``pace`` (never scored), one has a NULL score column (skipped as
#: invalid), one has a pace outside the enum, two sets of rows tie on every
#: culture column (so on fit score), and the industries cover case variants, a
#: stored value with spaces, an empty string, JSON null, a missing key, a
#: missing ``overview`` and a non-ASCII value.
SEED = [
    (7, "Acme 01", "Tech", "fast", "collaborative", 0.80, 0.60, 0.40, 0.70, 0.50, 0.30),
    (23, "Acme 02", "tech", "fast", "collaborative, remote", 0.70, 0.60, 0.40, 0.70, 0.50, 0.30),
    (3, "Acme 03", "Health", "moderate", "structured", 0.20, 0.30, 0.90, 0.10, 0.80, 0.90),
    (30, "Acme 10", "TECH", "very-fast", "remote", 0.50, 0.50, 0.50, 0.50, 0.50, 0.50),
    (12, "Acme North", "Finance", None, "remote", 0.60, 0.60, 0.60, 0.60, 0.60, 0.60),
    (18, "Acme-Labs", "Tech", "fast", "collaborative", 0.80, 0.60, 0.40, 0.70, 0.50, 0.30),
    (5, "AcmeCorp", "Retail", "slow", "hierarchical", 0.10, 0.20, 0.30, 0.20, 0.40, 0.10),
    (26, "acme ventures", "Finance", "moderate", "collaborative", 0.60, 0.70, 0.60, 0.80, 0.40, 0.50),
    (14, "Beacon", None, "fast", "remote", 0.55, 0.45, 0.65, 0.35, 0.60, 0.40),
    (2, "Beacon Health", "Health", "fast", "collaborative", 0.90, 0.40, 0.50, 0.60, 0.70, 0.20),
    (21, "Beacon Labs", "Tech", "chaotic", "startup", 0.30, 0.90, 0.80, 0.90, 0.20, 0.60),
    (9, "Cobalt", _NO_KEY, "moderate", None, 0.40, 0.40, 0.40, 0.40, 0.40, 0.40),
    (27, "Cobalt Systems", "Tech", "fast", "collaborative", None, 0.50, 0.50, 0.50, 0.50, 0.50),
    (1, "Delta & Co", "Finance", "moderate", "structured, remote", 0.45, 0.55, 0.35, 0.65, 0.45, 0.35),
    (16, "Delta Co", "finance", None, None, None, None, None, None, None, None),
    (11, "eBay", "Retail", "fast", "remote", 0.65, 0.55, 0.45, 0.75, 0.35, 0.25),
    (29, "Echo Analytics", "Tech", "fast", "data-driven", 0.30, 0.40, 0.60, 0.70, 0.30, 0.95),
    (4, "Foxtrot", "", "slow", "collaborative", 0.75, 0.65, 0.40, 0.70, 0.55, 0.30),
    (20, "Gamma Bank", "Finance", "moderate", "hierarchical", 0.35, 0.25, 0.30, 0.40, 0.70, 0.85),
    (8, "Gamma Bank Two", "Finance", "moderate", "hierarchical", 0.35, 0.25, 0.30, 0.40, 0.70, 0.85),
    (25, "Helix Bio", "Health", "fast", "collaborative, remote", 0.85, 0.65, 0.45, 0.75, 0.55, 0.35),
    (13, "iRobot", "Tech", "fast", "startup, remote", 0.40, 0.80, 0.70, 0.95, 0.30, 0.70),
    (6, "Indigo Finance", " Finance ", "moderate", "structured", 0.50, 0.40, 0.50, 0.40, 0.50, 0.60),
    (19, "Juniper", "Hospitality", "slow", "collaborative", 0.95, 0.50, 0.50, 0.30, 0.90, 0.20),
    (10, "Kestrel", "Tech", None, None, None, None, None, None, None, None),
    (24, "Lumen", _NO_OVERVIEW, "fast", "remote", 0.70, 0.70, 0.70, 0.70, 0.70, 0.70),
    (15, "Meridian", "Health", "moderate", "collaborative", 0.60, 0.50, 0.50, 0.50, 0.60, 0.40),
    (22, "Nimbus", "Tech", "very-fast", "remote, startup", 0.20, 0.85, 0.90, 0.90, 0.10, 0.80),
    (17, "Orbit", "A\u00e9rospatiale", "fast", "collaborative", 0.80, 0.60, 0.40, 0.70, 0.50, 0.30),
    (28, "Zeta Caf\u00e9", "Food", "slow", "collaborative", 0.50, 0.30, 0.20, 0.30, 0.80, 0.20),
]

_CULTURE_COLUMNS = (
    "pace", "work_environment", "empathy", "creative_drive", "adaptability",
    "futuristic", "harmony", "data_orientation",
)

def _noop(*_args, **_kwargs):
    return None


@pytest.fixture()
def auth(client, monkeypatch):
    """Signs the test client in as ``EMAIL``."""
    monkeypatch.setattr("solverah.infra.email.send_confirmation_email", _noop)
    monkeypatch.setattr("solverah.services.audit.log_audit_event", _noop)
    return _sign_in(client, EMAIL)


def _sign_in(client, email):
    """Register, confirm and sign in *email*; returns the CSRF token."""
    from app import app
    from model import User, db

    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "name": "Ledger F",
              "role": "job-seeker", "terms_accepted": True},
    )
    with app.app_context():
        user = User.query.filter_by(email=email).one()
        user.email_confirmed = True
        user.confirmation_token = None
        db.session.commit()
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()["csrfToken"]


def _slug(company_id, name):
    return "%s-%d" % (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"), company_id)


def _profile_json(name, industry):
    if industry == _NO_OVERVIEW:
        return {}
    overview = {"name": name}
    if industry != _NO_KEY:
        overview["industry"] = industry
    # Bulk the document out the way a real research profile is, so a query that
    # drags it along is doing visible work.
    return {"overview": overview, "notes": {"research": "x" * 2000}}


def _seed(rows=SEED):
    from app import app
    from model import Company, db

    with app.app_context():
        for company_id, name, industry, *culture in rows:
            db.session.add(Company(
                id=company_id,
                name=name,
                slug=_slug(company_id, name),
                profile_json=_profile_json(name, industry),
                culture_narrative_company="How %s describes itself." % name,
                culture_narrative_employees="How %s's staff describe it." % name,
                **dict(zip(_CULTURE_COLUMNS, culture)),
            ))
        db.session.commit()


def _user_id(email):
    from app import app
    from model import User

    with app.app_context():
        return User.query.filter_by(email=email).one().id


def _store_prefs(email, prefs):
    from app import app
    from model import db
    from solverah.repositories import profile_repository

    user_id = _user_id(email)
    with app.app_context():
        profile_repository.update_document(
            user_id, lambda existing: {**existing, "culture_preferences": prefs}
        )
        db.session.commit()


def _give_work_pulse(user_id, answers=WORK_PULSE_ANSWERS):
    """A scored Work Pulse sitting, written the way ``test_read_path_writes`` does."""
    from app import app
    from model import db
    from solverah.domain import auth as auth_domain
    from solverah.repositories import assessment_repository
    from solverah.services import assessment_service

    with app.app_context():
        submission = assessment_repository.open_current(
            user_id, "work_pulse", assessment_service.CLIENT_FORM_VERSION
        )
        submission.answers = answers
        submission.narrative = "A Work Pulse narrative nobody on the matches path reads."
        submission.status = "scored"
        submission.completed_at = submission.scored_at = auth_domain.utcnow()
        db.session.commit()


def _mint(key):
    from solverah.pagination import encode_cursor

    return encode_cursor(key)


def _mint_raw(obj):
    """A cursor token for *obj*, whatever shape it is -- for tampered-cursor cases."""
    import base64

    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


# -- recording ------------------------------------------------------------------


def _record(url, resp):
    """One response as the recording holds it: ``(url, status, sha256, summary)``.

    The digest is over the exact body bytes. A problem document carries a fresh
    ``request_id`` per request, so for those the digest is over the document
    with that one field removed.
    """
    body = resp.get_data()
    if resp.mimetype == "application/problem+json":
        doc = json.loads(body)
        doc.pop("request_id", None)
        canonical = json.dumps(doc, sort_keys=True).encode("utf-8")
        return (url, resp.status_code, hashlib.sha256(canonical).hexdigest(),
                doc.get("type", "").rsplit("/", 1)[-1])
    digest = hashlib.sha256(body).hexdigest()
    doc = json.loads(body)
    if resp.status_code != 200 or "data" not in doc:
        return (url, resp.status_code, digest, doc)
    if "total_companies_scored" in doc:
        summary = [[row["id"], row["fit_score"]] for row in doc["data"]]
        return (url, 200, digest, [summary, doc["next_cursor"], doc["total_companies_scored"]])
    summary = [[row["id"], row["name"], row["industry"]] for row in doc["data"]]
    return (url, 200, digest, [summary, doc["next_cursor"]])


def _get(client, url):
    return _record(url, client.get(url))


def _walk(client, start):
    """Every page of the list at *start*, following ``next_cursor`` to the end."""
    records, url = [], start
    for _ in range(60):
        resp = client.get(url)
        records.append(_record(url, resp))
        if resp.status_code != 200:
            return records
        cursor = resp.get_json()["next_cursor"]
        if cursor is None:
            return records
        url = "%s%scursor=%s" % (start, "&" if "?" in start else "?", cursor)
    raise AssertionError("pagination did not terminate: %s" % start)


def _db_name_order():
    from app import app
    from model import Company, db

    with app.app_context():
        return [
            name for (name,) in db.session.execute(
                sa.select(Company.name).order_by(Company.name, Company.id)
            )
        ]


COMPANY_WALKS = (
    "/api/v1/companies?limit=7",
    "/api/v1/companies",
    "/api/v1/companies?limit=3&q=acme",
    "/api/v1/companies?limit=4&industry=tech",
    "/api/v1/companies?limit=2&industry=%20FINANCE%20",
    "/api/v1/companies?limit=2&q=acme&industry=Tech",
    "/api/v1/companies?q=zzz",
    "/api/v1/companies?industry=nothing-here",
    "/api/v1/companies?limit=10&industry=%20",
    "/api/v1/companies?limit=10&q=%25",
    "/api/v1/companies?limit=15&q=_",
    "/api/v1/companies?limit=30&q=&industry=",
    "/api/v1/companies?limit=500",
    "/api/v1/companies?industry=A%C3%89ROSPATIALE",
    "/api/v1/companies?q=caf%C3%89",
    "/api/v1/companies?limit=1&industry=health",
)


def _company_walk_records(client):
    records = []
    for start in COMPANY_WALKS:
        records.extend(_walk(client, start))
    # Cursors from earlier pages, handed back after the walk has moved on,
    # answer exactly as they did the first time.
    records.extend(_get(client, url) for url, *_rest in records[1:3])
    return records


def _company_edge_records(client):
    """Cursors the fast path must not reinterpret, then a cursor whose row is gone."""
    from app import app
    from model import Company, db

    ebay = _mint({"id": 11, "name": "eBay"})
    records = [
        # The cursor's row exists but is filtered out of this list.
        _get(client, "/api/v1/companies?limit=5&industry=tech&cursor=%s" % ebay),
        _get(client, "/api/v1/companies?limit=5&q=o&cursor=%s" % ebay),
        # The cursor's row is the last row of the list: an empty final page.
        _get(client, "/api/v1/companies?limit=5&cursor=%s"
             % _mint({"id": 28, "name": "Zeta Caf\u00e9"})),
        # A position past every row that is not a row itself.
        _get(client, "/api/v1/companies?limit=5&cursor=%s" % _mint({"id": 99, "name": "zzz"})),
        _get(client, "/api/v1/companies?limit=5&cursor=%s" % _mint({"id": 0, "name": "Acme 01"})),
        # Tampered shapes: a bool id equals 1, a float id equals its int, an extra
        # key defeats the exact match, and a missing name cannot be compared.
        _get(client, "/api/v1/companies?limit=3&cursor=%s"
             % _mint_raw({"id": True, "name": "Delta & Co"})),
        _get(client, "/api/v1/companies?limit=3&cursor=%s"
             % _mint_raw({"id": 11.0, "name": "eBay"})),
        _get(client, "/api/v1/companies?limit=3&cursor=%s"
             % _mint_raw({"id": 11, "name": "eBay", "extra": 1})),
        _get(client, "/api/v1/companies?limit=3&cursor=%s" % _mint_raw({"id": 11})),
        _get(client, "/api/v1/companies?limit=3&cursor=%s"
             % _mint_raw({"id": "11", "name": "eBay"})),
        _get(client, "/api/v1/companies?limit=3&cursor=%s"
             % _mint_raw({"id": 11, "name": "e\u0000Bay"})),
        _get(client, "/api/v1/companies?limit=3&cursor=%s" % _mint_raw([1, 2])),
        _get(client, "/api/v1/companies?cursor=not-a-real-cursor"),
        _get(client, "/api/v1/companies?limit=abc"),
    ]
    with app.app_context():
        db.session.delete(db.session.get(Company, 11))
        db.session.commit()
    # The cursor's row has been deleted since the cursor was minted.
    records.append(_get(client, "/api/v1/companies?limit=5&cursor=%s" % ebay))
    records.append(_get(client, "/api/v1/companies?limit=5&industry=retail&cursor=%s" % ebay))
    return records


MATCH_WALKS = (
    "/api/v1/me/matches?limit=7",
    "/api/v1/me/matches?limit=7&order=worst",
    "/api/v1/me/matches",
    "/api/v1/me/matches?limit=4&order=%20WORST%20&lens=Culture",
    "/api/v1/me/matches?limit=500&order=best",
)


def _match_walk_records(client):
    records = []
    for start in MATCH_WALKS:
        records.extend(_walk(client, start))
    return records


def _match_edge_records(client):
    records = []
    best = client.get("/api/v1/me/matches?limit=5").get_json()
    # A cursor from the best-first walk handed to the worst-first one.
    records.append(_get(client, "/api/v1/me/matches?limit=5&order=worst&cursor=%s"
                        % best["next_cursor"]))
    records.append(_get(client, "/api/v1/me/matches?limit=0"))
    records.append(_get(client, "/api/v1/me/matches?limit=abc"))
    records.append(_get(client, "/api/v1/me/matches?lens=salary"))
    records.append(_get(client, "/api/v1/me/matches?order=sideways"))
    records.append(_get(client, "/api/v1/me/matches?cursor=not-a-real-cursor"))
    # The preferences change between two pages: every score moves, so the
    # cursor's (id, score) no longer names a row.
    _store_prefs(EMAIL, OTHER_PREFS)
    records.append(_get(client, "/api/v1/me/matches?limit=5&cursor=%s" % best["next_cursor"]))
    records.append(_get(client, "/api/v1/me/matches?limit=5&order=worst&cursor=%s"
                        % best["next_cursor"]))
    return records


def _assert_recording(actual, expected):
    """Compare record by record, printing the first difference in full."""
    for index, (got, want) in enumerate(zip(actual, expected)):
        assert got == want, "record %d differs:\n  got  %r\n  want %r" % (index, got, want)
    assert len(actual) == len(expected), (len(actual), len(expected))


def _matches_scenario(client):
    """No preferences yet (400 outranks a bad cursor), then every page and edge."""
    records = [
        _get(client, "/api/v1/me/matches?cursor=not-a-real-cursor"),
        _get(client, "/api/v1/me/matches"),
    ]
    _store_prefs(EMAIL, PREFS)
    return records + _match_walk_records(client) + _match_edge_records(client)


def _derived_scenario(client):
    """Preferences derived from Work Pulse answers on the read, never stored."""
    _sign_in(client, DERIVED_EMAIL)
    _give_work_pulse(_user_id(DERIVED_EMAIL))
    return (_walk(client, "/api/v1/me/matches?limit=9")
            + _walk(client, "/api/v1/me/matches?limit=9&order=worst"))


# -- characterisation: recorded before the change, required after it -----------


def _assert_db_orders_names_as_recorded():
    assert _db_name_order() == DB_NAME_ORDER, (
        "This database orders company names differently from the one the pages "
        "were recorded on (en_US.utf8, as CI's pgvector/pgvector:pg18 image). "
        "The recording is only meaningful under that order."
    )


def test_every_company_page_is_unchanged(client, auth):
    """Review focus 3: every page of every filter combination, byte for byte."""
    _seed()
    _assert_db_orders_names_as_recorded()

    _assert_recording(_company_walk_records(client), COMPANY_PAGES)


def test_company_cursor_edge_cases_are_unchanged(client, auth):
    """A cursor whose row is filtered out, past the end, tampered with, or deleted.

    Before the change, a cursor naming a row that is not in the list fell back to
    the first row that sorts after it *by Python's comparison* -- code point
    order -- while the list itself is in the database's collation order. Under
    en_US the two disagree (``eBay`` sorts after every capitalised name by code
    point, among the E's by collation), so this pins that fallback exactly.
    """
    _seed()
    _assert_db_orders_names_as_recorded()

    _assert_recording(_company_edge_records(client), COMPANY_EDGES)


def test_every_match_page_is_unchanged(client, auth):
    """Both orders, several page sizes, a cursor across orders and across a re-score."""
    _seed()

    _assert_recording(_matches_scenario(client), MATCH_PAGES)


def test_derived_preference_match_pages_are_unchanged(client, auth):
    _seed()

    _assert_recording(_derived_scenario(client), DERIVED_PAGES)


# -- regression: what each request reads ---------------------------------------


@contextlib.contextmanager
def _sql():
    """Every ``(statement, parameters, rowcount)`` the engine runs inside the block.

    Taken on the engine rather than inside an application context, so a request
    made in the block pushes a context and a session of its own -- nothing the
    test holds can turn one of its SELECTs into an identity-map hit.
    """
    from app import app
    from model import db

    with app.app_context():
        engine = db.engine
    sent = []

    def _record_statement(conn, cursor, statement, parameters, context, executemany):
        sent.append((statement, parameters, cursor.rowcount))

    event.listen(engine, "after_cursor_execute", _record_statement)
    try:
        yield sent
    finally:
        event.remove(engine, "after_cursor_execute", _record_statement)


def _reads_of(sent, table):
    """The SELECTs in *sent* whose FROM clause starts at *table*."""
    source = re.compile(r"\bFROM\s+%s\b" % re.escape(table), re.IGNORECASE)
    return [
        entry for entry in sent
        if entry[0].lstrip().upper().startswith("SELECT") and source.search(entry[0])
    ]


def _select_list(statement):
    """The bare column names a single-table ``SELECT ... FROM company`` returns."""
    columns = re.match(r"\s*SELECT\s+(.*?)\s+FROM\s", statement, re.S | re.I).group(1)
    return {part.split(" AS ")[0].strip().split(".")[-1] for part in columns.split(",")}


#: ``profile_json`` read whole, as opposed to one field out of it by JSON path.
_WHOLE_DOCUMENT = re.compile(r"company\.profile_json(?!\s*(?:->|#>))")

_PROFILE_CHILD_TABLES = ("profile_experiences", "profile_educations", "profile_skills", "resumes")


def test_a_company_page_reads_its_window_and_never_the_document(client, auth):
    """Ledger ``company_repository``:151, ``matching_service``:274/277, ``pagination``:132.

    Every page used to read every row -- ``profile_json`` included -- and then
    filter by industry and slice the page in Python. A page now reads at most
    the page plus two rows: the keyset, the filters and the LIMIT are in SQL,
    and the industry comes out of the document by JSON path.
    """
    _seed()
    first = client.get("/api/v1/companies?limit=5").get_json()
    urls = (
        "/api/v1/companies?limit=5",
        "/api/v1/companies?limit=5&cursor=%s" % first["next_cursor"],
        "/api/v1/companies?limit=3&industry=Tech",
        "/api/v1/companies?limit=3&q=acme&industry=tech",
    )

    for url in urls:
        with _sql() as sent:
            assert client.get(url).status_code == 200
        reads = _reads_of(sent, "company")

        assert len(reads) == 1, (url, reads)
        statement, _parameters, rowcount = reads[0]
        assert rowcount <= int(re.search(r"limit=(\d+)", url).group(1)) + 2, (url, rowcount)
        assert not _WHOLE_DOCUMENT.search(statement), (url, statement)


def test_matches_read_profile_json_only_for_the_page_it_returns(client, auth):
    """Ledger ``matching_service``:387 (``_score_all``) and :219 (``_format_entry``).

    Scoring reads the key and the eight culture columns of the scoreable rows --
    ``pace IS NOT NULL`` in SQL -- and the one statement that touches
    ``profile_json`` asks for the returned page's ids and no others.
    """
    _seed()
    _store_prefs(EMAIL, PREFS)

    with _sql() as sent:
        resp = client.get("/api/v1/me/matches?limit=3")
    assert resp.status_code == 200
    page_ids = [row["id"] for row in resp.get_json()["data"]]

    reads = _reads_of(sent, "company")
    touching = [entry for entry in reads if "profile_json" in entry[0]]
    assert len(touching) == 1, reads
    statement, parameters, rowcount = touching[0]
    assert re.search(r"company\.id IN \(", statement), statement
    assert sorted(v for v in parameters.values() if isinstance(v, int)) == sorted(page_ids)
    assert rowcount == len(page_ids)

    (scan, _parameters, scanned), = [entry for entry in reads if entry not in touching]
    assert _select_list(scan) == {"id", *_CULTURE_COLUMNS}, scan
    assert re.search(r"company\.pace IS NOT NULL", scan), scan
    assert scanned == len([row for row in SEED if row[3] is not None])


def test_matches_read_one_profile_key_not_the_document(client, auth):
    """Ledger ``matching_service``:155 (``resolve_culture_preferences``).

    Six statements -- the profile row, four child tables and the assessment
    results -- to read one key of ``profiles.extra``.
    """
    _seed()
    _store_prefs(EMAIL, PREFS)

    with _sql() as sent:
        assert client.get("/api/v1/me/matches?limit=3").status_code == 200

    assert len(_reads_of(sent, "profiles")) == 1, sent
    for table in _PROFILE_CHILD_TABLES + ("assessment_submissions",):
        assert _reads_of(sent, table) == [], (table, sent)


def test_the_derive_path_reads_the_answers_without_the_narrative(client, auth):
    """Ledger ``matching_service``:139 (``_derive_culture_preferences``).

    With no stored preferences the read derives them from the Work Pulse
    answers: one read of the submission, and not of its narrative.
    """
    _seed()
    _give_work_pulse(_user_id(EMAIL))

    with _sql() as sent:
        assert client.get("/api/v1/me/matches?limit=3").status_code == 200

    (statement, _parameters, _rows), = _reads_of(sent, "assessment_submissions")
    assert "narrative" not in statement, statement
    assert "answers" in statement, statement


# -- regression: the culture-preference backfill --------------------------------


def _backfill_population(derivable, underivable=1, stored=1):
    """Profiles with Work Pulse answers, without them, and already backfilled.

    Returns ``{"derivable": [...], "underivable": [...], "stored": [...]}`` ids.
    Only the first two kinds are candidates: the sweep selects on the key.
    """
    from app import app
    from model import User, db
    from solverah.repositories import profile_repository

    ids = {"derivable": [], "underivable": [], "stored": []}
    with app.app_context():
        for kind, count in (("derivable", derivable), ("underivable", underivable),
                            ("stored", stored)):
            for n in range(count):
                user = User(email="%s-%d@example.test" % (kind, n),
                            password_hash="not-a-real-hash")
                db.session.add(user)
                db.session.flush()
                ids[kind].append(user.id)
                profile_repository.update_document(
                    user.id, lambda doc: {**doc, "summary": "backfill fixture"}
                )
        for user_id in ids["stored"]:
            profile_repository.update_document(
                user_id, lambda doc: {**doc, "culture_preferences": PREFS}
            )
        db.session.commit()
    for user_id in ids["derivable"]:
        _give_work_pulse(user_id)
    return ids


@contextlib.contextmanager
def _commits():
    from model import db

    seen = []

    def _record_commit(conn):
        seen.append(conn)

    event.listen(db.engine, "commit", _record_commit)
    try:
        yield seen
    finally:
        event.remove(db.engine, "commit", _record_commit)


@pytest.mark.parametrize("derivable", [2, 5])
def test_the_backfill_reads_submissions_once_and_writes_one_key_per_user(client, derivable):
    """Ledger ``matching_service``:163/181/185/192/196.

    Per user it used to load the whole document (six statements), read the Work
    Pulse row, rewrite the whole document through ``update_document`` and
    commit. Now: one read of every candidate's Work Pulse answers, then per user
    the three statements of ``update_extra_key``, and one commit for the sweep.
    """
    from app import app
    from model import db
    from solverah.repositories import profile_repository
    from solverah.services import matching_service
    from work_pulse.derive_preferences import derive_culture_preferences

    ids = _backfill_population(derivable)

    with app.app_context():
        with count_queries() as statements, _commits() as commits:
            counts = matching_service.backfill_culture_preferences()

        assert counts == {"considered": derivable + 1, "written": derivable, "underivable": 1}
        reads = [(s, None, None) for s in statements]
        assert len(_reads_of(reads, "assessment_submissions")) == 1, statements
        for table in _PROFILE_CHILD_TABLES:
            assert _reads_of(reads, table) == [], (table, statements)
        assert len(statements) == 2 + 3 * derivable, statements
        assert len(commits) == 1

        expected = derive_culture_preferences(WORK_PULSE_ANSWERS)
        for user_id in ids["derivable"]:
            assert profile_repository.read_extra_key(user_id, "culture_preferences") == expected
        for user_id in ids["underivable"]:
            assert "culture_preferences" not in profile_repository.load_document(user_id)
        for user_id in ids["stored"]:
            assert profile_repository.read_extra_key(user_id, "culture_preferences") == PREFS
        db.session.rollback()


def test_the_backfill_never_overwrites_a_value_that_lands_mid_sweep(client, monkeypatch):
    """The sweep's rule -- write only where the key is still empty -- holds at write time.

    It checked the stored value, derived, then wrote unconditionally: a Work
    Pulse submit landing between the check and the write (the submit writes
    ``culture_preferences`` itself) was overwritten with a value derived from the
    answers the sweep had read. The check now runs inside the compare-and-swap.
    """
    from app import app
    from model import db
    from solverah.repositories import profile_repository
    from solverah.services import matching_service
    from work_pulse import derive_preferences

    ids = _backfill_population(2, underivable=0, stored=0)
    first = ids["derivable"][0]
    real_derive = derive_preferences.derive_culture_preferences
    calls = []

    def _derive_while_a_submit_lands(answers):
        if not calls:
            # The submit's own write, committed on a connection of its own while
            # the sweep is between reading and writing this user.
            with db.engine.begin() as connection:
                connection.execute(
                    sa.text(
                        "UPDATE profiles SET extra = extra || CAST(:patch AS jsonb), "
                        "version = version + 1 WHERE user_id = :user_id"
                    ),
                    {"patch": json.dumps({"culture_preferences": OTHER_PREFS}),
                     "user_id": first},
                )
        calls.append(answers)
        return real_derive(answers)

    monkeypatch.setattr(derive_preferences, "derive_culture_preferences",
                        _derive_while_a_submit_lands)

    with app.app_context():
        counts = matching_service.backfill_culture_preferences()

        assert counts == {"considered": 2, "written": 1, "underivable": 0}
        assert profile_repository.read_extra_key(first, "culture_preferences") == OTHER_PREFS
        db.session.rollback()


# -- regression: the agent chat --------------------------------------------------


def _mock_agent_llm(monkeypatch):
    from unittest.mock import MagicMock

    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta.content = "ok"
    client = MagicMock()
    client.chat.completions.create.return_value = iter([chunk])
    monkeypatch.setattr("solverah.infra.llm.get_agent_client", lambda: client)
    return client


def _chat(client, csrf):
    resp = client.post(
        "/api/v1/agent/messages",
        json={"messages": [{"role": "user", "content": "hi"}], "model": "test-model"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    resp.get_data()  # drain the stream inside the capture
    return resp


def test_an_agent_turn_loads_the_profile_once(client, auth, monkeypatch):
    """Ledger ``agent_service``:180/272 and ``intelligence.py``:129.

    ``resume_text_for`` and ``build_agent_context`` each loaded the whole
    profile document for the same turn: every profile table twice.
    """
    _mock_agent_llm(monkeypatch)

    with _sql() as sent:
        _chat(client, auth)

    for table in ("profiles",) + _PROFILE_CHILD_TABLES + ("assessment_submissions",):
        assert len(_reads_of(sent, table)) == 1, (table, sent)


def test_the_agent_company_sample_is_three_columns_in_a_stable_order(client, auth, monkeypatch):
    """Ledger ``agent_service``:216.

    ``Company.query.limit(10)`` loaded ten whole rows -- the research document
    and both narratives -- in whatever order the table scan met them, to use a
    name, a work environment and a pace from each.
    """
    _seed()
    llm = _mock_agent_llm(monkeypatch)

    with _sql() as sent:
        _chat(client, auth)

    (statement, _parameters, _rows), = _reads_of(sent, "company")
    assert _select_list(statement) == {"name", "work_environment", "pace"}, statement
    assert re.search(r"ORDER BY company\.id\b", statement), statement

    prompt = llm.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    network = prompt.split("## Companies in Network\n", 1)[1].split("\n\n", 1)[0]
    by_id = sorted(SEED)[:10]
    assert [line.split(":")[0].split(",")[0][2:] for line in network.splitlines()] == [
        row[1] for row in by_id
    ]


# -- the recording -------------------------------------------------------------
#
# Captured from the code before this change (HEAD b48348d) by running the
# scenario functions above, on the lane database. Each record is
# ``(url, status, sha256 of the body, summary)``; see ``_record``.

#: The seed's names as ``ORDER BY name, id`` returned them when the pages were
#: recorded: en_US.utf8, the collation of the pgvector/pgvector:pg18 image CI
#: and the compose stack both run. The recorded pages hold only under it.
DB_NAME_ORDER = [
    'Acme 01',
    'Acme 02',
    'Acme 03',
    'Acme 10',
    'AcmeCorp',
    'Acme-Labs',
    'Acme North',
    'acme ventures',
    'Beacon',
    'Beacon Health',
    'Beacon Labs',
    'Cobalt',
    'Cobalt Systems',
    'Delta & Co',
    'Delta Co',
    'eBay',
    'Echo Analytics',
    'Foxtrot',
    'Gamma Bank',
    'Gamma Bank Two',
    'Helix Bio',
    'Indigo Finance',
    'iRobot',
    'Juniper',
    'Kestrel',
    'Lumen',
    'Meridian',
    'Nimbus',
    'Orbit',
    'Zeta Caf\xe9',
]

COMPANY_PAGES = [
    ('/api/v1/companies?limit=7', 200, 'a0e6fd86e04ed1c6ad3828e829266aa3c8f6f4d8a347021e4bde0026f4d5a0c8',
     [[[7, 'Acme 01', 'Tech'], [23, 'Acme 02', 'tech'], [3, 'Acme 03', 'Health'], [30, 'Acme 10', 'TECH'], [5, 'AcmeCorp', 'Retail'], [18, 'Acme-Labs', 'Tech'], [12, 'Acme North', 'Finance']], 'eyJpZCI6MTIsIm5hbWUiOiJBY21lIE5vcnRoIn0']),
    ('/api/v1/companies?limit=7&cursor=eyJpZCI6MTIsIm5hbWUiOiJBY21lIE5vcnRoIn0', 200, '5e4f73193372672641655cbfa8e33b51a4d9ceae9d08b93fb65f73c445ca250e',
     [[[26, 'acme ventures', 'Finance'], [14, 'Beacon', None], [2, 'Beacon Health', 'Health'], [21, 'Beacon Labs', 'Tech'], [9, 'Cobalt', None], [27, 'Cobalt Systems', 'Tech'], [1, 'Delta & Co', 'Finance']], 'eyJpZCI6MSwibmFtZSI6IkRlbHRhICYgQ28ifQ']),
    ('/api/v1/companies?limit=7&cursor=eyJpZCI6MSwibmFtZSI6IkRlbHRhICYgQ28ifQ', 200, '418e723a498b1216e467855a55a81a905f8f81973815630f42b0a071232b5169',
     [[[16, 'Delta Co', 'finance'], [11, 'eBay', 'Retail'], [29, 'Echo Analytics', 'Tech'], [4, 'Foxtrot', ''], [20, 'Gamma Bank', 'Finance'], [8, 'Gamma Bank Two', 'Finance'], [25, 'Helix Bio', 'Health']], 'eyJpZCI6MjUsIm5hbWUiOiJIZWxpeCBCaW8ifQ']),
    ('/api/v1/companies?limit=7&cursor=eyJpZCI6MjUsIm5hbWUiOiJIZWxpeCBCaW8ifQ', 200, '6f7c1d4cf30dddce7d9746298569ce0328782ac65b55f1e65d16405279c29b29',
     [[[6, 'Indigo Finance', ' Finance '], [13, 'iRobot', 'Tech'], [19, 'Juniper', 'Hospitality'], [10, 'Kestrel', 'Tech'], [24, 'Lumen', None], [15, 'Meridian', 'Health'], [22, 'Nimbus', 'Tech']], 'eyJpZCI6MjIsIm5hbWUiOiJOaW1idXMifQ']),
    ('/api/v1/companies?limit=7&cursor=eyJpZCI6MjIsIm5hbWUiOiJOaW1idXMifQ', 200, '896ec16b159be912f3660c6804dd3ef7bec4fd00ba87f826bd8233a0fc2aa483',
     [[[17, 'Orbit', 'A\xe9rospatiale'], [28, 'Zeta Caf\xe9', 'Food']], None]),
    ('/api/v1/companies', 200, 'e7568fb6e3f17b3c57a79db3beca6382e538e791afc99589b0f90297e4be4806',
     [[[7, 'Acme 01', 'Tech'], [23, 'Acme 02', 'tech'], [3, 'Acme 03', 'Health'], [30, 'Acme 10', 'TECH'], [5, 'AcmeCorp', 'Retail'], [18, 'Acme-Labs', 'Tech'], [12, 'Acme North', 'Finance'], [26, 'acme ventures', 'Finance'], [14, 'Beacon', None], [2, 'Beacon Health', 'Health'], [21, 'Beacon Labs', 'Tech'], [9, 'Cobalt', None], [27, 'Cobalt Systems', 'Tech'], [1, 'Delta & Co', 'Finance'], [16, 'Delta Co', 'finance'], [11, 'eBay', 'Retail'], [29, 'Echo Analytics', 'Tech'], [4, 'Foxtrot', ''], [20, 'Gamma Bank', 'Finance'], [8, 'Gamma Bank Two', 'Finance']], 'eyJpZCI6OCwibmFtZSI6IkdhbW1hIEJhbmsgVHdvIn0']),
    ('/api/v1/companies?cursor=eyJpZCI6OCwibmFtZSI6IkdhbW1hIEJhbmsgVHdvIn0', 200, '3e268b5c0cfa16fdfc2f3b22543e1848709c8424c8f64464bd3226ee3b16e594',
     [[[25, 'Helix Bio', 'Health'], [6, 'Indigo Finance', ' Finance '], [13, 'iRobot', 'Tech'], [19, 'Juniper', 'Hospitality'], [10, 'Kestrel', 'Tech'], [24, 'Lumen', None], [15, 'Meridian', 'Health'], [22, 'Nimbus', 'Tech'], [17, 'Orbit', 'A\xe9rospatiale'], [28, 'Zeta Caf\xe9', 'Food']], None]),
    ('/api/v1/companies?limit=3&q=acme', 200, '8573c252d8cb4dec45260429512e672bc52564ecdf29d1b39b80ded2c84bced9',
     [[[7, 'Acme 01', 'Tech'], [23, 'Acme 02', 'tech'], [3, 'Acme 03', 'Health']], 'eyJpZCI6MywibmFtZSI6IkFjbWUgMDMifQ']),
    ('/api/v1/companies?limit=3&q=acme&cursor=eyJpZCI6MywibmFtZSI6IkFjbWUgMDMifQ', 200, '196e00f612ecd80f566075dafc66bd4f86a07b9c90aafe172c271ed138aaf29f',
     [[[30, 'Acme 10', 'TECH'], [5, 'AcmeCorp', 'Retail'], [18, 'Acme-Labs', 'Tech']], 'eyJpZCI6MTgsIm5hbWUiOiJBY21lLUxhYnMifQ']),
    ('/api/v1/companies?limit=3&q=acme&cursor=eyJpZCI6MTgsIm5hbWUiOiJBY21lLUxhYnMifQ', 200, 'bafebbe5d1c2e4418f2e82ee422487e90b322c205773086b518d34e83c9a1ba3',
     [[[12, 'Acme North', 'Finance'], [26, 'acme ventures', 'Finance']], None]),
    ('/api/v1/companies?limit=4&industry=tech', 200, '06a50a084c309f54dd4227a68891a2e461c15ea5061c2ba3e661bb7cb304d6b3',
     [[[7, 'Acme 01', 'Tech'], [23, 'Acme 02', 'tech'], [30, 'Acme 10', 'TECH'], [18, 'Acme-Labs', 'Tech']], 'eyJpZCI6MTgsIm5hbWUiOiJBY21lLUxhYnMifQ']),
    ('/api/v1/companies?limit=4&industry=tech&cursor=eyJpZCI6MTgsIm5hbWUiOiJBY21lLUxhYnMifQ', 200, 'e754a73779ad6dac85fa35317f0898c6c67a60d10ba96233bda93849568bb741',
     [[[21, 'Beacon Labs', 'Tech'], [27, 'Cobalt Systems', 'Tech'], [29, 'Echo Analytics', 'Tech'], [13, 'iRobot', 'Tech']], 'eyJpZCI6MTMsIm5hbWUiOiJpUm9ib3QifQ']),
    ('/api/v1/companies?limit=4&industry=tech&cursor=eyJpZCI6MTMsIm5hbWUiOiJpUm9ib3QifQ', 200, '21e9fc29c4a5028cb11e8678881429d9d59c0544313ee923c5480d992e11fab3',
     [[[10, 'Kestrel', 'Tech'], [22, 'Nimbus', 'Tech']], None]),
    ('/api/v1/companies?limit=2&industry=%20FINANCE%20', 200, '6b145a50a8f33e1204e1f87563c463a5819b1586b8cd9f41c243a11777e7d20e',
     [[[12, 'Acme North', 'Finance'], [26, 'acme ventures', 'Finance']], 'eyJpZCI6MjYsIm5hbWUiOiJhY21lIHZlbnR1cmVzIn0']),
    ('/api/v1/companies?limit=2&industry=%20FINANCE%20&cursor=eyJpZCI6MjYsIm5hbWUiOiJhY21lIHZlbnR1cmVzIn0', 200, 'f16d134435bce886539d52bcd7e27bc188a607ba089a840d2480de692c546b70',
     [[[1, 'Delta & Co', 'Finance'], [16, 'Delta Co', 'finance']], 'eyJpZCI6MTYsIm5hbWUiOiJEZWx0YSBDbyJ9']),
    ('/api/v1/companies?limit=2&industry=%20FINANCE%20&cursor=eyJpZCI6MTYsIm5hbWUiOiJEZWx0YSBDbyJ9', 200, '5f4a5c149c7b344f8ee0a42bd831e1fe32bf6b41aabecdc0536b508f9f26ae03',
     [[[20, 'Gamma Bank', 'Finance'], [8, 'Gamma Bank Two', 'Finance']], None]),
    ('/api/v1/companies?limit=2&q=acme&industry=Tech', 200, 'a8cd640690a56dec63c1c17c3c14072772e4ff80e99c2384c5a23edf48d31a14',
     [[[7, 'Acme 01', 'Tech'], [23, 'Acme 02', 'tech']], 'eyJpZCI6MjMsIm5hbWUiOiJBY21lIDAyIn0']),
    ('/api/v1/companies?limit=2&q=acme&industry=Tech&cursor=eyJpZCI6MjMsIm5hbWUiOiJBY21lIDAyIn0', 200, '1a1f69b5d3cc7af304689ebde5f720de7b05a283df89f1612edc1bae6ab98123',
     [[[30, 'Acme 10', 'TECH'], [18, 'Acme-Labs', 'Tech']], None]),
    ('/api/v1/companies?q=zzz', 200, '05532354076ec2173ec2aca88193c465ac3f5e7afe8f28c037b80fbcbb8b19ad',
     [[], None]),
    ('/api/v1/companies?industry=nothing-here', 200, '05532354076ec2173ec2aca88193c465ac3f5e7afe8f28c037b80fbcbb8b19ad',
     [[], None]),
    ('/api/v1/companies?limit=10&industry=%20', 200, '0179006bdf5bc24dc8ad0ec98a6e4c5a1ea260dfa0e708e0c53588bdd9400c32',
     [[[14, 'Beacon', None], [9, 'Cobalt', None], [4, 'Foxtrot', ''], [24, 'Lumen', None]], None]),
    ('/api/v1/companies?limit=10&q=%25', 200, 'd03a7f172545e6b6c041a3aec27f54503357c2a7c87f29848663f7fede0067f4',
     [[[7, 'Acme 01', 'Tech'], [23, 'Acme 02', 'tech'], [3, 'Acme 03', 'Health'], [30, 'Acme 10', 'TECH'], [5, 'AcmeCorp', 'Retail'], [18, 'Acme-Labs', 'Tech'], [12, 'Acme North', 'Finance'], [26, 'acme ventures', 'Finance'], [14, 'Beacon', None], [2, 'Beacon Health', 'Health']], 'eyJpZCI6MiwibmFtZSI6IkJlYWNvbiBIZWFsdGgifQ']),
    ('/api/v1/companies?limit=10&q=%25&cursor=eyJpZCI6MiwibmFtZSI6IkJlYWNvbiBIZWFsdGgifQ', 200, 'f5b677a7b3cf4bbbaf7a00d81f4db44dc15a4fa660dc84db8c014279f4870088',
     [[[21, 'Beacon Labs', 'Tech'], [9, 'Cobalt', None], [27, 'Cobalt Systems', 'Tech'], [1, 'Delta & Co', 'Finance'], [16, 'Delta Co', 'finance'], [11, 'eBay', 'Retail'], [29, 'Echo Analytics', 'Tech'], [4, 'Foxtrot', ''], [20, 'Gamma Bank', 'Finance'], [8, 'Gamma Bank Two', 'Finance']], 'eyJpZCI6OCwibmFtZSI6IkdhbW1hIEJhbmsgVHdvIn0']),
    ('/api/v1/companies?limit=10&q=%25&cursor=eyJpZCI6OCwibmFtZSI6IkdhbW1hIEJhbmsgVHdvIn0', 200, '3e268b5c0cfa16fdfc2f3b22543e1848709c8424c8f64464bd3226ee3b16e594',
     [[[25, 'Helix Bio', 'Health'], [6, 'Indigo Finance', ' Finance '], [13, 'iRobot', 'Tech'], [19, 'Juniper', 'Hospitality'], [10, 'Kestrel', 'Tech'], [24, 'Lumen', None], [15, 'Meridian', 'Health'], [22, 'Nimbus', 'Tech'], [17, 'Orbit', 'A\xe9rospatiale'], [28, 'Zeta Caf\xe9', 'Food']], None]),
    ('/api/v1/companies?limit=15&q=_', 200, '0d644f75ed8e078da61e1bec574aec20b5f494d1c1be469abaea9e65528e8de9',
     [[[7, 'Acme 01', 'Tech'], [23, 'Acme 02', 'tech'], [3, 'Acme 03', 'Health'], [30, 'Acme 10', 'TECH'], [5, 'AcmeCorp', 'Retail'], [18, 'Acme-Labs', 'Tech'], [12, 'Acme North', 'Finance'], [26, 'acme ventures', 'Finance'], [14, 'Beacon', None], [2, 'Beacon Health', 'Health'], [21, 'Beacon Labs', 'Tech'], [9, 'Cobalt', None], [27, 'Cobalt Systems', 'Tech'], [1, 'Delta & Co', 'Finance'], [16, 'Delta Co', 'finance']], 'eyJpZCI6MTYsIm5hbWUiOiJEZWx0YSBDbyJ9']),
    ('/api/v1/companies?limit=15&q=_&cursor=eyJpZCI6MTYsIm5hbWUiOiJEZWx0YSBDbyJ9', 200, '82a80465754511026572ed0c8c4c9c9dbd432473fc1df5009f9068a6131dfd24',
     [[[11, 'eBay', 'Retail'], [29, 'Echo Analytics', 'Tech'], [4, 'Foxtrot', ''], [20, 'Gamma Bank', 'Finance'], [8, 'Gamma Bank Two', 'Finance'], [25, 'Helix Bio', 'Health'], [6, 'Indigo Finance', ' Finance '], [13, 'iRobot', 'Tech'], [19, 'Juniper', 'Hospitality'], [10, 'Kestrel', 'Tech'], [24, 'Lumen', None], [15, 'Meridian', 'Health'], [22, 'Nimbus', 'Tech'], [17, 'Orbit', 'A\xe9rospatiale'], [28, 'Zeta Caf\xe9', 'Food']], None]),
    ('/api/v1/companies?limit=30&q=&industry=', 200, '023840f46fdcef4d2b60f300dc01954b3d37ac21e99aa1d032007cb812a94595',
     [[[7, 'Acme 01', 'Tech'], [23, 'Acme 02', 'tech'], [3, 'Acme 03', 'Health'], [30, 'Acme 10', 'TECH'], [5, 'AcmeCorp', 'Retail'], [18, 'Acme-Labs', 'Tech'], [12, 'Acme North', 'Finance'], [26, 'acme ventures', 'Finance'], [14, 'Beacon', None], [2, 'Beacon Health', 'Health'], [21, 'Beacon Labs', 'Tech'], [9, 'Cobalt', None], [27, 'Cobalt Systems', 'Tech'], [1, 'Delta & Co', 'Finance'], [16, 'Delta Co', 'finance'], [11, 'eBay', 'Retail'], [29, 'Echo Analytics', 'Tech'], [4, 'Foxtrot', ''], [20, 'Gamma Bank', 'Finance'], [8, 'Gamma Bank Two', 'Finance'], [25, 'Helix Bio', 'Health'], [6, 'Indigo Finance', ' Finance '], [13, 'iRobot', 'Tech'], [19, 'Juniper', 'Hospitality'], [10, 'Kestrel', 'Tech'], [24, 'Lumen', None], [15, 'Meridian', 'Health'], [22, 'Nimbus', 'Tech'], [17, 'Orbit', 'A\xe9rospatiale'], [28, 'Zeta Caf\xe9', 'Food']], None]),
    ('/api/v1/companies?limit=500', 200, '023840f46fdcef4d2b60f300dc01954b3d37ac21e99aa1d032007cb812a94595',
     [[[7, 'Acme 01', 'Tech'], [23, 'Acme 02', 'tech'], [3, 'Acme 03', 'Health'], [30, 'Acme 10', 'TECH'], [5, 'AcmeCorp', 'Retail'], [18, 'Acme-Labs', 'Tech'], [12, 'Acme North', 'Finance'], [26, 'acme ventures', 'Finance'], [14, 'Beacon', None], [2, 'Beacon Health', 'Health'], [21, 'Beacon Labs', 'Tech'], [9, 'Cobalt', None], [27, 'Cobalt Systems', 'Tech'], [1, 'Delta & Co', 'Finance'], [16, 'Delta Co', 'finance'], [11, 'eBay', 'Retail'], [29, 'Echo Analytics', 'Tech'], [4, 'Foxtrot', ''], [20, 'Gamma Bank', 'Finance'], [8, 'Gamma Bank Two', 'Finance'], [25, 'Helix Bio', 'Health'], [6, 'Indigo Finance', ' Finance '], [13, 'iRobot', 'Tech'], [19, 'Juniper', 'Hospitality'], [10, 'Kestrel', 'Tech'], [24, 'Lumen', None], [15, 'Meridian', 'Health'], [22, 'Nimbus', 'Tech'], [17, 'Orbit', 'A\xe9rospatiale'], [28, 'Zeta Caf\xe9', 'Food']], None]),
    ('/api/v1/companies?industry=A%C3%89ROSPATIALE', 200, 'f9a8a059f8bec7c9dba53db0a3927008ec428f2830516b997b0f1623dfc9977a',
     [[[17, 'Orbit', 'A\xe9rospatiale']], None]),
    ('/api/v1/companies?q=caf%C3%89', 200, 'ae859ab80efdf957a139555016d5cf1f531f8cd2aae8ee113dea8e9549c00792',
     [[[28, 'Zeta Caf\xe9', 'Food']], None]),
    ('/api/v1/companies?limit=1&industry=health', 200, '8f5f2eaafa3b1c83d096741c2a2f420203a08f2eeb38f97af87b3b6774c59e4f',
     [[[3, 'Acme 03', 'Health']], 'eyJpZCI6MywibmFtZSI6IkFjbWUgMDMifQ']),
    ('/api/v1/companies?limit=1&industry=health&cursor=eyJpZCI6MywibmFtZSI6IkFjbWUgMDMifQ', 200, 'd4671f25a82401c773984f807a680daf651b1462eafa8f7bcb716bafcc9dc931',
     [[[2, 'Beacon Health', 'Health']], 'eyJpZCI6MiwibmFtZSI6IkJlYWNvbiBIZWFsdGgifQ']),
    ('/api/v1/companies?limit=1&industry=health&cursor=eyJpZCI6MiwibmFtZSI6IkJlYWNvbiBIZWFsdGgifQ', 200, 'c1b849c4b2d3bbf3b035526f9fa29a74128485c0d3c24f8ce6dd0e4ff5fa3a45',
     [[[25, 'Helix Bio', 'Health']], 'eyJpZCI6MjUsIm5hbWUiOiJIZWxpeCBCaW8ifQ']),
    ('/api/v1/companies?limit=1&industry=health&cursor=eyJpZCI6MjUsIm5hbWUiOiJIZWxpeCBCaW8ifQ', 200, '66fd8cd7723c480ede0de0e382e8386778c950fe8958117eabd6ed13970a83a6',
     [[[15, 'Meridian', 'Health']], None]),
    ('/api/v1/companies?limit=7&cursor=eyJpZCI6MTIsIm5hbWUiOiJBY21lIE5vcnRoIn0', 200, '5e4f73193372672641655cbfa8e33b51a4d9ceae9d08b93fb65f73c445ca250e',
     [[[26, 'acme ventures', 'Finance'], [14, 'Beacon', None], [2, 'Beacon Health', 'Health'], [21, 'Beacon Labs', 'Tech'], [9, 'Cobalt', None], [27, 'Cobalt Systems', 'Tech'], [1, 'Delta & Co', 'Finance']], 'eyJpZCI6MSwibmFtZSI6IkRlbHRhICYgQ28ifQ']),
    ('/api/v1/companies?limit=7&cursor=eyJpZCI6MSwibmFtZSI6IkRlbHRhICYgQ28ifQ', 200, '418e723a498b1216e467855a55a81a905f8f81973815630f42b0a071232b5169',
     [[[16, 'Delta Co', 'finance'], [11, 'eBay', 'Retail'], [29, 'Echo Analytics', 'Tech'], [4, 'Foxtrot', ''], [20, 'Gamma Bank', 'Finance'], [8, 'Gamma Bank Two', 'Finance'], [25, 'Helix Bio', 'Health']], 'eyJpZCI6MjUsIm5hbWUiOiJIZWxpeCBCaW8ifQ']),
]

COMPANY_EDGES = [
    ('/api/v1/companies?limit=5&industry=tech&cursor=eyJpZCI6MTEsIm5hbWUiOiJlQmF5In0', 200, '6443cdd4e29c80d3a7773ea7082dd396aeb2da25af578817208934b3245e7226',
     [[[13, 'iRobot', 'Tech'], [10, 'Kestrel', 'Tech'], [22, 'Nimbus', 'Tech']], None]),
    ('/api/v1/companies?limit=5&q=o&cursor=eyJpZCI6MTEsIm5hbWUiOiJlQmF5In0', 200, '6faafed1223196f97f9a17c81a270462075e241c4aecdb29a9b595529b90b8bb',
     [[[13, 'iRobot', 'Tech'], [17, 'Orbit', 'A\xe9rospatiale']], None]),
    ('/api/v1/companies?limit=5&cursor=eyJpZCI6MjgsIm5hbWUiOiJaZXRhIENhZlx1MDBlOSJ9', 200, '05532354076ec2173ec2aca88193c465ac3f5e7afe8f28c037b80fbcbb8b19ad',
     [[], None]),
    ('/api/v1/companies?limit=5&cursor=eyJpZCI6OTksIm5hbWUiOiJ6enoifQ', 200, '05532354076ec2173ec2aca88193c465ac3f5e7afe8f28c037b80fbcbb8b19ad',
     [[], None]),
    ('/api/v1/companies?limit=5&cursor=eyJpZCI6MCwibmFtZSI6IkFjbWUgMDEifQ', 200, 'a198184c69b12cd59396cb7fd4811c50f065f1d9994569063713531f0043349b',
     [[[7, 'Acme 01', 'Tech'], [23, 'Acme 02', 'tech'], [3, 'Acme 03', 'Health'], [30, 'Acme 10', 'TECH'], [5, 'AcmeCorp', 'Retail']], 'eyJpZCI6NSwibmFtZSI6IkFjbWVDb3JwIn0']),
    ('/api/v1/companies?limit=3&cursor=eyJpZCI6dHJ1ZSwibmFtZSI6IkRlbHRhICYgQ28ifQ', 200, '4b09390564a86a05c47cf80898b744c9edae92700d85d199f9a722b6371d804f',
     [[[16, 'Delta Co', 'finance'], [11, 'eBay', 'Retail'], [29, 'Echo Analytics', 'Tech']], 'eyJpZCI6MjksIm5hbWUiOiJFY2hvIEFuYWx5dGljcyJ9']),
    ('/api/v1/companies?limit=3&cursor=eyJpZCI6MTEuMCwibmFtZSI6ImVCYXkifQ', 200, '019fa211d2dfba8b1874cd26017399544e26e2c3a07ac1dca3c03c9b97321f2b',
     [[[29, 'Echo Analytics', 'Tech'], [4, 'Foxtrot', ''], [20, 'Gamma Bank', 'Finance']], 'eyJpZCI6MjAsIm5hbWUiOiJHYW1tYSBCYW5rIn0']),
    ('/api/v1/companies?limit=3&cursor=eyJleHRyYSI6MSwiaWQiOjExLCJuYW1lIjoiZUJheSJ9', 200, '02d18c8711974dab817101db2ff96da8557cfdb3301758f2bc41dcfdb62cef30',
     [[[13, 'iRobot', 'Tech'], [19, 'Juniper', 'Hospitality'], [10, 'Kestrel', 'Tech']], 'eyJpZCI6MTAsIm5hbWUiOiJLZXN0cmVsIn0']),
    ('/api/v1/companies?limit=3&cursor=eyJpZCI6MTF9', 500, '55ba025712f7999bb7c48d1777b0ddf1b5b9b5c00e96af96d32a79aca4be2048',
     'internal'),
    ('/api/v1/companies?limit=3&cursor=eyJpZCI6IjExIiwibmFtZSI6ImVCYXkifQ', 500, '55ba025712f7999bb7c48d1777b0ddf1b5b9b5c00e96af96d32a79aca4be2048',
     'internal'),
    ('/api/v1/companies?limit=3&cursor=eyJpZCI6MTEsIm5hbWUiOiJlXHUwMDAwQmF5In0', 200, 'd4465c3a05bbb4f0279e0c4e0696111c6cdc83304ff5df6aa2721d76e3caffec',
     [[[11, 'eBay', 'Retail'], [29, 'Echo Analytics', 'Tech'], [4, 'Foxtrot', '']], 'eyJpZCI6NCwibmFtZSI6IkZveHRyb3QifQ']),
    ('/api/v1/companies?limit=3&cursor=WzEsMl0', 422, 'efe462c247d5334b13dd04cdba7f7ddbaa7baa1597dadc43b55f32123ca35164',
     'validation'),
    ('/api/v1/companies?cursor=not-a-real-cursor', 422, 'efe462c247d5334b13dd04cdba7f7ddbaa7baa1597dadc43b55f32123ca35164',
     'validation'),
    ('/api/v1/companies?limit=abc', 422, '0659c76369febc520ce7ccc9d2b58346d4feba9f9253d4e3b06cd5a15a239b5c',
     'validation'),
    ('/api/v1/companies?limit=5&cursor=eyJpZCI6MTEsIm5hbWUiOiJlQmF5In0', 200, '08fedec74a0d3fcdb8d1475cc0b860bbcf9e79ab5d1192a888581ea058457d5a',
     [[[13, 'iRobot', 'Tech'], [19, 'Juniper', 'Hospitality'], [10, 'Kestrel', 'Tech'], [24, 'Lumen', None], [15, 'Meridian', 'Health']], 'eyJpZCI6MTUsIm5hbWUiOiJNZXJpZGlhbiJ9']),
    ('/api/v1/companies?limit=5&industry=retail&cursor=eyJpZCI6MTEsIm5hbWUiOiJlQmF5In0', 200, '05532354076ec2173ec2aca88193c465ac3f5e7afe8f28c037b80fbcbb8b19ad',
     [[], None]),
]

MATCH_PAGES = [
    ('/api/v1/me/matches?cursor=not-a-real-cursor', 400, '291c92e2aa9bf6b0cee4af833374ff0732c7788973750c13de05f53c73c27f81',
     {'error': 'Work Pulse not completed \u2014 culture preferences not found'}),
    ('/api/v1/me/matches', 400, '291c92e2aa9bf6b0cee4af833374ff0732c7788973750c13de05f53c73c27f81',
     {'error': 'Work Pulse not completed \u2014 culture preferences not found'}),
    ('/api/v1/me/matches?limit=7', 200, '925b73c947c9bb2793d040271cabe81b4946c30b1ba9d98387ec9eeb18ce1091',
     [[[23, 0.9889], [25, 0.9667], [7, 0.9167], [17, 0.9167], [18, 0.9167], [11, 0.8611], [2, 0.8278]], 'eyJpZCI6Miwic2NvcmUiOjAuODI3OH0', 26]),
    ('/api/v1/me/matches?limit=7&cursor=eyJpZCI6Miwic2NvcmUiOjAuODI3OH0', 200, '0c85be3d7edbc2aa3ec3c1b6b77bb7076d62403901ee0020226fa0f7c5f56ebb',
     [[[24, 0.7944], [4, 0.79], [9, 0.7873], [14, 0.7833], [15, 0.7728], [1, 0.7672], [26, 0.7617]], 'eyJpZCI6MjYsInNjb3JlIjowLjc2MTd9', 26]),
    ('/api/v1/me/matches?limit=7&cursor=eyJpZCI6MjYsInNjb3JlIjowLjc2MTd9', 200, 'ee00b5bfc6f1a9cb155a16c25ce16b1247254f3e360935f79db1bd88937baab4',
     [[[30, 0.76], [13, 0.6944], [19, 0.6678], [6, 0.645], [29, 0.6389], [28, 0.6289], [8, 0.5617]], 'eyJpZCI6OCwic2NvcmUiOjAuNTYxN30', 26]),
    ('/api/v1/me/matches?limit=7&cursor=eyJpZCI6OCwic2NvcmUiOjAuNTYxN30', 200, 'd3a16db278fc8c2a7d6215918fcb2537b066e9777afdcb075ef4c1fea2a508f0',
     [[[20, 0.5617], [22, 0.56], [5, 0.5011], [3, 0.4561], [21, 0.4444]], None, 26]),
    ('/api/v1/me/matches?limit=7&order=worst', 200, '8d1aff2e8c4a82b0934fb55060b670127cc4cf427b75e3ecf0fd993153915121',
     [[[21, 0.4444], [3, 0.4561], [5, 0.5011], [22, 0.56], [8, 0.5617], [20, 0.5617], [28, 0.6289]], 'eyJpZCI6MjgsInNjb3JlIjowLjYyODl9', 26]),
    ('/api/v1/me/matches?limit=7&order=worst&cursor=eyJpZCI6MjgsInNjb3JlIjowLjYyODl9', 200, '5c8757d836d105464191303fcfa97d11a6348e583106de23ff40363a8f57747c',
     [[[29, 0.6389], [6, 0.645], [19, 0.6678], [13, 0.6944], [30, 0.76], [26, 0.7617], [1, 0.7672]], 'eyJpZCI6MSwic2NvcmUiOjAuNzY3Mn0', 26]),
    ('/api/v1/me/matches?limit=7&order=worst&cursor=eyJpZCI6MSwic2NvcmUiOjAuNzY3Mn0', 200, '976418ec87ba95607a7c3e10dbadba72bf6063a19e997c905f7e6c21696a2caf',
     [[[15, 0.7728], [14, 0.7833], [9, 0.7873], [4, 0.79], [24, 0.7944], [2, 0.8278], [11, 0.8611]], 'eyJpZCI6MTEsInNjb3JlIjowLjg2MTF9', 26]),
    ('/api/v1/me/matches?limit=7&order=worst&cursor=eyJpZCI6MTEsInNjb3JlIjowLjg2MTF9', 200, '12321c46382705fbd5afb62d26b668a883c7094ee9382c39ad020c0b488832e4',
     [[[7, 0.9167], [17, 0.9167], [18, 0.9167], [25, 0.9667], [23, 0.9889]], None, 26]),
    ('/api/v1/me/matches', 200, '83078678053c806d8a0bf24088dd7b2a2af263deaf2d0e71963ad1b6606d9878',
     [[[23, 0.9889], [25, 0.9667], [7, 0.9167], [17, 0.9167], [18, 0.9167], [11, 0.8611], [2, 0.8278], [24, 0.7944], [4, 0.79], [9, 0.7873], [14, 0.7833], [15, 0.7728], [1, 0.7672], [26, 0.7617], [30, 0.76], [13, 0.6944], [19, 0.6678], [6, 0.645], [29, 0.6389], [28, 0.6289]], 'eyJpZCI6MjgsInNjb3JlIjowLjYyODl9', 26]),
    ('/api/v1/me/matches?cursor=eyJpZCI6MjgsInNjb3JlIjowLjYyODl9', 200, '612dcfbc2428c553b3e24791c2a3172ecb41a3934da83f619ef338e31ed04fea',
     [[[8, 0.5617], [20, 0.5617], [22, 0.56], [5, 0.5011], [3, 0.4561], [21, 0.4444]], None, 26]),
    ('/api/v1/me/matches?limit=4&order=%20WORST%20&lens=Culture', 200, '01ab181bd41608eef212468c04eb3d0edbd219540a3caa286ae38b08203a7885',
     [[[21, 0.4444], [3, 0.4561], [5, 0.5011], [22, 0.56]], 'eyJpZCI6MjIsInNjb3JlIjowLjU2fQ', 26]),
    ('/api/v1/me/matches?limit=4&order=%20WORST%20&lens=Culture&cursor=eyJpZCI6MjIsInNjb3JlIjowLjU2fQ', 200, '179b75ed207de015f6499881e63c32cc849f65d5c518fa2eafbcc169050f4681',
     [[[8, 0.5617], [20, 0.5617], [28, 0.6289], [29, 0.6389]], 'eyJpZCI6MjksInNjb3JlIjowLjYzODl9', 26]),
    ('/api/v1/me/matches?limit=4&order=%20WORST%20&lens=Culture&cursor=eyJpZCI6MjksInNjb3JlIjowLjYzODl9', 200, 'd9d3b50c2147e7b1359f373db253ff327309a67fa3eacf1cda61917f1f2b4e63',
     [[[6, 0.645], [19, 0.6678], [13, 0.6944], [30, 0.76]], 'eyJpZCI6MzAsInNjb3JlIjowLjc2fQ', 26]),
    ('/api/v1/me/matches?limit=4&order=%20WORST%20&lens=Culture&cursor=eyJpZCI6MzAsInNjb3JlIjowLjc2fQ', 200, 'd9c04bbdd78f017b2bd6ed6bf30f4dec23bf952f0263e4c17e85e2a9eb350f2f',
     [[[26, 0.7617], [1, 0.7672], [15, 0.7728], [14, 0.7833]], 'eyJpZCI6MTQsInNjb3JlIjowLjc4MzN9', 26]),
    ('/api/v1/me/matches?limit=4&order=%20WORST%20&lens=Culture&cursor=eyJpZCI6MTQsInNjb3JlIjowLjc4MzN9', 200, 'de82667f595cd6944d2afad1421b1c404295c0e4e0f88a5b3347363d7a319094',
     [[[9, 0.7873], [4, 0.79], [24, 0.7944], [2, 0.8278]], 'eyJpZCI6Miwic2NvcmUiOjAuODI3OH0', 26]),
    ('/api/v1/me/matches?limit=4&order=%20WORST%20&lens=Culture&cursor=eyJpZCI6Miwic2NvcmUiOjAuODI3OH0', 200, '33b6bec417f66ec90311f21380c34bfd7858df6ea81fe830377eb1f5b3c7bc10',
     [[[11, 0.8611], [7, 0.9167], [17, 0.9167], [18, 0.9167]], 'eyJpZCI6MTgsInNjb3JlIjowLjkxNjd9', 26]),
    ('/api/v1/me/matches?limit=4&order=%20WORST%20&lens=Culture&cursor=eyJpZCI6MTgsInNjb3JlIjowLjkxNjd9', 200, 'ee143abe89ad10bcc127ee5e314d6ed7e56421c8245b4d5973a14195c3747c1c',
     [[[25, 0.9667], [23, 0.9889]], None, 26]),
    ('/api/v1/me/matches?limit=500&order=best', 200, 'f4a5262511595ed2b516d3fc7a3c56a3dfe5e2513db7138b8f2cd9a4e61eccd1',
     [[[23, 0.9889], [25, 0.9667], [7, 0.9167], [17, 0.9167], [18, 0.9167], [11, 0.8611], [2, 0.8278], [24, 0.7944], [4, 0.79], [9, 0.7873], [14, 0.7833], [15, 0.7728], [1, 0.7672], [26, 0.7617], [30, 0.76], [13, 0.6944], [19, 0.6678], [6, 0.645], [29, 0.6389], [28, 0.6289], [8, 0.5617], [20, 0.5617], [22, 0.56], [5, 0.5011], [3, 0.4561], [21, 0.4444]], None, 26]),
    ('/api/v1/me/matches?limit=5&order=worst&cursor=eyJpZCI6MTgsInNjb3JlIjowLjkxNjd9', 200, 'ee143abe89ad10bcc127ee5e314d6ed7e56421c8245b4d5973a14195c3747c1c',
     [[[25, 0.9667], [23, 0.9889]], None, 26]),
    ('/api/v1/me/matches?limit=0', 200, 'b197f0084e3da4864b8d8d83805f7c0177caf24b78a8487d13ba182d350b62b5',
     [[[23, 0.9889]], 'eyJpZCI6MjMsInNjb3JlIjowLjk4ODl9', 26]),
    ('/api/v1/me/matches?limit=abc', 422, '6d408085861cf299dff27db28e811653397c69da5ce9442876501cfa14b19240',
     'validation'),
    ('/api/v1/me/matches?lens=salary', 400, 'a22af6c4cb4c710712379b992292a2bdd348a6b69eff3a64d3c4e487cba87f1c',
     {'error': "Unsupported lens 'salary'"}),
    ('/api/v1/me/matches?order=sideways', 400, '09e1c4756fbf651d1c86d3dc83551f1dd43f8e34f1ad56d77020a143d18b349c',
     {'error': "order must be 'best' or 'worst'"}),
    ('/api/v1/me/matches?cursor=not-a-real-cursor', 422, '917e10460fe8a91d6073e10c7fa1e0628164c5a6ce3b156fd1322acd109dc624',
     'validation'),
    ('/api/v1/me/matches?limit=5&cursor=eyJpZCI6MTgsInNjb3JlIjowLjkxNjd9', 200, '0703f7a0ae6668552782f1a42e1df7f63f6f51ff604ea60836b87569e0ef964a',
     [[[13, 0.8822], [21, 0.7278], [30, 0.7056], [24, 0.6933], [11, 0.6489]], 'eyJpZCI6MTEsInNjb3JlIjowLjY0ODl9', 26]),
    ('/api/v1/me/matches?limit=5&order=worst&cursor=eyJpZCI6MTgsInNjb3JlIjowLjkxNjd9', 200, 'd2aabe8c5069aa98e6ceadf529fe2e5fc462fb8fde787f85ae612d670fb591bd',
     [[[22, 0.9611]], None, 26]),
]

DERIVED_PAGES = [
    ('/api/v1/me/matches?limit=9', 200, 'c875c97e279d0182439bced811490bfdcb0c3070fb91f4b3e15c51bda0bad5f1',
     [[[26, 0.9341], [15, 0.9196], [4, 0.8513], [7, 0.8346], [17, 0.8346], [18, 0.8346], [9, 0.8324], [2, 0.798], [23, 0.7624]], 'eyJpZCI6MjMsInNjb3JlIjowLjc2MjR9', 26]),
    ('/api/v1/me/matches?limit=9&cursor=eyJpZCI6MjMsInNjb3JlIjowLjc2MjR9', 200, '39fdc9ed3c1ea2d02e89f8444af487655ae0c4967b31307fa008ce25c0fc937f',
     [[[25, 0.7624], [28, 0.7498], [6, 0.7493], [19, 0.748], [1, 0.7381], [24, 0.718], [14, 0.6869], [8, 0.6715], [20, 0.6715]], 'eyJpZCI6MjAsInNjb3JlIjowLjY3MTV9', 26]),
    ('/api/v1/me/matches?limit=9&cursor=eyJpZCI6MjAsInNjb3JlIjowLjY3MTV9', 200, '98666f3a92dc4252b43795aeb0c50e014a93ebdb9f52bd1480202c2edc400764',
     [[[13, 0.6643], [11, 0.6569], [29, 0.6531], [30, 0.6487], [3, 0.6104], [22, 0.5298], [21, 0.5193], [5, 0.5165]], None, 26]),
    ('/api/v1/me/matches?limit=9&order=worst', 200, 'f12ad8a215134e5651932a9b2ba0e7929f0091742ea745890f1dd20d5d6d3fa9',
     [[[5, 0.5165], [21, 0.5193], [22, 0.5298], [3, 0.6104], [30, 0.6487], [29, 0.6531], [11, 0.6569], [13, 0.6643], [8, 0.6715]], 'eyJpZCI6OCwic2NvcmUiOjAuNjcxNX0', 26]),
    ('/api/v1/me/matches?limit=9&order=worst&cursor=eyJpZCI6OCwic2NvcmUiOjAuNjcxNX0', 200, '8642d59d69593618ca929451fff630ae28a28b3007c02313b76ece6ebcf9d562',
     [[[20, 0.6715], [14, 0.6869], [24, 0.718], [1, 0.7381], [19, 0.748], [6, 0.7493], [28, 0.7498], [23, 0.7624], [25, 0.7624]], 'eyJpZCI6MjUsInNjb3JlIjowLjc2MjR9', 26]),
    ('/api/v1/me/matches?limit=9&order=worst&cursor=eyJpZCI6MjUsInNjb3JlIjowLjc2MjR9', 200, '27e1de167a113867160531be7de85d85e8e5f794697bdaadecf3e6f6131760aa',
     [[[2, 0.798], [9, 0.8324], [7, 0.8346], [17, 0.8346], [18, 0.8346], [4, 0.8513], [15, 0.9196], [26, 0.9341]], None, 26]),
]
