"""
test_employer_visibility.py -- D-01 enforced as a test rather than as a policy someone remembers.

D-01: employers never see an individual's assessment answers or their six dimension scores. If
an employer ever sees anything it is a match result, never the underlying scores. That is a
durable data commitment, deliberately scoped to hold *after* employers join the platform.


WHY THIS TEST HAS AN UNUSUAL SHAPE
----------------------------------
There are currently no employer accounts, no employer role, and no employer-facing endpoints --
every protected route in the app is `job-seeker` only, and the company side of a match is the
generated company-profile database rather than signed-up employers.

So the obvious test ("call the employer endpoint, assert no scores in the response") cannot be
written: there is nothing to call. And a test that cannot be written today is exactly how a
commitment quietly becomes a comment. Design rule 3 sat specified-but-unconsumed for a full
session for the same reason -- nothing failed when it was missing.

This test therefore constrains *reachability* instead of responses. The person-side tables may
be touched only from an explicit allowlist of modules. Adding an employer-facing blueprint that
imports `PersonDimensionScore` fails here immediately -- at the moment someone writes the import,
which is months before there is any employer to leak to and while the decision is still cheap to
revisit.

It is a coarse instrument and it is honest about that. It does not prove no leak is possible; it
makes the most likely leak -- someone reaching for the model because it is right there -- loud.


IF THIS TEST FAILS
------------------
Do not add your module to the allowlist to make it pass. That inverts the test into a record of
what happened to be written. Either route the access through `assessment_store.py`, or bring the
change to `AGENT_DECISION_QUEUE.md` as an argument against D-01 (policy red rule 4: a documented
decision is not reversed in passing).
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# The names that must not spread.
PERSON_SIDE_NAMES = {
    "PersonDimensionScore",
    "AssessmentResponse",
    "person_dimension_score",
    "assessment_response",
    # The six-trait match model's stated tolerance and must-have flags (2026-10-13).
    # Self-stated rather than derived, but just as personal: an employer who could read
    # which traits a person will not bend on holds their negotiating position.
    "PersonTraitPreference",
    "person_trait_preference",
}

# Every module permitted to reference them, with the reason it is permitted. A path here is a
# deliberate grant, not an observation.
ALLOWED: dict[str, str] = {
    "model.py": "defines the two tables",
    "assessment_store.py": "the single write path; owns the transaction boundary",
    "migrations/versions/20260819_add_person_side_assessment.py": "creates the tables",
    "migrations/versions/20260827_assessment_unification.py": (
        "Phase 2d. Reads DISTINCT (submission_id, user_id, form_version) off the response "
        "table to build one assessment_submissions row per existing sitting, so the two "
        "join by public_id. It reads the sitting's *identity* and nothing else -- no "
        "choice, no dimension_key, no score -- and the row it writes is null in result and "
        "answers under a check constraint.\n\n"
        "A migration cannot route through assessment_store, and that is the point rather "
        "than an excuse: assessment_store writes through the ORM against today's model, "
        "while a migration must run against the schema as it stood at its revision. Same "
        "class of grant as the 20260819 entry above. It is one-shot, runs under `flask db "
        "upgrade`, and is not reachable from any HTTP route -- which is the property that "
        "makes this a grant and not a leak."
    ),
    "migrations/versions/20261013_trait_prefs.py": (
        "creates the trait-preference table (six-trait match model, 2026-10-13). Same "
        "class of grant as the 20260819 entry: a one-shot schema step under `flask db "
        "upgrade`, not reachable from any HTTP route, and unable to route through "
        "assessment_store because it must run against the schema as it stood at its "
        "revision."
    ),
    "causal_graph/v1_model/assemble_training_data.py": (
        "research pipeline, not app-facing. Reads person-side scores to build the training set "
        "for the Bayesian model. Not reachable from any HTTP route."
    ),
    "tests/test_employer_visibility.py": "this file",
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
    """os.walk with pruning, not rglob.

    rglob("*.py") descends into node_modules before the filter can discard anything; on this
    repo that alone took the scan past 45 seconds. Pruning dirnames in place skips those trees
    entirely. A test slow enough to be skipped is a test that does not run.
    """
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                out.append(Path(dirpath) / fn)
    return out


def _references(path: Path) -> set[str]:
    """Names from PERSON_SIDE_NAMES that appear as identifiers or string literals."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in PERSON_SIDE_NAMES:
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in PERSON_SIDE_NAMES:
            found.add(node.attr)
        elif isinstance(node, ast.alias):
            for part in (node.name, node.asname or ""):
                if part in PERSON_SIDE_NAMES:
                    found.add(part)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Catches raw SQL and __tablename__ strings, which bypass the model entirely.
            for name in PERSON_SIDE_NAMES:
                if name in node.value:
                    found.add(name)
    return found


