---
name: company-research-pipeline-c5
description: 2026-10-13 C5 + C5b (six-trait build) UNCOMMITTED -- solverah/services/company_research/ (research -> score -> aggregate -> records, job postings, dispatch, CLI); the v2 prompt versions, agg-v2 rules, the review fixes F1-F14, provisional Julie defaults, the no-live-call rule, the cost command, and the infra title trap
metadata:
  type: project
---

2026-10-13, lanes C5 and C5b (review fixes) of the CompanyLens six-trait build (plan:
docs/superpowers/plans/2026-10-13-companylens-six-trait.md). UNCOMMITTED; orchestrator
reviews. NO LIVE PAID CALL HAS BEEN MADE: Sebastian has no Anthropic key yet and spend
needs his go. Every test fakes the two clients at `solverah.infra.llm.get_research_client`
/ `get_scorer_client` (monkeypatch the module attribute; the package calls them through
`llm.`), real DB solverah_c3 (pytest).

**Shape.** `research.py` (Anthropic turn, max_tokens 64k -> last JSON object with an
`items` list anywhere in the text -> per-item verification against the item's OWN
source's citations -> paraphrase gate -> run card) -> `score_items.py` (OpenAI structured
outputs, one object per item; rubric = IMPORTED `causal_graph.scorer_pipeline.build_rubric_text`
on the package's FROZEN COPY `anchors_v3_1.json`, both pinned by sha256 in
test_company_research_pipeline; company name/domain scrubbed to "the company" in the
scorer input only) -> `aggregate.py` (pure `aggregate_dimension`; `aggregate_company_report`
reads ONE research run: the one given, else the latest `done`) -> `service.py`. Versions:
`cl-research-v2`, `cl-score-v2` (+ `RUBRIC_TEXT_SHA256`), `cl-posting-v2`, `agg-v2-2026-10-13`.

**Rules after C5b (constants.py).**
- Verified = citations from the item's URL (search citation by URL; char_location by
  title through the FETCHED source) cover >= 90% of the excerpt's words in runs of 3+,
  every double quote in the excerpt is in the cited text, URL fetched-or-cited. Search
  citations' cited_text is capped at 150 chars by the API, so a long excerpt verifies
  only off a fetched page -- intended (v4.11 rule 2).
- Paraphrase gate: run limit min(7, words/2) vs the excerpt AND every same-URL citation
  (postings: vs the whole paste), <= 35% of the excerpt's trigrams reused (binds before
  the run cap on short excerpts: a 7-run in 16 words is 5/14), any quotation mark rejects
  (apostrophes inside/after words are fine).
- Fail the run `research_unverified` when candidates > 0 and nothing kept, or zero
  citations; cost recorded; run card persisted to `company_research_run.diagnostics_internal`
  (JSONB, deferred, INTERNAL: raw text + cited_text; guard test names it; the CLI summary
  reports counts only). NAME DEVIATION from the brief ("diagnostics"): bare "diagnostics"
  already appears in devfit/path modules, so the literal-scan guard needed the `_internal` suffix.
- Gate 2/5: `company_evidence_item.speaker`, `evidence_item_score.confidence` (stored,
  never weighted). Known needs >= 1 INDEPENDENT item (employee_review/news, speaker not
  employer/CEO/...) among the SUPPORTING items (larger side + 0.5s); only independent
  items count toward recency; employee_review with an employer-reply speaker is retagged
  careers_page at research time. POSTING records are aggregated with
  `independent_required=False` (every item is the posting's words) -- my call, flagged.
- Split explained by scope TYPE only, every group >= 2. Time split with >= 3 recent
  independent items -> KNOWN in the recent direction with split_explained_by='time'
  (provisional ask 4); this needed the CHECK relaxed: `ck_ctrait_split_not_unknown`
  (`status <> 'unknown'`) replaces `ck_ctrait_split_only_mixed` in model + migration
  (amended IN PLACE, unreleased). C6 reads split_explained_by -- tell it a known record may carry 'time'.
- F8: careers_page dated == retrieval day -> access-dated; job_posting whose URL was
  FETCHED -> dated at retrieval (verified open); cited-only postings keep the model's date.
- Provisional Julie asks in constants.py: 1 mixed count rule, 2 no weighting, 3 company-only
  never known, 4 time split, 5 no clamp.

**Trap found 2026-10-13 (FIXED: llm-features resolves char_location url from document_index; C9 matches by url):** infra `_sources` keeps a
URL's FIRST-SEEN title; a page listed by search then fetched keeps the search title, so its
char_location citations (fetched document title) match nothing and its items drop
`no_citation_from_source`. Live run symptom: fetched pages yield 0 items while search-cited
ones pass. Fix belongs in solverah/infra/llm/research.py (prefer the fetch title, or expose
`document_index`).

**Design calls kept from C5.** Dispatch (`jobs.py`): broker -> enqueue; eager+TESTING ->
inline; eager+not testing = PRODUCTION -> 2-thread pool. `request_research` returns the
run AS QUEUED even when eager ran it inline; cache = latest `done` <= 90 days unless `force`;
providers checked before a row is written. TRAP: tests/test_company_evidence_internal.py
reads test files too -- never spell either internal column in a test; read a stored value
reflectively (`_internal` helper: the model's one deferred column) or prove through the
scorer fake's prompt. Never add a test file to ALLOWED.

**Cost command (once ANTHROPIC_API_KEY + OPENAI_API_KEY are in .env):**
`flask companies research "Company A" "Company B" "Company C"` from the repo root, local
5433 DB migrated to head; one JSON line per company (status, cost_usd, candidates,
citations, dropped counts, items, records) and a total line. `--force` ignores the cache.

**Why:** PRODUCT_DECISIONS section 2 pipeline calls; research-ground-truth's 2026-10-13
fidelity review (F1-F14) gates the first live run. **How to apply:** C6 calls
`service.request_research(...)`, `submit_job_posting(...)`, `aggregate_company(db,
company_id)` (latest done run); reads records through the store only. A rubric or anchors
change = new copy + both hashes + SCORING_PROMPT_VERSION bump, deliberately.
