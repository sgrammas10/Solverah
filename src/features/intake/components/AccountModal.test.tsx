import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ComponentProps } from "react";
import AccountModal from "./AccountModal";
import type { AccountStep, AccountAction } from "../useIntakeForm";

/**
 * G9, walked live on production 2026-09-15.
 *
 * The hero-form modal creates an unverified account and then had to decide
 * where to send the person next. It sent them to `/login`, where the only
 * thing that can happen is a failed sign-in -- the account is unconfirmed, and
 * the code they were just emailed is entered on `/verify-email`, a screen this
 * flow never mentioned. The email address has to ride along in router state
 * because `ConfirmEmail` posts it alongside the code; without it the field is
 * blank and the verify call has nothing to identify the account with.
 */

const mocks = vi.hoisted(() => ({ navigate: vi.fn() }));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

const SUBMISSION_EMAIL = "ada@example.com";

/** Mirrors the component's own props; it does not export them. */
type Props = ComponentProps<typeof AccountModal>;

function renderModal(overrides: Partial<Props> = {}) {
  const props: Props = {
    isOpen: true,
    onClose: vi.fn(),
    submissionEmail: SUBMISSION_EMAIL,
    step: "success" as AccountStep,
    setStep: vi.fn(),
    action: "create" as AccountAction,
    signInEmail: "",
    setSignInEmail: vi.fn(),
    signInPassword: "",
    setSignInPassword: vi.fn(),
    accountPassword: "",
    setAccountPassword: vi.fn(),
    accountConfirm: "",
    setAccountConfirm: vi.fn(),
    error: "",
    setError: vi.fn(),
    isCreatingAccount: false,
    isSigningIn: false,
    onCreateAccount: vi.fn(),
    onSignInExisting: vi.fn(),
    signInNeedsVerification: false,
    onResendVerification: vi.fn().mockResolvedValue(true),
    isResendingVerification: false,
    ...overrides,
  };
  return render(
    <MemoryRouter>
      <AccountModal {...props} />
    </MemoryRouter>
  );
}

/**
 * The success step renders exactly two buttons: the modal's "Close" affordance
 * and the one action. Selecting by elimination rather than by accessible name
 * keeps these assertions about *routing*, which is the defect, and leaves the
 * label free for Julie to revise without turning a copy edit into a red suite.
 */
function clickTheActionButton() {
  const action = screen
    .getAllByRole("button")
    .filter((b) => b.getAttribute("aria-label") !== "Close");
  expect(action).toHaveLength(1);
  fireEvent.click(action[0]);
}

describe("AccountModal success step, create action", () => {
  beforeEach(() => {
    mocks.navigate.mockClear();
  });

  it("sends a newly created account to /verify-email, not /login", () => {
    renderModal();

    clickTheActionButton();

    expect(mocks.navigate).toHaveBeenCalledWith("/verify-email", {
      state: { email: SUBMISSION_EMAIL },
    });
  });

  it("never routes to /login from this button", () => {
    renderModal();

    clickTheActionButton();

    expect(mocks.navigate).not.toHaveBeenCalledWith(
      "/login",
      expect.anything()
    );
    expect(mocks.navigate).not.toHaveBeenCalledWith("/login");
  });

  it("carries the submission email, which is what ConfirmEmail verifies with", () => {
    renderModal({ submissionEmail: "grace@example.com" });

    clickTheActionButton();

    expect(mocks.navigate).toHaveBeenCalledWith("/verify-email", {
      state: { email: "grace@example.com" },
    });
  });

  it("tells the user a code is waiting for them", () => {
    renderModal();

    expect(screen.getByText(/6-digit code/i)).toBeInTheDocument();
  });
});

/**
 * G29. A sign-in from this modal opens a real session (the claim sets both
 * cookies), so the visitor is signed in. This button used to just close the
 * modal, which left a signed-in visitor on the signed-out landing page -- its
 * sign-up calls to action and all -- until a reload. Every way out of the
 * success step now goes home instead; none of them goes to /verify-email,
 * because an account that can sign in is already verified.
 */
