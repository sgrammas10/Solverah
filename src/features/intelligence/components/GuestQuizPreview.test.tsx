import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import GuestQuizPreview from "./GuestQuizPreview";
import * as guestQuiz from "../../../shared/lib/guestQuiz";

vi.mock("../../../shared/lib/guestQuiz", () => ({
  hasCompletedGuestQuiz: vi.fn(),
  getPendingQuizSave: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(guestQuiz.hasCompletedGuestQuiz).mockReturnValue(false);
  vi.mocked(guestQuiz.getPendingQuizSave).mockReturnValue(null);
});

function renderGuestQuizPreview() {
  render(
    <MemoryRouter>
      <GuestQuizPreview />
    </MemoryRouter>
  );
}

// ─── happy path ────────────────────────────────────────────────────────────────

describe("GuestQuizPreview - happy path", () => {
  it("renders the page heading", () => {
    renderGuestQuizPreview();
    expect(screen.getByText(/Get a feel for what Solverah delivers/i)).toBeInTheDocument();
  });

  it("shows 'Start quiz' links for each quiz card", () => {
    renderGuestQuizPreview();
    const startLinks = screen.getAllByRole("link", { name: /start quiz/i });
    expect(startLinks.length).toBeGreaterThanOrEqual(4);
  });

  it("does not show the locked-out message", () => {
    renderGuestQuizPreview();
    expect(screen.queryByText(/already taken a guest quiz/i)).toBeNull();
  });

  it("renders all quiz card titles", () => {
    renderGuestQuizPreview();
    expect(screen.getByText("Early Career")).toBeInTheDocument();
    expect(screen.getByText("Career Transition")).toBeInTheDocument();
    expect(screen.getByText("Mid-Career / Strategic")).toBeInTheDocument();
    expect(screen.getByText(/Your Future, Your Way/i)).toBeInTheDocument();
  });
});

// ─── locked state ─────────────────────────────────────────────────────────────

describe("GuestQuizPreview - locked state (completed quiz)", () => {
  it("shows locked message when guest quiz has been completed", () => {
    vi.mocked(guestQuiz.hasCompletedGuestQuiz).mockReturnValue(true);
    renderGuestQuizPreview();
    expect(screen.getByText(/already taken a guest quiz/i)).toBeInTheDocument();
  });

  it("shows Sign in and Create account buttons instead of Start quiz", () => {
    vi.mocked(guestQuiz.hasCompletedGuestQuiz).mockReturnValue(true);
    renderGuestQuizPreview();
    expect(screen.getAllByRole("link", { name: /sign in/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /create account/i }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: /start quiz/i })).toBeNull();
  });

  it("shows locked message when pending quiz save exists", () => {
    vi.mocked(guestQuiz.getPendingQuizSave).mockReturnValue({
      quizGroup: "early-career",
      quizResults: {},
      quizPayload: {},
      createdAt: "2024-01-01T00:00:00.000Z",
    });
    renderGuestQuizPreview();
    expect(screen.getByText(/already taken a guest quiz/i)).toBeInTheDocument();
  });
});
