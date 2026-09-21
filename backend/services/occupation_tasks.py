"""The tasks the wants panel asks about -- the wants layer's first signal.

BUILD_PLAN W-3 (built in W-3b), design doc ``docs/PATH_INTELLIGENCE_REDESIGN.md``
§8.2/§8.3/§8.7.

WHAT THIS IS FOR
----------------
W-4's panel shows the user **their own job's tasks** and asks *more of this /
less of this* about each one, and ``path_scoring`` rotates the query with the
embeddings of whatever they marked.  O*NET gives an occupation 5 to 41 task
statements -- median 19 -- which is a wall of formal prose, not a panel.  This
module picks **up to eight of them, chosen for spread**, and writes a plain-words
display label beside each.

**SPREAD, not importance.**  A user marking *more* and *less* needs eight items
that differ from each other; eight paraphrases of the same duty collect one bit
of information eight times.  Software Developers' list contains "Develop or
direct software system testing or validation procedures, programming, or
documentation", "Design, develop and modify software systems..." and "Modify
existing software to correct errors..." -- three ways of saying *write software*,
and a panel that spends three of its eight rows on them cannot find out that the
person wants to stop doing it and talk to customers instead.  Selection is
therefore greedy farthest-point over the task embeddings, seeded with O*NET's
own first statement so the most representative one is always on the panel.

**TWO STRINGS PER TASK, AND THEY ARE NOT INTERCHANGEABLE.**

* ``task`` is the O*NET statement, byte-exact.  It is the ONLY thing that is
  ever embedded -- at request time, for the tapped tasks only (design doc §8.3;
  every task of every job precomputed is ~120 MB at float32 on a 512 MB
  instance).
* ``label`` is display prose and reaches a human eye and nothing else.

F-7 measured why that line has to be drawn in the data rather than in a
convention: an LLM wrote "prevent a fire" into a path narrative, an embedder
read it literally, and five firefighting occupations came back.  Design doc §8.7
keeps the original text on the scoring side for exactly that reason, and
``test_occupation_tasks.py`` asserts the labels never reach an embedder.

THE SIDECAR
-----------
``<artifact>.tasks.json``, beside the ``.npy``, exactly as ``*.zones.json``,
``*.clusters.json`` and ``*.experience.json`` are -- and for the same three
reasons: no network on the request path, every worker reads the same strings,
and data derived from the artifact is not the artifact.

**A missing sidecar is a DEGRADE, not an error.**  :func:`get_tasks` returns
None, one warning is logged per corpus, and W-4's panel shows its conditions
half with no task half.  A user can still say what kind of day they want; they
just cannot say it about their own duties.  That is a worse answer, not a broken
one -- the judgement ``occupation_conditions`` and ``_load_zones`` both make
about their own optional files.

WHAT IS NOT HERE
----------------
Ranking, scoring, and any notion of which task matters more.  This module
answers "which eight sentences should the panel show for this occupation, and
what do they say in plain words".  ``path_scoring`` owns what a tap on one of
them does.
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
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

from backend.services.occupation_retrieval import (
    OccupationCorpus,
    is_all_other_title,
)

_log = logging.getLogger(__name__)

__all__ = [
    "LABEL_MAX_WORDS",
    "LABEL_MIN_WORDS",
    "MAX_TASKS_PER_OCCUPATION",
    "OccupationTask",
    "TASKS_SCHEMA_VERSION",
    "TasksTable",
    "build_table",
    "get_tasks",
    "iter_documents",
    "label_occupation",
    "reset_tasks_cache",
    "select_task_indexes",
    "tasks_for",
    "tasks_sidecar_path",
    "write_tasks_sidecar",
]

#: Sidecar schema version.  Independent of the corpus artifact's and of the
#: other three sidecars', for the reason ``ZONES_SCHEMA_VERSION`` gives: the
#: files are written by different commands and regenerate independently.
TASKS_SCHEMA_VERSION = 1

#: How many task rows the panel gets at most.
#:
#: Design doc §8.3 says "about eight".  Eight is also where the label bill stops
#: being a rounding error (~7,400 statements across the catalog) and, more to the
#: point, where a one-screen skippable panel stops being one screen -- ⚑7's
#: lesson is that a step before any value is friction, and a 20-row form is a
#: step.  Occupations with fewer than eight statements keep all of them.
MAX_TASKS_PER_OCCUPATION = 8

#: A display label is a short gerund phrase: "Fixing bugs in existing software".
#: The bounds are deliberately wider than the prompt asks for (3-10), so the
#: validator rejects real failures -- an empty string, a restated paragraph --
#: and not a good label that came back one word long or short.
LABEL_MIN_WORDS = 2
LABEL_MAX_WORDS = 12

#: The chat model the label pass uses, and where the price of a run comes from.
#:
#: ``gpt-4o-mini`` because it is what ``path_narrative`` and ``insight_service``
#: already select (``OPENAI_NARRATIVE_MODEL`` / ``OPENAI_QUIZ_MODEL`` both
#: default to it) -- this adds no provider, no dependency and no second model to
#: reason about.  The rates are OpenAI's list price per 1M tokens as of
#: 2026-09-21 and are here only to let ``flask corpus tasks`` project a bill
#: from a 25-occupation sample before spending the rest; nothing reads them at
#: request time.
DEFAULT_LABEL_MODEL = "gpt-4o-mini"
_USD_PER_1M_INPUT = 0.15
_USD_PER_1M_OUTPUT = 0.60

#: A label that arrives as "1. Fixing bugs" is the model numbering its list
#: rather than answering; caught rather than shipped with the digits in it.
_NUMBERING = re.compile(r"^\s*\d+\s*[.)]\s*")


# ---------------------------------------------------------------------------
# The loaded table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OccupationTask:
    """One panel row: what O*NET said, and what the user reads.

    ``task`` is what gets embedded and ``label`` is what gets displayed.  They
    are separate fields rather than one field and a formatter because the
    difference is a measured hazard, not a presentation choice -- see the module
    docstring.
    """

    task: str
    label: str


@dataclass(frozen=True)
class TasksTable:
    """Per-occupation panel rows, as W-4 reads them.

    A code absent from ``tasks`` was not in the corpus documents the sidecar was
    built from; a code present with an empty tuple is an occupation O*NET
    publishes **no** task statements for (16 of the 939 retrievable rows, all of
    them military).  Both answer with ``()`` and neither is an error: the panel
    shows its conditions half and no task half.
    """

    tasks: Mapping[str, tuple[OccupationTask, ...]]
    source: str = ""
    built_at: str = ""
    label_model: str = ""
    label_fallbacks: int = 0
    path: Path | None = None

    @property
    def count(self) -> int:
        """Occupations in the table, including those with no statements."""
        return len(self.tasks)

    @property
    def task_count(self) -> int:
        return sum(len(rows) for rows in self.tasks.values())

    def for_code(self, code: str) -> tuple[OccupationTask, ...]:
        return self.tasks.get(code, ())


# ---------------------------------------------------------------------------
# Reading the corpus documents
# ---------------------------------------------------------------------------


def iter_documents(path: str | os.PathLike[str]) -> Iterator[dict[str, Any]]:
    """Yield the records of ``*.documents.jsonl``: ``{code, title, tasks, ...}``.

    Blank lines are skipped; a malformed line is a build failure rather than a
    silently dropped occupation, for the reason
    ``occupation_conditions.iter_raw_rows`` gives -- a half-built sidecar looks
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


