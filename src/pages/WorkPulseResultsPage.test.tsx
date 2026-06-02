import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import WorkPulseResultsPage from "./WorkPulseResultsPage";
import { WP_QUESTIONS } from "../data/wpQuestions";
import type { WpApiResponse } from "../hooks/useWP";

// vi.hoisted ensures these are available inside the vi.mock factories,
// which run before module-level variable initialisations.
const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
  setCachedResult: vi.fn(),
  wpState: {
    answers: [] as { questionId: string; optionId: string }[],
    cachedResult: null as WpApiResponse | null,
  },
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => mocks.navigate,
}));

vi.mock("../contexts/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth }),
}));

vi.mock("../hooks/useWP", () => ({
  useWP: () => ({
    state: mocks.wpState,
    setCachedResult: mocks.setCachedResult,
  }),
}));

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
};

describe("WorkPulseResultsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: all 12 answers present (avoids navigation redirect), no cached result.
    mocks.wpState.answers = ALL_ANSWERS;
    mocks.wpState.cachedResult = null;
  });

  // ── Loading state ──────────────────────────────────────────────────────────

  it("shows loading state on mount before the fetch resolves", () => {
    mocks.fetchWithAuth.mockReturnValue(new Promise(() => {})); // never resolves
    render(<WorkPulseResultsPage />);
    expect(screen.getByText("Analysing your responses…")).toBeInTheDocument();
  });

  // ── Success state ──────────────────────────────────────────────────────────

  it("renders all three result sections when fetch succeeds", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_RESULT);
    render(<WorkPulseResultsPage />);

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

  it("calls setCachedResult with the API response on success", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_RESULT);
    render(<WorkPulseResultsPage />);
    await waitFor(() =>
      expect(mocks.setCachedResult).toHaveBeenCalledWith(MOCK_RESULT)
    );
  });

  it("renders from cached result immediately without calling fetchWithAuth", () => {
    mocks.wpState.cachedResult = MOCK_RESULT;
    render(<WorkPulseResultsPage />);

    expect(screen.getByText("Structured Deep Thinker")).toBeInTheDocument();
    expect(screen.getByText("You bring deep focus to your work.")).toBeInTheDocument();
    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
  });

  // ── Error state ────────────────────────────────────────────────────────────

  it("shows error state when fetchWithAuth rejects", async () => {
    mocks.fetchWithAuth.mockRejectedValueOnce(new Error("API error"));
    render(<WorkPulseResultsPage />);

    await waitFor(() =>
      expect(
        screen.getByText("We couldn't generate your results right now.")
      ).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("clicking Try again re-calls fetchWithAuth and shows results on second success", async () => {
    mocks.fetchWithAuth
      .mockRejectedValueOnce(new Error("first failure"))
      .mockResolvedValueOnce(MOCK_RESULT);

    render(<WorkPulseResultsPage />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument()
    );

    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    await waitFor(() =>
      expect(screen.getByText("Structured Deep Thinker")).toBeInTheDocument()
    );

    expect(mocks.fetchWithAuth).toHaveBeenCalledTimes(2);
  });

  // ── Navigation guard ───────────────────────────────────────────────────────

  it("redirects to /work-pulse when no answers are present", () => {
    mocks.wpState.answers = []; // fewer than 12 → guard fires
    mocks.fetchWithAuth.mockReturnValue(new Promise(() => {}));
    render(<WorkPulseResultsPage />);
    expect(mocks.navigate).toHaveBeenCalledWith("/work-pulse", { replace: true });
  });
});
