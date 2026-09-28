/**
 * Feed -- /feed, shown honestly as not built yet.
 *
 * The page used to be a job board's shell: a search box into /search, a
 * Filters button that did nothing, Job Feed / Messages / Notifications tabs,
 * "Your Stats" at "--", and a recommendations list fed by an endpoint that is
 * always empty (see useRecommendations.ts). None of it was wired, and it was
 * drawn in the old dark palette on the cream page. The header's Feed link
 * already opens a "Feature coming soon" modal rather than navigating here, so
 * this route is only reached by typing the URL -- it now says the same thing
 * the modal does, the way CompanyLensPage does while its model is pending,
 * and makes no request.
 */
import { Link } from 'react-router-dom';
import { Newspaper } from 'lucide-react';
import { useAuth } from '../../auth';

function Feed() {
  const { user } = useAuth();
  const firstName = user?.name?.split(' ')[0];

  return (
    <div className="min-h-screen bg-cream-base font-sans text-ink-primary">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <h1 className="font-display text-3xl font-bold text-ink-primary">
          {firstName ? `Your feed, ${firstName}` : 'Your feed'}
        </h1>

        <div className="mt-8 rounded-xl border border-cream-muted bg-white px-6 py-8 text-center">
          <Newspaper className="h-8 w-8 text-forest-light mx-auto mb-4" aria-hidden="true" />
          <h2 className="font-display text-xl font-semibold text-ink-primary mb-2">
            The feed is coming soon
          </h2>
          <p className="text-sm text-ink-secondary leading-relaxed max-w-md mx-auto">
            This is where roles, messages and updates will collect once they're
            ready. None of that is live yet, so there's nothing to show here for
            now. Your dashboard and Intelligence pages are up and running.
          </p>
          <div className="mt-6 flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              to="/job-seeker/dashboard"
              className="bg-forest-dark text-white text-sm font-semibold px-6 py-3 rounded-[4px] hover:bg-forest-mid transition-colors"
            >
              Go to your dashboard
            </Link>
            <Link
              to="/intelligence"
              className="border border-forest-dark text-forest-dark text-sm font-semibold px-6 py-3 rounded-[4px] hover:bg-forest-pale transition-colors"
            >
              Open Intelligence
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Feed;
