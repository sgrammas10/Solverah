import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../auth";

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

/**
 * One page of `GET /api/v1/me/matches`.
 *
 * Phase 1b replaced `GET /company-lens/matches`, which returned two fixed-size
 * slices -- `best_fits` and `worst_fits` -- in a single body with nothing
 * reachable beyond them. The list is now cursor-paginated in one direction at a
 * time, so `?order=best` and `?order=worst` are two walks through one ranking
 * and either can be continued past the first page.
 */
interface MatchesPage {
  data: CompanyMatch[];
  next_cursor: string | null;
  total_companies_scored: number;
  lens: string;
  order: string;
}

/** Both ends of the ranking, as this screen renders them. */
interface MatchesView {
  best: CompanyMatch[];
  worst: CompanyMatch[];
  total_companies_scored: number;
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

interface MatchRowProps {
  match: CompanyMatch;
  accent: "forest" | "amber";
}

function MatchRow({ match, accent }: MatchRowProps) {
  const navigate = useNavigate();

  return (
    <div
      className="flex items-center gap-3 px-4 py-2.5 rounded-lg border border-cream-muted bg-white hover:border-forest-light transition-colors cursor-pointer"
      onClick={() =>
        navigate(`/companies/${match.id}`, {
          state: {
            fit_score: match.fit_score,
            top_matching_dimensions: match.top_matching_dimensions,
            top_mismatching_dimensions: match.top_mismatching_dimensions,
          },
        })
      }
    >
      <span className="font-semibold text-sm text-ink-primary min-w-0 truncate flex-1">
        {match.name}
      </span>
      <span
        className={`text-sm font-semibold shrink-0 ${
          accent === "forest" ? "text-forest-dark" : "text-amber-600"
        }`}
      >
        {Math.round(match.fit_score * 100)}%
      </span>
      <span className="text-xs font-semibold text-forest-mid shrink-0">→</span>
    </div>
  );
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

/** Query keys for the two-ended matches view. `all` is the invalidation handle. */
export const companyMatchKeys = {
  all: ["companyMatches"] as const,
  view: (limit: number) => ["companyMatches", "view", limit] as const,
};

export default function CompanyLensPage() {
  const navigate = useNavigate();
  const { fetchWithAuth } = useAuth();

  const [limit, setLimit] = useState(5);
  const [viewMode, setViewMode] = useState<"card" | "list">("card");

  // Keyed on `limit`: "Show more" bumps the key, and the fresh key loads like
  // the hand-rolled refetch did. A 5xx now gets queryClient.ts's bounded
  // retries (safe: Phase 3a removed every commit from GET handlers), while the
  // no-prefs rejection is a 4xx and surfaces immediately.
  const matchesQuery = useQuery({
    queryKey: companyMatchKeys.view(limit),
    queryFn: async (): Promise<MatchesView> => {
      // Two requests where there was one: the endpoint no longer returns
      // both ends of the ranking in a single body. They are issued together,
      // so this is still one round trip's latency.
      const [best, worst] = await Promise.all([
        fetchWithAuth<MatchesPage>(`/me/matches?order=best&limit=${limit}`),
        fetchWithAuth<MatchesPage>(`/me/matches?order=worst&limit=${limit}`),
      ]);
      // Drop from the weak end anything already shown at the strong end.
      //
      // The endpoint this replaced partitioned at the midpoint whenever there
      // were at most 2*limit companies, so a company could never appear in
      // both lists. A paginated list cannot do that -- it walks a ranking, it
      // does not carve one -- so the screen has to. Filtering rather than
      // slicing at a computed midpoint means no overlap regardless of how the
      // two page sizes and the total relate.
      const shownAsBest = new Set(best.data.map((match) => match.id));
      return {
        best: best.data,
        worst: worst.data.filter((match) => !shownAsBest.has(match.id)),
        total_companies_scored: best.total_companies_scored,
      };
    },
  });

  const data = matchesQuery.data ?? null;
  const errorMsg =
    matchesQuery.error instanceof Error ? matchesQuery.error.message : "";
  const needsPrefs =
    matchesQuery.isError &&
    (errorMsg.includes("culture preferences") ||
      errorMsg.includes("Work Pulse not completed"));

  const handleShowMore = () => {
    setLimit(limit + 5);
  };

  if (matchesQuery.isLoading) {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">
          Scoring companies against your Work Pulse results…
        </p>
      </div>
    );
  }

  if (matchesQuery.isError && !needsPrefs) {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div className="max-w-sm w-full rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
          <p className="font-medium mb-1">Couldn't load your company matches.</p>
          <p className="text-xs">Please try again in a moment.</p>
          <button
            type="button"
            onClick={() => matchesQuery.refetch()}
            className="mt-3 text-xs font-semibold text-red-700 underline"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  if (needsPrefs) {
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

        {/* Back link */}
        <button
          type="button"
          onClick={() => navigate("/intelligence")}
          className="text-sm font-semibold text-forest-mid hover:underline"
        >
          ← Back to Intelligence
        </button>

        {/* Header */}
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light">
            CompanyLens™
          </p>
          <div className="flex items-start justify-between gap-4">
            <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
              Companies ranked by how well they match how you work.
            </h1>
            {/* View toggle */}
            <div className="flex shrink-0 items-center gap-1 border border-cream-muted rounded-lg p-1 bg-white mt-1">
              <button
                type="button"
                onClick={() => setViewMode("card")}
                title="Card view"
                className={`p-1.5 rounded transition-colors ${
                  viewMode === "card"
                    ? "bg-forest-dark text-white"
                    : "text-ink-secondary hover:text-ink-primary"
                }`}
              >
                {/* Grid icon */}
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <rect x="1" y="1" width="6" height="6" rx="1" fill="currentColor" />
                  <rect x="9" y="1" width="6" height="6" rx="1" fill="currentColor" />
                  <rect x="1" y="9" width="6" height="6" rx="1" fill="currentColor" />
                  <rect x="9" y="9" width="6" height="6" rx="1" fill="currentColor" />
                </svg>
              </button>
              <button
                type="button"
                onClick={() => setViewMode("list")}
                title="List view"
                className={`p-1.5 rounded transition-colors ${
                  viewMode === "list"
                    ? "bg-forest-dark text-white"
                    : "text-ink-secondary hover:text-ink-primary"
                }`}
              >
                {/* List icon */}
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <rect x="1" y="2" width="14" height="2.5" rx="1" fill="currentColor" />
                  <rect x="1" y="6.75" width="14" height="2.5" rx="1" fill="currentColor" />
                  <rect x="1" y="11.5" width="14" height="2.5" rx="1" fill="currentColor" />
                </svg>
              </button>
            </div>
          </div>
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
          <div className={viewMode === "card" ? "space-y-3" : "space-y-1.5"}>
            {data.best.map((match) =>
              viewMode === "card" ? (
                <MatchCard key={match.id} match={match} accent="forest" />
              ) : (
                <MatchRow key={match.id} match={match} accent="forest" />
              )
            )}
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
          <div className={viewMode === "card" ? "space-y-3" : "space-y-1.5"}>
            {data.worst.map((match) =>
              viewMode === "card" ? (
                <MatchCard key={match.id} match={match} accent="amber" />
              ) : (
                <MatchRow key={match.id} match={match} accent="amber" />
              )
            )}
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
