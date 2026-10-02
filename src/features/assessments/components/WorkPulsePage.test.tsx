/**
 * WorkPulsePage now serves the 24-item person-side assessment (the instrument behind the
 * Bayesian matching model) under the Work Pulse name. These tests cover the page shell:
 * gating, copy, completion state, and the legacy-results link. The instrument mechanics --
 * server-ordered items, opaque tokens, no client shuffling -- are owned by
 * useAssessment.test.ts and AssessmentStepper.test.tsx.
 */
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import WorkPulsePage, { DASHBOARD_QUERY_KEY, SUBMIT_ERROR_MESSAGE } from "./WorkPulsePage";
import { situationReportKeys } from "../useSituationReport";
// A deep import on purpose, test-only: `dashboardKeys` is not on the profile
// slice's public surface, and this test exists to fail if WorkPulsePage's
// spelled-out copy of it drifts from the dashboard's own.
// eslint-disable-next-line no-restricted-imports
import { dashboardKeys } from "../../profile/dashboardKeys";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  user: null as any,
  updateProfile: vi.fn(),
  assessment: {
    items: null as any,
    answers: {} as Record<string, string>,
    loadError: null as string | null,
    submitError: null as string | null,
    submitting: false,
    setAnswer: vi.fn(),
    clearAnswers: vi.fn(),
    submit: vi.fn(),
    reloadForm: vi.fn(),
  },
  stepperProps: null as any,
  stepperMounts: 0,
  situation: null as any,
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ user: mocks.user, updateProfile: mocks.updateProfile }),
}));

vi.mock("../useAssessment", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../useAssessment")>();
  return { ...actual, useAssessment: () => mocks.assessment };
});

// The completion card reads the Situation Report to choose its next step.
vi.mock("../useSituationReport", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../useSituationReport")>();
  return { ...actual, useSituationReport: () => mocks.situation };
});

vi.mock("./AssessmentStepper", async () => {
  const { useEffect } = await import("react");
  return {
    default: (props: any) => {
      mocks.stepperProps = props;
      // Counts mounts, so a test can see the stepper reopen after a reload.
      useEffect(() => {
        mocks.stepperMounts += 1;
      }, []);
      return <div data-testid="assessment-stepper">AssessmentStepper</div>;
    },
  };
});

vi.mock("../../../shared/ui/HeroNetworkAnimation", () => ({
  default: () => null,
}));

const ITEMS = [
  { token: "zulu", prompt: "Q1", options: [{ key: "A", text: "a" }, { key: "B", text: "b" }] },
  { token: "mike", prompt: "Q2", options: [{ key: "A", text: "a" }, { key: "B", text: "b" }] },
];

beforeEach(() => {
  vi.clearAllMocks();
  mocks.user = { name: "Ada", wpl_completed: false, wp_v2_completed: false };
  mocks.assessment.items = ITEMS;
  mocks.assessment.answers = {};
  mocks.assessment.loadError = null;
  mocks.assessment.submitError = null;
  mocks.assessment.submitting = false;
  mocks.assessment.submit = vi.fn();
  mocks.assessment.reloadForm = vi.fn();
  mocks.assessment.clearAnswers = vi.fn();
  mocks.stepperProps = null;
  mocks.stepperMounts = 0;
  mocks.situation = {
    data: { state: "needs_environment_report", can_submit_environment_report: true },
    isPending: false,
    isFetching: false,
  };
});

let queryClient: QueryClient;

