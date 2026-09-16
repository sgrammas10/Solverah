"""Tests for the ``fresh_start`` seed's clustering (BUILD_PLAN F-7).

Two things shape this file.

**The partition is the claim, not the algorithm.**  k-means over 1,536-dimension
embeddings is scikit-learn's problem; what this module has to get right is that
the regions it produces are *occupational domains* and not document lengths, and
that a seed drawn from them spans the space without ever preferring a candidate
for being far away.  So the synthetic tests pin the mechanics and the
``real_corpus`` ones pin the property -- SOC-major-group purity against its own
base rate, which is the only form in which "these clusters mean something" can
be asserted rather than eyeballed.

**A sidecar that has gone stale must degrade, never mislead.**  The zone sidecar
established the pattern (``occupation_retrieval._load_zones``): an absent or
unusable file is normal and costs a fit, while a file that disagrees with the
corpus is the dangerous case, because a seed missing a region is invisible in
the output.  Those are the cases with the most tests here.
"""
from __future__ import annotations

import collections
import json
import os
from pathlib import Path

import numpy as np
import pytest

from backend.services import occupation_clusters as oc
from backend.services.occupation_retrieval import OccupationCorpus

DIMS = 6


def unit(*values: float) -> np.ndarray:
    vec = np.zeros(DIMS, dtype=np.float32)
    vec[: len(values)] = values
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm else vec


def build_corpus(rows, version: str = "test", path: Path | None = None):
    matrix = np.array([vec for _, _, vec in rows], dtype=np.float32)
    matrix.setflags(write=False)
    return OccupationCorpus(
        version=version,
        model="text-embedding-3-small",
        dimensions=DIMS,
        codes=tuple(code for code, _, _ in rows),
        titles=tuple(title for _, title, _ in rows),
        matrix=matrix,
        matrix_path=path or Path("test.npy"),
        zones={},
    )


#: Three obvious lumps plus one residual bucket, far enough apart that any
#: correct clustering finds them.
ROWS = [
    ("15-1252.00", "Software Developers", unit(1, 0, 0)),
    ("15-1251.00", "Computer Programmers", unit(0.98, 0.2, 0)),
    ("29-1141.00", "Registered Nurses", unit(0, 1, 0)),
    ("29-2061.00", "Licensed Practical Nurses", unit(0.1, 0.99, 0)),
    ("47-2111.00", "Electricians", unit(0, 0, 1)),
    ("47-2073.00", "Operating Engineers", unit(0, 0.15, 0.99)),
    ("15-1299.99", "Computer Occupations, All Other", unit(1, 0, 0)),
]


@pytest.fixture(autouse=True)
def _clear_memo():
    oc.reset_cluster_cache()
    yield
    oc.reset_cluster_cache()


@pytest.fixture()
def corpus():
    return build_corpus(ROWS)


class TestComputeAssignment:
    def test_every_retrievable_row_gets_a_cluster(self, corpus) -> None:
        assignment = oc.compute_assignment(corpus, k=3)
        assert assignment.count == 6
        assert set(assignment.labels) == {c for c, _, _ in ROWS if c != "15-1299.99"}

    def test_residual_buckets_are_not_clustered(self, corpus) -> None:
        """They are ~50-character title-only documents.

        Measured on the real artifact they form their OWN cluster on length
        alone, which would spend a seed slot on rows `retrieve` filters out of
        every result anyway. See the module docstring of `occupation_clusters`.
        """
        assignment = oc.compute_assignment(corpus, k=3)
        assert assignment.cluster_of("15-1299.99") is None

    def test_the_lumps_come_out_as_the_lumps(self, corpus) -> None:
        assignment = oc.compute_assignment(corpus, k=3)
        pairs = [
            ("15-1252.00", "15-1251.00"),
            ("29-1141.00", "29-2061.00"),
            ("47-2111.00", "47-2073.00"),
        ]
        for left, right in pairs:
            assert assignment.cluster_of(left) == assignment.cluster_of(right)
        assert len({assignment.cluster_of(left) for left, _ in pairs}) == 3

    def test_the_same_corpus_fits_the_same_way_twice(self, corpus) -> None:
        """`random_state` is fixed so two workers cannot disagree."""
        first = oc.compute_assignment(corpus, k=3)
        second = oc.compute_assignment(corpus, k=3)
        assert first.labels == second.labels

    def test_centroid_nearest_returns_one_real_occupation_per_cluster(
        self, corpus
    ) -> None:
        assignment = oc.compute_assignment(corpus, k=3)
        nearest = oc.centroid_nearest(corpus, assignment)
        assert len(nearest) == 3
        assert set(nearest) == set(assignment.labels.values())
        for code in nearest.values():
            assert corpus.index_of(code) is not None


