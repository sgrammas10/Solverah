import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ManagerMatchPage from "../ManagerMatchPage";
import { MM_QUESTIONS } from "../../data/mmQuestions";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  fetchWithAuth: vi.fn(),
  reset: vi.fn(),
  setAnswer: vi.fn(),
  setCachedResult: vi.fn(),
  mmState: { answers: [] as any[], cachedResult: null as any },
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../contexts/useAuth", () => ({
  useAuth: () => ({
    fetchWithAuth: mocks.fetchWithAuth,
  }),
}));

vi.mock("../../hooks/useMM", () => ({
  useMM: () => ({
    state: mocks.mmState,
    setAnswer: mocks.setAnswer,
    setCachedResult: mocks.setCachedResult,
    reset: mocks.reset,
  }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.mmState = { answers: [], cachedResult: null };
});

function renderPage(locationState?: object) {
  render(
    <MemoryRouter initialEntries={[{ pathname: "/manager-match", state: locationState }]}>
      <ManagerMatchPage />
    </MemoryRouter>
  );
}

// ── intro phase ───────────────────────────────────────────────────────────────

describe("ManagerMatchPage - intro phase", () => {
  it("renders intro screen with disclaimer text visible", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: "ManagerMatch™" })).toBeInTheDocument();
    expect(
      screen.getByText(/Each choice is final — there is no going back/i)
    ).toBeInTheDocument();
  });

  it("clicking 'Start ManagerMatch™' renders the first question with both option cards", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Start ManagerMatch™/i }));
    expect(screen.getByText(MM_QUESTIONS[0].optionA)).toBeInTheDocument();
    expect(screen.getByText(MM_QUESTIONS[0].optionB)).toBeInTheDocument();
  });

  it("shows 'Question 1 of 15' indicator after starting", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Start ManagerMatch™/i }));
    expect(screen.getByText(/Question 1 of 15/i)).toBeInTheDocument();
  });
});

// ── questions phase ───────────────────────────────────────────────────────────

describe("ManagerMatchPage - questions phase", () => {
  it("clicking an option card on question 1 advances to question 2", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Start ManagerMatch™/i }));
    fireEvent.click(screen.getByText(MM_QUESTIONS[0].optionA));
    expect(screen.getByText(/Question 2 of 15/i)).toBeInTheDocument();
    expect(screen.getByText(MM_QUESTIONS[1].optionA)).toBeInTheDocument();
  });

  it("calls setAnswer when an option is selected", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Start ManagerMatch™/i }));
    fireEvent.click(screen.getByText(MM_QUESTIONS[0].optionA));
    expect(mocks.setAnswer).toHaveBeenCalledWith("mm-q1", "a");
  });
});

// ── submitting phase ──────────────────────────────────────────────────────────

describe("ManagerMatchPage - submitting phase", () => {
  it("after all 15 answers fetchWithAuth is called once with correct payload shape", async () => {
    mocks.fetchWithAuth.mockReturnValue(new Promise(() => {}));
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Start ManagerMatch™/i }));

    for (let i = 0; i < 14; i++) {
      fireEvent.click(screen.getByText(MM_QUESTIONS[i].optionA));
    }
    await act(async () => {
      fireEvent.click(screen.getByText(MM_QUESTIONS[14].optionA));
    });

    await waitFor(() =>
      expect(screen.getByText(/Analysing your management preferences/i)).toBeInTheDocument()
    );

    expect(mocks.fetchWithAuth).toHaveBeenCalledTimes(1);
    const [, options] = mocks.fetchWithAuth.mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body.answers).toHaveLength(15);
    expect(body.answers[0]).toMatchObject({ question_id: expect.any(String), choice: expect.stringMatching(/^[ab]$/) });
  });

  it("navigates to /manager-match/results on successful submission", async () => {
    const mockResult = {
      archetype: "The Autonomist",
      dimension_scores: {},
      narrative: "...",
      what_to_look_for: [],
      red_flags: [],
      archetype_description: "...",
    };
    mocks.fetchWithAuth.mockResolvedValueOnce(mockResult);
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Start ManagerMatch™/i }));

    for (let i = 0; i < 14; i++) {
      fireEvent.click(screen.getByText(MM_QUESTIONS[i].optionA));
    }
    await act(async () => {
      fireEvent.click(screen.getByText(MM_QUESTIONS[14].optionA));
    });

    await waitFor(() =>
      expect(mocks.navigate).toHaveBeenCalledWith('/manager-match/results')
    );
  });
});

// ── error phase ───────────────────────────────────────────────────────────────

describe("ManagerMatchPage - error phase", () => {
  it("when fetchWithAuth rejects, the error phase renders with a retry button", async () => {
    mocks.fetchWithAuth.mockRejectedValueOnce(new Error("API error"));
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Start ManagerMatch™/i }));

    for (let i = 0; i < 14; i++) {
      fireEvent.click(screen.getByText(MM_QUESTIONS[i].optionA));
    }
    await act(async () => {
      fireEvent.click(screen.getByText(MM_QUESTIONS[14].optionA));
    });

    await waitFor(() =>
      expect(screen.getByText(/We couldn't generate your results right now/i)).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});

// ── retake flow ───────────────────────────────────────────────────────────────

describe("ManagerMatchPage - retake flow", () => {
  it("with location.state = { retake: true }, reset() is called on mount", () => {
    renderPage({ retake: true });
    expect(mocks.reset).toHaveBeenCalledTimes(1);
  });

  it("retake shows the intro screen", () => {
    renderPage({ retake: true });
    expect(screen.getByRole("heading", { name: "ManagerMatch™" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Start ManagerMatch™/i })).toBeInTheDocument();
  });
});