describe("AccountModal success step, signin action (G29)", () => {
  beforeEach(() => {
    mocks.navigate.mockClear();
  });

  it("Continue goes to the dashboard rather than back to the landing page", () => {
    const onClose = vi.fn();
    renderModal({ action: "signin" as AccountAction, onClose });

    clickTheActionButton();

    expect(mocks.navigate).toHaveBeenCalledWith("/job-seeker/dashboard");
    expect(onClose).not.toHaveBeenCalled();
  });

  it.each([
    ["the close button", () => fireEvent.click(screen.getByRole("button", { name: "Close" }))],
    ["Escape", () => fireEvent.keyDown(window, { key: "Escape" })],
  ])("%s goes to the dashboard too", (_how, leave) => {
    const onClose = vi.fn();
    renderModal({ action: "signin" as AccountAction, onClose });

    leave();

    expect(mocks.navigate).toHaveBeenCalledWith("/job-seeker/dashboard");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("before the sign-in succeeds, Escape just closes", () => {
    const onClose = vi.fn();
    renderModal({ step: "signin" as AccountStep, action: "signin" as AccountAction, onClose });

    fireEvent.keyDown(window, { key: "Escape" });

    expect(onClose).toHaveBeenCalled();
    expect(mocks.navigate).not.toHaveBeenCalled();
  });
});

describe("AccountModal sign-in refused for an unconfirmed email (G29)", () => {
  beforeEach(() => {
    mocks.navigate.mockClear();
  });

  const unconfirmed = {
    step: "signin" as AccountStep,
    signInEmail: SUBMISSION_EMAIL,
    error: "Email not confirmed. Please confirm your email before signing in.",
    signInNeedsVerification: true,
  };

  it("offers a fresh code, and takes the visitor to enter it once it is sent", async () => {
    const onResendVerification = vi.fn().mockResolvedValue(true);
    renderModal({ ...unconfirmed, onResendVerification });

    fireEvent.click(screen.getByRole("button", { name: "Resend verification code" }));

    expect(onResendVerification).toHaveBeenCalled();
    await vi.waitFor(() =>
      expect(mocks.navigate).toHaveBeenCalledWith("/verify-email", {
        state: { email: SUBMISSION_EMAIL },
      })
    );
  });

  it("stays put when the resend fails, so its error can show", async () => {
    const onResendVerification = vi.fn().mockResolvedValue(false);
    renderModal({ ...unconfirmed, onResendVerification });

    fireEvent.click(screen.getByRole("button", { name: "Resend verification code" }));

    await vi.waitFor(() => expect(onResendVerification).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(mocks.navigate).not.toHaveBeenCalled();
  });

  it("other sign-in errors do not offer a code", () => {
    renderModal({ ...unconfirmed, error: "Invalid credentials", signInNeedsVerification: false });

    expect(screen.queryByRole("button", { name: "Resend verification code" })).toBeNull();
  });
});

describe("AccountModal password fields: show/hide toggle", () => {
  it.each([
    ["form" as AccountStep, "Create a password"],
    ["form" as AccountStep, "Confirm password"],
    ["signin" as AccountStep, "Password"],
  ])("step %s, %s: starts hidden and toggles to visible and back", (step, label) => {
    renderModal({ step });

    const input = screen.getByLabelText(label);
    expect(input).toHaveAttribute("type", "password");

    const toggles = screen.getAllByRole("button", { name: "Show password" });
    // One toggle per password field, each inside the field's own wrapper.
    const toggle = toggles.find((b) => b.parentElement?.contains(input));
    expect(toggle).toBeDefined();

    fireEvent.click(toggle!);
    expect(input).toHaveAttribute("type", "text");
    expect(toggle).toHaveAccessibleName("Hide password");

    fireEvent.click(toggle!);
    expect(input).toHaveAttribute("type", "password");
  });
});
