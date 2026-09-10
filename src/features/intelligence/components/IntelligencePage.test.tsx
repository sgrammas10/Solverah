import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import IntelligencePage from "./IntelligencePage";
import type { WpApiResponse } from "../../assessments";
import { ApiError } from "../../../shared/api/apiError";
import { createQueryClient } from "../../../shared/api/queryClient";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
  user: null as any,
  profile: {} as Record<string, unknown>,
  wpState: {
    answers: [] as any[],
    cachedResult: null as WpApiResponse | null,
  },
  setCachedResult: vi.fn(),
  mmCachedResult: null as any,
  formData: {} as any,
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({
    fetchWithAuth: mocks.fetchWithAuth,
    user: mocks.user,
  }),
}));

vi.mock("../../assessments/useWP", () => ({
  useWP: () => ({
    state: mocks.wpState,
    setCachedResult: mocks.setCachedResult,
  }),
}));

vi.mock("../../profile/useProfileForm", () => ({
  useProfileForm: () => ({ formData: mocks.formData }),
}));

// FocusType and ManagerMatch results come from the profile query now.
vi.mock("../../profile/useProfile", () => ({
  // The query hook, resolved. `isLoading: false` is the point: consumers
  // branch on it, and a mock that omitted it would report undefined --
  // falsy, so the branches would run, but by accident rather than intent.
  useProfile: () => ({ data: mocks.profile, isLoading: false }),
}));

vi.mock("../../assessments/useMM", () => ({
  useMM: () => ({ state: { cachedResult: mocks.mmCachedResult } }),
}));

