/**
 * AuthContext.tsx — AuthProvider and all stateful authentication logic.
 *
 * Session lifecycle:
 *   1. On mount, attempt to restore an existing session by calling
 *      GET /auth/session (the JWT lives in an HttpOnly cookie, so no token
 *      management needed here).
 *   2. On successful restore, store the User object and the CSRF token in state.
 *   3. login() / register() / logout() mutate state and the HttpOnly cookie via
 *      the Flask API.
 *
 * CSRF protection:
 *   The backend issues a CSRF token inside the JSON response body (not in a
 *   readable cookie) on login/session-probe.  fetchWithAuth() attaches it as the
 *   X-CSRF-TOKEN header on all state-changing requests (POST/PUT/PATCH/DELETE).
 *
 * Loading state:
 *   The provider renders its children unconditionally. It used to render a
 *   full-screen spinner instead of the tree while the restore was in flight,
 *   which made the public landing page's first paint wait on an authenticated
 *   round trip (ARCHITECTURE.md 6.3, defect 2). The restore's in-flight state
 *   is now `sessionLoading` on the context, and the only place that waits on
 *   it is `RequireAuth` — the route boundary that guards the screens which
 *   actually need a session.
 */
import { useState, useEffect, useRef, ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { AuthContext, ProfileData, SessionResponse, User } from "./authContext";
import { emitAuthEvent } from "./authEvents";
import { API_BASE } from "../../shared/api/api";
import { parseApiError } from "../../shared/api/apiError";


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
 * holds any more, so it is split out here and announced on the signed-in event
 * for the profile slice to seed its cache from, instead of being carried in
 * auth state.
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

  // True once login()/loginWithData() has set auth state. The boot probe's
  // continuation checks it: children render while the probe is in flight now,
  // so a visitor can complete a sign-in on /login before a slow probe -- issued
  // pre-login, without the new cookie -- comes back 401. Letting that stale
  // response null out the user would sign them straight back out. An explicit
  // login is always fresher than the probe that raced it.
  const signedInExplicitly = useRef(false);

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

        if (sessionRes.ok && !signedInExplicitly.current) {
          const session = await sessionRes.json();
          setUser(toUser(session));
          // Read CSRF token from response body (cookie is inaccessible cross-origin)
          if (session.csrf_token) {
            setCsrfToken(session.csrf_token);
          }
        }
        // A failed probe sets nothing: `user` starts as null, and if a login
        // beat the probe (see signedInExplicitly) the stale 401 must not undo it.
      } catch (e) {
        console.error("Session restore failed:", e);
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
    signedInExplicitly.current = true;
    setUser(identity);
    setCsrfToken(token);
    // What the envelope carried is announced as it is: OTP sign-in returns the
    // summary user, which carries no profileData (see
    // PasswordResetVerifyResponse), and the profile slice's listener is the one
    // that knows an absent document must not be seeded as an empty one.
    emitAuthEvent({ type: "signed-in", user: identity, profileData: profile });
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

    // The login envelope still carries the profile document. It is split off
    // the `User` here and announced on the signed-in event; the profile slice
    // reacts by seeding its query cache (ProfileCacheSync), so the first screen
    // that renders the document does not pay for a request the sign-in already
    // answered. Auth itself no longer touches the profile cache — that import
    // was the auth ⇄ profile cycle.
    const { user: userData, profile } = splitLoginUser(data.user);
    signedInExplicitly.current = true;
    setUser(userData);
    emitAuthEvent({ type: "signed-in", user: userData, profileData: profile });

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
    const { TERMS_VERSION } = await import("../../shared/lib/legal");
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
      signedInExplicitly.current = false;
      setUser(null);
      setCsrfToken(null);
      // Every cached query belongs to the session that just ended -- the
      // profile document, matches, dashboard rows, all of it -- and none of it
      // may survive into the next sign-in on this tab. Clearing the whole cache
      // is deliberately broader than the profile-only removal this used to be:
      // it needs no knowledge of any other slice's query keys (removing that
      // knowledge is what broke the auth ⇄ profile cycle), and it closes the
      // same leak for every slice that has since moved onto the query cache.
      queryClient.clear();
    }
  };


  /**
   * Optimistically patch the in-memory User without a server round-trip.
   * Use after local mutations that don't require immediate server confirmation.
   */
  const updateProfile = (updates: Partial<User>) => {
    setUser((prev) => (prev ? { ...prev, ...updates } : prev));
  };


  const value = {
    user,
    sessionLoading: loading,
    login,
    loginWithData,
    register,
    logout,
    fetchWithAuth,
    streamFetch,
    updateProfile,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
