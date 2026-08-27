/**
 * AuthContext.tsx — AuthProvider and all stateful authentication logic.
 *
 * Session lifecycle:
 *   1. On mount, attempt to restore an existing session by calling GET /api/profile
 *      (the JWT lives in an HttpOnly cookie, so no token management needed here).
 *   2. On successful restore, store the User object and the CSRF token in state.
 *   3. login() / register() / logout() mutate state and the HttpOnly cookie via
 *      the Flask API.
 *
 * CSRF protection:
 *   The backend issues a CSRF token inside the JSON response body (not in a
 *   readable cookie) on login/profile-read.  fetchWithAuth() attaches it as the
 *   X-CSRF-TOKEN header on all state-changing requests (POST/PUT/PATCH/DELETE).
 *
 * Loading state:
 *   While the initial profile fetch is in-flight, a spinner is rendered instead
 *   of children to prevent flicker on protected routes.
 */
import { useState, useEffect, ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { AuthContext, ProfileData, SessionResponse, User } from "./authContext";
import { profileKeys, seedProfileCache } from "../hooks/useProfile";
import { API_BASE } from "../utils/api";
import { parseApiError } from "../utils/apiError";


/**
 * Assemble the `User` the app reads from the session probe alone.
 *
 * GET /auth/session returns `{ user, csrf_token, flags }`, and as of Phase 4a
 * that is the whole of it. This function is the seam the Phase 1b endpoint
 * split left behind: because the shape components saw was assembled here, the
 * redesign did not have to reach into them, and neither does this one. The
 * profile document it used to fold in now lives in its own query -- see
 * `hooks/useProfile.ts` -- so the boot path no longer has to wait on data the
 * app shell does not render.
 */
function toUser(session: SessionResponse): User {
  return {
    ...(session.user as unknown as User),
    wpl_completed: session.flags.wpl_completed,
    wpll_completed: session.flags.wpll_completed,
    wp_v2_completed: session.flags.wp_v2_completed,
  } as User;
}


/**
 * Strip the profile document off a login response's user envelope.
 *
 * `POST /auth/login` still returns `profileData` inside `user` -- the wire is
 * unchanged and deliberately so. It simply is not part of the `User` the app
 * holds any more, so it is split out here and seeded into the query cache
 * instead of being carried in auth state.
 */
function splitLoginUser(
  raw: User & { profileData?: ProfileData },
): { user: User; profile: ProfileData | undefined } {
  const { profileData, ...rest } = raw;
  return { user: rest, profile: profileData };
}


export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const queryClient = useQueryClient();

  // Restore session automatically using secure cookies.
  //
  // One request. Phase 1b split the endpoint this used to call -- GET /profile
  // returned identity, the whole profile_data blob, the CSRF token and three
  // completion flags in one document, and committed an AuditLog row on the way
  // out, a write on the hottest read in the system on every page load, for data
  // the app shell does not render (P0-3). That split produced GET /auth/session,
  // which writes nothing.
  //
  // The blob kept riding along in a Promise.all here for one reason: the `User`
  // type carried `profileData` and six components read it off the user object.
  // Phase 4a moved those onto `useProfile()`, so the second request is gone and
  // P0-3 is finished on the client. Anything that wants the document now asks
  // for it, on the screen that renders it, and gets a cached answer if another
  // screen already did.
  useEffect(() => {
    (async () => {
      try {
        const sessionRes = await fetch(`${API_BASE}/auth/session`, {
          method: "GET",
          credentials: "include",
        });

        if (sessionRes.ok) {
          const session = await sessionRes.json();
          setUser(toUser(session));
          // Read CSRF token from response body (cookie is inaccessible cross-origin)
          if (session.csrf_token) {
            setCsrfToken(session.csrf_token);
          }
        } else {
          setUser(null);
        }
      } catch (e) {
        console.error("Session restore failed:", e);
        setUser(null);
      }
      setLoading(false);
    })();
  }, []);


  const fetchWithAuth = async <T = any>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> => {
    const method = (options.method || "GET").toUpperCase();

    const headers: HeadersInit = {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    };

    // attach CSRF token for state-changing requests
    if (csrfToken && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      (headers as any)["X-CSRF-TOKEN"] = csrfToken;
    }

    const res = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
      credentials: "include",
    });

    const data = await res.json().catch((e) => {
      console.error("fetchWithAuth: failed to parse JSON response:", e);
      return null;
    });

    if (!res.ok) {
      // Throws an ApiError, which extends Error — existing `catch (e) { e.message }`
      // call sites are unaffected and simply get a better message. Reads both the
      // problem+json shape and the legacy {error} body; see utils/apiError.ts.
      throw parseApiError(res, data);
    }

    if (data === null) {
      throw new Error("Unexpected response from server (no JSON body).");
    }

    return data as T;
  };


  const streamFetch = async (
    endpoint: string,
    options: RequestInit = {}
  ): Promise<globalThis.Response> => {
    const method = (options.method || "GET").toUpperCase();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...((options.headers as Record<string, string>) || {}),
    };
    if (csrfToken && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      headers["X-CSRF-TOKEN"] = csrfToken;
    }
    return fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
      credentials: "include",
    });
  };

  const loginWithData = (userData: User, token: string) => {
    const { user: identity, profile } = splitLoginUser(userData);
    setUser(identity);
    setCsrfToken(token);
    // OTP sign-in returns the summary user, which carries no profileData (see
    // PasswordResetVerifyResponse). Seeding `undefined` would pin an empty
    // document into the cache and suppress the first real fetch, so only a
    // response that actually carried one writes through.
    if (profile) {
      seedProfileCache(queryClient, profile);
    }
  };

  // LOGIN — backend sets an HttpOnly JWT cookie
  const login = async (email: string, password: string) => {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password }),
    });

    // Guarded: an unguarded res.json() throws a SyntaxError on any non-JSON
    // error response (a proxy's HTML 502, an empty 429 body), which surfaces to
    // the user as a parse error instead of the real reason.
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      throw parseApiError(res, data, "Login failed");
    }
    if (data === null) {
      throw new Error("Unexpected response from server (no JSON body).");
    }

    // The login envelope still carries the profile document. It goes to the
    // query cache rather than into auth state, so the first screen that renders
    // it does not pay for a request the sign-in already answered.
    const { user: userData, profile } = splitLoginUser(data.user);
    setUser(userData);
    // Guarded for the same reason loginWithData is: `splitLoginUser` hands back
    // `undefined` when the envelope carried no profileData, and seeding that
    // writes the empty document into the cache -- resolved rather than missing
    // -- which suppresses the first real fetch for the whole staleTime window.
    // The password envelope does carry the field today; correctness here must
    // not depend on it continuing to.
    if (profile) {
      seedProfileCache(queryClient, profile);
    }

    // Read CSRF token from response body (cookie is inaccessible cross-origin)
    if (data.csrfToken) {
      setCsrfToken(data.csrfToken);
    }

    return userData;
  };

  // REGISTER — then user logs in normally.
  // termsAccepted: ToS/Privacy acceptance + 16+ attestation, required by the
  // backend; the accepted TERMS_VERSION is recorded server-side as evidence.
  const register = async (
    email: string,
    password: string,
    name: string,
    termsAccepted: boolean,
  ) => {
    const { TERMS_VERSION } = await import("../data/legal");
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        email,
        password,
        name,
        role: "job-seeker",
        terms_accepted: termsAccepted,
        terms_version: TERMS_VERSION,
      }),
    });

    const data = await res.json().catch(() => null);
    if (!res.ok) throw parseApiError(res, data, "Registration failed");
  };

  // LOGOUT — clears cookie on backend
  const logout = async () => {
    try {
      await fetchWithAuth("/auth/logout", { method: "POST" });
    } catch (e) {
      console.error(e);
    } finally {
      setUser(null);
      setCsrfToken(null);
      // The cached profile document belongs to the session that just ended. It
      // must not survive into the next sign-in on this tab.
      queryClient.removeQueries({ queryKey: profileKeys.all });
    }
  };


  /** Refetch identity and flags, and mark the profile document stale.
   *
   * One request now. The session probe is the only source of what `User` holds;
   * the document is refetched by whichever mounted `useProfile()` needs it,
   * which is nobody on a screen that does not render it.
   */
  const fetchProfile = async () => {
    const session = await fetchWithAuth<SessionResponse>("/auth/session", { method: "GET" });
    setUser(toUser(session));
    await queryClient.invalidateQueries({ queryKey: profileKeys.all });
  };

  /** Read the profile document, through the cache.
   *
   * Kept on the context for the four quiz components that read-modify-write the
   * document imperatively inside a submit handler, where a hook cannot be
   * called. `fetchQuery` -- not a bare fetch -- so those callers share the same
   * cached copy as every `useProfile()` consumer instead of opening a second,
   * invisible one.
   */
  const fetchProfileData = async () => {
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
  };

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
  const saveProfileData = async (profileData: ProfileData) => {
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
  };

  /**
   * Optimistically patch the in-memory User without a server round-trip.
   * Use after local mutations that don't require immediate server confirmation.
   */
  const updateProfile = (updates: Partial<User>) => {
    setUser((prev) => (prev ? { ...prev, ...updates } : prev));
  };

  /**
   * Shallow-merge partial profileData into the cached document.
   *
   * Same contract as before -- a merge, no round trip -- but the target is the
   * query cache rather than a field on `User`. That is what keeps this working
   * across the move: FocusTypePage still writes its result here on submit, and
   * FocusTypeResultsPage still finds it, now via `useProfile()`.
   */
  const updateProfileData = (profileData: ProfileData) => {
    queryClient.setQueryData<ProfileData>(profileKeys.document(), (prev) => ({
      ...(prev ?? {}),
      ...profileData,
    }));
  };


  const value = {
    user,
    login,
    loginWithData,
    register,
    logout,
    fetchProfile,
    fetchWithAuth,
    streamFetch,
    fetchProfileData,
    saveProfileData,
    updateProfile,
    updateProfileData,
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-emerald-400"></div>
      </div>
    );
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
