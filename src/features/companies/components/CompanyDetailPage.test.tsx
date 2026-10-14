/**
 * CompanyDetailPage -- "Your read" over a real (MSW) network.
 *
 * Rewritten for the six-trait build (2026-10-13). The old page read a `fit_score`
 * out of router state and printed it as a percentage; the read now comes from
 * `GET /companies/{id}/read`, which carries no score, and the legacy profile sits
 * below it only when it has content.
 */
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { HttpResponse } from "msw";

import { AuthProvider } from "../../auth";
import { createQueryClient } from "../../../shared/api/queryClient";
import { server, useApiMocks, recordRequests, signedIn } from "../../../../tests/msw/server";
import { mock } from "../../../../tests/msw/contract";
import {
  LEGACY_PROFILE,
  NORTHWIND_ID,
  POSTING_ID,
  POSTING_READ,
  assertNoProbabilityText,
  companyLink,
  companyLinksReply,
  companyProfileReply,
  companyReadReply,
  companyReadSequence,
  postingAccepted,
  postingProgresses,
  postingStatus,
  readBody,
  researchAccepted,
  researchProgresses,
  researchRun,
} from "../../../../tests/msw/companyLensHandlers";
import CompanyDetailPage from "./CompanyDetailPage";

useApiMocks();
const { requests } = recordRequests();

const FAST = { initialMs: 15, factor: 1, maxMs: 15 };
const readCalls = () => requests.filter((r) => r === `GET /api/v1/companies/${NORTHWIND_ID}/read`);
const readUrls: string[] = [];

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location">{location.pathname + location.search}</p>;
}

