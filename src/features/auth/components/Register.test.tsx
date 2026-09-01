import { render, screen, fireEvent, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import Register from "./Register";
import { createQueryClient } from "../../../shared/api/queryClient";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  register: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

vi.mock("../useAuth", () => ({
  useAuth: () => ({ register: mocks.register }),
}));

vi.mock("../../../shared/ui/HeroNetworkAnimation", () => ({ default: () => null }));

beforeEach(() => {
  vi.clearAllMocks();
});

/** The register mutation needs a client; fresh per render, per the
 *  useProfileForm.test precedent. Mutations never retry, so the real
 *  defaults from createQueryClient() are safe here. */
function renderRegister(search = "") {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[{ pathname: "/register", search }]}>
        <Register />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function fillAndSubmit({
  name = "Test User",
  email = "test@example.com",
  password = "ValidPass123!",
  confirmPassword = "ValidPass123!",
  acceptTerms = true,
} = {}) {
  fireEvent.change(screen.getByLabelText(/full name/i), { target: { value: name } });
  fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: email } });
  fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: password } });
  fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: confirmPassword } });
  if (acceptTerms) {
    fireEvent.click(screen.getByLabelText(/16 or older/i));
  }
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));
  });
}

// ─── validation ───────────────────────────────────────────────────────────────

describe("Register - validation", () => {
  it("shows error when passwords do not match", async () => {
    renderRegister();
    await fillAndSubmit({ password: "ValidPass123!", confirmPassword: "DifferentPass123!" });
    expect(screen.getByText(/Passwords do not match/i)).toBeInTheDocument();
    expect(mocks.register).not.toHaveBeenCalled();
  });

  it("shows error when password is too short", async () => {
    renderRegister();
    await fillAndSubmit({ password: "Short1!", confirmPassword: "Short1!" });
    expect(screen.getByText(/at least 12 characters/i)).toBeInTheDocument();
  });

  it("shows error when password lacks an uppercase letter", async () => {
    renderRegister();
    await fillAndSubmit({ password: "nouppercase123!", confirmPassword: "nouppercase123!" });
    expect(screen.getByText(/uppercase letter/i)).toBeInTheDocument();
  });

  it("shows error when password lacks a lowercase letter", async () => {
    renderRegister();
    await fillAndSubmit({ password: "NOLOWERCASE123!", confirmPassword: "NOLOWERCASE123!" });
    expect(screen.getByText(/lowercase letter/i)).toBeInTheDocument();
  });

  it("shows error when password lacks a number", async () => {
    renderRegister();
    await fillAndSubmit({ password: "NoNumberPass!!", confirmPassword: "NoNumberPass!!" });
    expect(screen.getByText(/contain a number/i)).toBeInTheDocument();
  });

  it("shows error when password lacks a symbol", async () => {
    renderRegister();
    await fillAndSubmit({ password: "NoSymbol12345678", confirmPassword: "NoSymbol12345678" });
    expect(screen.getByText(/symbol/i)).toBeInTheDocument();
  });

  // GAP-01/GAP-05 (2026-08-20): registration requires ToS/privacy acceptance
  // + 16+ attestation. This test fails if the checkbox gate is removed.
  it("blocks submission and never calls register when terms are not accepted", async () => {
    renderRegister();
    await fillAndSubmit({ acceptTerms: false });
    expect(screen.getByText(/16 or older and accept the Terms/i)).toBeInTheDocument();
    expect(mocks.register).not.toHaveBeenCalled();
  });
});

// ─── happy path ────────────────────────────────────────────────────────────────

describe("Register - happy path", () => {
  it("calls register and navigates to /verify-email on success", async () => {
    mocks.register.mockResolvedValueOnce(undefined);
    renderRegister();
    await fillAndSubmit();
    expect(mocks.register).toHaveBeenCalledWith(
      "test@example.com",
      "ValidPass123!",
      "Test User",
      true
    );
    expect(mocks.navigate).toHaveBeenCalledWith("/verify-email", {
      state: { email: "test@example.com", from: undefined },
    });
  });

  it("passes from=wpll in state when registered via ?from=wpll", async () => {
    mocks.register.mockResolvedValueOnce(undefined);
    renderRegister("?from=wpll");
    await fillAndSubmit();
    expect(mocks.navigate).toHaveBeenCalledWith("/verify-email", {
      state: { email: "test@example.com", from: "wpll" },
    });
  });
});

// ─── error handling ────────────────────────────────────────────────────────────

describe("Register - error handling", () => {
  it("shows 'already exists' message for duplicate accounts", async () => {
    mocks.register.mockRejectedValueOnce(new Error("User already exists"));
    renderRegister();
    await fillAndSubmit();
    expect(screen.getByText(/already exists/i)).toBeInTheDocument();
  });

  it("shows generic error for unexpected failures", async () => {
    mocks.register.mockRejectedValueOnce(new Error("Server error"));
    renderRegister();
    await fillAndSubmit();
    expect(screen.getByText(/Server error/i)).toBeInTheDocument();
  });
});

// ─── password visibility ───────────────────────────────────────────────────────

describe("Register - password visibility", () => {
  it("password starts as type=password", () => {
    renderRegister();
    expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("type", "password");
  });

  it("toggles password to type=text when show-password clicked", async () => {
    renderRegister();
    const toggles = screen.getAllByRole("button", { name: /show password/i });
    fireEvent.click(toggles[0]);
    expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("type", "text");
  });
});

// ─── loading state ─────────────────────────────────────────────────────────────

describe("Register - loading state", () => {
  it("disables button and shows 'Creating account…' while submitting", async () => {
    let resolve!: (v: any) => void;
    mocks.register.mockReturnValueOnce(new Promise((r) => { resolve = r; }));
    renderRegister();
    fireEvent.change(screen.getByLabelText(/full name/i), { target: { value: "Test User" } });
    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: "a@b.com" } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "ValidPass123!" } });
    fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: "ValidPass123!" } });
    fireEvent.click(screen.getByLabelText(/16 or older/i));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /create account/i }));
    });
    expect(screen.getByRole("button", { name: /creating account/i })).toBeDisabled();
    await act(async () => { resolve(undefined); });
  });
});
