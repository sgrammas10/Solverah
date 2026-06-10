import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import WorkPulsePage from "../WorkPulsePage";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  user: null as any,
  wpState: {
    answers: [] as { questionId: string; optionId: string }[],
    cachedResult: null as any,
  },
  isComplete: false,
  setAnswer: vi.fn(),
  onComplete: null as (() => void) | null,
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../contexts/useAuth", () => ({
  useAuth: () => ({ user: mocks.user }),
}));

vi.mock("../../hooks/useWP", () => ({
  useWP: () => ({
    state: mocks.wpState,
    isComplete: mocks.isComplete,
    setAnswer: mocks.setAnswer,
  }),
}));

vi.mock("../../components/wp/WPStepper", () => ({
  default: ({ onComplete }: { onComplete: () => void }) => {
    mocks.onComplete = onComplete;
    return <div data-testid="wp-stepper">WPStepper</div>;
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.user = null;
  mocks.isComplete = false;
  mocks.wpState = { answers: [], cachedResult: null };
  mocks.onComplete = null;
});

function renderWorkPulsePage() {
  render(
    <MemoryRouter>
      <WorkPulsePage />
    </MemoryRouter>
  );
}

// ─── navigation guard ─────────────────────────────────────────────────────────

describe("WorkPulsePage - navigation guard", () => {
  it("redirects to /work-pulse/results when user.wpl_completed is true", () => {
    mocks.user = { wpl_completed: true };
    renderWorkPulsePage();
    expect(mocks.navigate).toHaveBeenCalledWith("/work-pulse/results", { replace: true });
  });

  it("redirects to /work-pulse/results when isComplete is true", () => {
    mocks.isComplete = true;
    renderWorkPulsePage();
    expect(mocks.navigate).toHaveBeenCalledWith("/work-pulse/results", { replace: true });
  });
});

// ─── happy path ────────────────────────────────────────────────────────────────

describe("WorkPulsePage - happy path", () => {
  it("renders the Work Pulse heading", () => {
    renderWorkPulsePage();
    expect(screen.getByText("Work Pulse")).toBeInTheDocument();
  });

  it("renders the WPStepper component", () => {
    renderWorkPulsePage();
    expect(screen.getByTestId("wp-stepper")).toBeInTheDocument();
  });

  it("shows the question count subheading", () => {
    renderWorkPulsePage();
    expect(screen.getByText(/12 questions/i)).toBeInTheDocument();
  });
});

// ─── completion ───────────────────────────────────────────────────────────────

describe("WorkPulsePage - completion", () => {
  it("navigates to /work-pulse/results when onComplete is called", () => {
    renderWorkPulsePage();
    expect(mocks.onComplete).not.toBeNull();
    mocks.onComplete!();
    expect(mocks.navigate).toHaveBeenCalledWith("/work-pulse/results");
  });
});
