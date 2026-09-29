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
 * ── CARDS FIRST, SENTENCES AFTER (W-16) ─────────────────────────────────────
 *
 * A job now reaches ``succeeded`` as soon as the list is SCORED. While its
 * ``result.narration_pending`` is true the server is still writing the cards'
 * sentences and updates the same result in place, so the poll carries on --
 * faster, and bounded (``PATH_NARRATION_POLL_INTERVAL_MS`` /
 * ``PATH_NARRATION_MAX_POLLS``) -- until it is false.
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
 * The poll interval once the cards are on screen and only their sentences are
 * outstanding.
 *
 * W-18: 0.5 s, down from W-16's 1.5 s. Since W-17 the first three sentences
 * land ~2 s after the cards, one at a time, and at 1.5 s a written sentence
 * sat on the server for up to another 1.5 s while its card shimmered -- that
 * interval was most of the visible gap. 0.5 s is 120 polls a minute from one
 * tab, which is why the poll route's limit went to 300/minute keyed per
 * signed-in user (`PATH_SUGGESTION_POLL_LIMIT` in `api/v1/intelligence.py`);
 * at the old 60/minute per IP the 61st poll was a 429 and the page stopped.
 */
export const PATH_NARRATION_POLL_INTERVAL_MS = 500;

/**
 * W-18. How long one job may poll for sentences before the client gives up.
 *
 * The server already bounds the wait -- past 60 s every read of a pending
 * result answers with the fallback sentences (`resolve_stale_narration`) -- so
 * this is the client's own backstop, matched to that deadline. Stated as time
 * because the interval moved: W-16's 60 polls meant 90 s at 1.5 s and would
 * have meant 30 s at 0.5 s, cutting a slow narration off early.
 */
export const PATH_NARRATION_MAX_WAIT_MS = 60_000;

/**
 * The most polls one job gets while its result says `narration_pending`:
 * `PATH_NARRATION_MAX_WAIT_MS` at `PATH_NARRATION_POLL_INTERVAL_MS`, so 120.
 * When it trips, the page stops shimmering and shows the cards as they are.
 */
export const PATH_NARRATION_MAX_POLLS = Math.ceil(
  PATH_NARRATION_MAX_WAIT_MS / PATH_NARRATION_POLL_INTERVAL_MS,
);

/**
 * W-16. Is this job's result still waiting on sentences?
 *
 * `succeeded` is terminal for the JOB, but since W-16 it arrives as soon as the
 * list is scored and the result keeps being updated until the narration lands.
 */
export function isNarrationPending(job: PathSuggestionJobStatus | undefined): boolean {
  return job?.status === "succeeded" && Boolean(job.result?.narration_pending);
}

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
  options: { pollIntervalMs?: number; narrationPollIntervalMs?: number } = {},
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
      if (status === "queued" || status === "running") return pollIntervalMs;
      // W-16: the cards are here; keep polling for their sentences, bounded.
      if (isNarrationPending(query.state.data)) {
        return query.state.dataUpdateCount < PATH_NARRATION_MAX_POLLS
          ? (options.narrationPollIntervalMs ?? PATH_NARRATION_POLL_INTERVAL_MS)
          : false;
      }
      return false;
    },
    // `career_status_not_set` arrives as a `failed` job with an `error` -- an
    // in-band 200 the page renders itself, not a route-level failure.
    throwOnError: false,
  });
}
