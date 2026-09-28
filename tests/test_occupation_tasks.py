"""Tests for the W-3b panel-tasks sidecar.

Two things this file is careful about, and they are the two ways this data can
go wrong in a way nobody notices:

* **The label must never reach an embedder.**  ``task`` is O*NET's statement,
  byte-exact, and it is the only string the scorer sees; ``label`` is display
  prose.  F-7 measured the cost of confusing them (an LLM's "prevent a fire",
  read literally, returned five firefighting occupations).  Several tests here
  assert the separation from both ends.
* **Eight rows must be eight questions.**  Selection is for spread, so the
  tests that matter are the ones where the greedy pick has to reject a
  paraphrase in favour of something further away.

Nothing here reaches the network: OpenAI is a double for both the embeddings
and the chat completions, which are the only external services this module
touches.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from backend.services import occupation_tasks as tasks_mod
from backend.services.occupation_retrieval import tasks_sidecar_path

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "corpus"
FIXTURE_MATRIX = FIXTURE_DIR / "onet_corpus_testfix.npy"
FIXTURE_SIDECAR = FIXTURE_DIR / "onet_corpus_testfix.json"
FIXTURE_ZONES = FIXTURE_DIR / "onet_corpus_testfix.zones.json"

EMBED_DIM = 1536


@pytest.fixture(autouse=True)
def _clean_process_state():
    tasks_mod.reset_tasks_cache()
    yield
    tasks_mod.reset_tasks_cache()


@pytest.fixture
def scratch_corpus(tmp_path: Path) -> Path:
    target = tmp_path / FIXTURE_MATRIX.name
    target.write_bytes(FIXTURE_MATRIX.read_bytes())
    for source in (FIXTURE_SIDECAR, FIXTURE_ZONES):
        (tmp_path / source.name).write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8"
        )
    return target


def document(code: str, title: str, tasks: list[str]) -> dict:
    return {"code": code, "title": title, "tasks": tasks, "description": title}


def wide(*values: float) -> list[float]:
    """A full-width embedding whose first components are *values*.

    ``occupation_corpus.embed_documents`` validates the width, so a narrow
    vector would fail the build rather than the assertion the test is making.
    """
    vector = [0.0] * EMBED_DIM
    for index, value in enumerate(values):
        vector[index] = value
    return vector


class FakeEmbeddings:
    """``client.embeddings.create``, keyed by exact text."""

    def __init__(self, table: dict[str, list[float]]) -> None:
        self.table = table
        self.calls = 0
        self.seen: list[str] = []

    def create(self, model: str, input: list[str]):  # noqa: A002 -- the SDK's name
        self.calls += 1
        self.seen.extend(input)

        class _Item:
            def __init__(self, index: int, embedding: list[float]) -> None:
                self.index = index
                self.embedding = embedding

        class _Resp:
            pass

        resp = _Resp()
        resp.data = [
            _Item(i, self.table.get(text, wide(1.0))) for i, text in enumerate(input)
        ]
        return resp


class FakeChat:
    """``client.chat.completions.create``, answering from a scripted queue."""

    def __init__(self, replies: list) -> None:
        self.replies = list(replies)
        self.calls: list[dict] = []

    class _Completions:
        def __init__(self, outer: "FakeChat") -> None:
            self.outer = outer

        def create(self, model: str, messages: list, **kwargs):
            self.outer.calls.append(
                {"model": model, "messages": messages, "kwargs": kwargs}
            )
            reply = (
                self.outer.replies.pop(0)
                if self.outer.replies
                else {"labels": []}
            )
            if isinstance(reply, Exception):
                raise reply

            class _Msg:
                content = reply if isinstance(reply, str) else json.dumps(reply)

            class _Choice:
                message = _Msg()

            class _Usage:
                prompt_tokens = 100
                completion_tokens = 40

            class _Resp:
                choices = [_Choice()]
                usage = _Usage()

            return _Resp()

    @property
    def completions(self):
        return self._Completions(self)


class FakeOpenAI:
    def __init__(self, embeddings: dict | None = None, replies: list | None = None):
        self.embeddings = FakeEmbeddings(embeddings or {})
        self.chat = FakeChat(replies or [])


# ---------------------------------------------------------------------------
# Selection: eight rows must be eight questions
# ---------------------------------------------------------------------------


class TestSelection:
    def test_everything_is_kept_when_there_are_fewer_than_the_limit(self) -> None:
        vectors = np.eye(5, dtype=np.float32)

        assert tasks_mod.select_task_indexes(vectors, limit=8) == [0, 1, 2, 3, 4]

    def test_exactly_the_limit_is_also_kept_whole(self) -> None:
        vectors = np.eye(8, dtype=np.float32)

        assert tasks_mod.select_task_indexes(vectors, limit=8) == list(range(8))

    def test_onets_first_statement_is_always_taken(self) -> None:
        """The seed.  Index 0 is the closest thing the data has to "the
        representative one", and a panel that opens on an oddity reads as a
        panel about somebody else's job."""
        # Index 0 is deliberately the one a diversity rule would drop: it sits
        # in the middle of a tight cluster.
        rows = [[1.0, 0.0], [0.99, 0.14], [0.98, 0.20], [0.0, 1.0], [-1.0, 0.0]]
        vectors = np.asarray(rows, dtype=np.float32)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)

        assert 0 in tasks_mod.select_task_indexes(vectors, limit=3)

    def test_a_paraphrase_loses_to_something_further_away(self) -> None:
        """THE reason this is not "O*NET's first eight".

        Three near-identical statements and two distant ones: a limit of three
        must spend two of its rows on the distant pair, not on the cluster.
        """
        rows = [[1.0, 0.0, 0.0], [0.99, 0.1, 0.0], [0.98, 0.15, 0.0],
                [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        vectors = np.asarray(rows, dtype=np.float32)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)

        assert tasks_mod.select_task_indexes(vectors, limit=3) == [0, 3, 4]

    def test_the_same_input_selects_the_same_rows_twice(self) -> None:
        """Determinism.  A sidecar that differs between two builds of the same
        input is a sidecar nobody can diff."""
        rng = np.random.default_rng(11)
        vectors = rng.normal(size=(30, 12)).astype(np.float32)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)

        first = tasks_mod.select_task_indexes(vectors, limit=8)
        second = tasks_mod.select_task_indexes(vectors, limit=8)

        assert first == second
        assert len(first) == 8

    def test_ties_go_to_the_lower_index(self) -> None:
        """Two statements equidistant from everything chosen so far must not
        resolve on dict order."""
        rows = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]]
        vectors = np.asarray(rows, dtype=np.float32)

        assert tasks_mod.select_task_indexes(vectors, limit=2) == [0, 1]

    def test_the_result_is_in_onet_order_not_pick_order(self) -> None:
        rows = [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [0.9, 0.1, 0.0]]
        vectors = np.asarray(rows, dtype=np.float32)
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)

        picked = tasks_mod.select_task_indexes(vectors, limit=3)

        assert picked == sorted(picked)


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