class TestDiverseSeed:
    """The selection rule, over a ranking the test writes by hand."""

    ASSIGNMENT = oc.ClusterAssignment(
        k=3,
        labels={"a": 0, "b": 0, "c": 0, "d": 1, "e": 1, "f": 2},
        source="computed",
    )

    def test_one_per_cluster_before_any_cluster_gets_a_second(self) -> None:
        picked = oc.diverse_seed(["a", "b", "c", "d", "e", "f"], self.ASSIGNMENT, 3)
        assert [["a", "b", "c", "d", "e", "f"][i] for i in picked] == ["a", "d", "f"]

    def test_the_page_is_filled_past_the_last_cluster(self) -> None:
        """Eight regions and ten cards: a short page is not the answer.

        And the fill is by RANK, not round-robin: once every region has a card,
        spread has done its job and relevance takes the remaining slots.
        """
        codes = ["a", "b", "c", "d", "e", "f"]
        picked = oc.diverse_seed(codes, self.ASSIGNMENT, 5)
        assert [codes[i] for i in picked] == ["a", "b", "c", "d", "f"]

    def test_positions_come_back_in_ranking_order(self) -> None:
        """So the caller's list keeps its order and cluster ids never leak out."""
        picked = oc.diverse_seed(["a", "b", "c", "d", "e", "f"], self.ASSIGNMENT, 4)
        assert picked == sorted(picked)

    def test_the_best_ranked_candidate_is_always_shown(self) -> None:
        """A seed that could drop rank 1 would be diversity overriding the user."""
        for limit in (1, 2, 3, 6):
            picked = oc.diverse_seed(["a", "b", "c", "d"], self.ASSIGNMENT, limit)
            assert 0 in picked

    def test_an_unclustered_code_is_deferred_not_dropped(self) -> None:
        """A judgement can outlive the sidecar that named its occupation."""
        codes = ["zz", "a", "d", "f"]
        picked = oc.diverse_seed(codes, self.ASSIGNMENT, 4)
        assert sorted(codes[i] for i in picked) == ["a", "d", "f", "zz"]

    def test_a_limit_below_one_selects_nothing(self) -> None:
        assert oc.diverse_seed(["a", "b"], self.ASSIGNMENT, 0) == []

    def test_fewer_candidates_than_the_limit_is_not_an_error(self) -> None:
        assert len(oc.diverse_seed(["a"], self.ASSIGNMENT, 10)) == 1


