import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import IntelligencePage from "../IntelligencePage";
import type { WpApiResponse } from "../../hooks/useWP";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
  user: null as any,
  wpState: {
    answers: [] as any[],
    cachedResult: null as WpApiResponse | null,
  },
  setCachedResult: vi.fn(),
  formData: {} as any,
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../contexts/useAuth", () => ({
  useAuth: () => ({
    fetchWithAuth: mocks.fetchWithAuth,
    user: mocks.user,
  }),
}));

vi.mock("../../hooks/useWP", () => ({
  useWP: () => ({
    state: mocks.wpState,
    setCachedResult: mocks.setCachedResult,
  }),
}));

vi.mock("../../hooks/useProfileForm", () => ({
  useProfileForm: () => ({ formData: mocks.formData }),
}));

vi.mock("../../components/profile/AssessmentsTab", () => ({
  default: () => <div data-testid="assessments-tab">Assessments</div>,
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.user = null;
  mocks.wpState = { answers: [], cachedResult: null };
  mocks.formData = {};
});

const MOCK_WP_RESULT: WpApiResponse = {
  narrative: "You thrive in structured environments.",
  emerging_signals: [
    { title: "Deep Thinker", description: "You prefer analysis over speed." },
  ],
  archetype: "Structured Builder",
  archetype_description: "You plan before you act.",
};

function renderIntelligencePage() {
  render(
    <MemoryRouter>
      <IntelligencePage />
    </MemoryRouter>
  );
}

// ─── not-completed state ───────────────────────────────────────────────────────

describe("IntelligencePage - not completed", () => {
  it("shows Complete Work Pulse prompt when wpl_completed is false", () => {
    mocks.user = { wpl_completed: false, profileData: null };
    renderIntelligencePage();
    expect(screen.getByText(/Complete Work Pulse to unlock your profile/i)).toBeInTheDocument();
  });

  it("Start Work Pulse button navigates to /work-pulse", () => {
    mocks.user = { wpl_completed: false, profileData: null };
    renderIntelligencePage();
    fireEvent.click(screen.getByRole("button", { name: /start work pulse/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/work-pulse");
  });
});

// ─── loading state ─────────────────────────────────────────────────────────────

describe("IntelligencePage - loading state", () => {
  it("shows loading spinner when wpl_completed but no cached result", () => {
    mocks.user = { wpl_completed: true, profileData: null };
    mocks.wpState = { answers: [], cachedResult: null };
    mocks.fetchWithAuth.mockReturnValue(new Promise(() => {}));
    renderIntelligencePage();
    expect(screen.getByText(/Loading your profile/i)).toBeInTheDocument();
  });
});

// ─── error state ──────────────────────────────────────────────────────────────

describe("IntelligencePage - error state", () => {
  it("shows error UI when fetch fails", async () => {
    mocks.user = { wpl_completed: true, profileData: null };
    mocks.wpState = { answers: [], cachedResult: null };
    mocks.fetchWithAuth.mockRejectedValueOnce(new Error("API error"));
    renderIntelligencePage();
    await waitFor(() =>
      expect(screen.getByText(/couldn't load your profile right now/i)).toBeInTheDocument()
    );
  });

  it("retry button re-fetches and shows results", async () => {
    mocks.user = { wpl_completed: true, profileData: null };
    mocks.wpState = { answers: [], cachedResult: null };
    mocks.fetchWithAuth
      .mockRejectedValueOnce(new Error("first failure"))
      .mockResolvedValueOnce(MOCK_WP_RESULT);
    renderIntelligencePage();
    await waitFor(() => screen.getByRole("button", { name: /try again/i }));
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() => expect(screen.getByText("Structured Builder")).toBeInTheDocument());
  });
});

// ─── happy path (cached result) ────────────────────────────────────────────────

describe("IntelligencePage - happy path with cached result", () => {
  it("renders archetype from cached result without fetching", () => {
    mocks.user = { wpl_completed: true, profileData: null };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    expect(screen.getByText("Structured Builder")).toBeInTheDocument();
    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
  });

  it("renders emerging signal chips", () => {
    mocks.user = { wpl_completed: true, profileData: null };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    expect(screen.getByText("Deep Thinker")).toBeInTheDocument();
  });

  it("renders the assessments tab", () => {
    mocks.user = { wpl_completed: true, profileData: null };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    expect(screen.getByTestId("assessments-tab")).toBeInTheDocument();
  });

  it("view full analysis button navigates to /work-pulse/results", () => {
    mocks.user = { wpl_completed: true, profileData: null };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    fireEvent.click(screen.getByText(/View full Work Pulse analysis/i));
    expect(mocks.navigate).toHaveBeenCalledWith("/work-pulse/results");
  });
});

// ─── FocusType card ────────────────────────────────────────────────────────────

describe("IntelligencePage - FocusType card", () => {
  it("shows Start FocusType button when FocusType not completed", () => {
    mocks.user = { wpl_completed: true, profileData: null };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    expect(screen.getByRole("button", { name: /start focustype/i })).toBeInTheDocument();
  });

  it("shows FocusType results when user has completed it", () => {
    mocks.user = {
      wpl_completed: true,
      profileData: {
        focus_type_result: {
          archetype: "Sprint & Reset",
          dimension_scores: {},
          recommendations: [],
        },
      },
    };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    expect(screen.getByText("Sprint & Reset")).toBeInTheDocument();
  });

  it("Start FocusType navigates to /focus-type", () => {
    mocks.user = { wpl_completed: true, profileData: null };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    fireEvent.click(screen.getByRole("button", { name: /start focustype/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/focus-type");
  });

  it("CompanyLens button navigates to /company-lens", () => {
    mocks.user = { wpl_completed: true, profileData: null };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    fireEvent.click(screen.getByRole("button", { name: /open companylens/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/company-lens");
  });
});
