/**
 * usePathSuggestionJob.ts — path suggestions, as a mutation + a poll.
 *
 * Phase 3c's asynchronous counterpart to ``GET /me/path-suggestions``, which
 * fans out to O*NET and OpenAI *inside the request*. ``POST
 * /me/path-suggestion-jobs`` queues that fan-out and answers ``202`` with a job
 * handle; ``GET /me/path-suggestion-jobs/{job_id}`` is polled until terminal.
 *
 * Same shape as ``useScoringJob``/``useResumeParseJob`` and for the same
 * reasons; the differences are the two below.
 *
 * ``result`` on a succeeded job is byte-for-byte what the synchronous ``GET``
 * would have returned -- the job runs the same service function -- so a caller
 * routes it exactly where it routed that response, with no branch of its own.
 *
 * The job also warms ``path_cache`` on its way through, which is why the
 * synchronous ``GET`` is left in place rather than deleted alongside the call
 * site: it is a cache hit immediately after a job succeeds, and a client
 * mid-migration can poll the job and then read the old endpoint without paying
 * for the scoring twice.
 *
 * ── ONE LIMIT THAT THE SYNCHRONOUS GET DOES NOT HAVE (A19) ──────────────────
 *
 * ``POST /me/path-suggestion-jobs`` carries a rate limit its ``GET`` did not
 * need. The ``GET`` was self-limiting: the caller held the connection for the
 * whole fan-out, and a repeat inside the cache window reached no provider.
 * Neither property survives an enqueue that returns in milliseconds. Nothing
 * here should retry the POST on the caller's behalf.
 */
import { useMutation, useQuery, type UseQueryResult } from "@tanstack/react-query";

import { useAuth } from "../auth";
import { isKnownScoringPhase } from "../assessments";
import type { components } from "../../shared/api/schema";

type PathSuggestionJobAccepted = components["schemas"]["PathSuggestionJobAccepted"];
type PathSuggestionJobStatus = components["schemas"]["PathSuggestionJobStatus"];

/** The narrated paths themselves -- the same model the synchronous GET serves. */
export type PathSuggestionJobResult = NonNullable<PathSuggestionJobStatus["result"]>;

export const pathSuggestionJobKeys = {
  all: ["pathSuggestionJob"] as const,
  status: (jobId: string) => ["pathSuggestionJob", "status", jobId] as const,
};

/**
 * Shared with the assessment scoring jobs: one state machine, one table, one
 * vocabulary (A19). Re-exported here so a consumer of this module does not have
 * to import from the assessment hook to name a phase.
 */
export { isKnownScoringPhase, type ScoringJobPhase as PathSuggestionJobPhase } from "../assessments";

/** See `SCORING_JOB_POLL_INTERVAL_MS` -- the poll endpoints share a limit design. */
export const PATH_SUGGESTION_POLL_INTERVAL_MS = 3000;

/**
 * `POST /me/path-suggestion-jobs` -- queue the fan-out, get a job handle back.
 *
 * No request body: the scorer reads the caller's stored profile and path
 * preferences, exactly as the synchronous GET does. `requestBody?: never` in
 * the contract says the same thing.
 */
export function useStartPathSuggestionJob() {
  const { fetchWithAuth } = useAuth();

  return useMutation({
    mutationFn: () =>
      fetchWithAuth<PathSuggestionJobAccepted>("/me/path-suggestion-jobs", {
        method: "POST",
      }),
  });
}

/** `GET /me/path-suggestion-jobs/{job_id}`, polled until the job is terminal. */
export function usePathSuggestionJobStatus(
  jobId: string | null,
  options: { pollIntervalMs?: number } = {},
): UseQueryResult<PathSuggestionJobStatus> {
  const { user, fetchWithAuth } = useAuth();
  const pollIntervalMs = options.pollIntervalMs ?? PATH_SUGGESTION_POLL_INTERVAL_MS;

  return useQuery({
    // jobId is only ever "" while the query is disabled (enabled requires a
    // non-null id), so the inert key never collides with a real job's data.
    queryKey: pathSuggestionJobKeys.status(jobId ?? ""),
    queryFn: () =>
      fetchWithAuth<PathSuggestionJobStatus>(`/me/path-suggestion-jobs/${jobId}`, {
        method: "GET",
      }),
    enabled: Boolean(user) && jobId !== null,
    // A remount mid-poll must refetch rather than show a minute-old "queued"
    // from the global 60s staleTime (queryClient.ts's DEFAULT_STALE_TIME_MS).
    staleTime: 0,
    refetchInterval: (query) => {
      // Error first: an errored fetch leaves data undefined forever, and the
      // `status === undefined` branch below would otherwise read that as
      // "still loading" and poll a dead job indefinitely.
      if (query.state.status === "error") return false;
      const status = query.state.data?.status;
      if (status === undefined) return pollIntervalMs; // first fetch not landed yet
      if (!isKnownScoringPhase(status)) return false; // unrecognized -> stop, fail closed
      return status === "queued" || status === "running" ? pollIntervalMs : false;
    },
    // `career_status_not_set` arrives as a `failed` job with an `error` -- an
    // in-band 200 the page renders itself, not a route-level failure.
    throwOnError: false,
  });
}
