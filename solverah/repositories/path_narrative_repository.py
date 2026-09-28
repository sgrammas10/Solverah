"""Queries against ``path_narratives`` -- the narrator's sentences, stored (W-16).

``path_fit_repository`` is the model, and the table beside it:

               path_cache reserve         path_fits              path_narratives
    where      in-process dict            a table                a table
    lifetime   per worker, lost on deploy durable                durable
    keyed by   user_id                    (user_id, onet_code)   (user_id, onet_code,
                                                                   fingerprint)
    stale by   invalidate()               fingerprint + MAX_AGE  fingerprint + MAX_AGE

**The fingerprint is the whole staleness story here.**  ``path_fits`` carries a
fingerprint as the belt behind an explicit ``invalidate`` enumeration; this table
has no ``invalidate`` at all, on purpose.  Its reason to exist is that the
writes which DO invalidate the shortlist -- a wants save, above all -- do not
change a single narrator input, so dropping the sentences there would throw away
exactly what W-16 set out to keep.  A write that does change an input changes
the fingerprint (``path_narrative.narrative_fingerprint``), and the old row is
simply never asked for again.

**What goes in is already clean.**  Rows are written only from the narration
phase in ``intelligence_service``, after W-13's grade scrub has run inside the
narrator, and never for a card whose sentence is the house fallback
(``PathSuggestion.is_fallback``).  Nothing here re-checks either rule; the
repository stores what it is given.

Repositories never commit (see this package's docstring); the service does.
"""

from __future__ import annotations

import datetime
from typing import Dict, List, Mapping, Tuple

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from model import PathNarrative, db

__all__ = [
    "MAX_AGE",
    "delete_for_user",
    "list_for_user",
    "purge_older_than",
    "read_many",
    "store_many",
]

#: How long a stored sentence stays usable regardless of its fingerprint.
#:
#: ``path_fit_repository.MAX_AGE``'s thirty days, for its reason: two inputs no
#: profile write reaches still move under a stored row -- O*NET's titles (the
#: corpus is rebuilt quarterly) and the model behind ``OPENAI_NARRATIVE_MODEL``.
#: Past this a row is treated as absent on read and removed by
#: :func:`purge_older_than`.
MAX_AGE = datetime.timedelta(days=30)

_table = PathNarrative.__table__


def read_many(
    user_id: int, fingerprints: Mapping[str, str]
) -> Dict[str, Dict[str, object]]:
    """``{onet_code: {"why_text", "profile_dimensions"}}`` for every hit.

    *fingerprints* is ``{onet_code: fingerprint}`` for the cards being asked
    about.  One query for all of them.  A code whose row carries a different
    fingerprint, or whose row is older than :data:`MAX_AGE`, is a miss -- and is
    left in place rather than deleted, because a read that deletes is a write
    (P0-3), and the purge exists for that.
    """
    if not fingerprints:
        return {}
    cutoff = datetime.datetime.now(datetime.timezone.utc) - MAX_AGE
    pairs = [(code, fp) for code, fp in fingerprints.items()]
    rows = db.session.execute(
        sa.select(
            _table.c.onet_code,
            _table.c.fingerprint,
            _table.c.why_text,
            _table.c.profile_dimensions,
        ).where(
            _table.c.user_id == user_id,
            sa.tuple_(_table.c.onet_code, _table.c.fingerprint).in_(pairs),
            _table.c.created_at >= cutoff,
        )
    ).all()
    return {
        row.onet_code: {
            "why_text": row.why_text,
            "profile_dimensions": list(row.profile_dimensions or []),
        }
        for row in rows
        if fingerprints.get(row.onet_code) == row.fingerprint
    }


def store_many(
    user_id: int, narratives: Mapping[str, Tuple[str, str, List[str]]]
) -> None:
    """Upsert ``{onet_code: (fingerprint, why_text, profile_dimensions)}``.

    ``ON CONFLICT DO UPDATE`` on the unique key, so two narrations of one user
    that overlap (a reload while the first is still writing) converge on one row
    per key instead of one of them failing on the constraint.  ``created_at`` is
    refreshed on conflict: the row was just re-derived, and the age rule is about
    how long ago the sentence was written.

    Does not commit.
    """
    if not narratives:
        return
    values = [
        {
            "user_id": user_id,
            "onet_code": code,
            "fingerprint": fingerprint,
            "why_text": why_text,
            "profile_dimensions": list(dims or []),
        }
        for code, (fingerprint, why_text, dims) in narratives.items()
    ]
    statement = pg_insert(_table).values(values)
    statement = statement.on_conflict_do_update(
        constraint="uq_path_narratives_user_code_fp",
        set_={
            "why_text": statement.excluded.why_text,
            "profile_dimensions": statement.excluded.profile_dimensions,
            "created_at": sa.func.now(),
        },
    )
    db.session.execute(statement)


def delete_for_user(user_id: int) -> None:
    """Destroy every stored sentence for *user_id* on account deletion (D-7b).

    ``why_text`` is prose about the person, and free text about a person is
    never retained de-identified.  Does not commit.
    """
    PathNarrative.query.filter_by(user_id=user_id).delete()


def purge_older_than(max_age: datetime.timedelta = MAX_AGE) -> int:
    """Delete rows past *max_age* for every user.  Returns how many went.

    The other half of the read rule in :func:`read_many`: a row that no read
    will serve is retention with no reader.  Does not commit -- the sweep that
    calls it owns the transaction, as every other caller of a repository does.
    """
    cutoff = datetime.datetime.now(datetime.timezone.utc) - max_age
    result = db.session.execute(sa.delete(_table).where(_table.c.created_at < cutoff))
    return result.rowcount or 0


def list_for_user(user_id: int) -> List[PathNarrative]:
    """Every stored sentence for *user_id*, newest first.  Tests and diagnostics."""
    return (
        PathNarrative.query.filter_by(user_id=user_id)
        .order_by(PathNarrative.created_at.desc(), PathNarrative.id.desc())
        .all()
    )
