---
name: g47-was-a-misread
description: G47 ("Try again" on Work Pulse shows no activity) is false in source -- React Query v5 resets an errored query with no data to pending when a refetch starts
metadata:
  type: project
---

React Query 5.x `fetchState`: when a fetch starts and `data === undefined`, it sets `error: null, status: "pending"`. So `useAssessment().loadError` is null for the whole retry and WorkPulsePage shows "Loading…". WorkPulseResultsPage's `isError && isFetching` guard is redundant for the same reason. Pinned by a real-hook test in useAssessment.test.tsx (2026-11-23); no code change made.

**Why:** the gap was found by reading WorkPulseResultsPage's comment, not in a browser.

**How to apply:** a "the error survives a refetch" claim only holds once the query HAS data (e.g. placeholderData). Check the library before adding an isFetching guard.
