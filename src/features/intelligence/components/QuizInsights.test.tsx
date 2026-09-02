import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import QuizInsights from "./QuizInsights";
// Barrel import (boundary rule); the vi.mock below pins the concrete module,
// which still intercepts the barrel's re-export.
import { useProfile } from "../../profile";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

/**
 * The page reads the profile document through useProfile() now -- the
 * fetchProfileData() round trip it used to make on mount is gone. Mocking the
 * hook (the useProfileForm.test precedent) keeps these tests about what the
 * page renders from a given document, not about the query machinery, and
 * needs no QueryClientProvider. The document's *failure* is not renderable
 * here any more: useProfile throws it to RouteErrorBoundary for every
 * consumer, so the old inline-error test left with the inline error UI.
 */
vi.mock("../../profile/useProfile", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../profile/useProfile")>();
  return { ...actual, useProfile: vi.fn() };
});

/** What the mocked useProfile() hands back. Set per test before rendering. */
let mockProfile: Record<string, unknown> | undefined;
let mockProfileLoading: boolean;

beforeEach(() => {
  vi.clearAllMocks();
  mockProfile = {};
  mockProfileLoading = false;
  vi.mocked(useProfile).mockImplementation(
    () => ({ data: mockProfile, isLoading: mockProfileLoading }) as any
  );
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
  it("shows loading text while the profile document is in flight", () => {
    mockProfile = undefined;
    mockProfileLoading = true;
    renderQuizInsights();
    expect(screen.getByText(/Loading insights/i)).toBeInTheDocument();
  });
});

// ─── no insights ──────────────────────────────────────────────────────────────

describe("QuizInsights - no insights", () => {
  it("shows empty state when no insights found", async () => {
    mockProfile = { quizInsights: null };
    renderQuizInsights();
    await waitFor(() =>
      expect(screen.getByText(/No insights found yet/i)).toBeInTheDocument()
    );
  });

  it("shows empty state when the document has no quizInsights key", async () => {
    mockProfile = {};
    renderQuizInsights();
    await waitFor(() =>
      expect(screen.getByText(/No insights found yet/i)).toBeInTheDocument()
    );
  });
});

// ─── happy path (careerQuizzes group) ─────────────────────────────────────────

describe("QuizInsights - careerQuizzes group", () => {
  it("renders insight card titles from profile data", async () => {
    mockProfile = { quizInsights: MOCK_CAREER_INSIGHTS };
    renderQuizInsights("?group=careerQuizzes");
    await waitFor(() => expect(screen.getAllByText("Early Career")[0]).toBeInTheDocument());
  });

  it("renders insight summary text", async () => {
    mockProfile = { quizInsights: MOCK_CAREER_INSIGHTS };
    renderQuizInsights("?group=careerQuizzes");
    await waitFor(() =>
      expect(screen.getByText("You value structured environments.")).toBeInTheDocument()
    );
  });

  it("renders key takeaways", async () => {
    mockProfile = { quizInsights: MOCK_CAREER_INSIGHTS };
    renderQuizInsights("?group=careerQuizzes");
    await waitFor(() => expect(screen.getByText("Seek mentorship")).toBeInTheDocument());
  });

  it("renders overall insight when 'all' filter is active", async () => {
    mockProfile = { quizInsights: MOCK_CAREER_INSIGHTS };
    renderQuizInsights("?group=careerQuizzes");
    await waitFor(() =>
      expect(screen.getByText("Across all quizzes you show strong analytical skills.")).toBeInTheDocument()
    );
  });

  it("renders filter pills", async () => {
    mockProfile = { quizInsights: MOCK_CAREER_INSIGHTS };
    renderQuizInsights("?group=careerQuizzes");
    await waitFor(() => expect(screen.getByRole("button", { name: "All" })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Early Career" })).toBeInTheDocument();
  });

  it("filters to specific insight when pill clicked", async () => {
    mockProfile = { quizInsights: MOCK_CAREER_INSIGHTS };
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
    mockProfile = {};
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
    mockProfile = { quizInsights: MOCK_CAREER_INSIGHTS };
    renderQuizInsights();
    await waitFor(() => screen.getByRole("button", { name: /back to assessments/i }));
    fireEvent.click(screen.getByRole("button", { name: /back to assessments/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/intelligence");
  });
});
