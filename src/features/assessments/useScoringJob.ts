/**
 * useScoringJob.ts — the three provider-scored assessments, as a mutation + a poll.
 *
 * Phase 3c's ``202 + job handle`` replacing the synchronous
 * ``POST /assessments/{kind}/submissions`` in the UI. ``POST
 * /assessments/{kind}/scoring-jobs`` queues the scoring and hands back a job id;
 * ``GET /assessments/{kind}/scoring-jobs/{job_id}`` is polled until the job
 * reaches a terminal state.
 *
 * Modelled on ``useResumeParseJob.ts``, which is the reviewed template for this
 * shape: enabled-gated poll query, a ``refetchInterval`` that reads query state,
 * polling that stops on an error rather than reading "no data yet" as "still
 * running", and fail-closed handling of a status nobody recognises.
 *
 * ── EXACTLY THREE INSTRUMENTS ARE HERE, AND THAT IS THE DESIGN (A19) ─────────
 *
 * ``work_pulse``, ``wpll`` and ``manager_match`` block on an OpenAI call of
 * seconds to tens of seconds. ``core`` and ``focus_type`` score from
 * deterministic tables without opening a socket -- 211 ms and 40 ms measured,
 * including the database writes and the HTTP round trip -- so handing their
 * callers a job to poll would spend two extra round trips to deliver a slower
 * answer. They stay on the synchronous submit, and ``core`` has the stronger
 * second reason: it carries the six person dimension scores, withholds them
 * even from its own respondent (A12), and a job would put them in
 * ``scoring_jobs.result`` behind an endpoint that serves them back. The server
 * agrees rather than merely tolerating this -- it answers ``404`` to a
 * scoring-job POST for either of those two kinds.
 *
 * ── WHY THIS IS GENERIC IN `K` RATHER THAN RETURNING A UNION ────────────────
 *
 * ``{kind}`` is in the poll path precisely because the response model differs
 * per instrument (A12): ``result`` is that instrument's own model and nothing
 * else. A hook returning ``WorkPulseScoringJobStatus | WpllScoringJobStatus |
 * ManagerMatchScoringJobStatus`` would hand every caller a union it has to
 * re-narrow by hand, which is the shared result envelope A12 rejected, rebuilt
 * in TypeScript. Threading the kind through as a type parameter means
 * ``useScoringJobStatus("wpll", id).data.result`` is a ``WpllResultResponse``
 * at the call site and a ``ManagerMatchResult`` is a type error there. See
 * ``useScoringJob.test.tsx`` for that assertion, which `npm run type-check`
 * enforces.
 */
import { useMutation, useQuery, type UseQueryResult } from "@tanstack/react-query";

import { useAuth } from "../auth";
import { API_BASE } from "../../shared/api/api";
import { parseApiError } from "../../shared/api/apiError";
import type { components } from "../../shared/api/schema";

type ScoringJobAccepted = components["schemas"]["ScoringJobAccepted"];

/**
 * The instruments that have a scoring job.
 *
 * `scoring_jobs.JOB_ELIGIBLE_KINDS` is the authority; this is its client-side
 * restatement. `core` and `focus_type` are absent on purpose -- see the header.
 */
export type ScoringJobKind = "work_pulse" | "wpll" | "manager_match";

/**
 * `{kind}` -> the poll's response model.
 *
 * The three differ only in `result`, and that is the whole point of the path
 * parameter. Written as a map rather than a union so `ScoringJobStatusByKind[K]`
 * resolves to exactly one member for a known `K`.
 */
export interface ScoringJobStatusByKind {
  work_pulse: components["schemas"]["WorkPulseScoringJobStatus"];
  wpll: components["schemas"]["WpllScoringJobStatus"];
  manager_match: components["schemas"]["ManagerMatchScoringJobStatus"];
}

