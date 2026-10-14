/**
 * LegacyProfile and its content check. The page shows the old profile only when it
 * has written content, and never its numeric ratings or retired culture scores.
 */
import { render, screen } from "@testing-library/react";

import { hasLegacyContent } from "../legacyProfile";
import LegacyProfile from "./LegacyProfile";

describe("hasLegacyContent", () => {
  it("is false for nothing, an empty object, or numbers and blanks only", () => {
    expect(hasLegacyContent(null)).toBe(false);
    expect(hasLegacyContent({})).toBe(false);
    expect(hasLegacyContent({ overview: { industry: "Logistics" }, culture: { culture_narrative_company: "  " } })).toBe(false);
    expect(hasLegacyContent({ glassdoor: { overall_rating: 4.1 } } as never)).toBe(false);
  });

  it("is true once any written part has text", () => {
    expect(hasLegacyContent({ interview: { notes: "Two rounds." } })).toBe(true);
    expect(hasLegacyContent({ culture: { core_values: ["Ownership"] } })).toBe(true);
  });

  it("survives a core_values that is not a list", () => {
    expect(hasLegacyContent({ culture: { core_values: "Ownership" as never } })).toBe(false);
  });
});

describe("LegacyProfile", () => {
  it("renders the written parts under a secondary heading", () => {
    render(
      <LegacyProfile
        profile={{
          culture: { culture_narrative_employees: "People help each other.", core_values: ["Ownership", "Care"] },
          compensation: { base_range: "In line with the region." },
        }}
      />,
    );
    expect(screen.getByRole("heading", { name: "Background research" })).toBeInTheDocument();
    expect(screen.getByText("People help each other.")).toBeInTheDocument();
    expect(screen.getByText("Ownership, Care")).toBeInTheDocument();
    expect(screen.getByText("In line with the region.")).toBeInTheDocument();
    expect(screen.queryByText("Interview process")).toBeNull();
  });
});
