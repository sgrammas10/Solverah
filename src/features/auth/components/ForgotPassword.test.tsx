import { render, screen, fireEvent, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { HttpResponse } from "msw";

import ForgotPassword from "./ForgotPassword";
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

useApiMocks();
const { requests } = recordRequests();

const FORGOT = "POST /api/v1/auth/password/forgot";

beforeEach(() => {
  vi.clearAllMocks();
});

/** The forgot-password mutation needs a client; fresh per render, per the
 *  useProfileForm.test precedent. Mutations never retry, so the real defaults
 *  from createQueryClient() are safe here. */
function renderForgotPassword() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <ForgotPassword />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function submitEmail(email = "user@example.com") {
  fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: email } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /send code/i }));
  });
}

describe("ForgotPassword - happy path", () => {
  it("navigates to /forgot-password/verify on success", async () => {
    renderForgotPassword();
    await submitEmail("user@example.com");
    expect(mocks.navigate).toHaveBeenCalledWith("/forgot-password/verify", {
      state: { email: "user@example.com" },
    });
  });

  it("trims and lower-cases the email before sending", async () => {
    let sent: Record<string, unknown> | undefined;
    server.use(
      mock("post", "/api/v1/auth/password/forgot").resolve(async ({ request }) => {
        sent = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ message: "Code sent" });
      }),
    );
    renderForgotPassword();
    await submitEmail("  USER@EXAMPLE.COM  ");
    expect(sent?.email).toBe("user@example.com");
  });
});

describe("ForgotPassword - error handling", () => {
  it("shows server error message when response is not ok", async () => {
    server.use(
      mock("post", "/api/v1/auth/password/forgot").reply(404, { error: "Email not found" }),
    );
    renderForgotPassword();
    await submitEmail();
    expect(screen.getByText(/Email not found/i)).toBeInTheDocument();
  });

  it("shows fallback message when server error has no message", async () => {
    // Off-contract on purpose: `LegacyError` requires `error`, so `.reply`
    // cannot express a null body. This branch exists for responses that are not
    // the documented shape, so the test has to be able to send one.
    server.use(
      mock("post", "/api/v1/auth/password/forgot").resolve(
        () => new HttpResponse("null", { status: 500, headers: { "Content-Type": "application/json" } }),
      ),
    );
    renderForgotPassword();
    await submitEmail();
    expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
  });

  it("shows network error message when the request fails outright", async () => {
    // Genuine here, unlike the equivalent case in ConfirmEmail: this component's
    // catch is bare -- `catch { setError("Network error. Please try again.") }` --
    // so the string asserted below is the component's own and not the test's.
    server.use(
      mock("post", "/api/v1/auth/password/forgot").resolve(() => HttpResponse.error()),
    );
    renderForgotPassword();
    await submitEmail();
    expect(screen.getByText(/Network error/i)).toBeInTheDocument();
  });
});

describe("ForgotPassword - loading state", () => {
  it("disables the button and shows Sending… while loading", async () => {
    // The request is held open by a gate the test releases, which is the MSW
    // equivalent of the never-resolving promise the fetch stub used to return.
    let release!: () => void;
    const inFlight = new Promise<void>((resolve) => { release = resolve; });
    server.use(
      mock("post", "/api/v1/auth/password/forgot").resolve(async () => {
        await inFlight;
        return HttpResponse.json({ message: "Code sent" });
      }),
    );

    renderForgotPassword();
    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: "user@example.com" },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /send code/i }));
    });

    // findByRole, not getByRole: the mutation's pending re-render is notified
    // via notifyManager's setTimeout(0), so it can land after act() returns.
    // The gated request above keeps isPending true until `release`, so this
    // cannot over-wait past the state it asserts.
    expect(await screen.findByRole("button", { name: /sending/i })).toBeDisabled();

    await act(async () => {
      release();
      await inFlight;
    });
  });
});

describe("ForgotPassword - initial render", () => {
  it("renders the email input and submit button", () => {
    renderForgotPassword();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send code/i })).toBeInTheDocument();
  });

  it("posts to the password-forgot endpoint and nothing else", async () => {
    renderForgotPassword();
    await submitEmail();
    expect(requests).toEqual([FORGOT]);
  });
});
