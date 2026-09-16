"""Build the precomputed O*NET occupation vector corpus (BUILD_PLAN F-1).

One vector per O*NET occupation, computed offline, so retrieval becomes a single
``matrix @ query`` instead of the ~160-request per-run funnel that
``path_scoring._gather_candidates`` runs today.  ``docs/PATH_INTELLIGENCE_REDESIGN.md``
§2.1 is the design of record; §1 has the measurements that motivate it.

WHAT GETS EMBEDDED, AND WHY IT IS NOT THE TITLE
-----------------------------------------------
Each occupation is embedded as a **role document** -- title, O*NET's description
paragraph, its most important task statements, and its hot technologies -- not as
its bare title.  This is the single load-bearing decision in this module.

A 2-3 word title is dominated by one token, so title-only cosine puts "Data
Scientists" next to "Political Scientists" and "Atmospheric Scientists": the
exact failure the hand-written SOC allow-list at ``path_scoring.py:154`` exists
to suppress.  Embedding ~300-400 tokens of what the job actually involves makes
the similarity reflect the work rather than the noun, and is what lets that hack
be deleted in F-4.  Same one vector per occupation, same ~6 MB artifact, same
sub-cent build cost.

THE ARTIFACT
------------
Two files, versioned by filename so a new build never overwrites the one in
service:

    onet_corpus_<version>.npy    float32 (N, 1536), L2-normalised, row-major
    onet_corpus_<version>.json   sidecar: row index -> O*NET code + title

Measured: 1,016 occupations x 1536 dims x 4 bytes = 6.2 MB.  L2-normalised on
write so a consumer's cosine is exactly ``matrix @ unit_query`` with no
per-query renormalisation, and so ``.npy`` stays the only format contract.

**No S3 here.**  F-1 writes local files and stops; F-3 owns the load path and
the upload is a later addition over ``CorpusBuild.matrix_path`` /
``.sidecar_path``, which is why those are returned rather than swallowed.

RATE LIMITS
-----------
O*NET publishes its limits in the Terms of Service (https://services.onetcenter.org/terms),
not in the API reference: **"access may be temporarily throttled or suspended
for individual Web Services users who make more than: 1. 5 requests per second,
or 2. 50,000 requests per day."**  The v2 reference adds that a 429 should be
retried after "at least 200 milliseconds" and that there is no ``Retry-After``
header to honour (``onet_client._RETRY_DELAY`` is already 250 ms).

A full build is 3,073 requests, measured: 1 for the family list, 24 family pages
(23 families, one of which needs two pages), then 3 per occupation.  The daily
cap is therefore never in play -- 6% of it -- and the per-second threshold is the
only one that matters.  ``DEFAULT_REQUESTS_PER_SECOND`` is 4.0, deliberately
below the documented 5; the real build took 13 minutes.  Every O*NET call in this
module passes through one process-wide ``RateLimiter`` so raising ``workers``
changes latency hiding, never the request rate.

WHAT THE BUILT CORPUS ACTUALLY CONTAINS (measured, 2026-09-16 build)
--------------------------------------------------------------------
1,016 occupations x 1536 dims x 4 bytes = 6,242,432 bytes, matching §2.1's ~6 MB
estimate.  Documents average 1,768 characters (~440 tokens), 50 at the shortest
and 2,891 at the longest.  Two properties a consumer needs to know about,
because neither is visible from the matrix:

- **74 occupations have no tasks** and **112 no hot technologies**.  Those rows
  are thinner but still carry a real description; they are legitimate results.
- **57 rows are content-free by construction.**  The "..., All Other" residual
  SOC codes -- "Cooks, All Other", "Engineers, All Other", "Surgeons, All
  Other" -- have no tasks, no technologies, and a description that is literally
  "All cooks not listed separately."  Their documents are ~50 characters, which
  means they are *effectively title-only* and reproduce the exact
  title-domination failure §2.1 exists to avoid: "Engineers, All Other" will sit
  near anything called an engineer.  They are kept in the artifact so the
  sidecar stays a faithful index of the catalog, but **F-3 should filter them at
  the retrieval tier** -- they are never a useful career suggestion, and they
  are cheap to spot (title ends with ", All Other").

RESUMABILITY
------------
Fetched role documents are appended to a JSONL checkpoint as they arrive and
reloaded on the next run, so a trip 2,000 requests in costs those requests
once.  The checkpoint is also the human-readable record of what was embedded --
the only place the composed documents survive the build -- which is what makes
a bad corpus diagnosable without re-fetching it.
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

import numpy as np
import requests

from backend.services.onet_client import Occupation, OnetAPIError, OnetRateLimitError

_log = logging.getLogger(__name__)

__all__ = [
    "CorpusBuild",
    "CorpusBuildError",
    "RateLimiter",
    "RoleDocument",
    "build_corpus",
    "compose_role_document",
    "enumerate_occupations",
    "fetch_role_document",
]

#: The embedding model and its dimensionality.  Both are recorded in the sidecar
#: because a corpus built with one model is meaningless against a query embedded
#: with another, and a silent model swap is the failure mode that is hardest to
#: see: every cosine still returns a plausible-looking number.
EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536

#: Sidecar schema version.  Bump when the sidecar's *keys* change, not when the
#: corpus content changes -- that is what the filename version is for.
SCHEMA_VERSION = 1

#: How much of each occupation's content reaches the document.
#:
#: Tasks are capped at 15 of a typical 17-28 because the tail is
#: ``category: "Supplemental"`` -- statements O*NET itself marks as not core to
#: the occupation -- and every token spent there dilutes the ones that are.
#: Hot technologies are capped at 15 of up to 55 for a sharper reason: they
#: arrive ranked by the share of job postings mentioning them, and the tail of a
#: tech-heavy occupation is long enough to make tool names 40% of the document.
#: Both caps are applied to already-ranked lists, so "the first 15" means "the
#: 15 that matter most", not "the 15 that happened to come back first".
MAX_TASKS = 15
MAX_HOT_TECHNOLOGIES = 15

#: Hard ceiling on one document, as a backstop against a pathological O*NET
#: record.  text-embedding-3-small accepts 8,192 tokens per input; 24,000
#: characters is roughly 6,000.  Measured on the real catalog the longest
#: document is far below this, so this never fires -- it exists so that if it
#: ever does, the build degrades one row instead of failing the request.
MAX_DOCUMENT_CHARS = 24_000

#: OpenAI's embeddings endpoint caps a request at 2,048 inputs *and* at a total
#: token count.  The real catalog's 1,016 documents fit the input cap in one
#: request but not the token cap -- measured 2026-09-16, they are 1,797,025
#: characters, ~450k tokens -- so batches are bounded by both.  The character
#: budget is ~100k tokens at the usual 4 chars/token, a third of the documented
#: ceiling; it split the real build into 5 requests, and there is no prize for
#: filling it.
EMBED_MAX_INPUTS = 2048
EMBED_MAX_BATCH_CHARS = 400_000

#: O*NET's documented per-second threshold, and the rate this builder actually
#: uses.  See the module docstring.
ONET_DOCUMENTED_REQUESTS_PER_SECOND = 5.0
DEFAULT_REQUESTS_PER_SECOND = 4.0

#: Page size for the job-family walk.  The API is 1-indexed and inclusive.
FAMILY_PAGE_SIZE = 100

#: Refuse to write an artifact when more than this share of occupations failed
#: to fetch.  A corpus missing 2 occupations is a corpus; one missing 300 is a
#: silent quality regression that would only surface as bad recommendations
#: weeks later.
MAX_FAILURE_RATIO = 0.05


class CorpusBuildError(Exception):
    """The build could not produce a trustworthy artifact."""


# ---------------------------------------------------------------------------
# Throttling
# ---------------------------------------------------------------------------


class RateLimiter:
    """Process-wide minimum-interval gate, safe to share across threads.

    Hands out request slots spaced ``1 / rate_per_second`` apart.  A caller
    reserves its slot under the lock and then sleeps *outside* it, so N threads
    queue on arithmetic rather than on each other's sleeps -- the aggregate rate
    is the configured one whether one thread calls ``acquire`` or eight do.

    ``count`` is the number of slots handed out, which is how the build reports
    its O*NET spend.
    """

    def __init__(self, rate_per_second: float) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        self._min_interval: float = 1.0 / rate_per_second
        self._lock = threading.Lock()
        self._next_slot: float = 0.0
        self._count: int = 0

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    def acquire(self) -> None:
        """Block until this caller's slot is due."""
        with self._lock:
            now = time.monotonic()
            self._count += 1
            if self._next_slot <= now:
                self._next_slot = now + self._min_interval
                wait = 0.0
            else:
                wait = self._next_slot - now
                self._next_slot += self._min_interval
        if wait > 0:
            time.sleep(wait)


