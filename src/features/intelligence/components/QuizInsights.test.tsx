import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import QuizInsights from "./QuizInsights";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchProfileData: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ fetchProfileData: mocks.fetchProfileData }),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

const MOCK_CAREER_INSIGHTS = {
  careerQuizzes: {
    earlyCareer: {
      title: "Early Career",
      summary: "You value structured environments.",
      keyTakeaways: ["Seek mentorship", "Prioritise learning"],
      nextSteps: ["Build your network"],
    },
    _overallInsight: {
      summary: "Across all quizzes you show strong analytical skills.",
      keyTakeaways: ["Stay curious"],
      nextSteps: ["Apply to tech roles"],
    },
  },
};

function renderQuizInsights(search = "?group=careerQuizzes", locationState?: object) {
  render(
    <MemoryRouter initialEntries={[{ pathname: "/quiz-insights", search, state: locationState }]}>
      <QuizInsights />
    </MemoryRouter>
  );
}

// ─── loading state ─────────────────────────────────────────────────────────────

describe("QuizInsights - loading state", () => {
  it("shows loading text while fetching", () => {
    mocks.fetchProfileData.mockReturnValue(new Promise(() => {}));
    renderQuizInsights();
    expect(screen.getByText(/Loading insights/i)).toBeInTheDocument();
  });
});

// ─── error state ──────────────────────────────────────────────────────────────

describe("QuizInsights - error state", () => {
  it("shows error message when fetchProfileData rejects", async () => {
    mocks.fetchProfileData.mockRejectedValueOnce(new Error("API error"));
    renderQuizInsights();
    await waitFor(() =>
      expect(screen.getByText(/API error/i)).toBeInTheDocument()
    );
  });
});

// ─── no insights ──────────────────────────────────────────────────────────────

describe("QuizInsights - no insights", () => {
  it("shows empty state when no insights found", async () => {
    mocks.fetchProfileData.mockResolvedValueOnce({
      profileData: { quizInsights: null },
    });
    renderQuizInsights();
    await waitFor(() =>
      expect(screen.getByText(/No insights found yet/i)).toBeInTheDocument()
    );
  });

  it("shows empty state when profileData has no quizInsights key", async () => {
    mocks.fetchProfileData.mockResolvedValueOnce({ profileData: {} });
    renderQuizInsights();
    await waitFor(() =>
      expect(screen.getByText(/No insights found yet/i)).toBeInTheDocument()
    );
  });
});

// ─── happy path (careerQuizzes group) ─────────────────────────────────────────

describe("QuizInsights - careerQuizzes group", () => {
  it("renders insight card titles from profile data", async () => {
    mocks.fetchProfileData.mockResolvedValueOnce({
      profileData: { quizInsights: MOCK_CAREER_INSIGHTS },
    });
    renderQuizInsights("?group=careerQuizzes");
    await waitFor(() => expect(screen.getAllByText("Early Career")[0]).toBeInTheDocument());
  });

  it("renders insight summary text", async () => {
    mocks.fetchProfileData.mockResolvedValueOnce({
      profileData: { quizInsights: MOCK_CAREER_INSIGHTS },
    });
    renderQuizInsights("?group=careerQuizzes");
    await waitFor(() =>
      expect(screen.getByText("You value structured environments.")).toBeInTheDocument()
    );
  });

  it("renders key takeaways", async () => {
    mocks.fetchProfileData.mockResolvedValueOnce({
      profileData: { quizInsights: MOCK_CAREER_INSIGHTS },
    });
    renderQuizInsights("?group=careerQuizzes");
    await waitFor(() => expect(screen.getByText("Seek mentorship")).toBeInTheDocument());
  });

  it("renders overall insight when 'all' filter is active", async () => {
    mocks.fetchProfileData.mockResolvedValueOnce({
      profileData: { quizInsights: MOCK_CAREER_INSIGHTS },
    });
    renderQuizInsights("?group=careerQuizzes");
    await waitFor(() =>
      expect(screen.getByText("Across all quizzes you show strong analytical skills.")).toBeInTheDocument()
    );
  });

  it("renders filter pills", async () => {
    mocks.fetchProfileData.mockResolvedValueOnce({
      profileData: { quizInsights: MOCK_CAREER_INSIGHTS },
    });
    renderQuizInsights("?group=careerQuizzes");
    await waitFor(() => expect(screen.getByRole("button", { name: "All" })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Early Career" })).toBeInTheDocument();
  });

  it("filters to specific insight when pill clicked", async () => {
    mocks.fetchProfileData.mockResolvedValueOnce({
      profileData: { quizInsights: MOCK_CAREER_INSIGHTS },
    });
    renderQuizInsights("?group=careerQuizzes");
    await waitFor(() => screen.getByRole("button", { name: "Early Career" }));
    fireEvent.click(screen.getByRole("button", { name: "Early Career" }));
    // Overall insight should be hidden when a specific filter is active
    expect(screen.queryByText("Across all quizzes you show strong analytical skills.")).toBeNull();
  });
});

// ─── from location state ───────────────────────────────────────────────────────

describe("QuizInsights - from location state", () => {
  it("renders insights from location state when no profile data", async () => {
    mocks.fetchProfileData.mockResolvedValueOnce({ profileData: {} });
    renderQuizInsights("?group=careerQuizzes", {
      insight: {
        overallSummary: "Strong analytical profile.",
        insights: [
          { title: "Career Focus", summary: "You are goal-oriented." },
        ],
      },
    });
    await waitFor(() =>
      expect(screen.getByText("Career Focus")).toBeInTheDocument()
    );
    expect(screen.getByText("Strong analytical profile.")).toBeInTheDocument();
  });
});

// ─── navigation ───────────────────────────────────────────────────────────────

describe("QuizInsights - navigation", () => {
  it("back to assessments button navigates to /intelligence", async () => {
    mocks.fetchProfileData.mockResolvedValueOnce({
      profileData: { quizInsights: MOCK_CAREER_INSIGHTS },
    });
    renderQuizInsights();
    await waitFor(() => screen.getByRole("button", { name: /back to assessments/i }));
    fireEvent.click(screen.getByRole("button", { name: /back to assessments/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/intelligence");
  });
});
