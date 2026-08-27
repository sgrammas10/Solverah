/**
 * RouteFallback.tsx — what the content area shows while a route's chunk is in flight.
 *
 * This is the file where the "two spinners fighting each other" problem gets
 * settled, so the reasoning lives here rather than in a commit message.
 *
 * There are two loading states in this app and they answer different questions:
 *
 *   AuthProvider's spinner — "we do not know who you are yet." It owns the
 *     whole viewport, and correctly so: it renders *instead of* the Router, and
 *     even the Header cannot be drawn honestly before the session resolves,
 *     because the Header's own contents depend on whether anyone is signed in.
 *
 *   This fallback — "we know who you are, the chrome around you is already
 *     correct, and the code for this particular screen is still downloading."
 *     It renders below a real Header, inside the content area, and never
 *     replaces the shell.
 *
 * So the two never appear at the same time and never in the same place: the
 * first is gone before the Router mounts, and the second only ever appears
 * beneath a Header the first one was blocking. Chaining a second *full-screen
 * centred spinner* behind the first is what would have read as a stutter — the
 * same shape restarting in the same spot for no reason the user can see. A
 * skeleton in the content region reads instead as the page filling in, which is
 * what is actually happening.
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
