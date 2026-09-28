"""Tests for the W-3 working-conditions sidecar.

Three things this file is careful about, all of them the same point in
different places: **"not measured" is not "measured as zero".**  A missing
element, an occupation O*NET never rated, a corpus with no sidecar at all --
each degrades to "this axis does not apply here" and none of them may become a
score of 0.0, which would read as "this job has none of that" and demote it.

Nothing here reaches the network: the fetch path is exercised with a fake
client, and the build path with hand-written report records whose percentiles
can be worked out on paper.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.services import occupation_conditions as conditions
from backend.services.occupation_retrieval import (
    OccupationCorpus,
    conditions_sidecar_path,
    load_corpus,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "corpus"
FIXTURE_MATRIX = FIXTURE_DIR / "onet_corpus_testfix.npy"
FIXTURE_SIDECAR = FIXTURE_DIR / "onet_corpus_testfix.json"
FIXTURE_ZONES = FIXTURE_DIR / "onet_corpus_testfix.zones.json"

PEOPLE_ELEMENTS = [name for name, _ in conditions.AXES["people"]]
DESK_ELEMENTS = [name for name, _ in conditions.AXES["desk"]]


@pytest.fixture(autouse=True)
def _clean_process_state():
    conditions.reset_conditions_cache()
    yield
    conditions.reset_conditions_cache()


def record(code: str, title: str, work_context: dict[str, float], **reports):
    return {"code": code, "title": title, "reports": {"work_context": work_context, **reports}}


def people(value: float) -> dict[str, float]:
    """A work-context report that is *value* on every ``people`` element."""
    return {name: value for name in PEOPLE_ELEMENTS}


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
# Bundling: an axis averages the elements PRESENT
# ---------------------------------------------------------------------------


class TestBundles:
    def test_an_axis_is_the_mean_of_its_elements_on_a_0_1_scale(self) -> None:
        table = conditions.build_table(
            [record("11-1021.00", "Managers", {name: 60 for name in PEOPLE_ELEMENTS})]
        )

        assert table.raw["11-1021.00"]["people"] == pytest.approx(0.60)

    def test_a_missing_element_is_skipped_not_scored_zero(self) -> None:
        """The whole bundle rule.  Two of three elements at 90 is 0.90, not 0.60."""
        partial = {PEOPLE_ELEMENTS[0]: 90, PEOPLE_ELEMENTS[1]: 90}

        table = conditions.build_table([record("11-1021.00", "Managers", partial)])

        assert table.raw["11-1021.00"]["people"] == pytest.approx(0.90)

    def test_an_axis_with_no_elements_at_all_has_no_value(self) -> None:
        table = conditions.build_table(
            [record("11-1021.00", "Managers", {PEOPLE_ELEMENTS[0]: 50})]
        )

        assert "people" in table.raw["11-1021.00"]
        assert "desk" not in table.raw["11-1021.00"]
        assert table.percentile("11-1021.00", "desk") is None

    def test_a_negative_sign_element_counts_against_the_axis(self) -> None:
        """``desk`` is time sitting MINUS time standing and walking."""
        sitting, standing, walking = DESK_ELEMENTS

        table = conditions.build_table(
            [record("11-1021.00", "Managers", {sitting: 100, standing: 0, walking: 0})]
        )

        assert table.raw["11-1021.00"]["desk"] == pytest.approx(1.0)

    def test_a_row_with_no_work_context_report_is_absent_entirely(self) -> None:
        table = conditions.build_table(
            [{"code": "11-1021.00", "title": "Managers", "reports": {}}]
        )

        assert table.count == 0
        assert table.percentile("11-1021.00", "people") is None

    def test_a_non_numeric_value_is_ignored_rather_than_crashing(self) -> None:
        broken = dict.fromkeys(PEOPLE_ELEMENTS, 70)
        broken[PEOPLE_ELEMENTS[0]] = "not a number"

        table = conditions.build_table([record("11-1021.00", "Managers", broken)])

        assert table.raw["11-1021.00"]["people"] == pytest.approx(0.70)


# ---------------------------------------------------------------------------
# Percentiles: the reason raw values are not stored as the score
# ---------------------------------------------------------------------------


class TestPercentiles:
    def test_ranks_span_zero_to_one_across_the_rated_rows(self) -> None:
        rows = [
            record("15-2051.00", "Data Scientists", people(10)),
            record("29-1141.00", "Registered Nurses", people(50)),
            record("41-2031.00", "Retail Salespersons", people(90)),
        ]

        table = conditions.build_table(rows)

        assert table.percentile("15-2051.00", "people") == pytest.approx(0.0)
        assert table.percentile("29-1141.00", "people") == pytest.approx(0.5)
        assert table.percentile("41-2031.00", "people") == pytest.approx(1.0)

    def test_a_compressed_raw_range_becomes_a_wide_ranked_one(self) -> None:
        """Design doc §8.2's finding, as a test.

        Developers 72 and nurses 97 on Contact With Others is a 0.25 gap raw and
        the whole corpus apart once ranked -- which is why the sidecar stores
        the rank.
        """
        rows = [record("%02d-0000.00" % i, "Job %d" % i, people(70 + i)) for i in range(20)]

        table = conditions.build_table(rows)

        raw_span = table.raw["19-0000.00"]["people"] - table.raw["00-0000.00"]["people"]
        ranked_span = (
            table.percentile("19-0000.00", "people")
            - table.percentile("00-0000.00", "people")
        )
        assert raw_span == pytest.approx(0.19, abs=0.01)
        assert ranked_span == pytest.approx(1.0)

    def test_the_rank_is_taken_per_axis_over_the_rows_that_have_it(self) -> None:
        """A row missing one axis must not shift anybody's rank on it."""
        rows = [
            record("15-2051.00", "Data Scientists", people(10)),
            record("29-1141.00", "Registered Nurses", people(90)),
            record("41-2031.00", "Retail", {DESK_ELEMENTS[0]: 50}),
        ]

        table = conditions.build_table(rows)

        assert table.coverage("people") == 2
        assert table.percentile("29-1141.00", "people") == pytest.approx(1.0)
        assert table.percentile("41-2031.00", "people") is None

    def test_all_other_rows_are_left_out_of_the_ranking(self) -> None:
        """Retrieval never returns one, so it must not move anyone's percentile."""
        rows = [
            record("15-2051.00", "Data Scientists", people(10)),
            record("15-2099.00", "Mathematical Science Occupations, All Other", people(20)),
            record("29-1141.00", "Registered Nurses", people(90)),
        ]

        table = conditions.build_table(rows)

        assert "15-2099.00" not in table.percentiles
        assert table.percentile("15-2051.00", "people") == pytest.approx(0.0)
        assert table.percentile("29-1141.00", "people") == pytest.approx(1.0)

    def test_ties_rank_in_code_order_so_two_builds_agree(self) -> None:
        rows = [
            record("29-1141.00", "Registered Nurses", people(50)),
            record("15-2051.00", "Data Scientists", people(50)),
        ]

        first = conditions.build_table(rows)
        second = conditions.build_table(list(reversed(rows)))

        assert first.percentiles == second.percentiles
        assert first.percentile("15-2051.00", "people") == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# The sidecar file
