/**
 * useScoringJob.test.tsx — the per-kind mutation + poll against a real network.
 *
 * Follows `useResumeParseJob.test.tsx`, which follows `AuthContext.boot.test.tsx`:
 * `useApiMocks()` + `recordRequests()` and a real `AuthProvider` /
 * `QueryClientProvider`, rather than mocking `useAuth`. "Polling stops" is a
 * claim about requests on the wire; counting calls to a mocked function would
 * prove nothing about whether `refetchInterval` actually returned `false`.
 *
 * `pollIntervalMs` is overridden to a short real interval in every test here
 * rather than using fake timers, for the reason recorded in the resume file:
 * TanStack Query v5's interval scheduling interacts with React's `act()`
 * batching in ways that are fiddly under `vi.useFakeTimers()`, and this repo
 * has no fake-timer precedent to build on.
 */
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { HttpResponse } from "msw";

import { AuthProvider } from "../auth";
import { createQueryClient } from "../../shared/api/queryClient";
import { server, useApiMocks, recordRequests, signedIn } from "../../../tests/msw/server";
import { mock } from "../../../tests/msw/contract";
import {
  scoringJobAccepted,
  scoringJobProgresses,
  scoringJobNotFound,
} from "../../../tests/msw/scoringJobHandlers";
import {
  useScoringJobStatus,
  useStartScoringJob,
  type ScoringJobKind,
  type ScoringJobResult,
  type ScoringJobStatusByKind,
} from "./useScoringJob";

useApiMocks();
const { requests } = recordRequests();

const POLL_INTERVAL_MS = 20;
const pollsFor = (kind: ScoringJobKind) =>
  requests.filter((r) => r.startsWith(`GET /api/v1/assessments/${kind}/scoring-jobs`));

const MANAGER_MATCH_RESULT: ScoringJobResult<"manager_match"> = {
  archetype: "Autonomy Seeker",
  archetype_description: "You do your best work with room to move.",
  narrative: "You want direction, not supervision.",
  dimension_scores: { autonomy: 0.8 },
  red_flags: [],
  what_to_look_for: [],
};

// ── The narrowing, asserted at type-check time ──────────────────────────────
//
// Checked by `npm run type-check` rather than by a runtime expectation: `src` is
// in tsconfig.app.json's `include`, so a `@ts-expect-error` here that stops being
// an error fails the build. ManagerMatch is the only job-scored kind since
// `wpll` was retired with `/start` (2026-11-23); the two retired kinds are not
// kinds of this hook at all.

// The retired work_pulse has no scoring job any more (2026-10-02).
// @ts-expect-error work_pulse is not a scoring-job kind
export const _workPulseIsNotAKind: ScoringJobKind = "work_pulse";
// Nor does the retired anonymous teaser (2026-11-23).
// @ts-expect-error wpll is not a scoring-job kind
export const _wpllIsNotAKind: ScoringJobKind = "wpll";

/** `data` is that kind's own model, and its `result` that kind's result. */
export function NarrowingAtTheCallSite() {
  const mm = useScoringJobStatus("manager_match", "job-1");
  const _typed: ScoringJobStatusByKind["manager_match"] | undefined = mm.data;
  const _result: ScoringJobResult<"manager_match"> | null | undefined = mm.data?.result;

  void _typed;
  void _result;
  return null;
}

// ── Harnesses ───────────────────────────────────────────────────────────────

function StatusHarness<K extends ScoringJobKind>({
  kind,
  jobId,
}: {
  kind: K;
  jobId: string | null;
}) {
  const status = useScoringJobStatus(kind, jobId, { pollIntervalMs: POLL_INTERVAL_MS });
  const label =
    status.data?.status ?? (status.error ? "error" : status.isLoading ? "loading" : "none");
  return <span data-testid="status">{label}</span>;
}

function mountStatus(kind: ScoringJobKind, jobId: string | null) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <StatusHarness kind={kind} jobId={jobId} />
      </AuthProvider>
    </QueryClientProvider>
  );
}

function MutationHarness({ kind }: { kind: ScoringJobKind }) {
  const start = useStartScoringJob(kind);
  const label = start.isSuccess ? start.data.job_id : start.isPending ? "pending" : "idle";
  return (
    <div>
      <button
        type="button"
        onClick={() => start.mutate({ answers: [{ question_id: "mm-q1", choice: "a" }] })}
      >
        start
      </button>
      <span data-testid="mutation-status">{label}</span>
    </div>
  );
}

