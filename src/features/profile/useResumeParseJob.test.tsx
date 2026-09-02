/**
 * useResumeParseJob.test.ts — the mutation + poll against a real network.
 *
 * Follows `AuthContext.boot.test.tsx`'s pattern (`useApiMocks()` +
 * `recordRequests()`, real `AuthProvider`/`QueryClientProvider`) rather than
 * mocking `useAuth`, because "polling stops" is a claim about requests on the
 * wire -- counting calls to a mocked function would prove nothing about
 * whether `refetchInterval` actually returned `false`.
 *
 * `pollIntervalMs` is overridden to a short real interval in every test here
 * rather than using fake timers: TanStack Query v5's interval scheduling
 * interacts with React's `act()` batching in ways that are known to be
 * fiddly under `vi.useFakeTimers()`, and this repo has no existing fake-timer
 * precedent to build on.
 */
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { HttpResponse } from "msw";

import { AuthProvider } from "../auth";
import { createQueryClient } from "../../shared/api/queryClient";
import { server, useApiMocks, recordRequests, signedIn } from "../../../tests/msw/server";
import { mock } from "../../../tests/msw/contract";
import {
  resumeParseJobAccepted,
  resumeParseJobProgresses,
  resumeParseJobNotFound,
} from "../../../tests/msw/resumeHandlers";
import { useResumeParseJobStatus, useStartResumeParseJob } from "./useResumeParseJob";

useApiMocks();
const { requests } = recordRequests();

const POLL_INTERVAL_MS = 20;
const parseJobRequests = () => requests.filter((r) => r.startsWith("GET /api/v1/me/resume-parse-jobs"));

function StatusHarness({ jobId }: { jobId: string | null }) {
  const status = useResumeParseJobStatus(jobId, { pollIntervalMs: POLL_INTERVAL_MS });
  const label = status.data?.status ?? (status.error ? "error" : status.isLoading ? "loading" : "none");
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
  const start = useStartResumeParseJob();
  const label = start.isSuccess ? start.data.job_id : start.isPending ? "pending" : "idle";
  return (
    <div>
      <button
        type="button"
        onClick={() =>
          start.mutate({ resumeId: "resume-1", mime: "application/pdf", size: 1234, name: "resume.pdf" })
        }
      >
        start
      </button>
      <span data-testid="mutation-status">{label}</span>
    </div>
  );
}

describe("useResumeParseJobStatus", () => {
  it("polls queued -> running -> succeeded and stops issuing requests once terminal", async () => {
    server.use(
      signedIn(),
      resumeParseJobProgresses("job-1", [
        { status: "queued" },
        { status: "running" },
        { status: "succeeded", profile: { firstName: "Ada" } },
      ])
    );

    mountStatus("job-1");
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("succeeded"));
    expect(parseJobRequests()).toHaveLength(3);

    const countAtTerminal = parseJobRequests().length;
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));
    expect(parseJobRequests()).toHaveLength(countAtTerminal);
  });

  it("surfaces a failed job as data, distinct from an error state, and stops polling", async () => {
    server.use(
      signedIn(),
      resumeParseJobProgresses("job-2", [
        { status: "queued" },
        { status: "failed", error: "Could not parse the uploaded resume." },
      ])
    );

    mountStatus("job-2");
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("failed"));

    const countAtTerminal = parseJobRequests().length;
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));
    expect(parseJobRequests()).toHaveLength(countAtTerminal);
  });

  it("treats a 404 (stale/foreign job id) as terminal without a retry storm", async () => {
    server.use(signedIn(), resumeParseJobNotFound("stale-job"));

    mountStatus("stale-job");
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("error"));

    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS * 6));
    // shouldRetry (queryClient.ts) treats 404 as non-retryable, so exactly one
    // request -- no built-in retries, and refetchInterval never got a status
    // to read since the query stayed in its error state.
    expect(parseJobRequests()).toHaveLength(1);
  });
});

describe("useStartResumeParseJob", () => {
  it("posts exactly the schema-named fields, not the full variables object", async () => {
    let capturedBody: unknown;
    server.use(
      signedIn(),
      mock("post", "/api/v1/me/resumes/{resume_id}/parse-jobs").resolve(async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json(
          { job_id: "job-9", status: "queued", status_url: "/api/v1/me/resume-parse-jobs/job-9" },
          { status: 202 }
        );
      })
    );

    render(
      <QueryClientProvider client={createQueryClient()}>
        <AuthProvider>
          <MutationHarness />
        </AuthProvider>
      </QueryClientProvider>
    );

    fireEvent.click(await screen.findByRole("button"));
    await waitFor(() => expect(screen.getByTestId("mutation-status")).toHaveTextContent("job-9"));

    // resumeId rides in the URL path only -- confirmed separately by the 202
    // succeeding against the `{resume_id}`-templated route above.
    expect(capturedBody).toEqual({ mime: "application/pdf", size: 1234, name: "resume.pdf" });
  });

  it("reports 202 acceptance via resumeParseJobAccepted for reuse in other suites", async () => {
    server.use(signedIn(), resumeParseJobAccepted("job-5"));

    render(
      <QueryClientProvider client={createQueryClient()}>
        <AuthProvider>
          <MutationHarness />
        </AuthProvider>
      </QueryClientProvider>
    );

    fireEvent.click(await screen.findByRole("button"));
    await waitFor(() => expect(screen.getByTestId("mutation-status")).toHaveTextContent("job-5"));
  });
});
