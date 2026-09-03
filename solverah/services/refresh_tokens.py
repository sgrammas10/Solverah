"""Refresh-token issue, rotation, reuse detection, revocation, and retention.

This module is audit finding 1.1 (HIGH).  Until S3, `POST /auth/logout` called
`unset_jwt_cookies` and nothing else -- its own docstring admitted that the JWT
"stays valid until it expires" -- so a captured access cookie survived the
victim logging out for the rest of its hour, and no operator action short of
rotating `JWT_SECRET_KEY` fleet-wide revoked it.

The fix is a row.  A JWT is self-validating, which is precisely the property
that makes it unrevocable: the server can accept one without consulting any
state, so there is no state for a logout to change.  An opaque refresh token
means nothing on its own -- what makes it a session is a `user_sessions` row
that has not been retired -- so revoking it is one `UPDATE`.

Four rules, and the order they are checked in is load-bearing.

**Rotation on use.**  Every successful refresh retires the presented token and
mints a new one in the same family.  A refresh token is therefore single-use,
which is what makes the next rule possible at all: without rotation, a stolen
token and the real one are the same token forever and no observation
distinguishes them.

**Reuse detection.**  A token presented *after* it was retired is evidence the
chain leaked, because the legitimate holder rotated past it and would not have
kept a copy.  The response is to revoke the whole family, not the one row: at
that point the attacker's copy and the victim's copy are indistinguishable, and
killing either one alone has a 50% chance of killing the wrong one.  Forcing
both back through the password is the only answer that is right in both cases.

**The grace window, which is what stops the rule above from firing on ordinary
traffic.**  Two tabs -- or two parallel TanStack queries in one tab -- can hit a
401 at the same instant and present the *same* refresh token microseconds apart.
The second one looks exactly like theft.  Without a grace window this design
signs people out at random under concurrency, which is the single most common
way refresh rotation ships broken.  So a token retired *by rotation* within
:data:`GRACE_SECONDS` is not treated as reuse: the caller is told the rotation
already happened, and gets a fresh access token without a second rotation.

  That answer is complete rather than partial, and the reason is the cookie
  jar.  Cookies are per-browser, not per-tab, so the successor the *first*
  request minted is already in the jar by the time anyone reads the second
  response -- the second request needs an access token, not a refresh token,
  and issuing one without rotating is exactly what it needs.  It also means
  this function never has to hand back a raw successor value, which it could
  not do anyway: successors are stored hashed, like every other token here.

  The window is deliberately not "the presented token is the direct parent of a
  live token".  That formulation has no clock in it, so a genuinely stolen
  token replayed a week later would also find a live successor and be waved
  through.  The clock is the whole control.

  **Grace also requires the family to be alive, and that is a second condition
  rather than a detail of the first.**  A token belonging to a revoked family is
  never in grace.  :func:`revoke_family` retires live rows only -- so that an
  ancestor goes on saying it died of rotation, which is true and is what an
  audit needs to read -- which means the presented row cannot tell you whether
  its session is over.  Checking only the row let a *rotated ancestor* of a
  logged-out family through the window and mint a fifteen-minute access token
  after the user logged out, defeating the property this module exists to
  establish.  The fix belongs here, on the read path, and not in
  :func:`revoke_family`: rewriting history on revocation would make every
  ancestor of a stolen chain claim it was stolen, which is a worse answer to a
  different question.

  An ancestor of a dead family is *refused*, not treated as reuse.  Nothing
  live remains to revoke, and the caller is at least as likely to be a tab
  whose refresh was in flight when the logout committed as it is to be a thief.

**Expiry is not reuse.**  A token past `expires_at` is retired as `expired` and
refused, and its family is left alone: an expired token is the system working,
and revoking a family for it would sign a user out of a session they had
already stopped using.

Callable from a worker: nothing here reads `flask.request` or builds a
response.  Cookies, status codes and CSRF live in `solverah/api/v1/auth.py`;
what this module owns is the state machine and the transaction boundary.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Optional

import sqlalchemy as sa

from model import User, UserSession, db
from solverah.domain import auth as domain

__all__ = [
    "GRACE_SECONDS",
    "PURGE_DAYS",
    "REASON_EXPIRED",
    "REASON_LOGGED_OUT",
    "REASON_REUSED",
    "REASON_ROTATED",
    "REFRESH_TOKEN_DAYS",
    "IssuedSession",
    "RefreshOutcome",
    "expire_stale",
    "issue",
    "purge_terminal",
    "revoke_family",
    "rotate",
]

logger = logging.getLogger("solverah.refresh_tokens")

#: How long a refresh token lives.  Part 5.3's number, and the product decision
#: behind it: thirty days is how long someone may be away before signing in
#: again.  The access token is fifteen minutes, so this is the only thing
#: standing between a returning user and the login screen.
REFRESH_TOKEN_DAYS = 30

#: How long after rotation a token may still be presented without that being
#: read as theft.  See the module docstring -- this is the concurrency window,
#: not a grace period on expiry.
#:
#: Thirty seconds rather than two or three.  The window has to cover more than
#: the microseconds between two simultaneous 401s: a phone waking on a slow
#: connection can take double-digit seconds to complete the round trip that set
#: the successor cookie, and any request already in flight when that happened is
#: carrying the old token.  What the window costs is bounded and small -- inside
#: it a leaked token buys an access token but no rotation and no extension of
#: the family's life, and the moment it closes the same token revokes the whole
#: family.  A window measured in seconds cannot be walked into by an attacker
#: who has to steal the token first.
GRACE_SECONDS = 30

#: How long a dead row survives before `flask retention run` deletes it.
#: Part 4.8's "30 days past expiry" for this table, applied to whichever end
#: came first: `retired_at` for a token that died, `expires_at` for one that
#: simply ran out.  The rows are the audit trail -- "this session ended because
#: the user logged out" -- and thirty days is long enough to answer a question
#: about last month's incident, short enough that the trail is not a permanent
#: record of every sign-in anyone has ever made.
PURGE_DAYS = 30

#: The four ways a token dies.  A vocabulary rather than free text, fixed by a
#: check constraint in the migration, because a typo'd reason is an audit row
#: that answers nothing and a query that silently misses it.
REASON_ROTATED = "rotated"
REASON_LOGGED_OUT = "logged_out"
REASON_REUSED = "reused"
REASON_EXPIRED = "expired"

_table = UserSession.__table__


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _aware(value: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
    """Read a database timestamp as UTC-aware.

    The columns are TIMESTAMPTZ and psycopg returns aware values, but a row that
    reached here through SQLite (a developer pointing DATABASE_URL at a file)
    comes back naive, and comparing naive to aware raises rather than answering
    wrongly.  That exact mix is what made the login lockout raise TypeError the
    moment a lockout was actually in force (Phase 2c).
    """
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value


@dataclass(frozen=True)
class IssuedSession:
    """A newly minted session: the raw token, and the family it opened.

    Both halves are needed at the HTTP boundary and neither can be recovered
    from the other afterwards -- the token because only its digest is stored,
    the family because that is what goes into the access token's ``sid`` claim
    so ``POST /auth/logout`` knows what to revoke.
    """

    token: str
    family_id: str


@dataclass(frozen=True)
class RefreshOutcome:
    """What :func:`rotate` decided, in terms the HTTP layer can act on.

    Attributes:
        status: One of ``rotated``, ``grace``, ``reused``, ``revoked``,
            ``expired``, ``unknown``.  ``rotated`` and ``grace`` are the two
            successes and they differ in exactly one way: only ``rotated``
            carries a token to put in a cookie.  The four refusals are separate
            because they mean different things in the log -- on the wire they
            are one uniform 401, which is what stops the response telling a
            caller which one it hit.
        user: The account behind the presented token, when there was one.  Its
            email is the JWT identity and its session family is the ``sid``
            claim, so the API layer needs the row rather than just an id.
        token: The raw successor, present only for ``rotated``.  The only moment
            this value exists outside the caller's cookie.
        family_id: The family the presented token belonged to, for the ``sid``
            claim and for the log line.
    """

    status: str
    user: Optional[User] = None
    token: Optional[str] = None
    family_id: Optional[str] = None

    @property
    def ok(self) -> bool:
        """Whether the caller should be handed a fresh access token."""
        return self.status in ("rotated", "grace")


def issue(user: User) -> IssuedSession:
    """Mint a new session family for *user* and return its token and family id.

    Called on the two paths that establish a session -- password login and OTP
    sign-in.  Registration and email confirmation deliberately do not: neither
    issues an access token either, and a refresh token for a session that was
    never started is a credential nobody asked for.

    Commits, because the row must be durable before the token reaches the
    client.  The other order -- respond, then persist -- has a window in which
    the user holds a token the database has never heard of, and the next thing
    that token does is trip reuse detection against a row that does not exist.

    Returns:
        An :class:`IssuedSession`.  Its ``token`` is the only copy that will
        ever exist outside the caller's cookie; the database gets the digest.
    """
    raw = domain.generate_refresh_token()
    session = UserSession(
        user_id=user.id,
        token_hash=domain.hash_refresh_token(raw),
        expires_at=_utcnow() + datetime.timedelta(days=REFRESH_TOKEN_DAYS),
    )
    db.session.add(session)
    db.session.commit()
    logger.info(
        "refresh_session_issued",
        extra={
            "event": "refresh_session_issued",
            "user_id": user.id,
            "family_id": str(session.family_id),
        },
    )
    return IssuedSession(token=raw, family_id=str(session.family_id))


def _row_for(raw_token: str):
    """The `user_sessions` row a raw token hashes to, or None."""
    if not raw_token:
        return None
    return db.session.execute(
        sa.select(_table).where(
            _table.c.token_hash == domain.hash_refresh_token(raw_token)
        )
    ).one_or_none()


def rotate(raw_token: str) -> RefreshOutcome:
    """Exchange a refresh token for its successor, or refuse and say why.

    The decision order is the module docstring's four rules, and it matters:

    1. No row -> ``unknown``.  Not "reused": there is no family to revoke and
       no evidence of anything except a caller with a value that was never a
       token here.
    2. Already retired -> ``expired`` if that is what it was stamped as, since
       expiry is not theft on the second presentation either; ``grace`` if it
       was retired by *rotation* inside :data:`GRACE_SECONDS` **and** no
       sibling in its family was retired by logout or reuse; ``revoked`` if the
       family is dead, which refuses without revoking anything further;
       otherwise ``reused``, which revokes the family.  No token belonging to a
       revoked family is ever in grace, whenever it is presented: the user said
       the session was over.
    3. Past ``expires_at`` -> ``expired``, stamped as such, family untouched.
    4. Otherwise rotate: claim the row, mint the successor, link the two.

    The claim in step 4 is a conditional ``UPDATE ... WHERE retired_at IS
    NULL``, not a read-then-write.  Two simultaneous requests both pass step 2
    -- neither row is retired yet -- and without the condition both would mint a
    successor, leaving two live tokens in one family and a jar holding whichever
    response landed last.  The loser of the race sees zero rows updated and
    falls back into step 2's logic against the now-retired row, which is exactly
    where it belongs: it is the second half of a stampede, and it gets the grace
    answer.
    """
    row = _row_for(raw_token)
    if row is None:
        logger.info("refresh_token_unknown", extra={"event": "refresh_token_unknown"})
        return RefreshOutcome(status="unknown")

    if db.session.get(User, row.user_id) is None:
        # A session whose account is gone. Very nearly unreachable -- `user_id`
        # cascades, and account *deletion* removes these rows explicitly because
        # it tombstones rather than deletes -- but "very nearly" is not a thing
        # to leave unhandled on the path that mints credentials: without this
        # the successful branch would dereference None and answer 500, on a
        # request an attacker controls the input to. Answered as `unknown`,
        # which is what it is, and the orphan is retired so it stops being
        # presentable at all.
        revoke_family(str(row.family_id), reason=REASON_REUSED)
        logger.warning(
            "refresh_token_orphaned",
            extra={
                "event": "refresh_token_orphaned",
                "family_id": str(row.family_id),
                "user_id": row.user_id,
            },
        )
        return RefreshOutcome(status="unknown")

    outcome = _outcome_for_retired(row)
    if outcome is not None:
        return outcome

    if _aware(row.expires_at) <= _utcnow():
        return _expire(row)

    claimed = db.session.execute(
        sa.update(_table)
        .where(_table.c.id == row.id, _table.c.retired_at.is_(None))
        .values(retired_at=_utcnow(), retired_reason=REASON_ROTATED)
    )
    if not claimed.rowcount:
        # Lost the race with a concurrent refresh. Re-read and answer on the
        # row as it now stands -- which is retired-by-rotation seconds ago, so
        # this is the grace path and not a false theft alarm.
        db.session.rollback()
        reread = _row_for(raw_token)
        if reread is None:  # pragma: no cover - a delete mid-rotation
            return RefreshOutcome(status="unknown")
        return _outcome_for_retired(reread) or RefreshOutcome(status="unknown")

    raw = domain.generate_refresh_token()
    successor_id = db.session.execute(
        sa.insert(_table)
        .values(
            family_id=row.family_id,
            user_id=row.user_id,
            token_hash=domain.hash_refresh_token(raw),
            parent_id=row.id,
            expires_at=_utcnow() + datetime.timedelta(days=REFRESH_TOKEN_DAYS),
        )
        .returning(_table.c.id)
    ).scalar_one()
    db.session.execute(
        sa.update(_table).where(_table.c.id == row.id).values(successor_id=successor_id)
    )
    db.session.commit()

    return RefreshOutcome(
        status="rotated",
        user=db.session.get(User, row.user_id),
        token=raw,
        family_id=str(row.family_id),
    )


def _family_revoked(family_id) -> bool:
    """Whether anything in *family_id* was retired by logout or reuse detection.

    The second half of the grace test, and the reason grace is not decided by
    the presented row alone.  :func:`revoke_family` only touches rows that are
    still live -- deliberately, so an ancestor goes on saying it died of
    rotation, which is true -- so the presented row cannot tell you whether the
    session it belonged to is over.  Only its siblings can.

    ``expired`` is not in the list and must not be: expiry is not revocation,
    and a family whose live tip merely ran out has no ancestor within seconds
    of its rotation anyway.

    One index probe on ``ix_user_sessions_family``, paid only on the grace
    branch -- a row retired by rotation inside :data:`GRACE_SECONDS` -- and
    never on the ordinary rotate path.
    """
    return bool(
        db.session.execute(
            sa.select(
                sa.exists().where(
                    _table.c.family_id == family_id,
                    _table.c.retired_reason.in_((REASON_LOGGED_OUT, REASON_REUSED)),
                )
            )
        ).scalar()
    )


def _refuse_dead_family(row) -> RefreshOutcome:
    """Refuse an ancestor of a family that has already been revoked.

    Refused rather than re-detected as reuse, and the distinction is the point.
    There is nothing left to revoke -- every live row in this family died when
    the family did -- and the caller is at least as likely to be a tab whose
    refresh was in flight when the user logged out as it is to be a thief.
    Writing a second ``refresh_token_reuse`` row would make one incident read as
    two and would put an ordinary logout race in the same column as a theft.

    A WARNING, though, because a token presented after its session was revoked
    is worth seeing; and the same uniform 401 on the wire as every other
    refusal, so the response still tells a caller nothing.
    """
    logger.warning(
        "refresh_token_dead_family",
        extra={
            "event": "refresh_token_dead_family",
            "user_id": row.user_id,
            "family_id": str(row.family_id),
            "retired_reason": row.retired_reason,
        },
    )
    return RefreshOutcome(status="revoked", family_id=str(row.family_id))


def _outcome_for_retired(row) -> Optional[RefreshOutcome]:
    """Answer for an already-retired row, or None if the row is still live."""
    if row.retired_at is None:
        return None

    if row.retired_reason == REASON_EXPIRED:
        # Stamped by `expire_stale` in the retention cron, or by an `_expire` on
        # an earlier presentation of this same token. Either way the answer is
        # the one `_expire` gives, and the row sits in this state for
        # `PURGE_DAYS` -- so falling through to reuse detection here raised a
        # security event for every user coming back after thirty days away.
        logger.info(
            "refresh_token_expired",
            extra={
                "event": "refresh_token_expired",
                "user_id": row.user_id,
                "family_id": str(row.family_id),
            },
        )
        return RefreshOutcome(status="expired", family_id=str(row.family_id))

    within_grace = (
        row.retired_reason == REASON_ROTATED
        and (_utcnow() - _aware(row.retired_at)).total_seconds() <= GRACE_SECONDS
    )
    if within_grace:
        if _family_revoked(row.family_id):
            return _refuse_dead_family(row)
        logger.info(
            "refresh_token_grace",
            extra={
                "event": "refresh_token_grace",
                "user_id": row.user_id,
                "family_id": str(row.family_id),
            },
        )
        return RefreshOutcome(
            status="grace",
            user=db.session.get(User, row.user_id),
            family_id=str(row.family_id),
        )

    return _detect_reuse(row)


def _detect_reuse(row) -> RefreshOutcome:
    """Revoke the family behind a dead token that was presented anyway.

    The security event, and the one place in this module that writes an
    `AuditLog` row: rotation happens every fifteen minutes per signed-in user
    and would drown the table, but this is rare by construction and is the
    record an incident review needs.  Ids only in the metadata -- the same audit
    that raised this finding raised #18 against `event_metadata` holding an
    email address forever.
    """
    from solverah.services import audit

    revoked = revoke_family(str(row.family_id), reason=REASON_REUSED, commit=False)
    audit.log_audit_event(
        "refresh_token_reuse",
        row.user_id,
        "user_session",
        {
            "family_id": str(row.family_id),
            "session_id": row.id,
            "retired_reason": row.retired_reason,
            "revoked_siblings": revoked,
        },
    )
    db.session.commit()

    logger.warning(
        "refresh_token_reuse_detected",
        extra={
            "event": "refresh_token_reuse_detected",
            "user_id": row.user_id,
            "family_id": str(row.family_id),
            "retired_reason": row.retired_reason,
            "revoked_siblings": revoked,
        },
    )
    return RefreshOutcome(status="reused", family_id=str(row.family_id))


def _expire(row) -> RefreshOutcome:
    """Stamp a token that simply ran out, and refuse it without revoking."""
    db.session.execute(
        sa.update(_table)
        .where(_table.c.id == row.id, _table.c.retired_at.is_(None))
        .values(retired_at=_utcnow(), retired_reason=REASON_EXPIRED)
    )
    db.session.commit()
    logger.info(
        "refresh_token_expired",
        extra={
            "event": "refresh_token_expired",
            "user_id": row.user_id,
            "family_id": str(row.family_id),
        },
    )
    return RefreshOutcome(status="expired", family_id=str(row.family_id))


def revoke_family(family_id: str, *, reason: str, commit: bool = True) -> int:
    """Retire every live token in *family_id*.  Returns how many died.

    Idempotent, and that is what makes it safe on the logout path: a second
    logout, or a logout racing a refresh, updates zero rows and reports zero
    rather than failing.

    Already-retired rows keep the reason they died of.  A family revoked for
    reuse therefore reads as the truth -- the ancestors say `rotated`, because
    they did rotate, and the live descendant says `reused` -- rather than
    rewriting history to make the whole chain look stolen.

    Args:
        family_id: The family to end.
        reason: One of the module's four reasons.
        commit: False when the caller is already inside a transaction it will
            commit itself, which is how reuse detection lands the revocation
            and its audit row together.
    """
    result = db.session.execute(
        sa.update(_table)
        .where(
            _table.c.family_id == family_id,
            _table.c.retired_at.is_(None),
        )
        .values(retired_at=_utcnow(), retired_reason=reason)
    )
    if commit:
        db.session.commit()
    revoked = result.rowcount or 0
    if revoked:
        logger.info(
            "refresh_family_revoked",
            extra={
                "event": "refresh_family_revoked",
                "family_id": str(family_id),
                "reason": reason,
                "revoked": revoked,
            },
        )
    return revoked


def expire_stale() -> int:
    """Stamp `expired` on live rows whose `expires_at` has passed.

    Without this, "live" means two different things: `retired_at IS NULL` in
    every query, and `retired_at IS NULL AND expires_at > now()` in the one
    place that actually decides.  :func:`rotate` closes the gap for a token
    somebody presents; this closes it for the ones nobody ever comes back for,
    which is most of them.

    **`retired_at` is set to `expires_at`, not to `now()`,** and that is not a
    cosmetic choice.  The row died when the token stopped being usable, which is
    its expiry -- not the moment a cron job happened to notice.  Stamping the
    clock time instead would restart the retention window on every row this
    touches, so a token that expired thirteen months ago would survive another
    thirty days from the day it was first swept, and a fleet of them would
    survive thirty days from whenever the sweep was first deployed.  Retention
    that resets itself when you look at it is not retention.

    Runs in `flask retention run`, immediately before :func:`purge_terminal`.
    A row whose window has already passed is therefore stamped and deleted in
    the same pass, which is correct: the window is measured from the death, and
    the death was thirty days ago.
    """
    with db.engine.begin() as connection:
        result = connection.execute(
            sa.update(_table)
            .where(
                _table.c.retired_at.is_(None),
                _table.c.expires_at < _utcnow(),
            )
            .values(retired_at=_table.c.expires_at, retired_reason=REASON_EXPIRED)
        )
    expired = result.rowcount or 0
    if expired:
        logger.info(
            "refresh_sessions_expired",
            extra={"event": "refresh_sessions_expired", "count": expired},
        )
    return expired


def purge_terminal(older_than_days: int = PURGE_DAYS) -> int:
    """Delete dead session rows past their retention window.

    Two conditions, ORed, and neither is redundant:

    * `retired_at < cutoff` -- a token that died, whatever killed it.  This is
      the ordinary case, because :func:`expire_stale` runs first in the same
      pass and stamps the ones that merely ran out.
    * `expires_at < cutoff AND retired_at IS NULL` -- a row that outlived its
      expiry without ever being stamped.  It exists whenever a retention pass
      was missed, and dropping this half would mean one skipped cron run leaves
      rows that no later run ever reaches.

    A live row is never touched: not retired, not past expiry, and therefore
    somebody's current session.  Deleting one would sign a user out with no
    event anywhere saying why.
    """
    cutoff = _utcnow() - datetime.timedelta(days=older_than_days)
    with db.engine.begin() as connection:
        result = connection.execute(
            sa.delete(_table).where(
                sa.or_(
                    _table.c.retired_at < cutoff,
                    sa.and_(
                        _table.c.retired_at.is_(None),
                        _table.c.expires_at < cutoff,
                    ),
                )
            )
        )
    purged = result.rowcount or 0
    if purged:
        logger.info(
            "refresh_sessions_purged",
            extra={"event": "refresh_sessions_purged", "count": purged},
        )
    return purged
