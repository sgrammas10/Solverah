import { useState, useEffect, ReactNode } from "react";

import { AuthContext, ProfileData, User } from "./authContext";
import { API_BASE as API_URL } from "../utils/api";


export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);

  // Restore session automatically using secure cookies
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_URL}/profile`, {
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

    const res = await fetch(`${API_URL}${endpoint}`, {
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
    const res = await fetch(`${API_URL}/login`, {
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
    const res = await fetch(`${API_URL}/register`, {
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


  const fetchProfile = async () => {
    const data = await fetchWithAuth<User>("/profile", { method: "GET" });
    setUser(data);
  };

  const fetchProfileData = async () => {
    const data = await fetchWithAuth<{ profileData?: ProfileData }>("/profile", { method: "GET" });
    return { profileData: data.profileData };
  };

  const saveProfileData = async (profileData: ProfileData) => {
    return await fetchWithAuth<{ profileData?: ProfileData }>("/profile", {
      method: "POST",
      body: JSON.stringify({ profileData }),
    });
  };
  const updateProfile = (updates: Partial<User>) => {
    setUser((prev) => (prev ? { ...prev, ...updates } : prev));
  };

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
