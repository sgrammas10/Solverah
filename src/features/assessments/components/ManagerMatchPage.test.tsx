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
import ManagerMatchPage from "./ManagerMatchPage";
import { MM_QUESTIONS } from "../data/mmQuestions";
import { createQueryClient } from "../../../shared/api/queryClient";
import { ApiError } from "../../../shared/api/apiError";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  reset: vi.fn(),
  clearAnswers: vi.fn(),
  setAnswer: vi.fn(),
  setCachedResult: vi.fn(),
  startScoringMutate: vi.fn(),
  mmState: { answers: [] as any[], cachedResult: null as any },
  /** What `useScoringJobStatus` reports on the next render. */
  job: { data: undefined as any, error: null as Error | null },
  /** What `useManagerMatchResult` reports, and the `enabled` it was last given. */
  storedResult: { data: undefined as unknown, error: null as unknown },
  storedResultEnabled: undefined as boolean | undefined,
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../useMM", () => ({
  useMM: () => ({
    state: mocks.mmState,
    setAnswer: mocks.setAnswer,
    setCachedResult: mocks.setCachedResult,
    clearAnswers: mocks.clearAnswers,
    reset: mocks.reset,
  }),
}));

// The stored-result check on mount. `isNoManagerMatchResult` stays real: the
// 404-by-status decision is part of what these cases test.
vi.mock("../useManagerMatchResult", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../useManagerMatchResult")>();
  return {
    ...actual,
    useManagerMatchResult: (options: { enabled?: boolean } = {}) => {
      mocks.storedResultEnabled = options.enabled;
      return mocks.storedResult;
    },
  };
});

