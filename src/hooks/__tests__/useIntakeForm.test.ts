import { renderHook, act } from "@testing-library/react";
import type { FormEvent } from "react";
import { useIntakeForm } from "../useIntakeForm";

const mockFetch = vi.fn();
global.fetch = mockFetch;

const fakeEvent = { preventDefault: vi.fn() } as unknown as FormEvent<HTMLFormElement>;

beforeEach(() => {
  mockFetch.mockReset();
});

// Fills form and mocks the 3-step presign/upload/finalize flow so that
// submissionId is populated on the returned hook result.
async function runSuccessfulSubmission(
  result: ReturnType<typeof renderHook<ReturnType<typeof useIntakeForm>>>["result"]
) {
  act(() => {
    result.current.handleInputChange("firstName", "Ada");
    result.current.handleInputChange("lastName", "Lovelace");
    result.current.handleInputChange("email", "ada@example.com");
    result.current.handleInputChange("state", "CA");
    result.current.setPrivacyConsent(true);
    result.current.setResumeFile(
      new File(["content"], "resume.pdf", { type: "application/pdf" })
    );
  });

  mockFetch
    .mockResolvedValueOnce({
      ok: true,
      json: vi.fn().mockResolvedValue({
        submission_id: "sub-123",
        object_key: "obj-key",
        upload_url: "https://s3.example.com/upload",
      }),
    })
    .mockResolvedValueOnce({ ok: true }) // S3 PUT
    .mockResolvedValueOnce({
      ok: true,
      json: vi.fn().mockResolvedValue({ ok: true }),
    }); // finalize

  await act(async () => {
    await result.current.handleSubmit(fakeEvent);
  });
}

// ─── handleSubmit validation ────────────────────────────────────────────────

describe("handleSubmit - client-side validation", () => {
  it("sets error when first or last name is missing", async () => {
    const { result } = renderHook(() => useIntakeForm());
    await act(async () => { await result.current.handleSubmit(fakeEvent); });
    expect(result.current.errorMessage).toBe("Please enter your name.");
    expect(result.current.submissionStatus).toBe("error");
  });

  it("sets error when email is missing", async () => {
    const { result } = renderHook(() => useIntakeForm());
    act(() => {
      result.current.handleInputChange("firstName", "Ada");
      result.current.handleInputChange("lastName", "Lovelace");
    });
    await act(async () => { await result.current.handleSubmit(fakeEvent); });
    expect(result.current.errorMessage).toBe("Please enter your email.");
  });

  it("sets error when state is missing", async () => {
    const { result } = renderHook(() => useIntakeForm());
    act(() => {
      result.current.handleInputChange("firstName", "Ada");
      result.current.handleInputChange("lastName", "Lovelace");
      result.current.handleInputChange("email", "ada@example.com");
    });
    await act(async () => { await result.current.handleSubmit(fakeEvent); });
    expect(result.current.errorMessage).toBe("Please enter your state / region.");
  });

  it("sets error when privacy consent is not given", async () => {
    const { result } = renderHook(() => useIntakeForm());
    act(() => {
      result.current.handleInputChange("firstName", "Ada");
      result.current.handleInputChange("lastName", "Lovelace");
      result.current.handleInputChange("email", "ada@example.com");
      result.current.handleInputChange("state", "CA");
    });
    await act(async () => { await result.current.handleSubmit(fakeEvent); });
    expect(result.current.errorMessage).toBe("Please agree to the privacy notice to continue.");
  });

  it("sets error when no resume is attached", async () => {
    const { result } = renderHook(() => useIntakeForm());
    act(() => {
      result.current.handleInputChange("firstName", "Ada");
      result.current.handleInputChange("lastName", "Lovelace");
      result.current.handleInputChange("email", "ada@example.com");
      result.current.handleInputChange("state", "CA");
      result.current.setPrivacyConsent(true);
    });
    await act(async () => { await result.current.handleSubmit(fakeEvent); });
    expect(result.current.errorMessage).toBe("Please attach your resume to continue.");
  });

  it("sets error when LinkedIn URL is not a valid URL", async () => {
    const { result } = renderHook(() => useIntakeForm());
    act(() => {
      result.current.handleInputChange("firstName", "Ada");
      result.current.handleInputChange("lastName", "Lovelace");
      result.current.handleInputChange("email", "ada@example.com");
      result.current.handleInputChange("state", "CA");
      result.current.handleInputChange("linkedinUrl", "not-a-url");
      result.current.setPrivacyConsent(true);
      result.current.setResumeFile(
        new File(["content"], "resume.pdf", { type: "application/pdf" })
      );
    });
    await act(async () => { await result.current.handleSubmit(fakeEvent); });
    expect(result.current.errorMessage).toBe("Please enter a valid LinkedIn URL.");
  });

  it("accepts a valid LinkedIn URL without error", async () => {
    const { result } = renderHook(() => useIntakeForm());
    act(() => {
      result.current.handleInputChange("firstName", "Ada");
      result.current.handleInputChange("lastName", "Lovelace");
      result.current.handleInputChange("email", "ada@example.com");
      result.current.handleInputChange("state", "CA");
      result.current.handleInputChange("linkedinUrl", "https://linkedin.com/in/ada");
      result.current.setPrivacyConsent(true);
      result.current.setResumeFile(
        new File(["content"], "resume.pdf", { type: "application/pdf" })
      );
    });

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockResolvedValue({
          submission_id: "sub-123",
          object_key: "obj-key",
          upload_url: "https://s3.example.com/upload",
        }),
      })
      .mockResolvedValueOnce({ ok: true })
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockResolvedValue({ ok: true }),
      });

    await act(async () => { await result.current.handleSubmit(fakeEvent); });
    expect(result.current.errorMessage).toBe("");
    expect(result.current.submissionStatus).toBe("success");
  });

  it("does not call fetch when validation fails", async () => {
    const { result } = renderHook(() => useIntakeForm());
    await act(async () => { await result.current.handleSubmit(fakeEvent); });
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

// ─── handleCreateAccount validation ─────────────────────────────────────────

describe("handleCreateAccount - no submission ID", () => {
  it("sets error immediately when submissionId is not set", async () => {
    const { result } = renderHook(() => useIntakeForm());
    await act(async () => { await result.current.handleCreateAccount(); });
    expect(result.current.accountError).toBe(
      "We couldn't find your submission ID. Please resubmit the form."
    );
  });
});

describe("handleCreateAccount - password validation", () => {
  it("sets error when password is shorter than 8 characters", async () => {
    const { result } = renderHook(() => useIntakeForm());
    await runSuccessfulSubmission(result);

    act(() => {
      result.current.setAccountPassword("short");
      result.current.setAccountConfirm("short");
    });
    await act(async () => { await result.current.handleCreateAccount(); });
    expect(result.current.accountError).toBe(
      "Please choose a password with at least 8 characters."
    );
  });

  it("sets error when passwords do not match", async () => {
    const { result } = renderHook(() => useIntakeForm());
    await runSuccessfulSubmission(result);

    act(() => {
      result.current.setAccountPassword("SecurePass1");
      result.current.setAccountConfirm("DifferentPass1");
    });
    await act(async () => { await result.current.handleCreateAccount(); });
    expect(result.current.accountError).toBe("Passwords do not match.");
  });

  it("advances to success step when account is created", async () => {
    const { result } = renderHook(() => useIntakeForm());
    await runSuccessfulSubmission(result);

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: vi.fn().mockResolvedValue({ ok: true }),
    });

    act(() => {
      result.current.setAccountPassword("SecurePass1");
      result.current.setAccountConfirm("SecurePass1");
    });
    await act(async () => { await result.current.handleCreateAccount(); });
    expect(result.current.accountStep).toBe("success");
    expect(result.current.accountError).toBe("");
  });

  it("sets error when the create-account API fails", async () => {
    const { result } = renderHook(() => useIntakeForm());
    await runSuccessfulSubmission(result);

    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: vi.fn().mockResolvedValue({ error: "Email already taken" }),
    });

    act(() => {
      result.current.setAccountPassword("SecurePass1");
      result.current.setAccountConfirm("SecurePass1");
    });
    await act(async () => { await result.current.handleCreateAccount(); });
    expect(result.current.accountError).toBe("Email already taken");
    expect(result.current.accountStep).not.toBe("success");
  });
});