vi.mock("./AssessmentsTab", () => ({
  default: () => <div data-testid="assessments-tab">Assessments</div>,
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.user = null;
  mocks.profile = {};
  mocks.wpState = { answers: [], cachedResult: null };
  mocks.mmCachedResult = null;
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

/** The useWorkPulseResult query needs a client; fresh per render, per the
 *  useProfileForm.test precedent, so no cache entry leaks between tests.
 *  The real retry policy stays on: failure fixtures below are 4xx ApiErrors,
 *  which shouldRetry refuses — a bare Error would be retried into the mock's
 *  next queued response and take the test somewhere unintended. */
function renderIntelligencePage() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <IntelligencePage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ─── not-completed state ───────────────────────────────────────────────────────

describe("IntelligencePage - not completed", () => {
  it("shows Complete Work Pulse prompt when the current instrument is unfinished", () => {
    mocks.user = { wpl_completed: false, wp_v2_completed: false };
    renderIntelligencePage();
    expect(screen.getByText(/Complete Work Pulse to unlock your profile/i)).toBeInTheDocument();
  });

  it("Start Work Pulse button navigates to /work-pulse", () => {
    mocks.user = { wpl_completed: false, wp_v2_completed: false };
    renderIntelligencePage();
    fireEvent.click(screen.getByRole("button", { name: /start work pulse/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/work-pulse");
  });

  /**
   * The CTA above must lead somewhere that can actually satisfy the gate.
   *
   * Until 2026-09-08 this page gated on `wpl_completed`, set only by the retired
   * 12-item instrument, while "Start Work Pulse" opened `/work-pulse` -- which
   * serves the 24-item `core` and sets `wp_v2_completed`. Finishing the CTA's own
   * destination therefore left the page locked, with no other route to the
   * instrument it wanted: a closed loop. Found by the real-stack E2E walkthrough,
   * where a freshly registered user completed the assessment and the hub stayed
   * locked.
   */
  it("unlocks after the instrument its own CTA starts", () => {
    mocks.user = { wpl_completed: false, wp_v2_completed: true };
    renderIntelligencePage();
    expect(screen.queryByText(/Complete Work Pulse to unlock your profile/i)).toBeNull();
    expect(screen.getByText(/Everything we know about how you work/i)).toBeInTheDocument();
  });
});

// ─── current instrument, no narrative ─────────────────────────────────────────

/**
 * `core` is rules-scored and produces no narrative by design. The unlocked view
 * used to `return null` when the narrative was absent, so simply moving the gate
 * to `wp_v2_completed` would have replaced a locked page with a BLANK one --
 * strictly worse. These cover the shape a current-instrument user actually gets.
 */
describe("IntelligencePage - completed without a narrative", () => {
  beforeEach(() => {
    mocks.user = { wpl_completed: false, wp_v2_completed: true };
    mocks.wpState = { answers: [], cachedResult: null };
  });

  it("renders the hub rather than a blank page", () => {
    renderIntelligencePage();
    expect(screen.getByText(/Everything we know about how you work/i)).toBeInTheDocument();
  });

  it("states Work Pulse is complete instead of showing an empty card", () => {
    renderIntelligencePage();
    expect(screen.getByText(/Work Pulse complete/i)).toBeInTheDocument();
    expect(screen.getByText(/powering your matching in the background/i)).toBeInTheDocument();
  });

  it("still offers the rest of the ecosystem", () => {
    // The point of unlocking: FocusType and ManagerMatch never needed the
    // narrative, and were unreachable only because of the gate.
    renderIntelligencePage();
    expect(screen.getByRole("button", { name: /start focustype/i })).toBeInTheDocument();
  });

  it("does not tell a user to complete the thing they just completed", () => {
    // The CompanyLens card carried the same legacy-flag gate, so it read
    // "Complete Work Pulse to unlock company matching" two cards below one
    // announcing Work Pulse was complete -- locking the company matching the
    // assessment exists to feed.
    renderIntelligencePage();
    expect(screen.queryByText(/Complete Work Pulse to unlock company matching/i)).toBeNull();
  });

  it("shows the coming-soon CompanyLens card instead of implying matches are ready", () => {
    // Until 2026-09-08 this card read "Your company matches are ready." with a
    // button to /company-lens, which 400s for every current-instrument user:
    // ⚑3 (BUILD_PLAN.md §0.2) shelved the culture-preferences mapping the
    // matches endpoint needs. The gate never meant anything -- CompanyLens is
    // coming-soon regardless of wp_v2_completed.
    renderIntelligencePage();
    expect(screen.getByText(/CompanyLens™/)).toBeInTheDocument();
    expect(screen.getByText(/Coming soon/i)).toBeInTheDocument();
    expect(screen.queryByText(/matches are ready/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /open companylens/i })).toBeNull();
  });

  it("links to the trust page from the hub footer", () => {
    // BUILD_PLAN D-3. The Work Pulse card above says there is no score to
    // check; this is the only place on the hub that explains why, so a footer
    // link going missing turns that card back into an unexplained absence.
    renderIntelligencePage();
    expect(
      screen.getByRole("link", { name: /how this works, and what we hold back/i }),
    ).toHaveAttribute("href", "/trust");
  });

  it("does not tick Work Pulse Lite for someone who never took it", () => {
    // The progress row hard-coded its first two steps as complete.
    renderIntelligencePage();
    const wplStep = screen.getByText("Work Pulse Lite").previousElementSibling;
    expect(wplStep?.textContent).not.toContain("✓");
  });
});

// ─── loading state ─────────────────────────────────────────────────────────────

describe("IntelligencePage - loading state", () => {
  it("shows loading spinner when a legacy narrative is still loading", () => {
    mocks.user = { wpl_completed: true, wp_v2_completed: true };
    mocks.wpState = { answers: [], cachedResult: null };
    mocks.fetchWithAuth.mockReturnValue(new Promise(() => {}));
    renderIntelligencePage();
    expect(screen.getByText(/Loading your profile/i)).toBeInTheDocument();
  });
});

// ─── error state ──────────────────────────────────────────────────────────────

describe("IntelligencePage - error state", () => {
  it("shows error UI when fetch fails", async () => {
    mocks.user = { wpl_completed: true, wp_v2_completed: true };
    mocks.wpState = { answers: [], cachedResult: null };
    // 400, not a bare Error: this test means "the request failed and stays
    // failed", and a 4xx is the class shouldRetry surfaces immediately.
    mocks.fetchWithAuth.mockRejectedValueOnce(new ApiError("API error", { status: 400 }));
    renderIntelligencePage();
    await waitFor(() =>
      expect(screen.getByText(/couldn't load your profile right now/i)).toBeInTheDocument()
    );
  });

  it("retry button re-fetches and shows results", async () => {
    mocks.user = { wpl_completed: true, wp_v2_completed: true };
    mocks.wpState = { answers: [], cachedResult: null };
    // The 400 must not be auto-retried, or the queued success would render
    // before the button was ever clicked and the test would assert nothing.
    mocks.fetchWithAuth
      .mockRejectedValueOnce(new ApiError("first failure", { status: 400 }))
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
    mocks.user = { wpl_completed: true, wp_v2_completed: true };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    expect(screen.getByText("Structured Builder")).toBeInTheDocument();
    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
  });

  it("renders emerging signal chips", () => {
    mocks.user = { wpl_completed: true, wp_v2_completed: true };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    expect(screen.getByText("Deep Thinker")).toBeInTheDocument();
  });

  it("renders the assessments tab", () => {
    mocks.user = { wpl_completed: true, wp_v2_completed: true };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    expect(screen.getByTestId("assessments-tab")).toBeInTheDocument();
  });

  it("view full analysis button navigates to /work-pulse/results", () => {
    mocks.user = { wpl_completed: true, wp_v2_completed: true };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    fireEvent.click(screen.getByText(/View full Work Pulse analysis/i));
    expect(mocks.navigate).toHaveBeenCalledWith("/work-pulse/results");
  });
});

// ─── FocusType card ────────────────────────────────────────────────────────────

describe("IntelligencePage - FocusType card", () => {
  it("shows Start FocusType button when FocusType not completed", () => {
    mocks.user = { wpl_completed: true, wp_v2_completed: true };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    expect(screen.getByRole("button", { name: /start focustype/i })).toBeInTheDocument();
  });

  it("shows FocusType results when user has completed it", () => {
    mocks.user = { wpl_completed: true, wp_v2_completed: true };
    mocks.profile = {
      focus_type_result: {
        archetype: "Sprint & Reset",
        dimension_scores: {},
        recommendations: [],
      },
    };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    expect(screen.getByText("Sprint & Reset")).toBeInTheDocument();
  });

  it("Start FocusType navigates to /focus-type", () => {
    mocks.user = { wpl_completed: true, wp_v2_completed: true };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    fireEvent.click(screen.getByRole("button", { name: /start focustype/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/focus-type");
  });

});

// ─── ManagerMatch card ─────────────────────────────────────────────────────────

describe("IntelligencePage - ManagerMatch card", () => {
  it("shows 'Start ManagerMatch™ →' button when manager_match_result is absent", () => {
    mocks.user = { wpl_completed: true, wp_v2_completed: true };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    expect(screen.getByRole("button", { name: /start managermatch/i })).toBeInTheDocument();
  });

  it("renders archetype name and 'View results →' when manager_match_result exists", () => {
    mocks.user = { wpl_completed: true, wp_v2_completed: true };
    mocks.profile = {
      manager_match_result: {
        archetype: "The Autonomist",
        archetype_description: "...",
        dimension_scores: {},
        narrative: "...",
        what_to_look_for: [],
        red_flags: [],
      },
    };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    expect(screen.getByText("The Autonomist")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /view results/i })).toBeInTheDocument();
  });

  it("ManagerMatch ecosystem step dot is complete when result exists", () => {
    mocks.user = { wpl_completed: true, wp_v2_completed: true };
    mocks.profile = {
      manager_match_result: {
        archetype: "The Autonomist",
        archetype_description: "...",
        dimension_scores: {},
        narrative: "...",
        what_to_look_for: [],
        red_flags: [],
      },
    };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    // Steps 0, 1 are always complete (i < 2); step 3 is complete when managerMatchResult exists.
    // With no focusTypeResult, we get 3 checkmarks total.
    expect(screen.getAllByText("✓")).toHaveLength(3);
  });

  it("ManagerMatch ecosystem step dot is incomplete when result is absent", () => {
    mocks.user = { wpl_completed: true, wp_v2_completed: true };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    // Only steps 0 and 1 are complete.
    expect(screen.getAllByText("✓")).toHaveLength(2);
  });

  it("shows completed state when result is in useMM cache (fresh submission path)", () => {
    mocks.user = { wpl_completed: true, wp_v2_completed: true };
    mocks.mmCachedResult = {
      archetype: "The Collaborator",
      archetype_description: "...",
      dimension_scores: {},
      narrative: "...",
      what_to_look_for: [],
      red_flags: [],
    };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
    renderIntelligencePage();
    expect(screen.getByText("The Collaborator")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /view results/i })).toBeInTheDocument();
  });
});
