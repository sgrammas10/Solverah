"""Production CORS admits the four real origins and nothing else.

**The finding (2026-09 audit, 7.1 MED, probed live).** `factory.py` listed
`http://localhost:\\d+` and `http://127\\.0\\.0\\.1:\\d+` in the CORS origins
alongside the real hosts, with `supports_credentials=True` and no gate on the
environment. Probed against a production-configured app: `Origin:
http://localhost:9999` came back reflected as `Access-Control-Allow-Origin`
together with `Access-Control-Allow-Credentials: true`.

That is a live credential boundary, not a hygiene item. Production cookies are
`SameSite=None` (they have to be -- the SPA and the API are on different
subdomains), so the browser attaches them to a cross-origin request from any
permitted origin. Anything the victim's browser can be made to load from a local
listener -- a dev server they are running, an Electron app, an npm package that
binds a port during install -- was a permitted credentialed origin and could
read `/me`, `/me/profile` and `/me/export` in full. Writes still needed the
X-CSRF-TOKEN header; reads did not.

**Sub-finding, also closed here.** flask-cors 6.0.5 matches origin *patterns*
with `re.match`, which anchors on the left only, so the unanchored
`http://localhost:\\d+` also matched `http://localhost:3000.evil.com`. Not
browser-reachable -- no browser emits an Origin with that authority -- but the
anchor costs one character.

**Why these tests read the list rather than booting two apps.** The allowlist is
a pure function of `is_production`, and `_cors_origins` is where it is decided.
Booting a second production-configured `create_app()` inside the suite would
need a second database, HSTS, and `force_https` redirecting every probe -- a lot
of machinery between the assertion and the thing asserted. The one live test at
the bottom pins that the function's answer is what actually reaches flask-cors.
"""

import re

import pytest
from flask_cors.core import probably_regex, try_match_pattern

from solverah.factory import LOCAL_CORS_ORIGINS, PRODUCTION_CORS_ORIGINS, _cors_origins


def _admits(entry: str, origin: str) -> bool:
    """Whether flask-cors would let *origin* through on the strength of *entry*.

    Its own two functions, not a re-implementation. flask-cors decides
    literal-vs-regex per entry with `probably_regex` (a metacharacter sniff) and
    then compares with `==` or `re.match` accordingly -- so a test that assumed
    one or the other would be testing a matcher the library does not use, and
    would miss the case where adding a metacharacter silently reclassifies an
    entry from literal to pattern.
    """
    pattern = re.compile(entry) if probably_regex(entry) else entry
    return try_match_pattern(origin, pattern, caseSensitive=False)


#: The origins the product actually runs on (2026-09 prod-readiness Q10/Q11:
#: `solverah.com` serves the SPA, `api.solverah.com` serves this API, and the
#: Vercel alias sits behind the custom domain).
REAL_ORIGINS = {
    "https://solverah.com",
    "https://www.solverah.com",
    "https://api.solverah.com",
    "https://solverah.vercel.app",
}


def test_production_admits_exactly_the_real_origins():
    """The finding. Fails against the unconditional list."""
    assert set(_cors_origins(is_production=True)) == REAL_ORIGINS


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:5173",
        "http://localhost:9999",
        "http://127.0.0.1:3000",
        "http://localhost:3000.evil.com",
        "https://evil.example.com",
        "https://solverah.com.evil.net",
    ],
)
def test_no_production_entry_admits_a_hostile_or_local_origin(origin):
    """Run through flask-cors' own matcher, not through the list.

    Written this way so that adding a *pattern* to the production list -- the
    shape of the original defect -- fails here even if the literal strings still
    look right.
    """
    for entry in _cors_origins(is_production=True):
        assert not _admits(entry, origin), "%r admitted %r" % (entry, origin)


def test_development_keeps_localhost():
    """`npm run dev` on :5173 against a local API has to keep working."""
    origins = _cors_origins(is_production=False)

    assert set(REAL_ORIGINS).issubset(origins)
    for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
        assert any(_admits(e, origin) for e in origins), origin


@pytest.mark.parametrize("pattern", LOCAL_CORS_ORIGINS)
def test_the_local_patterns_are_anchored(pattern):
    """The sub-finding: `re.match` does not anchor the right-hand end.

    Fails against the unanchored form, which matches `localhost:3000.evil.com`.
    """
    assert re.match(pattern, "http://localhost:3000.evil.com") is None
    assert re.match(pattern, "http://127.0.0.1:3000.evil.com") is None


@pytest.mark.parametrize("origin", sorted(REAL_ORIGINS))
def test_the_production_entries_are_literals_not_patterns(origin):
    """Literals have no suffix to slip past; a pattern would need its own anchor.

    flask-cors classifies each entry itself, sniffing for metacharacters, so the
    classification is read back from `probably_regex` rather than eyeballed. As
    long as these stay literals, `https://solverah.com.evil.net` is compared with
    `==` against `https://solverah.com` and cannot match -- with no anchor for
    anyone to forget.
    """
    assert origin in PRODUCTION_CORS_ORIGINS
    assert probably_regex(origin) is False


def test_the_running_app_reflects_a_dev_origin_and_not_a_hostile_one(client):
    """One end-to-end check that `_cors_origins` is what flask-cors was given.

    The suite's app is not production-configured, so what is pinned here is the
    dev half plus the negative that holds in both: an unlisted origin is never
    reflected. The production half is the list assertions above -- booting a
    second, production-configured app inside this suite would bring HSTS and
    `force_https` with it and test the redirect rather than the allowlist.
    """
    allowed = client.get(
        "/api/v1/health", headers={"Origin": "http://localhost:5173"}
    )
    hostile = client.get(
        "/api/v1/health", headers={"Origin": "https://evil.example.com"}
    )

    assert allowed.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    assert hostile.headers.get("Access-Control-Allow-Origin") is None
