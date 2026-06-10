import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import GuestQuizInsights from "../GuestQuizInsights";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

beforeEach(() => {
  vi.clearAllMocks();
});

function renderGuestQuizInsights(insight?: object) {
  render(
    <MemoryRouter
      initialEntries={[
        { pathname: "/guest-quiz-insights", state: insight ? { insight } : undefined },
      ]}
    >
      <GuestQuizInsights />
    </MemoryRouter>
  );
}

const MOCK_INSIGHT = {
  overallSummary: "You have strong analytical tendencies.",
  insights: [
    {
      title: "Career Clarity",
      summary: "You value structured environments.",
      keyTakeaways: ["Prefer clear goals", "Thrive with mentorship"],
      nextSteps: ["Update your resume", "Explore tech roles"],
    },
    {
      title: "Growth Mindset",
      summary: "You embrace challenges.",
    },
  ],
};

// ─── happy path ────────────────────────────────────────────────────────────────

describe("GuestQuizInsights - happy path", () => {
  it("renders the page heading", () => {
    renderGuestQuizInsights(MOCK_INSIGHT);
    expect(screen.getByText("Quiz Insights")).toBeInTheDocument();
  });

  it("shows overall summary when provided", () => {
    renderGuestQuizInsights(MOCK_INSIGHT);
    expect(screen.getByText("You have strong analytical tendencies.")).toBeInTheDocument();
  });

  it("renders each insight card title", () => {
    renderGuestQuizInsights(MOCK_INSIGHT);
    expect(screen.getByText("Career Clarity")).toBeInTheDocument();
    expect(screen.getByText("Growth Mindset")).toBeInTheDocument();
  });

  it("renders key takeaways", () => {
    renderGuestQuizInsights(MOCK_INSIGHT);
    expect(screen.getByText("Prefer clear goals")).toBeInTheDocument();
    expect(screen.getByText("Thrive with mentorship")).toBeInTheDocument();
  });

  it("renders next steps", () => {
    renderGuestQuizInsights(MOCK_INSIGHT);
    expect(screen.getByText("Update your resume")).toBeInTheDocument();
  });
});

// ─── empty state ──────────────────────────────────────────────────────────────

describe("GuestQuizInsights - empty state", () => {
  it("shows no-insights message when no state is provided", () => {
    renderGuestQuizInsights();
    expect(screen.getByText(/No insights found/i)).toBeInTheDocument();
  });

  it("shows no-insights message when insights array is empty", () => {
    renderGuestQuizInsights({ overallSummary: null, insights: [] });
    expect(screen.getByText(/No insights found/i)).toBeInTheDocument();
  });
});

// ─── navigation ───────────────────────────────────────────────────────────────

describe("GuestQuizInsights - navigation", () => {
  it("back to quizzes button navigates to /quiz-preview", () => {
    renderGuestQuizInsights(MOCK_INSIGHT);
    fireEvent.click(screen.getByRole("button", { name: /back to quizzes/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/quiz-preview");
  });

  it("sign in button navigates to /login", () => {
    renderGuestQuizInsights(MOCK_INSIGHT);
    fireEvent.click(screen.getByRole("button", { name: /sign in to save results/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/login");
  });

  it("create account button navigates to /register", () => {
    renderGuestQuizInsights(MOCK_INSIGHT);
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/register");
  });
});
