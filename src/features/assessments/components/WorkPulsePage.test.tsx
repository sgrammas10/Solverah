/**
 * WorkPulsePage now serves the 24-item person-side assessment (the instrument behind the
 * Bayesian matching model) under the Work Pulse name. These tests cover the page shell:
 * gating, copy, completion state, and the legacy-results link. The instrument mechanics --
 * server-ordered items, opaque tokens, no client shuffling -- are owned by
 * useAssessment.test.ts and AssessmentStepper.test.tsx.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import WorkPulsePage from "./WorkPulsePage";

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
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ user: mocks.user, updateProfile: mocks.updateProfile }),
}));

vi.mock("../useAssessment", () => ({
  useAssessment: () => mocks.assessment,
}));

vi.mock("./AssessmentStepper", () => ({
  default: (props: any) => {
    mocks.stepperProps = props;
    return <div data-testid="assessment-stepper">AssessmentStepper</div>;
  },
}));

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
});

function renderPage() {
  render(
    <MemoryRouter>
      <WorkPulsePage />
    </MemoryRouter>
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
      screen.getByText("24 questions about you. Now 15 about your job."),
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
