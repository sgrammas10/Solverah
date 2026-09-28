"""The four O*NET answers a deep fit needs, in a file beside the corpus (W-9).

BUILD_PLAN W-9, design doc ``docs/PATH_INTELLIGENCE_REDESIGN.md`` §8.

WHAT THIS IS FOR
----------------
Opening a card runs ``path_deep_fit.deep_fit``, and the first thing that does is
:func:`path_deep_fit._fetch_occupation` -- **four live O*NET calls** for one
occupation: ``get_skills_profile``, ``get_hot_technologies``,
``get_work_activities``, ``get_tasks``.  F-5 measured the click at 2,384 ms cold
and 844 ms with ``onet_client._OCC_CACHE`` warm, against 12 ms once this user's
``path_fits`` row exists.  Sebastian's first click-through of the wants panel
said the obvious thing about that: *"the loading of a position when i click on
it takes so long to load"*.

Everything those four calls return is **static per occupation**.  O*NET re-rates
an occupation quarterly at most; the corpus artifact is rebuilt less often than
that.  So this is the same trade the other four sidecars already make -- no
network on the request path, every worker reads the same bytes, and data derived
from the artifact is not the artifact.

**A missing sidecar is a DEGRADE, not an error.**  :func:`get_fit_table` returns
None, one warning is logged per corpus version, and ``_fetch_occupation`` does
exactly what it did before this module existed: four live calls.  So does a code
the table happens to lack.  The sidecar can only make a click faster; it can
never make one fail.

WHAT IS STORED, AND WHY IT IS STORED RAW
----------------------------------------
Exactly what the four endpoints returned, unfiltered:

* ``generic_skills``  -- O*NET's ~35 Skills with importance and level
* ``hot_tech``        -- the hot-technology names **in O*NET's own order**,
  which is why ``deep_fit`` calls ``get_hot_technologies`` and not the unordered
  ``get_tech_skills``; the order is the only thing that can rank tools, since
  they all carry one flat importance constant
* ``work_activities`` -- O*NET's ~41 work activities with importance, with
  ``path_deep_fit._WORK_ACTIVITY_IMPORTANCE_THRESHOLD`` **not** applied
* ``tasks``           -- every task statement, with importance and category

Every filter and every trim stays where it is today, in ``path_deep_fit``.  Two
reasons, and the second is the load-bearing one: the equivalence between the
sidecar path and the live path is then exact rather than argued, and a threshold
somebody retunes next month does not need a 3,800-request rebuild to take
effect.

``parts`` records which of the four calls came back.  Each is isolated at build
time exactly as it is at request time -- losing hot tech thins the role profile,
losing work activities disables the style term -- so an occupation with a 404 on
one endpoint is stored with the three it has.  A code where **all four** failed
is not stored at all: an empty record would look like a hit and serve an empty
panel forever, where a miss costs four requests and gets the real answer.

WHY THE STORED TYPES ARE NOT ``onet_client.Skill`` AND ``onet_client.Task``
---------------------------------------------------------------------------
They are the same four fields, and :class:`FitElement` / :class:`FitTask` exist
only because those two are plain dataclasses and this table holds ~88,000
elements.  Measured on the real 941-occupation catalog: the identical table
costs **19.23 MB** resident built out of ``Skill``/``Task`` and **11.81 MB**
built out of the slotted pair below, because a slotted instance carries no
per-instance ``__dict__``.  On a 512 MB single-worker instance that booted at
~148 MB and OOMed once already (2026-09-15), 7.4 MB is worth two eight-line
dataclasses; the arithmetic is recorded in ``tests/test_cache_bounds.py``.  The
read site builds real ``Skill`` objects for the one occupation it was asked
about, which is ~35 allocations per click and measures 22 microseconds.

The repeated strings are interned on load for the same reason: O*NET's Skills
and Work Activities taxonomies are ~76 names shared by **every** occupation, so
without interning the table holds 941 copies of "Reading Comprehension".
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from backend.services.occupation_retrieval import (
    OccupationCorpus,
    is_all_other_title,
)

_log = logging.getLogger(__name__)

__all__ = [
    "FIT_PARTS",
    "FIT_SCHEMA_VERSION",
    "FitElement",
    "FitTable",
    "FitTask",
    "OccupationFit",
    "build_table",
    "fetch_occupation_fit",
    "fit_sidecar_path",
    "get_fit_table",
    "iter_raw_rows",
    "record_payload",
    "reset_fit_cache",
    "write_fit_sidecar",
]

#: Sidecar schema version.  Independent of the corpus artifact's and of the
#: other four sidecars', for the reason ``ZONES_SCHEMA_VERSION`` gives: the files
#: are written by different commands and regenerate independently.
FIT_SCHEMA_VERSION = 1

#: The four O*NET calls, named so a partial record says which it has.  The
#: names are the labels ``path_deep_fit._fetch_occupation`` already logs by, so
#: a build warning and a request warning read the same.
FIT_PARTS: tuple[str, ...] = (
    "skills",
    "hot_technologies",
    "work_activities",
    "tasks",
)


# ---------------------------------------------------------------------------
# The loaded table
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FitElement:
    """One rated O*NET element: a Skill, or a Work Activity.

    Structurally ``onet_client.Skill``.  Slotted for the reason the module
    docstring gives at length -- there are ~71,000 of these in the real table.
    """

    element_id: str
    name: str
    importance: float
    level: float


@dataclass(frozen=True, slots=True)
class FitTask:
    """One task statement, as ``onet_client.Task`` carries it."""

    task_id: str
    title: str
    importance: float
    category: str


@dataclass(frozen=True, slots=True)
class OccupationFit:
    """What the four calls returned for one occupation.

    ``parts`` names the calls that came back.  A record always has at least one
    -- see the module docstring for why a record with none is not written.
    """

    generic_skills: tuple[FitElement, ...] = ()
    hot_tech: tuple[str, ...] = ()
    work_activities: tuple[FitElement, ...] = ()
    tasks: tuple[FitTask, ...] = ()
    parts: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        """All four endpoints answered."""
        return len(self.parts) == len(FIT_PARTS)


@dataclass(frozen=True)
class FitTable:
    """Per-occupation O*NET answers, as ``path_deep_fit`` reads them.

    :meth:`for_code` answers **None** for a code the table lacks, not an empty
    record.  The difference is the whole contract: None means "ask O*NET", and
    an empty record would mean "O*NET says this occupation has nothing", which
    is a claim this file is not entitled to make about a code it never fetched.
    """

    fits: Mapping[str, OccupationFit]
    source: str = ""
    built_at: str = ""
    path: Path | None = None

    @property
    def count(self) -> int:
        return len(self.fits)

    @property
    def complete_count(self) -> int:
        """Occupations where all four endpoints answered."""
        return sum(1 for fit in self.fits.values() if fit.complete)

    def for_code(self, code: str) -> OccupationFit | None:
        return self.fits.get(code)


# ---------------------------------------------------------------------------
# Fetching -- the build path only.  Nothing below runs in a request.
# ---------------------------------------------------------------------------


def fetch_occupation_fit(
    onet_client: Any,
    onet_code: str,
    limiter: Any = None,
) -> OccupationFit:
    """The four calls for one code, each isolated from the other three.

    The isolation is ``path_deep_fit._fetch_occupation``'s, kept here so a code
    with a 404 on one endpoint is stored with what it has rather than dropped:
    the four failure modes are not the same failure, and none of them is a
    reason to refuse the three answers that did arrive.

    A **rate-limit** error is raised rather than swallowed, the judgement
    ``occupation_conditions.fetch_condition_reports`` makes and for its reason:
    continuing past one 429 only spends the rest of the run on more 429s.
    """
    from backend.services.onet_client import OnetAPIError  # noqa: PLC0415

    calls = {
        "skills": lambda: _elements(onet_client.get_skills_profile(onet_code)),
        "hot_technologies": lambda: tuple(
            str(name) for name in onet_client.get_hot_technologies(onet_code)
        ),
        "work_activities": lambda: _elements(
            onet_client.get_work_activities(onet_code)
        ),
        "tasks": lambda: _tasks(onet_client.get_tasks(onet_code)),
    }
    fields: dict[str, Any] = {
        "skills": (),
        "hot_technologies": (),
        "work_activities": (),
        "tasks": (),
    }
    got: list[str] = []

    for part in FIT_PARTS:
        if limiter is not None:
            limiter.acquire()
        try:
            fields[part] = calls[part]()
        except OnetAPIError as exc:
            _log.warning(
                "occupation fit: O*NET %s failed for %s (%s)", part, onet_code, exc
            )
            continue
        got.append(part)

    return OccupationFit(
        generic_skills=fields["skills"],
        hot_tech=fields["hot_technologies"],
        work_activities=fields["work_activities"],
        tasks=fields["tasks"],
        parts=tuple(got),
    )


def _elements(values: Iterable[Any]) -> tuple[FitElement, ...]:
    return tuple(
        FitElement(
            element_id=str(getattr(value, "element_id", "") or ""),
            name=str(getattr(value, "name", "") or ""),
            importance=float(getattr(value, "importance", 0.0) or 0.0),
            level=float(getattr(value, "level", 0.0) or 0.0),
        )
        for value in values
    )


def _tasks(values: Iterable[Any]) -> tuple[FitTask, ...]:
    return tuple(
        FitTask(
            task_id=str(getattr(value, "task_id", "") or ""),
            title=str(getattr(value, "title", "") or ""),
            importance=float(getattr(value, "importance", 0.0) or 0.0),
            category=str(getattr(value, "category", "") or ""),
        )
        for value in values
    )


# ---------------------------------------------------------------------------
# The checkpoint, and the table built from it
# ---------------------------------------------------------------------------
#
# One record shape serves both the resumable checkpoint JSONL and the sidecar's
# per-code value, deliberately: a build that wrote two shapes would need two
# readers and could disagree with itself about what it had already paid for.


def record_payload(code: str, title: str, fit: OccupationFit) -> dict[str, Any]:
    """One occupation as the checkpoint stores it (and the sidecar embeds it)."""
    return {"code": code, "title": title, **_fit_payload(fit)}


def _fit_payload(fit: OccupationFit) -> dict[str, Any]:
    return {
        "parts": list(fit.parts),
        "generic_skills": [_element_payload(e) for e in fit.generic_skills],
        "hot_tech": list(fit.hot_tech),
        "work_activities": [_element_payload(e) for e in fit.work_activities],
        "tasks": [
            {
                "task_id": t.task_id,
                "title": t.title,
                "importance": t.importance,
                "category": t.category,
            }
            for t in fit.tasks
        ],
    }


def _element_payload(element: FitElement) -> dict[str, Any]:
    return {
        "element_id": element.element_id,
        "name": element.name,
        "importance": element.importance,
        "level": element.level,
    }


def _fit_from_payload(raw: Mapping[str, Any]) -> OccupationFit:
    """Read one record back.  Strings are interned -- see the module docstring."""
    return OccupationFit(
        generic_skills=tuple(
            _element_from_payload(row) for row in (raw.get("generic_skills") or [])
        ),
        hot_tech=tuple(sys.intern(str(name)) for name in (raw.get("hot_tech") or [])),
        work_activities=tuple(
            _element_from_payload(row) for row in (raw.get("work_activities") or [])
        ),
        tasks=tuple(
            FitTask(
                task_id=str(row.get("task_id") or ""),
                title=str(row.get("title") or ""),
                importance=float(row.get("importance") or 0.0),
                category=sys.intern(str(row.get("category") or "")),
            )
            for row in (raw.get("tasks") or [])
        ),
        parts=tuple(sys.intern(str(part)) for part in (raw.get("parts") or [])),
    )


def _element_from_payload(raw: Mapping[str, Any]) -> FitElement:
    return FitElement(
        element_id=sys.intern(str(raw.get("element_id") or "")),
        name=sys.intern(str(raw.get("name") or "")),
        importance=float(raw.get("importance") or 0.0),
        level=float(raw.get("level") or 0.0),
    )


def iter_raw_rows(path: str | os.PathLike[str]) -> Iterator[dict[str, Any]]:
    """Yield the checkpoint's records.  A malformed line is a build failure.

    Not a silently dropped occupation, for the reason
    ``occupation_conditions.iter_raw_rows`` gives: a half-built sidecar looks
    exactly like a complete one to every reader downstream.
    """
    with Path(path).open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError as exc:
                raise ValueError(f"{path}:{number} is not valid JSON: {exc}") from exc


def build_table(
    rows: Iterable[Mapping[str, Any]],
    *,
    source: str = "",
) -> FitTable:
    """The table the sidecar is written from.

    ``"..., All Other"`` rows are excluded, the rule every other sidecar builder
    applies and for the same reason: retrieval never returns one, and
    ``deep_fit`` refuses a click on one before it fetches anything.

    A record where **no** endpoint answered is dropped rather than stored -- see
    the module docstring.
    """
    fits: dict[str, OccupationFit] = {}
    for row in rows:
        code = str(row.get("code") or "")
        if not code or is_all_other_title(str(row.get("title") or "")):
            continue
        fit = _fit_from_payload(row)
        if not fit.parts:
            continue
        fits[code] = fit
    return FitTable(fits=fits, source=source, built_at=_utc_now_iso())


# ---------------------------------------------------------------------------
# The sidecar
# ---------------------------------------------------------------------------


def fit_sidecar_path(matrix_path: str | os.PathLike[str]) -> Path:
    """The ``*.fit.json`` that belongs beside *matrix_path*."""
    path = Path(matrix_path)
    return path.with_name(path.stem + ".fit.json")


def write_fit_sidecar(
    matrix_path: str | os.PathLike[str],
    table: FitTable,
) -> Path:
    """Write ``<artifact>.fit.json`` beside *matrix_path*; return its path.

    Atomic, like the other four sidecars: a reader sees the old file or the new
    one and never half of either.  ``ensure_ascii`` is the default and is left
    that way deliberately -- O*NET's prose carries the odd non-ASCII character
    and this file is read on a cp1252 console often enough to matter.
    """
    path = fit_sidecar_path(matrix_path)
    payload = {
        "schema_version": FIT_SCHEMA_VERSION,
        "matrix_filename": Path(matrix_path).name,
        "source": table.source,
        "built_at": table.built_at or _utc_now_iso(),
        "count": table.count,
        "complete_count": table.complete_count,
        "parts": list(FIT_PARTS),
        "fits": {
            code: _fit_payload(fit) for code, fit in sorted(table.fits.items())
        },
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    os.replace(tmp, path)
    return path


def _load_sidecar(path: Path) -> FitTable | None:
    """Read the sidecar, or return None if it is absent or unusable.

    Degrades rather than fails, like every other optional file beside the
    artifact: without it a click costs the four O*NET calls it has always cost.
    """
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        version = raw.get("schema_version")
        if version != FIT_SCHEMA_VERSION:
            raise ValueError(
                f"fit sidecar schema_version {version!r}, expected {FIT_SCHEMA_VERSION}"
            )
        fits = {
            str(code): _fit_from_payload(row)
            for code, row in (raw.get("fits") or {}).items()
        }
        fits = {code: fit for code, fit in fits.items() if fit.parts}
    except (OSError, KeyError, ValueError, TypeError, AttributeError) as exc:
        _log.warning(
            "occupation fit: ignoring unusable sidecar %s (%s); deep fits will "
            "call O*NET live",
            path,
            exc,
        )
        return None

    if not fits:
        return None
    return FitTable(
        fits=fits,
        source=str(raw.get("source") or ""),
        built_at=str(raw.get("built_at") or ""),
        path=path,
    )


# ---------------------------------------------------------------------------
# Process-wide access
# ---------------------------------------------------------------------------

_LOCK = threading.Lock()
_TABLE: FitTable | None = None
_TABLE_FOR: str | None = None
_MISSING_LOGGED: set[str] = set()


def get_fit_table(corpus: OccupationCorpus) -> FitTable | None:
    """The fit table beside *corpus*, or None when there is no sidecar.

    Memoised per corpus version for the life of the process and lock-guarded,
    exactly as ``occupation_tasks.get_tasks`` is, and holding **one** table
    rather than one per version -- ``tests/test_cache_bounds.py`` asserts that,
    because two of these resident is the one way this memo can grow.

    Nothing here imports scikit-learn, touches the network, or runs in
    ``create_app()``: it is a dict read behind a memo, first paid for by
    whichever request first opens a card.
    """
    global _TABLE, _TABLE_FOR

    key = corpus.version
    cached = _TABLE
    if cached is not None and _TABLE_FOR == key:
        return cached

    with _LOCK:
        if _TABLE is not None and _TABLE_FOR == key:
            return _TABLE
        path = fit_sidecar_path(corpus.matrix_path)
        table = _load_sidecar(path)
        if table is None:
            if key not in _MISSING_LOGGED:
                _MISSING_LOGGED.add(key)
                _log.warning(
                    "no fit sidecar beside %s; every deep fit will spend four "
                    "live O*NET calls.  Run `flask corpus fit`",
                    corpus.matrix_path.name,
                )
            return None
        _TABLE, _TABLE_FOR = table, key
        _log.info(
            "occupation fit: loaded %d occupations (%d complete) from %s",
            table.count,
            table.complete_count,
            path.name,
        )
        return table


def reset_fit_cache() -> None:
    """Drop the memo.  Tests and the CLI; nothing in a request path."""
    global _TABLE, _TABLE_FOR
    with _LOCK:
        _TABLE, _TABLE_FOR = None, None
        _MISSING_LOGGED.clear()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