function mountMutation(kind: ScoringJobKind) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MutationHarness kind={kind} />
      </AuthProvider>
    </QueryClientProvider>
  );
}

// ── The poll ────────────────────────────────────────────────────────────────

describe("useScoringJobStatus", () => {
  it("polls queued -> running -> succeeded and stops issuing requests once terminal", async () => {
    server.use(
      signedIn(),
      scoringJobProgresses("manager_match", "mm-0", [
        { status: "queued" },
        { status: "running" },
        { status: "succeeded", result: MANAGER_MATCH_RESULT },
      ])
    );

    mountStatus("manager_match", "mm-0");
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("succeeded"));
    expect(pollsFor("manager_match")).toHaveLength(3);

    const countAtTerminal = pollsFor("manager_match").length;
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));
    expect(pollsFor("manager_match")).toHaveLength(countAtTerminal);
  });

  it("surfaces a failed job as data, distinct from an error state, and stops polling", async () => {
    server.use(
      signedIn(),
      scoringJobProgresses("manager_match", "mm-1", [
        { status: "queued" },
        { status: "failed", error: "We couldn't score that right now." },
      ])
    );

    mountStatus("manager_match", "mm-1");
    // `failed` is an in-band 200, so it arrives as data. The harness renders
    // "error" only for a rejected query -- the two are not the same state.
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("failed"));

    const countAtTerminal = pollsFor("manager_match").length;
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));
    expect(pollsFor("manager_match")).toHaveLength(countAtTerminal);
  });

  it("treats a 404 (stale/foreign handle) as terminal without a retry storm", async () => {
    server.use(signedIn(), scoringJobNotFound("manager_match", "stale-job"));

    mountStatus("manager_match", "stale-job");
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("error"));

    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));
    // shouldRetry (queryClient.ts) treats 404 as non-retryable, so exactly one
    // request -- and refetchInterval never got a status to read, because the
    // query stayed in its error state.
    expect(pollsFor("manager_match")).toHaveLength(1);
  });

  it("stops polling on an unrecognized status rather than running forever", async () => {
    server.use(
      signedIn(),
      scoringJobProgresses("manager_match", "mm-2", [{ status: "reticulating_splines" }])
    );

    mountStatus("manager_match", "mm-2");
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("reticulating_splines")
    );

    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));
    // Fail closed: a status this client does not know is treated as terminal.
    expect(pollsFor("manager_match")).toHaveLength(1);
  });

  it("issues no request while the job id is null", async () => {
    server.use(signedIn());

    mountStatus("manager_match", null);
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));

    expect(pollsFor("manager_match")).toEqual([]);
  });

  it("does not poll a signed-out user's manager_match job", async () => {
    // No `signedIn()`: the default session probe 401s, so `user` is null and
    // the poll stays closed. (`wpll`, retired 2026-11-23, was the one kind that
    // polled without a session.)
    mountStatus("manager_match", "mm-3");
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));

    expect(pollsFor("manager_match")).toEqual([]);
  });
});

// ── The enqueue ─────────────────────────────────────────────────────────────

describe("useStartScoringJob", () => {
  it("posts to the kind's own scoring-jobs path and returns the handle", async () => {
    let capturedBody: unknown;
    let capturedKind: unknown;
    server.use(
      signedIn(),
      mock("post", "/api/v1/assessments/{kind}/scoring-jobs").resolve(
        async ({ request, params }) => {
          capturedKind = params.kind;
          capturedBody = await request.json();
          return HttpResponse.json(
            {
              job_id: "mm-9",
              status: "queued",
              status_url: "/api/v1/assessments/manager_match/scoring-jobs/mm-9",
            },
            { status: 202 }
          );
        }
      )
    );

    mountMutation("manager_match");
    fireEvent.click(await screen.findByRole("button"));
    await waitFor(() => expect(screen.getByTestId("mutation-status")).toHaveTextContent("mm-9"));

    expect(capturedKind).toBe("manager_match");
    // The enqueue's body is the synchronous submit's body, unchanged (A19).
    expect(capturedBody).toEqual({ answers: [{ question_id: "mm-q1", choice: "a" }] });
    expect(requests).toContain("POST /api/v1/assessments/manager_match/scoring-jobs");
  });

  it("reports 202 acceptance via scoringJobAccepted for reuse in other suites", async () => {
    server.use(signedIn(), scoringJobAccepted("manager_match", "mm-5"));

    mountMutation("manager_match");
    fireEvent.click(await screen.findByRole("button"));
    await waitFor(() => expect(screen.getByTestId("mutation-status")).toHaveTextContent("mm-5"));
  });
});