# ---------------------------------------------------------------------------


class TestSidecar:
    def test_round_trips_through_the_file(self, tmp_path: Path) -> None:
        table = conditions.build_table(
            [
                record("15-2051.00", "Data Scientists", people(10)),
                record("29-1141.00", "Registered Nurses", people(90)),
            ],
            source="raw.jsonl",
        )

        path = conditions.write_conditions_sidecar(tmp_path / "onet_corpus_x.npy", table)
        back = conditions._load_sidecar(path)

        assert path.name == "onet_corpus_x.experience.json"
        assert back is not None
        assert back.percentiles == table.percentiles
        assert back.source == "raw.jsonl"

    def test_the_payload_carries_the_metadata_its_siblings_carry(
        self, tmp_path: Path
    ) -> None:
        table = conditions.build_table([record("29-1141.00", "Nurses", people(50))])

        path = conditions.write_conditions_sidecar(tmp_path / "onet_corpus_x.npy", table)
        payload = json.loads(path.read_text(encoding="utf-8"))

        assert payload["schema_version"] == conditions.CONDITIONS_SCHEMA_VERSION
        assert payload["matrix_filename"] == "onet_corpus_x.npy"
        assert payload["count"] == 1
        assert payload["built_at"]
        assert payload["elements"]["people"] == PEOPLE_ELEMENTS

    def test_no_temporary_file_is_left_behind(self, tmp_path: Path) -> None:
        table = conditions.build_table([record("29-1141.00", "Nurses", people(50))])

        conditions.write_conditions_sidecar(tmp_path / "onet_corpus_x.npy", table)

        assert list(tmp_path.glob("*.tmp")) == []

    def test_a_missing_file_loads_as_none(self, tmp_path: Path) -> None:
        assert conditions._load_sidecar(tmp_path / "nope.experience.json") is None

    def test_a_wrong_schema_version_is_refused_not_guessed(self, tmp_path: Path) -> None:
        path = tmp_path / "onet_corpus_x.experience.json"
        path.write_text(
            json.dumps({"schema_version": 99, "percentiles": {"29-1141.00": {"people": 0.5}}}),
            encoding="utf-8",
        )

        assert conditions._load_sidecar(path) is None

    def test_unreadable_json_degrades_rather_than_raising(self, tmp_path: Path) -> None:
        path = tmp_path / "onet_corpus_x.experience.json"
        path.write_text("{not json", encoding="utf-8")

        assert conditions._load_sidecar(path) is None

    def test_an_empty_percentile_table_loads_as_none(self, tmp_path: Path) -> None:
        path = tmp_path / "onet_corpus_x.experience.json"
        path.write_text(
            json.dumps({"schema_version": conditions.CONDITIONS_SCHEMA_VERSION, "percentiles": {}}),
            encoding="utf-8",
        )

        assert conditions._load_sidecar(path) is None

    def test_the_two_sidecar_path_helpers_agree(self, tmp_path: Path) -> None:
        """`occupation_retrieval` keeps its own copy of this name (import cycle)."""
        matrix = tmp_path / "onet_corpus_20260916.npy"

        assert conditions.conditions_sidecar_path(matrix) == conditions_sidecar_path(matrix)


