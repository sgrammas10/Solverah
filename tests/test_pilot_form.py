"""The pilot form (pre-registration Amendment 2): generator parity, item identity, CSV
parsing, the guard, and where respondent emails may go. No database here --
tests/test_pilot_form_import.py covers the import end to end.

The form must ask what the app asks, in the order and with the options the app uses,
because Amendment 2 counts its rows toward the same thresholds as app rows. So the parity
tests read the item banks directly (the core YAML through present_items, the environment
bank through situation_items) and compare the generated form against them, rather than
comparing the generator against itself.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from causal_graph.v1_model.devfit import guard  # noqa: E402
from causal_graph.v1_model.pilot_form import (  # noqa: E402
    generate_form_script,
    import_responses,
    responses,
    sample_csv,
    spec,
)
from work_pulse import situation_items  # noqa: E402

import present_items  # noqa: E402  -- on sys.path via the pilot_form package

PILOT_OK = "postgresql://solverah:solverah@localhost:5433/solverah_pilot"
PRODUCTION_SHAPED_URL = "postgresql://solverah:hunter2@dpg-abc123-a/solverah_prod"


@pytest.fixture(scope="module")
def form():
    return spec.build_spec()


@pytest.fixture(scope="module")
def mapping():
    return responses.load_mapping()


def _core_yaml() -> dict:
    return yaml.safe_load(Path(present_items.DEFAULT_ITEMS_PATH).read_text(encoding="utf-8"))


def _questions(form, *, role=None, slot=None):
    return [q for q in form.questions()
            if (role is None or q.role == role) and (slot is None or q.slot == slot)]


# ---------------------------------------------------------------------------
# 1. The committed files are what the banks generate today
# ---------------------------------------------------------------------------
def test_committed_script_and_mapping_match_a_fresh_generation():
    """THE drift guard. A bank edit changes the generated text; until someone reruns the
    generator (and so re-pastes the form), this fails."""
    script, mapping_text = generate_form_script.render_all()
    committed_script = generate_form_script.SCRIPT_PATH.read_text(encoding="ascii")
    committed_mapping = generate_form_script.MAPPING_PATH.read_text(encoding="ascii")
    assert committed_script == script, "build_form.gs is stale -- regenerate it"
    assert committed_mapping == mapping_text, "form_mapping.json is stale -- regenerate it"


def test_check_mode_reports_up_to_date(capsys):
    assert generate_form_script.main(["--check"]) == 0
    assert "up to date" in capsys.readouterr().out


def test_generated_files_are_pure_ascii():
    for path in (generate_form_script.SCRIPT_PATH, generate_form_script.MAPPING_PATH):
        path.read_bytes().decode("ascii")


def test_the_mapping_records_the_bank_versions_it_was_built_from(mapping):
    assert mapping["env_form_version"] == situation_items.FORM_VERSION
    assert mapping["core_form_version"] == _core_yaml()["form_version"]
    assert mapping["pilot_form_version"] == spec.PILOT_FORM_VERSION
    import_responses.check_bank_versions(mapping)  # does not raise


def test_import_refuses_a_mapping_from_other_banks(mapping):
    stale = dict(mapping, env_form_version="env-v1-2026-09-10")
    with pytest.raises(SystemExit) as exc:
        import_responses.check_bank_versions(stale)
    assert "different item banks" in str(exc.value)


# ---------------------------------------------------------------------------
# 2. Core: the app's 24 items, exact wording, option order, the app's own order
# ---------------------------------------------------------------------------
def test_core_is_the_24_items_with_exact_wording_and_option_order(form):
    by_id = {item["id"]: item for item in _core_yaml()["items"]}
    core = _questions(form, role="core")
    assert len(core) == 24
    assert {q.item_id for q in core} == set(by_id)
    for q in core:
        item = by_id[q.item_id]
        assert q.title == item["prompt"]
        assert [c.text for c in q.choices] == [o["text"] for o in item["options"]]
        assert [c.answer for c in q.choices] == [o["key"] for o in item["options"]]
        assert q.required is True


def test_core_order_is_what_the_app_serves_respondent_core_order_seed(form):
    payload, token_map = present_items.build_form(
        spec.CORE_ORDER_SEED, present_items.DEFAULT_ITEMS_PATH, secret=b"any-secret"
    )
    app_order = [token_map[i["token"]] for b in payload["blocks"] for i in b["items"]]
    assert [q.item_id for q in _questions(form, role="core")] == app_order
    assert list(form.core_item_order) == app_order


def test_core_order_keeps_rule_seven_no_adjacent_dimension(form):
    dims = {item["id"]: item["dimension"] for item in _core_yaml()["items"]}
    order = [dims[q.item_id] for q in _questions(form, role="core")]
    assert all(a != b for a, b in zip(order, order[1:]))


def test_core_pages_do_not_break_on_the_apps_block_boundaries(form):
    """A page of exactly six would hold one item per dimension and hand back the
    grouping the interleave hides."""
    core_pages = [p for p in form.pages if p.page_id.startswith("core_")]
    sizes = [len(p.questions) for p in core_pages]
    assert sum(sizes) == 24
    boundaries, running = [], 0
    for size in sizes[:-1]:
        running += size
        boundaries.append(running)
    assert not any(b % 6 == 0 for b in boundaries), boundaries


# ---------------------------------------------------------------------------
# 3. Job sections: both tenses, the app's form order, experienced alone and last
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("slot,past", [
    (spec.SLOT_CURRENT_PRESENT, False),
    (spec.SLOT_CURRENT_PAST, True),
    (spec.SLOT_PREVIOUS, True),
])
def test_each_job_section_is_the_environment_form_in_its_tense(form, slot, past):
    questions = [q for q in _questions(form, slot=slot) if q.role != "outcome"]
    expected_ids = (
        ["stage_size", "comp", "industry"]
        + [i["item_id"] for i in situation_items.item_list_in_form_order()]
        + ["experienced"]
    )
    assert [q.item_id for q in questions] == expected_ids

    env = {i["item_id"]: i for i in situation_items.ENVIRONMENT_ITEMS}
    ctx = {i["item_id"]: i for i in situation_items.CONTEXT_ITEMS}
    for q in questions:
        assert q.required is True
        source = env.get(q.item_id) or ctx[q.item_id]
        assert q.title == (source["prompt_past"] if past else source["prompt"])
        assert [c.text for c in q.choices] == [
            o["text_past"] if past else o["text"] for o in source["options"]
        ]
        if q.role == "env":
            # The authored (alternating) order, not a sorted one.
            assert [c.answer for c in q.choices] == [o["key"] for o in source["options"]]
        else:
            assert [c.answer for c in q.choices] == [o["value"] for o in source["options"]]


def test_comp_and_industry_keep_their_not_sure_options_as_null(form):
    for slot in spec.SLOTS:
        by_item = {q.item_id: q for q in _questions(form, slot=slot)}
        assert by_item["comp"].choices[-1].answer is None
        assert by_item["industry"].choices[-1].answer is None
        assert all(c.answer is not None for c in by_item["stage_size"].choices)
        assert all(c.answer is not None for c in by_item["experienced"].choices)


def test_experienced_sits_alone_on_the_last_page_of_every_job_section(form):
    """`experienced` is still the last REQUIRED question, immediately before the
    optional outcomes page -- never after it (situation_items module doc)."""
    for slot in spec.SLOTS:
        page = form.page("%s_overall" % slot)
        assert [q.item_id for q in page.questions] == ["experienced"]
        slot_pages = [p.page_id for p in form.pages if p.page_id.startswith(slot + "_")]
        assert slot_pages[-2] == page.page_id
        assert slot_pages[-1] == "%s_outcomes" % slot


def test_the_five_outcome_items_are_optional_and_follow_experienced(form):
    for slot in spec.SLOTS:
        page = form.page("%s_outcomes" % slot)
        assert [q.item_id for q in page.questions] == [
            i["item_id"] for i in situation_items.OUTCOME_ITEMS
        ]
        for q in page.questions:
            assert q.role == "outcome" and q.required is False
            item = next(i for i in situation_items.OUTCOME_ITEMS if i["item_id"] == q.item_id)
            past = slot != spec.SLOT_CURRENT_PRESENT
            assert q.title == (item["prompt_past"] if past else item["prompt"])
            assert [c.answer for c in q.choices] == [o["value"] for o in item["options"]]
            assert [c.text for c in q.choices] == [
                o["text_past"] if past else o["text"] for o in item["options"]
            ]


def test_alternating_pole_order_reaches_the_form(form):
    """Within each dimension one item is low-pole-first and one high-pole-first."""
    poles = {i["item_id"]: [o["pole"] for o in i["options"]]
             for i in situation_items.ENVIRONMENT_ITEMS}
    keys = {i["item_id"]: [o["key"] for o in i["options"]]
            for i in situation_items.ENVIRONMENT_ITEMS}
    for slot in spec.SLOTS:
        for q in _questions(form, role="env", slot=slot):
            assert [c.answer for c in q.choices] == keys[q.item_id]
        firsts = {}
        for q in _questions(form, role="env", slot=slot):
            dim = q.item_id.split("-")[1]
            firsts.setdefault(dim, set()).add(poles[q.item_id][0])
        assert all(f == {"low", "high"} for f in firsts.values()), firsts


# ---------------------------------------------------------------------------
# 4. Branching and settings
# ---------------------------------------------------------------------------
def test_career_status_branches_to_the_right_tense_or_the_end(form):
    status = form.page("status").questions[0]
    assert {c.answer: c.go_to for c in status.choices} == {
        "employed": "current_present_context",
        "between_jobs": "current_past_context",
        "first_job": "final",
    }


def test_gate_and_section_jumps(form):
    gate = form.page("gate").questions[0]
    assert {c.answer: c.go_to for c in gate.choices} == {"yes": "previous_context",
                                                         "no": "final"}
    ids = [p.page_id for p in form.pages]
    # Linear order the branching relies on. The optional outcomes page, not
    # `_overall`, is now the last page of each job section.
    assert ids.index("current_past_outcomes") + 1 == ids.index("gate")
    assert ids.index("previous_outcomes") + 1 == ids.index("final")
    assert form.page("current_present_outcomes").go_to == "gate"
    assert ids[-1] == "final"


def test_the_script_sets_the_jump_on_the_break_after_the_section(form):
    """Apps Script's setGoToPage acts on the page BEFORE the break, so the employed
    section's jump to the gate lives on the break that starts the between-jobs section."""
    script = generate_form_script.SCRIPT_PATH.read_text(encoding="ascii")
    assert 'pages["current_past_context"].setGoToPage(pages["gate"]);' in script
    assert script.count("setGoToPage(") == 1