class TestBuildTable:
    def test_a_short_list_is_kept_whole_and_costs_no_embedding(self) -> None:
        client = FakeOpenAI()
        rows = [document("29-1141.00", "Registered Nurses", ["Take vitals.", "Chart."])]

        table = tasks_mod.build_table(rows, client, with_labels=False)

        assert [row.task for row in table.for_code("29-1141.00")] == [
            "Take vitals.",
            "Chart.",
        ]
        assert client.embeddings.calls == 0

    def test_a_long_list_is_cut_to_the_limit(self) -> None:
        statements = ["Task number %d." % n for n in range(20)]
        client = FakeOpenAI({text: wide(*([0.0] * n + [1.0]))
                             for n, text in enumerate(statements)})

        table = tasks_mod.build_table(
            [document("15-1252.00", "Software Developers", statements)],
            client,
            with_labels=False,
        )

        rows = table.for_code("15-1252.00")
        assert len(rows) == tasks_mod.MAX_TASKS_PER_OCCUPATION
        assert all(row.task in statements for row in rows)

    def test_an_occupation_with_no_tasks_is_an_empty_list_not_an_error(self) -> None:
        """16 of the 939 retrievable rows, all military.  A panel with no task
        half is a degrade the panel already handles; a build failure is not."""
        table = tasks_mod.build_table(
            [document("55-1011.00", "Air Crew Officers", [])],
            FakeOpenAI(),
            with_labels=False,
        )

        assert table.for_code("55-1011.00") == ()
        assert "55-1011.00" in table.tasks, "the occupation vanished instead"

    def test_all_other_rows_are_excluded(self) -> None:
        """Retrieval never returns one, so a panel for one cannot be asked for."""
        rows = [
            document("15-1299.00", "Computer Occupations, All Other", ["Do things."]),
            document("15-1252.00", "Software Developers", ["Write code."]),
        ]

        table = tasks_mod.build_table(rows, FakeOpenAI(), with_labels=False)

        assert list(table.tasks) == ["15-1252.00"]

    def test_duplicate_statements_become_one_row(self) -> None:
        rows = [document("13-2011.00", "Accountants", ["Audit.", "Audit.", "File."])]

        table = tasks_mod.build_table(rows, FakeOpenAI(), with_labels=False)

        assert [row.task for row in table.for_code("13-2011.00")] == ["Audit.", "File."]

    def test_no_labels_writes_the_statement_as_its_own_label(self) -> None:
        """What `--no-labels` means, and what every test in this file uses."""
        table = tasks_mod.build_table(
            [document("29-1141.00", "Registered Nurses", ["Take vitals."])],
            FakeOpenAI(),
            with_labels=False,
        )

        row = table.for_code("29-1141.00")[0]
        assert row.label == row.task == "Take vitals."
        assert table.label_model == ""

    def test_the_labeller_seam_is_what_the_cli_resumes_through(self) -> None:
        seen: list[str] = []

        def _labels(code, title, statements):
            seen.append(code)
            return ["Doing the thing" for _ in statements], 0

        table = tasks_mod.build_table(
            [document("29-1141.00", "Registered Nurses", ["Take vitals."])],
            FakeOpenAI(),
            labels_for=_labels,
        )

        assert seen == ["29-1141.00"]
        assert table.for_code("29-1141.00")[0].label == "Doing the thing"
        assert table.for_code("29-1141.00")[0].task == "Take vitals."

    def test_one_embedding_pass_covers_every_occupation(self) -> None:
        """Not one request per occupation: `embed_documents` already batches to
        OpenAI's caps, so the whole catalog is a handful of requests."""
        statements = {
            code: ["%s task %d." % (code, n) for n in range(12)]
            for code in ("11-1021.00", "29-1141.00", "47-2111.00")
        }
        table_in = {
            text: wide(*([0.0] * (n % 12) + [1.0]))
            for texts in statements.values()
            for n, text in enumerate(texts)
        }
        client = FakeOpenAI(table_in)

        tasks_mod.build_table(
            [document(code, code, texts) for code, texts in statements.items()],
            client,
            with_labels=False,
        )

        assert client.embeddings.calls == 1

    def test_only_the_original_statements_are_ever_embedded(self) -> None:
        """F-7's hazard, asserted from the embedder's side.

        Whatever the label pass produces, the strings the embeddings API sees
        are O*NET's.  A future refactor that embedded the display prose fails
        here rather than in production, where it looks like bad recommendations.
        """
        statements = ["Statement %d about the work." % n for n in range(12)]
        client = FakeOpenAI(
            {text: wide(*([0.0] * n + [1.0])) for n, text in enumerate(statements)},
            replies=[{"labels": ["Preventing a fire"] * 8}],
        )

        tasks_mod.build_table(
            [document("33-2011.00", "Firefighters", statements)], client
        )

        assert set(client.embeddings.seen) <= set(statements)
        assert "Preventing a fire" not in client.embeddings.seen


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


