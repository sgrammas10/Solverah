/**
 * The no-probability guard for the companies slice: every state of the company page
 * and every new component, from fixtures, run through `assertNoProbabilityText`
 * (no percentage, no number beside fit/match/score, no number out of 5/10/100, no
 * star). The guard's own positive and negative cases live in
 * matching/noProbability.test.tsx.
 */
import { render, screen } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "../auth";
import { createQueryClient } from "../../shared/api/queryClient";
import { server, useApiMocks, signedIn } from "../../../tests/msw/server";
import {
  LEGACY_PROFILE,
  NORTHWIND_ID,
  POSTING_ID,
  POSTING_READ,
  TRAITS,
  assertNoProbabilityText,
  companyLink,
  companyLinksReply,
  companyProfileReply,
  companyReadReply,
  postingProgresses,
  postingStatus,
  readBody,
  researchRun,
  type CompanyReadResponse,
} from "../../../tests/msw/companyLensHandlers";
import CompanyDetailPage from "./components/CompanyDetailPage";
import TraitReadCard from "./components/TraitReadCard";
import PostingPanel from "./components/PostingPanel";
import TookThisJob from "./components/TookThisJob";
import LegacyProfile from "./components/LegacyProfile";

useApiMocks();

function providers(node: React.ReactNode, path = `/companies/${NORTHWIND_ID}`) {
  return (
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/companies/:id" element={node} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

const empty = { traits: undefined, coverage: null, flags: null, next_step: null };

describe("no probability anywhere on the company page", () => {
  it.each<[string, CompanyReadResponse]>([
    ["ranked", readBody()],
    ["not_enough_evidence", readBody({ state: "not_enough_evidence" })],
    ["ranked, preferences unanswered", readBody({ preferences_answered: false })],
    ["core_required", readBody({ state: "core_required", ...empty })],
    ["not_researched", readBody({ state: "not_researched", ...empty })],
    ["not_researched, run under way", readBody({ state: "not_researched", ...empty, research: researchRun({ status: "running" }) })],
  ])("CompanyDetailPage in state %s, with the legacy profile", async (_label, body) => {
    server.use(signedIn(), companyProfileReply(LEGACY_PROFILE), companyLinksReply([companyLink()]), companyReadReply(body));
    render(providers(<CompanyDetailPage />));
    await screen.findByRole("heading", { level: 1 });
    await screen.findAllByText(/Your read|Start with how you like to work|We haven't researched/);
    const text = document.body.textContent ?? "";
    assertNoProbabilityText(text);
    // The legacy profile's raw numbers must never surface, in any state.
    for (const raw of ["0.82", "3.9", ".82"]) expect(text).not.toContain(raw);
  });

  it("CompanyDetailPage with a posting read beside the company's", async () => {
    server.use(
      signedIn(),
      companyProfileReply(null),
      companyLinksReply([]),
      companyReadReply(readBody(), readBody({ posting: POSTING_READ })),
      postingProgresses([postingStatus({ status: "scored", has_read: true })]),
    );
    render(
      providers(
        <CompanyDetailPage pollTiming={{ initialMs: 10, factor: 1, maxMs: 10 }} />,
        `/companies/${NORTHWIND_ID}?posting=${POSTING_ID}`,
      ),
    );
    await screen.findByText(/They disagree on Collaboration/);
    assertNoProbabilityText(document.body.textContent ?? "");
  });

  it("every component on its own", () => {
    server.use(signedIn(), companyLinksReply([]));
    render(
      providers(
        <>
          {TRAITS.map((trait) => (
            <TraitReadCard
              key={trait.dimension}
              trait={{ ...trait, must_have: true, questions: ["What would I decide on my own?"] }}
              posting={(POSTING_READ.traits ?? []).find((p) => p.dimension === trait.dimension)}
            />
          ))}
          {[
            { status: null, error: null },
            { status: postingStatus(), error: null },
            { status: postingStatus({ status: "failed" }), error: null },
            { status: postingStatus({ status: "scored" }), error: null },
            { status: postingStatus({ status: "scored", has_read: true }), error: null },
          ].map((progress, index) => (
            <PostingPanel
              key={index}
              companyId={NORTHWIND_ID}
              companyName="Northwind Freight"
              postingId={index === 0 ? null : POSTING_ID}
              progress={progress}
              read={POSTING_READ}
              onPostingChange={() => {}}
            />
          ))}
          <TookThisJob companyId={NORTHWIND_ID} companyName="Northwind Freight" />
          <LegacyProfile profile={LEGACY_PROFILE} />
        </>,
      ),
    );
    assertNoProbabilityText(document.body.textContent ?? "");
  });
});
