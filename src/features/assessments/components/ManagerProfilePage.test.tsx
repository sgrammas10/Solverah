/**
 * ManagerProfilePage.test.tsx — the page's gate and its phases, over a mocked
 * `useMP`, the real `useManagerPlaybook` query, and a real query client (the
 * submit mutation and the cache write it makes are exercised for real, per
 * FocusTypePage.test.tsx's precedent for a synchronous, non-job-backed
 * submit). `fetchWithAuth` is routed by path -- once the page's own gate
 * query fires alongside the submit mutation, "the next call" is no longer a
 * safe assumption, so `serve()` distinguishes `/me/manager-playbook` from
 * `/assessments/manager-profile` explicitly, per EnvironmentReportPage's
 * precedent for a page with more than one endpoint in play.
 */
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import ManagerProfilePage from "./ManagerProfilePage";
import { MP_QUESTIONS } from "../data/mpQuestions";
import { managerPlaybookKeys } from "../useManagerPlaybook";
import { createQueryClient } from "../../../shared/api/queryClient";
import { ApiError } from "../../../shared/api/apiError";

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

// ── gate fixtures ──────────────────────────────────────────────────────────────

type GateMode = "no_manager_match" | "no_manager_profile" | "success" | "error" | "pending";

const GATE_SUCCESS_DATA = {
  dimension_scores: { autonomy: 0.5, feedback_style: 0.5, relationship: 0.5, growth_focus: 0.5 },
  scoring_key: "mp-v1",
  version: "v1",
  playbook: { privacy_notice: "...", dimensions: [], priority: [], grind_count: 0, mesh_count: 4 },
};

function gateHandler(mode: GateMode): () => Promise<unknown> {
  switch (mode) {
    case "no_manager_match":
      return () =>
        Promise.reject(
          new ApiError("Take ManagerMatch first", {
            status: 409,
            fieldErrors: [{ field: "manager_match", code: "no_manager_match" }],
          })
        );
    case "no_manager_profile":
      return () =>
        Promise.reject(
          new ApiError("Profile your manager first", {
            status: 409,
            fieldErrors: [{ field: "manager_profile", code: "no_manager_profile" }],
          })
        );
    case "success":
      return () => Promise.resolve(GATE_SUCCESS_DATA);
    case "error":
      return () => Promise.reject(new ApiError("Forbidden", { status: 403 }));
    case "pending":
      return () => new Promise(() => {});
  }
}

const DEFAULT_SUBMIT_RESPONSE = {
  dimension_scores: { autonomy: 0.5, feedback_style: 0.5, relationship: 0.5, growth_focus: 0.5 },
  scoring_key: "mp-v1",
  version: "v1",
  playbook: null,
};

/** Route `fetchWithAuth` by path: the gate GET and the submit POST are
 *  independent calls now that the page runs both. */
function serve(gate: GateMode = "no_manager_profile", submit?: () => Promise<unknown>) {
  mocks.fetchWithAuth.mockImplementation((path: string) => {
    if (path === "/me/manager-playbook") return gateHandler(gate)();
    if (path === "/assessments/manager-profile") {
      return submit ? submit() : Promise.resolve(DEFAULT_SUBMIT_RESPONSE);
    }
    return Promise.reject(new Error(`unexpected path ${path}`));
  });
}

/** Answer all 16 forced choices, which is what triggers the submit. */
async function answerEveryQuestion() {
  fireEvent.click(await screen.findByRole("button", { name: /^Start$/i }));
  for (let i = 0; i < MP_QUESTIONS.length - 1; i++) {
    fireEvent.click(screen.getByText(MP_QUESTIONS[i].optionA));
  }
  await act(async () => {
    fireEvent.click(screen.getByText(MP_QUESTIONS[MP_QUESTIONS.length - 1].optionA));
  });
}

// ── gate ──────────────────────────────────────────────────────────────────────

