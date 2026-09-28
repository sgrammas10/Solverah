/**
 * ReportSummary -- the "In short" block above the Situation Report's cards.
 * The page-level behaviour (document order, needs-forward) is covered in
 * SituationReportPage.test.tsx; this file covers the summary's own branches.
 */
import { render, screen, within } from "@testing-library/react";

import ReportSummary from "./ReportSummary";
import type { SituationDimensionEntry } from "../../useSituationReport";

function strain(
  dimension: SituationDimensionEntry["dimension"],
  bucket: "straining" | "notable",
  headline: string,
): SituationDimensionEntry {
  return {
    dimension,
    env_score: 0.4321,
    bucket,
    direction: "under",
    rank: 0,
    diagnosis: { headline, text: "Text." },
    registers: {},
    defers_to_decoder: false,
    decoder_crossref: null,
  };
}

function aligned(dimension: SituationDimensionEntry["dimension"]): SituationDimensionEntry {
  return {
    dimension,
    env_score: 0.5,
    bucket: "aligned",
    direction: null,
    rank: 3,
    aligned_note: "Much the same.",
  };
}

function rows(): [string, string][] {
  return screen
    .getAllByRole("term")
    .map((dt) => [dt.textContent ?? "", dt.nextElementSibling?.textContent ?? ""]);
}

describe("ReportSummary", () => {
  it("names the first strained row as the most strained and lists groups in server order", () => {
    render(
      <ReportSummary
        past={false}
        dimensions={[
          strain("pace", "straining", "Pace headline"),
          strain("autonomy", "straining", "Autonomy headline"),
          strain("decision", "straining", "Decision headline"),
          strain("feedback", "notable", "Feedback headline"),
          aligned("collaboration"),
          aligned("innovation"),
        ]}
      />,
    );

    const summary = screen.getByRole("region", { name: "In short" });
    expect(within(summary).getByText("Pace is under the most strain.")).toBeInTheDocument();
    expect(within(summary).getByText("Pace headline")).toBeInTheDocument();
    // Not re-sorted: Pace stays ahead of Autonomy because the server put it there.
    expect(rows()).toEqual([
      ["Under most strain", "Pace, Autonomy and Decision-making"],
      ["Worth watching", "Feedback"],
      ["Working well", "Collaboration and Innovation"],
    ]);
    expect(summary.textContent ?? "").not.toMatch(/\d/);
  });

  it("leads with a notable row when nothing is straining", () => {
    render(
      <ReportSummary
        past={false}
        dimensions={[strain("feedback", "notable", "Feedback headline"), aligned("pace")]}
      />,
    );

    expect(screen.getByText("Feedback is under the most strain.")).toBeInTheDocument();
    expect(rows()).toEqual([
      ["Worth watching", "Feedback"],
      ["Working well", "Pace"],
    ]);
  });

  it("says nothing is under strain when every row is aligned", () => {
    render(<ReportSummary past={false} dimensions={[aligned("pace"), aligned("autonomy")]} />);

    expect(screen.getByText("Nothing is under strain.")).toBeInTheDocument();
    expect(rows()).toEqual([["Working well", "Pace and Autonomy"]]);
  });

  it("uses the past tense for the needs-forward rendering", () => {
    render(
      <ReportSummary past dimensions={[strain("autonomy", "straining", "Autonomy headline")]} />,
    );

    expect(screen.getByText("Autonomy was under the most strain.")).toBeInTheDocument();
    expect(rows()).toEqual([["Strained most", "Autonomy"]]);
  });
});
