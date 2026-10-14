/**
 * useSetCareerStatus — `PATCH /me/career-status`, and what has to be refreshed
 * after it.
 *
 * Shared by the profile page's onboarding modal and the always-visible
 * control on the Experience tab. Until 2026-10-02 the modal was the only way to
 * set a status and was reachable only while the status was unset, so once set
 * it could never be changed from the UI (audit item 6).
 *
 * Lives under components/ rather than beside the profile slice's other hooks
 * because it imports the assessments barrel for the Situation Report's query
 * key, and the assessments slice imports the profile barrel: putting this
 * behind `profile/index.ts` would close that loop.
 */
import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { useAuth } from "../../auth";
import type { ProfileData } from "../../auth";
import { situationReportKeys } from "../../assessments";
import { profileKeys } from "../useProfile";
import { dashboardKeys } from "../dashboardKeys";
import type { CareerStatus } from "../types";

export { isCareerStatus } from "../types";
export type { CareerStatus } from "../types";

/** The three statuses the API accepts (`domain.profile.CAREER_STATUSES`), with
 *  the modal's wording. Best-guess copy; Julie revises. */
export const CAREER_STATUS_OPTIONS: { value: CareerStatus; label: string; hint: string }[] = [
  { value: "employed", label: "Currently employed", hint: "You have a job right now" },
  { value: "between_jobs", label: "Currently unemployed", hint: "You're between roles and actively looking" },
  {
    value: "first_job",
    label: "Looking for my first job",
    hint: "You're early in your career and seeking an entry-level role",
  },
];

/**
 * Drop every cached read that is computed from the profile's career status or
 * contents: the dashboard's next steps and the Situation Report (whose state
 * and needs-forward slicing turn on career_status). Called after a status
 * change and after a profile save.
 */
export function invalidateProfileDependents(queryClient: QueryClient): Promise<unknown> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: dashboardKeys.all }),
    queryClient.invalidateQueries({ queryKey: situationReportKeys.all }),
  ]);
}

export function useSetCareerStatus(options: { onSaved?: (status: CareerStatus) => void } = {}) {
  const { fetchWithAuth } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (status: CareerStatus) => {
      await fetchWithAuth("/me/career-status", {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      // Written into the cached document from the confirmed value rather than
      // refetched: a page that reads career_status off the cache (Path
      // Intelligence, the profile page) sees it at once, and the profile form
      // is not re-hydrated over edits the user has not saved yet.
      queryClient.setQueryData<ProfileData>(profileKeys.document(), (prev) =>
        prev ? { ...prev, career_status: status } : prev,
      );
      await invalidateProfileDependents(queryClient);
      return status;
    },
    onSuccess: (status) => options.onSaved?.(status),
  });
}
