/**
 * useWP — the stored result of the original 12-question Work Pulse, read-only.
 *
 * That instrument was retired on 2026-10-02 (the 24-item `core` instrument has
 * served /work-pulse since 2026-08-19). Its answer side — the sessionStorage
 * draft, `setAnswer`, `isComplete`, `resetWP` — went with WPStepper and
 * `wpQuestions.ts`, because nothing can submit a sitting any more: every write
 * door on the server answers 410.
 *
 * What stays is the cache observer two screens share: `cachedResult` lives in
 * the TanStack Query cache under `workPulseResultKeys.result()`, the key
 * `useWorkPulseResult` fetches `GET /me/assessments/work_pulse/result` into.
 * This hook never fetches (`skipToken`); `setCachedResult` writes that key
 * directly, which IntelligencePage uses to prime it for WorkPulseResultsPage.
 * Nothing is persisted to sessionStorage: the server copy is authoritative.
 */
import { skipToken, useQuery, useQueryClient } from "@tanstack/react-query";

import { workPulseResultKeys } from "./useWorkPulseResult";

export type WpApiResponse = {
  narrative: string;
  emerging_signals: { title: string; description: string }[];
  archetype: string;
  archetype_description: string;
};

export type WpState = {
  cachedResult: WpApiResponse | null;
};

export function useWP() {
  const queryClient = useQueryClient();

  // Observer only: `skipToken` means this never issues a request. Data appears
  // here when `useWorkPulseResult` fetches the key or `setCachedResult` writes it.
  const cachedQuery = useQuery<WpApiResponse>({
    queryKey: workPulseResultKeys.result(),
    queryFn: skipToken,
  });

  function setCachedResult(result: WpApiResponse) {
    queryClient.setQueryData(workPulseResultKeys.result(), result);
  }

  const state: WpState = { cachedResult: cachedQuery.data ?? null };

  return { state, setCachedResult };
}