def test_script_settings_shuffle_off_and_no_automatic_email_collection():
    script = generate_form_script.SCRIPT_PATH.read_text(encoding="ascii")
    assert "form.setShuffleQuestions(false);" in script
    assert "setShuffleQuestions(true)" not in script
    assert "EmailCollectionType.DO_NOT_COLLECT" in script
    assert "setCollectEmail(true)" not in script
    assert "VERIFIED" not in script and "RESPONDER_INPUT" not in script
    # Nothing calls a Google API at generation time; the script is only text.
    assert "UrlFetchApp" not in script


def test_the_only_optional_questions_are_outcomes_email_and_followup(form):
    optional = [q.qid for q in form.questions() if not q.required]
    outcome_qids = [q.qid for q in form.questions() if q.role == "outcome"]
    assert len(outcome_qids) == 5 * len(spec.SLOTS)
    assert optional == outcome_qids + ["email", "followup"]
    final = form.page("final").questions
    assert [q.qid for q in final] == ["email", "followup"]
    assert final[0].kind == "email"


def test_the_followup_consent_question_is_on_the_final_page_after_the_email(form, mapping):
    q = form.page("final").questions[1]
    assert (q.role, q.kind, q.required) == ("followup", "choice", False)
    assert [c.answer for c in q.choices] == [spec.FOLLOWUP_YES, spec.FOLLOWUP_NO]
    assert all(c.go_to is None for c in q.choices)
    assert mapping["columns"][-1]["qid"] == "followup"
    assert mapping["columns"][-1]["answers"] == [[t, a] for t, a in spec.FOLLOWUP_CHOICES]
    script = generate_form_script.SCRIPT_PATH.read_text(encoding="ascii")
    assert script.index(spec.EMAIL_TITLE) < script.index(spec.FOLLOWUP_TITLE)


