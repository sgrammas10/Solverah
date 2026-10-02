import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import GuestQuizPreview from "./GuestQuizPreview";
import * as guestQuiz from "../../../shared/lib/guestQuiz";

vi.mock("../../../shared/lib/guestQuiz", () => ({
  hasCompletedGuestQuiz: vi.fn(),
  getPendingQuizSave: vi.fn(),
  getGuestInsight: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(guestQuiz.hasCompletedGuestQuiz).mockReturnValue(false);
  vi.mocked(guestQuiz.getPendingQuizSave).mockReturnValue(null);
  vi.mocked(guestQuiz.getGuestInsight).mockReturnValue(null);
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
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Try a quiz before you sign up.");
  });

  it("shows 'Start quiz' links for each quiz card", () => {
    renderGuestQuizPreview();
    const startLinks = screen.getAllByRole("link", { name: /start quiz/i });
    expect(startLinks.length).toBeGreaterThanOrEqual(4);
  });

  it("offers Sign in beside Create account at the top", () => {
    renderGuestQuizPreview();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Create account" })).toHaveAttribute("href", "/register");
  });

  it("links each quiz to its own route", () => {
    renderGuestQuizPreview();
    expect(screen.getByRole("link", { name: "Start quiz: Early Career" })).toHaveAttribute(
      "href",
      "/quiz-preview/early-career",
    );
    expect(screen.getByRole("link", { name: /Start quiz: Your Future, Your Way/ })).toHaveAttribute(
      "href",
      "/quiz-preview/teen-focused",
    );
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

  it("locks every quiz row instead of offering Start quiz", () => {
    vi.mocked(guestQuiz.hasCompletedGuestQuiz).mockReturnValue(true);
    renderGuestQuizPreview();
    expect(screen.queryByRole("link", { name: /start quiz/i })).toBeNull();
    expect(screen.getAllByText("Sign in above to unlock")).toHaveLength(5);
  });

  it("keeps a single Sign in and a single Create account, at the top of the page", () => {
    vi.mocked(guestQuiz.hasCompletedGuestQuiz).mockReturnValue(true);
    renderGuestQuizPreview();
    // One of each: the rows no longer repeat the account actions.
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Create account" })).toHaveAttribute("href", "/register");
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

  // G20: the locked list was a dead end with no way back to the insight.
  it("links to the stored insight when there is one", () => {
    vi.mocked(guestQuiz.hasCompletedGuestQuiz).mockReturnValue(true);
    vi.mocked(guestQuiz.getGuestInsight).mockReturnValue({
      overallSummary: "S",
      insights: [{ title: "T", summary: "x" }],
    });
    renderGuestQuizPreview();
    expect(screen.getByRole("link", { name: /see your insight/i })).toHaveAttribute(
      "href",
      "/quiz-preview/insights",
    );
  });

  it("offers no insight link when nothing is stored", () => {
    vi.mocked(guestQuiz.hasCompletedGuestQuiz).mockReturnValue(true);
    renderGuestQuizPreview();
    expect(screen.queryByRole("link", { name: /see your insight/i })).toBeNull();
  });
});

// ─── styling guards ───────────────────────────────────────────────────────────

describe("GuestQuizPreview - landing style", () => {
  it("uses no uppercase eyebrow and no pill buttons", () => {
    renderGuestQuizPreview();
    expect(document.querySelector(".uppercase")).toBeNull();
    expect(document.querySelector(".rounded-full")).toBeNull();
  });
});