function renderPage() {
  queryClient = new QueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <WorkPulsePage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("WorkPulsePage — form state", () => {
  it("renders the Work Pulse heading and the stepper with server items", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: "Work Pulse" })).toBeInTheDocument();
    expect(screen.getByTestId("assessment-stepper")).toBeInTheDocument();
    expect(mocks.stepperProps.items).toBe(ITEMS);
  });

  it("carries the load-bearing copy verbatim", () => {
    // Both lines are mitigations, not marketing. See the page header before changing.
    renderPage();
    expect(screen.getByText(/There are no right answers/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Employers never see your answers or your dimension scores/i)
    ).toBeInTheDocument();
  });

  it("offers the trust page from the intro", () => {
    // BUILD_PLAN D-3. The two lines above make claims; this is the link to the
    // page that backs them. A reader who doubts the employer line should not
    // have to go hunting through the hub for the explanation.
    renderPage();
    expect(
      screen.getByRole("link", { name: /how this works, and what we hold back/i })
    ).toHaveAttribute("href", "/trust");
  });

  it("shows a loading state before the form arrives", () => {
    mocks.assessment.items = null;
    renderPage();
    expect(screen.getByText(/Loading/i)).toBeInTheDocument();
    expect(screen.queryByTestId("assessment-stepper")).toBeNull();
  });

  it("shows the house error panel, not the raw message, and no stepper when the form is unservable", () => {
    // G7 regression: the page used to render `loadError` verbatim. Without
    // the fix, this asserts the opposite of what it does now and fails.
    mocks.assessment.items = null;
    mocks.assessment.loadError = "boom";
    renderPage();
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("We couldn't load Work Pulse right now.");
    expect(alert).not.toHaveTextContent("boom");
    expect(screen.queryByTestId("assessment-stepper")).toBeNull();
  });

  it("retries the form fetch via reloadForm when Try again is clicked", () => {
    mocks.assessment.items = null;
    mocks.assessment.loadError = "boom";
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(mocks.assessment.reloadForm).toHaveBeenCalled();
  });

  it("does NOT link to previous results for a user with no old sitting", () => {
    renderPage();
    expect(screen.queryByText(/previous analysis/i)).toBeNull();
  });

  it("links old-quiz completers to their previous analysis while re-prompting them", () => {
    mocks.user = { name: "Ada", wpl_completed: true, wp_v2_completed: false };
    renderPage();
    // Re-prompted: the form is shown, not a completion state...
    expect(screen.getByTestId("assessment-stepper")).toBeInTheDocument();
    // ...and the old narrative stays reachable until they retake.
    expect(screen.getByText(/View your previous analysis/i)).toBeInTheDocument();
  });
});

