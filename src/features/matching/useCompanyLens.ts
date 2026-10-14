/**
 * useCompanyLens -- the six-trait CompanyLens API, as hooks.
 *
 *   GET  /me/matches?cursor=&limit=        the ranking, one page at a time
 *   POST /companies/research {name}        research a company on demand (202 + a run)
 *   GET  /companies/research/{run_id}      that run's status, polled
 *
 * PRODUCT_DECISIONS.md §2, "The six-trait match model" (2026-10-13). The API carries
 * no probability, score or percentage, and nothing here computes one: the order of
 * `data` is the ranking, and every per-trait read is words (direction, inside or
 * outside your give, a flag). Coverage counts ("4 of 6") are the only numbers.
 *
 * Types come from the generated contract (`schema.ts`), never a local copy.
 */
import { useEffect, useRef } from "react";
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../auth";
import { ApiError } from "../../shared/api/apiError";
import type { components } from "../../shared/api/schema";
import { DEFAULT_POLL_TIMING, usePoll, type PollTiming } from "./usePoll";

type Schemas = components["schemas"];
export type MatchesResponse = Schemas["MatchesResponse"];
export type MatchEntry = Schemas["MatchEntry"];
export type CoverageCounts = Schemas["CoverageCounts"];
export type FlagCounts = Schemas["FlagCounts"];
export type NextStep = Schemas["NextStep"];
export type TraitReadSummary = Schemas["TraitReadSummary"];
export type ResearchRunStatus = Schemas["ResearchRunStatus"];
export type ResearchRunResponse = Schemas["ResearchRunResponse"];
export type TraitKey = TraitReadSummary["dimension"];
export type Direction = NonNullable<TraitReadSummary["direction"]>;
export type TraitFlag = NonNullable<TraitReadSummary["flag"]>;

/**
 * Every CompanyLens query sits under `all`, so one invalidation (a research run
 * finishing) refreshes the list and any open company read together.
 */
export const companyLensKeys = {
  all: ["companyLens"] as const,
  matches: (limit: number) => ["companyLens", "matches", limit] as const,
  read: (companyId: string, postingId: number | null) =>
    ["companyLens", "read", companyId, postingId] as const,
  profile: (companyId: string) => ["companyLens", "profile", companyId] as const,
  links: ["companyLens", "links"] as const,
};

export const MATCHES_PAGE_SIZE = 20;

/** `GET /me/matches`, walked with "Show more". */
export function useMatches(limit: number = MATCHES_PAGE_SIZE) {
  const { fetchWithAuth } = useAuth();
  return useInfiniteQuery({
    queryKey: companyLensKeys.matches(limit),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => {
      const cursor = pageParam ? `&cursor=${encodeURIComponent(pageParam)}` : "";
      return fetchWithAuth<MatchesResponse>(`/me/matches?limit=${limit}${cursor}`);
    },
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

// ---------------------------------------------------------------------------
// On-demand research
// ---------------------------------------------------------------------------

export type ResearchPhase =
  | "idle"
  | "starting"
  | "queued"
  | "running"
  | "done"
  | "failed"
  | "error";

/** Why a research request did not start, in the terms the page explains it. */
export type ResearchStartProblem = "daily_limit" | "busy" | "unavailable" | "invalid" | "other";

export function isTerminalRun(status: ResearchRunStatus["status"]): boolean {
  return status === "done" || status === "failed";
}

export function researchStartProblem(error: unknown): ResearchStartProblem | null {
  if (!error) return null;
  if (error instanceof ApiError) {
    if (error.status === 429) {
      // The daily budget names itself; any other 429 is the burst limiter.
      return error.fieldErrors.some((e) => e.code === "research_daily_limit")
        ? "daily_limit"
        : "busy";
    }
    if (error.status === 503) return "unavailable";
    if (error.status === 400 || error.status === 422) return "invalid";
  }
  return "other";
}

export interface ResearchCompany {
  phase: ResearchPhase;
  /** The run as last seen (from the POST, then from each poll). */
  run: ResearchRunStatus | null;
  /** True when the POST found a finished run and started nothing. */
  cached: boolean;
  /** Set when phase is "error": why the request did not start, or why polling stopped. */
  problem: ResearchStartProblem | "lost" | null;
  start: (name: string) => void;
  reset: () => void;
}

/**
 * Start research on a company, then poll its run until it is done or failed.
 * When it finishes, every CompanyLens query is invalidated so the list and any
 * open read pick the company up.
 */
export function useResearchCompany(timing: PollTiming = DEFAULT_POLL_TIMING): ResearchCompany {
  const { fetchWithAuth } = useAuth();
  const queryClient = useQueryClient();

  const startMutation = useMutation({
    mutationFn: (name: string) =>
      fetchWithAuth<ResearchRunResponse>("/companies/research", {
        method: "POST",
        body: JSON.stringify({ name }),
      }),
  });

  const accepted = startMutation.data?.run ?? null;
  const pollTarget =
    accepted !== null && !isTerminalRun(accepted.status) ? String(accepted.run_id) : null;

  const poll = usePoll<ResearchRunStatus>(
    pollTarget,
    (runId) => fetchWithAuth<ResearchRunStatus>(`/companies/research/${runId}`),
    (run) => isTerminalRun(run.status),
    timing,
  );

  const run = poll.data ?? accepted;

  // Refresh the list once per finished run. Keyed on the run id so a second
  // research in the same session invalidates again.
  const refreshedRun = useRef<number | null>(null);
  useEffect(() => {
    if (run?.status === "done" && refreshedRun.current !== run.run_id) {
      refreshedRun.current = run.run_id;
      void queryClient.invalidateQueries({ queryKey: companyLensKeys.all });
    }
  }, [run, queryClient]);

  let phase: ResearchPhase;
  let problem: ResearchCompany["problem"] = null;
  if (startMutation.isPending) {
    phase = "starting";
  } else if (startMutation.isError) {
    phase = "error";
    problem = researchStartProblem(startMutation.error);
  } else if (poll.error) {
    phase = "error";
    problem = "lost";
  } else if (run === null) {
    phase = "idle";
  } else {
    phase = run.status;
  }

  return {
    phase,
    run,
    cached: startMutation.data?.cached ?? false,
    problem,
    start: (name: string) => startMutation.mutate(name),
    reset: () => startMutation.reset(),
  };
}
