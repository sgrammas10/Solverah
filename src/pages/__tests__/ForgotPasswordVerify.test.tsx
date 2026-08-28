import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { HttpResponse } from "msw";

import ForgotPasswordVerify from "../ForgotPasswordVerify";
import { mock } from "../../../tests/msw/contract";
import { server, useApiMocks, recordRequests, TEST_USER } from "../../../tests/msw/server";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  loginWithData: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../contexts/useAuth", () => ({
  useAuth: () => ({ loginWithData: mocks.loginWithData }),
}));

vi.mock("../../components/HeroNetworkAnimation", () => ({ default: () => null }));

/**
 * `useAuth` stays a module mock -- this page's job is to hand the envelope to
 * `loginWithData`, and asserting that it did is the point of the file. What
 * moved to MSW is the transport underneath: the page talks to two different
 * endpoints (`/auth/password/reset` to verify, `/auth/password/forgot` to
 * resend) and the old fetch stub answered both with the same object, so nothing
 * here could tell them apart.
 */
useApiMocks();
const { requests } = recordRequests();

const RESET = "POST /api/v1/auth/password/reset";
const RESEND = "POST /api/v1/auth/password/forgot";

/** A successful passwordless sign-in, in the contract's envelope. */
function resetSucceeds(user = TEST_USER, csrfToken = "token123") {
  return mock("post", "/api/v1/auth/password/reset").reply(200, {
    message: "Signed in",
    csrfToken,
    user,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

function renderForgotPasswordVerify(email = "user@example.com") {
  render(
    <MemoryRouter
      initialEntries={[{ pathname: "/forgot-password/verify", state: { email } }]}
    >
      <ForgotPasswordVerify />
    </MemoryRouter>
  );
}

async function submitCode(code = "123456") {
  fireEvent.change(screen.getByPlaceholderText("000000"), { target: { value: code } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
  });
}

// ─── initial render ────────────────────────────────────────────────────────────

describe("ForgotPasswordVerify - initial render", () => {
  it("shows the email from location state", () => {
    renderForgotPasswordVerify("user@example.com");
    expect(screen.getByText("user@example.com")).toBeInTheDocument();
  });

  it("shows 'your email' when no email in state", () => {
    renderForgotPasswordVerify("");
    expect(screen.getByText("your email")).toBeInTheDocument();
  });

  it("sign in button is disabled while code is fewer than 6 digits", () => {
    renderForgotPasswordVerify();
    fireEvent.change(screen.getByPlaceholderText("000000"), { target: { value: "123" } });
    expect(screen.getByRole("button", { name: /sign in/i })).toBeDisabled();
  });
});

// ─── validation ───────────────────────────────────────────────────────────────

describe("ForgotPasswordVerify - validation", () => {
  it("shows validation error for non-6-digit code submitted via form", async () => {
    // The input strips non-digits so we bypass the input and test the error path
    // by submitting a short code directly
    renderForgotPasswordVerify();
    // Manually trigger submit with short code by getting 5 chars
    fireEvent.change(screen.getByPlaceholderText("000000"), { target: { value: "12345" } });
    // Button is disabled at 5 chars, can't click — verify disabled
    expect(screen.getByRole("button", { name: /sign in/i })).toBeDisabled();
  });
});

// ─── happy path ────────────────────────────────────────────────────────────────

describe("ForgotPasswordVerify - happy path", () => {
  it("calls loginWithData and navigates to dashboard on success", async () => {
    // `TEST_USER.id` is a number because the contract says `integer`, where the
    // old fixture here used `"1"`. `src/contexts/authContext.ts` declares
    // `id: string`; the two disagree and the contract is the half CI checks.
    server.use(resetSucceeds());
    renderForgotPasswordVerify();
    await submitCode("123456");
    expect(mocks.loginWithData).toHaveBeenCalledWith(TEST_USER, "token123");
    expect(mocks.navigate).toHaveBeenCalledWith("/job-seeker/dashboard", { replace: true });
  });

  it("posts the email and code to the password-reset endpoint", async () => {
    let sent: Record<string, unknown> | undefined;
    server.use(
      mock("post", "/api/v1/auth/password/reset").resolve(async ({ request }) => {
        sent = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ message: "Signed in", csrfToken: "tok", user: TEST_USER });
      }),
    );
    renderForgotPasswordVerify("user@example.com");
    await submitCode("654321");

    expect(requests).toEqual([RESET]);
    expect(sent).toMatchObject({ email: "user@example.com", code: "654321" });
  });
});

// ─── error handling ────────────────────────────────────────────────────────────

describe("ForgotPasswordVerify - error handling", () => {
  it("shows error message on invalid/expired code", async () => {
    server.use(
      mock("post", "/api/v1/auth/password/reset").reply(400, { error: "Invalid code" }),
    );
    renderForgotPasswordVerify();
    await submitCode();
    expect(screen.getByText(/Invalid or expired code/i)).toBeInTheDocument();
  });

  it("shows network error message when the request fails outright", async () => {
    // Genuine: this component's catch is bare, so the string below is its own.
    server.use(
      mock("post", "/api/v1/auth/password/reset").resolve(() => HttpResponse.error()),
    );
    renderForgotPasswordVerify();
    await submitCode();
    expect(screen.getByText(/Network error/i)).toBeInTheDocument();
  });

  it("does not call loginWithData on failure", async () => {
    server.use(
      mock("post", "/api/v1/auth/password/reset").reply(400, { error: "Invalid code" }),
    );
    renderForgotPasswordVerify();
    await submitCode();
    expect(mocks.loginWithData).not.toHaveBeenCalled();
  });
});

// ─── loading state ─────────────────────────────────────────────────────────────

describe("ForgotPasswordVerify - loading state", () => {
  it("shows 'Verifying…' while request is in flight", async () => {
    let release!: () => void;
    const inFlight = new Promise<void>((resolve) => { release = resolve; });
    server.use(
      mock("post", "/api/v1/auth/password/reset").resolve(async () => {
        await inFlight;
        return HttpResponse.json({ message: "Signed in", csrfToken: "", user: TEST_USER });
      }),
    );

    renderForgotPasswordVerify();
    fireEvent.change(screen.getByPlaceholderText("000000"), { target: { value: "123456" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    });
    expect(screen.getByRole("button", { name: /verifying/i })).toBeDisabled();

    await act(async () => {
      release();
      await inFlight;
    });
  });
});

// ─── resend ───────────────────────────────────────────────────────────────────

describe("ForgotPasswordVerify - resend", () => {
  it("shows 'New code sent!' after successful resend", async () => {
    renderForgotPasswordVerify("user@example.com");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /resend code/i }));
    });
    await waitFor(() => expect(screen.getByText(/New code sent!/i)).toBeInTheDocument());
    // Resend re-requests a code from the *forgot* endpoint, not the reset one.
    // Indistinguishable before, because one stub answered both.
    expect(requests).toEqual([RESEND]);
  });

  it("shows error when no email available for resend", async () => {
    renderForgotPasswordVerify("");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /resend code/i }));
    });
    expect(screen.getByText(/No email available/i)).toBeInTheDocument();
    expect(requests).toEqual([]);
  });
});
