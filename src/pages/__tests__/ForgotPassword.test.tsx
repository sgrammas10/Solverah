import { render, screen, fireEvent, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ForgotPassword from "../ForgotPassword";

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

function renderForgotPassword() {
  render(
    <MemoryRouter>
      <ForgotPassword />
    </MemoryRouter>
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
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    });
    renderForgotPassword();
    await submitEmail("user@example.com");
    expect(mocks.navigate).toHaveBeenCalledWith("/forgot-password/verify", {
      state: { email: "user@example.com" },
    });
  });

  it("trims and lower-cases the email before sending", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    renderForgotPassword();
    await submitEmail("  USER@EXAMPLE.COM  ");
    const [, options] = mockFetch.mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body.email).toBe("user@example.com");
  });
});

describe("ForgotPassword - error handling", () => {
  it("shows server error message when response is not ok", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ error: "Email not found" }),
    });
    renderForgotPassword();
    await submitEmail();
    expect(screen.getByText(/Email not found/i)).toBeInTheDocument();
  });

  it("shows fallback message when server error has no message", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => null,
    });
    renderForgotPassword();
    await submitEmail();
    expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
  });

  it("shows network error message when fetch throws", async () => {
    mockFetch.mockRejectedValueOnce(new Error("Network failure"));
    renderForgotPassword();
    await submitEmail();
    expect(screen.getByText(/Network error/i)).toBeInTheDocument();
  });
});

describe("ForgotPassword - loading state", () => {
  it("disables the button and shows Sending… while loading", async () => {
    let resolve!: (v: any) => void;
    mockFetch.mockReturnValueOnce(new Promise((r) => { resolve = r; }));
    renderForgotPassword();
    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: "user@example.com" },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /send code/i }));
    });
    expect(screen.getByRole("button", { name: /sending/i })).toBeDisabled();
    await act(async () => { resolve({ ok: true, json: async () => ({}) }); });
  });
});

describe("ForgotPassword - initial render", () => {
  it("renders the email input and submit button", () => {
    renderForgotPassword();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /send code/i })).toBeInTheDocument();
  });

  it("calls the correct API endpoint", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    renderForgotPassword();
    await submitEmail();
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/request-password-reset"),
      expect.objectContaining({ method: "POST" })
    );
  });
});
