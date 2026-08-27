import { useLocation, useNavigate, Navigate } from "react-router-dom";
import { useProfile } from "../hooks/useProfile";
import type { FocusTypeResult } from "./FocusTypePage";

const ARCHETYPE_DESCRIPTIONS: Record<string, string> = {
  "Deep Diver": "You do your best work when nothing breaks your flow.",
  "Sprint & Reset": "Short intense bursts, then real recovery — that's your engine.",
  "Reactive Flow": "You thrive where others struggle to keep up.",
  "Structured Builder": "You build best when you can see the whole plan first.",
  "Pressure Igniter": "Deadlines don't scare you — they're your starting gun.",
  "Collaborative Charger": "Your energy multiplies when others are in the room.",
};

const DIMENSION_LABELS: Record<string, string> = {
  deep_focus: "Deep Focus",
  burst_energy: "Burst Energy",
  reactivity: "Reactivity",
  structure_need: "Structure Need",
  urgency_drive: "Urgency Drive",
  social_fuel: "Social Fuel",
};

export default function FocusTypeResultsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { data: profile, isLoading } = useProfile();
  const result =
    (location.state as { result?: FocusTypeResult } | null)?.result ??
    (profile?.focus_type_result as FocusTypeResult | undefined);

  // The redirect below must not fire against a document still in flight. Before
  // Phase 4a the profile was always already loaded here, because the boot path
  // had fetched it; now it is a query, and an un-arrived document looks exactly
  // like a user who has never taken FocusType. `isLoading` rather than
  // `isPending`: a disabled query (signed out) is pending forever and would
  // spin instead of redirecting.
  if (!result && isLoading) {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Loading your result…</p>
      </div>
    );
  }

  if (!result) {
    return <Navigate to="/focus-type" replace />;
  }

  const scores = result.dimension_scores;
  const maxScore = Math.max(...Object.values(scores), 1);

  return (
    <div className="min-h-screen bg-cream-base">
      <div className="mx-auto max-w-2xl px-6 pt-12 pb-20 space-y-8">

        {/* Back nav */}
        <button
          type="button"
          onClick={() => navigate("/intelligence")}
          className="flex items-center gap-1.5 text-sm font-semibold text-forest-dark hover:underline"
        >
          <span aria-hidden>←</span> Intelligence Hub
        </button>

        {/* Eyebrow */}
        <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
          FocusType™
        </p>

        {/* Hero — archetype name */}
        <div className="rounded-xl border border-forest-light bg-forest-pale px-6 py-8">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-3">
            Your FocusType
          </p>
          <h1 className="font-display text-4xl sm:text-5xl font-semibold text-forest-dark leading-tight">
            {result.archetype}
          </h1>
          {ARCHETYPE_DESCRIPTIONS[result.archetype] && (
            <p className="text-base text-forest-dark mt-3 leading-relaxed opacity-75">
              {ARCHETYPE_DESCRIPTIONS[result.archetype]}
            </p>
          )}
        </div>

        {/* Workplace recommendations */}
        <div className="rounded-xl border border-cream-muted bg-white px-6 py-5 space-y-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
            Your workplace recommendations
          </p>
          <ul className="space-y-3">
            {result.recommendations.map((rec, i) => (
              <li key={i} className="flex gap-3 text-sm text-ink-primary leading-relaxed">
                <span className="text-forest-mid shrink-0 font-bold mt-0.5">›</span>
                {rec}
              </li>
            ))}
          </ul>
        </div>

        {/* Dimension scores */}
        <div className="rounded-xl border border-cream-muted bg-white px-6 py-5 space-y-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
            What drove your result
          </p>
          <div className="space-y-3">
            {Object.entries(scores)
              .sort(([, a], [, b]) => b - a)
              .map(([dim, score]) => (
                <div key={dim} className="flex items-center gap-3">
                  <span className="text-xs text-ink-secondary w-32 shrink-0">
                    {DIMENSION_LABELS[dim] ?? dim}
                  </span>
                  <div className="flex-1 h-2 bg-cream-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-forest-mid rounded-full transition-all duration-500"
                      style={{ width: `${Math.max((score / maxScore) * 100, score > 0 ? 4 : 0)}%` }}
                    />
                  </div>
                  <span className="text-xs text-ink-tertiary w-4 text-right tabular-nums">
                    {score}
                  </span>
                </div>
              ))}
          </div>
        </div>

        {/* CTA */}
        <button
          type="button"
          onClick={() => navigate("/intelligence")}
          className="w-full bg-forest-dark text-white font-semibold py-3.5 rounded hover:bg-forest-mid transition-colors"
        >
          Back to Intelligence →
        </button>

      </div>
    </div>
  );
}
