import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import JobSeekerDashboard, { hrefsOfferedElsewhere, timeAgo } from "./JobSeekerDashboard";
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
    expect(await screen.findByText("You're just getting started.")).toBeInTheDocument();
    expect(
      screen.getByText(/When you take Work Pulse or update your profile/i),
    ).toBeInTheDocument();
  });

  it("tells a new user why Recommendations is empty", async () => {
    renderJobSeekerDashboard();
    expect(await screen.findByText("Suggestions start after Work Pulse.")).toBeInTheDocument();
    expect(screen.getByText(/point you to what.s worth doing next/i)).toBeInTheDocument();
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
    expect(screen.queryByText("You're just getting started.")).toBeNull();
    expect(screen.queryByText("Suggestions start after Work Pulse.")).toBeNull();
  });
});

// ─── real activity + recommendations ──────────────────────────────────────────

/**
 * `/me/dashboard` sends real rows now: activity `time` is an ISO timestamp the
 * page humanizes, and recommendation hrefs are SPA routes, not only profile
 * tabs. Before 2026-09-28 both lists were static placeholders.
 */
describe("JobSeekerDashboard - real activity and recommendations", () => {
  const withDoc = (doc: Record<string, unknown>) =>
    mocks.fetchWithAuth.mockImplementation((path: string) => {
      if (path.startsWith("/me/pulse/")) return Promise.resolve({ checkins: [], events: [] });
      if (path.startsWith("/me/situation-report")) return Promise.resolve(mocks.situationReport);
      return Promise.resolve({ ...DASHBOARD_DOC, ...doc });
    });

  it("humanizes an ISO activity timestamp and keeps the raw value on <time>", async () => {
    const iso = new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString();
    withDoc({
      recentActivity: [{ type: "pulse", icon: "TrendingUp", text: "You checked in on your week", time: iso }],
    });
    renderJobSeekerDashboard();

    expect(await screen.findByText("You checked in on your week")).toBeInTheDocument();
    const stamp = screen.getByText("3 hours ago");
    expect(stamp.tagName).toBe("TIME");
    expect(stamp).toHaveAttribute("datetime", iso);
  });

  it("navigates straight to a non-profile route", async () => {
    withDoc({
      recommendations: [{ id: "manager_match", title: "Try Manager Match", href: "/manager-match", priority: "normal" }],
    });
    renderJobSeekerDashboard();

    fireEvent.click(await screen.findByText("Try Manager Match"));
    expect(mocks.navigate).toHaveBeenCalledWith("/manager-match");
  });

  it("still turns a profile hash into a tab", async () => {
    withDoc({
      recommendations: [{ id: "skills", title: "Add your skills", href: "/job-seeker/profile#experience" }],
    });
    renderJobSeekerDashboard();

    fireEvent.click(await screen.findByText("Add your skills"));
    expect(mocks.navigate).toHaveBeenCalledWith({
      pathname: "/job-seeker/profile",
      search: "?tab=experience",
    });
  });

  it("opens the career-status modal for the career_status step", async () => {
    withDoc({
      recommendations: [{ id: "career_status", title: "Tell us where you are in your career", href: "/job-seeker/profile", priority: "urgent" }],
    });
    renderJobSeekerDashboard();

    fireEvent.click(await screen.findByText("Tell us where you are in your career"));
    expect(mocks.navigate).toHaveBeenCalledWith("/job-seeker/profile", {
      state: { showCareerStatusModal: true },
    });
  });
});

/**
 * D-6: one place, one button. A recommendation whose route the Work Pulse
 * banner or the Situation Report card already links to on this screen is not
 * rendered a second time.
 */
