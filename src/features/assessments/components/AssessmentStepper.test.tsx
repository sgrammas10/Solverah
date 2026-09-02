/**
 * Tests for AssessmentStepper.
 *
 * The tests that matter most are the ordering ones. A component that quietly sorted items or
 * options would look completely normal on screen and would corrupt every profile collected --
 * so the order contract is asserted, not assumed.
 */
import { render, screen, fireEvent } from "@testing-library/react";

import AssessmentStepper from "./AssessmentStepper";
import type { AssessmentItem } from "../useAssessment";

/**
 * Items whose prompts and option text are in deliberately NON-alphabetical order, so any
 * accidental sort shows up as a failure rather than passing by coincidence.
 */
const ITEMS: AssessmentItem[] = [
  {
    token: "tok-zulu",
    prompt: "Zulu prompt",
    options: [
      { key: "A", text: "zeta option" },
      { key: "B", text: "alpha option" },
    ],
  },
  {
    token: "tok-mike",
    prompt: "Mike prompt",
    options: [
      { key: "A", text: "yankee option" },
      { key: "B", text: "bravo option" },
    ],
  },
  {
    token: "tok-alfa",
    prompt: "Alfa prompt",
    options: [
      { key: "A", text: "xray option" },
      { key: "B", text: "charlie option" },
    ],
  },
];

const ALL_ANSWERED = Object.fromEntries(ITEMS.map((i) => [i.token, "A"]));

describe("AssessmentStepper", () => {
  const onAnswer = vi.fn();
  const onComplete = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  function renderStepper(answers = {}, overrides = {}) {
    return render(
      <AssessmentStepper
        items={ITEMS}
        answers={answers}
        onAnswer={onAnswer}
        onComplete={onComplete}
        {...overrides}
      />
    );
  }

  // -------------------------------------------------------------------------
  // The order contract -- D-04 and D-06
  // -------------------------------------------------------------------------

  it("renders items in the order received, not sorted", () => {
    // Answered throughout so Next is enabled and navigation actually moves.
    renderStepper(ALL_ANSWERED);
    expect(screen.getByText("Zulu prompt")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Mike prompt")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Alfa prompt")).toBeInTheDocument();
  });

  it("renders options in the order received, not sorted", () => {
    renderStepper();
    const rendered = screen.getAllByRole("radio").map((el) => el.textContent);
    expect(rendered[0]).toContain("zeta option");
    expect(rendered[1]).toContain("alpha option");
  });

  it("never displays block boundaries or any grouping label", () => {
    // Each server-side block holds exactly one item per dimension, so showing where a block
    // ends tells the respondent that every run of six covers all six dimensions.
    const { container } = renderStepper();
    expect(container.textContent).not.toMatch(/block/i);
    expect(container.textContent).not.toMatch(/section/i);
    expect(container.textContent).not.toMatch(
      /autonomy|pace|collaboration|feedback|innovation|decision/i
    );
  });

  it("does not put the token anywhere in the rendered text", () => {
    const { container } = renderStepper();
    expect(container.textContent).not.toContain("tok-zulu");
  });

  // -------------------------------------------------------------------------
  // Answering
  // -------------------------------------------------------------------------

  it("calls onAnswer with the item's token and the option key", () => {
    renderStepper();
    fireEvent.click(screen.getByText("alpha option"));
    expect(onAnswer).toHaveBeenCalledWith("tok-zulu", "B");
  });

  it("marks the selected option with aria-checked", () => {
    renderStepper({ "tok-zulu": "B" });
    expect(screen.getByRole("radio", { name: /alpha option/ })).toHaveAttribute(
      "aria-checked",
      "true"
    );
    expect(screen.getByRole("radio", { name: /zeta option/ })).toHaveAttribute(
      "aria-checked",
      "false"
    );
  });

  it("shows progress as a plain count of items", () => {
    renderStepper();
    expect(screen.getByText("Question 1 of 3")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Navigation
  // -------------------------------------------------------------------------

  it("disables Next until the current item is answered", () => {
    renderStepper();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("enables Next once the current item is answered", () => {
    renderStepper({ "tok-zulu": "A" });
    expect(screen.getByRole("button", { name: "Next" })).not.toBeDisabled();
  });

  it("hides Back on the first item", () => {
    renderStepper();
    expect(screen.queryByRole("button", { name: /back/i })).not.toBeInTheDocument();
  });

  it("Back returns to the previous item without changing its answer", () => {
    renderStepper(ALL_ANSWERED);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(screen.getByText("Zulu prompt")).toBeInTheDocument();
    expect(onAnswer).not.toHaveBeenCalled();
  });

  it("shows Finish instead of Next on the last item", () => {
    renderStepper(ALL_ANSWERED);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.queryByRole("button", { name: "Next" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Finish" })).toBeInTheDocument();
  });

  it("calls onComplete from the last item", () => {
    renderStepper(ALL_ANSWERED);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Finish" }));
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  // -------------------------------------------------------------------------
  // Submission state
  // -------------------------------------------------------------------------

  it("disables the button and shows a saving label while submitting", () => {
    // Navigate to the last item first: the button is disabled while submitting, which is the
    // point of the test but also stops the navigation clicks. Flip the prop with a rerender.
    const { rerender } = renderStepper(ALL_ANSWERED);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("button", { name: "Finish" })).toBeInTheDocument();

    rerender(
      <AssessmentStepper
        items={ITEMS}
        answers={ALL_ANSWERED}
        onAnswer={onAnswer}
        onComplete={onComplete}
        submitting
      />
    );
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
  });

  it("blocks a double submit by disabling the button while a submit is in flight", () => {
    const { rerender } = renderStepper(ALL_ANSWERED);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Finish" }));
    expect(onComplete).toHaveBeenCalledTimes(1);

    rerender(
      <AssessmentStepper
        items={ITEMS}
        answers={ALL_ANSWERED}
        onAnswer={onAnswer}
        onComplete={onComplete}
        submitting
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "Saving…" }));
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it("surfaces a submit error as an alert", () => {
    renderStepper(ALL_ANSWERED, { submitError: "Could not submit the assessment." });
    expect(screen.getByRole("alert")).toHaveTextContent("Could not submit the assessment.");
  });
});
