"""The prune policy, exhaustively -- this is the code that deletes backups.

``solverah/domain/backup_retention.py`` is pure by design so that every rule it
enforces can be stated as an input and an expected decision, with no bucket, no
database and no clock in the way.  This file spends that: the window itself gets
a handful of tests, and the three refusals get most of the file, because a bug
in the window costs disk and a bug in a refusal costs the database.

The failures each test pins, in the order the module lists them:

1. **Never delete the newest artifact.** A cron that has been broken for 40 days
   makes every artifact "expired". The naive reading of a 30-day window empties
   the bucket, and it does it at the exact moment nothing is producing new
   backups.
2. **Delete nothing unless this pass's dump verified.** Pruning is only ever
   "make room now that a good copy exists".
3. **Refuse entirely below the floor**, rather than deleting down to it. A thin
   bucket means something upstream is wrong -- a new bucket, a changed prefix, a
   cron that stopped -- and none of those are moments to start deleting.
"""

from datetime import datetime, timedelta, timezone

import pytest

from solverah.domain.backup_retention import (
    DEFAULT_MIN_RETAINED,
    DEFAULT_RETENTION_DAYS,
    Artifact,
    plan_prune,
)

NOW = datetime(2026, 9, 3, 3, 30, tzinfo=timezone.utc)
KB = 1024


def _artifact(age_days: float, *, size: int = 10 * KB, name: str = None) -> Artifact:
    moment = NOW - timedelta(days=age_days)
    return Artifact(
        key=name or "daily/solverah-%s.dump" % moment.strftime("%Y%m%dT%H%M%SZ"),
        size_bytes=size,
        modified_at=moment,
    )


def _daily_series(count: int, *, oldest_age_days: float = None) -> list:
    """``count`` artifacts one day apart, the newest taken moments ago."""
    return [_artifact(age_days=i) for i in range(count)]


def _plan(artifacts, **overrides):
    """plan_prune with a healthy pass's defaults; overrides name what a test varies."""
    kwargs = {
        "now": NOW,
        "uploaded_key": artifacts[0].key if artifacts else "daily/none.dump",
        "verified": True,
    }
    kwargs.update(overrides)
    return plan_prune(artifacts, **kwargs)


# ── The window ──────────────────────────────────────────────────────────────


def test_a_healthy_bucket_deletes_exactly_what_aged_out():
    """31 dailies plus one 31 days old: that one goes and nothing else does."""
    artifacts = _daily_series(31)
    oldest_kept = artifacts[-1]
    assert (NOW - oldest_kept.modified_at).days == 30, "the window's last day"

    plan = _plan(artifacts + [_artifact(age_days=31)])

    assert plan.refusal is None
    assert plan.delete == (_artifact(age_days=31).key,)
    assert plan.retained_files == 31


def test_nothing_expired_means_nothing_deleted_and_no_refusal():
    plan = _plan(_daily_series(10))

    assert plan.delete == ()
    assert plan.refusal is None
    assert plan.retained_files == 10


def test_the_boundary_day_is_kept_and_the_day_past_it_is_not():
    """A 30-day window keeps 30 days. Off-by-one here is a silently shorter policy."""
    artifacts = _daily_series(29) + [
        _artifact(age_days=29.9, name="daily/just-inside.dump"),
        _artifact(age_days=30.1, name="daily/just-outside.dump"),
    ]

    plan = _plan(artifacts)

    assert "daily/just-inside.dump" not in plan.delete
    assert "daily/just-outside.dump" in plan.delete


def test_a_custom_window_is_honoured():
    plan = _plan(_daily_series(20), retention_days=7)

    assert len(plan.delete) == 12  # ages 8..19; age 7 is not yet past a 7-day window
    assert plan.retained_files == 8


def test_retained_totals_describe_what_survives_not_what_was_listed():
    """The JSON line's growth numbers must be post-prune, or the trend lies."""
    artifacts = _daily_series(30) + [
        _artifact(age_days=40, size=99 * KB, name="daily/ancient.dump")
    ]

    plan = _plan(artifacts)

    assert plan.delete == ("daily/ancient.dump",)
    assert plan.retained_files == 30
    assert plan.retained_bytes == 30 * 10 * KB


