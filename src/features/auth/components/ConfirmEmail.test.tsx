import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { HttpResponse } from "msw";

import ConfirmEmail from "./ConfirmEmail";
import { createQueryClient } from "../../../shared/api/queryClient";
import { mock } from "../../../../tests/msw/contract";
import { server, useApiMocks, recordRequests } from "../../../../tests/msw/server";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../../shared/ui/HeroNetworkAnimation", () => ({ default: () => null }));

/**
 * The verify and resend endpoints are real requests here rather than a `vi.fn()`
 * over `globalThis.fetch`. What that buys, concretely: the old stub answered
 * both endpoints with the same canned object, so the resend tests would have
 * passed had the button posted to the verify path, and vice versa.
 */
useApiMocks();
const { requests } = recordRequests();

const VERIFY = "POST /api/v1/auth/email/verify";
const RESEND = "POST /api/v1/auth/email/verify/resend";

beforeEach(() => {
  mocks.navigate.mockReset();
});

/** The verify/resend mutations need a client; fresh per render, per the
 *  useProfileForm.test precedent. Mutations never retry, so the real defaults
 *  from createQueryClient() are safe here. */
function renderConfirmEmail(state?: { email?: string }, search = "") {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[{ pathname: "/verify-email", search, state }]}>
        <ConfirmEmail />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function enterCode(code: string) {
  fireEvent.change(screen.getByPlaceholderText("000000"), { target: { value: code } });
}

async function submitCode(code = "123456") {
  await enterCode(code);
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /verify email/i }));
  });
}

// ─── initial render ────────────────────────────────────────────────────────────

describe("ConfirmEmail - initial render", () => {
  it("shows the email from location state", () => {
    renderConfirmEmail({ email: "user@example.com" });
    expect(screen.getByText("user@example.com")).toBeInTheDocument();
  });

  it("shows the email from query param when no state", () => {
    renderConfirmEmail(undefined, "?email=query%40example.com");
    expect(screen.getByText("query@example.com")).toBeInTheDocument();
  });

  it("does not ask for the email when router state supplies it", () => {
    renderConfirmEmail({ email: "user@example.com" });
    expect(screen.queryByLabelText(/email address/i)).not.toBeInTheDocument();
  });

  it("submit button is disabled when code is empty", () => {
    renderConfirmEmail({ email: "a@b.com" });
    expect(screen.getByRole("button", { name: /verify email/i })).toBeDisabled();
  });
});

// ─── validation ───────────────────────────────────────────────────────────────

describe("ConfirmEmail - validation", () => {
  it("shows error for non-numeric code", async () => {
    renderConfirmEmail({ email: "a@b.com" });
    // The input strips non-digits; typing 6 letters won't reach length 6
    // so submit stays disabled — type mixed and submit via form directly
    fireEvent.change(screen.getByPlaceholderText("000000"), { target: { value: "abc123" } });
    // input filters to digits only; "abc123" → "123" (3 chars), button stays disabled
    expect(screen.getByRole("button", { name: /verify email/i })).toBeDisabled();
  });
});

// ─── happy path ────────────────────────────────────────────────────────────────

describe("ConfirmEmail - happy path", () => {
  it("shows success message after valid code submission", async () => {
    renderConfirmEmail({ email: "user@example.com" });
    await submitCode("123456");
    // findBy: the mutation's success state lands a scheduler tick after the
    // response, where the hand-rolled setStatus landed inside the awaited act.
    expect(await screen.findByText(/Email verified!/i)).toBeInTheDocument();
  });

  it("redirects to /login after success delay", async () => {
    vi.useFakeTimers();
    renderConfirmEmail({ email: "user@example.com" });
    await submitCode("123456");
    await act(async () => { vi.runAllTimers(); });
    expect(mocks.navigate).toHaveBeenCalledWith("/login");
    vi.useRealTimers();
  });

  it("posts the email and code to the verify endpoint", async () => {
    let sent: Record<string, unknown> | undefined;
    server.use(
      mock("post", "/api/v1/auth/email/verify").resolve(async ({ request }) => {
        sent = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ message: "Email verified" });
      }),
    );

    renderConfirmEmail({ email: "user@example.com" });
    await submitCode("654321");

    expect(requests).toEqual([VERIFY]);
    expect(sent).toEqual({ email: "user@example.com", code: "654321" });
  });
});

// ─── error handling ────────────────────────────────────────────────────────────

