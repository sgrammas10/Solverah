/**
 * ManagerMatchPage.test.tsx — the page's phases, over a mocked scoring job.
 *
 * The job hooks are mocked here (as `useProfileForm.test.tsx` mocks
 * `useResumeParseJob`) rather than driven over MSW, because this file is about
 * which phase the page is in. The wire-level claims — polling stops on a
 * terminal status, a failed job arrives as data — are proved against a real
 * network in `src/hooks/useScoringJob.test.tsx`.
 *
 * `isKnownScoringPhase` is left real: it is the fail-closed check the page
 * calls, and stubbing it would remove what one of these cases is testing.
 */
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import ManagerMatchPage from "../ManagerMatchPage";
import { MM_QUESTIONS } from "../../data/mmQuestions";
import { createQueryClient } from "../../utils/queryClient";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  reset: vi.fn(),
  setAnswer: vi.fn(),
  setCachedResult: vi.fn(),
  startScoringMutate: vi.fn(),
  mmState: { answers: [] as any[], cachedResult: null as any },
  /** What `useScoringJobStatus` reports on the next render. */
  job: { data: undefined as any, error: null as Error | null },
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../hooks/useMM", () => ({
  useMM: () => ({
    state: mocks.mmState,
    setAnswer: mocks.setAnswer,
    setCachedResult: mocks.setCachedResult,
    reset: mocks.reset,
  }),
}));

vi.mock("../../hooks/useScoringJob", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../hooks/useScoringJob")>();
  return {
    ...actual,
    useStartScoringJob: () => ({ mutate: mocks.startScoringMutate }),
    useScoringJobStatus: () => mocks.job,
  };
});

/** The 202 the enqueue answers with. */
const ACCEPTED = {
  job_id: "mm-job-1",
  status: "queued",
  status_url: "/api/v1/assessments/manager_match/scoring-jobs/mm-job-1",
};

/**
 * Make the enqueue succeed, and make the poll that follows report `job`.
 *
 * The page sets its job id inside `onSuccess`, which re-renders and re-reads
 * `useScoringJobStatus`, so writing `mocks.job.data` first is what that second
 * render sees.
 */
function scoringSettlesAs(job: Record<string, unknown>) {
  mocks.startScoringMutate.mockImplementation(
    (_body: unknown, opts: { onSuccess?: (a: typeof ACCEPTED) => void }) => {
      mocks.job.data = job;
      opts.onSuccess?.(ACCEPTED);
    }
  );
}

/** Leave the job queued: the enqueue lands, nothing terminal follows. */
function scoringStaysQueued() {
  scoringSettlesAs({ job_id: "mm-job-1", status: "queued", result: null, error: null });
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.mmState = { answers: [], cachedResult: null };
  mocks.job.data = undefined;
  mocks.job.error = null;
});

/**
 * The client the page invalidates through, kept so a test can assert on it.
 * Built per render so no cache crosses a test boundary.
 */
let queryClient: QueryClient;

function renderPage(locationState?: object) {
  queryClient = createQueryClient();
  vi.spyOn(queryClient, "invalidateQueries");
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[{ pathname: "/manager-match", state: locationState }]}>
        <ManagerMatchPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

/** Answer all 15 forced choices, which is what triggers the enqueue. */
async function answerEveryQuestion() {
  fireEvent.click(screen.getByRole("button", { name: /Start ManagerMatch™/i }));
  for (let i = 0; i < 14; i++) {
    fireEvent.click(screen.getByText(MM_QUESTIONS[i].optionA));
  }
  await act(async () => {
    fireEvent.click(screen.getByText(MM_QUESTIONS[14].optionA));
  });
}

// ── intro phase ───────────────────────────────────────────────────────────────

describe("ManagerMatchPage - intro phase", () => {
  it("renders intro screen with disclaimer text visible", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: "ManagerMatch™" })).toBeInTheDocument();
    expect(
      screen.getByText(/Each choice is final — there is no going back/i)
    ).toBeInTheDocument();
  });

  it("clicking 'Start ManagerMatch™' renders the first question with both option cards", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Start ManagerMatch™/i }));
    expect(screen.getByText(MM_QUESTIONS[0].optionA)).toBeInTheDocument();
    expect(screen.getByText(MM_QUESTIONS[0].optionB)).toBeInTheDocument();
  });

  it("shows 'Question 1 of 15' indicator after starting", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Start ManagerMatch™/i }));
    expect(screen.getByText(/Question 1 of 15/i)).toBeInTheDocument();
  });
});

// ── questions phase ───────────────────────────────────────────────────────────

describe("ManagerMatchPage - questions phase", () => {
  it("clicking an option card on question 1 advances to question 2", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Start ManagerMatch™/i }));
    fireEvent.click(screen.getByText(MM_QUESTIONS[0].optionA));
    expect(screen.getByText(/Question 2 of 15/i)).toBeInTheDocument();
    expect(screen.getByText(MM_QUESTIONS[1].optionA)).toBeInTheDocument();
  });

  it("calls setAnswer when an option is selected", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Start ManagerMatch™/i }));
    fireEvent.click(screen.getByText(MM_QUESTIONS[0].optionA));
    expect(mocks.setAnswer).toHaveBeenCalledWith("mm-q1", "a");
  });
});