def test_consent_copy_names_both_uses_of_the_email():
    """The email is used for the report and, only on a yes, one check-in -- the intro and
    the email help must not still say 'nothing else'."""
    for text in (spec.FORM_DESCRIPTION, spec.EMAIL_HELP):
        assert "nothing else" not in text
        assert "report" in text and "check-in" in text.replace("check in", "check-in")


# ---------------------------------------------------------------------------
# 5. Item identity: the mapping is unambiguous
# ---------------------------------------------------------------------------
def test_mapping_columns_are_unique_and_follow_form_order(form, mapping):
    keys = [(responses._norm(c["title"]), c["occurrence"]) for c in mapping["columns"]]
    assert len(keys) == len(set(keys))
    assert [c["qid"] for c in mapping["columns"]] == [q.qid for q in form.questions()]
    for column in mapping["columns"]:
        texts = [responses._norm(t) for t, _ in column["answers"]]
        assert len(texts) == len(set(texts)), column["qid"]


def test_only_the_two_past_tense_sections_share_titles(mapping):
    repeated = [c for c in mapping["columns"] if c["occurrence"] > 1]
    assert {c["slot"] for c in repeated} == {spec.SLOT_PREVIOUS}
    assert len(repeated) == 16 + 5  # the twelve dims + four context items + five outcomes


