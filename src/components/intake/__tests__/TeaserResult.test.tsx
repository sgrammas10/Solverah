/**
 * TeaserResult.test.tsx — the WPLL teaser over the real job endpoints.
 *
 * This file used to stub `utils/api` with
 * `{ API_BASE: "http://localhost:5000/api" }` -- the *unversioned* base, which
 * Phase 1b retired. Nothing caught it, because the fetch stub answered whatever
 * URL it was handed; the test was exercising a base URL the app has not used
 * since the `/api/v1` cutover and would have kept passing if the real one broke.
 *
 * The mock is gone and the component resolves the real `API_BASE`. That is only
 * safe because the handlers below are bound to contract paths and unhandled
 * requests are errors: if the component posted somewhere else, no handler would
 * match and the test would fail rather than shrug.
 *
 * ── WHY THIS FILE KEEPS A REAL NETWORK WHERE THE PAGE TESTS MOCK THE HOOK ────
 *
 * Phase 3c moved this component onto `POST /assessments/wpll/scoring-jobs` plus
 * a poll. `wpll` is the one kind fetched *without* the session's credentials --
 * it is the anonymous teaser, its job has no owner, and the handle is the whole
 * of its authorisation. That transport choice is only observable on the wire,
 * so it is exercised here rather than stubbed: the providers below are real, no
 * session is established (the default probe 401s), and the job still resolves.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { HttpResponse } from "msw";

import TeaserResult from "../TeaserResult";
import { AuthProvider } from "../../../contexts/AuthContext.tsx";
import { createQueryClient } from "../../../utils/queryClient";
import { mock } from "../../../../tests/msw/contract";
import { server, useApiMocks, recordRequests } from "../../../../tests/msw/server";
import {
  scoringJobAccepted,
  scoringJobProgresses,
} from "../../../../tests/msw/scoringJobHandlers";

const MOCK_ANSWERS = [
  { questionId: "wpll-q1", optionId: "wpll-q1-a" },
  { questionId: "wpll-q2", optionId: "wpll-q2-b" },
];

const MOCK_RESULT = {
  insight_text: "You show strong signs of career misalignment.",
  locked_sections: ["Environmental Friction Score", "Work Rhythm Pattern", "Emerging Archetype Signals"],
};

useApiMocks();
const { requests } = recordRequests();

const ENQUEUE = "POST /api/v1/assessments/wpll/scoring-jobs";
const JOB_ID = "wpll-job-1";
const POLL = `GET /api/v1/assessments/wpll/scoring-jobs/${JOB_ID}`;

/** Only this instrument's traffic. `AuthProvider` also probes the session. */
const wpllRequests = () =>
  requests.filter((r) => r.includes("/assessments/wpll/scoring-jobs"));

/**
 * The teaser's happy path: the enqueue is accepted and the first poll already
 * carries the result.
 *
 * One step rather than a queued/running ladder because the component does not
 * expose a `pollIntervalMs` override, so a second poll would cost a real three
 * seconds of wall clock. That the polling ladder itself works -- and stops --
 * is proved with a short interval in `src/hooks/useScoringJob.test.tsx`.
 */
function teaserJobSucceeds(result = MOCK_RESULT) {
  return [
    scoringJobAccepted("wpll", JOB_ID),
    scoringJobProgresses("wpll", JOB_ID, [{ status: "succeeded", result }]),
  ];
}

function makeProps(overrides: Partial<Parameters<typeof TeaserResult>[0]> = {}) {
  return {
    wpllAnswers: MOCK_ANSWERS,
    onInsightReceived: vi.fn(),
    cachedInsightText: "",
    onContinue: vi.fn(),
    ...overrides,
  };
}

function renderTeaser(props: Parameters<typeof TeaserResult>[0]) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <TeaserResult {...props} />
      </AuthProvider>
    </QueryClientProvider>
  );
}

