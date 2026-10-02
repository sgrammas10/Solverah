/**
 * NextChapterYourWayQuiz.test.tsx — Career & Job Search, the stand-alone quiz
 * whose storage and read paths disagreed (2026-10-02 audit #7 / G16): signed-in
 * insights were written under careerQuizzes.careerJobSearch and read from a
 * flat quizInsights.careerJobSearch, and the guest preview named its own flat
 * group. One home now: the career group.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { HttpResponse } from "msw";

import NextChapterYourWayQuiz from "./NextChapterYourWayQuiz";
import { createQueryClient } from "../../../shared/api/queryClient";
import { getPendingQuizSave, hasCompletedGuestQuiz } from "../../../shared/lib/guestQuiz";
import { apiServer, useApiMocks } from "../../../../tests/msw/server";
import { mock } from "../../../../tests/msw/contract";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
  fetchProfileData: vi.fn(),
  saveProfileData: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});
vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth }),
}));
vi.mock("../../profile/useProfileActions", () => ({
  useProfileActions: () => ({
    fetchProfileData: mocks.fetchProfileData,
    saveProfileData: mocks.saveProfileData,
  }),
}));

useApiMocks();

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

function renderQuiz(guest?: boolean) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <NextChapterYourWayQuiz guest={guest} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("NextChapterYourWayQuiz - guest", () => {
  it("cannot submit with no answers", () => {
    renderQuiz(true);
    expect(screen.getByRole("button", { name: "Get Insight" })).toBeDisabled();
  });

  it("posts into the career group and stores only after success", async () => {
    let requestBody: any;
    apiServer.use(
      mock("post", "/api/v1/intake/quiz-preview/insights").resolve(async ({ request }) => {
        requestBody = await request.json();
        return HttpResponse.json({
          quizGroup: "careerQuizzes",
          overallSummary: "S",
          insights: [{ key: "careerJobSearch", title: "Career & Job Search", summary: "CJS." }],
        });
      }),
    );
    renderQuiz(true);
    fireEvent.click(screen.getAllByRole("radio")[0]);
    expect(hasCompletedGuestQuiz()).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Get Insight" }));

    await waitFor(() => expect(screen.getByText(/your insights are ready/i)).toBeInTheDocument());
    expect(requestBody.quizGroup).toBe("careerQuizzes");
    expect(requestBody.quizzes[0].key).toBe("careerJobSearch");
    expect(hasCompletedGuestQuiz()).toBe(true);
    expect(getPendingQuizSave()?.quizGroup).toBe("careerQuizzes");
  });
});

describe("NextChapterYourWayQuiz - signed in", () => {
  it("preloads the insight stored under careerQuizzes.careerJobSearch", async () => {
    mocks.fetchProfileData.mockResolvedValue({
      profileData: {
        quizResults: { careerJobSearch: { 1: 0 } },
        quizInsights: {
          careerQuizzes: {
            careerJobSearch: { title: "Career & Job Search", summary: "Nested." },
            _overallInsight: { summary: "All of them." },
          },
        },
      },
    });
    renderQuiz();
    await waitFor(() => expect(screen.getByRole("button", { name: "View Insight" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "View Insight" }));
    const [, options] = mocks.navigate.mock.calls[0];
    expect(options.state.insight.insights[0].summary).toBe("Nested.");
    expect(options.state.insight.overallInsight.summary).toBe("All of them.");
  });

  it("posts every saved quiz with the response's overallInsight, not overallSummary", async () => {
    mocks.fetchProfileData.mockResolvedValue({
      profileData: { quizResults: { careerQuizzes: { earlyCareer: { 1: 0 } } } },
    });
    mocks.saveProfileData.mockResolvedValue({ profileData: {} });
    mocks.fetchWithAuth.mockResolvedValue({
      quizGroup: "careerQuizzes",
      overallInsight: { summary: "Across both." },
      insights: [{ key: "careerJobSearch", title: "CJS", summary: "x" }],
    });
    renderQuiz();
    await waitFor(() => expect(screen.getByRole("button", { name: "Save Answers" })).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole("radio")[0]);
    fireEvent.click(screen.getByRole("button", { name: "Save Answers" }));

    await waitFor(() => expect(mocks.fetchWithAuth).toHaveBeenCalled());
    const body = JSON.parse(mocks.fetchWithAuth.mock.calls[0][1].body);
    expect(body.quizzes.map((q: { key: string }) => q.key)).toEqual(["earlyCareer", "careerJobSearch"]);

    await waitFor(() => expect(screen.getByText(/your insights are ready/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "View insights" }));
    const [, options] = mocks.navigate.mock.calls[0];
    expect(options.state.insight.overallInsight.summary).toBe("Across both.");
  });
});