def test_validate_spec_refuses_duplicate_option_texts(form):
    import dataclasses

    page = form.pages[0]
    q = page.questions[0]
    bad_q = dataclasses.replace(q, choices=(q.choices[0], dataclasses.replace(
        q.choices[1], text=q.choices[0].text + "  ")))
    bad = dataclasses.replace(form, pages=(dataclasses.replace(
        page, questions=(bad_q,) + page.questions[1:]),) + form.pages[1:])
    with pytest.raises(spec.SpecError):
        spec.validate_spec(bad)


def test_validate_spec_refuses_an_ambiguous_repeated_title(form):
    import dataclasses

    page = form.pages[0]
    q0, q1 = page.questions[0], page.questions[1]
    bad = dataclasses.replace(form, pages=(dataclasses.replace(
        page, questions=(q0, dataclasses.replace(q1, title=q0.title))
        + page.questions[2:]),) + form.pages[1:])
    with pytest.raises(spec.SpecError):
        spec.validate_spec(bad)


# ---------------------------------------------------------------------------
# 6. CSV -> answers (pure)
# ---------------------------------------------------------------------------
def _parse(mapping, rows, **kw):
    return responses.parse_csv(sample_csv.to_csv(mapping, rows, **kw), mapping)


def test_an_employed_respondent_maps_to_a_current_report_payload(mapping):
    [p] = _parse(mapping, [sample_csv.respondent(
        mapping, status="employed", timestamp="10/2/2026 9:00:00",
        env_keys={"env-autonomy-1": "e", "env-pace-1": "a"}, stage_size=4, comp=2,
        industry="finance", experienced=5)])
    assert p.skip_reason is None and p.career_status == "employed"
    assert len(p.core_choices) == 24
    payload = p.current.payload()
    assert payload["subject"] == "current"
    assert payload["answers"]["env-autonomy-1"] == "e"
    assert payload["answers"]["env-pace-1"] == "a"
    assert payload["answers"]["env-decision-2"] == "c"
    assert set(payload["answers"]) == {
        i["item_id"] for i in situation_items.ENVIRONMENT_ITEMS}
    assert (payload["stage_size"], payload["comp"], payload["industry"],
            payload["experienced"]) == (4, 2, "finance", 5)
    assert p.previous is None and p.notes == []
    assert p.pilot_form_version == spec.PILOT_FORM_VERSION
    assert p.env_form_version == situation_items.FORM_VERSION


def test_outcome_answers_are_optional_and_stored_when_given(mapping):
    [answered] = _parse(mapping, [sample_csv.respondent(
        mapping, status="employed", timestamp="t1",
        outcomes={"satisfaction": 4, "retention_intention": 2})])
    payload = answered.current.payload()
    assert payload["satisfaction"] == 4
    assert payload["retention_intention"] == 2
    assert "performance" not in payload and "engagement" not in payload

    [skipped] = _parse(mapping, [sample_csv.respondent(
        mapping, status="employed", timestamp="t2")])
    payload = skipped.current.payload()
    for item_id in situation_items.OUTCOME_COLUMNS:
        assert item_id not in payload
    assert skipped.notes == []


# ---------------------------------------------------------------------------
# 6b. Accepting a form built before the outcome items existed (Amendment 3)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def legacy_mapping():
    [legacy] = responses.load_legacy_mappings()
    return legacy


def test_the_legacy_mapping_still_matches_the_live_banks_on_required_items(mapping, legacy_mapping):
    """The one check that lets `check_bank_versions` skip legacy CSVs: every column that
    isn't an outcome item must be byte-identical between the frozen v1 snapshot and a
    fresh generation, because those are the columns a legacy respondent's answers get
    scored against today. If this ever fails, the live banks changed a REQUIRED item
    and pilot-v1-2026-10-01 must stop being accepted."""
    required = [c for c in mapping["columns"] if c["role"] != "outcome"]
    legacy_required = [c for c in legacy_mapping["columns"] if c["role"] != "outcome"]
    assert required == legacy_required
    assert legacy_mapping["core_form_version"] == mapping["core_form_version"]


