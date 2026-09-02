/**
 * authContext.ts — Type definitions and React context object for authentication.
 *
 * This file intentionally contains ONLY types + the bare createContext() call.
 * The actual state, session-restore logic, and method implementations live in
 * AuthContext.tsx (AuthProvider) so that this file can be imported by any module
 * without pulling in React hooks.
 *
 * Architecture note:
 *   AuthContext (this file) → context object + types (no state)
 *   AuthContext.tsx         → AuthProvider with all stateful logic
 *   useAuth.ts              → convenience hook that reads this context
 */
import { createContext } from "react";

/**
 * Flexible profile blob stored in User.profile_data on the backend.
 *
 * Top-level shape is a loose record so new fields can be added server-side
 * without requiring frontend type changes.  Known sub-objects are typed explicitly:
 *   quizResults  — raw answers keyed by quiz key
 *   _quizSummary — server-computed answer statistics (read-only, set by backend)
 *   quizInsights — LLM-generated insights keyed by quiz group / key
 */
export type ProfileData = Record<string, unknown> & {
  quizResults?: Record<string, unknown>;
  _quizSummary?: Record<string, unknown>;
  quizInsights?: Record<string, unknown>;
};

/**
 * Body of `GET /api/v1/auth/session` -- the cheap session probe.
 *
 * Phase 1b split `GET /api/profile` into this and `GET /api/v1/me/profile`. The
 * old endpoint returned the whole user document *and* committed an audit row on
 * every page load; this one answers what the app shell actually needs -- who you
 * are, the CSRF token, and four booleans -- and writes nothing.
 *
 * `csrf_token` is snake_case here and `csrfToken` on the login response. That is
 * the wire, not a typo: the login envelope predates Phase 1b and is preserved
 * verbatim because changing it is a separate client-visible break.
 */
export interface SessionResponse {
  user: {
    id: string;
    email: string;
    name: string;
    role: "job-seeker";
  };
  csrf_token: string | null;
  flags: {
    email_confirmed: boolean;
    wpl_completed: boolean;
    wpll_completed: boolean;
    wp_v2_completed: boolean;
  };
}

/**
 * Authenticated user data the app reads.
 *
 * Assembled by `toUser()` in AuthContext.tsx from the session probe alone.
 * `POST /api/v1/auth/login` still returns the profile document inside its user
 * envelope -- the wire is unchanged -- but AuthContext splits it out and seeds
 * it into the query cache rather than carrying it here.
 *
 * `profileData` was a field on this type until Phase 4a, and its removal is the
 * point of that phase: because six components read the document off `user`, the
 * boot path had to fetch it before the shell could render, on every page load,
 * for data the shell does not display (P0-3). It is now its own query --
 * `hooks/useProfile.ts` -- fetched by the screens that actually render it.
 */
export interface User {
  id: string;
  email: string;
  name: string;
  role: "job-seeker";
  profileComplete: boolean;
  wpl_completed: boolean;
  wpll_completed: boolean;
  /**
   * Completion of the CURRENT Work Pulse instrument (the 24-item person-side assessment
   * that replaced the original 12-question quiz). Distinct from wpl_completed on purpose:
   * the old flag marks the retired instrument and keeps its stored narrative reachable,
   * while this one gates the live prompt/banner. Server-derived from the presence of a
   * current-scoring-key submission -- never set optimistically from the client except via
   * updateProfile immediately after a successful submit.
   */
  wp_v2_completed: boolean;
}

/**
 * Full shape of the value provided by AuthProvider.
 *
 * All methods that reach the network return Promises so callers can
 * await them and show appropriate loading / error states.
 *
 * fetchWithAuth<T> is the general-purpose authenticated fetch helper:
 *   - Attaches the CSRF token to state-changing requests automatically.
 *   - Throws on non-2xx responses with the server's error message.
 *
 * The profile-document operations (`fetchProfileData`, `saveProfileData`,
 * `updateProfileData`) lived here until the auth ⇄ profile cycle was broken:
 * they are profile-cache concerns, so they now live in the profile slice as
 * `useProfileActions()`, built on this context's `fetchWithAuth`. That is the
 * legal dependency direction — profile depends on auth, never the reverse.
 * `fetchProfile` (re-probe the session and invalidate the document) went with
 * them; it had no remaining callers.
 */
export interface AuthContextType {
  user: User | null;
  /**
   * True while the boot-time session restore (`GET /auth/session`) is still in
   * flight. Routing no longer waits on it — AuthProvider renders its children
   * immediately — so this flag is how `RequireAuth` knows to hold a protected
   * route's content back (neither render it nor bounce to /login) until the
   * probe has said who the visitor is. Public routes never read it.
   */
  sessionLoading: boolean;
  login: (email: string, password: string) => Promise<User>;
  /** Set auth state directly from a login response (e.g. OTP-based login). */
  loginWithData: (user: User, csrfToken: string) => void;
  register: (email: string, password: string, name: string, termsAccepted: boolean) => Promise<void>;
  logout: () => Promise<void>;
  fetchWithAuth: <T = any>(endpoint: string, options?: RequestInit) => Promise<T>;
  streamFetch: (endpoint: string, options?: RequestInit) => Promise<globalThis.Response>;
  /** Optimistically update the in-memory user object without a server round-trip. */
  updateProfile: (updates: Partial<User>) => void;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);
