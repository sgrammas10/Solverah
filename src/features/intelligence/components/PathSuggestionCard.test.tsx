import { render, screen, fireEvent } from "@testing-library/react";
import PathSuggestionCard from "./PathSuggestionCard";
import type { PathSuggestion } from "../types";

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

  it("renders no percentage, score number, or score bar (§8.5, W-1)", () => {
    const { container } = render(
      <PathSuggestionCard
        suggestion={BASE_SUGGESTION}
        currentTitle="Software Engineer"
        careerStatus="employed"
      />
    );
    expect(screen.queryByText(/%/)).toBeNull();
    expect(screen.queryByText("Match score")).toBeNull();
    expect(container.querySelector('[style*="width"]')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// W-5 — the reason line, where the percentage used to be
// ---------------------------------------------------------------------------

describe("PathSuggestionCard - reasons", () => {
  function renderWithReasons(reasons: string[] | undefined) {
    return render(
      <PathSuggestionCard
        suggestion={{ ...BASE_SUGGESTION, reasons }}
        currentTitle="Software Engineer"
        careerStatus="employed"
      />
    );
  }

  it("renders both reasons when the card carries two", () => {
    renderWithReasons([
      "Among the most people-facing jobs",
      "Less time at a desk than your current job",
    ]);
    expect(screen.getByText("Among the most people-facing jobs")).toBeInTheDocument();
    expect(
      screen.getByText("Less time at a desk than your current job")
    ).toBeInTheDocument();
    expect(document.querySelectorAll("[data-reasons] li")).toHaveLength(2);
  });

  it("renders one reason when the card carries one", () => {
    renderWithReasons(["Very little dealing with the public"]);
    expect(document.querySelectorAll("[data-reasons] li")).toHaveLength(1);
  });

  it("renders nothing at all for an empty list", () => {
    // No heading, no placeholder, no "nothing distinctive here". A card with
    // nothing to say about it still has its why-text.
    renderWithReasons([]);
    expect(document.querySelector("[data-reasons]")).toBeNull();
  });

  it("renders nothing at all when the field is absent", () => {
    // A payload cached before W-4 shipped, and a user who has stated no wants.
    renderWithReasons(undefined);
    expect(document.querySelector("[data-reasons]")).toBeNull();
  });

  it("still shows no percentage, number or bar with reasons present", () => {
    // W-1's rule survives the new line: these are phrases about the work, never
    // a grade on the user.
    const { container } = renderWithReasons([
      "Among the most people-facing jobs",
      "More leading than your current job",
    ]);
    expect(screen.queryByText(/%/)).toBeNull();
    expect(container.querySelector('[style*="width"]')).toBeNull();
    expect(container.textContent).not.toMatch(/\d+\s*%/);
  });

  it("keeps the why-text and the dimension tags alongside the reasons", () => {
    renderWithReasons(["Among the most people-facing jobs"]);
    expect(
      screen.getByText("Your skills align well with marketing leadership roles.")
    ).toBeInTheDocument();
    expect(screen.getByText("Matches your Creative Drive archetype")).toBeInTheDocument();
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

  it("opens below the button, never above it, so it cannot cover the verdict row", () => {
    // `bottom-full` opens upward and used to sit on top of the Interesting /
    // Too similar / Not for me row above this CTA.
    renderCard();
    const wrapper = screen.getByRole("button", { name: /set as target role/i })
      .parentElement!;
    fireEvent.mouseEnter(wrapper);
    const tooltip = screen.getByRole("tooltip");
    expect(tooltip.className).not.toMatch(/\bbottom-full\b/);
    expect(tooltip.className).toMatch(/\btop-full\b/);
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

// ---------------------------------------------------------------------------
// F-6 — inline feedback controls and click-to-open
// ---------------------------------------------------------------------------
//
// Controls are selected by `data-verdict` and `aria-pressed`, never by their
// text. Julie owns the labels and revises them on the built product; a test that
// matched "Too similar to my job" would turn a copy edit into a red suite
// (AccountModal.test.tsx set this precedent for F-9 and gives the reasoning).

function verdictButtons(): HTMLElement[] {
  return Array.from(
    document.querySelectorAll<HTMLElement>("[data-verdict]")
  );
}

function verdictButton(value: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(`[data-verdict="${value}"]`);
  if (!found) throw new Error(`no control for verdict ${value}`);
  return found;
}

describe("PathSuggestionCard - feedback controls", () => {
  it("renders no feedback controls when no handler is given", () => {
    renderCard();
    expect(verdictButtons()).toHaveLength(0);
  });

  it("offers all three verdicts, because they are three different signals", () => {
    render(
      <PathSuggestionCard
        suggestion={BASE_SUGGESTION}
        currentTitle="Software Engineer"
        careerStatus="employed"
        onVerdict={() => {}}
      />
    );
    expect(verdictButtons().map((b) => b.dataset.verdict)).toEqual([
      "interesting",
      "too_similar",
      "not_for_me",
    ]);
  });

  it("reports the tapped verdict with the card's O*NET code", () => {
    const onVerdict = vi.fn();
    render(
      <PathSuggestionCard
        suggestion={BASE_SUGGESTION}
        currentTitle="Software Engineer"
        careerStatus="employed"
        onVerdict={onVerdict}
      />
    );
    fireEvent.click(verdictButton("too_similar"));
    expect(onVerdict).toHaveBeenCalledWith("11-2021.00", "too_similar");
  });

  it("marks the standing verdict pressed and the others not", () => {
    render(
      <PathSuggestionCard
        suggestion={BASE_SUGGESTION}
        currentTitle="Software Engineer"
        careerStatus="employed"
        verdict="interesting"
        onVerdict={() => {}}
      />
    );
    expect(verdictButton("interesting")).toHaveAttribute("aria-pressed", "true");
    expect(verdictButton("too_similar")).toHaveAttribute("aria-pressed", "false");
  });

  it("disables every control while a tap is in flight", () => {
    render(
      <PathSuggestionCard
        suggestion={BASE_SUGGESTION}
        currentTitle="Software Engineer"
        careerStatus="employed"
        onVerdict={() => {}}
        feedbackPending
      />
    );
    for (const button of verdictButtons()) {
      expect(button).toBeDisabled();
    }
  });
});

describe("PathSuggestionCard - opening the deep fit", () => {
  it("is not clickable when no open handler is given", () => {
    renderCard();
    expect(screen.queryByRole("button", { name: /how .* fits you/i })).toBeNull();
  });

  it("opens the fit for its own occupation when the body is clicked", () => {
    const onOpen = vi.fn();
    render(
      <PathSuggestionCard
        suggestion={BASE_SUGGESTION}
        currentTitle="Software Engineer"
        careerStatus="employed"
        onOpen={onOpen}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /how .* fits you/i }));
    expect(onOpen).toHaveBeenCalledWith("11-2021.00");
  });

  it("keeps the feedback controls outside the clickable region", () => {
    // Nesting them would give a keyboard user a control they cannot reach and a
    // screen reader a button containing buttons -- and every tap would also open
    // the panel.
    const onOpen = vi.fn();
    render(
      <PathSuggestionCard
        suggestion={BASE_SUGGESTION}
        currentTitle="Software Engineer"
        careerStatus="employed"
        onOpen={onOpen}
        onVerdict={() => {}}
      />
    );
    fireEvent.click(verdictButton("interesting"));
    expect(onOpen).not.toHaveBeenCalled();
  });
});