def documents_path_for(matrix_path: str | os.PathLike[str]) -> Path:
    """The ``*.documents.jsonl`` ``corpus build`` wrote beside *matrix_path*."""
    path = Path(matrix_path)
    return path.with_name(path.stem + ".documents.jsonl")


def _statements(row: Mapping[str, Any]) -> list[str]:
    """The occupation's task statements, trimmed, deduplicated, in O*NET order.

    Deduplicated because two identical statements would be two identical panel
    rows, and because the label validator's "no two rows say the same thing"
    rule would then fail on data rather than on a bad label.
    """
    seen: dict[str, None] = {}
    for task in row.get("tasks") or []:
        text = str(task).strip()
        if text:
            seen.setdefault(text, None)
    return list(seen)


# ---------------------------------------------------------------------------
# Selection -- greedy farthest-point, seeded with O*NET's first statement
# ---------------------------------------------------------------------------


def select_task_indexes(
    vectors: Any,
    limit: int = MAX_TASKS_PER_OCCUPATION,
) -> list[int]:
    """Indexes of up to *limit* statements chosen for SPREAD, in O*NET order.

    *vectors* is an ``(N, D)`` array of unit-length task embeddings.  Index 0 is
    always taken -- that is O*NET's own first statement, the closest thing the
    data has to "the representative one", and anchoring the set means the panel
    never opens on an oddity.  Each further pick is the statement whose
    similarity to its NEAREST already-chosen neighbour is lowest, which is
    farthest-point sampling: it maximises the smallest gap in the set rather
    than the average one, so the eight rows are eight different questions.

    **Deterministic.**  Ties go to the lower index (the comparison is strict),
    so the same corpus builds the same sidecar twice -- the property
    ``occupation_conditions._percentile_ranks`` needs for the same reason: a
    sidecar that differs between two builds of the same input is a sidecar
    nobody can diff.

    Returns indexes in the original O*NET order, not pick order.  The file is a
    display artifact and O*NET's order is the only ordering in the data that
    means anything to a reader.
    """
    import numpy as np  # noqa: PLC0415 -- build path only; see module docstring

    total = len(vectors)
    if total <= limit:
        return list(range(total))

    chosen = [0]
    # `nearest[i]` is i's similarity to the closest statement already chosen.
    nearest = np.asarray(vectors @ vectors[0], dtype=float)
    while len(chosen) < limit:
        best = -1
        for index in range(total):
            if index in chosen:
                continue
            if best < 0 or nearest[index] < nearest[best]:
                best = index
        chosen.append(best)
        nearest = np.maximum(nearest, np.asarray(vectors @ vectors[best], dtype=float))
    return sorted(chosen)


