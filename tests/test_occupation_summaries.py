"""Tests for the W-18 card-summary sidecar.

The summary is O*NET's own first sentence, shown under a card's title the moment
the card appears.  Three things can go wrong with it unnoticed, and each has
tests here:

* **The wrong sentence.**  "U.S. Coast Guard" and "(e.g., hurricanes)" carry
  periods that are not sentence ends; a naive split turns a description into a
  fragment that still reads like a sentence.
* **A bad cut.**  92 of the catalog's first sentences are over the cap.  A cut
  must end on a clause, never an ellipsis, never a dangling "and" or a modifier
  that lost its noun.
* **A silent absence.**  The file is optional; a missing one must degrade to
  ``""`` with one warning, and must be published and fetched under one name.

Nothing here reaches the network, and building the file never does.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.services import occupation_summaries as summ
from backend.services.occupation_retrieval import summaries_sidecar_path

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "corpus"
FIXTURE_MATRIX = FIXTURE_DIR / "onet_corpus_testfix.npy"
FIXTURE_SIDECAR = FIXTURE_DIR / "onet_corpus_testfix.json"
FIXTURE_ZONES = FIXTURE_DIR / "onet_corpus_testfix.zones.json"


@pytest.fixture(autouse=True)
def _clean_process_state():
    summ.reset_summaries_cache()
    yield
    summ.reset_summaries_cache()


@pytest.fixture
def scratch_corpus(tmp_path: Path) -> Path:
    target = tmp_path / FIXTURE_MATRIX.name
    target.write_bytes(FIXTURE_MATRIX.read_bytes())
    for source in (FIXTURE_SIDECAR, FIXTURE_ZONES):
        (tmp_path / source.name).write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8"
        )
    return target


# ---------------------------------------------------------------------------
# The first sentence
# ---------------------------------------------------------------------------


class TestFirstSentence:
    def test_splits_at_the_first_sentence_end(self) -> None:
        text = (
            "Determine and formulate policies of companies. Plan, direct, or "
            "coordinate operational activities."
        )
        assert summ.first_sentence(text) == "Determine and formulate policies of companies."

    def test_an_abbreviation_before_a_capital_is_not_a_sentence_end(self) -> None:
        """53-5021.00's real text. A naive split stops at "U.S."."""
        text = (
            "Command or supervise operations of ships. Required to hold license "
            "issued by U.S. Coast Guard."
        )
        assert summ.first_sentence(text) == "Command or supervise operations of ships."
        assert summ.first_sentence("Serve the U.S. Coast Guard well. Then rest.") == (
            "Serve the U.S. Coast Guard well."
        )

    def test_a_period_inside_parentheses_is_not_a_sentence_end(self) -> None:
        text = "Diagnose conditions (e.g. Balloon angioplasty. Stents.) of the heart. More."
        assert summ.first_sentence(text) == (
            "Diagnose conditions (e.g. Balloon angioplasty. Stents.) of the heart."
        )

    def test_e_g_and_decimals_do_not_end_a_sentence(self) -> None:
        text = "Drive trucks, e.g. Vans, under 2.5 tons. Load them."
        assert summ.first_sentence(text) == "Drive trucks, e.g. Vans, under 2.5 tons."

    def test_text_with_no_sentence_end_is_returned_whole(self) -> None:
        assert summ.first_sentence("  Teach   students  ") == "Teach students"

    def test_empty_is_empty(self) -> None:
        assert summ.first_sentence("") == ""


# ---------------------------------------------------------------------------
# The cap
# ---------------------------------------------------------------------------

#: Real long first sentences from the 2026-09-16 catalog, one per cut strategy.
_SEMICOLON = (
    "Construct, erect, install, or repair structures and fixtures made of wood "
    "and comparable materials, such as concrete forms; building frameworks, "
    "including partitions, joists, studding, and rafters; and wood stairways, "
    "window and door frames, and hardwood floors."
)
_PARENTHESES = (
    "Provide personalized assistance to individuals with disabilities or "
    "illness who require help with personal care and activities of daily "
    "living support (e.g., feeding, bathing, dressing, grooming, toileting, and "
    "ambulation)."
)
_EXAMPLES = (
    "Perform engineering duties in planning, designing, and overseeing "
    "construction and maintenance of building structures and facilities, such "
    "as roads, railroads, airports, bridges, harbors, channels, dams, irrigation "
    "projects, pipelines, power plants, and water and sewage systems."
)
_MODIFIERS = (
    "Apply knowledge of engineering, biology, chemistry, computer science, and "
    "biomechanical principles to the design, development, and evaluation of "
    "biological, agricultural, and medical systems and products used in "
    "healthcare and industry settings everywhere."
)