function renderPage(path = `/companies/${NORTHWIND_ID}`) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route
              path="/companies/:id"
              element={
                <>
                  <CompanyDetailPage pollTiming={FAST} />
                  <LocationProbe />
                </>
              }
            />
            <Route path="/work-pulse" element={<p>Work Pulse page</p>} />
            <Route path="/company-lens" element={<p>CompanyLens page</p>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

// The query string of every read request (recordRequests keeps only the path).
const onReadStart = ({ request }: { request: Request }) => {
  if (request.url.includes("/read")) readUrls.push(new URL(request.url).search);
};
beforeAll(() => server.events.on("request:start", onReadStart));
beforeEach(() => {
  readUrls.length = 0;
});
afterAll(() => server.events.removeListener("request:start", onReadStart));

function baseHandlers() {
  return [signedIn(), companyProfileReply(null), companyLinksReply([])];
}

const bodyText = () => document.body.textContent ?? "";

describe("CompanyDetailPage - the read", () => {
  it("leads with Your read: coverage, next step, size note, one card per trait", async () => {
    server.use(...baseHandlers(), companyReadReply());
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Northwind Freight" })).toBeInTheDocument();
    const summary = screen.getByRole("region", { name: "Your read" });
    expect(within(summary).getByText(/Based on 4 of 6 traits/)).toBeInTheDocument();
    expect(within(summary).getByText("Investigate")).toBeInTheDocument();
    expect(within(summary).getByText(/Thousands of people/)).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(6);
    assertNoProbabilityText(bodyText());
  });

  it("shows a known trait's direction, give, evidence and at most three paraphrases", async () => {
    server.use(...baseHandlers(), companyReadReply());
    renderPage();
    const pace = await screen.findByRole("article", { name: "Pace" });
    expect(within(pace).getByText("About where you prefer.")).toBeInTheDocument();
    expect(within(pace).getByText(/From 4 pieces of evidence, dated .+ to .+, from employee review and news/)).toBeInTheDocument();
    expect(within(pace).getAllByText(/^Pace evidence \d/)).toHaveLength(3);
    expect(within(pace).getAllByRole("link", { name: /Source/ })[0]).toHaveAttribute("target", "_blank");

    const collaboration = screen.getByRole("article", { name: "Collaboration" });
    expect(within(collaboration).getByText("More on the collective side than you prefer, inside your give.")).toBeInTheDocument();
  });

  it("shows a mixed must-have's two ends side by side, its explanation and interview questions", async () => {
    server.use(...baseHandlers(), companyReadReply());
    renderPage();
    const autonomy = await screen.findByRole("article", { name: "Autonomy" });
    expect(within(autonomy).getByText("Evidence disagrees")).toBeInTheDocument();
    expect(within(autonomy).getByText("Must-have")).toBeInTheDocument();
    expect(within(autonomy).getByText("Must-have at risk")).toBeInTheDocument();
    expect(within(autonomy).getByText(/different parts of the company describe different things/)).toBeInTheDocument();
    expect(within(autonomy).getByText("Evidence on the directed side")).toBeInTheDocument();
    expect(within(autonomy).getByText("Evidence on the self-directed side")).toBeInTheDocument();
    expect(within(autonomy).getByText(/Warehouse staff describe tight procedures/)).toBeInTheDocument();
    expect(within(autonomy).getByText(/Office staff describe owning their projects/)).toBeInTheDocument();
    expect(within(autonomy).getByText(/Regional sites/)).toBeInTheDocument();
    expect(within(autonomy).getByText("Ask in your interview")).toBeInTheDocument();
    expect(within(autonomy).getByText(/Who proposed it, and who had to approve it/)).toBeInTheDocument();
  });

  it("shows an unknown trait's explanation and no read", async () => {
    server.use(...baseHandlers(), companyReadReply());
    renderPage();
    const feedback = await screen.findByRole("article", { name: "Feedback" });
    expect(within(feedback).getByText(/We found too little on how feedback works here/)).toBeInTheDocument();
    expect(within(feedback).queryByText(/than you prefer/)).toBeNull();
  });

  it("explains a not-enough-evidence read instead of placing it", async () => {
    server.use(...baseHandlers(), companyReadReply(readBody({ state: "not_enough_evidence", next_step: { category: "explore", reason: "Too little to go on." } })));
    renderPage();
    expect(await screen.findByText(/too few clear reads to say how this company compares/)).toBeInTheDocument();
    expect(screen.getByText("Explore")).toBeInTheDocument();
  });

  it("links to the tolerance step when preferences are unanswered", async () => {
    server.use(...baseHandlers(), companyReadReply(readBody({ preferences_answered: false })));
    renderPage();
    expect(await screen.findByRole("link", { name: "Tell us how much give you have" })).toHaveAttribute("href", "/trait-preferences");
  });

  it("shows an error with a working retry", async () => {
    let call = 0;
    server.use(
      ...baseHandlers(),
      mock("get", "/api/v1/companies/{company_id}/read").resolve(() => {
        call += 1;
        return call === 1
          ? HttpResponse.json({ error: "Company not found" }, { status: 404 })
          : HttpResponse.json(readBody(), { status: 200 });
      }),
    );
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("region", { name: "Your read" })).toBeInTheDocument();
  });
});

