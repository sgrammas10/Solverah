"""Canonical skill identity: how free text becomes one row in ``skills``.

Blob skills were free text.  ``profile_skills`` references ``skills(id)``, so
"Python", "python" and "PYTHON" have to resolve to one row or the dimension
table is a list of typos with a primary key.  :func:`slugify` is that rule, and
it is deliberately the *whole* rule -- everything it collapses is textual and
mechanical, and nothing it collapses is a judgement about meaning.

What it collapses
-----------------

===========================  ====================  ==================================
Input                        Slug                  Collapsed with
===========================  ====================  ==================================
``Python`` / ``python``      ``python``            case
``  machine   learning ``    ``machine-learning``  surrounding and repeated whitespace
``Node.js`` / ``Node JS``    ``node-js``           punctuation vs. space as separator
``node_js`` / ``Node-JS``    ``node-js``           separator character
``Café Management``          ``cafe-management``   diacritics (NFKD, marks dropped)
``ＰＹＴＨＯＮ``               ``python``            compatibility forms (NFKD)
``C++`` / ``c++``            ``cpp``               see below
``C#`` / ``F#``              ``csharp`` / ``fsharp``
``.NET``                     ``dotnet``
===========================  ====================  ==================================

What it does **not** collapse
-----------------------------

Near-duplicates by *meaning*: ``JS`` and ``JavaScript`` stay two rows, as do
``React`` and ``React.js``, ``k8s`` and ``Kubernetes``, ``Postgres`` and
``PostgreSQL``.  Merging those needs a curated dictionary, and inventing one
inside a storage migration would silently change which skills a profile matches
on -- a scoring change wearing a schema change's clothes.  ``skills.aliases``
and the trigram index on ``skills.label`` exist so that curation can happen
later as data, without another migration.

Why the symbol table comes first
--------------------------------

Stripping punctuation before substituting is the trap this rule exists to avoid:
``C``, ``C++`` and ``C#`` all reduce to ``c``, so three unrelated skills become
one row and every profile claiming any of them claims all three.  ``++`` -> ``pp``,
``#`` -> ``sharp`` and a leading ``.`` -> ``dot`` are applied while the symbols
are still there.  The substitutions are generic character rules rather than a
list of language names, so ``G#`` and ``.tmux`` behave predictably without
anyone having thought about them.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

__all__ = ["MAX_SLUG_LENGTH", "slugify"]

#: Cap on a generated slug. ``skills.slug`` is unbounded TEXT, so this is not a
#: storage limit -- it stops a pasted paragraph that happens to sit in a skills
#: array from becoming a dimension-table row wider than the screen.
MAX_SLUG_LENGTH = 128

#: Applied before punctuation is stripped. Order matters within the tuple:
#: ``++`` must be seen before any single ``+`` rule would be.
_SYMBOL_SUBSTITUTIONS = (
    ("++", "pp"),
    ("#", "sharp"),
)

_LEADING_DOT = re.compile(r"^\.+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(label: object) -> Optional[str]:
    """The canonical ``skills.slug`` for a free-text skill label.

    Args:
        label: Whatever was in the profile's ``skills`` array. Anything that is
            not a string, or that normalises away to nothing (``"---"``,
            ``"   "``, ``"🙂"``), is not a skill.

    Returns:
        The slug, or None when *label* does not name a skill. Callers treat None
        as "this list is not decomposable" rather than silently dropping the
        entry -- losing a skill is worse than leaving the list in
        ``profiles.extra`` for one more release.
    """
    if not isinstance(label, str):
        return None

    # NFKD rather than NFKC: decomposing is what separates a base letter from
    # its combining mark, which is what makes the mark droppable below.
    text = unicodedata.normalize("NFKD", label)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().strip()

    if not text:
        return None

    text = _LEADING_DOT.sub("dot", text)
    for symbol, replacement in _SYMBOL_SUBSTITUTIONS:
        text = text.replace(symbol, replacement)

    slug = _NON_ALNUM.sub("-", text).strip("-")
    if not slug:
        return None

    # Truncating can only ever shorten, so it cannot introduce a collision that
    # the untruncated slugs did not already have -- unless two labels agree for
    # 128 characters, at which point they are the same skill by any measure.
    return slug[:MAX_SLUG_LENGTH].strip("-") or None
