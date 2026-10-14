/**
 * TraitReadCard from fixtures: the three statuses, the must-have questions, the
 * posting row. Pure presentation, no network.
 */
import { render, screen, within } from "@testing-library/react";

import { POSTING_READ, TRAITS } from "../../../../tests/msw/companyLensHandlers";
import TraitReadCard, { EvidenceList } from "./TraitReadCard";
import type { TraitRead } from "../useCompanyRead";

const byKey = (key: TraitRead["dimension"]) => TRAITS.find((t) => t.dimension === key) as TraitRead;
const postingFor = (key: TraitRead["dimension"]) =>
  (POSTING_READ.traits ?? []).find((t) => t.dimension === key) ?? null;

describe("TraitReadCard", () => {
  it("names the trait's two poles", () => {
    render(<TraitReadCard trait={byKey("feedback")} />);
    expect(screen.getByText("From sparse and gentle to frequent and blunt")).toBeInTheDocument();
  });

  it("reads a known trait outside the user's give", () => {
    render(<TraitReadCard trait={byKey("innovation")} />);
    expect(
      screen.getByText("More on the refine what exists side than you prefer, outside your give."),
    ).toBeInTheDocument();
    expect(screen.getByText("Clear read")).toBeInTheDocument();
    // No dates on the record: the summary still reads, without a range.
    expect(screen.getByText("From 3 pieces of evidence, from news.")).toBeInTheDocument();
  });

  it("asks interview questions for a must-have that is unknown", () => {
    const trait: TraitRead = {
      ...byKey("feedback"),
      must_have: true,
      flag: "investigate",
      questions: ["How would I hear that something I did missed the mark?"],
    };
    render(<TraitReadCard trait={trait} />);
    expect(screen.getByText("Must-have to find out about")).toBeInTheDocument();
    expect(screen.getByText("Ask in your interview")).toBeInTheDocument();
    expect(screen.getByText(/missed the mark/)).toBeInTheDocument();
  });

  it("asks no questions for a trait that is not a must-have", () => {
    render(<TraitReadCard trait={{ ...byKey("feedback"), questions: ["Should not show"] }} />);
    expect(screen.queryByText("Ask in your interview")).toBeNull();
  });

  it("does not draw the posting row without a posting", () => {
    render(<TraitReadCard trait={byKey("collaboration")} />);
    expect(screen.queryByText(/Your pasted posting/)).toBeNull();
  });

  it("calls out a posting that disagrees, and names the pole it leans to", () => {
    render(<TraitReadCard trait={byKey("collaboration")} posting={postingFor("collaboration")} />);
    const row = screen.getByText(/Your pasted posting/).parentElement as HTMLElement;
    expect(within(row).getByText("More on the solo side than you prefer, inside your give")).toBeInTheDocument();
    expect(
      within(row).getByText("This posting describes collaboration as more on the solo side than the company evidence does."),
    ).toBeInTheDocument();
  });

  it("says a posting is silent on a trait it does not cover", () => {
    render(<TraitReadCard trait={byKey("pace")} posting={postingFor("pace")} />);
    expect(screen.getByText("The posting says nothing clear about this.")).toBeInTheDocument();
  });
});

describe("EvidenceList", () => {
  it("shows the source type, a non-company scope and the date, with no link when there is no URL", () => {
    render(
      <EvidenceList
        items={[
          {
            paraphrase: "Sites run on fixed procedures.",
            source_type: "employee_review",
            scope: "location",
            scope_label: "Regional sites",
            published_at: "2026-05-18",
            source_url: null,
            abstained: false,
          },
        ]}
      />,
    );
    expect(screen.getByText(/Employee review · Regional sites · /)).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
    // A paraphrase, not a quote: no quotation marks are added around it.
    expect(screen.getByText("Sites run on fixed procedures.")).toBeInTheDocument();
  });
});
