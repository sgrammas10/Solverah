"""Tests for W-9's deep-fit sidecar.

Two things this file is careful about, and they are the two ways this data can
go wrong in a way nobody notices:

* **A miss must be a miss.**  ``for_code`` answers None for a code the table
  lacks and a record for one it has, and ``path_deep_fit`` branches on exactly
  that.  A record that came back empty-but-present would serve an empty panel
  forever where a miss costs four requests and gets the real answer.
* **Nothing is filtered at build time.**  The importance thresholds and the
  trims all live in ``path_deep_fit`` and stay there, so the sidecar path and
  the live path can be compared byte-for-byte.  ``TestFetch`` asserts the
  builder stores what the client returned, thresholds and all.

Nothing here reaches the network: the O*NET client is a hand-written double,
which is the only external service this module touches.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend.services import occupation_fit as fit_mod
from backend.services.occupation_retrieval import fit_sidecar_path
from backend.services.onet_client import OnetAPIError, OnetRateLimitError, Skill, Task

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "corpus"
FIXTURE_MATRIX = FIXTURE_DIR / "onet_corpus_testfix.npy"
FIXTURE_SIDECAR = FIXTURE_DIR / "onet_corpus_testfix.json"
FIXTURE_ZONES = FIXTURE_DIR / "onet_corpus_testfix.zones.json"


@pytest.fixture(autouse=True)
def _clean_process_state():
    fit_mod.reset_fit_cache()
    yield
    fit_mod.reset_fit_cache()


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
# Doubles
# ---------------------------------------------------------------------------


class FakeOnet:
    """The four methods ``fetch_occupation_fit`` calls, and nothing else.

    Each answer can be replaced by an exception, which is how the isolation
    between the four is tested -- that is the property the builder shares with
    ``path_deep_fit._fetch_occupation``.
    """

    def __init__(self, **answers) -> None:
        self.answers = {
            "get_skills_profile": [
                Skill(element_id="2.A.1.a", name="Programming", importance=90.0, level=5.0),
                Skill(element_id="2.A.1.b", name="Trivia", importance=10.0, level=1.0),
            ],
            "get_hot_technologies": ["Python", "Git"],
            "get_work_activities": [
                Skill(element_id="4.A.1.a", name="Analyzing Data", importance=80.0, level=0.0),
                Skill(element_id="4.A.1.b", name="Filing", importance=20.0, level=0.0),
            ],
            "get_tasks": [
                Task(task_id="1", title="Write and test code.", importance=80.0,
                     category="Core"),
            ],
            **answers,
        }
        self.calls: list[tuple[str, str]] = []

    def _answer(self, method: str, code: str):
        self.calls.append((method, code))
        value = self.answers[method]
        if isinstance(value, Exception):
            raise value
        return value

    def get_skills_profile(self, code):
        return self._answer("get_skills_profile", code)

    def get_hot_technologies(self, code):
        return self._answer("get_hot_technologies", code)

    def get_work_activities(self, code):
        return self._answer("get_work_activities", code)

    def get_tasks(self, code):
        return self._answer("get_tasks", code)


class CountingLimiter:
    def __init__(self) -> None:
        self.count = 0

    def acquire(self) -> None:
        self.count += 1


def record(code: str = "15-1252.00", title: str = "Software Developers", **over):
    """One checkpoint/sidecar record, in the shape the builder writes."""
    payload = {
        "code": code,
        "title": title,
        "parts": list(fit_mod.FIT_PARTS),
        "generic_skills": [
            {"element_id": "2.A.1.a", "name": "Programming",
             "importance": 90.0, "level": 5.0}
        ],
        "hot_tech": ["Python", "Git"],
        "work_activities": [
            {"element_id": "4.A.1.a", "name": "Analyzing Data",
             "importance": 80.0, "level": 0.0}
        ],
        "tasks": [
            {"task_id": "1", "title": "Write and test code.",
             "importance": 80.0, "category": "Core"}
        ],
    }
    payload.update(over)
    return payload


# ---------------------------------------------------------------------------
# Fetching -- four calls, each isolated from the other three
# ---------------------------------------------------------------------------


class TestFetch:
    def test_the_happy_path_is_four_calls_and_four_parts(self) -> None:
        client = FakeOnet()

        fit = fit_mod.fetch_occupation_fit(client, "15-1252.00")

        assert [method for method, _ in client.calls] == [
            "get_skills_profile",
            "get_hot_technologies",
            "get_work_activities",
            "get_tasks",
        ]
        assert fit.parts == fit_mod.FIT_PARTS
        assert fit.complete is True

    def test_every_call_names_the_one_requested_code(self) -> None:
        client = FakeOnet()

        fit_mod.fetch_occupation_fit(client, "15-1252.00")

        assert {code for _, code in client.calls} == {"15-1252.00"}

    def test_nothing_is_filtered_on_the_way_in(self) -> None:
        """The whole equivalence argument rests on this.

        ``path_deep_fit`` drops work activities under importance 50 and generic
        skills under 50, and trims the task list to eight. Every one of those
        stays where it is, so a threshold somebody retunes next month does not
        need a 3,800-request rebuild to take effect.
        """
        fit = fit_mod.fetch_occupation_fit(FakeOnet(), "15-1252.00")

        assert [e.name for e in fit.work_activities] == ["Analyzing Data", "Filing"]
        assert [e.name for e in fit.generic_skills] == ["Programming", "Trivia"]

    def test_hot_tech_keeps_onets_order(self) -> None:
        """It is the only thing that can rank tools: they all carry one flat
        importance constant, so the order is the ranking."""
        client = FakeOnet(get_hot_technologies=["Tableau", "R", "Power BI"])

        fit = fit_mod.fetch_occupation_fit(client, "15-1252.00")

        assert fit.hot_tech == ("Tableau", "R", "Power BI")

    def test_one_failed_endpoint_keeps_the_other_three(self) -> None:
        client = FakeOnet(get_tasks=OnetAPIError("404"))

        fit = fit_mod.fetch_occupation_fit(client, "15-1252.00")

        assert fit.tasks == ()
        assert fit.parts == ("skills", "hot_technologies", "work_activities")
        assert fit.complete is False
        assert fit.hot_tech, "an unrelated answer was dropped with it"

    def test_all_four_failing_is_a_record_with_no_parts(self) -> None:
        client = FakeOnet(
            get_skills_profile=OnetAPIError("500"),
            get_hot_technologies=OnetAPIError("500"),
            get_work_activities=OnetAPIError("500"),
            get_tasks=OnetAPIError("500"),
        )

        fit = fit_mod.fetch_occupation_fit(client, "15-1252.00")

        assert fit.parts == ()

    def test_a_rate_limit_stops_the_run_rather_than_burning_the_budget(self) -> None:
        """Continuing past one 429 only spends the rest of the run on 429s --
        the judgement `occupation_conditions.fetch_condition_reports` makes."""
        client = FakeOnet(get_hot_technologies=OnetRateLimitError("429"))

        with pytest.raises(OnetRateLimitError):
            fit_mod.fetch_occupation_fit(client, "15-1252.00")

    def test_the_limiter_is_asked_once_per_request(self) -> None:
        """O*NET's documented threshold is 5/s and the builder runs at 4."""
        limiter = CountingLimiter()

        fit_mod.fetch_occupation_fit(FakeOnet(), "15-1252.00", limiter=limiter)

        assert limiter.count == 4

    def test_a_failed_endpoint_still_spent_its_slot(self) -> None:
        limiter = CountingLimiter()
        client = FakeOnet(get_tasks=OnetAPIError("404"))

        fit_mod.fetch_occupation_fit(client, "15-1252.00", limiter=limiter)

        assert limiter.count == 4


