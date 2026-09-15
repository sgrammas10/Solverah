import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import JobSeekerDashboard from "./JobSeekerDashboard";
import { createQueryClient } from "../../../shared/api/queryClient";
import { ApiError } from "../../../shared/api/apiError";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  user: null as any,
  fetchWithAuth: vi.fn(),
  /** The Situation Report state under test; D-6 drives the lead card off it. */
  situationReport: null as any,
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

/**
 * `/me/dashboard` still answers with the whole document — D-6 stopped RENDERING
 * the Job Matches / Applications tiles, it did not change the endpoint, and the
 * assertions below prove those two values reach the page and are not drawn.
 */
const DASHBOARD_DOC = {
  profileCompletion: "60%",
  jobMatches: "12",
  applications: "3",
  hasIntakeSubmission: false,
  recentActivity: [],
  recommendations: [],
};

const NEEDS_CORE = {
  state: "needs_core",
  manager: { has_profile: false },
  environment: null,
};

const NEEDS_ENV = {
  state: "needs_environment_report",
  manager: { has_profile: false },
  can_submit_environment_report: true,
};

const FIRST_JOB = { ...NEEDS_ENV, can_submit_environment_report: false };

const COMPLETE = {
  state: "complete",
  manager: { has_profile: false },
  career_status: "employed",
  needs_forward: false,
  guidance_notice: "Notice",
  dimensions: [
    {
      dimension: "autonomy",
      env_score: 0.17,
      bucket: "straining",
      direction: "under",
      rank: 1,
      diagnosis: { headline: "Headline", text: "Text" },
      registers: {},
      defers_to_decoder: false,
      decoder_crossref: null,
    },
  ],
};

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
  mocks.situationReport = NEEDS_CORE;
  mocks.fetchWithAuth.mockImplementation((path: string) => {
    if (path.startsWith("/me/pulse/")) {
      return Promise.resolve({ checkins: [], events: [] });
    }
    if (path.startsWith("/me/situation-report")) {
      return Promise.resolve(mocks.situationReport);
    }
    return Promise.resolve(DASHBOARD_DOC);
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

  it("frames the page around working life, not a job search (D-6)", async () => {
    renderJobSeekerDashboard();
    expect(
      screen.getByText(/Here's where your working life stands/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/job search overview/i)).toBeNull();
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
    // Waited on the fetch rather than on a rendered "60%": D-6 removed the
    // Profile Completion tile that used to be this test's settle signal.
    await waitFor(() => expect(mocks.fetchWithAuth).toHaveBeenCalledWith("/me/dashboard"));
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

/**
 * D-6: the job-board furniture is gone. These are the tests that would fail if
 * any of it came back — the whole point of the chunk is that this screen stops
 * being a job board without jobs (PRODUCT_DECISIONS §1).
 */
describe("JobSeekerDashboard - the job board is gone (D-6)", () => {
  it("offers no Browse Jobs action and no coming-soon modal", async () => {
    renderJobSeekerDashboard();
    await waitFor(() => expect(mocks.fetchWithAuth).toHaveBeenCalledWith("/me/dashboard"));
    expect(screen.queryByText("Browse Jobs")).toBeNull();
    expect(screen.queryByText(/Find matching opportunities/i)).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByText(/Feature coming soon/i)).toBeNull();
  });

  it("does not draw the Job Matches / Applications tiles, though the document still carries them", async () => {
    renderJobSeekerDashboard();
    await waitFor(() => expect(mocks.fetchWithAuth).toHaveBeenCalledWith("/me/dashboard"));
    expect(screen.queryByText("Job Matches")).toBeNull();
    expect(screen.queryByText("Applications")).toBeNull();
    expect(screen.queryByText("Profile Completion")).toBeNull();
    // The values themselves, not just the labels: a tile rendered without its
    // label would still be a count of matches on a screen that has none.
    expect(screen.queryByText("12")).toBeNull();
    expect(screen.queryByText("3")).toBeNull();
    expect(screen.queryByText("60%")).toBeNull();
  });

  it("keeps matching reachable as a plain link, with no matching framing", async () => {
    renderJobSeekerDashboard();
    const search = screen.getByRole("link", { name: /Search companies and roles/i });
    expect(search).toHaveAttribute("href", "/search");
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
    // Routed by path, not a blanket resolved value -- the dashboard now mounts
    // two sibling cards with their own queries (B-3's pulse card and D-6's
    // situation card), and a call-order-blind mock would hand one of them this
    // fixture.
    mocks.fetchWithAuth.mockImplementation((path: string) => {
      if (path.startsWith("/me/pulse/")) return Promise.resolve({ checkins: [], events: [] });
      if (path.startsWith("/me/situation-report")) return Promise.resolve(mocks.situationReport);
      return Promise.resolve({
        ...DASHBOARD_DOC,
        recentActivity: [{ icon: "User", text: "You updated your profile", time: "2h ago" }],
        recommendations: [{ title: "Add your resume", href: "#resume", priority: "urgent" }],
      });
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
      if (path.startsWith("/me/situation-report")) {
        return Promise.resolve(mocks.situationReport);
      }
      return Promise.resolve({ ...DASHBOARD_DOC, profileCompletion: "30%" });
    });
    renderJobSeekerDashboard();
    await waitFor(() => expect(screen.getByTestId("intake-modal")).toBeInTheDocument());
  });
});

// ─── D-6: the working-life frame ───────────────────────────────────────────────

/**
 * The lead card, driven end to end through the real `useSituationReport` hook
 * rather than a mocked component: what this asserts is the WIRING — that each
 * report state reaches the dashboard and resolves to one card and one suggested
 * action. The card's own branches are covered beside the component, in
 * `assessments/components/SituationDashboardCard.test.tsx`.
 */
describe("JobSeekerDashboard - Situation Report card", () => {
  it("needs_core: explains the missing half and lets the banner own the CTA", async () => {
    mocks.situationReport = NEEDS_CORE;
    renderJobSeekerDashboard();
    expect(
      await screen.findByText("Your conditions, once we have your side"),
    ).toBeInTheDocument();
    // The Work Pulse banner is on screen for this user and already says "Start
    // now", so the card must not print a second button to the same place.
    expect(screen.getByTestId("wp-banner")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Start Work Pulse/ })).toBeNull();
  });

  it("needs_core: takes the CTA back once the banner is dismissed", async () => {
    mocks.situationReport = NEEDS_CORE;
    renderJobSeekerDashboard();
    await screen.findByText("Your conditions, once we have your side");
    fireEvent.click(screen.getByText("Dismiss Banner"));
    expect(screen.getByRole("link", { name: /Start Work Pulse/ })).toHaveAttribute(
      "href",
      "/work-pulse",
    );
  });

  it("needs_environment_report: one card, one action — describe the job", async () => {
    mocks.situationReport = NEEDS_ENV;
    renderJobSeekerDashboard();
    expect(await screen.findByText("One half to go")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Describe your job/ })).toHaveAttribute(
      "href",
      "/environment-report",
    );
  });

  it("first_job: goes straight to the report, and does not offer a form it cannot accept", async () => {
    mocks.situationReport = FIRST_JOB;
    renderJobSeekerDashboard();
    expect(await screen.findByText("Your report starts when the job does")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /See your Situation Report/ })).toHaveAttribute(
      "href",
      "/situation-report",
    );
    expect(screen.queryByRole("link", { name: /Describe your job/ })).toBeNull();
  });

  it("complete: summarises conditions as words and offers exactly one next action", async () => {
    mocks.situationReport = COMPLETE;
    renderJobSeekerDashboard();
    expect(await screen.findByText("How your conditions sit")).toBeInTheDocument();
    expect(screen.getByText("Autonomy — Straining")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /See your Situation Report/ })).toHaveAttribute(
      "href",
      "/situation-report",
    );

    const card = screen.getByTestId("situation-card");
    expect(within(card).getAllByText("Next")).toHaveLength(1);
    expect(within(card).getByRole("link", { name: /Profile your manager/ })).toHaveAttribute(
      "href",
      "/manager-profile",
    );
  });

  it("complete: not one digit reaches the conditions summary (D-15)", async () => {
    // Scoped to the card, not the page: PulseDashboardCard legitimately renders
    // a date beside it. The rule is about the report's own resolution — the
    // payload's `env_score` and `rank` may not surface here in any form.
    mocks.situationReport = COMPLETE;
    renderJobSeekerDashboard();
    await screen.findByText("How your conditions sit");
    const text = screen.getByTestId("situation-card").textContent ?? "";
    expect(text, "a number reached the conditions summary").not.toMatch(/\d/);
  });
});

