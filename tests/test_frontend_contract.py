"""Every endpoint the SPA calls is still served.

The frontend has not been touched by Phase 1a and must not need to be: the
legacy `/api/...` aliases exist precisely so the deployed SPA keeps working while
the versioned paths become canonical. This test is what turns that from an
intention into a check.

It also has a job after the cutover. When the aliases are removed in Phase 1b,
this test fails for every call site that has not moved to `/api/v1/...` -- which
is a far better way to find them than a 404 in production. Until then, the second
test below reports how far along the cutover is.

Scanning source rather than running the app is deliberate: `npm` is not
available in every environment this suite runs in, and a Playwright smoke suite
(Phase 4) would not be able to enumerate paths that are only reached from rarely
visited screens.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"

# API_BASE already ends in "/api", so a call site supplies only what follows:
#   fetch(`${API_BASE}/quiz-insights`, ...)
#   fetchWithAuth("/quiz-insights", ...)
_CALL_PATTERNS = (
    re.compile(r"\$\{API_BASE\}(/[A-Za-z0-9_\-/\$\{\}.]*)"),
    re.compile(r"""(?:fetchWithAuth|streamFetch)\(\s*[`'"](/[A-Za-z0-9_\-/\$\{\}.]*)"""),
)

_SOURCE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx"}


def _frontend_endpoints() -> dict:
    """Endpoint suffix -> the files that call it."""
    found: dict = {}
    for path in SRC.rglob("*"):
        if path.suffix not in _SOURCE_SUFFIXES or "__tests__" in path.as_posix():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in _CALL_PATTERNS:
            for match in pattern.finditer(text):
                suffix = match.group(1).split("?")[0]
                found.setdefault(suffix, set()).add(
                    path.relative_to(REPO_ROOT).as_posix()
                )
    return found


def _to_rule(suffix: str) -> str:
    """A call-site suffix as the Werkzeug rule it should match.

    Template literals are collapsed to the one path converter the API has:
    `/companies/${id}` -> `/api/companies/<int:company_id>`.
    """
    url = "/api" + suffix
    url = re.sub(r"\$\{[^}]+\}", "<int:company_id>", url)
    return url.rstrip("/") or "/api"


@pytest.fixture()
def served_rules():
    from app import app

    return {rule.rule for rule in app.url_map.iter_rules()}


def test_the_scan_finds_the_call_sites(served_rules):
    """Guards the test below from passing because the regex stopped matching."""
    assert len(_frontend_endpoints()) >= 20


def test_every_endpoint_the_frontend_calls_is_served(served_rules):
    """A path the SPA calls and the API does not serve is a 404 in the browser."""
    missing = {
        suffix: sorted(files)
        for suffix, files in _frontend_endpoints().items()
        if _to_rule(suffix) not in served_rules
    }

    assert missing == {}, "frontend calls paths the API does not serve: %s" % missing


def test_the_frontend_has_not_started_the_v1_cutover_yet(served_rules):
    """Documents where the cutover stands, and fails when it begins.

    Phase 1a deliberately leaves the frontend alone. When someone starts moving
    call sites to `/api/v1/...`, this test fails and should be replaced by its
    inverse -- at which point the legacy aliases in
    `solverah.factory.register_legacy_aliases` can be deleted.
    """
    versioned = [
        suffix for suffix in _frontend_endpoints() if suffix.startswith("/v1/")
    ]

    assert versioned == [], (
        "the frontend has begun calling /api/v1: %s. Finish the cutover, then "
        "delete register_legacy_aliases and invert this test." % sorted(versioned)
    )
