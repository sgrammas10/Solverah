"""Schemas for the Manager Decoder's storage + playbook surface (BUILD_PLAN C-3).

`ManagerPlaybook` is open (``extra="allow"``) for the same reason ``WorkPulseResult`` and
``ManagerMatchResult`` are: it is an assembled document whose per-dimension entries carry
different keys depending on classification (a mesh entry has ``note``; a grind entry has
``headline``/``why``/``ask``/``agenda``/``scripts``/``constraint_note``), and a closed model
over that shape would either flatten it into ``Any`` or lie about which keys are guaranteed.
The keys this module does declare are the ones every caller can rely on.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from . import SolverahModel

__all__ = [
    "ManagerPlaybook",
    "ManagerPlaybookResponse",
    "ManagerProfileAnswer",
    "ManagerProfileSubmitRequest",
    "ManagerProfileSubmitResponse",
]


class ManagerProfileAnswer(SolverahModel):
    model_config = ConfigDict(extra="allow")

    question_id: Optional[str] = None
    choice: Optional[str] = Field(default=None, description='"a" or "b", as authored.')


class ManagerProfileSubmitRequest(SolverahModel):
    answers: List[ManagerProfileAnswer] = Field(
        description="Exactly 16 forced-choice answers, authored option identity."
    )


class ManagerPlaybook(SolverahModel):
    """`manager_match.decoder.build_playbook`'s output, verbatim."""

    model_config = ConfigDict(extra="allow")

    privacy_notice: str
    dimensions: List[Dict[str, Any]] = Field(
        default_factory=list, description="All four dimensions, mesh and grind alike."
    )
    priority: List[str] = Field(
        default_factory=list, description="Grind dimensions, widest gap first."
    )
    grind_count: int
    mesh_count: int


class ManagerProfileSubmitResponse(SolverahModel):
    """``POST /assessments/manager-profile``.

    `playbook` is `None` when this user has no ManagerMatch sitting yet -- there is
    nothing to diff the freshly-stored profile against. `GET /me/manager-playbook` picks
    it up once one exists.
    """

    model_config = ConfigDict(extra="allow")

    dimension_scores: Dict[str, float]
    scoring_key: str
    version: str
    playbook: Optional[ManagerPlaybook] = None


class ManagerPlaybookResponse(SolverahModel):
    """``GET /me/manager-playbook`` -- the latest manager profile and its playbook.

    Always carries a `playbook`: the route answers `409` rather than `200` with a null
    one when either side of the diff is missing (`ManagerProfileSubmitResponse` is where
    a null playbook is a real, reachable state).
    """

    model_config = ConfigDict(extra="allow")

    dimension_scores: Dict[str, float]
    scoring_key: str
    version: str
    created_at: Optional[str] = None
    playbook: ManagerPlaybook
