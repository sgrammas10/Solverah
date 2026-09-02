/**
 * AppErrorBoundary.tsx — the outermost net, for throws that have nowhere else to go.
 *
 * This sits above `QueryClientProvider`, `AuthProvider` and `Router` in
 * `main.tsx`, which is the point: it catches the failures that happen *before*
 * routing exists. A throw inside `AuthProvider`'s render, a bad `createRoot`
 * subtree, a provider misconfiguration — none of those are inside a route, so
 * `RouteErrorBoundary` never sees them, and without this the user gets the
 * blank white page that Phase 4b exists to eliminate.
 *
 * Two consequences follow from being above the Router, and both shape this file:
 *
 *  1. There is no `<Link>` and no `navigate()` here — react-router hooks throw
 *     outside a Router. Recovery is a full document load via `window.location`,
 *     which is also the more honest instrument: if the provider tree itself
 *     failed, re-rendering it in place is unlikely to produce a different
 *     result, and a fresh boot might.
 *  2. There is no `resetKeys`. Nothing above the Router changes on navigation,
 *     so there is no signal to reset against. This boundary is terminal by
 *     design: reaching it means the app shell is broken, not a screen.
 *
 * Styling stays deliberately primitive — no design tokens, no shared layout
 * components. Anything imported here is code that must survive the failure it
 * is reporting on, and the fewer modules that has to be true of, the better.
 */
import type { ReactNode } from "react";

import { ErrorBoundary } from "./ErrorBoundary";

function reload() {
  window.location.reload();
}

/** The full-page fallback. Deliberately does not print `error.message`. */
function AppErrorFallback() {
  return (
    <div
      role="alert"
      className="min-h-screen bg-cream-base flex items-center justify-center px-6"
    >
      <div className="max-w-md w-full text-center space-y-4">
        <h1 className="font-display text-2xl font-semibold text-ink-primary">
          Something went wrong.
        </h1>
        <p className="text-sm text-ink-secondary leading-relaxed">
          The page didn&apos;t load correctly. Reloading usually fixes it — your
          account and saved work are unaffected.
        </p>
        <button
          type="button"
          onClick={reload}
          className="w-full bg-forest-dark text-white font-semibold py-3 rounded hover:bg-forest-mid transition-colors"
        >
          Reload the page
        </button>
      </div>
    </div>
  );
}

/**
 * Wrap the entire application.
 *
 * The error message is intentionally not surfaced to the user: at this level it
 * is a bundler or provider failure whose text ("Cannot read properties of
 * undefined") tells them nothing actionable. `ErrorBoundary` has already put
 * the real error and component stack in the console for whoever is debugging.
 */
export function AppErrorBoundary({ children }: { children: ReactNode }) {
  return <ErrorBoundary fallback={() => <AppErrorFallback />}>{children}</ErrorBoundary>;
}

export default AppErrorBoundary;
