/**
 * useWorkPulseResult.ts — the stored Work Pulse result, as one query.
 *
 * `GET /me/assessments/work_pulse/result` was hand-fetched in two places —
 * WorkPulseResultsPage and IntelligencePage — each with its own `useState`
 * loading/error machine and its own copy of the response. This is the single
 * query both consume; the key means the second screen to mount gets the first
 * screen's answer instead of a second request.
 *
 * Retry behaviour is the shared default from `queryClient.ts` on purpose: a
 * 429/5xx gets `shouldRetry`'s two bounded retries, which the hand-rolled
 * fetches never had. That is safe here because Phase 3a removed every commit
 * from GET handlers — a retried read re-reads and nothing else. A 404 (no stored
 * legacy result; the 12-question kind is retired, 2026-10-02) is a client error
 * and surfaces immediately, which WorkPulseResultsPage relies on to redirect to
 * /work-pulse instead of showing a read-only view.
 *
 * `throwOnError` stays false (the default): both consumers own a real error
 * UI with a retry button, unlike the useProfile() consumers whose failures
 * escalate to RouteErrorBoundary.
 */
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "../auth";
import type { WpApiResponse } from "./useWP";

/**
 * Query keys for the stored Work Pulse result.
 *
 * `all` is the invalidation handle; `result()` is the one query under it.
 * A scoring job succeeding writes the fresh narrative here (see
 * WorkPulseResultsPage) so a later mount does not serve the pre-retake copy.
 */
export const workPulseResultKeys = {
  all: ["workPulseResult"] as const,
  result: () => ["workPulseResult", "result"] as const,
};

/**
 * The stored Work Pulse result, with the loading and error state of fetching it.
 *
 * `enabled` lets a consumer keep the request from firing when it already has
 * the answer (the sessionStorage cache in `useWP`) or when the user has not
 * completed the instrument — a fetch then would only 4xx.
 */
export function useWorkPulseResult(options: { enabled?: boolean } = {}) {
  const { user, fetchWithAuth } = useAuth();

  return useQuery({
    queryKey: workPulseResultKeys.result(),
    queryFn: () =>
      fetchWithAuth<WpApiResponse>("/me/assessments/work_pulse/result", { method: "GET" }),
    enabled: (options.enabled ?? true) && Boolean(user),
  });
}
