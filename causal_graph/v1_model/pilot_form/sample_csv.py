"""Sample response CSVs, built FROM form_mapping.json -- for the tests and for a dry run.

A hand-typed sample CSV would be a second copy of the item wording that drifts the first
time a prompt changes. Building it from the mapping means a sample is always the export
the current form would produce: a "Timestamp" column, then one column per question, in form
order, with option TEXT in the cells -- exactly what Google writes.
"""

from __future__ import annotations

import csv
import io

from . import responses, spec


def mapping() -> dict:
    return responses.load_mapping()


def header(m: dict) -> list:
    return [m["timestamp_column"]] + [c["title"] for c in m["columns"]]


def text_for(column: dict, answer) -> str:
    for option_text, value in column["answers"]:
        if value == answer:
            return option_text
    raise KeyError("%s has no answer %r" % (column["qid"], answer))


def core_answers(m: dict, pattern: str = "AB") -> dict:
    """{qid: option text} for every core item, cycling the option KEY through `pattern`."""
    out = {}
    cores = [c for c in m["columns"] if c["role"] == "core"]
    for i, column in enumerate(cores):
        out[column["qid"]] = text_for(column, pattern[i % len(pattern)])
    return out


def job_answers(m: dict, slot: str, *, env_key: str = "c", stage_size=2, comp=3,
                industry="tech", experienced=4, env_keys: dict | None = None,
                outcomes: dict | None = None) -> dict:
    """{qid: option text} for one complete job section. `outcomes` is
    {outcome item_id: 1..5}; an item left out of it is left unanswered (a blank cell),
    same as a respondent who skipped it -- the realistic default, since the items are
    optional. A mapping with no outcome columns at all (a legacy-form export) simply
    has none to fill."""
    out = {}
    values = {"stage_size": stage_size, "comp": comp, "industry": industry,
              "experienced": experienced}
    outcomes = outcomes or {}
    for column in m["columns"]:
        if column["slot"] != slot:
            continue
        if column["role"] == "context":
            out[column["qid"]] = text_for(column, values[column["item_id"]])
        elif column["role"] == "outcome":
            if column["item_id"] in outcomes:
                out[column["qid"]] = text_for(column, outcomes[column["item_id"]])
        else:
            key = (env_keys or {}).get(column["item_id"], env_key)
            out[column["qid"]] = text_for(column, key)
    return out


def respondent(m: dict, *, status: str, timestamp: str, previous: bool = False,
               email: str = "", core_pattern: str = "AB", followup: str | None = None,
               **job) -> dict:
    """{qid: cell} for a whole respondent, as the form's branching would leave it."""
    labels = {v: k for k, v in spec.CAREER_STATUS_CHOICES}
    row = {"__timestamp__": timestamp, "career_status": labels[status]}
    row.update(core_answers(m, core_pattern))
    slot = {"employed": spec.SLOT_CURRENT_PRESENT,
            "between_jobs": spec.SLOT_CURRENT_PAST}.get(status)
    if slot:
        row.update(job_answers(m, slot, **job))
        gate = dict((v, k) for k, v in spec.GATE_CHOICES)
        row["gate_previous"] = gate[spec.GATE_YES if previous else spec.GATE_NO]
        if previous:
            row.update(job_answers(m, spec.SLOT_PREVIOUS, env_key="a", experienced=2,
                                   comp=None, industry=None))
    if email:
        row["email"] = email
    if followup is not None:  # spec.FOLLOWUP_YES / FOLLOWUP_NO; None leaves it blank
        row["followup"] = dict((v, k) for k, v in spec.FOLLOWUP_CHOICES)[followup]
    return row


def to_csv(m: dict, rows: list, *, bom: bool = True) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header(m))
    for row in rows:
        writer.writerow([row.get("__timestamp__", "")]
                        + [row.get(c["qid"], "") for c in m["columns"]])
    return ("﻿" if bom else "") + buf.getvalue()
