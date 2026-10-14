/**
 * The no-probability guard for the matching slice (PRODUCT_DECISIONS §2: no
 * probability reaches a user until outcome data has trained the model).
 *
 * Renders every CompanyLens component in every state from fixtures and fails if the
 * text carries a percentage, a number beside fit/match/score, a number out of
 * 5/10/100, or a star. Coverage counts ("4 of 6") and dates are allowed. The
 * companies slice has the same sweep for the company page.
 *
 * The guard itself is tested first, so a regex that matches nothing cannot pass
 * this file vacuously.
 */
import { render, screen } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { AuthProvider } from "../auth";
import { createQueryClient } from "../../shared/api/queryClient";
import { server, useApiMocks, signedIn } from "../../../tests/msw/server";
import {
  MATCH_GRINDSTONE,
  MATCH_NORTHWIND,
  MATCH_STUDIO,
  assertNoProbabilityText,
  matchesBody,
  matchesReply,
} from "../../../tests/msw/companyLensHandlers";
import CompanyLensPage from "./components/CompanyLensPage";
import CompanyMatchCard, { NotEnoughEvidenceRow } from "./components/CompanyMatchCard";
import ResearchCompanyForm from "./components/ResearchCompanyForm";
import { FlagBadge, MustHaveBadge, NextStepChip } from "./components/LensBits";
import type { MatchesResponse } from "./useCompanyLens";

useApiMocks();

describe("assertNoProbabilityText (the guard)", () => {
  it.each([
    "91% match",
    "Fit: 0.82",
    "match score 7",
    "Scored 82",
    "4.1 / 5",
    "3 out of 10",
    "★★★",
    "about 70 per cent",
    "0.82",
    "Rated 3.9",
    "4.5 stars",
    "rated 4",
  ])("rejects %j", (text) => {
    expect(() => assertNoProbabilityText(text)).toThrow();
  });

  it.each([
    "Based on 4 of 6 traits",
    "From 6 pieces of evidence, dated Jan 2025 to May 2026",
    "1 must-have at risk",
    "Clear reads on 2 of 6 traits so far",
    "Updated 2026-03-02",
    "Thousands of people, 2,000 or so, since 2019.",
    "Dated 18 May 2026",
  ])("allows %j", (text) => {
    expect(() => assertNoProbabilityText(text)).not.toThrow();
  });
});

function withProviders(node: React.ReactNode) {
  return (
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter>{node}</MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

describe("no probability anywhere in CompanyLens", () => {
  it.each<[string, MatchesResponse]>([
    ["ranked", matchesBody()],
    ["ranked, preferences unanswered", matchesBody({ preferences_answered: false })],
    ["core_required", matchesBody({ state: "core_required", data: [] })],
    ["no_companies", matchesBody({ state: "no_companies", data: [] })],
  ])("CompanyLensPage in state %s", async (_label, body) => {
    server.use(signedIn(), matchesReply(body));
    render(withProviders(<CompanyLensPage />));
    await screen.findByRole("heading", { level: 1 });
    await screen.findByText(/Start with how you like to work|No companies yet|Your companies/);
    assertNoProbabilityText(document.body.textContent ?? "");
  });

  it("every card variant and the shared bits", () => {
    server.use(signedIn());
    render(
      withProviders(
        <>
          {[MATCH_NORTHWIND, MATCH_GRINDSTONE].map((entry) => (
            <CompanyMatchCard key={entry.id} entry={entry} />
          ))}
          <ul>
            <NotEnoughEvidenceRow entry={MATCH_STUDIO} />
          </ul>
          <FlagBadge flag="must_have_break" />
          <FlagBadge flag="risk" />
          <FlagBadge flag="investigate" />
          <MustHaveBadge />
          {(["decide", "investigate", "prepare", "explore", "act", "dont_act_yet"] as const).map(
            (category) => (
              <NextStepChip key={category} step={{ category, reason: "Because." }} />
            ),
          )}
          <ResearchCompanyForm />
          <ResearchCompanyForm fixedName="Northwind Freight" />
        </>,
      ),
    );
    assertNoProbabilityText(document.body.textContent ?? "");
  });
});