def _unit_rows(matrix: Any) -> Any:
    """L2-normalise every row so a dot product is a cosine."""
    import numpy as np  # noqa: PLC0415 -- build path only

    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return matrix / norms


# ---------------------------------------------------------------------------
# Labels -- one offline LLM pass, never the request path
# ---------------------------------------------------------------------------

_LABEL_SYSTEM = (
    "You rewrite O*NET occupation task statements as short, plain display "
    "labels for a web form. The user is about to tick 'I want more of this' or "
    "'less of this' beside each label, so each one has to name a concrete piece "
    "of their day in words they would use themselves."
)

_LABEL_RULES = """Rewrite each numbered task statement as a display label.

Rules for every label:
- a gerund phrase, 3 to 10 words, e.g. "Fixing bugs in existing software" or
  "Explaining technical issues to customers"
- plain words a person would use about their own day; no jargon, no O*NET
  vocabulary, no job-description register
- keep the concrete object of the task. "Working with systems" is useless;
  "Setting up new user accounts" is the label
- no metaphors, no figurative language, no analogies -- write only what is
  literally done
- no numbering, no leading dash, no trailing period, no quotation marks
- two labels for the same job must not say the same thing

Reply with JSON only: {"labels": ["...", "..."]} -- exactly one label per
statement, in the same order as the statements."""


def _label_prompt(title: str, statements: Sequence[str]) -> list[dict[str, str]]:
    listing = "\n".join(
        f"{n}. {text}" for n, text in enumerate(statements, start=1)
    )
    return [
        {"role": "system", "content": _LABEL_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Occupation: {title}\n\n{_LABEL_RULES}\n\n"
                f"Statements:\n{listing}"
            ),
        },
    ]


def validate_label(label: Any, others: Iterable[str] = ()) -> str | None:
    """Return the cleaned label, or None when it must not be shipped.

    Four failures, each of them one seen in a real LLM list-rewrite: an empty
    or non-string reply; a restated paragraph (or a one-word stub); the model
    numbering its own output; and two rows of the same job collapsing onto the
    same phrase, which turns two questions into one asked twice.
    """
    if not isinstance(label, str):
        return None
    text = " ".join(label.strip().strip('"').split())
    if not text:
        return None
    if _NUMBERING.match(label.strip()):
        return None
    if not (LABEL_MIN_WORDS <= len(text.split()) <= LABEL_MAX_WORDS):
        return None
    lowered = text.rstrip(".").casefold()
    if any(lowered == other.rstrip(".").casefold() for other in others):
        return None
    return text.rstrip(".")


