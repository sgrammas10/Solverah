"""Response CSV -> parsed respondents. Pure: no database, no app, no network.

ITEM IDENTITY: HOW A CSV COLUMN BECOMES AN ITEM
-----------------------------------------------
A Google Forms export carries only what the respondent saw: a header row of question
TITLES and cells of option TEXTS. Free-text matching against the item banks would break on
the first copy edit, so nothing here matches against the banks at all. The generator wrote
`form_mapping.json` from the SAME spec it wrote the form from, and this module reads that:

* **Columns** are identified by (title, occurrence). The past-tense current-job section and
  the previous-job section ask identical questions, so their titles repeat; the n-th column
  with a given title is the n-th question with that title in form order, which is also the
  order Google writes the columns in. `resolve_columns` demands an EXACT match between the
  CSV header and the mapping -- every expected column present, nothing unexpected, nothing
  repeated more often than the form repeats it -- and refuses the whole file otherwise. A
  form edited after generation therefore fails loudly here instead of importing shifted
  answers.
* **Answers** are identified by exact option text within that column's question (whitespace
  collapsed). Option texts are unique per question by construction (`spec.validate_spec`),
  so the lookup is unambiguous. Text the question does not offer is not guessed at: that
  respondent is skipped with the reason.

PILOT IDS
---------
A Forms export has no response id. `pilot_id` is a hash of the respondent's whole row --
timestamp and every answer -- EXCLUDING the email cell, so it is stable across re-exports
(re-importing the same CSV, or a later CSV that also contains these rows, maps each row to
the same id) and carries nothing about who the respondent is. Two byte-identical rows
submitted in the same second would share an id and count once; that is accepted.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from . import PACKAGE_DIR
from .spec import (
    GATE_YES,
    SLOT_CURRENT_PAST,
    SLOT_CURRENT_PRESENT,
    SLOT_PREVIOUS,
    SLOTS,
    _norm,
)

MAPPING_PATH = Path(PACKAGE_DIR) / "form_mapping.json"

#: Which job slot the career-status answer routes to. first_job has none.
SLOT_FOR_STATUS = {
    "employed": SLOT_CURRENT_PRESENT,
    "between_jobs": SLOT_CURRENT_PAST,
}

ENV_CONTEXT_ITEMS = ("stage_size", "comp", "industry", "experienced")

PILOT_ID_LENGTH = 16


class MappingMismatch(ValueError):
    """The CSV's columns are not the columns this mapping was generated for."""


def load_mapping(path: Path = MAPPING_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="ascii"))


@dataclass
class JobAnswers:
    """One job section, already in the shape `POST /me/environment-report` takes."""

    slot: str
    subject: str
    answers: dict  # {env item_id: option key}
    stage_size: Any
    comp: Any
    industry: Any
    experienced: Any

    def payload(self) -> dict:
        return {
            "answers": dict(self.answers),
            "stage_size": self.stage_size,
            "comp": self.comp,
            "industry": self.industry,
            "experienced": self.experienced,
            "subject": self.subject,
        }


@dataclass
class ParsedResponse:
    pilot_id: str
    row_number: int  # 1-based data row in the CSV, for the summary
    career_status: Optional[str] = None
    core_choices: dict = field(default_factory=dict)
    current: Optional[JobAnswers] = None
    previous: Optional[JobAnswers] = None
    email: Optional[str] = None
    #: Set when nothing at all can be imported for this respondent.
    skip_reason: Optional[str] = None
    #: Parts that were not imported, with why -- the respondent is still imported.
    notes: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------
def resolve_columns(header: list, mapping: dict) -> dict:
    """{csv column index: mapping column} for every mapped column, plus the timestamp
    under the key "timestamp". Raises MappingMismatch unless the header is exactly the
    mapping's columns (any order Google chooses, but each exactly as often as expected)."""
    expected = {(_norm(c["title"]), c["occurrence"]): c for c in mapping["columns"]}
    resolved: dict = {}
    seen: dict = {}
    unexpected = []
    timestamp_index = None
    for index, raw in enumerate(header):
        title = _norm(raw)
        if title == mapping["timestamp_column"] and timestamp_index is None:
            timestamp_index = index
            continue
        seen[title] = seen.get(title, 0) + 1
        column = expected.get((title, seen[title]))
        if column is None:
            unexpected.append(raw if seen[title] == 1 else "%s (#%d)" % (raw, seen[title]))
            continue
        resolved[index] = column
    missing = [
        c["title"] if c["occurrence"] == 1 else "%s (#%d)" % (c["title"], c["occurrence"])
        for key, c in expected.items()
        if c not in resolved.values()
    ]
    problems = []
    if timestamp_index is None:
        problems.append("no %r column" % mapping["timestamp_column"])
    if unexpected:
        problems.append("%d column(s) the form does not have: %s"
                        % (len(unexpected), _ascii_list(unexpected)))
    if missing:
        problems.append("%d expected column(s) missing: %s"
                        % (len(missing), _ascii_list(missing)))
    if problems:
        raise MappingMismatch(
            "the CSV does not match form_mapping.json (%s). Was the form edited after it "
            "was generated, or is this a different form's export?" % "; ".join(problems)
        )
    resolved["timestamp"] = timestamp_index
    return resolved


def _ascii_list(titles: list, limit: int = 3) -> str:
    shown = [t.encode("ascii", "replace").decode("ascii")[:60] for t in titles[:limit]]
    more = "" if len(titles) <= limit else " (+%d more)" % (len(titles) - limit)
    return "; ".join(repr(t) for t in shown) + more


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------
def pilot_id_for(row: list, email_index: Optional[int]) -> str:
    """Stable id from the row's cells, with the email cell left out (see module doc)."""
    cells = [_norm(v) for i, v in enumerate(row) if i != email_index]
    digest = hashlib.sha256("\x1f".join(cells).encode("utf-8")).hexdigest()
    return digest[:PILOT_ID_LENGTH]


