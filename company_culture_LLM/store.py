"""Re-export shim: the company queries moved to
:mod:`solverah.repositories.company_repository`.

``seed_from_generated_xlsx.py`` in this directory imports
``from company_culture_LLM.store import upsert_company``.  Delete this shim once
that script points at the repository directly.
"""

from solverah.repositories.company_repository import (  # noqa: F401
    all_companies,
    get_company,
    seed_all,
    upsert_company,
)

__all__ = ["all_companies", "get_company", "seed_all", "upsert_company"]