class TestSummarise:
    def test_a_short_sentence_is_returned_as_written(self) -> None:
        assert summ.summarise("Teach children to read. And to write.") == (
            "Teach children to read."
        )

    @pytest.mark.parametrize("text", [_SEMICOLON, _PARENTHESES, _EXAMPLES, _MODIFIERS])
    def test_every_cut_fits_the_cap_and_closes_as_a_sentence(self, text: str) -> None:
        out = summ.summarise(text)

        assert len(out) <= summ.SUMMARY_MAX_CHARS
        assert out.endswith(".")
        assert "..." not in out and "…" not in out
        last = out.rstrip(".").rsplit(" ", 1)[-1].casefold()
        assert last not in {"and", "or", "of", "the", "such", "as", "to", "including"}

    def test_a_semicolon_clause_is_the_first_choice(self) -> None:
        assert summ.summarise(_SEMICOLON) == (
            "Construct, erect, install, or repair structures and fixtures made of "
            "wood and comparable materials, such as concrete forms; building "
            "frameworks, including partitions, joists, studding, and rafters."
        )

    def test_dropping_the_parenthetical_is_preferred_to_cutting_the_duty(self) -> None:
        assert summ.summarise(_PARENTHESES) == (
            "Provide personalized assistance to individuals with disabilities or "
            "illness who require help with personal care and activities of daily "
            "living support."
        )

    def test_the_examples_list_is_dropped_before_the_duty_is_cut(self) -> None:
        assert summ.summarise(_EXAMPLES) == (
            "Perform engineering duties in planning, designing, and overseeing "
            "construction and maintenance of building structures and facilities."
        )

    def test_a_comma_cut_never_strands_a_modifier_without_its_noun(self) -> None:
        """"...evaluation of biological, agricultural." has kept the adjectives
        and lost "systems"; the cut backs off to an earlier comma."""
        out = summ.summarise(_MODIFIERS)

        assert not out.endswith(("biological.", "agricultural.", "medical."))
        assert out.startswith("Apply knowledge of engineering, biology")

    def test_a_sentence_with_no_punctuation_is_cut_on_a_word(self) -> None:
        text = "Operate " + " ".join(["heavy machinery"] * 40) + "."
        out = summ.summarise(text)

        assert len(out) <= summ.SUMMARY_MAX_CHARS
        kept = out[:-1]
        assert text.startswith(kept) and text[len(kept)] == " ", "cut mid-word"

    def test_a_custom_cap_is_honoured(self) -> None:
        assert len(summ.summarise(_EXAMPLES, max_chars=80)) <= 80


# ---------------------------------------------------------------------------
# The table and the sidecar
# ---------------------------------------------------------------------------


def _doc(code: str, title: str, description: str) -> dict:
    return {"code": code, "title": title, "description": description, "tasks": []}


class TestBuildTable:
    def test_one_summary_per_retrievable_row(self) -> None:
        table = summ.build_table(
            [
                _doc("29-1141.00", "Registered Nurses", "Assess patients. Chart."),
                _doc("15-1299.00", "Computer Occupations, All Other", "Anything."),
                _doc("11-1021.00", "General and Operations Managers", ""),
            ]
        )

        assert dict(table.summaries) == {"29-1141.00": "Assess patients."}


class TestSidecar:
    def test_round_trips_beside_the_artifact(self, scratch_corpus: Path) -> None:
        table = summ.SummariesTable(summaries={"29-1141.00": "Assess patients."})

        path = summ.write_summaries_sidecar(scratch_corpus, table)

        assert path.name == "onet_corpus_testfix.summaries.json"
        loaded = summ._load_sidecar(path)
        assert loaded is not None and loaded.for_code("29-1141.00") == "Assess patients."
        assert loaded.for_code("00-0000.00") == ""

    def test_the_file_is_ascii(self, scratch_corpus: Path) -> None:
        path = summ.write_summaries_sidecar(
            scratch_corpus, summ.SummariesTable(summaries={"x": "Café work."})
        )
        path.read_bytes().decode("ascii")

    @pytest.mark.parametrize(
        "payload",
        [
            b"not json",
            json.dumps({"schema_version": 99, "summaries": {"x": "y"}}).encode(),
            json.dumps({"schema_version": 1, "summaries": {}}).encode(),
        ],
    )
    def test_an_unusable_file_degrades_to_none(self, tmp_path: Path, payload) -> None:
        path = tmp_path / "x.summaries.json"
        path.write_bytes(payload)

        assert summ._load_sidecar(path) is None

    def test_the_two_summaries_sidecar_path_helpers_agree(self, tmp_path: Path) -> None:
        """The duplicated helper in `occupation_retrieval` exists so the S3
        fetch can name the file without importing back into a cycle. A drift
        leaves the object downloaded under one name and looked for under
        another."""
        matrix = tmp_path / "onet_corpus_x.npy"

        assert summaries_sidecar_path(matrix) == summ.summaries_sidecar_path(matrix)
        assert summ.summaries_sidecar_path(matrix).name == "onet_corpus_x.summaries.json"

    def test_the_sidecar_is_in_the_publish_set_and_names_its_command(self) -> None:
        from backend.services import occupation_corpus

        assert ".summaries.json" in occupation_corpus.OPTIONAL_PUBLISHED_SUFFIXES
        assert occupation_corpus._SUFFIX_COMMANDS[".summaries.json"] == (
            "flask corpus summaries"
        )