def test_a_legacy_csv_is_recognised_and_resolves_to_the_old_mapping(legacy_mapping):
    header = sample_csv.header(legacy_mapping)
    used_mapping, _columns = responses.resolve_mapping(header, None)
    assert used_mapping["pilot_form_version"] == legacy_mapping["pilot_form_version"]


def test_a_legacy_form_response_imports_with_outcomes_null_and_the_old_version_recorded(
    legacy_mapping,
):
    [p] = responses.parse_csv(sample_csv.to_csv(legacy_mapping, [sample_csv.respondent(
        legacy_mapping, status="employed", timestamp="t1")]))
    assert p.skip_reason is None
    assert p.pilot_form_version == legacy_mapping["pilot_form_version"]
    assert p.env_form_version == legacy_mapping["env_form_version"]
    assert p.env_form_version != situation_items.FORM_VERSION
    assert p.current.outcomes == {}
    payload = p.current.payload()
    for item_id in situation_items.OUTCOME_COLUMNS:
        assert item_id not in payload
    assert any("pilot_form_version=%s" % legacy_mapping["pilot_form_version"] in n
               for n in p.notes)


def test_a_current_form_response_imports_with_outcomes_stored_and_the_new_version_recorded(
    mapping,
):
    [p] = responses.parse_csv(sample_csv.to_csv(mapping, [sample_csv.respondent(
        mapping, status="employed", timestamp="t1", outcomes={"satisfaction": 5})]))
    assert p.skip_reason is None
    assert p.pilot_form_version == spec.PILOT_FORM_VERSION
    assert p.env_form_version == situation_items.FORM_VERSION
    assert p.current.outcomes == {"satisfaction": 5}
    assert not any("outcome items were not offered" in n for n in p.notes)


def test_a_csv_matching_no_known_mapping_is_refused(mapping):
    text = sample_csv.to_csv(mapping, [])
    with pytest.raises(responses.MappingMismatch) as exc:
        responses.parse_csv(text.replace(mapping["columns"][0]["title"], "Something else"))
    assert "any known pilot form" in str(exc.value)


def test_not_sure_maps_to_null_not_to_a_guess(mapping):
    [p] = _parse(mapping, [sample_csv.respondent(
        mapping, status="between_jobs", timestamp="t1", comp=None, industry=None)])
    payload = p.current.payload()
    assert payload["comp"] is None and payload["industry"] is None
    assert p.current.slot == spec.SLOT_CURRENT_PAST


def test_core_option_text_maps_to_the_option_key(mapping):
    [p] = _parse(mapping, [sample_csv.respondent(
        mapping, status="first_job", timestamp="t1", core_pattern="B")])
    assert set(p.core_choices.values()) == {"B"}


def test_a_previous_job_section_becomes_a_past_subject_report(mapping):
    [p] = _parse(mapping, [sample_csv.respondent(
        mapping, status="employed", timestamp="t1", previous=True)])
    assert p.previous is not None
    assert p.previous.payload()["subject"] == "past"
    assert p.previous.payload()["experienced"] == 2
    assert p.previous.payload()["comp"] is None


def test_first_job_gets_no_job_report(mapping):
    [p] = _parse(mapping, [sample_csv.respondent(mapping, status="first_job", timestamp="t")])
    assert p.skip_reason is None
    assert p.current is None and p.previous is None
    assert any("first_job" in n for n in p.notes)


def test_skipped_optional_sections_are_simply_absent(mapping):
    [p] = _parse(mapping, [sample_csv.respondent(
        mapping, status="employed", timestamp="t", previous=False)])
    assert p.previous is None and p.email is None and p.notes == []


def test_an_incomplete_core_skips_the_respondent(mapping):
    row = sample_csv.respondent(mapping, status="employed", timestamp="t")
    first_core = next(c["qid"] for c in mapping["columns"] if c["role"] == "core")
    row[first_core] = ""
    [p] = _parse(mapping, [row])
    assert p.skip_reason.startswith("core incomplete (23 of 24")


def test_an_incomplete_job_section_writes_no_report_but_keeps_the_respondent(mapping):
    row = sample_csv.respondent(mapping, status="employed", timestamp="t")
    row["env:%s:env-pace-2" % spec.SLOT_CURRENT_PRESENT] = ""
    [p] = _parse(mapping, [row])
    assert p.skip_reason is None and p.current is None
    assert any("incomplete" in n for n in p.notes)


