"""Re-export shim: the parser moved to :mod:`packages.ml.resume.parser`.

``app.py`` used to load this file by path with
``importlib.util.spec_from_file_location`` at module scope, which meant the
parser could not be imported normally, mocked, or reused from a worker.  It is
an ordinary module now.

The shim stays because ``Scripts/parse_edge_case.py``,
``Scripts/regression_check.py``, and ``resume_parser_test.py`` beside this file
all address the parser at this path, and the datasets they drive
(``datasets/v1/resume_parser_expected.jsonl``) are the parser's regression
corpus.  Delete it once those point at ``packages.ml.resume``.
"""

from packages.ml.resume.parser import *  # noqa: F401,F403
from packages.ml.resume.parser import parse_resume  # noqa: F401

__all__ = ["parse_resume"]
