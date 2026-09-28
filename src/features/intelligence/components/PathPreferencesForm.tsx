import { useState } from "react";
import { useAuth } from "../../auth";
import { useProfile, useProfileActions } from "../../profile";
import type { MoveIntent, SeniorityIntent, Priority } from "../types";

interface PathPreferencesFormProps {
  onComplete: () => void;
}

const QUESTIONS = [
  {
    key: "move_intent" as const,
    text: "What kind of move are you looking for?",
    options: [
      { value: "stay_in_field" as MoveIntent, label: "Stay in my field", description: "Same domain, potentially a different company or team" },
      { value: "adjacent" as MoveIntent, label: "Something adjacent", description: "Related skills, stepping into a nearby domain" },
      { value: "fresh_start" as MoveIntent, label: "Fresh direction", description: "New territory — using transferable skills in a different field" },
    ],
  },
  {
    key: "seniority_intent" as const,
    text: "What seniority level are you targeting?",
    options: [
      { value: "move_up" as SeniorityIntent, label: "Looking to move up", description: "Seeking a promotion or step up in responsibility" },
      { value: "stay_lateral" as SeniorityIntent, label: "Similar level", description: "Same seniority, different role or company" },
      { value: "open" as SeniorityIntent, label: "Open to either", description: "Not a dealbreaker — show me the best fits" },
    ],
  },
  {
    key: "priority" as const,
    text: "What matters most in your next role?",
    options: [
      { value: "pay_title" as Priority, label: "Pay & title", description: "Compensation and seniority signal are the priority" },
      { value: "interesting_work" as Priority, label: "Interesting work", description: "Stimulating problems and meaningful projects" },
      { value: "work_life_balance" as Priority, label: "Work-life balance", description: "Sustainable pace and flexibility" },
      { value: "learning_growth" as Priority, label: "Learning & growth", description: "Opportunities to build new skills and advance" },
    ],
  },
] as const;

type Answers = {
  move_intent: MoveIntent | null;
  seniority_intent: SeniorityIntent | null;
  priority: Priority | null;
};

export default function PathPreferencesForm({ onComplete }: PathPreferencesFormProps) {
  const { fetchWithAuth } = useAuth();
  const { updateProfileData } = useProfileActions();
  // The page passes only `onComplete` and this form cannot reach into
  // PathIntelligencePage (owned elsewhere), so it reads the same profile
  // document the page already has cached, straight from the shared query
  // cache. First visit, `path_preferences` is absent and every step opens
  // blank as before; on "Adjust search preferences" it re-enters with what
  // was last saved, rather than asking the three questions over again.
  const { data: profile } = useProfile();
  const stored = profile?.path_preferences as Partial<Answers> | undefined;
  const [step, setStep] = useState(0);
  const [answers, setAnswers] = useState<Answers>({
    move_intent: stored?.move_intent ?? null,
    seniority_intent: stored?.seniority_intent ?? null,
    priority: stored?.priority ?? null,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const question = QUESTIONS[step];
  const currentAnswer = answers[question.key];
  const isLastStep = step === QUESTIONS.length - 1;

  function selectOption(value: MoveIntent | SeniorityIntent | Priority) {
    setAnswers((prev) => ({ ...prev, [question.key]: value }));
  }

  async function handleNext() {
    if (!currentAnswer) return;
    if (!isLastStep) {
      setStep((s) => s + 1);
      return;
    }

    const { move_intent, seniority_intent, priority } = answers;
    if (!move_intent || !seniority_intent || !priority) return;

    setSubmitting(true);
    setError(null);
    try {
      // PUT, not POST: all three preferences are written together and the
      // write replaces whatever was stored.
      await fetchWithAuth("/me/path-preferences", {
        method: "PUT",
        body: JSON.stringify({ move_intent, seniority_intent, priority }),
      });
      updateProfileData({ path_preferences: { move_intent, seniority_intent, priority } });
      onComplete();
    } catch {
      setError("Something went wrong saving your preferences. Please try again.");
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Progress */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-widest text-ink-tertiary">
            Question {step + 1} of {QUESTIONS.length}
          </p>
          <div className="flex gap-1.5">
            {QUESTIONS.map((_, i) => (
              <div
                key={i}
                className={`h-1 rounded-full transition-all duration-300 ${
                  i <= step ? "w-6 bg-forest-dark" : "w-6 bg-cream-muted"
                }`}
              />
            ))}
          </div>
        </div>
        <h2 className="font-display text-xl font-semibold text-ink-primary">
          {question.text}
        </h2>
      </div>

      {/* Options */}
      <div className="space-y-3">
        {question.options.map((opt) => {
          const selected = currentAnswer === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              aria-pressed={selected}
              onClick={() => selectOption(opt.value as MoveIntent & SeniorityIntent & Priority)}
              // W-13, from the third browser test: after moving the choice
              // from "Fresh direction" to "Stay in my field", two options read
              // as selected. Only one ever IS -- `selected` is an equality
              // against a single stored value, and `aria-pressed` follows it --
              // so the defect was entirely in the palette: GREEN was the whole
              // of the selected signal (a forest border and a pale-green fill)
              // and it was ALSO the hover signal on every unselected option.
              // Put the pointer anywhere in the list on the way to "Next" and a
              // second option lights up green, tickless, exactly as reported.
              //
              // Hover is now neutral. Green means chosen and nothing else.
              className={`w-full text-left px-5 py-4 rounded-xl border transition-all ${
                selected
                  ? "border-2 border-forest-dark bg-forest-pale"
                  : "border border-cream-muted bg-white hover:border-ink-tertiary"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className={`font-semibold text-sm ${selected ? "text-forest-dark" : "text-ink-primary"}`}>
                    {opt.label}
                  </p>
                  <p className="text-xs text-ink-secondary mt-0.5 leading-relaxed">
                    {opt.description}
                  </p>
                </div>
                {selected && (
                  <span className="text-forest-dark font-bold text-sm shrink-0 mt-0.5">✓</span>
                )}
              </div>
            </button>
          );
        })}
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between pt-1">
        <button
          type="button"
          onClick={() => setStep((s) => s - 1)}
          className={`text-sm font-semibold text-ink-secondary hover:text-ink-primary transition-colors ${
            step === 0 ? "invisible" : ""
          }`}
        >
          ← Back
        </button>
        <button
          type="button"
          onClick={handleNext}
          disabled={!currentAnswer || submitting}
          className="bg-forest-dark text-white font-semibold px-6 py-2.5 rounded text-sm hover:bg-forest-mid transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {submitting ? "Saving…" : isLastStep ? "See my paths →" : "Next →"}
        </button>
      </div>

      {error && (
        <p className="text-xs text-red-600 text-center">{error}</p>
      )}
    </div>
  );
}
