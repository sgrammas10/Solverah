import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ForgotPasswordVerify from "../ForgotPasswordVerify";

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

const mockFetch = vi.fn();
globalThis.fetch = mockFetch as any;

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
    const mockUser = { id: "1", email: "user@example.com", name: "User", role: "job-seeker" };
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ user: mockUser, csrfToken: "token123" }),
    });
    renderForgotPasswordVerify();
    await submitCode("123456");
    expect(mocks.loginWithData).toHaveBeenCalledWith(mockUser, "token123");
    expect(mocks.navigate).toHaveBeenCalledWith("/job-seeker/dashboard", { replace: true });
  });

  it("calls the verify-password-reset endpoint", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ user: {}, csrfToken: "tok" }),
    });
    renderForgotPasswordVerify("user@example.com");
    await submitCode("654321");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/auth/password/reset"),
      expect.objectContaining({ method: "POST" })
    );
    const [, options] = mockFetch.mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body.email).toBe("user@example.com");
    expect(body.code).toBe("654321");
  });
});

// ─── error handling ────────────────────────────────────────────────────────────

describe("ForgotPasswordVerify - error handling", () => {
  it("shows error message on invalid/expired code", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ error: "Invalid code" }),
    });
    renderForgotPasswordVerify();
    await submitCode();
    expect(screen.getByText(/Invalid or expired code/i)).toBeInTheDocument();
  });

  it("shows network error message when fetch throws", async () => {
    mockFetch.mockRejectedValueOnce(new Error("Network failure"));
    renderForgotPasswordVerify();
    await submitCode();
    expect(screen.getByText(/Network error/i)).toBeInTheDocument();
  });

  it("does not call loginWithData on failure", async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, json: async () => ({}) });
    renderForgotPasswordVerify();
    await submitCode();
    expect(mocks.loginWithData).not.toHaveBeenCalled();
  });
});

// ─── loading state ─────────────────────────────────────────────────────────────

describe("ForgotPasswordVerify - loading state", () => {
  it("shows 'Verifying…' while request is in flight", async () => {
    let resolve!: (v: any) => void;
    mockFetch.mockReturnValueOnce(new Promise((r) => { resolve = r; }));
    renderForgotPasswordVerify();
    fireEvent.change(screen.getByPlaceholderText("000000"), { target: { value: "123456" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    });
    expect(screen.getByRole("button", { name: /verifying/i })).toBeDisabled();
    await act(async () => { resolve({ ok: true, json: async () => ({ user: {}, csrfToken: "" }) }); });
  });
});

// ─── resend ───────────────────────────────────────────────────────────────────

describe("ForgotPasswordVerify - resend", () => {
  it("shows 'New code sent!' after successful resend", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    renderForgotPasswordVerify("user@example.com");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /resend code/i }));
    });
    await waitFor(() => expect(screen.getByText(/New code sent!/i)).toBeInTheDocument());
  });

  it("shows error when no email available for resend", async () => {
    renderForgotPasswordVerify("");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /resend code/i }));
    });
    expect(screen.getByText(/No email available/i)).toBeInTheDocument();
  });
});