vi.mock("../useScoringJob", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../useScoringJob")>();
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
  mocks.storedResult = { data: undefined, error: null };
  mocks.storedResultEnabled = undefined;
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
  it("does not brand the free, live quiz as a Pro tier", () => {
    renderPage();
    expect(screen.queryByText(/WorkPulse Pro|Work Pulse Pro/)).toBeNull();
    expect(screen.getByText("Manager fit")).toBeInTheDocument();
  });

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

  it("clears the draft once the job succeeds", async () => {
    // Regression (audit 2026-10-02, F2): the 15-answer draft stayed in
    // sessionStorage after scoring, and the next visit re-scored it.
    scoringSettlesAs({
      job_id: "mm-job-1",
      status: "succeeded",
      result: { archetype: "The Autonomist", dimension_scores: {} },
      error: null,
    });
    renderPage();
    await answerEveryQuestion();

    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith('/manager-match/results'));
    expect(mocks.clearAnswers).toHaveBeenCalled();
    // A draft clear, not a reset: the result just cached must survive.
    expect(mocks.reset).not.toHaveBeenCalled();
  });

  it("invalidates the manager playbook when the job succeeds", async () => {
    // Regression (F3): the playbook diffs against these needs, so a retake
    // left a stale cached playbook for up to the 60 s staleTime.
    scoringSettlesAs({
      job_id: "mm-job-1",
      status: "succeeded",
      result: { archetype: "The Autonomist", dimension_scores: {} },
      error: null,
    });
    renderPage();
    await answerEveryQuestion();

    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith('/manager-match/results'));
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["managerPlaybook"],
    });
  });

  it("does not clear the draft while the job is still queued", async () => {
    // A reload mid-scoring needs the draft: it is the only copy of the answers.
    scoringStaysQueued();
    renderPage();
    await answerEveryQuestion();

    await waitFor(() =>
      expect(screen.getByText(/Analysing your management preferences/i)).toBeInTheDocument()
    );
    expect(mocks.clearAnswers).not.toHaveBeenCalled();
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

// ── resume prompt ─────────────────────────────────────────────────────────────

describe("ManagerMatchPage - resume prompt for a saved draft", () => {
  function draftOf(n: number) {
    return MM_QUESTIONS.slice(0, n).map((q) => ({ questionId: q.id, choice: "a" as const }));
  }

  it("asks before resuming rather than jumping silently into the questions", () => {
    // Regression: a 4-answer draft used to open straight on "Question 5 of 15".
    mocks.mmState = { answers: draftOf(4), cachedResult: null };
    renderPage();
    expect(screen.getByRole("button", { name: "Pick up where you left off" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start over" })).toBeInTheDocument();
    expect(screen.queryByText(/Question 5 of 15/)).toBeNull();
  });

  it("'Pick up where you left off' lands on the first unanswered question", () => {
    mocks.mmState = { answers: draftOf(4), cachedResult: null };
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Pick up where you left off" }));
    expect(screen.getByText(/Question 5 of 15/)).toBeInTheDocument();
    expect(mocks.reset).not.toHaveBeenCalled();
  });

  it("'Start over' clears the draft and lands on question 1", () => {
    mocks.mmState = { answers: draftOf(4), cachedResult: null };
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Start over" }));
    expect(mocks.reset).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Question 1 of 15/)).toBeInTheDocument();
  });

  it("a retake never shows the prompt", () => {
    mocks.mmState = { answers: draftOf(4), cachedResult: null };
    renderPage({ retake: true });
    expect(screen.queryByRole("button", { name: "Start over" })).toBeNull();
  });
});


// ── a complete draft on mount ─────────────────────────────────────────────────

describe("ManagerMatchPage - complete draft found on mount", () => {
  const completeDraft = () =>
    MM_QUESTIONS.map((q) => ({ questionId: q.id, choice: "a" as const }));

  it("sends the user to their stored result instead of re-scoring", async () => {
    // Regression (audit 2026-10-02, F2): a complete draft with an empty query
    // cache (any reload) was re-enqueued on mount, re-scoring a finished
    // sitting -- an LLM call and a replaced narrative on every visit.
    mocks.mmState = { answers: completeDraft(), cachedResult: null };
    mocks.storedResult = { data: { archetype: "The Autonomist" }, error: null };
    renderPage();

    await waitFor(() =>
      expect(mocks.navigate).toHaveBeenCalledWith('/manager-match/results', { replace: true })
    );
    expect(mocks.startScoringMutate).not.toHaveBeenCalled();
    expect(mocks.clearAnswers).toHaveBeenCalled();
  });

  it("asks the server only when the draft at mount is complete", () => {
    mocks.mmState = { answers: completeDraft(), cachedResult: null };
    mocks.storedResult = { data: undefined, error: null }; // still in flight
    renderPage();

    expect(mocks.storedResultEnabled).toBe(true);
    expect(screen.getByText(/Checking for your results/i)).toBeInTheDocument();
    expect(mocks.startScoringMutate).not.toHaveBeenCalled();
  });

  it("does not ask the server for a fresh sitting", () => {
    renderPage();
    expect(mocks.storedResultEnabled).toBe(false);
    expect(screen.getByRole("button", { name: /Start ManagerMatch™/i })).toBeInTheDocument();
  });

  it("scores the draft when the server has no result (404)", async () => {
    // The reload landed before the job finished: the draft is the only copy.
    scoringStaysQueued();
    mocks.mmState = { answers: completeDraft(), cachedResult: null };
    mocks.storedResult = {
      data: undefined,
      error: new ApiError("No ManagerMatch result found", { status: 404 }),
    };
    renderPage();

    await waitFor(() => expect(mocks.startScoringMutate).toHaveBeenCalledTimes(1));
    expect(mocks.startScoringMutate.mock.calls[0][0].answers).toHaveLength(15);
    expect(mocks.navigate).not.toHaveBeenCalled();
  });

  it("does not act on a cached 404 while the fresh check is still in flight", () => {
    // A 404 cached by an earlier visit survives the refetch this mount starts.
    mocks.mmState = { answers: completeDraft(), cachedResult: null };
    mocks.storedResult = {
      data: undefined,
      error: new ApiError("No ManagerMatch result found", { status: 404 }),
      isFetching: true,
    } as typeof mocks.storedResult;
    renderPage();

    expect(mocks.startScoringMutate).not.toHaveBeenCalled();
    expect(screen.getByText(/Checking for your results/i)).toBeInTheDocument();
  });

  it("never re-scores on an error that is not the 404", async () => {
    mocks.mmState = { answers: completeDraft(), cachedResult: null };
    mocks.storedResult = {
      data: undefined,
      error: new ApiError("Service unavailable", { status: 503 }),
    };
    renderPage();

    await waitFor(() =>
      expect(mocks.navigate).toHaveBeenCalledWith('/manager-match/results', { replace: true })
    );
    expect(mocks.startScoringMutate).not.toHaveBeenCalled();
  });

  it("goes straight to results, and drops the draft, when the result is already cached", () => {
    mocks.mmState = { answers: completeDraft(), cachedResult: { archetype: "The Autonomist" } };
    renderPage();

    expect(mocks.navigate).toHaveBeenCalledWith('/manager-match/results', { replace: true });
    expect(mocks.clearAnswers).toHaveBeenCalled();
    expect(mocks.storedResultEnabled).toBe(false);
    expect(mocks.startScoringMutate).not.toHaveBeenCalled();
  });

  it("a retake with a complete draft resets instead of checking or scoring", () => {
    mocks.mmState = { answers: completeDraft(), cachedResult: null };
    renderPage({ retake: true });

    expect(mocks.reset).toHaveBeenCalledTimes(1);
    expect(mocks.storedResultEnabled).toBe(false);
    expect(mocks.startScoringMutate).not.toHaveBeenCalled();
  });
});
