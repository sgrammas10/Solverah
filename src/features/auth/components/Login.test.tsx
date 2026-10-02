import { render, screen, fireEvent, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import Login from "./Login";
import { useAuth } from "../useAuth";
import * as guestQuiz from "../../../shared/lib/guestQuiz";
import { createQueryClient } from "../../../shared/api/queryClient";
import { ApiError } from "../../../shared/api/apiError";
import { profileKeys } from "../../profile";
import { useApiMocks } from "../../../../tests/msw/server";

vi.mock("../useAuth");
vi.mock("../../../shared/ui/HeroNetworkAnimation", () => ({ default: () => null }));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mockNavigate };
});

/**
 * This page's collaborators are all mocked at the module level -- `useAuth`
 * supplies both `login` and `fetchWithAuth` -- so nothing here is expected to
 * reach the network at all.
 *
 * There used to be a `globalThis.fetch = vi.fn()` here to make sure of that. It
 * was never asserted on, and it could not have been: a stray request would have
 * been swallowed by the stub and returned `undefined`, failing somewhere else
 * with an unrelated message. `useApiMocks()` inverts that -- unhandled requests
 * are errors, so a call escaping the mocked `useAuth` fails this file, by name,
 * at the point it happens.
 */
useApiMocks();

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

/** The page's login/resend mutations need a client; fresh per render, per the
 *  useProfileForm.test precedent. Mutations never retry, so the real defaults
 *  from createQueryClient() are safe here. */
function renderLogin() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function submitForm(email = "ada@example.com", password = "pass") {
  fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: email } });
  fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: password } });
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
    // findBy: the mutation's error state lands a scheduler tick after the
    // rejection, where the hand-rolled setState landed inside the awaited act.
    expect(await screen.findByText(/Failed to sign in/i)).toBeInTheDocument();
  });

  it("shows the email-not-confirmed message for that specific error", async () => {
    mockLogin.mockRejectedValueOnce(new Error("email not confirmed"));
    renderLogin();
    await submitForm();
    expect(await screen.findByText(/email is not confirmed/i)).toBeInTheDocument();
  });

  it("shows the ResendConfirmation component on email-not-confirmed error", async () => {
    mockLogin.mockRejectedValueOnce(new Error("email not confirmed"));
    renderLogin();
    await submitForm();
    expect(await screen.findByText(/Resend verification code/i)).toBeInTheDocument();
  });

  it("does not show ResendConfirmation on a generic error", async () => {
    mockLogin.mockRejectedValueOnce(new Error("wrong password"));
    renderLogin();
    await submitForm();
    // The error state has to have landed before the negative assertion means
    // anything — otherwise it would pass against a form still settling.
    await screen.findByText(/Failed to sign in/i);
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

});

// ─── return-to-origin ─────────────────────────────────────────────────────────