class TestLabelValidation:
    @pytest.mark.parametrize(
        "label",
        [
            "",
            "   ",
            None,
            123,
            "Fixing",
            "1. Fixing bugs in existing software",
            "2) Explaining technical issues to customers",
            " ".join(["word"] * 13),
        ],
    )
    def test_a_bad_label_is_refused(self, label) -> None:
        assert tasks_mod.validate_label(label) is None

    def test_a_good_label_comes_back_cleaned(self) -> None:
        assert (
            tasks_mod.validate_label('  "Fixing bugs in existing software."  ')
            == "Fixing bugs in existing software"
        )

    def test_two_rows_of_one_job_may_not_say_the_same_thing(self) -> None:
        """Two identical labels turn two questions into one asked twice."""
        assert tasks_mod.validate_label(
            "Fixing bugs in software", ["fixing bugs in software."]
        ) is None

    def test_a_different_job_is_allowed_to_reuse_a_phrase(self) -> None:
        """The rule is per occupation; "Answering customer questions" is a real
        row for a dozen jobs and deduplicating across them would be wrong."""
        assert tasks_mod.validate_label("Answering customer questions", []) is not None


class TestLabelOccupation:
    def test_the_happy_path_is_one_request_for_the_whole_job(self) -> None:
        client = FakeOpenAI(
            replies=[{"labels": ["Fixing bugs in software", "Talking to customers"]}]
        )

        labels, fallbacks = tasks_mod.label_occupation(
            client, "Software Developers", ["Modify existing software.", "Confer."]
        )

        assert labels == ["Fixing bugs in software", "Talking to customers"]
        assert fallbacks == 0
        assert len(client.chat.calls) == 1

    def test_the_prompt_carries_every_statement_of_the_job(self) -> None:
        """One request per occupation is what lets the model avoid repeating
        itself across the eight rows -- it can see the other seven."""
        client = FakeOpenAI(replies=[{"labels": ["Doing one thing", "Doing another"]}])

        tasks_mod.label_occupation(client, "Nurses", ["Take vitals.", "Chart notes."])

        sent = client.chat.calls[0]["messages"][-1]["content"]
        assert "Take vitals." in sent and "Chart notes." in sent
        assert "Nurses" in sent

    def test_a_validation_failure_is_retried_once(self) -> None:
        client = FakeOpenAI(
            replies=[
                {"labels": ["1. Fixing bugs in software"]},
                {"labels": ["Fixing bugs in software"]},
            ]
        )

        labels, fallbacks = tasks_mod.label_occupation(
            client, "Software Developers", ["Modify existing software."]
        )

        assert labels == ["Fixing bugs in software"]
        assert fallbacks == 0
        assert len(client.chat.calls) == 2

    def test_a_label_that_fails_twice_falls_back_to_the_statement(self) -> None:
        """A statement is a poor label and an honest one -- it is what the panel
        would have shown before this pass existed.  A bad label is never
        shipped, and the fallback is counted so a build can be judged."""
        client = FakeOpenAI(replies=[{"labels": [""]}, {"labels": ["  "]}])

        labels, fallbacks = tasks_mod.label_occupation(
            client, "Software Developers", ["Modify existing software."]
        )

        assert labels == ["Modify existing software."]
        assert fallbacks == 1

    def test_a_partial_reply_keeps_the_good_rows_and_falls_back_on_the_rest(
        self,
    ) -> None:
        client = FakeOpenAI(
            replies=[
                {"labels": ["Fixing bugs in software", ""]},
                {"labels": ["ignored because row 0 is already good", ""]},
            ]
        )

        labels, fallbacks = tasks_mod.label_occupation(
            client, "Software Developers", ["Modify existing software.", "Confer."]
        )

        assert labels == ["Fixing bugs in software", "Confer."]
        assert fallbacks == 1

    def test_an_api_failure_costs_the_labels_not_the_build(self) -> None:
        """923 occupations must not die on one 500."""
        client = FakeOpenAI(replies=[RuntimeError("503"), RuntimeError("503")])

        labels, fallbacks = tasks_mod.label_occupation(
            client, "Software Developers", ["Modify existing software."]
        )

        assert labels == ["Modify existing software."]
        assert fallbacks == 1

    def test_an_unparseable_reply_is_the_same_degrade(self) -> None:
        client = FakeOpenAI(replies=["not json at all", "still not json"])

        labels, fallbacks = tasks_mod.label_occupation(
            client, "Software Developers", ["Modify existing software."]
        )

        assert labels == ["Modify existing software."]
        assert fallbacks == 1

    def test_no_statements_costs_no_request(self) -> None:
        client = FakeOpenAI()

        assert tasks_mod.label_occupation(client, "Nobody", []) == ([], 0)
        assert client.chat.calls == []

    def test_token_usage_is_accumulated_for_the_spend_gate(self) -> None:
        client = FakeOpenAI(replies=[{"labels": ["Fixing bugs in software"]}])
        usage: dict[str, int] = {}

        tasks_mod.label_occupation(
            client, "Software Developers", ["Modify software."], usage=usage
        )

        assert usage == {"requests": 1, "prompt_tokens": 100, "completion_tokens": 40}

    def test_the_projection_scales_a_sample_to_the_catalog(self) -> None:
        usage = {"prompt_tokens": 10_000, "completion_tokens": 4_000}

        cost = tasks_mod.project_label_cost(usage, sampled=25, total=925)

        assert cost["projected_prompt_tokens"] == 370_000
        assert cost["projected_completion_tokens"] == 148_000
        assert cost["projected_usd"] == pytest.approx(0.1443, abs=1e-4)


