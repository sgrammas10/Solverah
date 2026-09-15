"""Which backup artifacts may be deleted -- decided as a pure function.

This is the only code in the system that decides to destroy a backup, so it is
deliberately the code with the fewest dependencies: no boto3, no database, no
clock of its own.  Everything it needs is an argument, which is what makes the
policy exhaustively testable (tests/test_backup_retention.py) rather than
reachable only through a command that has already dumped a database.

**The policy.** Keep dailies for 30 days; delete artifacts older than that.
That is the whole retention rule, and it is the least interesting half of this
module.  The interesting half is the three refusals, each of which exists
because the failure it prevents is unrecoverable:

1. **Never delete the newest artifact.**  A retention window and a broken cron
   are indistinguishable from inside this function: if nothing has uploaded for
   40 days, every artifact is "expired" and the honest reading of the rule
   would empty the bucket -- deleting the last copy of the database precisely
   when the thing that produces copies is broken.
2. **Delete nothing unless the just-uploaded dump verified.**  Pruning is only
   safe as "make room now that a good backup exists".  The caller already exits
   non-zero on a failed verification and never reaches here, so this parameter
   is a second lock on the same door: a future caller that forgets the ordering
   gets a refusal instead of a bucket with 29 good dumps and one truncated one.
3. **Refuse entirely below the floor.**  If applying the window would leave
   fewer than ``min_retained`` artifacts, nothing is deleted at all -- not
   "delete as many as the floor allows".  Landing under the floor means
   something upstream is wrong (a fresh bucket, a changed prefix, a cron that
   has not run in weeks), and none of those are situations to start deleting in.
   A first-week deployment therefore prunes nothing, which is correct and is
   *not* an error: the caller reports the refusal and exits 0.

A refusal is all-or-nothing on purpose.  Partial application of a policy whose
inputs are suspect is how a safety rail becomes a slower version of the
accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional, Tuple

__all__ = [
    "Artifact",
    "DEFAULT_MIN_RETAINED",
    "DEFAULT_RETENTION_DAYS",
    "PrunePlan",
    "plan_prune",
]

#: Keep dailies for 30 days.
DEFAULT_RETENTION_DAYS = 30

#: Never let the retention window take the artifact count below this.  Seven is
#: a week of dailies: enough that a corruption discovered a few days late still
#: has a pre-corruption copy behind it, and low enough that a healthy 30-day
#: bucket (30-31 artifacts) is never near it.
DEFAULT_MIN_RETAINED = 7


@dataclass(frozen=True)
class Artifact:
    """One stored backup, as the object store reports it.

    ``modified_at`` must be timezone-aware; a naive datetime here would compare
    against ``now`` by accident of the local timezone, which for a rule that
    deletes things is not a mistake worth being permissive about.
    """

    key: str
    size_bytes: int
    modified_at: datetime

    def __post_init__(self) -> None:
        if self.modified_at.tzinfo is None:
            raise ValueError("Artifact.modified_at must be timezone-aware: %r" % self.key)


@dataclass(frozen=True)
class PrunePlan:
    """What would be deleted, what survives, and why nothing was deleted.

    ``refusal`` being set always means ``delete`` is empty -- the two are never
    both meaningful -- and it is a *reason string*, not an error: the caller
    prints it and exits 0.
    """

    delete: Tuple[str, ...]
    retained: Tuple[Artifact, ...]
    refusal: Optional[str] = None

    @property
    def retained_bytes(self) -> int:
        return sum(a.size_bytes for a in self.retained)

    @property
    def retained_files(self) -> int:
        return len(self.retained)


def plan_prune(
    artifacts: Iterable[Artifact],
    *,
    now: datetime,
    uploaded_key: str,
    verified: bool,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    min_retained: int = DEFAULT_MIN_RETAINED,
) -> PrunePlan:
    """Decide which of *artifacts* the retention policy may delete.

    Args:
        artifacts: Every artifact currently under the backup prefix, including
            the one just uploaded.
        now: The moment ages are measured from; timezone-aware.
        uploaded_key: Key of the dump this pass just uploaded.  It must appear
            in *artifacts* -- if the listing that prune acts on does not contain
            the object that was just written to it, the listing is describing
            something other than what the upload wrote (wrong prefix, wrong
            bucket, a store that lied about success) and no deletion decision
            based on it can be trusted.
        verified: Whether that dump passed ``pg_restore --list``.
        retention_days: Age, in days, past which an artifact may be deleted.
        min_retained: Floor on the surviving artifact count.

    Returns:
        A :class:`PrunePlan`.  ``retained`` is what would remain after the plan
        is applied -- so on a refusal it is everything, which is what makes the
        reported retained-bytes number honest either way.

    Raises:
        ValueError: If *now* is naive, or the windows are not positive.  These
            are programming errors, not operational ones.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if retention_days < 1:
        raise ValueError("retention_days must be >= 1, got %d" % retention_days)
    if min_retained < 1:
        raise ValueError("min_retained must be >= 1, got %d" % min_retained)

    ordered = _newest_first(artifacts)

    if not verified:
        return PrunePlan(
            delete=(),
            retained=ordered,
            refusal=(
                "the dump uploaded in this pass did not verify, so nothing was "
                "pruned: old backups are only expendable once a good new one exists"
            ),
        )

    if uploaded_key not in {a.key for a in ordered}:
        return PrunePlan(
            delete=(),
            retained=ordered,
            refusal=(
                "the listing does not contain the artifact just uploaded (%s), so it "
                "is not a listing of the backups this pass wrote; nothing was pruned"
                % uploaded_key
            ),
        )

    cutoff = now - timedelta(days=retention_days)
    newest = ordered[0]
    expired = tuple(a for a in ordered if a.modified_at < cutoff and a.key != newest.key)

    if not expired:
        return PrunePlan(delete=(), retained=ordered)

    doomed = {a.key for a in expired}
    survivors = tuple(a for a in ordered if a.key not in doomed)
    if len(survivors) < min_retained:
        return PrunePlan(
            delete=(),
            retained=ordered,
            refusal=(
                "pruning %d of %d artifacts would leave %d, below the floor of %d; "
                "nothing was pruned -- a bucket this thin means the cron, the prefix "
                "or the bucket is wrong, not that the backups are expendable"
                % (len(expired), len(ordered), len(survivors), min_retained)
            ),
        )

    return PrunePlan(delete=tuple(a.key for a in expired), retained=survivors)


def _newest_first(artifacts: Iterable[Artifact]) -> Tuple[Artifact, ...]:
    """Sort newest first, breaking ties on the key.

    The tie-break is not cosmetic: "the newest artifact" has to name exactly one
    object even when two share a timestamp (an object store's granularity, or
    two passes in one second), or the rule protecting it protects whichever one
    the sort happened to put first.
    """
    return tuple(sorted(artifacts, key=lambda a: (a.modified_at, a.key), reverse=True))
