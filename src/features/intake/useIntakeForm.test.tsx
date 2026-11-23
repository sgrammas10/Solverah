/**
 * useIntakeForm.test.tsx — the pre-launch intake submission over the real endpoints.
 *
 * The presign → S3 PUT → finalize chain is one mutation now (the
 * IntakePromptModal shape), so these tests pin what that buys and what it must
 * not change:
 *
 *   - the three steps succeed or fail as a unit, in order, on the contract paths;
 *   - a 4xx anywhere in the chain means fail — mutations never retry, and the
 *     S3 PUT in particular must never be reissued, because the presigned URL
 *     has single-use semantics;
 *   - `submissionStatus`/`errorMessage` are the mutation's lifecycle, with
 *     client-side validation folded in as the "error" it always was.
 *
 * The handlers are contract-bound and unhandled requests are errors, so a
 * request to a path the API does not serve fails the test that made it. The S3
 * PUT goes to the presigned host, not the API, and gets a plain handler.
 */
import type { FormEvent, ReactNode } from "react";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";

import { useIntakeForm, passwordProblem, type IntakeFormOptions } from "./useIntakeForm";
import { createQueryClient } from "../../shared/api/queryClient";
import { mock } from "../../../tests/msw/contract";
import { server, useApiMocks, recordRequests } from "../../../tests/msw/server";

useApiMocks();
const { requests } = recordRequests();

const UPLOAD_URL = "https://uploads.example.com/intake-resume-1";

function presignSucceeds() {
  return mock("post", "/api/v1/intake/resume-tickets").resolve(() =>
    HttpResponse.json({
      submission_id: "sub-1",
      object_key: "intake/resume-1.pdf",
      upload_url: UPLOAD_URL,
    })
  );
}

function uploadSucceeds() {
  return http.put(UPLOAD_URL, () => new HttpResponse(null, { status: 200 }));
}

function finalizeSucceeds() {
  return mock("post", "/api/v1/intake/submissions").resolve(() =>
    HttpResponse.json({ submission_id: "sub-1" }, { status: 201 })
  );
}