def test_gate_yes_with_an_incomplete_previous_section_writes_no_past_report(mapping):
    row = sample_csv.respondent(mapping, status="employed", timestamp="t", previous=True)
    row["context:%s:experienced" % spec.SLOT_PREVIOUS] = ""
    [p] = _parse(mapping, [row])
    assert p.current is not None and p.previous is None
    assert any("previous" in n for n in p.notes)


def test_answers_in_the_wrong_tense_section_are_ignored_not_relabelled(mapping):
    row = sample_csv.respondent(mapping, status="employed", timestamp="t")
    row.update(sample_csv.job_answers(mapping, spec.SLOT_CURRENT_PAST))
    [p] = _parse(mapping, [row])
    assert p.current.slot == spec.SLOT_CURRENT_PRESENT
    assert any("ignored" in n for n in p.notes)


def test_text_the_question_does_not_offer_skips_with_a_reason(mapping):
    row = sample_csv.respondent(mapping, status="employed", timestamp="t")
    row["context:%s:comp" % spec.SLOT_CURRENT_PRESENT] = "About the same - at market."
    [p] = _parse(mapping, [row])
    assert p.skip_reason == "unrecognised answer to comp"


def test_whitespace_differences_do_not_break_the_match(mapping):
    row = sample_csv.respondent(mapping, status="employed", timestamp="t")
    qid = "context:%s:stage_size" % spec.SLOT_CURRENT_PRESENT
    row[qid] = "  " + row[qid].replace(" ", "   ") + "\n"
    [p] = _parse(mapping, [row])
    assert p.current is not None


def test_the_pilot_id_is_stable_and_ignores_the_email(mapping):
    base = sample_csv.respondent(mapping, status="employed", timestamp="t1", email="a@x.org")
    other_email = dict(base, email="b@y.org")
    changed = dict(base, __timestamp__="t2")
    a, b, c = (_parse(mapping, [r])[0].pilot_id for r in (base, other_email, changed))
    assert a == b
    assert a != c
    assert re.fullmatch(r"[0-9a-f]{16}", a)
    assert _parse(mapping, [base], bom=False)[0].pilot_id == a


def test_a_repeated_row_is_a_duplicate(mapping):
    row = sample_csv.respondent(mapping, status="employed", timestamp="t1")
    first, second = _parse(mapping, [row, row])
    assert first.skip_reason is None
    assert second.skip_reason == "duplicate of an earlier row in this file"


def test_a_header_that_is_not_this_form_is_refused(mapping):
    text = sample_csv.to_csv(mapping, [])
    with pytest.raises(responses.MappingMismatch, match="missing"):
        responses.parse_csv(text.replace(mapping["columns"][0]["title"], "Something else"),
                            mapping)
    header = sample_csv.header(mapping) + ["An extra question"]
    with pytest.raises(responses.MappingMismatch, match="does not have"):
        responses.resolve_columns(header, mapping)
    with pytest.raises(responses.MappingMismatch, match="Timestamp"):
        responses.resolve_columns(sample_csv.header(mapping)[1:], mapping)


def test_a_title_repeated_more_often_than_the_form_repeats_it_is_refused(mapping):
    header = sample_csv.header(mapping)
    dup = next(c["title"] for c in mapping["columns"] if c["occurrence"] == 2)
    with pytest.raises(responses.MappingMismatch):
        responses.resolve_columns(header + [dup], mapping)


# ---------------------------------------------------------------------------
# 7. The guard (pilot prefix) and the CLI's refusal before any connection
# ---------------------------------------------------------------------------
def _pilot(url, app_env="testing"):
    return guard.assert_local_database(url, prefix=guard.PILOT_DB_PREFIX, app_env=app_env)


def test_a_local_pilot_url_is_accepted():
    assert _pilot(PILOT_OK) == PILOT_OK
    assert _pilot("postgresql://u:p@127.0.0.1:5433/solverah_pilot_b?sslmode=disable")


