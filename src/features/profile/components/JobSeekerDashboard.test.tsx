import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import JobSeekerDashboard from "./JobSeekerDashboard";
import { createQueryClient } from "../../../shared/api/queryClient";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  user: null as any,
  fetchWithAuth: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ user: mocks.user, fetchWithAuth: mocks.fetchWithAuth }),
}));

vi.mock("../../intake/components/IntakePromptModal", () => ({
  default: ({ open, onClose }: any) =>
    open ? (
      <div data-testid="intake-modal">
        <button onClick={onClose}>Close Modal</button>
      </div>
    ) : null,
}));

vi.mock("../../assessments/components/WorkPulseBanner", () => ({
  default: ({ onDismiss, retake }: any) => (
    <div data-testid="wp-banner" data-retake={String(Boolean(retake))}>
      <button onClick={onDismiss}>Dismiss Banner</button>
    </div>
  ),
}));

vi.mock("../../assessments/components/WorkPulseUnlock", () => ({
  default: () => <div data-testid="wp-unlock">WorkPulse Unlocked</div>,
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.user = {
    name: "Ada Lovelace",
    profileComplete: true,
    wpl_completed: false,
    wp_v2_completed: false,
  };
  // Routed by path, not a blanket resolved value: the dashboard now mounts
  // PulseDashboardCard (BUILD_PLAN B-3) beside its own /me/dashboard query,
  // and a call-order-blind mock would hand that card's /me/pulse/history
  // request the dashboard fixture (or vice versa) depending on which query
  // happens to fire first.
  mocks.fetchWithAuth.mockImplementation((path: string) => {
    if (path.startsWith("/me/pulse/")) {
      return Promise.resolve({ checkins: [], events: [] });
    }
    return Promise.resolve({
      profileCompletion: "60%",
      jobMatches: "12",
      applications: "3",
      hasIntakeSubmission: false,
      recentActivity: [],
      recommendations: [],
    });
  });
});

/** The dashboard query needs a client; fresh per render, per the
 *  useProfileForm.test precedent, so no cache entry leaks between tests. */
function renderJobSeekerDashboard() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <JobSeekerDashboard />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ─── happy path ────────────────────────────────────────────────────────────────

describe("JobSeekerDashboard - happy path", () => {
  it("shows welcome message with user name", async () => {
    renderJobSeekerDashboard();
    expect(screen.getByText(/Welcome back, Ada Lovelace/i)).toBeInTheDocument();
  });

  it("renders stats cards after data loads", async () => {
    renderJobSeekerDashboard();
    await waitFor(() => expect(screen.getByText("60%")).toBeInTheDocument());
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("fetches /dashboard-data on mount", async () => {
    renderJobSeekerDashboard();
    await waitFor(() => expect(mocks.fetchWithAuth).toHaveBeenCalledWith("/me/dashboard"));
  });
});

// ─── profile completion alert ─────────────────────────────────────────────────

describe("JobSeekerDashboard - profile completion alert", () => {
  it("shows profile completion alert when profile is not complete", async () => {
    mocks.user = { name: "Ada", profileComplete: false, wpl_completed: false, wp_v2_completed: false };
    renderJobSeekerDashboard();
    await waitFor(() =>
      expect(screen.getByText(/Complete your profile/i)).toBeInTheDocument()
    );
  });

  it("does not show profile completion alert when profile is complete", async () => {
    mocks.user = { name: "Ada", profileComplete: true, wpl_completed: false, wp_v2_completed: false };
    renderJobSeekerDashboard();
    await waitFor(() => screen.getByText("60%"));
    expect(screen.queryByText(/Complete your profile/i)).toBeNull();
  });
});

// ─── work pulse banner ────────────────────────────────────────────────────────

describe("JobSeekerDashboard - work pulse banner", () => {
  it("shows the banner when the current instrument is not completed", async () => {
    mocks.user = { name: "Ada", profileComplete: true, wpl_completed: false, wp_v2_completed: false };
    renderJobSeekerDashboard();
    await waitFor(() => expect(screen.getByTestId("wp-banner")).toBeInTheDocument());
    expect(screen.getByTestId("wp-banner")).toHaveAttribute("data-retake", "false");
  });

  it("banner can be dismissed", async () => {
    mocks.user = { name: "Ada", profileComplete: true, wpl_completed: false, wp_v2_completed: false };
    renderJobSeekerDashboard();
    await waitFor(() => screen.getByTestId("wp-banner"));
    fireEvent.click(screen.getByText("Dismiss Banner"));
    expect(screen.queryByTestId("wp-banner")).toBeNull();
  });

  it("RE-PROMPTS a user who only completed the ORIGINAL Work Pulse (retake copy)", async () => {
    // The 12-question quiz was replaced 2026-08-19; old sittings don't feed the matching
    // model, so wpl_completed alone must NOT hide the banner. Decided with Sebastian.
    mocks.user = { name: "Ada", profileComplete: true, wpl_completed: true, wp_v2_completed: false };
    renderJobSeekerDashboard();
    await waitFor(() => expect(screen.getByTestId("wp-banner")).toBeInTheDocument());
    expect(screen.getByTestId("wp-banner")).toHaveAttribute("data-retake", "true");
    expect(screen.queryByTestId("wp-unlock")).toBeNull();
  });

  it("shows the completion card when the current instrument is completed", async () => {
    mocks.user = { name: "Ada", profileComplete: true, wpl_completed: false, wp_v2_completed: true };
    renderJobSeekerDashboard();
    await waitFor(() => expect(screen.getByTestId("wp-unlock")).toBeInTheDocument());
    expect(screen.queryByTestId("wp-banner")).toBeNull();
  });
});

// ─── jobs popup ───────────────────────────────────────────────────────────────

describe("JobSeekerDashboard - jobs popup modal", () => {
  it("shows jobs coming-soon dialog when Browse Jobs is clicked", async () => {
    renderJobSeekerDashboard();
    fireEvent.click(screen.getByText("Browse Jobs"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/Feature coming soon/i)).toBeInTheDocument();
  });

  it("closes the dialog when Got it is clicked", async () => {
    renderJobSeekerDashboard();
    fireEvent.click(screen.getByText("Browse Jobs"));
    fireEvent.click(screen.getByRole("button", { name: /got it/i }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

// ─── quick actions ─────────────────────────────────────────────────────────────

describe("JobSeekerDashboard - quick actions", () => {
  // Renamed 2026-09-08 from "Take Assessment / Complete psychometric test".
  // That label sat directly under a banner calling the same 24 questions "Work
  // Pulse", so one screen appeared to offer two different things. The
  // destination is unchanged and is still what this test protects.
  it("the profile quick action navigates to /intelligence", async () => {
    renderJobSeekerDashboard();
    fireEvent.click(screen.getByText("Your Solverah profile"));
    expect(mocks.navigate).toHaveBeenCalledWith("/intelligence");
  });

  it("does not offer two differently-named routes to the same assessment", async () => {
    renderJobSeekerDashboard();
    // The old copy. Its return would mean the naming collision is back.
    expect(screen.queryByText("Take Assessment")).toBeNull();
    expect(screen.queryByText("Complete psychometric test")).toBeNull();
  });
});

// ─── empty states ─────────────────────────────────────────────────────────────

/**
 * Regression tests for the blank cards found by the real-stack E2E walkthrough
 * on 2026-09-08.
 *
 * Both cards mapped over an array with no empty branch, so a new account -- for
 * whom both arrays are always empty -- got a heading over nothing on the first
 * screen after sign-up. It read as broken rather than new. Note the default mock
 * in `beforeEach` already returns empty arrays, which is why this went unnoticed:
 * every existing test in this file rendered the broken state and asserted
 * nothing about it.
 */
describe("JobSeekerDashboard - empty states", () => {
  it("tells a new user why Recent Activity is empty", async () => {
    renderJobSeekerDashboard();
    expect(await screen.findByText("Nothing here yet.")).toBeInTheDocument();
    expect(
      screen.getByText(/activity shows up here as you complete Work Pulse/i),
    ).toBeInTheDocument();
  });

  it("tells a new user why Recommendations is empty", async () => {
    renderJobSeekerDashboard();
    expect(await screen.findByText("No recommendations yet.")).toBeInTheDocument();
    expect(screen.getByText(/finish Work Pulse/i)).toBeInTheDocument();
  });

  it("shows the real content instead once there is any", async () => {
    // The other half of the branch: a conditional that renders the empty state
    // unconditionally would pass both tests above and break the product.
    mocks.fetchWithAuth.mockResolvedValue({
      profileCompletion: "60%",
      jobMatches: "12",
      applications: "3",
      hasIntakeSubmission: false,
      recentActivity: [{ icon: "User", text: "You updated your profile", time: "2h ago" }],
      recommendations: [{ title: "Add your resume", href: "#resume", priority: "urgent" }],
    });

    renderJobSeekerDashboard();

    expect(await screen.findByText("You updated your profile")).toBeInTheDocument();
    expect(screen.getByText("Add your resume")).toBeInTheDocument();
    expect(screen.queryByText("Nothing here yet.")).toBeNull();
    expect(screen.queryByText("No recommendations yet.")).toBeNull();
  });
});

// ─── intake modal ─────────────────────────────────────────────────────────────

describe("JobSeekerDashboard - intake modal", () => {
  it("shows intake modal when profile completion is below 50%", async () => {
    mocks.fetchWithAuth.mockImplementation((path: string) => {
      if (path.startsWith("/me/pulse/")) {
        return Promise.resolve({ checkins: [], events: [] });
      }
      return Promise.resolve({
        profileCompletion: "30%",
        jobMatches: "0",
        applications: "0",
        hasIntakeSubmission: false,
        recentActivity: [],
        recommendations: [],
      });
    });
    renderJobSeekerDashboard();
    await waitFor(() => expect(screen.getByTestId("intake-modal")).toBeInTheDocument());
  });
});
