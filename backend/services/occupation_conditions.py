"""Measured working conditions per occupation -- the wants layer's second signal.

BUILD_PLAN W-3, design doc ``docs/PATH_INTELLIGENCE_REDESIGN.md`` §8.2/§8.3.

WHAT THIS IS FOR
----------------
A user can say *what* they want more or less of -- their own job's tasks -- and
that steers the query (``path_scoring``'s Rocchio rotation).  What a task list
cannot say is what the *day* is like: time with people, time with the public,
leading other people, a desk against being on your feet.  O*NET measures those,
per occupation, in the ``work_context`` report, and this module turns that
report into a small per-occupation table that the scorer can read with no
network call and no scikit-learn.

**An axis is a BUNDLE of elements, and it is a PERCENTILE.**  Both halves were
forced by the look recorded in design doc §8.2:

* One element is too thin.  "Time with people" is *Contact With Others* and
  *Face-to-Face Discussions* and *Work With or Contribute to a Work Group* --
  an occupation can be low on one and high on the rest.  An axis averages the
  elements that are **present**; a missing element is never a zero, and a job
  with no element at all for an axis simply has no value for it.
* O*NET's raw 0-100 values are **compressed**, and taking them at face value
  makes every job look sociable: *Contact With Others* is 72 for software
  developers and 97 for registered nurses, so 0.72 against 0.97 reads as a
  small difference where the lived one is enormous.  Ranked across the corpus
  the same pair is percentile 0.07 and 0.93.  So the stored axis value is the
  **percentile rank across the retrievable rows**, and the raw bundle mean is
  stored beside it for anyone who needs to see what it came from.

THE SIDECAR
-----------
``<artifact>.experience.json``, beside the ``.npy``, exactly as
``*.zones.json`` (``occupation_retrieval.write_zone_sidecar``) and
``*.clusters.json`` (``occupation_clusters.write_cluster_sidecar``) are.  Same
three reasons: no network on the request path, every worker reads the same
numbers, and data derived from the artifact is not the artifact.

**A missing sidecar is a DEGRADE, not an error.**  ``get_conditions`` returns
None, one warning is logged, and the scorer drops the conditions term and keeps
the rest.  Conditions are the second signal (§8.2: "the conditions score alone
cannot rank"), so serving a page without them is a worse answer, not a broken
one -- the same judgement ``_load_zones`` makes about its own optional file.

WHY ``pace`` IS BUILT AND NOT USED BY THE WANTS SCHEMA
------------------------------------------------------
Seven axes are built because the fetched report carries them and rebuilding the
file to add one would mean re-fetching 2,733 O*NET reports.  Only four are in
W-2's ``wants`` schema (``people`` / ``public`` / ``leading`` / ``desk``) and
only those are asked about.  ``pace`` in particular is recorded as weak in
design doc §8.2 -- built from *Time Pressure* alone it rates air traffic
controllers as less pressured than nurses, because the element measures
deadlines rather than stress.  An axis nobody asks about costs nothing; an axis
asked about on a bad measurement costs a user's trust.

WHAT THIS MODULE MUST NEVER BECOME
----------------------------------
A ranker.  It answers "how much of X does this job have", and nothing else.
Design doc §8.2 measured the alternative: scored on conditions alone a
developer who wants more people-contact is shown Mechanical Engineers, Library
Technicians and Medical Records Specialists.  Skills have to be in the rank;
``path_scoring`` blends this in as one one-sided term and owns that decision.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

from backend.services.occupation_retrieval import (
    OccupationCorpus,
    is_all_other_title,
)

_log = logging.getLogger(__name__)

__all__ = [
    "AXES",
    "AXIS_NAMES",
    "CONDITIONS_SCHEMA_VERSION",
    "ConditionsTable",
    "REPORT_VALUE_FIELDS",
    "build_table",
    "conditions_sidecar_path",
    "fetch_condition_reports",
    "get_conditions",
    "iter_raw_rows",
    "reset_conditions_cache",
    "write_conditions_sidecar",
]

#: Sidecar schema version.  Independent of the corpus artifact's and of the
#: other two sidecars', for the reason ``ZONES_SCHEMA_VERSION`` gives: the files
#: are written by different commands and regenerate independently.
CONDITIONS_SCHEMA_VERSION = 1

#: The three ``details/`` reports a build fetches, and the field each one puts
#: its 0-100 value in.  ``details/work_values`` is **not** here: it 404s on the
#: v2 API (verified while fetching the prototype's data, 2026-09-17).
#:
#: Only ``work_context`` feeds an axis today.  The other two are fetched and
#: stored because they are the same request pass -- three reports per occupation
#: at 4 req/s -- and because ``work_styles`` ("Self Control", "Stress
#: Tolerance") and ``interests`` (the RIASEC six) are the obvious next axes if
#: W-3's measurement asks for them.  Nothing reads them yet, and a build that
#: cannot fetch them still writes a usable file.
REPORT_VALUE_FIELDS: dict[str, str] = {
    "work_context": "context",
    "work_styles": "importance",
    "interests": "occupational_interest",
}

#: Axis -> the ``work_context`` elements it averages, each with a sign.  A sign
#: of -1 means the element counts *against* the axis, so ``desk`` is time
#: sitting minus time standing and walking rather than a separate "on your feet"
#: axis pointing the other way.
#:
#: Element names are O*NET's own, verbatim, because that is the key the report
#: arrives under.  A rename upstream shows up as an axis losing an element,
#: which :func:`build_table` reports as coverage rather than silently scoring
#: zero.
AXES: dict[str, tuple[tuple[str, int], ...]] = {
    "people": (
        ("Contact With Others", 1),
        ("Face-to-Face Discussions with Individuals and Within Teams", 1),
        ("Work With or Contribute to a Work Group or Team", 1),
    ),
    "public": (("Deal With External Customers or the Public in General", 1),),
    "leading": (
        ("Coordinate or Lead Others in Accomplishing Work Activities", 1),
        ("Work Outcomes and Results of Other Workers", 1),
    ),
    "desk": (
        ("Spend Time Sitting", 1),
        ("Spend Time Standing", -1),
        ("Spend Time Walking or Running", -1),
    ),
    "outdoors": (
        ("Outdoors, Exposed to All Weather Conditions", 1),
        ("Outdoors, Under Cover", 1),
        ("Indoors, Environmentally Controlled", -1),
    ),
    "autonomy": (
        ("Freedom to Make Decisions", 1),
        ("Determine Tasks, Priorities and Goals", 1),
    ),
    #: Weak; see the module docstring.  Built, not asked about.
    "pace": (("Time Pressure", 1),),
}

AXIS_NAMES: tuple[str, ...] = tuple(AXES)

#: The report every axis is built from today.
_AXIS_REPORT = "work_context"


# ---------------------------------------------------------------------------
# The loaded table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConditionsTable:
    """Per-occupation axis percentiles, as the scorer reads them.

    ``percentiles[code][axis]`` is in [0, 1] and is a **rank across the
    occupations that have a value for that axis**, not a rescaled O*NET value.
    ``raw[code][axis]`` is the bundle mean in [0, 1] that the rank was taken
    over, kept so a number on a card can be traced back to the report.

    A code absent from ``percentiles`` has no ratings at all; a code present
    without a given axis has none for that axis.  Both are answered with None by
    :meth:`percentile`, and the scorer skips rather than penalises -- see
    ``path_scoring._conditions_shortfall``.
    """

    percentiles: Mapping[str, Mapping[str, float]]
    raw: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    source: str = ""
    built_at: str = ""
    path: Path | None = None

    @property
    def count(self) -> int:
        return len(self.percentiles)

    def percentile(self, code: str, axis: str) -> float | None:
        """Rank of *code* on *axis*, or None when it is not measured."""
        return self.percentiles.get(code, {}).get(axis)

    def coverage(self, axis: str) -> int:
        """How many occupations carry a value for *axis*."""
        return sum(1 for values in self.percentiles.values() if axis in values)


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


def iter_raw_rows(path: str | os.PathLike[str]) -> Iterator[dict[str, Any]]:
    """Yield the records of a fetched JSONL: ``{code, title, reports}``.

    Blank lines are skipped; a malformed line is a build failure rather than a
    silently dropped occupation, because a half-built conditions table looks
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


