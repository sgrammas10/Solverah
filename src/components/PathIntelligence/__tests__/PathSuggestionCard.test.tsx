import { render, screen, fireEvent } from "@testing-library/react";
import PathSuggestionCard from "../PathSuggestionCard";
import type { PathSuggestion } from "../../../types/pathIntelligence";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const BASE_SUGGESTION: PathSuggestion = {
  onet_code: "11-2021.00",
  title: "Marketing Managers",
  why_text: "Your skills align well with marketing leadership roles.",
  profile_dimensions: [
    "Matches your Creative Drive archetype",
    "Builds on your Communication skills",
  ],
  match_score: 0.82,
};

function renderCard(
  overrides: {
    suggestion?: PathSuggestion;
    currentTitle?: string | null;
    careerStatus?: "employed" | "between_jobs" | "first_job";
  } = {}
) {
  render(
    <PathSuggestionCard
      suggestion={overrides.suggestion ?? BASE_SUGGESTION}
      currentTitle={overrides.currentTitle !== undefined ? overrides.currentTitle : "Software Engineer"}
      careerStatus={overrides.careerStatus ?? "employed"}
    />
  );
}

// ---------------------------------------------------------------------------
// Field rendering
// ---------------------------------------------------------------------------

describe("PathSuggestionCard - field rendering", () => {
  it("renders the target role title", () => {
    renderCard();
    expect(screen.getByText("Marketing Managers")).toBeInTheDocument();
  });

  it("renders the why_text", () => {
    renderCard();
    expect(
      screen.getByText("Your skills align well with marketing leadership roles.")
    ).toBeInTheDocument();
  });

  it("renders each profile dimension tag", () => {
    renderCard();
    expect(
      screen.getByText("Matches your Creative Drive archetype")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Builds on your Communication skills")
    ).toBeInTheDocument();
  });

  it("renders the match score as a rounded percentage", () => {
    renderCard();
    expect(screen.getByText("82%")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Progression line variants
// ---------------------------------------------------------------------------

describe("PathSuggestionCard - progression line", () => {
  it("shows 'CurrentTitle → Target' for employed status", () => {
    renderCard({ currentTitle: "Software Engineer", careerStatus: "employed" });
    expect(
      screen.getByText("Software Engineer → Marketing Managers")
    ).toBeInTheDocument();
  });

  it("shows 'Previously ... → Target' for between_jobs status", () => {
    renderCard({ currentTitle: "Software Engineer", careerStatus: "between_jobs" });
    expect(
      screen.getByText("Previously Software Engineer → Marketing Managers")
    ).toBeInTheDocument();
  });

  it("shows 'Starting out → Target' for first_job status", () => {
    renderCard({ currentTitle: null, careerStatus: "first_job" });
    expect(
      screen.getByText("Starting out → Marketing Managers")
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Disabled CTA button
// ---------------------------------------------------------------------------

describe("PathSuggestionCard - Set as target role CTA", () => {
  it("renders the Set as target role button", () => {
    renderCard();
    expect(
      screen.getByRole("button", { name: /set as target role/i })
    ).toBeInTheDocument();
  });

  it("button is disabled", () => {
    renderCard();
    expect(
      screen.getByRole("button", { name: /set as target role/i })
    ).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Tooltip on hover
// ---------------------------------------------------------------------------

describe("PathSuggestionCard - tooltip", () => {
  it("shows the tooltip text when hovering the CTA wrapper", () => {
    renderCard();
    const wrapper = screen.getByRole("button", { name: /set as target role/i })
      .parentElement!;
    fireEvent.mouseEnter(wrapper);
    expect(screen.getByRole("tooltip")).toHaveTextContent(
      "Coming soon — goal tracking is on the way"
    );
  });

  it("hides the tooltip after the mouse leaves", () => {
    renderCard();
    const wrapper = screen.getByRole("button", { name: /set as target role/i })
      .parentElement!;
    fireEvent.mouseEnter(wrapper);
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
    fireEvent.mouseLeave(wrapper);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});
