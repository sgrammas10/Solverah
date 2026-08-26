"""Re-export shim: culture-fit scoring moved to :mod:`packages.ml.culture.scoring`.

See ``company.py`` beside this file for why the shim exists.
"""

from packages.ml.culture.scoring import (  # noqa: F401
    CultureFitResult,
    culture_fit_score,
)

__all__ = ["CultureFitResult", "culture_fit_score"]