describe("ManagerProfilePage - gate", () => {
  it("shows the hand-off when there is no completed ManagerMatch, and never submits", async () => {
    serve("no_manager_match");
    renderPage();

    expect(
      await screen.findByRole("heading", { name: /Take ManagerMatch first/i })
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Start$/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/Question 1 of/i)).not.toBeInTheDocument();

    const bodyText = document.body.textContent ?? "";
    expect(bodyText.toLowerCase()).not.toMatch(/unlock|locked/);

    fireEvent.click(screen.getByRole("button", { name: /take managermatch/i }));
    expect(mocks.navigate).toHaveBeenCalledWith("/manager-match");

    expect(mocks.fetchWithAuth).not.toHaveBeenCalledWith(
      "/assessments/manager-profile",
      expect.anything()
    );
  });

  it("shows the hand-off, not the mid-quiz question, for a blocked user with a partial draft", async () => {
    mocks.mpAnswers = MP_QUESTIONS.slice(0, 8).map((q) => ({ questionId: q.id, choice: "a" as const }));
    serve("no_manager_match");
    renderPage();

    expect(
      await screen.findByRole("heading", { name: /Take ManagerMatch first/i })
    ).toBeInTheDocument();
    expect(screen.queryByText(/Question 9 of/i)).not.toBeInTheDocument();
  });

  it("shows the hand-off and never auto-submits a complete draft while blocked", async () => {
    mocks.mpAnswers = MP_QUESTIONS.map((q) => ({ questionId: q.id, choice: "a" as const }));
    serve("no_manager_match");
    renderPage();

    expect(
      await screen.findByRole("heading", { name: /Take ManagerMatch first/i })
    ).toBeInTheDocument();
    expect(mocks.fetchWithAuth).not.toHaveBeenCalledWith(
      "/assessments/manager-profile",
      expect.anything()
    );
  });

  it("renders the intro as usual when ManagerMatch is done but no profile is sitting yet", async () => {
    serve("no_manager_profile");
    renderPage();

    expect(
      await screen.findByRole("heading", { name: /Profile your actual manager/i })
    ).toBeInTheDocument();
  });

  it("renders the intro (retake) when a playbook already exists", async () => {
    serve("success");
    renderPage();

    expect(
      await screen.findByRole("heading", { name: /Profile your actual manager/i })
    ).toBeInTheDocument();
  });

  it("shows an error card with retry, not the form, on an unrelated gate failure, and retry re-fetches", async () => {
    serve("error");
    renderPage();

    expect(
      await screen.findByText(/couldn't load your manager profile status/i)
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Start$/i })).not.toBeInTheDocument();

    serve("no_manager_profile");
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    expect(
      await screen.findByRole("heading", { name: /Profile your actual manager/i })
    ).toBeInTheDocument();
  });

  it("renders nothing from the intro while the gate is pending", () => {
    serve("pending");
    renderPage();

    expect(
      screen.queryByRole("heading", { name: /Profile your actual manager/i })
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Start$/i })).not.toBeInTheDocument();
    expect(screen.getByText(/Loading/i)).toBeInTheDocument();
  });
});

// ── intro phase ───────────────────────────────────────────────────────────────

describe("ManagerProfilePage - intro phase", () => {
  it("renders intro screen with disclaimer text visible", async () => {
    serve();
    renderPage();
    expect(
      await screen.findByRole("heading", { name: /Profile your actual manager/i })
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Each choice is final — there is no going back/i)
    ).toBeInTheDocument();
  });

  it("clicking Start renders the first question with both option cards", async () => {
    serve();
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /^Start$/i }));
    expect(screen.getByText(MP_QUESTIONS[0].optionA)).toBeInTheDocument();
    expect(screen.getByText(MP_QUESTIONS[0].optionB)).toBeInTheDocument();
  });

  it(`shows 'Question 1 of ${MP_QUESTIONS.length}' indicator after starting`, async () => {
    serve();
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /^Start$/i }));
    expect(screen.getByText(new RegExp(`Question 1 of ${MP_QUESTIONS.length}`, "i"))).toBeInTheDocument();
  });
});

// ── questions phase ───────────────────────────────────────────────────────────