def _answer(column: dict, cell: str):
    """(answered, value). Raises ValueError for text the question does not offer."""
    text = _norm(cell)
    if not text:
        return False, None
    for option_text, answer in column["answers"]:
        if _norm(option_text) == text:
            return True, answer
    raise ValueError("unrecognised answer to %s" % (column["item_id"] or column["qid"]))


def _job(slot: str, cells: dict) -> tuple[Optional[JobAnswers], Optional[str]]:
    """(answers, None) for a complete section, (None, reason) for an incomplete one,
    (None, None) for a section nobody touched."""
    columns = cells.get(slot, {})
    answered = {item_id: v for item_id, (ok, v) in columns.items() if ok}
    if not answered:
        return None, None
    missing = sorted(item_id for item_id, (ok, _v) in columns.items() if not ok)
    if missing:
        return None, "%s section incomplete (%d of %d answered; first missing: %s)" % (
            slot, len(answered), len(columns), missing[0])
    return JobAnswers(
        slot=slot,
        subject=SLOTS[slot][1],
        answers={k: v for k, v in answered.items() if k not in ENV_CONTEXT_ITEMS},
        stage_size=answered["stage_size"],
        comp=answered["comp"],
        industry=answered["industry"],
        experienced=answered["experienced"],
    ), None


def parse_row(row: list, row_number: int, columns: dict, mapping: dict) -> ParsedResponse:
    """One CSV data row -> ParsedResponse. Never raises for respondent-level problems;
    they become `skip_reason` or `notes`."""
    email_index = next((i for i, c in columns.items()
                        if i != "timestamp" and c["role"] == "email"), None)
    parsed = ParsedResponse(pilot_id=pilot_id_for(row, email_index), row_number=row_number)

    core: dict = {}
    by_slot: dict = {}
    gate = status = None
    try:
        for index, column in columns.items():
            if index == "timestamp":
                continue
            cell = row[index] if index < len(row) else ""
            role = column["role"]
            if role == "email":
                value = _norm(cell)
                parsed.email = value if "@" in value else None
                continue
            ok, value = _answer(column, cell)
            if role == "core":
                if ok:
                    core[column["item_id"]] = value
            elif role == "career_status":
                status = value if ok else None
            elif role == "gate":
                gate = value if ok else None
            elif role in ("env", "context"):
                by_slot.setdefault(column["slot"], {})[column["item_id"]] = (ok, value)
    except ValueError as exc:
        parsed.skip_reason = str(exc)
        return parsed

    n_core = sum(1 for c in mapping["columns"] if c["role"] == "core")
    if len(core) != n_core:
        parsed.skip_reason = (
            "core incomplete (%d of %d answered) -- the app does not score a partial "
            "sitting" % (len(core), n_core))
        return parsed
    if status is None:
        parsed.skip_reason = "no career status"
        return parsed

    parsed.career_status = status
    parsed.core_choices = core

    wanted = SLOT_FOR_STATUS.get(status)
    for slot in (SLOT_CURRENT_PRESENT, SLOT_CURRENT_PAST):
        # The form's branching makes this unreachable; an edited form or a merged export
        # could not, and an answer about the wrong tense is not silently re-labelled.
        if slot != wanted and any(ok for ok, _v in by_slot.get(slot, {}).values()):
            parsed.notes.append("answers in the %s section ignored: career status is %s"
                                % (slot, status))
    if wanted is None:
        parsed.notes.append("first_job: no environment report, as in the app")
        if any(ok for ok, _v in by_slot.get(SLOT_PREVIOUS, {}).values()):
            parsed.notes.append("previous-job answers ignored for first_job")
        return parsed

    parsed.current, reason = _job(wanted, by_slot)
    if parsed.current is None:
        parsed.notes.append(reason or "%s section empty" % wanted)
        parsed.notes.append("no environment report written, as in the app")

    previous, reason = _job(SLOT_PREVIOUS, by_slot)
    if gate == GATE_YES:
        if previous is None:
            parsed.notes.append(reason or "previous-job section empty")
        elif parsed.current is None:
            parsed.notes.append("previous-job report not written: the app accepts one only "
                                "after a current report")
        else:
            parsed.previous = previous
    elif previous is not None or reason:
        parsed.notes.append("previous-job answers ignored: the gate answer was %s"
                            % (gate or "blank"))
    return parsed


def parse_csv(text: str, mapping: Optional[dict] = None) -> list:
    """Every data row of a response CSV, parsed. Raises MappingMismatch on a header that
    does not match. Rows whose pilot_id repeats an earlier row are marked as duplicates."""
    mapping = load_mapping() if mapping is None else mapping
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    rows = list(reader)
    if not rows:
        raise MappingMismatch("the CSV is empty")
    columns = resolve_columns(rows[0], mapping)
    parsed = []
    seen: set = set()
    for number, row in enumerate(rows[1:], start=1):
        if not any(_norm(c) for c in row):
            continue
        response = parse_row(row, number, columns, mapping)
        if response.pilot_id in seen:
            response.skip_reason = "duplicate of an earlier row in this file"
        seen.add(response.pilot_id)
        parsed.append(response)
    return parsed


def read_csv(path) -> list:
    return parse_csv(Path(path).read_text(encoding="utf-8-sig"))


def iter_importable(parsed: Iterable[ParsedResponse]):
    return (p for p in parsed if p.skip_reason is None)
