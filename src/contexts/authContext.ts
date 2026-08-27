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
 * Assembled by `toUser()` in AuthContext.tsx from the session probe and the
 * profile resource, and returned whole by `POST /api/v1/auth/login`. Keeping
 * this shape stable across the Phase 1b endpoint split is deliberate: the
 * redesign stopped at the API boundary rather than reaching into components.
 */
export interface User {
  id: string;
  email: string;
  name: string;
  role: "job-seeker";
  profileComplete: boolean;
  profileData?: ProfileData;
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
 */
export interface AuthContextType {
  user: User | null;
  login: (email: string, password: string) => Promise<User>;
  /** Set auth state directly from a login response (e.g. OTP-based login). */
  loginWithData: (user: User, csrfToken: string) => void;
  register: (email: string, password: string, name: string, termsAccepted: boolean) => Promise<void>;
  logout: () => Promise<void>;
  fetchProfile: () => Promise<void>;
  fetchWithAuth: <T = any>(endpoint: string, options?: RequestInit) => Promise<T>;
  streamFetch: (endpoint: string, options?: RequestInit) => Promise<globalThis.Response>;
  fetchProfileData: () => Promise<{ profileData?: ProfileData } | null>;
  saveProfileData: (profileData: ProfileData) => Promise<{ profileData?: ProfileData } | null>;
  /** Optimistically update the in-memory user object without a server round-trip. */
  updateProfile: (updates: Partial<User>) => void;
  /** Merge partial profileData into the in-memory user without a server round-trip. */
  updateProfileData: (profileData: ProfileData) => void;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);