class TestSidecar:
    def test_round_trip(self, tmp_path) -> None:
        corpus = build_corpus(ROWS, path=tmp_path / "onet_corpus_x.npy")
        written = oc.compute_assignment(corpus, k=3)
        path = oc.write_cluster_sidecar(corpus.matrix_path, written)
        assert path.name == "onet_corpus_x.clusters.json"

        loaded = oc.get_assignment(corpus, k=3)
        assert loaded.source == "sidecar"
        assert loaded.labels == written.labels
        assert loaded.k == 3

    def test_the_sidecar_is_a_separate_file_from_the_artifact(self, tmp_path) -> None:
        """The reviewed `.npy` and its `.json` are not rewritten to add a field."""
        corpus = build_corpus(ROWS, path=tmp_path / "onet_corpus_x.npy")
        (tmp_path / "onet_corpus_x.npy").write_bytes(b"not really a matrix")
        before = (tmp_path / "onet_corpus_x.npy").read_bytes()
        oc.write_cluster_sidecar(
            corpus.matrix_path, oc.compute_assignment(corpus, k=3)
        )
        assert (tmp_path / "onet_corpus_x.npy").read_bytes() == before

    def test_no_sidecar_falls_back_to_a_fit(self, tmp_path) -> None:
        corpus = build_corpus(ROWS, path=tmp_path / "onet_corpus_x.npy")
        assert oc.get_assignment(corpus, k=3).source == "computed"

    def test_a_malformed_sidecar_is_ignored_rather_than_raised(
        self, tmp_path, caplog
    ) -> None:
        corpus = build_corpus(ROWS, path=tmp_path / "onet_corpus_x.npy")
        oc.cluster_sidecar_path(corpus.matrix_path).write_text("{not json")
        assignment = oc.get_assignment(corpus, k=3)
        assert assignment.source == "computed"
        assert assignment.count == 6

    def test_a_sidecar_from_another_schema_is_ignored(self, tmp_path) -> None:
        corpus = build_corpus(ROWS, path=tmp_path / "onet_corpus_x.npy")
        oc.cluster_sidecar_path(corpus.matrix_path).write_text(
            json.dumps({"schema_version": 99, "k": 3, "clusters": {"15-1252.00": 0}})
        )
        assert oc.get_assignment(corpus, k=3).source == "computed"

    def test_a_sidecar_that_predates_the_corpus_is_stale_not_partial(
        self, tmp_path, caplog
    ) -> None:
        """The dangerous case: a seed silently stops spanning part of the space.

        A corpus rebuild that adds an occupation leaves every existing sidecar
        short of it, and `diverse_seed` would quietly file the new rows under
        "no cluster". Refitting is the right answer and the warning names the
        command that fixes it.
        """
        corpus = build_corpus(ROWS, path=tmp_path / "onet_corpus_x.npy")
        full = oc.compute_assignment(corpus, k=3)
        partial = dict(full.labels)
        partial.pop("47-2111.00")
        oc.cluster_sidecar_path(corpus.matrix_path).write_text(
            json.dumps(
                {"schema_version": oc.CLUSTERS_SCHEMA_VERSION, "k": 3, "clusters": partial}
            )
        )
        with caplog.at_level("WARNING"):
            assignment = oc.get_assignment(corpus, k=3)
        assert assignment.source == "computed"
        assert "flask corpus" in caplog.text

    def test_a_sidecar_naming_retired_codes_is_still_usable(self, tmp_path) -> None:
        """The harmless direction: judgements and sidecars outlive occupations."""
        corpus = build_corpus(ROWS, path=tmp_path / "onet_corpus_x.npy")
        labels = dict(oc.compute_assignment(corpus, k=3).labels)
        labels["99-9999.00"] = 2
        oc.cluster_sidecar_path(corpus.matrix_path).write_text(
            json.dumps(
                {"schema_version": oc.CLUSTERS_SCHEMA_VERSION, "k": 3, "clusters": labels}
            )
        )
        assert oc.get_assignment(corpus, k=3).source == "sidecar"

    def test_a_sidecar_built_for_another_k_is_refitted(self, tmp_path) -> None:
        corpus = build_corpus(ROWS, path=tmp_path / "onet_corpus_x.npy")
        oc.write_cluster_sidecar(corpus.matrix_path, oc.compute_assignment(corpus, k=2))
        assert oc.get_assignment(corpus, k=3).source == "computed"


class TestMemo:
    def test_the_fit_is_paid_for_once(self, corpus, monkeypatch) -> None:
        calls: list[int] = []
        real = oc.compute_assignment
        monkeypatch.setattr(
            oc,
            "compute_assignment",
            lambda c, k=oc.CLUSTER_COUNT: (calls.append(1), real(c, k=k))[1],
        )
        first = oc.get_assignment(corpus, k=3)
        second = oc.get_assignment(corpus, k=3)
        assert first is second
        assert len(calls) == 1

    def test_a_different_corpus_is_not_served_the_old_labels(
        self, corpus, monkeypatch
    ) -> None:
        """A test that swaps in a synthetic corpus must not inherit the real one."""
        oc.get_assignment(corpus, k=3)
        other = build_corpus(ROWS[:4], version="other")
        assert oc.get_assignment(other, k=3).count == 4

    def test_a_different_k_is_not_served_the_old_labels(self, corpus) -> None:
        assert oc.get_assignment(corpus, k=3).k == 3
        assert oc.get_assignment(corpus, k=2).k == 2


