"""Re-export shim: the models moved to :mod:`packages.ml.culture.company`.

The seeding and profile-generation scripts in this directory import
``from company import ...`` -- a flat import that only resolves when this
directory is on ``sys.path``.  ``app.py`` used to arrange that with a
``sys.path.insert`` at import time; Phase 1 removed it (see
docs/ARCHITECTURE.md P0-4).  This shim keeps those scripts working without
reinstating the path hack.

Delete it once the scripts import ``packages.ml.culture`` directly.
"""

from packages.ml.culture.company import (  # noqa: F401
    PACE_TO_FLOAT,
    Compensation,
    CompanyOverview,
    CompanyProfile,
    CultureValues,
    Executive,
    GlassdoorRatings,
    InternshipProgram,
    InterviewProcess,
    NewsControversies,
    Pace,
    RecruitingContacts,
    RemotePolicy,
    TechStack,
    WorkforceSignals,
)

__all__ = [
    "PACE_TO_FLOAT",
    "Compensation",
    "CompanyOverview",
    "CompanyProfile",
    "CultureValues",
    "Executive",
    "GlassdoorRatings",
    "InternshipProgram",
    "InterviewProcess",
    "NewsControversies",
    "Pace",
    "RecruitingContacts",
    "RemotePolicy",
    "TechStack",
    "WorkforceSignals",
]
