import { useCareerIntake } from "../hooks/useCareerIntake";
import LandingNav from "../components/landing/LandingNav";
import StatementSelector from "../components/intake/StatementSelector";
import WPLLStepper from "../components/intake/WPLLStepper";
import TeaserResult from "../components/intake/TeaserResult";
import AccountGate from "../components/intake/AccountGate";

const STEP_LABELS: Record<1 | 2 | 3 | 4, string> = {
  1: "Your situation",
  2: "Quick pulse",
  3: "Your focus",
  4: "Get started",
};

const STEPS = [1, 2, 3, 4] as const;

export default function CareerIntakePage() {
  const { state, setStep, toggleStatement, setWpllAnswer, setWpllInsightText } = useCareerIntake();
  const { step, selectedStatementIds } = state;

  return (
    <div className="min-h-screen bg-cream-base">
      <LandingNav />

      {/* Progress bar */}
      <div className="mx-auto max-w-2xl px-6 pt-10 pb-6">
        <div className="flex items-center">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center flex-1 last:flex-none">
              <div className="flex flex-col items-center">
                <div
                  className={[
                    "w-3 h-3 rounded-full transition-colors",
                    s <= step ? "bg-forest-dark" : "bg-cream-muted",
                  ].join(" ")}
                />
                <span
                  className={[
                    "text-xs mt-1.5 whitespace-nowrap",
                    s === step ? "text-forest-dark font-semibold" : "text-ink-tertiary",
                  ].join(" ")}
                >
                  {STEP_LABELS[s]}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <div
                  className={[
                    "flex-1 h-px mx-2 mb-4 transition-colors",
                    s < step ? "bg-forest-dark" : "bg-cream-muted",
                  ].join(" ")}
                />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Step content */}
      <div className="mx-auto max-w-2xl px-6 pb-16">
        {step > 1 && (
          <button
            type="button"
            onClick={() => setStep((step - 1) as 1 | 2 | 3 | 4)}
            className="text-sm text-ink-secondary hover:text-ink-primary mb-6 block"
          >
            ← Back
          </button>
        )}

        {step === 1 && (
          <div className="space-y-6">
            <div className="space-y-1">
              <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
                What's true for you right now?
              </h1>
              <p className="text-sm text-ink-secondary">
                Select everything that resonates — there's no wrong answer.
              </p>
            </div>
            <StatementSelector selectedIds={selectedStatementIds} onToggle={toggleStatement} />
            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => setStep(2)}
                disabled={selectedStatementIds.length === 0}
                className={[
                  "bg-forest-dark text-white font-semibold px-8 py-3 rounded transition-colors",
                  selectedStatementIds.length === 0
                    ? "opacity-50 cursor-not-allowed"
                    : "hover:bg-forest-mid",
                ].join(" ")}
              >
                See what Solverah sees →
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <WPLLStepper
            wpllAnswers={state.wpllAnswers}
            onAnswer={setWpllAnswer}
            onComplete={() => setStep(3)}
          />
        )}

        {step === 3 && (
          <TeaserResult
            wpllAnswers={state.wpllAnswers}
            onInsightReceived={setWpllInsightText}
            cachedInsightText={state.wpllInsightText}
            onContinue={() => setStep(4)}
          />
        )}

        {step === 4 && <AccountGate />}
      </div>
    </div>
  );
}
