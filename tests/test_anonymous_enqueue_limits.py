"""The anonymous `wpll` enqueue is bounded per-IP *and* globally.

**The finding (2026-09 audit, 3.1 MED, probed live).** `POST
/assessments/wpll/scoring-jobs` is the application's second unauthenticated door
onto a paid provider: every accepted call commits a `scoring_jobs` row and, in
the worker, makes a `gpt-4o-mini` request with no account behind it. It carried
no limit of its own -- it rode `DEFAULT_LIMITS` (`200 per day;50 per hour`, per
IP), which has no burst term at all. The audit fired 40 back-to-back enqueues
from one address in 49 seconds and collected 40 `202`s.

**Why a per-IP limit alone was never going to be the fix.** Spend scales with
the number of *distinct* addresses, which is the one quantity an abuser controls
freely: N addresses buy N × the per-IP budget. `POST
/intake/quiz-preview/insights` already had the right shape for exactly this
reason and said so in its own comment -- a per-IP limit sized for a human, plus
a global-key bucket sized to a spend budget. S1 gives `wpll` the same two, and
`security.WPLL_ANON_GLOBAL_LIMIT` records what is deliberately *not* shared with
it.

**Three design decisions this file pins**, because each is a place the next
person could reasonably do the opposite:

  * The global ceiling is on the enqueue only, never on `POST
    /assessments/wpll/submissions`. That route answers `410 Gone` for `wpll`
    before auth and before the body is read, so it spends nothing -- and
    counting free refusals into a shared bucket would hand anyone a way to close
    the teaser for every real visitor.
  * The global ceiling does not touch the four authenticated instruments, which
    have an account behind them and are bounded by that.
  * The per-IP limit *replaced* wpll's bare defaults rather than stacking on top
    of them. Two per-IP buckets on one door is the conflicting-bucket shape,
    where the effective limit is whichever is tighter and neither string says
    which.

Enforcement itself -- that a limiter decorator fires at all -- is covered by
`tests/test_rate_limits.py`; what is verified here is that the right limits are
attached to the right routes with the right keys.
"""

import pytest

from security import (
    GUEST_INSIGHTS_GLOBAL_LIMIT,
    WPLL_ANON_GLOBAL_LIMIT,
    WPLL_ANON_PER_IP_LIMIT,
    global_rate_limit_key,
)
from solverah.api.v1 import assessments
from solverah.services import assessment_service

#: Flask-Limiter keys decorated limits by "<module>.<qualname>.<name>", which is
#: how a handler is identified independently of its URL rule.
_VIEW = "solverah.api.v1.assessments.%s.%s"
ENQUEUE = _VIEW % (("assessment_kind_scoring_job",) * 2)
SUBMIT = _VIEW % (("assessment_kind_submit",) * 2)


def _buckets_for(view, kind="wpll"):
    """The distinct rate-limit buckets *view* would consult for *kind*.

    Read off the limit manager rather than off the decorators, because a limit
    that is declared but never attached is exactly the defect this codebase has
    already been bitten by once -- every `@limiter.limit` in the pre-Phase-1
    `app.py` sat above its `@app.route` and enforced nothing. Asserting on
    decorator arguments would pass against that; asserting on the registry
    cannot.

    Resolved inside a request context because both the limit string and the
    scope are callables that read `{kind}` off `view_args` -- which is also why
    this returns *buckets* (key function plus resolved scope) rather than
    limits. `"5 per minute;20 per hour;50 per day"` expands to three
    `RuntimeLimit`s that all count into one bucket, so counting limits would
    answer a question nobody is asking.
    """
    from app import app
    from flask import request
    from solverah.extensions import limiter

    with app.test_request_context("/api/v1/assessments/%s/scoring-jobs" % kind):
        request.view_args = {"kind": kind}
        limits = limiter.limit_manager.decorated_limits(view)
        buckets = {(lim.key_func, lim.scope_for(view, "POST")) for lim in limits}

    assert buckets, "no limits registered for %s -- has the view been renamed?" % view
    return buckets


# ── The per-IP limit ────────────────────────────────────────────────────────

def test_wpll_no_longer_rides_the_bare_global_defaults():
    """The finding. `200 per day;50 per hour` has no burst term; this one does."""
    assert assessments.SUBMISSION_LIMITS["wpll"] == WPLL_ANON_PER_IP_LIMIT
    assert assessments.SUBMISSION_LIMITS["wpll"] != ";".join(assessments.DEFAULT_LIMITS)


def test_the_wpll_per_ip_limit_has_a_burst_term():
    """A per-minute term is what the 40-in-49-seconds probe walked through."""
    assert "per minute" in WPLL_ANON_PER_IP_LIMIT


def test_the_wpll_per_ip_limit_keeps_a_daily_backstop():
    """`shared_limit` defaults to `override_defaults=True`.

    So naming only a minute and an hour here would silently *remove* the
    200-per-day cap while reading like a tightening -- the trap
    `SUBMISSION_LIMITS` has documented since Phase 1b, and the reason the old
    value was spelled `";".join(DEFAULT_LIMITS)` in the first place.
    """
    assert "per day" in WPLL_ANON_PER_IP_LIMIT