describe("WorkPulsePage — completion", () => {
  it("shows the completion state instead of the form when the current instrument is done", () => {
    mocks.user = { name: "Ada", wpl_completed: false, wp_v2_completed: true };
    renderPage();
    expect(screen.getByText(/Work Pulse Complete/i)).toBeInTheDocument();
    expect(screen.queryByTestId("assessment-stepper")).toBeNull();
  });

  it("on successful submit flips to the completion state and updates the local profile", async () => {
    mocks.assessment.submit = vi.fn().mockResolvedValue({
      submission_id: "abc",
      scoring_key_version: "v2-2026-08-18+mean_pole",
      dimensions_scored: 6,
    });
    renderPage();
    mocks.stepperProps.onComplete();
    await waitFor(() =>
      expect(mocks.updateProfile).toHaveBeenCalledWith({ wp_v2_completed: true })
    );
    expect(screen.getByText(/Work Pulse Complete/i)).toBeInTheDocument();
    expect(screen.queryByTestId("assessment-stepper")).toBeNull();
  });

  it("stays on the form when submit fails, so the error remains visible", async () => {
    mocks.assessment.submit = vi.fn().mockResolvedValue(null);
    renderPage();
    mocks.stepperProps.onComplete();
    await waitFor(() => expect(mocks.assessment.submit).toHaveBeenCalled());
    expect(mocks.updateProfile).not.toHaveBeenCalled();
    expect(screen.getByTestId("assessment-stepper")).toBeInTheDocument();
  });

  it("completion state offers no results link, even for old-quiz completers (D-15)", () => {
    // A results link on the completion screen is the gradient D-15 exists to withhold.
    // wpl_completed true is the hard case: the old narrative link must not leak in here.
    mocks.user = { name: "Ada", wpl_completed: true, wp_v2_completed: true };
    renderPage();
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.queryByText(/previous analysis/i)).toBeNull();
  });

  it("back-to-dashboard navigates to the real dashboard route", () => {
    // Regression: this asserted "/dashboard", which is not a registered route.
    // App.tsx registers the dashboard at /job-seeker/dashboard, so the old target
    // fell through to the `path="*"` catch-all and redirected to "/" — the public
    // landing page, which renders its own logged-out nav. Finishing Work Pulse
    // therefore looked like being signed out. The test passed because it asserted
    // the literal string the component passed, never that the string was routable.
    mocks.user = { name: "Ada", wpl_completed: false, wp_v2_completed: true };
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /back to dashboard/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/job-seeker/dashboard", { replace: true });
  });

  it("offers next-instrument CTAs and navigates to FocusType and ManagerMatch", () => {
    mocks.user = { name: "Ada", wpl_completed: false, wp_v2_completed: true };
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /start focustype/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/focus-type");

    fireEvent.click(screen.getByRole("button", { name: /start managermatch/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/manager-match");
  });

  // ── The A-7 bridge, upgrading D-2's ──

  it("bridges to the environment report as the primary next step", () => {
    mocks.user = { name: "Ada", wpl_completed: false, wp_v2_completed: true };
    renderPage();

    expect(
      screen.getByText("24 questions about you. Now 16 about your job."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /describe your job/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/environment-report");
  });

  it("keeps the FocusType and ManagerMatch CTAs alongside it, not instead of it", () => {
    mocks.user = { name: "Ada", wpl_completed: false, wp_v2_completed: true };
    renderPage();

    expect(screen.getByRole("button", { name: /describe your job/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start focustype/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start managermatch/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /back to dashboard/i })).toBeInTheDocument();
  });
});

const THREE = [
  { token: "t1", prompt: "Q1", options: [{ key: "A", text: "a" }, { key: "B", text: "b" }] },
  { token: "t2", prompt: "Q2", options: [{ key: "A", text: "a" }, { key: "B", text: "b" }] },
  { token: "t3", prompt: "Q3", options: [{ key: "A", text: "a" }, { key: "B", text: "b" }] },
];

describe("WorkPulsePage — resume prompt for a saved draft", () => {
  it("asks before resuming instead of dropping the user into the stepper", () => {
    // Regression: a saved draft used to open the stepper at question 1 with the
    // old answers silently pre-selected.
    mocks.assessment.items = THREE;
    mocks.assessment.answers = { t1: "A", t2: "B" };
    renderPage();
    expect(screen.getByRole("button", { name: "Pick up where you left off" })).toBeInTheDocument();
    expect(screen.getByText(/2 of 3 questions/)).toBeInTheDocument();
    expect(screen.queryByTestId("assessment-stepper")).toBeNull();
  });

  it("'Pick up where you left off' opens the stepper at the first unanswered question", () => {
    mocks.assessment.items = THREE;
    mocks.assessment.answers = { t1: "A", t3: "B" };
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Pick up where you left off" }));
    expect(screen.getByTestId("assessment-stepper")).toBeInTheDocument();
    expect(mocks.stepperProps.initialIndex).toBe(1);
    expect(mocks.assessment.clearAnswers).not.toHaveBeenCalled();
  });

  it("'Start over' clears the draft and opens at question 1", () => {
    mocks.assessment.items = THREE;
    mocks.assessment.answers = { t1: "A", t2: "B" };
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Start over" }));
    expect(mocks.assessment.clearAnswers).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("assessment-stepper")).toBeInTheDocument();
    expect(mocks.stepperProps.initialIndex).toBe(0);
  });

  it("no draft: no prompt, straight to question 1", () => {
    mocks.assessment.items = THREE;
    renderPage();
    expect(screen.queryByRole("button", { name: "Start over" })).toBeNull();
    expect(mocks.stepperProps.initialIndex).toBe(0);
  });

  it("a draft whose tokens are not in this form is no draft (no prompt)", () => {
    mocks.assessment.items = THREE;
    mocks.assessment.answers = { stale: "A" };
    renderPage();
    expect(screen.queryByRole("button", { name: "Start over" })).toBeNull();
    expect(screen.getByTestId("assessment-stepper")).toBeInTheDocument();
  });
});

describe("WorkPulsePage — readability over the animation", () => {
  it("puts the form on a near-solid panel rather than straight over the animation", () => {
    // Regression: small ink-secondary copy sat directly on HeroNetworkAnimation.
    renderPage();
    const panel = screen.getByTestId("work-pulse-panel");
    expect(panel.className.split(" ")).toContain("bg-cream-base/95");
    expect(panel).toContainElement(screen.getByText(/There are no right answers/i));
  });

  it("wraps the completion state in the same panel", () => {
    mocks.user = { name: "Ada", wpl_completed: false, wp_v2_completed: true };
    renderPage();
    expect(screen.getByTestId("work-pulse-panel")).toContainElement(
      screen.getByText(/Work Pulse Complete/i)
    );
  });
});

// ─── F3: the dashboard and the Situation card must not contradict this page ──

describe("WorkPulsePage - caches refreshed on completion (F3)", () => {
  it("pins its dashboard key to the dashboard's own", () => {
    expect([...DASHBOARD_QUERY_KEY]).toEqual([...dashboardKeys.all]);
  });

  it("invalidates the Situation Report and the dashboard when Work Pulse is finished", async () => {
    // Regression: only the auth flag flipped, so a cached report still said
    // "needs_core" and the dashboard still prompted for Work Pulse.
    mocks.assessment.submit = vi.fn().mockResolvedValue({
      submission_id: "abc",
      scoring_key_version: "v2+mean_pole",
      dimensions_scored: 6,
    });
    renderPage();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    await act(async () => {
      await mocks.stepperProps.onComplete();
    });
    expect(spy).toHaveBeenCalledWith({ queryKey: situationReportKeys.all });
    expect(spy).toHaveBeenCalledWith({ queryKey: dashboardKeys.all });
  });

  it("invalidates nothing when the submit fails", async () => {
    mocks.assessment.submit = vi.fn().mockResolvedValue(null);
    renderPage();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    await act(async () => {
      await mocks.stepperProps.onComplete();
    });
    expect(spy).not.toHaveBeenCalled();
  });
});

// ─── F5: a failed submit shows the house message and a way out ──────────────

describe("WorkPulsePage - submit errors (F5)", () => {
  it("passes the house message to the stepper, never the server's text", () => {
    // Regression: the hook's error string (server text, e.g. naming an opaque
    // item token) was rendered verbatim under the Finish button.
    mocks.assessment.submitError = "Unknown item token 'zz9' for respondent 4f2a";
    renderPage();
    expect(mocks.stepperProps.submitError).toBe(SUBMIT_ERROR_MESSAGE);
    expect(mocks.stepperProps.submitError).not.toContain("zz9");
  });

  it("passes no message when there is no error", () => {
    renderPage();
    expect(mocks.stepperProps.submitError).toBeNull();
  });

  it("offers 'reload the questions', which refetches and reopens at the first unanswered item", async () => {
    mocks.assessment.submitError = "boom";
    mocks.assessment.answers = { zulu: "A" };
    // The reloaded form puts the unanswered "mike" first, so the reopen index
    // has to come from the fresh form, not from the one on screen.
    mocks.assessment.reloadForm = vi.fn().mockResolvedValue({
      data: {
        form_version: "v2",
        respondent_id: "r",
        blocks: [{ block: 1, items: [ITEMS[1], ITEMS[0]] }],
      },
    });
    renderPage();
    // The draft gets the resume prompt first; resuming opens at "mike" (1).
    fireEvent.click(screen.getByRole("button", { name: "Pick up where you left off" }));
    expect(mocks.stepperMounts).toBe(1);
    expect(mocks.stepperProps.initialIndex).toBe(1);
    expect(mocks.stepperProps.submitError).toBe(SUBMIT_ERROR_MESSAGE);

    await act(async () => {
      await mocks.stepperProps.onReloadQuestions();
    });

    expect(mocks.assessment.reloadForm).toHaveBeenCalled();
    // Remounted at "mike" again, which is index 0 in the reloaded form.
    expect(mocks.stepperMounts).toBe(2);
    expect(mocks.stepperProps.initialIndex).toBe(0);
    // The old error is answered by the reload; it stays hidden until Finish.
    expect(mocks.stepperProps.submitError).toBeNull();
  });
});

// ─── The Situation Report hand-off on the completion card ───────────────────

describe("WorkPulsePage - next step after completion", () => {
  beforeEach(() => {
    mocks.user = { name: "Ada", wpl_completed: false, wp_v2_completed: true };
  });

  it("first_job: no 'Describe your job' button; FocusType leads", () => {
    // Regression: a first_job user was led to a form the server refuses (409).
    mocks.situation = {
      data: { state: "needs_environment_report", can_submit_environment_report: false },
      isPending: false,
      isFetching: false,
    };
    renderPage();
    expect(screen.queryByRole("button", { name: /describe your job/i })).toBeNull();
    expect(screen.queryByText("24 questions about you. Now 16 about your job.")).toBeNull();
    const focusType = screen.getByRole("button", { name: /start focustype/i });
    expect(focusType.className).toContain("bg-forest-dark");
    expect(screen.getByRole("button", { name: /start managermatch/i }).className).not.toContain(
      "bg-forest-dark"
    );
  });

  it("job described first: opens the report instead of asking again", () => {
    mocks.situation = {
      data: { state: "complete", career_status: "employed" },
      isPending: false,
      isFetching: false,
    };
    renderPage();
    expect(screen.queryByRole("button", { name: /describe your job/i })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /see your situation report/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/situation-report");
  });

  it("while the report is loading, offers no bridge a first_job user could not use", () => {
    mocks.situation = { data: undefined, isPending: true, isFetching: true };
    renderPage();
    expect(screen.queryByRole("button", { name: /describe your job/i })).toBeNull();
    expect(screen.getByRole("button", { name: /start focustype/i })).toBeInTheDocument();
  });

  it("a stale pre-completion report being refetched counts as loading", () => {
    mocks.situation = { data: { state: "needs_core", environment: null }, isPending: false, isFetching: true };
    renderPage();
    expect(screen.queryByRole("button", { name: /describe your job/i })).toBeNull();
  });

  it("a failed report fetch falls back to describing the job", () => {
    mocks.situation = { data: undefined, isPending: false, isFetching: false, isError: true };
    renderPage();
    expect(screen.getByRole("button", { name: /describe your job/i })).toBeInTheDocument();
  });
});
