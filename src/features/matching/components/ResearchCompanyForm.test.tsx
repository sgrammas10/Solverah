/**
 * ResearchCompanyForm -- POST /companies/research, then poll the run, over a real
 * (MSW) network with the real AuthProvider. "Polling stops" is a claim about
 * requests on the wire, so it is counted there (recordRequests), not on a mock.
 *
 * A short real poll schedule instead of fake timers, for the reason
 * useScoringJob.test.tsx records.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AuthProvider } from "../../auth";
import { createQueryClient } from "../../../shared/api/queryClient";
import { server, useApiMocks, recordRequests, signedIn } from "../../../../tests/msw/server";
import {
  DAILY_LIMIT_PROBLEM,
  assertNoProbabilityText,
  researchAccepted,
  researchProgresses,
  researchRefused,
  researchRun,
} from "../../../../tests/msw/companyLensHandlers";
import ResearchCompanyForm from "./ResearchCompanyForm";
import type { PollTiming } from "../usePoll";

useApiMocks();
const { requests } = recordRequests();

const FAST: PollTiming = { initialMs: 15, factor: 1, maxMs: 15 };
const polls = () => requests.filter((r) => r.startsWith("GET /api/v1/companies/research/"));
const posts = () => requests.filter((r) => r === "POST /api/v1/companies/research");

function renderForm(props: { fixedName?: string } = {}) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter>
          <ResearchCompanyForm pollTiming={FAST} {...props} />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

async function submit(name: string) {
  // The session probe must land first: the POST carries its CSRF token.
  await waitFor(() => expect(requests).toContain("GET /api/v1/auth/session"));
  fireEvent.change(screen.getByLabelText("Research a company"), { target: { value: name } });
  fireEvent.click(screen.getByRole("button", { name: "Research" }));
}

describe("ResearchCompanyForm", () => {
  it("labels the input and announces progress in a polite live region", () => {
    server.use(signedIn());
    renderForm();
    expect(screen.getByLabelText("Research a company")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
  });

  it("posts the name, polls queued -> running -> done, then offers the read", async () => {
    server.use(signedIn(), researchAccepted(), researchProgresses(["running", "done"]));
    renderForm();
    await submit("Acme Logistics");

    expect(await screen.findByText(/Acme Logistics is in the queue/)).toBeInTheDocument();
    expect(await screen.findByText(/Researching Acme Logistics/)).toBeInTheDocument();
    expect(await screen.findByText("Research on Acme Logistics is finished.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the read on Acme Logistics" })).toHaveAttribute(
      "href",
      "/companies/60",
    );

    // Done is terminal: no poll after the one that saw it.
    const seen = polls().length;
    await new Promise((resolve) => setTimeout(resolve, 80));
    expect(polls().length).toBe(seen);
    assertNoProbabilityText(document.body.textContent ?? "");
  });

  it("does not poll at all when the POST answers with a finished cached run", async () => {
    server.use(signedIn(), researchAccepted(researchRun({ status: "done" }), true));
    renderForm();
    await submit("Acme Logistics");
    expect(await screen.findByText(/was already researched/)).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(polls()).toEqual([]);
  });

  it("says plainly when the daily research limit is reached (429)", async () => {
    server.use(signedIn(), researchRefused(429, DAILY_LIMIT_PROBLEM));
    renderForm();
    await submit("Acme Logistics");
    expect(await screen.findByText(/five new companies today, which is the daily limit/)).toBeInTheDocument();
    expect(polls()).toEqual([]);
  });

  it("tells a burst-limited 429 apart from the daily limit", async () => {
    server.use(
      signedIn(),
      researchRefused(429, { type: "https://solverah.com/errors/rate_limited", title: "Too many requests", status: 429 }),
    );
    renderForm();
    await submit("Acme Logistics");
    expect(await screen.findByText(/a lot of requests in a short time/)).toBeInTheDocument();
  });

  it("says research is temporarily unavailable on a 503", async () => {
    server.use(signedIn(), researchRefused(503, { error: "Company research is not available right now." }));
    renderForm();
    await submit("Acme Logistics");
    expect(await screen.findByText(/isn't available right now/)).toBeInTheDocument();
  });

  it("reports a failed run and stops polling", async () => {
    server.use(signedIn(), researchAccepted(), researchProgresses(["failed"]));
    renderForm();
    await submit("Acme Logistics");
    expect(await screen.findByText(/couldn't finish researching Acme Logistics/)).toBeInTheDocument();
    const seen = polls().length;
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(polls().length).toBe(seen);
  });

  it("asks for a name instead of sending an empty one", async () => {
    server.use(signedIn());
    renderForm();
    await waitFor(() => expect(requests).toContain("GET /api/v1/auth/session"));
    fireEvent.click(screen.getByRole("button", { name: "Research" }));
    expect(await screen.findByText("Enter a company name to research.")).toBeInTheDocument();
    expect(posts()).toEqual([]);
  });

  it("stops polling when the page unmounts", async () => {
    server.use(signedIn(), researchAccepted(), researchProgresses(["queued"]));
    const view = renderForm();
    await submit("Acme Logistics");
    await waitFor(() => expect(polls().length).toBeGreaterThan(0));
    view.unmount();
    const seen = polls().length;
    await new Promise((resolve) => setTimeout(resolve, 80));
    expect(polls().length).toBe(seen);
  });

  it("with a fixed name shows one button and posts that name", async () => {
    server.use(signedIn(), researchAccepted(researchRun({ status: "done" }), true));
    renderForm({ fixedName: "Northwind Freight" });
    await waitFor(() => expect(requests).toContain("GET /api/v1/auth/session"));
    expect(screen.queryByLabelText("Research a company")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Research Northwind Freight" }));
    await waitFor(() => expect(posts()).toHaveLength(1));
  });
});
