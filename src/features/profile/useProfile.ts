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

import type { ProfileData } from "../auth";
import { useAuth } from "../auth";

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
 *
 * ── Why this query throws (Phase 4b) ────────────────────────────────────────
 *
 * TanStack Query does not throw by default: a failed query hands back
 * `{ data: undefined, isLoading: false, error }` and leaves it to the caller to
 * notice. For most queries that is the right default. For this one it produced
 * a specific and silent class of bug, because every consumer *branches on the
 * document to decide which screen to show* — and an errored query is shaped
 * exactly like a successful fetch of a user who has done nothing yet:
 *
 *   FocusTypeResultsPage   `!result` -> <Navigate to="/focus-type">, sending a
 *                          user who has a result back to retake the quiz.
 *   FocusTypePage          renders the "Begin" intro to that same user.
 *   PathIntelligencePage   no `path_preferences` -> the preferences form, which
 *                          is precisely the failure its own gate comment says
 *                          the loading check exists to prevent.
 *   IntelligencePage       `if (!result) return null` — a blank screen — or the
 *                          FocusType/ManagerMatch cards drawn as "not started".
 *   useProfileForm         worst of the set: `isSuccess` is false, so the form
 *                          never hydrates, and a user who edits and saves
 *                          PATCHes empty defaults over their real document.
 *
 * None of those render an error. Four render a *plausible wrong screen*, which
 * is worse than a crash because nobody files a bug for it.
 *
 * So the policy is boundary-caught rather than in-component: `throwOnError`
 * sends the failure to `RouteErrorBoundary`, which draws one error card with a
 * working retry and leaves the Header alive. The alternative — an `isError`
 * branch in each consumer — is five copies of that card, and, more to the
 * point, a rule the sixth consumer will forget, silently, in exactly the way
 * this comment exists to describe.
 *
 * Two things make it safe rather than merely loud:
 *   - It fires after `shouldRetry` is exhausted, not on the first blip; a 429
 *     or 5xx still gets its two retries before anything reaches a boundary.
 *   - Writes are unaffected. `saveProfileData` and `fetchProfileData` go
 *     through `fetchWithAuth`/`fetchQuery` and still reject to their callers,
 *     which catch them and show inline form errors. Only *reads during render*
 *     escalate.
 *
 * The one behaviour deliberately given up: ManagerMatchResultsPage used to
 * treat a failed document as "no cached result" and fall through to
 * `/me/assessments/manager_match/result`, which occasionally recovered. It now
 * throws with its four siblings. Consistency is worth more than a fallback that
 * only helps when `/me/profile` fails while a sibling endpoint on the same
 * session succeeds — and that page's own fetch already has real error UI.
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
    throwOnError: true,
  });
}
