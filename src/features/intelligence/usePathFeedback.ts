/**
 * usePathFeedback.ts — the inline card feedback loop and the deep fit on click.
 *
 * Two mutations and one query, all synchronous on the server and all returning
 * what the screen needs rather than a handle to poll:
 *
 *   POST   /me/path-feedback         one judgement, then the re-ranked list
 *   DELETE /me/path-feedback         clear every judgement, then the default list
 *   POST   /me/path-fit/{onet_code}  the Tier-2 analysis of one occupation
 *
 * ── WHY NONE OF THESE IS A JOB/POLL PAIR ───────────────────────────────────
 *
 * `POST /me/path-suggestion-jobs` is queued because its fan-out is slow. These
 * are not: a re-rank is one matrix product plus, at most, a narrative for the
 * two to six cards that are new, and a deep fit is one embeddings batch. A job
 * handle the client had to poll would cost more round trips than it saved.
 *
 * ── WHY THE DEEP FIT IS A QUERY AND NOT A MUTATION (W-9) ───────────────────
 *
 * It was a `useMutation`, which has two consequences and both of them are what
 * Sebastian's first click-through complained about ("the loading of a position
 * when i click on it takes so long to load"): the same card re-requests on
 * every open, and nothing can be warmed before a click because a mutation has
 * no cache to warm. W-9 removed the four live O*NET calls on the server side;
 * this is the client half.
 *
 * As a query keyed by occupation, reopening a card is free and the three cards
 * on screen can be prefetched — see `usePrefetchPathFits`. POST is still the
 * verb: it is a per-click provider spend with a stored side effect, and a GET
 * would sit outside the CSRF guard every other write on this blueprint is
 * behind. A "query" that POSTs is unusual and is deliberate; TanStack's cache
 * is what is being used here, not its idea of what a read is.
 *
 * ── NOTHING HERE RETRIES ───────────────────────────────────────────────────
 *
 * The global mutation default is `retry: false`, and `retry: false` is set
 * explicitly on the query against the client default (`shouldRetry` retries a
 * 429 or a 5xx twice). All three carry a rate limit precisely because they can
 * reach a provider, and a client-side retry spends somebody's budget on a
 * request the user did not make twice.
 */
import { useCallback } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import { useAuth } from "../auth";
import type { components } from "../../shared/api/schema";

type PathFeedbackResponse = components["schemas"]["PathFeedbackResponse"];
type PathFitResponseSchema = components["schemas"]["PathFitResponse"];

/** The three verdicts a card can carry. Mirrors the server's closed vocabulary. */
export type PathVerdict = "too_similar" | "interesting" | "not_for_me";

export const PATH_VERDICTS: readonly PathVerdict[] = [
  "interesting",
  "too_similar",
  "not_for_me",
] as const;

/** Every judgement standing for this user, as `onet_code -> verdict`. */
export type PathFeedbackMap = Record<string, PathVerdict>;

export type PathFeedbackResult = PathFeedbackResponse;
export type PathFit = PathFitResponseSchema;

/**
 * How long the deep-fit panel expects to wait, in milliseconds.
 *
 * Sized to the **common** case rather than the best one, and 850 survived W-9
 * for a different reason than it was chosen for. It used to be the 844 ms of a
 * card another user had already opened, against 2.4 s cold and 12 ms stored.
 * W-9 removed the four O*NET calls, and what is left of an unstored click is
 * the one embeddings batch: measured 2026-09-22 against the real corpus, median
 * **710 ms**, range 560-1,958 ms, and 18 ms when this user's texts are already
 * embedded. So the spinner is still sized to a real middle, and a panel that
 * was prefetched shows no spinner at all.
 *
 * Exported so the panel and its test agree on the number rather than each
 * hard-coding it.
 */
export const PATH_FIT_EXPECTED_MS = 850;