// ─── handleSignInExisting validation ────────────────────────────────────────

describe("handleSignInExisting - no submission ID", () => {
  it("sets error immediately when submissionId is not set", async () => {
    const { result } = renderHook(() => useIntakeForm());
    await act(async () => { await result.current.handleSignInExisting(); });
    expect(result.current.accountError).toBe(
      "We couldn't find your submission ID. Please resubmit the form."
    );
  });
});

describe("handleSignInExisting - field validation", () => {
  it("sets error when sign-in email is empty", async () => {
    const { result } = renderHook(() => useIntakeForm());
    await runSuccessfulSubmission(result);

    act(() => { result.current.setSignInEmail(""); });
    await act(async () => { await result.current.handleSignInExisting(); });
    expect(result.current.accountError).toBe(
      "Please enter the email used on your submission."
    );
  });

  it("sets error when sign-in password is empty", async () => {
    const { result } = renderHook(() => useIntakeForm());
    await runSuccessfulSubmission(result);

    act(() => {
      result.current.setSignInEmail("ada@example.com");
      result.current.setSignInPassword("");
    });
    await act(async () => { await result.current.handleSignInExisting(); });
    expect(result.current.accountError).toBe("Please enter your password.");
  });

  it("advances to success step on successful sign-in", async () => {
    const { result } = renderHook(() => useIntakeForm());
    await runSuccessfulSubmission(result);

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: vi.fn().mockResolvedValue({ ok: true }),
    });

    act(() => {
      result.current.setSignInEmail("ada@example.com");
      result.current.setSignInPassword("MyPassword1");
    });
    await act(async () => { await result.current.handleSignInExisting(); });
    expect(result.current.accountStep).toBe("success");
    expect(result.current.accountError).toBe("");
  });
});