@pytest.mark.parametrize("url,needle", [
    (PRODUCTION_SHAPED_URL, "not local"),
    ("postgresql://u:p@db.example.com:5432/solverah_pilot", "not local"),
    ("postgresql://solverah:solverah@localhost:5433/solverah_test", "solverah_pilot"),
    ("postgresql://solverah:solverah@localhost:5433/solverah_modeldev", "solverah_pilot"),
    ("postgresql:///solverah_pilot", "not local"),
    ("postgresql://u:p@localhost:5433/solverah_pilot?host=prod.example.com", "query"),
    ("postgresql://u:p@localhost:5433/solverah_pilot?hostaddr=10.0.0.9", "query"),
    ("postgresql://u:p@localhost:5433/solverah_pilot?dbname=solverah_prod", "query"),
])
def test_the_pilot_guard_refuses(url, needle):
    with pytest.raises(guard.UnsafeDatabaseError) as exc:
        _pilot(url)
    assert needle in str(exc.value)


def test_the_pilot_guard_refuses_production_app_env():
    with pytest.raises(guard.UnsafeDatabaseError, match="production"):
        _pilot(PILOT_OK, app_env="production")


def test_the_devfit_guard_still_refuses_the_pilot_database():
    """Each harness accepts only its own family: synthetic cohorts never land beside
    real respondents."""
    with pytest.raises(guard.UnsafeDatabaseError):
        guard.assert_local_dev_database(PILOT_OK, app_env="testing")


def test_the_pilot_guard_agrees_with_what_the_driver_would_dial():
    from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2
    from sqlalchemy.engine import make_url

    _pilot(PILOT_OK)
    _, opts = PGDialect_psycopg2().create_connect_args(make_url(PILOT_OK))
    assert str(opts["host"]).lower() in ("localhost", "127.0.0.1")
    assert str(opts.get("dbname", opts.get("database"))).startswith("solverah_pilot")


@pytest.mark.parametrize("url", [
    PRODUCTION_SHAPED_URL,
    "postgresql://u:p@localhost:5433/solverah_pilot?host=prod.example.com",
])
def test_the_import_cli_refuses_before_it_connects(monkeypatch, tmp_path, url):
    monkeypatch.setenv("APP_ENV", "testing")
    called = []
    monkeypatch.setattr(import_responses, "open_app", lambda u: called.append(u))
    csv_path = tmp_path / "r.csv"
    csv_path.write_text("Timestamp\n", encoding="utf-8")
    with pytest.raises(guard.UnsafeDatabaseError):
        import_responses.main([str(csv_path), "--database-url", url])
    assert called == []