def _bundle_mean(report: Mapping[str, Any], bundle: Sequence[tuple[str, int]]) -> float | None:
    """The mean of the elements PRESENT in *report*, on a 0-1 scale, or None.

    A missing element is skipped, never scored zero.  That distinction is the
    whole reason this is a function: ``desk`` averages sitting against standing
    and walking, and an occupation O*NET never rated for walking is not an
    occupation nobody walks in.
    """
    parts: list[float] = []
    for element, sign in bundle:
        value = report.get(element)
        if value is None:
            continue
        try:
            scaled = float(value) / 100.0
        except (TypeError, ValueError):
            continue
        parts.append(scaled if sign > 0 else 1.0 - scaled)
    if not parts:
        return None
    return sum(parts) / len(parts)


def _percentile_ranks(values: Mapping[str, float]) -> dict[str, float]:
    """Rank *values* onto [0, 1], lowest 0.0 and highest 1.0.

    Ties are broken by code so the file is reproducible: two occupations with
    the same bundle mean would otherwise land in whichever order the dict
    happened to iterate, and a sidecar that differs between two builds of the
    same input is a sidecar nobody can diff.
    """
    ordered = sorted(values.items(), key=lambda pair: (pair[1], pair[0]))
    last = len(ordered) - 1
    if last <= 0:
        return {code: 0.5 for code, _ in ordered}
    return {code: rank / last for rank, (code, _) in enumerate(ordered)}


