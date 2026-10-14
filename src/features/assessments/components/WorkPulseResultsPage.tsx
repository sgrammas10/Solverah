/**
 * WorkPulseResultsPage — the retired 12-question Work Pulse's stored narrative, read-only.
 *
 * The original Work Pulse was retired on 2026-10-02 (the 24-item `core` instrument has
 * served /work-pulse since 2026-08-19, and has no results screen by design). Every
 * write door the old quiz had now answers 410 on the server, so this page no longer
 * enqueues a scoring job, polls one, or resubmits answers after a missing narrative:
 * those paths, and the answer draft they read, are deleted.
 *
 * What it still does is the smaller of the two options the retirement offered: a user
 * who finished the old quiz keeps a read-only view of the narrative stored for them
 * (`GET /me/assessments/work_pulse/result`); anyone else, or a sitting with no stored
 * narrative (a 404), is sent to /work-pulse. The route line in App.tsx is unchanged.
 */
import { Link, Navigate, useNavigate } from "react-router-dom";
import type { WpApiResponse } from "../useWP";
import { useWP } from "../useWP";
import { useAuth } from "../../auth";
import { useWorkPulseResult } from "../useWorkPulseResult";
import { ApiError } from "../../../shared/api/apiError";
import { TierBar } from "../../intake";

export default function WorkPulseResultsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { state } = useWP();

  const hasCached = state.cachedResult !== null;
  const legacyCompleter = Boolean(user?.wpl_completed);

  // The stored result, shared with IntelligencePage through one query. Fetched only
  // for a user the server says finished the old quiz and only when no screen has
  // already put it in the cache.
  const wpQuery = useWorkPulseResult({ enabled: legacyCompleter && !hasCached });
  const result: WpApiResponse | null = state.cachedResult ?? wpQuery.data ?? null;

  // Nothing to show: never took the old quiz, or took it and no narrative was stored.
  // Either way the instrument to take is the current one.
  const notFound = wpQuery.error instanceof ApiError && wpQuery.error.status === 404;
  if ((!legacyCompleter && !hasCached) || notFound) {
    return <Navigate to="/work-pulse" replace />;
  }

  // `isError && isFetching` is the retry in flight: the error object survives a
  // refetch, and rendering the card through it would make "Try again" look dead.
  if (wpQuery.isLoading || (wpQuery.isError && wpQuery.isFetching)) {
    return (
      <div className="min-h-screen bg-cream-base flex flex-col items-center justify-center gap-4">
        <div className="w-8 h-8 rounded-full border-2 border-forest-light border-t-transparent animate-spin" />
        <p className="text-sm text-ink-secondary">Loading your results…</p>
      </div>
    );
  }

  if (wpQuery.isError) {
    return (
      <div className="min-h-screen bg-cream-base flex items-center justify-center px-6">
        <div
          className="max-w-sm w-full rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700"
          role="alert"
        >
          <p className="font-medium mb-1">We couldn't load your results right now.</p>
          <p className="text-xs">Please try again in a moment.</p>
          <button
            type="button"
            onClick={() => wpQuery.refetch()}
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
            Your original Work Pulse
          </p>
          <h1 className="font-display text-2xl sm:text-3xl font-semibold text-ink-primary">
            Here's how you work
          </h1>
          {/* Says what this page is now: a record of the retired quiz, kept for the
              people who took it, not a result of the current instrument. */}
          <p className="text-sm text-ink-secondary">
            This is the analysis from the first version of Work Pulse, which has since been
            replaced. It's kept here for you to read; it no longer changes.{" "}
            <Link to="/work-pulse" className="font-semibold text-forest-dark hover:underline">
              Go to the current Work Pulse →
            </Link>
          </p>
        </div>

        {/* Narrative */}
        <div className="rounded-xl border border-cream-muted bg-white p-6 space-y-4">
          {paragraphs.map((para, i) => (
            <p key={i} className="text-base text-ink-primary leading-relaxed">
              {para}
            </p>
          ))}
        </div>

        {/* Emerging signals */}
        {result.emerging_signals.length > 0 && (
          <div className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-widest text-forest-light">
              Emerging signals
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {result.emerging_signals.map((signal) => (
                <div
                  key={signal.title}
                  className="rounded-lg border border-cream-muted bg-white px-5 py-4"
                >
                  <p className="text-sm font-semibold text-ink-primary mb-1">{signal.title}</p>
                  <p className="text-xs text-ink-secondary leading-relaxed">{signal.description}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Archetype callout */}
        <div className="rounded-xl border border-forest-light bg-forest-pale px-6 py-5">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-1">
            Your primary work archetype
          </p>
          <p className="font-display text-xl font-semibold text-forest-dark">{result.archetype}</p>
          {result.archetype_description && (
            <p className="text-sm text-forest-dark leading-relaxed mt-3">
              {result.archetype_description}
            </p>
          )}
        </div>

        {/* What this unlocks */}
        <div className="rounded-xl border border-cream-muted bg-white px-6 py-5">
          <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-2">
            Who sees this
          </p>
          {/* This used to say the narrative was visible to employers. It never
              was, and the promise on /work-pulse and /trust is that employers
              never see what you tell Work Pulse. */}
          <p className="text-sm text-ink-secondary leading-relaxed">
            Only you. Your archetype and narrative stay in your Intelligence Hub, where
            they shape what Solverah shows you. Employers never see them.{" "}
            <Link to="/trust" className="font-semibold text-forest-dark hover:underline">
              How this works →
            </Link>
          </p>
          <button
            type="button"
            onClick={() => navigate("/intelligence")}
            className="mt-4 w-full bg-forest-dark text-white font-semibold py-3.5 rounded hover:bg-forest-mid transition-colors"
          >
            Go to Intelligence Hub →
          </button>
        </div>

        {/* CompanyLens: live. Words only -- no score, percentage or probability
            anywhere on this card (D-15, product decisions section 2). */}
        {(() => {
          const topSignalTitle =
            result.emerging_signals.length > 0
              ? result.emerging_signals[0].title
              : result.archetype;
          return (
            <div className="rounded-xl border border-cream-muted bg-white px-6 py-5">
              <p className="text-xs font-semibold uppercase tracking-widest text-forest-light mb-2">
                Based on your results
              </p>
              <h2 className="font-display text-lg font-semibold text-ink-primary">
                Your {topSignalTitle} signals may reveal something about company fit.
              </h2>
              <p className="text-sm text-ink-secondary leading-relaxed mt-2">
                CompanyLens reads real company environments against what you need, and
                shows you what each company looks like on the things that matter to you,
                where the evidence is thin, and what to ask next.
              </p>
              <Link
                to="/company-lens"
                className="mt-4 block w-full rounded bg-forest-dark py-3.5 text-center font-semibold text-white transition-colors hover:bg-forest-mid"
              >
                Open CompanyLens →
              </Link>
            </div>
          );
        })()}

        {/* Tier progression */}
        <TierBar nextTierIndex={2} />

        {/* Pro teaser -- a label, not a button: there is nothing to buy yet. */}
        <div className="pt-2">
          <p className="rounded-[4px] border border-dashed border-cream-muted bg-white px-4 py-3.5 text-center text-sm font-semibold text-ink-secondary">
            Work Pulse Pro · coming soon
          </p>
          <p className="text-xs text-ink-tertiary text-center mt-2">
            Deeper analysis, personalised recommendations, and more.
          </p>
        </div>

      </div>
    </div>
  );
}
