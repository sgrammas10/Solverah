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

import { AuthContext, ProfileData, User } from "./authContext";
import { API_BASE } from "../utils/api";


export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);

  // Restore session automatically using secure cookies
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/profile`, {
          method: "GET",
          credentials: "include",
        });

        if (res.ok) {
          const data = await res.json();
          setUser(data as User);
          // Read CSRF token from response body (cookie is inaccessible cross-origin)
          if (data.csrfToken) {
            setCsrfToken(data.csrfToken);
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
      throw new Error(data?.error || data?.message || "Request failed");
    }

    if (data === null) {
      throw new Error("Unexpected response from server (no JSON body).");
    }

    return data as T;
  };


  // LOGIN — backend sets an HttpOnly JWT cookie
  const login = async (email: string, password: string) => {
    const res = await fetch(`${API_BASE}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password }),
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || "Login failed");
    }

    const userData = data.user as User;
    setUser(userData);

    // Read CSRF token from response body (cookie is inaccessible cross-origin)
    if (data.csrfToken) {
      setCsrfToken(data.csrfToken);
    }

    return userData;
  };

  // REGISTER — then user logs in normally
  const register = async (
    email: string,
    password: string,
    name: string,
    role: "job-seeker" | "recruiter"
  ) => {
    const res = await fetch(`${API_BASE}/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password, name, role }),
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Registration failed");
  };

  // LOGOUT — clears cookie on backend
  const logout = async () => {
    try {
      await fetchWithAuth("/logout", { method: "POST" });
    } catch (e) {
      console.error(e);
    } finally {
      setUser(null);
      setCsrfToken(null);
    }
  };


  /** Refetch the full User object from the server and sync local state. */
  const fetchProfile = async () => {
    const data = await fetchWithAuth<User>("/profile", { method: "GET" });
    setUser(data);
  };

  /** Fetch only the profileData portion of the user's profile. */
  const fetchProfileData = async () => {
    const data = await fetchWithAuth<{ profileData?: ProfileData }>("/profile", { method: "GET" });
    return { profileData: data.profileData };
  };

  /** Persist updated profileData to the server (POST /api/profile). */
  const saveProfileData = async (profileData: ProfileData) => {
    return await fetchWithAuth<{ profileData?: ProfileData }>("/profile", {
      method: "POST",
      body: JSON.stringify({ profileData }),
    });
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
    register,
    logout,
    fetchProfile,
    fetchWithAuth,
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