describe("Login - return-to-origin", () => {
  /** Mount /login the way RequireAuth's redirect does: with `from` in router
   *  state. `from` is deliberately untyped — the hostile cases plant values a
   *  real Location would never carry, exactly as history.pushState can. */
  function renderLoginWithFrom(from: unknown) {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter initialEntries={[{ pathname: "/login", state: { from } }]}>
          <Login />
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  const seeker = { role: "job-seeker", id: "1", email: "a@b.com", name: "A", profileComplete: false };

  it("returns to the intercepted location, keeping search and hash", async () => {
    mockLogin.mockResolvedValueOnce(seeker);
    renderLoginWithFrom({ pathname: "/job-seeker/matches", search: "?tab=2", hash: "#saved" });
    await submitForm();
    expect(mockNavigate).toHaveBeenCalledWith("/job-seeker/matches?tab=2#saved");
  });

  it("uses the default redirect when the state carries no from", async () => {
    mockLogin.mockResolvedValueOnce(seeker);
    renderLoginWithFrom(undefined);
    await submitForm();
    expect(mockNavigate).toHaveBeenCalledWith("/job-seeker/dashboard");
  });

  it.each([
    ["protocol-relative pathname", { pathname: "//evil.example/phish" }],
    ["backslash protocol-relative pathname", { pathname: "/\\evil.example/phish" }],
    ["absolute URL as pathname", { pathname: "https://evil.example/phish" }],
    ["non-object from", "//evil.example/phish"],
    ["missing pathname", { search: "?x=1" }],
  ])("falls back to the default for a hostile from: %s", async (_name, from) => {
    mockLogin.mockResolvedValueOnce(seeker);
    renderLoginWithFrom(from);
    await submitForm();
    expect(mockNavigate).toHaveBeenCalledWith("/job-seeker/dashboard");
  });

  it("drops forged search/hash that are not of location shape, keeping the safe pathname", async () => {
    mockLogin.mockResolvedValueOnce(seeker);
    renderLoginWithFrom({ pathname: "/job-seeker/matches", search: "https://evil.example", hash: 42 });
    await submitForm();
    expect(mockNavigate).toHaveBeenCalledWith("/job-seeker/matches");
  });
});

// ─── pending quiz save ────────────────────────────────────────────────────────

describe("Login - pending quiz save", () => {
  // What the guest quiz now stores (guestQuiz.completeGuestQuiz): real answers
  // and a request with items. getPendingQuizSave() returns nothing else.
  const pendingQuiz = {
    quizGroup: "careerQuizzes",
    quizResults: { careerQuizzes: { earlyCareer: { 1: 0 } }, careerQuizzesSubmittedAt: "t" },
    quizPayload: {
      quizGroup: "careerQuizzes",
      quizzes: [{ key: "earlyCareer", title: "Early", items: [{ question: "Q", selected: "A" }] }],
    },
    createdAt: "2024-01-01T00:00:00.000Z",
  };
  const seeker = { role: "job-seeker", id: "1", email: "a@b.com", name: "A", profileComplete: false };

  function renderWithClient(queryClient = createQueryClient()) {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <Login />
        </MemoryRouter>
      </QueryClientProvider>
    );
    return queryClient;
  }

  const patchBodies = () =>
    mockFetchWithAuth.mock.calls
      .filter(([path, init]) => path === "/me/profile" && init?.method === "PATCH")
      .map(([, init]) => JSON.parse(init.body));

  it("saves pending quiz results and redirects to quiz-insights", async () => {
    vi.spyOn(guestQuiz, "getPendingQuizSave").mockReturnValue(pendingQuiz);
    mockLogin.mockResolvedValueOnce(seeker);
    mockFetchWithAuth
      .mockResolvedValueOnce({})  // PATCH /me/profile
      .mockResolvedValueOnce({});  // POST /me/quiz-insights

    renderLogin();
    await submitForm();

    expect(mockFetchWithAuth).toHaveBeenCalledTimes(2);
    expect(mockFetchWithAuth).toHaveBeenLastCalledWith("/me/quiz-insights", expect.objectContaining({
      method: "POST",
      body: JSON.stringify(pendingQuiz.quizPayload),
    }));
    expect(mockNavigate).toHaveBeenCalledWith(
      `/quiz-insights?group=${encodeURIComponent("careerQuizzes")}`
    );
  });

  it("invalidates the cached profile document before navigating to quiz-insights (G22)", async () => {
    vi.spyOn(guestQuiz, "getPendingQuizSave").mockReturnValue(pendingQuiz);
    mockLogin.mockResolvedValueOnce(seeker);
    mockFetchWithAuth.mockResolvedValue({});

    // A pre-login copy of the profile with no quizResults, as the app holds it.
    const queryClient = createQueryClient();
    queryClient.setQueryData(profileKeys.document(), { name: "A" });
    let invalidatedAtNavigate: boolean | undefined;
    mockNavigate.mockImplementationOnce(() => {
      invalidatedAtNavigate = queryClient.getQueryState(profileKeys.document())?.isInvalidated;
    });

    renderWithClient(queryClient);
    await submitForm();

    expect(mockNavigate).toHaveBeenCalledWith(`/quiz-insights?group=${encodeURIComponent("careerQuizzes")}`);
    expect(invalidatedAtNavigate).toBe(true);
  });

  // Audit 2026-10-02 #2: the server merges quizResults one level deep, so the
  // guest's `careerQuizzes` map used to replace the account's whole map.
  it("merges the guest's career quiz with the account's saved career answers", async () => {
    vi.spyOn(guestQuiz, "getPendingQuizSave").mockReturnValue(pendingQuiz);
    mockLogin.mockResolvedValueOnce(seeker);
    mockFetchWithAuth.mockResolvedValue({});

    const queryClient = createQueryClient();
    queryClient.setQueryData(profileKeys.document(), {
      quizResults: { careerQuizzes: { midCareer: { 2: 1 } } },
    });
    renderWithClient(queryClient);
    await submitForm();

    expect(patchBodies()).toEqual([
      {
        profile: {
          quizResults: {
            careerQuizzes: { midCareer: { 2: 1 }, earlyCareer: { 1: 0 } },
            careerQuizzesSubmittedAt: "t",
          },
        },
      },
    ]);
  });

  it("never PATCHes empty quizResults over existing answers", async () => {
    vi.spyOn(guestQuiz, "getPendingQuizSave").mockReturnValue({
      ...pendingQuiz,
      quizResults: { careerQuizzes: {} },
    });
    mockLogin.mockResolvedValueOnce(seeker);
    mockFetchWithAuth.mockResolvedValue({});

    renderLogin();
    await submitForm();

    expect(patchBodies()).toEqual([]);
  });

  it("clears the pending quiz save after successfully saving", async () => {
    vi.spyOn(guestQuiz, "getPendingQuizSave").mockReturnValue(pendingQuiz);
    mockLogin.mockResolvedValueOnce(seeker);
    mockFetchWithAuth.mockResolvedValue({});

    renderLogin();
    await submitForm();

    expect(guestQuiz.clearPendingQuizSave).toHaveBeenCalled();
  });

  it("still navigates to dashboard if pending quiz save fails", async () => {
    vi.spyOn(guestQuiz, "getPendingQuizSave").mockReturnValue(pendingQuiz);
    mockLogin.mockResolvedValueOnce(seeker);
    mockFetchWithAuth.mockRejectedValue(new Error("save failed"));

    renderLogin();
    await submitForm();

    // Falls back to the normal job-seeker redirect
    expect(mockNavigate).toHaveBeenCalledWith("/job-seeker/dashboard");
  });

  // Audit #2: a 4xx fails identically on every sign-in, so it must not be
  // replayed forever.
  it("clears the pending save when the replay is refused with a 4xx", async () => {
    vi.spyOn(guestQuiz, "getPendingQuizSave").mockReturnValue(pendingQuiz);
    mockLogin.mockResolvedValueOnce(seeker);
    mockFetchWithAuth
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce(new ApiError("bad", { status: 400 }));

    renderLogin();
    await submitForm();

    expect(guestQuiz.clearPendingQuizSave).toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith("/job-seeker/dashboard");
  });

  it.each([429, 500, 401])("keeps the pending save for a later sign-in on a %s", async (status) => {
    vi.spyOn(guestQuiz, "getPendingQuizSave").mockReturnValue(pendingQuiz);
    mockLogin.mockResolvedValueOnce(seeker);
    mockFetchWithAuth
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce(new ApiError("later", { status }));

    renderLogin();
    await submitForm();

    expect(guestQuiz.clearPendingQuizSave).not.toHaveBeenCalled();
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

// ─── from=wpll intake save ────────────────────────────────────────────────────

describe("Login - from=wpll intake save", () => {
  function renderLoginWithParam(search = "?from=wpll") {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter initialEntries={[`/login${search}`]}>
          <Login />
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  beforeEach(() => {
    sessionStorage.clear();
  });

  it("calls fetchWithAuth with intake save payload when from=wpll and sessionStorage has data", async () => {
    sessionStorage.setItem(
      "solverah_intake",
      JSON.stringify({
        step: 4,
        selectedStatementIds: ["dir-1", "sus-1"],
        wpllAnswers: [{ questionId: "wpll-q1", optionId: "wpll-q1-c" }],
        wpllInsightText: "Test insight.",
      })
    );
    mockLogin.mockResolvedValueOnce({ role: "job-seeker", id: "1", email: "a@b.com", name: "A" });
    mockFetchWithAuth.mockResolvedValueOnce({ message: "Intake saved" });

    renderLoginWithParam();
    await submitForm();

    expect(mockFetchWithAuth).toHaveBeenCalledWith(
      "/intake/claims",
      expect.objectContaining({ method: "POST" })
    );
    const callArgs = mockFetchWithAuth.mock.calls[0][1];
    const body = JSON.parse(callArgs.body);
    // `mode` is the discriminator that picks which of the four collapsed
    // account-attachment operations this is. Without it the request is a 422.
    expect(body.mode).toBe("session");
    expect(body.selected_statement_ids).toEqual(["dir-1", "sus-1"]);
    expect(body.wpll_answers[0].question_id).toBe("wpll-q1");
    expect(body.wpll_answers[0].option_id).toBe("wpll-q1-c");
  });

  it("clears solverah_intake from sessionStorage after successful save", async () => {
    sessionStorage.setItem(
      "solverah_intake",
      JSON.stringify({
        selectedStatementIds: ["dir-1"],
        wpllAnswers: [{ questionId: "wpll-q1", optionId: "wpll-q1-b" }],
        wpllInsightText: "",
      })
    );
    mockLogin.mockResolvedValueOnce({ role: "job-seeker", id: "1", email: "a@b.com", name: "A" });
    mockFetchWithAuth.mockResolvedValueOnce({});

    renderLoginWithParam();
    await submitForm();

    expect(sessionStorage.getItem("solverah_intake")).toBeNull();
  });

  it("still navigates to dashboard if intake save fails (non-fatal)", async () => {
    sessionStorage.setItem(
      "solverah_intake",
      JSON.stringify({
        selectedStatementIds: ["dir-1"],
        wpllAnswers: [{ questionId: "wpll-q1", optionId: "wpll-q1-b" }],
        wpllInsightText: "",
      })
    );
    mockLogin.mockResolvedValueOnce({ role: "job-seeker", id: "1", email: "a@b.com", name: "A" });
    mockFetchWithAuth.mockRejectedValueOnce(new Error("network error"));

    renderLoginWithParam();
    await submitForm();

    expect(mockNavigate).toHaveBeenCalledWith("/job-seeker/dashboard");
  });

  it("does not call intake save when sessionStorage has no wpll answers", async () => {
    sessionStorage.setItem(
      "solverah_intake",
      JSON.stringify({
        selectedStatementIds: [],
        wpllAnswers: [],
        wpllInsightText: "",
      })
    );
    mockLogin.mockResolvedValueOnce({ role: "job-seeker", id: "1", email: "a@b.com", name: "A" });

    renderLoginWithParam();
    await submitForm();

    expect(mockFetchWithAuth).not.toHaveBeenCalledWith(
      "/intake/claims",
      expect.anything()
    );
  });

  it("does not call intake save when sessionStorage has no intake data", async () => {
    // No solverah_intake key — user navigated directly to /login without going through intake
    mockLogin.mockResolvedValueOnce({ role: "job-seeker", id: "1", email: "a@b.com", name: "A" });

    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter initialEntries={["/login"]}>
          <Login />
        </MemoryRouter>
      </QueryClientProvider>
    );
    await submitForm();

    expect(mockFetchWithAuth).not.toHaveBeenCalledWith(
      "/intake/claims",
      expect.anything()
    );
  });
});

// ─── loading state ────────────────────────────────────────────────────────────

describe("Login - loading state", () => {
  it("disables the submit button and shows Signing in… while loading", async () => {
    let resolve!: (v: any) => void;
    mockLogin.mockReturnValueOnce(new Promise((r) => { resolve = r; }));

    renderLogin();
    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "a@b.com" } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "pass" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    });

    // findBy: isPending lands a scheduler tick after mutate(), where the
    // hand-rolled setLoading(true) was synchronous with the click.
    expect(await screen.findByRole("button", { name: /signing in/i })).toBeDisabled();

    // Clean up
    await act(async () => { resolve({ role: "job-seeker", id: "1", email: "a@b.com", name: "A", profileComplete: false }); });
  });
});
