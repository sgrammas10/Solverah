"""
test_company_confidence_unused.py -- the company-side confidence rule enforced as a test
rather than as a policy someone remembers.

THE RULE
--------
`company_dimension_score.confidence` is STORED, and nothing may FILTER or WEIGHT by it,
pending S-60.

This mirrors D-17(b) onto the company side. D-17(b) already binds the person-side field
("analyses upstream of S-18 may not filter or weight by these values at all",
assessment_store.get_dimension_confidences); the company side had no equivalent because
until S1-6 nothing wrote company scores at all.

WHY, SPECIFICALLY
-----------------
Round 1 measured company-side confidence NOT tracking reliability:
Spearman(B-C band distance, mean confidence) = -0.073 -- no relationship, and if anything
the wrong sign. `decision` carried 3.2x `pace`'s disagreement at ABOVE-average confidence.
A confidence weight built on that number would weight the worst cells as heavily as the
best, while looking principled. S-60 is the open item that decides what the field is good
for; until it lands, the field is a record, not an input.

Storing it is still correct. It is the extractor's own report, it cannot be re-derived
later, and a column that stays honest about not knowing beats a placeholder that reads as
real (the same call D-17(a) makes for feedback's NULL confidence).

WHY THIS TEST HAS THE SHAPE IT DOES
-----------------------------------
Copied deliberately from test_employer_visibility.py, which enforces D-01 the same way and
explains the reasoning at length. The short version: nothing consumes the field yet, so the
obvious test ("call the ranking, assert confidence did not move it") cannot be written --
there is no ranking. And a test that cannot be written today is exactly how a commitment
quietly becomes a comment.

So this constrains REACHABILITY instead. Only an allowlisted module may touch company-side
confidence at all. A future match surface that reaches for the column fails here at the
moment someone writes the line -- while the decision is still cheap -- rather than after a
weighted ranking has shipped.

It is a coarse instrument and it is honest about that: it flags a module that touches BOTH
the company-score table AND a confidence field, which is not the same as proving no
weighting happens. It makes the most likely version loud.

IF THIS TEST FAILS
------------------
Do not add your module to the allowlist to make it pass -- that turns the test into a
record of what happened to be written. Route the read through company_score_store.py, or
close S-60 first and change this rule deliberately.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The company-score table, under every name it is reachable by.
COMPANY_SCORE_NAMES = {"CompanyDimensionScore", "company_dimension_score"}

#: The field that must not spread. Bare `confidence` is far too common to scan for on its
#: own -- the person side, the extractor and the packet builders all use the word -- so a
#: module is only an offender when it touches the company-score table AND this.
CONFIDENCE_NAMES = {"confidence", "min_company_confidence"}

# Every module permitted to reference company-side confidence, with the reason. A path here
# is a deliberate grant, not an observation.
ALLOWED: dict[str, str] = {
    "model.py": "defines the column",
    "company_score_store.py": (
        "the single doorway; stores the value and states the rule. This is the module the "
        "allowlist exists to point at -- a caller that needs the number reads it here, "
        "where the rule is written next to it."
    ),
    "migrations/versions/20260819_add_company_side_model_tables.py": "creates the column",
    "migrations/versions/20260819_add_person_side_assessment.py": (
        "false positive, granted explicitly rather than by loosening the scan: this "
        "migration names `company_dimension_score` once, in its docstring, in a list of "
        "tables it deliberately does NOT create. Its own `confidence` column is the "
        "person-side one governed by D-17. The scan reads string literals on purpose -- "
        "raw SQL and __tablename__ bypass the model entirely -- and the price of that is "
        "the occasional prose match, which is cheaper to allowlist than to guess about."
    ),
    "Scripts/backfill_company_scores.py": (
        "one-shot backfill of the two historical extractor runs. It PASSES confidence "
        "through to the store as a stored value and never branches on it. Not reachable "
        "from any HTTP route."
    ),
    "causal_graph/v1_model/assemble_training_data.py": (
        "research pipeline, not app-facing; already allowlisted for the same reason in "
        "test_employer_visibility.py.\n\n"
        "NOTE, and it is the live tension this rule names: this module has a "
        "`min_company_confidence` parameter that DOES filter rows by company confidence. "
        "It is opt-in and defaults to None -- its own docstring says 'v1 keeps confidence "
        "OUT of the ranking math per the 08-10 handoff; this param exists but is not "
        "silently applied' -- so the default path obeys the rule and the parameter is the "
        "knob S-60 exists to decide about. It is granted here rather than deleted because "
        "removing a research affordance is S-60's call to make, not this test's. If S-60 "
        "concludes confidence is not usable, this parameter is the first thing to go."
    ),
    "tests/test_company_confidence_unused.py": "this file",
    "tests/test_company_side_tables.py": (
        "constraint tests for the table, including the confidence range CHECK; asserts on "
        "storage, never on confidence steering a result"
    ),
}

# Directories that are not application code. Same list as test_employer_visibility.py.
SKIP_DIRS = {
    "node_modules",
    "_to_delete",
    "_mutation_tmp",
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    "dist",
    ".pytest_cache",
}


def _python_files() -> list[Path]:
    """os.walk with pruning, not rglob -- rglob descends into node_modules before the
    filter can discard anything. See test_employer_visibility.py for the measurement."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                out.append(Path(dirpath) / fn)
    return out


