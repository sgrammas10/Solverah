/**
 * useManagerMatchResult.ts — the stored ManagerMatch result, as one query.
 *
 * `GET /me/assessments/manager_match/result` was hand-fetched inside
 * ManagerMatchResultsPage with its own `useState` loading/error machine, next
 * to a module-level singleton in `useMM` holding the same data. This is the
 * single query both read now; the singleton is gone because the query cache is
 * the singleton, keyed by `managerMatchResultKeys.result()`.
 *
 * A scoring job succeeding writes its result into this key (see `useMM`'s
 * `setCachedResult`, called from ManagerMatchPage), so ManagerMatchResultsPage
 * mounts with the fresh result already in cache and issues no request.
 *
 * Retry behaviour is the shared default from `queryClient.ts` on purpose: a
 * 429/5xx gets `shouldRetry`'s two bounded retries, which the hand-rolled
 * fetch never had. That is safe here because Phase 3a removed every commit
 * from GET handlers — a retried read re-reads and nothing else. The 404 for
 * "no result yet" is a client error and surfaces immediately, which
 * ManagerMatchResultsPage relies on for its redirect back to the instrument.
 *
 * `throwOnError` stays false (the default): the consumer owns a real error UI
 * with a retry button rather than escalating to RouteErrorBoundary.
 */
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "../auth";
import { ApiError } from "../../shared/api/apiError";
import type { MMResult } from "./useMM";

/**
 * Query keys for the stored ManagerMatch result.
 *
 * `all` is the invalidation handle; `result()` is the one query under it.
 */
export const managerMatchResultKeys = {
  all: ["managerMatchResult"] as const,
  result: () => ["managerMatchResult", "result"] as const,
};

/**
 * The stored ManagerMatch result, with the loading and error state of
 * fetching it.
 *
 * `enabled` lets the consumer keep the request from firing when it already
 * has the answer — a fresh result in the cache, or the copy stored on the
 * profile document.
 */
export function useManagerMatchResult(options: { enabled?: boolean } = {}) {
  const { fetchWithAuth } = useAuth();

  return useQuery({
    queryKey: managerMatchResultKeys.result(),
    queryFn: () =>
      fetchWithAuth<MMResult>("/me/assessments/manager_match/result", { method: "GET" }),
    enabled: options.enabled ?? true,
  });
}

/**
 * True when `error` is this endpoint's "no ManagerMatch result yet" answer.
 *
 * Decided by the 404 status alone. It used to be a substring match on the
 * message ("No ManagerMatch result found"), which is prose: rewording the
 * server's sentence would have silently turned "never finished" into the
 * generic error card. The route has exactly one 404, so the status is the
 * whole signal.
 */
export function isNoManagerMatchResult(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}