/** `{kind}` -> the enqueue's request body, which is the submit's body unchanged. */
export interface ScoringJobRequestByKind {
  work_pulse: components["schemas"]["WorkPulseSubmitRequest"];
  wpll: components["schemas"]["WpllSubmitRequest"];
  manager_match: components["schemas"]["ManagerMatchSubmitRequest"];
}

/**
 * The instrument's own result model, with the `null` it carries before
 * `succeeded` removed.
 *
 * This is the same shape the synchronous submit returned for that kind, so a
 * caller can route it wherever it routed the submit's response.
 */
export type ScoringJobResult<K extends ScoringJobKind> = NonNullable<
  ScoringJobStatusByKind[K]["result"]
>;

export const scoringJobKeys = {
  all: ["scoringJob"] as const,
  status: (kind: ScoringJobKind, jobId: string) =>
    ["scoringJob", "status", kind, jobId] as const,
};

/**
 * The server's real vocabulary for `status`.
 *
 * The OpenAPI field is a bare `string` -- no enum -- so openapi-typescript
 * cannot narrow it (confirmed against the three `*ScoringJobStatus` schemas in
 * `docs/openapi.json`). Reconstructed here by hand, as `useResumeParseJob` does
 * for the same reason.
 */
export type ScoringJobPhase = "queued" | "running" | "succeeded" | "failed";

const KNOWN_PHASES: readonly string[] = ["queued", "running", "succeeded", "failed"];

/** Fail closed: an unrecognized status is treated as terminal, not as "keep polling." */
export function isKnownScoringPhase(status: string): status is ScoringJobPhase {
  return KNOWN_PHASES.includes(status);
}

/**
 * How often a queued or running job is re-read.
 *
 * A19 gives both poll endpoints an explicit limit with a daily backstop, set
 * because a client polling every two seconds against the global `50 per hour`
 * default exhausted it inside a single scoring. Three seconds sits inside what
 * that limit was sized for. Do not lower it.
 */
export const SCORING_JOB_POLL_INTERVAL_MS = 3000;

/**
 * `wpll` is the one kind that is not fetched with the session's credentials.
 *
 * It is the anonymous pre-launch teaser: its job has no owner (the server's
 * `ck_scoring_jobs_owner_required` grants ownerless rows to `wpll` by name) and
 * the handle is the whole of its authorisation. `fetchWithAuth` sends
 * `credentials: "include"`, so routing this kind through it would start
 * attaching a signed-in visitor's cookie to a request that today carries none
 * -- a change to which branch the server takes, smuggled in under a transport
 * change. The synchronous call site this replaces used a bare `fetch`; so does
 * this.
 *
 * Takes a whole URL rather than a path suffix -- see the note on the two
 * spellings below.
 */
async function anonymousJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
  });
  const data = await res.json().catch(() => null);
  // parseApiError rather than a bare Error so `shouldRetry` in queryClient.ts
  // classifies this the way it classifies every other failure -- a 404 on a
  // stale handle must not be retried three times.
  if (!res.ok) throw parseApiError(res, data);
  if (data === null) throw new Error("Unexpected response from server (no JSON body).");
  return data as T;
}

/**
 * Whether this kind's endpoints can be called yet.
 *
 * `wpll` is reachable signed out; the other two are not, and a poll issued
 * before the session probe lands would 401 and stop as a terminal error.
 */
function useScoringJobReady(kind: ScoringJobKind): boolean {
  const { user } = useAuth();
  return kind === "wpll" || Boolean(user);
}

