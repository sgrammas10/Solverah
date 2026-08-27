/**
 * useProfile.ts — the profile document as a query, not as a field on `User`.
 *
 * `GET /api/v1/me/profile` returns `{ profile }`: the flexible blob that holds
 * quiz results, FocusType and ManagerMatch results, experience, skills and path
 * preferences. Until Phase 4a it arrived on the boot path, was folded into the
 * `User` object by `toUser()`, and six consumers read it off `user.profileData`.
 *
 * That coupling is what forced the second request in AuthProvider's restore:
 * the shell cannot render `user` until the profile it does not use has arrived.
 * Keying the document on its own — `["profile", "document"]`, with nothing of
 * the session in the key — is what lets the boot path drop to one request. The
 * query is gated on being signed in rather than on session *identity*, because
 * `logout()` clears the cache outright; a stale document cannot outlive the
 * session it belongs to.
 *
 * The transport is deliberately still `fetchWithAuth`. CSRF attachment,
 * `credentials: "include"` and `parseApiError` all live there and are correct;
 * this module changes who caches the answer, not how it is asked for.
 *
 * Writes still go through AuthContext's `saveProfileData` / `updateProfileData`,
 * which target this cache. Keeping one writer meant the four quiz components
 * that read-modify-write the document inside a submit handler — where a hook
 * cannot be called — did not have to change to share a cache with the readers.
 */
import { useQuery, type QueryClient } from "@tanstack/react-query";

import type { ProfileData } from "../contexts/authContext";
import { useAuth } from "../contexts/useAuth";

/** Wire shape of `GET`/`PATCH /me/profile`. */
interface ProfileEnvelope {
  profile?: ProfileData;
}

/**
 * Query keys for the profile document.
 *
 * `all` is the invalidation handle; `document()` is the one query under it.
 * Nothing session-derived appears in the key — see the module docstring.
 */
export const profileKeys = {
  all: ["profile"] as const,
  document: () => ["profile", "document"] as const,
};

/** The empty document, as a shared frozen constant so the resolved-but-empty
 *  case hands back a stable reference rather than a fresh `{}` each render. */
const EMPTY_PROFILE = Object.freeze({}) as ProfileData;

/**
 * Seed the cache with a profile document the server already sent us.
 *
 * `POST /auth/login` returns `profileData` inside its user envelope (see
 * `SessionUser` in `solverah/schemas/auth.py`). Writing it here means a fresh
 * sign-in has the document before anything asks for it, so removing the boot
 * fetch does not simply move that request one screen later.
 *
 * Takes the client as an argument because AuthContext calls it from outside the
 * render pass that would give it one.
 */
export function seedProfileCache(client: QueryClient, profile: ProfileData | undefined): void {
  client.setQueryData(profileKeys.document(), profile ?? EMPTY_PROFILE);
}

/**
 * The profile document, with the loading and error state of fetching it.
 *
 * Consumers must respect `isLoading` rather than treating `data` as the whole
 * truth on first render. This is the one real behavioural difference from
 * reading `user.profileData`: that field was never in flight at a consumer,
 * because the boot path had already fetched it — which is exactly the cost the
 * second request was paying. An un-arrived document is `undefined` here, and
 * defaulting it to `{}` before it lands makes "still loading" indistinguishable
 * from "the user has no such key". Every consumer that *branches* on the
 * document — redirecting when a result is missing, choosing which screen to
 * show on mount — waits on `isLoading` first.
 *
 * `isLoading`, not `isPending`: a disabled query (nobody signed in) stays
 * pending forever, and a consumer gated on `isPending` would spin rather than
 * render its signed-out path.
 */
export function useProfile() {
  const { user, fetchWithAuth } = useAuth();

  return useQuery({
    queryKey: profileKeys.document(),
    queryFn: async (): Promise<ProfileData> => {
      const data = await fetchWithAuth<ProfileEnvelope>("/me/profile", { method: "GET" });
      return data.profile ?? EMPTY_PROFILE;
    },
    enabled: Boolean(user),
  });
}