# ---------------------------------------------------------------------------
# The sidecar file
# ---------------------------------------------------------------------------


def table_of(rows: dict[str, list[tuple[str, str]]]) -> tasks_mod.TasksTable:
    return tasks_mod.TasksTable(
        tasks={
            code: tuple(tasks_mod.OccupationTask(task=t, label=l) for t, l in pairs)
            for code, pairs in rows.items()
        },
        source="test.documents.jsonl",
        label_model="gpt-4o-mini",
        label_fallbacks=2,
    )


class TestSidecar:
    def test_round_trips_through_the_file(self, tmp_path: Path) -> None:
        matrix = tmp_path / "onet_corpus_x.npy"
        table = table_of({"29-1141.00": [("Take vitals.", "Checking on patients")]})

        path = tasks_mod.write_tasks_sidecar(matrix, table)
        loaded = tasks_mod._load_sidecar(path)

        assert loaded is not None
        assert loaded.for_code("29-1141.00")[0].task == "Take vitals."
        assert loaded.for_code("29-1141.00")[0].label == "Checking on patients"
        assert loaded.label_model == "gpt-4o-mini"
        assert loaded.label_fallbacks == 2

    def test_the_payload_carries_the_metadata_its_siblings_carry(
        self, tmp_path: Path
    ) -> None:
        matrix = tmp_path / "onet_corpus_x.npy"
        path = tasks_mod.write_tasks_sidecar(
            matrix, table_of({"29-1141.00": [("Take vitals.", "Checking on patients")]})
        )

        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == tasks_mod.TASKS_SCHEMA_VERSION
        assert payload["matrix_filename"] == "onet_corpus_x.npy"
        assert payload["max_per_occupation"] == tasks_mod.MAX_TASKS_PER_OCCUPATION
        assert payload["count"] == 1
        assert payload["task_count"] == 1
        assert payload["built_at"]

    def test_no_temporary_file_is_left_behind(self, tmp_path: Path) -> None:
        tasks_mod.write_tasks_sidecar(
            tmp_path / "onet_corpus_x.npy", table_of({"a": [("t", "l")]})
        )

        assert not list(tmp_path.glob("*.tmp"))

    def test_a_missing_file_loads_as_none(self, tmp_path: Path) -> None:
        assert tasks_mod._load_sidecar(tmp_path / "nothing.tasks.json") is None

    def test_a_wrong_schema_version_is_refused_not_guessed(self, tmp_path: Path) -> None:
        path = tmp_path / "x.tasks.json"
        path.write_text(json.dumps({"schema_version": 99, "tasks": {}}), encoding="utf-8")

        assert tasks_mod._load_sidecar(path) is None

    def test_unreadable_json_degrades_rather_than_raising(self, tmp_path: Path) -> None:
        path = tmp_path / "x.tasks.json"
        path.write_text("{ not json", encoding="utf-8")

        assert tasks_mod._load_sidecar(path) is None

    def test_an_empty_table_loads_as_none(self, tmp_path: Path) -> None:
        path = tmp_path / "x.tasks.json"
        path.write_text(
            json.dumps({"schema_version": tasks_mod.TASKS_SCHEMA_VERSION, "tasks": {}}),
            encoding="utf-8",
        )

        assert tasks_mod._load_sidecar(path) is None

    def test_a_row_with_no_task_text_is_dropped_not_crashed_on(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "x.tasks.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": tasks_mod.TASKS_SCHEMA_VERSION,
                    "tasks": {"a": [{"label": "orphan"}, {"task": "real", "label": "L"}]},
                }
            ),
            encoding="utf-8",
        )

        loaded = tasks_mod._load_sidecar(path)

        assert loaded is not None
        assert [row.task for row in loaded.for_code("a")] == ["real"]

    def test_a_missing_label_falls_back_to_the_statement(self, tmp_path: Path) -> None:
        path = tmp_path / "x.tasks.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": tasks_mod.TASKS_SCHEMA_VERSION,
                    "tasks": {"a": [{"task": "Take vitals."}]},
                }
            ),
            encoding="utf-8",
        )

        loaded = tasks_mod._load_sidecar(path)

        assert loaded is not None
        assert loaded.for_code("a")[0].label == "Take vitals."

    def test_the_two_sidecar_path_helpers_agree(self, tmp_path: Path) -> None:
        """The duplicated helper in `occupation_retrieval` exists so the S3
        fetch can name the file without importing back into a cycle.  A drift
        between the two spellings leaves the object downloaded under one name
        and looked for under another."""
        matrix = tmp_path / "onet_corpus_x.npy"

        assert tasks_sidecar_path(matrix) == tasks_mod.tasks_sidecar_path(matrix)
        assert tasks_mod.tasks_sidecar_path(matrix).name == "onet_corpus_x.tasks.json"


