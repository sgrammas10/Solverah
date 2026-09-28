/**
 * usePathSuggestionJob.test.tsx — the path-suggestion mutation + poll on the wire.
 *
 * Same construction as `useScoringJob.test.tsx` and `useResumeParseJob.test.tsx`,
 * and for the same reason: "polling stops" is a claim about requests issued, so
 * the network is real (MSW) and the assertion is a request count.
 */
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";

import { AuthProvider } from "../auth";
import { createQueryClient } from "../../shared/api/queryClient";
import { server, useApiMocks, recordRequests, signedIn } from "../../../tests/msw/server";
import {
  pathSuggestionJobAccepted,
  pathSuggestionJobProgresses,
} from "../../../tests/msw/scoringJobHandlers";
import {
  PATH_NARRATION_MAX_POLLS,
  usePathSuggestionJobStatus,
  useStartPathSuggestionJob,
  type PathSuggestionJobResult,
} from "./usePathSuggestionJob";

useApiMocks();
const { requests } = recordRequests();

const POLL_INTERVAL_MS = 20;
const polls = () =>
  requests.filter((r) => r.startsWith("GET /api/v1/me/path-suggestion-jobs"));

const RESULT: PathSuggestionJobResult = {
  career_status: "employed",
  generated_at: "2026-09-01T00:00:00Z",
  suggestions: [],
  narration_pending: false,
};

/** W-16: a scored result whose sentences are still being written. */
const PENDING: PathSuggestionJobResult = { ...RESULT, narration_pending: true };

function StatusHarness({ jobId }: { jobId: string | null }) {
  const status = usePathSuggestionJobStatus(jobId, {
    pollIntervalMs: POLL_INTERVAL_MS,
    narrationPollIntervalMs: POLL_INTERVAL_MS,
  });
  const label =
    status.data?.status ?? (status.error ? "error" : status.isLoading ? "loading" : "none");
  return <span data-testid="status">{label}</span>;
}

function mountStatus(jobId: string | null) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <StatusHarness jobId={jobId} />
      </AuthProvider>
    </QueryClientProvider>
  );
}

function MutationHarness() {
  const start = useStartPathSuggestionJob();
  const label = start.isSuccess ? start.data.job_id : start.isPending ? "pending" : "idle";
  return (
    <div>
      <button type="button" onClick={() => start.mutate()}>
        start
      </button>
      <span data-testid="mutation-status">{label}</span>
    </div>
  );
}

describe("usePathSuggestionJobStatus", () => {
  it("polls queued -> running -> succeeded and stops once terminal", async () => {
    server.use(
      signedIn(),
      pathSuggestionJobProgresses("path-1", [
        { status: "queued" },
        { status: "running" },
        { status: "succeeded", result: RESULT },
      ])
    );

    mountStatus("path-1");
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("succeeded"));
    expect(polls()).toHaveLength(3);

    const countAtTerminal = polls().length;
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));
    expect(polls()).toHaveLength(countAtTerminal);
  });

  it("keeps polling a succeeded job while its sentences are pending, then stops (W-16)", async () => {
    server.use(
      signedIn(),
      pathSuggestionJobProgresses("path-narr", [
        { status: "succeeded", result: PENDING },
        { status: "succeeded", result: PENDING },
        { status: "succeeded", result: RESULT },
      ])
    );

    mountStatus("path-narr");
    await waitFor(() => expect(polls()).toHaveLength(3));

    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));
    expect(polls()).toHaveLength(3);
  });

  it("gives up on pending sentences after the cap rather than polling forever (W-16)", async () => {
    server.use(
      signedIn(),
      pathSuggestionJobProgresses("path-stuck", [{ status: "succeeded", result: PENDING }])
    );

    mountStatus("path-stuck");
    await waitFor(() => expect(polls()).toHaveLength(PATH_NARRATION_MAX_POLLS), {
      timeout: 5000,
    });

    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));
    expect(polls()).toHaveLength(PATH_NARRATION_MAX_POLLS);
  });

  it("surfaces career_status_not_set as a failed job, not as a thrown error", async () => {
    server.use(
      signedIn(),
      pathSuggestionJobProgresses("path-2", [
        { status: "queued" },
        { status: "failed", error: "career_status_not_set" },
      ])
    );

    mountStatus("path-2");
    // The synchronous GET answered this condition with a 400. As a job it is an
    // in-band 200 carrying `failed`, which the page renders itself.
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("failed"));

    const countAtTerminal = polls().length;
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));
    expect(polls()).toHaveLength(countAtTerminal);
  });

  it("treats a 404 on a foreign handle as terminal without a retry storm", async () => {
    server.use(signedIn(), pathSuggestionJobProgresses("path-3", [{ status: "queued" }]));

    // A different id than the handler was built for -- the builder 404s it, as
    // the real endpoint does for an unknown or someone else's job.
    mountStatus("not-my-job");
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("error"));

    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));
    expect(polls()).toHaveLength(1);
  });

  it("issues no request while the job id is null", async () => {
    server.use(signedIn());

    mountStatus(null);
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));

    expect(polls()).toEqual([]);
  });
});

describe("useStartPathSuggestionJob", () => {
  it("posts to /me/path-suggestion-jobs and returns the handle", async () => {
    server.use(signedIn(), pathSuggestionJobAccepted("path-9"));

    render(
      <QueryClientProvider client={createQueryClient()}>
        <AuthProvider>
          <MutationHarness />
        </AuthProvider>
      </QueryClientProvider>
    );

    fireEvent.click(await screen.findByRole("button"));
    await waitFor(() =>
      expect(screen.getByTestId("mutation-status")).toHaveTextContent("path-9")
    );

    expect(requests).toContain("POST /api/v1/me/path-suggestion-jobs");
  });
});
