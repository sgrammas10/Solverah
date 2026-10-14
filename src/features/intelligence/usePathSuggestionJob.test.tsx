/**
 * usePathSuggestionJob.test.tsx — the path-suggestion mutation + poll on the wire.
 *
 * Same construction as `useScoringJob.test.tsx` and `useResumeParseJob.test.tsx`,
 * and for the same reason: "polling stops" is a claim about requests issued, so
 * the network is real (MSW) and the assertion is a request count.
 */
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { HttpResponse } from "msw";

import { AuthProvider } from "../auth";
import { createQueryClient } from "../../shared/api/queryClient";
import { server, useApiMocks, recordRequests, signedIn } from "../../../tests/msw/server";
import { mock } from "../../../tests/msw/contract";
import {
  pathSuggestionJobAccepted,
  pathSuggestionJobProgresses,
} from "../../../tests/msw/scoringJobHandlers";
import {
  PATH_NARRATION_MAX_POLLS,
  PATH_NARRATION_MAX_WAIT_MS,
  PATH_NARRATION_POLL_INTERVAL_MS,
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
      timeout: 15000,
    });

    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));
    expect(polls()).toHaveLength(PATH_NARRATION_MAX_POLLS);
    // W-18: the cap is 120 polls now (60 s at 0.5 s), so this walk takes a
    // few seconds even at the test's 20 ms interval -- past Vitest's 5 s
    // default when the whole suite shares the machine.
  }, 30_000);

  it("polls for sentences every half second, for about a minute (W-18)", () => {
    // W-17 measured the 1.5 s poll as most of the gap between a sentence
    // landing on the server and reaching the card. The cap is bounded by TIME,
    // matched to the server's 60 s NARRATION_DEADLINE: 60 polls at 0.5 s would
    // have given up after 30 s.
    expect(PATH_NARRATION_POLL_INTERVAL_MS).toBe(500);
    expect(PATH_NARRATION_MAX_WAIT_MS).toBe(60_000);
    expect(PATH_NARRATION_MAX_POLLS).toBe(120);
    expect(PATH_NARRATION_MAX_POLLS * PATH_NARRATION_POLL_INTERVAL_MS).toBe(60_000);
  });

  it("stops polling on a failed poll mid-narration rather than retrying (W-16)", async () => {
    // A 429 is the likeliest failure here: the page answers it by keeping the
    // cards and stopping the shimmer, so the hook must stop too.
    let call = 0;
    server.use(
      signedIn(),
      mock("get", "/api/v1/me/path-suggestion-jobs/{job_id}").resolve(() => {
        call += 1;
        if (call === 1) {
          return HttpResponse.json({
            job_id: "path-429",
            status: "succeeded",
            result: PENDING,
            error: null,
          });
        }
        return HttpResponse.json({ error: "Too Many Requests" }, { status: 429 });
      })
    );

    mountStatus("path-429");
    await waitFor(() => expect(polls().length).toBeGreaterThanOrEqual(2));

    const countAtError = polls().length;
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 8));
    expect(polls()).toHaveLength(countAtError);
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
