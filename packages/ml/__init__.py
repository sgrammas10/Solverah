"""Deterministic, offline machine-learning code: parsing, scoring, matching.

Nothing in here imports Flask, SQLAlchemy, or the network.  That is the whole
point -- see docs/ARCHITECTURE.md 3.2 rule 2.  It makes the most valuable IP in
the product importable from the API, from a worker, and from a notebook, and
testable without an application context.

Before Phase 1 this code was reached two different broken ways:

  * ``app.py`` pushed ``company_culture_LLM/`` onto ``sys.path`` at import time
    so that ``from company import CultureValues`` resolved.  A module named
    ``company`` at the top of the path is a name collision waiting to happen,
    and it made the import graph unreadable.
  * ``resume_parser.py`` was loaded with ``importlib.util.spec_from_file_location``
    against a hard-coded path, executed at module scope.  It could not be
    imported by anything else, could not be mocked, and failed at boot rather
    than at use if the file moved.

Both are gone.  ``company_culture_LLM/`` and
``job_descr_LLM/user_input_pipeline/`` keep re-export shims so the one-off
seeding and dataset scripts that live beside them still run.

Sub-packages:
    culture -- company profile models, culture-fit scoring, vector similarity.
    resume  -- rule-based resume parsing.

Still to move (they already import cleanly, so nothing is blocked on it):
``work_pulse/``, ``focus_type/``, ``manager_match/``, ``backend/services/path_*``.
"""
