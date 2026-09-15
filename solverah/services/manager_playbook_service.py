"""Manager Decoder storage + playbook assembly (BUILD_PLAN C-3).

⚑4: `manager_profiles` is the one shared store the Decoder's playbook and the Situation
Report's manager section both read -- see `model.ManagerProfile`'s docstring. This module
owns writing to it and assembling the playbook `manager_match.decoder` computes; it does
not own the instrument (C-1, `manager_match/manager_profile.py`) or the diff/content
(C-2, `manager_match/decoder.py`).

Deterministic and instant, like `focus_type` and unlike `manager_match`: there is no
provider call on this path, so both operations below are synchronous -- no job, no
polling, matching the two rules-scored instruments rather than the three provider-scored
ones (`solverah/api/v1/assessments.py`'s `_sync_kind_or_410`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from model import User, db
from solverah.errors import ConflictError
from solverah.repositories import assessment_repository

__all__ = [
    "ManagerPlaybookResult",
    "get_manager_playbook",
    "submit_manager_profile",
]


@dataclass
class ManagerPlaybookResult:
    """A service outcome the API layer turns into a response."""

    status: int
    body: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status < 400


def _error(status: int, message: str) -> ManagerPlaybookResult:
    return ManagerPlaybookResult(status=status, body={"error": message})


def _require_manager_match(user_id: int):
    """This user's completed ManagerMatch sitting, or a distinguishable 409.

    Raised rather than returned: a service may raise a `solverah.errors` type exactly as
    it may return a Result (`solverah/services/__init__.py`), and both the submit route
    and the playbook read need this same precondition -- the Decoder has nothing to diff
    a manager profile against without it.
    """
    submission = assessment_repository.current_submission(user_id, "manager_match")
    if submission is None or submission.answers is None:
        raise ConflictError(
            detail=(
                "Take ManagerMatch first -- the Decoder diffs your manager profile "
                "against it and has nothing to diff without one."
            ),
            errors=[{"field": "manager_match", "code": "no_manager_match"}],
        )
    return submission


def submit_manager_profile(user: User, answers: Any) -> ManagerPlaybookResult:
    """Score, persist, and (if a ManagerMatch sitting already exists) assemble the
    playbook.

    Unlike `GET /me/manager-playbook`, a missing ManagerMatch is not a 409 here: the
    profile itself is valid and worth storing on its own, and the product's intended
    order (ManagerMatch, then manager-profile) is a frontend bridge, not a server-side
    requirement one route enforces and the other does not. `playbook` is simply `None`
    when there is nothing yet to diff against; a later `GET` picks it up once ManagerMatch
    exists.
    """
    from manager_match.decoder import build_playbook
    from manager_match.manager_profile import (
        EXPECTED_ANSWER_COUNT,
        INSTRUMENT_VERSION,
        SCORING_KEY,
        score_manager_profile,
    )
    from manager_match.score import score_manager_match
    import manager_profile_store

    if not isinstance(answers, list) or len(answers) != EXPECTED_ANSWER_COUNT:
        return _error(
            400, "answers must be a list of exactly %d items" % EXPECTED_ANSWER_COUNT
        )

    try:
        scoring = score_manager_profile(answers)
    except ValueError as exc:
        return _error(400, str(exc))

    dimension_scores = scoring["dimension_scores"]

    manager_profile_store.write_manager_profile(
        db,
        user.id,
        answers=answers,
        dimension_scores=dimension_scores,
        scoring_key=SCORING_KEY,
        version=INSTRUMENT_VERSION,
    )
    db.session.commit()

    playbook = None
    manager_match_submission = assessment_repository.current_submission(
        user.id, "manager_match"
    )
    if manager_match_submission is not None and manager_match_submission.answers is not None:
        user_scores = score_manager_match(manager_match_submission.answers)["dimension_scores"]
        playbook = build_playbook(user_scores, dimension_scores)

    return ManagerPlaybookResult(
        status=200,
        body={
            "dimension_scores": dimension_scores,
            "scoring_key": SCORING_KEY,
            "version": INSTRUMENT_VERSION,
            "playbook": playbook,
        },
    )


def get_manager_playbook(user: User) -> ManagerPlaybookResult:
    """Latest manager profile x this user's ManagerMatch -> the assembled playbook.

    409s, distinguishably: no ManagerMatch yet, and no manager profile yet -- the two
    states a client tells apart to route the user at the right instrument
    (BUILD_PLAN C-3).
    """
    from manager_match.decoder import build_playbook
    from manager_match.score import score_manager_match
    import manager_profile_store

    manager_match_submission = _require_manager_match(user.id)

    profile = manager_profile_store.latest_manager_profile(user.id)
    if profile is None:
        raise ConflictError(
            detail=(
                "Profile your manager first -- there is no manager-profile sitting to "
                "build a playbook from yet."
            ),
            errors=[{"field": "manager_profile", "code": "no_manager_profile"}],
        )

    user_scores = score_manager_match(manager_match_submission.answers)["dimension_scores"]
    playbook = build_playbook(user_scores, profile["dimension_scores"])

    return ManagerPlaybookResult(
        status=200,
        body={
            "dimension_scores": profile["dimension_scores"],
            "scoring_key": profile["scoring_key"],
            "version": profile["version"],
            "created_at": profile["created_at"],
            "playbook": playbook,
        },
    )
