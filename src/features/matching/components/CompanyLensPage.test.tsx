/**
 * CompanyLensPage -- the six-trait list over a real (MSW) network.
 *
 * Rewritten for the six-trait build (2026-10-13): the old page rendered
 * `fit_score` as "91% match" from two `?order=` walks. The API now carries no
 * score at all, so every state here is also run through `assertNoProbabilityText`.
 */
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "../../auth";
import { createQueryClient } from "../../../shared/api/queryClient";
import { server, useApiMocks, recordRequests, signedIn } from "../../../../tests/msw/server";
import { mock } from "../../../../tests/msw/contract";
import {
  MATCH_GRINDSTONE,
  MATCH_NORTHWIND,
  MATCH_STUDIO,
  assertNoProbabilityText,
  matchesBody,
  matchesReply,
  researchAccepted,
  researchProgresses,
} from "../../../../tests/msw/companyLensHandlers";
import CompanyLensPage from "./CompanyLensPage";

useApiMocks();
const { requests } = recordRequests();

const matchCalls = () => requests.filter((r) => r === "GET /api/v1/me/matches");

function renderPage() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={["/company-lens"]}>
          <Routes>
            <Route
              path="/company-lens"
              element={<CompanyLensPage researchPollTiming={{ initialMs: 15, factor: 1, maxMs: 15 }} />}
            />
            <Route path="/work-pulse" element={<p>Work Pulse page</p>} />
            <Route path="/intelligence" element={<p>Intelligence page</p>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

const bodyText = () => document.body.textContent ?? "";

describe("CompanyLensPage - loading and errors", () => {
  it("shows a loading state first", () => {
    server.use(
      signedIn(),
      mock("get", "/api/v1/me/matches").resolve(() => new Promise(() => {})),
    );
    renderPage();
    expect(screen.getByText(/Reading companies against your answers/)).toBeInTheDocument();
  });

  it("shows an error with a working retry", async () => {
    let call = 0;
    server.use(
      signedIn(),
      mock("get", "/api/v1/me/matches").resolve(({ request }) => {
        void request;
        call += 1;
        return call === 1
          ? Response.json({ error: "nope" }, { status: 404 })
          : Response.json(matchesBody(), { status: 200 });
      }),
    );
    renderPage();
    expect(await screen.findByText(/couldn't load CompanyLens/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Northwind Freight")).toBeInTheDocument();
  });
});

describe("CompanyLensPage - core_required", () => {
  it("invites the user to Work Pulse without blaming them", async () => {
    server.use(signedIn(), matchesReply(matchesBody({ state: "core_required", data: [], total_companies: 0 })));
    renderPage();
    expect(await screen.findByText("Start with how you like to work")).toBeInTheDocument();
    expect(bodyText()).not.toMatch(/you (haven't|have not|didn't|failed)|unlock|locked/i);
    // No research input until there is something to read companies against.
    expect(screen.queryByLabelText("Research a company")).toBeNull();
    assertNoProbabilityText(bodyText());

    fireEvent.click(screen.getByRole("button", { name: "Take Work Pulse" }));
    expect(await screen.findByText("Work Pulse page")).toBeInTheDocument();
  });
});

describe("CompanyLensPage - no_companies", () => {
  it("invites the user to research a company", async () => {
    server.use(signedIn(), matchesReply(matchesBody({ state: "no_companies", data: [], total_companies: 0 })));
    renderPage();
    expect(await screen.findByText("No companies yet")).toBeInTheDocument();
    expect(screen.getByLabelText("Research a company")).toBeInTheDocument();
    assertNoProbabilityText(bodyText());
  });
});

describe("CompanyLensPage - ranked", () => {
  it("renders ranked cards in the API's order, then the not-enough-evidence section", async () => {
    server.use(signedIn(), matchesReply());
    renderPage();
    await screen.findByText("Northwind Freight");

    const ranked = screen.getByRole("region", { name: "Your companies" });
    const names = within(ranked)
      .getAllByRole("article")
      .map((card) => card.getAttribute("aria-label"));
    expect(names).toEqual([MATCH_NORTHWIND.name, MATCH_GRINDSTONE.name]);

    const thin = screen.getByRole("region", { name: "Not enough evidence yet" });
    expect(within(thin).getByText(MATCH_STUDIO.name as string)).toBeInTheDocument();
    expect(within(thin).getByText(/Too little evidence on Autonomy, Collaboration, Feedback and Decision basis/)).toBeInTheDocument();
    expect(within(thin).getByText(/Clear reads on 2 of 6 traits/)).toBeInTheDocument();
    // An unranked company is not placed among the ranked ones.
    expect(within(ranked).queryByText(MATCH_STUDIO.name as string)).toBeNull();
  });

  it("shows coverage, the next step with its reason, must-have reads, flags and size", async () => {
    server.use(signedIn(), matchesReply());
    renderPage();
    const card = await screen.findByRole("article", { name: "Northwind Freight" });
    expect(within(card).getByText(/Based on 4 of 6 traits/)).toBeInTheDocument();
    expect(within(card).getByText("Investigate")).toBeInTheDocument();
    expect(within(card).getByText(MATCH_NORTHWIND.next_step.reason)).toBeInTheDocument();
    expect(within(card).getByText(/The evidence disagrees/)).toBeInTheDocument();
    expect(within(card).getByText("Must-have at risk")).toBeInTheDocument();
    expect(within(card).getByText("1 must-have at risk")).toBeInTheDocument();
    expect(within(card).getByText(/Thousands of people/)).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Northwind Freight" })).toHaveAttribute("href", "/companies/41");

    const broken = screen.getByRole("article", { name: "Grindstone Corp" });
    expect(within(broken).getByText(/More on the fast side than you prefer, outside your give/)).toBeInTheDocument();
    expect(within(broken).getByText("Must-have outside your give")).toBeInTheDocument();
    expect(within(broken).getByText(/updating the research/)).toBeInTheDocument();

    assertNoProbabilityText(bodyText());
  });

  it("links gently to the tolerance step when preferences are unanswered", async () => {
    server.use(signedIn(), matchesReply(matchesBody({ preferences_answered: false })));
    renderPage();
    const link = await screen.findByRole("link", { name: "Tell us how much give you have" });
    expect(link).toHaveAttribute("href", "/trait-preferences");
  });

  it("does not show the tolerance nudge once preferences are answered", async () => {
    server.use(signedIn(), matchesReply());
    renderPage();
    await screen.findByText("Northwind Freight");
    expect(screen.queryByRole("link", { name: "Tell us how much give you have" })).toBeNull();
  });

  it("walks the cursor with Show more", async () => {
    const cursors: (string | null)[] = [];
    server.use(
      signedIn(),
      mock("get", "/api/v1/me/matches").resolve(({ request }) => {
        const cursor = new URL(request.url).searchParams.get("cursor");
        cursors.push(cursor);
        const body = cursor
          ? matchesBody({ data: [MATCH_STUDIO], next_cursor: null })
          : matchesBody({ data: [MATCH_NORTHWIND], next_cursor: "page-2" });
        return Response.json(body, { status: 200 });
      }),
    );
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Show more companies" }));
    expect(await screen.findByText(MATCH_STUDIO.name as string)).toBeInTheDocument();
    expect(cursors).toEqual([null, "page-2"]);
    expect(screen.queryByRole("button", { name: "Show more companies" })).toBeNull();
  });

  it("refreshes the list when a research run finishes", async () => {
    server.use(signedIn(), matchesReply(), researchAccepted(), researchProgresses(["done"]));
    renderPage();
    await screen.findByText("Northwind Freight");
    expect(matchCalls()).toHaveLength(1);

    fireEvent.change(screen.getByLabelText("Research a company"), {
      target: { value: "Acme Logistics" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Research" }));
    expect(await screen.findByText("Research on Acme Logistics is finished.")).toBeInTheDocument();
    await waitFor(() => expect(matchCalls().length).toBeGreaterThanOrEqual(2));
  });
});
