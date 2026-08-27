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

import { AuthContext, ProfileData, SessionResponse, User } from "./authContext";
import { API_BASE } from "../utils/api";
import { parseApiError } from "../utils/apiError";


/**
 * Assemble the `User` the app reads from the two resources that now serve it.
 *
 * GET /auth/session returns `{ user, csrf_token, flags }` and GET /me/profile
 * returns `{ profile }`. Keeping the seam here rather than at every consumer is
 * the point of splitting at the API boundary: the shape the components see is
 * unchanged, so the endpoint redesign did not have to reach into them -- and
 * when Phase 2 decomposes `profile_data` into columns, this is again the only
 * place that has to know.
 */
function toUser(session: SessionResponse, profile?: ProfileData): User {
  return {
    ...(session.user as unknown as User),
    profileData: profile ?? {},
    wpl_completed: session.flags.wpl_completed,
    wpll_completed: session.flags.wpll_completed,
    wp_v2_completed: session.flags.wp_v2_completed,
  } as User;
}


export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);

  // Restore session automatically using secure cookies.
  //
  // Phase 1b split the endpoint this used to call. GET /profile returned
  // identity, the whole profile_data blob, the CSRF token and three completion
  // flags in one document, and committed an AuditLog row on the way out -- a
  // write on the hottest read in the system, on every page load, for data the
  // app shell does not render (P0-3).
  //
  // It is now two resources: GET /auth/session for identity, the CSRF token and
  // the flags, which writes nothing; and GET /me/profile for the blob. They are
  // issued together so a restore is still one round trip's latency rather than
  // two.
  //
  // Fetching the profile here at all is transitional. It is on the boot path
  // only because the `User` type still carries `profileData` and six components
  // read it off the user object. When Phase 4 moves those onto their own
  // queries, deleting the second request from this Promise.all is what finishes
  // P0-3 on the client -- the split it needs has already happened.
  useEffect(() => {
    (async () => {
      try {
        const [sessionRes, profileRes] = await Promise.all([
          fetch(`${API_BASE}/auth/session`, { method: "GET", credentials: "include" }),
          fetch(`${API_BASE}/me/profile`, { method: "GET", credentials: "include" }),
        ]);

        if (sessionRes.ok) {
          const session = await sessionRes.json();
          // A failed profile read must not fail the restore: the session is
          // valid either way, and a signed-in user with an empty profile is a
          // recoverable state where a logged-out one is not.
          const profile = profileRes.ok ? await profileRes.json() : null;
          setUser(toUser(session, profile?.profile));
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
    setUser(userData);
    setCsrfToken(token);
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

    const userData = data.user as User;
    setUser(userData);

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
    }
  };


  /** Refetch the full User object and sync local state.
   *
   * Two requests since the Phase 1b split, for the reason in the restore effect
   * above: identity and flags come from the session probe, the blob from the
   * profile resource.
   */
  const fetchProfile = async () => {
    const [session, profile] = await Promise.all([
      fetchWithAuth<SessionResponse>("/auth/session", { method: "GET" }),
      fetchWithAuth<{ profile?: ProfileData }>("/me/profile", { method: "GET" }),
    ]);
    setUser(toUser(session, profile.profile));
  };

  /** Fetch only the profileData portion of the user's profile.
   *
   * One request now rather than a whole user document -- this is what the split
   * buys a caller that only wants the blob.
   */
  const fetchProfileData = async () => {
    const data = await fetchWithAuth<{ profile?: ProfileData }>("/me/profile", {
      method: "GET",
    });
    return { profileData: data.profile };
  };

  /** Persist updated profileData (PATCH /api/v1/me/profile).
   *
   * Still a merge, not a replace: the server folds these keys over the stored
   * document. The return shape is adapted to `{ profileData }` so the callers
   * that read it do not each need to know the wire name changed.
   */
  const saveProfileData = async (profileData: ProfileData) => {
    const data = await fetchWithAuth<{ profile?: ProfileData }>("/me/profile", {
      method: "PATCH",
      body: JSON.stringify({ profile: profileData }),
    });
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
   * Shallow-merge partial profileData into the in-memory User.
   * Useful for updating quiz results or other profile fields after a save
   * without re-fetching the entire profile.
   */
  const updateProfileData = (profileData: ProfileData) => {
    setUser((prev) =>
      prev ? { ...prev, profileData: { ...(prev.profileData || {}), ...profileData } } : prev
    );
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