# ── Refusal 1: the newest artifact is never deleted ─────────────────────────


def test_the_newest_artifact_is_never_deleted_even_when_it_is_expired():
    """The broken-cron case: nothing has uploaded in 40 days, so everything is
    'expired' and the literal reading of the window empties the bucket at the
    exact moment nothing is producing new backups.

    ``min_retained=1`` here on purpose. With the real floor this case is refused
    before the newest-artifact rule is ever consulted (see the double-rail test
    below), so testing the rule at all means removing the rail in front of it.
    """
    artifacts = [_artifact(age_days=40 + i) for i in range(12)]

    plan = _plan(artifacts, uploaded_key=artifacts[0].key, min_retained=1)

    assert plan.refusal is None
    assert artifacts[0].key not in plan.delete, "prune deleted the newest backup"
    assert len(plan.delete) == 11


def test_an_all_expired_bucket_is_protected_by_both_rails_independently():
    """The last backup survives twice over: the floor refuses the whole prune,
    and if the floor were ever lowered the newest-artifact rule still holds."""
    artifacts = [_artifact(age_days=40 + i) for i in range(12)]

    with_floor = _plan(artifacts, uploaded_key=artifacts[0].key)
    assert with_floor.delete == ()
    assert "below the floor" in with_floor.refusal

    without_floor = _plan(artifacts, uploaded_key=artifacts[0].key, min_retained=1)
    assert artifacts[0].key not in without_floor.delete


def test_the_newest_is_identified_by_time_not_by_listing_order():
    older = _artifact(age_days=50, name="daily/aaa-older.dump")
    newest = _artifact(age_days=40, name="daily/zzz-newest.dump")
    rest = [_artifact(age_days=41 + i) for i in range(10)]

    plan = _plan([older] + rest + [newest], uploaded_key=newest.key, min_retained=1)

    assert newest.key not in plan.delete
    assert older.key in plan.delete


def test_a_tie_on_timestamp_still_protects_exactly_one_artifact():
    """Two artifacts sharing a timestamp must not both be treated as 'not newest'."""
    same_moment = NOW - timedelta(days=40)
    tied = [
        Artifact(key="daily/a.dump", size_bytes=KB, modified_at=same_moment),
        Artifact(key="daily/b.dump", size_bytes=KB, modified_at=same_moment),
    ]
    others = [_artifact(age_days=41 + i) for i in range(10)]

    plan = _plan(tied + others, uploaded_key="daily/b.dump", min_retained=1)

    assert len(plan.delete) == 11
    assert "daily/b.dump" not in plan.delete  # the tie-break winner
    assert "daily/a.dump" in plan.delete


def test_a_single_artifact_bucket_deletes_nothing():
    """The degenerate case both rails cover; either one alone would be enough."""
    only = _artifact(age_days=100)

    plan = _plan([only], uploaded_key=only.key)

    assert plan.delete == ()
    assert plan.retained_files == 1


# ── Refusal 2: an unverified dump prunes nothing ────────────────────────────


def test_an_unverified_dump_prunes_nothing_however_expired_the_rest_is():
    artifacts = _daily_series(20) + [_artifact(age_days=99, name="daily/ancient.dump")]

    plan = _plan(artifacts, verified=False)

    assert plan.delete == ()
    assert "did not verify" in plan.refusal
    assert plan.retained_files == 21, "a refusal still reports everything as retained"


def test_verification_is_checked_before_anything_else():
    """An unverified pass is refused for that reason, not for a lesser one.

    Ordering matters for the operator: 'the dump did not verify' names a broken
    backup; 'below the floor' names a thin bucket. Reporting the second when the
    first is true sends someone to look at the wrong thing.
    """
    plan = _plan([_artifact(age_days=99)], verified=False, uploaded_key="daily/absent.dump")

    assert "did not verify" in plan.refusal


# ── Refusal 3: the listing must contain what this pass uploaded ─────────────


