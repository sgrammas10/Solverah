"""Cross-language parity guard for the client-rendered question data
(BUILD_PLAN A-7b, item 3).

`envQuestions.ts` and `mpQuestions.ts` are hand-authored twins of the Python
scoring authorities `work_pulse/situation_items.py` and
`manager_match/manager_profile.py` -- both TS files say as much in their own
header comments. `envQuestions.ts` goes further and claims to have been
"generated from it rather than transcribed by hand", but no generator script
exists anywhere in this repo (checked 2026-09-11: nothing under `scripts/`,
`tools/`, or elsewhere references either TS path from Python). Regenerate-
and-diff is therefore unavailable, so this follows `test_frontend_contract.py`'s
own precedent instead: scan the TS source with regex rather than run Node,
since npm/node availability is not guaranteed in every environment this suite
runs in (that file's docstring makes the identical call for the identical
reason).

The scan is a flat, order-preserving field extraction, not a full JS-object
parse: each named field (`itemId:`, `prompt:`, `key:`, ...) is read out of a
bounded section of the file in document order via a `field: "value"` regex, then
regrouped into items using the arity the Python side already declares
(`OPTION_KEYS`, one context item = one item). This works only because neither
TS file contains an escaped double quote inside a string value -- confirmed
by direct read on 2026-09-11 and reasserted below so a future edit that
introduces one fails loudly here instead of silently truncating a match.

Per `test_frontend_contract.py`'s own lesson: a regex that has quietly
stopped matching and a TS file with nothing left to say about the drift look
identical (`[] == []`) unless the count itself is pinned to something the
Python side declares. Every list compared below is length-checked against an
`EXPECTED_*` constant before its contents are compared, for that reason.
"""
from __future__ import annotations

import re
from pathlib import Path

