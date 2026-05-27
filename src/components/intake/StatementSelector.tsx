import { CAREER_STATEMENTS } from "../../data/careerStatements";

interface StatementSelectorProps {
  selectedIds: string[];
  onToggle: (id: string) => void;
}

export default function StatementSelector({ selectedIds, onToggle }: StatementSelectorProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {CAREER_STATEMENTS.map((statement) => {
        const isSelected = selectedIds.includes(statement.id);
        const isLast = statement.id === "self-1";
        return (
          <button
            key={statement.id}
            type="button"
            role="checkbox"
            aria-checked={isSelected}
            onClick={() => onToggle(statement.id)}
            className={[
              "relative text-left p-4 rounded-lg transition-colors",
              isLast ? "sm:col-span-2" : "",
              isSelected
                ? "border-2 border-forest-dark bg-forest-pale"
                : "border border-cream-muted bg-white hover:border-forest-light",
            ].join(" ")}
          >
            {isSelected && (
              <span className="absolute top-3 right-3 text-forest-dark text-sm font-bold" aria-hidden="true">
                ✓
              </span>
            )}
            <p className="text-sm font-medium text-ink-primary pr-5">{statement.text}</p>
            <p className="text-xs text-ink-tertiary mt-1">{statement.category}</p>
          </button>
        );
      })}
    </div>
  );
}