class TestGetSummaries:
    def test_a_corpus_with_no_sidecar_degrades_with_one_warning(
        self, scratch_corpus: Path, caplog
    ) -> None:
        from backend.services.occupation_retrieval import load_corpus

        corpus = load_corpus(scratch_corpus)
        with caplog.at_level("WARNING"):
            assert summ.get_summaries(corpus) is None
            assert summ.summary_for(corpus, "29-1141.00") == ""

        warnings = [r for r in caplog.records if "no summaries sidecar" in r.getMessage()]
        assert len(warnings) == 1, "the missing file was logged on every call"

    def test_the_table_is_memoised_per_corpus_version(self, scratch_corpus: Path) -> None:
        from backend.services.occupation_retrieval import load_corpus

        summ.write_summaries_sidecar(
            scratch_corpus, summ.SummariesTable(summaries={"29-1141.00": "Assess."})
        )
        corpus = load_corpus(scratch_corpus)

        first = summ.get_summaries(corpus)
        summaries_sidecar_path(scratch_corpus).unlink()

        assert summ.get_summaries(corpus) is first
        assert summ.summary_for(corpus, "29-1141.00") == "Assess."


# ---------------------------------------------------------------------------
# `flask corpus summaries`
# ---------------------------------------------------------------------------


@pytest.fixture()
def ctx(client):
    from app import app

    with app.app_context():
        yield app


def _text(result) -> str:
    parts = [result.output or ""]
    try:
        parts.append(result.stderr or "")
    except (ValueError, AttributeError):
        pass
    if result.exception is not None:
        parts.append(str(result.exception))
    return "\n".join(parts)


@pytest.fixture()
def scratch_documents(scratch_corpus: Path) -> Path:
    path = scratch_corpus.with_name(scratch_corpus.stem + ".documents.jsonl")
    path.write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                _doc("29-1141.00", "Registered Nurses", "Assess patients. Chart."),
                _doc("15-1299.00", "Computer Occupations, All Other", "Anything."),
                _doc("11-1021.00", "General and Operations Managers", _EXAMPLES),
            )
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*_a, **_k):
        raise AssertionError("corpus summaries made a network call")

    monkeypatch.setattr("solverah.infra.llm.get_openai_client", explode)
    monkeypatch.setattr("backend.services.onet_client.OnetClient", explode)
    monkeypatch.setattr("solverah.infra.storage.get_s3_client", explode)


class TestCorpusSummariesCommand:
    def test_registered_on_the_app_cli(self, ctx) -> None:
        group = ctx.cli.get_command(None, "corpus")

        assert "summaries" in group.list_commands(None)

    def test_refuses_without_an_artifact(self, ctx, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SOLVERAH_CORPUS_PATH", raising=False)
        monkeypatch.delenv("SOLVERAH_CORPUS_DIR", raising=False)

        result = ctx.test_cli_runner().invoke(args=["corpus", "summaries"])

        assert result.exit_code != 0
        assert "SOLVERAH_CORPUS_PATH" in _text(result)

    def test_a_missing_documents_file_is_a_clean_refusal(
        self, ctx, scratch_corpus: Path, no_network
    ) -> None:
        result = ctx.test_cli_runner().invoke(
            args=["corpus", "summaries", "--corpus", str(scratch_corpus)]
        )

        assert result.exit_code != 0
        assert "documents" in _text(result)
        assert "Traceback" not in _text(result)

    def test_writes_the_sidecar_with_no_network_and_echoes_ascii_json(
        self, ctx, scratch_corpus: Path, scratch_documents: Path, no_network
    ) -> None:
        result = ctx.test_cli_runner().invoke(
            args=["corpus", "summaries", "--corpus", str(scratch_corpus), "--show", "5"]
        )

        assert result.exit_code == 0, _text(result)
        result.output.encode("ascii")
        summary = json.loads(result.output.strip().splitlines()[-1])
        assert summary["event"] == "corpus_summaries"
        assert summary["occupations"] == 2
        written = json.loads(
            summaries_sidecar_path(scratch_corpus).read_text(encoding="utf-8")
        )
        assert written["summaries"] == {
            "11-1021.00": summ.summarise(_EXAMPLES),
            "29-1141.00": "Assess patients.",
        }
