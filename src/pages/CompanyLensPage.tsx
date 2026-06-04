import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/useAuth";

type FetchState = "loading" | "error" | "success" | "no-prefs";

interface CompanyMatch {
  id: number;
  name: string;
  slug: string;
  industry: string;
  fit_score: number;
  top_matching_dimensions: string[];
  top_mismatching_dimensions: string[];
  fit_summary: string;
}

interface MatchesResponse {
  best_fits: CompanyMatch[];
  worst_fits: CompanyMatch[];
  total_companies_scored: number;
  limit: number;
}

const DIM_LABELS: Record<string, string> = {
  empathy: "Empathy",
  creative_drive: "Creative Drive",
  adaptability: "Adaptability",
  futuristic: "Future Orientation",
  harmony: "Harmony",
  data_orientation: "Data Orientation",
  pace: "Work Pace",
  work_environment: "Work Environment",
};

interface MatchCardProps {
  match: CompanyMatch;
  accent: "forest" | "amber";
}

function MatchCard({ match, accent }: MatchCardProps) {
  const navigate = useNavigate();

  return (
    <div className="rounded-xl border border-cream-muted bg-white px-5 py-5 space-y-3 hover:border-forest-light transition-colors">
      {/* Top row */}
      <div className="flex justify-between items-start gap-3">
        <div>
          <p className="font-display text-lg font-semibold text-ink-primary">{match.name}</p>
          {match.industry && (
            <p className="text-xs text-forest-light mt-0.5">{match.industry}</p>
          )}
        </div>
        <p
          className={`shrink-0 text-xl font-semibold ${
            accent === "forest" ? "text-forest-dark" : "text-amber-600"
          }`}
        >
          {Math.round(match.fit_score * 100)}% match
        </p>
      </div>

      {/* Dimension chips */}
      {(match.top_matching_dimensions.length > 0 ||
        match.top_mismatching_dimensions.length > 0) && (
        <div className="flex flex-wrap gap-1.5">
          {match.top_matching_dimensions.map((d) => (
            <span
              key={`m-${d}`}
              className="bg-forest-pale text-forest-mid border border-forest-light text-xs font-semibold px-2.5 py-1 rounded-full"
            >
              {DIM_LABELS[d] ?? d}
            </span>
          ))}
          {match.top_mismatching_dimensions.map((d) => (
            <span
              key={`mm-${d}`}
              className="bg-amber-50 text-amber-700 border border-amber-200 text-xs font-semibold px-2.5 py-1 rounded-full"
            >
              {DIM_LABELS[d] ?? d}
            </span>
          ))}
        </div>
      )}

      {/* Fit summary */}
      {match.fit_summary && (
        <p className="text-sm text-ink-secondary leading-relaxed">{match.fit_summary}</p>
      )}

      {/* Footer link */}
      <button
        type="button"
        onClick={() =>
          navigate(`/companies/${match.id}`, {
            state: {
              fit_score: match.fit_score,
              top_matching_dimensions: match.top_matching_dimensions,
              top_mismatching_dimensions: match.top_mismatching_dimensions,
            },
          })
        }
        className="text-sm font-semibold text-forest-mid hover:underline"
      >
        View company profile →
      </button>
    </div>
  );
}

export default function CompanyLensPage() {
  const navigate = useNavigate();
  const { fetchWithAuth } = useAuth();

  const [fetchState, setFetchState] = useState<FetchState>("loading");
  const [data, setData] = useState<MatchesResponse | null>(null);
  const [limit, setLimit] = useState(5);

  const fetchMatches = useCallback(
    async (lim: number) => {
      setFetchState("loading");
      try {
        const res = await fetchWithAuth<MatchesResponse>(
          `/company-lens/matches?limit=${lim}`
        );
        setData(res);
        setFetchState("success");
      } catch (err) {
        const msg = err instanceof Error ? err.message : "";
        if (
          msg.includes("culture preferences") ||
          msg.includes("Work Pulse not completed")
        ) {
          setFetchState("no-prefs");
        } else {
          setFetchState("error");
        }
      }
    },
    [fetchWithAuth]
  );

  useEffect(() => {
    fetchMatches(limit);
  }, []); // intentionally runs once on mount

  const handleShowMore = () => {
    const next = limit + 5;
    setLimit(next);
    fetchMatches(next);
  };

  if (fetchState === "loading") {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">
          Scoring companies against your Work Pulse results…
        </p>
      </div>
    );
  }

  if (fetchState === "error") {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div className="max-w-sm w-full rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
          <p className="font-medium mb-1">Couldn't load your company matches.</p>
          <p className="text-xs">Please try again in a moment.</p>
          <button
            type="button"
            onClick={() => fetchMatches(limit)}
            className="mt-3 text-xs font-semibold text-red-700 underline"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  if (fetchState === "no-prefs") {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div className="rounded-xl border border-cream-muted bg-white px-6 py-8 text-center max-w-sm w-full">
          <h2 className="font-display text-xl font-semibold text-ink-primary mb-2">
            Complete Work Pulse to unlock CompanyLens™
          </h2>
          <p className="text-sm text-ink-secondary leading-relaxed mb-6">
            Work Pulse takes about 4 minutes and gives Solverah enough to score
            companies against how you work.
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

  if (!data) return null;

  const maxPerGroup = Math.floor(data.total_companies_scored / 2);
  const showMoreVisible = limit < maxPerGroup;

  return (
    <div className="min-h-screen bg-cream-base">
      <div className="mx-auto max-w-3xl px-6 pt-12 pb-20 space-y-10">

        {/* Header */}
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
            CompanyLens™
          </p>
          <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
            Companies ranked by how well they match how you work.
          </h1>
          <p className="text-sm text-ink-secondary">
            Based on your Work Pulse results. Scores reflect culture and environment
            fit — not job availability.
          </p>
        </div>

        {/* Section 1 — Strong fits */}
        <div className="space-y-4">
          <h2 className="font-display text-lg font-semibold text-ink-primary">
            Companies that match how you work
          </h2>
          <div className="space-y-3">
            {data.best_fits.map((match) => (
              <MatchCard key={match.id} match={match} accent="forest" />
            ))}
          </div>
          {showMoreVisible && (
            <div className="flex justify-center pt-2">
              <button
                type="button"
                onClick={handleShowMore}
                className="border-2 border-forest-dark text-forest-dark font-semibold px-5 py-2.5 rounded hover:bg-forest-pale transition-colors"
              >
                Show more
              </button>
            </div>
          )}
        </div>

        {/* Section 2 — Approach carefully */}
        <div className="space-y-4">
          <h2 className="font-display text-lg font-semibold text-ink-primary">
            Companies worth understanding before committing
          </h2>
          <div className="space-y-3">
            {data.worst_fits.map((match) => (
              <MatchCard key={match.id} match={match} accent="amber" />
            ))}
          </div>
          {showMoreVisible && (
            <div className="flex justify-center pt-2">
              <button
                type="button"
                onClick={handleShowMore}
                className="border-2 border-amber-400 text-amber-700 font-semibold px-5 py-2.5 rounded hover:bg-amber-50 transition-colors"
              >
                Show more
              </button>
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
