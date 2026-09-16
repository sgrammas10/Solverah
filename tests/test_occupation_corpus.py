"""Tests for backend.services.occupation_corpus (BUILD_PLAN F-1).

O*NET and OpenAI are the only things faked here -- they are external paid
services, which is exactly the exception CLAUDE.md's "prefer real dependencies"
rule carves out.  Everything else (the rate limiter's clock arithmetic, the
checkpoint's file I/O, numpy, the artifact on disk) is the real thing, so these
tests fail if the real artifact would be wrong.

The fakes are hand-written classes rather than MagicMocks so that a signature
change in the client is a test failure rather than a silently-absorbed
``mock.whatever()``.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from backend.services import occupation_corpus as corpus
from backend.services.occupation_corpus import (
    CorpusBuildError,
    DocumentCheckpoint,
    RateLimiter,
    RoleDocument,
    build_corpus,
    compose_role_document,
    enumerate_occupations,
    fetch_role_document,
)
from backend.services.onet_client import Occupation, OnetAPIError, Task


# ---------------------------------------------------------------------------
# Fakes for the two external services
# ---------------------------------------------------------------------------


class FakeOnetClient:
    """Stands in for OnetClient with the same call surface the builder uses."""

    def __init__(
        self,
        families: list[dict] | None = None,
        family_occupations: dict[str, list[Occupation]] | None = None,
        descriptions: dict[str, str] | None = None,
        tasks: dict[str, list[Task]] | None = None,
        hot_technologies: dict[str, list[str]] | None = None,
        fail_codes: set[str] | None = None,
    ) -> None:
        self._families = families if families is not None else [{"code": "15-0000", "title": "Computer"}]
        self._family_occupations = family_occupations or {}
        self._descriptions = descriptions or {}
        self._tasks = tasks or {}
        self._hot_technologies = hot_technologies or {}
        self._fail_codes = fail_codes or set()
        self.calls: list[tuple] = []
        self._lock = threading.Lock()

    def _record(self, *call: object) -> None:
        with self._lock:
            self.calls.append(call)

    def get_job_families(self) -> list[dict]:
        self._record("get_job_families")
        return list(self._families)

    def get_job_family_occupations(
        self, family_code: str, start: int = 1, end: int = 100
    ) -> list[Occupation]:
        self._record("get_job_family_occupations", family_code, start, end)
        everything = self._family_occupations.get(family_code, [])
        return everything[start - 1 : end]

    def get_occupation_description(self, onet_code: str) -> str:
        self._record("get_occupation_description", onet_code)
        if onet_code in self._fail_codes:
            raise OnetAPIError(f"500 for {onet_code}")
        return self._descriptions.get(onet_code, "")

    def get_tasks(self, onet_code: str) -> list[Task]:
        self._record("get_tasks", onet_code)
        return self._tasks.get(onet_code, [])

    def get_hot_technologies(self, onet_code: str) -> list[str]:
        self._record("get_hot_technologies", onet_code)
        return self._hot_technologies.get(onet_code, [])


class _FakeEmbeddingItem:
    def __init__(self, index: int, embedding: list[float]) -> None:
        self.index = index
        self.embedding = embedding


class _FakeEmbeddingResponse:
    def __init__(self, data: list[_FakeEmbeddingItem]) -> None:
        self.data = data


class _FakeEmbeddings:
    def __init__(self, owner: "FakeOpenAIClient") -> None:
        self._owner = owner

    def create(self, model: str, input: list[str]):  # noqa: A002 - matches the SDK
        self._owner.requests.append({"model": model, "input": list(input)})
        data = [
            _FakeEmbeddingItem(index, self._owner.vector_for(text))
            for index, text in enumerate(input)
        ]
        if self._owner.shuffle_response:
            data = list(reversed(data))
        return _FakeEmbeddingResponse(data)


class FakeOpenAIClient:
    """Deterministic embeddings: a unit vector whose direction depends on the text."""

    def __init__(self, dimensions: int = corpus.EMBED_DIM, shuffle_response: bool = False) -> None:
        self.embeddings = _FakeEmbeddings(self)
        self.requests: list[dict] = []
        self.dimensions = dimensions
        self.shuffle_response = shuffle_response

    def vector_for(self, text: str) -> list[float]:
        seed = abs(hash(text)) % (2**32)
        rng = np.random.default_rng(seed)
        return [float(v) for v in rng.normal(size=self.dimensions)]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


DATA_SCIENTISTS = Occupation(code="15-2051.00", title="Data Scientists")
DIETITIANS = Occupation(code="29-1031.00", title="Dietitians and Nutritionists")


def _task(title: str, importance: float, category: str = "Core") -> Task:
    return Task(task_id=title[:4], title=title, importance=importance, category=category)


@pytest.fixture()
def onet() -> FakeOnetClient:
    return FakeOnetClient(
        families=[{"code": "15-0000", "title": "Computer"}, {"code": "29-0000", "title": "Health"}],
        family_occupations={
            "15-0000": [DATA_SCIENTISTS],
            "29-0000": [DIETITIANS],
        },
        descriptions={
            "15-2051.00": "Develop and implement a set of techniques or analytics applications.",
            "29-1031.00": "Plan and conduct food service or nutritional programs.",
        },
        tasks={
            "15-2051.00": [
                _task("Analyze large sets of data using statistical software.", 83),
                _task("Create graphs and charts to convey results.", 71),
            ],
            "29-1031.00": [_task("Assess nutritional needs and diet restrictions.", 88)],
        },
        hot_technologies={
            "15-2051.00": ["Python", "Structured query language SQL"],
            "29-1031.00": ["Microsoft Excel"],
        },
    )


# ---------------------------------------------------------------------------
# compose_role_document -- the load-bearing decision of the whole chunk
# ---------------------------------------------------------------------------


class TestComposeRoleDocument:
    _DOC = RoleDocument(
        code="15-2051.00",
        title="Data Scientists",
        description="Develop and implement a set of techniques or analytics applications.",
        tasks=["Analyze large sets of data.", "Create graphs and charts."],
        hot_technologies=["Python", "Tableau"],
    )

    def test_is_not_the_bare_title(self) -> None:
        """The entire redesign turns on this.  A 2-3 word title is dominated by
        one token, which is what puts "Data Scientists" next to "Political
        Scientists" and forced the SOC allow-list at path_scoring.py:154."""
        text = compose_role_document(self._DOC)

        assert text != "Data Scientists"
        assert len(text) > 10 * len("Data Scientists")

    def test_carries_title_description_tasks_and_technologies(self) -> None:
        text = compose_role_document(self._DOC)

        assert "Data Scientists" in text
        assert "Develop and implement a set of techniques" in text
        assert "Analyze large sets of data." in text
        assert "Create graphs and charts." in text
        assert "Python" in text
        assert "Tableau" in text

    def test_title_leads_the_document(self) -> None:
        assert compose_role_document(self._DOC).startswith("Data Scientists")

    def test_caps_tasks_at_max_tasks(self) -> None:
        doc = RoleDocument(
            code="x",
            title="T",
            description="d",
            tasks=[f"Task number {i}." for i in range(40)],
        )
        text = compose_role_document(doc)

        assert f"Task number {corpus.MAX_TASKS - 1}." in text
        assert f"Task number {corpus.MAX_TASKS}." not in text

    def test_caps_hot_technologies(self) -> None:
        doc = RoleDocument(
            code="x",
            title="T",
            description="d",
            hot_technologies=[f"Tool{i}" for i in range(40)],
        )
        text = compose_role_document(doc)

        assert f"Tool{corpus.MAX_HOT_TECHNOLOGIES - 1}" in text
        assert f"Tool{corpus.MAX_HOT_TECHNOLOGIES}," not in text

    def test_omits_empty_sections_entirely(self) -> None:
        """74 of the catalog's 1,016 occupations have no tasks, and many of
        those no hot technologies either; an empty "Tasks:" label would be a
        constant carrying no information, which is §1.1's complaint in
        miniature."""
        doc = RoleDocument(
            code="55-1011.00",
            title="Air Crew Officers",
            description="Perform and direct in-flight duties.",
        )
        text = compose_role_document(doc)

        assert "Tasks:" not in text
        assert "Technologies:" not in text
        assert text == "Air Crew Officers\n\nPerform and direct in-flight duties."

    def test_title_only_occupation_still_composes(self) -> None:
        doc = RoleDocument(code="x", title="Widget Makers", description="")
        assert compose_role_document(doc) == "Widget Makers"

    def test_truncates_a_pathological_document(self) -> None:
        doc = RoleDocument(
            code="x", title="T", description="word " * 20_000, tasks=["tail task."]
        )
        assert len(compose_role_document(doc)) == corpus.MAX_DOCUMENT_CHARS


