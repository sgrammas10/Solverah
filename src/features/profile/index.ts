/**
 * Public surface of the profile slice — the only legal import path for other
 * feature slices (ARCHITECTURE.md 6.4).
 *
 * The profile pages (JobSeekerProfile, JobSeekerDashboard) are consumed only
 * by src/app's route-level lazy() imports, which deep-import by design, so
 * they are not exported here.
 */
export { useProfile, profileKeys, seedProfileCache } from "./useProfile";
export { useProfileForm } from "./useProfileForm";
export type { ProfileFormData } from "./types";
