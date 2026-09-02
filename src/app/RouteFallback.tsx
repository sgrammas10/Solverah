/**
 * RouteFallback.tsx — what the content area shows while a route's content is
 * not ready to draw.
 *
 * Two waits end up here, and rendering them identically is deliberate:
 *
 *   Chunk in flight — the route-level Suspense fallback: the code for this
 *     particular screen is still downloading.
 *
 *   Session in flight — RequireAuth holds a protected route's subtree back
 *     until `GET /auth/session` has said who the visitor is. (AuthProvider
 *     used to answer this wait with a full-screen spinner that blocked the
 *     whole app, public routes included; retiring that gate is what moved the
 *     wait here, into the content area, beneath a Header that already works.)
 *
 * To the user both are the same statement — "this screen is on its way, the
 * chrome around you is real" — so they get the same skeleton, in the same
 * place. Two different placeholders trading places in the same spot is the
 * "stutter" this file exists to avoid: on a hard refresh of a protected
 * screen, the session wait ends and the chunk wait begins with no visible
 * seam, because the fallback never changes.
 *
 * The 240ms delay is the other half. Most chunks arrive in well under that on a
 * warm connection, and a placeholder that appears and vanishes inside 60ms is a
 * flicker that costs more than the reassurance it buys. Rendering nothing for
 * the first 240ms means fast navigations look instant and only genuinely slow
 * ones grow a skeleton. It is a CSS animation delay rather than a JS timer so
 * there is no extra render, no state, and nothing to clean up on unmount.
 */

/** Neutral bars, matched to the widest common page layout (max-w-3xl). */
export function RouteFallback() {
  return (
    <div
      // Not `role="status"`: this is decorative scaffolding, and announcing it
      // would interrupt a screen reader mid-navigation to say nothing useful.
      // `aria-hidden` leaves the announcement to the route that lands.
      aria-hidden="true"
      className="min-h-[60vh] bg-cream-base px-6 pt-12 pb-20 animate-deferred-fade-in"
    >
      <div className="mx-auto max-w-3xl space-y-6">
        <div className="h-8 w-1/3 rounded bg-cream-muted" />
        <div className="space-y-3">
          <div className="h-4 w-full rounded bg-cream-muted" />
          <div className="h-4 w-5/6 rounded bg-cream-muted" />
          <div className="h-4 w-2/3 rounded bg-cream-muted" />
        </div>
        <div className="h-40 w-full rounded-lg bg-cream-muted" />
      </div>
    </div>
  );
}

export default RouteFallback;
