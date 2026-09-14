/**
 * ManagerProfilePage.test.tsx — the page's phases, over a mocked `useMP` and a
 * real query client (the submit mutation and the cache write it makes are
 * exercised for real, per FocusTypePage.test.tsx's precedent for a
 * synchronous, non-job-backed submit).
 */
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import ManagerProfilePage from "./ManagerProfilePage";
import { MP_QUESTIONS } from "../data/mpQuestions";
import { managerPlaybookKeys } from "../useManagerPlaybook";
import { createQueryClient } from "../../../shared/api/queryClient";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  reset: vi.fn(),
  setAnswer: vi.fn(),
  fetchWithAuth: vi.fn(),
  mpAnswers: [] as any[],
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../useMP", () => ({
  useMP: () => ({
    answers: mocks.mpAnswers,
    setAnswer: mocks.setAnswer,
    reset: mocks.reset,
  }),
}));

vi.mock("../../auth/useAuth", () => ({
  useAuth: () => ({ fetchWithAuth: mocks.fetchWithAuth }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.mpAnswers = [];
});

let queryClient: QueryClient;

function renderPage(locationState?: object) {
  queryClient = createQueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[{ pathname: "/manager-profile", state: locationState }]}>
        <ManagerProfilePage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

/** Answer all 16 forced choices, which is what triggers the submit. */
async function answerEveryQuestion() {
  fireEvent.click(screen.getByRole("button", { name: /^Start$/i }));
  for (let i = 0; i < MP_QUESTIONS.length - 1; i++) {
    fireEvent.click(screen.getByText(MP_QUESTIONS[i].optionA));
  }
  await act(async () => {
    fireEvent.click(screen.getByText(MP_QUESTIONS[MP_QUESTIONS.length - 1].optionA));
  });
}

// ── intro phase ───────────────────────────────────────────────────────────────

describe("ManagerProfilePage - intro phase", () => {
  it("renders intro screen with disclaimer text visible", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: /Profile your actual manager/i })).toBeInTheDocument();
    expect(
      screen.getByText(/Each choice is final — there is no going back/i)
    ).toBeInTheDocument();
  });

  it("clicking Start renders the first question with both option cards", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /^Start$/i }));
    expect(screen.getByText(MP_QUESTIONS[0].optionA)).toBeInTheDocument();
    expect(screen.getByText(MP_QUESTIONS[0].optionB)).toBeInTheDocument();
  });

  it(`shows 'Question 1 of ${MP_QUESTIONS.length}' indicator after starting`, () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /^Start$/i }));
    expect(screen.getByText(new RegExp(`Question 1 of ${MP_QUESTIONS.length}`, "i"))).toBeInTheDocument();
  });
});

// ── questions phase ───────────────────────────────────────────────────────────

describe("ManagerProfilePage - questions phase", () => {
  it("clicking an option card on question 1 advances to question 2", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /^Start$/i }));
    fireEvent.click(screen.getByText(MP_QUESTIONS[0].optionA));
    expect(screen.getByText(new RegExp(`Question 2 of ${MP_QUESTIONS.length}`, "i"))).toBeInTheDocument();
    expect(screen.getByText(MP_QUESTIONS[1].optionA)).toBeInTheDocument();
  });

  it("calls setAnswer with the authored option identity when an option is selected", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /^Start$/i }));
    fireEvent.click(screen.getByText(MP_QUESTIONS[0].optionB));
    expect(mocks.setAnswer).toHaveBeenCalledWith("mp-q1", "b");
  });
});

// ── submitting (pending) phase ────────────────────────────────────────────────

describe("ManagerProfilePage - submitting phase", () => {
  it("submits once, in the request's documented body shape, after the last answer", async () => {
    mocks.fetchWithAuth.mockReturnValue(new Promise(() => {})); // never resolves
    renderPage();
    await answerEveryQuestion();

    await waitFor(() =>
      expect(screen.getByText(/Scoring your manager profile/i)).toBeInTheDocument()
    );
    expect(mocks.fetchWithAuth).toHaveBeenCalledTimes(1);
    const [url, init] = mocks.fetchWithAuth.mock.calls[0];
    expect(url).toBe("/assessments/manager-profile");
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body);
    expect(body.answers).toHaveLength(MP_QUESTIONS.length);
    expect(body.answers[0]).toMatchObject({
      question_id: expect.any(String),
      choice: expect.stringMatching(/^[ab]$/),
    });
  });

  it("navigates to /manager-profile/playbook and caches a non-null playbook", async () => {
    const mockPlaybook = { privacy_notice: "...", dimensions: [], priority: [], grind_count: 0, mesh_count: 4 };
    mocks.fetchWithAuth.mockResolvedValueOnce({
      dimension_scores: { autonomy: 0.5, feedback_style: 0.5, relationship: 0.5, growth_focus: 0.5 },
      scoring_key: "mp-v1",
      version: "v1",
      playbook: mockPlaybook,
    });
    renderPage();
    await answerEveryQuestion();

    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith("/manager-profile/playbook"));
    expect(queryClient.getQueryData(managerPlaybookKeys.result())).toMatchObject({
      playbook: mockPlaybook,
    });
    expect(mocks.reset).toHaveBeenCalled();
  });

  it("navigates to /manager-profile/playbook without caching anything when playbook is null", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce({
      dimension_scores: { autonomy: 0.5, feedback_style: 0.5, relationship: 0.5, growth_focus: 0.5 },
      scoring_key: "mp-v1",
      version: "v1",
      playbook: null,
    });
    renderPage();
    await answerEveryQuestion();

    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith("/manager-profile/playbook"));
    expect(queryClient.getQueryData(managerPlaybookKeys.result())).toBeUndefined();
  });
});

// ── error phase ────────────────────────────────────────────────────────────────

describe("ManagerProfilePage - error phase", () => {
  it("shows error UI when submission fails", async () => {
    mocks.fetchWithAuth.mockRejectedValueOnce(new Error("API error"));
    renderPage();
    await answerEveryQuestion();

    await waitFor(() =>
      expect(screen.getByText(/Something went wrong submitting your answers/i)).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("try again re-submits and navigates on success", async () => {
    const mockPlaybook = { privacy_notice: "...", dimensions: [], priority: [], grind_count: 0, mesh_count: 4 };
    mocks.fetchWithAuth
      .mockRejectedValueOnce(new Error("first failure"))
      .mockResolvedValueOnce({
        dimension_scores: {},
        scoring_key: "mp-v1",
        version: "v1",
        playbook: mockPlaybook,
      });
    renderPage();
    await answerEveryQuestion();

    await waitFor(() => screen.getByRole("button", { name: /try again/i }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    });

    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith("/manager-profile/playbook"));
  });
});

// ── retake flow ───────────────────────────────────────────────────────────────

describe("ManagerProfilePage - retake flow", () => {
  it("with location.state = { retake: true }, reset() is called on mount", () => {
    renderPage({ retake: true });
    expect(mocks.reset).toHaveBeenCalledTimes(1);
  });

  it("retake shows the intro screen", () => {
    renderPage({ retake: true });
    expect(screen.getByRole("heading", { name: /Profile your actual manager/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Start$/i })).toBeInTheDocument();
  });
});
