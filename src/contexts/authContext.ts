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

/** Authenticated user data returned by GET /api/profile and POST /api/login. */
export interface User {
  id: string;
  email: string;
  name: string;
  role: "job-seeker" | "recruiter";
  profileComplete: boolean;
  profileData?: ProfileData;
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
  register: (email: string, password: string, name: string, role: "job-seeker" | "recruiter") => Promise<void>;
  logout: () => Promise<void>;
  fetchProfile: () => Promise<void>;
  fetchWithAuth: <T = any>(endpoint: string, options?: RequestInit) => Promise<T>;
  fetchProfileData: () => Promise<{ profileData?: ProfileData } | null>;
  saveProfileData: (profileData: ProfileData) => Promise<{ profileData?: ProfileData } | null>;
  /** Optimistically update the in-memory user object without a server round-trip. */
  updateProfile: (updates: Partial<User>) => void;
  /** Merge partial profileData into the in-memory user without a server round-trip. */
  updateProfileData: (profileData: ProfileData) => void;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);