# ---------------------------------------------------------------------------
# Building the table
# ---------------------------------------------------------------------------


class TestBuildTable:
    def test_a_record_becomes_a_lookup(self) -> None:
        table = fit_mod.build_table([record()])

        stored = table.for_code("15-1252.00")
        assert stored is not None
        assert stored.hot_tech == ("Python", "Git")
        assert stored.generic_skills[0].importance == 90.0
        assert stored.tasks[0].title == "Write and test code."

    def test_a_code_the_table_lacks_is_none_not_an_empty_record(self) -> None:
        """The branch `path_deep_fit` takes: None means "ask O*NET"."""
        table = fit_mod.build_table([record()])

        assert table.for_code("29-1141.00") is None

    def test_all_other_rows_are_excluded(self) -> None:
        """Retrieval never returns one and `deep_fit` refuses a click on one, so
        four requests each would buy nothing but rate limit."""
        table = fit_mod.build_table(
            [
                record("15-1299.00", "Computer Occupations, All Other"),
                record("15-1252.00", "Software Developers"),
            ]
        )

        assert list(table.fits) == ["15-1252.00"]

    def test_a_record_where_every_endpoint_failed_is_dropped(self) -> None:
        """An empty record would look like a hit and serve an empty panel
        forever; a miss costs four requests and gets the real answer."""
        table = fit_mod.build_table(
            [record(parts=[], generic_skills=[], hot_tech=[], work_activities=[],
                    tasks=[])]
        )

        assert table.count == 0

    def test_a_partial_record_is_kept_and_counted_as_partial(self) -> None:
        table = fit_mod.build_table(
            [record(), record("29-1141.00", "Registered Nurses",
                              parts=["skills", "hot_technologies"], tasks=[])]
        )

        assert table.count == 2
        assert table.complete_count == 1

    def test_a_row_with_no_code_is_skipped(self) -> None:
        assert fit_mod.build_table([record(code="")]).count == 0