def test_a_listing_missing_the_uploaded_key_prunes_nothing():
    """Wrong prefix, wrong bucket, or a store that lied about the upload.

    All three produce a listing that is not a listing of these backups, and no
    deletion decision taken on it can be trusted -- including one that looks
    perfectly reasonable.
    """
    artifacts = _daily_series(20) + [_artifact(age_days=99, name="daily/ancient.dump")]

    plan = _plan(artifacts, uploaded_key="daily/solverah-not-in-this-bucket.dump")

    assert plan.delete == ()
    assert "just uploaded" in plan.refusal
    assert plan.retained_files == 21


def test_an_empty_listing_prunes_nothing():
    plan = plan_prune([], now=NOW, uploaded_key="daily/x.dump", verified=True)

    assert plan.delete == ()
    assert plan.refusal is not None
    assert plan.retained_files == 0


# ── Refusal 4: the floor ────────────────────────────────────────────────────


def test_pruning_below_the_floor_deletes_nothing_at_all():
    """Not 'delete down to seven' -- delete nothing. Partial application of a
    policy whose inputs look wrong is a slower version of the accident."""
    artifacts = [_artifact(age_days=0)] + [_artifact(age_days=40 + i) for i in range(4)]

    plan = _plan(artifacts, uploaded_key=artifacts[0].key)

    assert plan.delete == ()
    assert "below the floor" in plan.refusal
    assert plan.retained_files == 5


def test_the_floor_counts_survivors_not_deletions():
    """Exactly at the floor is allowed; one below it is refused."""
    at_floor = [_artifact(age_days=i) for i in range(DEFAULT_MIN_RETAINED)] + [
        _artifact(age_days=40 + i) for i in range(3)
    ]
    plan = _plan(at_floor, uploaded_key=at_floor[0].key)
    assert len(plan.delete) == 3
    assert plan.retained_files == DEFAULT_MIN_RETAINED

    below = at_floor[1:]  # one fewer survivor
    plan = _plan(below, uploaded_key=below[0].key)
    assert plan.delete == ()
    assert "below the floor" in plan.refusal


def test_a_first_week_bucket_prunes_nothing_and_is_not_an_error():
    """Days 1-7 of this feature in production: expected, and exit 0."""
    for day in range(1, DEFAULT_MIN_RETAINED + 1):
        artifacts = _daily_series(day)
        plan = _plan(artifacts)

        assert plan.delete == ()
        assert plan.retained_files == day


def test_a_custom_floor_is_honoured():
    artifacts = [_artifact(age_days=0), _artifact(age_days=1), _artifact(age_days=40)]

    refused = _plan(artifacts, uploaded_key=artifacts[0].key)
    assert refused.delete == ()

    allowed = _plan(artifacts, uploaded_key=artifacts[0].key, min_retained=2)
    assert allowed.delete == (artifacts[2].key,)


# ── Inputs the policy refuses to guess about ────────────────────────────────


def test_a_naive_now_is_rejected():
    """Comparing an aware timestamp against a naive one raises deep inside the
    window arithmetic; better to refuse at the door than to guess a timezone."""
    with pytest.raises(ValueError, match="timezone-aware"):
        plan_prune([], now=datetime(2026, 9, 3, 3, 30), uploaded_key="k", verified=True)


def test_a_naive_artifact_timestamp_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        Artifact(key="daily/x.dump", size_bytes=1, modified_at=datetime(2026, 9, 3))


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"retention_days": 0}, "retention_days"),
        ({"retention_days": -1}, "retention_days"),
        ({"min_retained": 0}, "min_retained"),
        ({"min_retained": -5}, "min_retained"),
    ],
)
def test_nonsensical_windows_are_rejected(kwargs, match):
    """`--retention-days 0` would expire everything; `--min-retained 0` removes
    the floor. Both are refused here as well as by the CLI's IntRange, because
    the policy must not depend on its only current caller validating for it."""
    with pytest.raises(ValueError, match=match):
        _plan(_daily_series(10), **kwargs)


def test_a_plan_is_immutable():
    """The plan is carried out by a loop that deletes; it must not be editable
    between the decision and the deletion."""
    plan = _plan(_daily_series(10))

    with pytest.raises(AttributeError):
        plan.delete = ("daily/anything.dump",)


def test_defaults_are_the_documented_policy():
    """The runbook and render.yaml quote these numbers; keep them in step."""
    assert DEFAULT_RETENTION_DAYS == 30
    assert DEFAULT_MIN_RETAINED == 7
