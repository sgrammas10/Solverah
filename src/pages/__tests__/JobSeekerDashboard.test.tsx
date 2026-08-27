import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import JobSeekerDashboard from "../JobSeekerDashboard";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  user: null as any,
  fetchWithAuth: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../contexts/useAuth", () => ({
  useAuth: () => ({ user: mocks.user, fetchWithAuth: mocks.fetchWithAuth }),
}));

vi.mock("../../components/IntakePromptModal", () => ({
  default: ({ open, onClose }: any) =>
    open ? (
      <div data-testid="intake-modal">
        <button onClick={onClose}>Close Modal</button>
      </div>
    ) : null,
}));

vi.mock("../../components/dashboard/WorkPulseBanner", () => ({
  default: ({ onDismiss, retake }: any) => (
    <div data-testid="wp-banner" data-retake={String(Boolean(retake))}>
      <button onClick={onDismiss}>Dismiss Banner</button>
    </div>
  ),
}));

vi.mock("../../components/profile/WorkPulseUnlock", () => ({
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
  mocks.fetchWithAuth.mockResolvedValue({
    profileCompletion: "60%",
    jobMatches: "12",
    applications: "3",
    hasIntakeSubmission: false,
    recentActivity: [],
    recommendations: [],
  });
});

function renderJobSeekerDashboard() {
  render(
    <MemoryRouter>
      <JobSeekerDashboard />
    </MemoryRouter>
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
  it("Take Assessment button navigates to /intelligence", async () => {
    renderJobSeekerDashboard();
    fireEvent.click(screen.getByText("Take Assessment"));
    expect(mocks.navigate).toHaveBeenCalledWith("/intelligence");
  });
});

// ─── intake modal ─────────────────────────────────────────────────────────────

describe("JobSeekerDashboard - intake modal", () => {
  it("shows intake modal when profile completion is below 50%", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce({
      profileCompletion: "30%",
      jobMatches: "0",
      applications: "0",
      hasIntakeSubmission: false,
      recentActivity: [],
      recommendations: [],
    });
    renderJobSeekerDashboard();
    await waitFor(() => expect(screen.getByTestId("intake-modal")).toBeInTheDocument());
  });
});
