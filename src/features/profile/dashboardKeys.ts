/**
 * Query keys for the `/me/dashboard` document. `all` is the invalidation handle.
 *
 * Its own module rather than a constant inside JobSeekerDashboard.tsx so the
 * profile writers (useProfileForm, the career-status control) can drop the
 * dashboard after a write without importing a lazy-loaded route component.
 * Until 2026-10-02 nothing invalidated it at all, so a profile, status or
 * resume write left the dashboard showing the steps the user had just done.
 */
export const dashboardKeys = {
  all: ["dashboard"] as const,
  summary: () => ["dashboard", "summary"] as const,
};
