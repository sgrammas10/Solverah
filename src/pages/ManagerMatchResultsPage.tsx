import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useMM } from "../hooks/useMM";
import type { MMResult } from "../hooks/useMM";
import { useAuth } from "../contexts/useAuth";

type FetchState = "loading" | "error" | "success";

const DIMENSIONS = [
  { key: "autonomy", label: "Autonomy" },
  { key: "feedback_style", label: "Feedback Style" },
  { key: "relationship", label: "Relationship" },
  { key: "growth_focus", label: "Growth Focus" },
];

function bandLabel(score: number): string {
  if (score < 0.4) return "Low";
  if (score <= 0.65) return "Mid";
  return "High";
}

export default function ManagerMatchResultsPage() {
  const navigate = useNavigate();
  const { fetchWithAuth, user } = useAuth();
  const { state, setCachedResult } = useMM();

  const hasCached = state.cachedResult !== null;
  const [fetchState, setFetchState] = useState<FetchState>(hasCached ? "success" : "loading");
  const [result, setResult] = useState<MMResult | null>(state.cachedResult);
  const hasFiredRef = useRef(false);

  const fetchFromServer = useCallback(async () => {
    setFetchState("loading");
    try {
      const data = await fetchWithAuth<MMResult>("/manager-match/results");
      setResult(data);
      setCachedResult(data);
      setFetchState("success");
    } catch {
      setFetchState("error");
    }
  }, [fetchWithAuth, setCachedResult]);

  useEffect(() => {
    if (hasCached) return;

    const profileResult = user?.profileData?.manager_match_result as MMResult | undefined;
    if (profileResult) {
      setCachedResult(profileResult);
      setResult(profileResult);
      setFetchState("success");
      return;
    }

    if (!hasFiredRef.current) {
      hasFiredRef.current = true;
      fetchFromServer();
    }
  }, []); // intentionally runs once on mount

  if (fetchState === "loading") {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Loading your results…</p>
      </div>
    );
  }

  if (fetchState === "error") {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div className="max-w-sm w-full rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
          <p className="font-medium mb-1">We couldn't load your results right now.</p>
          <p className="text-xs">Please try again in a moment.</p>
          <button
            type="button"
            onClick={fetchFromServer}
            className="mt-3 text-xs font-semibold text-red-700 underline"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  if (!result) return null;

  const paragraphs = result.narrative
    .split(/\n\n+/)
    .map((p) => p.trim())
    .filter(Boolean);

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

        {/* Header */}
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
            Your ManagerMatch™
          </p>
          <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
            {result.archetype}
          </h1>
          {result.archetype_description && (
            <p className="text-base text-ink-primary leading-relaxed">
              {result.archetype_description}
            </p>
          )}
        </div>

        {/* Narrative card */}
        <div className="rounded-xl border border-cream-muted bg-white p-6 space-y-4">
          {paragraphs.map((para, i) => (
            <p key={i} className="text-base text-ink-primary leading-relaxed">
              {para}
            </p>
          ))}
        </div>

        {/* Dimension breakdown */}
        <div className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-forest-light">
            How you scored
          </h2>
          <div className="space-y-3">
            {DIMENSIONS.map(({ key, label }) => {
              const score = (result.dimension_scores[key] as number) ?? 0;
              return (
                <div key={key} className="flex items-center gap-3">
                  <span className="text-sm text-ink-primary w-32 shrink-0">{label}</span>
                  <div className="flex-1 h-2 bg-cream-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-forest-dark rounded-full"
                      style={{ width: `${score * 100}%` }}
                    />
                  </div>
                  <span className="text-xs text-ink-secondary w-8 text-right">
                    {bandLabel(score)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* What to look for */}
        <div className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-forest-light">
            What to look for
          </h2>
          <ul className="space-y-2">
            {result.what_to_look_for.map((item, i) => (
              <li key={i} className="flex gap-2 text-sm text-ink-primary leading-relaxed">
                <span className="text-forest-mid shrink-0 font-bold">›</span>
                {item}
              </li>
            ))}
          </ul>
        </div>

        {/* Watch out for */}
        <div className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-forest-light">
            Watch out for
          </h2>
          <ul className="space-y-2">
            {result.red_flags.map((item, i) => (
              <li key={i} className="flex gap-2 text-sm text-ink-primary leading-relaxed">
                <span className="text-forest-mid shrink-0 font-bold">›</span>
                {item}
              </li>
            ))}
          </ul>
        </div>

        {/* CTA */}
        <button
          type="button"
          onClick={() => navigate("/intelligence")}
          className="w-full bg-forest-dark text-white font-semibold py-3.5 rounded hover:bg-forest-mid transition-colors"
        >
          Back to Intelligence Hub
        </button>

      </div>
    </div>
  );
}
