"""Re-export shim: moved to :mod:`packages.ml.culture.similarity`.

See ``company.py`` beside this file for why the shim exists.
"""

from packages.ml.culture.similarity import (  # noqa: F401
    profile_cosine_similarity,
)

__all__ = ["profile_cosine_similarity"]
