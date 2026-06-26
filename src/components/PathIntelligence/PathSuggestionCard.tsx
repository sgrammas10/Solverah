import { useState } from "react";
import type { PathSuggestion, CareerStatus } from "../../types/pathIntelligence";

export interface PathSuggestionCardProps {
  suggestion: PathSuggestion;
  currentTitle: string | null;
  careerStatus: CareerStatus;
}

function buildProgressionLine(
  careerStatus: CareerStatus,
  currentTitle: string | null,
  targetTitle: string
): string {
  if (careerStatus === "first_job") {
    return `Starting out → ${targetTitle}`;
  }
  if (careerStatus === "between_jobs") {
    return `Previously ${currentTitle ?? "Last Role"} → ${targetTitle}`;
  }
  return `${currentTitle ?? "Current Role"} → ${targetTitle}`;
}

export default function PathSuggestionCard({
  suggestion,
  currentTitle,
  careerStatus,
}: PathSuggestionCardProps) {
  const [showTooltip, setShowTooltip] = useState(false);

  const progressionLine = buildProgressionLine(careerStatus, currentTitle, suggestion.title);
  const scorePercent = Math.round(suggestion.match_score * 100);

  return (
    <div className="rounded-xl border border-cream-muted bg-white px-5 py-5 space-y-4">

      {/* Title + progression */}
      <div>
        <p className="font-display text-lg font-semibold text-ink-primary">
          {suggestion.title}
        </p>
        <p className="text-xs text-ink-secondary mt-0.5">{progressionLine}</p>
      </div>

      {/* Why this fits */}
      <p className="text-sm text-ink-primary leading-relaxed">{suggestion.why_text}</p>

      {/* Profile dimension tags */}
      {suggestion.profile_dimensions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {suggestion.profile_dimensions.map((dim) => (
            <span
              key={dim}
              className="rounded-full border border-forest-light bg-white px-3 py-1 text-xs font-semibold text-forest-mid"
            >
              {dim}
            </span>
          ))}
        </div>
      )}

      {/* Match score */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-ink-tertiary">Match score</span>
          <span className="text-xs font-semibold text-forest-mid">{scorePercent}%</span>
        </div>
        <div className="w-full h-1.5 bg-cream-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-forest-light rounded-full"
            style={{ width: `${scorePercent}%` }}
          />
        </div>
      </div>

      {/* Set as target role — disabled CTA with hover tooltip */}
      <div
        className="relative inline-block"
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        <button
          type="button"
          disabled
          className="border border-cream-muted text-ink-tertiary text-xs font-semibold px-3 py-1.5 rounded cursor-not-allowed opacity-60"
        >
          Set as target role
        </button>
        {showTooltip && (
          <div
            role="tooltip"
            className="absolute bottom-full left-0 mb-2 w-56 rounded bg-ink-primary px-3 py-2 text-xs text-white shadow-lg"
          >
            Coming soon — goal tracking is on the way
          </div>
        )}
      </div>

    </div>
  );
}