describe("CompanyDetailPage - other states", () => {
  it("core_required asks for Work Pulse", async () => {
    server.use(...baseHandlers(), companyReadReply(readBody({ state: "core_required", traits: undefined, coverage: null, flags: null, next_step: null })));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Take Work Pulse" }));
    expect(await screen.findByText("Work Pulse page")).toBeInTheDocument();
  });

  it("not_researched offers research and shows the read once it is done", async () => {
    const notResearched = readBody({ state: "not_researched", traits: undefined, coverage: null, flags: null, next_step: null });
    server.use(
      ...baseHandlers(),
      companyReadSequence([notResearched, readBody()]),
      researchAccepted(researchRun({ company_id: NORTHWIND_ID, company: null })),
      researchProgresses(["done"], researchRun({ company_id: NORTHWIND_ID, company: null })),
    );
    renderPage();
    expect(await screen.findByText("We haven't researched Northwind Freight yet")).toBeInTheDocument();
    await waitFor(() => expect(requests).toContain("GET /api/v1/auth/session"));
    fireEvent.click(screen.getByRole("button", { name: "Research Northwind Freight" }));
    expect(await screen.findByRole("region", { name: "Your read" })).toBeInTheDocument();
    expect(readCalls().length).toBeGreaterThanOrEqual(2);
  });

  it("not_researched with a run under way says so and offers a re-check", async () => {
    server.use(
      ...baseHandlers(),
      companyReadReply(readBody({ state: "not_researched", traits: undefined, research: researchRun({ status: "running" }) })),
    );
    renderPage();
    expect(await screen.findByText(/Research on this company is under way/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check again" })).toBeInTheDocument();
  });
});

describe("CompanyDetailPage - the legacy profile", () => {
  it("sits below the read when it has content, without its old numbers", async () => {
    server.use(signedIn(), companyLinksReply([]), companyProfileReply(LEGACY_PROFILE), companyReadReply());
    renderPage();
    const legacy = await screen.findByRole("region", { name: "Background research" });
    expect(within(legacy).getByText(/practical and steady/)).toBeInTheDocument();
    expect(within(legacy).getByText(/Stable hours/)).toBeInTheDocument();
    expect(screen.getByText(/Logistics · 2,000 people · Leeds/)).toBeInTheDocument();
    // The rating and the retired culture-score bar are not drawn.
    expect(bodyText()).not.toContain("3.9");
    expect(bodyText()).not.toMatch(/Empathy/);
    // Below the read: the read's heading comes first in document order.
    const read = screen.getByRole("region", { name: "Your read" });
    expect(read.compareDocumentPosition(legacy) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("is absent when the profile is empty", async () => {
    server.use(signedIn(), companyLinksReply([]), companyProfileReply({ overview: { name: "X" } }), companyReadReply());
    renderPage();
    await screen.findByRole("region", { name: "Your read" });
    expect(screen.queryByRole("region", { name: "Background research" })).toBeNull();
  });
});

describe("CompanyDetailPage - paste a job posting", () => {
  async function paste() {
    await screen.findByRole("region", { name: "Your read" });
    await waitFor(() => expect(requests).toContain("GET /api/v1/auth/session"));
    fireEvent.change(screen.getByLabelText("Role title (optional)"), { target: { value: "Regional Operations Manager" } });
    fireEvent.change(screen.getByLabelText("The posting's text"), { target: { value: "Own the regional process end to end." } });
    fireEvent.click(screen.getByRole("button", { name: "Read this posting" }));
  }

  it("polls until the posting has a read, then shows it beside the company's with the disagreement", async () => {
    let body: unknown = null;
    server.use(
      ...baseHandlers(),
      companyReadReply(readBody(), readBody({ posting: POSTING_READ })),
      mock("post", "/api/v1/me/job-postings").resolve(async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ posting: postingStatus() }, { status: 202 });
      }),
      postingProgresses([postingStatus(), postingStatus({ status: "scored", has_read: true })]),
    );
    renderPage();
    await paste();

    await waitFor(() =>
      expect(body).toEqual({
        company_id: NORTHWIND_ID,
        text: "Own the regional process end to end.",
        title: "Regional Operations Manager",
      }),
    );
    expect(await screen.findByText(/Reading the posting/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("location").textContent).toContain(`posting=${POSTING_ID}`));

    expect(await screen.findByText(/They disagree on Collaboration/)).toBeInTheDocument();
    expect(readUrls).toContain(`?posting_id=${POSTING_ID}`);
    const collaboration = screen.getByRole("article", { name: "Collaboration" });
    expect(
      within(collaboration).getByText(
        "This posting describes collaboration as more on the solo side than the company evidence does.",
      ),
    ).toBeInTheDocument();
    const autonomy = screen.getByRole("article", { name: "Autonomy" });
    expect(within(autonomy).getByText(/owns the regional process end to end/)).toBeInTheDocument();
    expect(within(autonomy).queryByText(/than the company evidence does/)).toBeNull();
    assertNoProbabilityText(bodyText());
  });

  it("says so when the posting only lists requirements (every trait abstained)", async () => {
    server.use(
      ...baseHandlers(),
      companyReadReply(),
      postingAccepted(),
      postingProgresses([postingStatus({ status: "scored", has_read: false })]),
    );
    renderPage();
    await paste();
    expect(await screen.findByText(/says nothing clear about how the work runs/)).toBeInTheDocument();
    expect(readUrls.every((search) => !search.includes("posting_id"))).toBe(true);
    expect(screen.queryByText(/than the company evidence does/)).toBeNull();
  });

  it("reports a failed posting and lets the user paste another", async () => {
    server.use(
      ...baseHandlers(),
      companyReadReply(),
      postingAccepted(),
      postingProgresses([postingStatus({ status: "failed" })]),
    );
    renderPage();
    await paste();
    expect(await screen.findByText(/couldn't read that posting/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Paste a different posting" }));
    expect(await screen.findByLabelText("The posting's text")).toBeInTheDocument();
    expect(screen.getByTestId("location").textContent).not.toContain("posting=");
  });

  it("asks for text instead of sending an empty posting", async () => {
    server.use(...baseHandlers(), companyReadReply());
    renderPage();
    await screen.findByRole("region", { name: "Your read" });
    fireEvent.click(screen.getByRole("button", { name: "Read this posting" }));
    expect(await screen.findByText("Paste the posting's text first.")).toBeInTheDocument();
    expect(requests).not.toContain("POST /api/v1/me/job-postings");
  });

  it("keeps a posting from the URL across a reload", async () => {
    server.use(
      ...baseHandlers(),
      companyReadReply(readBody(), readBody({ posting: POSTING_READ })),
      postingProgresses([postingStatus({ status: "scored", has_read: true })]),
    );
    renderPage(`/companies/${NORTHWIND_ID}?posting=${POSTING_ID}`);
    expect(await screen.findByText(/They disagree on Collaboration/)).toBeInTheDocument();
  });
});

describe("CompanyDetailPage - I took this job", () => {
  it("posts a link with the chosen date, then shows it and removes it", async () => {
    let links = [] as ReturnType<typeof companyLink>[];
    let posted: unknown = null;
    server.use(
      signedIn(),
      companyProfileReply(null),
      companyReadReply(),
      mock("get", "/api/v1/me/company-links").resolve(() => HttpResponse.json({ data: links }, { status: 200 })),
      mock("post", "/api/v1/me/company-links").resolve(async ({ request }) => {
        posted = await request.json();
        links = [companyLink({ started_on: "2026-11-02" })];
        return HttpResponse.json({ link: links[0] }, { status: 201 });
      }),
      mock("delete", "/api/v1/me/company-links/{link_id}").resolve(() => {
        links = [];
        return HttpResponse.json({ ok: true }, { status: 200 });
      }),
    );
    renderPage();
    const section = await screen.findByRole("region", { name: "Did you take a job here?" });
    await waitFor(() => expect(requests).toContain("GET /api/v1/auth/session"));
    fireEvent.change(within(section).getByLabelText("Start date"), { target: { value: "2026-11-02" } });
    fireEvent.click(within(section).getByRole("button", { name: "I took this job" }));

    expect(await within(section).findByText(/You took a job at Northwind Freight, starting/)).toBeInTheDocument();
    expect(posted).toEqual({ company_id: NORTHWIND_ID, started_on: "2026-11-02" });

    fireEvent.click(within(section).getByRole("button", { name: "Remove this" }));
    expect(await within(section).findByLabelText("Start date")).toBeInTheDocument();
    expect(requests).toContain("DELETE /api/v1/me/company-links/5");
  });

  it("only treats a link to this company as taken", async () => {
    server.use(
      signedIn(),
      companyProfileReply(null),
      companyReadReply(),
      companyLinksReply([companyLink({ company_id: 999 })]),
    );
    renderPage();
    const section = await screen.findByRole("region", { name: "Did you take a job here?" });
    expect(await within(section).findByRole("button", { name: "I took this job" })).toBeInTheDocument();
  });
});
