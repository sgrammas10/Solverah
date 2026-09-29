"""Queries against ``path_fits`` -- the stored Tier-2 deep fits (BUILD_PLAN F-5).

``path_cache`` is the Tier-1 equivalent and the model for the invalidation
discipline here, but the two are deliberately different things:

               path_cache                 path_fits
    where      in-process dict            a table
    lifetime   per worker, lost on deploy durable
    keyed by   user_id                    (user_id, onet_code)
    bounded    500 MRU entries            by the profile, and by MAX_AGE

A Tier-2 fit is worth a table where a Tier-1 shortlist is not, because it costs
four provider calls *per occupation* and a user clicking back and forth between
two cards should pay for neither twice -- including after a deploy, and
including on whichever gunicorn worker they land on.  ``path_cache``'s own
docstring names both of those as the problems it still has.

**Staleness is answered twice, and the second answer is what makes the first
safe.**  :func:`invalidate` is called from every write that changes a scoring
input -- the same enumeration ``path_cache.invalidate`` has, tested in
``tests/test_path_preferences_api.py``.  That enumeration can be missed, and
missing it fails silently by serving a stale answer.  So every stored row also
carries the :func:`fingerprint` of the profile it was computed from, and
:func:`read` refuses a row whose fingerprint has moved.  The enumeration is the
fast path; the fingerprint is the correctness.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from model import PathFit, db

__all__ = [
    "MAX_AGE",
    "delete_for_user",
    "fingerprint",
    "invalidate",
    "purge_older_than",
    "read",
    "store",
]

#: How long a fit stays usable regardless of the profile.
#:
#: The third input to a deep fit is O*NET's own content -- rated skills, hot
#: technologies, work activities, tasks -- and **no profile write invalidates
#: it**.  It changes quarterly, so nothing bounds a stored row's age without a
#: TTL.  ``path_cache`` argues against TTLs, correctly, on the grounds that they
#: add "a second, weaker correctness mechanism next to a working one"; for this
#: input there is no working one to sit next to.  Thirty days re-derives a fit
#: roughly three times per O*NET release, which costs four cached calls.
MAX_AGE = datetime.timedelta(days=30)


def fingerprint(user_profile) -> str:
    """A digest of exactly the ``UserProfile`` fields a deep fit reads.

    Not a hash of the whole profile document: a user editing their phone number
    must not throw away every fit they have looked at.  The fields below are the
    ones ``path_deep_fit.deep_fit`` and the ``path_scoring`` helpers it calls
    actually read, so a change to any of them changes the answer and a change to
    anything else does not.

    ``archetype_description`` is deliberately absent (F-8 follow-up). F-8 box 8
    (02dd338) changed ``_build_behavioral_profile`` to compose the behavioural
    document from the structured fields below instead and stop embedding that
    LLM-written prose, and nothing in ``path_deep_fit.deep_fit`` or the
    ``path_scoring`` helpers it calls has read the field since. Hashing it anyway
    cost nothing incorrect -- a fit was never served stale -- but it invalidated
    every stored fit whenever the description happened to be regenerated with
    nothing the analysis reads having changed, which is waste with no correctness
    behind it. Dropping it changes every stored fingerprint once; there is
    nothing stored in production to invalidate, because the feature is not yet
    deployed.

    Skills are sorted before hashing -- the profile document's list order is not
    meaningful and reordering it is not a change -- and the digest is over
    canonical JSON so key order cannot make two equal profiles differ.
    """
    payload = {
        "current_title": user_profile.current_title,
        "career_status": user_profile.career_status,
        "skills": sorted((s.name, s.level) for s in user_profile.skills),
        "archetype": user_profile.archetype,
        "focus_type": user_profile.focus_type,
        "manager_match": user_profile.manager_match,
        "work_style_tags": sorted(user_profile.work_style_tags or []),
        "move_intent": user_profile.move_intent,
        "seniority_intent": user_profile.seniority_intent,
        "priority": user_profile.priority,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def read(user_id: int, onet_code: str, expected_fingerprint: str) -> Optional[Dict[str, Any]]:
    """The stored payload for this pair, or ``None`` when there is none or it is stale.

    Stale means either digest: the profile moved, or the row is older than
    :data:`MAX_AGE`.  A stale row is left in place rather than deleted here --
    the caller is about to overwrite it through :func:`store`, and deleting on a
    *read* would make a read a write, which is the P0-3 shape Phase 3 spent a
    chunk removing from ``path_suggestions``.
    """
    row = PathFit.query.filter_by(user_id=user_id, onet_code=onet_code).first()
    if row is None:
        return None
    if row.profile_fingerprint != expected_fingerprint:
        return None
    if _age(row) > MAX_AGE:
        return None
    return row.payload


def store(
    user_id: int, onet_code: str, payload: Dict[str, Any], profile_fingerprint: str
) -> None:
    """Write the fit for this pair, replacing any earlier one.

    Does not commit -- the service owns the transaction boundary (see this
    package's docstring).  One ``INSERT ... ON CONFLICT (user_id, onet_code) DO
    UPDATE`` with no read first, so :func:`read`'s SELECT is the only one on the
    miss path, and two first-time fits of one card converge on one row instead
    of the second failing on the unique constraint after its four provider
    calls.  An update keeps the row's ``id``.

    The row comes back through ``RETURNING`` with ``populate_existing``, so a
    copy :func:`read` already loaded into this session is refreshed rather than
    left holding the fit this call replaced.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    statement = pg_insert(PathFit).values(
        user_id=user_id,
        onet_code=onet_code,
        payload=payload,
        profile_fingerprint=profile_fingerprint,
        computed_at=now,
    )
    statement = statement.on_conflict_do_update(
        index_elements=["user_id", "onet_code"],
        set_={
            "payload": statement.excluded.payload,
            "profile_fingerprint": statement.excluded.profile_fingerprint,
            "computed_at": statement.excluded.computed_at,
        },
    )
    db.session.scalars(
        statement.returning(PathFit), execution_options={"populate_existing": True}
    ).one()


def invalidate(user_id: int) -> None:
    """Drop every stored fit for *user_id*.

    The ``path_cache.invalidate`` counterpart, called from the same write sites
    and enumerated in the same test.  Does not commit: every one of those sites
    already commits the write that made the fits stale, and folding the delete
    into that transaction is what stops a crash between the two from leaving a
    changed profile beside fits computed from the old one.
    """
    PathFit.query.filter_by(user_id=user_id).delete()


def delete_for_user(user_id: int) -> None:
    """Destroy this user's fits on account deletion (D-7b).

    Separate from :func:`invalidate` despite the identical statement, because
    the two mean different things and only one of them may ever grow a
    "keep the row, clear the payload" variant: invalidation is a cache miss,
    deletion is a promise.  ``payload.matched_skills`` is the user's own typed
    skill names, and free text is never retained de-identified.
    """
    PathFit.query.filter_by(user_id=user_id).delete()


def purge_older_than(max_age: datetime.timedelta = MAX_AGE) -> int:
    """Delete fits computed more than *max_age* ago, for every user.  Returns the count.

    The other half of :func:`read`'s age rule: a row past :data:`MAX_AGE` is
    never served, only overwritten if its user comes back to that card, so one
    whose user never does is retention with no reader -- and
    ``payload.matched_skills`` is the user's own typed skill names.  Run from
    ``flask retention run`` (W-19).  Does not commit -- the command owns the
    transaction.
    """
    cutoff = datetime.datetime.now(datetime.timezone.utc) - max_age
    table = PathFit.__table__
    result = db.session.execute(sa.delete(table).where(table.c.computed_at < cutoff))
    return result.rowcount or 0


def list_for_user(user_id: int) -> List[PathFit]:
    """Every stored fit for *user_id*, newest first.  For tests and diagnostics."""
    return (
        PathFit.query.filter_by(user_id=user_id)
        .order_by(PathFit.computed_at.desc())
        .all()
    )


def _age(row: PathFit) -> datetime.timedelta:
    """How old *row* is, tolerating a naive ``computed_at``.

    The column is ``timestamptz`` and Postgres hands back an aware datetime, but
    a row written and read back inside one session without a flush can still
    carry whatever the caller set.  Comparing an aware and a naive datetime
    raises, and a fit that raises on read is worse than one that is treated as
    fresh, so the naive case is assumed UTC rather than rejected.
    """
    computed = row.computed_at
    if computed is None:
        return datetime.timedelta(0)
    if computed.tzinfo is None:
        computed = computed.replace(tzinfo=datetime.timezone.utc)
    return datetime.datetime.now(datetime.timezone.utc) - computed
