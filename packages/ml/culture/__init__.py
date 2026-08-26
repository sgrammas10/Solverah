"""Company culture modelling: profile schema, fit scoring, and similarity.

Formerly ``company_culture_LLM/{company,score,similarity}.py``, reached via a
``sys.path`` injection in ``app.py``.
"""

from .company import (
    PACE_TO_FLOAT,
    CompanyProfile,
    CultureValues,
    Pace,
)
from .scoring import CultureFitResult, culture_fit_score
from .similarity import profile_cosine_similarity

__all__ = [
    "PACE_TO_FLOAT",
    "CompanyProfile",
    "CultureFitResult",
    "CultureValues",
    "Pace",
    "culture_fit_score",
    "profile_cosine_similarity",
]