class TestCheckpointRows:
    def test_a_record_round_trips_through_the_jsonl(self, tmp_path: Path) -> None:
        path = tmp_path / "fit.raw.jsonl"
        fit = fit_mod.fetch_occupation_fit(FakeOnet(), "15-1252.00")
        path.write_text(
            json.dumps(
                fit_mod.record_payload("15-1252.00", "Software Developers", fit),
                ensure_ascii=True,
            )
            + "\n",
            encoding="utf-8",
        )

        table = fit_mod.build_table(fit_mod.iter_raw_rows(path))

        assert table.for_code("15-1252.00") == fit

    def test_blank_lines_are_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "fit.raw.jsonl"
        path.write_text(
            json.dumps(record()) + "\n\n" + json.dumps(record("29-1141.00", "Nurses")),
            encoding="utf-8",
        )

        assert len(list(fit_mod.iter_raw_rows(path))) == 2

    def test_a_malformed_line_is_a_build_failure_not_a_dropped_occupation(
        self, tmp_path: Path
    ) -> None:
        """A half-built sidecar looks exactly like a complete one downstream."""
        path = tmp_path / "fit.raw.jsonl"
        path.write_text(json.dumps(record()) + "\n{ not json\n", encoding="utf-8")

        with pytest.raises(ValueError):
            list(fit_mod.iter_raw_rows(path))


# ---------------------------------------------------------------------------
# The sidecar file
# ---------------------------------------------------------------------------


