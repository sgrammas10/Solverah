"""Tests for backend.services.occupation_retrieval (BUILD_PLAN F-3).

THE FIXTURE
-----------
``tests/fixtures/corpus/`` holds a **synthetic** artifact: 26 occupations at 8
dimensions, ~1 KB, in exactly the format ``occupation_corpus.build_corpus``
writes.  The real artifact is 6 MB and lives outside the repo; committing it
would put binary in every clone and break the guard tests that walk the tree.

The vectors are hand-placed in four two-dimensional planes -- data, care,
trades, management -- so every ranking assertion below is arithmetic a reader
can check, not "whatever the embedding did".  One property is deliberate and
load-bearing: ``15-2099.00 Mathematical Science Occupations, All Other`` sits
*closer* to Data Scientists than Statisticians does.  That is the real
contamination in miniature (measured on the real corpus, 27 of 200 random
occupations have a residual bucket in their top-10), and it is what makes the
"..., All Other" filter test fail if the filter stops working.

:func:`test_the_committed_fixture_is_what_the_generator_produces` regenerates it
and compares bytes, so the fixture stays auditable: the table below *is* its
source, and a hand-edit to the .npy is a test failure.

Everything external is faked (S3, O*NET) and everything else is real -- numpy,
the files on disk, the process-wide memoisation, real threads.
"""
from __future__ import annotations

