/**
 * Public surface of the intelligence slice — the only legal import path for
 * other feature slices (ARCHITECTURE.md 6.4).
 *
 * Deliberately empty: no other slice consumes anything from intelligence
 * today. Its pages and quiz components are reached only through src/app's
 * route-level lazy() imports, which deep-import by design.
 */
export {};
