"""
Pytest wrapper so check_assessment_items.py runs as a CI gate rather than a script somebody
has to remember. The repo already has pytest.ini and a conftest.py in causal_graph/, so this
is picked up by a bare `pytest` run and by .github/workflows.

Two guarantees, deliberately separate:
  - every non-superseded person-side item file passes the full structural gate
  - any file marked status: superseded is REFUSED by default, so a retired file cannot be
    silently scored against
"""
from pathlib import Path

import pytest
import yaml

from check_assessment_items import check_file

HERE = Path(__file__).resolve().parent
ITEM_FILES = sorted(HERE.glob("assessment_items*.yaml"))


def _status(p):
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("status")


def test_item_files_exist():
    assert ITEM_FILES, "no assessment_items*.yaml found -- the gate would silently pass"


@pytest.mark.parametrize("path", [p for p in ITEM_FILES if _status(p) != "superseded"],
                         ids=lambda p: p.name)
def test_structural_gate(path):
    r = check_file(path, allow_superseded=False)
    assert not r.fails, f"{path.name} failed the structural gate:\n" + "\n".join(
        f"  - {m}" for m in r.fails)


@pytest.mark.parametrize("path", [p for p in ITEM_FILES if _status(p) == "superseded"],
                         ids=lambda p: p.name)
def test_superseded_files_are_refused(path):
    r = check_file(path, allow_superseded=False)
    assert r.fails, (f"{path.name} is marked superseded but the gate accepted it -- "
                     f"a retired item file must not be scoreable")
