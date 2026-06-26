import { render, screen, fireEvent } from "@testing-library/react";
import ProfileCompletenessNudge from "../ProfileCompletenessNudge";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ALL_COMPLETE = {
  workPulseComplete: true,
  careerStatusSet: true,
  managerMatchComplete: true,
  onCareerStatusSet: vi.fn(),
};

function renderNudge(
  overrides: Partial<typeof ALL_COMPLETE> = {},
  children = <div>Suggestion cards</div>
) {
  return render(
    <ProfileCompletenessNudge {...ALL_COMPLETE} {...overrides}>
      {children}
    </ProfileCompletenessNudge>
  );
}

// ---------------------------------------------------------------------------
// WorkPulse blocking state
// ---------------------------------------------------------------------------

describe("WorkPulse not completed", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the WorkPulse blocking message", () => {
    renderNudge({ workPulseComplete: false });
    expect(
      screen.getByText(/complete workpulse to unlock path suggestions/i)
    ).toBeInTheDocument();
  });

  it("hides suggestion cards when WorkPulse is incomplete", () => {
    renderNudge({ workPulseComplete: false });
    expect(screen.queryByText("Suggestion cards")).not.toBeInTheDocument();
  });

  it("navigates to /work-pulse when the CTA is clicked", () => {
    renderNudge({ workPulseComplete: false });
    fireEvent.click(screen.getByRole("button", { name: /take workpulse/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/work-pulse");
  });
});

// ---------------------------------------------------------------------------
// Career status not set
// ---------------------------------------------------------------------------

describe("Career status not set", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the career status prompt", () => {
    renderNudge({ careerStatusSet: false });
    expect(screen.getByText(/where are you in your career/i)).toBeInTheDocument();
  });

  it("hides suggestion cards when career status is not set", () => {
    renderNudge({ careerStatusSet: false });
    expect(screen.queryByText("Suggestion cards")).not.toBeInTheDocument();
  });

  it("collapses the prompt to an inline nudge after dismiss", () => {
    renderNudge({ careerStatusSet: false });
    fireEvent.click(screen.getByRole("button", { name: /dismiss career status prompt/i }));
    expect(screen.queryByText(/where are you in your career/i)).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /set your career status/i })
    ).toBeInTheDocument();
  });

  it("reopens the full prompt when the inline nudge link is clicked", () => {
    renderNudge({ careerStatusSet: false });
    fireEvent.click(screen.getByRole("button", { name: /dismiss career status prompt/i }));
    fireEvent.click(screen.getByRole("button", { name: /set your career status/i }));
    expect(screen.getByText(/where are you in your career/i)).toBeInTheDocument();
  });

  it("calls onCareerStatusSet when a status option is selected", () => {
    const onCareerStatusSet = vi.fn();
    render(
      <ProfileCompletenessNudge
        {...ALL_COMPLETE}
        careerStatusSet={false}
        onCareerStatusSet={onCareerStatusSet}
      >
        <div>Suggestion cards</div>
      </ProfileCompletenessNudge>
    );
    fireEvent.click(screen.getByRole("button", { name: /currently employed/i }));
    expect(onCareerStatusSet).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// ManagerMatch soft nudge
// ---------------------------------------------------------------------------

describe("ManagerMatch not completed", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the ManagerMatch banner", () => {
    renderNudge({ managerMatchComplete: false });
    expect(
      screen.getByText(/complete managermatch to factor your management preferences/i)
    ).toBeInTheDocument();
  });

  it("renders suggestion cards alongside the ManagerMatch banner", () => {
    renderNudge({ managerMatchComplete: false });
    expect(screen.getByText("Suggestion cards")).toBeInTheDocument();
  });

  it("hides the banner after dismiss", () => {
    renderNudge({ managerMatchComplete: false });
    fireEvent.click(screen.getByRole("button", { name: /dismiss managermatch nudge/i }));
    expect(
      screen.queryByText(/complete managermatch to factor your management preferences/i)
    ).not.toBeInTheDocument();
  });

  it("keeps suggestion cards visible after dismissing the banner", () => {
    renderNudge({ managerMatchComplete: false });
    fireEvent.click(screen.getByRole("button", { name: /dismiss managermatch nudge/i }));
    expect(screen.getByText("Suggestion cards")).toBeInTheDocument();
  });

  it("navigates to /manager-match when the link is clicked", () => {
    renderNudge({ managerMatchComplete: false });
    fireEvent.click(screen.getByRole("button", { name: /go to managermatch/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/manager-match");
  });
});

// ---------------------------------------------------------------------------
// All conditions met
// ---------------------------------------------------------------------------

describe("All conditions met", () => {
  it("renders only children with no nudge UI", () => {
    renderNudge();
    expect(screen.getByText("Suggestion cards")).toBeInTheDocument();
    expect(screen.queryByText(/complete workpulse/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/complete managermatch/i)
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/where are you in your career/i)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Priority ordering
// ---------------------------------------------------------------------------

describe("Priority ordering", () => {
  it("WorkPulse blocker takes priority over career status nudge", () => {
    renderNudge({ workPulseComplete: false, careerStatusSet: false });
    expect(
      screen.getByText(/complete workpulse to unlock path suggestions/i)
    ).toBeInTheDocument();
    expect(screen.queryByText(/where are you in your career/i)).not.toBeInTheDocument();
  });

  it("career status nudge takes priority over ManagerMatch banner", () => {
    renderNudge({ careerStatusSet: false, managerMatchComplete: false });
    expect(screen.getByText(/where are you in your career/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/complete managermatch/i)
    ).not.toBeInTheDocument();
  });
});
