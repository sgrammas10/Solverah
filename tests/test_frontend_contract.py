"""Every endpoint the SPA calls is served, and it calls the versioned ones.

This file has had two jobs and is now on its second.

Through Phase 1a it asserted that the frontend had *not* started calling
``/api/v1`` -- the legacy aliases existed so the deployed SPA kept working while
the versioned paths became canonical, and a call site moving early would have
been a change nobody had coordinated.  It was written to fail the moment the
cutover began, which is what it did.

Phase 1b is that cutover.  The assertions below are the inverse: every call site
is on ``/api/v1``, no call site is on an unversioned path, and every path the
SPA calls is one the API actually serves.  The last one is what makes deleting
``register_legacy_aliases`` safe -- a path the frontend still called and the API
had stopped serving would otherwise be a 404 found in a browser rather than here.

Scanning source rather than running the app is deliberate: ``npm`` is not
available in every environment this suite runs in, and a Playwright smoke suite
(Phase 4) could not enumerate paths only reached from rarely visited screens.

**A defect this file carried until Phase 1b, worth knowing about.** The call-site
regex did not allow a generic type argument, so it never matched
``fetchWithAuth<AssessmentForm>("/assessment/form")`` -- the form the majority of
authenticated call sites are written in. It saw 24 of 37 paths and reported
success, and ``test_the_scan_finds_the_call_sites`` passed because 24 cleared its
floor of 20. A guard whose threshold is far below the real number cannot tell a
partial scan from a complete one, so the floor below is now close to the real
count and there is a second guard that fails if the two shapes stop being seen.
"""

import re
from pathlib import Path

import pytest

from solverah.factory import LEGACY_PREFIX, V1_PREFIX

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"

# Two shapes reach the API, and the second has an optional generic argument:
#   fetch(`${API_BASE}/auth/login`, ...)
#   fetchWithAuth<AssessmentForm>("/assessments/core/form")
_CALL_PATTERNS = (
    re.compile(r"\$\{API_BASE\}(/[A-Za-z0-9_\-/\$\{\}.]*)"),
    re.compile(
        r"""(?:fetchWithAuth|streamFetch)\s*(?:<[^>]*>)?\(\s*[`'"](/[A-Za-z0-9_\-/\$\{\}.]*)"""
    ),
)

_SOURCE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx"}

#: Below the real count, above a scan that has silently stopped matching one of
#: the two shapes. See the module docstring for why this is not simply 20.
_MINIMUM_CALL_SITES = 32


def _is_source(path: Path) -> bool:
    """Production source only -- a test file's mocked URL is not a call site."""
    return (
        path.suffix in _SOURCE_SUFFIXES
        and "__tests__" not in path.as_posix()
        and ".test." not in path.name
    )


