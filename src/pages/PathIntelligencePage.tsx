import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/useAuth";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PathSuggestion {
  onet_code: string;
  title: string;
  why_text: string;
  profile_dimensions: string[];
  match_score: number;
}

export interface PathSuggestionsResponse {
  suggestions: PathSuggestion[];
  career_status: string;
  generated_at: string;
}

type FetchState = "loading" | "error" | "career_status_not_set" | "success";

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SkeletonCards() {
  return (
    <div className="space-y-4" aria-label="Loading suggestions">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="rounded-xl border border-cream-muted bg-white px-5 py-5 animate-pulse"
        >
          <div className="h-4 bg-cream-muted rounded w-1/3 mb-3" />
          <div className="h-3 bg-cream-muted rounded w-full mb-2" />
          <div className="h-3 bg-cream-muted rounded w-5/6 mb-4" />
          <div className="flex gap-2">
            <div className="h-5 bg-cream-muted rounded-full w-24" />
            <div className="h-5 bg-cream-muted rounded-full w-32" />
          </div>
        </div>
      ))}
    </div>
  );
}

// Placeholder — will be replaced by the full component in SOL-31.
function CareerStatusOnboardingPrompt() {
  const navigate = useNavigate();
  return (
    <div className="rounded-xl border border-cream-muted bg-white px-6 py-8 text-center space-y-4">
      <p className="font-semibold text-ink-primary">Set your career status to get started.</p>
      <p className="text-sm text-ink-secondary leading-relaxed">
        Tell us where you are in your career so we can tailor your path suggestions.
      </p>
      <button
        type="button"
        onClick={() => navigate("/job-seeker/profile")}
        className="bg-forest-dark text-white font-semibold px-4 py-2 rounded text-sm hover:bg-forest-mid transition-colors"
      >
        Update Profile
      </button>
    </div>
  );
}

// Placeholder — will be replaced by the full component in SOL-37.
function PathSuggestionCards({ suggestions }: { suggestions: PathSuggestion[] }) {
  return (
    <div className="space-y-4">
      {suggestions.map((s) => (
        <div
          key={s.onet_code}
          className="rounded-xl border border-cream-muted bg-white px-5 py-5"
        >
          <p className="font-semibold text-ink-primary">{s.title}</p>
          <p className="text-xs text-ink-secondary mt-1">{s.why_text}</p>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function PathIntelligencePage() {
  const { fetchWithAuth } = useAuth();
  const [fetchState, setFetchState] = useState<FetchState>("loading");
  const [data, setData] = useState<PathSuggestionsResponse | null>(null);
  const hasFiredRef = useRef(false);

  const fetchSuggestions = useCallback(async () => {
    setFetchState("loading");
    try {
      const result = await fetchWithAuth<PathSuggestionsResponse>(
        "/intelligence/path-suggestions"
      );
      setData(result);
      setFetchState("success");
    } catch (err) {
      if (err instanceof Error && err.message === "career_status_not_set") {
        setFetchState("career_status_not_set");
      } else {
        setFetchState("error");
      }
    }
  }, [fetchWithAuth]);

  useEffect(() => {
    if (!hasFiredRef.current) {
      hasFiredRef.current = true;
      fetchSuggestions();
    }
  }, []); // intentionally runs once on mount; hasFiredRef guards against Strict Mode double-fire

  return (
    <div className="min-h-screen bg-cream-base">
      <div className="mx-auto max-w-2xl px-6 pt-12 pb-20 space-y-8">

        {/* Header */}
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
              Path Intelligence
            </p>
            <span className="rounded-full bg-forest-pale border border-forest-light px-2 py-0.5 text-xs font-semibold text-forest-mid">
              Pro
            </span>
          </div>
          <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
            Your Career Paths
          </h1>
          <p className="text-sm text-ink-secondary pt-1">
            Career paths scored against your skills and work profile, with plain-language
            guidance on why each one fits.
          </p>
        </div>

        {/* Loading */}
        {fetchState === "loading" && <SkeletonCards />}

        {/* Error */}
        {fetchState === "error" && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
            <p className="font-medium mb-1">
              We couldn't load your path suggestions right now.
            </p>
            <p className="text-xs">Please try again in a moment.</p>
            <button
              type="button"
              onClick={fetchSuggestions}
              className="mt-3 text-xs font-semibold text-red-700 underline"
            >
              Try again
            </button>
          </div>
        )}

        {/* Career status not set */}
        {fetchState === "career_status_not_set" && <CareerStatusOnboardingPrompt />}

        {/* Success */}
        {fetchState === "success" && data && (
          <PathSuggestionCards suggestions={data.suggestions} />
        )}

      </div>
    </div>
  );
}