def test_the_wpll_per_ip_limit_is_not_looser_than_the_defaults_it_replaced():
    """Tightening, in every term the old value had."""
    assert "50 per hour" not in WPLL_ANON_PER_IP_LIMIT
    assert "200 per day" not in WPLL_ANON_PER_IP_LIMIT


def test_the_four_authenticated_instruments_are_untouched():
    """S1 changed one entry in this table. The other four are not its business."""
    for kind in ("core", "work_pulse", "focus_type", "manager_match"):
        assert assessments.SUBMISSION_LIMITS[kind] == assessments.DEFAULT_SUBMISSION_LIMIT


def test_only_one_per_ip_bucket_is_attached_to_the_enqueue():
    """The "don't stack conflicting buckets" instruction, as an assertion.

    Two per-IP buckets on one door means the effective limit is whichever is
    tighter, and neither limit string tells you which. The enqueue consults
    exactly two buckets, and exactly one of them is keyed on the caller.
    """
    buckets = _buckets_for(ENQUEUE)
    per_ip = {b for b in buckets if b[0] is not global_rate_limit_key}

    assert len(buckets) == 2
    assert len(per_ip) == 1


# ── The global ceiling ──────────────────────────────────────────────────────

def test_the_enqueue_carries_a_global_key_ceiling():
    """The control that actually caps the bill. Fails against the pre-S1 route."""
    buckets = _buckets_for(ENQUEUE)

    assert any(key is global_rate_limit_key for key, _ in buckets)


def test_the_global_ceiling_is_exempt_for_authenticated_instruments(app_ctx):
    """It applies to the anonymous door and to nothing else.

    Driven through `_is_authenticated_kind` with a real request context per
    kind, rather than asserted about the source, because "which kinds does this
    exempt" is the question and the registry is what answers it.
    """
    from app import app

    for kind in assessment_service.ASSESSMENT_KINDS:
        with app.test_request_context("/api/v1/assessments/%s/scoring-jobs" % kind.key):
            from flask import request

            request.view_args = {"kind": kind.key}
            exempt = assessments._is_authenticated_kind()

        assert exempt is kind.requires_auth, kind.key


def test_an_unknown_kind_does_not_spend_the_anonymous_budget(app_ctx):
    """A 404 must not be able to close the door for real visitors.

    `_job_kind_or_404` is about to refuse this request, and it reaches no
    provider -- so counting it into a bucket shared by every caller would let
    anyone exhaust the day's teaser budget by typing a name that does not exist.
    """
    from app import app
    from flask import request

    with app.test_request_context("/api/v1/assessments/nope/scoring-jobs"):
        request.view_args = {"kind": "nope"}

        assert assessments._is_authenticated_kind() is True


def test_the_global_ceiling_is_not_on_the_410_route():
    """`POST /assessments/wpll/submissions` spends nothing, so it counts nothing.

    Since Phase 3c that route answers `410 Gone` for `wpll` before auth and
    before the body is read. Attaching the shared bucket there would make 500
    free refusals enough to close the teaser for everyone -- the per-IP bucket
    still counts them, and should, because it bounds only the caller doing it.
    """
    buckets = _buckets_for(SUBMIT)

    assert not any(key is global_rate_limit_key for key, _ in buckets)
    assert len(buckets) == 1


def test_the_two_anonymous_ceilings_do_not_share_a_bucket(app_ctx):
    """wpll and guest-insights are separate budgets, on purpose.

    One shared bucket would mean abuse of either endpoint silently closes the
    other -- two funnel entrances failing together for a reason neither log
    would explain.
    """
    from app import app
    from flask import request

    with app.test_request_context("/api/v1/assessments/wpll/scoring-jobs"):
        request.view_args = {"kind": "wpll"}
        wpll_scope = assessments._anonymous_submission_scope("whatever")

    assert wpll_scope == "assessments:submit:wpll:global"
    assert "intake" not in wpll_scope


def test_the_global_scope_is_distinct_from_the_per_ip_one(app_ctx):
    """Same name with two key functions would be one name for two counters."""
    from app import app
    from flask import request

    with app.test_request_context("/api/v1/assessments/wpll/scoring-jobs"):
        request.view_args = {"kind": "wpll"}

        assert (
            assessments._anonymous_submission_scope("e")
            != assessments._submission_scope("e")
        )


def test_the_global_ceiling_is_a_daily_spend_budget():
    """Sized like the endpoint it mirrors, and stated in the same unit."""
    assert "per day" in WPLL_ANON_GLOBAL_LIMIT
    assert WPLL_ANON_GLOBAL_LIMIT == GUEST_INSIGHTS_GLOBAL_LIMIT


@pytest.fixture()
def app_ctx(client):
    """Schema plus a context; `client` owns the create/drop."""
    from app import app

    with app.app_context():
        yield app
