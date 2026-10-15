"""The CompanyLens pipeline (six-trait build, C5; C5b review fixes) end to end, against
the real test database with FAKES AT THE CLIENT BOUNDARY and nothing else.

No test here reaches the network or needs a provider key: `solverah.infra.llm`'s two
accessors are monkeypatched to return fakes (the substitution seam that module exists
for), so the pipeline, the store, the aggregation and the job dispatch all run for
real. The research fake speaks the SDK's own `BetaMessage` shape, as
tests/test_llm_research_client.py does; the scorer fake answers whatever structured
schema it is handed, which is how the posting-extraction and scoring calls are told
apart.

The two internal columns (the scored text and the run card) are never named in this
file: the GAP-14 guard scans test files too. Where a test must assert on what was
STORED in one, it reads the model's one deferred column reflectively (`_internal`);
everything else is proven through the scorer fake's recorded prompt or the views.
"""
from __future__ import annotations

import ast
import copy
import datetime
import hashlib
import io
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from anthropic.types.beta import BetaMessage

import company_evidence_store as store
from solverah.infra import llm
from solverah.infra.llm import LLMProviderUnavailable
from solverah.infra.llm.research import ResearchProviderError, ResearchUsage, TokenUsage
from solverah.services.company_research import research, score_items, service, textcheck
from solverah.services.company_research.constants import (
    AGGREGATION_VERSION,
    RESEARCH_MAX_TOKENS,
)
from solverah.services.company_research.prompts import (
    POSTING_EXTRACT_PROMPT_VERSION,
    RESEARCH_PROMPT_VERSION,
    RUBRIC_TEXT_SHA256,
    SCORING_PROMPT_VERSION,
    build_research_prompt,
    build_scoring_instruction,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DIMENSIONS = ("autonomy", "pace", "collaboration", "feedback", "innovation", "decision")

CAREERS_URL = "https://acme.example/careers"
REVIEWS_URL = "https://reviews.example/acme"
POSTING_URL = "https://jobs.example/acme/123"
NEWS_URL = "https://news.example/acme-reorg"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class _FakeStream:
    def __init__(self, message):
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._message


class FakeResearchClient:
    """Stands in for ``anthropic.Anthropic``. Each response is a BetaMessage or an
    exception to raise from the stream."""

    def __init__(self, *responses):
        self._responses = list(responses)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **request):
        self.requests.append(copy.deepcopy(request))
        item = self._responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return _FakeStream(item)


class NeverCalledResearchClient(FakeResearchClient):
    def _stream(self, **request):  # pragma: no cover - the assertion is the point
        raise AssertionError("the research client must never be called with user content")


class FakeScorerClient:
    """Stands in for the OpenAI client. Answers a posting-extraction schema with
    *extraction_items* and a scoring schema with *scores* applied to the items in id
    order (each a {dimension: band} dict; dimensions not named abstain)."""

    def __init__(self, *, scores=(), extraction_items=()):
        self.scores = list(scores)
        self.extraction_items = list(extraction_items)
        self.requests = []
        self._next_item = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        schema = kwargs["response_format"]["json_schema"]["schema"]
        props = schema["properties"]
        if "items" in props and props["items"].get("type") == "array":
            answer = {"items": list(self.extraction_items)}
        else:
            answer = {}
            keys = sorted(props, key=lambda k: int(k.split("_")[1]))
            for key in keys:
                given = self.scores[self._next_item] if self._next_item < len(self.scores) else {}
                self._next_item += 1
                answer[key] = {
                    dim: ({"score": given[dim], "confidence": 0.6} if dim in given
                          else {"score": None, "confidence": None})
                    for dim in DIMENSIONS
                }
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(answer)))],
            usage=SimpleNamespace(prompt_tokens=1200, completion_tokens=300, total_tokens=1500),
        )


def _usage(searches=3):
    return {"input_tokens": 5000, "output_tokens": 800,
            "server_tool_use": {"web_search_requests": searches, "web_fetch_requests": 2}}


def _message(content, *, stop_reason="end_turn", usage=None):
    return BetaMessage.model_validate({
        "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": content, "stop_reason": stop_reason, "stop_sequence": None,
        "stop_details": None, "usage": usage or _usage(),
    })


SEARCH_USE = {"type": "server_tool_use", "id": "srvtoolu_s1", "name": "web_search",
              "input": {"query": "Acme Corp careers"}}
FETCH_USE = {"type": "server_tool_use", "id": "srvtoolu_f1", "name": "web_fetch",
             "input": {"url": CAREERS_URL}}


def _search_result(urls):
    return {
        "type": "web_search_tool_result", "tool_use_id": "srvtoolu_s1",
        "content": [
            {"type": "web_search_result", "url": url, "title": "Page", "encrypted_content": "ENC",
             "page_age": None}
            for url in urls
        ],
    }


def _fetch_result(url, title, text="page text"):
    return {
        "type": "web_fetch_tool_result", "tool_use_id": "srvtoolu_f1",
        "content": {
            "type": "web_fetch_result", "url": url, "retrieved_at": "2026-10-13T09:00:00Z",
            "content": {"type": "document", "title": title,
                        "source": {"type": "text", "media_type": "text/plain", "data": text},
                        "citations": {"enabled": True}},
        },
    }


def _cited_line(text, cited_text, url):
    return {"type": "text", "text": text + "\n", "citations": [
        {"type": "web_search_result_location", "url": url, "title": "Page",
         "encrypted_index": "EI", "cited_text": cited_text},
    ]}


def _char_cited_line(text, cited_text, title):
    return {"type": "text", "text": text + "\n", "citations": [
        {"type": "char_location", "document_index": 0, "document_title": title,
         "start_char_index": 0, "end_char_index": len(cited_text), "cited_text": cited_text},
    ]}


#: The evidence the research fake "found": (source_type, scope, label, url, date,
#: access, excerpt, paraphrase, cited_text, speaker). cited_text None = the API never
#: saw it quoted. Under the coverage rule a kept item is cited WHOLE.
EXCERPT_A = "We ship to production every single day and expect engineers to own their roadmap end to end."
EXCERPT_B = "The pace here is relentless; deadlines move up, never back, and weekends happen."
EXCERPT_C = "Managers set the priorities each quarter and the team executes against that plan with weekly check-ins."
EXCERPT_D = "This company really values collaborative work across teams and shared goals."
EXCERPT_E = "Nobody at this company has ever heard of a calm week."

FOUND_ITEMS = [
    ("careers_page", "company", None, CAREERS_URL, None, True, EXCERPT_A,
     "Engineers release daily and are expected to take full responsibility for their area.",
     EXCERPT_A, "company careers page"),
    ("employee_review", "role", "Software Engineer", REVIEWS_URL, "2026-05-02", False, EXCERPT_B,
     "A reviewer describes constant urgency, with deadlines that only tighten and weekend work.",
     EXCERPT_B, "employee review, Software Engineer"),
    ("job_posting", "role", "Operations Analyst", POSTING_URL, "2026-09-20", False, EXCERPT_C,
     "Quarterly priorities come from management; the team carries them out with a weekly cadence.",
     EXCERPT_C, "job posting"),
    # paraphrase copies a 12-word run from the excerpt -> paraphrase gate drops it
    ("employee_review", "role", "Account Manager", REVIEWS_URL, "2026-03-11", False, EXCERPT_D,
     "Reviewers say this company really values collaborative work across teams and shared goals.",
     EXCERPT_D, "employee review, Account Manager"),
    # never cited by the API -> its URL was only listed, dropped
    ("employee_review", "role", "Recruiter", REVIEWS_URL, "2026-01-05", False, EXCERPT_E,
     "A reviewer says calm weeks do not exist.", None, "employee review, Recruiter"),
]


def _record_json(items=FOUND_ITEMS, headcount=450):
    return {
        "company": {"official_domain": "https://www.acme.example/", "headcount": headcount,
                    "headcount_as_of": "2026-09-01", "headcount_source": "careers page"},
        "scope_declaration": "The employee reviews come from engineering and sales roles.",
        "items": [
            {"source_type": st, "scope": sc, "scope_label": lb, "url": url, "date": date or "2026-10-13",
             "date_is_access_date": access, "speaker": speaker, "excerpt": ex, "paraphrase": para}
            for st, sc, lb, url, date, access, ex, para, _cited, speaker in items
        ],
    }