class TestSidecar:
    def test_round_trips_through_the_file(self, tmp_path: Path) -> None:
        matrix = tmp_path / "onet_corpus_x.npy"
        table = fit_mod.build_table([record()], source="fit.raw.jsonl")

        path = fit_mod.write_fit_sidecar(matrix, table)
        loaded = fit_mod._load_sidecar(path)

        assert loaded is not None
        assert loaded.for_code("15-1252.00") == table.for_code("15-1252.00")
        assert loaded.source == "fit.raw.jsonl"

    def test_the_payload_carries_the_metadata_its_siblings_carry(
        self, tmp_path: Path
    ) -> None:
        matrix = tmp_path / "onet_corpus_x.npy"
        path = fit_mod.write_fit_sidecar(matrix, fit_mod.build_table([record()]))

        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == fit_mod.FIT_SCHEMA_VERSION
        assert payload["matrix_filename"] == "onet_corpus_x.npy"
        assert payload["count"] == 1
        assert payload["complete_count"] == 1
        assert payload["parts"] == list(fit_mod.FIT_PARTS)
        assert payload["built_at"]

    def test_the_file_is_pure_ascii(self, tmp_path: Path) -> None:
        """O*NET's prose carries the odd non-ASCII character and this file is
        read on a cp1252 console often enough to matter."""
        path = fit_mod.write_fit_sidecar(
            tmp_path / "onet_corpus_x.npy",
            fit_mod.build_table(
                [
                    record(
                        tasks=[
                            {"task_id": "1", "title": "Confer with clients — daily.",
                             "importance": 80.0, "category": "Core"}
                        ]
                    )
                ]
            ),
        )

        path.read_bytes().decode("ascii")  # raises if anything slipped through
        assert fit_mod._load_sidecar(path).for_code("15-1252.00").tasks[0].title == (
            "Confer with clients — daily."
        )

    def test_no_temporary_file_is_left_behind(self, tmp_path: Path) -> None:
        fit_mod.write_fit_sidecar(
            tmp_path / "onet_corpus_x.npy", fit_mod.build_table([record()])
        )

        assert not list(tmp_path.glob("*.tmp"))

    def test_a_missing_file_loads_as_none(self, tmp_path: Path) -> None:
        assert fit_mod._load_sidecar(tmp_path / "nothing.fit.json") is None

    def test_a_wrong_schema_version_is_refused_not_guessed(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "x.fit.json"
        path.write_text(json.dumps({"schema_version": 99, "fits": {}}), encoding="utf-8")

        assert fit_mod._load_sidecar(path) is None

    def test_unreadable_json_degrades_rather_than_raising(self, tmp_path: Path) -> None:
        path = tmp_path / "x.fit.json"
        path.write_text("{ not json", encoding="utf-8")

        assert fit_mod._load_sidecar(path) is None

    def test_an_empty_table_loads_as_none(self, tmp_path: Path) -> None:
        path = tmp_path / "x.fit.json"
        path.write_text(
            json.dumps({"schema_version": fit_mod.FIT_SCHEMA_VERSION, "fits": {}}),
            encoding="utf-8",
        )

        assert fit_mod._load_sidecar(path) is None

    def test_a_stored_record_with_no_parts_is_dropped_on_load(
        self, tmp_path: Path
    ) -> None:
        """Belt and braces on the build rule: a file written by some older or
        hand-edited build must not hand back a hit with nothing in it."""
        path = tmp_path / "x.fit.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": fit_mod.FIT_SCHEMA_VERSION,
                    "fits": {
                        "15-1252.00": {"parts": [], "tasks": []},
                        "29-1141.00": {"parts": ["tasks"], "tasks": []},
                    },
                }
            ),
            encoding="utf-8",
        )

        loaded = fit_mod._load_sidecar(path)

        assert loaded is not None
        assert loaded.for_code("15-1252.00") is None
        assert loaded.for_code("29-1141.00") is not None

    def test_the_two_fit_sidecar_path_helpers_agree(self, tmp_path: Path) -> None:
        """The duplicated helper in `occupation_retrieval` exists so the S3
        fetch can name the file without importing back into a cycle. A drift
        between the two spellings leaves the object downloaded under one name
        and looked for under another."""
        matrix = tmp_path / "onet_corpus_x.npy"

        assert fit_sidecar_path(matrix) == fit_mod.fit_sidecar_path(matrix)
        assert fit_mod.fit_sidecar_path(matrix).name == "onet_corpus_x.fit.json"

    def test_the_sidecar_is_in_the_publish_set_and_names_its_command(self) -> None:
        """F-8 box 9's failure, twice over: a file the builder writes and the
        publisher does not carry is a feature that looks built and does
        nothing."""
        from backend.services import occupation_corpus

        assert ".fit.json" in occupation_corpus.OPTIONAL_PUBLISHED_SUFFIXES
        assert occupation_corpus._SUFFIX_COMMANDS[".fit.json"] == "flask corpus fit"


# ---------------------------------------------------------------------------
# Process-wide access
# ---------------------------------------------------------------------------