# ---------------------------------------------------------------------------
# Process-wide access
# ---------------------------------------------------------------------------


class TestGetConditions:
    def test_a_corpus_with_no_sidecar_degrades_with_one_warning(
        self, scratch_corpus: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        corpus = load_corpus(scratch_corpus)

        with caplog.at_level("WARNING"):
            assert conditions.get_conditions(corpus) is None
            assert conditions.get_conditions(corpus) is None

        warnings = [r for r in caplog.records if "conditions sidecar" in r.getMessage()]
        assert len(warnings) == 1
        assert "flask corpus experience" in warnings[0].getMessage()

    def test_loads_the_sidecar_beside_the_artifact(self, scratch_corpus: Path) -> None:
        corpus = load_corpus(scratch_corpus)
        conditions.write_conditions_sidecar(
            scratch_corpus,
            conditions.build_table([record("29-1141.00", "Registered Nurses", people(50))]),
        )

        table = conditions.get_conditions(corpus)

        assert table is not None
        assert table.percentile("29-1141.00", "people") == pytest.approx(0.5)

    def test_the_table_is_memoised_per_corpus_version(self, scratch_corpus: Path) -> None:
        corpus = load_corpus(scratch_corpus)
        conditions.write_conditions_sidecar(
            scratch_corpus,
            conditions.build_table([record("29-1141.00", "Nurses", people(50))]),
        )

        first = conditions.get_conditions(corpus)
        scratch_corpus.with_name(
            scratch_corpus.stem + ".experience.json"
        ).unlink()  # a second read would now find nothing

        assert conditions.get_conditions(corpus) is first

    def test_a_different_corpus_version_is_not_served_the_memo(
        self, scratch_corpus: Path
    ) -> None:
        corpus = load_corpus(scratch_corpus)
        conditions.write_conditions_sidecar(
            scratch_corpus,
            conditions.build_table([record("29-1141.00", "Nurses", people(50))]),
        )
        conditions.get_conditions(corpus)

        other = OccupationCorpus(
            version="another-build",
            model=corpus.model,
            dimensions=corpus.dimensions,
            codes=corpus.codes,
            titles=corpus.titles,
            matrix=corpus.matrix,
            matrix_path=scratch_corpus.with_name("onet_corpus_other.npy"),
            zones=dict(corpus.zones),
        )

        assert conditions.get_conditions(other) is None


# ---------------------------------------------------------------------------
# Fetching, against a fake client
# ---------------------------------------------------------------------------


class FakeOnet:
    """Records what was asked for and answers from a table."""

    def __init__(self, table: dict[str, dict[str, float]] | None = None, fail: set = frozenset()):
        self.table = table or {}
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def _answer(self, report: str, code: str) -> dict[str, float]:
        from backend.services.onet_client import OnetAPIError

        self.calls.append((report, code))
        if (report, code) in self.fail:
            raise OnetAPIError("404 for %s %s" % (report, code))
        return dict(self.table.get(code, {"Contact With Others": 50}))

    def get_work_context(self, code: str) -> dict[str, float]:
        return self._answer("work_context", code)

    def get_work_styles(self, code: str) -> dict[str, float]:
        return self._answer("work_styles", code)

    def get_occupational_interests(self, code: str) -> dict[str, float]:
        return self._answer("interests", code)


class TestFetch:
    def test_fetches_three_reports_per_occupation(self) -> None:
        client = FakeOnet()

        records = conditions.fetch_condition_reports(
            client, [("29-1141.00", "Registered Nurses")]
        )

        assert len(records) == 1
        assert sorted(records[0]["reports"]) == ["interests", "work_context", "work_styles"]
        assert len(client.calls) == 3

    def test_already_fetched_codes_are_skipped_so_a_run_resumes(self) -> None:
        client = FakeOnet()

        records = conditions.fetch_condition_reports(
            client,
            [("29-1141.00", "Nurses"), ("15-2051.00", "Data Scientists")],
            already_done=["29-1141.00"],
        )

        assert [r["code"] for r in records] == ["15-2051.00"]
        assert all(code == "15-2051.00" for _, code in client.calls)

    def test_each_record_is_handed_to_the_checkpoint_as_it_completes(self) -> None:
        client = FakeOnet()
        seen: list[str] = []

        conditions.fetch_condition_reports(
            client,
            [("29-1141.00", "Nurses"), ("15-2051.00", "Data Scientists")],
            on_record=lambda record: seen.append(record["code"]),
        )

        assert seen == ["29-1141.00", "15-2051.00"]

    def test_one_failing_report_does_not_cost_the_occupation(self) -> None:
        client = FakeOnet(fail={("interests", "29-1141.00")})

        records = conditions.fetch_condition_reports(
            client, [("29-1141.00", "Registered Nurses")]
        )

        assert records[0]["reports"]["interests"] == {}
        assert records[0]["reports"]["work_context"]
        assert "interests" in records[0]["errors"]

    def test_a_rate_limit_stops_the_run_rather_than_burning_the_budget(self) -> None:
        from backend.services.onet_client import OnetRateLimitError

        class Limited(FakeOnet):
            def get_work_context(self, code: str) -> dict[str, float]:
                raise OnetRateLimitError("slow down")

        with pytest.raises(OnetRateLimitError):
            conditions.fetch_condition_reports(Limited(), [("29-1141.00", "Nurses")])

    def test_every_request_takes_a_slot_from_the_limiter(self) -> None:
        from backend.services.occupation_corpus import RateLimiter

        limiter = RateLimiter(10_000)

        conditions.fetch_condition_reports(
            FakeOnet(), [("29-1141.00", "Nurses")], limiter=limiter
        )

        assert limiter.count == 3


class TestRawRows:
    def test_reads_a_jsonl_and_skips_blank_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "raw.jsonl"
        path.write_text(
            json.dumps({"code": "a", "title": "A", "reports": {}}) + "\n\n"
            + json.dumps({"code": "b", "title": "B", "reports": {}}) + "\n",
            encoding="utf-8",
        )

        assert [row["code"] for row in conditions.iter_raw_rows(path)] == ["a", "b"]

    def test_a_malformed_line_is_a_build_failure_naming_the_line(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "raw.jsonl"
        path.write_text('{"code": "a"}\n{oops\n', encoding="utf-8")

        with pytest.raises(ValueError, match="raw.jsonl:2"):
            list(conditions.iter_raw_rows(path))


# ---------------------------------------------------------------------------
# `flask corpus experience`
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


class TestCorpusExperienceCommand:
    def test_registered_on_the_app_cli(self, ctx) -> None:
        group = ctx.cli.get_command(None, "corpus")

        assert group is not None
        assert "experience" in group.list_commands(None)

    def test_refuses_without_an_artifact_to_write_beside(
        self, ctx, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SOLVERAH_CORPUS_PATH", raising=False)
        monkeypatch.delenv("SOLVERAH_CORPUS_DIR", raising=False)

        result = ctx.test_cli_runner().invoke(args=["corpus", "experience"])

        assert result.exit_code != 0
        assert "SOLVERAH_CORPUS_PATH" in _text(result)

    def test_from_raw_builds_the_sidecar_and_makes_no_onet_call(
        self, ctx, scratch_corpus: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ONET_API_KEY", raising=False)
        raw = tmp_path / "raw.jsonl"
        raw.write_text(
            "\n".join(
                json.dumps(record(code, title, people(value)))
                for code, title, value in (
                    ("29-1141.00", "Registered Nurses", 90),
                    ("15-2051.00", "Data Scientists", 10),
                )
            ),
            encoding="utf-8",
        )

        result = ctx.test_cli_runner().invoke(
            args=[
                "corpus", "experience",
                "--corpus", str(scratch_corpus),
                "--from-raw", str(raw),
            ]
        )

        assert result.exit_code == 0, _text(result)
        summary = json.loads(result.output.strip().splitlines()[-1])
        assert summary["event"] == "corpus_experience"
        assert summary["occupations"] == 2
        assert summary["onet_requests"] == 0
        assert summary["coverage"]["people"] == 2
        written = conditions._load_sidecar(Path(summary["experience_path"]))
        assert written is not None
        assert written.percentile("29-1141.00", "people") == pytest.approx(1.0)

    def test_a_raw_file_with_no_ratings_writes_nothing(
        self, ctx, scratch_corpus: Path, tmp_path: Path
    ) -> None:
        raw = tmp_path / "raw.jsonl"
        raw.write_text(
            json.dumps({"code": "29-1141.00", "title": "Nurses", "reports": {}}),
            encoding="utf-8",
        )

        result = ctx.test_cli_runner().invoke(
            args=[
                "corpus", "experience",
                "--corpus", str(scratch_corpus),
                "--from-raw", str(raw),
            ]
        )

        assert result.exit_code != 0
        assert "empty sidecar" in _text(result)
        assert not conditions.conditions_sidecar_path(scratch_corpus).exists()

    def test_a_missing_artifact_is_a_clean_refusal(self, ctx, tmp_path: Path) -> None:
        result = ctx.test_cli_runner().invoke(
            args=["corpus", "experience", "--corpus", str(tmp_path)]
        )

        assert result.exit_code != 0
        assert "onet_corpus" in _text(result)

    def test_missing_onet_key_is_a_clean_refusal_not_a_traceback(
        self, ctx, scratch_corpus: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ONET_API_KEY", raising=False)

        result = ctx.test_cli_runner().invoke(
            args=["corpus", "experience", "--corpus", str(scratch_corpus)]
        )

        assert result.exit_code != 0
        assert "ONET_API_KEY" in _text(result)

    def test_the_fetch_path_checkpoints_and_skips_the_all_other_rows(
        self, ctx, scratch_corpus: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Three requests per occupation is the whole cost argument, so the
        residual rows -- which retrieval never returns -- must not be fetched."""
        fake = FakeOnet()
        monkeypatch.setattr(
            "backend.services.onet_client.OnetClient", lambda *a, **k: fake
        )
        monkeypatch.setenv("ONET_API_KEY", "test-key-not-a-real-one")
        checkpoint = tmp_path / "raw.jsonl"

        result = ctx.test_cli_runner().invoke(
            args=[
                "corpus", "experience",
                "--corpus", str(scratch_corpus),
                "--checkpoint", str(checkpoint),
                "--rate", "10000",
            ]
        )

        assert result.exit_code == 0, _text(result)
        summary = json.loads(result.output.strip().splitlines()[-1])
        fetched = {code for _, code in fake.calls}
        corpus = load_corpus(scratch_corpus)
        residuals = {
            code
            for code, title in zip(corpus.codes, corpus.titles)
            if title.endswith(", All Other")
        }
        assert residuals
        assert not (fetched & residuals)
        assert summary["onet_requests"] == 3 * len(fetched)
        assert len(checkpoint.read_text(encoding="utf-8").strip().splitlines()) == len(fetched)

    def test_a_second_run_resumes_from_the_checkpoint(
        self, ctx, scratch_corpus: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = FakeOnet()
        monkeypatch.setattr(
            "backend.services.onet_client.OnetClient", lambda *a, **k: fake
        )
        monkeypatch.setenv("ONET_API_KEY", "test-key-not-a-real-one")
        checkpoint = tmp_path / "raw.jsonl"
        args = [
            "corpus", "experience",
            "--corpus", str(scratch_corpus),
            "--checkpoint", str(checkpoint),
            "--rate", "10000",
        ]
        first = ctx.test_cli_runner().invoke(args=args)
        assert first.exit_code == 0, _text(first)
        calls_after_first = len(fake.calls)

        second = ctx.test_cli_runner().invoke(args=args)

        assert second.exit_code == 0, _text(second)
        assert len(fake.calls) == calls_after_first
        assert json.loads(second.output.strip().splitlines()[-1])["onet_requests"] == 0


# ---------------------------------------------------------------------------
# Against the real artifact
# ---------------------------------------------------------------------------

_REAL = __import__("os").environ.get("SOLVERAH_CORPUS_PATH")

real_corpus = pytest.mark.skipif(
    not _REAL or not Path(_REAL).exists(),
    reason="SOLVERAH_CORPUS_PATH is unset or absent; CI has no artifact",
)


@real_corpus
class TestTheRealSidecar:
    """The built file, checked against the claim it exists to support.

    Design doc §8.2 measured that O*NET's raw values are compressed -- contact
    with others is 72 for developers and 97 for nurses, which reads as a small
    difference -- and that the ranked form separates them properly.  If a
    rebuild ever produced a file where a developer's day looks sociable, the
    conditions term would be steering users on noise.
    """

    @pytest.fixture()
    def table(self):
        from backend.services.occupation_retrieval import get_corpus

        loaded = conditions.get_conditions(get_corpus())
        if loaded is None:
            pytest.skip("no conditions sidecar beside the artifact")
        return loaded

    def test_it_covers_almost_every_retrievable_row(self, table) -> None:
        from backend.services.occupation_retrieval import get_corpus, is_all_other_title

        corpus = get_corpus()
        retrievable = [
            code
            for code, title in zip(corpus.codes, corpus.titles)
            if not is_all_other_title(title)
        ]

        assert table.count >= 900
        missing = [code for code in retrievable if code not in table.percentiles]
        assert len(missing) < 0.05 * len(retrievable)

    def test_a_developer_is_at_a_desk_and_away_from_people(self, table) -> None:
        assert table.percentile("15-1252.00", "desk") > 0.90
        assert table.percentile("15-1252.00", "people") < 0.20

    def test_a_nurse_is_the_other_way_round(self, table) -> None:
        assert table.percentile("29-1141.00", "people") > 0.90
        assert table.percentile("29-1141.00", "desk") < 0.60

    def test_every_percentile_is_a_rank_in_range(self, table) -> None:
        for code, values in table.percentiles.items():
            for axis, value in values.items():
                assert axis in conditions.AXES, (code, axis)
                assert 0.0 <= value <= 1.0, (code, axis, value)


class TestProcessState:
    def test_create_app_does_not_read_the_sidecar(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same rule as the corpus and the clusters: the factory runs in
        `flask db upgrade` and in a five-minute cron, and must acquire no file
        dependency from this module."""

        def explode(*args, **kwargs):  # pragma: no cover -- must not be called
            raise AssertionError("create_app() read the conditions sidecar")

        monkeypatch.setattr(conditions, "_load_sidecar", explode)

        from solverah.factory import create_app

        create_app()

        assert conditions._TABLE is None

    def test_the_module_imports_no_scientific_stack(self) -> None:
        """A sidecar reader that imported sklearn or pandas would defeat the
        reason sidecars exist (`occupation_clusters`' docstring, the 512 MB
        dyno).  numpy is already loaded by everything else; these are not."""
        source = (
            Path(__file__).resolve().parents[1]
            / "backend" / "services" / "occupation_conditions.py"
        ).read_text(encoding="utf-8")

        assert "import sklearn" not in source
        assert "import pandas" not in source
        assert "import requests" not in source
