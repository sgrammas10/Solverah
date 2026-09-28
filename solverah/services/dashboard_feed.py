"""The dashboard's Recent Activity and Recommendations, built from real rows.

Both lists used to be static placeholders sent to every account. They are now
derived per user from what :mod:`solverah.repositories.dashboard_repository`
reads, the already-loaded profile document, and whether the current Work Pulse
instrument is on record.

**``time`` is an ISO-8601 UTC timestamp, not a phrase.** The payload sits in a
Redis cache for up to the TTL, and a server-rendered "just now" would still say
so five minutes later; the frontend humanizes at render time instead.

**Cache invalidation.** ``dashboard_data`` is cached per user and was only ever
dropped by a profile-document write. Four of the five activity sources are
written elsewhere (assessment, environment-report, manager-profile and pulse
services), so rather than a ``cache.delete`` at each of those sites -- one of
which is easy to forget the next time a writer is added -- :func:`install_invalidation`
attaches an ``after_flush`` hook that parks the owner's dashboard key for
deletion on commit whenever a row of one of those tables is inserted or changed.
A rolled-back transaction drops nothing, the same as every other invalidation
(``solverah.infra.cache``).
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import event as sa_event

from model import (
    AssessmentSubmission,
    EnvironmentReport,
    ManagerProfile,
    PulseCheckin,
    Resume,
    db,
)
from solverah.infra import cache
from solverah.repositories import dashboard_repository as repo
from solverah.services import pulse_settings

__all__ = [
    "ACTIVITY_LIMIT",
    "RECOMMENDATION_LIMIT",
    "build_activity",
    "build_recommendations",
    "install_invalidation",
]

ACTIVITY_LIMIT = 5
RECOMMENDATION_LIMIT = 3

#: Icon names must be ones `JobSeekerDashboard.tsx`'s `iconMap` resolves.
_ASSESSMENT_COPY: Dict[str, Tuple[str, str]] = {
    "core": ("You took Work Pulse", "Brain"),
    "work_pulse": ("You took the original Work Pulse quiz", "Brain"),
    "focus_type": ("You took FocusType", "Brain"),
    "manager_match": ("You took ManagerMatch", "Brain"),
}

_SOURCE_COPY: Dict[str, Tuple[str, str, str]] = {
    repo.SOURCE_ENVIRONMENT_REPORT: ("assessment", "You described your current job", "FileText"),
    repo.SOURCE_MANAGER_PROFILE: ("assessment", "You described your manager", "Briefcase"),
    repo.SOURCE_PULSE_CHECKIN: ("pulse", "You checked in on your week", "TrendingUp"),
    repo.SOURCE_RESUME: ("profile", "You uploaded your resume", "FileText"),
}


# ---------------------------------------------------------------------------
# Recent Activity
# ---------------------------------------------------------------------------

def _iso(at: datetime.datetime) -> str:
    """UTC ISO-8601; a naive value is taken to be UTC already."""
    if at.tzinfo is None:
        at = at.replace(tzinfo=datetime.timezone.utc)
    return at.astimezone(datetime.timezone.utc).isoformat()


def _item(kind: str, text: str, icon: str, at: datetime.datetime) -> Dict[str, Any]:
    return {"type": kind, "text": text, "time": _iso(at), "icon": icon, "_at": at}


def _row_item(row: repo.ActivityRow) -> Optional[Dict[str, Any]]:
    """One repository row as an activity item, or None for an unknown kind."""
    if row.source == repo.SOURCE_ASSESSMENT:
        copy = _ASSESSMENT_COPY.get(row.kind or "")
        return _item("assessment", copy[0], copy[1], row.at) if copy else None
    kind, text, icon = _SOURCE_COPY[row.source]
    return _item(kind, text, icon, row.at)


def _parse_iso(raw: Any) -> Optional[datetime.datetime]:
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime.timezone.utc)


def _quiz_insights_at(profile: Dict[str, Any]) -> Optional[datetime.datetime]:
    """When career-quiz insights were last generated, from the profile document.

    ``insight_service`` stamps ``generatedAt`` on each flat group and
    ``_generatedAt`` on the career-quiz group; the newest of them is the event.
    """
    groups = profile.get("quizInsights")
    if not isinstance(groups, dict):
        return None
    stamps = [
        _parse_iso(group.get("_generatedAt") or group.get("generatedAt"))
        for group in groups.values()
        if isinstance(group, dict)
    ]
    stamps = [stamp for stamp in stamps if stamp is not None]
    return max(stamps) if stamps else None


def build_activity(
    rows: Iterable[repo.ActivityRow], profile: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Newest first, at most :data:`ACTIVITY_LIMIT`, in the wire shape."""
    items = [item for item in (_row_item(row) for row in rows) if item is not None]
    insights_at = _quiz_insights_at(profile)
    if insights_at is not None:
        items.append(_item("assessment", "You got insights from your career quizzes", "Brain", insights_at))
    items.sort(key=lambda item: item["_at"], reverse=True)
    return [{k: v for k, v in item.items() if k != "_at"} for item in items[:ACTIVITY_LIMIT]]


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def _rec(rec_id: str, title: str, description: str, action: str, href: str,
         priority: str = "normal") -> Dict[str, Any]:
    return {
        "id": rec_id,
        "title": title,
        "description": description,
        "action": action,
        "priority": priority,
        "href": href,
    }