from manager_match.manager_profile import EXPECTED_ANSWER_COUNT, MANAGER_PROFILE_QUESTIONS
from work_pulse.situation_items import (
    COMP_ITEM,
    EXPECTED_DIMENSION_ITEM_COUNT,
    EXPERIENCED_ITEM,
    INDUSTRY_ITEM,
    OPTION_KEYS,
    STAGE_SIZE_ITEM,
    item_list_in_form_order,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "src" / "features" / "assessments" / "data"
ENV_TS = DATA_DIR / "envQuestions.ts"
MP_TS = DATA_DIR / "mpQuestions.ts"


def _read(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert '\\"' not in text, (
        f"{path} contains an escaped double quote; the flat field scan below "
        "assumes none exist (verified at authoring time) and would silently "
        "misparse this file if one were introduced."
    )
    return text


def _section(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def _field(pattern: str, block: str) -> list[str]:
    return re.findall(pattern, block)


def _chunk(seq: list, size: int) -> list[list]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


# ---------------------------------------------------------------------------
# envQuestions.ts vs work_pulse/situation_items.py
# ---------------------------------------------------------------------------


def test_env_dimension_items_match_situation_items_py():
    text = _read(ENV_TS)
    dim_block = _section(
        text, "export const ENV_ITEMS: EnvItem[] = [", "export const STAGE_SIZE_ITEM"
    )

    item_ids = _field(r'\bitemId:\s*"([^"]*)"', dim_block)
    dimensions = _field(r'\bdimension:\s*"([^"]*)"', dim_block)
    prompts = _field(r'\bprompt:\s*"([^"]*)"', dim_block)
    prompts_past = _field(r'\bpromptPast:\s*"([^"]*)"', dim_block)
    keys = _field(r'\bkey:\s*"([^"]*)"', dim_block)
    texts = _field(r'\btext:\s*"([^"]*)"', dim_block)
    texts_past = _field(r'\btextPast:\s*"([^"]*)"', dim_block)

    assert len(item_ids) == EXPECTED_DIMENSION_ITEM_COUNT, (
        f"expected {EXPECTED_DIMENSION_ITEM_COUNT} dimension items in envQuestions.ts, "
        f"found {len(item_ids)} -- the field scan may have stopped matching"
    )
    for name, values in [
        ("dimension", dimensions),
        ("prompt", prompts),
        ("promptPast", prompts_past),
    ]:
        assert len(values) == EXPECTED_DIMENSION_ITEM_COUNT, f"{name}: found {len(values)}"

    py_items = item_list_in_form_order()
    assert item_ids == [i["item_id"] for i in py_items]
    assert dimensions == [i["dimension"] for i in py_items]
    assert prompts == [i["prompt"] for i in py_items]
    assert prompts_past == [i["prompt_past"] for i in py_items]

    expected_option_count = EXPECTED_DIMENSION_ITEM_COUNT * len(OPTION_KEYS)
    for name, values in [("key", keys), ("text", texts), ("textPast", texts_past)]:
        assert len(values) == expected_option_count, f"{name}: found {len(values)}"

    for py_item, ts_keys, ts_texts, ts_texts_past in zip(
        py_items, _chunk(keys, len(OPTION_KEYS)), _chunk(texts, len(OPTION_KEYS)), _chunk(texts_past, len(OPTION_KEYS))
    ):
        assert ts_keys == [o["key"] for o in py_item["options"]], py_item["item_id"]
        assert ts_texts == [o["text"] for o in py_item["options"]], py_item["item_id"]
        assert ts_texts_past == [o["text_past"] for o in py_item["options"]], py_item["item_id"]


def test_env_context_items_match_situation_items_py():
    text = _read(ENV_TS)

    for py_item, start_marker, end_marker in [
        (STAGE_SIZE_ITEM, "export const STAGE_SIZE_ITEM", "export const COMP_ITEM"),
        (COMP_ITEM, "export const COMP_ITEM", "export const INDUSTRY_ITEM"),
        (INDUSTRY_ITEM, "export const INDUSTRY_ITEM", "export const EXPERIENCED_ITEM"),
        (EXPERIENCED_ITEM, "export const EXPERIENCED_ITEM", "export type EnvStep"),
    ]:
        block = _section(text, start_marker, end_marker)

        item_ids = _field(r'\bitemId:\s*"([^"]*)"', block)
        prompts = _field(r'\bprompt:\s*"([^"]*)"', block)
        prompts_past = _field(r'\bpromptPast:\s*"([^"]*)"', block)
        # An int, null, or (industry only) a quoted level key.
        raw_values = _field(r'\bvalue:\s*(-?\d+|null|"[^"]*")', block)
        texts = _field(r'\btext:\s*"([^"]*)"', block)
        texts_past = _field(r'\btextPast:\s*"([^"]*)"', block)

        expected_option_count = len(py_item["options"])
        assert item_ids == [py_item["item_id"]]
        assert prompts == [py_item["prompt"]]
        assert prompts_past == [py_item["prompt_past"]]
        assert len(raw_values) == expected_option_count, py_item["item_id"]
        assert len(texts) == expected_option_count, py_item["item_id"]
        assert len(texts_past) == expected_option_count, py_item["item_id"]

        values = [
            None if v == "null" else v.strip('"') if v.startswith('"') else int(v)
            for v in raw_values
        ]
        assert values == [o["value"] for o in py_item["options"]], py_item["item_id"]
        assert texts == [o["text"] for o in py_item["options"]], py_item["item_id"]
        assert texts_past == [o["text_past"] for o in py_item["options"]], py_item["item_id"]


def test_env_form_steps_order_and_version_match_situation_items_py():
    """The form order is load-bearing (context facts first, `experienced`
    last), and the TS stamps the same FORM_VERSION the server writes."""
    from work_pulse.situation_items import CONTEXT_ITEMS, FORM_VERSION

    text = _read(ENV_TS)
    steps = _section(text, "export const ENV_FORM_STEPS: EnvStep[] = [", "\n];")
    names = re.findall(r'\{ kind: "context", item: (\w+) \}|(\.\.\.ENV_ITEMS)', steps)
    order = [a or b for a, b in names]
    ts_ids = {
        "STAGE_SIZE_ITEM": "stage_size", "COMP_ITEM": "comp",
        "INDUSTRY_ITEM": "industry", "EXPERIENCED_ITEM": "experienced",
        "...ENV_ITEMS": "<twelve>",
    }
    py_ids = [i["item_id"] for i in CONTEXT_ITEMS]
    assert [ts_ids[n] for n in order] == py_ids[:-1] + ["<twelve>", py_ids[-1]]

    assert re.search(r'ENV_FORM_VERSION = "([^"]*)"', text).group(1) == FORM_VERSION


# ---------------------------------------------------------------------------
# mpQuestions.ts vs manager_match/manager_profile.py
# ---------------------------------------------------------------------------


def test_mp_questions_match_manager_profile_py():
    text = _read(MP_TS)
    block = _section(text, "export const MP_QUESTIONS: MPQuestion[] = [", "\n];")

    ids = _field(r'\bid:\s*"([^"]*)"', block)
    option_a = _field(r'\boptionA:\s*"([^"]*)"', block)
    option_b = _field(r'\boptionB:\s*"([^"]*)"', block)
    dimensions = _field(r'\bdimension:\s*"([^"]*)"', block)

    for name, values in [
        ("id", ids),
        ("optionA", option_a),
        ("optionB", option_b),
        ("dimension", dimensions),
    ]:
        assert len(values) == EXPECTED_ANSWER_COUNT, (
            f"{name}: expected {EXPECTED_ANSWER_COUNT} in mpQuestions.ts, found {len(values)} "
            "-- the field scan may have stopped matching"
        )

    assert ids == [q["question_id"] for q in MANAGER_PROFILE_QUESTIONS]
    assert option_a == [q["option_a_text"] for q in MANAGER_PROFILE_QUESTIONS]
    assert option_b == [q["option_b_text"] for q in MANAGER_PROFILE_QUESTIONS]
    assert dimensions == [q["dimension"] for q in MANAGER_PROFILE_QUESTIONS]
