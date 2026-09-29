"""One plain sentence per occupation, in a file beside the corpus (W-18).

BUILD_PLAN W-18 (W-17's option A, approved by Sebastian 2026-09-29).

WHAT THIS IS FOR
----------------
A Path Intelligence card used to open as a title, its reasons and a shimmer
line, and only became readable when the narrator's personal sentence landed a
few seconds later.  This module is the part of a card that does not need the
narrator: **O*NET's own description of the occupation, first sentence only**,
shown under the title the moment the card is.  The personal ``why_text`` then
fades in *below* it -- added, never swapped in.

The sentence is static per occupation, so it is filled at scoring time from a
file read once per process, like every other sidecar: no network on the request
path, every worker reads the same bytes, and data derived from the artifact is
not the artifact.

WHERE THE TEXT COMES FROM
-------------------------
``<stem>.documents.jsonl``, which ``corpus build`` already writes beside the
artifact and which carries O*NET's ``description`` for every code.  **Building
this file makes no O*NET call and no LLM call** -- it is string handling over a
file already on disk, which is why ``corpus refresh`` runs it before publishing:
the summaries rebuild themselves with the corpus.

:func:`summarise` takes the first sentence and caps it.  Measured on the
2026-09-16 catalog (1,016 rows, none empty): first sentences run p50 111
characters, p90 196, max 486, and 92 are over 200.  The cap is
:data:`SUMMARY_MAX_CHARS`, and a long sentence is cut **at a clause boundary**
(a semicolon, then a parenthetical dropped, then a comma), never with an ellipsis
in the middle of a clause.

**A missing sidecar is a DEGRADE, not an error.**  :func:`get_summaries` returns
None, one warning is logged per corpus version, and every card carries
``summary == ""`` -- the card then keeps its thin shimmer line until the
narrator lands, exactly as before this module existed.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from backend.services.occupation_retrieval import (
    OccupationCorpus,
    is_all_other_title,
)

_log = logging.getLogger(__name__)

__all__ = [
    "SUMMARIES_SCHEMA_VERSION",
    "SUMMARY_MAX_CHARS",
    "SummariesTable",
    "build_table",
    "first_sentence",
    "get_summaries",
    "reset_summaries_cache",
    "summarise",
    "summaries_sidecar_path",
    "summary_for",
    "write_summaries_sidecar",
]

#: Sidecar schema version.  Independent of the corpus artifact's and of the
#: other sidecars', for the reason ``ZONES_SCHEMA_VERSION`` gives: the files are
#: written by different commands and regenerate independently.
SUMMARIES_SCHEMA_VERSION = 1

#: The longest summary a card shows.  W-17 measured p90 at 196, so about nine
#: in ten first sentences pass through untouched and the rest are cut at a
#: clause boundary.
SUMMARY_MAX_CHARS = 200

#: A cut shorter than this reads as a fragment, so a clause boundary this early
#: is passed over in favour of the next strategy.
_MIN_CUT_CHARS = 60

#: Tokens that end in a period without ending a sentence.  O*NET's descriptions
#: carry "U.S. Coast Guard" and "(e.g., ...)" -- the first is followed by a
#: capital letter, which is exactly what a naive splitter takes for a new
#: sentence.
_ABBREVIATIONS = frozenset(
    {
        "e.g.", "i.e.", "etc.", "u.s.", "vs.", "inc.", "st.", "dr.", "mr.",
        "mrs.", "ms.", "no.", "jr.", "sr.", "co.", "corp.", "approx.", "dept.",
    }
)

#: Words a cut must not end on: a clause that stops at "and" or "such as" is
#: still mid-clause however the characters fall.
_DANGLING = frozenset(
    {
        "a", "an", "and", "as", "at", "by", "for", "from", "in", "including",
        "into", "of", "on", "or", "such", "the", "to", "with", "within", "may",
        "that", "which", "who", "their", "its", "other", "various", "both",
        "either", "whether", "like", "via", "than", "also", "nor", "but",
    }
)

#: Endings that mark a word as probably an adjective.  O*NET's long sentences
#: are mostly lists, and a list cut after "biological, agricultural" has kept
#: the modifiers and lost the noun they modify.  A false positive (a noun such
#: as "material") only costs a shorter cut, never a worse one.
_ADJECTIVE_ENDINGS = ("al", "ic", "ive", "ous", "ary", "ern")

#: Where a long sentence turns from the duty into its examples.  Cutting just
#: before one keeps the whole duty and drops only the list.
_EXAMPLES = re.compile(r", (?:such as|including|especially) ")

_PARENTHETICAL = re.compile(r"\s*\([^()]*\)")


# ---------------------------------------------------------------------------
# The sentence
# ---------------------------------------------------------------------------


def first_sentence(text: str) -> str:
    """The first sentence of *text*, whitespace collapsed.

    A sentence ends at ``.``, ``!`` or ``?`` followed by whitespace and a capital
    letter (or by the end of the text), **outside parentheses**, and not after a
    known abbreviation.  So "U.S. Coast Guard" and "(e.g., hurricanes)" stay
    inside their sentence, and a decimal such as "2.5" can never end one because
    no whitespace follows its point.
    """
    clean = " ".join(str(text or "").split())
    depth = 0
    for index, char in enumerate(clean):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char in ".!?" and depth == 0:
            rest = clean[index + 1 :]
            if rest and not (rest[0] == " " and rest[1:2].isupper()):
                continue
            token = clean[: index + 1].rsplit(" ", 1)[-1].lstrip("(").casefold()
            if char == "." and token in _ABBREVIATIONS:
                continue
            return clean[: index + 1]
    return clean


def _is_adjective_like(word: str) -> bool:
    return word.casefold().strip(",;:").endswith(_ADJECTIVE_ENDINGS)


def _trim_words(text: str, drop_adjectives: bool) -> list[str]:
    words = text.rstrip(" ,;:-").split(" ")
    while len(words) > 1:
        last = words[-1].casefold().strip(",;:")
        if last in _DANGLING or (drop_adjectives and _is_adjective_like(last)):
            words.pop()
            continue
        break
    return words


def _end_clause(text: str, drop_adjectives: bool = False) -> str:
    """Trim a cut back to a word that can end a clause, then close it."""
    return " ".join(_trim_words(text, drop_adjectives)).rstrip(" ,;:-") + "."


def _comma_cut(body: str, limit: int) -> str | None:
    """The latest comma cut inside *limit* that does not end on a modifier."""
    cut = body.rfind(",", 0, limit)
    while cut >= _MIN_CUT_CHARS:
        words = _trim_words(body[:cut], drop_adjectives=False)
        if not _is_adjective_like(words[-1]):
            return " ".join(words).rstrip(" ,;:-") + "."
        cut = body.rfind(",", 0, cut)
    return None


def summarise(description: str, max_chars: int = SUMMARY_MAX_CHARS) -> str:
    """The card's one sentence: the first sentence, capped at *max_chars*.

    Within the cap it is returned as O*NET wrote it.  Over the cap it is cut, in
    this order of preference, and always closed with a period:

    1. at the last semicolon inside the cap -- O*NET separates whole clauses
       with them ("Plan and direct X; or coordinate Y");
    2. with its parentheticals dropped, if that alone brings it inside the cap;
    3. just before its examples ("..., such as", "including") -- the duty is
       kept whole and only the list is dropped;
    4. at the last comma inside the cap that does not leave a modifier
       stranded ("of biological, agricultural" has lost its noun);
    5. at the last word boundary inside the cap.

    Each cut is backed off any dangling word ("and", "such as", "of"), so no
    summary ends mid-clause, and none carries an ellipsis.
    """
    sentence = first_sentence(description)
    if len(sentence) <= max_chars:
        return sentence

    body = sentence.rstrip(".!?")
    limit = max_chars - 1  # room for the closing period

    cut = body.rfind(";", 0, limit)
    if cut >= _MIN_CUT_CHARS:
        return _end_clause(body[:cut])

    bare = " ".join(_PARENTHETICAL.sub("", body).split())
    if len(bare) + 1 <= max_chars:
        return bare + "."
    body = bare

    examples = [m.start() for m in _EXAMPLES.finditer(body, 0, limit)]
    if examples and examples[-1] >= _MIN_CUT_CHARS:
        return _end_clause(body[: examples[-1]])

    by_comma = _comma_cut(body, limit)
    if by_comma is not None:
        return by_comma

    cut = body.rfind(" ", 0, limit)
    return _end_clause(body[: cut if cut > 0 else limit], drop_adjectives=True)


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SummariesTable:
    """``{onet_code: summary}``, as the scorer reads it."""

    summaries: Mapping[str, str]
    source: str = ""
    built_at: str = ""
    path: Path | None = None

    @property
    def count(self) -> int:
        return len(self.summaries)

    def for_code(self, code: str) -> str:
        return self.summaries.get(code, "")


def build_table(
    rows: Iterable[Mapping[str, Any]],
    *,
    source: str = "",
    max_chars: int = SUMMARY_MAX_CHARS,
) -> SummariesTable:
    """One summary per retrievable ``*.documents.jsonl`` record.

    "..., All Other" rows are excluded -- retrieval never returns one, so no
    card can ever ask for its summary -- and so is a row with no description,
    which would otherwise be stored as an empty string that looks like a hit.
    """
    summaries: dict[str, str] = {}
    for row in rows:
        code = str(row.get("code") or "")
        title = str(row.get("title") or "")
        if not code or is_all_other_title(title):
            continue
        text = summarise(str(row.get("description") or ""), max_chars)
        if text:
            summaries[code] = text
    return SummariesTable(summaries=summaries, source=source, built_at=_utc_now_iso())


# ---------------------------------------------------------------------------
# The sidecar
# ---------------------------------------------------------------------------


def summaries_sidecar_path(matrix_path: str | os.PathLike[str]) -> Path:
    """The ``*.summaries.json`` that belongs beside *matrix_path*."""
    path = Path(matrix_path)
    return path.with_name(path.stem + ".summaries.json")


def write_summaries_sidecar(
    matrix_path: str | os.PathLike[str],
    table: SummariesTable,
) -> Path:
    """Write ``<artifact>.summaries.json`` beside *matrix_path*; return its path.

    Atomic, like the other sidecars: a reader sees the old file or the new one
    and never half of either.  ASCII-escaped for the reason
    ``occupation_fit.write_fit_sidecar`` gives: O*NET prose carries the odd
    non-ASCII character and these files are read on a cp1252 console.
    """
    path = summaries_sidecar_path(matrix_path)
    payload = {
        "schema_version": SUMMARIES_SCHEMA_VERSION,
        "matrix_filename": Path(matrix_path).name,
        "source": table.source,
        "built_at": table.built_at or _utc_now_iso(),
        "count": table.count,
        "max_chars": SUMMARY_MAX_CHARS,
        "summaries": dict(sorted(table.summaries.items())),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=0), encoding="utf-8")
    os.replace(tmp, path)
    return path


def _load_sidecar(path: Path) -> SummariesTable | None:
    """Read the sidecar, or return None if it is absent or unusable."""
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        version = raw.get("schema_version")
        if version != SUMMARIES_SCHEMA_VERSION:
            raise ValueError(
                f"summaries sidecar schema_version {version!r}, "
                f"expected {SUMMARIES_SCHEMA_VERSION}"
            )
        summaries = {
            str(code): str(text).strip()
            for code, text in (raw.get("summaries") or {}).items()
            if isinstance(text, str) and text.strip()
        }
    except (OSError, KeyError, ValueError, TypeError, AttributeError) as exc:
        _log.warning(
            "occupation summaries: ignoring unusable sidecar %s (%s); cards "
            "will open with no summary line",
            path,
            exc,
        )
        return None

    if not summaries:
        return None
    return SummariesTable(
        summaries=summaries,
        source=str(raw.get("source") or ""),
        built_at=str(raw.get("built_at") or ""),
        path=path,
    )


# ---------------------------------------------------------------------------
# Process-wide access
# ---------------------------------------------------------------------------

_LOCK = threading.Lock()
_TABLE: SummariesTable | None = None
_TABLE_FOR: str | None = None
_MISSING_LOGGED: set[str] = set()


def get_summaries(corpus: OccupationCorpus) -> SummariesTable | None:
    """The summaries table beside *corpus*, or None when there is no sidecar.

    Memoised per corpus version for the life of the process and lock-guarded,
    exactly as ``occupation_fit.get_fit_table`` is, and holding **one** table
    rather than one per version (``tests/test_cache_bounds.py`` asserts it).
    A missing file is logged once per corpus version.
    """
    global _TABLE, _TABLE_FOR

    key = corpus.version
    cached = _TABLE
    if cached is not None and _TABLE_FOR == key:
        return cached

    with _LOCK:
        if _TABLE is not None and _TABLE_FOR == key:
            return _TABLE
        path = summaries_sidecar_path(corpus.matrix_path)
        table = _load_sidecar(path)
        if table is None:
            if key not in _MISSING_LOGGED:
                _MISSING_LOGGED.add(key)
                _log.warning(
                    "no summaries sidecar beside %s; cards open with no summary "
                    "line.  Run `flask corpus summaries`",
                    corpus.matrix_path.name,
                )
            return None
        _TABLE, _TABLE_FOR = table, key
        _log.info(
            "occupation summaries: loaded %d occupations from %s",
            table.count,
            path.name,
        )
        return table


def summary_for(corpus: OccupationCorpus, code: str) -> str:
    """One occupation's summary; ``""`` when there is none."""
    table = get_summaries(corpus)
    return table.for_code(code) if table is not None else ""


def reset_summaries_cache() -> None:
    """Drop the memo.  Tests and the CLI; nothing in a request path."""
    global _TABLE, _TABLE_FOR
    with _LOCK:
        _TABLE, _TABLE_FOR = None, None
        _MISSING_LOGGED.clear()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
