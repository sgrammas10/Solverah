/**
 * WorkPulseResultsPage.test.tsx — the page's branching, over a mocked scoring job.
 *
 * The job hooks are mocked here (as `useProfileForm.test.tsx` mocks
 * `useResumeParseJob`) rather than driven over MSW, because this file already
 * mocks `useAuth` itself and is about which screen the page puts up in which
 * state. The wire-level claims — that polling stops on a terminal status, that
 * a failed job is data rather than a thrown error — are proved against a real
 * network in `src/hooks/useScoringJob.test.tsx`, and are not restated here.
 *
 * `isKnownScoringPhase` is left real: it is the fail-closed check the page
 * calls, and stubbing it would remove the thing under test in the last case.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import WorkPulseResultsPage from "./WorkPulseResultsPage";
import { WP_QUESTIONS } from "../data/wpQuestions";
import { createQueryClient } from "../utils/queryClient";
import type { WpApiResponse } from "../hooks/useWP";

// vi.hoisted ensures these are available inside the vi.mock factories,
// which run before module-level variable initialisations.
const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
  updateProfile: vi.fn(),
  setCachedResult: vi.fn(),
  startScoringMutate: vi.fn(),
  user: null as { wpl_completed: boolean } | null,
  wpState: {
    answers: [] as { questionId: string; optionId: string }[],
    cachedResult: null as WpApiResponse | null,
  },
  /** What `useScoringJobStatus` reports on the next render. */
  job: { data: undefined as Record<string, unknown> | undefined, error: null as Error | null },
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => mocks.navigate,
}));

vi.mock("../contexts/useAuth", () => ({
  useAuth: () => ({
    fetchWithAuth: mocks.fetchWithAuth,
    updateProfile: mocks.updateProfile,
    user: mocks.user,
  }),
}));

vi.mock("../hooks/useWP", () => ({
  useWP: () => ({
    state: mocks.wpState,
    setCachedResult: mocks.setCachedResult,
  }),
}));

vi.mock("../hooks/useScoringJob", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../hooks/useScoringJob")>();
  return {
    ...actual,
    useStartScoringJob: () => ({ mutate: mocks.startScoringMutate }),
    useScoringJobStatus: () => mocks.job,
  };
});

// TierBar is a pure component — no mock needed.

const ALL_ANSWERS = WP_QUESTIONS.map((q) => ({
  questionId: q.id,
  optionId: q.options[0].id,
}));

const MOCK_RESULT: WpApiResponse = {
  narrative: "You bring deep focus to your work.\n\nRecovery matters to you.",
  emerging_signals: [
    { title: "Deep Focus Seeker", description: "You need uninterrupted time to reach your best." },
  ],
  archetype: "Structured Deep Thinker",
  archetype_description: "You pair sustained concentration with a need for clear structure.",
};

/** The 202 the enqueue answers with. */
const ACCEPTED = {
  job_id: "wp-job-1",
  status: "queued",
  status_url: "/api/v1/assessments/work_pulse/scoring-jobs/wp-job-1",
};

/**
 * Make the enqueue succeed, and make the poll that follows report `status`.
 *
 * The page sets its job id inside `onSuccess`, which re-renders and re-reads
 * `useScoringJobStatus` — so writing `mocks.job.data` before invoking the
 * callback is what the second render then sees.
 */
function scoringSettlesAs(job: Record<string, unknown>) {
  mocks.startScoringMutate.mockImplementation(
    (_body: unknown, opts: { onSuccess?: (a: typeof ACCEPTED) => void }) => {
      mocks.job.data = job;
      opts.onSuccess?.(ACCEPTED);
    }
  );
}

/**
 * The client the page invalidates through, kept so a test can assert on it.
 *
 * Built per render rather than shared: a client that outlived a test would
 * carry its cache into the next one.
 */
let queryClient: QueryClient;

function renderPage() {
  queryClient = createQueryClient();
  vi.spyOn(queryClient, "invalidateQueries");
  render(
    <QueryClientProvider client={queryClient}>
      <WorkPulseResultsPage />
    </QueryClientProvider>
  );
}

