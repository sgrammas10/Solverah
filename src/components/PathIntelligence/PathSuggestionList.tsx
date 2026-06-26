import { useState } from "react";
import type { PathSuggestion, CareerStatus } from "../../types/pathIntelligence";
import PathSuggestionCard from "./PathSuggestionCard";

interface PathSuggestionListProps {
  suggestions: PathSuggestion[];
  currentTitle: string | null;
  careerStatus: CareerStatus;
}

const PAGE_SIZE = 3;

export default function PathSuggestionList({
  suggestions,
  currentTitle,
  careerStatus,
}: PathSuggestionListProps) {
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const visible = suggestions.slice(0, visibleCount);
  const remaining = suggestions.length - visibleCount;
  const nextBatch = Math.min(PAGE_SIZE, remaining);

  return (
    <div className="space-y-4">
      {visible.map((suggestion) => (
        <PathSuggestionCard
          key={suggestion.onet_code}
          suggestion={suggestion}
          currentTitle={currentTitle}
          careerStatus={careerStatus}
        />
      ))}

      {nextBatch > 0 && (
        <button
          type="button"
          onClick={() => setVisibleCount((n) => n + PAGE_SIZE)}
          className="w-full rounded-xl border border-cream-muted bg-white px-5 py-3 text-sm font-semibold text-forest-mid hover:bg-cream-base transition-colors"
        >
          Show {nextBatch} more path{nextBatch !== 1 ? "s" : ""}
        </button>
      )}
    </div>
  );
}
