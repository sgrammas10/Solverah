/**
 * RouteErrorBoundary.tsx — one broken screen must not cost the user the app.
 *
 * Placed inside `AppShell`, wrapping `<Routes>` but *below* the `Header`. That
 * position is the entire design:
 *
 *   AppShell
 *     Header            <- outside the boundary, so navigation survives
 *     RouteErrorBoundary
 *       Suspense
 *         Routes        <- a throw in here is contained
 *     footer            <- outside the boundary
 *
 * If the boundary wrapped the shell instead, a crash on one results page would
 * take the Header with it and strand the user with no way out but the browser
 * back button. Keeping the chrome outside means the fallback occupies the
 * content area and every nav link still works.
 *
 * Recovery has two independent routes out, because a caught error has two
 * plausible causes:
 *
 *   "Try again"  — resets the boundary *and*, through `QueryErrorResetBoundary`,
 *                  the failed queries underneath it. Both halves are required:
 *                  `useProfile` sets `throwOnError`, so a network failure lands
 *                  here, and clearing only the boundary would re-render the
 *                  consumer, re-read the still-errored query, and throw again
 *                  before paint. That is a retry button that cannot work, and
 *                  it is the standard way this integration is got wrong.
 *
 *   Navigation   — `resetKeys={[pathname]}` clears the error when the user goes
 *                  somewhere else, so the broken screen does not follow them.
 *                  Without it the boundary stays latched and every subsequent
 *                  route renders the fallback.
 *
 * `key={pathname}` on the Suspense boundary is separate and also deliberate: it
 * discards the previous route's suspended subtree on navigation rather than
 * letting React try to reconcile a half-mounted screen with a different one.
 */
import { Suspense, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { QueryErrorResetBoundary } from "@tanstack/react-query";

import { ErrorBoundary } from "./ErrorBoundary";
import { RouteFallback } from "./RouteFallback";

/** The in-shell fallback. Sized to the content area, not the viewport. */
function RouteErrorFallback({ reset }: { reset: () => void }) {
  return (
    <div
      role="alert"
      className="min-h-[60vh] bg-cream-base flex items-center justify-center px-6 py-16"
    >
      <div className="max-w-sm w-full rounded-lg border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
        <p className="font-medium mb-1">We couldn&apos;t load this page.</p>
        <p className="text-xs">
          Something went wrong on our side. Your account and saved work are
          unaffected — you can retry, or use the menu above to go somewhere else.
        </p>
        <button
          type="button"
          onClick={reset}
          className="mt-3 text-xs font-semibold text-red-700 underline"
        >
          Try again
        </button>
      </div>
    </div>
  );
}

/**
 * Contain render-phase failures for the currently matched route.
 *
 * Also owns the route-level `Suspense`, because the two are inseparable in
 * practice: `React.lazy` throws a promise on the way in and can throw an
 * `Error` on the way out — a chunk that 404s after a redeploy is the common
 * case — and that rejection has to land somewhere other than a blank page.
 */
export function RouteErrorBoundary({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();

  return (
    <QueryErrorResetBoundary>
      {({ reset: resetQueries }) => (
        <ErrorBoundary
          resetKeys={[pathname]}
          onReset={resetQueries}
          fallback={(_error, reset) => <RouteErrorFallback reset={reset} />}
        >
          <Suspense key={pathname} fallback={<RouteFallback />}>
            {children}
          </Suspense>
        </ErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}

export default RouteErrorBoundary;
