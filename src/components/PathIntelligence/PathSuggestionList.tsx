import type { PathSuggestion, CareerStatus } from "../../types/pathIntelligence";
import PathSuggestionCard from "./PathSuggestionCard";

interface PathSuggestionListProps {
  suggestions: PathSuggestion[];
  currentTitle: string | null;
  careerStatus: CareerStatus;
}

export default function PathSuggestionList({
  suggestions,
  currentTitle,
  careerStatus,
}: PathSuggestionListProps) {
  return (
    <div className="space-y-4">
      {suggestions.map((suggestion) => (
        <PathSuggestionCard
          key={suggestion.onet_code}
          suggestion={suggestion}
          currentTitle={currentTitle}
          careerStatus={careerStatus}
        />
      ))}
    </div>
  );
}
