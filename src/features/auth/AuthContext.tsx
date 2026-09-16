/**
 * AuthContext.tsx — AuthProvider and all stateful authentication logic.
 *
 * Session lifecycle:
 *   1. On mount, attempt to restore an existing session by calling
 *      GET /auth/session (the JWT lives in an HttpOnly cookie, so no token
 *      management needed here).  A 401 there is not the end of the session any
 *      more — see "Refresh" below.
 *   2. On successful restore, store the User object and the CSRF token in state.
 *   3. login() / register() / logout() mutate state and the HttpOnly cookie via
 *      the Flask API.
 *
 * CSRF protection:
 *   The backend issues a CSRF token inside the JSON response body (not in a
 *   readable cookie) on login/session-probe.  fetchWithAuth() attaches it as the
 *   X-CSRF-TOKEN header on all state-changing requests (POST/PUT/PATCH/DELETE).
 *
 * Refresh (S3):
 *   The access token is fifteen minutes now, not an hour, and a thirty-day
 *   opaque refresh token sits behind it in a cookie the browser sends only to
 *   POST /auth/refresh.  So a 401 means "the access token aged out", not "you
 *   are signed out", and the answer is refresh-then-retry — once, never in a
 *   loop.  Both places that talk to the API do it: the boot probe and
 *   fetchWithAuth.
 *
 *   The boot probe only attempts a refresh when this browser has had a session
 *   before (`hasHadSession()`).  An anonymous landing page is the
 *   highest-volume boot in the product and it has no refresh cookie to
 *   exchange, so without the gate every visitor would spend a second request on
 *   a guaranteed 401 — against a rate-limited endpoint, which behind one NAT
 *   gateway is how real users start getting 429s on genuine refreshes.
 *
 *   `refreshSession()` is SINGLE-FLIGHT, and that is a security property rather
 *   than an optimisation.  Refresh tokens rotate on use and a token presented
 *   after it was retired is treated as evidence of theft — the server revokes
 *   the whole family and the user is signed out.  Two queries hitting a 401 at
 *   the same instant would present the same token twice, which is exactly that
 *   shape.  The server has a short grace window for it (see
 *   solverah/services/refresh_tokens.py) and this ref is the other half: the
 *   second caller awaits the first one's promise instead of issuing a second
 *   refresh, so under normal concurrency the grace window is never even needed.
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
// The `solverah.hasSession` hint that gates the boot-time refresh; see
// sessionHint.ts for what it is and is not.
import { hasHadSession, rememberSession } from "./sessionHint";
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
  const queryClient = useQueryClient();

  // The CSRF token, in a ref rather than in state.
  //
  // It was state until S3 and nothing ever rendered off it -- only the two
  // fetch helpers read it. State is now actively wrong here: a 401 retry
  // refreshes and replays in the same tick, and a `setState` is not visible to
  // the closure that has to attach the NEW token to that replay. The ref is,
  // and dropping the state removes a re-render nothing was waiting for.
  const csrfTokenRef = useRef<string | null>(null);

  // The in-flight refresh, if there is one. See the module docstring: this is
  // what stops two simultaneous 401s presenting the same refresh token twice
  // and tripping the server's reuse detection.
  const refreshInFlight = useRef<Promise<boolean> | null>(null);

  // True once login()/loginWithData() has set auth state. The boot probe's
  // continuation checks it: children render while the probe is in flight now,
  // so a visitor can complete a sign-in on /login before a slow probe -- issued
  // pre-login, without the new cookie -- comes back 401. Letting that stale
  // response null out the user would sign them straight back out. An explicit
  // login is always fresher than the probe that raced it.
  const signedInExplicitly = useRef(false);

  /** Record the CSRF token the next state-changing request must echo. */
  const applyCsrfToken = (token: string | null) => {
    csrfTokenRef.current = token;
  };

  /**
   * Exchange the refresh cookie for a new access token. Resolves to whether it
   * worked.
   *
   * Single-flight: every caller during one exchange awaits the same promise, so
   * N simultaneous 401s produce ONE POST /auth/refresh. That is what keeps the
   * client off the server's reuse-detection tripwire — the refresh token
   * rotates on use, and presenting the retired one is indistinguishable from
   * theft once the grace window closes.
   *
   * The ref is cleared when the exchange settles, not when it succeeds, so a
   * failed refresh does not wedge every later attempt behind a promise that
   * already resolved false.
   */
  const refreshSession = (): Promise<boolean> => {
    if (!refreshInFlight.current) {
      refreshInFlight.current = (async () => {
        try {
          const res = await fetch(`${API_BASE}/auth/refresh`, {
            method: "POST",
            // The server requires application/json on this route: a cross-site
            // HTML form cannot send it, which is half of the CSRF control that
            // replaces the double-submit token here (the token is exactly what
            // this call does not have yet). See the handler's docstring.
            headers: { "Content-Type": "application/json" },
            credentials: "include",
            body: "{}",
          });
          if (!res.ok) return false;
          const data = await res.json().catch(() => null);
          if (data?.csrfToken) applyCsrfToken(data.csrfToken);
          rememberSession(true);
          return true;
        } catch (e) {
          console.error("Session refresh failed:", e);
          return false;
        }
      })().finally(() => {
        refreshInFlight.current = null;
      });
    }
    return refreshInFlight.current;
  };

  /**
   * Drop every trace of the session this tab was holding.
   *
   * The local half of logout, reached when a refresh fails: the session is over
   * server-side and there is nothing to tell it. Same cache hygiene as logout()
   * for the same reason -- every cached query belongs to the session that just
   * ended -- but no request, because the thing that would authenticate one is
   * exactly what is gone.
   */
  const clearSessionLocally = () => {
    signedInExplicitly.current = false;
    setUser(null);
    applyCsrfToken(null);
    rememberSession(false);
    queryClient.clear();
  };


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
        const probe = () =>
          fetch(`${API_BASE}/auth/session`, {
            method: "GET",
            credentials: "include",
          });

        let sessionRes = await probe();

        // A 401 on boot is the ordinary case for a returning visitor: the
        // access token is fifteen minutes and they have been away longer. The
        // refresh cookie is thirty days, so one exchange restores the session
        // and the visitor never sees a login screen. Without this, S3's shorter
        // access token would sign everyone out a quarter of an hour after they
        // closed the tab — the feature inverted.
        //
        // Exactly one retry. `refreshSession` resolving false means there is no
        // usable refresh token (never had one, expired, revoked, or the family
        // was killed by reuse detection), and re-probing after that would ask
        // the same question and get the same answer forever.
        //
        // Gated on `hasHadSession()` so an anonymous visitor's boot stays one
        // request: they have no refresh cookie, the exchange is a certain 401,
        // and the landing page is the highest-volume boot there is.
        if (sessionRes.status === 401 && hasHadSession()) {
          if (await refreshSession()) sessionRes = await probe();
          else rememberSession(false);
        }

        if (sessionRes.ok && !signedInExplicitly.current) {
          const session = await sessionRes.json();
          setUser(toUser(session));
          rememberSession(true);
          // Read CSRF token from response body (cookie is inaccessible cross-origin)
          if (session.csrf_token) {
            applyCsrfToken(session.csrf_token);
          }
        }
        // A failed probe sets nothing: `user` starts as null, and if a login
        // beat the probe (see signedInExplicitly) the stale 401 must not undo it.
      } catch (e) {
        console.error("Session restore failed:", e);
      }
      setLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- boot-once probe
  }, []);


  const fetchWithAuth = async <T = any>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> => {
    const method = (options.method || "GET").toUpperCase();

    const send = () => {
      const headers: HeadersInit = {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      };

      // attach CSRF token for state-changing requests. Read from the ref, not
      // from state: a retry after a refresh happens in the same tick as the
      // refresh, and the new token has to reach this line before React has
      // re-rendered anything.
      const token = csrfTokenRef.current;
      if (token && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
        (headers as any)["X-CSRF-TOKEN"] = token;
      }

      return fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers,
        credentials: "include",
      });
    };

    let res = await send();

    // A 401 means the fifteen-minute access token aged out mid-session, which
    // is now routine rather than terminal. Refresh once and replay the request;
    // if the refresh fails there is no session left to salvage, so drop the
    // local one and let the original error surface.
    //
    // ONE retry, unconditionally, and it is the shape that guarantees it: a
    // plain `if`, no loop, and no path back into here from the replay. A loop
    // would turn an expired family into an infinite refresh storm against the
    // auth endpoint; because there is none, a second 401 falls straight through
    // to the throw below and means what it says.
    if (res.status === 401) {
      if (await refreshSession()) {
        res = await send();
      } else {
        clearSessionLocally();
      }
    }

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
    const token = csrfTokenRef.current;
    if (token && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      headers["X-CSRF-TOKEN"] = token;
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
    applyCsrfToken(token);
    rememberSession(true);
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
    rememberSession(true);
    emitAuthEvent({ type: "signed-in", user: userData, profileData: profile });

    // Read CSRF token from response body (cookie is inaccessible cross-origin)
    if (data.csrfToken) {
      applyCsrfToken(data.csrfToken);
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

  // LOGOUT — the backend revokes the refresh family and clears both cookies
  //
  // The request matters more than it used to. Until S3 this was a courtesy: the
  // server cleared a cookie the client was about to forget anyway, and the JWT
  // stayed valid for the rest of its hour regardless. It now revokes the
  // refresh-token family server-side, so a failed logout request leaves a live
  // thirty-day session behind. Local state is still cleared either way — a user
  // who clicked "log out" is logged out of this tab no matter what the network
  // did — and the residue is the same one the endpoint's docstring names.
  const logout = async () => {
    try {
      await fetchWithAuth("/auth/logout", { method: "POST" });
    } catch (e) {
      console.error(e);
    } finally {
      signedInExplicitly.current = false;
      setUser(null);
      applyCsrfToken(null);
      rememberSession(false);
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
    clearSessionLocally,
    fetchWithAuth,
    streamFetch,
    updateProfile,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
