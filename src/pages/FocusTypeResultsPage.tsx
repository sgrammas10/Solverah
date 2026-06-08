import { useLocation, useNavigate } from "react-router-dom";
import type { FocusTypeResult } from "./FocusTypePage";

export default function FocusTypeResultsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const result = (location.state as { result?: FocusTypeResult } | null)?.result;

  if (!result) {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center px-6 text-center gap-4">
        <p className="text-sm text-ink-secondary">No results found.</p>
        <button
          type="button"
          onClick={() => navigate("/focus-type")}
          className="text-sm font-semibold text-forest-dark hover:underline"
        >
          Start FocusType
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-cream-base">
      <div className="mx-auto max-w-2xl px-6 pt-12 pb-20 space-y-8">
        <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
          FocusType™ Result
        </p>
        <div className="rounded-xl border border-forest-light bg-forest-pale px-6 py-6">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-1">
            Your FocusType
          </p>
          <p className="font-display text-2xl font-semibold text-forest-dark">
            {result.archetype}
          </p>
        </div>
        <div className="rounded-xl border border-cream-muted bg-white px-6 py-5 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-3">
            Workplace recommendations
          </p>
          <ul className="space-y-2">
            {result.recommendations.map((rec, i) => (
              <li key={i} className="text-sm text-ink-primary leading-relaxed flex gap-2">
                <span className="text-forest-light mt-0.5">›</span>
                {rec}
              </li>
            ))}
          </ul>
        </div>
        <button
          type="button"
          onClick={() => navigate("/intelligence")}
          className="w-full bg-forest-dark text-white font-semibold py-3.5 rounded hover:bg-forest-mid transition-colors"
        >
          Go to Intelligence Hub →
        </button>
      </div>
    </div>
  );
}
