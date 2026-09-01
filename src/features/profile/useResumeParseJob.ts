/**
 * useResumeParseJob.ts — the async resume-parse job, as a mutation + a poll.
 *
 * Phase 3a's ``202 + job handle`` alongside the synchronous ``/complete`` this
 * replaces in the UI (Part 5.2). ``POST .../parse-jobs`` queues the parse and
 * hands back a job id; ``GET .../resume-parse-jobs/{job_id}`` is polled until
 * the job reaches a terminal state.
 *
 * The server persists the parse before the job is marked ``succeeded`` --
 * ``solverah/services/resume_jobs.py``'s ``run()`` merges the parsed fields
 * into the stored profile and commits before ``_finish(job_id, SUCCEEDED)`` --
 * so ``status_for()`` on a succeeded job returns the document already holding
 * the merge, not a snapshot from parse time. Consumers of this hook should
 * treat a ``succeeded`` response as "the server already has this," not as
 * something that still needs saving.
 */
import { useMutation, useQuery, type UseQueryResult } from "@tanstack/react-query";

import { useAuth } from "../auth";
import type { components } from "../../shared/api/schema";

type ResumeParseJobAccepted = components["schemas"]["ResumeParseJobAccepted"];
type ResumeParseJobStatus = components["schemas"]["ResumeParseJobStatus"];

export const resumeParseJobKeys = {
  all: ["resumeParseJob"] as const,
  status: (jobId: string) => ["resumeParseJob", "status", jobId] as const,
};

/**
 * The server's real vocabulary for `status`.
 *
 * The OpenAPI field is a bare `string` -- no enum -- so openapi-typescript
 * cannot narrow it (confirmed against `docs/openapi.json`'s `ResumeParseJobStatus`
 * schema). Reconstructed here by hand instead.
 */
export type ResumeParseJobPhase = "queued" | "running" | "succeeded" | "failed";

const KNOWN_PHASES: readonly string[] = ["queued", "running", "succeeded", "failed"];

/** Fail closed: an unrecognized status is treated as terminal, not as "keep polling." */
export function isKnownPhase(status: string): status is ResumeParseJobPhase {
  return KNOWN_PHASES.includes(status);
}

export const RESUME_PARSE_POLL_INTERVAL_MS = 3000;

export interface StartResumeParseJobVariables {
  resumeId: string;
  mime: string;
  size: number;
  name?: string | null;
}

/** `POST /me/resumes/{resume_id}/parse-jobs` -- queue a parse, get a job handle back. */
export function useStartResumeParseJob() {
  const { fetchWithAuth } = useAuth();

  return useMutation({
    mutationFn: ({ resumeId, mime, size, name }: StartResumeParseJobVariables) =>
      fetchWithAuth<ResumeParseJobAccepted>(`/me/resumes/${resumeId}/parse-jobs`, {
        method: "POST",
        // resumeId is path-only; the body is exactly what ResumeCompleteRequest
        // names (the same shape /complete already takes), not the full variables
        // object above.
        body: JSON.stringify({ mime, size, name: name ?? null }),
      }),
  });
}

/** `GET /me/resume-parse-jobs/{job_id}`, polled until the job reaches a terminal state. */
export function useResumeParseJobStatus(
  jobId: string | null,
  options: { pollIntervalMs?: number } = {},
): UseQueryResult<ResumeParseJobStatus> {
  const { user, fetchWithAuth } = useAuth();
  const pollIntervalMs = options.pollIntervalMs ?? RESUME_PARSE_POLL_INTERVAL_MS;

  return useQuery({
    // jobId is only ever "" while the query is disabled (enabled requires a
    // non-null id), so the inert key never collides with a real job's data.
    queryKey: resumeParseJobKeys.status(jobId ?? ""),
    queryFn: () => fetchWithAuth<ResumeParseJobStatus>(`/me/resume-parse-jobs/${jobId}`, { method: "GET" }),
    enabled: Boolean(user) && jobId !== null,
    // A remount mid-poll must refetch rather than show a minute-old "queued"
    // from the global 60s staleTime (queryClient.ts's DEFAULT_STALE_TIME_MS).
    staleTime: 0,
    refetchInterval: (query) => {
      // An errored fetch (a 404 on a stale/foreign job, say) leaves data
      // undefined forever -- checked first, or the `status === undefined`
      // branch below would read "never succeeded" as "still loading" and
      // poll a dead job indefinitely.
      if (query.state.status === "error") return false;
      const status = query.state.data?.status;
      if (status === undefined) return pollIntervalMs; // first fetch not landed yet
      if (!isKnownPhase(status)) return false; // unrecognized -> stop, fail closed
      return status === "queued" || status === "running" ? pollIntervalMs : false;
    },
    // A `failed` job is an in-band 200, and even a 404 here (stale/foreign job
    // id) is this section's concern, not a route-level one -- unlike
    // useProfile.ts, this must not escalate to RouteErrorBoundary.
    throwOnError: false,
  });
}