def label_occupation(
    openai_client: Any,
    title: str,
    statements: Sequence[str],
    model: str = DEFAULT_LABEL_MODEL,
    usage: dict[str, int] | None = None,
) -> tuple[list[str], int]:
    """Plain-words labels for one occupation's chosen statements.

    **One request per occupation**, all of its statements in it: the model sees
    the other seven while writing each label, which is what makes "two labels
    for the same job must not say the same thing" a rule it can follow rather
    than a coincidence to check for afterwards.

    Returns ``(labels, fallbacks)`` with exactly ``len(statements)`` labels.
    Every label is validated; if any fails the whole request is retried **once**
    (a second sample fixes most of them), and any that still fails falls back to
    the original O*NET statement and is counted.  A statement is a poor label
    and a perfectly honest one -- it is what the panel would have shown before
    this pass existed -- so a bad label is never shipped and a failed run never
    costs the row.
    """
    if not statements:
        return [], 0

    labels: list[str | None] = [None] * len(statements)
    for _attempt in range(2):
        received = _request_labels(openai_client, title, statements, model, usage)
        accepted: list[str] = [text for text in labels if text]
        for index, candidate in enumerate(received[: len(statements)]):
            if labels[index] is not None:
                continue
            cleaned = validate_label(candidate, accepted)
            if cleaned is not None:
                labels[index] = cleaned
                accepted.append(cleaned)
        if all(text is not None for text in labels):
            break

    fallbacks = sum(1 for text in labels if text is None)
    if fallbacks:
        _log.info(
            "occupation tasks: %d of %d labels for %s fell back to the O*NET "
            "statement",
            fallbacks,
            len(statements),
            title,
        )
    return [
        text if text is not None else statements[index]
        for index, text in enumerate(labels)
    ], fallbacks


def _request_labels(
    openai_client: Any,
    title: str,
    statements: Sequence[str],
    model: str,
    usage: dict[str, int] | None,
) -> list[Any]:
    """One chat completion; any failure is an empty list, never an exception.

    A build that walks 923 occupations must not die on one 500 from OpenAI --
    the occupation falls back to its statements and the run carries on, which is
    the same trade ``occupation_conditions.fetch_condition_reports`` makes about
    one failed report.
    """
    try:
        response = openai_client.chat.completions.create(
            model=model,
            messages=_label_prompt(title, statements),
            response_format={"type": "json_object"},
        )
    except Exception as exc:  # noqa: BLE001 -- one occupation, never the run
        _log.warning("occupation tasks: label request failed for %s (%s)", title, exc)
        return []

    if usage is not None:
        counts = getattr(response, "usage", None)
        usage["requests"] = usage.get("requests", 0) + 1
        usage["prompt_tokens"] = usage.get("prompt_tokens", 0) + int(
            getattr(counts, "prompt_tokens", 0) or 0
        )
        usage["completion_tokens"] = usage.get("completion_tokens", 0) + int(
            getattr(counts, "completion_tokens", 0) or 0
        )

    try:
        content = response.choices[0].message.content or "{}"
        payload = json.loads(content)
    except (AttributeError, IndexError, TypeError, ValueError) as exc:
        _log.warning("occupation tasks: unreadable label reply for %s (%s)", title, exc)
        return []
    if isinstance(payload, list):
        return list(payload)
    labels = payload.get("labels") if isinstance(payload, dict) else None
    return list(labels) if isinstance(labels, list) else []


def project_label_cost(usage: Mapping[str, int], sampled: int, total: int) -> dict[str, Any]:
    """Extrapolate a full label pass from a sample's measured token usage.

    The spend gate: a 25-occupation sample is ~3% of the catalog and costs
    fractions of a cent, and it is the only honest way to price the rest --
    task lists vary from 5 statements to 41 and a per-token guess from the
    prompt alone is off by whatever the average list length turns out to be.
    """
    scale = (total / sampled) if sampled else 0.0
    prompt = usage.get("prompt_tokens", 0) * scale
    completion = usage.get("completion_tokens", 0) * scale
    usd = prompt / 1e6 * _USD_PER_1M_INPUT + completion / 1e6 * _USD_PER_1M_OUTPUT
    return {
        "sampled_occupations": sampled,
        "total_occupations": total,
        "sample_prompt_tokens": usage.get("prompt_tokens", 0),
        "sample_completion_tokens": usage.get("completion_tokens", 0),
        "sample_usd": round(
            usage.get("prompt_tokens", 0) / 1e6 * _USD_PER_1M_INPUT
            + usage.get("completion_tokens", 0) / 1e6 * _USD_PER_1M_OUTPUT,
            6,
        ),
        "projected_prompt_tokens": int(prompt),
        "projected_completion_tokens": int(completion),
        "projected_usd": round(usd, 4),
        "model": DEFAULT_LABEL_MODEL,
    }


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


