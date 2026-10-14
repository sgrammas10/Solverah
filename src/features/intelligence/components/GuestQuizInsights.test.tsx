import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import GuestQuizInsights from "./GuestQuizInsights";
import { completeGuestQuiz, markGuestQuizCompleted } from "../../../shared/lib/guestQuiz";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

beforeEach(() => {
  localStorage.clear();
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
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Your quiz insights");
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

  it("labels sections with headings in sentence case, not uppercase eyebrows", () => {
    renderGuestQuizInsights(MOCK_INSIGHT);
    expect(screen.getByRole("heading", { level: 3, name: "Key takeaways" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Next steps" })).toBeInTheDocument();
    expect(document.querySelector(".uppercase")).toBeNull();
    expect(document.querySelector(".rounded-full")).toBeNull();
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

  it("offers a way to a quiz from the empty state", () => {
    renderGuestQuizInsights();
    fireEvent.click(screen.getByRole("button", { name: "Choose a quiz" }));
    expect(mocks.navigate).toHaveBeenCalledWith("/quiz-preview");
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

// ─── persistence (G20) ────────────────────────────────────────────────────────

describe("GuestQuizInsights - persisted insight", () => {
  const save = {
    quizGroup: "careerQuizzes",
    quizResults: { careerQuizzes: { earlyCareer: { 1: 0 } } },
    quizPayload: {
      quizGroup: "careerQuizzes",
      quizzes: [{ key: "earlyCareer", title: "Early", items: [{ question: "Q", selected: "A" }] }],
    },
  };

  it("renders the stored insight in a fresh tab with no router state", () => {
    completeGuestQuiz(save, MOCK_INSIGHT);
    renderGuestQuizInsights();
    expect(screen.getByText("Career Clarity")).toBeInTheDocument();
    expect(screen.queryByText(/No insights found/i)).toBeNull();
  });

  it("a locked-out guest with nothing stored is offered sign-in, not the locked quiz list", () => {
    markGuestQuizCompleted();
    renderGuestQuizInsights();
    expect(screen.queryByRole("button", { name: "Choose a quiz" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(mocks.navigate).toHaveBeenCalledWith("/login");
  });

  it("does not crash on a list field that is not a list", () => {
    renderGuestQuizInsights({
      insights: [{ title: "Odd", summary: "x", keyTakeaways: "not a list", nextSteps: 3 }],
    });
    expect(screen.getByText("Odd")).toBeInTheDocument();
  });
});
