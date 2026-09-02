/**
 * ManagerMatchResultsPage.test.tsx — the three tiers, each asserted.
 *
 *   1. Fresh: the result already in `managerMatchResultKeys.result()` (put
 *      there by ManagerMatchPage after a scoring job) renders with no request.
 *   2. Stored: `profile.manager_match_result` renders with no ManagerMatch
 *      request.
 *   3. Fetched: with neither, `GET /me/assessments/manager_match/result` is
 *      issued through `useManagerMatchResult`.
 *
 * Failure paths use 4xx `ApiError`s on purpose: the query adopts the shared
 * bounded-retry default (safe — Phase 3a removed commits from GET handlers),
 * so a test that means "the fetch fails" must throw something `shouldRetry`
 * refuses to retry, or it would sit through two real backoffs first.
 */
import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import ManagerMatchResultsPage from "./ManagerMatchResultsPage";
import { managerMatchResultKeys } from "../useManagerMatchResult";
import { createQueryClient } from "../../../shared/api/queryClient";
import { ApiError } from "../../../shared/api/apiError";
import type { MMResult } from "../useMM";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
  profile: {} as Record<string, unknown>,
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => mocks.navigate,
}));

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({
    fetchWithAuth: mocks.fetchWithAuth,
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

/** Fresh client per render — the established idiom; no cache crosses a test. */
let queryClient: QueryClient;

function renderPage({ freshResult }: { freshResult?: MMResult } = {}) {
  queryClient = createQueryClient();
  if (freshResult) {
    // Tier 1's precondition: exactly what ManagerMatchPage does (through
    // useMM's setCachedResult) when a scoring job succeeds.
    queryClient.setQueryData(managerMatchResultKeys.result(), freshResult);
  }
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  render(<ManagerMatchResultsPage />, { wrapper });
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.profile = {};
});

// ── Tier 1: fresh result in the shared query cache ───────────────────────────

describe("ManagerMatchResultsPage - fresh result (tier 1)", () => {
  it("renders the archetype name", () => {
    renderPage({ freshResult: MOCK_RESULT });
    expect(screen.getByRole("heading", { name: "The Autonomist" })).toBeInTheDocument();
  });

  it("renders all four dimension rows with correct labels", () => {
    renderPage({ freshResult: MOCK_RESULT });
    expect(screen.getByText("Autonomy")).toBeInTheDocument();
    expect(screen.getByText("Feedback Style")).toBeInTheDocument();
    expect(screen.getByText("Relationship")).toBeInTheDocument();
    expect(screen.getByText("Growth Focus")).toBeInTheDocument();
  });

  it("renders correct band labels for dimension scores", () => {
    renderPage({ freshResult: MOCK_RESULT });
    // autonomy = 0.8 → High, feedback_style = 0.3 → Low, relationship = 0.55 → Mid, growth_focus = 0.7 → High
    expect(screen.getAllByText("High")).toHaveLength(2);
    expect(screen.getByText("Low")).toBeInTheDocument();
    expect(screen.getByText("Mid")).toBeInTheDocument();
  });

  it("renders all what_to_look_for items", () => {
    renderPage({ freshResult: MOCK_RESULT });
    expect(screen.getByText("Results-focused managers")).toBeInTheDocument();
    expect(screen.getByText("Async-friendly teams")).toBeInTheDocument();
  });

  it("renders all red_flags items", () => {
    renderPage({ freshResult: MOCK_RESULT });
    expect(screen.getByText("Daily standups that feel like check-ins")).toBeInTheDocument();
    expect(screen.getByText("Approval chains for minor decisions")).toBeInTheDocument();
  });

  it("back nav button navigates to /intelligence", () => {
    renderPage({ freshResult: MOCK_RESULT });
    const buttons = screen.getAllByRole("button", { name: /intelligence hub/i });
    fireEvent.click(buttons[0]);
    expect(mocks.navigate).toHaveBeenCalledWith("/intelligence");
  });

  it("CTA button navigates to /intelligence", () => {
    renderPage({ freshResult: MOCK_RESULT });
    fireEvent.click(screen.getByRole("button", { name: /Back to Intelligence Hub/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/intelligence");
  });

  it("issues no request when the fresh result is in cache", () => {
    renderPage({ freshResult: MOCK_RESULT });
    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
  });

  it("prefers the fresh result over a stored profile copy", () => {
    // A retake's fresh result must beat the pre-retake copy still sitting on
    // the (not-yet-refetched) profile document.
    mocks.profile = {
      manager_match_result: { ...MOCK_RESULT, archetype: "The Pre-Retake Relic" },
    };
    renderPage({ freshResult: MOCK_RESULT });
    expect(screen.getByRole("heading", { name: "The Autonomist" })).toBeInTheDocument();
    expect(screen.queryByText("The Pre-Retake Relic")).toBeNull();
    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
  });
});

// ── Tier 2: stored on the profile document ───────────────────────────────────

describe("ManagerMatchResultsPage - stored profile result (tier 2)", () => {
  it("renders from the profile document without any ManagerMatch request", () => {
    mocks.profile = { manager_match_result: MOCK_RESULT };
    renderPage();
    expect(screen.getByRole("heading", { name: "The Autonomist" })).toBeInTheDocument();
    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
  });
});

// ── Tier 3: fetched from the server ──────────────────────────────────────────

describe("ManagerMatchResultsPage - server fetch (tier 3)", () => {
  it("fetches the stored result when neither cache nor profile has one", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_RESULT);
    renderPage();
    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/me/assessments/manager_match/result",
        { method: "GET" }
      )
    );
  });

  it("renders results after successful fetch", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(MOCK_RESULT);
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "The Autonomist" })).toBeInTheDocument()
    );
  });

  it("redirects to the instrument when the server has no result", async () => {
    // The 404's message is the routing signal, as it was for the hand-rolled
    // fetch; 4xx means no retry delay before the redirect.
    mocks.fetchWithAuth.mockRejectedValueOnce(
      new ApiError("No ManagerMatch result found", { status: 404 })
    );
    renderPage();
    await waitFor(() =>
      expect(mocks.navigate).toHaveBeenCalledWith("/manager-match", { replace: true })
    );
  });
});

// ── Loading state ─────────────────────────────────────────────────────────────

describe("ManagerMatchResultsPage - loading state", () => {
  it("shows loading spinner while fetch is in progress", () => {
    mocks.fetchWithAuth.mockReturnValue(new Promise(() => {})); // never resolves
    renderPage();
    expect(screen.getByText("Loading your results…")).toBeInTheDocument();
  });
});

// ── Error state ───────────────────────────────────────────────────────────────

describe("ManagerMatchResultsPage - error state", () => {
  it("shows error card when fetch fails", async () => {
    // 403: a non-retryable failure that is not the not-found redirect.
    mocks.fetchWithAuth.mockRejectedValueOnce(new ApiError("API error", { status: 403 }));
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("We couldn't load your results right now.")).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    expect(mocks.navigate).not.toHaveBeenCalled();
  });

  it("retry button re-fetches and renders results on success", async () => {
    mocks.fetchWithAuth
      .mockRejectedValueOnce(new ApiError("fail", { status: 403 }))
      .mockResolvedValueOnce(MOCK_RESULT);
    renderPage();
    await waitFor(() => screen.getByRole("button", { name: /try again/i }));
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "The Autonomist" })).toBeInTheDocument()
    );
  });
});
