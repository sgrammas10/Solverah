"""k-means over the occupation corpus -- the ``fresh_start`` seed (BUILD_PLAN F-7).

WHAT THIS IS FOR
----------------
``fresh_start`` has nothing to probe around: the user is asking to leave their
field, so the one vector every other intent retrieves from is the one thing they
have ruled out.  Design doc §3.3's answer is to seed the first page with a
**maximally diverse spanning set** -- one occupation per cluster of the corpus
-- and let F-6's feedback loop rotate the query toward whatever they tap.  This
module owns the clustering half of that.

**The trap it must not fall into is rewarding distance.**  Nothing here scores
anything.  It answers one question -- "which region of the corpus is this
occupation in" -- and ``path_scoring`` uses the answer only to stop ten cards
from being ten variations of the same job.  Which cards are eligible at all is
decided by the hard filters (feasibility, own field, transferable skill) and
their order by the query; a cluster label is never a reason to prefer a row.

WHY THE RESIDUAL BUCKETS ARE CLUSTERED OUT, WHICH IS A MEASUREMENT
------------------------------------------------------------------
The 75 "..., All Other" rows are ~50-character title-only documents, and
measured on the real artifact they form **their own cluster** -- at k=12 a
58-row cluster whose median document is 52 characters against ~2,000 for every
other cluster.  That is the "clusters on document length rather than
occupational domain" failure F-7's brief asks to look for, and it is real: with
them in, cluster identity explains 38% of document-length variance; with them
out, 12-13%.  It would also waste a whole seed slot, because ``retrieve``
filters those rows from every result anyway.  So the fit runs over the
**retrievable** rows only.

What is left really is occupational domain.  Measured over 941 retrievable rows
at the shipped k=8: mean SOC-major-group purity **0.486** against a 0.114 base
rate (0.547 at k=10), and the eight nearest-centroid triples read as
science/IT, transport and equipment operation, education, management and
marketing, office/clerical, engineering, production and skilled trades, and
healthcare.  `tests/test_occupation_clusters.py` asserts the purity against its
own base rate rather than against a pinned number, so a corpus rebuild that
degraded the partition would fail rather than drift.

SIDECAR FIRST, IN-PROCESS FALLBACK
----------------------------------
The assignment is precomputed into ``<artifact>.clusters.json`` by ``flask
corpus clusters``, exactly as the Job Zones are (``occupation_retrieval
.write_zone_sidecar``), for three reasons:

1. **scikit-learn never has to be imported on the request path.**  The dyno is
   512 MB and OOMed on 2026-09-15; the scientific stack is the largest single
   contributor to worker RSS in this process.  Reading a 30 KB JSON file costs
   nothing, and the import inside :func:`compute_assignment` is deliberately
   lazy so that a process serving a sidecar never pays it.
2. **Reproducible across workers.**  ``KMeans(random_state=0)`` is
   deterministic for one build of scikit-learn on one machine (verified), so
   "deterministic" is a promise about a version rather than about the
   algorithm.  Two workers that disagree about cluster identity would show two
   different first pages for the same user on alternate requests.  A file
   cannot disagree with itself.

   F-8 box 10 closes the version half of that: the sidecar records the
   scikit-learn and numpy versions that fitted it, and :func:`_load_sidecar`
   refits rather than trusting a file it cannot reproduce.  See
   :func:`library_versions`, including the measurement that says the 1.7.2 ->
   1.9.0 bump this repo just made did **not** move a single row.
3. It is the pattern already established for data that is derived from the
   artifact but is not the artifact.

The fallback is a per-process memo: if no sidecar is present, the fit runs once
(0.7 s over 941 rows) and is cached for the life of the process.  That keeps
``fresh_start`` working on a machine that has the corpus but not the sidecar --
including, today, the S3 path, because ``occupation_retrieval._fetch_from_s3``
downloads the matrix and the zone sidecar and nothing else, and that module is
F-3's to change.  **For F-8:** when the artifact is uploaded, upload the
clusters sidecar with it and teach the S3 fetch to pull it, or every production
worker pays the fit and the import.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import numpy as np

from backend.services.occupation_retrieval import (
    OccupationCorpus,
    is_all_other_title,
)

_log = logging.getLogger(__name__)

__all__ = [
    "CLUSTER_COUNT",
    "CLUSTERS_SCHEMA_VERSION",
    "ClusterAssignment",
    "RANDOM_STATE",
    "SKLEARN_DISTRIBUTION",
    "cluster_sidecar_path",
    "compute_assignment",
    "diverse_seed",
    "get_assignment",
    "library_versions",
    "reset_cluster_cache",
    "write_cluster_sidecar",
]

#: Bumped 1 -> 2 in F-8 box 10: the sidecar now records the versions of the
#: libraries that produced it.  A v1 file cannot answer "which scikit-learn
#: fitted this", so it is refitted rather than trusted -- which is the same
#: answer the version check would give it anyway, reached one step earlier.
CLUSTERS_SCHEMA_VERSION = 2

#: The distribution name to read the running scikit-learn version from.
#:
#: Read through ``importlib.metadata`` and **never** by importing ``sklearn``.
#: The entire reason this sidecar exists is that a worker serving one must not
#: pay for the scientific stack's RSS; a version check that imported the
#: library to find its version would defeat the file it is checking.
#: ``importlib.metadata.version`` reads the installed distribution's metadata
#: off disk and leaves ``sys.modules`` untouched -- asserted by
#: ``test_reading_a_sidecar_does_not_import_sklearn``.
SKLEARN_DISTRIBUTION = "scikit-learn"

#: How many regions the corpus is cut into.
#:
#: Design doc §3.3 says 8-10.  Measured on the F-2 harness -- macro nDCG@10 of
#: the zero-tap ``fresh_start`` page over four profiles:
#:
#:     k        6        8       10       12
#:     nDCG   0.2297   0.2420   0.2200   0.2470
#:
#: a 0.027 spread at n=4, which is noise and which F-2's sample-size rule
#: forbids reading as a ranking.  So the tie is broken structurally instead, on
#: the clusters themselves:
#:
#: * **k=10 and k=12 each produce a cluster that is nothing but the military
#:   group** (SOC ``55-``, 17-21 rows, median document 557-626 characters).  Not
#:   one of those rows carries a Job Zone, so for every ``fresh_start`` user
#:   whose own occupation resolved -- i.e. everyone with a feasibility ceiling --
#:   that cluster is filtered away entirely and the seed silently runs at k-1.
#: * **k=8 has no such cluster**: the military rows sit inside the
#:   transport-and-equipment cluster, where a ceiling removes them and leaves the
#:   cluster populated.
#: * k=6 merges regions that read as distinct occupational families.
#:
#: Eight regions, eight usable regions.  The page is still filled to ``_TOP_N``
#: -- :func:`diverse_seed` takes the best-ranked survivor in each cluster first
#: and then keeps going down the ranking -- so a smaller k buys spread without
#: costing cards.
CLUSTER_COUNT = 8

#: Fixed so that two machines, two workers and two sidecar rebuilds agree.
RANDOM_STATE = 0

#: ``n_init`` for the fit.  10 is scikit-learn's own pre-1.4 default and costs
#: 0.7 s against 0.07 s for a single init; this runs once per sidecar build (or
#: once per process on the fallback path), so the better local optimum is worth
#: more than the 0.6 s.
N_INIT = 10


@dataclass(frozen=True)
class ClusterAssignment:
    """Which cluster each retrievable occupation belongs to.

    ``labels`` is keyed by O*NET code rather than by row index on purpose: a
    corpus rebuild reorders rows, and a sidecar keyed by position would be
    silently wrong rather than loudly stale.  Codes the corpus no longer carries
    are ignored on load; codes it carries that the sidecar does not make the
    sidecar stale, and :func:`_load_sidecar` refits rather than serving a
    partial partition.

    ``sklearn_version`` / ``numpy_version`` are what actually produced the
    labels, not what the reader is running.  See :func:`library_versions`.
    """

    k: int
    labels: dict[str, int]
    source: str  # "sidecar" | "computed"
    path: Path | None = None
    sklearn_version: str | None = None
    numpy_version: str | None = None

    def cluster_of(self, code: str) -> int | None:
        """The cluster *code* sits in, or None when it was not clustered.

        None for the "..., All Other" residuals, which are deliberately left
        out of the fit, and for anything the assignment predates.
        """
        return self.labels.get(code)

    @property
    def count(self) -> int:
        return len(self.labels)


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------


def library_versions() -> tuple[str, str]:
    """``(scikit-learn, numpy)`` as installed here, WITHOUT importing sklearn.

    F-8 box 10.  ``RANDOM_STATE`` makes the fit reproducible for one build of
    scikit-learn; it is not a promise across builds, and two workers that
    disagreed about cluster identity would show one user two different first
    pages on alternate requests.  The sidecar therefore records what fitted it
    and :func:`_load_sidecar` refuses a file it cannot reproduce.

    **Measured 2026-09-16, and the news is good:** the shipped
    ``onet_corpus_20260916.clusters.json`` was fitted under scikit-learn 1.7.2,
    and a fresh fit under the pinned 1.9.0 over the same 941 rows reproduces it
    **exactly** -- 941/941 rows in the same partition, cluster ids included.
    So this check is a guard against a hazard that has not yet fired, not a fix
    for one that has.  It is still worth having: the cost of being wrong is
    silent and per-worker, the cost of the check is one metadata read, and the
    alternative is finding out from a user.

    ``importlib.metadata`` rather than ``sklearn.__version__`` for the reason
    :data:`SKLEARN_DISTRIBUTION` gives.  numpy is already imported by this
    module, so it costs nothing and is recorded because the matrix arithmetic
    and the BLAS underneath it are its, not scikit-learn's.
    """
    from importlib.metadata import PackageNotFoundError, version  # noqa: PLC0415

    try:
        sklearn_version = version(SKLEARN_DISTRIBUTION)
    except PackageNotFoundError:  # pragma: no cover -- sklearn is a hard pin
        sklearn_version = "unknown"
    return sklearn_version, str(np.__version__)


def _clusterable_codes(corpus: OccupationCorpus) -> list[str]:
    """Every code the fit runs over: the retrievable rows, in corpus order.

    The residual buckets are excluded here rather than filtered afterwards --
    see the module docstring for the measurement that says why.
    """
    return [
        code
        for code, title in zip(corpus.codes, corpus.titles)
        if not is_all_other_title(title)
    ]


def compute_assignment(
    corpus: OccupationCorpus, k: int = CLUSTER_COUNT
) -> ClusterAssignment:
    """Fit k-means over the retrievable rows.  ~0.7 s over 941 x 1536.

    scikit-learn is imported **inside** this function.  Every worker that has a
    sidecar must be able to serve ``fresh_start`` without paying for the
    scientific stack's RSS on a 512 MB dyno; see the module docstring.
    """
    from sklearn.cluster import KMeans

    sklearn_version, numpy_version = library_versions()
    codes = _clusterable_codes(corpus)
    rows = [corpus.index_of(code) for code in codes]
    matrix = corpus.matrix[rows]
    if not codes:
        return ClusterAssignment(
            k=0,
            labels={},
            source="computed",
            sklearn_version=sklearn_version,
            numpy_version=numpy_version,
        )
    if k > len(codes):
        # A corpus smaller than the seed wants regions for.  Not reachable with
        # the real 941-row artifact, and a `ValueError` out of scikit-learn is
        # the wrong way to meet it: one region per occupation is the honest
        # answer to "cut this into more parts than it has".
        _log.warning(
            "occupation clusters: %d retrievable rows for k=%d; clustering at "
            "k=%d instead",
            len(codes),
            k,
            len(codes),
        )
        k = len(codes)
    model = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=N_INIT)
    labels = model.fit_predict(matrix)
    return ClusterAssignment(
        k=k,
        labels={code: int(label) for code, label in zip(codes, labels.tolist())},
        source="computed",
        sklearn_version=sklearn_version,
        numpy_version=numpy_version,
    )


def centroid_nearest(
    corpus: OccupationCorpus, assignment: ClusterAssignment
) -> dict[int, str]:
    """The real occupation nearest each cluster's mean vector.

    Design doc §3.3's literal seed, and F-7's measurement arm (a).  Kept because
    it is the thing arm (b) had to be measured *against*, and because it is what
    a reader of the design doc will come here looking for.
    """
    nearest: dict[int, str] = {}
    for cluster in sorted(set(assignment.labels.values())):
        codes = [c for c, label in assignment.labels.items() if label == cluster]
        rows = [corpus.index_of(code) for code in codes]
        centroid = corpus.matrix[rows].mean(axis=0)
        norm = float(np.linalg.norm(centroid))
        if norm <= 0.0:
            continue
        sims = corpus.matrix[rows] @ (centroid / norm)
        nearest[cluster] = codes[int(np.argmax(sims))]
    return nearest


# ---------------------------------------------------------------------------
# The seed
# ---------------------------------------------------------------------------


def diverse_seed(
    codes: Sequence[str],
    assignment: ClusterAssignment,
    limit: int,
) -> list[int]:
    """Positions in *codes* to show: one per cluster, then filled to *limit*.

    *codes* is every candidate that survived the hard filters, **already ranked**
    -- best first.  The walk takes the highest-ranked member of each cluster it
    has not seen yet; once every cluster is represented it continues down the
    same ranking to fill the page.  Positions come back in ranking order, so the
    caller's list keeps whatever order it arrived in and the cluster ids never
    leak into what the user sees.

    Returns positions rather than rows so that the caller can rank whatever it
    likes -- ``path_scoring`` ranks by the full four-term score, not by the
    retrieval cosine, so the card that represents a region is the best one there
    *for this user* rather than the one nearest the query.

    **The choice inside a cluster is the ranking's, not the centroid's**, and
    that was measured against the alternative rather than assumed.  Arm (a) --
    design doc §3.3's literal "take the real occupation nearest each centroid,
    filtered" -- picks the most *typical* member of each region, which is
    uncorrelated with whether this particular user could do it.  Over the four
    F-2 ``fresh_start`` profiles it returns **four, four, four and six cards out
    of ten**, because a centroid is not a candidate and most of them do not
    survive the hard filters; macro nDCG 0.0855 against this arm's 0.2420.
    Padding the leftovers back in from the ranking rescues the page (0.2630, a
    0.021 difference from this arm that n=4 cannot resolve), but then the
    centroid is only choosing the first four cards and the ranking is choosing
    the rest -- which is this function with extra steps and a worse guarantee.

    A cluster is only ever a reason to move *down* the ranking to a region not
    yet represented; it is never a reason to prefer a candidate, which is what
    keeps "different" from turning into "distant".
    """
    if limit < 1:
        return []
    picked: list[int] = []
    deferred: list[int] = []
    seen: set[int] = set()

    for position, code in enumerate(codes):
        if len(picked) >= limit:
            break
        cluster = assignment.cluster_of(code)
        if cluster is None or cluster in seen:
            deferred.append(position)
            continue
        seen.add(cluster)
        picked.append(position)

    for position in deferred:
        if len(picked) >= limit:
            break
        picked.append(position)
    return sorted(picked)


# ---------------------------------------------------------------------------
# The sidecar
# ---------------------------------------------------------------------------


def cluster_sidecar_path(matrix_path: str | os.PathLike[str]) -> Path:
    """The ``*.clusters.json`` that belongs beside *matrix_path*."""
    path = Path(matrix_path)
    return path.with_name(path.stem + ".clusters.json")


def write_cluster_sidecar(
    matrix_path: str | os.PathLike[str],
    assignment: ClusterAssignment,
) -> Path:
    """Write ``<artifact>.clusters.json`` beside *matrix_path*; return its path.

    A separate file for the same three reasons ``write_zone_sidecar`` gives, and
    written atomically for the same one: a reader sees the old file or the new
    one, never half of either.
    """
    path = cluster_sidecar_path(matrix_path)
    sklearn_version, numpy_version = library_versions()
    payload = {
        "schema_version": CLUSTERS_SCHEMA_VERSION,
        "matrix_filename": Path(matrix_path).name,
        "algorithm": f"sklearn.cluster.KMeans(n_clusters={assignment.k}, "
        f"random_state={RANDOM_STATE}, n_init={N_INIT})",
        # What produced these labels, so a reader can tell whether it could
        # reproduce them.  Taken from the assignment when it carries them --
        # the fit's own answer -- and only falling back to this process's
        # versions for an assignment built some other way.
        "sklearn_version": assignment.sklearn_version or sklearn_version,
        "numpy_version": assignment.numpy_version or numpy_version,
        "built_at": _utc_now_iso(),
        "k": assignment.k,
        "count": assignment.count,
        "clusters": dict(sorted(assignment.labels.items())),
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    return path


def _load_sidecar(path: Path, corpus: OccupationCorpus) -> ClusterAssignment | None:
    """Read the sidecar, or return None if it is absent, unusable or stale.

    Degrades rather than fails, like ``occupation_retrieval._load_zones``: a
    corpus with no usable cluster sidecar is a working corpus whose
    ``fresh_start`` seed costs one in-process fit.  Refusing to serve would turn
    a missing optional file into an outage.

    Stale means *the corpus has retrievable rows the sidecar does not name*,
    **or** the labels were produced by a different build of the libraries that
    produce labels (F-8 box 10).  The first is what a corpus rebuild produces;
    the second is what a dependency bump produces, and it is the quieter of the
    two because every row is still labelled -- just possibly not the way this
    process would label it.  The reverse of the first -- the sidecar naming
    codes the corpus has dropped -- is harmless and tolerated:
    :meth:`ClusterAssignment.cluster_of` is only ever asked about rows that came
    back from retrieval.
    """
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        version = raw.get("schema_version")
        if version != CLUSTERS_SCHEMA_VERSION:
            raise ValueError(
                f"cluster sidecar schema_version {version!r}, "
                f"expected {CLUSTERS_SCHEMA_VERSION}"
            )
        labels = {
            str(code): int(label)
            for code, label in (raw.get("clusters") or {}).items()
            if label is not None
        }
        k = int(raw.get("k") or 0)
        built_with = (raw.get("sklearn_version"), raw.get("numpy_version"))
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        _log.warning(
            "occupation clusters: ignoring unusable sidecar %s (%s); "
            "the fresh_start seed will cluster in-process",
            path,
            exc,
        )
        return None

    if not labels or k < 1:
        return None

    running = library_versions()
    if built_with != running:
        _log.warning(
            "occupation clusters: sidecar %s was fitted with scikit-learn %s / "
            "numpy %s, this process runs %s / %s; `random_state` is a promise "
            "about one build and not across builds, so the labels are refitted "
            "rather than trusted.  Re-run `flask corpus clusters` and publish "
            "the sidecar to stop paying for this",
            path,
            built_with[0],
            built_with[1],
            running[0],
            running[1],
        )
        return None

    missing = [code for code in _clusterable_codes(corpus) if code not in labels]
    if missing:
        _log.warning(
            "occupation clusters: sidecar %s predates this corpus (%d of %d "
            "retrievable rows unlabelled, e.g. %s); re-run `flask corpus "
            "clusters`.  Clustering in-process for now",
            path,
            len(missing),
            corpus.count,
            missing[0],
        )
        return None
    return ClusterAssignment(
        k=k,
        labels=labels,
        source="sidecar",
        path=path,
        sklearn_version=built_with[0],
        numpy_version=built_with[1],
    )


# ---------------------------------------------------------------------------
# Process-wide access
# ---------------------------------------------------------------------------

_LOCK = threading.Lock()
_ASSIGNMENT: ClusterAssignment | None = None
_ASSIGNMENT_FOR: tuple[str, int] | None = None


def get_assignment(
    corpus: OccupationCorpus, k: int = CLUSTER_COUNT
) -> ClusterAssignment:
    """The cluster assignment for *corpus*: sidecar if there is one, else a fit.

    Memoised for the life of the process and keyed by ``(corpus version, k)``,
    so a test that swaps in a synthetic corpus does not inherit the real one's
    labels.  Lock-guarded like ``occupation_retrieval.get_corpus``: two threads
    arriving together must not both pay for the fit.
    """
    global _ASSIGNMENT, _ASSIGNMENT_FOR

    key = (corpus.version, k)
    cached = _ASSIGNMENT
    if cached is not None and _ASSIGNMENT_FOR == key:
        return cached

    with _LOCK:
        if _ASSIGNMENT is not None and _ASSIGNMENT_FOR == key:
            return _ASSIGNMENT
        assignment = _load_sidecar(cluster_sidecar_path(corpus.matrix_path), corpus)
        if assignment is None or assignment.k != k:
            if assignment is not None:
                _log.warning(
                    "occupation clusters: sidecar holds k=%d, this build wants "
                    "k=%d; clustering in-process",
                    assignment.k,
                    k,
                )
            assignment = compute_assignment(corpus, k=k)
            _log.info(
                "occupation clusters: fitted k=%d over %d rows in-process "
                "(no usable sidecar beside %s)",
                k,
                assignment.count,
                corpus.matrix_path.name,
            )
        _ASSIGNMENT, _ASSIGNMENT_FOR = assignment, key
        return assignment


def reset_cluster_cache() -> None:
    """Drop the memo.  Tests and the CLI; nothing in a request path."""
    global _ASSIGNMENT, _ASSIGNMENT_FOR
    with _LOCK:
        _ASSIGNMENT, _ASSIGNMENT_FOR = None, None


def summarise(
    corpus: OccupationCorpus, assignment: ClusterAssignment, top: int = 3
) -> list[dict[str, object]]:
    """Per cluster: size and the *top* titles nearest its centroid.

    What ``flask corpus clusters`` prints.  A seed is only as meaningful as the
    partition under it, so the command that builds one shows what it built --
    F-7's brief asks for exactly this check and it should not need a script.
    """
    rows: list[dict[str, object]] = []
    for cluster, code in sorted(centroid_nearest(corpus, assignment).items()):
        members = [c for c, label in assignment.labels.items() if label == cluster]
        indexes = [corpus.index_of(c) for c in members]
        centroid = corpus.matrix[indexes].mean(axis=0)
        centroid = centroid / (float(np.linalg.norm(centroid)) or 1.0)
        order = np.argsort(-(corpus.matrix[indexes] @ centroid))[:top]
        rows.append(
            {
                "cluster": cluster,
                "size": len(members),
                "nearest_centroid": code,
                "titles": [corpus.titles[indexes[i]] for i in order.tolist()],
            }
        )
    return rows


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
