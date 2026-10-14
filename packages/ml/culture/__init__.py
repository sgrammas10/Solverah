"""Company culture modelling: profile schema and similarity.

Formerly ``company_culture_LLM/{company,score,similarity}.py``, reached via a
``sys.path`` injection in ``app.py``. ``scoring.py`` (the interim
``culture_fit_score``) was deleted by the six-trait build (2026-10-13): the causal
model in ``causal_graph/v1_model`` serves matching now.
"""

from .company import (
    PACE_TO_FLOAT,
    CompanyProfile,
    CultureValues,
    Pace,
)
from .similarity import profile_cosine_similarity

__all__ = [
    "PACE_TO_FLOAT",
    "CompanyProfile",
    "CultureValues",
    "Pace",
    "profile_cosine_similarity",
]