class TestRoleDocumentSerialisation:
    def test_round_trips_through_json(self) -> None:
        doc = RoleDocument(
            code="15-2051.00",
            title="Data Scientists",
            description="d",
            tasks=["t1", "t2"],
            hot_technologies=["Python"],
        )
        assert RoleDocument.from_json(json.loads(json.dumps(doc.to_json()))) == doc

    def test_tolerates_missing_keys(self) -> None:
        doc = RoleDocument.from_json({"code": "x"})
        assert doc == RoleDocument(code="x", title="", description="", tasks=[], hot_technologies=[])


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    def test_rejects_a_non_positive_rate(self) -> None:
        with pytest.raises(ValueError):
            RateLimiter(0)

    def test_spaces_calls_by_the_interval(self) -> None:
        limiter = RateLimiter(50.0)  # 20 ms apart
        started = time.monotonic()
        for _ in range(5):
            limiter.acquire()
        elapsed = time.monotonic() - started

        # 5 slots, the first free: at least 4 intervals must have been waited.
        assert elapsed >= 4 * 0.020 * 0.9

    def test_counts_every_slot_handed_out(self) -> None:
        limiter = RateLimiter(1000.0)
        for _ in range(7):
            limiter.acquire()

        assert limiter.count == 7

    def test_aggregate_rate_holds_across_threads(self) -> None:
        """The point of the shared limiter: raising workers must change latency
        hiding, never the request rate O*NET sees."""
        limiter = RateLimiter(100.0)  # 10 ms apart
        started = time.monotonic()

        def burst() -> None:
            for _ in range(5):
                limiter.acquire()

        threads = [threading.Thread(target=burst) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.monotonic() - started

        assert limiter.count == 20
        assert elapsed >= 19 * 0.010 * 0.9


# ---------------------------------------------------------------------------
# enumerate_occupations
# ---------------------------------------------------------------------------


class TestEnumerateOccupations:
    def test_returns_every_occupation_across_families(self, onet: FakeOnetClient) -> None:
        result = enumerate_occupations(onet)

        assert [o.code for o in result] == ["15-2051.00", "29-1031.00"]

    def test_sorted_by_code_not_by_family_order(self) -> None:
        """Row order must be a property of the catalog, so two builds of the
        same catalog put the same occupation in the same row."""
        client = FakeOnetClient(
            families=[{"code": "53-0000", "title": "Transport"}, {"code": "11-0000", "title": "Mgmt"}],
            family_occupations={
                "53-0000": [Occupation(code="53-3032.00", title="Truck Drivers")],
                "11-0000": [Occupation(code="11-1011.00", title="Chief Executives")],
            },
        )
        assert [o.code for o in enumerate_occupations(client)] == ["11-1011.00", "53-3032.00"]

    def test_pages_a_family_larger_than_one_page(self) -> None:
        """Regression: 51-0000 (Production) holds 114 occupations against a
        100-entry page, so a single unpaged request silently drops 14."""
        big = [Occupation(code=f"51-{i:04d}.00", title=f"Maker {i}") for i in range(114)]
        client = FakeOnetClient(
            families=[{"code": "51-0000", "title": "Production"}],
            family_occupations={"51-0000": big},
        )

        result = enumerate_occupations(client)

        assert len(result) == 114
        page_calls = [c for c in client.calls if c[0] == "get_job_family_occupations"]
        assert [(c[2], c[3]) for c in page_calls] == [(1, 100), (101, 200)]

    def test_stops_paging_on_a_short_page(self, onet: FakeOnetClient) -> None:
        enumerate_occupations(onet)
        page_calls = [c for c in onet.calls if c[0] == "get_job_family_occupations"]

        assert len(page_calls) == 2  # one per family, no speculative second page

    def test_deduplicates_codes_seen_in_two_families(self) -> None:
        shared = Occupation(code="15-2051.00", title="Data Scientists")
        client = FakeOnetClient(
            families=[{"code": "15-0000", "title": "A"}, {"code": "19-0000", "title": "B"}],
            family_occupations={"15-0000": [shared], "19-0000": [shared]},
        )
        assert len(enumerate_occupations(client)) == 1

    def test_skips_the_family_entry_with_no_code(self) -> None:
        client = FakeOnetClient(
            families=[{"title": "All Job Families"}, {"code": "15-0000", "title": "Computer"}],
            family_occupations={"15-0000": [DATA_SCIENTISTS]},
        )
        result = enumerate_occupations(client)

        assert [o.code for o in result] == ["15-2051.00"]
        assert not any(c[0] == "get_job_family_occupations" and c[1] == "" for c in client.calls)

    def test_raises_when_the_catalog_is_empty(self) -> None:
        with pytest.raises(CorpusBuildError, match="get_job_families"):
            enumerate_occupations(FakeOnetClient(families=[]))

    def test_every_request_passes_through_the_limiter(self, onet: FakeOnetClient) -> None:
        limiter = RateLimiter(10_000.0)
        enumerate_occupations(onet, limiter)

        assert limiter.count == len(onet.calls)


# ---------------------------------------------------------------------------
# fetch_role_document
# ---------------------------------------------------------------------------


class TestFetchRoleDocument:
    def test_collects_description_tasks_and_technologies(self, onet: FakeOnetClient) -> None:
        doc = fetch_role_document(onet, DATA_SCIENTISTS)

        assert doc.code == "15-2051.00"
        assert doc.title == "Data Scientists"
        assert doc.description.startswith("Develop and implement")
        assert doc.tasks == [
            "Analyze large sets of data using statistical software.",
            "Create graphs and charts to convey results.",
        ]
        assert doc.hot_technologies == ["Python", "Structured query language SQL"]

    def test_costs_exactly_three_requests(self, onet: FakeOnetClient) -> None:
        limiter = RateLimiter(10_000.0)
        fetch_role_document(onet, DATA_SCIENTISTS, limiter)

        assert limiter.count == 3
        assert len(onet.calls) == 3

    def test_an_occupation_with_no_data_still_yields_a_document(self, onet: FakeOnetClient) -> None:
        doc = fetch_role_document(onet, Occupation(code="55-1011.00", title="Air Crew Officers"))

        assert doc == RoleDocument(
            code="55-1011.00", title="Air Crew Officers", description="", tasks=[], hot_technologies=[]
        )

    def test_propagates_an_api_error(self, onet: FakeOnetClient) -> None:
        onet._fail_codes = {"15-2051.00"}
        with pytest.raises(OnetAPIError):
            fetch_role_document(onet, DATA_SCIENTISTS)


# ---------------------------------------------------------------------------
# DocumentCheckpoint
# ---------------------------------------------------------------------------


class TestDocumentCheckpoint:
    def test_missing_file_loads_as_empty(self, tmp_path: Path) -> None:
        assert DocumentCheckpoint(tmp_path / "nope.jsonl").load() == {}

    def test_appended_documents_round_trip(self, tmp_path: Path) -> None:
        checkpoint = DocumentCheckpoint(tmp_path / "c.jsonl")
        doc = RoleDocument(code="15-2051.00", title="Data Scientists", description="d", tasks=["t"])
        checkpoint.append(doc)

        assert DocumentCheckpoint(tmp_path / "c.jsonl").load() == {"15-2051.00": doc}

    def test_tolerates_a_truncated_final_line(self, tmp_path: Path) -> None:
        """The one record a kill can corrupt.  Refusing to resume over it would
        mean re-spending every request the checkpoint exists to save."""
        path = tmp_path / "c.jsonl"
        checkpoint = DocumentCheckpoint(path)
        checkpoint.append(RoleDocument(code="15-2051.00", title="Data Scientists", description="d"))
        with path.open("a", encoding="utf-8") as fh:
            fh.write('{"code": "29-1031.00", "title": "Diet')

        loaded = DocumentCheckpoint(path).load()

        assert list(loaded) == ["15-2051.00"]

    def test_concurrent_appends_do_not_interleave(self, tmp_path: Path) -> None:
        checkpoint = DocumentCheckpoint(tmp_path / "c.jsonl")

        def write(index: int) -> None:
            checkpoint.append(RoleDocument(code=f"11-{index:04d}.00", title=f"T{index}", description="d" * 200))

        threads = [threading.Thread(target=write, args=(i,)) for i in range(25)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(checkpoint.load()) == 25


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------


class TestEmbedding:
    def test_one_batch_when_everything_fits(self) -> None:
        client = FakeOpenAIClient()
        matrix, calls = corpus.embed_documents(["a", "b", "c"], client)

        assert calls == 1
        assert matrix.shape == (3, corpus.EMBED_DIM)
        assert matrix.dtype == np.float32

    def test_splits_on_the_character_budget(self) -> None:
        """1,016 real documents are ~400k tokens, over OpenAI's per-request
        token cap, so the input-count cap alone is not enough."""
        big = "x" * (corpus.EMBED_MAX_BATCH_CHARS // 2 + 1)
        client = FakeOpenAIClient()
        _matrix, calls = corpus.embed_documents([big, big, big], client)

        assert calls == 3
        assert [len(r["input"]) for r in client.requests] == [1, 1, 1]

    def test_a_single_oversized_document_still_goes_out(self) -> None:
        client = FakeOpenAIClient()
        _matrix, calls = corpus.embed_documents(["y" * (corpus.EMBED_MAX_BATCH_CHARS * 3)], client)

        assert calls == 1

    def test_rows_follow_item_index_not_response_order(self) -> None:
        """The API documents that responses may be reordered, and a misaligned
        corpus is invisible until the recommendations are nonsense."""
        ordered = FakeOpenAIClient()
        shuffled = FakeOpenAIClient(shuffle_response=True)
        texts = ["alpha", "beta", "gamma"]

        assert np.array_equal(
            corpus.embed_documents(texts, ordered)[0],
            corpus.embed_documents(texts, shuffled)[0],
        )

    def test_rejects_a_wrong_dimensionality(self) -> None:
        with pytest.raises(CorpusBuildError, match="dimensions"):
            corpus.embed_documents(["a"], FakeOpenAIClient(dimensions=768))

    def test_raises_when_a_row_comes_back_unfilled(self) -> None:
        class Gappy(FakeOpenAIClient):
            def vector_for(self, text: str) -> list[float]:
                return super().vector_for(text)

        client = Gappy()
        client.embeddings.create = lambda model, input: _FakeEmbeddingResponse(  # type: ignore[assignment]
            [_FakeEmbeddingItem(0, client.vector_for(input[0]))]
        )
        with pytest.raises(CorpusBuildError, match="without an embedding"):
            corpus.embed_documents(["a", "b"], client)

    def test_api_failure_is_not_swallowed(self) -> None:
        """path_scoring._batch_embed silently degrades one response; a corpus
        build that did the same would write a permanently wrong artifact."""
        client = FakeOpenAIClient()

        def boom(model, input):  # noqa: A002
            raise RuntimeError("provider down")

        client.embeddings.create = boom  # type: ignore[assignment]
        with pytest.raises(RuntimeError, match="provider down"):
            corpus.embed_documents(["a"], client)


# ---------------------------------------------------------------------------
# build_corpus
# ---------------------------------------------------------------------------


def _build(tmp_path: Path, onet: FakeOnetClient, **kwargs):
    defaults = dict(
        out_dir=tmp_path,
        onet_client=onet,
        openai_client=FakeOpenAIClient(),
        version="test",
        requests_per_second=5.0,
        workers=2,
    )
    defaults.update(kwargs)
    return build_corpus(**defaults)  # type: ignore[arg-type]


class TestBuildCorpus:
    def test_writes_a_matrix_and_a_sidecar(self, tmp_path: Path, onet: FakeOnetClient) -> None:
        build = _build(tmp_path, onet)

        assert build.matrix_path == tmp_path / "onet_corpus_test.npy"
        assert build.sidecar_path == tmp_path / "onet_corpus_test.json"
        assert build.matrix_path.exists()
        assert build.sidecar_path.exists()
        assert build.count == 2

    def test_matrix_shape_and_dtype(self, tmp_path: Path, onet: FakeOnetClient) -> None:
        build = _build(tmp_path, onet)
        matrix = np.load(build.matrix_path)

        assert matrix.shape == (2, corpus.EMBED_DIM)
        assert matrix.dtype == np.float32

    def test_rows_are_unit_normalised(self, tmp_path: Path, onet: FakeOnetClient) -> None:
        """So a consumer's cosine is exactly ``matrix @ unit_query``."""
        matrix = np.load(_build(tmp_path, onet).matrix_path)

        assert np.allclose(np.linalg.norm(matrix, axis=1), 1.0, atol=1e-5)

    def test_sidecar_maps_row_index_to_onet_code(self, tmp_path: Path, onet: FakeOnetClient) -> None:
        build = _build(tmp_path, onet)
        sidecar = json.loads(build.sidecar_path.read_text(encoding="utf-8"))

        assert sidecar["codes"] == ["15-2051.00", "29-1031.00"]
        assert sidecar["titles"] == ["Data Scientists", "Dietitians and Nutritionists"]
        assert len(sidecar["codes"]) == sidecar["count"] == build.count

    def test_sidecar_records_the_model_and_dimensions(self, tmp_path: Path, onet: FakeOnetClient) -> None:
        """A corpus built with one model is meaningless against a query embedded
        with another, and a silent swap still returns plausible cosines."""
        sidecar = json.loads(_build(tmp_path, onet).sidecar_path.read_text(encoding="utf-8"))

        assert sidecar["model"] == "text-embedding-3-small"
        assert sidecar["dimensions"] == 1536
        assert sidecar["dtype"] == "float32"
        assert sidecar["normalised"] is True
        assert sidecar["matrix_filename"] == "onet_corpus_test.npy"

    def test_embeds_role_documents_not_titles(self, tmp_path: Path, onet: FakeOnetClient) -> None:
        """The chunk's whole thesis, asserted against what actually goes over
        the wire rather than against compose_role_document in isolation."""
        openai_client = FakeOpenAIClient()
        _build(tmp_path, onet, openai_client=openai_client)

        sent = openai_client.requests[0]["input"]
        assert len(sent) == 2
        assert all(text not in ("Data Scientists", "Dietitians and Nutritionists") for text in sent)
        assert "Analyze large sets of data using statistical software." in sent[0]
        assert "Python" in sent[0]

    def test_no_temporary_files_are_left_behind(self, tmp_path: Path, onet: FakeOnetClient) -> None:
        """np.save appends ".npy" to a path that lacks it, which turned the
        atomic-write scratch name into a file the rename could not find."""
        _build(tmp_path, onet)

        assert not list(tmp_path.glob("*.tmp"))
        assert not list(tmp_path.glob("*.tmp.npy"))

    def test_limit_truncates_the_catalog(self, tmp_path: Path, onet: FakeOnetClient) -> None:
        build = _build(tmp_path, onet, limit=1)

        assert build.count == 1
        assert json.loads(build.sidecar_path.read_text(encoding="utf-8"))["codes"] == ["15-2051.00"]

    def test_writes_a_checkpoint_of_every_document(self, tmp_path: Path, onet: FakeOnetClient) -> None:
        build = _build(tmp_path, onet)
        loaded = DocumentCheckpoint(build.checkpoint_path).load()

        assert set(loaded) == {"15-2051.00", "29-1031.00"}
        assert loaded["15-2051.00"].hot_technologies == ["Python", "Structured query language SQL"]

    def test_resume_skips_fetches_already_checkpointed(self, tmp_path: Path, onet: FakeOnetClient) -> None:
        first = _build(tmp_path, onet)
        assert first.resumed_documents == 0

        second_client = FakeOnetClient(
            families=onet._families, family_occupations=onet._family_occupations
        )
        second = _build(tmp_path, second_client)

        assert second.resumed_documents == 2
        assert second.count == 2
        assert not any(c[0] == "get_occupation_description" for c in second_client.calls)

    def test_no_resume_refetches(self, tmp_path: Path, onet: FakeOnetClient) -> None:
        _build(tmp_path, onet)
        again = FakeOnetClient(
            families=onet._families,
            family_occupations=onet._family_occupations,
            descriptions=onet._descriptions,
        )
        build = _build(tmp_path, again, resume=False)

        assert build.resumed_documents == 0
        assert any(c[0] == "get_occupation_description" for c in again.calls)

    def test_counts_its_onet_and_embedding_spend(self, tmp_path: Path, onet: FakeOnetClient) -> None:
        build = _build(tmp_path, onet)

        # 1 families + 2 family pages + 3 requests x 2 occupations
        assert build.onet_requests == 9
        assert build.embed_requests == 1
        assert build.estimated_tokens > 0

    def test_refuses_a_rate_above_onets_documented_threshold(
        self, tmp_path: Path, onet: FakeOnetClient
    ) -> None:
        with pytest.raises(CorpusBuildError, match="exceeds"):
            _build(tmp_path, onet, requests_per_second=25.0)
        assert not list(tmp_path.glob("*.npy"))

    def test_refuses_zero_workers(self, tmp_path: Path, onet: FakeOnetClient) -> None:
        with pytest.raises(CorpusBuildError, match="workers"):
            _build(tmp_path, onet, workers=0)

    def test_a_tolerable_number_of_failures_is_recorded_not_fatal(self, tmp_path: Path) -> None:
        occupations = [Occupation(code=f"15-{i:04d}.00", title=f"Role {i}") for i in range(100)]
        client = FakeOnetClient(
            families=[{"code": "15-0000", "title": "Computer"}],
            family_occupations={"15-0000": occupations},
            descriptions={o.code: f"Description for {o.title}." for o in occupations},
            fail_codes={"15-0007.00"},
        )
        build = _build(tmp_path, client)

        assert build.count == 99
        assert [code for code, _ in build.failures] == ["15-0007.00"]
        assert "15-0007.00" not in json.loads(
            build.sidecar_path.read_text(encoding="utf-8")
        )["codes"]

    def test_a_network_error_is_recorded_not_fatal(self, tmp_path: Path) -> None:
        """onet_client._get only converts HTTPError, so a connection reset or a
        read timeout arrives here as a raw requests exception.  During a
        13-minute live run one of those must not end the build."""
        import requests

        occupations = [Occupation(code=f"15-{i:04d}.00", title=f"Role {i}") for i in range(50)]
        client = FakeOnetClient(
            families=[{"code": "15-0000", "title": "Computer"}],
            family_occupations={"15-0000": occupations},
        )
        original = client.get_occupation_description

        def flaky(onet_code: str) -> str:
            if onet_code == "15-0003.00":
                raise requests.ConnectionError("connection reset by peer")
            return original(onet_code)

        client.get_occupation_description = flaky  # type: ignore[method-assign]
        build = _build(tmp_path, client)

        assert build.count == 49
        assert [code for code, _ in build.failures] == ["15-0003.00"]

    def test_refuses_to_write_a_corpus_with_a_big_hole_in_it(self, tmp_path: Path) -> None:
        """An artifact missing 300 occupations would be loaded and trusted for a
        quarter, surfacing only as bad recommendations."""
        occupations = [Occupation(code=f"15-{i:04d}.00", title=f"Role {i}") for i in range(20)]
        client = FakeOnetClient(
            families=[{"code": "15-0000", "title": "Computer"}],
            family_occupations={"15-0000": occupations},
            fail_codes={o.code for o in occupations[:5]},
        )
        with pytest.raises(CorpusBuildError, match="refusing to write"):
            _build(tmp_path, client)

        assert not list(tmp_path.glob("*.npy"))

    def test_raises_when_nothing_could_be_fetched(self, tmp_path: Path) -> None:
        client = FakeOnetClient(
            families=[{"code": "15-0000", "title": "Computer"}],
            family_occupations={"15-0000": [DATA_SCIENTISTS]},
            fail_codes={"15-2051.00"},
        )
        with pytest.raises(CorpusBuildError):
            _build(tmp_path, client)

    def test_creates_the_output_directory(self, tmp_path: Path, onet: FakeOnetClient) -> None:
        target = tmp_path / "nested" / "corpus"
        build = _build(target, onet)

        assert build.matrix_path.parent == target
        assert build.matrix_path.exists()

    def test_summary_is_json_serialisable(self, tmp_path: Path, onet: FakeOnetClient) -> None:
        """The CLI echoes it as one JSON line for cron log scraping."""
        summary = _build(tmp_path, onet).summary()

        assert json.loads(json.dumps(summary))["occupations"] == 2
        assert summary["event"] == "corpus_build"

    def test_default_version_is_a_utc_date_stamp(self) -> None:
        stamp = corpus.default_version()

        assert len(stamp) == 8 and stamp.isdigit()

    def test_version_appears_in_both_filenames(self, tmp_path: Path, onet: FakeOnetClient) -> None:
        """Versioned by filename, so a rebuild never overwrites the artifact in
        service."""
        build = _build(tmp_path, onet, version="20260916")

        assert build.matrix_path.name == "onet_corpus_20260916.npy"
        assert build.sidecar_path.name == "onet_corpus_20260916.json"


# ---------------------------------------------------------------------------
# flask corpus build
# ---------------------------------------------------------------------------


@pytest.fixture()
def ctx(client):
    """An application context on the app the factory actually builds.

    Same shape as tests/test_ops_cli.py's: a cron box with nothing but the repo
    and env vars boots through ``create_app()``, so the command must be reachable
    there and not merely importable.
    """
    from app import app

    with app.app_context():
        yield app


def _text(result) -> str:
    """Everything the command said, on either stream.

    Click 8.2 stopped merging stderr into ``output``, and this command writes
    progress and every ClickException to stderr -- asserting on ``output`` alone
    would pass by looking at nothing.
    """
    parts = [result.output or ""]
    try:
        parts.append(result.stderr or "")
    except (ValueError, AttributeError):  # older click, or nothing captured
        pass
    if result.exception is not None:
        parts.append(str(result.exception))
    return "\n".join(parts)


class TestCorpusBuildCommand:
    def test_registered_on_the_app_cli(self, ctx) -> None:
        group = ctx.cli.get_command(None, "corpus")

        assert group is not None
        assert "build" in group.list_commands(None)

    def test_refuses_to_run_without_an_output_directory(
        self, ctx, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """There is deliberately no default: the artifact is ~6 MB of binary and
        must not land in the repo tree, which the guard tests walk."""
        monkeypatch.delenv("SOLVERAH_CORPUS_DIR", raising=False)
        result = ctx.test_cli_runner().invoke(args=["corpus", "build"])

        assert result.exit_code != 0
        assert "SOLVERAH_CORPUS_DIR" in _text(result)

    def test_builds_and_echoes_a_json_summary(
        self, ctx, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, onet: FakeOnetClient
    ) -> None:
        monkeypatch.setattr("backend.services.onet_client.OnetClient", lambda *a, **k: onet)
        monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: FakeOpenAIClient())

        result = ctx.test_cli_runner().invoke(
            args=[
                "corpus", "build",
                "--out-dir", str(tmp_path),
                "--version", "cli",
                "--rate", "5",
            ]
        )

        assert result.exit_code == 0, _text(result)
        summary = json.loads(result.output.strip().splitlines()[-1])
        assert summary["event"] == "corpus_build"
        assert summary["occupations"] == 2
        assert summary["model"] == "text-embedding-3-small"
        assert (tmp_path / "onet_corpus_cli.npy").exists()
        assert (tmp_path / "onet_corpus_cli.json").exists()

    def test_a_build_error_exits_non_zero(
        self, ctx, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, onet: FakeOnetClient
    ) -> None:
        """Unlike `outbox sweep`, a partial pass is not a success here: an
        artifact with a hole in it gets loaded and trusted for a quarter."""
        monkeypatch.setattr("backend.services.onet_client.OnetClient", lambda *a, **k: onet)
        monkeypatch.setattr("solverah.infra.llm.get_openai_client", lambda: FakeOpenAIClient())

        result = ctx.test_cli_runner().invoke(
            args=["corpus", "build", "--out-dir", str(tmp_path), "--rate", "99"]
        )

        assert result.exit_code != 0
        assert "exceeds" in _text(result)
        assert not list(tmp_path.glob("*.npy"))

    def test_missing_onet_key_is_a_clean_refusal_not_a_traceback(
        self, ctx, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ONET_API_KEY", raising=False)
        result = ctx.test_cli_runner().invoke(
            args=["corpus", "build", "--out-dir", str(tmp_path)]
        )

        assert result.exit_code != 0
        assert "ONET_API_KEY" in _text(result)
