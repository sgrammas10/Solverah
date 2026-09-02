/**
 * Public surface of the landing slice — the only legal import path for other
 * feature slices (ARCHITECTURE.md 6.4).
 *
 * NOTE: landing is a ninth slice beyond the eight named in ARCHITECTURE.md
 * 3.1. The prelaunch/marketing/legal pages fit none of the eight (they are
 * not intake machinery — the funnel hooks and forms they render live in
 * features/intake), so they get their own slice rather than a forced home.
 *
 * Deliberately empty: no other slice consumes anything from landing. All of
 * its pages are reached through src/app's routes (deep imports by design).
 */
export {};