def _research_message(record=None, items=FOUND_ITEMS, usage=None):
    content = [SEARCH_USE, _search_result([CAREERS_URL, REVIEWS_URL, POSTING_URL])]
    for st, sc, lb, url, date, access, excerpt, para, cited, speaker in items:
        if cited:
            content.append(_cited_line('"%s"' % excerpt, cited, url))
    content.append({"type": "text", "text": "```json\n%s\n```" % json.dumps(record or _record_json())})
    return _message(content, usage=usage)


def _internal(row):
    """The value of the row's one deferred column, found reflectively (see the module
    docstring for why this file never spells either column's name)."""
    from sqlalchemy import inspect

    (attr,) = [a for a in inspect(type(row)).column_attrs if a.deferred]
    return getattr(row, attr.key)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def ctx(client):
    from app import app
    from model import db

    with app.app_context():
        yield db


@pytest.fixture()
def no_keys(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _research_switch_on(monkeypatch):
    """The public switch is OFF by default (C5c); every test here that starts a run
    is exercising the enabled path unless it clears the variable itself."""
    monkeypatch.setenv(service.RESEARCH_ENABLED_VAR, "1")
    monkeypatch.delenv(research.BLOCKED_DOMAINS_VAR, raising=False)


def _install(monkeypatch, research_client, scorer_client):
    monkeypatch.setattr(llm, "get_research_client", lambda: research_client)
    monkeypatch.setattr(llm, "get_scorer_client", lambda: scorer_client)


def _mk_user(db, user_id=7):
    from model import User

    db.session.add(User(id=user_id, email="u%d@example.test" % user_id, password_hash="x"))
    db.session.commit()
    return user_id


# ---------------------------------------------------------------------------
# Research run, end to end
# ---------------------------------------------------------------------------

def test_research_job_writes_verified_items_scores_and_six_records(ctx, no_keys, monkeypatch):
    db = ctx
    from model import (
        Company, CompanyConfounderValue, CompanyEvidenceItem, CompanyResearchRun,
        EvidenceItemScore, ScorerRun,
    )

    research_fake = FakeResearchClient(_research_message())
    # item order by id == FOUND_ITEMS order of the kept ones: A, B, C
    scorer_fake = FakeScorerClient(scores=[
        {"pace": 0.9, "autonomy": 0.7}, {"pace": 0.9}, {"pace": 0.7, "autonomy": 0.3},
    ])
    _install(monkeypatch, research_fake, scorer_fake)

    queued = service.request_research(db, company_name="Acme Corp", trigger="on_demand")
    assert queued.status == "queued"  # the view as queued, even though eager ran it inline
    assert queued.prompt_version == RESEARCH_PROMPT_VERSION
    assert queued.provider == "anthropic"

    run = store.latest_research_run(db, queued.company_id)
    assert run.id == queued.id and run.status == "done", run.error
    assert run.cost_usd == Decimal("0.066")  # 3 searches ($0.03) + 5000 in ($0.02) + 800 out ($0.016), Opus 5.5 list price

    # The research client saw the company name and nothing else of substance, and the
    # turn was given the larger output ceiling (review F3b).
    (request,) = research_fake.requests
    assert "Acme Corp" in request["messages"][0]["content"]
    assert request["system"]
    assert request["max_tokens"] == RESEARCH_MAX_TOKENS == 64_000

    # Two of five were dropped: one whose URL was only listed, one failing the
    # paraphrase gate. The items are checked by paraphrase (the only text a reader may
    # use); that the verbatim text was stored and read back by the scorer is proven
    # below through the scorer's recorded prompt.
    items = (
        db.session.query(CompanyEvidenceItem)
        .filter(CompanyEvidenceItem.research_run_id == run.id)
        .order_by(CompanyEvidenceItem.id).all()
    )
    assert [i.paraphrase for i in items] == [FOUND_ITEMS[k][7] for k in (0, 1, 2)]
    assert items[0].published_at is None  # access-dated: no publication date claimed
    assert items[1].published_at == datetime.date(2026, 5, 2)
    assert items[2].published_at == datetime.date(2026, 9, 20)  # cited, not fetched: the model's date
    assert items[1].scope == "role" and items[1].scope_label == "Software Engineer"
    assert items[0].scope == "company" and items[0].scope_label is None
    assert [i.speaker for i in items] == [FOUND_ITEMS[k][9] for k in (0, 1, 2)]

    # Company row: domain claimed, headcount recorded, stage_size confounder cut.
    company = db.session.get(Company, run.company_id)
    assert company.domain == "acme.example"
    assert company.headcount == 450 and company.headcount_source == "careers page"
    size = db.session.query(CompanyConfounderValue).filter_by(
        company_id=company.id, confounder_key="stage_size").one()
    assert size.value_num == 3.0 and size.source == "researched"

    # Scorer: one call (3 items < batch), the excerpts and speakers in the prompt, the
    # item-level abstain clauses, a run row.
    assert len(scorer_fake.requests) == 1
    prompt = scorer_fake.requests[0]["messages"][0]["content"]
    assert EXCERPT_A in prompt and EXCERPT_C in prompt
    assert "speaker: employee review, Software Engineer" in prompt
    assert "Company Culture Rating Rubric" in prompt
    assert "no dominant signal" in prompt and "does not apply to a single item" in prompt
    schema = scorer_fake.requests[0]["response_format"]["json_schema"]["schema"]
    assert sorted(schema["required"]) == sorted("item_%d" % i.id for i in items)
    scorer_run = db.session.query(ScorerRun).one()
    assert scorer_run.model == "gpt-5.5-2026-04-23"
    assert scorer_run.temperature_honored is True
    assert scorer_run.rubric_version == "v3.1-PROPOSED-2026-09-29"
    assert scorer_run.packet_version == RESEARCH_PROMPT_VERSION
    assert json.loads(scorer_run.notes)["scoring_prompt_version"] == SCORING_PROMPT_VERSION

    # The scorer's confidence is stored per cell (gate 5), None on abstentions.
    cells = {(s.evidence_item_id, s.dimension_key): s for s in db.session.query(EvidenceItemScore)}
    assert cells[(items[0].id, "pace")].confidence == 0.6
    assert cells[(items[1].id, "autonomy")].abstained and cells[(items[1].id, "autonomy")].confidence is None

    # Six records every time; pace is known (3 scored, one independent recent item),
    # autonomy unknown (2 scored).
    records = {r.dimension_key: r for r in store.trait_records(db, company.id)}
    assert sorted(records) == sorted(DIMENSIONS)
    assert all(r.aggregation_version == AGGREGATION_VERSION for r in records.values())
    assert records["pace"].status == "known"
    assert records["pace"].estimate == pytest.approx((0.9 + 0.9 + 0.7) / 3)
    assert records["pace"].evidence_count == 3 and records["pace"].abstain_count == 0
    assert records["pace"].last_dated == datetime.date(2026, 9, 20)
    assert records["autonomy"].status == "unknown"
    assert records["autonomy"].evidence_count == 2 and records["autonomy"].abstain_count == 1
    assert records["feedback"].status == "unknown" and records["feedback"].abstain_count == 3

    # The evidence behind a record carries paraphrases and never the verbatim text.
    behind = store.items_for_record(db, records["pace"].id)
    assert len(behind) == 3
    assert {v.paraphrase for v in behind} == {FOUND_ITEMS[k][7] for k in (0, 1, 2)}
    for view in behind:
        assert EXCERPT_A not in repr(view) and EXCERPT_B not in repr(view)

    # The run card (review F2): counts, reasons, kinds, yield, the aggregation report,
    # the raw text -- on the row, never on the view.
    card = _internal(db.session.get(CompanyResearchRun, run.id))
    assert card["candidates"] == 5 and card["kept"] == 3
    # E's URL was cited (by B and D), so E fails on coverage, not on its URL.
    assert card["dropped"]["by_reason"] == {"coverage": 1, "paraphrase_shared_run": 1}
    assert card["citations"] == {"total": 4, "by_kind": {"web_search_result_location": 4}}
    assert card["served_model"] == "claude-opus-5-5" and card["fell_back"] is False
    assert card["scope_declaration"].startswith("The employee reviews come from")
    assert card["yield"]["employee_review"] == {"kept": 1, "minimum": 12, "maximum": 15, "met": False}
    assert card["yield"]["job_posting"]["distinct_postings"] == 1
    assert [i["verified_by"] for i in card["items"]] == ["web_search_result_location"] * 3
    assert card["aggregation"]["research_run_id"] == run.id
    assert card["aggregation"]["dimensions"]["autonomy"]["unknown_reason"] == "too_few_items"
    assert card["aggregation"]["dimensions"]["pace"]["status"] == "known"
    assert card["scoring"]["scorer_run_id"] == scorer_run.id
    assert EXCERPT_A in card["raw_text"]
    assert "raw_text" not in repr(run) and EXCERPT_A not in repr(run)

    summary = service.research_run_summary(db, run.id)
    assert summary["status"] == "done" and summary["items"] == 3 and summary["known"] == 1
    assert summary["candidates"] == 5 and summary["citations"] == 4
    assert summary["dropped"] == {"invalid": 0, "unverified": 1, "paraphrase": 1}
    assert EXCERPT_A not in repr(summary)


def test_the_90_day_cache_in_flight_and_failed_paths(ctx, no_keys, monkeypatch):
    db = ctx
    from model import CompanyResearchRun

    research_fake = FakeResearchClient(_research_message(), _research_message())
    _install(monkeypatch, research_fake, FakeScorerClient())

    first = service.request_research(db, company_name="Acme Corp", trigger="on_demand")
    assert store.latest_research_run(db, first.company_id).status == "done"

    # A done run younger than 90 days is reused: no second research call.
    again = service.request_research(db, company_name="acme corp", trigger="on_demand")
    assert again.id == first.id and again.status == "done"
    by_id = service.request_research(db, company_id=first.company_id, trigger="batch")
    assert by_id.id == first.id
    assert len(research_fake.requests) == 1

    # Older than 90 days: a new run.
    row = db.session.get(CompanyResearchRun, first.id)
    row.finished_at = row.finished_at - datetime.timedelta(days=91)
    db.session.commit()
    second = service.request_research(db, company_name="Acme Corp", trigger="on_demand")
    assert second.id != first.id
    assert len(research_fake.requests) == 2

    # In flight: returned as is, no dispatch.
    queued = service.request_research(
        db, company_name="Acme Corp", trigger="batch", force=True, dispatch=False
    )
    assert queued.status == "queued"
    same = service.request_research(db, company_name="Acme Corp", trigger="on_demand")
    assert same.id == queued.id and same.status == "queued"
    assert len(research_fake.requests) == 2

    # A failed latest run is not a cache hit. (A run finishes only from `running`:
    # the claim comes first.)
    assert store.mark_research_run_running(db, queued.id).status == "running"
    store.finish_research_run(db, queued.id, status="failed", error="research_refused")
    research_fake._responses.append(_research_message())
    third = service.request_research(db, company_name="Acme Corp", trigger="on_demand")
    assert third.id != queued.id
    assert store.latest_research_run(db, first.company_id).status == "done"


def test_review_f7_a_rerun_aggregates_from_its_own_items_only(ctx, no_keys, monkeypatch):
    """Measured hole: a second run used to pool the first run's items with its own, so
    every re-run doubled the evidence counts."""
    db = ctx
    from model import CompanyEvidenceItem

    research_fake = FakeResearchClient(_research_message(), _research_message())
    scorer_fake = FakeScorerClient(scores=[{"pace": 0.9}, {"pace": 0.9}, {"pace": 0.7}] * 2)
    _install(monkeypatch, research_fake, scorer_fake)

    first = service.request_research(db, company_name="Acme Corp", trigger="on_demand")
    second = service.request_research(db, company_name="Acme Corp", trigger="batch", force=True)
    assert second.id != first.id
    assert db.session.query(CompanyEvidenceItem).filter_by(company_id=first.company_id).count() == 6

    records = {r.dimension_key: r for r in store.trait_records(db, first.company_id)}
    assert records["pace"].evidence_count == 3  # not 6
    behind = store.items_for_record(db, records["pace"].id)
    assert {v.research_run_id for v in behind} == {second.id}

    # The re-aggregate C6 calls (no run id) reads the latest DONE run, same answer.
    service.aggregate_company(db, first.company_id)
    records = {r.dimension_key: r for r in store.trait_records(db, first.company_id)}
    assert records["pace"].evidence_count == 3
    assert {v.research_run_id for v in store.items_for_record(db, records["pace"].id)} == {second.id}


def test_a_failed_research_call_records_its_cost_and_a_fixed_error(ctx, no_keys, monkeypatch):
    db = ctx
    spent = ResearchUsage(by_model={"claude-opus-5-5": TokenUsage(input_tokens=20_000, output_tokens=0)},
                          web_search_requests=4, api_requests=1)
    research_fake = FakeResearchClient(
        ResearchProviderError("HTTP 529", spent, retryable=True, status_code=529)
    )
    scorer_fake = FakeScorerClient()
    _install(monkeypatch, research_fake, scorer_fake)

    queued = service.request_research(db, company_name="Globex", trigger="on_demand")
    run = store.latest_research_run(db, queued.company_id)
    assert run.status == "failed"
    assert run.error == service.ERROR_PROVIDER
    assert run.cost_usd == Decimal("0.12")  # 4 searches ($0.04) + 20k input tokens ($0.08, Opus 5.5)
    assert scorer_fake.requests == []
    assert store.trait_records(db, queued.company_id) == []


def test_an_unparseable_record_is_a_failed_run_with_its_cost_and_its_text(ctx, no_keys, monkeypatch):
    db = ctx
    from model import CompanyResearchRun

    message = _message([SEARCH_USE, _search_result([CAREERS_URL]),
                        {"type": "text", "text": "I could not find enough to report."}])
    _install(monkeypatch, FakeResearchClient(message), FakeScorerClient())
    queued = service.request_research(db, company_name="Initech", trigger="on_demand")
    run = store.latest_research_run(db, queued.company_id)
    assert run.status == "failed" and run.error == service.ERROR_UNPARSEABLE
    assert run.cost_usd == Decimal("0.066")
    card = _internal(db.session.get(CompanyResearchRun, run.id))
    assert card["parsed"] is False and card["candidates"] == 0
    assert "could not find enough" in card["raw_text"]


def test_review_f2_no_verified_evidence_fails_the_run_as_research_unverified(ctx, no_keys, monkeypatch):
    """Measured hole: a run whose every item was dropped used to finish `done` with
    six quiet unknowns. Now it is a FAILED run with its cost and its run card."""
    db = ctx
    from model import CompanyResearchRun

    # (1) Zero citations at all: the API never saw the model quote anything.
    unverifiable = [FOUND_ITEMS[4]]
    _install(monkeypatch, FakeResearchClient(_research_message(items=unverifiable, record=_record_json(unverifiable))),
             FakeScorerClient())
    queued = service.request_research(db, company_name="Hooli", trigger="on_demand")
    run = store.latest_research_run(db, queued.company_id)
    assert run.status == "failed" and run.error == service.ERROR_UNVERIFIED == "research_unverified"
    assert run.cost_usd == Decimal("0.066")
    assert store.trait_records(db, queued.company_id) == []
    card = _internal(db.session.get(CompanyResearchRun, run.id))
    assert card["candidates"] == 1 and card["kept"] == 0 and card["citations"]["total"] == 0
    assert card["dropped"]["by_reason"] == {"url_only_listed": 1}

    # (2) Citations exist but cover a fragment only: candidates, nothing kept.
    fragment = [("employee_review", "role", "Analyst", REVIEWS_URL, "2026-05-02", False,
                 "Leadership told us that the culture of radical candor means nobody is ever protected from blunt criticism.",
                 "A reviewer says blunt criticism is the norm.", "radical candor", "employee review, Analyst")]
    _install(monkeypatch, FakeResearchClient(_research_message(items=fragment, record=_record_json(fragment))),
             FakeScorerClient())
    queued = service.request_research(db, company_name="Hooli", trigger="on_demand", force=True)
    run = store.latest_research_run(db, queued.company_id)
    assert run.status == "failed" and run.error == "research_unverified"
    card = _internal(db.session.get(CompanyResearchRun, run.id))
    assert card["citations"]["total"] == 1
    assert card["dropped"]["by_reason"] == {"coverage": 1}


def test_request_research_without_a_key_raises_before_writing_anything(ctx, no_keys):
    db = ctx
    with pytest.raises(LLMProviderUnavailable):
        service.request_research(db, company_name="Vandelay", trigger="on_demand")
    from model import Company, CompanyResearchRun

    company = db.session.query(Company).filter_by(slug="vandelay").one()  # resolved first
    assert db.session.query(CompanyResearchRun).filter_by(company_id=company.id).count() == 0


# ---------------------------------------------------------------------------
# The research step on its own (no database): verification, dates, speakers, parsing
# ---------------------------------------------------------------------------

NOW = datetime.datetime(2026, 10, 13, 9, 30, tzinfo=datetime.timezone.utc)


def _outcome(content, record):
    content = list(content) + [{"type": "text", "text": "```json\n%s\n```" % json.dumps(record)}]
    fake = FakeResearchClient(_message(content))
    return research.run_research("Acme Corp", domain="acme.example", client=fake, now=NOW)


def _raw_item(source_type, url, excerpt, *, scope="company", label=None, date="2026-05-02",
              access=False, speaker="employee review, Analyst", paraphrase="A reviewer describes it in other words."):
    return {"source_type": source_type, "scope": scope, "scope_label": label, "url": url,
            "date": date, "date_is_access_date": access, "speaker": speaker,
            "excerpt": excerpt, "paraphrase": paraphrase}


def test_review_f1_citations_must_come_from_the_items_own_fetched_or_cited_source():
    """(a) a char_location citation matches the fetched page by URL (resolved by the
    infra from document_index); (c) a URL only listed in search results verifies
    nothing; a citation from another URL verifies nothing; a fetched page with no
    citation verifies nothing."""
    # The careers page is fetched directly (not listed by the search). See
    # test_review_f1_a_fetched_page_is_matched_by_url_not_by_its_title for the case
    # where the search title and the fetched title differ.
    content = [
        SEARCH_USE, _search_result([REVIEWS_URL, NEWS_URL, POSTING_URL]),
        FETCH_USE, _fetch_result(CAREERS_URL, "Careers at Acme"),
        {"type": "server_tool_use", "id": "srvtoolu_f2", "name": "web_fetch", "input": {"url": POSTING_URL}},
        dict(_fetch_result(POSTING_URL, "Operations Analyst - Acme"), tool_use_id="srvtoolu_f2"),
        _char_cited_line('"%s"' % EXCERPT_A, EXCERPT_A, "Careers at Acme"),
        _cited_line('"%s"' % EXCERPT_B, EXCERPT_B, REVIEWS_URL),
    ]
    record = {"company": {}, "scope_declaration": "x", "items": [
        _raw_item("careers_page", CAREERS_URL, EXCERPT_A, speaker="company careers page",
                  paraphrase="Engineers release daily and are expected to take full responsibility."),
        _raw_item("employee_review", REVIEWS_URL, EXCERPT_B, scope="role", label="SWE",
                  paraphrase="A reviewer describes constant urgency and weekend work."),
        _raw_item("news", NEWS_URL, EXCERPT_B),                       # only listed
        _raw_item("employee_review", REVIEWS_URL, EXCERPT_A),         # cited text belongs to another URL
        _raw_item("job_posting", POSTING_URL, EXCERPT_C),             # fetched, nothing cited from it
        _raw_item("employee_review", "https://elsewhere.example/x", EXCERPT_B),  # never seen
    ]}
    outcome = _outcome(content, record)
    assert [i.source_url for i in outcome.items] == [CAREERS_URL, REVIEWS_URL]
    assert [m["verified_by"] for m in outcome.item_meta] == ["char_location", "web_search_result_location"]
    assert outcome.diagnostics["dropped"]["by_reason"] == {
        "coverage": 1, "no_citation_from_source": 1, "url_not_seen": 1, "url_only_listed": 1,
    }
    assert outcome.diagnostics["citations"]["by_kind"] == {"char_location": 1, "web_search_result_location": 1}
    assert not outcome.unverified_run


def _char_cited_line_at(text, cited_text, title, document_index):
    return {"type": "text", "text": text + "\n", "citations": [
        {"type": "char_location", "document_index": document_index, "document_title": title,
         "start_char_index": 0, "end_char_index": len(cited_text), "cited_text": cited_text},
    ]}


def test_review_f1_a_fetched_page_is_matched_by_url_not_by_its_title():
    """C9 (2026-10-13): a page the search lists under one title and the fetch returns
    under another is matched by the URL the infra resolves from document_index, so its
    char_location citations verify its items. Two guards on the new rule: a citation
    that resolved to a DIFFERENT fetched URL does not match through a coincidentally
    equal title; a citation the infra could not resolve (document_index out of range,
    url None) still falls back to the title, the pre-fix rule."""
    same_title = "Careers | Acme Corporation"
    content = [
        SEARCH_USE,
        {
            "type": "web_search_tool_result", "tool_use_id": "srvtoolu_s1",
            "content": [
                {"type": "web_search_result", "url": CAREERS_URL, "title": "Acme Careers - Join Us",
                 "encrypted_content": "ENC", "page_age": None},
                {"type": "web_search_result", "url": NEWS_URL, "title": "Acme reorg",
                 "encrypted_content": "ENC", "page_age": None},
            ],
        },
        FETCH_USE, _fetch_result(CAREERS_URL, same_title),                       # document 0
        {"type": "server_tool_use", "id": "srvtoolu_f2", "name": "web_fetch", "input": {"url": NEWS_URL}},
        dict(_fetch_result(NEWS_URL, same_title), tool_use_id="srvtoolu_f2"),   # document 1, same title
        # resolves to CAREERS_URL by index: the careers item verifies by URL although
        # the search listed the page under a different title.
        _char_cited_line_at('"%s"' % EXCERPT_A, EXCERPT_A, same_title, 0),
        # resolves to NEWS_URL by index; its title equals the careers page's title, and
        # that must NOT let it verify the careers item.
        _char_cited_line_at('"%s"' % EXCERPT_B, EXCERPT_B, same_title, 1),
        # unresolvable index (no such document): url None -> title fallback.
        _char_cited_line_at('"%s"' % EXCERPT_C, EXCERPT_C, same_title, 9),
    ]
    record = {"company": {}, "scope_declaration": "x", "items": [
        _raw_item("careers_page", CAREERS_URL, EXCERPT_A, speaker="company careers page",
                  paraphrase="Engineers release daily and are expected to take full responsibility."),
        # EXCERPT_B was cited from NEWS_URL, not the careers page: coverage fails here
        _raw_item("careers_page", CAREERS_URL, EXCERPT_B, speaker="company careers page",
                  paraphrase="A description of constant urgency and weekend work."),
        # EXCERPT_C's citation has no URL; the title fallback matches the news page
        _raw_item("news", NEWS_URL, EXCERPT_C,
                  paraphrase="Quarterly priorities come from management with a weekly cadence."),
    ]}
    outcome = _outcome(content, record)

    assert [(i.source_url, i.source_type) for i in outcome.items] == [
        (CAREERS_URL, "careers_page"), (NEWS_URL, "news"),
    ]
    assert [m["verified_by"] for m in outcome.item_meta] == ["char_location", "char_location"]
    assert outcome.diagnostics["dropped"]["by_reason"] == {"coverage": 1}
    sources = {s["url"]: s for s in outcome.diagnostics["sources"]}
    assert sources[CAREERS_URL]["title"] == same_title
    assert not outcome.unverified_run


def test_review_f8_dates_careers_access_dates_and_open_postings():
    content = [
        SEARCH_USE, _search_result([CAREERS_URL, POSTING_URL, REVIEWS_URL]),
        FETCH_USE, dict(_fetch_result(POSTING_URL, "Analyst - Acme"), tool_use_id="srvtoolu_f1"),
        _cited_line('"%s"' % EXCERPT_A, EXCERPT_A, CAREERS_URL),
        _cited_line('"%s"' % EXCERPT_C, EXCERPT_C, POSTING_URL),
        _cited_line('"%s"' % EXCERPT_B, EXCERPT_B, REVIEWS_URL),
        _cited_line('"%s"' % EXCERPT_D, EXCERPT_D, REVIEWS_URL),
    ]
    record = {"company": {}, "items": [
        # careers page dated on the retrieval day with the flag NOT set: access-dated anyway
        _raw_item("careers_page", CAREERS_URL, EXCERPT_A, date="2026-10-13", access=False,
                  speaker="company careers page", paraphrase="Engineers release daily."),
        # posting that was FETCHED (verified open): dated at retrieval, whatever the model said
        _raw_item("job_posting", POSTING_URL, EXCERPT_C, scope="role", label="Analyst", date="2026-01-15",
                  speaker="job posting", paraphrase="Management sets quarterly priorities."),
        # review with a real date keeps it
        _raw_item("employee_review", REVIEWS_URL, EXCERPT_B, scope="role", label="SWE",
                  paraphrase="A reviewer describes constant urgency."),
        # review dated on the retrieval day is NOT access-dated (the rule is careers pages)
        _raw_item("employee_review", REVIEWS_URL, EXCERPT_D, scope="role", label="AM", date="2026-10-13",
                  paraphrase="A reviewer praises cross-team cooperation."),
    ]}
    outcome = _outcome(content, record)
    assert [i.published_at for i in outcome.items] == [
        None, datetime.date(2026, 10, 13), datetime.date(2026, 5, 2), datetime.date(2026, 10, 13),
    ]
    assert [(m["access_dated"], m["verified_open"]) for m in outcome.item_meta] == [
        (True, False), (False, True), (False, False), (False, False),
    ]


def test_review_f4_an_employer_reply_is_retagged_company_authored_and_the_speaker_is_kept():
    content = [
        SEARCH_USE, _search_result([REVIEWS_URL]),
        _cited_line('"%s"' % EXCERPT_B, EXCERPT_B, REVIEWS_URL),
        _cited_line('"%s"' % EXCERPT_D, EXCERPT_D, REVIEWS_URL),
    ]
    record = {"company": {}, "items": [
        _raw_item("employee_review", REVIEWS_URL, EXCERPT_B, scope="role", label="SWE",
                  speaker="Employer response", paraphrase="The employer answers that urgency is temporary."),
        _raw_item("employee_review", REVIEWS_URL, EXCERPT_D, scope="role", label="Employer Brand Manager",
                  speaker="employee review, Employer Brand Manager",
                  paraphrase="A reviewer praises cross-team cooperation."),
    ]}
    outcome = _outcome(content, record)
    assert [i.source_type for i in outcome.items] == ["careers_page", "employee_review"]
    assert [i.speaker for i in outcome.items] == ["Employer response", "employee review, Employer Brand Manager"]
    assert outcome.diagnostics["retagged_employer_replies"] == 1


def test_review_f3c_the_record_is_found_anywhere_in_the_turns_text():
    """The JSON may land before a late tool call, so the text after the last tool call
    is not the record; the LAST JSON object with an items list anywhere in the text is."""
    record = {"company": {}, "items": [_raw_item("employee_review", REVIEWS_URL, EXCERPT_B,
                                                 paraphrase="A reviewer describes constant urgency.")]}
    content = [
        SEARCH_USE, _search_result([REVIEWS_URL]),
        _cited_line('"%s"' % EXCERPT_B, EXCERPT_B, REVIEWS_URL),
        {"type": "text", "text": "Here is the record {not json} then:\n" + json.dumps(record) + "\nChecking one more thing."},
        {"type": "server_tool_use", "id": "srvtoolu_s2", "name": "web_search", "input": {"query": "Acme Corp news"}},
        dict(_search_result([NEWS_URL]), tool_use_id="srvtoolu_s2"),
        {"type": "text", "text": "Nothing further to add."},
    ]
    fake = FakeResearchClient(_message(content))
    outcome = research.run_research("Acme Corp", client=fake, now=NOW)
    assert len(outcome.items) == 1
    # Braces in prose before the record, and objects without an items list after it,
    # do not hide it; the record's own nested dicts (no items list) are skipped.
    assert research.parse_record('x {not json} {"items": [{"a": {"b": 1}}]} y {"a": 2} z')["items"] == [{"a": {"b": 1}}]
    with pytest.raises(ValueError):
        research.parse_record("no record here {broken")
    with pytest.raises(ValueError):
        research.parse_record('{"items": "not a list"}')


# ---------------------------------------------------------------------------
# Scoring: the scrub (F9) and the frozen anchors + rubric pin (F14)
# ---------------------------------------------------------------------------

def test_review_f9_the_scorer_input_is_scrubbed_but_the_stored_text_is_not(ctx, no_keys, monkeypatch):
    db = ctx
    from model import CompanyEvidenceItem

    named = "At Acme Corp we ship daily; see acme.example and the Acme values page, says ACME's CEO."
    items = [("careers_page", "company", None, CAREERS_URL, None, True, named,
              "The firm releases every day and points readers to its values page.", named,
              "company careers page")]
    _install(monkeypatch, FakeResearchClient(_research_message(items=items, record=_record_json(items))),
             FakeScorerClient(scores=[{"pace": 0.9}]))
    queued = service.request_research(db, company_name="Acme Corp", trigger="on_demand")
    assert store.latest_research_run(db, queued.company_id).status == "done"

    (request,) = [r for r in _scorer_requests(monkeypatch)]
    prompt = request["messages"][0]["content"]
    assert "Acme" not in prompt and "ACME" not in prompt and "acme.example" not in prompt
    assert "At the company we ship daily; see the company and the the company values page, says the company's CEO." in prompt
    assert "has been replaced by 'the company'" in prompt
    (item,) = db.session.query(CompanyEvidenceItem).filter_by(company_id=queued.company_id).all()
    assert _internal(item) == named  # stored untouched


def _scorer_requests(monkeypatch):
    return llm.get_scorer_client().requests


def test_company_scrubber_rules():
    scrub = score_items.company_scrubber("Acme Corp", "acme.example")
    assert scrub("Acme Corp's teams at acme.example; Acme; acmeish; ACME CORP") == \
        "the company's teams at the company; the company; acmeish; the company"
    # Short labels are not scrubbed on their own; the full domain and name still are.
    scrub = score_items.company_scrubber("Go Inc", "go.com")
    assert scrub("Go Inc lets you go to go.com") == "the company lets you go to the company"
    assert score_items.company_scrubber(None, None)("unchanged") == "unchanged"


def test_review_f14_the_anchors_copy_and_the_rubric_text_are_pinned():
    """The package ships a frozen copy of anchors v3.1; it must stay byte-identical to the
    research corpus original. The rubric text the scorer reads is build_rubric_text
    (IMPORTED from the harness) on those anchors; its hash is tied to
    SCORING_PROMPT_VERSION so a harness edit fails here rather than changing production."""
    assert score_items.ANCHORS_PATH.parent == REPO_ROOT / "solverah" / "services" / "company_research"
    assert score_items.ANCHORS_SOURCE_PATH.exists(), "the Solverah_IP original is tracked in the repo"
    assert hashlib.sha256(score_items.ANCHORS_PATH.read_bytes()).hexdigest() == \
        hashlib.sha256(score_items.ANCHORS_SOURCE_PATH.read_bytes()).hexdigest()
    assert score_items.anchors()["rubric_version"] == "v3.1-PROPOSED-2026-09-29"
    digest = hashlib.sha256(score_items.rubric_text().encode("utf-8")).hexdigest()
    assert digest == RUBRIC_TEXT_SHA256, (
        "build_rubric_text(anchors v3.1) no longer produces the text SCORING_PROMPT_VERSION "
        "was pinned to; bump the version and the hash together, deliberately"
    )
    assert SCORING_PROMPT_VERSION == "cl-score-v2-2026-10-13/anchors-v3.1"


def test_the_scoring_instruction_states_the_item_level_abstain_rules():
    text = build_scoring_instruction(["item_1"], DIMENSIONS, [0.1, 0.9], [0.1, 0.9],
                                     scrub_replacement="the company")
    assert "'no strong signal' or 'no dominant signal'" in text
    assert "record insufficient evidence rather than that band" in text
    assert "does not apply to a single item" in text
    assert "speaker" in text
    assert "replaced by 'the company'" in text
    assert "replaced by" not in build_scoring_instruction(["item_1"], DIMENSIONS, [0.1], [0.1])


# ---------------------------------------------------------------------------
# Job postings
# ---------------------------------------------------------------------------

POSTING_TEXT = """Operations Analyst

What you'll do:
- Execute against the quarterly roadmap set by the operations leadership team.
- Follow established processes and escalate exceptions for manager sign-off.
- Join a daily stand-up with the wider team and pair with analysts on reconciliations.

Compensation: $80,000 - $95,000. Location: Austin, TX office.
"""


def test_a_posting_is_scored_by_the_scorer_client_only_and_its_records_are_private(
    ctx, no_keys, monkeypatch
):
    db = ctx
    from model import CompanyEvidenceItem, ScorerRun

    research_fake = NeverCalledResearchClient()
    scorer_fake = FakeScorerClient(
        extraction_items=[
            {"excerpt": "Execute against the quarterly roadmap set by the operations leadership team.",
             "paraphrase": "The role works to a quarterly plan handed down by operations leaders."},
            {"excerpt": "Follow established processes and escalate exceptions for manager sign-off.",
             "paraphrase": "Standard procedures apply and anything unusual needs a manager's approval."},
            {"excerpt": "Join a daily stand-up with the wider team and pair with analysts on reconciliations.",
             "paraphrase": "There is a daily team meeting and reconciliation work is done in pairs."},
            # invented: not in the posting
            {"excerpt": "You will set your own priorities with no oversight.",
             "paraphrase": "Complete freedom over priorities."},
            # in the posting, but the paraphrase copies a 9-word run: paraphrase gate
            {"excerpt": "Compensation: $80,000 - $95,000. Location: Austin, TX office.",
             "paraphrase": "As stated: compensation: $80,000 - $95,000. Location: Austin, TX office."},
            # in the posting, paraphrase copies a DIFFERENT sentence of the posting
            {"excerpt": "Follow established processes and escalate exceptions for manager sign-off.",
             "paraphrase": "Also: join a daily stand-up with the wider team and pair with analysts on reconciliations."},
        ],
        scores=[{"autonomy": 0.1}, {"autonomy": 0.1}, {"autonomy": 0.3, "collaboration": 0.9}],
    )
    _install(monkeypatch, research_fake, scorer_fake)

    from solverah.repositories.company_repository import find_or_create_company

    company = find_or_create_company("Acme Corp")
    user_id = _mk_user(db)
    posting = service.submit_job_posting(
        db, user_id, company_id=company.id, text=POSTING_TEXT, title="Operations Analyst"
    )
    assert posting.status == "pending"  # the view as submitted; eager ran the job inline

    assert research_fake.requests == []
    assert len(scorer_fake.requests) == 2  # one extraction, one scoring batch
    assert POSTING_TEXT.strip() in scorer_fake.requests[0]["messages"][0]["content"]

    refreshed = store.job_postings_for_user(db, user_id)[0]
    assert refreshed.status == "scored"

    items = (
        db.session.query(CompanyEvidenceItem)
        .filter(CompanyEvidenceItem.job_posting_id == posting.id)
        .order_by(CompanyEvidenceItem.id).all()
    )
    assert len(items) == 3
    scoring_prompt = scorer_fake.requests[1]["messages"][0]["content"]
    assert "Execute against the quarterly roadmap" in scoring_prompt  # the verbatim text, read back
    assert "You will set your own priorities" not in scoring_prompt  # the invented one never stored
    assert "speaker: not recorded" in scoring_prompt
    assert all(i.source_type == "user_pasted_posting" and i.scope == "role" for i in items)
    assert all(i.scope_label == "Operations Analyst" for i in items)
    assert db.session.query(ScorerRun).one().packet_version == POSTING_EXTRACT_PROMPT_VERSION

    private = {r.dimension_key: r for r in store.posting_trait_records(db, posting.id)}
    assert sorted(private) == sorted(DIMENSIONS)
    assert all(r.job_posting_id == posting.id and r.scope == "role" for r in private.values())
    # A posting's own words carry its private record (no independence rule there).
    assert private["autonomy"].status == "known"
    assert private["autonomy"].estimate == pytest.approx((0.1 + 0.1 + 0.3) / 3)
    assert private["collaboration"].status == "unknown"  # one scored item
    # Posting items are dated on the paste date, so they sit inside the recency window.
    assert all(i.published_at == datetime.date.today() for i in items)
    assert private["autonomy"].first_dated == datetime.date.today()
    assert store.trait_records(db, company.id) == []  # nothing leaked into the shared read


def test_a_pure_requirements_posting_abstains_everywhere_and_is_unknown(ctx, no_keys, monkeypatch):
    db = ctx
    scorer_fake = FakeScorerClient(extraction_items=[])
    _install(monkeypatch, NeverCalledResearchClient(), scorer_fake)
    from solverah.repositories.company_repository import find_or_create_company

    company = find_or_create_company("Acme Corp")
    user_id = _mk_user(db)
    posting = service.submit_job_posting(
        db, user_id, company_id=company.id, text="Requirements: 5 years of SQL. BSc. Must relocate."
    )
    assert store.job_postings_for_user(db, user_id)[0].status == "scored"
    records = store.posting_trait_records(db, posting.id)
    assert len(records) == 6 and {r.status for r in records} == {"unknown"}
    assert len(scorer_fake.requests) == 1  # extraction only; nothing to score


def test_a_posting_without_a_company_is_refused_before_anything_is_written(ctx, no_keys, monkeypatch):
    db = ctx
    _install(monkeypatch, NeverCalledResearchClient(), FakeScorerClient())
    user_id = _mk_user(db)
    with pytest.raises(ValueError, match="needs a company"):
        service.submit_job_posting(db, user_id, company_id=None, text=POSTING_TEXT)
    with pytest.raises(ValueError, match="does not exist"):
        service.submit_job_posting(db, user_id, company_id=999_999, text=POSTING_TEXT)
    assert store.job_postings_for_user(db, user_id) == []
    # And the store itself refuses to attach items to a company-less posting.
    orphan = store.create_job_posting(db, user_id, posting_text="x")
    with pytest.raises(ValueError, match="has no company"):
        store.write_items(db, 1, [store.EvidenceItemInput("role", "user_pasted_posting", "x", "y")],
                          job_posting_id=orphan.id)


def test_the_posting_module_never_imports_the_research_client():
    path = REPO_ROOT / "solverah" / "services" / "company_research" / "job_posting.py"
    tree = ast.parse(io.open(path, encoding="utf-8").read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update("%s.%s" % (node.module, a.name) for a in node.names)
        elif isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
    assert not any(n.startswith("solverah.infra.llm.research") for n in names), sorted(names)
    assert not any(n.endswith("get_research_client") or n.endswith("run_research_call") for n in names)


def test_the_research_prompt_takes_a_name_and_a_domain_and_nothing_else():
    import inspect

    assert list(inspect.signature(build_research_prompt).parameters) == ["company_name", "domain"]
    text = build_research_prompt("Acme Corp", "acme.example")
    assert "Acme Corp" in text and "acme.example" in text
    assert "paraphrase" in text and "excerpt" in text
    assert "no quotation marks of any kind" in text
    assert "employer response" in text


# ---------------------------------------------------------------------------
# The store change account deletion needs
# ---------------------------------------------------------------------------

def test_delete_job_postings_with_commit_false_leaves_the_commit_to_the_caller(ctx):
    db = ctx
    user_id = _mk_user(db)
    store.create_job_posting(db, user_id, posting_text="pasted")
    assert len(store.job_postings_for_user(db, user_id)) == 1

    removed = store.delete_job_postings_for_user(db, user_id, commit=False)
    assert removed == 1
    assert store.job_postings_for_user(db, user_id) == []  # visible inside the transaction
    db.session.rollback()
    assert len(store.job_postings_for_user(db, user_id)) == 1  # the caller decides

    assert store.delete_job_postings_for_user(db, user_id) == 1  # default still commits
    db.session.rollback()
    assert store.job_postings_for_user(db, user_id) == []


# ---------------------------------------------------------------------------
# The text gates, pinned (review F1 and F13: one test per measured hole)
# ---------------------------------------------------------------------------

def test_paraphrase_gate_run_limit_scales_with_the_excerpt():
    """The run cap is seven words, or half the excerpt; the trigram cap (35%) binds
    first on short excerpts, since a 7-word run is 5 of a 16-word excerpt's 14 trigrams."""
    long = " ".join("w%d" % i for i in range(24))  # 24 words, 22 trigrams
    assert textcheck.shared_run_limit(long) == 7
    assert textcheck.paraphrase_passes_gate(long, "alpha w1 w2 w3 w4 w5 w6 w7 beta")  # 7 shared, 5/22 trigrams
    assert textcheck.paraphrase_gate(long, "alpha w1 w2 w3 w4 w5 w6 w7 w8 beta") == "shared_run"  # 8
    sixteen = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen"
    assert textcheck.shared_run_limit(sixteen) == 7
    assert textcheck.paraphrase_gate(sixteen, "alpha two three four five six seven eight beta") == "trigram_reuse"
    assert textcheck.paraphrase_passes_gate(sixteen, "alpha two three four five six beta")  # 5 shared, 3/14
    twelve = "one two three four five six seven eight nine ten eleven twelve"
    assert textcheck.shared_run_limit(twelve) == 6
    assert textcheck.paraphrase_passes_gate(twelve, "alpha two three four five six beta")  # 5 shared, 3/10
    assert textcheck.paraphrase_gate(twelve, "alpha one two three four five six seven beta") == "shared_run"
    assert textcheck.paraphrase_gate(sixteen, "") == "empty"
    assert textcheck.paraphrase_gate(sixteen, sixteen.upper()) == "identical"
    # punctuation and case do not hide a copied clause
    assert not textcheck.paraphrase_passes_gate(
        "We ship, to production, every single day and expect engineers to own it.",
        "They say: we SHIP to production every single day and expect engineers to own it",
    )


def test_review_f13_a_short_verbatim_excerpt_with_a_prefix_is_rejected():
    """Measured hole: 'A reviewer wrote: Micromanagement is constant here.' passed with
    seven words allowed. A four-word excerpt allows a run of two."""
    short = "Micromanagement is constant here."
    assert textcheck.shared_run_limit(short) == 2
    assert textcheck.paraphrase_gate(short, "A reviewer wrote: Micromanagement is constant here.") == "shared_run"
    assert textcheck.paraphrase_passes_gate(short, "A reviewer says close supervision never lets up.")


def test_review_f13_a_near_copy_that_changes_every_fifth_word_is_rejected():
    """Measured hole: a 16-word paraphrase sharing 13 of its words with the excerpt in
    runs of four passed the run rule. The trigram cap catches it."""
    excerpt = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen"
    words = excerpt.split()
    words[3], words[7], words[11] = "X", "Y", "Z"
    near = " ".join(words)
    assert textcheck.longest_shared_word_run(excerpt, near) == 4  # under the run limit
    assert textcheck.trigram_reuse(excerpt, near) > 0.35
    assert textcheck.paraphrase_gate(excerpt, near) == "trigram_reuse"
    ex = "We expect every engineer to own their roadmap and ship without waiting for approval from managers."
    assert textcheck.paraphrase_gate(
        ex, "We expect each engineer to own their roadmap and ship without waiting on approval from managers."
    ) is not None
    assert textcheck.paraphrase_passes_gate(
        ex, "Engineers release on their own authority and manage their own plans."
    )


def test_review_f13_quotation_marks_and_other_citations_from_the_page_reject_a_paraphrase():
    ex = "We expect every engineer to own their roadmap and ship without waiting for approval from managers."
    assert textcheck.paraphrase_gate(ex, 'Engineers are told to "own their roadmap".') == "quote_marks"
    assert textcheck.paraphrase_gate(ex, "A reviewer said 'we ship without waiting' is the norm.") == "quote_marks"
    assert textcheck.paraphrase_gate(ex, "Staff “own” their work.") == "quote_marks"
    # apostrophes inside and after words are not quotes
    assert textcheck.paraphrase_gate(ex, "Engineers don't wait for managers' sign-off on their plans.") is None
    # a paraphrase copying a DIFFERENT sentence cited from the same page is a quote too
    other = "Engineers release on their own authority and manage their own plans every quarter."
    assert textcheck.paraphrase_gate(
        ex, "Engineers release on their own authority and manage their own plans.", [other]
    ) == "shared_run"


def test_review_f1_excerpt_verification_is_coverage_not_a_fragment():
    """Measured holes: an invented sentence containing 'radical candor' verified against
    the citation 'radical candor'; an invented 20-word sentence verified on one real
    eight-word run. Coverage of 90% of the excerpt's words is required."""
    fake = "Leadership told us that the culture of radical candor means nobody is ever protected from blunt criticism."
    v = textcheck.verify_excerpt(fake, ["radical candor"])
    assert not v.verified and v.reason == "coverage" and v.coverage < 0.2
    v = textcheck.verify_excerpt(
        "The company says we move fast and break things every single day and the CEO personally reviews every launch.",
        ["we move fast and break things every single day, at scale"],
    )
    assert not v.verified and v.reason == "coverage" and v.coverage < 0.5
    real = "The pace here is relentless; deadlines move up, never back, and weekends happen."
    assert textcheck.verify_excerpt(real, [real]).verified
    # one corrected typo costs one word and still passes; two citations may cover jointly
    assert textcheck.verify_excerpt(real, [real.replace("relentless", "relentles")]).coverage == pytest.approx(12 / 13)
    assert textcheck.verify_excerpt(
        real, ["The pace here is relentless; deadlines", "deadlines move up, never back, and weekends happen."]
    ).verified
    assert textcheck.excerpt_is_verified(real, ["", "x", real])
    assert textcheck.verify_excerpt(real, []).reason == "no_citation"
    assert textcheck.verify_excerpt("short", ["short"]).reason == "too_short"


def test_review_f1_a_quotation_mark_the_source_did_not_print_fails_verification():
    said = 'The CEO said "we never sleep" during the call.'
    assert textcheck.verify_excerpt(said, ["The CEO said we never sleep during the call."]).reason == "quote_marks"
    assert textcheck.verify_excerpt(said, [said]).verified
    assert textcheck.verify_excerpt(said, ["The CEO said “we never sleep” during the call."]).verified


def test_normalisation_follows_the_scorer_pipeline_rules():
    from causal_graph.scorer_pipeline import _normalize

    sample = "“A” — b’s  – c\n d"
    assert textcheck.normalize(sample) == _normalize(sample)
    assert textcheck.longest_shared_word_run("a b c d", "x b c d y") == 3
    assert textcheck.longest_shared_word_run("", "a") == 0


# ---------------------------------------------------------------------------
# Dispatch: the production path (eager Celery, no worker) runs on the thread pool
# ---------------------------------------------------------------------------

def test_without_a_broker_and_outside_testing_the_job_runs_on_the_thread_pool(
    ctx, no_keys, monkeypatch
):
    import time

    from app import app
    from solverah.services.company_research import jobs

    db = ctx
    _install(monkeypatch, FakeResearchClient(_research_message()), FakeScorerClient())
    monkeypatch.setitem(app.config, jobs.INLINE_CONFIG_KEY, False)

    queued = service.request_research(db, company_name="Threaded Co", trigger="on_demand")
    assert queued.status == "queued"

    deadline = time.time() + 20
    while time.time() < deadline:
        db.session.expire_all()
        run = store.latest_research_run(db, queued.company_id)
        if run.status in ("done", "failed"):
            break
        time.sleep(0.05)
    assert run.id == queued.id
    assert run.status == "done", run.error
    assert len(store.trait_records(db, queued.company_id)) == 6


def test_dispatch_reports_which_path_it_took(ctx, monkeypatch):
    from app import app
    from solverah.services.company_research import jobs

    calls = []
    fake_task = SimpleNamespace(name="fake", delay=lambda *a: calls.append(a) or SimpleNamespace(id="x"))
    assert jobs.dispatch(fake_task, lambda _id: None, 1) == "inline"
    assert calls == [(1,)]
    monkeypatch.setitem(app.config, jobs.INLINE_CONFIG_KEY, False)
    ran = []
    assert jobs.dispatch(fake_task, lambda _id: ran.append(_id), 2) == "threaded"
    deadline = __import__("time").time() + 5
    while not ran and __import__("time").time() < deadline:
        __import__("time").sleep(0.01)
    assert ran == [2] and calls == [(1,)]


# ---------------------------------------------------------------------------
# C5c: one claim per run, no overwrite of a reaped row, the public switch, blocked
# domains
# ---------------------------------------------------------------------------

def _reap(db, run_id):
    """Age the running row past the hard limit and let the sweep reap it, as the
    cron would from another process."""
    from model import CompanyResearchRun
    from solverah.services.company_research.constants import RESEARCH_JOB_HARD_LIMIT_SECONDS

    row = db.session.get(CompanyResearchRun, run_id)
    row.started_at = row.started_at - datetime.timedelta(seconds=RESEARCH_JOB_HARD_LIMIT_SECONDS + 60)
    db.session.commit()
    assert service.sweep_research_runs(db)["reaped"] == 1
    db.session.expire_all()
    assert store.research_run(db, run_id).status == "failed"


def test_a_queued_run_is_claimed_once_two_workers_one_provider_call(ctx, no_keys, monkeypatch):
    """Production hands one row to two workers (the web pool and the sweep cron). The
    second to arrive sees `running` and must make NO provider call: here the second
    worker runs re-entrantly from inside the first worker's research turn."""
    db = ctx
    from model import CompanyEvidenceItem

    research_fake = FakeResearchClient(_research_message(), _research_message())
    _install(monkeypatch, research_fake, FakeScorerClient())
    queued = service.request_research(db, company_name="Race Co", trigger="on_demand", dispatch=False)
    assert queued.status == "queued"

    # The claim in the store is atomic: the second claim on the same row loses.
    assert store.mark_research_run_running(db, queued.id).status == "running"
    assert store.mark_research_run_running(db, queued.id) is None
    db.session.expire_all()
    assert service.run_research_job(queued.id).status == "running"  # not ours: no call
    assert research_fake.requests == []

    second = service.request_research(db, company_name="Race Two Co", trigger="on_demand", dispatch=False)
    real_run_research = research.run_research
    nested = []

    def racing_run_research(name, **kwargs):
        nested.append(service.run_research_job(second.id).status)
        return real_run_research(name, **kwargs)

    monkeypatch.setattr(research, "run_research", racing_run_research)
    finished = service.run_research_job(second.id)
    assert finished.status == "done", finished.error
    assert nested == ["running"]
    assert len(research_fake.requests) == 1
    assert db.session.query(CompanyEvidenceItem).filter_by(research_run_id=second.id).count() == 3
    assert service.run_research_job(second.id).status == "done"  # terminal: idempotent
    assert len(research_fake.requests) == 1


def test_a_reaped_run_keeps_its_verdict_and_the_late_result_writes_nothing(ctx, no_keys, monkeypatch):
    """The sweep reaps a row at the hard limit; the thread that was still working
    finishes later. The reaper's failed/timed_out stands, no item is written, and
    the cost of the late turn lands in the internal run card."""
    db = ctx
    from model import CompanyEvidenceItem, CompanyResearchRun

    research_fake = FakeResearchClient(_research_message())
    _install(monkeypatch, research_fake, FakeScorerClient())
    queued = service.request_research(db, company_name="Slow Co", trigger="on_demand", dispatch=False)
    real_run_research = research.run_research

    def reaped_during_the_turn(name, **kwargs):
        outcome = real_run_research(name, **kwargs)
        _reap(db, queued.id)
        return outcome

    monkeypatch.setattr(research, "run_research", reaped_during_the_turn)
    view = service.run_research_job(queued.id)
    assert view.status == "failed" and view.error == service.ERROR_TIMED_OUT
    assert view.cost_usd is None  # the reaper wrote the row; it is untouched
    assert db.session.query(CompanyEvidenceItem).filter_by(research_run_id=queued.id).count() == 0
    assert store.trait_records(db, queued.company_id) == []
    card = _internal(db.session.get(CompanyResearchRun, queued.id))
    (late,) = card["late_finish"]
    assert late["attempted_status"] == "done" and late["cost_usd"] == 0.066
    assert late["items_discarded"] == 0 and late["row_error"] == service.ERROR_TIMED_OUT


def test_a_run_reaped_after_its_writes_is_discarded_and_the_shared_read_restored(ctx, no_keys, monkeypatch):
    """The narrower window: reaped between the ownership check and the finish (during
    scoring). The conditional finish loses, the items, scores and records of that run
    are removed, and the shared read is rebuilt from the previous done run."""
    db = ctx
    from model import CompanyEvidenceItem, CompanyResearchRun

    research_fake = FakeResearchClient(_research_message(), _research_message())
    scorer_fake = FakeScorerClient(scores=[{"pace": 0.9}, {"pace": 0.9}, {"pace": 0.7}] * 2)
    _install(monkeypatch, research_fake, scorer_fake)
    first = service.request_research(db, company_name="Window Co", trigger="on_demand")
    assert store.latest_research_run(db, first.company_id).status == "done"
    before = {r.dimension_key: r.id for r in store.trait_records(db, first.company_id)}

    second = service.request_research(
        db, company_name="Window Co", trigger="batch", force=True, dispatch=False
    )
    real_score_items = score_items.score_items

    def reaped_during_scoring(db_, item_ids, **kwargs):
        result = real_score_items(db_, item_ids, **kwargs)
        _reap(db, second.id)
        return result

    monkeypatch.setattr(score_items, "score_items", reaped_during_scoring)
    view = service.run_research_job(second.id)
    assert view.status == "failed" and view.error == service.ERROR_TIMED_OUT
    assert db.session.query(CompanyEvidenceItem).filter_by(research_run_id=second.id).count() == 0
    assert db.session.query(CompanyEvidenceItem).filter_by(research_run_id=first.id).count() == 3
    card = _internal(db.session.get(CompanyResearchRun, second.id))
    (late,) = card["late_finish"]
    assert late["items_discarded"] == 3 and late["cost_usd"] == 0.066
    # The shared read is a fresh generation built from the FIRST run only.
    after = {r.dimension_key: r for r in store.trait_records(db, first.company_id)}
    assert after["pace"].evidence_count == 3
    assert {v.research_run_id for v in store.items_for_record(db, after["pace"].id)} == {first.id}
    assert after["pace"].id != before["pace"]
    assert store.latest_research_run(db, first.company_id).id == second.id


def test_the_switch_gates_new_runs_only(ctx, no_keys, monkeypatch):
    db = ctx
    from model import CompanyResearchRun

    research_fake = FakeResearchClient(_research_message(), _research_message())
    _install(monkeypatch, research_fake, FakeScorerClient())
    done = service.request_research(db, company_name="Open Co", trigger="on_demand")

    monkeypatch.delenv(service.RESEARCH_ENABLED_VAR)
    assert service.research_enabled() is False
    # Cached research is served with the switch off...
    assert service.request_research(db, company_name="Open Co", trigger="on_demand").id == done.id
    # ...a new run is refused before anything is written...
    with pytest.raises(service.ResearchDisabled):
        service.request_research(db, company_name="Shut Co", trigger="on_demand")
    assert db.session.query(CompanyResearchRun).count() == 1
    assert len(research_fake.requests) == 1
    # ...unless the caller is the internal batch prefill.
    view = service.request_research(
        db, company_name="Shut Co", trigger="batch", allow_when_disabled=True
    )
    assert store.latest_research_run(db, view.company_id).status == "done"
    assert len(research_fake.requests) == 2
    for value in ("1", "true", "YES", " on "):
        monkeypatch.setenv(service.RESEARCH_ENABLED_VAR, value)
        assert service.research_enabled() is True
    for value in ("0", "false", "", "off"):
        monkeypatch.setenv(service.RESEARCH_ENABLED_VAR, value)
        assert service.research_enabled() is False


def test_research_asks_for_high_effort_and_the_opus_5_5_default(ctx, no_keys, monkeypatch):
    """Regression (2026-10-14): Opus 5.5 defaults to effort "medium" where Opus 5,
    the model the method was validated on, defaulted to "high". Research must ask
    for "high" explicitly or it quietly runs at less depth."""
    db = ctx
    research_fake = FakeResearchClient(_research_message(), _research_message())
    _install(monkeypatch, research_fake, FakeScorerClient())

    service.request_research(db, company_name="Effort Co", trigger="on_demand")
    (request,) = research_fake.requests
    assert request["output_config"] == {"effort": "high"}
    assert request["model"] == "claude-opus-5-5"


def test_blocked_domains_reach_both_tools_and_the_run_card(ctx, no_keys, monkeypatch):
    db = ctx
    from model import CompanyResearchRun

    research_fake = FakeResearchClient(_research_message(), _research_message())
    _install(monkeypatch, research_fake, FakeScorerClient())
    monkeypatch.setenv(research.BLOCKED_DOMAINS_VAR, " glassdoor.com, https://Indeed.com/ ,glassdoor.com,")
    assert research.blocked_domains() == ["glassdoor.com", "indeed.com"]

    run = service.request_research(db, company_name="Blocked Co", trigger="on_demand")
    (request,) = research_fake.requests
    tools = [t for t in request["tools"] if "blocked_domains" in t]
    assert len(tools) == 2  # web search and web fetch
    assert all(t["blocked_domains"] == ["glassdoor.com", "indeed.com"] for t in tools)
    card = _internal(db.session.get(CompanyResearchRun, run.id))
    assert card["blocked_domains"] == ["glassdoor.com", "indeed.com"]

    monkeypatch.delenv(research.BLOCKED_DOMAINS_VAR)
    run = service.request_research(db, company_name="Open Web Co", trigger="on_demand")
    request = research_fake.requests[-1]
    assert all("blocked_domains" not in t for t in request["tools"])
    assert _internal(db.session.get(CompanyResearchRun, run.id))["blocked_domains"] == []