describe("ConfirmEmail - error handling", () => {
  it("shows the server's message on a rejected code", async () => {
    server.use(
      mock("post", "/api/v1/auth/email/verify").reply(400, { error: "That code has expired." }),
    );
    renderConfirmEmail({ email: "a@b.com" });
    await submitCode();
    expect(screen.getByText(/That code has expired/i)).toBeInTheDocument();
  });

  // G8: the server answers a bad code with `invalid code` / `code expired` --
  // terse by design, they are the codes the legacy body has no other field
  // for -- and the screen used to print them raw. Keyed on the exact wire
  // strings (pinned server-side by test_register_api.py).
  it.each([
    ["invalid code", /didn't match/i],
    ["code expired", /has expired/i],
  ])("turns the wire string %j into friendly copy (G8)", async (wire, friendly) => {
    server.use(mock("post", "/api/v1/auth/email/verify").reply(400, { error: wire }));
    renderConfirmEmail({ email: "a@b.com" });
    await submitCode();

    const errorPanel = document.querySelector(".bg-red-50");
    expect(errorPanel?.textContent).toMatch(friendly);
    expect(errorPanel?.textContent?.trim()).not.toBe(wire);
  });

  it("does not mistake a rate limit for a wrong code", async () => {
    // The limiter's 429 is a problem+json body; its own message must survive.
    server.use(
      mock("post", "/api/v1/auth/email/verify").resolve(() =>
        HttpResponse.json(
          { title: "Too Many Requests", status: 429, detail: "Too many attempts. Wait a minute." },
          { status: 429 },
        ),
      ),
    );
    renderConfirmEmail({ email: "a@b.com" });
    await submitCode();
    expect(screen.getByText(/Too many attempts/i)).toBeInTheDocument();
  });

  it("shows the fallback message when the error body carries nothing usable", async () => {
    // Off-contract on purpose -- see the equivalent note in useEarlyAccess.test.ts.
    // `LegacyError` requires `error`, so `.reply` cannot express a null body, and
    // the fallback branch this covers exists precisely for responses that are not
    // the documented shape.
    server.use(
      mock("post", "/api/v1/auth/email/verify").resolve(
        () => new HttpResponse("null", { status: 400, headers: { "Content-Type": "application/json" } }),
      ),
    );
    renderConfirmEmail({ email: "a@b.com" });
    await submitCode();
    expect(screen.getByText(/Verification failed/i)).toBeInTheDocument();
  });

  it("enters the error state, not success, when the request fails outright", async () => {
    /**
     * This assertion changed when the file moved to MSW, and the old one was
     * wrong rather than merely different.
     *
     * It read `mockFetch.mockRejectedValueOnce(new Error("Network error. Please
     * try again."))` and then asserted `/Network error/i` was on screen -- but
     * the component's catch is `setMessage(err?.message || "Network error.
     * Please try again.")`, so what it rendered was the message the *test* had
     * just put in the error. The test asserted on its own fixture. The `||`
     * fallback it looked like it was covering was never reached, and would not
     * have been reached however the fallback was written.
     *
     * A real transport failure rejects with whatever the runtime says --
     * "Failed to fetch" under undici -- so pinning the string here would only
     * pin the runtime. What is worth asserting is the behaviour: the failure
     * surfaces in the error panel, the success path does not run, and the form
     * is still there to retry with.
     */
    server.use(
      mock("post", "/api/v1/auth/email/verify").resolve(() => HttpResponse.error()),
    );
    renderConfirmEmail({ email: "a@b.com" });
    await submitCode();

    expect(screen.queryByText(/Email verified!/i)).not.toBeInTheDocument();
    expect(mocks.navigate).not.toHaveBeenCalled();

    const errorPanel = document.querySelector(".bg-red-50");
    expect(errorPanel).not.toBeNull();
    expect(errorPanel?.textContent?.trim()).not.toBe("");
  });
});

// ─── resend ───────────────────────────────────────────────────────────────────

describe("ConfirmEmail - resend", () => {
  it("shows 'New code sent!' after successful resend", async () => {
    renderConfirmEmail({ email: "user@example.com" });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /resend code/i }));
    });
    await waitFor(() => {
      expect(screen.getByText(/New code sent!/i)).toBeInTheDocument();
    });
    // The resend button posts to the resend path, not the verify one. The old
    // fetch stub answered both identically and could not tell them apart.
    expect(requests).toEqual([RESEND]);
  });

  it("shows a network-error sentence, not the runtime's raw text, when resend never reaches the server", async () => {
    // A transport failure rejects with the runtime's wording ("Failed to fetch"
    // under undici), which this used to print as-is.
    server.use(
      mock("post", "/api/v1/auth/email/verify/resend").resolve(() => HttpResponse.error()),
    );
    renderConfirmEmail({ email: "user@example.com" });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /resend code/i }));
    });
    expect(await screen.findByText("Network error. Please try again.")).toBeInTheDocument();
    expect(screen.queryByText(/failed to fetch/i)).not.toBeInTheDocument();
  });

  it("asks for the email before resending when none is known", async () => {
    renderConfirmEmail();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /resend code/i }));
    });
    expect(screen.getByText(/Enter your email address above/i)).toBeInTheDocument();
    expect(requests).toEqual([]);
  });
});

// ─── no routed email (G35) ────────────────────────────────────────────────────

/**
 * G35: `/verify-email` opened in a new tab has no router state and no
 * `?email=`. The page used to read "We sent a 6-digit code to your email",
 * post an empty address, and render the server's "email and code are
 * required" as "Please enter the 6-digit code" -- the code was fine; the
 * address was what was missing. It now asks for the address.
 */
describe("ConfirmEmail - no email in state or query (G35)", () => {
  it("asks for the email instead of claiming a code went to 'your email'", () => {
    renderConfirmEmail();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.queryByText("your email")).not.toBeInTheDocument();
  });

  it("says the email is missing, not the code, and sends nothing", async () => {
    renderConfirmEmail();
    await submitCode("123456");
    expect(
      screen.getByText("Please enter the email address you signed up with."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/6-digit code from your email/i)).not.toBeInTheDocument();
    expect(requests).toEqual([]);
  });

  it("verifies with the typed email, trimmed and lower-cased", async () => {
    let sent: Record<string, unknown> | undefined;
    server.use(
      mock("post", "/api/v1/auth/email/verify").resolve(async ({ request }) => {
        sent = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ message: "Email verified" });
      }),
    );
    renderConfirmEmail();
    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: "  New.Tab@Example.com " },
    });
    await submitCode("654321");

    expect(requests).toEqual([VERIFY]);
    expect(sent).toEqual({ email: "new.tab@example.com", code: "654321" });
    expect(await screen.findByText(/Email verified!/i)).toBeInTheDocument();
  });

  it("resends to the typed email", async () => {
    let sent: Record<string, unknown> | undefined;
    server.use(
      mock("post", "/api/v1/auth/email/verify/resend").resolve(async ({ request }) => {
        sent = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ message: "New code sent" });
      }),
    );
    renderConfirmEmail();
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
