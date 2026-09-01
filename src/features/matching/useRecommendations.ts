/**
 * useRecommendations.ts — the recommendations list, shared by Feed and
 * SearchResults instead of each holding its own `useState` copy.
 *
 * Paginated since Phase 1b: `{ data, next_cursor }`. The list is always
 * empty today -- the ML pipeline behind it was replaced by the agent and
 * the Groq-backed successor is not wired up -- so there is no cursor to
 * follow yet. Reading `data` now means the day it returns rows is not
 * the day this file changes.
 *
 * Failed fetches gain the bounded retries from `queryClient.ts` on purpose
 * (safe: Phase 3a removed every commit from GET handlers). After they are
 * exhausted, `data` stays undefined and both consumers render the same empty
 * state the hand-rolled `setJobs([])` produced.
 */
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "../auth";

export const recommendationKeys = {
  all: ["recommendations"] as const,
  list: () => ["recommendations", "list"] as const,
};

export function useRecommendations() {
  const { fetchWithAuth } = useAuth();

  return useQuery({
    queryKey: recommendationKeys.list(),
    queryFn: async () => {
      const res = await fetchWithAuth<{ data: any[]; next_cursor: string | null }>(
        "/me/recommendations",
        { method: "GET" }
      );
      return res.data ?? [];
    },
  });
}