def test_the_import_cli_refuses_production_app_env(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(import_responses, "open_app", lambda u: pytest.fail("connected"))
    csv_path = tmp_path / "r.csv"
    csv_path.write_text("Timestamp\n", encoding="utf-8")
    with pytest.raises(guard.UnsafeDatabaseError, match="production"):
        import_responses.main([str(csv_path), "--database-url", PILOT_OK])


def test_the_import_cli_has_no_force_flag():
    with pytest.raises(SystemExit):
        import_responses.main(["x.csv", "--force"])


def test_a_dry_run_touches_no_database(monkeypatch, tmp_path, mapping, capsys):
    monkeypatch.setattr(import_responses, "open_app", lambda u: pytest.fail("connected"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    csv_path = tmp_path / "r.csv"
    csv_path.write_text(sample_csv.to_csv(mapping, [sample_csv.respondent(
        mapping, status="employed", timestamp="t", email="someone@example.org")]),
        encoding="utf-8")
    assert import_responses.main([str(csv_path), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "someone@example.org" not in out
    out.encode("ascii")


# ---------------------------------------------------------------------------
# 8. Respondent emails: outside the repo only
# ---------------------------------------------------------------------------
def _parsed_with_email(mapping, email, ts="t"):
    return _parse(mapping, [sample_csv.respondent(
        mapping, status="employed", timestamp=ts, email=email)])


def test_emails_are_refused_inside_the_repo(mapping):
    parsed = _parsed_with_email(mapping, "a@example.org")
    with pytest.raises(import_responses.UnsafeOutputPath):
        import_responses.write_emails(REPO_ROOT / "emails.csv", parsed)
    with pytest.raises(import_responses.UnsafeOutputPath):
        import_responses.write_emails(
            REPO_ROOT / "causal_graph" / "v1_model" / "pilot_form" / "e.csv", parsed)
    assert not (REPO_ROOT / "emails.csv").exists()


def test_emails_are_written_by_pilot_id_and_merged(tmp_path, mapping):
    target = tmp_path / "pilot" / "emails.csv"
    first = _parsed_with_email(mapping, "a@example.org", "t1")
    second = _parsed_with_email(mapping, "b@example.org", "t2")
    assert import_responses.write_emails(target, first) == 1
    assert import_responses.write_emails(target, second) == 1
    assert import_responses.write_emails(target, second, only=set()) == 0
    text = target.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "pilot_id,email,followup_ok"
    assert "%s,a@example.org,no" % first[0].pilot_id in text
    assert "%s,b@example.org,no" % second[0].pilot_id in text


def _parsed_followup(mapping, *, email, followup, ts="t"):
    return _parse(mapping, [sample_csv.respondent(
        mapping, status="employed", timestamp=ts, email=email, followup=followup)])[0]


@pytest.mark.parametrize("email,followup,expected", [
    ("a@example.org", spec.FOLLOWUP_YES, True),
    ("a@example.org", spec.FOLLOWUP_NO, False),
    ("a@example.org", None, False),          # blank
    ("", spec.FOLLOWUP_YES, False),          # a yes with no email cannot be acted on
])
def test_followup_consent_parses_yes_no_blank(mapping, email, followup, expected):
    p = _parsed_followup(mapping, email=email, followup=followup)
    assert p.skip_reason is None
    assert p.followup_ok is expected
    if not email:
        assert p.email is None


def test_unrecognised_followup_text_is_no_and_does_not_skip(mapping):
    row = sample_csv.respondent(mapping, status="employed", timestamp="t", email="a@x.org")
    row["followup"] = "Maybe later"
    [p] = _parse(mapping, [row])
    assert p.skip_reason is None and p.followup_ok is False
    assert any("follow-up" in n for n in p.notes)


def test_the_followup_answer_does_not_change_the_pilot_id(mapping):
    """Consent is contact data like the email, not an answer: pilot_id stays a function
    of the answers alone, so changing it never re-identifies a row."""
    ids = {
        _parsed_followup(mapping, email=e, followup=f).pilot_id
        for e, f in (("a@x.org", spec.FOLLOWUP_YES), ("a@x.org", spec.FOLLOWUP_NO),
                     ("", None), ("b@y.org", None))
    }
    assert len(ids) == 1


def test_emails_csv_records_followup_and_merges_idempotently(tmp_path, mapping):
    target = tmp_path / "emails.csv"
    yes = [_parsed_followup(mapping, email="a@example.org", followup=spec.FOLLOWUP_YES,
                            ts="t1")]
    no = [_parsed_followup(mapping, email="b@example.org", followup=spec.FOLLOWUP_NO,
                           ts="t2")]
    import_responses.write_emails(target, yes)
    import_responses.write_emails(target, no)
    once = target.read_text(encoding="utf-8")
    import_responses.write_emails(target, yes)
    import_responses.write_emails(target, no)
    assert target.read_text(encoding="utf-8") == once
    assert "%s,a@example.org,yes" % yes[0].pilot_id in once
    assert "%s,b@example.org,no" % no[0].pilot_id in once
    assert len(once.splitlines()) == 3


def test_an_old_format_emails_csv_still_merges(tmp_path, mapping):
    target = tmp_path / "emails.csv"
    target.write_text("pilot_id,email\r\nold0000000000001,old@example.org\r\n",
                      encoding="utf-8")
    new = [_parsed_followup(mapping, email="new@example.org", followup=spec.FOLLOWUP_YES)]
    assert import_responses.write_emails(target, new) == 1
    lines = target.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "pilot_id,email,followup_ok"
    assert "old0000000000001,old@example.org,no" in lines
    assert "%s,new@example.org,yes" % new[0].pilot_id in lines


def test_pilot_email_is_an_invalid_tld_address_on_the_provenance_domain():
    email = import_responses.pilot_email("ab12")
    assert email == "pilot-ab12@pilotform.solverah.invalid"
    assert email.endswith(import_responses.PILOT_FORM_EMAIL_DOMAIN)
    with pytest.raises(ValueError):
        import_responses.pilot_email("../x")


def test_no_print_in_the_package_can_emit_non_ascii():
    """Every print() is ASCII-only on this console: string literals inside print calls
    are checked here, and dynamic text goes through _ascii / an ascii encode."""
    import ast

    pkg = REPO_ROOT / "causal_graph" / "v1_model" / "pilot_form"
    for path in pkg.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "print":
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        sub.value.encode("ascii")


def test_mapping_json_parses_and_has_one_column_per_question(form):
    doc = json.loads(generate_form_script.MAPPING_PATH.read_text(encoding="ascii"))
    assert len(doc["columns"]) == len(form.questions())
