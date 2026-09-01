import { render, screen, waitFor } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import ManagerMatchResultsPage from "./ManagerMatchResultsPage";
import type { MMResult } from "../useMM";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
  user: null as any,
  profile: {} as Record<string, unknown>,
  setCachedResult: vi.fn(),
  mmState: {
    cachedResult: null as MMResult | null,
  },
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => mocks.navigate,
}));

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({
    fetchWithAuth: mocks.fetchWithAuth,
    user: mocks.user,
  }),
}));

vi.mock("../useMM", () => ({
  useMM: () => ({
    state: mocks.mmState,
    setCachedResult: mocks.setCachedResult,
  }),
}));

// The stored result comes from the profile query rather than off `user`.
vi.mock("../../profile/useProfile", () => ({
  // The query hook, resolved. `isLoading: false` is the point: consumers
  // branch on it, and a mock that omitted it would report undefined --
  // falsy, so the branches would run, but by accident rather than intent.
  useProfile: () => ({ data: mocks.profile, isLoading: false }),
}));

const MOCK_RESULT: MMResult = {
  archetype: "The Autonomist",
  archetype_description: "You do your best work with clear goals and minimal oversight.",
  narrative: "You thrive when trusted to deliver.\n\nMicromanagement drains you fast.",
  dimension_scores: {
    autonomy: 0.8,
    feedback_style: 0.3,
    relationship: 0.55,
    growth_focus: 0.7,
  },
  what_to_look_for: ["Results-focused managers", "Async-friendly teams"],
  red_flags: ["Daily standups that feel like check-ins", "Approval chains for minor decisions"],
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.user = null;
  mocks.profile = {};
  mocks.mmState = { cachedResult: null };
});

// ── Cached result ─────────────────────────────────────────────────────────────

describe("ManagerMatchResultsPage - cached result", () => {
  beforeEach(() => {
    mocks.mmState = { cachedResult: MOCK_RESULT };
  });

  it("renders the archetype name", () => {
    render(<ManagerMatchResultsPage />);
    expect(screen.getByRole("heading", { name: "The Autonomist" })).toBeInTheDocument();
  });

  it("renders all four dimension rows with correct labels", () => {
    render(<ManagerMatchResultsPage />);
    expect(screen.getByText("Autonomy")).toBeInTheDocument();
    expect(screen.getByText("Feedback Style")).toBeInTheDocument();
    expect(screen.getByText("Relationship")).toBeInTheDocument();
    expect(screen.getByText("Growth Focus")).toBeInTheDocument();
  });

  it("renders correct band labels for dimension scores", () => {
    render(<ManagerMatchResultsPage />);
    // autonomy = 0.8 → High, feedback_style = 0.3 → Low, relationship = 0.55 → Mid, growth_focus = 0.7 → High
    expect(screen.getAllByText("High")).toHaveLength(2);
    expect(screen.getByText("Low")).toBeInTheDocument();
    expect(screen.getByText("Mid")).toBeInTheDocument();
  });

  it("renders all what_to_look_for items", () => {
    render(<ManagerMatchResultsPage />);
    expect(screen.getByText("Results-focused managers")).toBeInTheDocument();
    expect(screen.getByText("Async-friendly teams")).toBeInTheDocument();
  });

  it("renders all red_flags items", () => {
    render(<ManagerMatchResultsPage />);
    expect(screen.getByText("Daily standups that feel like check-ins")).toBeInTheDocument();
    expect(screen.getByText("Approval chains for minor decisions")).toBeInTheDocument();
  });

  it("back nav button navigates to /intelligence", () => {
    render(<ManagerMatchResultsPage />);
    const buttons = screen.getAllByRole("button", { name: /intelligence hub/i });
    fireEvent.click(buttons[0]);
    expect(mocks.navigate).toHaveBeenCalledWith("/intelligence");
  });

  it("CTA button navigates to /intelligence", () => {
    render(<ManagerMatchResultsPage />);
    fireEvent.click(screen.getByRole("button", { name: /Back to Intelligence Hub/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/intelligence");
  });

  it("does not call fetchWithAuth when cached result exists", () => {
    render(<ManagerMatchResultsPage />);
    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
  });
});

// ── Fetch on mount ────────────────────────────────────────────────────────────

describe("ManagerMatchResultsPage - fetch on mount", () => {
  it("calls fetchWithAuth for /manager-match/results when no cache exists", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_RESULT);
    render(<ManagerMatchResultsPage />);
    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith("/me/assessments/manager_match/result")
    );
  });

  it("renders results after successful fetch", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_RESULT);
    render(<ManagerMatchResultsPage />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "The Autonomist" })).toBeInTheDocument()
    );
  });

  it("uses the cached profile result when useMM has none", async () => {
    mocks.profile = { manager_match_result: MOCK_RESULT };
    render(<ManagerMatchResultsPage />);
    expect(screen.getByRole("heading", { name: "The Autonomist" })).toBeInTheDocument();
    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
  });
});

// ── Loading state ─────────────────────────────────────────────────────────────

describe("ManagerMatchResultsPage - loading state", () => {
  it("shows loading spinner while fetch is in progress", () => {
    mocks.fetchWithAuth.mockReturnValue(new Promise(() => {})); // never resolves
    render(<ManagerMatchResultsPage />);
    expect(screen.getByText("Loading your results…")).toBeInTheDocument();
  });
});

// ── Error state ───────────────────────────────────────────────────────────────

describe("ManagerMatchResultsPage - error state", () => {
  it("shows error card when fetch fails", async () => {
    mocks.fetchWithAuth.mockRejectedValueOnce(new Error("API error"));
    render(<ManagerMatchResultsPage />);
    await waitFor(() =>
      expect(screen.getByText("We couldn't load your results right now.")).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("retry button re-fetches and renders results on success", async () => {
    mocks.fetchWithAuth
      .mockRejectedValueOnce(new Error("fail"))
      .mockResolvedValueOnce(MOCK_RESULT);
    render(<ManagerMatchResultsPage />);
    await waitFor(() => screen.getByRole("button", { name: /try again/i }));
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "The Autonomist" })).toBeInTheDocument()
    );
  });
});
