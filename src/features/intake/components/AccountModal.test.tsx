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

describe("AccountModal success step, signin action", () => {
  beforeEach(() => {
    mocks.navigate.mockClear();
  });

  it("closes instead of navigating -- an existing account is already verified", () => {
    const onClose = vi.fn();
    renderModal({ action: "signin" as AccountAction, onClose });

    clickTheActionButton();

    expect(onClose).toHaveBeenCalled();
    expect(mocks.navigate).not.toHaveBeenCalled();
  });
});
