/**
 * WorkPulseResultsPage.test.tsx — the retired quiz's stored narrative, read-only.
 *
 * Until 2026-10-02 this page could enqueue a scoring job for the 12-question quiz and
 * resubmit answers after a missing narrative; those paths were deleted when the
 * instrument was retired, and the tests below pin that they stay gone. What remains:
 * a legacy completer sees the narrative stored for them, and anyone with nothing
 * stored is sent to /work-pulse.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import WorkPulseResultsPage from "./WorkPulseResultsPage";
import { createQueryClient } from "../../../shared/api/queryClient";
import { ApiError } from "../../../shared/api/apiError";
import type { WpApiResponse } from "../useWP";

// vi.hoisted ensures these are available inside the vi.mock factories,
// which run before module-level variable initialisations.
const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
  user: null as { wpl_completed: boolean } | null,
  wpState: { cachedResult: null as WpApiResponse | null },
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => mocks.navigate,
  Navigate: ({ to }: { to: string }) => <div data-testid="redirect">{to}</div>,
  // The page renders no router; a plain anchor is all the links need here.
  Link: ({ to, children, ...rest }: { to: string; children: React.ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({
    fetchWithAuth: mocks.fetchWithAuth,
    user: mocks.user,
  }),
}));

vi.mock("../useWP", () => ({
  useWP: () => ({ state: mocks.wpState, setCachedResult: vi.fn() }),
}));

const MOCK_RESULT: WpApiResponse = {
  narrative: "You bring deep focus to your work.\n\nRecovery matters to you.",
  emerging_signals: [
    { title: "Deep Focus Seeker", description: "You need uninterrupted time to reach your best." },
  ],
  archetype: "Structured Deep Thinker",
  archetype_description: "You pair sustained concentration with a need for clear structure.",
};

function notFound() {
  return new ApiError("No Work Pulse results found", { status: 404 });
}

function renderPage() {
  // Retries off: a 5xx must reach the error card inside the test's waitFor.
  const queryClient = createQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false } });
  render(
    <QueryClientProvider client={queryClient}>
      <WorkPulseResultsPage />
    </QueryClientProvider>
  );
}

describe("WorkPulseResultsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.wpState.cachedResult = null;
    mocks.user = null;
  });

  // ── The read-only view ─────────────────────────────────────────────────────

  it("reads the stored narrative for a legacy completer and renders it", async () => {
    mocks.user = { wpl_completed: true };
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_RESULT);
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("Structured Deep Thinker")).toBeInTheDocument()
    );
    expect(screen.getByText("You bring deep focus to your work.")).toBeInTheDocument();
    expect(screen.getByText("Recovery matters to you.")).toBeInTheDocument();
    expect(screen.getByText("Deep Focus Seeker")).toBeInTheDocument();
    // Still a plain GET of the persisted row.
    expect(mocks.fetchWithAuth).toHaveBeenCalledWith("/me/assessments/work_pulse/result", {
      method: "GET",
    });
    expect(mocks.fetchWithAuth).toHaveBeenCalledTimes(1);
  });

  it("says the page is a record of the retired quiz, with a way to the current one", () => {
    mocks.wpState.cachedResult = MOCK_RESULT;
    mocks.user = { wpl_completed: true };
    renderPage();

    expect(screen.getByText(/first version of Work Pulse, which has since been replaced/i))
      .toBeInTheDocument();
    expect(screen.getByRole("link", { name: /current work pulse/i })).toHaveAttribute(
      "href",
      "/work-pulse"
    );
  });

  it("renders from the cache without a request", () => {
    mocks.wpState.cachedResult = MOCK_RESULT;
    mocks.user = { wpl_completed: true };
    renderPage();

    expect(screen.getByText("Structured Deep Thinker")).toBeInTheDocument();
    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
  });

  it("never tells the user employers can see the narrative (F7)", () => {
    mocks.wpState.cachedResult = MOCK_RESULT;
    mocks.user = { wpl_completed: true };
    renderPage();

    expect(screen.queryByText(/window into how you actually work/i)).toBeNull();
    expect(screen.queryByText(/visible on your Solverah profile/i)).toBeNull();
    expect(screen.getByText(/Employers never see them/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /how this works/i })).toHaveAttribute("href", "/trust");
  });

  it("links to the live CompanyLens, with no fit score or number, and Pro stays a label", () => {
    mocks.wpState.cachedResult = MOCK_RESULT;
    mocks.user = { wpl_completed: true };
    renderPage();

    expect(screen.getByRole("link", { name: /open companylens/i })).toHaveAttribute(
      "href",
      "/company-lens"
    );
    expect(screen.queryByText(/fit score/i)).toBeNull();
    expect(screen.queryByText(/%/)).toBeNull();
    expect(screen.queryByText(/CompanyLens™ · Pro · coming soon/)).toBeNull();
    expect(screen.getByText("Work Pulse Pro · coming soon")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /unlock/i })).toBeNull();
  });

  // ── Nothing to show: off to the current instrument ─────────────────────────

  it("redirects to /work-pulse when the user never took the old quiz", () => {
    mocks.user = { wpl_completed: false };
    renderPage();

    expect(screen.getByTestId("redirect")).toHaveTextContent("/work-pulse");
    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
  });

  it("redirects to /work-pulse when no narrative was stored (404)", async () => {
    // Was a 422 "please resubmit" that re-enqueued the answers; with the scorer
    // retired the server answers 404 and there is nothing to resubmit to.
    mocks.user = { wpl_completed: true };
    mocks.fetchWithAuth.mockRejectedValueOnce(notFound());
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("redirect")).toHaveTextContent("/work-pulse")
    );
  });

  // ── The deleted write paths stay deleted ───────────────────────────────────

  it("never enqueues or resubmits anything, whatever is in session storage", async () => {
    // An old session may still hold the 12 answers under the legacy key.
    sessionStorage.setItem(
      "solverah_wp",
      JSON.stringify({ answers: [{ questionId: "wp-q1", optionId: "wp-q1-a" }] })
    );
    mocks.user = { wpl_completed: true };
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_RESULT);
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("Structured Deep Thinker")).toBeInTheDocument()
    );
    const posts = mocks.fetchWithAuth.mock.calls.filter(
      ([, init]) => (init as RequestInit | undefined)?.method === "POST"
    );
    expect(posts).toEqual([]);
    sessionStorage.clear();
  });

  it("shows a retryable error for a failure that is not a 404", async () => {
    mocks.user = { wpl_completed: true };
    mocks.fetchWithAuth
      .mockRejectedValueOnce(new Error("Network down"))
      .mockResolvedValueOnce(MOCK_RESULT);
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("We couldn't load your results right now.")).toBeInTheDocument()
    );
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    await waitFor(() =>
      expect(screen.getByText("Structured Deep Thinker")).toBeInTheDocument()
    );
    // The retry is a re-read, never a re-scoring.
    expect(mocks.fetchWithAuth).toHaveBeenCalledTimes(2);
  });
});