# ---------------------------------------------------------------------------
# Process-wide access
# ---------------------------------------------------------------------------


class TestGetTasks:
    def test_a_corpus_with_no_sidecar_degrades_with_one_warning(
        self, scratch_corpus: Path, caplog
    ) -> None:
        from backend.services.occupation_retrieval import load_corpus

        corpus = load_corpus(scratch_corpus)
        with caplog.at_level("WARNING"):
            assert tasks_mod.get_tasks(corpus) is None
            assert tasks_mod.get_tasks(corpus) is None

        warnings = [r for r in caplog.records if "no tasks sidecar" in r.getMessage()]
        assert len(warnings) == 1, "the missing file was logged on every call"

    def test_loads_the_sidecar_beside_the_artifact(self, scratch_corpus: Path) -> None:
        from backend.services.occupation_retrieval import load_corpus

        tasks_mod.write_tasks_sidecar(
            scratch_corpus, table_of({"29-1141.00": [("Take vitals.", "Checking in")]})
        )
        corpus = load_corpus(scratch_corpus)

        table = tasks_mod.get_tasks(corpus)

        assert table is not None
        assert table.for_code("29-1141.00")[0].label == "Checking in"

    def test_the_table_is_memoised_per_corpus_version(self, scratch_corpus: Path) -> None:
        from backend.services.occupation_retrieval import load_corpus

        tasks_mod.write_tasks_sidecar(
            scratch_corpus, table_of({"29-1141.00": [("Take vitals.", "Checking in")]})
        )
        corpus = load_corpus(scratch_corpus)

        first = tasks_mod.get_tasks(corpus)
        tasks_sidecar_path(scratch_corpus).unlink()

        assert tasks_mod.get_tasks(corpus) is first

    def test_tasks_for_answers_the_same_for_no_sidecar_and_no_statements(
        self, scratch_corpus: Path
    ) -> None:
        """W-4's accessor.  A route that could tell the two apart would be
        reporting our deployment state to a user."""
        from backend.services.occupation_retrieval import load_corpus

        corpus = load_corpus(scratch_corpus)
        assert tasks_mod.tasks_for(corpus, "29-1141.00") == ()

        tasks_mod.reset_tasks_cache()
        tasks_mod.write_tasks_sidecar(
            scratch_corpus,
            tasks_mod.TasksTable(tasks={"29-1141.00": (), "11-1021.00": (
                tasks_mod.OccupationTask("Run the place.", "Running the place"),
            )}),
        )

        assert tasks_mod.tasks_for(corpus, "29-1141.00") == ()
        assert tasks_mod.tasks_for(corpus, "11-1021.00")[0].label == "Running the place"


