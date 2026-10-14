"""Queries against ``assessment_forms`` and ``assessment_submissions``.

Phase 2d ended the four-storage-locations arrangement this module used to
document.  Work Pulse lived in ``user_intake.wpl_*``, the Lite-Lite session in
``user_intake.wpll_*``, FocusType and ManagerMatch in two keys inside the profile
document, and the core assessment in its own two tables.  Four places, five
products, and ``GET /assessments`` reading three of them to answer one question.

All five now write one shape.  What did **not** move is the core assessment's
answers and dimension scores.  They stay in the two person-side tables, still
reachable only through ``assessment_store``, and this module does not name,
import or query them -- the sentence you are reading avoids naming them too,
because ``tests/test_employer_visibility.py`` scans for the names in string
literals as well as in code, and prose that names them is prose that would have
to be allowlisted.

Unifying where a *submission* is recorded was not licence to widen what a
submission exposes.  That is why a ``core`` row here carries a null ``result``
and null ``answers`` under a check constraint rather than under a convention, and
why the core submission row is written by ``assessment_store`` rather than by
this module: that write belongs inside the doorway, in the same transaction as
the raw rows it identifies.

``user_intake`` is gone from this module entirely.  The row still exists and
still holds ``selected_statement_ids``, which is intake data and not an
assessment; ``intake_repository`` owns it.  The ``wpl_*`` and ``wpll_*`` columns
beside it are no longer read by anything and are dropped in the next release --
the same one-release stay ``users.profile_data`` is serving.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence

import sqlalchemy as sa
from sqlalchemy.orm import load_only

from model import AssessmentForm, AssessmentSubmission, db

__all__ = [
    "completed_kinds",
    "current_result",
    "current_submission",
    "current_submissions",
    "delete_for_user",
    "open_current",
]

#: Kinds whose current sitting is one row, updated in place on a retake. ``core``
#: is the exception and appends -- see ``AssessmentSubmission``'s docstring for
#: why the schema draws that line rather than a comment.
_SINGLE_ROW_KINDS = ("work_pulse", "wpll", "focus_type", "manager_match")

#: What "current" means, as an ORDER BY within one kind: the most recently
#: completed sitting, an unfinished one after every finished one, and the newest
#: row among ties. One definition, because three readers below apply it.
_CURRENT_ORDER = (
    AssessmentSubmission.completed_at.desc().nullslast(),
    AssessmentSubmission.id.desc(),
)

#: The columns :func:`current_result` loads: every one a result reader branches
#: on or returns -- ``result``; ``completed_at``, which splits Work Pulse's "not
#: taken" 404 from its "complete but not scored" 422; and ``answers``, which
#: ManagerMatch's precondition diffs a manager profile against -- plus the row's
#: identity and status. Not ``narrative``: the one large column none of them
#: reads, and for both instruments that have one, a copy of
#: ``result["narrative"]``.
_RESULT_COLUMNS = (
    AssessmentSubmission.public_id,
    AssessmentSubmission.user_id,
    AssessmentSubmission.kind,
    AssessmentSubmission.form_version,
    AssessmentSubmission.status,
    AssessmentSubmission.result,
    AssessmentSubmission.answers,
    AssessmentSubmission.started_at,
    AssessmentSubmission.completed_at,
    AssessmentSubmission.scored_at,
)


def current_submission(user_id: int, kind: str) -> Optional[AssessmentSubmission]:
    """This user's current sitting of *kind*, or None.

    For the four single-row kinds the partial unique index makes "current"
    unambiguous. ``core`` appends, so the most recently completed row is the
    current one -- and nothing reads a core row through here today, because
    everything a caller wants from a core sitting is behind ``assessment_store``.
    """
    return (
        db.session.execute(
            sa.select(AssessmentSubmission)
            .where(
                AssessmentSubmission.user_id == user_id,
                AssessmentSubmission.kind == kind,
            )
            .order_by(*_CURRENT_ORDER)
            .limit(1)
        )
        .scalars()
        .first()
    )


def current_submissions(
    user_id: int, kinds: Sequence[str]
) -> Dict[str, AssessmentSubmission]:
    """This user's current sitting of each of *kinds*, in one query.

    ``{kind: submission}``, holding for each kind the row
    :func:`current_submission` would return, and no entry for a kind the user
    has never sat. ``DISTINCT ON (kind)`` keeps the first row of each kind under
    the same ``_CURRENT_ORDER``, so the two cannot disagree about which row is
    current. Sends nothing at all for an empty *kinds*.
    """
    wanted = list(dict.fromkeys(kinds))
    if not wanted:
        return {}
    rows = db.session.execute(
        sa.select(AssessmentSubmission)
        .where(
            AssessmentSubmission.user_id == user_id,
            AssessmentSubmission.kind.in_(wanted),
        )
        .order_by(AssessmentSubmission.kind, *_CURRENT_ORDER)
        .distinct(AssessmentSubmission.kind)
    ).scalars()
    return {row.kind: row for row in rows}


def current_result(user_id: int, kind: str) -> Optional[AssessmentSubmission]:
    """:func:`current_submission` for a caller that reads the result, not the prose.

    The same row by the same rule, loaded with ``_RESULT_COLUMNS`` only. It is an
    ordinary instance in the session: touching ``narrative`` lazy-loads it (one
    more query rather than an error), and a later full read of the same row
    fills it in.
    """
    return (
        db.session.execute(
            sa.select(AssessmentSubmission)
            .options(load_only(*_RESULT_COLUMNS))
            .where(
                AssessmentSubmission.user_id == user_id,
                AssessmentSubmission.kind == kind,
            )
            .order_by(*_CURRENT_ORDER)
            .limit(1)
        )
        .scalars()
        .first()
    )


def open_current(user_id: int, kind: str, form_version: str) -> AssessmentSubmission:
    """Return the row a submission of *kind* should be written to, creating it.

    The caller sets the fields and owns the commit. That is deliberate rather
    than lazy: the four instruments genuinely disagree about what a resubmission
    means -- Work Pulse refreshes its completion timestamp, the claimed WPLL
    session must not -- and a repository that took every field as a keyword
    argument would have to grow a flag per disagreement. Setting two attributes
    at the call site keeps each instrument's rule where someone reading that
    instrument will find it.

    Flushes immediately after the INSERT so a concurrent duplicate raises
    ``IntegrityError`` here rather than at the caller's commit. On that collision
    the other request's row is re-read and used. Callers that score or narrate
    (Work Pulse's LLM call) do that work first and open the row only once the
    reply is in, so no flushed INSERT is held across a provider round trip and
    the collision, if any, is resolved at write time. This is the same shape
    ``get_or_create_user_intake`` had, and it is now enforced by
    ``uq_assessment_submissions_current`` rather than by ``user_intake``'s
    one-row-per-user constraint.

    **The insert runs inside a SAVEPOINT, and that is not decoration.**
    ``get_or_create_user_intake`` recovered from the collision with a plain
    ``db.session.rollback()``, which was safe only because it happened to be the
    first write in its transaction. This function is not: ``save_to_account``
    writes the statement selections to ``user_intake`` and *then* opens the WPLL
    submission, so a bare rollback on the losing request would silently discard
    the selections the same request had just made, and go on to commit the
    submission without them. ``begin_nested`` unwinds the failed INSERT and
    nothing else, which makes the recovery correct regardless of what the caller
    wrote first -- a property worth having in the repository rather than as an
    ordering rule every caller has to know.

    Raises:
        ValueError: If *kind* appends rather than having a current row. A
            ``core`` sitting is written by ``assessment_store``, inside the same
            transaction as the raw responses it identifies.
    """
    from sqlalchemy.exc import IntegrityError

    if kind not in _SINGLE_ROW_KINDS:
        raise ValueError(
            "%r has no single current submission; core sittings are append-only" % kind
        )

    AssessmentForm.register(kind, form_version)

    existing = current_submission(user_id, kind)
    if existing is not None:
        # A retake under a newer form version is still the current sitting; the
        # row moves to the new version rather than a second row appearing beside
        # it under the old one.
        existing.form_version = form_version
        return existing

    row = AssessmentSubmission(
        user_id=user_id,
        kind=kind,
        form_version=form_version,
        status="in_progress",
    )
    try:
        with db.session.begin_nested():
            db.session.add(row)
    except IntegrityError:
        row = current_submission(user_id, kind)
        row.form_version = form_version
    return row


def completed_kinds(user_id: int) -> set:
    """Every non-core kind this user has completed, in one query.

    The catalogue used to work this out from three unrelated places. It is one
    round trip now, which is the point of the unification and the only place in
    this phase where a read got cheaper rather than merely tidier.
    """
    rows = db.session.execute(
        sa.select(AssessmentSubmission.kind)
        .where(
            AssessmentSubmission.user_id == user_id,
            AssessmentSubmission.completed_at.isnot(None),
            AssessmentSubmission.kind != "core",
        )
        .distinct()
    ).scalars()
    return set(rows)


def delete_for_user(user_id: int) -> None:
    """Destroy every submission held for this user. Does not commit.

    Called from the account-deletion path. The rows hold narratives, archetypes
    and raw answers, so they are in the "must be destroyed" class rather than the
    "survives scrubbed" one -- unlike the person-side research rows, whose
    survival de-identified is a decided reconciliation
    (``tests/test_account_lifecycle.py``).

    An explicit delete rather than a reliance on ``ON DELETE CASCADE``: deletion
    tombstones the user row instead of removing it, so the cascade never fires.
    """
    db.session.execute(
        sa.delete(AssessmentSubmission).where(AssessmentSubmission.user_id == user_id)
    )