function createWrapper() {
  const queryClient = createQueryClient();
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

function setup() {
  const { result } = renderHook(() => useIntakeForm(), { wrapper: createWrapper() });
  return result;
}

function fillValidForm(result: ReturnType<typeof setup>) {
  act(() => {
    result.current.handleInputChange("firstName", "Ada");
    result.current.handleInputChange("lastName", "Lovelace");
    result.current.handleInputChange("email", "ada@example.com");
    result.current.handleInputChange("state", "NY");
    result.current.setPrivacyConsent(true);
    result.current.setResumeFile(
      new File(["%PDF-1.4"], "resume.pdf", { type: "application/pdf" })
    );
  });
}

const submitEvent = { preventDefault: () => {} } as unknown as FormEvent<HTMLFormElement>;

describe("useIntakeForm - submission chain", () => {
  it("runs presign → S3 PUT → finalize as one chain and lands on success", async () => {
    server.use(presignSucceeds(), uploadSucceeds(), finalizeSucceeds());
    const result = setup();
    fillValidForm(result);

    await act(async () => {
      result.current.handleSubmit(submitEvent);
    });

    await waitFor(() => expect(result.current.submissionStatus).toBe("success"));
    expect(result.current.accountModalOpen).toBe(true);
    expect(result.current.submissionId).toBe("sub-1");
    expect(result.current.submissionEmail).toBe("ada@example.com");
    // The form is cleared for the next visitor once the chain lands.
    expect(result.current.formData.firstName).toBe("");
    expect(result.current.resumeFile).toBeNull();

    expect(requests).toEqual([
      "POST /api/v1/intake/resume-tickets",
      "PUT /intake-resume-1",
      "POST /api/v1/intake/submissions",
    ]);
  });

  it("a 4xx on the presign fails the submission without retrying or uploading", async () => {
    // 4xx means fail: the input is wrong, a second attempt cannot succeed, and
    // mutations never retry — one request is the whole of the traffic.
    server.use(
      mock("post", "/api/v1/intake/resume-tickets").resolve(() =>
        HttpResponse.json({ error: "File too large" }, { status: 422 })
      ),
      uploadSucceeds(),
      finalizeSucceeds()
    );
    const result = setup();
    fillValidForm(result);

    await act(async () => {
      result.current.handleSubmit(submitEvent);
    });

    await waitFor(() => expect(result.current.submissionStatus).toBe("error"));
    expect(result.current.errorMessage).toMatch(/file too large/i);
    expect(requests).toEqual(["POST /api/v1/intake/resume-tickets"]);
  });

  it("a failed S3 PUT fails the chain and never reissues the single-use URL", async () => {
    // Even a 5xx — retryable for a GET — must not be retried here: the
    // presigned URL is single-use, so the chain's own error handling is the
    // only recovery, and the finalize is never reached.
    server.use(
      presignSucceeds(),
      http.put(UPLOAD_URL, () => new HttpResponse(null, { status: 500 })),
      finalizeSucceeds()
    );
    const result = setup();
    fillValidForm(result);

    await act(async () => {
      result.current.handleSubmit(submitEvent);
    });

    await waitFor(() => expect(result.current.submissionStatus).toBe("error"));
    expect(result.current.errorMessage).toBe("Upload failed. Please try again.");
    expect(requests).toEqual([
      "POST /api/v1/intake/resume-tickets",
      "PUT /intake-resume-1",
    ]);
  });

  it("a 4xx on the finalize fails the chain after the upload", async () => {
    server.use(
      presignSucceeds(),
      uploadSucceeds(),
      mock("post", "/api/v1/intake/submissions").resolve(() =>
        HttpResponse.json({ error: "Submission already exists" }, { status: 409 })
      )
    );
    const result = setup();
    fillValidForm(result);

    await act(async () => {
      result.current.handleSubmit(submitEvent);
    });

    await waitFor(() => expect(result.current.submissionStatus).toBe("error"));
    expect(result.current.errorMessage).toMatch(/already exists/i);
    // The account modal is a success affordance; a failed chain must not open it.
    expect(result.current.accountModalOpen).toBe(false);
    expect(requests).toEqual([
      "POST /api/v1/intake/resume-tickets",
      "PUT /intake-resume-1",
      "POST /api/v1/intake/submissions",
    ]);
  });

  it("client-side validation failures report error without touching the network", () => {
    const result = setup();

    act(() => {
      result.current.handleSubmit(submitEvent);
    });

    expect(result.current.submissionStatus).toBe("error");
    expect(result.current.errorMessage).toBe("Please enter your name.");
    expect(requests).toEqual([]);
  });
});

/** Run the whole chain once so the account modal has a submission to claim. */
async function submitSuccessfully(result: ReturnType<typeof setup>) {
  server.use(presignSucceeds(), uploadSucceeds(), finalizeSucceeds());
  fillValidForm(result);
  await act(async () => {
    result.current.handleSubmit(submitEvent);
  });
  await waitFor(() => expect(result.current.submissionStatus).toBe("success"));
  requests.length = 0;
}

describe("useIntakeForm - account password (G30)", () => {
  // validate_password in validators.py is what /intake/claims enforces. The
  // modal used to accept anything of 8+ characters, so these passed here and
  // came back from the server as an error the client had just waved through.
  it.each([
    ["Abcdef1!x", "Password must be at least 12 characters."],
    ["abcdefgh1!xy", "Password must contain an uppercase letter."],
    ["ABCDEFGH1!XY", "Password must contain a lowercase letter."],
    ["Abcdefghi!xy", "Password must contain a number."],
    ["Abcdefghi1xy", "Password must contain a symbol."],
  ])("refuses %s with the server's own message and sends nothing", async (password, message) => {
    const result = setup();
    await submitSuccessfully(result);

    act(() => {
      result.current.setAccountPassword(password);
      result.current.setAccountConfirm(password);
    });
    act(() => {
      result.current.handleCreateAccount();
    });

    expect(result.current.accountError).toBe(message);
    expect(requests).toEqual([]);
  });

  it("a password that meets every rule goes to the server", async () => {
    server.use(
      mock("post", "/api/v1/intake/claims").resolve(() =>
        HttpResponse.json(
          { message: "Account created", user: { id: "u1", email: "ada@example.com", name: "Ada Lovelace", role: "job-seeker" } },
          { status: 201 }
        )
      )
    );
    const result = setup();
    await submitSuccessfully(result);

    act(() => {
      result.current.setAccountPassword("Abcdefgh1!xy");
      result.current.setAccountConfirm("Abcdefgh1!xy");
    });
    await act(async () => {
      result.current.handleCreateAccount();
    });

    await waitFor(() => expect(result.current.accountStep).toBe("success"));
    expect(requests).toEqual(["POST /api/v1/intake/claims"]);
  });
});

describe("passwordProblem", () => {
  it("passes a password that meets all five rules", () => {
    expect(passwordProblem("Abcdefgh1!xy")).toBe("");
  });
});

type SignedIn = NonNullable<IntakeFormOptions["onSignedIn"]>;

describe("useIntakeForm - signing in from the account modal (G29)", () => {
  const SUMMARY_USER = { id: "u1", email: "ada@example.com", name: "Ada Lovelace", role: "job-seeker" as const };

  function signInClaim(status: 200 | 403, body: Record<string, unknown>) {
    return mock("post", "/api/v1/intake/claims").resolve(() =>
      HttpResponse.json(body as never, { status })
    );
  }

  function setupWith(onSignedIn: SignedIn) {
    const { result } = renderHook(() => useIntakeForm({ onSignedIn }), {
      wrapper: createWrapper(),
    });
    return result;
  }

  async function signIn(result: ReturnType<typeof setup>) {
    act(() => {
      result.current.setSignInEmail("ada@example.com");
      result.current.setSignInPassword("Correct-horse-1");
    });
    await act(async () => {
      result.current.handleSignInExisting();
    });
  }

  it("hands the opened session to the app, flags and all, so the page stops looking signed out", async () => {
    server.use(
      signInClaim(200, { message: "signed in", csrfToken: "csrf-from-claim", user: SUMMARY_USER }),
      mock("get", "/api/v1/auth/session").resolve(() =>
        HttpResponse.json({
          user: SUMMARY_USER,
          csrf_token: "csrf-from-session",
          flags: { email_confirmed: true, wpl_completed: false, wpll_completed: true, wp_v2_completed: true },
        })
      )
    );
    const onSignedIn = vi.fn<SignedIn>();
    const result = setupWith(onSignedIn);
    await submitSuccessfully(result);

    await signIn(result);

    await waitFor(() => expect(result.current.accountStep).toBe("success"));
    expect(onSignedIn).toHaveBeenCalledTimes(1);
    expect(onSignedIn).toHaveBeenCalledWith(
      expect.objectContaining({ ...SUMMARY_USER, wpll_completed: true, wp_v2_completed: true }),
      "csrf-from-session"
    );
    expect(requests).toEqual(["POST /api/v1/intake/claims", "GET /api/v1/auth/session"]);
  });

  it("falls back to the claim's own user when the probe fails, rather than staying signed out", async () => {
    server.use(
      signInClaim(200, { message: "signed in", csrfToken: "csrf-from-claim", user: SUMMARY_USER }),
      mock("get", "/api/v1/auth/session").resolve(() =>
        HttpResponse.json({ error: "Not authenticated" } as never, { status: 401 })
      )
    );
    const onSignedIn = vi.fn<SignedIn>();
    const result = setupWith(onSignedIn);
    await submitSuccessfully(result);

    await signIn(result);

    await waitFor(() => expect(result.current.accountStep).toBe("success"));
    expect(onSignedIn).toHaveBeenCalledWith(expect.objectContaining(SUMMARY_USER), "csrf-from-claim");
  });

  it("a 403 (email not confirmed) flags the resend path, and resending posts the submission's email", async () => {
    server.use(
      signInClaim(403, { error: "Email not confirmed. Please confirm your email before signing in." }),
      mock("post", "/api/v1/auth/email/verify/resend").resolve(() =>
        HttpResponse.json({ message: "sent" } as never)
      )
    );
    const onSignedIn = vi.fn<SignedIn>();
    const result = setupWith(onSignedIn);
    await submitSuccessfully(result);

    await signIn(result);

    await waitFor(() => expect(result.current.signInNeedsVerification).toBe(true));
    expect(result.current.accountError).toMatch(/not confirmed/i);
    expect(onSignedIn).not.toHaveBeenCalled();

    let sent = false;
    await act(async () => {
      sent = await result.current.resendVerification();
    });
    expect(sent).toBe(true);
    expect(requests).toEqual(["POST /api/v1/intake/claims", "POST /api/v1/auth/email/verify/resend"]);
  });

  it("any other refusal does not offer a code", async () => {
    server.use(
      mock("post", "/api/v1/intake/claims").resolve(() =>
        HttpResponse.json({ error: "Invalid credentials" }, { status: 401 })
      )
    );
    const result = setupWith(vi.fn<SignedIn>());
    await submitSuccessfully(result);

    await signIn(result);

    await waitFor(() => expect(result.current.accountError).toBe("Invalid credentials"));
    expect(result.current.signInNeedsVerification).toBe(false);
  });
});