/*
 * ── WHY THE PATH IS WRITTEN OUT IN BOTH BRANCHES BELOW ──────────────────────
 *
 * The obvious shape is to pick a transport once -- `const request = kind ===
 * "wpll" ? anonymousJson : fetchWithAuth` -- and call `request(path)`. It works
 * at runtime and it is invisible to `tests/test_frontend_contract.py`, which
 * scans this source for two literal shapes: an API_BASE template literal, and a
 * fetchWithAuth (or streamFetch) call whose first argument is a quoted path
 * beginning with a slash. A call through a variable named `request` matches
 * neither, so these four endpoints would be the only ones in the SPA that the
 * "every path the frontend calls is one the API serves" check could not see --
 * and that check is what turns a 404 on a rarely-visited screen into a failing
 * test instead of a bug report.
 *
 * (Neither shape is written out above for the same reason: this file is scanned
 * as source, so an illustrative example in a comment would be read as a real
 * call site to a path the API does not serve.)
 *
 * So each request is spelled out on the branch that issues it. The duplication
 * is one line per branch and it keeps both call sites scannable.
 */

/** `POST /assessments/{kind}/scoring-jobs` -- queue a scoring, get a job handle back. */
export function useStartScoringJob<K extends ScoringJobKind>(kind: K) {
  const { fetchWithAuth } = useAuth();

  return useMutation({
    mutationFn: (body: ScoringJobRequestByKind[K]) => {
      const init: RequestInit = { method: "POST", body: JSON.stringify(body) };
      return kind === "wpll"
        ? anonymousJson<ScoringJobAccepted>(
            `${API_BASE}/assessments/${kind}/scoring-jobs`,
            init
          )
        : fetchWithAuth<ScoringJobAccepted>(`/assessments/${kind}/scoring-jobs`, init);
    },
  });
}

/**
 * `GET /assessments/{kind}/scoring-jobs/{job_id}`, polled until terminal.
 *
 * The return type is this kind's model, not the union of the three.
 */
export function useScoringJobStatus<K extends ScoringJobKind>(
  kind: K,
  jobId: string | null,
  options: { pollIntervalMs?: number } = {},
): UseQueryResult<ScoringJobStatusByKind[K]> {
  const { fetchWithAuth } = useAuth();
  const ready = useScoringJobReady(kind);
  const pollIntervalMs = options.pollIntervalMs ?? SCORING_JOB_POLL_INTERVAL_MS;

  return useQuery({
    // jobId is only ever "" while the query is disabled (enabled requires a
    // non-null id), so the inert key never collides with a real job's data.
    // `kind` is in the key as well: two instruments' handles are distinct
    // namespaces on the server and must not share a cache entry here either.
    queryKey: scoringJobKeys.status(kind, jobId ?? ""),
    queryFn: () => {
      const init: RequestInit = { method: "GET" };
      // Both spellings written out -- see the note above `useStartScoringJob`.
      return kind === "wpll"
        ? anonymousJson<ScoringJobStatusByKind[K]>(
            `${API_BASE}/assessments/${kind}/scoring-jobs/${jobId}`,
            init
          )
        : fetchWithAuth<ScoringJobStatusByKind[K]>(
            `/assessments/${kind}/scoring-jobs/${jobId}`,
            init
          );
    },
    enabled: ready && jobId !== null,
    // A remount mid-poll must refetch rather than show a minute-old "queued"
    // from the global 60s staleTime (queryClient.ts's DEFAULT_STALE_TIME_MS).
    staleTime: 0,
    refetchInterval: (query) => {
      // An errored fetch (a 404 on a stale/foreign handle, say) leaves data
      // undefined forever -- checked first, or the `status === undefined`
      // branch below would read "never succeeded" as "still loading" and poll
      // a dead job indefinitely. That exact bug was found and fixed in
      // useResumeParseJob; it is not reintroduced here.
      if (query.state.status === "error") return false;
      const status = query.state.data?.status;
      if (status === undefined) return pollIntervalMs; // first fetch not landed yet
      if (!isKnownScoringPhase(status)) return false; // unrecognized -> stop, fail closed
      return status === "queued" || status === "running" ? pollIntervalMs : false;
    },
    // A `failed` job is an in-band 200, and even a 404 here (stale/foreign job
    // id) is this screen's concern, not a route-level one -- it must not
    // escalate to RouteErrorBoundary.
    throwOnError: false,
  });
}