describe("WorkPulseResultsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: all 12 answers present (avoids navigation redirect), no cached result, not yet completed.
    mocks.wpState.answers = ALL_ANSWERS;
    mocks.wpState.cachedResult = null;
    mocks.user = null;
    mocks.job.data = undefined;
    mocks.job.error = null;
  });

  // ── Pending state ──────────────────────────────────────────────────────────

  it("shows the scoring state while the job is queued", async () => {
    scoringSettlesAs({ job_id: "wp-job-1", status: "queued", result: null, error: null });
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("Analysing your responses…")).toBeInTheDocument()
    );
    // Pending says so, rather than leaving the user to infer it from a spinner
    // that has not stopped.
    expect(screen.getByText(/This usually takes under a minute/)).toBeInTheDocument();
  });

  it("keeps showing the scoring state while the job is running", async () => {
    scoringSettlesAs({ job_id: "wp-job-1", status: "running", result: null, error: null });
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("Analysing your responses…")).toBeInTheDocument()
    );
    expect(screen.queryByText("We couldn't generate your results right now.")).toBeNull();
  });

  // ── Success state ──────────────────────────────────────────────────────────

  it("renders all three result sections when the job succeeds", async () => {
    scoringSettlesAs({
      job_id: "wp-job-1",
      status: "succeeded",
      result: MOCK_RESULT,
      error: null,
    });
    renderPage();

    // Narrative — first paragraph
    await waitFor(() =>
      expect(screen.getByText("You bring deep focus to your work.")).toBeInTheDocument()
    );
    // Narrative — second paragraph
    expect(screen.getByText("Recovery matters to you.")).toBeInTheDocument();
    // Emerging signal
    expect(screen.getByText("Deep Focus Seeker")).toBeInTheDocument();
    // Archetype callout
    expect(screen.getByText("Structured Deep Thinker")).toBeInTheDocument();
  });

  it("enqueues the answers in the submit's own body shape", async () => {
    scoringSettlesAs({
      job_id: "wp-job-1",
      status: "succeeded",
      result: MOCK_RESULT,
      error: null,
    });
    renderPage();

    await waitFor(() => expect(mocks.startScoringMutate).toHaveBeenCalledTimes(1));
    // A19: the enqueue takes the synchronous submit's body, unchanged.
    expect(mocks.startScoringMutate.mock.calls[0][0]).toEqual({
      answers: ALL_ANSWERS.map((a) => ({ question_id: a.questionId, option_id: a.optionId })),
    });
  });

  it("routes a succeeded job's result exactly where the sync response went", async () => {
    scoringSettlesAs({
      job_id: "wp-job-1",
      status: "succeeded",
      result: MOCK_RESULT,
      error: null,
    });
    renderPage();

    await waitFor(() => expect(mocks.setCachedResult).toHaveBeenCalledWith(MOCK_RESULT));
    // The completion flag the shell gates on is still set from here.
    expect(mocks.updateProfile).toHaveBeenCalledWith({ wpl_completed: true });
    // And the profile document the server has now written this result into --
    // without this, a screen reading it through useProfile() shows a
    // pre-completion copy for up to the 60 s staleTime.
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["profile", "document"],
    });
  });

  it("does not invalidate the profile document while the job is still running", async () => {
    scoringSettlesAs({ job_id: "wp-job-1", status: "running", result: null, error: null });
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("Analysing your responses…")).toBeInTheDocument()
    );
    expect(queryClient.invalidateQueries).not.toHaveBeenCalled();
    expect(mocks.updateProfile).not.toHaveBeenCalled();
  });

  it("renders from cached result immediately without enqueuing anything", () => {
    mocks.wpState.cachedResult = MOCK_RESULT;
    mocks.user = { wpl_completed: true };
    renderPage();

    expect(screen.getByText("Structured Deep Thinker")).toBeInTheDocument();
    expect(screen.getByText("You bring deep focus to your work.")).toBeInTheDocument();
    expect(mocks.startScoringMutate).not.toHaveBeenCalled();
    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
  });

  // ── Failed state ───────────────────────────────────────────────────────────

  it("shows the failed state — not the scoring one — when the job fails", async () => {
    scoringSettlesAs({
      job_id: "wp-job-1",
      status: "failed",
      result: null,
      error: "The scorer could not read those answers.",
    });
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByText("We couldn't generate your results right now.")
      ).toBeInTheDocument()
    );
    // The scorer's own message, and definitively not the pending copy: a failed
    // scoring must not be distinguishable from a slow one only by patience.
    expect(screen.getByText("The scorer could not read those answers.")).toBeInTheDocument();
    expect(screen.queryByText("Analysing your responses…")).toBeNull();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("shows the failed state when the enqueue itself is rejected", async () => {
    mocks.startScoringMutate.mockImplementation(
      (_body: unknown, opts: { onError?: (e: Error) => void }) => {
        opts.onError?.(new Error("429"));
      }
    );
    renderPage();

    await waitFor(() =>
      expect(
        screen.getByText("We couldn't generate your results right now.")
      ).toBeInTheDocument()
    );
    expect(screen.queryByText("Analysing your responses…")).toBeNull();
  });

  it("fails closed on a status this client does not recognise", async () => {
    scoringSettlesAs({
      job_id: "wp-job-1",
      status: "reticulating_splines",
      result: null,
      error: null,
    });
    renderPage();

    // The hook has stopped polling such a status, so the page must not sit on
    // the spinner waiting for a poll that will never be issued.
    await waitFor(() =>
      expect(
        screen.getByText("We couldn't generate your results right now.")
      ).toBeInTheDocument()
    );
  });

  it("clicking Try again re-enqueues and shows results on the second attempt", async () => {
    scoringSettlesAs({
      job_id: "wp-job-1",
      status: "failed",
      result: null,
      error: "First failure.",
    });
    renderPage();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument()
    );

    scoringSettlesAs({
      job_id: "wp-job-2",
      status: "succeeded",
      result: MOCK_RESULT,
      error: null,
    });
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    await waitFor(() =>
      expect(screen.getByText("Structured Deep Thinker")).toBeInTheDocument()
    );
    expect(mocks.startScoringMutate).toHaveBeenCalledTimes(2);
  });

  // ── Navigation guard ───────────────────────────────────────────────────────

  it("redirects to /work-pulse when no answers are present and user has not completed WP", () => {
    mocks.wpState.answers = [];
    mocks.user = null;
    renderPage();
    expect(mocks.navigate).toHaveBeenCalledWith("/work-pulse", { replace: true });
    expect(mocks.startScoringMutate).not.toHaveBeenCalled();
  });

  // ── Fresh-session server fetch ─────────────────────────────────────────────

  it("reads the stored result synchronously when wpl_completed but nothing is cached", async () => {
    mocks.wpState.answers = [];
    mocks.user = { wpl_completed: true };
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_RESULT);
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("Structured Deep Thinker")).toBeInTheDocument()
    );
    expect(mocks.navigate).not.toHaveBeenCalled();
    // Still a plain GET: this reads a persisted row and opens no socket, so it
    // was never one of the three that moved to a job.
    expect(mocks.fetchWithAuth).toHaveBeenCalledWith("/me/assessments/work_pulse/result");
    expect(mocks.startScoringMutate).not.toHaveBeenCalled();
  });
});