describe("TeaserResult", () => {
  beforeEach(() => {
    server.use(...teaserJobSucceeds());
  });

  it("renders insight text immediately when cachedInsightText is provided — no job", async () => {
    renderTeaser(makeProps({ cachedInsightText: "Cached insight here." }));

    expect(await screen.findByText("Cached insight here.")).toBeInTheDocument();
    expect(wpllRequests()).toEqual([]);
  });

  it("shows loading state on mount then renders insight once the job succeeds", async () => {
    renderTeaser(makeProps());

    // `findBy`, not `getBy`: AuthProvider renders its own spinner until the
    // session probe settles, so this component is not mounted synchronously.
    expect(await screen.findByText("Reading your responses…")).toBeInTheDocument();

    await waitFor(() =>
      expect(screen.getByText(MOCK_RESULT.insight_text)).toBeInTheDocument()
    );
  });

  it("enqueues the answers against the wpll scoring-jobs endpoint, then polls", async () => {
    let sent: { answers?: unknown } | undefined;
    server.use(
      mock("post", "/api/v1/assessments/{kind}/scoring-jobs").resolve(async ({ request }) => {
        sent = (await request.json()) as { answers?: unknown };
        return HttpResponse.json(
          {
            job_id: JOB_ID,
            status: "queued",
            status_url: `/api/v1/assessments/wpll/scoring-jobs/${JOB_ID}`,
          },
          { status: 202 }
        );
      })
    );

    renderTeaser(makeProps());
    await waitFor(() =>
      expect(screen.getByText(MOCK_RESULT.insight_text)).toBeInTheDocument()
    );

    // Enqueue then poll, on this instrument's own path -- `{kind}` is what
    // decides which of the three result shapes comes back.
    expect(wpllRequests()).toEqual([ENQUEUE, POLL]);
    // The enqueue carries the synchronous submit's body, unchanged (A19).
    expect(sent?.answers).toEqual([
      { question_id: "wpll-q1", option_id: "wpll-q1-a" },
      { question_id: "wpll-q2", option_id: "wpll-q2-b" },
    ]);
  });

  it("renders exactly 3 locked section cards", async () => {
    renderTeaser(makeProps());

    await waitFor(() =>
      expect(screen.getByText(MOCK_RESULT.insight_text)).toBeInTheDocument()
    );

    const unlockTexts = screen.getAllByText("Unlock with a free account");
    expect(unlockTexts).toHaveLength(3);
  });

  it("renders each locked section title", async () => {
    renderTeaser(makeProps());

    await waitFor(() =>
      expect(screen.getByText("Environmental Friction Score")).toBeInTheDocument()
    );
    expect(screen.getByText("Work Rhythm Pattern")).toBeInTheDocument();
    expect(screen.getByText("Emerging Archetype Signals")).toBeInTheDocument();
  });

  it("calls onInsightReceived with the insight text from the job result", async () => {
    const onInsightReceived = vi.fn();

    renderTeaser(makeProps({ onInsightReceived }));

    await waitFor(() =>
      expect(onInsightReceived).toHaveBeenCalledWith(MOCK_RESULT.insight_text)
    );
  });

  it("shows the error state when the job fails, and retry enqueues a new job", async () => {
    // A retry is a *new* scoring, so the server mints a new handle for it --
    // modelled here rather than replaying one id, because reusing a handle
    // would also mean reusing the failed job's cache entry, which is not what
    // the real endpoint does.
    const ids = ["wpll-job-1", "wpll-job-2"];
    let enqueued = 0;
    server.use(
      mock("post", "/api/v1/assessments/{kind}/scoring-jobs").resolve(() => {
        const jobId = ids[Math.min(enqueued, ids.length - 1)];
        enqueued += 1;
        return HttpResponse.json(
          {
            job_id: jobId,
            status: "queued",
            status_url: `/api/v1/assessments/wpll/scoring-jobs/${jobId}`,
          },
          { status: 202 }
        );
      }),
      mock("get", "/api/v1/assessments/{kind}/scoring-jobs/{job_id}").resolve(({ params }) =>
        // A `failed` job is an in-band 200, not a transport error -- the
        // component has to read the status rather than rely on a rejection.
        HttpResponse.json(
          params.job_id === "wpll-job-1"
            ? { job_id: params.job_id, status: "failed", result: null, error: "scoring_failed" }
            : { job_id: params.job_id, status: "succeeded", result: MOCK_RESULT, error: null }
        )
      )
    );

    renderTeaser(makeProps());

    await waitFor(() =>
      expect(
        screen.getByText("We couldn't generate your insight right now.")
      ).toBeInTheDocument()
    );
    // Failed is its own screen, not a spinner the visitor is left to interpret.
    expect(screen.queryByText("Reading your responses…")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    await waitFor(() =>
      expect(screen.getByText(MOCK_RESULT.insight_text)).toBeInTheDocument()
    );

    expect(wpllRequests()).toEqual([
      ENQUEUE,
      "GET /api/v1/assessments/wpll/scoring-jobs/wpll-job-1",
      ENQUEUE,
      "GET /api/v1/assessments/wpll/scoring-jobs/wpll-job-2",
    ]);
  });

  it("shows the error state when the enqueue itself fails", async () => {
    server.use(
      mock("post", "/api/v1/assessments/{kind}/scoring-jobs").resolve(() =>
        HttpResponse.json({ error: "Too many requests" }, { status: 429 })
      )
    );

    renderTeaser(makeProps());

    await waitFor(() =>
      expect(
        screen.getByText("We couldn't generate your insight right now.")
      ).toBeInTheDocument()
    );
  });

  it("calls onContinue when the CTA button is clicked", async () => {
    const onContinue = vi.fn();

    renderTeaser(makeProps({ onContinue }));

    await waitFor(() =>
      expect(screen.getByText(MOCK_RESULT.insight_text)).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole("button", { name: /create my free account/i }));
    expect(onContinue).toHaveBeenCalledTimes(1);
  });
});
