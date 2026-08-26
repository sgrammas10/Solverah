"""Deterministic, offline resume parsing.

Formerly ``job_descr_LLM/user_input_pipeline/resume_parser.py``, loaded by
``app.py`` through ``importlib.util.spec_from_file_location`` at module scope.
It is an ordinary import now.
"""

from .parser import parse_resume

__all__ = ["parse_resume"]
