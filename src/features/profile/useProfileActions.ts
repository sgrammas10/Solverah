/**
 * useProfileActions.ts — imperative reads and writes of the profile document.
 *
 * These three lived on AuthContext until the auth ⇄ profile cycle was broken:
 * they are profile-cache operations, and keeping them on the auth context meant
 * auth had to import this slice's query keys — the wrong dependency direction,
 * and half of the barrel cycle Rollup warned about on every build. They are
 * unchanged in behavior; only their home moved. The transport is still the
 * context's `fetchWithAuth`, because CSRF attachment, `credentials: "include"`
 * and `parseApiError` all live there and are correct.
 *
 * Kept as imperative functions rather than mutations-with-hooks because the
 * four quiz components that read-modify-write the document do so inside a
 * submit handler, where a hook cannot be called. They take the functions from
 * this hook at the top of the component, exactly as they used to take them
 * from `useAuth()`.
 *
 * Everything is wrapped in `useCallback` on the two stable dependencies, and
 * that is load-bearing: consumers list `fetchProfileData` in effect dependency
 * arrays, and a function recreated on every consumer render would re-run those
 * effects — which set state — on every render.
 */
import { useCallback, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";

import type { ProfileData } from "../auth";
import { useAuth } from "../auth";
import { profileKeys } from "./useProfile";

export function useProfileActions() {
  const { fetchWithAuth } = useAuth();
  const queryClient = useQueryClient();

  /** Read the profile document, through the cache.
   *
   * `fetchQuery` -- not a bare fetch -- so imperative callers share the same
   * cached copy as every `useProfile()` consumer instead of opening a second,
   * invisible one.
   */
  const fetchProfileData = useCallback(async () => {
    const profile = await queryClient.fetchQuery<ProfileData>({
      queryKey: profileKeys.document(),
      queryFn: async () => {
        const data = await fetchWithAuth<{ profile?: ProfileData }>("/me/profile", {
          method: "GET",
        });
        return data.profile ?? {};
      },
    });
    return { profileData: profile };
  }, [fetchWithAuth, queryClient]);

  /** Persist updated profileData (PATCH /api/v1/me/profile).
   *
   * Still a merge, not a replace: the server folds these keys over the stored
   * document. The server's copy of the result replaces the cache, so anything
   * the write allowlist dropped or normalised is what consumers see next.
   *
   * `data.profile ?? {}` used to make that write unconditional, which is the
   * same conflation the login path had: a *missing* `profile` key is the
   * response failing to carry the document, not the document being empty, and
   * writing `{}` for it would replace a good cached copy with an empty one and
   * mark it fresh for the staleTime window. A *present* `{}` is a different
   * statement -- the server describing the document it just wrote -- so that
   * value is written through, and an object is truthy, so the check below keeps
   * it. When nothing usable came back the cache is invalidated instead: the
   * PATCH landed, so the cached copy is out of date either way, and a refetch
   * gets the truth rather than this function guessing at it.
   *
   * Truthiness rather than `!== undefined` because a `null` would otherwise be
   * written as cache data. `ProfileData` is not nullable, so every consumer
   * spreading or indexing the document would throw on it.
   */
  const saveProfileData = useCallback(async (profileData: ProfileData) => {
    const data = await fetchWithAuth<{ profile?: ProfileData }>("/me/profile", {
      method: "PATCH",
      body: JSON.stringify({ profile: profileData }),
    });
    if (data.profile) {
      queryClient.setQueryData<ProfileData>(profileKeys.document(), data.profile);
    } else {
      await queryClient.invalidateQueries({ queryKey: profileKeys.all });
    }
    return { profileData: data.profile };
  }, [fetchWithAuth, queryClient]);

  /**
   * Shallow-merge partial profileData into the cached document, no round trip.
   *
   * Same contract as when this lived on AuthContext: FocusTypePage still
   * writes its result here on submit, and FocusTypeResultsPage still finds it,
   * via `useProfile()`.
   */
  const updateProfileData = useCallback((profileData: ProfileData) => {
    queryClient.setQueryData<ProfileData>(profileKeys.document(), (prev) => ({
      ...(prev ?? {}),
      ...profileData,
    }));
  }, [queryClient]);

  return useMemo(
    () => ({ fetchProfileData, saveProfileData, updateProfileData }),
    [fetchProfileData, saveProfileData, updateProfileData],
  );
}
