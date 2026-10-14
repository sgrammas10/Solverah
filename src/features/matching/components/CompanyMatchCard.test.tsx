/**
 * CompanyMatchCard and NotEnoughEvidenceRow, from fixtures. No network: the card is
 * pure presentation of one `MatchEntry`.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import {
  MATCH_GRINDSTONE,
  MATCH_NORTHWIND,
  MATCH_STUDIO,
} from "../../../../tests/msw/companyLensHandlers";
import CompanyMatchCard, { NotEnoughEvidenceRow } from "./CompanyMatchCard";
import type { MatchEntry } from "../useCompanyLens";

function renderCard(entry: MatchEntry) {
  render(
    <MemoryRouter>
      <CompanyMatchCard entry={entry} />
    </MemoryRouter>,
  );
}

describe("CompanyMatchCard", () => {
  it("phrases a known must-have by its pole and its give, with its flag", () => {
    renderCard(MATCH_GRINDSTONE);
    expect(screen.getByText("Pace:")).toBeInTheDocument();
    expect(screen.getByText(/More on the fast side than you prefer, outside your give/)).toBeInTheDocument();
    expect(screen.getByText("Must-have outside your give")).toBeInTheDocument();
    expect(screen.getByText("1 must-have outside your give")).toBeInTheDocument();
  });

  it("reads a mixed must-have as disagreeing evidence, flagged as a risk", () => {
    renderCard(MATCH_NORTHWIND);
    expect(screen.getByText(/The evidence disagrees/)).toBeInTheDocument();
    expect(screen.getByText("Must-have at risk")).toBeInTheDocument();
  });

  it("shows no must-have block when the user has none", () => {
    renderCard({ ...MATCH_NORTHWIND, must_have_reads: [], flags: { must_have_breaks: 0, risks: 0, investigate: 0 } });
    expect(screen.queryByText("Your must-haves")).toBeNull();
  });

  it("links the name and the full read to the company page", () => {
    renderCard(MATCH_NORTHWIND);
    for (const link of screen.getAllByRole("link")) {
      expect(link).toHaveAttribute("href", "/companies/41");
    }
  });
});

describe("NotEnoughEvidenceRow", () => {
  it("says what is missing and gives no rank", () => {
    render(
      <MemoryRouter>
        <ul>
          <NotEnoughEvidenceRow entry={MATCH_STUDIO} />
        </ul>
      </MemoryRouter>,
    );
    expect(screen.getByText(/Clear reads on 2 of 6 traits so far/)).toBeInTheDocument();
    expect(screen.getByText(/Autonomy, Collaboration, Feedback and Decision basis/)).toBeInTheDocument();
    expect(screen.getByText("Explore")).toBeInTheDocument();
  });
});
