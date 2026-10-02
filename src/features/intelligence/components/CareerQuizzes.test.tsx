/**
 * CareerQuizzes.test.tsx — the submit paths the 2026-10-02 audit found broken.
 *
 *   - #2 guest lockout: the lockout and the pending save were written before
 *     the insight call, so a failed call (or an empty submit) locked the guest
 *     out with nothing to show.
 *   - #6 a signed-in post must carry every saved quiz, so the combined insight
 *     really covers all of them.
 *   - #8 the profile cache is invalidated after the signed-in POST.
 *   - #14 failures are inline, not alert().
 *   - G19 the guest "Back" on an unknown quiz goes to the public quiz list.
 *
 * The guest call goes over the (MSW) network; the signed-in transport is the
 * mocked useAuth, like every other page test here.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { HttpResponse } from "msw";

import CareerQuizzes from "./CareerQuizzes";
import { createQueryClient } from "../../../shared/api/queryClient";
import { profileKeys } from "../../profile";
import { getGuestInsight, getPendingQuizSave, hasCompletedGuestQuiz } from "../../../shared/lib/guestQuiz";
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

const INSIGHT_BODY = {
  quizGroup: "careerQuizzes",
  overallSummary: "Guest summary.",
  insights: [{ key: "earlyCareer", title: "Quiz 1: Early Career", summary: "Guest insight." }],
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

function renderQuiz(props: { quizKey?: string; guest?: boolean }, queryClient = createQueryClient()) {
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CareerQuizzes {...props} />
      </MemoryRouter>
    </QueryClientProvider>
  );
  return queryClient;
}

const answerFirstQuestion = () => fireEvent.click(screen.getAllByRole("radio")[0]);

describe("CareerQuizzes - guest", () => {
  it("cannot submit with no answers", () => {
    renderQuiz({ quizKey: "earlyCareer", guest: true });
    expect(screen.getByRole("button", { name: "Get Insight" })).toBeDisabled();
  });

  it("locks out and stores the save only after a successful insight", async () => {
    let requestBody: any;
    apiServer.use(
      mock("post", "/api/v1/intake/quiz-preview/insights").resolve(async ({ request }) => {
        requestBody = await request.json();
        return HttpResponse.json(INSIGHT_BODY);
      }),
    );
    renderQuiz({ quizKey: "earlyCareer", guest: true });
    answerFirstQuestion();
    fireEvent.click(screen.getByRole("button", { name: "Get Insight" }));

    await waitFor(() => expect(screen.getByText(/your insights are ready/i)).toBeInTheDocument());
    expect(requestBody.quizGroup).toBe("careerQuizzes");
    expect(requestBody.quizzes).toHaveLength(1);
    expect(requestBody.quizzes[0].items).toHaveLength(1);
    expect(hasCompletedGuestQuiz()).toBe(true);
    expect(getPendingQuizSave()?.quizResults).toMatchObject({
      careerQuizzes: { earlyCareer: { 1: 0 } },
    });
    expect(getGuestInsight()?.insights?.[0].summary).toBe("Guest insight.");
  });

  it("a failed insight does not lock the guest out or store anything", async () => {
    apiServer.use(
      mock("post", "/api/v1/intake/quiz-preview/insights").reply(500, {
        error: "We couldn't generate your insight right now. Please try again in a moment.",
        code: "insight_generation_failed",
      }),
    );
    renderQuiz({ quizKey: "earlyCareer", guest: true });
    answerFirstQuestion();
    fireEvent.click(screen.getByRole("button", { name: "Get Insight" }));

    await waitFor(() => expect(screen.getByText(/couldn't generate your insight/i)).toBeInTheDocument());
    expect(hasCompletedGuestQuiz()).toBe(false);
    expect(getPendingQuizSave()).toBeNull();
  });

  it("G19: an unknown quiz sends a guest back to the public quiz list", () => {
    renderQuiz({ quizKey: "noSuchQuiz", guest: true });
    fireEvent.click(screen.getByRole("button", { name: "Back to quizzes" }));
    expect(mocks.navigate).toHaveBeenCalledWith("/quiz-preview");
  });

  it("an unknown quiz still sends a signed-in user to /intelligence", () => {
    mocks.fetchProfileData.mockResolvedValue({ profileData: {} });
    renderQuiz({ quizKey: "noSuchQuiz" });
    fireEvent.click(screen.getByRole("button", { name: "Back to Assessments" }));
    expect(mocks.navigate).toHaveBeenCalledWith("/intelligence");
  });
});

describe("CareerQuizzes - signed in", () => {
  const STORED = {
    quizResults: {
      careerQuizzes: { midCareer: { 1: 2 } },
      careerJobSearch: { 1: 1 },
      yourFutureYourWay: { 2: 3 },
    },
  };

  it("posts every saved quiz, merges the career map, and invalidates the profile", async () => {
    mocks.fetchProfileData.mockResolvedValue({ profileData: STORED });
    mocks.saveProfileData.mockResolvedValue({ profileData: {} });
    mocks.fetchWithAuth.mockResolvedValue({ quizGroup: "careerQuizzes", overallInsight: null, insights: [] });

    const queryClient = createQueryClient();
    queryClient.setQueryData(profileKeys.document(), STORED);
    renderQuiz({ quizKey: "earlyCareer" }, queryClient);

    await waitFor(() => expect(screen.getByRole("button", { name: "Save Answers" })).toBeInTheDocument());
    answerFirstQuestion();
    fireEvent.click(screen.getByRole("button", { name: "Save Answers" }));

    await waitFor(() => expect(mocks.fetchWithAuth).toHaveBeenCalled());
    // Only the quizResults slice is written, with the career map merged.
    expect(mocks.saveProfileData).toHaveBeenCalledWith({
      quizResults: expect.objectContaining({
        careerQuizzes: { midCareer: { 1: 2 }, earlyCareer: { 1: 0 } },
      }),
    });
    const [path, init] = mocks.fetchWithAuth.mock.calls[0];
    expect(path).toBe("/me/quiz-insights");
    const body = JSON.parse(init.body);
    expect(body.quizGroup).toBe("careerQuizzes");
    expect(body.quizzes.map((q: { key: string }) => q.key)).toEqual([
      "earlyCareer",
      "midCareer",
      "careerJobSearch",
      "yourFutureYourWay",
    ]);
    await waitFor(() =>
      expect(queryClient.getQueryState(profileKeys.document())?.isInvalidated).toBe(true),
    );
  });

  it("shows a failed save inline instead of alert()", async () => {
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    mocks.fetchProfileData.mockResolvedValue({ profileData: {} });
    mocks.saveProfileData.mockRejectedValue(new Error("Network down"));
    renderQuiz({ quizKey: "earlyCareer" });

    await waitFor(() => expect(screen.getByRole("button", { name: "Save Answers" })).toBeInTheDocument());
    answerFirstQuestion();
    fireEvent.click(screen.getByRole("button", { name: "Save Answers" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Network down"));
    expect(alertSpy).not.toHaveBeenCalled();
    expect(mocks.fetchWithAuth).not.toHaveBeenCalled();
    alertSpy.mockRestore();
  });

  it("preloads a stored insight from the nested career entry", async () => {
    mocks.fetchProfileData.mockResolvedValue({
      profileData: {
        quizResults: { careerQuizzes: { earlyCareer: { 1: 0 } } },
        quizInsights: { careerQuizzes: { earlyCareer: { title: "Early", summary: "Stored." } } },
      },
    });
    renderQuiz({ quizKey: "earlyCareer" });
    await waitFor(() => expect(screen.getByRole("button", { name: "View Insight" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "View Insight" }));
    expect(mocks.navigate).toHaveBeenCalledWith(
      "/quiz-insights?group=careerQuizzes",
      expect.objectContaining({ state: { insight: expect.objectContaining({ insights: [expect.objectContaining({ summary: "Stored." })] }) } }),
    );
  });
});
