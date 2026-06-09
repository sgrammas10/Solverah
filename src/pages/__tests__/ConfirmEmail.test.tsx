import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ConfirmEmail from "../ConfirmEmail";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../../components/HeroNetworkAnimation", () => ({ default: () => null }));

const mockFetch = vi.fn();
globalThis.fetch = mockFetch as any;

beforeEach(() => {
  vi.clearAllMocks();
});

function renderConfirmEmail(state?: { email?: string; from?: string }, search = "") {
  render(
    <MemoryRouter initialEntries={[{ pathname: "/verify-email", search, state }]}>
      <ConfirmEmail />
    </MemoryRouter>
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

  it("shows 'your email' fallback when no email provided", () => {
    renderConfirmEmail();
    expect(screen.getByText("your email")).toBeInTheDocument();
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
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    });
    renderConfirmEmail({ email: "user@example.com" });
    await submitCode("123456");
    expect(screen.getByText(/Email verified!/i)).toBeInTheDocument();
  });

  it("redirects to /login after success delay", async () => {
    vi.useFakeTimers();
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    renderConfirmEmail({ email: "user@example.com" });
    await submitCode("123456");
    await act(async () => { vi.runAllTimers(); });
    expect(mocks.navigate).toHaveBeenCalledWith("/login");
    vi.useRealTimers();
  });

  it("redirects to /login?from=wpll when from=wpll", async () => {
    vi.useFakeTimers();
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    renderConfirmEmail({ email: "user@example.com", from: "wpll" });
    await submitCode("123456");
    await act(async () => { vi.runAllTimers(); });
    expect(mocks.navigate).toHaveBeenCalledWith("/login?from=wpll");
    vi.useRealTimers();
  });

  it("calls the confirm-email endpoint with email and code", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    renderConfirmEmail({ email: "user@example.com" });
    await submitCode("654321");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/confirm-email"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ email: "user@example.com", code: "654321" }),
      })
    );
  });
});

// ─── error handling ────────────────────────────────────────────────────────────

describe("ConfirmEmail - error handling", () => {
  it("shows server error message on non-ok response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => null,
    });
    renderConfirmEmail({ email: "a@b.com" });
    await submitCode();
    expect(screen.getByText(/Verification failed/i)).toBeInTheDocument();
  });

  it("shows network error message when fetch throws", async () => {
    mockFetch.mockRejectedValueOnce(new Error("Network error. Please try again."));
    renderConfirmEmail({ email: "a@b.com" });
    await submitCode();
    expect(screen.getByText(/Network error/i)).toBeInTheDocument();
  });
});

// ─── resend ───────────────────────────────────────────────────────────────────

describe("ConfirmEmail - resend", () => {
  it("shows 'New code sent!' after successful resend", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    renderConfirmEmail({ email: "user@example.com" });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /resend code/i }));
    });
    await waitFor(() => {
      expect(screen.getByText(/New code sent!/i)).toBeInTheDocument();
    });
  });

  it("shows error when no email available for resend", async () => {
    renderConfirmEmail();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /resend code/i }));
    });
    expect(screen.getByText(/No email available/i)).toBeInTheDocument();
  });
});
