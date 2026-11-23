import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { HttpResponse } from "msw";

import ForgotPasswordVerify from "./ForgotPasswordVerify";
import { createQueryClient } from "../../../shared/api/queryClient";
import { mock } from "../../../../tests/msw/contract";
import { server, useApiMocks, recordRequests, TEST_USER } from "../../../../tests/msw/server";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  loginWithData: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../useAuth", () => ({
  useAuth: () => ({ loginWithData: mocks.loginWithData }),
}));

vi.mock("../../../shared/ui/HeroNetworkAnimation", () => ({ default: () => null }));

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

/** The reset/resend mutations need a client; fresh per render, per the
 *  useProfileForm.test precedent. Mutations never retry, so the real defaults
 *  from createQueryClient() are safe here. */
function renderForgotPasswordVerify(email = "user@example.com") {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter
        initialEntries={[{ pathname: "/forgot-password/verify", state: { email } }]}
      >
        <ForgotPasswordVerify />
      </MemoryRouter>
    </QueryClientProvider>
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

  it("does not ask for the email when router state supplies it", () => {
    renderForgotPasswordVerify("user@example.com");
    expect(screen.queryByLabelText(/email address/i)).not.toBeInTheDocument();
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
  it("shows friendly copy for the wire string invalid_or_expired_code", async () => {
    // The real body (auth_service.RESET_INVALID_OR_EXPIRED), not a fixture of
    // the test's own invention: this screen keys its copy on the exact string.
    server.use(
      mock("post", "/api/v1/auth/password/reset").reply(400, { error: "invalid_or_expired_code" }),
    );
    renderForgotPasswordVerify();
    await submitCode();
    expect(screen.getByText(/invalid or has expired/i)).toBeInTheDocument();
    expect(screen.queryByText(/invalid_or_expired_code/)).not.toBeInTheDocument();
  });

  it("does not mistake a rate limit for a wrong code (G8)", async () => {
    // Before G8 every ApiError here rendered "Invalid or expired code", so a
    // person who hit the 5/minute limit was told their code was wrong.
    server.use(
      mock("post", "/api/v1/auth/password/reset").resolve(() =>
        HttpResponse.json(
          { title: "Too Many Requests", status: 429, detail: "Too many attempts. Wait a minute." },
          { status: 429 },
        ),
      ),
    );
    renderForgotPasswordVerify();
    await submitCode();
    expect(screen.getByText(/Too many attempts/i)).toBeInTheDocument();
    expect(screen.queryByText(/invalid or has expired/i)).not.toBeInTheDocument();
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
      mock("post", "/api/v1/auth/password/reset").reply(400, { error: "invalid_or_expired_code" }),
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
    // findByRole, not getByRole: the mutation's pending re-render is notified
    // via notifyManager's setTimeout(0), so it can land after act() returns.
    // The gated request above keeps isPending true until `release`, so this
    // cannot over-wait past the state it asserts.
    expect(await screen.findByRole("button", { name: /verifying/i })).toBeDisabled();

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

  // G34: the resend used to be a bare fetch whose response was never read, so
  // a 429 from `/auth/password/forgot`'s 3/minute limit still said "New code
  // sent!" and no email arrived.
  it("shows the server's 429 detail instead of claiming a code was sent (G34)", async () => {
    server.use(
      mock("post", "/api/v1/auth/password/forgot").resolve(() =>
        HttpResponse.json(
          {
            title: "Too Many Requests",
            status: 429,
            detail: "Too many attempts. Please wait a moment and try again.",
          },
          { status: 429 },
        ),
      ),
    );
    renderForgotPasswordVerify("user@example.com");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /resend code/i }));
    });
    expect(
      await screen.findByText("Too many attempts. Please wait a moment and try again."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/New code sent!/i)).not.toBeInTheDocument();
    // Not stuck on "Sent!": the person can try again once the window passes.
    expect(screen.getByRole("button", { name: /resend code/i })).toBeEnabled();
  });

  it("falls back to apiError's status wording when the failure has no body (G34)", async () => {
    // Off-contract on purpose: a body-less failure is what this branch is for.
    server.use(
      mock("post", "/api/v1/auth/password/forgot").resolve(
        () => new HttpResponse(null, { status: 503 }),
      ),
    );
    renderForgotPasswordVerify("user@example.com");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /resend code/i }));
    });
    expect(await screen.findByText(/temporarily unavailable/i)).toBeInTheDocument();
    expect(screen.queryByText(/New code sent!/i)).not.toBeInTheDocument();
  });

  it("asks for the email before resending when none is known", async () => {
    renderForgotPasswordVerify("");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /resend code/i }));
    });
    expect(screen.getByText(/Enter your email address above/i)).toBeInTheDocument();
    expect(requests).toEqual([]);
  });
});

// ─── no routed email (new tab) ────────────────────────────────────────────────

/**
 * The /forgot-password/verify twin of /verify-email's G35. Opened in a new tab
 * there is no router state: the page read "We sent a 6-digit code to your
 * email", posted an empty address on submit (which the server's "email and code
 * are required" turned into "Please enter the 6-digit code"), and the resend
 * said "No email available". It now asks for the address.
 */
describe("ForgotPasswordVerify - no email in state or query", () => {
  function renderWithoutState() {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter initialEntries={["/forgot-password/verify"]}>
          <ForgotPasswordVerify />
        </MemoryRouter>
      </QueryClientProvider>
    );
  }

  it("asks for the email instead of claiming a code went to 'your email'", () => {
    renderWithoutState();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.queryByText("your email")).not.toBeInTheDocument();
  });

  it("says the email is missing, not the code, and sends nothing", async () => {
    renderWithoutState();
    await submitCode("123456");
    expect(
      screen.getByText("Please enter the email address you asked for a code with."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/6-digit code from your email/i)).not.toBeInTheDocument();
    expect(requests).toEqual([]);
  });

  it("signs in with the typed email, trimmed and lower-cased", async () => {
    let sent: Record<string, unknown> | undefined;
    server.use(
      mock("post", "/api/v1/auth/password/reset").resolve(async ({ request }) => {
        sent = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ message: "Signed in", csrfToken: "tok", user: TEST_USER });
      }),
    );
    renderWithoutState();
    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: "  New.Tab@Example.com " },
    });
    await submitCode("654321");

    expect(requests).toEqual([RESET]);
    expect(sent).toEqual({ email: "new.tab@example.com", code: "654321" });
    expect(mocks.loginWithData).toHaveBeenCalledWith(TEST_USER, "tok");
  });

  it("resends to the typed email", async () => {
    let sent: Record<string, unknown> | undefined;
    server.use(
      mock("post", "/api/v1/auth/password/forgot").resolve(async ({ request }) => {
        sent = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ message: "reset_sent" });
      }),
    );
    renderWithoutState();
    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: "new.tab@example.com" },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /resend code/i }));
    });
    expect(await screen.findByText(/New code sent!/i)).toBeInTheDocument();
    expect(requests).toEqual([RESEND]);
    expect(sent).toEqual({ email: "new.tab@example.com" });
  });
});
