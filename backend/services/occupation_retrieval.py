"""Retrieval over the precomputed O*NET occupation corpus (BUILD_PLAN F-3).

The seam between the artifact ``occupation_corpus.build_corpus`` writes and the
scorer F-4 rewrites.  It answers one question -- *"nearest occupations to this
vector"* -- as one exact dot product over a 6 MB float32 matrix.

WHY THERE IS NO INDEX
---------------------
1,016 x 1536 float32 is ~1.5M multiply-adds per query.  Measured end to end
through :meth:`OccupationCorpus.retrieve` on the real artifact, 2026-09-16, on
this laptop: **0.21 ms** at k=10, and **0.25 ms** with all three filters on.
The dot product is 0.11 ms of that and the sort is 0.03 ms; the rest is mask
construction and building the result objects.  An ANN index, pgvector, or any
other structure would trade exactness for a speedup two orders of magnitude
below the HTTP request it sits inside.  ``docs/PATH_INTELLIGENCE_REDESIGN.md``
§2.1 is the design of record and this is decided, not open.

LAZY, NOT AT BOOT
-----------------
The corpus loads on the **first retrieval**, memoised per process behind a lock.
It is deliberately not wired into ``create_app()``.

That factory runs in every gunicorn worker, in the Celery worker, and in every
``flask`` CLI process -- which includes the ``flask db upgrade`` pre-deploy step
and the ``flask outbox sweep`` cron that fires every five minutes.  Loading here
would put an S3 dependency on database migrations and a 6 MB download on a cron
job that never touches an occupation.  Boot-eager is a one-line addition
(``get_corpus()`` in the factory) if it is ever wanted; lazy is the reversible
direction.

The lock matters because gunicorn runs gthread: eight threads can reach the
first retrieval together, and without it each would decode its own 6 MB matrix.

FAIL SOFT, ALWAYS
-----------------
Nothing in this module raises at import or at ``create_app()``.  A missing,
unreadable or mismatched artifact becomes :class:`CorpusUnavailable` from
:func:`retrieve` / :func:`vector_for` / :func:`get_corpus`, logged once per
process, and the caller decides the fallback.  A service that had two OOM
incidents in eight days (2026-09-08, 2026-09-15) does not get a new boot-time
outage mode from this chunk.

A failed load is remembered for ``FAILURE_RETRY_SECONDS`` rather than forever:
an S3 blip at the wrong moment should cost five minutes of degraded
recommendations, not the lifetime of the worker.

THE THREE HARD FILTERS
----------------------
Hard means *applied to the candidate set*, never as a score penalty.  Each is a
named predicate with its own test.

a. **"..., All Other" rows** -- excluded from results by default,
   :func:`is_all_other_title`.  These are the SOC residual buckets ("Managers,
   All Other", "Engineers, All Other"): "all X not listed separately".  They
   are never a career suggestion -- nobody can become a Manager, All Other --
   and they cluster hard on their shared token, so they crowd real results out.

   **The criterion is the title suffix, not document length.**  Both were
   measured on the real 1,016-row artifact, 2026-09-16:

   =====================================  =====  =============================
   criterion                              rows   what it gets wrong
   =====================================  =====  =============================
   title ends ``", All Other"``             75   nothing found
   role document < 200 characters           57   misses 20 residuals, catches 2
                                                 real occupations
   =====================================  =====  =============================

   F-1's docstring counts 57 by document length, and that count is real but it
   is a **proxy**.  20 residual rows have genuine task lists and documents up
   to 2,084 characters ("Managers, All Other" is 1,746) -- length lets exactly
   the ones with the most semantic reach through.  Going the other way it
   catches "Dentists, All Other Specialists" and "First-Line Supervisors of Air
   Crew Members", which are real occupations that happen to be tersely
   documented.  Document length is also not a property of the catalog: it moves
   whenever ``MAX_TASKS`` or O*NET's prose changes, so a threshold tuned today
   silently re-scopes on the next quarterly rebuild.

   Contamination, measured over 200 random occupations' top-10 (seed 0):
   **27/200 before the filter, 0/200 after.**  (The overseer's 24/200 is the
   same measurement on a different sample; a SOC-residual-code rule --
   ``\\d{2}-\\d{3}9\\.00``, which is the title set plus "Dentists, All Other
   Specialists" -- yields an identical 27, so the extra row buys nothing.)

   ``vector_for`` still returns these rows.  F-4 needs an anchor vector for a
   user whose own resolved occupation is one of them.

b. **Job Zone ceiling** (``zone_max``), :func:`zone_within_ceiling`.  Zones are
   NOT in the corpus artifact; they live in a separate ``*.zones.json`` sidecar
   written by :func:`write_zone_sidecar` (``flask corpus zones``).  See that
   function for why it is a second file rather than a schema bump, and
   :func:`zone_within_ceiling` for what an unknown zone means.

   **The live range is 2-5, not 1-5.**  Measured 2026-09-16: O*NET v2 has
   merged Job Zones 1 and 2 into one band whose ``code`` is ``2`` and whose
   title is the range label "Job Zone 1-2: Very Little to Some Preparation
   Needed".  This is not an artefact of the bulk endpoint -- the
   per-occupation ``summary/job_zone`` route returns the same collapsed pair
   for Dishwashers and for Fast Food and Counter Workers.  No occupation in
   the catalog reports zone 1, so ``zone_max=1`` is always empty, and
   ``path_scoring``'s ``_zone_delta_score`` arithmetic (written against a 1-5
   scale) has one fewer step than it thinks.  F-4's problem, recorded here.

c. **SOC prefix / explicit-code exclusions** (``exclude_codes``,
   ``exclude_soc_prefixes``), :func:`soc_prefix_excluded`.  The mechanism only.
   ``path_scoring.py``'s hand-written allow-list is deliberately not ported --
   F-8 decides whether that list survives, with evidence, and building its
   semantics in here would prejudge that.

SOURCES
-------
``SOLVERAH_CORPUS_PATH`` first (a directory or an explicit ``.npy``), then S3.
Local wins because that is what dev and tests use and because a developer with
a local artifact should never be able to accidentally spend an S3 GET.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np

from backend.services.occupation_corpus import (
    EMBED_MODEL,
    SCHEMA_VERSION,
    RateLimiter,
)

_log = logging.getLogger(__name__)

__all__ = [
    "CorpusUnavailable",
    "FAILURE_RETRY_SECONDS",
    "Match",
    "OccupationCorpus",
    "ZONES_SCHEMA_VERSION",
    "clusters_sidecar_path",
    "fetch_job_zones",
    "get_corpus",
    "is_all_other_title",
    "load_corpus",
    "reset_corpus_cache",
    "resolve_matrix_path",
    "retrieve",
    "soc_prefix_excluded",
    "vector_for",
    "write_zone_sidecar",
    "zone_sidecar_path",
    "zone_within_ceiling",
]

#: Suffix that marks a SOC residual ("catch-all") occupation.  See the module
#: docstring for why this, and not document length, is the criterion.
ALL_OTHER_SUFFIX = ", All Other"

#: Sidecar schema version for the *zones* file.  Independent of
#: ``occupation_corpus.SCHEMA_VERSION`` because the two files are written by
#: different commands, at different times, and can legitimately be regenerated
#: independently -- zones change when O*NET re-rates an occupation, vectors
#: change when its prose does.
ZONES_SCHEMA_VERSION = 1

#: Page size for the catalog walk in :func:`fetch_job_zones`.  The catalog is
#: 1,016 occupations, so this is 11 requests.
OCCUPATIONS_PAGE_SIZE = 100

#: How long a failed load is remembered before the next retrieval retries it.
#:
#: Not forever: the S3 path can fail transiently and a worker that gave up
#: permanently would serve degraded recommendations until it was recycled, which
#: at ``max_requests = 2000`` on a low-traffic service is effectively never
#: (see ``docs/PATH_INTELLIGENCE_REDESIGN.md`` §1.3 on why that recycling is
#: inert here).  Not zero either: retrying on every request turns one outage
#: into an S3 call per page view.
FAILURE_RETRY_SECONDS = 300.0

#: Filenames the loader recognises when handed a directory.
_MATRIX_GLOB = "onet_corpus_*.npy"


class CorpusUnavailable(RuntimeError):
    """No usable corpus for this process, or none that answers the question.

    The single typed failure F-4 catches.  Raised for a missing artifact, an
    unreadable one, a schema or dimension mismatch, and for a ``zone_max``
    request when no zone sidecar was loaded -- one exception type means one
    fallback path in the caller rather than four.
    """


@dataclass(frozen=True)
class Match:
    """One ranked retrieval result."""

    code: str
    title: str
    score: float
    row: int


# ---------------------------------------------------------------------------
# The three hard-filter predicates
# ---------------------------------------------------------------------------


def is_all_other_title(title: str) -> bool:
    """True for a SOC residual bucket -- a title ending ``", All Other"``.

    Case- and whitespace-tolerant on the right edge only; O*NET is consistent
    here and a looser rule would catch "Dentists, All Other Specialists", which
    the module docstring explains is a real occupation to keep.
    """
    return title.rstrip().lower().endswith(ALL_OTHER_SUFFIX.lower())


def zone_within_ceiling(zone: int | None, zone_max: int | None) -> bool:
    """True when *zone* is allowed under a ``zone_max`` ceiling.

    ``zone_max=None`` allows everything, including rows with no recorded zone.

    With a ceiling set, an **unknown zone is excluded**.  A hard feasibility
    filter that cannot prove feasibility must not pass the row: recommending a
    career that needs years of licensure to someone who ruled that out is worse
    than recommending one fewer option.  And if zones were not loaded at all,
    :func:`OccupationCorpus.retrieve` raises rather than silently returning
    nothing, so "no zone data" and "nothing is feasible" never look alike.

    **Unknown is not rare, and the brief for this chunk assumed it would be.**
    Measured 2026-09-16 over the real catalog: ``/online/occupations`` carries a
    zone for **923 of 1,016** rows.  The 93 without one are 75 "..., All Other"
    residuals -- already gone by default -- plus 18 real occupations, 17 of
    which are the military group (SOC ``55-*``: Infantry, Air Crew Officers,
    ...) and the last of which is "Dentists, All Other Specialists".  So after
    the residual filter, a zone ceiling silently costs 18 of 941 retrievable
    rows, nearly all of them military.  If F-7 ever wants ``55-*`` reachable
    under a ceiling it needs a zone for them, not a change here.
    """
    if zone_max is None:
        return True
    if zone is None:
        return False
    return zone <= zone_max


def soc_prefix_excluded(code: str, prefixes: Sequence[str]) -> bool:
    """True when *code* starts with any of *prefixes* (e.g. ``("15-", "29-1")``).

    Plain prefix matching over the O*NET-SOC code, which is hierarchical by
    construction: ``15-`` is the major group, ``15-12`` a minor group,
    ``15-1252`` a broad occupation.  One mechanism covers every level, so there
    is no separate "major group" concept to keep in step.
    """
    return any(code.startswith(p) for p in prefixes)


# ---------------------------------------------------------------------------
# The loaded corpus
# ---------------------------------------------------------------------------


@dataclass
class OccupationCorpus:
    """A loaded artifact: the matrix, its index, and the optional zone sidecar.

    The matrix is L2-normalised and marked read-only, so cosine is a plain dot
    product and no caller can corrupt the copy every other thread is sharing.
    """

    version: str
    model: str
    dimensions: int
    codes: tuple[str, ...]
    titles: tuple[str, ...]
    matrix: np.ndarray
    matrix_path: Path
    zones: dict[str, int]
    zones_path: Path | None = None

    def __post_init__(self) -> None:
        self._row_by_code: dict[str, int] = {
            code: i for i, code in enumerate(self.codes)
        }
        self._all_other: np.ndarray = np.array(
            [is_all_other_title(t) for t in self.titles], dtype=bool
        )
        self._zone_by_row: np.ndarray = np.array(
            [self.zones.get(code, -1) for code in self.codes], dtype=np.int16
        )
        self._codes_array: np.ndarray = np.array(self.codes)

    # -- index -------------------------------------------------------------

    @property
    def count(self) -> int:
        return len(self.codes)

    @property
    def zones_available(self) -> bool:
        return bool(self.zones)

    @property
    def all_other_count(self) -> int:
        """How many rows the default result filter removes."""
        return int(self._all_other.sum())

    def index_of(self, code: str) -> int | None:
        """Row index for *code*, or ``None`` if the corpus does not carry it."""
        return self._row_by_code.get(code)

    def vector_for(self, code: str) -> np.ndarray:
        """Return the unit vector for *code*, **including filtered rows**.

        ``retrieve`` will not return a "..., All Other" row, but a user whose
        own occupation resolves to one still needs an anchor to retrieve
        *from*.  Filtering results and refusing to look up a vector are
        different questions and this module only conflates them deliberately.

        A writable copy, not a view: the matrix is shared and read-only, and
        F-6's Rocchio update does arithmetic on whatever it is handed.

        Raises:
            KeyError: If *code* is not in the corpus.  This is a lookup miss,
                not a corpus failure, so it is not ``CorpusUnavailable``.
        """
        row = self._row_by_code.get(code)
        if row is None:
            raise KeyError(f"{code} is not in corpus {self.version}")
        return np.array(self.matrix[row], dtype=np.float32)

    # -- retrieval ---------------------------------------------------------

    def retrieve(
        self,
        query_vec: Sequence[float] | np.ndarray,
        k: int = 10,
        *,
        exclude_codes: Iterable[str] = (),
        exclude_soc_prefixes: Sequence[str] = (),
        zone_max: int | None = None,
        include_all_other: bool = False,
    ) -> list[Match]:
        """Return the *k* nearest occupations to *query_vec*, best first.

        One ``matrix @ query``.  Exact cosine, because both sides are unit
        vectors -- the artifact is normalised on write and the query is
        normalised here if it is not already.

        Filters are **hard**: an excluded row cannot appear at any rank and
        contributes no score.  They are implemented by masking scores to
        ``-inf`` before the sort rather than by slicing the matrix, which is
        the same ranking and avoids copying 6 MB per query.

        Args:
            query_vec: A ``dimensions``-length vector.  Normalised if needed.
            k: How many results to return.  Fewer come back when fewer rows
                survive the filters.
            exclude_codes: Exact O*NET codes to drop -- typically the user's
                own occupation, and F-6's already-shown probes.
            exclude_soc_prefixes: SOC code prefixes to drop, e.g. ``("15-",)``
                for F-7's "a different major group" constraint.
            zone_max: Job Zone ceiling.  See :func:`zone_within_ceiling`.
            include_all_other: Keep the SOC residual buckets in the results.
                Off by default; see the module docstring.

        Raises:
            ValueError: On a wrong-length query, a zero query, or ``k < 1``.
            CorpusUnavailable: If ``zone_max`` is set but no zone sidecar was
                loaded.  Silently returning an unfiltered list would hand the
                caller results that violate the constraint it asked for;
                silently returning nothing would look like "no matches".
        """
        if k < 1:
            raise ValueError("k must be at least 1")
        if zone_max is not None and not self.zones_available:
            raise CorpusUnavailable(
                "zone_max was requested but no job-zone sidecar is loaded "
                f"for corpus {self.version}; run `flask corpus zones` and put "
                f"the .zones.json next to {self.matrix_path.name}"
            )

        query = self._as_unit_query(query_vec)
        scores = self.matrix @ query

        allowed = np.ones(self.count, dtype=bool)
        if not include_all_other:
            allowed &= ~self._all_other
        if zone_max is not None:
            allowed &= (self._zone_by_row >= 0) & (self._zone_by_row <= zone_max)
        for code in exclude_codes:
            row = self._row_by_code.get(code)
            if row is not None:
                allowed[row] = False
        for prefix in exclude_soc_prefixes:
            # ``np.strings.startswith`` over the precomputed code array rather
            # than :func:`soc_prefix_excluded` per row.  Measured 2026-09-16 on
            # the real 1,016-row corpus: 0.006 ms vectorised against 0.44 ms as
            # a Python comprehension -- four times the cost of the dot product
            # this whole module exists to make cheap.  The predicate stays the
            # statement of the rule and
            # ``test_the_vectorised_prefix_mask_agrees_with_the_named_predicate``
            # pins the two together.
            allowed &= ~np.strings.startswith(self._codes_array, prefix)

        survivors = int(allowed.sum())
        if survivors == 0:
            return []

        masked = np.where(allowed, scores, -np.inf)
        # A full stable argsort, not argpartition: 1,016 floats sort in tens of
        # microseconds, and stability makes ties resolve by row order -- which
        # is catalog order -- so the same query returns the same list every
        # time.  A flaky top-10 under ties would be untestable and would look
        # like a scoring bug from the frontend.
        order = np.argsort(-masked, kind="stable")[: min(k, survivors)]
        return [
            Match(
                code=self.codes[i],
                title=self.titles[i],
                score=float(scores[i]),
                row=int(i),
            )
            for i in order.tolist()
        ]

    def _as_unit_query(self, query_vec: Sequence[float] | np.ndarray) -> np.ndarray:
        query = np.asarray(query_vec, dtype=np.float32).reshape(-1)
        if query.shape[0] != self.dimensions:
            raise ValueError(
                f"query has {query.shape[0]} dimensions, corpus "
                f"{self.version} has {self.dimensions}"
            )
        if not np.all(np.isfinite(query)):
            raise ValueError("query contains NaN or infinity")
        norm = float(np.linalg.norm(query))
        if norm == 0.0:
            raise ValueError("query vector is all zeros; cosine is undefined")
        if abs(norm - 1.0) > 1e-4:
            query = query / norm
        return query


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def resolve_matrix_path(source: str | os.PathLike[str]) -> Path:
    """Resolve *source* to a ``.npy`` path.

    *source* may be the ``.npy`` itself or a directory holding one or more
    ``onet_corpus_<version>.npy``.  A directory resolves to the **highest
    version by filename**, which is newest: versions are UTC build dates
    (``occupation_corpus.default_version``) so lexical and chronological order
    are the same thing.

    Raises:
        CorpusUnavailable: If nothing matches.
    """
    path = Path(source)
    if path.is_dir():
        candidates = sorted(path.glob(_MATRIX_GLOB))
        if not candidates:
            raise CorpusUnavailable(f"no {_MATRIX_GLOB} in {path}")
        return candidates[-1]
    if path.suffix != ".npy":
        raise CorpusUnavailable(f"{path} is not a .npy or a directory")
    if not path.is_file():
        raise CorpusUnavailable(f"{path} does not exist")
    return path


def clusters_sidecar_path(matrix_path: str | os.PathLike[str]) -> Path:
    """The ``*.clusters.json`` that belongs beside *matrix_path*.

    **A deliberate duplicate of** ``occupation_clusters.cluster_sidecar_path``,
    which is the owner of that name and of the file's meaning.  This module
    cannot import it: ``occupation_clusters`` imports ``OccupationCorpus`` and
    ``is_all_other_title`` from here, so the dependency runs one way only and
    importing back would make it a cycle.  Six lines of duplicated path
    arithmetic is the cheaper of the two, and
    ``test_the_two_cluster_sidecar_path_helpers_agree`` fails if they drift.

    Why this module needs the name at all (F-8 box 9): ``_fetch_from_s3`` has
    to download the cluster sidecar alongside the matrix and the zones.  Before
    it did, every worker on the S3 path -- i.e. all of production -- found no
    sidecar, fell back to ``occupation_clusters``' in-process k-means, and paid
    a 0.7 s fit **and** the scikit-learn import, per worker, on a 512 MB dyno
    that OOMed on 2026-09-15.
    """
    path = Path(matrix_path)
    return path.with_name(path.stem + ".clusters.json")


def zone_sidecar_path(matrix_path: str | os.PathLike[str]) -> Path:
    """The ``*.zones.json`` that belongs beside *matrix_path*."""
    path = Path(matrix_path)
    return path.with_name(path.stem + ".zones.json")


def _sidecar_path(matrix_path: Path) -> Path:
    return matrix_path.with_suffix(".json")


def _load_zones(path: Path) -> tuple[dict[str, int], Path | None]:
    """Read the optional zone sidecar.

    A missing file is normal -- the reviewed 2026-09-16 artifact ships without
    one -- and yields no zones, which makes ``zone_max`` raise rather than
    silently pass everything.

    A *malformed* one is logged and treated as absent rather than failing the
    whole load, which is a deliberate departure from how the main sidecar is
    validated: the corpus is still perfectly usable for every retrieval that
    does not ask for a zone ceiling, and the one that does gets a loud
    ``CorpusUnavailable`` naming the sidecar.  Failing the corpus over an
    optional file would turn a degraded filter into a total outage.
    """
    if not path.is_file():
        return {}, None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        version = raw.get("schema_version")
        if version != ZONES_SCHEMA_VERSION:
            raise ValueError(
                f"zone sidecar schema_version {version!r}, "
                f"expected {ZONES_SCHEMA_VERSION}"
            )
        zones = {
            str(code): int(zone)
            for code, zone in (raw.get("zones") or {}).items()
            if zone is not None
        }
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        _log.warning(
            "occupation corpus: ignoring unusable zone sidecar %s (%s); "
            "zone_max retrieval will refuse until it is rebuilt",
            path,
            exc,
        )
        return {}, None
    if not zones:
        return {}, None
    return zones, path


def load_corpus(source: str | os.PathLike[str] | None = None) -> OccupationCorpus:
    """Load an artifact from *source*, or from the configured sources.

    Not memoised -- :func:`get_corpus` is the memoised entry point.  Exposed
    so tests and one-off scripts can load an explicit artifact without
    touching process state.

    Validation is strict on everything that would make a cosine meaningless:
    ``schema_version``, ``dimensions`` against the matrix's real second axis,
    and the code/title arrays against its row count.  A mismatch is a load
    failure, not a warning -- a corpus built with a different embedding model
    still returns plausible-looking numbers for every query, which is the
    hardest failure of all to notice downstream.

    Raises:
        CorpusUnavailable: On any failure to produce a trustworthy corpus.
    """
    matrix_path = (
        resolve_matrix_path(source) if source is not None else _resolve_configured()
    )
    sidecar_path = _sidecar_path(matrix_path)
    if not sidecar_path.is_file():
        raise CorpusUnavailable(f"sidecar {sidecar_path} is missing")

    try:
        meta: dict[str, Any] = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CorpusUnavailable(f"sidecar {sidecar_path} is unreadable: {exc}") from exc

    schema_version = meta.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise CorpusUnavailable(
            f"sidecar {sidecar_path.name} declares schema_version "
            f"{schema_version!r}; this build reads {SCHEMA_VERSION}"
        )

    declared_dims = meta.get("dimensions")
    if not isinstance(declared_dims, int) or declared_dims < 1:
        raise CorpusUnavailable(
            f"sidecar {sidecar_path.name} declares dimensions {declared_dims!r}"
        )

    try:
        matrix = np.load(matrix_path, allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise CorpusUnavailable(f"{matrix_path} is unreadable: {exc}") from exc

    if matrix.ndim != 2:
        raise CorpusUnavailable(
            f"{matrix_path.name} has shape {matrix.shape}; expected 2 dimensions"
        )
    if matrix.shape[1] != declared_dims:
        raise CorpusUnavailable(
            f"{matrix_path.name} has {matrix.shape[1]} dimensions but its "
            f"sidecar declares {declared_dims}"
        )

    codes = [str(c) for c in meta.get("codes") or []]
    titles = [str(t) for t in meta.get("titles") or []]
    if len(codes) != matrix.shape[0] or len(titles) != matrix.shape[0]:
        raise CorpusUnavailable(
            f"{sidecar_path.name} indexes {len(codes)} codes / {len(titles)} "
            f"titles against {matrix.shape[0]} matrix rows"
        )

    matrix = np.ascontiguousarray(matrix, dtype=np.float32)
    if not meta.get("normalised"):
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        matrix = (matrix / norms).astype(np.float32)
    # Shared across every thread in the process; a caller that mutates it
    # corrupts every subsequent query instead of failing its own.
    matrix.setflags(write=False)

    zones, zones_path = _load_zones(zone_sidecar_path(matrix_path))
    return OccupationCorpus(
        version=str(meta.get("version") or matrix_path.stem),
        model=str(meta.get("model") or EMBED_MODEL),
        dimensions=int(declared_dims),
        codes=tuple(codes),
        titles=tuple(titles),
        matrix=matrix,
        matrix_path=matrix_path,
        zones=zones,
        zones_path=zones_path,
    )


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


def _corpus_cache_dir() -> Path:
    configured = os.environ.get("SOLVERAH_CORPUS_CACHE_DIR")
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / "solverah-corpus-cache"


def _resolve_configured() -> Path:
    """Find an artifact from the environment: local path first, then S3."""
    local = os.environ.get("SOLVERAH_CORPUS_PATH")
    if local:
        return resolve_matrix_path(local)
    return _fetch_from_s3()


def _fetch_from_s3() -> Path:
    """Download the artifact into the local cache once, then reuse it.

    The **app** bucket (``S3_BUCKET_NAME``), never the backup bucket --
    ``solverah/config.py`` refuses that pairing by design and this refuses it
    again rather than trusting a boot-time validator it does not run under
    (the Celery worker and the CLI reach this code too).

    The client is ``solverah.infra.storage.get_s3_client``, not a fresh
    ``boto3.client``: that factory carries the 3s connect / 10s read / 3-attempt
    bounds that are the only thing stopping an unresponsive R2 from holding a
    request thread for ten minutes, and ``tests/test_storage_client_config.py``
    guards the tree against a second unbounded client.

    Imported lazily so this module stays importable with no S3 environment at
    all, which is how every test that does not exercise S3 runs.
    """
    key = os.environ.get("SOLVERAH_CORPUS_S3_KEY")
    bucket = (os.environ.get("S3_BUCKET_NAME") or "").strip()
    if not key:
        raise CorpusUnavailable(
            "no corpus source: set SOLVERAH_CORPUS_PATH to a local artifact "
            "or SOLVERAH_CORPUS_S3_KEY to an object in S3_BUCKET_NAME"
        )
    if not bucket:
        raise CorpusUnavailable(
            "SOLVERAH_CORPUS_S3_KEY is set but S3_BUCKET_NAME is empty"
        )
    backup_bucket = (os.environ.get("BACKUP_S3_BUCKET_NAME") or "").strip()
    if backup_bucket and bucket == backup_bucket:
        raise CorpusUnavailable(
            "S3_BUCKET_NAME equals BACKUP_S3_BUCKET_NAME; the corpus is an "
            "application artifact and is never read from the backup bucket"
        )
    if not key.endswith(".npy"):
        raise CorpusUnavailable(f"SOLVERAH_CORPUS_S3_KEY {key!r} is not a .npy")

    cache_dir = _corpus_cache_dir()
    matrix_path = cache_dir / Path(key).name
    sidecar_path = _sidecar_path(matrix_path)
    stem_key = key[: -len(".npy")]

    #: The optional sidecars, as ``(what, key, local path)``.  Each is fetched
    #: best-effort and separately from the artifact, because each is written on
    #: its own cadence by its own CLI command and any of them can land after a
    #: worker has already cached the matrix.
    optional = [
        ("zone", stem_key + ".zones.json", zone_sidecar_path(matrix_path)),
        ("cluster", stem_key + ".clusters.json", clusters_sidecar_path(matrix_path)),
    ]

    from solverah.infra import storage  # noqa: PLC0415 -- see docstring

    if matrix_path.is_file() and sidecar_path.is_file():
        _log.debug("occupation corpus: reusing cached artifact %s", matrix_path)
        missing = [row for row in optional if not row[2].is_file()]
        if missing:
            # A sidecar is uploaded separately and can appear after a worker has
            # already cached the matrix.  One attempt per process load -- not
            # per query -- so a corpus that genuinely has neither costs two
            # 404s, and one that gained them does not stay degraded until
            # somebody clears the cache directory.
            client = storage.get_s3_client()
            for what, sidecar_key, target in missing:
                _try_download_optional(client, bucket, sidecar_key, target, what)
        return matrix_path

    client = storage.get_s3_client()
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        _download(client, bucket, key, matrix_path)
        _download(client, bucket, stem_key + ".json", sidecar_path)
    except Exception as exc:  # botocore raises a wide family; all are fatal here
        matrix_path.unlink(missing_ok=True)
        sidecar_path.unlink(missing_ok=True)
        raise CorpusUnavailable(
            f"could not fetch corpus {key} from {bucket}: {exc}"
        ) from exc
    for what, sidecar_key, target in optional:
        _try_download_optional(client, bucket, sidecar_key, target, what)

    _log.info("occupation corpus: cached %s from %s", key, bucket)
    return matrix_path


def _try_download_optional(
    client: Any, bucket: str, key: str, target: Path, what: str
) -> None:
    """Fetch one optional sidecar; its absence is a normal case, never fatal."""
    try:
        _download(client, bucket, key, target)
    except Exception as exc:  # noqa: BLE001 -- optional file, never fatal
        _log.info("occupation corpus: no %s sidecar at %s (%s)", what, key, exc)


def _download(client: Any, bucket: str, key: str, target: Path) -> None:
    """Fetch one object to *target*, via a temp file so a partial never loads.

    ``get_object`` streamed rather than ``download_file``: R2 is reached
    through the same client for every other object in this codebase, and
    ``download_file``'s transfer manager spawns its own threads on a request
    thread that is already one of eight.
    """
    body = client.get_object(Bucket=bucket, Key=key)["Body"]
    tmp = target.with_suffix(target.suffix + ".part")
    try:
        with tmp.open("wb") as fh:
            for chunk in iter(lambda: body.read(1024 * 1024), b""):
                fh.write(chunk)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
        close = getattr(body, "close", None)
        if close is not None:
            close()


# ---------------------------------------------------------------------------
# Process-wide memoisation
# ---------------------------------------------------------------------------

_LOCK = threading.Lock()
_CORPUS: OccupationCorpus | None = None
#: The last failure's *message*, not the exception object.  Re-raising one
#: instance appends a frame to its ``__traceback__`` on every raise, so a
#: five-minute cooldown on a busy worker would accumulate thousands of live
#: frame references -- a slow leak of exactly the shape that took this service
#: down twice in September.  A fresh exception per call costs nothing.
_FAILURE: str | None = None
_FAILURE_AT: float = 0.0
_FAILURE_LOGGED = False


def get_corpus() -> OccupationCorpus:
    """Return the process's corpus, loading it on first call.

    Double-checked under a lock so eight gthread threads arriving together
    decode one 6 MB matrix rather than eight.  Failures are memoised for
    :data:`FAILURE_RETRY_SECONDS` and logged **once** per process -- a
    per-request log line for a missing artifact is how a degraded feature
    becomes a log-volume incident.

    Raises:
        CorpusUnavailable: If no source yields a trustworthy artifact.
    """
    global _CORPUS, _FAILURE, _FAILURE_AT, _FAILURE_LOGGED

    corpus = _CORPUS
    if corpus is not None:
        return corpus

    with _LOCK:
        if _CORPUS is not None:
            return _CORPUS
        if (
            _FAILURE is not None
            and time.monotonic() - _FAILURE_AT < FAILURE_RETRY_SECONDS
        ):
            raise CorpusUnavailable(_FAILURE)
        try:
            _CORPUS = load_corpus()
        except CorpusUnavailable as exc:
            _FAILURE, _FAILURE_AT = str(exc), time.monotonic()
            if not _FAILURE_LOGGED:
                _FAILURE_LOGGED = True
                _log.warning(
                    "occupation corpus unavailable; retrieval will fail soft "
                    "until an artifact is reachable: %s",
                    exc,
                )
            raise
        except Exception as exc:  # an unexpected shape is still fail-soft
            wrapped = CorpusUnavailable(f"corpus load failed: {exc}")
            _FAILURE, _FAILURE_AT = str(wrapped), time.monotonic()
            if not _FAILURE_LOGGED:
                _FAILURE_LOGGED = True
                _log.exception("occupation corpus load raised unexpectedly")
            raise wrapped from exc
        _FAILURE, _FAILURE_LOGGED = None, False
        _log.info(
            "occupation corpus loaded: %s rows x %s dims from %s (zones: %s)",
            _CORPUS.count,
            _CORPUS.dimensions,
            _CORPUS.matrix_path,
            "yes" if _CORPUS.zones_available else "no",
        )
        return _CORPUS


def reset_corpus_cache() -> None:
    """Drop the memoised corpus and any remembered failure.

    For tests, and for a future ``flask corpus reload``.  Not called anywhere
    in the request path.
    """
    global _CORPUS, _FAILURE, _FAILURE_AT, _FAILURE_LOGGED
    with _LOCK:
        _CORPUS = None
        _FAILURE = None
        _FAILURE_AT = 0.0
        _FAILURE_LOGGED = False


def vector_for(code: str) -> np.ndarray:
    """Module-level :meth:`OccupationCorpus.vector_for` over the loaded corpus."""
    return get_corpus().vector_for(code)


def retrieve(
    query_vec: Sequence[float] | np.ndarray,
    k: int = 10,
    *,
    exclude_codes: Iterable[str] = (),
    exclude_soc_prefixes: Sequence[str] = (),
    zone_max: int | None = None,
    include_all_other: bool = False,
) -> list[Match]:
    """Module-level :meth:`OccupationCorpus.retrieve` over the loaded corpus."""
    return get_corpus().retrieve(
        query_vec,
        k,
        exclude_codes=exclude_codes,
        exclude_soc_prefixes=exclude_soc_prefixes,
        zone_max=zone_max,
        include_all_other=include_all_other,
    )


# ---------------------------------------------------------------------------
# The zone sidecar
# ---------------------------------------------------------------------------


def fetch_job_zones(
    onet_client: Any,
    limiter: RateLimiter | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> dict[str, int]:
    """Return ``{onet_code: job_zone}`` for the whole catalog, in ~11 requests.

    ``/online/occupations`` pages the entire catalog with a Job Zone on every
    record, so the alternative -- ``get_job_zone`` per occupation -- costs
    1,016 requests for the same data.

    *limiter* is ``occupation_corpus.RateLimiter``, the same process-wide gate
    the corpus build uses, so O*NET's 5 req/s threshold is respected by one
    mechanism rather than two that do not know about each other.  Pass the
    build's limiter when both run in one process.
    """
    zones: dict[str, int] = {}
    start = 1
    while True:
        if limiter is not None:
            limiter.acquire()
        page = onet_client.get_all_occupations(
            start=start, end=start + OCCUPATIONS_PAGE_SIZE - 1
        )
        for entry in page:
            zone = entry.get("zone")
            if entry.get("code") and zone is not None:
                zones[str(entry["code"])] = int(zone)
        if on_progress is not None:
            on_progress(f"job zones: {len(zones)} after page starting {start}")
        if len(page) < OCCUPATIONS_PAGE_SIZE:
            break
        start += OCCUPATIONS_PAGE_SIZE
    return zones


def write_zone_sidecar(
    matrix_path: str | os.PathLike[str],
    zones: dict[str, int],
) -> Path:
    """Write ``<artifact>.zones.json`` beside *matrix_path*; return its path.

    **A separate file, not a bump of the corpus sidecar's schema_version.**
    Three reasons, in order of weight:

    1. The ``.npy`` and its ``.json`` are the exact bytes Sebastian is
       reviewing for the S3 upload.  Rewriting either to add a field means the
       reviewed artifact and the shipped artifact are not the same file.
    2. The two datasets have different refresh reasons and different costs.
       Vectors change when O*NET's prose changes and cost ~3,070 requests and
       an OpenAI bill to rebuild; zones change when an occupation is re-rated
       and cost 11 requests.  Fusing them makes the cheap refresh pay the
       expensive one's price.
    3. Zones are an input to *one* hard filter, not to the geometry.  A corpus
       with no zone sidecar is a working corpus that cannot answer ``zone_max``
       -- which is exactly what :meth:`OccupationCorpus.retrieve` reports.

    Written atomically, like the corpus artifact: a reader is either seeing the
    old file or the new one, never half of either.
    """
    path = zone_sidecar_path(matrix_path)
    payload = {
        "schema_version": ZONES_SCHEMA_VERSION,
        "matrix_filename": Path(matrix_path).name,
        "source": "onet:/online/occupations",
        "built_at": _utc_now_iso(),
        "count": len(zones),
        "zones": {code: int(zone) for code, zone in sorted(zones.items())},
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    return path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
