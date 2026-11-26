/**
 * useSaveOnboarding -- `PATCH /me/onboarding`, and what has to be refreshed
 * after it.
 *
 * The first-run dialog writes the career moment (and with it, often, the
 * career status) in step 1 and the optional own words in step 2. A status can
 * change in step 1, so that write drops the same reads `useSetCareerStatus`
 * does. Lives under components/ for the same reason that hook does: it
 * imports the assessments barrel (through `invalidateProfileDependents`), and
 * the assessments slice imports the profile barrel.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../../auth";
import type { ProfileData } from "../../auth";
import { profileKeys } from "../useProfile";
import type { CareerMoment } from "../careerMoments";
import type { CareerStatus } from "../types";
import { invalidateProfileDependents } from "./useSetCareerStatus";

export interface OnboardingUpdate {
  career_moment?: CareerMoment;
  career_status?: CareerStatus;
  own_words?: string | null;
}

export interface OnboardingSaved {
  career_moment: string | null;
  career_status: string | null;
  own_words: string | null;
}

export function useSaveOnboarding() {
  const { fetchWithAuth } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (update: OnboardingUpdate) => {
      const saved = await fetchWithAuth<OnboardingSaved>("/me/onboarding", {
        method: "PATCH",
        body: JSON.stringify(update),
      });
      // Written into the cached document from the confirmed values rather than
      // refetched, as useSetCareerStatus does: a page that reads the document
      // off the cache sees them at once, and an open profile form is not
      // re-hydrated over unsaved edits. A null is the key's absence there.
      queryClient.setQueryData<ProfileData>(profileKeys.document(), (prev) => {
        if (!prev) return prev;
        const next: ProfileData = { ...prev };
        for (const key of ["career_moment", "career_status", "own_words"] as const) {
          const value = saved?.[key];
          if (value == null) delete next[key];
          else next[key] = value;
        }
        return next;
      });
      if (update.career_moment !== undefined || update.career_status !== undefined) {
        await invalidateProfileDependents(queryClient);
      }
      return saved;
    },
  });
}