// ── submitting (pending) phase ────────────────────────────────────────────────

describe("ManagerMatchPage - submitting phase", () => {
  it("after all 15 answers the scoring is enqueued once, in the submit's body shape", async () => {
    scoringStaysQueued();
    renderPage();
    await answerEveryQuestion();

    await waitFor(() =>
      expect(screen.getByText(/Analysing your management preferences/i)).toBeInTheDocument()
    );
    // Pending says it is pending, rather than leaving the user to read a
    // spinner that has not stopped.
    expect(screen.getByText(/This usually takes under a minute/)).toBeInTheDocument();

    expect(mocks.startScoringMutate).toHaveBeenCalledTimes(1);
    // A19: the enqueue carries the synchronous submit's body, unchanged.
    const body = mocks.startScoringMutate.mock.calls[0][0];
    expect(body.answers).toHaveLength(15);
    expect(body.answers[0]).toMatchObject({
      question_id: expect.any(String),
      choice: expect.stringMatching(/^[ab]$/),
    });
  });

  it("navigates to /manager-match/results when the job succeeds", async () => {
    const mockResult = {
      archetype: "The Autonomist",
      dimension_scores: {},
      narrative: "...",
      what_to_look_for: [],
      red_flags: [],
      archetype_description: "...",
    };
    scoringSettlesAs({
      job_id: "mm-job-1",
      status: "succeeded",
      result: mockResult,
      error: null,
    });
    renderPage();
    await answerEveryQuestion();

    await waitFor(() =>
      expect(mocks.navigate).toHaveBeenCalledWith('/manager-match/results')
    );
    // The result goes exactly where the synchronous response went.
    expect(mocks.setCachedResult).toHaveBeenCalledWith(mockResult);
    // And the profile document is invalidated, because that is where
    // ManagerMatchResultsPage looks first (`profile.manager_match_result`).
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["profile", "document"],
    });
  });

  it("does not invalidate the profile document while the job is still queued", async () => {
    scoringStaysQueued();
    renderPage();
    await answerEveryQuestion();

    await waitFor(() =>
      expect(screen.getByText(/Analysing your management preferences/i)).toBeInTheDocument()
    );
    expect(queryClient.invalidateQueries).not.toHaveBeenCalled();
    expect(mocks.navigate).not.toHaveBeenCalled();
  });
});

// ── error (failed) phase ──────────────────────────────────────────────────────

describe("ManagerMatchPage - error phase", () => {
  it("renders the failed phase, not the pending one, when the job fails", async () => {
    scoringSettlesAs({
      job_id: "mm-job-1",
      status: "failed",
      result: null,
      error: "The scorer could not read those answers.",
    });
    renderPage();
    await answerEveryQuestion();

    await waitFor(() =>
      expect(screen.getByText(/We couldn't generate your results right now/i)).toBeInTheDocument()
    );
    // The scorer's own message, and definitively not the pending copy: a failed
    // scoring must not be distinguishable from a slow one only by patience.
    expect(screen.getByText("The scorer could not read those answers.")).toBeInTheDocument();
    expect(screen.queryByText(/Analysing your management preferences/i)).toBeNull();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("renders the failed phase when the enqueue itself is rejected", async () => {
    mocks.startScoringMutate.mockImplementation(
      (_body: unknown, opts: { onError?: (e: Error) => void }) => {
        opts.onError?.(new Error("429"));
      }
    );
    renderPage();
    await answerEveryQuestion();

    await waitFor(() =>
      expect(screen.getByText(/We couldn't generate your results right now/i)).toBeInTheDocument()
    );
  });

  it("fails closed on a status this client does not recognise", async () => {
    scoringSettlesAs({
      job_id: "mm-job-1",
      status: "reticulating_splines",
      result: null,
      error: null,
    });
    renderPage();
    await answerEveryQuestion();

    // The hook stopped polling that status, so sitting on the spinner would
    // hang the screen forever.
    await waitFor(() =>
      expect(screen.getByText(/We couldn't generate your results right now/i)).toBeInTheDocument()
    );
  });

  it("try again re-enqueues after a failure", async () => {
    scoringSettlesAs({
      job_id: "mm-job-1",
      status: "failed",
      result: null,
      error: "First failure.",
    });
    renderPage();
    await answerEveryQuestion();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument()
    );

    scoringStaysQueued();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    });

    // The single-fire guard exists to stop one submission double-firing, not to
    // make a failure final.
    expect(mocks.startScoringMutate).toHaveBeenCalledTimes(2);
  });
});


// ── retake flow ───────────────────────────────────────────────────────────────

describe("ManagerMatchPage - retake flow", () => {
  it("with location.state = { retake: true }, reset() is called on mount", () => {
    renderPage({ retake: true });
    expect(mocks.reset).toHaveBeenCalledTimes(1);
  });

  it("retake shows the intro screen", () => {
    renderPage({ retake: true });
    expect(screen.getByRole("heading", { name: "ManagerMatch™" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Start ManagerMatch™/i })).toBeInTheDocument();
  });
});