def _names_in(tree: ast.AST, wanted: set[str]) -> set[str]:
    """Names from *wanted* appearing as identifiers, attributes, aliases, keyword
    arguments, or inside string literals (which is how raw SQL and __tablename__ bypass
    the model entirely)."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in wanted:
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in wanted:
            found.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg in wanted:
            found.add(node.arg)
        elif isinstance(node, ast.arg) and node.arg in wanted:
            found.add(node.arg)
        elif isinstance(node, ast.alias):
            for part in (node.name, node.asname or ""):
                if part in wanted:
                    found.add(part)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for name in wanted:
                if name in node.value:
                    found.add(name)
    return found


def _company_confidence_hits(path: Path) -> set[str]:
    """The confidence names a module touches, but only if it also reaches the company-score
    table. The conjunction is what keeps this from flagging every use of the word."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()

    if not _names_in(tree, COMPANY_SCORE_NAMES):
        return set()
    return _names_in(tree, CONFIDENCE_NAMES)


def test_company_confidence_is_reachable_only_from_the_allowlist():
    offenders: dict[str, set[str]] = {}
    for path in _python_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in ALLOWED:
            continue
        hits = _company_confidence_hits(path)
        if hits:
            offenders[rel] = hits

    assert not offenders, (
        "company_dimension_score.confidence is stored but must not be filtered or weighted "
        "by, pending S-60 (round 1: Spearman(band distance, mean confidence) = -0.073 -- it "
        "does not track reliability, so a weight built on it would weight the worst cells as "
        "heavily as the best).\n\n"
        "These modules reach the company-score table AND a confidence field, and are not on "
        "the allowlist:\n"
        + "\n".join(f"  {p}: {sorted(names)}" for p, names in sorted(offenders.items()))
        + "\n\nDo not add them to ALLOWED to make this pass. Route the read through "
        "company_score_store.py, or close S-60 and change the rule deliberately."
    )


def test_the_allowlist_has_not_rotted():
    """Every allowlisted path must exist and must still reference the names. A stale entry
    is a silently widened grant: the file is deleted or refactored, the permission stays,
    and a future file at that path inherits it."""
    stale = []
    for rel in ALLOWED:
        path = REPO_ROOT / rel
        if not path.exists():
            stale.append(f"{rel}: allowlisted but does not exist")
        elif rel != "tests/test_company_confidence_unused.py" and not _company_confidence_hits(
            path
        ):
            stale.append(f"{rel}: allowlisted but no longer touches company-side confidence")
    assert not stale, "Stale allowlist entries — remove them:\n" + "\n".join(stale)


def test_every_allowlist_entry_states_a_reason():
    unexplained = [rel for rel, why in ALLOWED.items() if not why.strip()]
    assert not unexplained, (
        f"Allowlist entries without a stated reason: {unexplained}. The reason is the part "
        f"a reviewer audits."
    )


def test_the_store_states_the_rule_where_a_caller_will_read_it():
    """The rule has to live next to the column's doorway, not only in this test. A reader
    who opens company_score_store.py to find out what confidence is for must be told there;
    they will not think to grep the test suite first."""
    import company_score_store

    rule = company_score_store.CONFIDENCE_IS_NOT_A_WEIGHT
    assert "S-60" in rule, "the rule must name the open item that governs it"
    assert "filtered or weighted" in rule
    assert "-0.073" in rule, "the rule must carry the measurement it rests on"
    assert "confidence" in (company_score_store.__doc__ or "").lower()


def test_the_store_does_not_import_the_research_stack():
    """company_score_store must not import openai, and must not import causal_graph --
    causal_graph/scorer_pipeline.py imports openai at module scope, so a single import
    would drag an API client into the web process to read a database row. The store takes
    plain dicts; converting extractor output into them is the caller's job."""
    tree = ast.parse((REPO_ROOT / "company_score_store.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    forbidden = {"openai", "causal_graph", "scorer_pipeline"}
    leaked = imported & forbidden
    assert not leaked, f"company_score_store.py imports {sorted(leaked)}"