def build_table(
    rows: Iterable[Mapping[str, Any]],
    openai_client: Any = None,
    *,
    source: str = "",
    limit: int = MAX_TASKS_PER_OCCUPATION,
    label_model: str = DEFAULT_LABEL_MODEL,
    with_labels: bool = True,
    labels_for: Callable[[str, str, Sequence[str]], tuple[list[str], int]] | None = None,
    usage: dict[str, int] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> TasksTable:
    """Choose and label every retrievable occupation's panel rows.

    *rows* are ``*.documents.jsonl`` records.  **"..., All Other" rows are
    excluded**, the same rule ``occupation_conditions.build_table`` and
    ``occupation_clusters`` apply and for the same reason: retrieval never
    returns one, so a panel for one can never be asked for.

    ``with_labels=False`` writes each statement as its own label.  That costs
    nothing, needs no OpenAI client, and is what every test uses -- the pass
    this flag turns off is a *display* pass, so a sidecar without it is
    structurally identical and only reads worse.

    *labels_for* is the resumable seam: the CLI passes a callable that consults
    its checkpoint file first and only calls :func:`label_occupation` for
    occupations it has not already paid for.  Default is the plain call.
    """
    import numpy as np  # noqa: PLC0415 -- build path only

    from backend.services.occupation_corpus import embed_documents  # noqa: PLC0415

    write_label = labels_for
    if write_label is None:
        def write_label(code, title, statements):  # type: ignore[misc]
            return label_occupation(
                openai_client, title, statements, label_model, usage
            )

    # Pass one: read the documents and split the occupations into those short
    # enough to keep whole and those that need choosing between.
    keep: dict[str, tuple[str, list[str]]] = {}
    crowded: list[tuple[str, str, list[str]]] = []
    for row in rows:
        code = str(row.get("code") or "")
        title = str(row.get("title") or "")
        if not code or is_all_other_title(title):
            continue
        statements = _statements(row)
        if len(statements) <= limit:
            keep[code] = (title, statements)
        else:
            crowded.append((code, title, statements))

    # Pass two: **one** embedding sequence for every statement that needs
    # choosing between, not one per occupation.  `embed_documents` already
    # batches to OpenAI's input and character caps, so handing it the whole
    # catalog at once is ~7 requests instead of ~900 -- the difference between
    # a build that takes a minute and one that takes twenty.
    flat = [text for _code, _title, statements in crowded for text in statements]
    if flat:
        if on_progress is not None:
            on_progress(f"  embedding {len(flat)} statements for selection")
        matrix, _calls = embed_documents(flat, openai_client, on_progress=on_progress)
        matrix = _unit_rows(np.asarray(matrix, dtype=np.float32))
        offset = 0
        for code, title, statements in crowded:
            block = matrix[offset : offset + len(statements)]
            offset += len(statements)
            picked = select_task_indexes(block, limit)
            keep[code] = (title, [statements[index] for index in picked])

    # Pass three: the label pass, in CODE ORDER so a resumed run walks the
    # occupations in the order the checkpoint holds them.
    tasks: dict[str, tuple[OccupationTask, ...]] = {}
    fallbacks = 0
    for number, (code, (title, statements)) in enumerate(sorted(keep.items()), start=1):
        if not statements:
            tasks[code] = ()
            continue
        if with_labels:
            labels, missed = write_label(code, title, statements)
            fallbacks += missed
        else:
            labels = list(statements)
        tasks[code] = tuple(
            OccupationTask(task=statement, label=labels[index])
            for index, statement in enumerate(statements)
        )
        if on_progress is not None and number % 50 == 0:
            on_progress(f"  labelled {number}/{len(keep)} occupations")

    return TasksTable(
        tasks=tasks,
        source=source,
        built_at=_utc_now_iso(),
        label_model=label_model if with_labels else "",
        label_fallbacks=fallbacks,
    )


# ---------------------------------------------------------------------------
# The sidecar
# ---------------------------------------------------------------------------


def tasks_sidecar_path(matrix_path: str | os.PathLike[str]) -> Path:
    """The ``*.tasks.json`` that belongs beside *matrix_path*."""
    path = Path(matrix_path)
    return path.with_name(path.stem + ".tasks.json")


def write_tasks_sidecar(
    matrix_path: str | os.PathLike[str],
    table: TasksTable,
) -> Path:
    """Write ``<artifact>.tasks.json`` beside *matrix_path*; return its path.

    Atomic, like the other three sidecars: a reader sees the old file or the new
    one and never half of either.
    """
    path = tasks_sidecar_path(matrix_path)
    payload = {
        "schema_version": TASKS_SCHEMA_VERSION,
        "matrix_filename": Path(matrix_path).name,
        "source": table.source,
        "built_at": table.built_at or _utc_now_iso(),
        "count": table.count,
        "task_count": table.task_count,
        "max_per_occupation": MAX_TASKS_PER_OCCUPATION,
        "label_model": table.label_model,
        "label_fallbacks": table.label_fallbacks,
        "tasks": {
            code: [{"task": row.task, "label": row.label} for row in rows]
            for code, rows in sorted(table.tasks.items())
        },
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    return path


def _load_sidecar(path: Path) -> TasksTable | None:
    """Read the sidecar, or return None if it is absent or unusable.

    Degrades rather than fails, like every other optional file beside the
    artifact: a corpus with no tasks file still answers every question except
    "what does this person actually do all day".
    """
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        version = raw.get("schema_version")
        if version != TASKS_SCHEMA_VERSION:
            raise ValueError(
                f"tasks sidecar schema_version {version!r}, "
                f"expected {TASKS_SCHEMA_VERSION}"
            )
        tasks = {
            str(code): tuple(
                OccupationTask(
                    task=str(row["task"]),
                    label=str(row.get("label") or row["task"]),
                )
                for row in (rows or [])
                if row.get("task")
            )
            for code, rows in (raw.get("tasks") or {}).items()
        }
    except (OSError, KeyError, ValueError, TypeError, AttributeError) as exc:
        _log.warning(
            "occupation tasks: ignoring unusable sidecar %s (%s); the wants "
            "panel will have no task half",
            path,
            exc,
        )
        return None

    if not tasks:
        return None
    return TasksTable(
        tasks=tasks,
        source=str(raw.get("source") or ""),
        built_at=str(raw.get("built_at") or ""),
        label_model=str(raw.get("label_model") or ""),
        label_fallbacks=int(raw.get("label_fallbacks") or 0),
        path=path,
    )


# ---------------------------------------------------------------------------
# Process-wide access
# ---------------------------------------------------------------------------

_LOCK = threading.Lock()
_TABLE: TasksTable | None = None
_TABLE_FOR: str | None = None
_MISSING_LOGGED: set[str] = set()


def get_tasks(corpus: OccupationCorpus) -> TasksTable | None:
    """The tasks table beside *corpus*, or None when there is no sidecar.

    Memoised per corpus version for the life of the process and lock-guarded,
    exactly as ``occupation_conditions.get_conditions`` is, and with the same
    **no in-process fallback**: the labels come from an offline LLM pass and
    cannot be derived from the artifact at request time.  A missing file is the
    degrade this returns None for, logged **once per corpus** so a server
    without the sidecar says so on the first panel request rather than on every
    one.

    Nothing here imports scikit-learn, touches the network, or runs in
    ``create_app()``: it is a dict read behind a memo, first paid for by
    whichever request first opens a wants panel.
    """
    global _TABLE, _TABLE_FOR

    key = corpus.version
    cached = _TABLE
    if cached is not None and _TABLE_FOR == key:
        return cached

    with _LOCK:
        if _TABLE is not None and _TABLE_FOR == key:
            return _TABLE
        path = tasks_sidecar_path(corpus.matrix_path)
        table = _load_sidecar(path)
        if table is None:
            if key not in _MISSING_LOGGED:
                _MISSING_LOGGED.add(key)
                _log.warning(
                    "no tasks sidecar beside %s; the wants panel has no task "
                    "half and only the conditions can be stated.  "
                    "Run `flask corpus tasks`",
                    corpus.matrix_path.name,
                )
            return None
        _TABLE, _TABLE_FOR = table, key
        _log.info(
            "occupation tasks: loaded %d occupations (%d tasks) from %s",
            table.count,
            table.task_count,
            path.name,
        )
        return table


def tasks_for(corpus: OccupationCorpus, code: str) -> tuple[OccupationTask, ...]:
    """The panel rows for one occupation; ``()`` when there are none.

    W-4's accessor.  One call, one answer, and no way for a caller to tell a
    missing sidecar from an occupation with no statements -- deliberately: the
    panel does the same thing in both cases, and a route that branched on the
    difference would be reporting our deployment state to a user.
    """
    table = get_tasks(corpus)
    return table.for_code(code) if table is not None else ()


def reset_tasks_cache() -> None:
    """Drop the memo.  Tests and the CLI; nothing in a request path."""
    global _TABLE, _TABLE_FOR
    with _LOCK:
        _TABLE, _TABLE_FOR = None, None
        _MISSING_LOGGED.clear()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
