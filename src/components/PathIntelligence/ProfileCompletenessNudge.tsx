import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { X } from "lucide-react";

export interface ProfileCompletenessNudgeProps {
  workPulseComplete: boolean;
  careerStatusSet: boolean;
  managerMatchComplete: boolean;
  onCareerStatusSet: () => void;
  children: ReactNode;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function WorkPulseBlocker() {
  const navigate = useNavigate();
  return (
    <div className="rounded-xl border border-cream-muted bg-white px-6 py-10 text-center space-y-4">
      <p className="font-semibold text-ink-primary">
        Complete WorkPulse to unlock path suggestions
      </p>
      <p className="text-sm text-ink-secondary leading-relaxed">
        WorkPulse reveals how you work — we use it to score career paths against your real profile.
      </p>
      <button
        type="button"
        onClick={() => navigate("/work-pulse")}
        className="bg-forest-dark text-white font-semibold px-5 py-2.5 rounded-lg text-sm hover:bg-forest-mid transition-colors"
      >
        Take WorkPulse
      </button>
    </div>
  );
}

interface CareerStatusPromptProps {
  onSelect: () => void;
  onDismiss: () => void;
}

function CareerStatusPrompt({ onSelect, onDismiss }: CareerStatusPromptProps) {
  const options = [
    {
      value: "employed",
      label: "Currently employed",
      description: "You have a job and are exploring options",
    },
    {
      value: "between_jobs",
      label: "Between jobs",
      description: "You're actively looking for your next role",
    },
    {
      value: "first_job",
      label: "Looking for my first job",
      description: "You're early in your career journey",
    },
  ];

  return (
    <div className="rounded-xl border border-cream-muted bg-white px-6 py-8 space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-semibold text-ink-primary">Where are you in your career?</p>
          <p className="text-sm text-ink-secondary mt-1">
            Select your current status so we can tailor your path suggestions.
          </p>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss career status prompt"
          className="shrink-0 p-1 text-ink-tertiary hover:text-ink-primary transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="space-y-2">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={onSelect}
            className="w-full text-left rounded-lg border border-cream-muted bg-cream-base hover:bg-cream-subtle px-4 py-3 transition-colors"
          >
            <p className="font-medium text-sm text-ink-primary">{option.label}</p>
            <p className="text-xs text-ink-secondary mt-0.5">{option.description}</p>
          </button>
        ))}
      </div>
    </div>
  );
}

interface ManagerMatchBannerProps {
  onDismiss: () => void;
}

function ManagerMatchBanner({ onDismiss }: ManagerMatchBannerProps) {
  const navigate = useNavigate();
  return (
    <div className="relative bg-forest-pale border border-forest-light rounded-xl px-5 py-4 flex items-start gap-4">
      <p className="flex-1 text-sm text-ink-secondary">
        Complete ManagerMatch to factor your management preferences into your recommendations.{" "}
        <button
          type="button"
          onClick={() => navigate("/manager-match")}
          className="font-semibold text-forest-dark underline hover:text-forest-mid transition-colors"
        >
          Go to ManagerMatch
        </button>
      </p>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss ManagerMatch nudge"
        className="shrink-0 p-1 text-forest-light hover:text-forest-dark transition-colors"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ProfileCompletenessNudge({
  workPulseComplete,
  careerStatusSet,
  managerMatchComplete,
  onCareerStatusSet,
  children,
}: ProfileCompletenessNudgeProps) {
  const [careerPromptCollapsed, setCareerPromptCollapsed] = useState(false);
  const [managerMatchDismissed, setManagerMatchDismissed] = useState(false);

  // Priority 1: WorkPulse blocking — no suggestions shown
  if (!workPulseComplete) {
    return <WorkPulseBlocker />;
  }

  // Priority 2: Career status missing — no suggestions shown
  if (!careerStatusSet) {
    if (careerPromptCollapsed) {
      return (
        <div className="rounded-lg bg-cream-subtle border border-cream-muted px-4 py-3">
          <p className="text-sm text-ink-secondary">
            Set your career status to get personalized path suggestions.{" "}
            <button
              type="button"
              onClick={() => setCareerPromptCollapsed(false)}
              className="font-semibold text-forest-dark underline hover:text-forest-mid transition-colors"
            >
              Set your career status
            </button>
          </p>
        </div>
      );
    }
    return (
      <CareerStatusPrompt
        onSelect={onCareerStatusSet}
        onDismiss={() => setCareerPromptCollapsed(true)}
      />
    );
  }

  // Priority 3: ManagerMatch soft nudge — suggestions still render
  return (
    <>
      {!managerMatchComplete && !managerMatchDismissed && (
        <ManagerMatchBanner onDismiss={() => setManagerMatchDismissed(true)} />
      )}
      {children}
    </>
  );
}
