/**
 * Public surface of the companies slice — the only legal import path for
 * other feature slices (ARCHITECTURE.md 6.4).
 *
 * Deliberately empty: no other slice consumes anything from companies today.
 * CompanyDetailPage is reached only through src/app's route-level lazy()
 * import, which deep-imports by design.
 */
export {};
