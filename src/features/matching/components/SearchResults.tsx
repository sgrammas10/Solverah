/**
 * SearchResults -- /search, shown honestly as not built yet.
 *
 * It used to filter `/me/recommendations` by `?q=` and render the matches with
 * pagination and a "Match score". That list is always empty (see
 * useRecommendations.ts), so every query, real or gibberish, ended at
 * "No results found for ...", which read as a search that works and found
 * nothing. It also rendered in the old dark palette on the cream page.
 *
 * Until there is something to search, the route says so, the way
 * CompanyLensPage does while its model is pending, and makes no request.
 * `?q=` is ignored on purpose: echoing it back would imply it was used.
 */
import { Link } from "react-router-dom";
import { Search } from "lucide-react";

export default function SearchResults() {
  return (
    <div className="min-h-screen bg-cream-base flex items-start justify-center px-4 sm:px-6 pt-16 pb-20">
      <div className="rounded-xl border border-cream-muted bg-white px-6 py-8 text-center max-w-md w-full">
        <Search className="h-8 w-8 text-forest-light mx-auto mb-4" aria-hidden="true" />
        <h1 className="font-display text-xl font-semibold text-ink-primary mb-2">
          Search is coming soon
        </h1>
        <p className="text-sm text-ink-secondary leading-relaxed mb-6">
          We're still building search for companies and roles, so there's
          nothing to look through yet. We'll switch it on once it can give you
          real answers.
        </p>
        <Link
          to="/job-seeker/dashboard"
          className="block w-full bg-forest-dark text-white text-sm font-semibold py-3 rounded-[4px] hover:bg-forest-mid transition-colors"
        >
          Back to your dashboard
        </Link>
      </div>
    </div>
  );
}