def _career_status(profile: Dict[str, Any]) -> Optional[str]:
    """Explicit status, else the derivation every other reader falls back to."""
    from solverah.services.intelligence_service import derive_career_status

    return profile.get("career_status") or derive_career_status(profile)


def _pulse_is_stale(profile: Dict[str, Any], last_checkin: Optional[datetime.datetime],
                    now: datetime.datetime) -> bool:
    """Never checked in, or the last check-in is older than the user's cadence."""
    settings = profile.get(pulse_settings.SETTINGS_KEY)
    settings = settings if isinstance(settings, dict) else {}
    cadence = settings.get("cadence") or pulse_settings.DEFAULT_CADENCE
    interval = pulse_settings.CADENCE_INTERVALS.get(cadence)
    if interval is None:  # "off"
        return False
    return last_checkin is None or now - last_checkin >= interval


def build_recommendations(
    profile: Dict[str, Any],
    rows: Iterable[repo.ActivityRow],
    *,
    has_work_pulse: bool,
    now: datetime.datetime,
) -> List[Dict[str, Any]]:
    """The user's next unfinished steps, most important first, at most three."""
    latest = {row.source: row.at for row in rows if row.source != repo.SOURCE_ASSESSMENT}
    has_env_report = repo.SOURCE_ENVIRONMENT_REPORT in latest
    status = _career_status(profile)
    recs: List[Dict[str, Any]] = []

    if not status:
        recs.append(_rec(
            "career_status", "Tell us where you are in your career",
            "Working, between jobs, or looking for your first one. It changes what we ask and suggest.",
            "Set your status", "/job-seeker/profile", "urgent"))
    if not has_work_pulse:
        recs.append(_rec(
            "work_pulse", "Take Work Pulse",
            "24 questions about how you work best. Most of Solverah builds on it.",
            "Start Work Pulse", "/work-pulse", "urgent"))
    if has_work_pulse and not has_env_report and status != "first_job":
        recs.append(_rec(
            "environment_report", "Describe your current job",
            "The Environment Report is how we compare your job with what you need.",
            "Start the report", "/environment-report"))
    if has_work_pulse and has_env_report:
        recs.append(_rec(
            "situation_report", "Read your Situation Report",
            "Where your job fits you, and where it pulls against you.",
            "Open the report", "/situation-report"))
    if not profile.get("skills"):
        recs.append(_rec(
            "skills", "Add your skills",
            "A few skills make your path suggestions much sharper.",
            "Add skills", "/job-seeker/profile#experience"))
    if _pulse_is_stale(profile, latest.get(repo.SOURCE_PULSE_CHECKIN), now):
        recs.append(_rec(
            "pulse", "Check in on your week",
            "A one-minute pulse keeps your picture of work up to date.",
            "Check in", "/pulse"))
    return recs[:RECOMMENDATION_LIMIT]


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------

#: Tables whose rows appear in, or change, the dashboard. Profile-document
#: writes are not here: `profile_repository.update_document` already drops
#: the key itself.
_ACTIVITY_MODELS = (AssessmentSubmission, EnvironmentReport, ManagerProfile, PulseCheckin, Resume)

_installed = False


def _owners(objects: Iterable[Any]) -> List[int]:
    return sorted({
        obj.user_id for obj in objects
        if isinstance(obj, _ACTIVITY_MODELS) and getattr(obj, "user_id", None) is not None
    })


def _park_dashboard_keys(session, _flush_context) -> None:  # noqa: ANN001 -- SQLAlchemy's signature
    """``after_flush``: queue the dashboard key of every affected user."""
    owners = _owners(list(session.new) + list(session.dirty))
    if owners:
        pending = session.info.setdefault(cache.SESSION_INVALIDATION_KEY, [])
        pending.extend(cache.dashboard_key(user_id) for user_id in owners)


def install_invalidation() -> None:
    """Attach :func:`_park_dashboard_keys` to the app session. Idempotent."""
    global _installed
    if _installed:
        return
    sa_event.listen(db.session, "after_flush", _park_dashboard_keys)
    _installed = True