describe("JobSeekerDashboard - recommendations do not repeat the lead cards (D-6)", () => {
  const RECS = [
    { id: "work_pulse", title: "Take Work Pulse", href: "/work-pulse", priority: "urgent" },
    { id: "environment_report", title: "Describe your current job", href: "/environment-report" },
    { id: "situation_report", title: "Read your Situation Report", href: "/situation-report" },
    { id: "skills", title: "Add your skills", href: "/job-seeker/profile#experience" },
  ];
  const withRecs = () =>
    mocks.fetchWithAuth.mockImplementation((path: string) => {
      if (path.startsWith("/me/pulse/")) return Promise.resolve({ checkins: [], events: [] });
      if (path.startsWith("/me/situation-report")) return Promise.resolve(mocks.situationReport);
      return Promise.resolve({ ...DASHBOARD_DOC, recommendations: RECS });
    });
  const recsCard = async () => {
    await screen.findByText("Add your skills");
    // The situation card resolves on its own query; wait for it before judging.
    await screen.findByTestId("situation-card");
    return screen.getByText("Recommendations").parentElement as HTMLElement;
  };

  it("drops Work Pulse while the banner offers it", async () => {
    mocks.situationReport = NEEDS_CORE;
    withRecs();
    renderJobSeekerDashboard();
    const card = await recsCard();
    expect(within(card).queryByText("Take Work Pulse")).toBeNull();
    expect(within(card).getByText("Describe your current job")).toBeInTheDocument();
  });

  it("drops the Environment Report while the situation card's Next offers it", async () => {
    mocks.user = { ...mocks.user, wp_v2_completed: true };
    mocks.situationReport = NEEDS_ENV;
    withRecs();
    renderJobSeekerDashboard();
    const card = await recsCard();
    expect(within(card).queryByText("Describe your current job")).toBeNull();
    expect(within(card).getByText("Take Work Pulse")).toBeInTheDocument();
    expect(within(card).getByText("Read your Situation Report")).toBeInTheDocument();
  });

  it("drops the pulse check-in, which the pulse card always links to", async () => {
    mocks.situationReport = NEEDS_CORE;
    mocks.fetchWithAuth.mockImplementation((path: string) => {
      if (path.startsWith("/me/pulse/")) return Promise.resolve({ checkins: [], events: [] });
      if (path.startsWith("/me/situation-report")) return Promise.resolve(mocks.situationReport);
      return Promise.resolve({
        ...DASHBOARD_DOC,
        recommendations: [...RECS, { id: "pulse", title: "Check in on your week", href: "/pulse" }],
      });
    });
    renderJobSeekerDashboard();
    const card = await recsCard();
    expect(within(card).queryByText("Check in on your week")).toBeNull();
  });

  it("drops the Situation Report once the card links to it", async () => {
    mocks.user = { ...mocks.user, wp_v2_completed: true };
    mocks.situationReport = COMPLETE;
    withRecs();
    renderJobSeekerDashboard();
    const card = await recsCard();
    expect(within(card).queryByText("Read your Situation Report")).toBeNull();
    expect(within(card).getByText("Add your skills")).toBeInTheDocument();
  });
});

describe("hrefsOfferedElsewhere", () => {
  it("offers only the always-present pulse card's link without a report or banner", () => {
    expect([...hrefsOfferedElsewhere(undefined, false)]).toEqual(["/pulse"]);
  });

  it("needs_core: the card takes Work Pulse only when the banner is gone", () => {
    expect([...hrefsOfferedElsewhere(NEEDS_CORE as any, true)]).toEqual(["/pulse", "/work-pulse"]);
    expect([...hrefsOfferedElsewhere(NEEDS_CORE as any, false)]).toEqual(["/pulse", "/work-pulse"]);
  });

  it("first_job: FocusType and the report link", () => {
    expect(hrefsOfferedElsewhere(FIRST_JOB as any, false)).toEqual(
      new Set(["/pulse", "/focus-type", "/situation-report"]),
    );
  });

  it("complete: the manager step and the report link", () => {
    expect(hrefsOfferedElsewhere(COMPLETE as any, false)).toEqual(
      new Set(["/pulse", "/manager-profile", "/situation-report"]),
    );
  });
});

describe("timeAgo", () => {
  const now = new Date("2026-09-28T12:00:00Z");
  const ago = (ms: number) => new Date(now.getTime() - ms).toISOString();

  it.each([
    [ago(20 * 1000), "just now"],
    [ago(5 * 60 * 1000), "5 min ago"],
    [ago(60 * 60 * 1000), "1 hour ago"],
    [ago(26 * 60 * 60 * 1000), "yesterday"],
    [ago(3 * 24 * 60 * 60 * 1000), "3 days ago"],
    [ago(9 * 24 * 60 * 60 * 1000), "last week"],
    [ago(21 * 24 * 60 * 60 * 1000), "3 weeks ago"],
  ])("%s -> %s", (iso, expected) => {
    expect(timeAgo(iso, now)).toBe(expected);
  });

  it("treats a future timestamp (clock skew) as just now", () => {
    expect(timeAgo("2026-09-28T12:05:00Z", now)).toBe("just now");
  });

  it("falls back to a date after a month, and passes unparseable text through", () => {
    expect(timeAgo(ago(45 * 24 * 60 * 60 * 1000), now)).toMatch(/2026/);
    expect(timeAgo("2h ago", now)).toBe("2h ago");
    expect(timeAgo(undefined, now)).toBe("");
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
 * undefined and render straight through to the two empty-state cards (then
 * "Nothing here yet." / "No recommendations yet.") as if this were simply a new
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
    expect(screen.queryByText("You're just getting started.")).not.toBeInTheDocument();
    expect(screen.queryByText("Suggestions start after Work Pulse.")).not.toBeInTheDocument();
    // hasIntakeSubmission must not be forced to false: the modal must not open
    // off an unknown document.
    expect(screen.queryByTestId("intake-modal")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("You're just getting started.")).toBeInTheDocument();
  });

  it("shows Loading… rather than the empty-state cards while the document is in flight", async () => {
    mocks.fetchWithAuth.mockImplementation((path: string) => {
      if (path.startsWith("/me/pulse/")) return Promise.resolve({ checkins: [], events: [] });
      if (path.startsWith("/me/situation-report")) return Promise.resolve(mocks.situationReport);
      return new Promise(() => {});
    });
    renderJobSeekerDashboard();

    expect(await screen.findAllByText("Loading…")).toHaveLength(2);
    expect(screen.queryByText("You're just getting started.")).not.toBeInTheDocument();
    expect(screen.queryByText("Suggestions start after Work Pulse.")).not.toBeInTheDocument();
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