class TestGetFitTable:
    def test_a_corpus_with_no_sidecar_degrades_with_one_warning(
        self, scratch_corpus: Path, caplog
    ) -> None:
        from backend.services.occupation_retrieval import load_corpus

        corpus = load_corpus(scratch_corpus)
        with caplog.at_level("WARNING"):
            assert fit_mod.get_fit_table(corpus) is None
            assert fit_mod.get_fit_table(corpus) is None

        warnings = [r for r in caplog.records if "no fit sidecar" in r.getMessage()]
        assert len(warnings) == 1, "the missing file was logged on every call"

    def test_loads_the_sidecar_beside_the_artifact(self, scratch_corpus: Path) -> None:
        from backend.services.occupation_retrieval import load_corpus

        fit_mod.write_fit_sidecar(scratch_corpus, fit_mod.build_table([record()]))
        corpus = load_corpus(scratch_corpus)

        table = fit_mod.get_fit_table(corpus)

        assert table is not None
        assert table.for_code("15-1252.00").hot_tech == ("Python", "Git")

    def test_the_table_is_memoised_per_corpus_version(
        self, scratch_corpus: Path
    ) -> None:
        from backend.services.occupation_retrieval import load_corpus

        fit_mod.write_fit_sidecar(scratch_corpus, fit_mod.build_table([record()]))
        corpus = load_corpus(scratch_corpus)

        first = fit_mod.get_fit_table(corpus)
        fit_sidecar_path(scratch_corpus).unlink()

        assert fit_mod.get_fit_table(corpus) is first

    def test_reset_drops_the_memo_and_the_warning_it_logged(
        self, scratch_corpus: Path, caplog
    ) -> None:
        from backend.services.occupation_retrieval import load_corpus

        corpus = load_corpus(scratch_corpus)
        assert fit_mod.get_fit_table(corpus) is None

        fit_mod.reset_fit_cache()
        fit_mod.write_fit_sidecar(scratch_corpus, fit_mod.build_table([record()]))

        assert fit_mod.get_fit_table(corpus) is not None