import io
import json
import logging
import os
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from backend.services import occupation_retrieval as retrieval
from backend.services.occupation_corpus import SCHEMA_VERSION, RateLimiter
from backend.services.onet_client import OnetClient
from backend.services.occupation_retrieval import (
    CorpusUnavailable,
    Match,
    OccupationCorpus,
    ZONES_SCHEMA_VERSION,
    fetch_job_zones,
    is_all_other_title,
    load_corpus,
    resolve_matrix_path,
    soc_prefix_excluded,
    write_zone_sidecar,
    zone_sidecar_path,
    zone_within_ceiling,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "corpus"
FIXTURE_VERSION = "testfix"
FIXTURE_MATRIX = FIXTURE_DIR / f"onet_corpus_{FIXTURE_VERSION}.npy"
FIXTURE_SIDECAR = FIXTURE_DIR / f"onet_corpus_{FIXTURE_VERSION}.json"
FIXTURE_ZONES = FIXTURE_DIR / f"onet_corpus_{FIXTURE_VERSION}.zones.json"

#: The cluster sidecar (F-8 box 9) is NOT committed beside the other three.
#: It is `occupation_clusters`' file, it is a k-means output rather than a hand
#: table, and nothing in this module reads its contents -- `_fetch_from_s3`'s
#: only job is to put it on disk at the right name. So it exists here as bytes
#: for the S3 fake, and its shape is asserted by `test_occupation_clusters.py`.
FIXTURE_CLUSTERS_NAME = f"onet_corpus_{FIXTURE_VERSION}.clusters.json"
FIXTURE_CLUSTERS_BYTES = json.dumps(
    {
        "schema_version": 1,
        "matrix_filename": f"onet_corpus_{FIXTURE_VERSION}.npy",
        "k": 2,
        "count": 2,
        "clusters": {"11-1021.00": 0, "29-1141.00": 1},
    }
).encode("utf-8")

#: W-3's two sidecars and W-9's, here for the same reason the cluster one is:
#: this module only has to put them on disk at the right name, and their
#: contents are asserted by `test_occupation_conditions.py`,
#: `test_occupation_tasks.py` and `test_occupation_fit.py`.
FIXTURE_CONDITIONS_NAME = f"onet_corpus_{FIXTURE_VERSION}.experience.json"
FIXTURE_CONDITIONS_BYTES = json.dumps(
    {
        "schema_version": 1,
        "matrix_filename": f"onet_corpus_{FIXTURE_VERSION}.npy",
        "count": 2,
        "percentiles": {"11-1021.00": {"people": 0.9}, "29-1141.00": {"people": 1.0}},
        "raw": {},
    }
).encode("utf-8")

FIXTURE_TASKS_NAME = f"onet_corpus_{FIXTURE_VERSION}.tasks.json"
FIXTURE_TASKS_BYTES = json.dumps(
    {
        "schema_version": 1,
        "matrix_filename": f"onet_corpus_{FIXTURE_VERSION}.npy",
        "count": 1,
        "tasks": {
            "29-1141.00": [
                {"task": "Record patients' vital signs.", "label": "Taking vital signs"}
            ]
        },
    }
).encode("utf-8")

FIXTURE_FIT_NAME = f"onet_corpus_{FIXTURE_VERSION}.fit.json"
FIXTURE_FIT_BYTES = json.dumps(
    {
        "schema_version": 1,
        "matrix_filename": f"onet_corpus_{FIXTURE_VERSION}.npy",
        "count": 1,
        "fits": {
            "29-1141.00": {
                "parts": ["hot_technologies"],
                "hot_tech": ["Epic Systems"],
            }
        },
    }
).encode("utf-8")

#: W-18's sidecar, for the same reason: the fetch only has to put it on disk at
#: the right name; its contents are asserted by `test_occupation_summaries.py`.
FIXTURE_SUMMARIES_NAME = f"onet_corpus_{FIXTURE_VERSION}.summaries.json"
FIXTURE_SUMMARIES_BYTES = json.dumps(
    {
        "schema_version": 1,
        "matrix_filename": f"onet_corpus_{FIXTURE_VERSION}.npy",
        "count": 1,
        "summaries": {"29-1141.00": "Assess patient health problems and needs."},
    }
).encode("utf-8")

FIXTURE_DIMS = 8

#: (code, title, job zone, unnormalised vector).  Sorted by code on write, the
#: way the real builder sorts.  Planes: dims 0-1 data, 2-3 care, 4-5 trades,
#: 6-7 management.
FIXTURE_ROWS: list[tuple[str, str, int, list[float]]] = [
    ("11-1021.00", "General and Operations Managers", 4, [0, 0, 0, 0, 0, 0, 1.00, 0.00]),
    ("11-3021.00", "Computer and Information Systems Managers", 4, [0.30, 0, 0, 0, 0, 0, 0.95, 0]),
    ("11-9199.00", "Managers, All Other", 4, [0, 0, 0, 0, 0, 0, 0.98, 0.20]),
    ("13-1199.00", "Business Operations Specialists, All Other", 4, [0, 0, 0, 0, 0, 0, 0.30, 0.95]),
    ("13-2011.00", "Accountants and Auditors", 4, [0.25, 0, 0, 0, 0, 0, 0.10, 0.96]),
    ("15-1243.00", "Database Architects", 4, [0.80, 0.60, 0, 0, 0, 0, 0, 0]),
    ("15-1299.00", "Computer Occupations, All Other", 3, [0.95, 0.30, 0, 0, 0, 0, 0, 0]),
    ("15-2031.00", "Operations Research Analysts", 4, [0.90, 0.44, 0, 0, 0, 0, 0, 0]),
    ("15-2041.00", "Statisticians", 4, [0.98, 0.20, 0, 0, 0, 0, 0, 0]),
    ("15-2051.00", "Data Scientists", 4, [1.00, 0.00, 0, 0, 0, 0, 0, 0]),
    ("15-2099.00", "Mathematical Science Occupations, All Other", 4, [0.99, 0.10, 0, 0, 0, 0, 0, 0]),
    ("19-3094.00", "Political Scientists", 5, [0.45, 0.10, 0, 0, 0, 0, 0.20, 0.60]),
    ("25-2021.00", "Elementary School Teachers, Except Special Education", 4, [0, 0, 0.40, 0.30, 0, 0, 0.20, 0.50]),
    ("29-1141.00", "Registered Nurses", 3, [0, 0, 1.00, 0.00, 0, 0, 0, 0]),
    ("29-1299.00", "Healthcare Diagnosing or Treating Practitioners, All Other", 5, [0, 0, 0.99, 0.14, 0, 0, 0, 0]),
    ("29-2061.00", "Licensed Practical and Licensed Vocational Nurses", 3, [0.02, 0, 0.97, 0.24, 0, 0, 0, 0]),
    ("31-1131.00", "Nursing Assistants", 2, [0, 0, 0.90, 0.44, 0, 0, 0, 0]),
    ("31-9099.00", "Healthcare Support Workers, All Other", 2, [0, 0, 0.93, 0.37, 0, 0, 0, 0]),
    ("35-3023.00", "Fast Food and Counter Workers", 1, [0, 0, 0.30, 0.50, 0.40, 0.20, 0, 0]),
    ("39-9011.00", "Childcare Workers", 2, [0, 0, 0.60, 0.70, 0, 0, 0, 0]),
    ("47-2031.00", "Carpenters", 2, [0, 0, 0, 0, 1.00, 0.00, 0, 0]),
    ("47-2111.00", "Electricians", 3, [0.10, 0, 0, 0, 0.96, 0.28, 0, 0]),
    ("47-4099.00", "Construction and Related Workers, All Other", 2, [0, 0, 0, 0, 0.99, 0.12, 0, 0]),
    ("47-5041.00", "Continuous Mining Machine Operators", 2, [0, 0, 0, 0, 0.70, 0.71, 0, 0]),
    ("49-3023.00", "Automotive Service Technicians and Mechanics", 3, [0.05, 0, 0, 0, 0.88, 0.47, 0, 0]),
    ("53-7062.00", "Laborers and Freight, Stock, and Material Movers, Hand", 1, [0, 0, 0, 0, 0.50, 0.60, 0.10, 0]),
]

DATA_SCIENTISTS = "15-2051.00"


# ---------------------------------------------------------------------------
# Fixture generation
# ---------------------------------------------------------------------------


def _fixture_bytes() -> tuple[bytes, str, str]:
    """Produce the three fixture files' contents from :data:`FIXTURE_ROWS`."""
    rows = sorted(FIXTURE_ROWS, key=lambda r: r[0])
    matrix = np.array([r[3] for r in rows], dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    matrix = (matrix / norms).astype(np.float32)

    buf = io.BytesIO()
    np.save(buf, matrix, allow_pickle=False)

    sidecar = {
        "schema_version": SCHEMA_VERSION,
        "version": FIXTURE_VERSION,
        "model": "synthetic-fixture",
        "dimensions": FIXTURE_DIMS,
        "dtype": "float32",
        "normalised": True,
        "built_at": "2026-09-16T00:00:00+00:00",
        "count": len(rows),
        "matrix_filename": FIXTURE_MATRIX.name,
        "max_tasks": 15,
        "max_hot_technologies": 15,
        "codes": [r[0] for r in rows],
        "titles": [r[1] for r in rows],
    }
    zones = {
        "schema_version": ZONES_SCHEMA_VERSION,
        "matrix_filename": FIXTURE_MATRIX.name,
        "source": "onet:/online/occupations",
        "built_at": "2026-09-16T00:00:00+00:00",
        "count": len(rows),
        "zones": {r[0]: r[2] for r in rows},
    }
    return (
        buf.getvalue(),
        json.dumps(sidecar, ensure_ascii=False, indent=1),
        json.dumps(zones, ensure_ascii=False, indent=1),
    )


def test_the_committed_fixture_is_what_the_generator_produces() -> None:
    """The table in this module is the fixture's source, and stays so.

    Without this, a hand-edited .npy would drift from the documented vectors
    and every ranking assertion below would silently be testing something else.
    """
    matrix, sidecar, zones = _fixture_bytes()

    assert FIXTURE_MATRIX.read_bytes() == matrix
    assert FIXTURE_SIDECAR.read_text(encoding="utf-8") == sidecar
    assert FIXTURE_ZONES.read_text(encoding="utf-8") == zones


def test_the_fixture_is_tiny_enough_to_live_in_the_repo() -> None:
    """The real artifact is 6 MB and stays outside the tree."""
    total = sum(p.stat().st_size for p in FIXTURE_DIR.iterdir() if p.is_file())

    assert total < 100_000, f"corpus fixture is {total} bytes"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_process_state(monkeypatch: pytest.MonkeyPatch):
    """No memoised corpus and no ambient corpus environment leaks into a test.

    ``SOLVERAH_CORPUS_PATH`` is deliberately deleted rather than merely
    overridden: this machine's .env is loaded by a developer shell, and a test
    that meant to exercise the S3 path would otherwise quietly load a local
    artifact and pass.
    """
    for name in (
        "SOLVERAH_CORPUS_PATH",
        "SOLVERAH_CORPUS_S3_KEY",
        "SOLVERAH_CORPUS_CACHE_DIR",
        "S3_BUCKET_NAME",
        "BACKUP_S3_BUCKET_NAME",
    ):
        monkeypatch.delenv(name, raising=False)
    retrieval.reset_corpus_cache()
    _reset_sidecar_memos()
    yield
    retrieval.reset_corpus_cache()
    _reset_sidecar_memos()


def _reset_sidecar_memos() -> None:
    """The two W-3 sidecar readers memoise per corpus VERSION, and every corpus
    in this file is version "testfix" -- so a table loaded by one test would be
    served to the next one, whose cache directory does not hold the file."""
    from backend.services import occupation_conditions, occupation_tasks

    occupation_conditions.reset_conditions_cache()
    occupation_tasks.reset_tasks_cache()


@pytest.fixture
def corpus() -> OccupationCorpus:
    return load_corpus(FIXTURE_MATRIX)


@pytest.fixture
def scratch_corpus(tmp_path: Path) -> Path:
    """A writable copy of the fixture, for tests that must corrupt it."""
    target = tmp_path / FIXTURE_MATRIX.name
    target.write_bytes(FIXTURE_MATRIX.read_bytes())
    (tmp_path / FIXTURE_SIDECAR.name).write_text(
        FIXTURE_SIDECAR.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (tmp_path / FIXTURE_ZONES.name).write_text(
        FIXTURE_ZONES.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return target


def _codes(matches: list[Match]) -> list[str]:
    return [m.code for m in matches]


# ---------------------------------------------------------------------------
# The three filter predicates, on their own
# ---------------------------------------------------------------------------


class TestAllOtherPredicate:
    @pytest.mark.parametrize(
        "title",
        [
            "Managers, All Other",
            "Engineers, All Other",
            "Healthcare Diagnosing or Treating Practitioners, All Other",
            "Surgeons, All Other  ",
        ],
    )
    def test_residual_buckets_match(self, title: str) -> None:
        assert is_all_other_title(title) is True

    @pytest.mark.parametrize(
        "title",
        [
            "Data Scientists",
            # Both of these carry the words and are real occupations. The
            # document-length criterion catches the first (68 characters on the
            # real corpus) and this one does not, which is the point.
            "Dentists, All Other Specialists",
            "First-Line Supervisors of All Other Tactical Operations Specialists",
        ],
    )
    def test_real_occupations_do_not_match(self, title: str) -> None:
        assert is_all_other_title(title) is False

    def test_the_fixture_carries_the_residuals_the_table_declares(
        self, corpus: OccupationCorpus
    ) -> None:
        assert corpus.all_other_count == 7


class TestZonePredicate:
    def test_no_ceiling_allows_everything_including_unknown(self) -> None:
        assert zone_within_ceiling(5, None) is True
        assert zone_within_ceiling(None, None) is True

    @pytest.mark.parametrize("zone,ceiling,ok", [(1, 3, True), (3, 3, True), (4, 3, False)])
    def test_the_ceiling_is_inclusive(self, zone: int, ceiling: int, ok: bool) -> None:
        assert zone_within_ceiling(zone, ceiling) is ok

    def test_unknown_zone_is_excluded_under_a_ceiling(self) -> None:
        """A feasibility filter that cannot prove feasibility must not pass."""
        assert zone_within_ceiling(None, 3) is False


class TestSocPrefixPredicate:
    def test_matches_at_every_level_of_the_soc_hierarchy(self) -> None:
        assert soc_prefix_excluded("15-1252.00", ("15-",)) is True
        assert soc_prefix_excluded("15-1252.00", ("15-12",)) is True
        assert soc_prefix_excluded("15-1252.00", ("15-2",)) is False

    def test_empty_prefix_list_excludes_nothing(self) -> None:
        assert soc_prefix_excluded("15-1252.00", ()) is False


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


class TestLoad:
    def test_loads_the_fixture_from_an_explicit_path(
        self, corpus: OccupationCorpus
    ) -> None:
        assert corpus.count == len(FIXTURE_ROWS)
        assert corpus.dimensions == FIXTURE_DIMS
        assert corpus.matrix.shape == (len(FIXTURE_ROWS), FIXTURE_DIMS)
        assert corpus.version == FIXTURE_VERSION
        assert corpus.index_of(DATA_SCIENTISTS) is not None
        assert corpus.zones_available is True

    def test_loads_from_a_directory_and_picks_the_highest_version(
        self, tmp_path: Path
    ) -> None:
        """Versions are UTC build dates, so lexical order is chronological.

        A quarterly rebuild lands beside its predecessor rather than replacing
        it (``occupation_corpus`` versions by filename precisely so that a new
        build never overwrites the one in service), so "a directory" routinely
        means "several artifacts" and the newest has to win.
        """
        directory = tmp_path / "artifacts"
        directory.mkdir()
        for version in ("20260101", "20260916"):
            target = directory / f"onet_corpus_{version}.npy"
            target.write_bytes(FIXTURE_MATRIX.read_bytes())
            target.with_suffix(".json").write_text(
                FIXTURE_SIDECAR.read_text(encoding="utf-8"), encoding="utf-8"
            )

        assert resolve_matrix_path(directory).name == "onet_corpus_20260916.npy"
        assert load_corpus(directory).count == len(FIXTURE_ROWS)

    def test_the_matrix_is_read_only(self, corpus: OccupationCorpus) -> None:
        """One thread mutating it would corrupt every other thread's queries."""
        with pytest.raises(ValueError):
            corpus.matrix[0, 0] = 99.0

    def test_missing_file_is_unavailable_not_a_crash(self, tmp_path: Path) -> None:
        with pytest.raises(CorpusUnavailable):
            load_corpus(tmp_path / "onet_corpus_nope.npy")

    def test_empty_directory_is_unavailable(self, tmp_path: Path) -> None:
        with pytest.raises(CorpusUnavailable, match="onet_corpus"):
            load_corpus(tmp_path)

    def test_missing_sidecar_is_unavailable(self, scratch_corpus: Path) -> None:
        scratch_corpus.with_suffix(".json").unlink()

        with pytest.raises(CorpusUnavailable, match="sidecar"):
            load_corpus(scratch_corpus)

    def test_schema_version_mismatch_is_a_hard_failure(
        self, scratch_corpus: Path
    ) -> None:
        """Not a warning.  A sidecar this build does not understand may be
        indexing rows that are not the rows in the matrix."""
        sidecar = scratch_corpus.with_suffix(".json")
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        meta["schema_version"] = SCHEMA_VERSION + 1
        sidecar.write_text(json.dumps(meta), encoding="utf-8")

        with pytest.raises(CorpusUnavailable, match="schema_version"):
            load_corpus(scratch_corpus)

    def test_dimension_mismatch_is_a_hard_failure(self, scratch_corpus: Path) -> None:
        """The failure this catches is a silent model swap, which returns
        plausible numbers for every query and is invisible downstream."""
        sidecar = scratch_corpus.with_suffix(".json")
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        meta["dimensions"] = 1536
        sidecar.write_text(json.dumps(meta), encoding="utf-8")

        with pytest.raises(CorpusUnavailable, match="dimensions"):
            load_corpus(scratch_corpus)

    def test_row_count_mismatch_is_a_hard_failure(self, scratch_corpus: Path) -> None:
        sidecar = scratch_corpus.with_suffix(".json")
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        meta["codes"] = meta["codes"][:-1]
        sidecar.write_text(json.dumps(meta), encoding="utf-8")

        with pytest.raises(CorpusUnavailable, match="matrix rows"):
            load_corpus(scratch_corpus)

    def test_a_corrupt_matrix_is_unavailable_not_a_traceback(
        self, scratch_corpus: Path
    ) -> None:
        scratch_corpus.write_bytes(b"not a numpy file")

        with pytest.raises(CorpusUnavailable, match="unreadable"):
            load_corpus(scratch_corpus)

    def test_an_unnormalised_matrix_is_normalised_on_load(
        self, tmp_path: Path, scratch_corpus: Path
    ) -> None:
        matrix = np.load(scratch_corpus, allow_pickle=False) * 7.0
        with scratch_corpus.open("wb") as fh:
            np.save(fh, matrix.astype(np.float32), allow_pickle=False)
        sidecar = scratch_corpus.with_suffix(".json")
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        meta["normalised"] = False
        sidecar.write_text(json.dumps(meta), encoding="utf-8")

        loaded = load_corpus(scratch_corpus)

        assert np.allclose(np.linalg.norm(loaded.matrix, axis=1), 1.0, atol=1e-5)


class TestZoneSidecarLoading:
    def test_absent_zone_sidecar_loads_a_working_corpus(
        self, scratch_corpus: Path
    ) -> None:
        """The reviewed 2026-09-16 artifact ships without one."""
        zone_sidecar_path(scratch_corpus).unlink()

        loaded = load_corpus(scratch_corpus)

        assert loaded.zones_available is False
        assert loaded.retrieve(loaded.vector_for(DATA_SCIENTISTS), 3)

    def test_zone_max_without_zones_refuses_rather_than_returning_wrong_results(
        self, scratch_corpus: Path
    ) -> None:
        zone_sidecar_path(scratch_corpus).unlink()
        loaded = load_corpus(scratch_corpus)

        with pytest.raises(CorpusUnavailable, match="zone"):
            loaded.retrieve(loaded.vector_for(DATA_SCIENTISTS), 3, zone_max=3)

    def test_an_unusable_zone_sidecar_degrades_the_filter_not_the_corpus(
        self, scratch_corpus: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        zone_sidecar_path(scratch_corpus).write_text("{ not json", encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            loaded = load_corpus(scratch_corpus)

        assert loaded.zones_available is False
        assert loaded.count == len(FIXTURE_ROWS)
        assert "zone sidecar" in caplog.text

    def test_a_row_with_no_recorded_zone_is_excluded_under_a_ceiling(
        self, scratch_corpus: Path
    ) -> None:
        """Not hypothetical: 18 real occupations have no zone on the live
        catalog, 17 of them the military group (SOC 55-*).  Measured
        2026-09-16 -- `/online/occupations` returns a zone for 923 of 1,016.

        They stay retrievable with no ceiling and disappear with one, which is
        the conservative reading of a feasibility filter.
        """
        zones = {code: zone for code, _, zone, _ in FIXTURE_ROWS}
        del zones[DATA_SCIENTISTS]
        write_zone_sidecar(scratch_corpus, zones)
        loaded = load_corpus(scratch_corpus)
        query = loaded.vector_for(DATA_SCIENTISTS)

        assert DATA_SCIENTISTS in _codes(loaded.retrieve(query, 5))
        assert DATA_SCIENTISTS not in _codes(loaded.retrieve(query, 50, zone_max=5))

    def test_a_zone_sidecar_from_a_future_schema_is_ignored(
        self, scratch_corpus: Path
    ) -> None:
        path = zone_sidecar_path(scratch_corpus)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["schema_version"] = ZONES_SCHEMA_VERSION + 1
        path.write_text(json.dumps(payload), encoding="utf-8")

        assert load_corpus(scratch_corpus).zones_available is False


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


class TestRetrieveRanking:
    def test_ranks_by_exact_cosine_best_first(self, corpus: OccupationCorpus) -> None:
        query = corpus.vector_for(DATA_SCIENTISTS)

        matches = corpus.retrieve(query, 5, include_all_other=True)

        assert _codes(matches) == [
            DATA_SCIENTISTS,       # itself, cos 1.0
            "15-2099.00",          # the residual bucket, cos 0.9949
            "15-2041.00",          # Statisticians, cos 0.9798
            "15-1299.00",          # another residual, cos 0.9536
            "15-2031.00",          # Operations Research Analysts, cos 0.8984
        ]
        assert matches[0].score == pytest.approx(1.0, abs=1e-5)
        assert matches[2].score == pytest.approx(0.9798, abs=1e-3)
        assert [m.score for m in matches] == sorted(
            (m.score for m in matches), reverse=True
        )

    def test_scores_are_the_dot_product_with_the_stored_row(
        self, corpus: OccupationCorpus
    ) -> None:
        query = corpus.vector_for(DATA_SCIENTISTS)

        match = corpus.retrieve(query, 1, exclude_codes=[DATA_SCIENTISTS])[0]

        expected = float(np.dot(corpus.matrix[match.row], query))
        assert match.score == pytest.approx(expected, abs=1e-6)

    def test_an_unnormalised_query_gives_the_same_ranking(
        self, corpus: OccupationCorpus
    ) -> None:
        """F-6's Rocchio update produces vectors of arbitrary magnitude."""
        query = corpus.vector_for(DATA_SCIENTISTS)

        scaled = corpus.retrieve(query * 37.0, 5, include_all_other=True)

        assert _codes(scaled) == _codes(corpus.retrieve(query, 5, include_all_other=True))
        assert scaled[0].score == pytest.approx(1.0, abs=1e-5)

    def test_k_larger_than_the_corpus_returns_everything_that_survives(
        self, corpus: OccupationCorpus
    ) -> None:
        matches = corpus.retrieve(corpus.vector_for(DATA_SCIENTISTS), 500)

        assert len(matches) == corpus.count - corpus.all_other_count

    def test_ties_resolve_in_catalog_order_every_time(
        self, corpus: OccupationCorpus
    ) -> None:
        """A flaky top-k under ties reads as a scoring bug from the frontend."""
        query = corpus.vector_for("47-2031.00")  # orthogonal to the data plane

        first = _codes(corpus.retrieve(query, 20))
        assert first == _codes(corpus.retrieve(query, 20))

    @pytest.mark.parametrize("k", [0, -1])
    def test_a_nonsense_k_is_a_value_error(
        self, corpus: OccupationCorpus, k: int
    ) -> None:
        with pytest.raises(ValueError, match="k must be"):
            corpus.retrieve(corpus.vector_for(DATA_SCIENTISTS), k)

    def test_a_wrong_width_query_is_a_value_error(
        self, corpus: OccupationCorpus
    ) -> None:
        with pytest.raises(ValueError, match="dimensions"):
            corpus.retrieve(np.ones(1536, dtype=np.float32), 3)

    def test_a_zero_query_is_a_value_error(self, corpus: OccupationCorpus) -> None:
        with pytest.raises(ValueError, match="zeros"):
            corpus.retrieve(np.zeros(FIXTURE_DIMS, dtype=np.float32), 3)

    def test_a_non_finite_query_is_a_value_error(
        self, corpus: OccupationCorpus
    ) -> None:
        query = corpus.vector_for(DATA_SCIENTISTS)
        query[0] = np.nan

        with pytest.raises(ValueError, match="NaN"):
            corpus.retrieve(query, 3)

    def test_a_plain_list_query_works(self, corpus: OccupationCorpus) -> None:
        matches = corpus.retrieve([1.0] + [0.0] * (FIXTURE_DIMS - 1), 1)

        assert matches[0].code == DATA_SCIENTISTS


class TestHardFilters:
    def test_all_other_rows_are_absent_by_default(
        self, corpus: OccupationCorpus
    ) -> None:
        """Unfiltered, the residual bucket outranks Statisticians -- which is
        the real corpus's failure reproduced at 8 dimensions."""
        query = corpus.vector_for(DATA_SCIENTISTS)

        matches = corpus.retrieve(query, 4, exclude_codes=[DATA_SCIENTISTS])

        assert _codes(matches) == [
            "15-2041.00",
            "15-2031.00",
            "15-1243.00",
            "19-3094.00",
        ]
        assert not any(is_all_other_title(m.title) for m in matches)

    def test_the_flag_puts_them_back(self, corpus: OccupationCorpus) -> None:
        query = corpus.vector_for(DATA_SCIENTISTS)

        matches = corpus.retrieve(
            query, 1, exclude_codes=[DATA_SCIENTISTS], include_all_other=True
        )

        assert matches[0].code == "15-2099.00"

    def test_zone_ceiling_drops_every_row_above_it(
        self, corpus: OccupationCorpus
    ) -> None:
        matches = corpus.retrieve(corpus.vector_for(DATA_SCIENTISTS), 50, zone_max=3)

        assert _codes(matches)[:3] == ["47-2111.00", "49-3023.00", "29-2061.00"]
        assert all(corpus.zones[m.code] <= 3 for m in matches)
        assert "15-2041.00" not in _codes(matches)  # zone 4

    def test_zone_ceiling_of_five_keeps_everything(
        self, corpus: OccupationCorpus
    ) -> None:
        with_ceiling = corpus.retrieve(corpus.vector_for(DATA_SCIENTISTS), 50, zone_max=5)
        without = corpus.retrieve(corpus.vector_for(DATA_SCIENTISTS), 50)

        assert _codes(with_ceiling) == _codes(without)

    @pytest.mark.parametrize("ceiling", [2, 3, 4, 5])
    def test_the_vectorised_zone_mask_agrees_with_the_named_predicate(
        self, corpus: OccupationCorpus, ceiling: int
    ) -> None:
        """``retrieve`` reimplements the zone rule as a numpy mask for speed.

        That is the one filter whose predicate and whose implementation are
        two pieces of code, so this pins them together: drift here would be a
        feasibility filter that passes rows :func:`zone_within_ceiling` says
        it should not, and nothing else would notice.
        """
        query = corpus.vector_for(DATA_SCIENTISTS)

        returned = set(_codes(corpus.retrieve(query, corpus.count, zone_max=ceiling)))
        expected = {
            code
            for code, title in zip(corpus.codes, corpus.titles)
            if not is_all_other_title(title)
            and zone_within_ceiling(corpus.zones.get(code), ceiling)
        }

        assert returned == expected

    def test_soc_prefix_exclusion_drops_a_whole_major_group(
        self, corpus: OccupationCorpus
    ) -> None:
        """F-7's "same capabilities, different field" constraint."""
        matches = corpus.retrieve(
            corpus.vector_for(DATA_SCIENTISTS), 5, exclude_soc_prefixes=("15-",)
        )

        assert _codes(matches)[:2] == ["19-3094.00", "11-3021.00"]
        assert not any(m.code.startswith("15-") for m in matches)

    @pytest.mark.parametrize(
        "prefixes", [("15-",), ("15-2", "29-"), ("1",), ("no-such-",)]
    )
    def test_the_vectorised_prefix_mask_agrees_with_the_named_predicate(
        self, corpus: OccupationCorpus, prefixes: tuple[str, ...]
    ) -> None:
        """``retrieve`` runs this filter through numpy for speed.

        Measured on the real corpus: 0.006 ms vectorised against 0.44 ms as a
        per-row call of the predicate, which is four times what the dot product
        costs.  That is worth the second implementation only while the two
        agree, so this is what keeps them agreeing.
        """
        query = corpus.vector_for(DATA_SCIENTISTS)

        returned = set(
            _codes(corpus.retrieve(query, corpus.count, exclude_soc_prefixes=prefixes))
        )
        expected = {
            code
            for code, title in zip(corpus.codes, corpus.titles)
            if not is_all_other_title(title)
            and not soc_prefix_excluded(code, prefixes)
        }

        assert returned == expected

    def test_exclude_codes_drops_exactly_those_rows(
        self, corpus: OccupationCorpus
    ) -> None:
        matches = corpus.retrieve(
            corpus.vector_for(DATA_SCIENTISTS),
            2,
            exclude_codes=[DATA_SCIENTISTS, "15-2041.00"],
        )

        assert _codes(matches) == ["15-2031.00", "15-1243.00"]

    def test_an_unknown_exclude_code_is_ignored(
        self, corpus: OccupationCorpus
    ) -> None:
        matches = corpus.retrieve(
            corpus.vector_for(DATA_SCIENTISTS), 1, exclude_codes=["99-9999.00"]
        )

        assert matches[0].code == DATA_SCIENTISTS

    def test_all_three_filters_combine(self, corpus: OccupationCorpus) -> None:
        matches = corpus.retrieve(
            corpus.vector_for(DATA_SCIENTISTS),
            10,
            exclude_codes=[DATA_SCIENTISTS, "47-2111.00"],
            exclude_soc_prefixes=("15-", "31-"),
            zone_max=3,
        )

        assert _codes(matches)[:2] == ["49-3023.00", "29-2061.00"]
        for match in matches:
            assert not is_all_other_title(match.title)
            assert not match.code.startswith(("15-", "31-"))
            assert corpus.zones[match.code] <= 3
            assert match.code not in {DATA_SCIENTISTS, "47-2111.00"}

    def test_filters_that_exclude_everything_return_an_empty_list(
        self, corpus: OccupationCorpus
    ) -> None:
        """Empty, not an exception: "nothing is feasible" is a real answer and
        F-4 has to render it either way."""
        matches = corpus.retrieve(
            corpus.vector_for(DATA_SCIENTISTS),
            10,
            exclude_soc_prefixes=tuple({c[:3] for c in corpus.codes}),
        )

        assert matches == []


class TestVectorFor:
    def test_returns_the_row_for_a_filtered_code(
        self, corpus: OccupationCorpus
    ) -> None:
        """F-4 needs an anchor even for a code retrieval must never return."""
        vector = corpus.vector_for("15-2099.00")

        assert vector.shape == (FIXTURE_DIMS,)
        assert float(np.linalg.norm(vector)) == pytest.approx(1.0, abs=1e-5)
        assert "15-2099.00" not in _codes(corpus.retrieve(vector, 10))

    def test_the_vector_is_a_writable_copy(self, corpus: OccupationCorpus) -> None:
        """Rocchio mutates what it is handed; the shared matrix must not move."""
        before = np.array(corpus.matrix[corpus.index_of(DATA_SCIENTISTS)])

        vector = corpus.vector_for(DATA_SCIENTISTS)
        vector += 5.0

        assert np.array_equal(corpus.matrix[corpus.index_of(DATA_SCIENTISTS)], before)

    def test_an_unknown_code_is_a_key_error_not_a_corpus_failure(
        self, corpus: OccupationCorpus
    ) -> None:
        with pytest.raises(KeyError):
            corpus.vector_for("99-9999.00")


# ---------------------------------------------------------------------------
# Process-wide memoisation and fail-soft
# ---------------------------------------------------------------------------


class TestProcessState:
    def test_get_corpus_memoises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SOLVERAH_CORPUS_PATH", str(FIXTURE_MATRIX))

        assert retrieval.get_corpus() is retrieval.get_corpus()

    def test_a_directory_in_the_env_var_works_too(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SOLVERAH_CORPUS_PATH", str(FIXTURE_DIR))

        assert retrieval.get_corpus().count == len(FIXTURE_ROWS)

    def test_module_level_retrieve_and_vector_for_use_the_memoised_corpus(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SOLVERAH_CORPUS_PATH", str(FIXTURE_MATRIX))

        matches = retrieval.retrieve(retrieval.vector_for(DATA_SCIENTISTS), 2)

        assert _codes(matches) == [DATA_SCIENTISTS, "15-2041.00"]

    def test_eight_threads_racing_the_first_load_decode_one_matrix(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """gthread runs eight threads per worker and they arrive together."""
        monkeypatch.setenv("SOLVERAH_CORPUS_PATH", str(FIXTURE_MATRIX))
        loads: list[float] = []
        real_load = retrieval.load_corpus

        def counting_load(source=None):
            loads.append(time.monotonic())
            time.sleep(0.02)  # widen the window a racing thread could slip into
            return real_load(source)

        monkeypatch.setattr(retrieval, "load_corpus", counting_load)

        start = threading.Barrier(8)
        seen: list[OccupationCorpus] = []
        errors: list[BaseException] = []

        def worker() -> None:
            try:
                start.wait(timeout=5)
                seen.append(retrieval.get_corpus())
            except BaseException as exc:  # noqa: BLE001 -- reported below
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == []
        assert len(loads) == 1
        assert len(seen) == 8
        assert all(c is seen[0] for c in seen)

    def test_no_source_is_unavailable_not_an_import_or_boot_failure(self) -> None:
        with pytest.raises(CorpusUnavailable, match="SOLVERAH_CORPUS_PATH"):
            retrieval.get_corpus()

    def test_the_failure_is_logged_once_per_process(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A per-request line for a missing artifact is a log-volume incident."""
        with caplog.at_level(logging.WARNING):
            for _ in range(5):
                with pytest.raises(CorpusUnavailable):
                    retrieval.get_corpus()

        assert caplog.text.count("occupation corpus unavailable") == 1

    def test_each_refusal_is_a_fresh_exception(self) -> None:
        """Re-raising one cached instance grows its ``__traceback__`` per raise.

        Over a five-minute cooldown on a busy worker that is thousands of live
        frame references held by a module global -- a slow leak of the shape
        that took this service down on 2026-09-08 and 2026-09-15.
        """
        seen = []
        for _ in range(3):
            with pytest.raises(CorpusUnavailable) as caught:
                retrieval.get_corpus()
            seen.append(caught.value)

        assert len({id(exc) for exc in seen}) == 3
        assert len({str(exc) for exc in seen}) == 1

    def test_a_remembered_failure_is_retried_after_the_cooldown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An S3 blip costs five minutes of degradation, not the worker's life."""
        with pytest.raises(CorpusUnavailable):
            retrieval.get_corpus()

        monkeypatch.setenv("SOLVERAH_CORPUS_PATH", str(FIXTURE_MATRIX))
        with pytest.raises(CorpusUnavailable):
            retrieval.get_corpus()  # still inside the cooldown

        monkeypatch.setattr(retrieval, "FAILURE_RETRY_SECONDS", 0.0)
        assert retrieval.get_corpus().count == len(FIXTURE_ROWS)

    def test_create_app_does_not_load_the_corpus(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The factory runs in `flask db upgrade` and in a five-minute cron.

        Neither should acquire an S3 dependency or a 6 MB download from this
        chunk, so the factory must not reach this module at all.
        """
        def explode(*args, **kwargs):  # pragma: no cover -- must not be called
            raise AssertionError("create_app() loaded the occupation corpus")

        monkeypatch.setattr(retrieval, "load_corpus", explode)
        monkeypatch.setattr(retrieval, "get_corpus", explode)

        from solverah.factory import create_app

        create_app()

        assert retrieval._CORPUS is None

    def test_the_factory_module_does_not_even_import_this_one(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "solverah" / "factory.py"
        ).read_text(encoding="utf-8")

        assert "occupation_retrieval" not in source


# ---------------------------------------------------------------------------
# S3 source
# ---------------------------------------------------------------------------


class _FakeBody:
    def __init__(self, payload: bytes) -> None:
        self._buf = io.BytesIO(payload)
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        return self._buf.read(size)

    def close(self) -> None:
        self.closed = True


class _FakeS3:
    """The two-method slice of the boto3 client this module uses."""

    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.gets: list[tuple[str, str]] = []

    def get_object(self, Bucket: str, Key: str) -> dict:  # noqa: N803 -- boto3's casing
        self.gets.append((Bucket, Key))
        if Key not in self.objects:
            raise KeyError(f"NoSuchKey: {Key}")
        return {"Body": _FakeBody(self.objects[Key])}


@pytest.fixture
def s3_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _FakeS3:
    monkeypatch.setenv("S3_BUCKET_NAME", "solverah-app")
    monkeypatch.setenv("SOLVERAH_CORPUS_S3_KEY", f"corpus/{FIXTURE_MATRIX.name}")
    monkeypatch.setenv("SOLVERAH_CORPUS_CACHE_DIR", str(tmp_path / "cache"))
    fake = _FakeS3(
        {
            f"corpus/{FIXTURE_MATRIX.name}": FIXTURE_MATRIX.read_bytes(),
            f"corpus/{FIXTURE_SIDECAR.name}": FIXTURE_SIDECAR.read_bytes(),
            f"corpus/{FIXTURE_ZONES.name}": FIXTURE_ZONES.read_bytes(),
            f"corpus/{FIXTURE_CLUSTERS_NAME}": FIXTURE_CLUSTERS_BYTES,
            f"corpus/{FIXTURE_CONDITIONS_NAME}": FIXTURE_CONDITIONS_BYTES,
            f"corpus/{FIXTURE_TASKS_NAME}": FIXTURE_TASKS_BYTES,
            f"corpus/{FIXTURE_FIT_NAME}": FIXTURE_FIT_BYTES,
            f"corpus/{FIXTURE_SUMMARIES_NAME}": FIXTURE_SUMMARIES_BYTES,
        }
    )
    monkeypatch.setattr("solverah.infra.storage.get_s3_client", lambda: fake)
    return fake


class TestS3Source:
    def test_downloads_and_loads_the_artifact(self, s3_env: _FakeS3) -> None:
        corpus = retrieval.get_corpus()

        assert corpus.count == len(FIXTURE_ROWS)
        assert corpus.zones_available is True
        assert [key for _, key in s3_env.gets] == [
            f"corpus/{FIXTURE_MATRIX.name}",
            f"corpus/{FIXTURE_SIDECAR.name}",
            f"corpus/{FIXTURE_ZONES.name}",
            f"corpus/{FIXTURE_CLUSTERS_NAME}",
            f"corpus/{FIXTURE_CONDITIONS_NAME}",
            f"corpus/{FIXTURE_TASKS_NAME}",
            f"corpus/{FIXTURE_FIT_NAME}",
            f"corpus/{FIXTURE_SUMMARIES_NAME}",
        ]


class TestTheClusterSidecarComesDownToo:
    """F-8 box 9. Without this, production never had a cluster sidecar.

    `_fetch_from_s3` pulled the matrix and the zones and stopped, so every
    worker on the S3 path -- which is all of production -- found no
    `*.clusters.json`, fell through to `occupation_clusters`' in-process
    k-means, and paid a 0.7 s fit plus the scikit-learn import. Per worker, on
    the 512 MB dyno that OOMed on 2026-09-15. The local-artifact path never
    showed it, because `flask corpus clusters` writes the file right next to
    the matrix.
    """

    def test_the_sidecar_lands_in_the_cache_dir(
        self, s3_env: _FakeS3, tmp_path: Path
    ) -> None:
        corpus = retrieval.get_corpus()

        path = retrieval.clusters_sidecar_path(corpus.matrix_path)
        assert path.is_file(), "the cluster sidecar was not cached"
        assert path.parent == corpus.matrix_path.parent
        assert json.loads(path.read_text(encoding="utf-8"))["k"] == 2

    def test_occupation_clusters_finds_what_this_module_downloaded(
        self, s3_env: _FakeS3
    ) -> None:
        """The two halves agree on the filename, proved rather than assumed.

        This is the assertion the duplicated path helper exists for: a drift
        between the name written here and the name read there would leave the
        file on disk and the fit still running, which is exactly the bug this
        box closes and is invisible from either side alone.
        """
        from backend.services import occupation_clusters

        corpus = retrieval.get_corpus()

        assert occupation_clusters.cluster_sidecar_path(
            corpus.matrix_path
        ) == retrieval.clusters_sidecar_path(corpus.matrix_path)

    def test_the_conditions_sidecar_comes_down_with_the_rest(
        self, s3_env: _FakeS3
    ) -> None:
        """W-3b flipped this. It used to assert the file was NOT fetched.

        Recorded as a test rather than only as a comment because the failure it
        guards is silent: a production worker with no conditions file quietly
        serves pages that ignore what the user stated, which looks exactly like
        the feature not working rather than like a missing object. The second
        assertion is the one that earns the duplicated path helper -- the name
        the fetch writes must be the name `occupation_conditions` reads.
        """
        from backend.services import occupation_conditions

        corpus = retrieval.get_corpus()
        path = retrieval.conditions_sidecar_path(corpus.matrix_path)

        assert path == occupation_conditions.conditions_sidecar_path(corpus.matrix_path)
        assert path.name.endswith(".experience.json")
        assert path.is_file(), "the conditions sidecar was not cached"
        assert occupation_conditions.get_conditions(corpus) is not None

    def test_the_tasks_sidecar_comes_down_too(self, s3_env: _FakeS3) -> None:
        """W-3b's second sidecar, same fetch, same reason.

        Without it W-4's panel has no task half -- and tasks are the wants
        layer's FIRST signal (design doc §8.2: "for this persona tasks steer
        better than conditions"), so a worker missing this file is missing most
        of the feature.
        """
        from backend.services import occupation_tasks

        corpus = retrieval.get_corpus()
        path = retrieval.tasks_sidecar_path(corpus.matrix_path)

        assert path == occupation_tasks.tasks_sidecar_path(corpus.matrix_path)
        assert path.name.endswith(".tasks.json")
        assert path.is_file(), "the tasks sidecar was not cached"
        assert occupation_tasks.get_tasks(corpus) is not None

    def test_the_summaries_sidecar_comes_down_too(self, s3_env: _FakeS3) -> None:
        """W-18. Without it every card opens with no summary line, which looks
        like a design choice rather than a missing object -- so it is asserted,
        and the name the fetch writes must be the name the loader reads."""
        from backend.services import occupation_summaries

        occupation_summaries.reset_summaries_cache()
        corpus = retrieval.get_corpus()
        path = retrieval.summaries_sidecar_path(corpus.matrix_path)

        assert path == occupation_summaries.summaries_sidecar_path(corpus.matrix_path)
        assert path.name.endswith(".summaries.json")
        assert path.is_file(), "the summaries sidecar was not cached"
        assert occupation_summaries.summary_for(corpus, "29-1141.00") == (
            "Assess patient health problems and needs."
        )
        occupation_summaries.reset_summaries_cache()

    @pytest.mark.parametrize("name", ["experience", "tasks", "summaries"])
    def test_a_missing_wants_sidecar_is_not_fatal(self, s3_env: _FakeS3, name) -> None:
        """The upload is Sebastian's trigger and the two files are published
        separately from the matrix, so "not there yet" is a normal state and
        must serve a page rather than a 503."""
        del s3_env.objects[f"corpus/onet_corpus_{FIXTURE_VERSION}.{name}.json"]

        corpus = retrieval.get_corpus()

        assert corpus.count == len(FIXTURE_ROWS)

    def test_a_missing_cluster_object_is_not_fatal(self, s3_env: _FakeS3) -> None:
        """The fallback fit stays: a corpus with no sidecar is a working corpus."""
        del s3_env.objects[f"corpus/{FIXTURE_CLUSTERS_NAME}"]

        corpus = retrieval.get_corpus()

        assert corpus.count == len(FIXTURE_ROWS)
        assert not retrieval.clusters_sidecar_path(corpus.matrix_path).is_file()

    def test_a_sidecar_uploaded_after_the_cache_was_filled_is_picked_up(
        self, s3_env: _FakeS3
    ) -> None:
        """`flask corpus clusters` runs after `corpus build`, so it lands later.

        The zones sidecar already had this; the cluster sidecar needs it for the
        same reason and one step more strongly, because nobody clears a cache
        directory on a Render dyno and the cost of not noticing is a k-means fit
        per worker rather than a filter that does not fire.
        """
        key = f"corpus/{FIXTURE_CLUSTERS_NAME}"
        payload = s3_env.objects.pop(key)
        corpus = retrieval.get_corpus()
        assert not retrieval.clusters_sidecar_path(corpus.matrix_path).is_file()

        s3_env.objects[key] = payload
        retrieval.reset_corpus_cache()
        corpus = retrieval.get_corpus()

        assert retrieval.clusters_sidecar_path(corpus.matrix_path).is_file()

    def test_a_late_fetch_costs_one_client_not_one_per_sidecar(
        self, s3_env: _FakeS3, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two missing sidecars must not mean two client constructions.

        `get_s3_client` builds a boto3 client each call, and this path runs on
        the warm-cache branch that exists to be cheap.
        """
        del s3_env.objects[f"corpus/{FIXTURE_CLUSTERS_NAME}"]
        del s3_env.objects[f"corpus/{FIXTURE_ZONES.name}"]
        retrieval.get_corpus()
        retrieval.reset_corpus_cache()

        built = 0

        def counting():
            nonlocal built
            built += 1
            return s3_env

        monkeypatch.setattr("solverah.infra.storage.get_s3_client", counting)
        retrieval.get_corpus()

        assert built == 1

    def test_the_cached_copy_is_reused_on_the_next_load(
        self, s3_env: _FakeS3, tmp_path: Path
    ) -> None:
        retrieval.get_corpus()
        retrieval.reset_corpus_cache()
        s3_env.gets.clear()

        assert retrieval.get_corpus().count == len(FIXTURE_ROWS)
        assert s3_env.gets == []

    def test_a_zone_sidecar_uploaded_after_the_cache_was_filled_is_picked_up(
        self, s3_env: _FakeS3
    ) -> None:
        """The zones file is uploaded separately and can land later.

        Without this, a worker that cached the matrix before the upload would
        refuse every ``zone_max`` query until somebody cleared its cache
        directory -- and nobody clears a cache directory on a Render dyno.
        """
        zones_key = f"corpus/{FIXTURE_ZONES.name}"
        zone_bytes = s3_env.objects.pop(zones_key)
        assert retrieval.get_corpus().zones_available is False

        s3_env.objects[zones_key] = zone_bytes
        retrieval.reset_corpus_cache()

        assert retrieval.get_corpus().zones_available is True

    def test_a_missing_zone_object_is_not_fatal(self, s3_env: _FakeS3) -> None:
        del s3_env.objects[f"corpus/{FIXTURE_ZONES.name}"]

        corpus = retrieval.get_corpus()

        assert corpus.count == len(FIXTURE_ROWS)
        assert corpus.zones_available is False

    def test_a_missing_matrix_object_is_unavailable_and_leaves_no_partial(
        self, s3_env: _FakeS3, tmp_path: Path
    ) -> None:
        del s3_env.objects[f"corpus/{FIXTURE_MATRIX.name}"]

        with pytest.raises(CorpusUnavailable, match="could not fetch"):
            retrieval.get_corpus()

        assert not list((tmp_path / "cache").glob("*.npy"))

    def test_the_local_path_wins_over_s3(
        self, s3_env: _FakeS3, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A developer with a local artifact never accidentally spends a GET."""
        monkeypatch.setenv("SOLVERAH_CORPUS_PATH", str(FIXTURE_MATRIX))

        retrieval.get_corpus()

        assert s3_env.gets == []

    def test_the_backup_bucket_is_refused(
        self, s3_env: _FakeS3, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """config.py refuses the pairing at boot; the CLI and Celery worker do
        not run that validator, so it is refused here too."""
        monkeypatch.setenv("BACKUP_S3_BUCKET_NAME", "solverah-app")

        with pytest.raises(CorpusUnavailable, match="BACKUP_S3_BUCKET_NAME"):
            retrieval.get_corpus()

    def test_a_key_without_a_bucket_is_refused(
        self, s3_env: _FakeS3, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("S3_BUCKET_NAME")

        with pytest.raises(CorpusUnavailable, match="S3_BUCKET_NAME"):
            retrieval.get_corpus()

    def test_a_non_npy_key_is_refused(
        self, s3_env: _FakeS3, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SOLVERAH_CORPUS_S3_KEY", "corpus/onet_corpus.tar.gz")

        with pytest.raises(CorpusUnavailable, match="not a .npy"):
            retrieval.get_corpus()


# ---------------------------------------------------------------------------
# The zone sidecar: fetching and writing
# ---------------------------------------------------------------------------


class _FakeZoneClient:
    """O*NET's /online/occupations paging, faked one page at a time."""

    def __init__(self, records: list[dict]) -> None:
        self.records = records
        self.pages: list[tuple[int, int]] = []

    def get_all_occupations(self, start: int = 1, end: int = 100) -> list[dict]:
        self.pages.append((start, end))
        return self.records[start - 1 : end]


class TestGetAllOccupations:
    """The one new ``onet_client`` method, against its real parsing.

    Lives in this file rather than ``tests/test_onet_client.py`` because F-3
    owns only the method, not that file -- F-2 is editing the tree concurrently
    and a shared file is where two agents collide.

    The response shapes below are the live v2 API's, captured 2026-09-16.
    """

    @staticmethod
    def _client(payload: dict) -> OnetClient:
        client = OnetClient(api_key="test-key-not-a-real-one")
        client._get = lambda path, params=None: payload  # type: ignore[method-assign]
        return client

    def test_reads_the_zone_code_not_the_zone_title(self) -> None:
        """Measured: "Actors" is ``{"code": 2, "title": "Job Zone 1-2: ..."}``.

        The title is sometimes a *range* label while the code is always one
        integer, so parsing the title would give that occupation two zones or
        none.
        """
        client = self._client(
            {
                "total": 2,
                "occupation": [
                    {
                        "code": "27-2011.00",
                        "title": "Actors",
                        "zone": {
                            "code": 2,
                            "title": "Job Zone 1-2: Very Little to Some Preparation Needed",
                        },
                    },
                    {
                        "code": "15-2011.00",
                        "title": "Actuaries",
                        "zone": {
                            "code": 4,
                            "title": "Job Zone Four: Considerable Preparation Needed",
                        },
                    },
                ],
            }
        )

        page = client.get_all_occupations(start=1, end=2)

        assert page == [
            {"code": "27-2011.00", "title": "Actors", "zone": 2},
            {"code": "15-2011.00", "title": "Actuaries", "zone": 4},
        ]

    def test_a_record_with_no_zone_block_yields_none_not_a_default(self) -> None:
        """A caller filtering on feasibility has to decide what unknown means."""
        client = self._client(
            {"occupation": [{"code": "55-1011.00", "title": "Air Crew Officers"}]}
        )

        assert client.get_all_occupations() == [
            {"code": "55-1011.00", "title": "Air Crew Officers", "zone": None}
        ]

    def test_an_unparseable_zone_is_none_rather_than_an_exception(self) -> None:
        client = self._client(
            {"occupation": [{"code": "11-1011.00", "title": "x", "zone": {"code": "?"}}]}
        )

        assert client.get_all_occupations()[0]["zone"] is None

    def test_a_record_without_a_code_is_skipped(self) -> None:
        client = self._client(
            {"occupation": [{"title": "All Occupations", "href": "..."}]}
        )

        assert client.get_all_occupations() == []

    def test_an_empty_page_is_an_empty_list(self) -> None:
        assert self._client({"total": 0}).get_all_occupations() == []


class TestFetchJobZones:
    def test_pages_until_a_short_page_and_keeps_the_zone_codes(self) -> None:
        records = [
            {"code": f"00-{i:04d}.00", "title": f"Occupation {i}", "zone": (i % 5) + 1}
            for i in range(1, 251)
        ]
        client = _FakeZoneClient(records)

        zones = fetch_job_zones(client)

        assert len(zones) == 250
        assert client.pages == [(1, 100), (101, 200), (201, 300)]
        assert zones["00-0001.00"] == 2

    def test_a_record_without_a_zone_is_absent_not_defaulted(self) -> None:
        client = _FakeZoneClient(
            [
                {"code": "15-2051.00", "title": "Data Scientists", "zone": 4},
                {"code": "55-1011.00", "title": "Air Crew Officers", "zone": None},
            ]
        )

        zones = fetch_job_zones(client)

        assert zones == {"15-2051.00": 4}

    def test_the_shared_rate_limiter_gates_every_page(self) -> None:
        """One process-wide limiter, not a second throttle of this module's own."""
        limiter = RateLimiter(1000.0)
        client = _FakeZoneClient(
            [{"code": f"00-{i:04d}.00", "title": "x", "zone": 3} for i in range(1, 151)]
        )

        fetch_job_zones(client, limiter=limiter)

        assert limiter.count == 2


class TestWriteZoneSidecar:
    def test_writes_beside_the_artifact_without_touching_it(
        self, scratch_corpus: Path
    ) -> None:
        """The .npy and its sidecar are the bytes under review for S3 upload."""
        matrix_before = scratch_corpus.read_bytes()
        sidecar_before = scratch_corpus.with_suffix(".json").read_bytes()

        path = write_zone_sidecar(scratch_corpus, {"15-2051.00": 4, "47-2031.00": 2})

        assert path == zone_sidecar_path(scratch_corpus)
        assert scratch_corpus.read_bytes() == matrix_before
        assert scratch_corpus.with_suffix(".json").read_bytes() == sidecar_before

    def test_what_it_writes_is_what_the_loader_reads(
        self, scratch_corpus: Path
    ) -> None:
        write_zone_sidecar(scratch_corpus, {r[0]: 1 for r in FIXTURE_ROWS})

        loaded = load_corpus(scratch_corpus)

        assert loaded.zones_available is True
        assert set(loaded.zones.values()) == {1}
        assert loaded.retrieve(loaded.vector_for(DATA_SCIENTISTS), 5, zone_max=1)

    def test_it_leaves_no_temp_file_behind(self, scratch_corpus: Path) -> None:
        write_zone_sidecar(scratch_corpus, {"15-2051.00": 4})

        assert not list(scratch_corpus.parent.glob("*.tmp"))


# ---------------------------------------------------------------------------
# The CLI entry point
# ---------------------------------------------------------------------------


@pytest.fixture
def ctx(client):
    """An application context on the app the factory actually builds."""
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


class TestCorpusZonesCommand:
    def test_registered_on_the_app_cli(self, ctx) -> None:
        group = ctx.cli.get_command(None, "corpus")

        assert group is not None
        assert "zones" in group.list_commands(None)

    def test_refuses_without_an_artifact_to_write_beside(
        self, ctx, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SOLVERAH_CORPUS_PATH", raising=False)
        monkeypatch.delenv("SOLVERAH_CORPUS_DIR", raising=False)

        result = ctx.test_cli_runner().invoke(args=["corpus", "zones"])

        assert result.exit_code != 0
        assert "SOLVERAH_CORPUS_PATH" in _text(result)

    def test_writes_the_sidecar_and_echoes_a_json_summary(
        self, ctx, scratch_corpus: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        records = [
            {"code": code, "title": title, "zone": zone}
            for code, title, zone, _ in FIXTURE_ROWS
        ]
        monkeypatch.setattr(
            "backend.services.onet_client.OnetClient",
            lambda *a, **k: _FakeZoneClient(records),
        )
        monkeypatch.setenv("ONET_API_KEY", "test-key-not-a-real-one")

        result = ctx.test_cli_runner().invoke(
            args=["corpus", "zones", "--corpus", str(scratch_corpus), "--rate", "1000"]
        )

        assert result.exit_code == 0, _text(result)
        summary = json.loads(result.output.strip().splitlines()[-1])
        assert summary["event"] == "corpus_zones"
        assert summary["occupations"] == len(FIXTURE_ROWS)
        assert summary["onet_requests"] == 1
        assert load_corpus(scratch_corpus).zones_available is True

    def test_a_missing_artifact_is_a_clean_refusal(
        self, ctx, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ONET_API_KEY", "test-key-not-a-real-one")

        result = ctx.test_cli_runner().invoke(
            args=["corpus", "zones", "--corpus", str(tmp_path)]
        )

        assert result.exit_code != 0
        assert "onet_corpus" in _text(result)

    def test_missing_onet_key_is_a_clean_refusal_not_a_traceback(
        self, ctx, scratch_corpus: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ONET_API_KEY", raising=False)

        result = ctx.test_cli_runner().invoke(
            args=["corpus", "zones", "--corpus", str(scratch_corpus)]
        )

        assert result.exit_code != 0
        assert "ONET_API_KEY" in _text(result)


# ---------------------------------------------------------------------------
# The real 6 MB artifact
# ---------------------------------------------------------------------------

_REAL = os.environ.get("SOLVERAH_CORPUS_PATH")


@pytest.mark.skipif(
    not _REAL or not Path(_REAL).exists(),
    reason="SOLVERAH_CORPUS_PATH is unset or absent; CI has no artifact",
)
def test_the_real_corpus_puts_statisticians_above_political_scientists() -> None:
    """The failure the whole redesign exists to avoid.

    Title-only similarity put "Data Scientists" next to "Political Scientists",
    which is why the hand-written SOC allow-list at ``path_scoring.py:154``
    exists.  Measured on the 2026-09-16 artifact: Statisticians rank 1 at
    0.759, Political Scientists rank 46 at 0.585.

    Not marked xfail and not skipped when the numbers move -- if a rebuilt
    corpus reintroduces this, the allow-list deletion in F-8 is unsafe and
    somebody needs to know before the recommendations ship.
    """
    corpus = load_corpus(_REAL)

    assert corpus.matrix.shape == (1016, 1536)
    assert np.allclose(np.linalg.norm(corpus.matrix, axis=1), 1.0, atol=1e-4)

    top5 = corpus.retrieve(
        corpus.vector_for("15-2051.00"), 5, exclude_codes=["15-2051.00"]
    )
    titles = [m.title for m in top5]

    assert "Statisticians" in titles
    assert "Political Scientists" not in titles
    assert not any(is_all_other_title(t) for t in titles)
