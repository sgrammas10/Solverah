import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Lock } from "lucide-react";
import { useWP } from "../hooks/useWP";
import type { WpApiResponse } from "../hooks/useWP";
import { useAuth } from "../contexts/useAuth";

const ECOSYSTEM_STEPS = [
  { label: "Work Pulse Lite" },
  { label: "Work Pulse" },
  { label: "FocusType" },
  { label: "ManagerMatch" },
  { label: "CompanyLens" },
  { label: "Future Path" },
];

const LOCKED_CARDS = [
  {
    title: "FocusType™",
    subtitle: "Attention, focus, and energy patterns",
    description:
      "Understand how your attention works and which environments protect it.",
  },
  {
    title: "ManagerMatch™",
    subtitle: "Leadership and management alignment",
    description:
      "Discover which management styles bring out your best — and which create friction.",
  },
  {
    title: "CompanyLens™",
    subtitle: "Company environment and cultural alignment",
    description:
      "See which real companies match your work patterns and sustainability signals.",
  },
  {
    title: "Future Path Intelligence",
    subtitle: "Sustainability and long-term direction",
    description:
      "Map the career paths most likely to feel sustainable and meaningful over time.",
  },
];

type FetchState = "loading" | "error" | "success";

export default function SolverahProfilePage() {
  const navigate = useNavigate();
  const { fetchWithAuth, user } = useAuth();
  const { state, setCachedResult } = useWP();

  const hasCached = state.cachedResult !== null;
  const [fetchState, setFetchState] = useState<FetchState>(
    !user?.wpl_completed || hasCached ? "success" : "loading"
  );
  const [result, setResult] = useState<WpApiResponse | null>(state.cachedResult);
  const hasFiredRef = useRef(false);

  const fetchFromServer = useCallback(async () => {
    setFetchState("loading");
    try {
      const data = await fetchWithAuth<WpApiResponse>("/work-pulse/results");
      setResult(data);
      setCachedResult(data);
      setFetchState("success");
    } catch {
      setFetchState("error");
    }
  }, [fetchWithAuth, setCachedResult]);

  useEffect(() => {
    if (!user?.wpl_completed) return;
    if (hasCached) return;
    if (!hasFiredRef.current) {
      hasFiredRef.current = true;
      fetchFromServer();
    }
  }, []); // intentionally runs once on mount; hasFiredRef guards against Strict Mode double-fire

  if (fetchState === "loading") {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Loading your profile…</p>
      </div>
    );
  }

  if (fetchState === "error") {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div className="max-w-sm w-full rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
          <p className="font-medium mb-1">We couldn't load your profile right now.</p>
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

  if (!user?.wpl_completed) {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center px-6 text-center">
        <div className="max-w-sm space-y-4">
          <h1 className="font-display text-2xl font-semibold text-ink-primary">
            Complete Work Pulse to unlock your profile.
          </h1>
          <p className="text-sm text-ink-secondary leading-relaxed">
            Work Pulse takes about 4 minutes and gives you a personalized
            narrative, your work archetype, and the foundation of your Solverah
            profile.
          </p>
          <button
            type="button"
            onClick={() => navigate("/work-pulse")}
            className="w-full bg-forest-dark text-white font-semibold py-3 rounded hover:bg-forest-mid transition-colors"
          >
            Start Work Pulse
          </button>
        </div>
      </div>
    );
  }

  if (!result) return null;

  return (
    <div className="min-h-screen bg-cream-base">
      <div className="mx-auto max-w-3xl px-6 pt-12 pb-20 space-y-8">

        {/* Header */}
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
            Your Solverah Profile
          </p>
          <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
            Here's what we know about you so far.
          </h1>
          <p className="text-sm text-ink-secondary pt-1">
            Your profile grows as you complete more of the Solverah ecosystem.
          </p>
        </div>

        {/* Progress indicator */}
        <div className="flex items-start gap-2 sm:gap-4 overflow-x-auto pb-1">
          {ECOSYSTEM_STEPS.map((step, i) => {
            const complete = i < 2;
            return (
              <div key={step.label} className="flex flex-col items-center gap-1.5 min-w-[56px]">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                    complete
                      ? "bg-forest-dark text-white"
                      : "bg-cream-muted text-ink-tertiary"
                  }`}
                >
                  {complete ? "✓" : ""}
                </div>
                <span className="text-xs text-ink-secondary text-center leading-tight">
                  {step.label}
                </span>
              </div>
            );
          })}
        </div>

        {/* WorkPulse card — unlocked */}
        <div className="rounded-xl border border-forest-light bg-forest-pale px-6 py-6 space-y-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
            ✦ Unlocked · Work Pulse™
          </p>
          <p className="font-display text-2xl font-semibold text-forest-dark">
            {result.archetype}
          </p>
          {result.archetype_description && (
            <p className="text-sm text-ink-primary leading-relaxed">
              {result.archetype_description}
            </p>
          )}
          {result.emerging_signals.length > 0 && (
            <>
              <hr className="border-forest-light/30" />
              <div className="flex flex-wrap gap-2">
                {result.emerging_signals.map((signal) => (
                  <span
                    key={signal.title}
                    className="rounded-full border border-forest-light bg-white px-3 py-1 text-xs font-semibold text-forest-mid"
                  >
                    {signal.title}
                  </span>
                ))}
              </div>
            </>
          )}
          <button
            type="button"
            onClick={() => navigate("/work-pulse/results")}
            className="text-sm font-semibold text-forest-dark hover:underline"
          >
            View full Work Pulse analysis →
          </button>
        </div>

        {/* Locked ecosystem cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {LOCKED_CARDS.map((card) => {
            const isCompanyLens = card.title === "CompanyLens™";
            return (
              <div
                key={card.title}
                className={`rounded-xl border border-cream-muted bg-white px-5 py-5 relative ${
                  isCompanyLens ? "" : "opacity-60"
                }`}
              >
                {!isCompanyLens && (
                  <Lock className="absolute top-4 right-4 w-4 h-4 text-ink-tertiary" />
                )}
                <p className="text-sm font-semibold text-ink-primary pr-6">{card.title}</p>
                <p className="text-xs text-ink-secondary mt-0.5 mb-2">{card.subtitle}</p>
                <p className="text-xs text-ink-secondary leading-relaxed mb-4">
                  {card.description}
                </p>
                {isCompanyLens ? (
                  <button
                    type="button"
                    onClick={() => navigate("/company-lens")}
                    className="bg-forest-dark text-white font-semibold px-3 py-1.5 rounded text-xs hover:bg-forest-mid"
                  >
                    Open CompanyLens™
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled
                    className="border border-cream-muted text-ink-tertiary text-xs font-semibold px-3 py-1.5 rounded cursor-not-allowed"
                  >
                    Unlocks with Work Pulse Pro
                  </button>
                )}
              </div>
            );
          })}
        </div>

      </div>
    </div>
  );
}