class TestProcessState:
    def test_create_app_does_not_read_the_sidecar(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same rule as the corpus, the clusters, the conditions and the tasks:
        the factory runs in `flask db upgrade` and in a five-minute cron, and
        must acquire no file dependency from this module."""

        def explode(*args, **kwargs):  # pragma: no cover -- must not be called
            raise AssertionError("create_app() read the fit sidecar")

        monkeypatch.setattr(fit_mod, "_load_sidecar", explode)

        from solverah.factory import create_app

        create_app()

        assert fit_mod._TABLE is None

    def test_the_module_imports_no_scientific_stack_at_import_time(self) -> None:
        """Reading a sidecar needs json and a dict. A worker that only serves
        clicks must pay for nothing else -- the reason sidecars exist at all
        (the 512 MB dyno that OOMed on 2026-09-15)."""
        source = (
            Path(__file__).resolve().parents[1]
            / "backend" / "services" / "occupation_fit.py"
        ).read_text(encoding="utf-8")
        header = source[: source.index("# ----")]

        assert "import sklearn" not in source
        assert "import pandas" not in source
        assert "import requests" not in source
        assert "import numpy" not in header


# ---------------------------------------------------------------------------
# `flask corpus fit`
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
def fake_onet(monkeypatch: pytest.MonkeyPatch) -> FakeOnet:
    client = FakeOnet()
    monkeypatch.setattr(
        "backend.services.onet_client.OnetClient", lambda *a, **k: client
    )
    monkeypatch.setenv("ONET_API_KEY", "test-key-not-a-real-one")
    return client


def _run(ctx, *args):
    return ctx.test_cli_runner().invoke(args=["corpus", "fit", *args])


class TestCorpusFitCommand:
    def test_registered_on_the_app_cli(self, ctx) -> None:
        group = ctx.cli.get_command(None, "corpus")

        assert group is not None
        assert "fit" in group.list_commands(None)

    def test_refuses_without_an_artifact_to_write_beside(
        self, ctx, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SOLVERAH_CORPUS_PATH", raising=False)
        monkeypatch.delenv("SOLVERAH_CORPUS_DIR", raising=False)

        result = _run(ctx)

        assert result.exit_code != 0
        assert "SOLVERAH_CORPUS_PATH" in _text(result)

    def test_a_missing_artifact_is_a_clean_refusal(self, ctx, tmp_path: Path) -> None:
        result = _run(ctx, "--corpus", str(tmp_path))

        assert result.exit_code != 0
        assert "onet_corpus" in _text(result)

    def test_missing_onet_key_is_a_clean_refusal_not_a_traceback(
        self, ctx, scratch_corpus: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ONET_API_KEY", raising=False)

        result = _run(ctx, "--corpus", str(scratch_corpus))

        assert result.exit_code != 0
        assert "ONET_API_KEY" in _text(result)

    def test_it_fetches_four_per_row_and_skips_the_all_other_rows(
        self, ctx, scratch_corpus: Path, tmp_path: Path, fake_onet: FakeOnet
    ) -> None:
        """Four requests per occupation is the whole cost argument, so the
        residual rows -- which retrieval never returns and `deep_fit` refuses a
        click on -- must not be fetched."""
        from backend.services.occupation_retrieval import load_corpus

        checkpoint = tmp_path / "fit.raw.jsonl"

        result = _run(
            ctx,
            "--corpus", str(scratch_corpus),
            "--checkpoint", str(checkpoint),
            "--rate", "10000",
        )

        assert result.exit_code == 0, _text(result)
        summary = json.loads(result.output.strip().splitlines()[-1])
        fetched = {code for _, code in fake_onet.calls}
        corpus = load_corpus(scratch_corpus)
        residuals = {
            code
            for code, title in zip(corpus.codes, corpus.titles)
            if title.endswith(", All Other")
        }
        assert residuals
        assert not (fetched & residuals)
        assert summary["event"] == "corpus_fit"
        assert summary["occupations"] == len(fetched)
        assert summary["complete"] == len(fetched)
        assert summary["onet_requests"] == 4 * len(fetched)
        assert len(
            checkpoint.read_text(encoding="utf-8").strip().splitlines()
        ) == len(fetched)
        assert fit_sidecar_path(scratch_corpus).is_file()

    def test_a_second_run_resumes_and_pays_for_nothing(
        self, ctx, scratch_corpus: Path, tmp_path: Path, fake_onet: FakeOnet
    ) -> None:
        """The whole reason the checkpoint exists. ~3,800 requests is 16
        minutes, and a run that dies at 3,000 must cost the remaining 800."""
        args = (
            "--corpus", str(scratch_corpus),
            "--checkpoint", str(tmp_path / "fit.raw.jsonl"),
            "--rate", "10000",
        )
        first = _run(ctx, *args)
        assert first.exit_code == 0, _text(first)
        spent = len(fake_onet.calls)

        second = _run(ctx, *args)

        assert second.exit_code == 0, _text(second)
        assert len(fake_onet.calls) == spent, "the rerun re-paid for finished work"
        assert json.loads(second.output.strip().splitlines()[-1])["onet_requests"] == 0
        assert "resuming: %d occupations" % (spent // 4) in _text(second)

    def test_limit_samples_the_catalog(
        self, ctx, scratch_corpus: Path, tmp_path: Path, fake_onet: FakeOnet
    ) -> None:
        result = _run(
            ctx,
            "--corpus", str(scratch_corpus),
            "--checkpoint", str(tmp_path / "fit.raw.jsonl"),
            "--limit", "2",
            "--rate", "10000",
        )

        assert result.exit_code == 0, _text(result)
        summary = json.loads(result.output.strip().splitlines()[-1])
        assert summary["occupations"] == 2
        assert summary["onet_requests"] == 8

    def test_a_limited_run_does_not_drag_an_earlier_full_runs_rows_in(
        self, ctx, scratch_corpus: Path, tmp_path: Path, fake_onet: FakeOnet
    ) -> None:
        """Otherwise `--limit 2` over a finished checkpoint would answer 19 and
        the sample would not be a sample."""
        checkpoint = tmp_path / "fit.raw.jsonl"
        full = _run(
            ctx, "--corpus", str(scratch_corpus),
            "--checkpoint", str(checkpoint), "--rate", "10000",
        )
        assert full.exit_code == 0, _text(full)

        sample = _run(
            ctx, "--corpus", str(scratch_corpus), "--checkpoint", str(checkpoint),
            "--limit", "2", "--rate", "10000",
        )

        assert sample.exit_code == 0, _text(sample)
        assert json.loads(sample.output.strip().splitlines()[-1])["occupations"] == 2

    def test_the_summary_line_is_ascii(
        self, ctx, scratch_corpus: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Every print on this cp1252 console is ASCII or the command dies after
        the writes -- which is the worst place for it to die."""
        client = FakeOnet(
            get_tasks=[
                Task(task_id="1", title="Confer with clients — daily.",
                     importance=80.0, category="Core")
            ]
        )
        monkeypatch.setattr(
            "backend.services.onet_client.OnetClient", lambda *a, **k: client
        )
        monkeypatch.setenv("ONET_API_KEY", "test-key-not-a-real-one")

        result = _run(
            ctx, "--corpus", str(scratch_corpus),
            "--checkpoint", str(tmp_path / "fit.raw.jsonl"), "--rate", "10000",
        )

        assert result.exit_code == 0, _text(result)
        result.output.encode("ascii")
        (tmp_path / "fit.raw.jsonl").read_bytes().decode("ascii")

    def test_a_partial_row_is_stored_with_what_it_has(
        self, ctx, scratch_corpus: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 404 on one endpoint must not drop the occupation: three answers is
        a thinner panel, and re-fetching it live on every click is the cost this
        whole sidecar exists to remove."""
        client = FakeOnet(get_hot_technologies=OnetAPIError("404"))
        monkeypatch.setattr(
            "backend.services.onet_client.OnetClient", lambda *a, **k: client
        )
        monkeypatch.setenv("ONET_API_KEY", "test-key-not-a-real-one")

        result = _run(
            ctx, "--corpus", str(scratch_corpus),
            "--checkpoint", str(tmp_path / "fit.raw.jsonl"), "--rate", "10000",
        )

        assert result.exit_code == 0, _text(result)
        summary = json.loads(result.output.strip().splitlines()[-1])
        assert summary["complete"] == 0
        assert summary["partial"] == summary["occupations"] > 0
        stored = fit_mod._load_sidecar(fit_sidecar_path(scratch_corpus))
        assert stored.for_code("29-1141.00").hot_tech == ()
        assert stored.for_code("29-1141.00").tasks

    def test_a_corpus_where_nothing_answered_writes_nothing(
        self, ctx, scratch_corpus: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = FakeOnet(
            get_skills_profile=OnetAPIError("500"),
            get_hot_technologies=OnetAPIError("500"),
            get_work_activities=OnetAPIError("500"),
            get_tasks=OnetAPIError("500"),
        )
        monkeypatch.setattr(
            "backend.services.onet_client.OnetClient", lambda *a, **k: client
        )
        monkeypatch.setenv("ONET_API_KEY", "test-key-not-a-real-one")

        result = _run(
            ctx, "--corpus", str(scratch_corpus),
            "--checkpoint", str(tmp_path / "fit.raw.jsonl"), "--rate", "10000",
        )

        assert result.exit_code != 0
        assert "empty sidecar" in _text(result)
        assert not fit_sidecar_path(scratch_corpus).is_file()

    def test_a_rate_limit_names_the_checkpoint_to_resume_from(
        self, ctx, scratch_corpus: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = FakeOnet(get_work_activities=OnetRateLimitError("429"))
        monkeypatch.setattr(
            "backend.services.onet_client.OnetClient", lambda *a, **k: client
        )
        monkeypatch.setenv("ONET_API_KEY", "test-key-not-a-real-one")
        checkpoint = tmp_path / "fit.raw.jsonl"

        result = _run(
            ctx, "--corpus", str(scratch_corpus),
            "--checkpoint", str(checkpoint), "--rate", "10000",
        )

        assert result.exit_code != 0
        assert "rate limit" in _text(result)
        assert str(checkpoint) in _text(result)


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

        loaded = fit_mod.get_fit_table(get_corpus())
        if loaded is None:
            pytest.skip("no fit sidecar beside the artifact")
        return loaded

    def test_it_covers_almost_every_retrievable_row(self, table) -> None:
        from backend.services.occupation_retrieval import get_corpus, is_all_other_title

        corpus = get_corpus()
        retrievable = [
            code
            for code, title in zip(corpus.codes, corpus.titles)
            if not is_all_other_title(title)
        ]

        missing = [code for code in retrievable if table.for_code(code) is None]
        assert len(missing) < 0.05 * len(retrievable)

    def test_no_residual_row_was_paid_for(self, table) -> None:
        from backend.services.occupation_retrieval import get_corpus, is_all_other_title

        corpus = get_corpus()
        for code in table.fits:
            row = corpus.index_of(code)
            if row is None:
                continue
            assert not is_all_other_title(corpus.titles[row]), code

    def test_every_stored_record_has_at_least_one_answer(self, table) -> None:
        for code, stored in table.fits.items():
            assert stored.parts, code
