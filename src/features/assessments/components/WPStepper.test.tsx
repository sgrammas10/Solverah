import { render, screen, fireEvent } from "@testing-library/react";
import WPStepper from "./WPStepper";
import { WP_QUESTIONS } from "../data/wpQuestions";

// All 12 questions answered with the first option — used to enable Next throughout.
const ALL_ANSWERS = WP_QUESTIONS.map((q) => ({
  questionId: q.id,
  optionId: q.options[0].id,
}));

describe("WPStepper", () => {
  const onAnswer = vi.fn();
  const onComplete = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the first question on mount", () => {
    render(<WPStepper answers={[]} onAnswer={onAnswer} onComplete={onComplete} />);
    expect(screen.getByText(WP_QUESTIONS[0].text)).toBeInTheDocument();
    expect(screen.getByText("Question 1 of 12")).toBeInTheDocument();
  });

  it("renders all 4 options for the first question", () => {
    render(<WPStepper answers={[]} onAnswer={onAnswer} onComplete={onComplete} />);
    WP_QUESTIONS[0].options.forEach((opt) => {
      expect(screen.getByText(opt.text)).toBeInTheDocument();
    });
  });

  it("calls onAnswer with the correct questionId and optionId when an option is clicked", () => {
    render(<WPStepper answers={[]} onAnswer={onAnswer} onComplete={onComplete} />);
    const option = WP_QUESTIONS[0].options[2];
    fireEvent.click(screen.getByText(option.text));
    expect(onAnswer).toHaveBeenCalledWith("wp-q1", option.id);
  });

  it("Next button is disabled when no answer is selected for the current question", () => {
    render(<WPStepper answers={[]} onAnswer={onAnswer} onComplete={onComplete} />);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("Next button is enabled when the current question has an answer", () => {
    const answers = [{ questionId: "wp-q1", optionId: "wp-q1-b" }];
    render(<WPStepper answers={answers} onAnswer={onAnswer} onComplete={onComplete} />);
    expect(screen.getByRole("button", { name: "Next" })).not.toBeDisabled();
  });

  it("Back button is not visible on question 1", () => {
    render(<WPStepper answers={[]} onAnswer={onAnswer} onComplete={onComplete} />);
    expect(screen.queryByRole("button", { name: /back/i })).not.toBeInTheDocument();
  });

  it("clicking Next advances to question 2", () => {
    render(<WPStepper answers={ALL_ANSWERS} onAnswer={onAnswer} onComplete={onComplete} />);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText(WP_QUESTIONS[1].text)).toBeInTheDocument();
    expect(screen.getByText("Question 2 of 12")).toBeInTheDocument();
  });

  it("clicking Back on question 2 returns to question 1", () => {
    render(<WPStepper answers={ALL_ANSWERS} onAnswer={onAnswer} onComplete={onComplete} />);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText(WP_QUESTIONS[1].text)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(screen.getByText(WP_QUESTIONS[0].text)).toBeInTheDocument();
  });

  it("shows 'See my results' on the last question instead of 'Next'", () => {
    render(<WPStepper answers={ALL_ANSWERS} onAnswer={onAnswer} onComplete={onComplete} />);
    for (let i = 0; i < WP_QUESTIONS.length - 1; i++) {
      fireEvent.click(screen.getByRole("button", { name: "Next" }));
    }
    expect(screen.queryByRole("button", { name: "Next" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "See my results" })).toBeInTheDocument();
  });

  it("clicking 'See my results' on the last question calls onComplete", () => {
    render(<WPStepper answers={ALL_ANSWERS} onAnswer={onAnswer} onComplete={onComplete} />);
    for (let i = 0; i < WP_QUESTIONS.length - 1; i++) {
      fireEvent.click(screen.getByRole("button", { name: "Next" }));
    }
    fireEvent.click(screen.getByRole("button", { name: "See my results" }));
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it("selected option is shown with aria-checked='true'", () => {
    const selectedId = WP_QUESTIONS[0].options[1].id;
    const answers = [{ questionId: "wp-q1", optionId: selectedId }];
    render(<WPStepper answers={answers} onAnswer={onAnswer} onComplete={onComplete} />);
    const selectedOption = screen.getByRole("radio", {
      name: WP_QUESTIONS[0].options[1].text,
    });
    expect(selectedOption).toHaveAttribute("aria-checked", "true");
  });
});
