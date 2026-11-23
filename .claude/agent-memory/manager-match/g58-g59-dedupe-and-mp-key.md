---
name: g58-g59-dedupe-and-mp-key
description: 2026-11-23 fixes (uncommitted when written) — G58 server-side join of an in-flight scoring job with the same answers; G59 mp_answers keyed per user like mm_answers
metadata:
  type: project
---

**G58 (S14.3a): fixed on the server, not the client.** `scoring_jobs.create_assessment` (core-assessments' file, edited on the orchestrator's brief) returns the user's newest queued/running job of the same kind whose payload matches (answers compared order-insensitively) instead of queuing a new one. Same 202 body shape. Terminal jobs are never joined (their payload is emptied by `_finish`), so retry-after-failure still scores; different answers still queue; ownerless `wpll` is not deduped. ManagerMatchPage was left alone: its reload path (404 then enqueue) now lands on the existing handle.
Known gap: two truly concurrent POSTs can still both insert (no lock). The 202 `status` can now be "running", while the schema description still says "Always queued". The type is `str`, so the wire is unchanged and openapi was not regenerated.

**G59 (S14.7):** `useMP` uses `mp_answers:<userId>` and drops the legacy bare key on sight, mirroring `useMM`. `draftStorage.ts` needed no edit because its `mp_answers` prefix already matches the suffixed key.

**Why:** these were sprint gaps found by reading the source.
**How to apply:** if a third job-scored kind gets an owner, it inherits the dedupe. If someone reports a stale narrative after a quick retake, check whether the answers were identical first.
