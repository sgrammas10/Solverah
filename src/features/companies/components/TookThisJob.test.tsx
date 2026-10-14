/**
 * TookThisJob on its own. The create-then-remove round trip is covered in
 * CompanyDetailPage.test.tsx; this pins the date default and the save error.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { HttpResponse } from "msw";

import { AuthProvider } from "../../auth";
import { createQueryClient } from "../../../shared/api/queryClient";
import { server, useApiMocks, recordRequests, signedIn } from "../../../../tests/msw/server";
import { mock } from "../../../../tests/msw/contract";
import { NORTHWIND_ID, companyLink, companyLinksReply } from "../../../../tests/msw/companyLensHandlers";
import TookThisJob from "./TookThisJob";

useApiMocks();
const { requests } = recordRequests();

function renderIt() {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <TookThisJob companyId={NORTHWIND_ID} companyName="Northwind Freight" />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

describe("TookThisJob", () => {
  it("defaults the labelled start date to today", async () => {
    server.use(signedIn(), companyLinksReply([]));
    renderIt();
    const input = (await screen.findByLabelText("Start date")) as HTMLInputElement;
    expect(input.value).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("treats an ended link as history and offers the form again", async () => {
    server.use(signedIn(), companyLinksReply([companyLink({ ended_on: "2027-01-31" })]));
    renderIt();
    expect(await screen.findByText(/You worked at Northwind Freight from/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "I took this job" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove this" })).toBeNull();
  });

  it("warns that a new link replaces the open one at another company", async () => {
    server.use(
      signedIn(),
      companyLinksReply([
        companyLink({ id: 9, company_id: 7, company: { id: 7, name: "Grindstone Corp", slug: "grindstone-corp", industry: null } }),
      ]),
    );
    renderIt();
    expect(await screen.findByText(/This replaces the job you recorded at Grindstone Corp/)).toBeInTheDocument();
  });

  it("I left this job: patches the last day, refetches, and reads the link as past", async () => {
    let links = [companyLink({ started_on: "2026-11-02" })];
    let patched: unknown = null;
    server.use(
      signedIn(),
      mock("get", "/api/v1/me/company-links").resolve(() => HttpResponse.json({ data: links }, { status: 200 })),
      mock("patch", "/api/v1/me/company-links/{link_id}").resolve(async ({ request, params }) => {
        patched = { id: params.link_id, body: await request.json() };
        links = [companyLink({ started_on: "2026-11-02", ended_on: "2027-03-31" })];
        return HttpResponse.json({ link: links[0] }, { status: 200 });
      }),
    );
    renderIt();
    expect(await screen.findByText(/You took a job at Northwind Freight, starting/)).toBeInTheDocument();
    await waitFor(() => expect(requests).toContain("GET /api/v1/auth/session"));

    fireEvent.click(screen.getByRole("button", { name: "I left this job" }));
    const lastDay = screen.getByLabelText("Last day") as HTMLInputElement;
    expect(lastDay.min).toBe("2026-11-02");
    fireEvent.change(lastDay, { target: { value: "2027-03-31" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(/You worked at Northwind Freight from/)).toBeInTheDocument();
    expect(patched).toEqual({ id: "5", body: { ended_on: "2027-03-31" } });
    expect(requests.filter((r) => r === "GET /api/v1/me/company-links").length).toBeGreaterThanOrEqual(2);
    // Past, so the "took this job" form is back and the open-link actions are gone.
    expect(screen.getByRole("button", { name: "I took this job" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "I left this job" })).toBeNull();
  });

  it("explains a last day before the start date (422)", async () => {
    server.use(
      signedIn(),
      companyLinksReply([companyLink({ started_on: "2026-11-02" })]),
      mock("patch", "/api/v1/me/company-links/{link_id}").resolve(() =>
        HttpResponse.json(
          { type: "https://solverah.com/errors/validation", title: "Validation failed", status: 422, detail: "ended_on is before started_on" },
          { status: 422 },
        ),
      ),
    );
    renderIt();
    await screen.findByText(/You took a job at Northwind Freight/);
    await waitFor(() => expect(requests).toContain("GET /api/v1/auth/session"));
    fireEvent.click(screen.getByRole("button", { name: "I left this job" }));
    // A date the input's own `min` allows (the browser blocks an earlier one before
    // any request), refused by the server anyway.
    fireEvent.change(screen.getByLabelText("Last day"), { target: { value: "2027-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText(/on or after your start date/)).toBeInTheDocument();
  });

  it("says when the link could not be saved", async () => {
    server.use(
      signedIn(),
      companyLinksReply([]),
      mock("post", "/api/v1/me/company-links").resolve(() =>
        HttpResponse.json({ error: "Company not found" }, { status: 404 }),
      ),
    );
    renderIt();
    await screen.findByLabelText("Start date");
    await waitFor(() => expect(requests).toContain("GET /api/v1/auth/session"));
    fireEvent.click(screen.getByRole("button", { name: "I took this job" }));
    expect(await screen.findByText("We couldn't save that. Please try again.")).toBeInTheDocument();
  });
});