def _frontend_endpoints() -> dict:
    """Endpoint suffix -> the files that call it."""
    found: dict = {}
    for path in SRC.rglob("*"):
        if not _is_source(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in _CALL_PATTERNS:
            for match in pattern.finditer(text):
                suffix = match.group(1).split("?")[0].rstrip("/") or "/"
                found.setdefault(suffix, set()).add(
                    path.relative_to(REPO_ROOT).as_posix()
                )
    return found


def _segments(rule: str) -> list:
    return [part for part in rule.strip("/").split("/") if part]


def _matches_rule(suffix: str, rule: str) -> bool:
    """Whether a call-site suffix is served by *rule*.

    Compared segment by segment rather than by string, because the two do not
    line up literally in either direction:

    * A call site can interpolate where a rule declares a converter --
      ``/companies/${id}`` against ``/api/v1/companies/<int:company_id>``, and
      ``/me/resumes/${resumeId}/complete`` against
      ``/api/v1/me/resumes/<resume_id>/complete``.
    * A call site can also pass a *literal* where a rule declares one --
      ``/assessments/core/form`` against ``/api/v1/assessments/<kind>/form``,
      and ``/me/resumes/current/download-url``. Those are constants at the call
      site because the instrument is known there.

    So a converter segment matches any single segment, and an interpolated
    segment matches only a converter -- an interpolated value cannot be checked
    against a literal, since the whole point is that it varies. Matching by
    shape rather than by substituting one hard-coded converter name is what lets
    a new templated route exist without this test learning about it.
    """
    call = _segments(V1_PREFIX + suffix)
    served = _segments(rule)
    if len(call) != len(served):
        return False
    for from_call, from_rule in zip(call, served):
        if from_rule.startswith("<") and from_rule.endswith(">"):
            continue
        if "${" in from_call:
            return False
        if from_call != from_rule:
            return False
    return True


@pytest.fixture()
def served_rules():
    from app import app

    return [rule.rule for rule in app.url_map.iter_rules()]


# ── The scan itself ─────────────────────────────────────────────────────────


def test_the_scan_finds_the_call_sites(served_rules):
    """Guards the tests below from passing because the regex stopped matching."""
    assert len(_frontend_endpoints()) >= _MINIMUM_CALL_SITES


def test_the_scan_sees_both_call_shapes(served_rules):
    """The regression cover for the generics gap described in the module docstring.

    A floor on the total is not enough on its own: one of the two patterns can
    stop matching entirely while the other still clears it, which is exactly
    what happened. This fails if either shape stops being found.
    """
    template_literal, helper_with_generic = _CALL_PATTERNS
    seen = {"template_literal": 0, "helper": 0}
    for path in SRC.rglob("*"):
        if not _is_source(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        seen["template_literal"] += len(template_literal.findall(text))
        seen["helper"] += len(helper_with_generic.findall(text))

    assert seen["template_literal"] > 0, "no `${API_BASE}/...` call sites matched"
    assert seen["helper"] > 0, "no `fetchWithAuth(...)` call sites matched"


# ── The cutover ─────────────────────────────────────────────────────────────


def test_every_endpoint_the_frontend_calls_is_served(served_rules):
    """A path the SPA calls and the API does not serve is a 404 in the browser.

    This is what makes removing the legacy aliases safe rather than hopeful.
    """
    missing = {
        suffix: sorted(files)
        for suffix, files in _frontend_endpoints().items()
        if not any(_matches_rule(suffix, rule) for rule in served_rules)
    }

    assert missing == {}, "frontend calls paths the API does not serve: %s" % missing


def test_the_frontend_calls_only_versioned_paths(served_rules):
    """The inverse of what this test asserted through Phase 1a.

    `API_BASE` now ends in `/api/v1`, so a call site is versioned by
    construction unless it hard-codes a prefix of its own. This catches one that
    does -- which is the only way an unversioned path can reappear now that the
    aliases serving them are gone.
    """
    unversioned = sorted(
        suffix
        for suffix in _frontend_endpoints()
        if suffix.startswith(LEGACY_PREFIX + "/") or suffix.startswith("/v1/")
    )

    assert unversioned == [], (
        "call sites carry their own prefix instead of relying on API_BASE: %s"
        % unversioned
    )


def test_the_api_base_constant_carries_the_version(served_rules):
    """The version lives in exactly one place, which is what made the cutover one line.

    Had it been repeated at every call site, moving to /api/v1 would have been 37
    edits and moving to /api/v2 will be 37 more.
    """
    # Phase 4 moved the transport module: src/utils/api.ts -> src/shared/api/api.ts.
    # Path-only change; the assertion and its meaning are untouched.
    api_module = (SRC / "shared" / "api" / "api.ts").read_text(encoding="utf-8")

    assert "/api/v1" in api_module


def test_no_call_site_targets_a_superseded_path(served_rules):
    """Named paths, because a rename that half-lands is the failure mode here.

    Every entry below was a real endpoint before Phase 1b and is now gone. If one
    reappears in a call site it is a merge that resurrected an old line, and the
    symptom in production is a 404 on one screen rather than a broken build.
    """
    superseded = {
        "/profile",
        "/profile/career-status",
        "/profile/skills/proficiency",
        "/profile/resume-url",
        "/profile/resume/presign",
        "/profile/resume/finalize",
        "/dashboard-data",
        "/register",
        "/login",
        "/logout",
        "/confirm-email",
        "/resend-confirmation",
        "/request-password-reset",
        "/verify-password-reset",
        "/early-access-request",
        "/intake/presign",
        "/intake/finalize",
        "/intake/create-account",
        "/intake/sign-in",
        "/intake/link-account",
        "/intake/save-to-account",
        "/quiz-insights",
        "/quiz-insights-guest",
        "/recommendations",
        "/agent/chat",
        "/intelligence/path-preferences",
        "/intelligence/path-suggestions",
        "/assessment/form",
        "/assessment/submit",
        "/work-pulse/lite-lite/result",
        "/work-pulse/submit",
        "/work-pulse/results",
        "/focus-type/submit",
        "/manager-match/submit",
        "/manager-match/results",
        "/company-lens/matches",
    }
    called = _frontend_endpoints()
    still_used = {
        suffix: sorted(called[suffix]) for suffix in sorted(superseded & set(called))
    }

    assert still_used == {}, "call sites still on superseded paths: %s" % still_used
