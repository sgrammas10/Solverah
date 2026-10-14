"""Text checks the pipeline applies before anything is written: excerpt verification and
the paraphrase gate. Pure functions, no I/O.

Normalisation is scorer_pipeline's (dashes, smart quotes, whitespace), lifted rather
than imported so this module has no dependency on the research harness; the rules are
three lines and ``tests/test_company_research_pipeline.py`` pins them against the
harness's own cases.

**Excerpt verification** (review F1, 2026-10-13) is COVERAGE, not containment: an
excerpt is verified when at least ``VERIFY_MIN_COVERAGE`` of its words lie inside runs
of ``VERIFY_MIN_RUN_WORDS``+ consecutive words shared with the citations the caller
hands in -- and the caller hands in only the citations from the item's own source
(``research.py`` does that matching). An invented sentence wrapped around one real
fragment covers the fragment and fails; a real sentence with one corrected typo loses
one word and passes. Every quotation mark in the excerpt must be accounted for by the
cited text, so a fabricated quote around reported speech fails too.

**The paraphrase gate** (review F13): no shared run longer than ``shared_run_limit``
(seven words, or half the reference's length when that is shorter), no more than
``PARAPHRASE_MAX_TRIGRAM_REUSE`` of the reference's word trigrams reused, checked
against the excerpt AND every other citation from the same URL, and no quotation marks
at all. Rejection, not regeneration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from solverah.services.company_research.constants import (
    PARAPHRASE_MAX_SHARED_WORDS,
    PARAPHRASE_MAX_TRIGRAM_REUSE,
    VERIFY_MIN_CITED_CHARS,
    VERIFY_MIN_COVERAGE,
    VERIFY_MIN_RUN_WORDS,
)

__all__ = [
    "Verification",
    "count_quote_marks",
    "excerpt_coverage",
    "excerpt_is_verified",
    "has_quote_marks",
    "longest_shared_word_run",
    "normalize",
    "paraphrase_gate",
    "paraphrase_passes_gate",
    "shared_run_limit",
    "text_contains",
    "trigram_reuse",
    "verify_excerpt",
    "words",
]

_DASH_CHARS = "‒–—―‑"


def normalize(text: str) -> str:
    """scorer_pipeline._normalize: dashes to '-', smart quotes to straight, whitespace
    collapsed. Case is kept here; the word-run check lowers it."""
    out = text or ""
    for d in _DASH_CHARS:
        out = out.replace(d, "-")
    out = out.replace("‘", "'").replace("’", "'")
    out = out.replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", out).strip()


_WORD_RE = re.compile(r"[a-z0-9]+")


def words(text: str) -> list[str]:
    """Lower-cased alphanumeric tokens, punctuation dropped: the unit of the shared-run
    checks, so a copied clause is caught whether or not its commas survived."""
    return _WORD_RE.findall(normalize(text).lower())


def _run_table(wa: Sequence[str], wb: Sequence[str]) -> list:
    """dp[i][j] = length of the shared run ENDING at wa[i-1] / wb[j-1]."""
    table = [[0] * (len(wb) + 1) for _ in range(len(wa) + 1)]
    for i in range(1, len(wa) + 1):
        row, prev = table[i], table[i - 1]
        a = wa[i - 1]
        for j in range(1, len(wb) + 1):
            if a == wb[j - 1]:
                row[j] = prev[j - 1] + 1
    return table


def longest_shared_word_run(a: str, b: str) -> int:
    """Length of the longest run of consecutive words *a* and *b* have in common."""
    wa, wb = words(a), words(b)
    if not wa or not wb:
        return 0
    return max(max(row) for row in _run_table(wa, wb))


def _covered_positions(excerpt_words: Sequence[str], cited_words: Sequence[str],
                       min_run: int) -> set:
    """Positions in *excerpt_words* that sit inside a shared run of >= *min_run* words."""
    covered: set = set()
    if not excerpt_words or not cited_words:
        return covered
    table = _run_table(excerpt_words, cited_words)
    n, m = len(excerpt_words), len(cited_words)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            length = table[i][j]
            if length < min_run:
                continue
            # Only at a run's end (the next pair does not extend it): the whole run is
            # marked at once, so an inner cell never needs its own pass.
            if i < n and j < m and excerpt_words[i] == cited_words[j]:
                continue
            covered.update(range(i - length, i))
    return covered


def excerpt_coverage(excerpt: str, cited_texts: Iterable[str]) -> float:
    """The fraction of the excerpt's words covered by runs shared with ANY of the cited
    texts (union). 0.0 for an empty excerpt."""
    ew = words(excerpt)
    if not ew:
        return 0.0
    min_run = min(VERIFY_MIN_RUN_WORDS, len(ew))
    covered: set = set()
    for cited in cited_texts:
        if not cited:
            continue
        covered |= _covered_positions(ew, words(cited), min_run)
    return len(covered) / len(ew)


_QUOTE_CHARS = "\"“”„«»"


def count_quote_marks(text: str) -> int:
    """Double quotation marks in *text*, straight or typographic. Apostrophes are not
    counted: a possessive is not a quote."""
    return sum(1 for ch in (text or "") if ch in _QUOTE_CHARS)


_OPENING_SINGLE_RE = re.compile(r"(?:^|[\s(\[])['‘](?=\S)")


def has_quote_marks(text: str) -> bool:
    """Whether *text* carries any quotation mark: a double quote of any shape, or a
    single quote that OPENS a quotation (preceded by nothing, whitespace or a bracket
    and followed by a character). "managers' approval" and "don't" are not quotes;
    "'we move fast'" is."""
    if count_quote_marks(text):
        return True
    return bool(_OPENING_SINGLE_RE.search(text or ""))


@dataclass(frozen=True)
class Verification:
    verified: bool
    coverage: float
    #: 'ok', or why not: 'too_short', 'no_citation', 'coverage', 'quote_marks'.
    reason: str


def verify_excerpt(excerpt: str, cited_texts: Sequence[str]) -> Verification:
    """Whether *excerpt* is backed by the citations in *cited_texts* -- which must be
    the citations from the excerpt's OWN source; this function trusts that.

    (b) coverage >= VERIFY_MIN_COVERAGE over the union of the citations, and (d) every
    double quotation mark in the excerpt is matched by one in the cited text. (a) and
    (c) -- the citations come from the item's URL, and the URL was fetched or cited --
    are the caller's, because they need the call's sources.
    """
    e = normalize(excerpt)
    if len(e) < VERIFY_MIN_CITED_CHARS:
        return Verification(False, 0.0, "too_short")
    cited = [c for c in cited_texts if c and normalize(c)]
    if not cited:
        return Verification(False, 0.0, "no_citation")
    coverage = excerpt_coverage(e, cited)
    if coverage < VERIFY_MIN_COVERAGE:
        return Verification(False, coverage, "coverage")
    if count_quote_marks(e) > sum(count_quote_marks(normalize(c)) for c in cited):
        return Verification(False, coverage, "quote_marks")
    return Verification(True, coverage, "ok")


def excerpt_is_verified(excerpt: str, cited_texts: Iterable[str]) -> bool:
    """``verify_excerpt(...).verified`` for callers that only need the bool."""
    return verify_excerpt(excerpt, list(cited_texts)).verified


# ---------------------------------------------------------------------------
# The paraphrase gate
# ---------------------------------------------------------------------------

def shared_run_limit(reference: str) -> int:
    """The longest run of consecutive words a paraphrase may share with *reference*:
    min(PARAPHRASE_MAX_SHARED_WORDS, floor(words / 2))."""
    return min(PARAPHRASE_MAX_SHARED_WORDS, len(words(reference)) // 2)


def _trigrams(ws: Sequence[str]) -> set:
    return {tuple(ws[i:i + 3]) for i in range(len(ws) - 2)}


def trigram_reuse(reference: str, paraphrase: str) -> float:
    """The fraction of *reference*'s word trigrams that also appear in *paraphrase*.
    0.0 when the reference has fewer than three words."""
    ref = _trigrams(words(reference))
    if not ref:
        return 0.0
    return len(ref & _trigrams(words(paraphrase))) / len(ref)


def paraphrase_gate(excerpt: str, paraphrase: str,
                    references: Sequence[str] = ()) -> Optional[str]:
    """None when *paraphrase* passes; otherwise why it was rejected: 'empty',
    'quote_marks', 'identical', 'shared_run' or 'trigram_reuse'.

    *references* are the other cited texts from the same URL: a paraphrase that copies
    a different sentence of the page than its excerpt is still a quote on a page.
    """
    if not paraphrase or not paraphrase.strip():
        return "empty"
    if has_quote_marks(paraphrase):
        return "quote_marks"
    p_norm = normalize(paraphrase).lower()
    for reference in (excerpt, *references):
        if not reference or not reference.strip():
            continue
        if p_norm == normalize(reference).lower():
            return "identical"
        if longest_shared_word_run(reference, paraphrase) > shared_run_limit(reference):
            return "shared_run"
        if trigram_reuse(reference, paraphrase) > PARAPHRASE_MAX_TRIGRAM_REUSE:
            return "trigram_reuse"
    return None


def paraphrase_passes_gate(excerpt: str, paraphrase: str,
                           references: Sequence[str] = ()) -> bool:
    """``paraphrase_gate(...) is None``. GAP-14: the paraphrase is the only text a user
    sees, so a copied clause inside it is a verbatim quote on a page."""
    return paraphrase_gate(excerpt, paraphrase, references) is None


# ---------------------------------------------------------------------------
# Posting-side containment
# ---------------------------------------------------------------------------

def text_contains(haystack: str, needle: str) -> bool:
    """Normalised, case-insensitive containment with the same length floor -- the
    posting-side verifier, where the whole source text is in hand."""
    n = normalize(needle)
    if len(n) < VERIFY_MIN_CITED_CHARS:
        return False
    return n.lower() in normalize(haystack).lower()


def first_or_none(values: Sequence[Optional[str]]) -> Optional[str]:
    for value in values:
        if value:
            return value
    return None