def test_person_side_tables_are_reachable_only_from_the_allowlist():
    offenders: dict[str, set[str]] = {}
    for path in _python_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in ALLOWED:
            continue
        hits = _references(path)
        if hits:
            offenders[rel] = hits

    assert not offenders, (
        "D-01: employers never see an individual's answers or dimension scores.\n\n"
        "These modules reference the person-side tables and are not on the allowlist:\n"
        + "\n".join(f"  {p}: {sorted(names)}" for p, names in sorted(offenders.items()))
        + "\n\nDo not add them to ALLOWED to make this pass -- that turns the test into a "
        "record of what happened to be written. Route the access through assessment_store.py, "
        "or argue against D-01 in AGENT_DECISION_QUEUE.md first."
    )


def test_app_py_does_not_touch_the_models_directly():
    """The routes go through assessment_store. app.py is where an employer-facing endpoint
    would most plausibly be added, and it is the file least likely to be reviewed line by line
    -- it is over three thousand lines long."""
    hits = _references(REPO_ROOT / "app.py")
    assert not hits, (
        f"app.py references {sorted(hits)}. Route person-side access through "
        f"assessment_store.py so there is one place to audit."
    )


def test_the_allowlist_has_not_rotted():
    """Every allowlisted path must exist and must actually still reference the names. A stale
    entry is a silently widened grant: the file gets deleted or refactored, the permission
    stays, and a future file at that path inherits it."""
    stale = []
    for rel in ALLOWED:
        path = REPO_ROOT / rel
        if not path.exists():
            stale.append(f"{rel}: allowlisted but does not exist")
        elif rel != "tests/test_employer_visibility.py" and not _references(path):
            stale.append(f"{rel}: allowlisted but no longer references the tables")
    assert not stale, "Stale allowlist entries — remove them:\n" + "\n".join(stale)


def test_every_allowlist_entry_states_a_reason():
    unexplained = [rel for rel, why in ALLOWED.items() if not why.strip()]
    assert not unexplained, (
        f"Allowlist entries without a stated reason: {unexplained}. The reason is the part a "
        f"reviewer audits."
    )


# ---------------------------------------------------------------------------
# The response side of the same commitment
# ---------------------------------------------------------------------------

def test_submit_response_carries_no_dimension_scores():
    """D-15. Even the respondent's own submit response omits the six scores -- returning them
    hands a retaker a gradient to optimise against. An employer-facing endpoint reusing this
    payload shape therefore cannot leak scores either."""
    source = (REPO_ROOT / "solverah" / "api" / "v1" / "assessments.py").read_text(
        encoding="utf-8"
    )
    # Phase 1b collapsed the five submit handlers onto one route; `core` is the
    # kind that carries this instrument.
    start = source.index(
        '@assessments_bp.route("/assessments/<kind>/submissions", methods=["POST"])'
    )
    body = source[start : start + 4000]

    # The route returns submission_id / scoring_key_version / dimensions_scored -- a count, not
    # values. `result.scores` must never be serialised.
    assert "result.scores" not in body or "len(result.scores)" in body, (
        "the submit route appears to serialise result.scores; D-15 says it returns no scores"
    )
    assert "jsonify" in body


@pytest.mark.parametrize(
    "path", ["assessment_form.py", "causal_graph/v1_model/present_items.py"]
)
def test_the_instrument_layer_has_no_database_dependency(path):
    """assessment_form.py and present_items.py must stay free of SQLAlchemy and Flask. Keeping
    the instrument unable to reach the database is what makes assessment_store.py the single
    auditable write path -- and it is why the allowlist above can be two files long."""
    source = (REPO_ROOT / path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    forbidden = {"flask", "flask_sqlalchemy", "sqlalchemy", "model", "assessment_store"}
    leaked = imported & forbidden
    assert not leaked, f"{path} imports {sorted(leaked)}; it must stay database-free"
