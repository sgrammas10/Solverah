/**
 * PostingPanel's status lines, driven by props. The submit-and-poll round trip is
 * covered end to end in CompanyDetailPage.test.tsx; this file pins what each
 * progress state says, including a 503 on submit.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { HttpResponse } from "msw";

import { AuthProvider } from "../../auth";
import { createQueryClient } from "../../../shared/api/queryClient";
import { ApiError } from "../../../shared/api/apiError";
import { server, useApiMocks, recordRequests, signedIn } from "../../../../tests/msw/server";
import { mock } from "../../../../tests/msw/contract";
import { NORTHWIND_ID, POSTING_ID, POSTING_READ, postingStatus } from "../../../../tests/msw/companyLensHandlers";
import PostingPanel, { type PostingProgress } from "./PostingPanel";

useApiMocks();
const { requests } = recordRequests();

function renderPanel(postingId: number | null, progress: PostingProgress, read = null as typeof POSTING_READ | null) {
  const onPostingChange = vi.fn();
  render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <PostingPanel
          companyId={NORTHWIND_ID}
          companyName="Northwind Freight"
          postingId={postingId}
          progress={progress}
          read={read}
          onPostingChange={onPostingChange}
        />
      </AuthProvider>
    </QueryClientProvider>,
  );
  return onPostingChange;
}

describe("PostingPanel", () => {
  beforeEach(() => server.use(signedIn()));

  it("labels both fields", () => {
    renderPanel(null, { status: null, error: null });
    expect(screen.getByLabelText("Role title (optional)")).toBeInTheDocument();
    expect(screen.getByLabelText("The posting's text")).toBeInTheDocument();
  });

  it("says it is reading while the posting is pending", () => {
    renderPanel(POSTING_ID, { status: postingStatus(), error: null });
    expect(screen.getByText(/Reading the posting/)).toBeInTheDocument();
    expect(screen.getByText("Regional Operations Manager")).toBeInTheDocument();
  });

  it("names the disagreements once the read is in", () => {
    renderPanel(POSTING_ID, { status: postingStatus({ status: "scored", has_read: true }), error: null }, POSTING_READ);
    expect(screen.getByText(/They disagree on Collaboration/)).toBeInTheDocument();
  });

  it("says when there is no disagreement", () => {
    renderPanel(
      POSTING_ID,
      { status: postingStatus({ status: "scored", has_read: true }), error: null },
      { ...POSTING_READ, disagreements: [] },
    );
    expect(screen.getByText(/They don't disagree anywhere/)).toBeInTheDocument();
  });

  it("says a stale posting id is gone", () => {
    renderPanel(POSTING_ID, { status: null, error: new ApiError("Job posting not found", { status: 404 }) });
    expect(screen.getByText(/couldn't find that posting any more/)).toBeInTheDocument();
  });

  it("explains a 503 on submit in plain words", async () => {
    server.use(
      mock("post", "/api/v1/me/job-postings").resolve(() =>
        HttpResponse.json({ error: "Posting scoring is not available right now." }, { status: 503 }),
      ),
    );
    const onPostingChange = renderPanel(null, { status: null, error: null });
    await waitFor(() => expect(requests).toContain("GET /api/v1/auth/session"));
    fireEvent.change(screen.getByLabelText("The posting's text"), { target: { value: "Some posting" } });
    fireEvent.click(screen.getByRole("button", { name: "Read this posting" }));
    expect(await screen.findByText(/Reading postings isn't available right now/)).toBeInTheDocument();
    expect(onPostingChange).not.toHaveBeenCalled();
  });
});