/** `POST /me/path-feedback` — store one judgement, get the re-ranked list back. */
export function useRecordPathFeedback() {
  const { fetchWithAuth } = useAuth();

  return useMutation({
    mutationFn: (body: { onet_code: string; verdict: PathVerdict }) =>
      fetchWithAuth<PathFeedbackResponse>("/me/path-feedback", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

/**
 * `DELETE /me/path-feedback` — clear every judgement, get the default list back.
 *
 * A DELETE that returns a body, and the body is the point: the alternative is a
 * 204 and a second round trip to find out what the user is now looking at.
 */
export function useClearPathFeedback() {
  const { fetchWithAuth } = useAuth();

  return useMutation({
    mutationFn: () =>
      fetchWithAuth<PathFeedbackResponse>("/me/path-feedback", {
        method: "DELETE",
      }),
  });
}

/** The deep fit's cache keys. One entry per occupation, never a shared one. */
export const pathFitKeys = {
  all: ["path-fit"] as const,
  one: (onetCode: string) => ["path-fit", onetCode] as const,
};

/**
 * How long a fetched deep fit is served without going back to the server.
 *
 * `Infinity`, and it is the page, not this number, that keeps that honest. The
 * server invalidates its stored `path_fits` rows whenever skills, title or
 * career status change, but the `QueryClient` is NOT replaced by a navigation
 * -- it lives as long as the SPA does -- so a user who edits their profile and
 * comes back would otherwise be served the analysis from before the edit.
 * `PathIntelligencePage.fetchSuggestions` removes every `pathFitKeys.all`
 * entry on each fresh scoring, which is every point at which the profile can
 * have changed under this page. Between two scorings nothing can change the
 * answer and nothing a refetch could discover.
 */
const PATH_FIT_STALE_TIME_MS = Infinity;

/**
 * How long an unopened prefetch survives with nobody watching it.
 *
 * The default `gcTime` is 5 minutes, which would quietly throw away the three
 * warmed cards of somebody who reads the list before clicking. Thirty minutes
 * is longer than any session spent on one shortlist.
 */
const PATH_FIT_GC_TIME_MS = 30 * 60_000;

/** `AuthContext.fetchWithAuth`, named so the shared options below can take it. */
type Fetcher = <T = unknown>(endpoint: string, options?: RequestInit) => Promise<T>;

/**
 * The one definition of the request, shared by the hook and the prefetcher.
 *
 * Two call sites that each spelled out the path, the verb and the cache policy
 * would be two chances to disagree — and the disagreement that matters is
 * `staleTime`, because a prefetch stored under different terms from the one the
 * click reads is a prefetch the click ignores.
 */
function pathFitOptions(fetchWithAuth: Fetcher, onetCode: string) {
  return {
    queryKey: pathFitKeys.one(onetCode),
    queryFn: () =>
      fetchWithAuth<PathFitResponseSchema>(`/me/path-fit/${onetCode}`, {
        method: "POST",
      }),
    staleTime: PATH_FIT_STALE_TIME_MS,
    gcTime: PATH_FIT_GC_TIME_MS,
    retry: false as const,
  };
}

export interface UsePathFitResult {
  /** The analysis, or null while there isn't one. */
  data: PathFit | null;
  /** Nothing to show yet and something is being done about it. */
  isPending: boolean;
  /** A *settled* failure. A retry in flight is `isPending`, not this. */
  isError: boolean;
  error: unknown;
  /** Ask again. The panel's "Try again". */
  retry: () => void;
}

/**
 * `POST /me/path-fit/{onet_code}` — the Tier-2 analysis of one occupation.
 *
 * Pass the open card's code, or null when no card is open: the request is made
 * only while a panel is on screen. No request body — the analysis reads the
 * caller's stored profile.
 *
 * **Closing a card does not cancel anything and does not clear anything.**
 * There is nothing to clear: each occupation has its own cache entry, so the
 * next card cannot inherit this one's error (which is what the old
 * `mutation.reset()` on close was for). And cancelling would be actively wrong
 * now — a close could tear down a prefetch that a different card is waiting on.
 *
 * **A settled error and a retry in flight are told apart**, because a prefetch
 * that failed leaves an error in the cache; opening that card refetches, and
 * without the distinction the panel would flash the old failure for a moment
 * before the new attempt resolved.
 */
export function usePathFit(onetCode: string | null): UsePathFitResult {
  const { fetchWithAuth } = useAuth();

  const query = useQuery({
    ...pathFitOptions(fetchWithAuth, onetCode ?? ""),
    enabled: Boolean(onetCode),
    // A failed deep fit is a panel that explains itself, never a screen: the
    // other nine suggestions are still good ones.
    throwOnError: false,
  });

  const { refetch } = query;
  const retry = useCallback(() => {
    void refetch();
  }, [refetch]);

  const settledError = query.isError && query.fetchStatus === "idle";
  return {
    data: query.data ?? null,
    isPending: query.data === undefined && !settledError,
    isError: settledError,
    error: query.error,
    retry,
  };
}

/**
 * Warm the deep fits of the cards that are on screen, before they are clicked.
 *
 * The three rules this follows, and each is a way it could go wrong:
 *
 * * **Silent.** A refused prefetch (a 429, a 5xx) renders nothing, logs
 *   nothing, and changes no state the user can see. They did not ask for it;
 *   being told it failed would be worse than not having had it.
 * * **Once.** A code with any cache entry — warm, in flight, or failed — is
 *   skipped. A re-render with the same list must not re-request, and a failed
 *   prefetch must not be retried behind the user's back; the click that follows
 *   refetches through the normal path with its own error handling.
 * * **Never in front of the user.** The caller fires this from an effect, after
 *   the list has rendered, and nothing here is awaited.
 *
 * The server upserts `path_fits`, so a prefetch followed by a click is still
 * one stored row — `tests/e2e/path_wants.spec.ts` asserts exactly that.
 */
export function usePrefetchPathFits(): (onetCodes: string[]) => void {
  const { fetchWithAuth } = useAuth();
  const queryClient: QueryClient = useQueryClient();

  return useCallback(
    (onetCodes: string[]) => {
      for (const onetCode of onetCodes) {
        if (!onetCode) continue;
        if (queryClient.getQueryState(pathFitKeys.one(onetCode))) continue;
        void queryClient
          .prefetchQuery(pathFitOptions(fetchWithAuth, onetCode))
          .catch(() => {});
      }
    },
    [queryClient, fetchWithAuth],
  );
}
