"""
test_company_evidence_internal.py -- GAP-14 on the company evidence tables, enforced as a
test rather than as a policy someone remembers.

THE RULE
--------
`company_evidence_item.excerpt_internal` -- the verbatim third-party text the scorer
scored -- never reaches a route, a page, or a view. Users see the paraphrase, the source
type, the scope and the dates (Solverah_IP/compliance/AI_GOVERNANCE_AND_CLAIMS.md, GAP-14:
verbatim third-party quotes never render in the product; PRODUCT_DECISIONS.md §2, the
six-trait entry, "paraphrased excerpts -- no verbatim third-party quotes").

WHY THIS TEST HAS THE SHAPE IT DOES
-----------------------------------
Copied deliberately from tests/test_employer_visibility.py, which enforces D-01 the same
way and explains the reasoning at length. The short version: the match service and the
CompanyLens page that would serialize this column do not exist yet (C6, C7), so the
obvious test -- "call the route, assert the excerpt is not in the body" -- cannot be
written today, and a test that cannot be written today is exactly how a commitment
quietly becomes a comment.

So this constrains REACHABILITY. The column name may appear only in the modules on the
allowlist below -- the model that defines it, the migration that creates it, the store's
write path, the scorer package that reads it to score, and the tests that prove the rule.
A route, a schema or a serializer that names the column fails here at the moment someone
writes the line.

IF THIS TEST FAILS
------------------
Do not add your module to the allowlist to make it pass. If you need the text a user may
see, that is `paraphrase`, which every view already carries. If you are writing the
scorer, it lives in `solverah/services/company_research/`, which is already allowed.
"""

from __future__ import annotations

import ast
import dataclasses
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The names that must not spread. `diagnostics_internal` (C5b, review F2) is the
#: research run card: it holds the turn's raw text and every citation's verbatim
#: cited_text, so it is under GAP-14 exactly as the excerpt is.
INTERNAL_NAMES = {"excerpt_internal", "diagnostics_internal"}

#: Every module permitted to reference it, with the reason. A path here is a deliberate
#: grant, not an observation.
ALLOWED: dict[str, str] = {
    "model.py": "defines the column (deferred, so no row walk picks it up by accident)",
    "migrations/versions/20261013_company_evidence.py": "creates the column",
    "company_evidence_store.py": (
        "the single write path (EvidenceItemInput -> write_items; finish_research_run "
        "for the run card). Its read functions and views are built field by field and "
        "never carry either column; "
        "test_company_evidence_store.py::test_views_never_carry_the_internal_excerpt pins "
        "the shape, and `test_no_view_dataclass_carries_the_excerpt` below pins every "
        "dataclass in the module."
    ),
    "tests/test_company_evidence_store.py": "the store's tests write items, so they name the input field",
    "tests/test_company_evidence_internal.py": "this file",
}

#: Directories (prefixes, posix-relative) permitted as a whole. The scorer must read the
#: text it scores. The package does not exist until C5 lands; a prefix that does not exist
#: grants nothing, so it is not a stale entry.
ALLOWED_PREFIXES: dict[str, str] = {
    "solverah/services/company_research/": (
        "the production research + scoring package (C5): it writes the excerpt through "
        "the store and reads it back to score. Not reachable from any HTTP route; the "
        "match service (C6) reads trait records and paraphrases only."
    ),
}

# Directories that are not application code.
SKIP_DIRS = {
    "node_modules",
    "_to_delete",
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "dist",
    "Scripts",
    ".pytest_cache",
}


def _python_files() -> list[Path]:
    """os.walk with pruning, not rglob -- see test_employer_visibility.py for why."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                out.append(Path(dirpath) / fn)
    return out


def _references(path: Path) -> set[str]:
    """Names from INTERNAL_NAMES that appear as identifiers, attributes, keywords or
    string literals (raw SQL and column-name strings bypass the model entirely)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in INTERNAL_NAMES:
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in INTERNAL_NAMES:
            found.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg in INTERNAL_NAMES:
            found.add(node.arg)
        elif isinstance(node, ast.alias):
            for part in (node.name, node.asname or ""):
                if part in INTERNAL_NAMES:
                    found.add(part)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for name in INTERNAL_NAMES:
                if name in node.value:
                    found.add(name)
    return found


def _is_allowed(rel: str) -> bool:
    return rel in ALLOWED or any(rel.startswith(prefix) for prefix in ALLOWED_PREFIXES)


def test_the_excerpt_is_reachable_only_from_the_allowlist():
    offenders: dict[str, set[str]] = {}
    for path in _python_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if _is_allowed(rel):
            continue
        hits = _references(path)
        if hits:
            offenders[rel] = hits

    assert not offenders, (
        "GAP-14: verbatim third-party quotes never render in the product.\n\n"
        "These modules reference the internal excerpt column and are not on the allowlist:\n"
        + "\n".join(f"  {p}: {sorted(names)}" for p, names in sorted(offenders.items()))
        + "\n\nDo not add them to ALLOWED to make this pass. Read `paraphrase` through "
        "company_evidence_store's views instead; if you are the scorer, you live in "
        "solverah/services/company_research/."
    )


