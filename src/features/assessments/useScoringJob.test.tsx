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

const WPLL_RESULT: ScoringJobResult<"wpll"> = {
  insight_text: "You show strong signs of career misalignment.",
  locked_sections: ["Environmental Friction Score", "Work Rhythm Pattern"],
};

const WORK_PULSE_RESULT: ScoringJobResult<"work_pulse"> = {
  archetype: "Structured Deep Thinker",
  archetype_description: "Sustained concentration with a need for clear structure.",
  narrative: "You bring deep focus to your work.",
  emerging_signals: [],
};

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
// This is the assertion A12 is really about, and it is checked by
// `npm run type-check` rather than by a runtime expectation: `src` is in
// tsconfig.app.json's `include`, so a `@ts-expect-error` here that stops being
// an error fails the build. That is what makes it a gate. A runtime
// `expect(...)` could not see any of this — the three shapes are structurally
// different but all valid JSON, and the whole risk is that a caller reads
// `result` as the wrong instrument's model.
//
// If the hook ever went back to returning
// `WorkPulseScoringJobStatus | WpllScoringJobStatus | ManagerMatchScoringJobStatus`,
// every line below would stop erroring and this block would fail.

// @ts-expect-error a wpll result is not a manager_match result
export const _wpllIsNotManagerMatch: ScoringJobResult<"manager_match"> = WPLL_RESULT;
// @ts-expect-error a wpll result is not a work_pulse result
export const _wpllIsNotWorkPulse: ScoringJobResult<"work_pulse"> = WPLL_RESULT;
// @ts-expect-error a manager_match result is not a wpll result
export const _managerMatchIsNotWpll: ScoringJobResult<"wpll"> = MANAGER_MATCH_RESULT;

/**
 * And the narrowing survives the hook: `data` is that kind's model, not the union.
 *
 * Asserted by assignment rather than by reading a field of the wrong model.
 * Every one of these schemas carries an `[key: string]: unknown` index signature
 * (the API documents them as open), so `wpll.data.result.archetype` type-checks
 * as `unknown` and proves nothing. Assignability is where the three shapes
 * actually separate.
 */
export function NarrowingAtTheCallSite() {
  const wpll = useScoringJobStatus("wpll", "job-1");
  const mm = useScoringJobStatus("manager_match", "job-1");

  // @ts-expect-error the hook returns wpll's model here, not manager_match's
  const _crossed: ScoringJobStatusByKind["manager_match"] | undefined = wpll.data;
  // @ts-expect-error and the result inside it is that kind's own model
  const _crossedResult: ScoringJobResult<"wpll"> | null | undefined = mm.data?.result;

  // Assigned to a value the compiler can see, so `noUnusedLocals` does not
  // remove the two declarations the directives above are attached to.
  void _crossed;
  void _crossedResult;
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
        onClick={() => start.mutate({ answers: [{ question_id: "q1", option_id: "a" }] })}
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
      scoringJobProgresses("work_pulse", "wp-1", [
        { status: "queued" },
        { status: "running" },
        { status: "succeeded", result: WORK_PULSE_RESULT },
      ])
    );

    mountStatus("work_pulse", "wp-1");
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("succeeded"));
    expect(pollsFor("work_pulse")).toHaveLength(3);

    const countAtTerminal = pollsFor("work_pulse").length;
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));
    expect(pollsFor("work_pulse")).toHaveLength(countAtTerminal);
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
      scoringJobProgresses("work_pulse", "wp-2", [{ status: "reticulating_splines" }])
    );

    mountStatus("work_pulse", "wp-2");
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("reticulating_splines")
    );

    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));
    // Fail closed: a status this client does not know is treated as terminal.
    expect(pollsFor("work_pulse")).toHaveLength(1);
  });

  it("issues no request while the job id is null", async () => {
    server.use(signedIn());

    mountStatus("work_pulse", null);
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));

    expect(pollsFor("work_pulse")).toEqual([]);
  });

  it("polls wpll with no session, because the handle is the whole authorisation", async () => {
    // No `signedIn()`: the default session probe 401s, so `user` is null. The
    // other two kinds are gated on a user; wpll is the anonymous teaser and is
    // not, which is the branch this covers.
    server.use(
      scoringJobProgresses("wpll", "wpll-1", [
        { status: "queued" },
        { status: "succeeded", result: WPLL_RESULT },
      ])
    );

    mountStatus("wpll", "wpll-1");
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("succeeded"));
    expect(pollsFor("wpll")).toHaveLength(2);
  });

  it("does not poll a signed-out user's work_pulse job", async () => {
    // Mirror of the test above: the same absent session that is fine for wpll
    // holds the other two kinds' polls closed.
    mountStatus("work_pulse", "wp-3");
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));

    expect(pollsFor("work_pulse")).toEqual([]);
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
              job_id: "wp-9",
              status: "queued",
              status_url: "/api/v1/assessments/work_pulse/scoring-jobs/wp-9",
            },
            { status: 202 }
          );
        }
      )
    );

    mountMutation("work_pulse");
    fireEvent.click(await screen.findByRole("button"));
    await waitFor(() => expect(screen.getByTestId("mutation-status")).toHaveTextContent("wp-9"));

    expect(capturedKind).toBe("work_pulse");
    // The enqueue's body is the synchronous submit's body, unchanged (A19).
    expect(capturedBody).toEqual({ answers: [{ question_id: "q1", option_id: "a" }] });
    expect(requests).toContain("POST /api/v1/assessments/work_pulse/scoring-jobs");
  });

  it("enqueues wpll with no session", async () => {
    server.use(scoringJobAccepted("wpll", "wpll-5"));

    mountMutation("wpll");
    fireEvent.click(await screen.findByRole("button"));
    await waitFor(() =>
      expect(screen.getByTestId("mutation-status")).toHaveTextContent("wpll-5")
    );

    expect(requests).toContain("POST /api/v1/assessments/wpll/scoring-jobs");
  });

  it("reports 202 acceptance via scoringJobAccepted for reuse in other suites", async () => {
    server.use(signedIn(), scoringJobAccepted("manager_match", "mm-5"));

    mountMutation("manager_match");
    fireEvent.click(await screen.findByRole("button"));
    await waitFor(() => expect(screen.getByTestId("mutation-status")).toHaveTextContent("mm-5"));
  });
});
