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
  /** What `useManagerPlaybook` reports on the next render. Mocked directly
   *  (rather than left real, as `useWorkPulseResult` is) so this page's own
   *  `fetchWithAuth` fixtures for the Work Pulse query are not consumed by a
   *  second, unrelated query firing on the same mock. */
  playbookQuery: {
    data: undefined as any,
    isLoading: false,
    isError: false,
    error: null as unknown,
    refetch: vi.fn(),
  },
  /** What `useSituationReport` reports on the next render. Mocked directly for
   *  the same reason `playbookQuery` is: left real it fires a third query on
   *  the shared `fetchWithAuth` mock and eats the Work Pulse fixtures. */
  situationQuery: { data: undefined as any },
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

vi.mock("../../assessments/useManagerPlaybook", () => ({
  useManagerPlaybook: () => mocks.playbookQuery,
}));

vi.mock("../../assessments/useSituationReport", () => ({
  useSituationReport: () => mocks.situationQuery,
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
  // Default: a fresh user who has taken neither instrument yet -- the
  // realistic starting state, so tests unrelated to the Manager Decoder card
  // see its "take ManagerMatch first" variant rather than the generic
  // unexpected-failure one.
  mocks.playbookQuery = {
    data: undefined,
    isLoading: false,
    isError: true,
    error: new ApiError("Take ManagerMatch first", {
      status: 409,
      fieldErrors: [{ field: "manager_match", code: "no_manager_match" }],
    }),
    refetch: vi.fn(),
  };
  // Default: the report state is unresolved, so the Situation Report block is
  // silent. Tests that care set it explicitly.
  mocks.situationQuery = { data: undefined };
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

  // ── Situation Report block (BUILD_PLAN A-7) ──
  //
  // The Work Pulse completion card used to end at "nothing to check", which
  // made the hub a dead end for a user who had just finished the instrument.
  // It now carries the Situation Report path, and these are the three states
  // that block can be in.

  it("stays silent about the Situation Report while its state is unresolved", () => {
    mocks.situationQuery = { data: undefined };
    renderIntelligencePage();
    expect(screen.queryByText(/Situation Report/i)).toBeNull();
  });

  it("prompts for the environment report when the user has not filed one", () => {
    mocks.situationQuery = {
      data: {
        state: "needs_environment_report",
        manager: { has_profile: false },
        can_submit_environment_report: true,
      },
    };
    renderIntelligencePage();

    expect(screen.getByText(/about ten questions about the role/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Describe your job/ }));
    expect(mocks.navigate).toHaveBeenCalledWith("/environment-report");
  });

  it("offers no environment-report prompt to a user who cannot file one", () => {
    // `first_job`: the report page renders forward rather than prompting, so a
    // button here would be a call to action they cannot act on.
    mocks.situationQuery = {
      data: {
        state: "needs_environment_report",
        manager: { has_profile: false },
        can_submit_environment_report: false,
      },
    };
    renderIntelligencePage();
    expect(screen.queryByRole("button", { name: /Describe your job/ })).toBeNull();
  });

  it("links to the report once both halves exist", () => {
    mocks.situationQuery = {
      data: {
        state: "complete",
        manager: { has_profile: false },
        career_status: "employed",
        needs_forward: false,
        dimensions: [],
        guidance_notice: "notice",
      },
    };
    renderIntelligencePage();

    fireEvent.click(screen.getByRole("button", { name: /View your Situation Report/ }));
    expect(mocks.navigate).toHaveBeenCalledWith("/situation-report");
    expect(screen.queryByRole("button", { name: /Describe your job/ })).toBeNull();
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

// ─── Manager Decoder card ──────────────────────────────────────────────────────

describe("IntelligencePage - Manager Decoder card", () => {
  beforeEach(() => {
    mocks.user = { wpl_completed: true, wp_v2_completed: true };
    mocks.wpState = { answers: [], cachedResult: MOCK_WP_RESULT };
  });

  it("shows a loading placeholder while the playbook query is in flight", () => {
    mocks.playbookQuery = { ...mocks.playbookQuery, isLoading: true, isError: false, error: null };
    renderIntelligencePage();
    expect(screen.queryByText(/Manager Decoder/i)).toBeNull();
  });

  it("'take ManagerMatch first' state on the no_manager_match 409", () => {
    // beforeEach's default already fixtures this; asserted explicitly here.
    renderIntelligencePage();
    expect(
      screen.getByText(/Take ManagerMatch first — the Decoder diffs your manager profile/i)
    ).toBeInTheDocument();
  });

  it("'take ManagerMatch first' CTA navigates to /manager-match", () => {
    renderIntelligencePage();
    fireEvent.click(screen.getByRole("button", { name: /Take ManagerMatch™/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/manager-match");
  });

  it("'start' state on the no_manager_profile 409", () => {
    mocks.playbookQuery = {
      ...mocks.playbookQuery,
      isError: true,
      error: new ApiError("Profile your manager first", {
        status: 409,
        fieldErrors: [{ field: "manager_profile", code: "no_manager_profile" }],
      }),
    };
    renderIntelligencePage();
    expect(
      screen.getByText(/Profile how your manager actually works/i)
    ).toBeInTheDocument();
  });

  it("'start' CTA navigates to /manager-profile", () => {
    mocks.playbookQuery = {
      ...mocks.playbookQuery,
      isError: true,
      error: new ApiError("Profile your manager first", {
        status: 409,
        fieldErrors: [{ field: "manager_profile", code: "no_manager_profile" }],
      }),
    };
    renderIntelligencePage();
    fireEvent.click(screen.getByRole("button", { name: /Profile your manager/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/manager-profile");
  });

  it("'view playbook' state when the playbook is ready", () => {
    mocks.playbookQuery = {
      ...mocks.playbookQuery,
      isError: false,
      error: null,
      data: {
        dimension_scores: {},
        scoring_key: "mp-v1",
        version: "v1",
        playbook: { privacy_notice: "...", dimensions: [], priority: ["autonomy"], grind_count: 1, mesh_count: 3 },
      },
    };
    renderIntelligencePage();
    expect(screen.getByText(/1 dimension to work on/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /view your playbook/i })).toBeInTheDocument();
  });

  it("'view playbook' CTA navigates to /manager-profile/playbook", () => {
    mocks.playbookQuery = {
      ...mocks.playbookQuery,
      isError: false,
      error: null,
      data: {
        dimension_scores: {},
        scoring_key: "mp-v1",
        version: "v1",
        playbook: { privacy_notice: "...", dimensions: [], priority: [], grind_count: 0, mesh_count: 4 },
      },
    };
    renderIntelligencePage();
    fireEvent.click(screen.getByRole("button", { name: /view your playbook/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/manager-profile/playbook");
  });

  it("shows a distinct card for an unexpected (non-409) failure", () => {
    mocks.playbookQuery = {
      ...mocks.playbookQuery,
      isError: true,
      error: new ApiError("Server error", { status: 500 }),
    };
    renderIntelligencePage();
    expect(screen.getByText(/couldn't check your Manager Decoder status/i)).toBeInTheDocument();
    expect(screen.queryByText(/Take ManagerMatch first/i)).toBeNull();
  });
});