describe("ManagerProfilePage - questions phase", () => {
  it("clicking an option card on question 1 advances to question 2", async () => {
    serve();
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /^Start$/i }));
    fireEvent.click(screen.getByText(MP_QUESTIONS[0].optionA));
    expect(screen.getByText(new RegExp(`Question 2 of ${MP_QUESTIONS.length}`, "i"))).toBeInTheDocument();
    expect(screen.getByText(MP_QUESTIONS[1].optionA)).toBeInTheDocument();
  });

  it("calls setAnswer with the authored option identity when an option is selected", async () => {
    serve();
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /^Start$/i }));
    fireEvent.click(screen.getByText(MP_QUESTIONS[0].optionB));
    expect(mocks.setAnswer).toHaveBeenCalledWith("mp-q1", "b");
  });
});

// ── submitting (pending) phase ────────────────────────────────────────────────

describe("ManagerProfilePage - submitting phase", () => {
  it("submits once, in the request's documented body shape, after the last answer", async () => {
    serve("no_manager_profile", () => new Promise(() => {})); // never resolves
    renderPage();
    await answerEveryQuestion();

    await waitFor(() =>
      expect(screen.getByText(/Scoring your manager profile/i)).toBeInTheDocument()
    );
    const submitCalls = mocks.fetchWithAuth.mock.calls.filter(
      ([path]) => path === "/assessments/manager-profile"
    );
    expect(submitCalls).toHaveLength(1);
    const [url, init] = submitCalls[0];
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
    serve("no_manager_profile", () =>
      Promise.resolve({
        dimension_scores: { autonomy: 0.5, feedback_style: 0.5, relationship: 0.5, growth_focus: 0.5 },
        scoring_key: "mp-v1",
        version: "v1",
        playbook: mockPlaybook,
      })
    );
    renderPage();
    await answerEveryQuestion();

    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith("/manager-profile/playbook"));
    expect(queryClient.getQueryData(managerPlaybookKeys.result())).toMatchObject({
      playbook: mockPlaybook,
    });
    expect(mocks.reset).toHaveBeenCalled();
  });

  it("navigates to /manager-profile/playbook without caching anything when playbook is null", async () => {
    serve("no_manager_profile", () =>
      Promise.resolve({
        dimension_scores: { autonomy: 0.5, feedback_style: 0.5, relationship: 0.5, growth_focus: 0.5 },
        scoring_key: "mp-v1",
        version: "v1",
        playbook: null,
      })
    );
    renderPage();
    await answerEveryQuestion();

    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith("/manager-profile/playbook"));
    expect(queryClient.getQueryData(managerPlaybookKeys.result())).toBeUndefined();
  });
});

// ── error phase ────────────────────────────────────────────────────────────────

describe("ManagerProfilePage - error phase", () => {
  it("shows error UI when submission fails", async () => {
    serve("no_manager_profile", () => Promise.reject(new Error("API error")));
    renderPage();
    await answerEveryQuestion();

    await waitFor(() =>
      expect(screen.getByText(/Something went wrong submitting your answers/i)).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("try again re-submits and navigates on success", async () => {
    const mockPlaybook = { privacy_notice: "...", dimensions: [], priority: [], grind_count: 0, mesh_count: 4 };
    let submitAttempt = 0;
    serve("no_manager_profile", () => {
      submitAttempt += 1;
      if (submitAttempt === 1) return Promise.reject(new Error("first failure"));
      return Promise.resolve({
        dimension_scores: {},
        scoring_key: "mp-v1",
        version: "v1",
        playbook: mockPlaybook,
      });
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
  it("with location.state = { retake: true }, reset() is called once the gate resolves", async () => {
    serve("success");
    renderPage({ retake: true });
    await waitFor(() => expect(mocks.reset).toHaveBeenCalledTimes(1));
  });

  it("retake shows the intro screen", async () => {
    serve("success");
    renderPage({ retake: true });
    expect(
      await screen.findByRole("heading", { name: /Profile your actual manager/i })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Start$/i })).toBeInTheDocument();
  });
});
