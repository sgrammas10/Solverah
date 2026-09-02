"""Guards on the alembic revision chain itself.

Incident (2026-09-02): ``flask db upgrade`` on any *fresh* database failed
partway up the chain.  Alembic creates ``alembic_version`` with
``version_num VARCHAR(32)``, and four revision ids were longer than that
(``20260203_add_email_confirmation_to_user`` was 39 characters), so stamping
the first long id raised ``StringDataRightTruncation``.  Nobody had noticed
because every deployed database was already past the long ids on a short
current head, incremental upgrades never re-stamp history, and CI builds its
schema with ``db.create_all()`` rather than the migrations.  The ids were
renamed to fit; this file is what keeps the next one out.
"""

import re
from pathlib import Path

VERSIONS_DIR = Path(__file__).resolve().parents[1] / "migrations" / "versions"

#: Alembic's default width for ``alembic_version.version_num``.  The table is
#: created by alembic itself on a fresh database, so the app cannot widen it
#: before the first revision is stamped -- the ids must fit instead.
ALEMBIC_VERSION_NUM_WIDTH = 32

_REVISION_RE = re.compile(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
_DOWN_REVISION_RE = re.compile(
    r"^down_revision\s*=\s*(?:['\"]([^'\"]+)['\"]|None)", re.MULTILINE
)


def _revision_map() -> dict:
    """``{revision_id: down_revision_or_None}`` for every migration file."""
    chain = {}
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        revision = _REVISION_RE.search(source)
        assert revision, "%s declares no revision id" % path.name
        down = _DOWN_REVISION_RE.search(source)
        assert down, "%s declares no down_revision" % path.name
        chain[revision.group(1)] = down.group(1)
    return chain


def test_every_revision_id_fits_alembic_version_num():
    """No revision id may exceed VARCHAR(32) -- see the module docstring."""
    too_long = {
        rid: len(rid)
        for rid in _revision_map()
        if len(rid) > ALEMBIC_VERSION_NUM_WIDTH
    }
    assert not too_long, (
        "Revision ids longer than %d characters cannot be stamped into "
        "alembic_version.version_num on a fresh database, so `flask db upgrade` "
        "from empty dies at them: %r. Shorten the id (and every down_revision "
        "naming it) before merging." % (ALEMBIC_VERSION_NUM_WIDTH, too_long)
    )


def test_chain_is_a_single_unbroken_line():
    """Every down_revision names a real revision, and exactly one base and head exist.

    This is what makes the rename above safe to repeat: a typo in a renamed
    ``down_revision`` splits the chain, and alembic only reports that when a
    migration actually runs.
    """
    chain = _revision_map()

    dangling = {
        rid: down
        for rid, down in chain.items()
        if down is not None and down not in chain
    }
    assert not dangling, "down_revision names a revision that does not exist: %r" % dangling

    bases = [rid for rid, down in chain.items() if down is None]
    assert len(bases) == 1, "expected exactly one base revision, got %r" % bases

    referenced = {down for down in chain.values() if down is not None}
    heads = [rid for rid in chain if rid not in referenced]
    assert len(heads) == 1, "expected exactly one head revision, got %r" % heads
