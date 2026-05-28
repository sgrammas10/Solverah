import { useState } from "react";
import { WPLL_QUESTIONS } from "../../data/wpllQuestions";

interface WPLLStepperProps {
  wpllAnswers: { questionId: string; optionId: string }[];
  onAnswer: (questionId: string, optionId: string) => void;
  onComplete: () => void;
}

export default function WPLLStepper({ wpllAnswers, onAnswer, onComplete }: WPLLStepperProps) {
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);

  const question = WPLL_QUESTIONS[currentQuestionIndex];
  const currentAnswer = wpllAnswers.find((a) => a.questionId === question.id);
  const isAnswered = !!currentAnswer;
  const total = WPLL_QUESTIONS.length;
  const progressPct = ((currentQuestionIndex + 1) / total) * 100;

  function handleNext() {
    if (currentQuestionIndex < total - 1) {
      setCurrentQuestionIndex((i) => i + 1);
    } else {
      onComplete();
    }
  }

  function handleBack() {
    setCurrentQuestionIndex((i) => i - 1);
  }

  return (
    <div className="space-y-4">
      <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
        Question {currentQuestionIndex + 1} of {total}
      </p>

      <div className="w-full h-1 bg-cream-muted rounded-full overflow-hidden">
        <div
          className="h-full bg-forest-dark transition-all duration-300"
          style={{ width: `${progressPct}%` }}
        />
      </div>

      <h2 className="font-display text-xl sm:text-2xl font-semibold text-ink-primary mt-6">
        {question.text}
      </h2>

      <div className="space-y-3 pt-2">
        {question.options.map((option) => {
          const isSelected = currentAnswer?.optionId === option.id;
          return (
            <button
              key={option.id}
              type="button"
              role="radio"
              aria-checked={isSelected}
              onClick={() => onAnswer(question.id, option.id)}
              className={[
                "w-full text-left px-5 py-3.5 rounded transition-colors text-sm flex items-center justify-between",
                isSelected
                  ? "border-2 border-forest-dark bg-forest-pale text-ink-primary font-medium"
                  : "border border-cream-muted bg-white text-ink-primary hover:border-forest-light",
              ].join(" ")}
            >
              <span>{option.text}</span>
              {isSelected && (
                <span className="text-forest-dark text-sm font-bold ml-3 shrink-0" aria-hidden="true">
                  ✓
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="flex items-center justify-between pt-4">
        {currentQuestionIndex > 0 ? (
          <button
            type="button"
            onClick={handleBack}
            className="text-sm text-ink-secondary hover:text-ink-primary"
          >
            ← Back
          </button>
        ) : (
          <div />
        )}
        <button
          type="button"
          onClick={handleNext}
          disabled={!isAnswered}
          className="bg-forest-dark text-white font-semibold px-8 py-3 rounded hover:bg-forest-mid transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Next
        </button>
      </div>
    </div>
  );
}