// ─── failed dashboard document (G14) ────────────────────────────────────────

/**
 * Regression tests: `/me/dashboard` failing used to leave `dashboardData`
 * undefined and render straight through to the two empty-state cards ("Nothing
 * here yet." / "No recommendations yet.") as if this were simply a new
 * account with nothing in it, and `dashboardData?.hasIntakeSubmission ?? false`
 * forced the intake flag to a known-wrong value the moment the fetch failed.
 */
describe("JobSeekerDashboard - failed dashboard document (G14)", () => {
  it("shows a retry notice in place of both cards, not the empty states", async () => {
    let calls = 0;
    mocks.fetchWithAuth.mockImplementation((path: string) => {
      if (path.startsWith("/me/pulse/")) return Promise.resolve({ checkins: [], events: [] });
      if (path.startsWith("/me/situation-report")) return Promise.resolve(mocks.situationReport);
      calls += 1;
      return calls === 1
        ? Promise.reject(new ApiError("boom", { status: 403 }))
        : Promise.resolve(DASHBOARD_DOC);
    });
    renderJobSeekerDashboard();

    expect(
      await screen.findByText(/We couldn't load your dashboard right now/),
    ).toBeInTheDocument();
    expect(screen.queryByText("Nothing here yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("No recommendations yet.")).not.toBeInTheDocument();
    // hasIntakeSubmission must not be forced to false: the modal must not open
    // off an unknown document.
    expect(screen.queryByTestId("intake-modal")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Nothing here yet.")).toBeInTheDocument();
  });

  it("shows Loading… rather than the empty-state cards while the document is in flight", async () => {
    mocks.fetchWithAuth.mockImplementation((path: string) => {
      if (path.startsWith("/me/pulse/")) return Promise.resolve({ checkins: [], events: [] });
      if (path.startsWith("/me/situation-report")) return Promise.resolve(mocks.situationReport);
      return new Promise(() => {});
    });
    renderJobSeekerDashboard();

    expect(await screen.findAllByText("Loading…")).toHaveLength(2);
    expect(screen.queryByText("Nothing here yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("No recommendations yet.")).not.toBeInTheDocument();
  });
});

describe("JobSeekerDashboard - what D-6 keeps", () => {
  it("still mounts the pulse card", async () => {
    renderJobSeekerDashboard();
    // Its no-check-ins invitation, i.e. the real B-3 card rendering for a new
    // account rather than a stand-in.
    expect(await screen.findByText("Keep a pulse on work")).toBeInTheDocument();
  });

  it("still offers Edit Profile and the one instrument action", async () => {
    renderJobSeekerDashboard();
    expect(screen.getByText("Edit Profile")).toBeInTheDocument();
    expect(screen.getByText("Your Solverah profile")).toBeInTheDocument();
  });
});