def test_routes_and_schemas_never_name_the_excerpt():
    """The two places a leak would actually ship from, checked by name so the failure
    message says 'route' rather than 'module'. Redundant with the scan above on purpose."""
    leaks = []
    for sub in ("solverah/api", "solverah/schemas", "solverah/services"):
        root = REPO_ROOT / sub
        for path in root.rglob("*.py"):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if _is_allowed(rel):
                continue
            if _references(path):
                leaks.append(rel)
    assert not leaks, "route/schema/service modules naming the internal excerpt: %r" % leaks


def test_the_allowlist_has_not_rotted():
    """Every allowlisted path must exist and must still reference the name. A stale entry
    is a silently widened grant. Prefixes are exempt: an absent package grants nothing."""
    stale = []
    for rel in ALLOWED:
        path = REPO_ROOT / rel
        if not path.exists():
            stale.append(f"{rel}: allowlisted but does not exist")
        elif rel != "tests/test_company_evidence_internal.py" and not _references(path):
            stale.append(f"{rel}: allowlisted but no longer references the column")
    assert not stale, "Stale allowlist entries -- remove them:\n" + "\n".join(stale)


def test_every_allowlist_entry_states_a_reason():
    unexplained = [rel for rel, why in {**ALLOWED, **ALLOWED_PREFIXES}.items() if not why.strip()]
    assert not unexplained, f"Allowlist entries without a stated reason: {unexplained}."


def test_the_rule_is_stated_once_in_the_store():
    import company_evidence_store

    assert "excerpt_internal" in company_evidence_store.EXCERPT_IS_INTERNAL
    assert "GAP-14" in company_evidence_store.EXCERPT_IS_INTERNAL
    assert "diagnostics_internal" in company_evidence_store.DIAGNOSTICS_ARE_INTERNAL
    assert "GAP-14" in company_evidence_store.DIAGNOSTICS_ARE_INTERNAL


def test_no_view_dataclass_carries_the_excerpt():
    """Every frozen dataclass the store exports is either an input (the write path) or a
    view; only the one input that writes the item may name the column, and NOTHING
    names the run card (it is written through a keyword argument, never a dataclass)."""
    import company_evidence_store as store

    carriers = []
    for name in dir(store):
        obj = getattr(store, name)
        if isinstance(obj, type) and dataclasses.is_dataclass(obj):
            if any(f.name in INTERNAL_NAMES for f in dataclasses.fields(obj)):
                carriers.append(name)
    assert carriers == ["EvidenceItemInput"], (
        "only the item INPUT may carry the excerpt; these dataclasses do: %r" % carriers
    )
    assert not any(name.endswith("View") for name in carriers)
    assert "diagnostics" not in {f.name for f in dataclasses.fields(store.ResearchRunView)}
    assert "diagnostics_internal" not in {f.name for f in dataclasses.fields(store.ResearchRunView)}


def test_the_columns_are_deferred_on_the_models():
    """A serializer that walks a loaded row (`row.__dict__`, `inspect(row).attrs`) must not
    find the excerpt or the run card loaded. `deferred` is what makes that true; this
    pins it for both."""
    from sqlalchemy import inspect

    from model import CompanyEvidenceItem, CompanyResearchRun

    prop = inspect(CompanyEvidenceItem).column_attrs["excerpt_internal"]
    assert prop.deferred, "CompanyEvidenceItem.excerpt_internal must stay `deferred`"
    prop = inspect(CompanyResearchRun).column_attrs["diagnostics_internal"]
    assert prop.deferred, "CompanyResearchRun.diagnostics_internal must stay `deferred`"


def test_the_run_summary_carries_counts_and_never_the_card_text():
    """The one consumer of the run card outside the pipeline is the CLI summary
    (service.research_run_summary). It may report counts; it may not report text. Pinned
    by the shape of what it returns on a card that holds marked text."""
    from solverah.services.company_research import service

    raw = "VERBATIM THIRD-PARTY TEXT"
    card = {
        "candidates": 4, "kept": 1, "served_model": "m",
        "citations": {"total": 3, "by_kind": {"char_location": 3}},
        "dropped": {"invalid": 0, "unverified": 2, "paraphrase": 1,
                    "by_reason": {"coverage": 2, "paraphrase_shared_run": 1}},
        "raw_text": raw, "raw_citations": [{"cited_text": raw}],
    }

    class _Row:
        id = 1; company_id = 1; status = "done"; error = None; model = "m"; cost_usd = None
        diagnostics_internal = card

    class _Company:
        id = 1; name = "Acme"; headcount = None

    class _Query:
        def filter(self, *a): return self
        def count(self): return 1

    class _Session:
        def get(self, cls, _id): return _Row() if cls.__name__ == "CompanyResearchRun" else _Company()
        def query(self, *a): return _Query()

    class _DB:
        session = _Session()

    import company_evidence_store as store_mod
    original = store_mod.trait_records
    store_mod.trait_records = lambda db, cid, scope=None: []
    try:
        summary = service.research_run_summary(_DB(), 1)
    finally:
        store_mod.trait_records = original
    assert summary["candidates"] == 4 and summary["citations"] == 3
    assert summary["dropped"] == {"invalid": 0, "unverified": 2, "paraphrase": 1}
    assert raw not in repr(summary)
