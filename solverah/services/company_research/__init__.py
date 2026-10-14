"""The CompanyLens production pipeline (six-trait build, C5):

    research.py      company name -> verified, paraphrased evidence items (Anthropic)
    score_items.py   items -> per-item, per-dimension bands with the abstain (OpenAI)
    aggregate.py     scores -> one CompanyTraitRecord per trait (known / mixed / unknown)
    job_posting.py   a user's pasted posting -> role-scope items (OpenAI only)
    service.py       the functions C6's routes and the CLI call
    jobs.py          how a job leaves the request thread
    prompts.py       the three prompts, versioned
    constants.py     every number, under AGGREGATION_VERSION

Writes go through ``company_evidence_store`` only. This package is the one place
outside the store and the model that reads ``excerpt_internal`` (it is the scorer);
nothing it returns carries that text.
"""

from __future__ import annotations

from solverah.services.company_research.constants import AGGREGATION_VERSION
from solverah.services.company_research.service import (
    aggregate_company,
    request_research,
    research_run_summary,
    run_job_posting_job,
    run_research_job,
    submit_job_posting,
    sweep_research_runs,
)

__all__ = [
    "AGGREGATION_VERSION",
    "aggregate_company",
    "request_research",
    "research_run_summary",
    "run_job_posting_job",
    "run_research_job",
    "submit_job_posting",
    "sweep_research_runs",
]