def build_table(
    rows: Iterable[Mapping[str, Any]],
    source: str = "",
) -> ConditionsTable:
    """Build a :class:`ConditionsTable` from fetched report records.

    *rows* are ``{"code", "title", "reports": {report: {element: 0-100}}}`` --
    what :func:`fetch_condition_reports` produces and what the prototype's
    ``onet_experience_raw.jsonl`` already holds.

    **"..., All Other" rows are excluded from the ranking**, which is the same
    rule ``occupation_clusters`` applies to its fit and for a related reason:
    retrieval never returns them, so letting them into the denominator would
    shift every percentile by rows no user can be shown.  In practice the
    prototype's fetch already skipped them; the filter is here so a future fetch
    that does not cannot quietly change everyone's numbers.
    """
    raw: dict[str, dict[str, float]] = {}
    for row in rows:
        code = str(row.get("code") or "")
        if not code:
            continue
        if is_all_other_title(str(row.get("title") or "")):
            continue
        report = (row.get("reports") or {}).get(_AXIS_REPORT) or {}
        values = {
            axis: mean
            for axis, bundle in AXES.items()
            if (mean := _bundle_mean(report, bundle)) is not None
        }
        if values:
            raw[code] = values

    percentiles: dict[str, dict[str, float]] = {code: {} for code in raw}
    for axis in AXES:
        have = {code: values[axis] for code, values in raw.items() if axis in values}
        for code, rank in _percentile_ranks(have).items():
            percentiles[code][axis] = round(rank, 6)

    return ConditionsTable(
        percentiles=percentiles,
        raw={code: {a: round(v, 6) for a, v in values.items()} for code, values in raw.items()},
        source=source,
        built_at=_utc_now_iso(),
    )


# ---------------------------------------------------------------------------
# Fetching (build time only -- never the request path)
# ---------------------------------------------------------------------------


