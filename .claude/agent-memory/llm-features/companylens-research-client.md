---
name: companylens-research-client
description: Anthropic research client + OpenAI scorer client built 2026-10-13 for CompanyLens (C5) — model ids and why, tool versions, pricing, ZDR, open threads
metadata:
  type: project
---

Built 2026-10-13 (orchestrator dispatch, uncommitted): `get_research_client()`,
`get_scorer_client()`, `LLMProviderUnavailable` in `solverah/infra/llm/__init__.py`;
`run_research_call()` + `estimate_research_cost_usd()` in `solverah/infra/llm/research.py`;
tests `tests/test_llm_research_client.py`. `anthropic==1.13.0` pinned (1.x uses httpx2,
same as openai 3.6.0; resolves clean in solverah-venv311, which is actually Python 3.13).

**Model choice:** research default `claude-opus-5` (the claude-api skill's mandated default;
exact id, no date suffix exists). Claude Opus 5.5 (`claude-opus-5-5`) IS live in the pricing
page ($4/$20 vs $5/$25) but the skill says use it only when the user names it — offered to
Sebastian as a cost decision, not adopted. Scorer default `gpt-5.5-2026-04-23` (the snapshot
scorer_pipeline validated). Scorer client gets 300 s / 3 retries because get_openai_client's
60 s is sized for gpt-4o-mini and would time out a reasoning model.

**Why:** Sebastian's 2026-10-13 decision: research on Anthropic (the packets were validated
browsing with Claude), scoring stays on OpenAI.

**How to apply:**
- Tool versions `web_search_20260318` / `web_fetch_20260318` (live docs newer than the skill's
  20260209). Dynamic filtering → NOT ZDR-eligible unless `allowed_callers: ["direct"]`.
- `fallbacks: "default"` + beta `server-side-fallback-2026-07-01` is on; usage is split per
  model from `usage.iterations` when a fallback ran (top-level usage covers only the final attempt).
- Pricing (2026-10-13): Opus 5 and 4.8 $5 in / $25 out / $6.25 5m-write / $0.50 read per MTok;
  web search $10 per 1,000; web fetch and its code execution free beyond tokens.
- `cited_text` is verbatim third-party text: must never reach a route (GAP-14).
- Open threads: docs/LLM_ARCHITECTURE.md not yet updated for the two new clients;
  config.py `providers` redaction has no anthropic entry (backend-platform's file).

**Re-verified 2026-10-13 (same day, second pass):** a research-ground-truth review
flagged that the *bundled* claude-api skill docs only list `web_search_20260209` as
the dynamic-filtering search version, with `web_fetch_20260318` confirmed — i.e. the
skill's cached knowledge is stale, not research.py. Live WebFetch of
platform.claude.com's web-search-tool and web-fetch-tool pages confirmed both
`web_search_20260318` and `web_fetch_20260318` are real, current (latest) versions,
need no beta header, and add `response_inclusion` over `_20260209`. research.py's
strings were already correct — no bug. Still added
`SOLVERAH_RESEARCH_SEARCH_TOOL` / `SOLVERAH_RESEARCH_FETCH_TOOL` env overrides
(`web_search_tool_type()` / `web_fetch_tool_type()`, read per call) as cheap
insurance against a future docs/version drift landing on deploy day as a 400
instead of a config edit. Also raised `DEFAULT_MAX_TOKENS` 32_000 → 64_000 (the
call streams, so no HTTP-timeout risk). Lesson: when a ground-truth review cites
"the bundled docs," check whether it means the *skill's* cached copy (can lag) vs.
a live WebFetch — they disagreed here and the live fetch wins.

**Fixed 2026-10-13 (third pass, orchestrator dispatch): the title-mismatch citation
bug matching-model's C5b found.** `char_location` citations carry no URL at all —
only `document_index` + `document_title` (confirmed against the live
web-fetch-tool docs' example response). `document_index` counts *successfully
fetched* documents in the order they appear in the turn — same convention as a
directly-attached PDF's citations. `_fetched_documents()` (new) builds that list;
`_citations()` now resolves a `char_location` citation's `url` through it instead
of leaving it `None`. `ResearchCitation.document_index` is a new field (default
`None`) recording which position it resolved against.

Also: `ResearchSource.title` used to keep whichever title was seen FIRST (usually
search's), even after a fetch of the same URL returned a different document
title — so a `char_location` citation (which always carries the *fetched* title)
matched nothing when search and fetch titles differed, and C5's
`_citations_for` dropped the item as `no_citation_from_source`. Now a fetch's
document title always overrides `title`. `ResearchSource.search_title` is new
(default `None`): the original search-listed title, kept for a caller that wants
both. Both new fields are additive (dataclass, defaulted) — nothing renamed.

**Hand-off to matching-model:** `_citations_for` in
`solverah/services/company_research/research.py` can now match a `char_location`
citation by URL directly (`cite.url == url`) instead of by title through
`source.title` — simpler and no longer sensitive to a title mismatch. The title
match still works today (this fix makes `source.title` agree with the fetched
title), but the URL match is the more direct fix the module's own `_citations_for`
docstring asked for. Not changed here — it's matching-model's file.

Tests: `tests/test_llm_research_client.py` (mine) got one new regression test
(`test_char_location_resolves_to_the_fetched_url_even_when_search_title_differs`)
plus updates to the two assertions that construct `ResearchCitation`/`ResearchSource`
tuples with the new fields. `tests/test_company_research_pipeline.py` (matching-model's,
not edited) stays green unchanged — its one test that exercises title matching
(`test_review_f1_citations_must_come_from_the_items_own_fetched_or_cited_source`)
never hit the bug: that fixture's careers page is fetched directly, never
search-listed, so it only ever had one title. Full cluster: 59 passed on a scratch
DB (`solverah_c5llm` — `solverah_c5` was locked by a concurrent run at the time;
a stray scratch DB may be worth dropping later).
