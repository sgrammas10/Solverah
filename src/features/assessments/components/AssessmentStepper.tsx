/**
 * AssessmentStepper -- renders the person-side assessment, one item at a time.
 *
 * Presentational only. It receives the items already ordered by the server and renders them in
 * that order. It must not sort, group, reorder or shuffle them, and it must not reorder options
 * within an item -- the 2/2 key balance in the item file already neutralises positional bias
 * deterministically, and every frozen probe file keys its choices by letter, so a stored
 * "chose A" becomes ambiguous the moment the client shuffles.
 *
 * Progress is shown as "n of 24" and nothing else. No block boundaries, no section headings, no
 * category labels: each block contains exactly one item per dimension, so any visible grouping
 * hands back what the interleave exists to hide.
 */
import { useState } from "react";

import type { AssessmentAnswers, AssessmentItem } from "../useAssessment";

interface AssessmentStepperProps {
  items: AssessmentItem[];
  answers: AssessmentAnswers;
  onAnswer: (token: string, optionKey: string) => void;
  onComplete: () => void;
  submitting?: boolean;
  /** Shown as given, so the caller decides the wording. WorkPulsePage passes a
   *  fixed house message, never the server's text. */
  submitError?: string | null;
  /** Offered beside `submitError` as "Reload the questions". */
  onReloadQuestions?: () => void;
  /** Where to open. The resume prompt passes the first unanswered question; a fresh
   *  attempt opens at 0. Read once, on mount. */
  initialIndex?: number;
}

export default function AssessmentStepper({
  items,
  answers,
  onAnswer,
  onComplete,
  submitting = false,
  submitError = null,
  onReloadQuestions,
  initialIndex = 0,
}: AssessmentStepperProps) {
  const [currentIndex, setCurrentIndex] = useState(() =>
    Math.min(Math.max(initialIndex, 0), Math.max(items.length - 1, 0))
  );

  const item = items[currentIndex];
  const currentAnswer = answers[item.token];
  const isAnswered = currentAnswer !== undefined;
  const total = items.length;
  const progressPct = ((currentIndex + 1) / total) * 100;
  const isLast = currentIndex === total - 1;

  function handleNext() {
    if (!isLast) {
      setCurrentIndex((i) => i + 1);
    } else {
      onComplete();
    }
  }

  function handleBack() {
    setCurrentIndex((i) => i - 1);
  }

  return (
    <div className="space-y-4">
      <p className="text-xs font-semibold uppercase tracking-widest text-forest-mid">
        Question {currentIndex + 1} of {total}
      </p>

      <div className="w-full h-1 bg-cream-muted rounded-full overflow-hidden">
        <div
          className="h-full bg-forest-dark transition-all duration-300"
          style={{ width: `${progressPct}%` }}
        />
      </div>

      <h2 className="font-display text-xl sm:text-2xl font-semibold text-ink-primary mt-6">
        {item.prompt}
      </h2>

      <div className="space-y-3 pt-2">
        {/* Rendered in the order received. Do not sort. Do not randomize. */}
        {item.options.map((option) => {
          const isSelected = currentAnswer === option.key;
          return (
            <button
              key={option.key}
              type="button"
              role="radio"
              aria-checked={isSelected}
              onClick={() => onAnswer(item.token, option.key)}
              className={[
                "w-full text-left px-5 py-3.5 rounded transition-colors text-sm flex items-center justify-between",
                isSelected
                  ? "border-2 border-forest-dark bg-forest-pale/90 text-ink-primary font-medium"
                  : "border border-cream-muted bg-white/80 backdrop-blur-sm text-ink-primary hover:border-forest-light",
              ].join(" ")}
            >
              <span>{option.text}</span>
              {isSelected && (
                <span
                  className="text-forest-dark text-sm font-bold ml-3 shrink-0"
                  aria-hidden="true"
                >
                  ✓
                </span>
              )}
            </button>
          );
        })}
      </div>

      {submitError && (
        <div role="alert" className="text-sm text-red-700 pt-2 space-y-2">
          <p>{submitError}</p>
          {onReloadQuestions && (
            <button
              type="button"
              onClick={onReloadQuestions}
              disabled={submitting}
              className="text-xs font-semibold text-red-700 underline disabled:opacity-50"
            >
              Reload the questions
            </button>
          )}
        </div>
      )}

      <div className="flex items-center justify-between pt-4">
        {currentIndex > 0 ? (
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
          disabled={!isAnswered || submitting}
          className="bg-forest-dark text-white font-semibold px-8 py-3 rounded hover:bg-forest-mid transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLast ? (submitting ? "Saving…" : "Finish") : "Next"}
        </button>
      </div>
    </div>
  );
}
