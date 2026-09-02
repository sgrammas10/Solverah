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

import { useIntakeForm } from "./useIntakeForm";
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