def test_sklearn_is_not_imported_merely_by_importing_this_module() -> None:
    """The dyno is 512 MB and OOMed on 2026-09-15.

    A worker with a sidecar must never pay for the scientific stack, so the
    scikit-learn import lives inside `compute_assignment` rather than at module
    scope. Asserted on the source rather than on `sys.modules`, because any
    earlier test in the session may legitimately have imported it.
    """
    source = Path(oc.__file__).read_text(encoding="utf-8")
    head = source[: source.index("def compute_assignment")]
    assert "import sklearn" not in head
    assert "from sklearn" not in head


# ---------------------------------------------------------------------------
# Against the real 1,016-row artifact
# ---------------------------------------------------------------------------

real_corpus = pytest.mark.skipif(
    not os.environ.get("SOLVERAH_CORPUS_PATH"),
    reason="SOLVERAH_CORPUS_PATH is unset; CI has no corpus artifact",
)


@real_corpus
class TestAgainstTheRealCorpus:
    """Do these clusters mean occupational domain, or document length?

    F-7's brief names this as the thing that would make the whole seed
    meaningless, so it is asserted rather than eyeballed.
    """

    @pytest.fixture()
    def real(self):
        from backend.services.occupation_retrieval import get_corpus

        return get_corpus()

    def test_the_clusters_are_occupational_domains(self, real) -> None:
        """SOC major group purity against its own base rate.

        Measured 2026-09-16 at k=8 over 941 retrievable rows: mean purity 0.486
        against a 0.114 base rate -- the largest major group is 11% of the
        corpus, so a partition that knew nothing would score about that. The
        bar here is deliberately well below the measurement: this is a "the
        clusters mean something" gate, not a pin on the current artifact.
        """
        assignment = oc.compute_assignment(real, k=oc.CLUSTER_COUNT)
        by_cluster: dict[int, list[str]] = collections.defaultdict(list)
        for code, cluster in assignment.labels.items():
            by_cluster[cluster].append(code[:2])

        purity = sum(
            collections.Counter(majors).most_common(1)[0][1] / len(majors)
            for majors in by_cluster.values()
        ) / len(by_cluster)
        base = (
            collections.Counter(c[:2] for c in assignment.labels).most_common(1)[0][1]
            / assignment.count
        )
        assert purity > 3 * base, (
            "clusters are no more occupational than chance (purity %.3f, base "
            "rate %.3f) -- if they have started clustering on document length or "
            "boilerplate, the fresh_start seed spans nothing" % (purity, base)
        )

    def test_the_clusters_are_not_document_length(self, real) -> None:
        """The confound the brief names, measured as variance explained.

        With the residual buckets IN the fit this is 0.38 and one whole cluster
        is the 52-character rows; with them out it is 0.12-0.13.
        """
        assignment = oc.compute_assignment(real, k=oc.CLUSTER_COUNT)
        lengths = np.array(
            [len(real.titles[real.index_of(code)]) for code in assignment.labels],
            dtype=float,
        )
        labels = np.array(list(assignment.labels.values()))
        within = np.mean(
            [lengths[labels == c].var() for c in sorted(set(labels.tolist()))]
        )
        assert 1 - within / lengths.var() < 0.5

    def test_every_cluster_is_big_enough_to_be_a_region(self, real) -> None:
        sizes = collections.Counter(
            oc.compute_assignment(real, k=oc.CLUSTER_COUNT).labels.values()
        )
        assert len(sizes) == oc.CLUSTER_COUNT
        assert min(sizes.values()) >= 20

    def test_summarise_names_each_region(self, real) -> None:
        rows = oc.summarise(real, oc.compute_assignment(real, k=oc.CLUSTER_COUNT))
        assert len(rows) == oc.CLUSTER_COUNT
        for row in rows:
            assert len(row["titles"]) == 3
            assert row["size"] > 0
