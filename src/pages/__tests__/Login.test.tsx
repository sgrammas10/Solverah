import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Login from "../Login";
import { useAuth } from "../../contexts/useAuth";
import * as guestQuiz from "../../utils/guestQuiz";

vi.mock("../../contexts/useAuth");
vi.mock("../../components/HeroNetworkAnimation", () => ({ default: () => null }));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mockNavigate };
});

const mockFetch = vi.fn();
globalThis.fetch = mockFetch as any;

const mockLogin = vi.fn();
const mockFetchWithAuth = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue({
    login: mockLogin,
    fetchWithAuth: mockFetchWithAuth,
    user: null,
    register: vi.fn(),
    logout: vi.fn(),
    fetchProfile: vi.fn(),
    fetchProfileData: vi.fn(),
    saveProfileData: vi.fn(),
    updateProfile: vi.fn(),
    updateProfileData: vi.fn(),
  } as any);
  vi.spyOn(guestQuiz, "getPendingQuizSave").mockReturnValue(null);
  vi.spyOn(guestQuiz, "clearPendingQuizSave").mockImplementation(() => {});
});

function renderLogin() {
  render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>
  );
}

async function submitForm(email = "ada@example.com", password = "pass") {
  fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: email } });
  fireEvent.change(screen.getByLabelText(/password/i), { target: { value: password } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
  });
}

// ─── error states ─────────────────────────────────────────────────────────────

describe("Login - error handling", () => {
  it("shows a generic error when login fails", async () => {
    mockLogin.mockRejectedValueOnce(new Error("Invalid credentials"));
    renderLogin();
    await submitForm();
    expect(screen.getByText(/Failed to sign in/i)).toBeInTheDocument();
  });

  it("shows the email-not-confirmed message for that specific error", async () => {
    mockLogin.mockRejectedValueOnce(new Error("email not confirmed"));
    renderLogin();
    await submitForm();
    expect(screen.getByText(/email is not confirmed/i)).toBeInTheDocument();
  });

  it("shows the ResendConfirmation component on email-not-confirmed error", async () => {
    mockLogin.mockRejectedValueOnce(new Error("email not confirmed"));
    renderLogin();
    await submitForm();
    expect(screen.getByText(/Resend verification code/i)).toBeInTheDocument();
  });

  it("does not show ResendConfirmation on a generic error", async () => {
    mockLogin.mockRejectedValueOnce(new Error("wrong password"));
    renderLogin();
    await submitForm();
    expect(screen.queryByText(/Resend verification code/i)).toBeNull();
  });
});

// ─── role-based redirect ──────────────────────────────────────────────────────

describe("Login - role-based redirect", () => {
  it("navigates job-seeker to /job-seeker/dashboard", async () => {
    mockLogin.mockResolvedValueOnce({ role: "job-seeker", id: "1", email: "a@b.com", name: "A", profileComplete: false });
    renderLogin();
    await submitForm();
    expect(mockNavigate).toHaveBeenCalledWith("/job-seeker/dashboard");
  });

  it("navigates recruiter to /recruiter/dashboard", async () => {
    mockLogin.mockResolvedValueOnce({ role: "recruiter", id: "2", email: "r@b.com", name: "R", profileComplete: false });
    renderLogin();
    await submitForm();
    expect(mockNavigate).toHaveBeenCalledWith("/recruiter/dashboard");
  });
});

// ─── pending quiz save ────────────────────────────────────────────────────────

describe("Login - pending quiz save", () => {
  it("saves pending quiz results and redirects to quiz-insights", async () => {
    const pendingQuiz = {
      quizGroup: "next-chapter",
      quizResults: { q1: "a" },
      quizPayload: { answers: {} },
      createdAt: "2024-01-01T00:00:00.000Z",
    };
    vi.spyOn(guestQuiz, "getPendingQuizSave").mockReturnValue(pendingQuiz);
    mockLogin.mockResolvedValueOnce({ role: "job-seeker", id: "1", email: "a@b.com", name: "A", profileComplete: false });
    mockFetchWithAuth
      .mockResolvedValueOnce({})  // POST /profile
      .mockResolvedValueOnce({});  // POST /quiz-insights

    renderLogin();
    await submitForm();

    expect(mockFetchWithAuth).toHaveBeenCalledTimes(2);
    expect(mockNavigate).toHaveBeenCalledWith(
      `/quiz-insights?group=${encodeURIComponent("next-chapter")}`
    );
  });

  it("clears the pending quiz save after successfully saving", async () => {
    const pendingQuiz = {
      quizGroup: "next-chapter",
      quizResults: {},
      quizPayload: {},
      createdAt: "2024-01-01T00:00:00.000Z",
    };
    vi.spyOn(guestQuiz, "getPendingQuizSave").mockReturnValue(pendingQuiz);
    mockLogin.mockResolvedValueOnce({ role: "job-seeker", id: "1", email: "a@b.com", name: "A", profileComplete: false });
    mockFetchWithAuth.mockResolvedValue({});

    renderLogin();
    await submitForm();

    expect(guestQuiz.clearPendingQuizSave).toHaveBeenCalled();
  });

  it("still navigates to dashboard if pending quiz save fails", async () => {
    const pendingQuiz = {
      quizGroup: "next-chapter",
      quizResults: {},
      quizPayload: {},
      createdAt: "2024-01-01T00:00:00.000Z",
    };
    vi.spyOn(guestQuiz, "getPendingQuizSave").mockReturnValue(pendingQuiz);
    mockLogin.mockResolvedValueOnce({ role: "job-seeker", id: "1", email: "a@b.com", name: "A", profileComplete: false });
    mockFetchWithAuth.mockRejectedValue(new Error("save failed"));

    renderLogin();
    await submitForm();

    // Falls back to the normal job-seeker redirect
    expect(mockNavigate).toHaveBeenCalledWith("/job-seeker/dashboard");
  });
});

// ─── password visibility toggle ───────────────────────────────────────────────

describe("Login - password visibility", () => {
  it("password input starts as type=password", () => {
    renderLogin();
    expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("type", "password");
  });

  it("toggles to type=text when the show-password button is clicked", async () => {
    renderLogin();
    fireEvent.click(screen.getByRole("button", { name: /show password/i }));
    expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("type", "text");
  });

  it("toggles back to type=password on second click", async () => {
    renderLogin();
    const toggle = screen.getByRole("button", { name: /show password/i });
    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("button", { name: /hide password/i }));
    expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("type", "password");
  });
});

// ─── loading state ────────────────────────────────────────────────────────────

describe("Login - loading state", () => {
  it("disables the submit button and shows Signing in… while loading", async () => {
    let resolve!: (v: any) => void;
    mockLogin.mockReturnValueOnce(new Promise((r) => { resolve = r; }));

    renderLogin();
    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "a@b.com" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "pass" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /signing in/i })).toBeDisabled();
    });

    // Clean up
    await act(async () => { resolve({ role: "job-seeker", id: "1", email: "a@b.com", name: "A", profileComplete: false }); });
  });
});
