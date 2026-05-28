import { render, screen, fireEvent } from "@testing-library/react";
import WPLLStepper from "../WPLLStepper";
import { WPLL_QUESTIONS } from "../../../data/wpllQuestions";

// Pre-fill all answers (first option per question) so Next is always enabled during navigation tests
const ALL_ANSWERS = WPLL_QUESTIONS.map((q) => ({
  questionId: q.id,
  optionId: q.options[0].id,
}));

describe("WPLLStepper", () => {
  const onAnswer = vi.fn();
  const onComplete = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders all 4 options for Q1", () => {
    render(<WPLLStepper wpllAnswers={[]} onAnswer={onAnswer} onComplete={onComplete} />);
    WPLL_QUESTIONS[0].options.forEach((opt) => {
      expect(screen.getByText(opt.text)).toBeInTheDocument();
    });
  });

  it("calls onAnswer with correct questionId and optionId when an option is clicked", () => {
    render(<WPLLStepper wpllAnswers={[]} onAnswer={onAnswer} onComplete={onComplete} />);
    const option = WPLL_QUESTIONS[0].options[1];
    fireEvent.click(screen.getByText(option.text));
    expect(onAnswer).toHaveBeenCalledWith("wpll-q1", option.id);
  });

  it("Next button is disabled when no answer is selected for the current question", () => {
    render(<WPLLStepper wpllAnswers={[]} onAnswer={onAnswer} onComplete={onComplete} />);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("Next button is enabled when the current question has an answer", () => {
    const answers = [{ questionId: "wpll-q1", optionId: "wpll-q1-a" }];
    render(<WPLLStepper wpllAnswers={answers} onAnswer={onAnswer} onComplete={onComplete} />);
    expect(screen.getByRole("button", { name: "Next" })).not.toBeDisabled();
  });

  it("Back button is not visible on Q1", () => {
    render(<WPLLStepper wpllAnswers={[]} onAnswer={onAnswer} onComplete={onComplete} />);
    expect(screen.queryByRole("button", { name: /back/i })).not.toBeInTheDocument();
  });

  it("clicking Back on Q2 returns to Q1", () => {
    render(
      <WPLLStepper wpllAnswers={ALL_ANSWERS} onAnswer={onAnswer} onComplete={onComplete} />
    );
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText(WPLL_QUESTIONS[1].text)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(screen.getByText(WPLL_QUESTIONS[0].text)).toBeInTheDocument();
  });

  it("clicking Next on Q5 calls onComplete", () => {
    render(
      <WPLLStepper wpllAnswers={ALL_ANSWERS} onAnswer={onAnswer} onComplete={onComplete} />
    );
    for (let i = 0; i < 4; i++) {
      fireEvent.click(screen.getByRole("button", { name: "Next" }));
    }
    expect(screen.getByText(WPLL_QUESTIONS[4].text)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onComplete).toHaveBeenCalledTimes(1);
  });
});
