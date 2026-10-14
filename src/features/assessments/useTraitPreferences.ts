/**
 * useTraitPreferences -- per-trait tolerance and must-have flags.
 *
 *   GET /me/trait-preferences   the latest sitting, or all six traits unanswered
 *   PUT /me/trait-preferences   a new sitting of all six; returns the saved document
 *
 * The six-trait match model (PRODUCT_DECISIONS.md §2, 2026-10-13). This is a short,
 * skippable step after Work Pulse and is retakeable any time at /trait-preferences.
 * Skipping writes nothing: an unanswered user keeps exactly today's matching and
 * Situation Report behaviour, so the client never sends a default on their behalf.
 *
 * Steps are person-lattice steps of 0.25: `under_steps` is how much LESS of a trait
 * than the user prefers a job may give without cost, `over_steps` how much MORE.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../auth";
import type { components } from "../../shared/api/schema";

export type TraitPreferencesDocument = components["schemas"]["TraitPreferencesDocument"];
export type TraitPreferenceEntry = components["schemas"]["TraitPreferenceEntry"];
export type TraitPreferenceInput = components["schemas"]["TraitPreferenceInput"];
export type TraitKey = TraitPreferenceEntry["dimension_key"];

/** 0 = not at all, 1 = a little is fine, 2 = a lot is fine. */
export type ToleranceSteps = 0 | 1 | 2;

/** The product's fixed trait order, the same order the server returns. */
export const TRAIT_KEYS: readonly TraitKey[] = [
  "autonomy",
  "pace",
  "collaboration",
  "feedback",
  "innovation",
  "decision",
];

/** Mirrors the server's limit; the server is what enforces it. */
export const MAX_MUST_HAVES = 2;

export const traitPreferenceKeys = {
  all: ["traitPreferences"] as const,
};

export function useTraitPreferences() {
  const { fetchWithAuth } = useAuth();
  return useQuery({
    queryKey: traitPreferenceKeys.all,
    queryFn: () => fetchWithAuth<TraitPreferencesDocument>("/me/trait-preferences"),
  });
}

export function useSaveTraitPreferences() {
  const { fetchWithAuth } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (traits: TraitPreferenceInput[]) =>
      fetchWithAuth<TraitPreferencesDocument>("/me/trait-preferences", {
        method: "PUT",
        body: JSON.stringify({ traits }),
      }),
    onSuccess: (saved) => {
      queryClient.setQueryData(traitPreferenceKeys.all, saved);
    },
  });
}