def fetch_condition_reports(
    onet_client: Any,
    rows: Sequence[tuple[str, str]],
    limiter: Any = None,
    already_done: Iterable[str] = (),
    on_record: Callable[[dict[str, Any]], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Fetch the three ``details/`` reports for each ``(code, title)`` in *rows*.

    **Three requests per occupation**, so the whole catalog is ~2,800 -- which
    is why this is resumable: *already_done* skips codes a previous run
    recorded, and *on_record* is called with each record as it completes so the
    caller can append it to a checkpoint file before the next one starts.  A run
    that dies at row 800 costs 800 requests, not 2,800.

    A report that errors is stored as an empty mapping with the error noted on
    the record rather than aborting: one occupation missing ``interests`` is a
    gap in a file that nothing reads yet, and losing the other 938 rows to it
    would be the wrong trade.  A rate-limit error IS raised, because continuing
    past one just burns the remaining budget on 429s.
    """
    from backend.services.onet_client import OnetAPIError

    done = set(already_done)
    records: list[dict[str, Any]] = []
    for index, (code, title) in enumerate(rows, start=1):
        if code in done:
            continue
        record: dict[str, Any] = {"code": code, "title": title, "reports": {}}
        for report in REPORT_VALUE_FIELDS:
            if limiter is not None:
                limiter.acquire()
            try:
                record["reports"][report] = _fetch_one(onet_client, code, report)
            except OnetAPIError as exc:
                record["reports"][report] = {}
                record.setdefault("errors", {})[report] = str(exc)[:200]
        records.append(record)
        if on_record is not None:
            on_record(record)
        if on_progress is not None and index % 50 == 0:
            on_progress(f"  {index}/{len(rows)} occupations")
    return records


def _fetch_one(onet_client: Any, code: str, report: str) -> dict[str, float]:
    """One report for one occupation, through the typed client method."""
    method = {
        "work_context": onet_client.get_work_context,
        "work_styles": onet_client.get_work_styles,
        "interests": onet_client.get_occupational_interests,
    }[report]
    return method(code)


# ---------------------------------------------------------------------------
# The sidecar
# ---------------------------------------------------------------------------


def conditions_sidecar_path(matrix_path: str | os.PathLike[str]) -> Path:
    """The ``*.experience.json`` that belongs beside *matrix_path*."""
    path = Path(matrix_path)
    return path.with_name(path.stem + ".experience.json")


def write_conditions_sidecar(
    matrix_path: str | os.PathLike[str],
    table: ConditionsTable,
) -> Path:
    """Write ``<artifact>.experience.json`` beside *matrix_path*; return its path.

    Atomic, like the other two sidecars: a reader sees the old file or the new
    one and never half of either.
    """
    path = conditions_sidecar_path(matrix_path)
    payload = {
        "schema_version": CONDITIONS_SCHEMA_VERSION,
        "matrix_filename": Path(matrix_path).name,
        "source": table.source,
        "built_at": table.built_at or _utc_now_iso(),
        "count": table.count,
        "axes": list(AXIS_NAMES),
        "elements": {axis: [name for name, _ in bundle] for axis, bundle in AXES.items()},
        "coverage": {axis: table.coverage(axis) for axis in AXIS_NAMES},
        "percentiles": {code: dict(values) for code, values in sorted(table.percentiles.items())},
        "raw": {code: dict(values) for code, values in sorted(table.raw.items())},
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    return path


def _load_sidecar(path: Path) -> ConditionsTable | None:
    """Read the sidecar, or return None if it is absent or unusable.

    Degrades rather than fails, like ``occupation_retrieval._load_zones`` and
    ``occupation_clusters._load_sidecar``: a corpus with no conditions file
    still answers every question except "how much of the day is spent with
    people", and the scorer drops one term instead of the request.
    """
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        version = raw.get("schema_version")
        if version != CONDITIONS_SCHEMA_VERSION:
            raise ValueError(
                f"conditions sidecar schema_version {version!r}, "
                f"expected {CONDITIONS_SCHEMA_VERSION}"
            )
        percentiles = {
            str(code): {
                str(axis): float(value)
                for axis, value in (values or {}).items()
                if value is not None
            }
            for code, values in (raw.get("percentiles") or {}).items()
        }
        raw_values = {
            str(code): {
                str(axis): float(value)
                for axis, value in (values or {}).items()
                if value is not None
            }
            for code, values in (raw.get("raw") or {}).items()
        }
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        _log.warning(
            "occupation conditions: ignoring unusable sidecar %s (%s); the "
            "wants layer will score without conditions",
            path,
            exc,
        )
        return None

    percentiles = {code: values for code, values in percentiles.items() if values}
    if not percentiles:
        return None
    return ConditionsTable(
        percentiles=percentiles,
        raw=raw_values,
        source=str(raw.get("source") or ""),
        built_at=str(raw.get("built_at") or ""),
        path=path,
    )


# ---------------------------------------------------------------------------
# Process-wide access
# ---------------------------------------------------------------------------

_LOCK = threading.Lock()
_TABLE: ConditionsTable | None = None
_TABLE_FOR: str | None = None
_MISSING_LOGGED: set[str] = set()


def get_conditions(corpus: OccupationCorpus) -> ConditionsTable | None:
    """The conditions table beside *corpus*, or None when there is no sidecar.

    Memoised per corpus version for the life of the process and lock-guarded,
    exactly as ``occupation_clusters.get_assignment`` is -- but with **no
    in-process fallback**, because there is nothing to fall back to: the numbers
    come from 2,733 O*NET requests and cannot be derived from the artifact.  A
    missing file is therefore the degrade this returns None for, logged **once
    per corpus** so a server without the sidecar says so at startup instead of
    on every request.

    Nothing here imports scikit-learn, touches the network, or runs in
    ``create_app()``: it is a dict read behind a memo, first paid for by
    whichever request first asks a user's stated conditions about.
    """
    global _TABLE, _TABLE_FOR

    key = corpus.version
    cached = _TABLE
    if cached is not None and _TABLE_FOR == key:
        return cached

    with _LOCK:
        if _TABLE is not None and _TABLE_FOR == key:
            return _TABLE
        path = conditions_sidecar_path(corpus.matrix_path)
        table = _load_sidecar(path)
        if table is None:
            if key not in _MISSING_LOGGED:
                _MISSING_LOGGED.add(key)
                _log.warning(
                    "no conditions sidecar beside %s; stated work conditions "
                    "are being ignored and only the task rotation applies.  "
                    "Run `flask corpus experience`",
                    corpus.matrix_path.name,
                )
            return None
        _TABLE, _TABLE_FOR = table, key
        _log.info(
            "occupation conditions: loaded %d occupations from %s",
            table.count,
            path.name,
        )
        return table


def reset_conditions_cache() -> None:
    """Drop the memo.  Tests and the CLI; nothing in a request path."""
    global _TABLE, _TABLE_FOR
    with _LOCK:
        _TABLE, _TABLE_FOR = None, None
        _MISSING_LOGGED.clear()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