# ---------------------------------------------------------------------------
# `flask corpus tasks`
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
                document("29-1141.00", "Registered Nurses", ["Take vitals.", "Chart."]),
                document("15-1299.00", "Computer Occupations, All Other", ["Do it."]),
                document("11-1021.00", "General and Operations Managers", ["Run it."]),
            )
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture()
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> FakeOpenAI:
    client = FakeOpenAI(
        replies=[{"labels": ["Checking on patients", "Writing up notes"]}] * 20
    )
    monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: client)
    return client


class TestCorpusTasksCommand:
    def test_registered_on_the_app_cli(self, ctx) -> None:
        group = ctx.cli.get_command(None, "corpus")

        assert group is not None
        assert "tasks" in group.list_commands(None)

    def test_refuses_without_an_artifact_to_write_beside(
        self, ctx, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SOLVERAH_CORPUS_PATH", raising=False)
        monkeypatch.delenv("SOLVERAH_CORPUS_DIR", raising=False)

        result = ctx.test_cli_runner().invoke(args=["corpus", "tasks"])

        assert result.exit_code != 0
        assert "SOLVERAH_CORPUS_PATH" in _text(result)

    def test_a_missing_documents_file_is_a_clean_refusal(
        self, ctx, scratch_corpus: Path, fake_llm
    ) -> None:
        result = ctx.test_cli_runner().invoke(
            args=["corpus", "tasks", "--corpus", str(scratch_corpus), "--no-labels"]
        )

        assert result.exit_code != 0
        assert "documents" in _text(result)

    def test_no_labels_builds_the_sidecar_and_makes_no_chat_call(
        self, ctx, scratch_corpus: Path, scratch_documents: Path, fake_llm
    ) -> None:
        result = ctx.test_cli_runner().invoke(
            args=["corpus", "tasks", "--corpus", str(scratch_corpus), "--no-labels"]
        )

        assert result.exit_code == 0, _text(result)
        payload = json.loads(result.output.strip().splitlines()[-1])
        assert payload["event"] == "corpus_tasks"
        assert payload["occupations"] == 2, "the All Other row was not excluded"
        assert payload["tasks_chosen"] == 3
        assert payload["labelled"] is False
        assert payload["cost"] is None
        assert fake_llm.chat.calls == []
        assert tasks_sidecar_path(scratch_corpus).is_file()

    def test_labels_are_written_and_the_run_is_priced(
        self, ctx, scratch_corpus: Path, scratch_documents: Path, fake_llm,
        tmp_path: Path
    ) -> None:
        result = ctx.test_cli_runner().invoke(
            args=[
                "corpus", "tasks", "--corpus", str(scratch_corpus),
                "--checkpoint", str(tmp_path / "labels.jsonl"),
            ]
        )

        assert result.exit_code == 0, _text(result)
        payload = json.loads(result.output.strip().splitlines()[-1])
        assert payload["labelled"] is True
        assert payload["cost"]["model"] == "gpt-4o-mini"
        assert payload["cost"]["projected_usd"] > 0
        assert len(fake_llm.chat.calls) == 2

        loaded = tasks_mod._load_sidecar(tasks_sidecar_path(scratch_corpus))
        assert loaded.for_code("29-1141.00")[0].label == "Checking on patients"
        assert loaded.for_code("29-1141.00")[0].task == "Take vitals."

    def test_a_rerun_resumes_and_does_not_re_pay_for_finished_work(
        self, ctx, scratch_corpus: Path, scratch_documents: Path, fake_llm,
        tmp_path: Path
    ) -> None:
        """The whole reason the checkpoint exists.  923 completions is not much
        money and it is a lot of minutes, and a run that dies at 800 must cost
        the remaining 123."""
        args = [
            "corpus", "tasks", "--corpus", str(scratch_corpus),
            "--checkpoint", str(tmp_path / "labels.jsonl"),
        ]
        first = ctx.test_cli_runner().invoke(args=args)
        assert first.exit_code == 0, _text(first)
        spent = len(fake_llm.chat.calls)

        second = ctx.test_cli_runner().invoke(args=args)

        assert second.exit_code == 0, _text(second)
        assert len(fake_llm.chat.calls) == spent, "the rerun re-paid for finished work"
        assert "resuming: 2" in _text(second)

    def test_a_checkpoint_row_of_the_wrong_length_is_not_reused(
        self, ctx, scratch_corpus: Path, scratch_documents: Path, fake_llm,
        tmp_path: Path
    ) -> None:
        """A rebuilt corpus can change which statements were chosen, and
        reusing labels by position would put one task's words beside
        another's text."""
        checkpoint = tmp_path / "labels.jsonl"
        checkpoint.write_text(
            json.dumps({"code": "29-1141.00", "labels": ["Only one"], "fallbacks": 0})
            + "\n",
            encoding="utf-8",
        )

        result = ctx.test_cli_runner().invoke(
            args=[
                "corpus", "tasks", "--corpus", str(scratch_corpus),
                "--checkpoint", str(checkpoint),
            ]
        )

        assert result.exit_code == 0, _text(result)
        loaded = tasks_mod._load_sidecar(tasks_sidecar_path(scratch_corpus))
        assert loaded.for_code("29-1141.00")[0].label == "Checking on patients"

    def test_limit_samples_the_catalog_but_prices_the_whole_of_it(
        self, ctx, scratch_corpus: Path, scratch_documents: Path, fake_llm,
        tmp_path: Path
    ) -> None:
        """The spend gate.  A sample must project the FULL bill or it is not a
        gate, so the denominator is every retrievable row in the documents
        file, not the ones this run happened to touch."""
        result = ctx.test_cli_runner().invoke(
            args=[
                "corpus", "tasks", "--corpus", str(scratch_corpus), "--limit", "1",
                "--checkpoint", str(tmp_path / "labels.jsonl"),
            ]
        )

        assert result.exit_code == 0, _text(result)
        payload = json.loads(result.output.strip().splitlines()[-1])
        assert payload["occupations"] == 1
        assert payload["cost"]["sampled_occupations"] == 1
        assert payload["cost"]["total_occupations"] == 2, "the All Other row was priced"

    def test_a_documents_file_with_nothing_retrievable_writes_nothing(
        self, ctx, scratch_corpus: Path, fake_llm
    ) -> None:
        docs = scratch_corpus.with_name(scratch_corpus.stem + ".documents.jsonl")
        docs.write_text(
            json.dumps(document("15-1299.00", "Computer Occupations, All Other", ["x"])),
            encoding="utf-8",
        )

        result = ctx.test_cli_runner().invoke(
            args=["corpus", "tasks", "--corpus", str(scratch_corpus), "--no-labels"]
        )

        assert result.exit_code != 0
        assert "empty sidecar" in _text(result)
        assert not tasks_sidecar_path(scratch_corpus).is_file()


# ---------------------------------------------------------------------------
# The real artifact
# ---------------------------------------------------------------------------

_REAL = os.environ.get("SOLVERAH_CORPUS_PATH")

real_corpus = pytest.mark.skipif(
    not _REAL or not Path(_REAL).exists(),
    reason="SOLVERAH_CORPUS_PATH is unset or absent; CI has no artifact",
)


@real_corpus
class TestTheRealSidecar:
    """The built file, checked against the claims it exists to support."""

    @pytest.fixture()
    def table(self):
        from backend.services.occupation_retrieval import get_corpus

        loaded = tasks_mod.get_tasks(get_corpus())
        if loaded is None:
            pytest.skip("no tasks sidecar beside the artifact")
        return loaded

    def test_it_covers_almost_every_retrievable_row(self, table) -> None:
        from backend.services.occupation_retrieval import get_corpus, is_all_other_title

        corpus = get_corpus()
        retrievable = [
            code
            for code, title in zip(corpus.codes, corpus.titles)
            if not is_all_other_title(title)
        ]

        missing = [code for code in retrievable if code not in table.tasks]
        assert len(missing) < 0.05 * len(retrievable)

    def test_no_occupation_exceeds_the_panel_size(self, table) -> None:
        for code, rows in table.tasks.items():
            assert len(rows) <= tasks_mod.MAX_TASKS_PER_OCCUPATION, code

    def test_every_stored_statement_is_a_real_onet_statement(self, table) -> None:
        """The byte-exact rule, checked against the source rather than trusted.

        If a build ever wrote a cleaned-up statement, the request-time embedding
        would no longer be of the text O*NET published and the whole "the
        original is what gets embedded" argument would be decoration.
        """
        from backend.services.occupation_retrieval import get_corpus

        documents = tasks_mod.documents_path_for(get_corpus().matrix_path)
        if not documents.is_file():
            pytest.skip("no documents JSONL beside the artifact")
        published = {
            str(row.get("code")): set(row.get("tasks") or [])
            for row in tasks_mod.iter_documents(documents)
        }

        for code, rows in table.tasks.items():
            for row in rows:
                assert row.task in published.get(code, set()), (code, row.task)

    def test_two_rows_of_one_job_never_carry_the_same_label(self, table) -> None:
        for code, rows in table.tasks.items():
            labels = [row.label.casefold() for row in rows]
            assert len(set(labels)) == len(labels), code


class TestProcessState:
    def test_create_app_does_not_read_the_sidecar(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same rule as the corpus, the clusters and the conditions: the factory
        runs in `flask db upgrade` and in a five-minute cron, and must acquire
        no file dependency from this module."""

        def explode(*args, **kwargs):  # pragma: no cover -- must not be called
            raise AssertionError("create_app() read the tasks sidecar")

        monkeypatch.setattr(tasks_mod, "_load_sidecar", explode)

        from solverah.factory import create_app

        create_app()

        assert tasks_mod._TABLE is None

    def test_the_module_imports_no_scientific_stack_at_import_time(self) -> None:
        """Selection needs numpy; reading a sidecar does not.  Both imports are
        inside the build functions, so a worker that only serves panels pays
        for neither -- the reason sidecars exist at all (the 512 MB dyno)."""
        source = (
            Path(__file__).resolve().parents[1]
            / "backend" / "services" / "occupation_tasks.py"
        ).read_text(encoding="utf-8")
        header = source[: source.index("# ----")]

        assert "import sklearn" not in source
        assert "import pandas" not in source
        assert "import requests" not in source
        assert "import numpy" not in header
        assert "occupation_corpus" not in header
