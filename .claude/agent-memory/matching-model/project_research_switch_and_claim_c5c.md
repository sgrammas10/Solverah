---
name: research-switch-and-claim-c5c
description: 2026-10-14 C5c UNCOMMITTED -- SOLVERAH_COMPANYLENS_RESEARCH_ENABLED is the public switch (default OFF, 503 research_disabled), atomic run claim, finish-only-from-running + late-finish discard, SOLVERAH_RESEARCH_BLOCKED_DOMAINS plumbing, provider_unavailable as a problem document, CLI --allow-when-disabled
metadata:
  type: project
---

2026-10-14, lane C5c (fix chunk on C5, orchestrator-dispatched). UNCOMMITTED. Lane DB
for the cluster: solverah_c3.

**The switch.** `service.research_enabled()` reads `SOLVERAH_COMPANYLENS_RESEARCH_ENABLED`
at call time (1/true/yes/on), default OFF. The KEY is not the switch: Sebastian decided
2026-10-13 that review-site collection waits for attorney review before research is public.
Off: `request_research` raises `ResearchDisabled` only when a NEW run is needed
(`allow_when_disabled=True` bypasses -- the CLI's `--allow-when-disabled`); cached and
in-flight runs are always returned. Route order: `find_company` (no create) -> existing
run? -> switch -> providers -> daily budget -> `resolve_company` (create) -> request.
A refused request writes nothing, not even the Company row. Postings are never gated.
Tests set the switch ON via autouse fixtures in test_company_research_pipeline.py and
test_company_lens_api.py -- a new test file that starts a run needs the same.

**Ownership of a run.** `store.mark_research_run_running` = one conditional UPDATE
(`WHERE status='queued' RETURNING`), None for the loser; `run_research_job` claims first
and returns the row untouched when the claim fails (a `running` row is someone else's --
it used to proceed). `finish_research_run` is `WHERE status='running'` and returns None
when the row was reaped; `_late()` then discards the run's output
(`store.discard_research_run_output`: items, scores, links, linked records), rebuilds the
shared read from the latest done run, and records `late_finish` (cost, attempted status,
items_discarded) in `diagnostics_internal`. An ownership re-check (`_owned`) sits between
the research turn and the first write. Residual window: a reap during scoring is handled
by the discard path (tested). A run finishes ONLY from running: tests that finish a
queued row must `mark_research_run_running` first.

**Blocked domains.** `research.blocked_domains()` parses `SOLVERAH_RESEARCH_BLOCKED_DOMAINS`
(comma list, lower-cased, scheme stripped, de-duped) and passes it to `run_research_call`;
the run card carries `blocked_domains`. The attorney decides the real list.

**Wire.** Both 503s on the research door and the posting door are problem documents now
(`research_disabled`, `provider_unavailable`), `503: PROBLEM_RESPONSE_MODEL` in
`@document`; backend-platform captures them in A33. The dead `posting_id must be an
integer` 422 branch in `company_read` is gone (query enforcement answers first).

**Not done / open:** posting jobs have no `running` status (pending/scored/failed), so an
atomic claim there needs a vocabulary change (schema-steward) -- not needed today because
nothing re-dispatches postings. `sweep_research_runs` still re-dispatches stale queued rows
while the switch is off (such rows only exist if queued while enabled or by the CLI).
`solverah.errors` logs every 5xx ApiError with a traceback, so `research_disabled` is an
ERROR-level log line per hit -- backend-platform's call.

**Why:** ops-crons' 2026-10-14 findings (double paid run via sweep + web pool, reaped-row
overwrite, key-as-switch, stale docstrings). **How to apply:** deploy day sets the switch,
not just the key; `flask companies research --allow-when-disabled` is the prefill path.