def _acquire(limiter: RateLimiter | None) -> None:
    if limiter is not None:
        limiter.acquire()


# ---------------------------------------------------------------------------
# Role documents
# ---------------------------------------------------------------------------


@dataclass
class RoleDocument:
    """Everything that goes into one occupation's vector, before composition."""

    code: str
    title: str
    description: str
    tasks: list[str] = field(default_factory=list)
    hot_technologies: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "title": self.title,
            "description": self.description,
            "tasks": list(self.tasks),
            "hot_technologies": list(self.hot_technologies),
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "RoleDocument":
        return cls(
            code=str(raw.get("code", "")),
            title=str(raw.get("title", "")),
            description=str(raw.get("description", "")),
            tasks=[str(t) for t in raw.get("tasks") or []],
            hot_technologies=[str(t) for t in raw.get("hot_technologies") or []],
        )


def compose_role_document(doc: RoleDocument) -> str:
    """Render *doc* as the text that gets embedded.

    Sections are labelled and blank-line separated.  The labels are three tokens
    shared by every document in the corpus, which is a real but negligible cost:
    §1.1's complaint is about a vocabulary that is *mostly* constant (15-20 of
    ~25 terms), not about 3 tokens of ~350.  What they buy is structure the
    embedding model can use to tell a duty from a tool name.

    Task statements already end in a period, so they join into prose with a
    single space.  Missing sections are omitted entirely rather than emitted
    empty -- measured over the live catalog, 74 of 1,016 occupations have no
    task data at all (all 19 Military Specific ones, plus every "..., All Other"
    residual code), and "Tasks:" followed by nothing would be a constant
    carrying no information.
    """
    parts: list[str] = [doc.title.strip()]
    description = doc.description.strip()
    if description:
        parts.append(description)
    tasks = [t.strip() for t in doc.tasks[:MAX_TASKS] if t.strip()]
    if tasks:
        parts.append("Tasks: " + " ".join(tasks))
    tech = [t.strip() for t in doc.hot_technologies[:MAX_HOT_TECHNOLOGIES] if t.strip()]
    if tech:
        parts.append("Technologies: " + ", ".join(tech) + ".")
    return "\n\n".join(p for p in parts if p)[:MAX_DOCUMENT_CHARS]


# ---------------------------------------------------------------------------
# Enumeration
# ---------------------------------------------------------------------------


def enumerate_occupations(
    onet_client: Any,
    limiter: RateLimiter | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> list[Occupation]:
    """Return every occupation in the O*NET catalog, deduplicated, sorted by code.

    Walks ``get_job_families()`` then every family, **paging each family** until
    a short page comes back.  Paging is not optional: measured 2026-09-16,
    ``51-0000`` (Production) holds 114 occupations, so the client's default
    single 100-entry page drops 14 of them.

    Sorted by code so the artifact's row order is a property of the catalog
    rather than of family iteration order -- two builds of the same catalog
    produce the same row for the same occupation, which is what makes an
    artifact diffable and a regression bisectable.
    """
    _acquire(limiter)
    families = onet_client.get_job_families()
    if not families:
        raise CorpusBuildError("get_job_families() returned nothing")

    seen: set[str] = set()
    result: list[Occupation] = []
    for family in families:
        code = family.get("code") if isinstance(family, dict) else None
        if not code:
            continue
        start = 1
        while True:
            _acquire(limiter)
            page = onet_client.get_job_family_occupations(
                code, start=start, end=start + FAMILY_PAGE_SIZE - 1
            )
            for occ in page:
                if occ.code and occ.code not in seen:
                    seen.add(occ.code)
                    result.append(occ)
            if len(page) < FAMILY_PAGE_SIZE:
                break
            start += FAMILY_PAGE_SIZE
        if on_progress is not None:
            on_progress(f"enumerated {code}: {len(result)} occupations so far")

    result.sort(key=lambda o: o.code)
    return result


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def fetch_role_document(
    onet_client: Any,
    occupation: Occupation,
    limiter: RateLimiter | None = None,
) -> RoleDocument:
    """Fetch one occupation's description, tasks and hot technologies.

    Three O*NET requests, each gated.  There is no bulk endpoint that carries
    descriptions -- ``/online/occupations`` pages the whole catalog with code,
    title and job zone but no prose -- so three per occupation is the floor.
    """
    _acquire(limiter)
    description = onet_client.get_occupation_description(occupation.code)
    _acquire(limiter)
    tasks = onet_client.get_tasks(occupation.code)
    _acquire(limiter)
    hot_tech = onet_client.get_hot_technologies(occupation.code)
    return RoleDocument(
        code=occupation.code,
        title=occupation.title,
        description=description,
        tasks=[t.title for t in tasks],
        hot_technologies=list(hot_tech),
    )


class DocumentCheckpoint:
    """Append-only JSONL record of fetched role documents.

    Flushed per record: a build killed at request 2,000 keeps 1,999 documents,
    so the cost of a trip is the in-flight request, not the run.  Reading
    tolerates a truncated final line -- the one record a kill *can* corrupt --
    rather than refusing to resume over it.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> dict[str, RoleDocument]:
        if not self.path.exists():
            return {}
        docs: dict[str, RoleDocument] = {}
        with self.path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    _log.warning(
                        "checkpoint %s line %d is not valid JSON; ignoring it",
                        self.path,
                        lineno,
                    )
                    continue
                doc = RoleDocument.from_json(raw)
                if doc.code:
                    docs[doc.code] = doc
        return docs

    def append(self, doc: RoleDocument) -> None:
        line = json.dumps(doc.to_json(), ensure_ascii=False)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------


def _estimate_tokens(text: str) -> int:
    """Rough token count for batch sizing only.

    ``tiktoken`` is not a dependency of this project and is not worth adding for
    a batching heuristic: the consequence of being wrong is one extra HTTP
    request, and the budget already sits at a third of the documented cap.
    """
    return max(1, math.ceil(len(text) / 4))


def _embed_batches(texts: Sequence[str]) -> Iterator[tuple[int, list[str]]]:
    """Yield ``(offset, chunk)`` pairs respecting both OpenAI request caps."""
    start = 0
    while start < len(texts):
        chunk: list[str] = []
        chars = 0
        index = start
        while index < len(texts) and len(chunk) < EMBED_MAX_INPUTS:
            length = len(texts[index])
            if chunk and chars + length > EMBED_MAX_BATCH_CHARS:
                break
            chunk.append(texts[index])
            chars += length
            index += 1
        yield start, chunk
        start = index


def embed_documents(
    texts: Sequence[str],
    openai_client: Any,
    on_progress: Callable[[str], None] | None = None,
) -> tuple["np.ndarray", int]:
    """Embed *texts* in order, returning an ``(N, EMBED_DIM)`` float32 matrix.

    Rows are filled by ``item.index`` within each batch rather than by
    enumeration order, mirroring ``path_scoring._batch_embed``: the API
    documents that the response may be reordered, and a misaligned corpus is
    invisible until somebody notices the recommendations are nonsense.

    Unlike ``_batch_embed`` this does **not** swallow API failures.  A scoring
    run that loses some embeddings degrades one response; a corpus build that
    loses some writes a permanently wrong artifact.
    """
    matrix = np.zeros((len(texts), EMBED_DIM), dtype=np.float32)
    filled = np.zeros(len(texts), dtype=bool)
    calls = 0
    for offset, chunk in _embed_batches(texts):
        response = openai_client.embeddings.create(model=EMBED_MODEL, input=list(chunk))
        calls += 1
        for item in response.data:
            vector = np.asarray(item.embedding, dtype=np.float32)
            if vector.shape != (EMBED_DIM,):
                raise CorpusBuildError(
                    f"{EMBED_MODEL} returned {vector.shape[0]} dimensions, "
                    f"expected {EMBED_DIM}"
                )
            matrix[offset + item.index] = vector
            filled[offset + item.index] = True
        if on_progress is not None:
            on_progress(f"embedded {int(filled.sum())}/{len(texts)} documents")
    missing = int((~filled).sum())
    if missing:
        raise CorpusBuildError(
            f"{missing} of {len(texts)} documents came back without an embedding"
        )
    return matrix, calls


def _l2_normalise(matrix: "np.ndarray") -> "np.ndarray":
    """Unit-normalise each row so cosine is a plain dot product downstream."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return (matrix / norms).astype(np.float32)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


@dataclass
class CorpusBuild:
    """What a completed build produced, and what it cost."""

    version: str
    matrix_path: Path
    sidecar_path: Path
    checkpoint_path: Path
    count: int
    dimensions: int
    model: str
    matrix_bytes: int
    onet_requests: int
    embed_requests: int
    document_chars: int
    estimated_tokens: int
    resumed_documents: int
    failures: list[tuple[str, str]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "event": "corpus_build",
            "version": self.version,
            "matrix_path": str(self.matrix_path),
            "sidecar_path": str(self.sidecar_path),
            "checkpoint_path": str(self.checkpoint_path),
            "occupations": self.count,
            "dimensions": self.dimensions,
            "model": self.model,
            "matrix_bytes": self.matrix_bytes,
            "onet_requests": self.onet_requests,
            "embed_requests": self.embed_requests,
            "document_chars": self.document_chars,
            "estimated_tokens": self.estimated_tokens,
            "resumed_documents": self.resumed_documents,
            "failures": [{"code": c, "error": e} for c, e in self.failures],
        }


def default_version() -> str:
    """Artifact version stamp: the UTC build date.

    Versioning by filename is the storage decision (`BUILD_PLAN.md` F-1), and a
    date is the right granularity because O*NET content changes quarterly. Two
    builds on one day overwrite each other by design -- a rebuild on the same
    catalog is the same artifact.
    """
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _write_atomic(path: Path, write: Callable[[Path], None]) -> None:
    """Write via a sibling temp file and rename, so readers never see a partial.

    A 6 MB artifact written in place is readable and wrong for the duration of
    the write; F-3 loads this file at boot, and "loaded half a matrix" is not a
    failure mode worth having.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    write(tmp)
    os.replace(tmp, path)


def build_corpus(
    *,
    out_dir: str | os.PathLike[str],
    onet_client: Any,
    openai_client: Any,
    version: str | None = None,
    limit: int | None = None,
    requests_per_second: float = DEFAULT_REQUESTS_PER_SECOND,
    workers: int = 4,
    resume: bool = True,
    checkpoint_path: str | os.PathLike[str] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> CorpusBuild:
    """Build the corpus artifact into *out_dir* and return what it produced.

    Args:
        out_dir: Directory for the ``.npy``, the sidecar and the checkpoint.
            Created if absent.  Deliberately not inside the repo: the artifact
            is a 6 MB binary and the guard tests walk the tree.
        onet_client: An ``OnetClient`` (or anything with its surface).
        openai_client: An OpenAI client exposing ``embeddings.create``.
        version: Filename version stamp; defaults to today's UTC date.
        limit: Embed only the first *limit* occupations by code.  For smoke
            runs -- a full build is ~3,070 O*NET requests.
        requests_per_second: Aggregate O*NET rate ceiling across all workers.
            Refuses to exceed O*NET's documented 5/s.
        workers: Concurrent fetchers.  Hides latency; does not change the rate.
        resume: Reuse role documents already in the checkpoint.
        checkpoint_path: Override the checkpoint location.
        on_progress: Called with human-readable progress lines.

    Raises:
        CorpusBuildError: On an unusable catalog, an embedding failure, or more
            than ``MAX_FAILURE_RATIO`` of occupations failing to fetch.
    """
    if requests_per_second > ONET_DOCUMENTED_REQUESTS_PER_SECOND:
        raise CorpusBuildError(
            f"requests_per_second={requests_per_second} exceeds O*NET's documented "
            f"{ONET_DOCUMENTED_REQUESTS_PER_SECOND}/s threshold "
            "(https://services.onetcenter.org/terms)"
        )
    if workers < 1:
        raise CorpusBuildError("workers must be at least 1")

    def progress(message: str) -> None:
        _log.info("%s", message)
        if on_progress is not None:
            on_progress(message)

    stamp = version or default_version()
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    matrix_path = directory / f"onet_corpus_{stamp}.npy"
    sidecar_path = directory / f"onet_corpus_{stamp}.json"
    checkpoint = DocumentCheckpoint(
        Path(checkpoint_path)
        if checkpoint_path is not None
        else directory / f"onet_corpus_{stamp}.documents.jsonl"
    )

    limiter = RateLimiter(requests_per_second)

    progress("enumerating O*NET occupations")
    occupations = enumerate_occupations(onet_client, limiter, on_progress=progress)
    if limit is not None:
        occupations = occupations[:limit]
    progress(f"catalog: {len(occupations)} occupations")

    cached = checkpoint.load() if resume else {}
    resumed = 0
    documents: dict[str, RoleDocument] = {}
    pending: list[Occupation] = []
    for occ in occupations:
        existing = cached.get(occ.code)
        if existing is not None:
            documents[occ.code] = existing
            resumed += 1
        else:
            pending.append(occ)
    if resumed:
        progress(f"resuming: {resumed} documents already in {checkpoint.path.name}")

    failures: list[tuple[str, str]] = []
    failure_lock = threading.Lock()
    done = 0
    done_lock = threading.Lock()

    def worker(occ: Occupation) -> RoleDocument | None:
        nonlocal done
        try:
            doc = fetch_role_document(onet_client, occ, limiter)
        except (
            OnetAPIError,
            OnetRateLimitError,
            # requests' own errors reach here unwrapped: onet_client._get only
            # converts HTTPError, so a connection reset or a read timeout during
            # a 13-minute run would otherwise escape the pool and end the build.
            # Recording it as a failure keeps the other 1,015 occupations and
            # lets the run resume; MAX_FAILURE_RATIO is what stops a genuine
            # outage from being written out as a corpus.
            requests.RequestException,
            ValueError,
            KeyError,
        ) as exc:
            with failure_lock:
                failures.append((occ.code, f"{type(exc).__name__}: {exc}"))
            _log.warning("role document failed for %s: %s", occ.code, exc)
            return None
        checkpoint.append(doc)
        with done_lock:
            done += 1
            if done % 50 == 0 or done == len(pending):
                progress(f"fetched {done}/{len(pending)} role documents")
        return doc

    if pending:
        progress(
            f"fetching {len(pending)} role documents "
            f"({3 * len(pending)} requests at {requests_per_second}/s, "
            f"~{3 * len(pending) / requests_per_second / 60:.0f} min)"
        )
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for doc in pool.map(worker, pending):
                if doc is not None:
                    documents[doc.code] = doc

    ordered = [documents[occ.code] for occ in occupations if occ.code in documents]
    if not ordered:
        raise CorpusBuildError("no role documents were fetched")
    if failures and len(failures) / len(occupations) > MAX_FAILURE_RATIO:
        raise CorpusBuildError(
            f"{len(failures)} of {len(occupations)} occupations failed to fetch, "
            f"over the {MAX_FAILURE_RATIO:.0%} tolerance; refusing to write a "
            "corpus with a hole in it. Re-run to resume from the checkpoint."
        )

    texts = [compose_role_document(doc) for doc in ordered]
    document_chars = sum(len(t) for t in texts)
    estimated_tokens = sum(_estimate_tokens(t) for t in texts)
    progress(
        f"embedding {len(texts)} documents "
        f"(~{estimated_tokens:,} tokens with {EMBED_MODEL})"
    )
    matrix, embed_calls = embed_documents(texts, openai_client, on_progress=progress)
    matrix = _l2_normalise(matrix)

    def _save_matrix(target: Path) -> None:
        # Through an open handle, not a path: np.save APPENDS ".npy" to a path
        # that does not already end in it, so handing it the ".npy.tmp" scratch
        # name writes ".npy.tmp.npy" and the rename then fails on a file that
        # was never created.  A file object suppresses that rewriting entirely.
        with target.open("wb") as fh:
            np.save(fh, matrix, allow_pickle=False)

    _write_atomic(matrix_path, _save_matrix)
    sidecar = {
        "schema_version": SCHEMA_VERSION,
        "version": stamp,
        "model": EMBED_MODEL,
        "dimensions": EMBED_DIM,
        "dtype": "float32",
        "normalised": True,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "count": len(ordered),
        "matrix_filename": matrix_path.name,
        "max_tasks": MAX_TASKS,
        "max_hot_technologies": MAX_HOT_TECHNOLOGIES,
        # Row i of the matrix is codes[i] / titles[i].  Two parallel arrays
        # rather than a list of objects: this is read at boot by every worker
        # and the flat form is both smaller and directly usable as an index.
        "codes": [doc.code for doc in ordered],
        "titles": [doc.title for doc in ordered],
    }
    _write_atomic(
        sidecar_path,
        lambda p: p.write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=1), encoding="utf-8"
        ),
    )

    return CorpusBuild(
        version=stamp,
        matrix_path=matrix_path,
        sidecar_path=sidecar_path,
        checkpoint_path=checkpoint.path,
        count=len(ordered),
        dimensions=EMBED_DIM,
        model=EMBED_MODEL,
        matrix_bytes=matrix_path.stat().st_size,
        onet_requests=limiter.count,
        embed_requests=embed_calls,
        document_chars=document_chars,
        estimated_tokens=estimated_tokens,
        resumed_documents=resumed,
        failures=failures,
    )
